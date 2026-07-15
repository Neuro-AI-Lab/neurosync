#!/usr/bin/env bash
# EXP-010 sub-run script — runs all 4 VPs x n=2 at a single fixed --k value.
# Usage: run_k.sh <k>
set -u
K="${1:?usage: run_k.sh <k>}"
REPO_ROOT="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$REPO_ROOT/apps/ai-server" || exit 1
export PROMPTS_BASE_DIR="$REPO_ROOT/docs/ai/prompts"

run_one () {
  local vp="$1" run="$2" input="$3"
  local outdir="$REPO_ROOT/experiments/EXP-010/runs/k${K}/$vp/$run"
  mkdir -p "$outdir"
  echo "=== k=$K $vp $run START $(date -Is) ==="
  .venv/bin/python -m src.f2 --conversation "$REPO_ROOT/$input" --k "$K" --out "$outdir" \
    > "$outdir/stdout.log" 2>&1
  echo "=== k=$K $vp $run END $(date -Is) exit=$? ==="
}

run_one VP-001 run1 "docs/ai/simulation_results/VP-001/VP-001_20260707_152922_conversation.json"
run_one VP-001 run2 "docs/ai/simulation_results/VP-001/VP-001_20260707_153451_conversation.json"
run_one VP-002 run1 "docs/ai/simulation_results/VP-002/VP-002_20260707_154130_conversation.json"
run_one VP-002 run2 "docs/ai/simulation_results/VP-002/VP-002_20260707_154407_conversation.json"
run_one VP-003 run1 "docs/ai/simulation_results/VP-003/VP-003_20260707_155149_conversation.json"
run_one VP-003 run2 "docs/ai/simulation_results/VP-003/VP-003_20260707_155446_conversation.json"
run_one VP-004 run1 "docs/ai/simulation_results/VP-004/VP-004_20260707_155542_conversation.json"
run_one VP-004 run2 "docs/ai/simulation_results/VP-004/VP-004_20260707_155625_conversation.json"

echo "=== k=$K ALL DONE $(date -Is) ==="
