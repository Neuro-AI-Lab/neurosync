#!/usr/bin/env bash
# EXP-017 cell 1 driver — SM-01..08b regression bundle, sequential (matches EXP-014/r2 precedent).
# Harness-only; no production code touched.
set -u
cd /home/neuroai/users/dhkim/aichampion/neurosync

for sm in SM-01 SM-02 SM-03 SM-04a SM-04b SM-05 SM-06 SM-07a SM-07b SM-08a SM-08b; do
  .claude/scripts/run_with_status.sh "EXP-017/runs/sm/$sm" -- bash -c "cd apps/ai-server && .venv/bin/python -m src.safety_matrix --scenario $sm"
done

echo "EXP-017 cell 1 (SM bundle) complete."
