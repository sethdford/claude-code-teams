#!/usr/bin/env python3
"""
Trajectory miner — pre-filters JSONL session transcripts and prepares them for
Haiku extraction.

Usage:
  mine.py --since 7d          # mine last 7 days of sessions
  mine.py --session <uuid>    # mine one specific session
  mine.py --dry-run           # show what would be mined, no extraction

Designed to be invoked by the /mine-transcripts skill. The skill orchestrates
the Haiku invocation; this script handles the boring filesystem + parsing work.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
TELEMETRY_DIR = Path.home() / ".claude" / "telemetry" / "mining-runs"
PROCESSED_LOG = TELEMETRY_DIR / ".processed.jsonl"

INTERESTING_USER_KEYWORDS = (
    "no",
    "stop",
    "wait",
    "actually",
    "instead",
    "don't",
    "wrong",
    "should be",
    "not what",
    "i meant",
    "go back",
)


def parse_since(s: str) -> datetime:
    """Parse '7d', '24h', '30m', or ISO date — return cutoff datetime in UTC."""
    s = s.strip().lower()
    now = datetime.now(timezone.utc)
    if s.endswith("d"):
        return now - timedelta(days=int(s[:-1]))
    if s.endswith("h"):
        return now - timedelta(hours=int(s[:-1]))
    if s.endswith("m"):
        return now - timedelta(minutes=int(s[:-1]))
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def already_processed(session_path: Path) -> bool:
    if not PROCESSED_LOG.exists():
        return False
    target = str(session_path.resolve())
    with PROCESSED_LOG.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("path") == target and (
                time.time() - rec.get("ts", 0) < 86400
            ):  # within 24h
                return True
    return False


def mark_processed(session_path: Path, signal_count: int) -> None:
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    with PROCESSED_LOG.open("a") as f:
        f.write(
            json.dumps(
                {
                    "path": str(session_path.resolve()),
                    "ts": int(time.time()),
                    "signal_count": signal_count,
                }
            )
            + "\n"
        )


def find_sessions(cutoff: datetime) -> list[Path]:
    out: list[Path] = []
    if not PROJECTS_DIR.exists():
        return out
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            # Skip subagent sidechains
            if jsonl.name.startswith("agent-"):
                continue
            try:
                mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < cutoff:
                continue
            if jsonl.stat().st_size < 2048:  # too small, probably empty
                continue
            out.append(jsonl)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def filter_chunk(jsonl_path: Path, max_tokens: int = 50_000) -> str:
    """
    Read a session transcript and extract events that likely contain signal.
    Returns a single string (filtered JSONL) ready to feed into Haiku.

    Heuristic: keep user messages that look like corrections, plus the
    immediately-preceding assistant turn. Drop tool_result blobs and
    file-history-snapshot records (they're huge and rarely have signal).
    """
    keep: list[str] = []
    last_assistant: str | None = None

    with jsonl_path.open() as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = evt.get("type")
            if etype == "file-history-snapshot":
                continue
            if etype == "queue-operation":
                continue

            if etype == "assistant":
                msg = evt.get("message", {})
                # Compress: keep only text blocks, drop tool_use detail
                content = msg.get("content", []) or []
                text_parts: list[str] = []
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            text_parts.append(b.get("text", ""))
                if text_parts:
                    last_assistant = json.dumps(
                        {
                            "type": "assistant",
                            "uuid": evt.get("uuid"),
                            "text": "\n".join(text_parts)[:1500],
                        }
                    )
                continue

            if etype == "user":
                msg = evt.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    text = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )
                else:
                    text = str(content)
                lower = text.lower()
                interesting = any(kw in lower for kw in INTERESTING_USER_KEYWORDS)
                # Always keep first 200 chars of user messages — short ones are easy to score
                interesting = interesting or len(text) < 200

                if interesting:
                    if last_assistant:
                        keep.append(last_assistant)
                        last_assistant = None
                    keep.append(
                        json.dumps(
                            {
                                "type": "user",
                                "uuid": evt.get("uuid"),
                                "text": text[:1500],
                            }
                        )
                    )

    out = "\n".join(keep)
    # Truncate if still too big (rough proxy: 4 bytes ~= 1 token)
    if len(out) > max_tokens * 4:
        out = out[: max_tokens * 4]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="7d", help="Cutoff (e.g. 7d, 24h, ISO date)")
    ap.add_argument("--session", help="Mine one specific session UUID instead")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", help="Output directory (default: timestamped)")
    args = ap.parse_args()

    cutoff = parse_since(args.since)
    sessions = find_sessions(cutoff)

    if args.session:
        sessions = [p for p in sessions if args.session in p.name]
        if not sessions:
            print(f"[mine] no session matching {args.session}", file=sys.stderr)
            return 1

    if not sessions:
        print(f"[mine] no sessions since {cutoff.isoformat()}", file=sys.stderr)
        return 0

    sessions = [s for s in sessions if not already_processed(s)]
    print(
        f"[mine] {len(sessions)} sessions to mine (since {args.since})",
        file=sys.stderr,
    )

    if args.dry_run:
        for s in sessions[:50]:
            print(s)
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else TELEMETRY_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    for s in sessions:
        chunk = filter_chunk(s)
        if not chunk.strip():
            continue
        target = out_dir / f"{s.stem}.filtered.jsonl"
        target.write_text(chunk)
        # signal_count gets updated after Haiku extraction by the orchestrating skill
        mark_processed(s, signal_count=0)

    manifest = {
        "timestamp": timestamp,
        "since": args.since,
        "session_count": len(sessions),
        "out_dir": str(out_dir),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[mine] wrote {len(sessions)} filtered chunks to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
