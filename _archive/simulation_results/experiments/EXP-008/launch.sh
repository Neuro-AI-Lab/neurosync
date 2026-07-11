#!/usr/bin/env bash
# EXP-008 launch script — VP-003 n=2 + VP-001 n=2, RAG mode, genuinely new live LLM calls.
set -u
REPO_ROOT="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$REPO_ROOT/apps/ai-server" || exit 1
export PROMPTS_BASE_DIR="$REPO_ROOT/docs/ai/prompts"

run_one () {
  local vp="$1" run="$2" input="$3"
  local outdir="$REPO_ROOT/experiments/EXP-008/runs/$vp/$run"
  echo "=== $vp $run START $(date -Is) ==="
  .venv/bin/python -m src.f2 --conversation "$REPO_ROOT/$input" --out "$outdir" \
    > "$outdir/stdout.log" 2>&1
  echo "=== $vp $run END $(date -Is) exit=$? ==="
}

run_one VP-003 run1 "docs/ai/simulation_results/VP-003/VP-003_20260707_155149_conversation.json"
run_one VP-003 run2 "docs/ai/simulation_results/VP-003/VP-003_20260707_155446_conversation.json"
run_one VP-001 run1 "docs/ai/simulation_results/VP-001/VP-001_20260707_152922_conversation.json"
run_one VP-001 run2 "docs/ai/simulation_results/VP-001/VP-001_20260707_153451_conversation.json"

echo "=== ALL DONE $(date -Is) ==="
