Source: origin/main coordinator.py, arms_v6cf.py, arms_v6state.py; halved F1 s4 cell coordinator_result.json.
ANSWER: 1,148 = 1,111 + 37. Counting/definition difference: the 37 extra are real touches, issued by the cf
protect-and-defer compound's PROTECT action, which is a KEEP_GPU_WARM not chosen by the state planner. Not a bug.
Counter sites:
- state_chosen_<X>: arms_v6state.py:873 (self.stats["state_chosen_"+d.chosen] += 1), planner only. state_touch_emitted = 1111 too.
- _submit_touch has ONE caller: coordinator.py:1220, inside the session-action loop, branch xa.action=="KEEP_GPU_WARM"
  (and only if self._touch_requests). It does not know who proposed the action. session_KEEP_GPU_WARM is counted at :1201.
- touch_considered :1589 (every call, after the D319 P-consult block :1570-1586, before any refusal);
  refusals :1591-1596 (touch_refused_guard/budget/no_prefix), :1597, :1604 (budget), share-admission return :1620 (no counter),
  :1625 (no_confirmed_prefix); touch_issued :1628 (+ touch_issued_<tier> :1629); submitted_touch/completed_touch via _submit.
- So considered == issued whenever nothing is refused; here refused = 0 (no touch_refused* keys at all), so 1148 = 1148.
Non-planner KEEP_GPU_WARM source: arms_v6cf.py:602, extra.append(SessionAction(KEEP_GPU_WARM)) per victim in `protect`,
  pd_protects += 1 at :603. Protect is filled from the PROTECT_AND_DEFER request branch (victim, ~:585-588) and the state-chunk path.
  Dispatched through the same coordinator.py:1220 path, so it passes the same should_touch guard and is counted as a touch.
  The DEVICE_ANSWERS branch deliberately does not protect (:559). No other caller found: not HOLD_BACK/WARM (those are
  state_chosen_HOLD_BACK 3 / WARM 1, no touch), not the touch guard P-consult (it only changes belief; consulted 2, allowed 2),
  not cf3 (cf3_admitted 6 etc. are gates for catch-up/claim, no KEEP_GPU_WARM; cf3_resident_* is accounting only).
Halved cell counters: session_KEEP_GPU_WARM 1148; state_chosen_TOUCH 1111 (= state_touch_emitted); pd_protects 37
  (pd_victim_found 268, pd_request_defers 32, pd_state_defers 2, pd_protect_unexpressible_session_busy 1: protect skipped when
  the victim already had a session action); touch_considered 1148; touch_issued 1148 (all tier gpu); submitted_touch 1148;
  completed_touch 1148; touch_guard_p_consulted/allowed 2/2. Arithmetic: 1111 + 37 = 1148 exactly.
Why F0 has chosen == issued: F0 has no protect-and-defer, so pd_protects = 0 and the only KEEP_GPU_WARM source is the planner.
  Caveat: I did not read F0 cells, so that last line is inferred from the code path; also the guard-refusal tally for F1 1x was not checked.
  Also not verified: that every planner TOUCH maps 1:1 to a KEEP_GPU_WARM (the 1111+37 fit exactly says it does here).
Interpretation: the 37 touches are the cf mechanism's own issued touches (protect victims), counted as touch_issued but not state_chosen_TOUCH.
