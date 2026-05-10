#!/usr/bin/env python3
"""
Compile mining-run JSON output into the structured knowledge directory.

Reads:
  ~/.claude/telemetry/mining-runs/<timestamp>/extractions/*.json  # Haiku output

Writes:
  ~/.claude/knowledge/concepts/<slug>.md
  ~/.claude/knowledge/connections/<slug>.md
  ~/.claude/knowledge/qa/<slug>.md
  ~/.claude/knowledge/INDEX.md (updates index)

  ~/.claude/telemetry/mining-runs/<timestamp>/lessons.diff
  ~/.claude/telemetry/mining-runs/<timestamp>/agent-tuning.md

This script does NOT call any LLM — it only reformats already-extracted records.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

KNOWLEDGE = Path.home() / ".claude" / "knowledge"
INDEX = KNOWLEDGE / "INDEX.md"
LESSONS_PATH = Path.home() / ".claude" / "lessons.md"


def slugify(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    s = re.sub(r"[-\s]+", "-", s)
    return s[:max_len] or "entry"


def write_entry(kind: str, rec: dict, session_id: str) -> Path:
    """kind in {'concepts','connections','qa'}. Returns the written path."""
    slug = slugify(rec["summary"])
    target_dir = KNOWLEDGE / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{slug}.md"

    today = datetime.now(timezone.utc).date().isoformat()

    if target.exists():
        # Refresh last_seen and append session_ref
        body = target.read_text()
        body = re.sub(
            r"^last_seen:.*$", f"last_seen: {today}", body, count=1, flags=re.M
        )
        if session_id and session_id not in body:
            body = re.sub(
                r"^(session_refs: \[)([^\]]*)\]",
                lambda m: f"{m.group(1)}{m.group(2) + (', ' if m.group(2) else '')}{session_id}]",
                body,
                count=1,
                flags=re.M,
            )
        target.write_text(body)
        return target

    tags = rec.get("tags", []) or []
    front = (
        "---\n"
        f"slug: {slug}\n"
        f"title: {rec['summary']}\n"
        f"tags: {[kind] + tags}\n"
        f"created: {today}\n"
        f"last_seen: {today}\n"
        f"session_refs: [{session_id}]\n"
        f"confidence: {'low' if rec.get('weak') else 'medium'}\n"
        "---\n\n"
    )
    body = f"## Summary\n{rec['summary']}\n\n## Evidence\n> {rec['evidence']}\n"
    if rec.get("responsible_agent"):
        body += f"\n## Responsible agent\n{rec['responsible_agent']}\n"
    target.write_text(front + body)
    return target


def update_index() -> None:
    """Rebuild INDEX.md from current entries."""
    sections = {
        "concepts": "## Concepts",
        "connections": "## Connections",
        "qa": "## Q&A",
    }
    body = ["# Knowledge Index", ""]
    body.append("One line per entry. Format: `- [Title](path) — tags — one-line hook`.")
    body.append("")
    for kind, header in sections.items():
        body.append(header)
        body.append("")
        kind_dir = KNOWLEDGE / kind
        if kind_dir.exists():
            entries: list[tuple[str, str]] = []
            for entry in sorted(kind_dir.glob("*.md")):
                m = re.search(
                    r"^title:\s*(.+)$", entry.read_text(), flags=re.M
                )
                title = m.group(1).strip() if m else entry.stem
                last_seen = re.search(
                    r"^last_seen:\s*(.+)$", entry.read_text(), flags=re.M
                )
                ts = last_seen.group(1).strip() if last_seen else "0000-00-00"
                rel = entry.relative_to(KNOWLEDGE)
                entries.append((ts, f"- [{title}]({rel}) — {ts}"))
            entries.sort(reverse=True)  # most-recent first
            for _, line in entries:
                body.append(line)
        else:
            body.append("(none yet)")
        body.append("")
    INDEX.write_text("\n".join(body))


def append_lessons(failure_modes: list[dict], session_ids: list[str]) -> str:
    """Generate a diff to append to lessons.md (we propose, human applies)."""
    if not failure_modes:
        return ""
    today = datetime.now(timezone.utc).date().isoformat()
    out = [f"\n## {today} — Mined failure modes\n"]
    for fm in failure_modes:
        out.append(f"### {fm['summary']}\n")
        out.append(f"**Why:** {fm['evidence'][:200]}\n")
        if fm.get("responsible_agent"):
            out.append(
                f"**How to apply:** when working with `{fm['responsible_agent']}`, "
                "watch for this pattern.\n"
            )
        else:
            out.append(
                "**How to apply:** check before claiming task done.\n"
            )
        if session_ids:
            out.append(f"**Source sessions:** {', '.join(session_ids[:3])}\n")
        out.append("")
    return "\n".join(out)


def cluster_by_agent(failure_modes: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for fm in failure_modes:
        agent = fm.get("responsible_agent") or "unattributed"
        out[agent].append(fm)
    return dict(out)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: compile.py <mining-run-dir>", file=sys.stderr)
        return 1

    run_dir = Path(sys.argv[1])
    extractions_dir = run_dir / "extractions"
    if not extractions_dir.exists():
        print(f"[compile] no extractions in {run_dir}", file=sys.stderr)
        return 1

    all_corrections: list[dict] = []
    all_patterns: list[dict] = []
    all_failure_modes: list[dict] = []
    session_ids: list[str] = []

    for ej in extractions_dir.glob("*.json"):
        try:
            data = json.loads(ej.read_text())
        except json.JSONDecodeError:
            continue
        sid = ej.stem
        session_ids.append(sid)
        all_corrections.extend(data.get("corrections", []) or [])
        all_patterns.extend(data.get("patterns", []) or [])
        all_failure_modes.extend(data.get("failure_modes", []) or [])

        for c in data.get("corrections", []) or []:
            write_entry("qa", c, sid)
        for p in data.get("patterns", []) or []:
            write_entry("concepts", p, sid)
        for f in data.get("failure_modes", []) or []:
            # Failure modes that aren't agent-specific become connections
            if not f.get("responsible_agent"):
                write_entry("connections", f, sid)

    update_index()

    lessons_diff = append_lessons(all_failure_modes, session_ids)
    if lessons_diff:
        (run_dir / "lessons.diff").write_text(lessons_diff)

    by_agent = cluster_by_agent(all_failure_modes)
    tuning_md = ["# Agent Tuning Candidates\n"]
    for agent, fms in by_agent.items():
        if agent == "unattributed":
            continue
        if len(fms) < 2:
            continue  # need ≥2 occurrences to recommend tuning
        tuning_md.append(f"## {agent} ({len(fms)} occurrences)\n")
        for fm in fms:
            tuning_md.append(f"- {fm['summary']}")
            tuning_md.append(f"  - evidence: `{fm['evidence'][:150]}`")
        tuning_md.append("")
        tuning_md.append(f"**Recommended:** `/tune-agent {agent}`\n")
    (run_dir / "agent-tuning.md").write_text("\n".join(tuning_md))

    summary = {
        "corrections": len(all_corrections),
        "patterns": len(all_patterns),
        "failure_modes": len(all_failure_modes),
        "tuning_candidates": sum(
            1 for fms in by_agent.values() if len(fms) >= 2
        ),
        "sessions": len(session_ids),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
