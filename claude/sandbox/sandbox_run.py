#!/usr/bin/env python3
"""
Cross-platform OS-level sandbox runner.

macOS:  sandbox-exec (Seatbelt) with a generated profile
Linux:  bwrap (bubblewrap) with --unshare-all + bind mounts
Other:  subprocess with env scrubbing (no real isolation; warns)

Goals (mirrors anthropic-experimental/sandbox-runtime):
  - Writes only allowed under CWD + /tmp
  - Reads denied for ~/.ssh, ~/.aws, ~/.config/gcloud, ~/.claude/secrets*
  - Network denied by default; --allow-network to opt in
  - Sensitive env vars scrubbed (ANTHROPIC_API_KEY, AWS_*, OPENAI_*, ...)

Usage:
  sandbox_run.py --cwd /tmp/work -- pytest -v
  sandbox_run.py --cwd . --allow-network -- npm install
  sandbox_run.py --cwd . --json -- ./script.sh   # output single JSON record
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SENSITIVE_ENV_PREFIXES = (
    "ANTHROPIC_",
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_",
    "OPENAI_",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "SENDGRID_",
    "STRIPE_",
    "TWILIO_",
    "DATADOG_",
    "SECRET_",
    "PRIVATE_KEY",
)
SENSITIVE_ENV_EXACT = {
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "API_KEY",
    "API_SECRET",
}

DENY_READ_PATHS = [
    str(Path.home() / ".ssh"),
    str(Path.home() / ".aws"),
    str(Path.home() / ".config" / "gcloud"),
    str(Path.home() / ".claude" / "mcp.json"),  # contains MCP creds
    str(Path.home() / ".claude" / "policy-limits.json"),
    str(Path.home() / ".claude" / "remote-settings.json"),
]


def scrub_env(allow_network: bool) -> dict:
    """Build a clean environment without sensitive vars."""
    clean: dict[str, str] = {}
    for k, v in os.environ.items():
        if any(k.startswith(p) for p in SENSITIVE_ENV_PREFIXES):
            continue
        if k in SENSITIVE_ENV_EXACT or any(s in k for s in ("SECRET", "PASSWORD", "TOKEN")):
            continue
        clean[k] = v
    # Force basic PATH if stripped
    if "PATH" not in clean:
        clean["PATH"] = "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"
    if not allow_network:
        clean["NO_NETWORK"] = "1"
    return clean


def make_macos_profile(cwd: str, allow_network: bool) -> str:
    """Generate a Seatbelt profile, return path."""
    deny_reads = "\n".join(
        f'  (deny file-read* (subpath "{p}"))'
        for p in DENY_READ_PATHS
        if Path(p).exists()
    )
    network_block = (
        "(allow network*)"
        if allow_network
        else "(deny network*)\n(allow network* (local ip))"  # localhost OK
    )
    cwd_canonical = os.path.realpath(cwd)
    profile = f"""(version 1)
; Defaults
(deny default)

; Process
(allow process-fork)
(allow process-exec)
(allow process-exec*)
(allow signal)

; IPC + system info
(allow ipc*)
(allow mach-lookup)
(allow sysctl-read)
(allow iokit-open)

; File reads — broad, but with deny-list overlay
(allow file-read*)
{deny_reads}

; File writes — restricted to CWD, /tmp, and per-user temp.
; macOS /var, /tmp, /etc are symlinks to /private/var, /private/tmp, /private/etc;
; the kernel sees the canonical path so we must allow both.
(deny file-write*)
(allow file-write* (subpath "{cwd}"))
(allow file-write* (subpath "{cwd_canonical}"))
(allow file-write* (subpath "/tmp"))
(allow file-write* (subpath "/private/tmp"))
(allow file-write* (subpath "/var/folders"))
(allow file-write* (subpath "/private/var/folders"))
(allow file-write* (literal "/dev/null"))
(allow file-write* (literal "/dev/stdout"))
(allow file-write* (literal "/dev/stderr"))
(allow file-write-data (regex #"/dev/fd/.*"))

; Network
{network_block}
"""
    fd, path = tempfile.mkstemp(suffix=".sb", prefix="sandbox-")
    with os.fdopen(fd, "w") as f:
        f.write(profile)
    return path


def run_macos(cmd: list[str], cwd: str, env: dict, allow_network: bool) -> dict:
    profile = make_macos_profile(cwd, allow_network)
    full = ["/usr/bin/sandbox-exec", "-f", profile] + cmd
    start = time.time()
    try:
        proc = subprocess.run(
            full, cwd=cwd, env=env, capture_output=True, text=True, timeout=600,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.time() - start) * 1000),
            "sandboxed": True,
            "sandbox_mechanism": "sandbox-exec",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "TIMEOUT after 600s",
            "duration_ms": int((time.time() - start) * 1000),
            "sandboxed": True,
            "sandbox_mechanism": "sandbox-exec",
            "timed_out": True,
        }
    finally:
        try:
            os.unlink(profile)
        except OSError:
            pass


def run_linux(cmd: list[str], cwd: str, env: dict, allow_network: bool) -> dict:
    if not shutil.which("bwrap"):
        return run_fallback(cmd, cwd, env, reason="bwrap-not-installed")
    bw = ["bwrap", "--die-with-parent", "--unshare-pid"]
    # Network: --share-net allows it; --unshare-net denies
    bw += ["--share-net"] if allow_network else ["--unshare-net"]
    # Bind essential ro paths
    for p in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"):
        if Path(p).exists():
            bw += ["--ro-bind", p, p]
    bw += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    bw += ["--bind", cwd, cwd]
    bw += ["--chdir", cwd]
    # Deny-listed reads: shadow them with empty tmpfs over their parent? Simpler:
    # block by env (HOME unset) and by not bind-mounting them into the namespace.
    bw += ["--unsetenv", "HOME"]
    bw += ["--"] + cmd

    start = time.time()
    try:
        proc = subprocess.run(
            bw, cwd=cwd, env=env, capture_output=True, text=True, timeout=600,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.time() - start) * 1000),
            "sandboxed": True,
            "sandbox_mechanism": "bwrap",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "TIMEOUT after 600s",
            "duration_ms": int((time.time() - start) * 1000),
            "sandboxed": True,
            "sandbox_mechanism": "bwrap",
            "timed_out": True,
        }


def run_fallback(cmd: list[str], cwd: str, env: dict, reason: str = "unsupported-platform") -> dict:
    """No real sandbox — just run with scrubbed env. Warn."""
    start = time.time()
    sys.stderr.write(
        f"[sandbox] WARNING: no isolation — {reason}. Env vars scrubbed but "
        "filesystem and network are not constrained.\n"
    )
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.time() - start) * 1000),
            "sandboxed": False,
            "sandbox_mechanism": f"none ({reason})",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1, "stdout": "", "stderr": "TIMEOUT",
            "duration_ms": int((time.time() - start) * 1000),
            "sandboxed": False, "sandbox_mechanism": "none",
            "timed_out": True,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="OS-level sandboxed command runner.")
    ap.add_argument("--cwd", required=True, help="Working directory (writable)")
    ap.add_argument("--allow-network", action="store_true",
                    help="Allow network egress (default: deny)")
    ap.add_argument("--json", action="store_true",
                    help="Print a single-line JSON record (default: pass through stdio)")
    ap.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="Command + args to run (after --)")
    args = ap.parse_args()

    if not args.cmd:
        sys.stderr.write("[sandbox] no command given. Usage: sandbox_run.py --cwd PATH -- CMD ARGS\n")
        return 2

    # Strip leading -- if present
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    cwd = os.path.abspath(args.cwd)
    if not os.path.isdir(cwd):
        sys.stderr.write(f"[sandbox] cwd does not exist: {cwd}\n")
        return 2

    env = scrub_env(args.allow_network)

    sysname = platform.system()
    if sysname == "Darwin":
        result = run_macos(cmd, cwd, env, args.allow_network)
    elif sysname == "Linux":
        result = run_linux(cmd, cwd, env, args.allow_network)
    else:
        result = run_fallback(cmd, cwd, env, reason=f"platform-{sysname}")

    result["command"] = cmd
    result["cwd"] = cwd
    result["allow_network"] = args.allow_network

    if args.json:
        print(json.dumps(result))
    else:
        sys.stdout.write(result.get("stdout", ""))
        sys.stderr.write(result.get("stderr", ""))

    return result.get("exit_code", 1)


if __name__ == "__main__":
    sys.exit(main())
