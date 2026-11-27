== (0) headline per cell; decision kinds
f1 robot cloud on-time 83 / 132 acc_on_served 0.614458 n_dev_standing 49 SS 319 / 357 dash within_L 6153 worst (0.413, 'dash002') | decisions {'release_piece': 149, 'release_monitor': 6801, 'release_recall': 433, 'release_infeasible': 3164, 'state_action': 1148, 'touch': 1148, 'defer': 51, 'decline': 56}
cd robot cloud on-time 85 / 132 acc_on_served 0.670588 n_dev_standing 47 SS 305 / 357 dash within_L 6042 worst (0.45, 'dash002') | decisions {'release_piece': 156, 'release_monitor': 6665, 'release_recall': 421, 'release_infeasible': 3517, 'defer': 11, 'decline': 68, 'state_action': 1862, 'touch': 1862}
c2 robot cloud on-time 92 / 132 acc_on_served 0.641304 n_dev_standing 40 SS 324 / 357 dash within_L 6459 worst (0.48, 'dash001') | decisions {'release_piece': 150, 'release_monitor': 6997, 'release_recall': 440, 'release_infeasible': 3195, 'defer': 17, 'decline': 49, 'state_action': 2366, 'touch': 20}
a robot cloud on-time 91 / 132 acc_on_served 0.692308 n_dev_standing 41 SS 309 / 357 dash within_L 5895 worst (0.453, 'dash001') | decisions {'release_piece': 150, 'release_monitor': 6572, 'release_recall': 441, 'release_infeasible': 3480, 'defer': 16, 'decline': 48, 'state_action': 2284, 'touch': 2284}
pw robot cloud on-time 95 / 132 acc_on_served 0.673684 n_dev_standing 37 SS 328 / 357 dash within_L 6412 worst (0.5, 'dash001') | decisions {'release_piece': 145, 'release_monitor': 7073, 'release_recall': 446, 'release_infeasible': 3180, 'defer': 14, 'decline': 43, 'state_action': 2468, 'touch': 1277}
la robot cloud on-time 83 / 132 acc_on_served 0.710843 n_dev_standing 49 SS 310 / 357 dash within_L 6301 worst (0.506, 'dash000') | decisions {'release_piece': 158, 'release_monitor': 6907, 'release_recall': 427, 'release_infeasible': 3442, 'defer': 15, 'decline': 62, 'state_action': 1477, 'touch': 1031}
e robot cloud on-time 73 / 132 acc_on_served 0.657534 n_dev_standing 59 SS 299 / 357 dash within_L 5617 worst (0.446, 'dash004') | decisions {'release_piece': 163, 'release_monitor': 6202, 'release_recall': 462, 'release_infeasible': 3773, 'decline': 27, 'state_action': 1498, 'defer': 1, 'touch': 630}
r3 robot cloud on-time 72 / 132 acc_on_served 0.680556 n_dev_standing 60 SS 311 / 357 dash within_L 6112 worst (0.454, 'dash005') | decisions {'release_piece': 155, 'release_monitor': 6779, 'release_recall': 455, 'release_infeasible': 3141, 'decline': 34, 'state_action': 1434, 'touch': 1371}
== (1) positive control: classifier vs committed rows
f1 committed cbd 63 classifier cbd 63 per-opp agree 132 / 132 | cloud-correct 51 device-correct 12 device-route n 49 cloud stands 83 | committed cloud-correct 51 device-correct 12
cd committed cbd 69 classifier cbd 69 per-opp agree 132 / 132 | cloud-correct 57 device-correct 12 device-route n 47 cloud stands 85 | committed cloud-correct 57 device-correct 12
c2 committed cbd 70 classifier cbd 70 per-opp agree 132 / 132 | cloud-correct 59 device-correct 11 device-route n 40 cloud stands 92 | committed cloud-correct 59 device-correct 11
a committed cbd 74 classifier cbd 74 per-opp agree 132 / 132 | cloud-correct 63 device-correct 11 device-route n 41 cloud stands 91 | committed cloud-correct 63 device-correct 11
pw committed cbd 71 classifier cbd 71 per-opp agree 132 / 132 | cloud-correct 64 device-correct 7 device-route n 37 cloud stands 95 | committed cloud-correct 64 device-correct 7
la committed cbd 77 classifier cbd 77 per-opp agree 132 / 132 | cloud-correct 59 device-correct 18 device-route n 49 cloud stands 83 | committed cloud-correct 59 device-correct 18
e committed cbd 66 classifier cbd 66 per-opp agree 132 / 132 | cloud-correct 48 device-correct 18 device-route n 59 cloud stands 73 | committed cloud-correct 48 device-correct 18
r3 committed cbd 72 classifier cbd 72 per-opp agree 132 / 132 | cloud-correct 49 device-correct 23 device-route n 60 cloud stands 72 | committed cloud-correct 49 device-correct 23
== (2) paired diffs f1 minus cd; opps overlap 132 132 132
distinct questions 20
cbd                            -6 CI[-17,+4] incl0
cloud on-time                  -2 CI[-15,+13] incl0
cloud-correct                  -6 CI[-15,+3] incl0
device-route (not cloud)       +2 CI[-13,+15] incl0
dashcam within_L +111 CI[-434,+577] (20 60s blocks; instants 11764/11764/11764)
SS cloud on-time f1 319 cd 305 diff +14 CI[+0,+28] (357 questions)
== (2) paired diffs f1 minus r3; opps overlap 132 132 132
distinct questions 20
cbd                            -9 CI[-27,+6] incl0
cloud on-time                  +11 CI[-7,+30] incl0
cloud-correct                  +2 CI[-10,+14] incl0
device-route (not cloud)       -11 CI[-30,+7] incl0
dashcam within_L +41 CI[-690,+774] (20 60s blocks; instants 11764/11764/11764)
SS cloud on-time f1 319 r3 311 diff +8 CI[-7,+23] (357 questions)
== (3) loss decomposition e vs cd ; states {'f1': {'WRONG': 32, 'LATE_ENGINE': 15, 'ONTIME_CORRECT': 51, 'REJECTED': 27, 'LATE_DISPATCH': 7}, 'cd': {'WRONG': 28, 'ONTIME_CORRECT': 57, 'LATE_ENGINE': 10, 'REJECTED': 37}}
 on-time LOST by e 15 failing side (e state) {'LATE_ENGINE': 6, 'REJECTED': 7, 'LATE_DISPATCH': 2} | of lost, cd answer WRONG 3
 on-time GAINED by e 13 failing side (cd state) {'REJECTED': 12, 'LATE_ENGINE': 1} | e answer WRONG 7 correct 6
 cbd-differing opps by owner and states
   ('cd+1', 'cd:ONTIME_CORRECT', 'e:LATE_DISPATCH') 2
   ('cd+1', 'cd:ONTIME_CORRECT', 'e:LATE_ENGINE') 1
   ('cd+1', 'cd:ONTIME_CORRECT', 'e:REJECTED') 4
   ('cd+1', 'cd:REJECTED', 'e:WRONG') 4
   ('e+1', 'cd:LATE_ENGINE', 'e:ONTIME_CORRECT') 1
   ('e+1', 'cd:REJECTED', 'e:ONTIME_CORRECT') 4
== (3) loss decomposition e vs r3 ; states {'f1': {'WRONG': 32, 'LATE_ENGINE': 15, 'ONTIME_CORRECT': 51, 'REJECTED': 27, 'LATE_DISPATCH': 7}, 'r3': {'WRONG': 23, 'ONTIME_CORRECT': 49, 'LATE_ENGINE': 26, 'REJECTED': 34}}
 on-time LOST by e 16 failing side (e state) {'LATE_ENGINE': 6, 'LATE_DISPATCH': 4, 'REJECTED': 6} | of lost, r3 answer WRONG 4
 on-time GAINED by e 27 failing side (r3 state) {'LATE_ENGINE': 9, 'REJECTED': 18} | e answer WRONG 13 correct 14
 cbd-differing opps by owner and states
   ('e+1', 'r3:LATE_ENGINE', 'e:ONTIME_CORRECT') 5
   ('e+1', 'r3:REJECTED', 'e:ONTIME_CORRECT') 4
   ('r3+1', 'r3:LATE_ENGINE', 'e:WRONG') 1
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:LATE_DISPATCH') 3
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:LATE_ENGINE') 1
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:REJECTED') 4
   ('r3+1', 'r3:REJECTED', 'e:WRONG') 9
== (9) per-opportunity flips cd vs pw (noise floor at 1x)
cbd flips 16 (cd+1 7 pw+1 9) | on-time(source cloud) flips 32 (cd on-time only 11, pw only 21) | of 132
== (4) residency cold (analyse with opp ids)
f1 asks reached engine 105 resid-eligible 105 cold<.5 9 <.25 6 | declined recall opps 27
cd asks reached engine 95 resid-eligible 95 cold<.5 9 <.25 5 | declined recall opps 37
c2 asks reached engine 110 resid-eligible 110 cold<.5 9 <.25 4 | declined recall opps 22
a asks reached engine 108 resid-eligible 108 cold<.5 12 <.25 7 | declined recall opps 24
pw asks reached engine 107 resid-eligible 107 cold<.5 8 <.25 4 | declined recall opps 25
la asks reached engine 100 resid-eligible 100 cold<.5 11 <.25 6 | declined recall opps 32
e asks reached engine 105 resid-eligible 105 cold<.5 20 <.25 15 | declined recall opps 27
r3 asks reached engine 98 resid-eligible 98 cold<.5 18 <.25 12 | declined recall opps 34
RESID <.5 e-cd all q      n_q=20 e=9 cd=9 diff +0 CI[-6,+6]
RESID <.5 e-cd asked both n_q=17 e=8 cd=9 diff -1 CI[-6,+5]
RESID <.25 e-cd all q      n_q=20 e=6 cd=5 diff +1 CI[-4,+6]
RESID <.25 e-cd asked both n_q=17 e=5 cd=5 diff +0 CI[-5,+5]
 opps cold(<.5) in cd (9): fate in e {'declined in e (b7)': 5, 'sent in e: warm >=.5': 4}
 opps cold(<.5) in E (9): same opp in cd {'cd: warm': 6, 'cd: absent': 3}
RESID <.5 e-r3 all q      n_q=19 e=9 r3=18 diff -9 CI[-17,-1]
RESID <.5 e-r3 asked both n_q=19 e=9 r3=18 diff -9 CI[-17,-1]
RESID <.25 e-r3 all q      n_q=19 e=6 r3=12 diff -6 CI[-13,+1]
RESID <.25 e-r3 asked both n_q=19 e=6 r3=12 diff -6 CI[-13,+1]
 opps cold(<.5) in r3 (18): fate in e {'declined in e (b7)': 10, 'sent in e: warm >=.5': 8}
 opps cold(<.5) in E (9): same opp in r3 {'r3: warm': 7, 'r3: absent': 2}
== (7) FAIR share (RE-IMPLEMENTATION: robot+SS rows, oracle all-cloud with history, floors A_RD/A_SD; no over-32k exclusion, no question dedup)
f1 combined rel 0.7324 (abs gain 49.39 of oracle 67.44) | robot rel 0.6288 (25.82 of 41.06) | ss rel 0.8936 (23.57 of 26.38)
cd combined rel 0.7262 (abs gain 48.98 of oracle 67.44) | robot rel 0.6439 (26.44 of 41.06) | ss rel 0.8543 (22.54 of 26.38)
c2 combined rel 0.7793 (abs gain 52.56 of oracle 67.44) | robot rel 0.6970 (28.62 of 41.06) | ss rel 0.9076 (23.94 of 26.38)
a combined rel 0.7583 (abs gain 51.14 of oracle 67.44) | robot rel 0.6894 (28.31 of 41.06) | ss rel 0.8655 (22.83 of 26.38)
pw combined rel 0.7976 (abs gain 53.79 of oracle 67.44) | robot rel 0.7197 (29.55 of 41.06) | ss rel 0.9188 (24.24 of 26.38)
la combined rel 0.7225 (abs gain 48.73 of oracle 67.44) | robot rel 0.6288 (25.82 of 41.06) | ss rel 0.8683 (22.91 of 26.38)
e combined rel 0.6643 (abs gain 44.80 of oracle 67.44) | robot rel 0.5530 (22.71 of 41.06) | ss rel 0.8375 (22.09 of 26.38)
r3 combined rel 0.6729 (abs gain 45.38 of oracle 67.44) | robot rel 0.5455 (22.40 of 41.06) | ss rel 0.8711 (22.98 of 26.38)
FAIR f1-cd rel diff +0.0061 CI[-0.0540,+0.0739] | abs gain diff +0.41 CI[-3.76,+4.92]
FAIR f1-r3 rel diff +0.0595 CI[-0.0279,+0.1471] | abs gain diff +4.01 CI[-1.72,+10.49]
== (8) touches per robot session
f1 touch requests 1148 sessions 22 per-session min/med/max 0 1.0 1040 zero-touch sessions 10
cd touch requests 1862 sessions 22 per-session min/med/max 0 0.0 1161 zero-touch sessions 17
c2 touch requests 20 sessions 22 per-session min/med/max 0 0.0 20 zero-touch sessions 21
a touch requests 2284 sessions 22 per-session min/med/max 0 0.0 1270 zero-touch sessions 19
pw touch requests 1277 sessions 22 per-session min/med/max 0 0.0 1263 zero-touch sessions 20
la touch requests 1031 sessions 22 per-session min/med/max 0 0.0 800 zero-touch sessions 18
e touch requests 630 sessions 22 per-session min/med/max 0 0.0 405 zero-touch sessions 19
r3 touch requests 1371 sessions 22 per-session min/med/max 0 0.0 819 zero-touch sessions 19
##### an
== (A) run validity / budget / counters F1 vs F0
f1 run_valid True wall 1200.000217 budget 831.5 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 1148, 'recall_CLOUD': 433, 'recall_DEFER': 51, 'recall_REJECT': 56, 'release_infeasible': 3164, 'release_infeasible_alert': 3164, 'submitted_touch': 1148, 'touch_considered': 1148, 'touch_guard_p_allowed': 2, 'touch_guard_p_consulted': 2, 'touch_issued': 1148, 'touch_issued_gpu': 1148, 'touch_price_milli_sum': 3444}
   arm_stats {'cf3_resident_epochs': 12000, 'cf3_resident_members_sum': 58027, 'cf3_resident_excluded_sum': 36900, 'pd_kv_bound_by_belief': 283, 'pd_decisions': 283, 'pd_decisions_state': 154, 'pd_gate_no_active_alert_episode': 32, 'pd_u_max': 20707, 'pd_u_sum': 1381251, 'pd_free_kv_min': 0, 'pd_free_kv_max': 31472, 'pd_free_kv_sum': 2762679, 'pd_decisions_request': 129, 'pd_gate_rebuild_fits_without_evicting': 145, 'cf_planner_decisions': 62122, 'cf_planner_decisions_state': 62122, 'cf_budget_ms': 20.0, 'cf3_resident_rotations': 87, 'pd_deferred_to_guard_epochs': 884, 'pd_victim_found': 268, 'pd_harm_n': 106, 'pd_harm_micro_sum': 289788375, 'pd_harm_micro_max': 7340913, 'pd_harm_gt_0': 106, 'pd_harm_gt_0p01': 97, 'pd_harm_gt_0p1': 87, 'pd_harm_gt_0p65824': 86, 'pd_harm_gt_1': 84, 'pd_harm_gt_2': 67, 'pd_harm_over_bar': 84, 'pd_request_crossed_bar_unexpressible': 46, 'pd_gate_defer_to_latest_safe_start': 34, 'pd_request_defers': 32, 'pd_protects': 37, 'cf3_considered': 33, 'cf3_gate_no_question_estimate': 2, 'pd_harm_gt_5': 15, 'cf3_gate_admit_forfeit_valued': 6, 'cf3_net_checked': 6, 'cf3_admitted': 6, 'cf3_claim_f1_opened': 6, 'pd_gate_harm_does_not_exceed_the_bar': 22, 'cf3_gate_net_does_not_exceed_the_bar': 7, 'cf3_resident_stale_session': 53191, 'cf3_resident_epochs_with_excluded': 7358, 'pd_state_chunks': 4, 'cf3_gate_not_in_resident_set': 14, 'pd_state_defers': 2, 'pd_protect_unexpressible_session_busy': 1, 'cf3_gate_next_question_beyond_horizon': 3, 'cf3_gate_no_future_gain': 1, 'catchup_candidates': 0}
   residency-cold counters {'belief_to_cold': 27, 'state_priced_build_cold': 63} {'book0b_cold_pieces': 43}
cd run_valid True wall 1200.000132 budget 838.04 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 1862, 'recall_CLOUD': 421, 'recall_DEFER': 11, 'recall_REJECT': 68, 'release_infeasible': 3517, 'release_infeasible_alert': 3517, 'submitted_touch': 1862, 'touch_considered': 1862, 'touch_guard_p_allowed': 14, 'touch_guard_p_consulted': 14, 'touch_issued': 1862, 'touch_issued_gpu': 1862, 'touch_price_milli_sum': 5586}
   arm_stats {'cf_planner_decisions': 55179, 'cf_planner_decisions_state': 55179, 'cf_budget_ms': 20.0}
   residency-cold counters {'belief_to_cold': 24, 'state_priced_build_cold': 59} {'book0b_cold_pieces': 40}
r3 run_valid True wall 1200.000179 budget 815.42 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 1371, 'recall_CLOUD': 455, 'recall_REJECT': 34, 'release_infeasible': 3141, 'release_infeasible_alert': 3141, 'submitted_touch': 1371, 'touch_considered': 1434, 'touch_issued': 1371, 'touch_issued_gpu': 1371, 'touch_price_milli_sum': 4113, 'touch_refused': 63, 'touch_refused_guard': 63}
   arm_stats {'cf_planner_decisions': 54766, 'cf_planner_decisions_state': 54766, 'cf_budget_ms': 20.0}
   residency-cold counters {'belief_to_cold': 29, 'state_priced_build_cold': 61} {}
== (B) TTFT t_first_token-t_submit quantiles per class
f1 {'robo': (1401, [0.474, 2.557, 5.752]), 'asst': (327, [0.511, 1.013, 3.102]), 'dash': (6797, [0.331, 0.719, 1.956])}
cd {'robo': (2113, [0.827, 5.931, 9.362]), 'asst': (325, [0.524, 1.241, 3.5]), 'dash': (6662, [0.341, 0.724, 2.186])}
r3 {'robo': (1623, [0.851, 8.599, 18.112]), 'asst': (356, [0.606, 2.337, 9.895]), 'dash': (6776, [0.356, 0.756, 3.041])}
== (C) release_infeasible by class and SS/dash outcomes
f1 [('none', 3164)]
  monitor within_L {('monitor', True): 6153, ('monitor', False): 5611}  n monitor opps 11764
cd [('none', 3517)]
  monitor within_L {('monitor', True): 6042, ('monitor', False): 5722}  n monitor opps 11764
r3 [('none', 3141)]
  monitor within_L {('monitor', True): 6112, ('monitor', False): 5652}  n monitor opps 11764
== (D) cf admissions: outcomes
Counter({'not_in_resident_set': 14, 'net_does_not_exceed_the_bar': 7, 'admit_forfeit_valued': 6, 'next_question_beyond_horizon': 3, 'no_question_estimate': 2, 'no_future_gain': 1}) 6
opp0001942 robo006 t=205.2 net 6.1 f1 state LATE_DISPATCH cbd 0 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 1.7
opp0003652 robo004 t=369.1 net 1.8 f1 state LATE_ENGINE cbd 1 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 27.7
opp0003840 robo001 t=387.8 net 2.2 f1 state WRONG cbd 0 | F0 state REJECTED cbd 1 | next ask dt 41.6
opp0004451 robo003 t=445.8 net 10.9 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 26.4
opp0008714 robo003 t=857.4 net 6.1 f1 state LATE_ENGINE cbd 0 | F0 state WRONG cbd 0 | next ask dt 22.0
opp0011117 robo000 t=1089.6 net 3.3 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 39.7
admit summary f1 states Counter({'LATE_ENGINE': 4, 'LATE_DISPATCH': 1, 'WRONG': 1}) F0 states same opps Counter({'REJECTED': 3, 'ONTIME_CORRECT': 2, 'WRONG': 1}) cbd f1 2 cbd F0 4
KEEP_REJECT 27 cbd f1 4 F0 state Counter({'REJECTED': 15, 'ONTIME_CORRECT': 7, 'LATE_ENGINE': 5})
##### an2
touch decisions per robot session F0 vs F1 (total) 1862 1148
cbd differs F1 worse 11 {'late, warm ask, not admitted: queue/congestion': 2, 'cf KEEP_REJECT (considered, not admitted)': 4, 'cf ADMISSION (late-engine/late)': 2, 'F1 gained (F0 failed)': 3}
cbd differs F1 better 5 {'F1 gained (F0 failed)': 5}
on-time differs F1 worse 15 {'late, warm ask, not admitted: queue/congestion': 3, 'cf KEEP_REJECT (considered, not admitted)': 7, 'cf ADMISSION (late-engine/late)': 3, 'cold ask, touches not fewer': 2}
on-time differs F1 better 13 {'F1 gained (F0 failed)': 12, 'cf ADMISSION (late-engine/late)': 1}
sessions: touches F0->F1
  robo005| 324 49
  robo000| 280 28
  robo006| 1161 1040
  robo001| 60 7
  robo003| 37 4
  robo002| 0 1
f1 resid-eligible 105 mean cached frac 0.903 <.5 9
cd resid-eligible 95 mean cached frac 0.889 <.5 9
next ask after each admission: (admit, next, cached frac F1, F1 state, F0 state)
[('opp0003840', 'opp0004083', 1.0, 'WRONG', 'REJECTED'), ('opp0001942', 'opp0002912', 1.0, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0008714', 'opp0010346', 1.0, 'ONTIME_CORRECT', 'REJECTED'), ('opp0011117', 'opp0011909', 1.0, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0003652', 'opp0003857', 0.4, 'LATE_ENGINE', 'ONTIME_CORRECT')]
next-ask F1 states Counter({'ONTIME_CORRECT': 3, 'WRONG': 1, 'LATE_ENGINE': 1}) F0 Counter({'ONTIME_CORRECT': 3, 'REJECTED': 2})
f1 SS on-time 319 / 357
  SS opps by decision {'sent': 328, 'declined': 29} SS decisions decline/defer 38
cd SS on-time 305 / 357
  SS opps by decision {'sent': 326, 'declined': 31} SS decisions decline/defer 36
##### an3
f1 robot n 132 final dec {'CLOUD': 99, 'REJECT': 33} est_la q [0.37, 0.54, 0.91, 2.62, 4.12] queued_ahead q [380, 760, 2090, 3802, 6104] slack q [2.03, 2.75, 2.91, 2.94, 2.96] uncached_u q [193, 729, 2075, 9639, 19015]
f1 SS n 357 final dec {'CLOUD': 328, 'REJECT': 29} est_la q [0.21, 0.33, 0.49, 0.75, 1.16] queued_ahead q [380, 760, 1786, 3532, 6088] slack q [1.9, 1.91, 1.92, 1.96, 1.97] uncached_u q [1, 223, 446, 1340, 1368]
cd robot n 132 final dec {'CLOUD': 95, 'REJECT': 37} est_la q [0.37, 0.61, 1.17, 3.28, 4.96] queued_ahead q [380, 790, 2653, 5003, 17918] slack q [2.88, 2.9, 2.92, 2.95, 2.96] uncached_u q [189, 903, 2813, 10677, 17851]
cd SS n 357 final dec {'CLOUD': 326, 'REJECT': 31} est_la q [0.28, 0.37, 0.53, 0.82, 1.67] queued_ahead q [380, 760, 1784, 3612, 9563] slack q [1.89, 1.91, 1.92, 1.95, 1.96] uncached_u q [228, 336, 1333, 1352, 1622]
f1 uncached prefill tokens total 4945168 {'robo': 903303, 'dash': 3774974, 'asst': 266891} n requests 8531
  robot requests by decision kind {'release_piece': 149, 'release_recall': 105, 'touch': 1148}
cd uncached prefill tokens total 5044087 {'robo': 933840, 'dash': 3782618, 'asst': 327629} n requests 9104
  robot requests by decision kind {'release_piece': 156, 'release_recall': 95, 'touch': 1862}
##### an4
f1 robot uncached tokens by kind {'release_piece': 462288, 'release_recall': 377335, 'touch': 63680} n {'release_piece': 148, 'release_recall': 105, 'touch': 1148}
  dash release_monitor n None uncached dash 3774974
cd robot uncached tokens by kind {'release_piece': 581198, 'release_recall': 306298, 'touch': 46344} n {'release_piece': 156, 'release_recall': 95, 'touch': 1862}
  dash release_monitor n None uncached dash 3782618
22 admissions: uncached tokens 96207 ttft [2.2, 2.5, 4.1, 4.4, 5.3, 7.5]
