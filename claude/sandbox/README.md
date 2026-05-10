# Sandboxed Execution (Phase H2)

Cross-platform OS-level sandbox for running untrusted code from agents. Implements
the same security goals as Anthropic's `sandbox-runtime`:

- **Filesystem**: write only to a designated working directory + /tmp; deny writes elsewhere
- **Filesystem read deny-list**: `~/.ssh`, `~/.aws`, `~/.config/gcloud`, `~/.claude/secrets*`
- **Network**: denied by default; opt-in via `--allow-network`
- **Credentials**: never inherit `ANTHROPIC_API_KEY`, `AWS_*`, `GCP_*`, `OPENAI_*` from the parent env (the agent's own work shouldn't touch user creds)

## Implementation

| Platform | Mechanism |
|---|---|
| macOS (Darwin) | `sandbox-exec` (Seatbelt) with a generated profile |
| Linux | `bwrap` (bubblewrap) with bind-mounts and `--unshare-all` |
| Other | Fall back to subprocess with explicit env scrubbing (no real isolation; warn) |

## Usage

```bash
# Direct: run a command in CWD with no network
python3 ~/.claude/sandbox/sandbox_run.py --cwd /tmp/work -- pytest -v

# Allow network (e.g., for `pip install` or `curl`)
python3 ~/.claude/sandbox/sandbox_run.py --cwd /tmp/work --allow-network -- pip install requests

# Output: JSON line with exit code, stdout, stderr, duration, sandbox flag
```

## Output schema

```json
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "duration_ms": 1234,
  "sandboxed": true,
  "sandbox_mechanism": "sandbox-exec",
  "command": ["pytest", "-v"],
  "cwd": "/tmp/work",
  "allow_network": false
}
```

## Use from agents

The `verifier` agent uses this for every Bash invocation that runs untrusted test code.
The `/best-of-n --execution-grounded` mode uses this to verify each candidate.

For agents that must not bypass: the `verifier.md` prompt is updated to invoke
`sandbox_run.py` instead of raw `Bash`. The hook layer (TaskCompleted →
auto-verify-on-complete.sh) wraps in sandbox by default.

## Anti-patterns

- **Disabling sandbox to make a test pass.** If a test fails in sandbox but passes
  unsandboxed, the test depends on something being deny-listed (network, secret,
  out-of-CWD path). Fix the test's dependency, don't disable the sandbox.
- **Using `--allow-network` for everything.** Default-deny network is the
  highest-value isolation. Explicit allow only for the specific cases that need it.
- **Sandboxing read operations.** Sandboxing has overhead (~50-200ms cold). For
  read-only operations (Glob, Grep), don't bother — just read.
