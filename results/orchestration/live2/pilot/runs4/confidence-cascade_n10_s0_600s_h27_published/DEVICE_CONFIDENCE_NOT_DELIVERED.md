# DEVICE CONFIDENCE NOT DELIVERED (ABSENT LINK)

This run predates the device-confidence wiring fix of 2026-11-20 (user ruling). Its arm declares
`reads_device_answer = True` and reads `recall[].device_answer_confidence` in its own code, but
live2 supplied that field as `None` on every recall query, for three independent reasons:
`cstate.observation` hard-coded it, that function ignored its own `reads_device_answer` parameter,
and `coordinator.py` never passed the parameter at all.

The declaration WAS charged: the coordinator made the arm wait StudyD8's 0.567 s before it could
act, and served the opportunity that much later. So this run's arm paid the full price of reading
the device answer and received nothing.

CONSEQUENCE FOR READING THIS RUN. Any recall decision here in which the arm did not escalate is an
ABSENT LINK under CLAUDE.md Rule 2, not evidence about cascading. `confidence-cascade` in
particular sends EVERY recall to the device when the confidence is None, by the explicit
`c is None` branch in `baselines/cascade_adapted.py`, so its recall behaviour in this run carries
no information about its confidence threshold.

The run's own numbers are not wrong and nothing here is deleted or recomputed; it is the
INTERPRETATION that is bounded. See reports/study_ss2.md section 12 for the audit and 12.1 for the
fix and its proof.
