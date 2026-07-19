#!/usr/bin/env bash
# SC-2 paired A/B replay driver (harness-only, no production code touched).
# Reuses the 8 SC-1 baseline F1 conversation.json artifacts (no new F1 run);
# for a given VP, replays BOTH of its SC-1 reps through F2 once under
# --rag-trigger-policy A and once under --rag-trigger-policy B, strictly
# sequentially (same-VP-never-concurrent discipline -- all 4 calls write
# into the same docs/ai/simulation_results/<VP>/ dir, so "ls -t" capture
# right after each call is unambiguous only if calls for one VP never
# overlap). Different VPs may run concurrently.
# Usage: sc2_chain.sh <VP-ID> <rep1_conversation_path> <rep2_conversation_path>
set -uo pipefail
VP="$1"
REP1_CONV="$2"
REP2_CONV="$3"
BASE="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$BASE/apps/ai-server" || exit 97

OVERALL_RC=0

for pair in "rep1:$REP1_CONV" "rep2:$REP2_CONV"; do
  rep="${pair%%:*}"
  conv="${pair#*:}"
  vp_dir=$(dirname "$conv")
  for policy in A B; do
    echo "=== SC-2 $VP $rep policy=$policy start $(date -Is) — conv=$conv ==="
    .venv/bin/python -m src.f2 --conversation "$conv" --rag-trigger-policy "$policy"
    rc=$?
    echo "F2 exit=$rc ($VP $rep policy=$policy)"
    [ "$rc" -ne 0 ] && OVERALL_RC=1
    di=$(ls -t "$vp_dir"/*_domain_inference.json 2>/dev/null | head -1)
    echo "domain_inference_artifact=$di ($VP $rep policy=$policy)"
    echo "=== SC-2 $VP $rep policy=$policy DONE $(date -Is) ==="
  done
done

exit "$OVERALL_RC"
