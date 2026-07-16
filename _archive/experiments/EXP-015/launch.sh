#!/usr/bin/env bash
# EXP-015 launch script — Policy-B Gate-0 certification batch (REV-024 ruling 4 / plan Appendix C).
# Fresh, first-visit F1 sessions (VP-003, VP-001) chained into f2.py --rag-trigger-policy B.
# Two separate CLI invocations per VP (f1.py then f2.py) because continuous_test.py's own
# F1->F2 chaining harness hardcodes Policy A internally (discussion.md:3814, EXP-015 config note).
set -u
REPO_ROOT="/home/neuroai/users/dhkim/aichampion/neurosync"
cd "$REPO_ROOT/apps/ai-server" || exit 1
export PROMPTS_BASE_DIR="$REPO_ROOT/docs/ai/prompts"

run_vp () {
  local vp="$1"
  local rundir="$REPO_ROOT/experiments/EXP-015/runs/cert/$vp"
  mkdir -p "$rundir"

  echo "=== $vp F1 START $(date -Is) ===" | tee -a "$rundir/run.log"
  # f1.py has no --first-visit flag (re-verified via --help); first-visit is the default when
  # --followup-from is omitted (fresh session, no prior-session chaining requested).
  .venv/bin/python -m src.f1 --persona "$vp" \
    >> "$rundir/f1_stdout.log" 2>&1
  local f1_rc=$?
  echo "=== $vp F1 END $(date -Is) exit=$f1_rc ===" | tee -a "$rundir/run.log"
  if [ "$f1_rc" -ne 0 ]; then
    echo "$vp F1 FAILED, aborting F2 step" | tee -a "$rundir/run.log"
    return "$f1_rc"
  fi

  # Locate the freshly-written conversation.json (most recent for this VP).
  local conv
  conv=$(ls -t "$REPO_ROOT/docs/ai/simulation_results/$vp/${vp}_"*_conversation.json 2>/dev/null | head -1)
  if [ -z "$conv" ]; then
    echo "$vp: no conversation.json found after F1 run" | tee -a "$rundir/run.log"
    return 1
  fi
  echo "$vp F1 artifact: $conv" | tee -a "$rundir/run.log"
  echo "$conv" > "$rundir/f1_artifact_path.txt"

  echo "=== $vp F2 (Policy B) START $(date -Is) ===" | tee -a "$rundir/run.log"
  .venv/bin/python -m src.f2 --conversation "$conv" --rag-trigger-policy B --k 3 --out "$rundir" \
    >> "$rundir/f2_stdout.log" 2>&1
  local f2_rc=$?
  echo "=== $vp F2 END $(date -Is) exit=$f2_rc ===" | tee -a "$rundir/run.log"
  return "$f2_rc"
}

run_vp VP-003
vp003_rc=$?
run_vp VP-001
vp001_rc=$?

echo "=== ALL DONE $(date -Is) VP-003_exit=$vp003_rc VP-001_exit=$vp001_rc ==="
if [ "$vp003_rc" -ne 0 ] || [ "$vp001_rc" -ne 0 ]; then
  exit 1
fi
exit 0
