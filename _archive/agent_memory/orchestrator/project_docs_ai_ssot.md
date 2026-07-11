---
name: project-docs-ai-ssot
description: neurosync live project state lives in docs/ai/ (DR-NNN reports), not the four root docs; root docs are gitignored
metadata:
  type: project
---

The live neurosync project record is `docs/ai/development_report.md` (DR-001..004 as of 2026-07-07), `docs/ai/PRD_task1_v2.md`, `docs/ai/checklist_task1.md`, and `docs/ai/vp_validation_scenarios.md` — NOT the four root docs, whose June-2026 entries predate the F1-pipeline era. **Why:** the repo's `.gitignore` (lines ~82-87) ignores `CLAUDE.md`, `result.md`, `discussion.md`, `error.md`, `version.md` and all of `.claude/` — root docs never reach git history; docs/ai/ does. **How to apply:** ground mission briefs in docs/ai/ paths; still maintain PLAN/ADR/STATE in discussion.md for in-session state, but treat DR-NNN as the durable record that commits reference. Related: [[routing-prompt-rewrite-missions]].

Other durable facts (verified 2026-07-07): runtime prompts load from `docs/ai/prompts/{agent}/vN.system.md` via PromptLoader; version pins are constants in `apps/ai-server/src/agents/*.py` (+ `routes/chat.py`); active LLM agents are safety_classifier, dialogue, clinical_slot, handoff_generator, sentiment_analyzer — the rest are orphan/rule-based. Suite invocation: `cd apps/ai-server && .venv/bin/python -m pytest -q`.
