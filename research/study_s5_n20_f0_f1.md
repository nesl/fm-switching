KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
== (0) headline per cell; decision kinds
f1 robot cloud on-time 137 / 222 acc_on_served 0.569343 n_dev_standing 85 SS 174 / 240 dash within_L 4174 worst (0.494, 'dash001') | decisions {'release_piece': 332, 'release_recall': 374, 'release_monitor': 4429, 'release_infeasible': 2952, 'decline': 88, 'defer': 28, 'state_action': 4180, 'touch': 4180}
tl robot cloud on-time 148 / 222 acc_on_served 0.574324 n_dev_standing 74 SS 211 / 240 dash within_L 5025 worst (0.619, 'dash003') | decisions {'release_piece': 321, 'release_recall': 401, 'release_monitor': 5288, 'release_infeasible': 2094, 'defer': 14, 'decline': 61, 'state_action': 5435, 'touch': 5435}
r3 robot cloud on-time 145 / 222 acc_on_served 0.558621 n_dev_standing 77 SS 187 / 240 dash within_L 4489 worst (0.519, 'dash001') | decisions {'release_piece': 344, 'release_recall': 431, 'release_monitor': 4854, 'release_infeasible': 2342, 'defer': 6, 'decline': 31, 'state_action': 4304, 'touch': 3353}
== (1) positive control: classifier vs committed rows
f1 committed cbd 108 classifier cbd 108 per-opp agree 222 / 222 | cloud-correct 78 device-correct 30 device-route n 85 cloud stands 137 | committed cloud-correct 78 device-correct 30
tl committed cbd 109 classifier cbd 109 per-opp agree 222 / 222 | cloud-correct 85 device-correct 24 device-route n 74 cloud stands 148 | committed cloud-correct 85 device-correct 24
r3 committed cbd 106 classifier cbd 106 per-opp agree 222 / 222 | cloud-correct 81 device-correct 25 device-route n 77 cloud stands 145 | committed cloud-correct 81 device-correct 25
== (2) paired diffs f1 minus tl; opps overlap 222 222 222
distinct questions 40
cbd                            -1 CI[-11,+9] incl0
cloud on-time                  -11 CI[-40,+29] incl0
cloud-correct                  -7 CI[-21,+8] incl0
device-route (not cloud)       +11 CI[-29,+40] incl0
dashcam within_L -851 CI[-1377,-372] (20 60s blocks; instants 7862/7862/7862)
SS cloud on-time f1 174 tl 211 diff -37 CI[-53,-22] (240 questions)
== (2) paired diffs f1 minus r3; opps overlap 222 222 222
distinct questions 40
cbd                            +2 CI[-8,+13] incl0
cloud on-time                  -8 CI[-22,+6] incl0
cloud-correct                  -3 CI[-15,+9] incl0
device-route (not cloud)       +8 CI[-6,+22] incl0
dashcam within_L -315 CI[-803,+125] (20 60s blocks; instants 7862/7862/7862)
SS cloud on-time f1 174 r3 187 diff -13 CI[-29,+2] (240 questions)
== (3) loss decomposition e vs tl ; states {'f1': {'WRONG': 59, 'ONTIME_CORRECT': 78, 'LATE_ENGINE': 39, 'REJECTED': 43, 'LATE_DISPATCH': 3}, 'tl': {'WRONG': 63, 'ONTIME_CORRECT': 85, 'REJECTED': 42, 'LATE_ENGINE': 32}}
 on-time LOST by e 44 failing side (e state) {'REJECTED': 25, 'LATE_ENGINE': 17, 'LATE_DISPATCH': 2} | of lost, tl answer WRONG 20
 on-time GAINED by e 33 failing side (tl state) {'REJECTED': 23, 'LATE_ENGINE': 10} | e answer WRONG 16 correct 17
 cbd-differing opps by owner and states
   ('e+1', 'tl:LATE_ENGINE', 'e:ONTIME_CORRECT') 3
   ('e+1', 'tl:REJECTED', 'e:ONTIME_CORRECT') 4
   ('e+1', 'tl:WRONG', 'e:LATE_ENGINE') 3
   ('e+1', 'tl:WRONG', 'e:REJECTED') 2
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:LATE_DISPATCH') 1
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:LATE_ENGINE') 6
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:REJECTED') 6
== (3) loss decomposition e vs r3 ; states {'f1': {'WRONG': 59, 'ONTIME_CORRECT': 78, 'LATE_ENGINE': 39, 'REJECTED': 43, 'LATE_DISPATCH': 3}, 'r3': {'WRONG': 64, 'ONTIME_CORRECT': 81, 'LATE_ENGINE': 46, 'REJECTED': 31}}
 on-time LOST by e 36 failing side (e state) {'REJECTED': 19, 'LATE_ENGINE': 14, 'LATE_DISPATCH': 3} | of lost, r3 answer WRONG 15
 on-time GAINED by e 28 failing side (r3 state) {'LATE_ENGINE': 16, 'REJECTED': 12} | e answer WRONG 10 correct 18
 cbd-differing opps by owner and states
   ('e+1', 'r3:LATE_ENGINE', 'e:ONTIME_CORRECT') 6
   ('e+1', 'r3:REJECTED', 'e:ONTIME_CORRECT') 4
   ('e+1', 'r3:WRONG', 'e:LATE_ENGINE') 3
   ('e+1', 'r3:WRONG', 'e:REJECTED') 1
   ('r3+1', 'r3:LATE_ENGINE', 'e:WRONG') 1
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:LATE_DISPATCH') 2
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:LATE_ENGINE') 4
   ('r3+1', 'r3:ONTIME_CORRECT', 'e:REJECTED') 4
   ('r3+1', 'r3:REJECTED', 'e:WRONG') 1
== (4) residency cold (analyse with opp ids)
f1 asks reached engine 179 resid-eligible 179 cold<.5 28 <.25 22 | declined recall opps 43
tl asks reached engine 180 resid-eligible 180 cold<.5 11 <.25 9 | declined recall opps 42
r3 asks reached engine 191 resid-eligible 191 cold<.5 22 <.25 20 | declined recall opps 31
RESID <.5 e-tl all q      n_q=38 e=28 tl=11 diff +17 CI[+7,+27]
RESID <.5 e-tl asked both n_q=36 e=28 tl=11 diff +17 CI[+7,+28]
RESID <.25 e-tl all q      n_q=38 e=22 tl=9 diff +13 CI[+4,+22]
RESID <.25 e-tl asked both n_q=36 e=22 tl=9 diff +13 CI[+4,+22]
 opps cold(<.5) in tl (11): fate in e {'declined in e (b7)': 3, 'sent in e: warm >=.5': 6, 'sent in e: still cold': 2}
 opps cold(<.5) in E (28): same opp in tl {'tl: warm': 19, 'tl: absent': 7, 'tl: cold': 2}
RESID <.5 e-r3 all q      n_q=38 e=28 r3=22 diff +6 CI[-6,+17]
RESID <.5 e-r3 asked both n_q=35 e=27 r3=21 diff +6 CI[-5,+17]
RESID <.25 e-r3 all q      n_q=38 e=22 r3=20 diff +2 CI[-8,+11]
RESID <.25 e-r3 asked both n_q=35 e=21 r3=19 diff +2 CI[-8,+11]
 opps cold(<.5) in r3 (22): fate in e {'sent in e: still cold': 8, 'sent in e: warm >=.5': 9, 'declined in e (b7)': 5}
 opps cold(<.5) in E (28): same opp in r3 {'r3: warm': 14, 'r3: cold': 8, 'r3: absent': 6}
== (7) FAIR share (RE-IMPLEMENTATION: robot+SS rows, oracle all-cloud with history, floors A_RD/A_SD; no over-32k exclusion, no question dedup)
f1 combined rel 0.6392 (abs gain 55.47 of oracle 86.79) | robot rel 0.6171 (42.62 of 69.06) | ss rel 0.7250 (12.86 of 17.74)
tl combined rel 0.7101 (abs gain 61.63 of oracle 86.79) | robot rel 0.6667 (46.04 of 69.06) | ss rel 0.8792 (15.59 of 17.74)
r3 combined rel 0.6789 (abs gain 58.92 of oracle 86.79) | robot rel 0.6532 (45.10 of 69.06) | ss rel 0.7792 (13.82 of 17.74)
FAIR f1-tl rel diff -0.0709 CI[-0.1778,+0.0590] | abs gain diff -6.16 CI[-14.87,+4.88]
FAIR f1-r3 rel diff -0.0397 CI[-0.0942,+0.0129] | abs gain diff -3.45 CI[-7.79,+1.13]
== (8) touches per robot session
f1 touch requests 4180 sessions 43 per-session min/med/max 0 0 1117 zero-touch sessions 31
tl touch requests 5435 sessions 42 per-session min/med/max 0 0.0 1641 zero-touch sessions 36
r3 touch requests 3353 sessions 42 per-session min/med/max 0 0.0 993 zero-touch sessions 35
#### an
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
== (A) run validity / budget / counters F1 vs F0
f1 run_valid True wall 1199.935701 budget 771.19 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 4174, 'recall_CLOUD': 374, 'recall_DEFER': 28, 'recall_REJECT': 88, 'release_infeasible': 2952, 'release_infeasible_alert': 2952, 'submitted_touch': 4180, 'touch_considered': 4180, 'touch_guard_p_allowed': 22, 'touch_guard_p_consulted': 22, 'touch_issued': 4180, 'touch_issued_gpu': 4179, 'touch_issued_host': 1, 'touch_price_milli_sum': 12540}
   arm_stats {'cf3_resident_epochs': 11998, 'cf3_resident_members_sum': 107474, 'cf3_resident_excluded_sum': 39830, 'pd_kv_bound_by_belief': 474, 'pd_decisions': 474, 'pd_decisions_state': 345, 'pd_gate_no_active_alert_episode': 181, 'pd_u_max': 19009, 'pd_u_sum': 1626396, 'pd_free_kv_min': 0, 'pd_free_kv_max': 62944, 'pd_free_kv_sum': 9794060, 'pd_gate_rebuild_fits_without_evicting': 208, 'pd_decisions_request': 129, 'cf_planner_decisions': 80985, 'cf_planner_decisions_state': 80985, 'cf_budget_ms': 20.0, 'cf3_resident_rotations': 127, 'pd_victim_found': 446, 'cf_timeout_abandons': 1, 'cf_timeout_abandons_state': 1, 'cf3_considered': 56, 'cf3_gate_no_question_estimate': 5, 'pd_deferred_to_g
   residency-cold counters {'belief_to_cold': 62, 'state_priced_build_cold': 165} {'book0b_cold_pieces': 126}
tl run_valid True wall 1199.935698 budget 771.59 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 1
   counts {'completed_touch': 5435, 'recall_CLOUD': 401, 'recall_DEFER': 14, 'recall_REJECT': 61, 'release_infeasible': 2094, 'release_infeasible_alert': 2094, 'submitted_touch': 5435, 'touch_considered': 5435, 'touch_guard_p_allowed': 23, 'touch_guard_p_consulted': 23, 'touch_issued': 5435, 'touch_issued_gpu': 5433, 'touch_issued_host': 2, 'touch_price_milli_sum': 16305}
   arm_stats {'cf_planner_decisions': 106668, 'cf_planner_decisions_state': 106668, 'cf_budget_ms': 20.0}
   residency-cold counters {'belief_to_cold': 54, 'state_priced_build_cold': 136} {'book0b_cold_pieces': 109}
r3 run_valid True wall 1199.935691 budget 682.52 / 1200.0 lateness_p99 50.0 uplink_q_p99_med 0.0 epoch_overruns 0 max_lag 0.0 n_errors 0
   counts {'completed_touch': 3353, 'recall_CLOUD': 431, 'recall_DEFER': 6, 'recall_REJECT': 31, 'release_infeasible': 2342, 'release_infeasible_alert': 2342, 'submitted_touch': 3353, 'touch_considered': 4304, 'touch_issued': 3353, 'touch_issued_gpu': 3353, 'touch_price_milli_sum': 10059, 'touch_refused': 951, 'touch_refused_guard': 951}
   arm_stats {'cf_planner_decisions': 80385, 'cf_planner_decisions_state': 80385, 'cf_budget_ms': 20.0}
   residency-cold counters {'belief_to_cold': 62, 'state_priced_build_cold': 190} {}
== (B) TTFT t_first_token-t_submit quantiles per class
f1 {'robo': (4683, [0.61, 3.924, 9.797]), 'asst': (195, [0.426, 1.693, 5.69]), 'dash': (4429, [0.24, 0.618, 2.272])}
tl {'robo': (5935, [0.45, 2.305, 8.159]), 'asst': (221, [0.406, 1.037, 3.314]), 'dash': (5287, [0.241, 0.605, 1.553])}
r3 {'robo': (3888, [0.382, 1.81, 7.953]), 'asst': (240, [0.462, 3.471, 8.036]), 'dash': (4853, [0.24, 0.69, 4.203])}
== (C) release_infeasible by class and SS/dash outcomes
f1 [('none', 2952)]
  monitor within_L {('monitor', True): 4174, ('monitor', False): 3688}  n monitor opps 7862
tl [('none', 2094)]
  monitor within_L {('monitor', True): 5025, ('monitor', False): 2837}  n monitor opps 7862
r3 [('none', 2342)]
  monitor within_L {('monitor', True): 4489, ('monitor', False): 3373}  n monitor opps 7862
== (D) cf admissions: outcomes
Counter({'net_does_not_exceed_the_bar': 15, 'admit_forfeit_valued': 13, 'no_future_gain': 12, 'not_in_resident_set': 6, 'no_question_estimate': 5, 'next_question_beyond_horizon': 5}) 13
opp0001343 robo007 t=203.4 net 12.2 f1 state LATE_ENGINE cbd 0 | F0 state WRONG cbd 0 | next ask dt 21.1
opp0001472 robo011 t=221.3 net 1.6 f1 state LATE_ENGINE cbd 0 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 17.2
opp0001806 robo006 t=268.3 net 1.0 f1 state LATE_ENGINE cbd 0 | F0 state WRONG cbd 0 | next ask dt 31.8
opp0001850 robo002 t=275.2 net 35.3 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 2.2
opp0001873 robo011 t=278.6 net 3.5 f1 state LATE_ENGINE cbd 0 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 20.4
opp0003487 robo008 t=509.6 net 4.6 f1 state LATE_ENGINE cbd 1 | F0 state WRONG cbd 0 | next ask dt 49.5
opp0003846 robo002 t=560.8 net 1.7 f1 state LATE_ENGINE cbd 1 | F0 state REJECTED cbd 1 | next ask dt 20.6
opp0005308 robo003 t=769.1 net 3.3 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 28.2
opp0005494 robo007 t=796.4 net 2.3 f1 state LATE_ENGINE cbd 0 | F0 state LATE_ENGINE cbd 0 | next ask dt 52.0
opp0005521 robo005 t=799.6 net 4.8 f1 state LATE_ENGINE cbd 1 | F0 state ONTIME_CORRECT cbd 1 | next ask dt 35.2
opp0005959 robo005 t=862.1 net 3.7 f1 state LATE_ENGINE cbd 1 | F0 state LATE_ENGINE cbd 1 | next ask dt 29.0
opp0006108 robo005 t=883.0 net 8.2 f1 state LATE_ENGINE cbd 1 | F0 state WRONG cbd 0 | next ask dt 26.5
opp0006338 robo007 t=916.7 net 5.9 f1 state LATE_ENGINE cbd 0 | F0 state REJECTED cbd 0 | next ask dt 27.3
admit summary f1 states Counter({'LATE_ENGINE': 13}) F0 states same opps Counter({'WRONG': 4, 'REJECTED': 4, 'ONTIME_CORRECT': 3, 'LATE_ENGINE': 2}) cbd f1 6 cbd F0 6
KEEP_REJECT 43 cbd f1 16 F0 state Counter({'ONTIME_CORRECT': 13, 'WRONG': 12, 'REJECTED': 11, 'LATE_ENGINE': 7})
#### an2
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
touch decisions per robot session F0 vs F1 (total) 5435 4180
cbd differs F1 worse 13 {'cf KEEP_REJECT (considered, not admitted)': 6, 'cf ADMISSION (late-engine/late)': 2, 'cold ask, touches not fewer': 1, 'late, warm ask, not admitted: queue/congestion': 4}
cbd differs F1 better 12 {'F1 gained (F0 failed)': 7, 'cf KEEP_REJECT (considered, not admitted)': 2, 'late, warm ask, not admitted: queue/congestion': 1, 'cf ADMISSION (late-engine/late)': 2}
on-time differs F1 worse 44 {'cf KEEP_REJECT (considered, not admitted)': 25, 'cf ADMISSION (late-engine/late)': 7, 'late, warm ask, not admitted: queue/congestion': 9, 'cold ask, touches not fewer': 3}
on-time differs F1 better 33 {'F1 gained (F0 failed)': 33}
sessions: touches F0->F1
  robo011| 1301 551
  robo008| 1641 1117
  robo003| 571 100
  robo004| 343 0
  robo006| 485 166
  robo002| 1094 1095
f1 resid-eligible 179 mean cached frac 0.852 <.5 28
tl resid-eligible 180 mean cached frac 0.925 <.5 11
next ask after each admission: (admit, next, cached frac F1, F1 state, F0 state)
[('opp0001343', 'opp0001791', 0.0, 'LATE_ENGINE', 'REJECTED'), ('opp0001806', 'opp0001949', 0.99, 'WRONG', 'WRONG'), ('opp0005521', 'opp0005655', 0.47, 'LATE_ENGINE', 'ONTIME_CORRECT'), ('opp0001472', 'opp0001532', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0003487', 'opp0003538', 1.0, 'WRONG', 'WRONG'), ('opp0005959', 'opp0006108', 0.0, 'LATE_ENGINE', 'WRONG'), ('opp0005494', 'opp0005607', 0.99, 'ONTIME_CORRECT', 'REJECTED'), ('opp0001850', 'opp0002484', 1.0, 'ONTIME_CORRECT', 'ONTIME_CORRECT'), ('opp0005308', 'opp0005468', 1.0, 'WRONG', 'WRONG')]
next-ask F1 states Counter({'LATE_ENGINE': 3, 'WRONG': 3, 'ONTIME_CORRECT': 3}) F0 Counter({'WRONG': 4, 'REJECTED': 3, 'ONTIME_CORRECT': 2})
f1 SS on-time 174 / 240
  SS opps by decision {'sent': 195, 'declined': 45} SS decisions decline/defer 49
tl SS on-time 211 / 240
  SS opps by decision {'sent': 221, 'declined': 19} SS decisions decline/defer 26
#### an3
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
f1 robot n 222 final dec {'CLOUD': 166, 'REJECT': 56} est_la q [0.24, 0.41, 0.99, 2.84, 4.49] queued_ahead q [0, 410, 1816, 8207, 24240] slack q [2.88, 2.89, 2.92, 2.95, 2.97] uncached_u q [193, 369, 1113, 5961, 13803]
f1 SS n 240 final dec {'CLOUD': 195, 'REJECT': 45} est_la q [0.13, 0.29, 0.46, 1.44, 4.07] queued_ahead q [0, 380, 1794, 8255, 25411] slack q [1.89, 1.89, 1.91, 1.97, 1.97] uncached_u q [1, 220, 338, 1335, 1363]
tl robot n 222 final dec {'CLOUD': 180, 'REJECT': 42} est_la q [0.24, 0.42, 0.88, 2.44, 4.65] queued_ahead q [45, 395, 1520, 4299, 14669] slack q [2.88, 2.9, 2.93, 2.95, 2.97] uncached_u q [193, 385, 1181, 5965, 15955]
tl SS n 240 final dec {'CLOUD': 221, 'REJECT': 19} est_la q [0.14, 0.27, 0.4, 0.86, 1.82] queued_ahead q [0, 380, 1056, 4058, 10556] slack q [1.89, 1.91, 1.94, 1.96, 1.96] uncached_u q [224, 330, 352, 1337, 1363]
f1 uncached prefill tokens total 4357461 {'robo': 1897044, 'asst': 139055, 'dash': 2321362} n requests 9315
  robot requests by decision kind {'release_piece': 332, 'release_recall': 179, 'touch': 4180}
tl uncached prefill tokens total 4279549 {'robo': 1445889, 'asst': 177670, 'dash': 2655990} n requests 11445
  robot requests by decision kind {'release_piece': 321, 'release_recall': 180, 'touch': 5435}
#### an4
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
f1 robot uncached tokens by kind {'release_piece': 1036052, 'release_recall': 799218, 'touch': 61774} n {'release_piece': 330, 'release_recall': 179, 'touch': 4174}
  dash release_monitor n None uncached dash 2321362
tl robot uncached tokens by kind {'release_piece': 893315, 'release_recall': 520364, 'touch': 32210} n {'release_piece': 321, 'release_recall': 180, 'touch': 5434}
  dash release_monitor n None uncached dash 2655990
22 admissions: uncached tokens 263008 ttft [4.4, 5.0, 5.9, 6.2, 6.2, 6.4, 7.0, 7.0, 7.1, 7.9, 8.3, 10.3, 10.6]
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
KEYS f1=F1 tl=F0 r3=rung3;: tl=CAND-TL, c=CAND (rung3+P+0b+B+qp), la=PWIRE, l0=-la-er (cell e), r3=rung 3, l1=earlier -la
== POOLED F1 minus F0 seeds [4, 5]
cbd                -23 CI[-45,-3] clusters=87 excl0
cloud on-time      -41 CI[-78,+7] clusters=87 incl0
cloud-correct      -30 CI[-55,-7] clusters=87 excl0
SS cloud on-time   -81 CI[-103,-60] clusters=477 excl0
dashcam            -2259 CI[-3275,-1325] clusters=40 excl0
FAIR rel 0.5922 vs 0.6896 diff -0.0974 CI[-0.1607,-0.0275] | abs gain diff -18.74 CI[-31.08,-5.54] (oracle 192.34 vs 192.34)
== POOLED F1 minus F0 s4 only seeds [4]
cbd                -22 CI[-41,-7] clusters=47 excl0
cloud on-time      -30 CI[-54,-9] clusters=47 excl0
cloud-correct      -23 CI[-43,-7] clusters=47 excl0
SS cloud on-time   -44 CI[-59,-29] clusters=237 excl0
dashcam            -1408 CI[-2264,-616] clusters=20 excl0
FAIR rel 0.5536 vs 0.6728 diff -0.1192 CI[-0.1862,-0.0551] | abs gain diff -12.58 CI[-20.20,-5.61] (oracle 105.55 vs 105.55)
== POOLED F1 minus F0 s5 only seeds [5]
cbd                -1 CI[-11,+9] clusters=40 incl0
cloud on-time      -11 CI[-40,+29] clusters=40 incl0
cloud-correct      -7 CI[-21,+8] clusters=40 incl0
SS cloud on-time   -37 CI[-53,-22] clusters=240 excl0
dashcam            -851 CI[-1377,-372] clusters=20 excl0
FAIR rel 0.6392 vs 0.7101 diff -0.0709 CI[-0.1778,+0.0590] | abs gain diff -6.16 CI[-14.87,+4.88] (oracle 86.79 vs 86.79)
== POOLED F0 minus rung3 seeds [4, 5]
cbd                +26 CI[+4,+49] clusters=87 excl0
cloud on-time      +60 CI[+14,+97] clusters=87 excl0
cloud-correct      +36 CI[+12,+60] clusters=87 excl0
SS cloud on-time   +60 CI[+38,+81] clusters=477 excl0
dashcam            +2131 CI[+1183,+3068] clusters=40 excl0
FAIR rel 0.6896 vs 0.5695 diff +0.1201 CI[+0.0491,+0.1784] | abs gain diff +23.10 CI[+9.26,+35.67] (oracle 192.34 vs 192.34)
== POOLED F0 minus rung3 s4 only seeds [4]
cbd                +23 CI[+3,+42] clusters=47 excl0
cloud on-time      +57 CI[+35,+80] clusters=47 excl0
cloud-correct      +32 CI[+15,+51] clusters=47 excl0
SS cloud on-time   +36 CI[+21,+51] clusters=237 excl0
dashcam            +1595 CI[+948,+2296] clusters=20 excl0
FAIR rel 0.6728 vs 0.4796 diff +0.1932 CI[+0.1317,+0.2500] | abs gain diff +20.39 CI[+12.09,+28.98] (oracle 105.55 vs 105.55)
== POOLED F0 minus rung3 s5 only seeds [5]
cbd                +3 CI[-7,+12] clusters=40 incl0
cloud on-time      +3 CI[-35,+30] clusters=40 incl0
cloud-correct      +4 CI[-10,+16] clusters=40 incl0
SS cloud on-time   +24 CI[+10,+38] clusters=240 excl0
dashcam            +536 CI[-112,+1100] clusters=20 incl0
FAIR rel 0.7101 vs 0.6789 diff +0.0312 CI[-0.0903,+0.1291] | abs gain diff +2.71 CI[-7.91,+10.63] (oracle 86.79 vs 86.79)
