# Architecture

> The design rationale, data flow, and component map for claude-code-teams.

## High-level diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  USER prompt → Claude Code session                                │
└────────────────────────┬─────────────────────────────────────────┘
                         │
   ┌─────────────────────┼─────────────────────┐
   ▼                     ▼                     ▼
[SessionStart]    [UserPromptSubmit]    [PreToolUse: Bash]
knowledge inject  correction signal +    auto-critic on commit
                  completion-claim
                  detector

                         │
                         ▼
                  agent processes work
                         │
   ┌─────────────────────┼─────────────────────┐
   ▼                     ▼                     ▼
[PostToolUse]    [TaskCompleted]      [PreCompact]
auto-eval on     auto-verify +         compaction log
agent edit       reward emit

                         │
                         ▼
                   [SessionEnd]
              cache stats + value update

                         │
                         ▼
                  ~/.claude/rl/
              rewards.jsonl, value/, policy/

                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
   /tune-agent      /ab-test          /best-of-n
   Reflexion        promotion         test-time
   patches          gating            scaling
```

## Components

### Skills (`claude/skills/`)

13 user-and-assistant-invocable workflows. Each is a directory with `SKILL.md` (frontmatter + body).

| Skill | Layer | Purpose |
|---|---|---|
| `/eval` | Measurement | Test skill/agent triggers + quality scoring |
| `/eval-author` | Measurement | Generate scenario stubs |
| `/verify` | Gating | Spawn verifier agent |
| `/cache-report` | Telemetry | Cache hit-rate trends + anomalies |
| `/team` | Orchestration | Native multi-agent fleet |
| `/spec` | Process | Three-file spec workflow (Kiro-style) |
| `/mine-transcripts` | Learning | Trajectory miner — proposes diffs |
| `/apply-mining-patches` | Learning | Apply approved miner output |
| `/tune-agent` | Reflexion | Patch agent prompt from failure evidence |
| `/best-of-n` | Test-time RL | N rollouts + critic + USC + confidence-weighted |
| `/aspect-panel` | Verification | 5-aspect verifier panel |
| `/ab-test` | Policy | A/B variant comparison + promotion |
| `/rl-status` | Telemetry | Per-agent reward + value snapshot |

### Agents (`claude/agents/`)

16 specialized subagents. 4 core + 12 domain specialists.

**Core (4):**
- `verifier` — runs code, captures evidence; emits `RESULT_verifier=PASS|FAIL|INCONCLUSIVE`
- `critic` — adversarial reviewer, never edits; emits `RESULT_critic=CLEAN|HAS_FINDINGS_n_n`
- `agent-tuner` — Reflexion patcher; emits `RESULT_agent-tuner=PATCHED|...`
- `spec-verifier` — checks impl satisfies spec; emits `RESULT_spec-verifier=PASS|FAIL|...`

**Specialists (12):**
- `migration-planner`, `regression-hunter`, `flake-detector`, `dep-auditor`
- `cost-analyzer`, `docs-drift-checker`, `api-contract-watcher`, `latency-profiler`
- `dead-code-finder`, `error-budget-tracker`, `security-reviewer`, `accessibility-reviewer`

Each emits `RESULT_<agent-name>=<status>` on the last line so hooks can parse.

### Hooks (`claude/hooks/`)

8 scripts wired into 7 hook events in `settings.json`:

| Hook event | Script | What |
|---|---|---|
| SessionStart (startup\|resume) | `session-start-knowledge.sh` | Inject relevant knowledge entries |
| SessionStart (compact) | inline | Re-inject critical context post-compaction |
| PreCompact | inline | Log compaction event |
| SessionEnd | `log-cache-stats.sh` (→ `_log_cache_stats.py`) | Append cache-stats record + anomaly entry if hit rate <70% |
| SessionEnd | `emit_session_rewards.py` | Aggregate rewards by agent, recompute `value/<agent>.json` |
| TaskCompleted | `auto-verify-on-complete.sh` | Headlessly spawn verifier if no evidence; bypass on `trivial:` |
| TaskCompleted | `emit_task_reward.py` | Emit reward event from session JSONL |
| UserPromptSubmit | `emit_correction_signal.py` | Detect "no/wrong/instead" → emit -2.0 |
| UserPromptSubmit | `completion-claim-detector.sh` | Detect "I think it's done" → inject `/verify` reminder |
| PreToolUse (Bash) | `auto-critic-on-commit.sh` | On `git commit`: spawn critic on staged diff; CRITICAL → exit 2 |
| PostToolUse (Edit\|Write) | `auto-eval-on-agent-edit.sh` | On `agents/*.md` or `skills/*/SKILL.md` edit: queue debounced /eval |

### RL (`claude/rl/`)

```
rl/
├── rewards.jsonl                # append-only event log
├── preferences.jsonl            # (chosen, rejected) pairs (DPO format)
├── value/<agent>.json           # rolling reward statistics (V-function approx)
├── policy/<agent>/              # current/candidates/history/ab-runs/
│
├── emit_task_reward.py          # TaskCompleted hook
├── emit_correction_signal.py    # UserPromptSubmit hook
├── emit_session_rewards.py      # SessionEnd hook
│
├── best_of_n.py                 # 4 modes: critic, usc, confidence, hybrid
├── usc.py                       # Universal Self-Consistency
├── aspect_panel.py              # 5-aspect verifier panel
└── ab_test.py                   # A/B test current vs candidate
```

### Memory (`claude/knowledge/` + `claude/skills/mine-transcripts/`)

```
knowledge/
├── INDEX.md                     # master index (Karpathy-style)
├── concepts/<slug>.md           # durable patterns
├── connections/<slug>.md        # how things relate
└── qa/<slug>.md                 # specific Q&A

skills/mine-transcripts/
├── mine.py                      # filter session JSONL
├── compile.py                   # extract → write structured entries
├── zettelkasten.py              # A-MEM bidirectional linking
└── temporal_validity.py         # Zep-style valid_from/superseded_by
```

### Eval harness (`claude/evals/`)

```
evals/
├── _runner/
│   ├── run.sh                   # auth-aware claude -p invoker
│   ├── detect.py                # programmatic RESULT_/tool/agent detection
│   └── judge.md                 # LLM judge prompt
├── scenarios/<target>/<name>.md # frontmatter: prompt, expects_*, rubric
└── runs/<target>/<ts>/          # run outputs
```

## Data flow: a typical task

```
1. User sends prompt to Claude Code
   → UserPromptSubmit fires:
     - emit_correction_signal.py checks for negation patterns
     - completion-claim-detector.sh checks for "I think it's done"
   → If correction matched: -2.0 reward emitted to rewards.jsonl
   → If completion claim: nudge to /verify injected as additionalContext

2. Claude works (Read, Edit, Write, Bash, Agent calls)
   → PreToolUse(Bash) on `git commit`:
     - auto-critic-on-commit.sh spawns critic on staged diff
     - CRITICAL findings → exit 2 (block); HIGH → warn
   → PostToolUse(Edit|Write) on agent .md:
     - auto-eval-on-agent-edit.sh queues debounced /eval

3. Claude marks task complete (TaskCompleted hook)
   → auto-verify-on-complete.sh:
     - If RESULT_verifier=PASS in session: pass through
     - If FAIL/INCONCLUSIVE: surface, exit 2
     - If no evidence: spawn verifier headlessly via claude -p
       → produces RESULT_verifier=PASS|FAIL|INCONCLUSIVE
   → emit_task_reward.py:
     - Greps session JSONL for RESULT_<agent>=
     - Emits +1.0 / -1.0 / +0.5 / -0.5 events to rewards.jsonl

4. Claude continues or session ends (SessionEnd hook)
   → log-cache-stats.sh: append cache-stats record (with anomaly flag if <70%)
   → emit_session_rewards.py: aggregate per-agent, recompute value/<agent>.json
```

## Why these design choices

### Why prompt-only RL (no fine-tuning)?

We don't have weight access to Claude. The available levers are:
- **Reflexion** = prompt update via /tune-agent
- **Best-of-N + critic** = test-time scaling
- **A/B test + promotion** = policy gating
- **Reward modeling** = scoring future runs by past patterns

Each of these is API-compatible. Together they're the production-realistic RL stack for closed-source LLMs.

### Why markdown + grep instead of vector DB?

At hundreds-to-thousands of memory entries:
- BM25/grep is sub-ms latency, zero GPU cost, exact-match for technical content
- Curation quality dominates retrieval algorithm at small scale (per HippoRAG/Mem0/Zep papers)
- The real wins are write-time policy (A-MEM linking, Zep validity, Mem0 ADD/UPDATE classification) — these IMPROVE the index, not the lookup

See [arXiv 2501.01880 — Long Context vs RAG](https://arxiv.org/abs/2501.01880).

### Why aspect-panel instead of multi-round debate?

Per arXiv 2502.08788 ("Stop Overvaluing MAD") and 2509.05396 ("Talk Isn't Always Cheap"), multi-round debate at rounds 4+ measurably HURTS — group accuracy declines. The actual gain comes from:
- Heterogeneous personas (ChatEval 2308.07201)
- Confidence-weighted aggregation (ReConcile 2309.13007, Beyond Majority Voting 2510.01499)

Our `/aspect-panel` does both. We do NOT do multi-round debate.

### Why no hierarchical agent structure?

Per arXiv 2509.10769, hierarchical beats flat only at >10 agents. We have 22 agents but most invocations involve 3-5. Flat with a lead is correct.

## Limitations (honest)

1. **No fine-tuning** — Reflexion is a prompt-level operation. Real SOTA in academic terms requires weight access.
2. **Reward sparsity** — most tasks don't generate strong signal. Baseline +0.1 keeps the value function moving.
3. **Auto-verify cost** — every TaskCompleted with no prior evidence triggers ~$0.10 headless run. Mitigated by `trivial:` bypass.
4. **No cross-machine sync** — `~/.claude/rl/` is local. Future: sync via git or cloud.
5. **Reward hacking** — agents could in principle learn to skip work to avoid critic findings. Mitigation: verifier reward dominates and requires real PASS evidence in JSONL — can't fake.
6. **Subscription rate limits** — auto-firing hooks consume the same quota as manual usage. Set `ANTHROPIC_API_KEY` for `--bare` mode if you hit ceiling.

## Roadmap (Tier 2/3 deferred)

When the foundation has data (run for 30+ days), promote these from `docs/arxiv-references.md`:
- **Math-Shepherd MC step values** (process rewards) — `rl/process_rewards.py`
- **AB-MCTS adaptive branching** — extension to `best_of_n.py`
- **Difficulty-routed cascade** — Haiku-first, Opus-on-hard
- **MemGPT core memory + tool-driven page-in** — when knowledge/ exceeds 100 entries
- **TextGrad for compound pipelines** — when 3+ agent chains underperform
- **Training-Free GRPO frame for /tune-agent** — when ≥50 reward events accumulated
- **LATS for release-blocking calls** — opt-in for security/migration only
