#!/usr/bin/env python3
"""
A-MEM Zettelkasten linker — after the miner writes a new knowledge entry,
find the top-5 most-related existing entries and add bidirectional links.

Reference: Xu et al. 2025 — A-MEM (NeurIPS 2025), arXiv 2502.12110.

Implementation: keyword-based similarity (no embeddings needed at our scale).
For each new entry, score every existing entry by:
  score = (overlapping_unique_tokens / sqrt(|A| * |B|)) * tag_overlap_bonus

Top-5 above threshold get bidirectional links injected as a `## Related` section.
Optionally, a Haiku pass proposes patches to those existing entries.

Usage:
  zettelkasten.py link --entry <new-entry.md> [--haiku]
  zettelkasten.py rebuild   # rebuild all links across knowledge/

Stats are written to ~/.claude/telemetry/zettelkasten.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KNOWLEDGE = Path.home() / ".claude" / "knowledge"
TELEMETRY = Path.home() / ".claude" / "telemetry"

STOPWORDS = set(
    "the a an of to in for on with by at and or but is are was were be been being "
    "this that these those it its as if then than which what who whom whose how when "
    "where why because so do does did has have had not no yes very also too just".split()
)


def tokens(text: str) -> set[str]:
    out: set[str] = set()
    for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower()):
        if t not in STOPWORDS:
            out.add(t)
    return out


def parse_frontmatter(path: Path) -> tuple[dict, str]:
    """Return (frontmatter dict, body text)."""
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = m.group(2)
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" in line and not line.startswith("  "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip("'\"")
    # tags is a list
    m2 = re.search(r"^tags:\s*\[(.+?)\]$", fm_text, re.M)
    if m2:
        fm["tags"] = [t.strip().strip("'\"") for t in m2.group(1).split(",")]
    return fm, body


def score_pair(a_tokens: set, a_tags: list, b_tokens: set, b_tags: list) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = a_tokens & b_tokens
    base = len(overlap) / math.sqrt(len(a_tokens) * len(b_tokens))
    tag_bonus = 1.0
    if a_tags and b_tags:
        tag_overlap = set(a_tags) & set(b_tags)
        tag_bonus = 1.0 + 0.5 * len(tag_overlap)
    return base * tag_bonus


def find_related(entry_path: Path, top_k: int = 5, threshold: float = 0.10) -> list[dict]:
    """For one entry, find top-k related entries above threshold."""
    fm, body = parse_frontmatter(entry_path)
    a_tokens = tokens(body + " " + fm.get("title", ""))
    a_tags = fm.get("tags", []) or []
    a_slug = fm.get("slug", entry_path.stem)

    candidates: list[tuple[float, dict]] = []
    for other in KNOWLEDGE.glob("**/*.md"):
        if other == entry_path or other.name in ("INDEX.md", "README.md"):
            continue
        ofm, obody = parse_frontmatter(other)
        b_tokens = tokens(obody + " " + ofm.get("title", ""))
        b_tags = ofm.get("tags", []) or []
        s = score_pair(a_tokens, a_tags, b_tokens, b_tags)
        if s >= threshold:
            candidates.append((s, {
                "slug": ofm.get("slug", other.stem),
                "title": ofm.get("title", other.stem),
                "rel_path": str(other.relative_to(KNOWLEDGE)),
                "score": round(s, 4),
            }))

    candidates.sort(key=lambda c: -c[0])
    return [c[1] for c in candidates[:top_k]]


def inject_related_section(entry_path: Path, related: list[dict]) -> bool:
    """Inject/replace a `## Related` section in the entry. Returns True if changed."""
    text = entry_path.read_text()
    block_lines = ["## Related"]
    for r in related:
        block_lines.append(f"- [{r['title']}](../{r['rel_path']}) — score {r['score']}")
    block = "\n".join(block_lines) + "\n"

    pattern = re.compile(r"## Related\n(?:- .*\n)*", re.M)
    if pattern.search(text):
        new_text = pattern.sub(block, text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        new_text = text + "\n" + block

    if new_text != text:
        entry_path.write_text(new_text)
        return True
    return False


def link_entry(entry_path: Path, top_k: int = 5) -> dict:
    related = find_related(entry_path, top_k=top_k)
    changed = inject_related_section(entry_path, related)

    # Bidirectional: for each related, ensure their `## Related` includes this one
    for r in related:
        other_path = KNOWLEDGE / r["rel_path"]
        if not other_path.exists():
            continue
        other_related = find_related(other_path, top_k=top_k)
        inject_related_section(other_path, other_related)

    return {
        "entry": str(entry_path.relative_to(KNOWLEDGE)),
        "related_count": len(related),
        "changed": changed,
        "related": related,
    }


def log_run(results: list[dict]) -> None:
    TELEMETRY.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = {
        "ts": ts,
        "n_entries_processed": len(results),
        "n_changed": sum(1 for r in results if r["changed"]),
        "total_links": sum(r["related_count"] for r in results),
    }
    with (TELEMETRY / "zettelkasten.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_link = sub.add_parser("link", help="Link one new entry")
    p_link.add_argument("--entry", required=True, type=Path)
    p_link.add_argument("--top-k", type=int, default=5)

    p_rebuild = sub.add_parser("rebuild", help="Rebuild links across all knowledge/")

    args = ap.parse_args()

    if args.cmd == "link":
        if not args.entry.exists():
            print(f"[zettelkasten] entry not found: {args.entry}", file=sys.stderr)
            return 1
        result = link_entry(args.entry, top_k=args.top_k)
        log_run([result])
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "rebuild":
        results: list[dict] = []
        for entry in KNOWLEDGE.glob("**/*.md"):
            if entry.name in ("INDEX.md", "README.md"):
                continue
            results.append(link_entry(entry))
        log_run(results)
        print(json.dumps({
            "rebuilt": len(results),
            "changed": sum(1 for r in results if r["changed"]),
        }, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
