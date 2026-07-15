---
name: severity-calibration
description: How blocking vs major vs minor was calibrated at plan-stage review (CVR-001) — reuse this judgment for future plan-stage CVRs
metadata:
  type: feedback
---

At plan-stage review (nothing implemented/run yet), reserve `blocking` for a behavior that is
*already being validated as adequate* and is not clinically defensible for its scenario class.
A coverage gap or an undefined metric in a plan is not, by itself, blocking — it is `major` (should
shape implementation before the battery runs) or `minor` (should be bound before the specific wave
that depends on it ships). This is not an explicit rule from the agent spec; it's a calibration I
inferred from how this repo's `REV-NNN` entries use severity (e.g. REV-013 "0 blocking, 2 major, 2
minor" at a similarly early implementation-gate stage) and applied consistently in CVR-001.

**Why:** the spec says blocking means "this behavior is not defensible for the scenario class — the
orchestrator must treat it as a gate." At plan stage there is no live behavior yet to certify or
reject, only an absence of coverage or of a metric definition. Treating every plan-stage thinness as
blocking would make the gate meaningless (everything in a plan-only review would qualify) and would
overstep into design decisions that are the orchestrator's/other specialists' to make, not mine to
force via a gate.

**How to apply:** at the *artifact-level* CVR reviews that come later in this program (once scenarios
actually run), recalibrate — a live under-triage, an over-leading safety re-probe, a clinically
harmful candidate ordering actually shipped, etc. are exactly the kind of behavior `blocking` is for.
Plan-stage CVRs (like [[role-origin-and-scope]]'s CVR-001) should stay in the major/minor range unless
the plan itself proposes to *ship* something already known to be clinically indefensible.

**Confirmed again at CVR-002 (v1.2 re-review, 2026-07-10):** kept the same major/minor-only calibration
even for a finding I initially thought might deserve elevated urgency — the "adopted remedies at risk
of silent archival loss at the W6→W7 blind-state boundary" finding (several of my own CVR-001
recommendations exist only as `discussion.md` prose that a version-transition/archive step is about to
remove access to). This is a real, time-bound, high-consequence risk, but it is still a *process/
documentation* risk about future execution, not a live clinical behavior — stayed `major`, not
`blocking`, consistent with the rule above. General pattern worth carrying forward: distinguish
"this plan-stage design choice is clinically thin" (major/minor) from "this plan-stage design choice
describes a live behavior already shipped as adequate" (blocking) — the archival-loss case is a good
test of the boundary because it *feels* urgent (there's a real deadline) without being a live behavior.
