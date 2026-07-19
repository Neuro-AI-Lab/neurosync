#!/usr/bin/env bash
# EXP-014 r2 driver: sequential per-cell launch of the SM-01..08b safety-matrix
# regression through the run_with_status.sh wrapper, on the post-fix commit
# (4be9818, BUG-025 fix). Per ADR-025: full 11-cell re-run required, partial
# SM-06-only re-run is insufficient (the other 9 r1 passes do not transfer to
# the post-fix dialogue subsystem). Same harness/conventions as r1
# (run_sm_regression.sh), sequential to avoid vendor rate-limit contention.
set -u
cd /home/neuroai/users/dhkim/aichampion/neurosync

SCENARIOS=(SM-01 SM-02 SM-03 SM-04a SM-04b SM-05 SM-06 SM-07a SM-07b SM-08a SM-08b)

for sid in "${SCENARIOS[@]}"; do
  echo "=== [$(date -Is)] launching $sid (r2) ==="
  .claude/scripts/run_with_status.sh "EXP-014/runs/sm_regression_r2/$sid" -- \
    bash -c "cd apps/ai-server && .venv/bin/python -m src.safety_matrix --scenario $sid"
  RC=$?
  echo "=== [$(date -Is)] $sid exit_code=$RC ==="

  mkdir -p "experiments/EXP-014/runs/sm_regression_r2/$sid/artifacts"
  latest_json=$(ls -t "docs/ai/simulation_results/safety_matrix/${sid}_"*_result.json 2>/dev/null | head -1)
  latest_md=$(ls -t "docs/ai/simulation_results/safety_matrix/${sid}_"*_report.md 2>/dev/null | head -1)
  if [ -n "$latest_json" ]; then
    cp "$latest_json" "experiments/EXP-014/runs/sm_regression_r2/$sid/artifacts/"
  else
    echo "!!! [$sid] no result.json artifact found in docs/ai/simulation_results/safety_matrix/"
  fi
  if [ -n "$latest_md" ]; then
    cp "$latest_md" "experiments/EXP-014/runs/sm_regression_r2/$sid/artifacts/"
  fi
done

echo "=== [$(date -Is)] SM regression sweep r2 complete ==="
