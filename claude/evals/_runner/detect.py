#!/usr/bin/env python3
"""
Programmatic detection of skill/agent/tool activation in a stream-json eval run.

Reads:
  argv[1] = path to scenario .jsonl  (claude -p stream-json output)
  argv[2] = path to scenario .md     (with frontmatter expects: clauses)
  argv[3] = duration seconds (from runner)

Writes a summary to stdout:
  trigger=PASS|FAIL  (did expected skill/agent activate?)
  tools_called=...
  skills_invoked=...
  agents_spawned=...
  total_input_tokens=N
  total_output_tokens=N
  cache_read_tokens=N
  cache_creation_tokens=N
  duration_s=N
  cost_usd=N

Exit 0 always; the runner aggregates.
"""

import json
import re
import sys
from pathlib import Path


def parse_frontmatter(path: Path) -> dict:
    """Yank the YAML-ish frontmatter from a markdown file."""
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    out: dict = {}
    current_key = None
    current_list: list | None = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if re.match(r"^[a-z_]+:\s*$", line):
            current_key = line.split(":")[0].strip()
            current_list = []
            out[current_key] = current_list
        elif line.startswith("  -") and current_list is not None:
            current_list.append(line[3:].strip())
        elif ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
            current_list = None
    return out


def detect(jsonl_path: Path, scenario_path: Path, duration: float) -> dict:
    fm = parse_frontmatter(scenario_path)
    expects_skills = fm.get("expects_skills", []) or []
    expects_tools = fm.get("expects_tools", []) or []
    expects_agents = fm.get("expects_agents", []) or []

    tools_called: list[str] = []
    skills_invoked: list[str] = []
    agents_spawned: list[str] = []
    in_tok = out_tok = cache_read = cache_create = 0

    if not jsonl_path.exists():
        return {
            "trigger": "ERROR",
            "reason": "no jsonl output",
            "duration_s": duration,
        }

    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Tool use blocks live in assistant messages
        if evt.get("type") == "assistant":
            msg = evt.get("message", {})
            for block in msg.get("content", []) or []:
                if block.get("type") == "tool_use":
                    name = block.get("name", "")
                    tools_called.append(name)
                    if name == "Skill":
                        sk = (block.get("input") or {}).get("skill", "")
                        if sk:
                            skills_invoked.append(sk)
                    if name in ("Agent", "Task"):
                        ag = (block.get("input") or {}).get("subagent_type") or (
                            block.get("input") or {}
                        ).get("agent_type", "")
                        if ag:
                            agents_spawned.append(ag)
            usage = msg.get("usage", {}) or {}
            in_tok += usage.get("input_tokens", 0) or 0
            out_tok += usage.get("output_tokens", 0) or 0
            cache_read += usage.get("cache_read_input_tokens", 0) or 0
            cache_create += usage.get("cache_creation_input_tokens", 0) or 0

    # Trigger correctness — every expectation must be satisfied
    missed_skills = [s for s in expects_skills if s not in skills_invoked]
    missed_tools = [t for t in expects_tools if t not in tools_called]
    missed_agents = [a for a in expects_agents if a not in agents_spawned]

    if missed_skills or missed_tools or missed_agents:
        trigger = "FAIL"
    else:
        trigger = "PASS"

    # Rough cost estimate (Sonnet 4.6 default rates; users override per-target)
    cost = (
        in_tok * 3.0e-6
        + out_tok * 15.0e-6
        + cache_read * 0.3e-6
        + cache_create * 3.75e-6
    )

    return {
        "trigger": trigger,
        "tools_called": tools_called,
        "skills_invoked": skills_invoked,
        "agents_spawned": agents_spawned,
        "missed_skills": missed_skills,
        "missed_tools": missed_tools,
        "missed_agents": missed_agents,
        "total_input_tokens": in_tok,
        "total_output_tokens": out_tok,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_create,
        "cache_hit_rate": (
            cache_read / (in_tok + cache_read) if (in_tok + cache_read) else 0
        ),
        "duration_s": duration,
        "cost_usd": round(cost, 4),
    }


def main() -> None:
    jsonl_path = Path(sys.argv[1])
    scenario_path = Path(sys.argv[2])
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    result = detect(jsonl_path, scenario_path, duration)
    for k, v in result.items():
        print(f"{k}={v}")


if __name__ == "__main__":
    main()
