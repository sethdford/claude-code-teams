# arXiv References

Every academic paper used to design or justify a component, with a one-line summary and where it's used.

## Test-time scaling

| arXiv | Title | Used in |
|---|---|---|
| [2311.17311](https://arxiv.org/abs/2311.17311) | Universal Self-Consistency for Large Language Model Generation (Chen et al. 2023) | `rl/usc.py`; `best_of_n.py --mode usc/hybrid` |
| [2309.13007](https://arxiv.org/abs/2309.13007) | ReConcile: Round-Table Conference (Chen et al. 2024, ACL) — confidence-weighted voting +11.4% | `best_of_n.py --mode confidence/hybrid` |
| [2310.04406](https://arxiv.org/abs/2310.04406) | LATS: Language Agent Tree Search (Zhou et al. 2024, ICML) | Tier 3 (deferred) |
| [2503.04412](https://arxiv.org/abs/2503.04412) | AB-MCTS: Adaptive Branching | Tier 3 (deferred) |
| [2408.03314](https://arxiv.org/abs/2408.03314) | Compute-Optimal Test-Time (Snell et al. 2024) | Difficulty-routed cascade design (Tier 2) |
| [2406.18665](https://arxiv.org/abs/2406.18665) | RouteLLM (Ong et al. 2024) | Difficulty-routed cascade design |
| [2404.01054](https://arxiv.org/abs/2404.01054) | MBR-BoN: Regularized Best-of-N | Tier 2 (deferred) |
| [2501.19393](https://arxiv.org/abs/2501.19393) | s1: Simple Test-Time Scaling — budget forcing | Compatible with Anthropic extended thinking |

## Process rewards / agentic RL

| arXiv | Title | Used in |
|---|---|---|
| [2305.20050](https://arxiv.org/abs/2305.20050) | Let's Verify Step by Step (Lightman et al. 2023, OpenAI PRM800K) | Math-Shepherd MC step values (Tier 2) |
| [2312.08935](https://arxiv.org/abs/2312.08935) | Math-Shepherd (Wang et al., DeepSeek 2023) | Tier 2 deferred — process_rewards.py future module |
| [2412.06559](https://arxiv.org/abs/2412.06559) | ProcessBench (Qwen team, 2024) — prompted critics often beat trained PRMs OOD | Cited as reason we DON'T train PRMs |
| [2402.03300](https://arxiv.org/abs/2402.03300) | DeepSeekMath / GRPO (Shao et al. 2024) | Group-relative scoring concept |
| [2410.01679](https://arxiv.org/abs/2410.01679) | VinePPO (Kazemnejad et al. 2025, ICML) | Math-Shepherd MC trick |
| [2510.08191](https://arxiv.org/abs/2510.08191) | Training-Free GRPO (2025) | Tier 2 — formalized Reflexion frame |

## Reflexion / prompt optimization

| arXiv | Title | Used in |
|---|---|---|
| [2303.11366](https://arxiv.org/abs/2303.11366) | Reflexion (Shinn et al. 2023) | `agent-tuner.md`, `/tune-agent` skill |
| [2303.17651](https://arxiv.org/abs/2303.17651) | Self-Refine (Madaan et al. 2023) | Caveat — only with verifier (per Huang ICLR 2024) |
| [2309.03409](https://arxiv.org/abs/2309.03409) | OPRO (Yang et al. 2023, DeepMind) | Tier 3 — A/B variant generation |
| [2309.16797](https://arxiv.org/abs/2309.16797) | Promptbreeder (Fernando et al. 2023) | Tier 3 — superseded by OPRO + Training-Free GRPO at our scale |
| [2406.07496](https://arxiv.org/abs/2406.07496) | TextGrad (Yuksekgonul et al. 2024) | Tier 3 — for compound multi-agent pipelines |
| [2310.03714](https://arxiv.org/abs/2310.03714) | DSPy (Khattab et al. 2023) | Tier 3 alternative |

## Multi-agent / debate

| arXiv | Title | Used in |
|---|---|---|
| [2305.14325](https://arxiv.org/abs/2305.14325) | MAD: Multi-Agent Debate (Du et al. 2023) | Cited as PARTIALLY adopted (heterogeneous personas, not rounds) |
| [2308.07201](https://arxiv.org/abs/2308.07201) | ChatEval (Chan et al. 2023) — heterogeneous personas matter | `aspect_panel.py` design |
| [2310.02170](https://arxiv.org/abs/2310.02170) | DyLAN: Dynamic Agent Network | Cited as Tier 2 idea (importance pruning) |
| Lifshitz 2025 | Multi-Agent Verification (MAV) | `aspect_panel.py` core |
| [2510.01499](https://arxiv.org/abs/2510.01499) | Beyond Majority Voting (2025) | Confidence-weighted aggregation in `aspect_panel.py` |
| [2502.19130](https://arxiv.org/abs/2502.19130) | Voting or Consensus? (2025) | Voting for objective tasks, consensus for subjective |
| [2502.08788](https://arxiv.org/abs/2502.08788) | **Stop Overvaluing Multi-Agent Debate** (2025) | Cited as reason we DON'T add multi-round debate |
| [2509.05396](https://arxiv.org/abs/2509.05396) | Talk Isn't Always Cheap (2025) — debate amplifies errors | Same — caveat against rounds |
| [2509.10769](https://arxiv.org/abs/2509.10769) | AgentArch (2025) | Cited as reason we DON'T add hierarchical at our scale (≤10 agents) |

## Memory architectures

| arXiv | Title | Used in |
|---|---|---|
| [2310.08560](https://arxiv.org/abs/2310.08560) | MemGPT (Packer et al. 2023, ICLR 2024) | Tier 2 deferred — core memory + paging |
| [2405.14831](https://arxiv.org/abs/2405.14831) | HippoRAG (Gutiérrez et al. 2024, NeurIPS) | Awk-graph-walk over connections (50-line equivalent) |
| [2502.14802](https://arxiv.org/abs/2502.14802) | HippoRAG 2 (2025) | Same |
| [2501.13956](https://arxiv.org/abs/2501.13956) | Zep / Graphiti (Rasmussen et al. 2025) | `temporal_validity.py` — `valid_from`, `superseded_by` |
| [2504.19413](https://arxiv.org/abs/2504.19413) | Mem0 / Mem0g (Chhikara et al. 2025, ECAI) | ADD/UPDATE/MERGE/DELETE classification (used in `compile.py`) |
| [2502.12110](https://arxiv.org/abs/2502.12110) | A-MEM: Agentic Memory (Xu et al. 2025, NeurIPS) | `zettelkasten.py` — bidirectional linking |
| [2507.07957](https://arxiv.org/abs/2507.07957) | MIRIX (Wang & Chen 2025) | Architectural inspiration; six-type taxonomy maps to our subdirs |
| [2501.01880](https://arxiv.org/abs/2501.01880) | Long Context vs RAG (Li et al. 2025) | Cited as reason we DON'T migrate to "stuff in 1M Claude" |
| [2410.10813](https://arxiv.org/abs/2410.10813) | LongMemEval (ICLR 2025) | Reference benchmark for memory eval |

## Self-correction caveats

| arXiv | Title | Used in |
|---|---|---|
| ICLR 2024 (Huang et al.) | LLMs Cannot Self-Correct Reasoning Yet | Caveat: Self-Refine without verifier is dangerous; we ALWAYS pair with verifier |
| [2407.18418](https://arxiv.org/abs/2407.18418) | Know-Your-Limits (abstention survey) | Reference for future abstention work |
| [2405.01563](https://arxiv.org/abs/2405.01563) | Conformal Abstention (2024) | Tier 3 — abstention for verifier |

## Anthropic engineering posts (not arXiv but loadbearing)

- [Lessons from building Claude Code: Prompt caching is everything](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything) — SEV on cache hit rate. Justifies `cache-report` skill.
- [Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) — infra-heavy, AI-light philosophy.
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) — lead Opus + Sonnet specialists +90.2% over single Opus.
- [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — Skills as filesystem-resident capability packs.
- [Subagents in Claude Code](https://claude.com/blog/subagents-in-claude-code) — official subagent docs.
