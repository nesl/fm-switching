#### score
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
== (0) headline per cell; decision kinds
ca robot cloud on-time 149 / 283 acc_on_served 0.630872 n_dev_standing 134 SS 160 / 237 dash within_L 3897 worst (0.465, 'dash001') | decisions {'release_piece': 296, 'release_recall': 383, 'release_monitor': 4048, 'release_infeasible': 3381, 'state_action': 1962, 'touch': 1907, 'defer': 34, 'decline': 137}
f1 robot cloud on-time 151 / 283 acc_on_served 0.649007 n_dev_standing 132 SS 155 / 237 dash within_L 3935 worst (0.482, 'dash000') | decisions {'release_piece': 333, 'release_recall': 365, 'release_monitor': 4067, 'release_infeasible': 3424, 'state_action': 1619, 'touch': 1590, 'defer': 25, 'decline': 155}
tl robot cloud on-time 181 / 283 acc_on_served 0.668508 n_dev_standing 102 SS 199 / 237 dash within_L 5343 worst (0.654, 'dash002') | decisions {'release_piece': 296, 'release_recall': 407, 'release_monitor': 5509, 'release_infeasible': 2051, 'decline': 113, 'defer': 29, 'state_action': 2391, 'touch': 2391}
r3 robot cloud on-time 124 / 283 acc_on_served 0.717742 n_dev_standing 159 SS 163 / 237 dash within_L 3748 worst (0.448, 'dash001') | decisions {'release_piece': 333, 'release_recall': 458, 'release_monitor': 3977, 'release_infeasible': 3093, 'defer': 7, 'decline': 62, 'state_action': 3133, 'touch': 2152}
== (1) positive control: classifier vs committed rows
ca committed cbd 132 classifier cbd 132 per-opp agree 283 / 283 | cloud-correct 94 device-correct 38 device-route n 134 cloud stands 149 | committed cloud-correct 94 device-correct 38
f1 committed cbd 132 classifier cbd 132 per-opp agree 283 / 283 | cloud-correct 98 device-correct 34 device-route n 132 cloud stands 151 | committed cloud-correct 98 device-correct 34
tl committed cbd 154 classifier cbd 154 per-opp agree 283 / 283 | cloud-correct 121 device-correct 33 device-route n 102 cloud stands 181 | committed cloud-correct 121 device-correct 33
r3 committed cbd 131 classifier cbd 131 per-opp agree 283 / 283 | cloud-correct 89 device-correct 42 device-route n 159 cloud stands 124 | committed cloud-correct 89 device-correct 42
== (2) paired diffs ca minus tl; opps overlap 283 283 283
distinct questions 47
cbd                            -22 CI[-38,-8] excl0
cloud on-time                  -32 CI[-56,-10] excl0
cloud-correct                  -27 CI[-47,-10] excl0
device-route (not cloud)       +32 CI[+10,+56] excl0
dashcam within_L -1446 CI[-2204,-710] (20 60s blocks; instants 7850/7850/7850)
SS cloud on-time ca 160 tl 199 diff -39 CI[-53,-24] (237 questions)
== (2) paired diffs ca minus f1; opps overlap 283 283 283
distinct questions 47
cbd                            +0 CI[-10,+10] incl0
cloud on-time                  -2 CI[-19,+13] incl0
cloud-correct                  -4 CI[-17,+9] incl0
device-route (not cloud)       +2 CI[-13,+19] incl0
dashcam within_L -38 CI[-370,+304] (20 60s blocks; instants 7850/7850/7850)
SS cloud on-time ca 160 f1 155 diff +5 CI[-10,+21] (237 questions)
== (2) paired diffs ca minus r3; opps overlap 283 283 283
distinct questions 47
cbd                            +1 CI[-16,+15] incl0
cloud on-time                  +25 CI[+7,+43] excl0
cloud-correct                  +5 CI[-9,+18] incl0
device-route (not cloud)       -25 CI[-43,-7] excl0
dashcam within_L +149 CI[-220,+517] (20 60s blocks; instants 7850/7850/7850)
SS cloud on-time ca 160 r3 163 diff -3 CI[-18,+13] (237 questions)
== (3) loss decomposition e vs tl ; states {'ca': {'WRONG': 55, 'ONTIME_CORRECT': 94, 'LATE_ENGINE': 60, 'REJECTED': 73, 'LATE_DISPATCH': 1}, 'tl': {'WRONG': 60, 'ONTIME_CORRECT': 121, 'LATE_ENGINE': 22, 'REJECTED': 80}}
 on-time LOST by e 61 failing side (e state) {'LATE_ENGINE': 29, 'REJECTED': 31, 'LATE_DISPATCH': 1} | of lost, tl answer WRONG 19
 on-time GAINED by e 29 failing side (tl state) {'LATE_ENGINE': 8, 'REJECTED': 21} | e answer WRONG 13 correct 16
 cbd-differing opps by owner and states
   ('e+1', 'tl:LATE_ENGINE', 'e:ONTIME_CORRECT') 5
   ('e+1', 'tl:REJECTED', 'e:ONTIME_CORRECT') 8
   ('e+1', 'tl:WRONG', 'e:LATE_ENGINE') 3
   ('e+1', 'tl:WRONG', 'e:REJECTED') 1
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:LATE_DISPATCH') 1
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:LATE_ENGINE') 12
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:REJECTED') 17
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:WRONG') 1
   ('tl+1', 'tl:REJECTED', 'e:WRONG') 8
== (3) loss decomposition e vs f1 ; states {'ca': {'WRONG': 55, 'ONTIME_CORRECT': 94, 'LATE_ENGINE': 60, 'REJECTED': 73, 'LATE_DISPATCH': 1}, 'f1': {'WRONG': 53, 'ONTIME_CORRECT': 98, 'LATE_ENGINE': 43, 'REJECTED': 87, 'LATE_DISPATCH': 2}}
 on-time LOST by e 43 failing side (e state) {'LATE_ENGINE': 10, 'REJECTED': 32, 'LATE_DISPATCH': 1} | of lost, f1 answer WRONG 16
 on-time GAINED by e 41 failing side (f1 state) {'REJECTED': 26, 'LATE_ENGINE': 15} | e answer WRONG 17 correct 24
 cbd-differing opps by owner and states
   ('e+1', 'f1:LATE_ENGINE', 'e:ONTIME_CORRECT') 5
   ('e+1', 'f1:REJECTED', 'e:ONTIME_CORRECT') 11
   ('e+1', 'f1:WRONG', 'e:LATE_ENGINE') 2
   ('e+1', 'f1:WRONG', 'e:REJECTED') 3
   ('f1+1', 'f1:LATE_ENGINE', 'e:WRONG') 3
   ('f1+1', 'f1:ONTIME_CORRECT', 'e:LATE_DISPATCH') 1
   ('f1+1', 'f1:ONTIME_CORRECT', 'e:LATE_ENGINE') 2
   ('f1+1', 'f1:ONTIME_CORRECT', 'e:REJECTED') 11
   ('f1+1', 'f1:ONTIME_CORRECT', 'e:WRONG') 1
   ('f1+1', 'f1:REJECTED', 'e:WRONG') 3
== (3) loss decomposition e vs r3 ; states {'ca': {'WRONG': 55, 'ONTIME_CORRECT': 94, 'LATE_ENGINE': 60, 'REJECTED': 73, 'LATE_DISPATCH': 1}, 'r3': {'WRONG': 35, 'ONTIME_CORRECT': 89, 'REJECTED': 62, 'LATE_ENGINE': 97}}
 on-time LOST by e 24 failing side (e state) {'LATE_ENGINE': 11, 'REJECTED': 13} | of lost, r3 answer WRONG 5
 on-time GAINED by e 49 failing side (r3 state) {'REJECTED': 20, 'LATE_ENGINE': 29} | e answer WRONG 24 correct 25
 cbd-differing opps by owner and states
   ('e+1', 'r3:LATE_ENGINE', 'e:ONTIME_CORRECT') 10
   ('e+1', 'r3:REJECTED', 'e:ONTIME_CORRECT') 8
   ('r3+1', 'r3:LATE_ENGINE', 'e:WRONG') 3
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:LATE_ENGINE') 4
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:REJECTED') 4
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:WRONG') 1
   ('r3+1', 'r3:REJECTED', 'e:WRONG') 5
== (4) residency cold (analyse with opp ids)
ca asks reached engine 208 resid-eligible 208 cold<.5 43 <.25 39 | declined recall opps 73
f1 asks reached engine 196 resid-eligible 196 cold<.5 31 <.25 27 | declined recall opps 87
tl asks reached engine 203 resid-eligible 203 cold<.5 11 <.25 8 | declined recall opps 80
r3 asks reached engine 218 resid-eligible 218 cold<.5 42 <.25 35 | declined recall opps 62
RESID <.5 e-tl all q      n_q=44 e=43 tl=11 diff +32 CI[+20,+46]
RESID <.5 e-tl asked both n_q=39 e=39 tl=11 diff +28 CI[+16,+42]
RESID <.25 e-tl all q      n_q=44 e=39 tl=8 diff +31 CI[+20,+43]
RESID <.25 e-tl asked both n_q=39 e=35 tl=8 diff +27 CI[+16,+39]
 opps cold(<.5) in tl (11): fate in e {'sent in e: still cold': 5, 'declined in e (b7)': 4, 'sent in e: warm >=.5': 2}
 opps cold(<.5) in E (43): same opp in tl {'tl: cold': 5, 'tl: warm': 25, 'tl: absent': 13}
RESID <.5 e-f1 all q      n_q=45 e=43 f1=31 diff +12 CI[+1,+23]
RESID <.5 e-f1 asked both n_q=39 e=40 f1=30 diff +10 CI[+0,+20]
RESID <.25 e-f1 all q      n_q=45 e=39 f1=27 diff +12 CI[+2,+22]
RESID <.25 e-f1 asked both n_q=39 e=36 f1=26 diff +10 CI[+1,+19]
 opps cold(<.5) in f1 (31): fate in e {'sent in e: still cold': 13, 'sent in e: warm >=.5': 12, 'declined in e (b7)': 6}
 opps cold(<.5) in E (43): same opp in f1 {'f1: cold': 13, 'f1: warm': 8, 'f1: absent': 22}
RESID <.5 e-r3 all q      n_q=45 e=43 r3=42 diff +1 CI[-13,+14]
RESID <.5 e-r3 asked both n_q=38 e=38 r3=42 diff -4 CI[-16,+8]
RESID <.25 e-r3 all q      n_q=45 e=39 r3=35 diff +4 CI[-8,+16]
RESID <.25 e-r3 asked both n_q=38 e=35 r3=35 diff +0 CI[-11,+11]
 opps cold(<.5) in r3 (42): fate in e {'sent in e: still cold': 13, 'declined in e (b7)': 13, 'sent in e: warm >=.5': 16}
 opps cold(<.5) in E (43): same opp in r3 {'r3: cold': 13, 'r3: absent': 12, 'r3: warm': 18}
== (7) FAIR share (RE-IMPLEMENTATION: robot+SS rows, oracle all-cloud with history, floors A_RD/A_SD; no over-32k exclusion, no question dedup)
ca combined rel 0.5512 (abs gain 58.17 of oracle 105.55) | robot rel 0.5265 (46.35 of 88.03) | ss rel 0.6751 (11.82 of 17.51)
f1 combined rel 0.5536 (abs gain 58.43 of oracle 105.55) | robot rel 0.5336 (46.97 of 88.03) | ss rel 0.6540 (11.45 of 17.51)
tl combined rel 0.6728 (abs gain 71.01 of oracle 105.55) | robot rel 0.6396 (56.30 of 88.03) | ss rel 0.8397 (14.71 of 17.51)
r3 combined rel 0.4796 (abs gain 50.62 of oracle 105.55) | robot rel 0.4382 (38.57 of 88.03) | ss rel 0.6878 (12.05 of 17.51)
FAIR ca-tl rel diff -0.1216 CI[-0.1893,-0.0560] | abs gain diff -12.84 CI[-20.60,-5.55]
FAIR ca-f1 rel diff -0.0024 CI[-0.0522,+0.0447] | abs gain diff -0.25 CI[-5.38,+4.64]
FAIR ca-r3 rel diff +0.0716 CI[+0.0205,+0.1242] | abs gain diff +7.56 CI[+1.99,+13.91]
== (8) touches per robot session
ca touch requests 1907 sessions 43 per-session min/med/max 0 0 964 zero-touch sessions 37
f1 touch requests 1590 sessions 43 per-session min/med/max 0 0 685 zero-touch sessions 34
tl touch requests 2391 sessions 43 per-session min/med/max 0 0 1434 zero-touch sessions 40
r3 touch requests 2152 sessions 43 per-session min/med/max 0 0 786 zero-touch sessions 38
#### an
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
== (A) run validity / budget / counters F1 vs F0
ca run_valid True wall 1200.03246 budget 815.28 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 1907, 'recall_CLOUD': 383, 'recall_DEFER': 34, 'recall_REJECT': 137, 'release_infeasible': 3381, 'release_infeasible_alert': 3381, 'submitted_touch': 1907, 'touch_considered': 1962, 'touch_guard_p_allowed': 24, 'touch_guard_p_consulted': 79, 'touch_guard_p_kept_cold': 55, 'touch_issued': 1907, 'touch_issued_gpu': 1906, 'touch_issued_host': 1, 'touch_price_milli_sum': 5721, 'touch_refused': 55, 'touch_refused_guard': 55}
   arm_stats {'cf3_resident_epochs': 11999, 'cf3_resident_members_sum': 101564, 'cf3_resident_excluded_sum': 76037, 'pd_kv_bound_by_belief': 438, 'pd_decisions': 438, 'pd_decisions_state': 311, 'pd_gate_no_active_alert_episode': 145, 'pd_u_max': 17343, 'pd_u_sum': 1418776, 'pd_free_kv_min': 0, 'pd_free_kv_max': 62944, 'pd_free_kv_sum': 10394571, 'pd_decisions_request': 127, 'pd_gate_rebuild_fits_without_evicting': 243, 'cf_planner_decisions': 67554, 'cf_planner_decisions_state': 67554, 'cf_budget_ms': 20.0, 'cf3_resident_rotations': 148, 'pd_victim_found': 418, 'pd_gate_defer_to_latest_safe_start': 5, 'pd_harm_n': 50, 'pd_harm_micro_sum': 40163631, 'pd_harm_micro_max': 4712058, 'pd_harm_gt_0': 50, 'pd_harm_gt_0p01': 29, 'pd_harm_gt_0p1': 26, 'pd_harm_gt_0p65824': 24, 'pd_harm_over_bar': 13, 'pd_request_defers': 3, 'pd_protects': 3, 'pd_deferred_to_guard_epochs': 4913, 'cf3_considered': 103, 'cf3_gate_net_does_not_exceed_the_bar': 43, 'cf3_gate_no_future_gain': 23, 'cf3_gate_no_question_estimate': 3, 'cf3_gate_admit_forfeit_valued': 30, 'cf3_net_checked': 30, 'cf3_admitted': 30, 'cf3_claim_f1_opened': 30, 'cf3_resident_stale_session': 96088, 'cf3_resident_epochs_with_excluded': 7289, 'pd_gate_harm_does_not_exceed_the_bar': 37, 'pd_harm_gt_1': 22, 'pd_harm_gt_2': 6, 'pd_request_crossed_bar_unexpressible': 7, 'pd_state_defers': 2, 'pd_protect_unexpressible_session_busy': 3, 'pd_state_chunks': 1, 'cf3_gate_next_question_beyond_horizon': 4, 'catchup_candidates': 0}
   residency-cold counters {'belief_to_cold': 60, 'state_priced_build_cold': 148, 'touch_guard_p_kept_cold': 55} {'book0b_cold_pieces': 118}
f1 run_valid True wall 1200.032461 budget 822.47 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 1577, 'recall_CLOUD': 365, 'recall_DEFER': 25, 'recall_REJECT': 155, 'release_infeasible': 3424, 'release_infeasible_alert': 3424, 'submitted_touch': 1590, 'touch_considered': 1619, 'touch_guard_p_allowed': 21, 'touch_guard_p_consulted': 49, 'touch_guard_p_kept_cold': 28, 'touch_issued': 1590, 'touch_issued_gpu': 1588, 'touch_issued_host': 2, 'touch_price_milli_sum': 4770, 'touch_refused': 29, 'touch_refused_guard': 28, 'touch_refused_no_prefix': 1}
   arm_stats {'cf3_resident_epochs': 11998, 'cf3_resident_members_sum': 101721, 'cf3_resident_excluded_sum': 75840, 'pd_kv_bound_by_belief': 482, 'pd_decisions': 482, 'pd_decisions_state': 346, 'pd_gate_no_active_alert_episode': 199, 'pd_u_max': 17635, 'pd_u_sum': 1547148, 'pd_free_kv_min': 0, 'pd_free_kv_max': 62944, 'pd_free_kv_sum': 10155479, 'pd_decisions_request': 136, 'pd_gate_rebuild_fits_without_evicting': 222, 'cf_planner_decisions': 65931, 'cf_planner_decisions_state': 65931, 'cf_budget_ms': 20.0, 'cf3_resident_rotations': 158, 'pd_victim_found': 462, 'pd_gate_defer_to_latest_safe_start': 8, 'pd_harm_n': 61, 'pd_harm_micro_sum': 65300807, 'pd_harm_micro_max': 4651206, 'pd_harm_gt_0': 55, 'pd_harm_gt_0p01': 30, 'pd_harm_gt_0p1': 29, 'pd_harm_gt_0p65824': 29, 'pd_harm_over_bar': 25, 'pd_request_defers': 7, 'pd_protects': 7, 'pd_deferred_to_guard_epochs': 4904, 'pd_harm_gt_1': 27, 'pd_harm_gt_2': 17, 'pd_request_crossed_bar_unexpressible': 17, 'cf3_considered': 109, 'cf3_gate_no_question_estimate': 3, 'cf3_gate_net_does_not_exceed_the_bar': 15, 'cf3_resident_stale_session': 96074, 'cf3_gate_admit_forfeit_valued': 22, 'cf3_net_checked': 22, 'cf3_admitted': 22, 'cf3_claim_f1_opened': 22, 'cf3_gate_no_future_gain': 17, 'cf3_resident_epochs_with_excluded': 7288, 'cf3_gate_not_in_resident_set': 44, 'pd_gate_harm_does_not_exceed_the_bar': 36, 'cf3_gate_next_question_beyond_horizon': 8, 'pd_protect_unexpressible_session_busy': 1, 'pd_state_defers': 1, 'pd_harm_zero': 6, 'cf3_touch_dropped_outside_set': 86, 'catchup_candidates': 0}
   residency-cold counters {'belief_to_cold': 67, 'state_priced_build_cold': 152, 'touch_guard_p_kept_cold': 28} {'book0b_cold_pieces': 133}
tl run_valid True wall 1200.032484 budget 777.27 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 1
   counts {'completed_touch': 2391, 'recall_CLOUD': 407, 'recall_DEFER': 29, 'recall_REJECT': 113, 'release_infeasible': 2051, 'release_infeasible_alert': 2051, 'submitted_touch': 2391, 'touch_considered': 2391, 'touch_guard_p_allowed': 8, 'touch_guard_p_consulted': 8, 'touch_issued': 2391, 'touch_issued_gpu': 2390, 'touch_issued_host': 1, 'touch_price_milli_sum': 7173}
   arm_stats {'cf_planner_decisions': 121179, 'cf_planner_decisions_state': 121179, 'cf_budget_ms': 20.0}
   residency-cold counters {'belief_to_cold': 58, 'state_priced_build_cold': 100} {'book0b_cold_pieces': 87}
r3 run_valid True wall 1200.032436 budget 632.57 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 1
   counts {'completed_touch': 2152, 'recall_CLOUD': 458, 'recall_DEFER': 7, 'recall_REJECT': 62, 'release_infeasible': 3093, 'release_infeasible_alert': 3093, 'submitted_touch': 2152, 'touch_considered': 3133, 'touch_issued': 2152, 'touch_issued_gpu': 2152, 'touch_price_milli_sum': 6456, 'touch_refused': 981, 'touch_refused_guard': 981}
   arm_stats {'cf_planner_decisions': 57644, 'cf_planner_decisions_state': 57644, 'cf_budget_ms': 20.0}
   residency-cold counters {'belief_to_cold': 66, 'state_priced_build_cold': 182} {}
== (B) TTFT t_first_token-t_submit quantiles per class
ca {'robo': (2411, [0.705, 4.303, 9.918]), 'asst': (173, [0.266, 1.185, 6.835]), 'dash': (4043, [0.227, 0.565, 1.212])}
f1 {'robo': (2102, [0.827, 5.447, 13.186]), 'asst': (169, [0.389, 1.266, 4.732]), 'dash': (4067, [0.23, 0.563, 1.226])}
tl {'robo': (2888, [0.429, 2.555, 5.161]), 'asst': (204, [0.298, 0.827, 2.386]), 'dash': (5509, [0.232, 0.539, 0.997])}
r3 {'robo': (2702, [0.544, 8.428, 24.037]), 'asst': (237, [0.476, 8.265, 23.667]), 'dash': (3977, [0.226, 0.57, 3.282])}
== (C) release_infeasible by class and SS/dash outcomes
ca [('none', 3381)]
  monitor within_L {('monitor', True): 3897, ('monitor', False): 3953}  n monitor opps 7850
f1 [('none', 3424)]
  monitor within_L {('monitor', True): 3935, ('monitor', False): 3915}  n monitor opps 7850
tl [('none', 2051)]
  monitor within_L {('monitor', True): 5343, ('monitor', False): 2507}  n monitor opps 7850
r3 [('none', 3093)]
  monitor within_L {('monitor', True): 3748, ('monitor', False): 4102}  n monitor opps 7850
== (D) cf admissions: outcomes
Counter({'not_in_resident_set': 44, 'admit_forfeit_valued': 22, 'no_future_gain': 17, 'net_does_not_exceed_the_bar': 15, 'next_question_beyond_horizon': 8, 'no_question_estimate': 3}) 22
opp0002046 robo009 t=307.7 net 34.1 f1 state LATE_DISPATCH cbd 0 | F0 state REJECTED cbd 0 | next ask dt 5.6
opp0002074 robo010 t=311.4 net 1.8 f1 state LATE_ENGINE cbd 0 | F0 state LATE_ENGINE cbd 0 | next ask dt 28.7
opp0002185 robo009 t=327.2 net 12.3 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 10.0
opp0002409 robo011 t=358.2 net 1.1 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 28.5
opp0002423 robo006 t=360.8 net 8.5 f1 state LATE_ENGINE cbd 0 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 19.5
opp0002471 robo001 t=367.8 net 6.1 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 51.8
opp0002477 robo004 t=369.1 net 2.7 f1 state LATE_ENGINE cbd 1 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 27.7
opp0002484 robo008 t=370.2 net 2.4 f1 state LATE_ENGINE cbd 0 | F0 state LATE_ENGINE cbd 0 | next ask dt 61.3
opp0002497 robo011 t=372.2 net 1.0 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 24.1
opp0002536 robo010 t=377.1 net 7.3 f1 state LATE_ENGINE cbd 0 | F0 state WRONG cbd 0 | next ask dt 13.1
opp0002611 robo001 t=387.3 net 5.0 f1 state WRONG cbd 0 | F0 state REJECTED cbd 1 | next ask dt 42.1
opp0002933 robo001 t=432.1 net 2.4 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 31.9
opp0003028 robo003 t=445.8 net 8.9 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 26.5
opp0003043 robo013 t=447.5 net 21.8 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 15.7
opp0003044 robo009 t=447.6 net 7.2 f1 state LATE_ENGINE cbd 0 | F0 state LATE_ENGINE cbd 0 | next ask dt 40.4
opp0003601 robo009 t=526.6 net 4.0 f1 state LATE_ENGINE cbd 0 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 41.3
opp0006478 robo013 t=936.4 net 4.8 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 24.1
opp0006553 robo001 t=945.5 net 1.9 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 29.0
opp0006964 robo009 t=1001.8 net 5.0 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 29.4
opp0007121 robo003 t=1024.4 net 2.4 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 118.2
opp0007147 robo009 t=1027.2 net 3.4 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 21.3
opp0007187 robo001 t=1032.8 net 12.5 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 18.8
admit summary f1 states Counter({'LATE_ENGINE': 20, 'LATE_DISPATCH': 1, 'WRONG': 1}) F0 states same opps Counter({'REJECTED': 15, 'LATE_ENGINE': 3, 'ONTIME_CORRECT': 3, 'WRONG': 1}) cbd f1 6 cbd F0 9
KEEP_REJECT 87 cbd f1 24 F0 state Counter({'REJECTED': 36, 'ONTIME_CORRECT': 31, 'WRONG': 15, 'LATE_ENGINE': 5})
#### an2
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
touch decisions per robot session F0 vs F1 (total) 2391 1590
cbd differs F1 worse 35 {'late, warm ask, not admitted: queue/congestion': 4, 'cf ADMISSION (late-engine/late)': 3, 'cf KEEP_REJECT (considered, not admitted)': 21, 'F1 gained (F0 failed)': 4, 'cold ask, touches not fewer': 3}
cbd differs F1 better 13 {'F1 gained (F0 failed)': 10, 'cf KEEP_REJECT (considered, not admitted)': 2, 'cold ask, touches not fewer': 1}
on-time differs F1 worse 62 {'late, warm ask, not admitted: queue/congestion': 7, 'cf KEEP_REJECT (considered, not admitted)': 46, 'cf ADMISSION (late-engine/late)': 4, 'cold ask, touches not fewer': 5}
on-time differs F1 better 32 {'F1 gained (F0 failed)': 28, 'cf ADMISSION (late-engine/late)': 1, 'cold ask, touches not fewer': 3}
sessions: touches F0->F1
  robo007| 1434 685
  robo006| 526 0
  robo002| 0 1
  robo004| 0 1
  robo002| 0 1
  robo000| 0 2
ca resid-eligible 208 mean cached frac 0.787 <.5 43
f1 resid-eligible 196 mean cached frac 0.836 <.5 31
tl resid-eligible 203 mean cached frac 0.938 <.5 11
next ask after each admission: (admit, next, cached frac F1, F1 state, F0 state)
[('opp0002497', 'opp0002803', 1.0, 'ONTIME_CORRECT', 'REJECTED'), ('opp0006553', 'opp0007187', 0.0, 'LATE_ENGINE', 'REJECTED'), ('opp0002471', 'opp0002611', 1.0, 'WRONG', 'REJECTED'), ('opp0002046', 'opp0002185', 0.27, 'LATE_ENGINE', 'REJECTED'), ('opp0002074', 'opp0002177', 0.99, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0006478', 'opp0006523', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0002185', 'opp0002217', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0002536', 'opp0002645', 0.99, 'WRONG', 'WRONG'), ('opp0007147', 'opp0007768', 0.19, 'LATE_ENGINE', 'REJECTED'), ('opp0002484', 'opp0002987', 0.69, 'LATE_ENGINE', 'WRONG'), ('opp0007121', 'opp0007313', 0.99, 'WRONG', 'REJECTED'), ('opp0003044', 'opp0003213', 0.99, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0002611', 'opp0002775', 1.0, 'WRONG', 'REJECTED'), ('opp0003043', 'opp0003229', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0002477', 'opp0002625', 0.5, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0007187', 'opp0007367', 1.0, 'LATE_ENGINE', 'REJECTED'), ('opp0006964', 'opp0007017', 0.99, 'WRONG', 'REJECTED'), ('opp0002409', 'opp0002497', 0.99, 'LATE_ENGINE', 'REJECTED')]
next-ask F1 states Counter({'ONTIME_CORRECT': 7, 'LATE_ENGINE': 6, 'WRONG': 5}) F0 Counter({'REJECTED': 13, 'ONTIME_CORRECT': 3, 'WRONG': 2})
ca SS on-time 160 / 237
  SS opps by decision {'sent': 173, 'declined': 64} SS decisions decline/defer 75
f1 SS on-time 155 / 237
  SS opps by decision {'sent': 169, 'declined': 68} SS decisions decline/defer 72
tl SS on-time 199 / 237
  SS opps by decision {'sent': 204, 'declined': 33} SS decisions decline/defer 44
#### an3
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
ca robot n 283 final dec {'CLOUD': 180, 'REJECT': 103} est_la q [0.28, 0.63, 1.72, 4.1, 6.98] queued_ahead q [0, 760, 3288, 14251, 39080] slack q [2.88, 2.9, 2.93, 2.95, 2.97] uncached_u q [181, 461, 1359, 9663, 19291]
ca SS n 237 final dec {'CLOUD': 173, 'REJECT': 64} est_la q [0.11, 0.19, 0.43, 2.25, 4.16] queued_ahead q [0, 380, 1755, 13353, 26131] slack q [1.89, 1.94, 1.96, 1.97, 1.97] uncached_u q [1, 1, 331, 866, 1341]
f1 robot n 283 final dec {'CLOUD': 174, 'REJECT': 109} est_la q [0.3, 0.56, 1.79, 4.18, 8.57] queued_ahead q [0, 760, 2788, 17525, 41750] slack q [2.88, 2.9, 2.92, 2.95, 2.96] uncached_u q [187, 463, 1365, 11235, 18661]
f1 SS n 237 final dec {'CLOUD': 169, 'REJECT': 68} est_la q [0.17, 0.28, 0.54, 2.67, 6.16] queued_ahead q [0, 380, 2170, 15334, 39244] slack q [1.88, 1.89, 1.91, 1.92, 1.95] uncached_u q [223, 327, 343, 1336, 1361]
tl robot n 283 final dec {'CLOUD': 203, 'REJECT': 80} est_la q [0.24, 0.44, 1.16, 3.33, 4.76] queued_ahead q [0, 380, 1520, 5201, 14339] slack q [2.88, 2.9, 2.92, 2.95, 2.97] uncached_u q [185, 543, 1715, 11731, 21811]
tl SS n 237 final dec {'CLOUD': 204, 'REJECT': 33} est_la q [0.13, 0.19, 0.35, 0.8, 2.51] queued_ahead q [0, 380, 1140, 4140, 14899] slack q [1.91, 1.92, 1.94, 1.96, 1.97] uncached_u q [1, 224, 335, 1331, 1353]
ca uncached prefill tokens total 4405456 {'robo': 2222029, 'dash': 2095374, 'asst': 88053} n requests 6634
  robot requests by decision kind {'release_piece': 296, 'release_recall': 210, 'touch': 1907}
f1 uncached prefill tokens total 4463298 {'robo': 2294839, 'dash': 2043888, 'asst': 124571} n requests 6355
  robot requests by decision kind {'release_piece': 333, 'release_recall': 196, 'touch': 1590}
tl uncached prefill tokens total 4238814 {'robo': 1427962, 'dash': 2698062, 'asst': 112790} n requests 8603
  robot requests by decision kind {'release_piece': 296, 'release_recall': 203, 'touch': 2391}
#### adm
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
ca gates Counter({'net_does_not_exceed_the_bar': 43, 'admit_forfeit_valued': 30, None: 30, 'no_future_gain': 23, 'next_question_beyond_horizon': 4, 'no_question_estimate': 3}) Counter({'KEEP_REJECT': 73, 'ADMIT': 30, None: 30})
ca adm 30 f1 adm 22 shared 9 ca-only 21 f1-only 13
f1-only admits considered in ca: 5 ; ca-only considered in f1: 16
considered ca 103 f1 109 both 62
ca admit states {'LATE_ENGINE': 26, 'WRONG': 1, 'ONTIME_CORRECT': 2, 'LATE_DISPATCH': 1} cbd 8 uncached tok 528034 ttft [1.3, 1.7, 1.9, 3.7, 3.9, 4.3, 4.4, 4.9, 5.4, 5.5, 5.5, 5.7, 5.8, 5.9, 6.0, 6.2, 6.9, 7.1, 7.6, 8.3, 8.4, 8.5, 8.6, 9.1, 9.9, 10.2, 11.5, 12.2, 13.0, 16.6]
f1 admit states {'LATE_ENGINE': 20, 'WRONG': 1, 'LATE_DISPATCH': 1} cbd 6 uncached tok 351675 ttft [0.9, 3.8, 4.4, 4.7, 4.9, 5.0, 5.3, 5.3, 6.3, 6.6, 6.9, 8.5, 9.8, 10.3, 10.8, 10.9, 11.0, 11.1, 11.6, 11.9, 12.4, 16.7]
F0 states on ca admits {'REJECTED': 14, 'WRONG': 6, 'LATE_ENGINE': 3, 'ONTIME_CORRECT': 7} cbd F0 9
ca admit ids not in f1: ['opp0001988', 'opp0002281', 'opp0002546', 'opp0002625', 'opp0003249', 'opp0003253', 'opp0005346', 'opp0005695', 'opp0006522', 'opp0006718', 'opp0006825', 'opp0006931']
f1 not in ca: ['opp0002046', 'opp0002074', 'opp0002185', 'opp0002409', 'opp0002477', 'opp0002497', 'opp0002611', 'opp0002933', 'opp0003601', 'opp0006478', 'opp0006553', 'opp0007121', 'opp0007187']
ca KEEP_REJECT 73 states {'REJECTED': 73}
