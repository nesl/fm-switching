== 1x (an.py 1x_f1 1x_f0)
opps 12065 differing kind-seq 3580
robot/single-shot recall-type differing 7
F1 la dev/decision {('robo', 'CLOUD'): 132, ('asst', 'CLOUD'): 352, ('asst', 'DEFER'): 1, ('asst', 'REJECT'): 5}
F0 la dev/decision {('robo', 'CLOUD'): 130, ('asst', 'CLOUD'): 354, ('asst', 'REJECT'): 3, ('robo', 'DEFER'): 1, ('robo', 'REJECT'): 2}
la decision diffs 7 first [(319.34, ('opp0003142', 1), 'asst001', 'DEFER', 'REJECT')]
   319.34 opp0003142 asst001 realworldqa F1 DEFER F0 REJECT
   419.24 opp0004175 robo003 location_trace F1 CLOUD F0 DEFER
   419.34 opp0004178 asst001 realworldqa F1 REJECT F0 CLOUD
   421.04 opp0004192 asst002 realworldqa F1 REJECT F0 CLOUD
   423.84 opp0004219 asst000 refspatial F1 REJECT F0 CLOUD
   445.84 opp0004451 robo003 location_trace F1 CLOUD F0 REJECT
   1041.05 opp0010619 asst002 realworldqa F1 CLOUD F0 REJECT
only in one: 2
F1 Counter({'release_monitor': 8809, 'state_action': 2676, 'touch': 2676, 'release_infeasible': 2084, 'release_recall': 484, 'release_piece': 145, 'decline': 5, 'defer': 1})
F0 Counter({'release_monitor': 9114, 'state_action': 2671, 'touch': 2671, 'release_infeasible': 1778, 'release_recall': 484, 'release_piece': 146, 'decline': 5, 'defer': 1})
touch total 2676 2671 sessions 3 3
  catchup_candidates 0 None
  cf3_resident_epochs 12000 None
  cf3_resident_epochs_with_excluded 3535 None
  cf3_resident_excluded_sum 14092 None
  cf3_resident_members_sum 80841 None
  cf3_resident_rotations 92 None
  cf3_resident_stale_session 53187 None
  pd_decisions 278 None
  pd_decisions_request 131 None
  pd_decisions_state 147 None
  submitted_monitor 8809 9114
  submitted_recall 484 484
  submitted_touch 2676 2671
cf3 keys present in F1: ['cf3_resident_epochs', 'cf3_resident_members_sum', 'cf3_resident_excluded_sum', 'cf3_resident_rotations', 'cf3_resident_stale_session', 'state_deferred_to_guard_epochs', 'pd_deferred_to_guard_epochs', 'cf3_resident_epochs_with_excluded', "pd_gate_wanted_to_act_but_a_request_has_no_slice_channel: the latest safe start is already here and a recall query is one prompt, so there is nothing to send less of. The registered candidate that WOULD apply is DEVICE_ANSWERS (spec v6 section 7's request row), which is not part of the protect-and-defer compound and is not built here"]
dashcam n,within_L F1 (11764, 8335) F0 (11764, 8621)
== n20
opps 8311 differing kind-seq 3268
robot/single-shot recall-type differing 187
F1 la dev/decision {('robo', 'CLOUD'): 181, ('asst', 'CLOUD'): 169, ('asst', 'DEFER'): 4, ('asst', 'REJECT'): 68, ('robo', 'REJECT'): 109, ('robo', 'DEFER'): 14}
F0 la dev/decision {('robo', 'CLOUD'): 203, ('asst', 'CLOUD'): 204, ('asst', 'REJECT'): 33, ('asst', 'DEFER'): 11, ('robo', 'REJECT'): 80, ('robo', 'DEFER'): 18}
la decision diffs 177 first [(276.73, ('opp0001820', 1), 'asst000', 'CLOUD', 'REJECT')]
only in one: 48
F1 Counter({'release_monitor': 4067, 'release_infeasible': 3424, 'state_action': 1619, 'touch': 1590, 'release_recall': 365, 'release_piece': 333, 'decline': 155, 'defer': 25})
F0 Counter({'release_monitor': 5509, 'state_action': 2391, 'touch': 2391, 'release_infeasible': 2051, 'release_recall': 407, 'release_piece': 296, 'decline': 113, 'defer': 29})
touch total 1590 2391 sessions 9 3
  catchup_candidates 0 None
  cf3_admitted 22 None
  cf3_claim_f1_opened 22 None
  cf3_considered 109 None
  cf3_gate_admit_forfeit_valued 22 None
  cf3_gate_net_does_not_exceed_the_bar 15 None
  cf3_gate_next_question_beyond_horizon 8 None
  cf3_gate_no_future_gain 17 None
  cf3_gate_no_question_estimate 3 None
  cf3_gate_not_in_resident_set 44 None
  cf3_net_checked 22 None
  cf3_resident_epochs 11998 None
  cf3_resident_epochs_with_excluded 7288 None
  cf3_resident_excluded_sum 75840 None
  cf3_resident_members_sum 101721 None
  cf3_resident_rotations 158 None
  cf3_resident_stale_session 96074 None
  cf3_touch_dropped_outside_set 86 None
  pd_decisions 482 None
  pd_decisions_request 136 None
  pd_decisions_state 346 None
  submitted_monitor 4067 5509
  submitted_recall 365 407
  submitted_touch 1590 2391
cf3 keys present in F1: ['cf3_resident_epochs', 'cf3_resident_members_sum', 'cf3_resident_excluded_sum', 'cf3_resident_rotations', 'pd_gate_defer_to_latest_safe_start', 'pd_request_defers', 'pd_protec
dashcam n,within_L F1 (7850, 3935) F0 (7850, 5343)
n20 dashcam within_L: F1 3935, F0 5343, cand 4855, la-er 4382; guard_active_epochs 4904/748/3264/4978
