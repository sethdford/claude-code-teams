# claude-code-teams

> A production-realistic, arXiv-grounded SOTA setup for Anthropic's Claude Code: native multi-agent orchestration, eval harness, RL-style reward telemetry, Reflexion-based prompt evolution, and seamless auto-firing hooks.

[![Smoke Test](https://github.com/sethdford/claude-code-teams/actions/workflows/smoke.yml/badge.svg)](https://github.com/sethdford/claude-code-teams/actions/workflows/smoke.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌐 **Site:** [sethdford.github.io/claude-code-teams](https://sethdford.github.io/claude-code-teams/) · 🏛️ [Architecture](https://sethdford.github.io/claude-code-teams/architecture.html) · 📚 [arXiv references](docs/arxiv-references.md)

## What this is

A drop-in upgrade for `~/.claude/` that gives you:

- **16 custom skills** — `/eval`, `/verify`, `/cache-report`, `/team`, `/spec`, `/mine-transcripts`, `/tune-agent`, `/best-of-n`, `/aspect-panel`, `/ab-test`, `/rl-status`, `/eval-author`, `/apply-mining-patches`, `/exec-grounded`, `/verify-ui`, `/scrum`
- **20 specialized agents** — verifier (sandbox-aware), critic, agent-tuner, spec-verifier, **product-owner, scrum-master, tech-lead, sprint-auditor**, plus 12 domain specialists
- **Full SCRUM team with adversarial audit** — `/scrum "<goal>"` runs all ceremonies (planning → wave execution → review → adversarial audit → retro). Sprint Auditor independently re-derives whether each AC was delivered, catches scope creep + drift + DoD violations. Demo proves NORMAL=PASS, BREAK-IT=FAIL with specific drift detection.
- **8 auto-firing hooks** — verifier auto-spawns on TaskCompleted, critic auto-runs before commit, eval auto-queues after agent edits, completion-claim phrases nudge `/verify`, cache stats logged at SessionEnd, knowledge entries injected at SessionStart
- **Eval harness** — programmatic + LLM-judge scoring with regression detection
- **RL infrastructure** — `rewards.jsonl`, per-agent `value/<agent>.json`, best-of-N test-time scaling with USC + confidence-weighted modes, Reflexion-based prompt evolution, A/B testing with reward gating
- **Execution-grounded Best-of-N** (Phase H, May 2026) — `/exec-grounded` runs N candidates in sandboxed copies, scores by ACTUAL test pass rate. Mirrors SWE-bench leader pattern (60-80% verification compute). Up to +10-20pp on SWE-bench-style tasks per published baselines.
- **OS-level sandbox** (Phase H) — `sandbox-exec` (macOS) / `bwrap` (Linux) with credential scrub, deny-list reads, write-only-CWD, network-deny-by-default. Used by verifier for any untrusted code.
- **Multi-modal UI verification** (Phase H) — `/verify-ui` with Mano-verify pattern (pre/post screenshots + intent → vision-LLM judge). Catches layout drift, missing elements, color regressions.
- **Skill auto-proposer** (Phase H, Voyager-style) — `/mine-transcripts` extension drafts NEW skill candidates from observed multi-step patterns (≥3 occurrences). Closes the autonomous-improvement loop.
- **Memory discipline** — A-MEM Zettelkasten linking, Zep-style temporal validity (`valid_from`, `superseded_by`)
- **Custom statusline** — live cache hit rate, model, cost, context %

## Why

Production Claude Code setups have orchestration but no measurement. This setup ships:

- **Cache hit rate telemetry** (Anthropic alerts on this internally per their engineering blog)
- **Verifier ≠ Critic** split (LangChain Reflection)
- **arXiv-grounded test-time scaling**: USC ([2311.17311](https://arxiv.org/abs/2311.17311)), confidence-weighted Best-of-N (ReConcile [2309.13007](https://arxiv.org/abs/2309.13007)), aspect-verifier panels (Lifshitz 2025)
- **Memory architecture from current research**: A-MEM ([2502.12110](https://arxiv.org/abs/2502.12110)), Zep ([2501.13956](https://arxiv.org/abs/2501.13956))
- **Reflexion** with version-controlled rollback ([Shinn 2024])
- **Native primitives only**: no Shipwright, no AutoGen, no MetaGPT — uses Claude Code's `Agent` tool, `Skill` tool, `TaskCreate`, hooks

## Compounding theory

```
Single-agent baseline
  + Best-of-N with critic
  + USC aggregation             (3-stream consensus)
  + Confidence weighting        (+11.4% per ReConcile)
  + Aspect verifiers            (orthogonal coverage)
  + Step-level signals          (Math-Shepherd-style)  [Tier 2, on demand]
  + Difficulty cascade          (~50% cost reduction)  [Tier 2, on demand]
  + Auto-fire hooks             (no prompting needed)
  = compounding 25-40% quality lift over baseline at lower cost
```

Each gain is small; stacked, they compound. See [`docs/architecture.md`](docs/architecture.md) and [`docs/arxiv-references.md`](docs/arxiv-references.md).

## Quick start

```bash
# Clone
git clone https://github.com/sethdford/claude-code-teams.git
cd claude-code-teams

# Inspect what you'd install
ls claude/

# Install (symlinks into ~/.claude/; idempotent; backs up existing files)
./install.sh

# Restart Claude Code (statusline + new hooks need fresh harness)

# Run the smoke test
./tests/smoke.sh

# Run real end-to-end proof (requires Claude Code + auth)
./tests/e2e/test-verifier.sh
```

## Prerequisites

- Claude Code v2.1.32+ (we use Agent Teams, modify-tool-input hooks, `--bare` mode, `--include-hook-events`)
- macOS / Linux (bash 3.2+)
- Python 3.9+ (used by hooks, RL scripts, eval runner)
- Optional: `ANTHROPIC_API_KEY` env var for `--bare` headless eval runs (otherwise falls back to subscription auth via `--setting-sources user`)

## Documentation

| Doc | Topic |
|---|---|
| [INSTALL.md](INSTALL.md) | Step-by-step install, including manual settings.json merge |
| [docs/architecture.md](docs/architecture.md) | Full architecture: components, data flow, design decisions |
| [docs/arxiv-references.md](docs/arxiv-references.md) | Every paper cited with one-line summary + where it's used |
| [docs/components.md](docs/components.md) | Per-skill / per-agent reference |
| [docs/runbook.md](docs/runbook.md) | Daily / weekly cadence |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to add skills, agents, scenarios |

## What this is NOT

- **Not RLHF / fine-tuning**. Pure prompt + context engineering. Reflexion is the policy update lever; A/B test is the gating lever.
- **Not a framework**. No Python package, no JS lib. Just a directory layout that Claude Code natively respects.
- **Not multi-round agent debate**. Per arXiv 2502.08788 ("Stop Overvaluing MAD"), multi-round debate is largely captured by best-of-N + USC; we do the latter.
- **Not vector-DB-backed**. At hundreds of memory entries, BM25/grep + curated markdown beats dense retrieval — see [`docs/architecture.md`](docs/architecture.md).

## Provenance

Built and validated 2026-05-10 against Claude Code 2.1.138. Synthesized from:
- 4 production research streams (Anthropic docs, Twitter/X, GitHub ecosystem, blogs)
- 4 arXiv research streams (agentic RL/PRMs, memory architectures, multi-agent debate, test-time scaling)

See [`docs/arxiv-references.md`](docs/arxiv-references.md) for the complete citation list.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Skills, agents, and eval scenarios are the primary contribution surfaces. See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions must include eval scenarios that demonstrate the addition's value.
