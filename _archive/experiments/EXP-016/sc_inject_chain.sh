#!/usr/bin/env bash
# SC-7/SC-9/SC-11 injected F1->F2 chain driver (harness-only, no production
# code touched). Composes run_injected_session.py (real STT/OCR arbitrary-
# turn injection over F1's existing public patient_input_fn seam -- the same
# seam f1._run_simulation's own live PatientLLM wiring uses) with src.f2's
# existing public CLI. No --first-visit/--revisit override on F2 (auto-infer
# from F1's own persisted is_revisit field, same convention as SC-1/SC-12).
#
# Usage: sc_inject_chain.sh <VP-ID> <schedule.json> <max_turns>
set -uo pipefail
VP="$1"
SCHEDULE="$2"
MAX_TURNS="${3:-10}"
BASE="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$BASE/apps/ai-server" || exit 97

OUT_DIR="$BASE/docs/ai/simulation_results/$VP"

echo "=== $VP injected-F1 start $(date -Is) schedule=$SCHEDULE max_turns=$MAX_TURNS ==="
.venv/bin/python -m src.run_injected_session --persona "$VP" --schedule "$SCHEDULE" --max-turns "$MAX_TURNS"
F1_RC=$?
echo "F1(injected) exit=$F1_RC"

CONV=$(ls -t "$OUT_DIR"/*_conversation.json 2>/dev/null | head -1)
echo "conversation_artifact=$CONV"
SIDECAR=$(ls -t "$OUT_DIR"/*_modality_provenance.json 2>/dev/null | head -1)
echo "provenance_sidecar=$SIDECAR"

if [ "$F1_RC" -ne 0 ] || [ -z "$CONV" ]; then
  echo "ABORT: F1(injected) failed or no conversation artifact found -- skipping F2"
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
