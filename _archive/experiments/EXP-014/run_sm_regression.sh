#!/usr/bin/env bash
# EXP-014 driver: sequential per-cell launch of the SM-01..08b safety-matrix
# regression through the run_with_status.sh wrapper, one cell at a time
# (sequential to avoid vendor rate-limit contention on live Upstage calls).
# Each cell gets its own status.json + run.log under
# experiments/EXP-014/runs/sm_regression/<cell>/, and the canonical
# safety_matrix.py output artifacts are mirrored into that same directory.
set -u
cd /home/neuroai/users/dhkim/aichampion/neurosync

SCENARIOS=(SM-01 SM-02 SM-03 SM-04a SM-04b SM-05 SM-06 SM-07a SM-07b SM-08a SM-08b)

for sid in "${SCENARIOS[@]}"; do
  echo "=== [$(date -Is)] launching $sid ==="
  .claude/scripts/run_with_status.sh "EXP-014/runs/sm_regression/$sid" -- \
    bash -c "cd apps/ai-server && .venv/bin/python -m src.safety_matrix --scenario $sid"
  RC=$?
  echo "=== [$(date -Is)] $sid exit_code=$RC ==="

  mkdir -p "experiments/EXP-014/runs/sm_regression/$sid/artifacts"
  latest_json=$(ls -t "docs/ai/simulation_results/safety_matrix/${sid}_"*_result.json 2>/dev/null | head -1)
  latest_md=$(ls -t "docs/ai/simulation_results/safety_matrix/${sid}_"*_report.md 2>/dev/null | head -1)
  if [ -n "$latest_json" ]; then
    cp "$latest_json" "experiments/EXP-014/runs/sm_regression/$sid/artifacts/"
  else
    echo "!!! [$sid] no result.json artifact found in docs/ai/simulation_results/safety_matrix/"
  fi
  if [ -n "$latest_md" ]; then
    cp "$latest_md" "experiments/EXP-014/runs/sm_regression/$sid/artifacts/"
  fi
done

echo "=== [$(date -Is)] SM regression sweep complete ==="
