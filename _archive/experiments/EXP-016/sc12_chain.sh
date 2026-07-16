#!/usr/bin/env bash
# SC-12 standalone F1->F2 chain driver (harness-only, no production code touched).
# New-persona dialogue-only baseline: VP-010/011/012, first-visit, no modality cross.
# Usage: sc12_chain.sh <VP-ID>
# Identical mechanism to sc1_chain.sh (SC-1's own driver): composes the existing
# public CLI (src.f1, src.f2) exactly as a human operator would -- no
# --followup-from (standalone, single-session), no --first-visit/--revisit
# override on F2 (let it auto-infer from F1's own persisted is_revisit field,
# which is False for every standalone run by construction). VP-010/011/012 are
# all first-visit-authored personas (no revisit-framing mismatch, unlike
# VP-002/VP-004 in SC-1).
set -uo pipefail
VP="$1"
BASE="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$BASE/apps/ai-server" || exit 97

OUT_DIR="$BASE/docs/ai/simulation_results/$VP"

echo "=== $VP F1 start $(date -Is) ==="
.venv/bin/python -m src.f1 --persona "$VP" --max-turns 10
F1_RC=$?
echo "F1 exit=$F1_RC"

CONV=$(ls -t "$OUT_DIR"/*_conversation.json 2>/dev/null | head -1)
echo "conversation_artifact=$CONV"

if [ "$F1_RC" -ne 0 ] || [ -z "$CONV" ]; then
  echo "ABORT: F1 failed or no conversation artifact found -- skipping F2"
  exit 1
fi

echo "=== $VP F2 start $(date -Is) ==="
.venv/bin/python -m src.f2 --conversation "$CONV"
F2_RC=$?
echo "F2 exit=$F2_RC"

DI=$(ls -t "$OUT_DIR"/*_domain_inference.json 2>/dev/null | head -1)
echo "domain_inference_artifact=$DI"
echo "=== $VP DONE $(date -Is) ==="
exit "$F2_RC"
