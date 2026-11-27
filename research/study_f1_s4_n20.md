F1 n20 s4 scoring; files score_out.txt an_out.txt an2_out.txt an3_out.txt an4_out.txt; scripts score.py an.py an2.py an3.py an4.py
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
== (0) headline per cell; decision kinds
f1 robot cloud on-time 151 / 283 acc_on_served 0.649007 n_dev_standing 132 SS 155 / 237 dash within_L 3935 worst (0.482, 'dash000') | decisions {'release_piece': 333, 'release_recall': 365, 'release_monitor': 4067, 'release_infeasible': 3424, 'state_action': 1619, 'touch': 1590, 'defer': 25, 'decline': 155}
tl robot cloud on-time 181 / 283 acc_on_served 0.668508 n_dev_standing 102 SS 199 / 237 dash within_L 5343 worst (0.654, 'dash002') | decisions {'release_piece': 296, 'release_recall': 407, 'release_monitor': 5509, 'release_infeasible': 2051, 'decline': 113, 'defer': 29, 'state_action': 2391, 'touch': 2391}
r3 robot cloud on-time 124 / 283 acc_on_served 0.717742 n_dev_standing 159 SS 163 / 237 dash within_L 3748 worst (0.448, 'dash001') | decisions {'release_piece': 333, 'release_recall': 458, 'release_monitor': 3977, 'release_infeasible': 3093, 'defer': 7, 'decline': 62, 'state_action': 3133, 'touch': 2152}
== (1) positive control: classifier vs committed rows
f1 committed cbd 132 classifier cbd 132 per-opp agree 283 / 283 | cloud-correct 98 device-correct 34 device-route n 132 cloud stands 151 | committed cloud-correct 98 device-correct 34
tl committed cbd 154 classifier cbd 154 per-opp agree 283 / 283 | cloud-correct 121 device-correct 33 device-route n 102 cloud stands 181 | committed cloud-correct 121 device-correct 33
r3 committed cbd 131 classifier cbd 131 per-opp agree 283 / 283 | cloud-correct 89 device-correct 42 device-route n 159 cloud stands 124 | committed cloud-correct 89 device-correct 42
== (2) paired diffs f1 minus tl; opps overlap 283 283 283
distinct questions 47
cbd                            -22 CI[-41,-7] excl0
cloud on-time                  -30 CI[-54,-9] excl0
cloud-correct                  -23 CI[-43,-7] excl0
device-route (not cloud)       +30 CI[+9,+54] excl0
dashcam within_L -1408 CI[-2264,-616] (20 60s blocks; instants 7850/7850/7850)
SS cloud on-time f1 155 tl 199 diff -44 CI[-59,-29] (237 questions)
== (2) paired diffs f1 minus r3; opps overlap 283 283 283
distinct questions 47
cbd                            +1 CI[-16,+16] incl0
cloud on-time                  +27 CI[+9,+46] excl0
cloud-correct                  +9 CI[-4,+23] incl0
device-route (not cloud)       -27 CI[-46,-9] excl0
dashcam within_L +187 CI[-212,+556] (20 60s blocks; instants 7850/7850/7850)
SS cloud on-time f1 155 r3 163 diff -8 CI[-22,+7] (237 questions)
== (3) loss decomposition e vs tl ; states {'f1': {'WRONG': 53, 'ONTIME_CORRECT': 98, 'LATE_ENGINE': 43, 'REJECTED': 87, 'LATE_DISPATCH': 2}, 'tl': {'WRONG': 60, 'ONTIME_CORRECT': 121, 'LATE_ENGINE': 22, 'REJECTED': 80}}
 on-time LOST by e 62 failing side (e state) {'LATE_ENGINE': 16, 'REJECTED': 46} | of lost, tl answer WRONG 20
 on-time GAINED by e 32 failing side (tl state) {'LATE_ENGINE': 11, 'REJECTED': 21} | e answer WRONG 13 correct 19
 cbd-differing opps by owner and states
   ('e+1', 'tl:LATE_ENGINE', 'e:ONTIME_CORRECT') 6
   ('e+1', 'tl:REJECTED', 'e:ONTIME_CORRECT') 5
   ('e+1', 'tl:WRONG', 'e:REJECTED') 2
   ('tl+1', 'tl:LATE_ENGINE', 'e:WRONG') 1
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:LATE_ENGINE') 9
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:REJECTED') 21
   ('tl+1', 'tl:REJECTED', 'e:WRONG') 4
== (3) loss decomposition e vs r3 ; states {'f1': {'WRONG': 53, 'ONTIME_CORRECT': 98, 'LATE_ENGINE': 43, 'REJECTED': 87, 'LATE_DISPATCH': 2}, 'r3': {'WRONG': 35, 'ONTIME_CORRECT': 89, 'REJECTED': 62, 'LATE_ENGINE': 97}}
 on-time LOST by e 28 failing side (e state) {'LATE_ENGINE': 7, 'REJECTED': 21} | of lost, r3 answer WRONG 7
 on-time GAINED by e 55 failing side (r3 state) {'REJECTED': 19, 'LATE_ENGINE': 36} | e answer WRONG 25 correct 30
 cbd-differing opps by owner and states
   ('e+1', 'r3:LATE_ENGINE', 'e:ONTIME_CORRECT') 11
   ('e+1', 'r3:REJECTED', 'e:ONTIME_CORRECT') 7
   ('e+1', 'r3:WRONG', 'e:LATE_ENGINE') 2
   ('r3+1', 'r3:LATE_ENGINE', 'e:WRONG') 3
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:LATE_ENGINE') 1
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:REJECTED') 9
   ('r3+1', 'r3:REJECTED', 'e:WRONG') 6
== (4) residency cold (analyse with opp ids)
f1 asks reached engine 196 resid-eligible 196 cold<.5 31 <.25 27 | declined recall opps 87
tl asks reached engine 203 resid-eligible 203 cold<.5 11 <.25 8 | declined recall opps 80
r3 asks reached engine 218 resid-eligible 218 cold<.5 42 <.25 35 | declined recall opps 62
RESID <.5 e-tl all q      n_q=45 e=31 tl=11 diff +20 CI[+10,+31]
RESID <.5 e-tl asked both n_q=34 e=27 tl=11 diff +16 CI[+6,+26]
RESID <.25 e-tl all q      n_q=45 e=27 tl=8 diff +19 CI[+10,+29]
RESID <.25 e-tl asked both n_q=34 e=23 tl=8 diff +15 CI[+6,+24]
 opps cold(<.5) in tl (11): fate in e {'sent in e: still cold': 5, 'sent in e: warm >=.5': 6}
 opps cold(<.5) in E (31): same opp in tl {'tl: cold': 5, 'tl: absent': 16, 'tl: warm': 10}
RESID <.5 e-r3 all q      n_q=45 e=31 r3=42 diff -11 CI[-27,+4]
RESID <.5 e-r3 asked both n_q=34 e=26 r3=39 diff -13 CI[-27,+1]
RESID <.25 e-r3 all q      n_q=45 e=27 r3=35 diff -8 CI[-22,+5]
RESID <.25 e-r3 asked both n_q=34 e=23 r3=32 diff -9 CI[-22,+3]
 opps cold(<.5) in r3 (42): fate in e {'sent in e: still cold': 9, 'sent in e: warm >=.5': 17, 'declined in e (b7)': 16}
 opps cold(<.5) in E (31): same opp in r3 {'r3: cold': 9, 'r3: absent': 12, 'r3: warm': 10}
== (7) FAIR share (RE-IMPLEMENTATION: robot+SS rows, oracle all-cloud with history, floors A_RD/A_SD; no over-32k exclusion, no question dedup)
f1 combined rel 0.5536 (abs gain 58.43 of oracle 105.55) | robot rel 0.5336 (46.97 of 88.03) | ss rel 0.6540 (11.45 of 17.51)
tl combined rel 0.6728 (abs gain 71.01 of oracle 105.55) | robot rel 0.6396 (56.30 of 88.03) | ss rel 0.8397 (14.71 of 17.51)
r3 combined rel 0.4796 (abs gain 50.62 of oracle 105.55) | robot rel 0.4382 (38.57 of 88.03) | ss rel 0.6878 (12.05 of 17.51)
FAIR f1-tl rel diff -0.1192 CI[-0.1862,-0.0551] | abs gain diff -12.58 CI[-20.20,-5.61]
FAIR f1-r3 rel diff +0.0740 CI[+0.0213,+0.1253] | abs gain diff +7.81 CI[+2.06,+14.13]
== (8) touches per robot session
f1 touch requests 1590 sessions 43 per-session min/med/max 0 0 685 zero-touch sessions 34
tl touch requests 2391 sessions 43 per-session min/med/max 0 0 1434 zero-touch sessions 40
r3 touch requests 2152 sessions 43 per-session min/med/max 0 0 786 zero-touch sessions 38

#### an_out
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
== (A) run validity / budget / counters F1 vs F0
f1 run_valid True wall 1200.032461 budget 822.47 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 1577, 'recall_CLOUD': 365, 'recall_DEFER': 25, 'recall_REJECT': 155, 'release_infeasible': 3424, 'release_infeasible_alert': 3424, 'submitted_touch': 1590, 'touch_considered': 1619, 'touch_guard_p_allowed': 21, 'touch_guard_p_consulted': 49, 'touch_guard_p_kept_cold': 28, 'touch_issued': 1590, 'touch_issued_gpu': 1588, 'touch_issued_host': 2, 'touch_price_milli_sum': 4770, 'touch_refused': 29, 'touch_refused_guard': 28, 'touch_refused_no_prefix': 1}
   arm_stats {'cf3_resident_epochs': 11998, 'cf3_resident_members_sum': 101721, 'cf3_resident_excluded_sum': 75840, 'pd_kv_bound_by_belief': 482, 'pd_decisions': 482, 'pd_decisions_state': 346, 'pd_gate_no_active_alert_episode': 199, 'pd_u_max': 17635, 'pd_u_sum': 1547148, 'pd_free_kv_min': 0, 'pd_free_kv_max': 62944, 'pd_free_kv_sum': 10155479, 'pd_decisions_request': 136, 'pd_gate_rebuild_fits_without_evicting': 222, 'cf_planner_decisions': 65931, 'cf_planner_decisions_state': 65931, 'cf_budget_ms': 20.0, 'cf3_resident_rotations': 158, 'pd_victim_found': 462, 'pd_gate_defer_to_latest_safe_st
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
f1 {'robo': (2102, [0.827, 5.447, 13.186]), 'asst': (169, [0.389, 1.266, 4.732]), 'dash': (4067, [0.23, 0.563, 1.226])}
tl {'robo': (2888, [0.429, 2.555, 5.161]), 'asst': (204, [0.298, 0.827, 2.386]), 'dash': (5509, [0.232, 0.539, 0.997])}
r3 {'robo': (2702, [0.544, 8.428, 24.037]), 'asst': (237, [0.476, 8.265, 23.667]), 'dash': (3977, [0.226, 0.57, 3.282])}
== (C) release_infeasible by class and SS/dash outcomes
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
  robo004| 0 1
  robo002| 0 1
  robo002| 0 1
  robo000| 0 2
f1 resid-eligible 196 mean cached frac 0.836 <.5 31
tl resid-eligible 203 mean cached frac 0.938 <.5 11
next ask after each admission: (admit, next, cached frac F1, F1 state, F0 state)
[('opp0002074', 'opp0002177', 0.99, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0006478', 'opp0006523', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0002536', 'opp0002645', 0.99, 'WRONG', 'WRONG'), ('opp0006964', 'opp0007017', 0.99, 'WRONG', 'REJECTED'), ('opp0007147', 'opp0007768', 0.19, 'LATE_ENGINE', 'REJECTED'), ('opp0002611', 'opp0002775', 1.0, 'WRONG', 'REJECTED'), ('opp0002185', 'opp0002217', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0007187', 'opp0007367', 1.0, 'LATE_ENGINE', 'REJECTED'), ('opp0007121', 'opp0007313', 0.99, 'WRONG', 'REJECTED'), ('opp0002471', 'opp0002611', 1.0, 'WRONG', 'REJECTED'), ('opp0002046', 'opp0002185', 0.27, 'LATE_ENGINE', 'REJECTED'), ('opp0002477', 'opp0002625', 0.5, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0003043', 'opp0003229', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0006553', 'opp0007187', 0.0, 'LATE_ENGINE', 'REJECTED'), ('opp0002497', 'opp0002803',
next-ask F1 states Counter({'ONTIME_CORRECT': 7, 'LATE_ENGINE': 6, 'WRONG': 5}) F0 Counter({'REJECTED': 13, 'ONTIME_CORRECT': 3, 'WRONG': 2})
f1 SS on-time 155 / 237
  SS opps by decision {'sent': 169, 'declined': 68} SS decisions decline/defer 72
tl SS on-time 199 / 237
  SS opps by decision {'sent': 204, 'declined': 33} SS decisions decline/defer 44
#### an3
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
f1 robot n 283 final dec {'CLOUD': 174, 'REJECT': 109} est_la q [0.3, 0.56, 1.79, 4.18, 8.57] queued_ahead q [0, 760, 2788, 17525, 41750] slack q [2.88, 2.9, 2.92, 2.95, 2.96] uncached_u q [187, 463, 1365, 11235, 18661]
f1 SS n 237 final dec {'CLOUD': 169, 'REJECT': 68} est_la q [0.17, 0.28, 0.54, 2.67, 6.16] queued_ahead q [0, 380, 2170, 15334, 39244] slack q [1.88, 1.89, 1.91, 1.92, 1.95] uncached_u q [223, 327, 343, 1336, 1361]
tl robot n 283 final dec {'CLOUD': 203, 'REJECT': 80} est_la q [0.24, 0.44, 1.16, 3.33, 4.76] queued_ahead q [0, 380, 1520, 5201, 14339] slack q [2.88, 2.9, 2.92, 2.95, 2.97] uncached_u q [185, 543, 1715, 11731, 21811]
tl SS n 237 final dec {'CLOUD': 204, 'REJECT': 33} est_la q [0.13, 0.19, 0.35, 0.8, 2.51] queued_ahead q [0, 380, 1140, 4140, 14899] slack q [1.91, 1.92, 1.94, 1.96, 1.97] uncached_u q [1, 224, 335, 1331, 1353]
f1 uncached prefill tokens total 4463298 {'robo': 2294839, 'dash': 2043888, 'asst': 124571} n requests 6355
  robot requests by decision kind {'release_piece': 333, 'release_recall': 196, 'touch': 1590}
tl uncached prefill tokens total 4238814 {'robo': 1427962, 'dash': 2698062, 'asst': 112790} n requests 8603
  robot requests by decision kind {'release_piece': 296, 'release_recall': 203, 'touch': 2391}
#### an4
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
f1 robot uncached tokens by kind {'release_piece': 1378223, 'release_recall': 880243, 'touch': 36373} n {'release_piece': 329, 'release_recall': 196, 'touch': 1577}
  dash release_monitor n None uncached dash 2043888
tl robot uncached tokens by kind {'release_piece': 885433, 'release_recall': 530661, 'touch': 11868} n {'release_piece': 295, 'release_recall': 203, 'touch': 2390}
  dash release_monitor n None uncached dash 2698062
22 admissions: uncached tokens 351675 ttft [0.9, 3.8, 4.4, 4.7, 4.9, 5.0, 5.3, 5.3, 6.3, 6.6, 6.9, 8.5, 9.8, 10.3, 10.8, 10.9, 11.0, 11.1, 11.6, 11.9, 12.4, 16.7]
