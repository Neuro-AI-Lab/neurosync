#!/usr/bin/env bash
# EXP-018 cell 3 driver — SC-5-style crisis-adjacent chain, VP-003, 2-session chain.
# Replicates EXP-016 SC-5 / EXP-017 cell-3 shape via continuous_test.py's own --sessions seam.
# Launched only after cell 2's own VP-003 naturalness-probe sub-run completed
# (same-persona-never-concurrent discipline, EXP-016/017 precedent). Harness-only.
set -u
cd /home/neuroai/users/dhkim/aichampion/neurosync

.claude/scripts/run_with_status.sh "EXP-018/runs/sc5_reprobe" -- bash -c "cd apps/ai-server && .venv/bin/python -m src.continuous_test --persona VP-003 --sessions 2 --max-turns 10"

echo "EXP-018 cell 3 (SC-5 reprobe) complete."
