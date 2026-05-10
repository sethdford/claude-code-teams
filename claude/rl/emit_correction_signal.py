#!/usr/bin/env python3
"""
UserPromptSubmit hook: detect user corrections and emit negative reward.

Reads JSON event from stdin. If the user's prompt looks like a correction
(negation patterns, redirection language), emits a negative reward against
whichever agent was last active in the session.

This is RL signal collection — the actual reward score for the agent is small
(detection is heuristic, false positives common); the value lies in aggregating
many of these and feeding them into preferences.jsonl.

Always exits 0 — never blocks user input.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RL_DIR = Path.home() / ".claude" / "rl"
PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Regex patterns: each captures a likely correction-style user prompt.
# Tuned for high precision (low false positives) over recall.
CORRECTION_PATTERNS = [
    r"^\s*(no|stop|wait|wrong|not what)\b",
    r"\b(don'?t|do not)\s+(do|use|run|edit|delete|remove|add|change)",
    r"\b(that'?s|this is)\s+(wrong|incorrect|not right|broken)",
    r"\bi\s+(meant|wanted|need)\s+(?!to)",
    r"\bgo\s+back\b",
    r"\b(undo|revert|rollback)\b",
    r"\binstead\s+of\b.*",
    r"\bshould\s+(be|have|not)\b",
    r"\byou\s+(broke|broke it|missed|forgot)\b",
]


def is_correction(prompt: str) -> str | None:
    """Returns matched pattern key if prompt looks like a correction, else None."""
    if not prompt:
        return None
    lower = prompt.lower().strip()
    if len(lower) > 600:
        # Long prompts are usually new tasks, not corrections
        return None
    for pat in CORRECTION_PATTERNS:
        if re.search(pat, lower):
            return pat
    return None


def find_last_active_agent(session_id: str) -> str:
    """Walk the session JSONL backward to find the last-used Agent or skill."""
    if not session_id:
        return "session"
    matches = list(PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    if not matches:
        return "session"
    try:
        with matches[0].open() as f:
            lines = f.readlines()[-200:]
    except OSError:
        return "session"
    for line in reversed(lines):
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") != "assistant":
            continue
        content = (evt.get("message") or {}).get("content") or []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                name = b.get("name", "")
                if name in ("Agent", "Task"):
                    inp = b.get("input") or {}
                    return inp.get("subagent_type") or inp.get("agent_type") or "session"
                if name == "Skill":
                    inp = b.get("input") or {}
                    return f"skill:{inp.get('skill', 'unknown')}"
    return "session"


def main() -> int:
    try:
        e = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    prompt = e.get("prompt") or e.get("user_prompt") or e.get("text") or ""
    sid = e.get("session_id") or ""

    matched = is_correction(prompt)
    if not matched:
        return 0

    agent = find_last_active_agent(sid)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rec = {
        "ts": ts,
        "session_id": sid,
        "agent": agent,
        "source": "user_correction",
        "signal": "correction_detected",
        "reward": -2.0,
        "matched_pattern": matched,
        "prompt_excerpt": prompt[:300],
    }

    RL_DIR.mkdir(parents=True, exist_ok=True)
    with (RL_DIR / "rewards.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
