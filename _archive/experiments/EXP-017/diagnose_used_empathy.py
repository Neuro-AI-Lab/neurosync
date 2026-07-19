"""THROWAWAY / READ-ONLY diagnostic — not production code, not imported anywhere.

Re-derives, offline, exactly what DialogueAgent._build_slot_context's
used_empathy extraction (apps/ai-server/src/agents/dialogue.py:449-455) would
have constructed at each turn of the 3 post-BUG-030-fix naturalness-probe
sessions, and checks whether the turn's actual agent_response violates the
X-listed (negative-constraint) phrases shown to the model that turn.

Does NOT call any model, does NOT modify any tracked file. Reads the
conversation JSONs under docs/ai/simulation_results/ and replicates the
f1.py conversation_history bookkeeping (turn0 greeting appended once before
the main loop; each loop turn's dialogue.run sees history from all
*prior* completed turns only, not the current one) plus the exact
extraction logic copied verbatim from dialogue.py.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path("/home/neuroai/users/dhkim/aichampion/neurosync")

SESSIONS = {
    "VP-001": REPO / "docs/ai/simulation_results/VP-001/VP-001_20260712_094644_conversation.json",
    "VP-003": REPO / "docs/ai/simulation_results/VP-003/VP-003_20260712_094812_conversation.json",
    "VP-010": REPO / "docs/ai/simulation_results/VP-010/VP-010_20260712_094946_conversation.json",
}


def extract_first_sent(content: str) -> str:
    """Verbatim copy of dialogue.py:453 extraction logic."""
    return content.split(".")[0].split("?")[0][:30]


def build_used_empathy(conversation_history: list[dict[str, str]]) -> list[str]:
    """Verbatim copy of dialogue.py:449-455 loop."""
    used_empathy: list[str] = []
    for m in conversation_history:
        if m.get("role") == "assistant":
            first_sent = extract_first_sent(m["content"])
            if first_sent and first_sent not in used_empathy:
                used_empathy.append(first_sent)
    return used_empathy


def analyze(persona: str, path: Path) -> None:
    data = json.loads(path.read_text())
    turns = data["turns"]
    assert turns[0]["turn"] == 0

    greeting = turns[0]["agent_response"]
    # f1.py: conversation_history = [] initially, then
    # conversation_history.append({"role": "assistant", "content": greeting})
    # right before `for turn in range(1, max_turns + 1):` (line 1276).
    conversation_history: list[dict[str, str]] = [
        {"role": "assistant", "content": greeting},
    ]

    print(f"\n{'='*70}\n{persona}  ({path.name})\n{'='*70}")
    print(f"turn0 greeting: {greeting[:60]!r}")
    print(f"  first_sent(greeting) = {extract_first_sent(greeting)!r} "
          f"(len={len(extract_first_sent(greeting))})")

    # Loop turns are JSON turns 1..N (turn 0 is the greeting/opening call,
    # never passes through the used_empathy branch — opening_turn short-
    # circuits _build_slot_context before that code is reached).
    loop_turns = [t for t in turns if t["turn"] >= 1]

    for t in loop_turns:
        turn_no = t["turn"]
        patient_msg = t["patient_message"]
        actual_response = t["agent_response"]

        # Context as seen by dialogue.run AT CALL TIME for this turn —
        # i.e. conversation_history BEFORE this turn's user/assistant are
        # appended (f1.py appends at lines 1557-1558, after the call).
        used_empathy = build_used_empathy(conversation_history)
        shown = used_empathy[-5:]  # dialogue.py:463 `used_empathy[-5:]`

        actual_first_sent = extract_first_sent(actual_response)
        raw_first_sentence = actual_response.split(".")[0].split("?")[0]
        truncated = len(raw_first_sentence) > 30

        # Would this turn's response have violated a X-listed entry?
        violates_shown = actual_first_sent in shown
        # Was an *exact 30-char-prefix* duplicate of a PREVIOUS response
        # already used earlier in the session, even if not in the shown
        # last-5 window (i.e. extraction saw it, dedup absorbed it, but
        # window eviction hid it)?
        violates_any_seen = actual_first_sent in used_empathy

        print(f"\n-- turn {turn_no} --")
        print(f"  patient_msg[:40]      = {patient_msg[:40]!r}")
        print(f"  agent_response[:70]   = {actual_response[:70]!r}")
        print(f"  raw first sentence    = {raw_first_sentence!r} (len={len(raw_first_sentence)})")
        print(f"  extracted first_sent  = {actual_first_sent!r} (len={len(actual_first_sent)}) "
              f"{'[TRUNCATED]' if truncated else '[whole]'}")
        print(f"  X-list shown (last 5) = {shown}")
        print(f"  >>> violates shown X-list: {violates_shown}"
              f"{'  <=== EXACT-MATCH BAN VIOLATED' if violates_shown else ''}")
        if violates_any_seen and not violates_shown:
            print("  >>> NOTE: matches an earlier used_empathy entry that fell "
                  "outside the last-5 display window (window eviction)")

        # Advance history exactly as f1.py does at the end of the loop body
        # (lines 1557-1558): append user then assistant for *this* turn.
        conversation_history.append({"role": "user", "content": patient_msg})
        conversation_history.append({"role": "assistant", "content": actual_response})


def main() -> None:
    for persona, path in SESSIONS.items():
        analyze(persona, path)


if __name__ == "__main__":
    main()
