#!/usr/bin/env bash
# EXP-018 cell 2 driver — naturalness probe, 3 full F1 sessions (VP-001, VP-003, VP-010).
# Same probe configuration as EXP-017 cell 2, for before/after comparability. No production code touched.
set -u
cd /home/neuroai/users/dhkim/aichampion/neurosync

for vp in VP-001 VP-003 VP-010; do
  .claude/scripts/run_with_status.sh "EXP-018/runs/naturalness/$vp" -- bash -c "cd apps/ai-server && .venv/bin/python -m src.f1 --persona $vp --max-turns 10"
done

echo "EXP-018 cell 2 (naturalness probe) complete."
