#!/usr/bin/env bash
# SC-4/SC-5/SC-8 multi-session chain driver (harness-only, no production code
# touched). Composes the existing public multi-session CLI
# (`continuous_test.py --sessions N`) exactly as a human operator would --
# this is the same seam continuous_test.py's own module docstring documents
# ("Chain 3 sessions ... .venv/bin/python -m src.continuous_test --persona
# VP-001 --sessions 3"). No --followup-from is passed manually; the chain
# runner wires session N+1's followup_from internally from session N's own
# saved conversation.json (run_multi_session_chain in continuous_test.py).
#
# Usage: sc458_chain.sh <VP-ID> <label> <n_sessions>
set -uo pipefail
VP="$1"
LABEL="$2"
N_SESSIONS="${3:-2}"
BASE="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$BASE/apps/ai-server" || exit 97

echo "=== $LABEL ($VP) continuous_test --sessions $N_SESSIONS start $(date -Is) ==="
.venv/bin/python -m src.continuous_test --persona "$VP" --sessions "$N_SESSIONS" --max-turns 10
RC=$?
echo "continuous_test exit=$RC"

LEDGER="$BASE/docs/ai/simulation_results/$VP/${VP}_session_ledger.json"
echo "session_ledger=$LEDGER"
echo "=== $LABEL ($VP) DONE $(date -Is) ==="
exit "$RC"
