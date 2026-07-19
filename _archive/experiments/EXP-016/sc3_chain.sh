#!/usr/bin/env bash
# SC-3 induced-truncation paired A/B replay driver (harness-only, no
# production code touched). For a given VP: runs 2 NEW F1 sessions with
# --max-turns 3 (slot-insufficiency inducer, deliberate/by-design per brief,
# not a defect), then replays EACH truncated F1 artifact through F2 once
# under Policy A and once under Policy B. All 6 calls per VP run strictly
# sequentially (same-VP-never-concurrent discipline, same reasoning as
# sc1_chain.sh/sc2_chain.sh). Different VPs may run concurrently.
# Usage: sc3_chain.sh <VP-ID>
set -uo pipefail
VP="$1"
BASE="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$BASE/apps/ai-server" || exit 97

OUT_DIR="$BASE/docs/ai/simulation_results/$VP"
OVERALL_RC=0

for rep in rep1 rep2; do
  echo "=== SC-3 $VP $rep F1(max-turns=3) start $(date -Is) ==="
  .venv/bin/python -m src.f1 --persona "$VP" --max-turns 3
  F1_RC=$?
  echo "F1 exit=$F1_RC ($VP $rep)"
  CONV=$(ls -t "$OUT_DIR"/*_conversation.json 2>/dev/null | head -1)
  echo "conversation_artifact=$CONV ($VP $rep)"
  if [ "$F1_RC" -ne 0 ] || [ -z "$CONV" ]; then
    echo "ABORT $rep: F1 failed or no conversation artifact found -- skipping F2 for $rep"
    OVERALL_RC=1
    continue
  fi

  for policy in A B; do
    echo "=== SC-3 $VP $rep policy=$policy F2 start $(date -Is) — conv=$CONV ==="
    .venv/bin/python -m src.f2 --conversation "$CONV" --rag-trigger-policy "$policy"
    rc=$?
    echo "F2 exit=$rc ($VP $rep policy=$policy)"
    [ "$rc" -ne 0 ] && OVERALL_RC=1
    DI=$(ls -t "$OUT_DIR"/*_domain_inference.json 2>/dev/null | head -1)
    echo "domain_inference_artifact=$DI ($VP $rep policy=$policy)"
    echo "=== SC-3 $VP $rep policy=$policy F2 DONE $(date -Is) ==="
  done
done

exit "$OVERALL_RC"
