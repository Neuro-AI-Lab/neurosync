#!/usr/bin/env bash
# SC-3b Policy-B judge-stability driver (harness-only, no production code
# touched). 3 identical-input repeats against the SAME conversation.json,
# each a fresh --rag-trigger-policy B F2 call (which makes exactly one
# RagTriggerJudgeAgent call per invocation, plus the usual domain_inference
# call). Strictly sequential (same-VP-never-concurrent discipline -- all 3
# calls write into the same docs/ai/simulation_results/<VP>/ dir).
# Usage: sc3b_chain.sh <VP-ID> <conversation_path>
set -uo pipefail
VP="$1"
CONV="$2"
BASE="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$BASE/apps/ai-server" || exit 97

OUT_DIR=$(dirname "$CONV")
OVERALL_RC=0

for i in 1 2 3; do
  echo "=== SC-3b $VP repeat=$i policy=B start $(date -Is) — conv=$CONV ==="
  .venv/bin/python -m src.f2 --conversation "$CONV" --rag-trigger-policy B
  rc=$?
  echo "F2 exit=$rc ($VP repeat=$i)"
  [ "$rc" -ne 0 ] && OVERALL_RC=1
  DI=$(ls -t "$OUT_DIR"/*_domain_inference.json 2>/dev/null | head -1)
  echo "domain_inference_artifact=$DI ($VP repeat=$i)"
  echo "=== SC-3b $VP repeat=$i policy=B DONE $(date -Is) ==="
done

exit "$OVERALL_RC"
