#!/usr/bin/env python3
"""
Zep-style temporal validity for lessons.md.

Reference: Rasmussen et al. 2025 — Zep (arXiv 2501.13956).

Each lesson entry gets:
  - valid_from: ISO date when it became true
  - superseded_by: optional ref to the entry that replaced it
  - superseded_at: ISO date when superseded

When a new lesson contradicts an old one, mark the old as superseded — DON'T DELETE.
This preserves the "why did we change?" history. Filter superseded by default.

Usage:
  temporal_validity.py annotate <lesson-id> --supersedes <old-lesson-id>
  temporal_validity.py filter <lessons-file>      # print only valid (non-superseded)
  temporal_validity.py audit <lessons-file>       # report stale lessons (older than N days unchanged)

Lesson entry format (markdown headers as identity):
  ## YYYY-MM-DD — Title

  valid_from: YYYY-MM-DD
  superseded_by: <ref>      (optional)
  superseded_at: YYYY-MM-DD (optional)

  Body content...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LESSONS_PATH = Path.home() / ".claude" / "lessons.md"


def parse_lessons(path: Path) -> list[dict]:
    """Parse lessons.md into a list of entries with frontmatter-style metadata."""
    if not path.exists():
        return []
    text = path.read_text()
    entries: list[dict] = []
    # Split on `## YYYY-MM-DD — Title` headers
    chunks = re.split(r"^(?=## \d{4}-\d{2}-\d{2})", text, flags=re.M)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("## "):
            continue
        m = re.match(r"^## (\d{4}-\d{2}-\d{2})\s*—\s*(.+?)$", chunk.split("\n")[0])
        if not m:
            continue
        date = m.group(1)
        title = m.group(2).strip()
        # Pull metadata fields if present
        fm: dict = {"date": date, "title": title}
        for line in chunk.split("\n")[1:]:
            for key in ("valid_from", "superseded_by", "superseded_at"):
                m2 = re.match(rf"^\*\*{key}:\*\*\s*(.+)$", line, re.IGNORECASE)
                if m2:
                    fm[key] = m2.group(1).strip()
        fm["raw"] = chunk
        fm["id"] = f"{date}-{re.sub(r'[^a-z0-9]+', '-', title.lower())[:40]}"
        entries.append(fm)
    return entries


def filter_valid(entries: list[dict]) -> list[dict]:
    """Filter out superseded entries."""
    return [e for e in entries if not e.get("superseded_by")]


def annotate_supersede(lessons_path: Path, new_id: str, old_id: str) -> bool:
    """Mark old_id as superseded_by new_id. Returns True if found and modified."""
    if not lessons_path.exists():
        return False
    text = lessons_path.read_text()
    today = datetime.now(timezone.utc).date().isoformat()

    # Find the old entry by id (date+slugified title)
    entries = parse_lessons(lessons_path)
    for e in entries:
        if e["id"] == old_id:
            old_chunk = e["raw"]
            # If superseded_by already present, replace it; else inject after title
            if "**superseded_by:**" in old_chunk.lower():
                new_chunk = re.sub(
                    r"\*\*superseded_by:\*\*.*",
                    f"**superseded_by:** {new_id}",
                    old_chunk,
                    flags=re.IGNORECASE,
                )
                new_chunk = re.sub(
                    r"\*\*superseded_at:\*\*.*",
                    f"**superseded_at:** {today}",
                    new_chunk,
                    flags=re.IGNORECASE,
                )
            else:
                lines = old_chunk.split("\n", 1)
                head, body = lines[0], lines[1] if len(lines) > 1 else ""
                injection = f"\n**superseded_by:** {new_id}\n**superseded_at:** {today}\n"
                new_chunk = head + injection + body
            text = text.replace(old_chunk, new_chunk)
            lessons_path.write_text(text)
            return True
    return False


def audit_stale(entries: list[dict], days: int = 365) -> list[dict]:
    """Lessons older than N days that have no superseded_by are flagged for review."""
    now = datetime.now(timezone.utc).date()
    stale: list[dict] = []
    for e in entries:
        if e.get("superseded_by"):
            continue
        try:
            d = datetime.fromisoformat(e["date"]).date()
        except ValueError:
            continue
        age = (now - d).days
        if age >= days:
            stale.append({
                "id": e["id"],
                "title": e["title"],
                "date": e["date"],
                "age_days": age,
            })
    return stale


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_supersede = sub.add_parser("supersede")
    p_supersede.add_argument("--new", required=True)
    p_supersede.add_argument("--old", required=True)
    p_supersede.add_argument("--lessons", default=str(LESSONS_PATH))

    p_filter = sub.add_parser("filter")
    p_filter.add_argument("--lessons", default=str(LESSONS_PATH))

    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--lessons", default=str(LESSONS_PATH))
    p_audit.add_argument("--days", type=int, default=365)

    args = ap.parse_args()

    if args.cmd == "supersede":
        ok = annotate_supersede(Path(args.lessons), args.new, args.old)
        print(json.dumps({"superseded": ok, "old": args.old, "new": args.new}, indent=2))
        return 0 if ok else 1

    if args.cmd == "filter":
        entries = parse_lessons(Path(args.lessons))
        valid = filter_valid(entries)
        print(json.dumps([{"id": e["id"], "title": e["title"], "date": e["date"]} for e in valid], indent=2))
        return 0

    if args.cmd == "audit":
        entries = parse_lessons(Path(args.lessons))
        stale = audit_stale(entries, days=args.days)
        print(json.dumps({"stale_count": len(stale), "stale": stale}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
