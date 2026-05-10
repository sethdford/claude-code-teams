# Structured Knowledge Index

This directory holds long-form persistent knowledge built up over time. It's the "Karpathy index" pattern: a curated, human-readable index that an LLM can read and navigate, which beats vector retrieval at our scale (thousands of entries, not millions).

## Layout

```
knowledge/
├── INDEX.md             # the master index — every entry has one line here
├── concepts/<slug>.md   # durable concepts (architectural decisions, mental models)
├── connections/<slug>.md # observations about how things relate (X depends on Y; A causes B)
├── qa/<slug>.md         # specific Q&A pairs from past sessions
└── _build/              # mining-time artifacts; safe to delete
```

## How entries are written

Manually or by `/mine-transcripts` running through `compile.py`.

Each entry frontmatter:
```yaml
---
slug: short-kebab-name
title: One-line title
tags: [concept | connection | qa, ...domain-tags]
created: 2026-05-10
last_seen: 2026-05-10       # last time this was relevant in a session
session_refs: [<id>, ...]
confidence: high | medium | low
---
```

## How retrieval works

`session-start-context.sh` reads `INDEX.md`, picks the top-N entries by tag-match against the current cwd / project, and injects them as additional context. The full entry body is loaded only if the index hit warrants it.

## How pruning works

Weekly: `/consolidate-memory` reads INDEX.md, merges duplicates, demotes entries with low `last_seen` recency, archives obsolete ones to `_archive/`.

## What does NOT belong here

- Project-specific code conventions (use project `CLAUDE.md`)
- Anything in `git log` or `git blame`
- Anything that's already in the project's docs
- Ephemeral state (in-progress work, debugging snapshots)

If you can read it from the codebase in 10 seconds, it doesn't need to be here.
