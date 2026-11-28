POOLED 1x seeds [5] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            +1 CI[+0,+3] incl0
  cloud on-time                  +0 CI[+0,+0] incl0
  cloud-correct                  +1 CI[+0,+3] incl0
  device-route                   +0 CI[+0,+0] incl0
  dashcam within_L (60s blocks)  +104 CI[-121,+347] incl0 (20 blocks)
  SS cloud on-time               -1 CI[-6,+4] incl0
  FAIR F0 0.9671 rung3 0.9683 RELATIVE diff -0.0011 CI[-0.0073,+0.0047] | ABSOLUTE -0.07 CI[-0.44,+0.30]
1X s5: NO-HARM point cbd +1 (rule >= -2: True), on-time +0 / CI cbd [+0,+3] on-time [+0,+0]: PASS
#### 1x seed 5  F0=covex-v6-fair-final-cand-tl_n16_s5_1200s_h27_3t_L3_epg_rq30_qp
     r3=covex-v6-fair-final_n16_s5_1200s_h27_3t_L3_epg_rq30
== (0) headline
F0 robot cloud on-time 121 / 127 acc_on_served 0.429752 SS 352 / 356 dash within_L 8415 worst (0.673, 'dash001') | decisions {'release_piece': 146, 'release_recall': 478, 'release_monitor': 8955, 'release_infeasible': 1886, 'defer': 8, 'decline': 5, 'state_action': 174, 'touch': 174}
r3 robot cloud on-time 121 / 127 acc_on_served 0.421488 SS 353 / 356 dash within_L 8311 worst (0.684, 'dash004') | decisions {'release_piece': 143, 'release_recall': 480, 'release_monitor': 8799, 'release_infeasible': 2046, 'decline': 3, 'state_action': 176, 'touch': 176}
== (1) POSITIVE CONTROL: classifier cbd vs committed cbd per opportunity
F0 committed cbd 57 classifier cbd 57 per-opp agree 127 / 127 | cloud-correct 52 device-correct 5 device-route n 6
r3 committed cbd 56 classifier cbd 56 per-opp agree 127 / 127 | cloud-correct 51 device-correct 5 device-route n 6
POSITIVE CONTROL PASS
== (2) paired F0 minus rung3, question-clustered, seed 7, 2000 reps
  cbd                            +1 CI[+0,+3] incl0
  cloud on-time                  +0 CI[+0,+0] incl0
  cloud-correct                  +1 CI[+0,+3] incl0
  device-route                   +0 CI[+0,+0] incl0
  dashcam within_L (60s blocks)  +104 CI[-125,+356] incl0 (20 blocks)
  SS cloud on-time               -1 CI[-6,+4] incl0
== (3) FAIR (frozen table)
FAIR CONSTANTS F0: A_RC_H=0.568799 A_RC_N=0.212222 CR=0.257732 A_SC=0.621881 A_SD=0.547985
  source results/orchestration/live2/oracle/oracle_fair_table.json @origin/main blob 947ad92a102581a9fcf0e30f7ac936832a15f511 sha256 f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562 (D268 corrected conditioned FAIR table, commit d6b24cb9; FROZEN)
  robot_rows=127 ss_rows(all assistive rows)=356 oracle_total=127*(A_RC_H-CR)+356*(A_SC-A_SD)=65.81
FAIR CONSTANTS r3: A_RC_H=0.568799 A_RC_N=0.212222 CR=0.257732 A_SC=0.621881 A_SD=0.547985
  source results/orchestration/live2/oracle/oracle_fair_table.json @origin/main blob 947ad92a102581a9fcf0e30f7ac936832a15f511 sha256 f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562 (D268 corrected conditioned FAIR table, commit d6b24cb9; FROZEN)
  robot_rows=127 ss_rows(all assistive rows)=356 oracle_total=127*(A_RC_H-CR)+356*(A_SC-A_SD)=65.81
F0 combined rel 0.9671 (abs gain 63.65 of oracle 65.81)
r3 combined rel 0.9683 (abs gain 63.72 of oracle 65.81)
FAIR F0 0.9671 rung3 0.9683 RELATIVE diff -0.0011 CI[-0.0073,+0.0047] | ABSOLUTE gain diff -0.07 CI[-0.44,+0.30]
== (4) touches / guard / latch
F0 {'belief_to_cold': 1, 'belief_to_gpu': 11, 'completed_touch': 170, 'state_priced_build_cold': 30, 'submitted_touch': 174, 'touch_considered': 174, 'touch_issued': 174, 'touch_issued_gpu': 174, 'touch_price_milli_sum': 522, 'state_deferred_to_guard_epochs': 4, 'state_touch_emitted': 174, 'guard_active_epochs': 4, 'guard_by_lag': 4, 'guard_by_backlog': 0, 'guard_shed_warming_epochs': 4}
   chosen(touch_considered)=174 issued=174 refused(considered-issued)=0 | guard consulted=None allowed=None
   robot sessions 21 per-session touch REQUESTS min/med/max 0 0 174 zero-touch sessions 20 | total touch requests 174 | per-session list [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 174]
   LATCH (touches stop >120s before session last request): 0 of 21 sessions
r3 {'belief_to_cold': 2, 'belief_to_gpu': 11, 'completed_touch': 172, 'state_priced_build_cold': 31, 'submitted_touch': 176, 'touch_considered': 176, 'touch_issued': 176, 'touch_issued_gpu': 176, 'touch_price_milli_sum': 528, 'state_deferred_to_guard_epochs': 34, 'state_touch_emitted': 176, 'guard_active_epochs': 34, 'guard_by_lag': 34, 'guard_by_backlog': 0, 'guard_shed_warming_epochs': 34}
   chosen(touch_considered)=176 issued=176 refused(considered-issued)=0 | guard consulted=None allowed=None
   robot sessions 21 per-session touch REQUESTS min/med/max 0 0 172 zero-touch sessions 20 | total touch requests 172 | per-session list [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 172]
   LATCH (touches stop >120s before session last request): 0 of 21 sessions
== (5) residency cold
F0 asks reached engine 122 resid-eligible 122 cold<.5 0 <.25 0 | declined recall opps 4
r3 asks reached engine 123 resid-eligible 123 cold<.5 0 <.25 0 | declined recall opps 3
== (6) loss decomposition F0 vs rung3 (states per recall opp)
states {'F0': {'WRONG': 69, 'ONTIME_CORRECT': 52, 'LATE_ENGINE': 2, 'REJECTED': 4}, 'r3': {'WRONG': 70, 'ONTIME_CORRECT': 51, 'LATE_ENGINE': 2, 'REJECTED': 3, 'NOT_SENT_OTHER': 1}}
 on-time LOST by F0 0 F0 failing state {} | of lost, rung3 answer WRONG 0
 on-time GAINED by F0 0 rung3 failing state {} | F0 answer WRONG 0 correct 0
 cbd-differing opps by owner and states
   ('F0+1', 'r3:WRONG', 'F0:ONTIME_CORRECT') 1
== (7) robo003 asks (recall opps of robo003 whose F0/rung3 state or cbd differ; all robo003 count)
robo003 recall opps 19 differing 0
POOLED 1x seeds [4, 5] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            +2 CI[-2,+6] incl0
  cloud on-time                  -2 CI[-6,+2] incl0
  cloud-correct                  +1 CI[-3,+5] incl0
  device-route                   +2 CI[-2,+6] incl0
  dashcam within_L (60s blocks)  +347 CI[-30,+728] incl0 (40 blocks)
  SS cloud on-time               +1 CI[-6,+9] incl0
  FAIR F0 0.9629 rung3 0.9670 RELATIVE diff -0.0041 CI[-0.0146,+0.0059] | ABSOLUTE -0.55 CI[-1.94,+0.75]
1X s4+s5: NO-HARM point cbd +2 (rule >= -2: True), on-time -2 / CI cbd [-2,+6] on-time [-6,+2]: PASS
#### half seed 5  F0=covex-v6-fair-final-cand-tl_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30_qp
     r3=covex-v6-fair-final_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30_preD249
== (0) headline
F0 robot cloud on-time 83 / 127 acc_on_served 0.385542 SS 320 / 356 dash within_L 6469 worst (0.504, 'dash004') | decisions {'release_piece': 145, 'release_recall': 420, 'release_monitor': 7010, 'release_infeasible': 3183, 'decline': 63, 'defer': 10}
r3 robot cloud on-time 65 / 127 acc_on_served 0.461538 SS 292 / 356 dash within_L 5535 worst (0.397, 'dash001') | decisions {'release_piece': 163, 'release_recall': 452, 'release_monitor': 6202, 'release_infeasible': 3157, 'decline': 31, 'defer': 4, 'state_action': 612, 'touch': 612}
== (1) POSITIVE CONTROL: classifier cbd vs committed cbd per opportunity
F0 committed cbd 47 classifier cbd 47 per-opp agree 127 / 127 | cloud-correct 32 device-correct 15 device-route n 44
r3 committed cbd 52 classifier cbd 52 per-opp agree 127 / 127 | cloud-correct 30 device-correct 22 device-route n 62
POSITIVE CONTROL PASS
== (2) paired F0 minus rung3, question-clustered, seed 7, 2000 reps
  cbd                            -5 CI[-17,+6] incl0
  cloud on-time                  +18 CI[+3,+34] excl0 POS
  cloud-correct                  +2 CI[-8,+12] incl0
  device-route                   -18 CI[-34,-3] excl0 NEG
  dashcam within_L (60s blocks)  +934 CI[+421,+1487] excl0 POS (20 blocks)
  SS cloud on-time               +28 CI[+13,+43] excl0 POS
== (3) FAIR (frozen table)
FAIR CONSTANTS F0: A_RC_H=0.568799 A_RC_N=0.212222 CR=0.257732 A_SC=0.621881 A_SD=0.547985
  source results/orchestration/live2/oracle/oracle_fair_table.json @origin/main blob 947ad92a102581a9fcf0e30f7ac936832a15f511 sha256 f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562 (D268 corrected conditioned FAIR table, commit d6b24cb9; FROZEN)
  robot_rows=127 ss_rows(all assistive rows)=356 oracle_total=127*(A_RC_H-CR)+356*(A_SC-A_SD)=65.81
FAIR CONSTANTS r3: A_RC_H=0.568799 A_RC_N=0.212222 CR=0.257732 A_SC=0.621881 A_SD=0.547985
  source results/orchestration/live2/oracle/oracle_fair_table.json @origin/main blob 947ad92a102581a9fcf0e30f7ac936832a15f511 sha256 f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562 (D268 corrected conditioned FAIR table, commit d6b24cb9; FROZEN)
  robot_rows=127 ss_rows(all assistive rows)=356 oracle_total=127*(A_RC_H-CR)+356*(A_SC-A_SD)=65.81
F0 combined rel 0.7516 (abs gain 49.47 of oracle 65.81)
r3 combined rel 0.6351 (abs gain 41.80 of oracle 65.81)
FAIR F0 0.7516 rung3 0.6351 RELATIVE diff +0.1165 CI[+0.0437,+0.1828] | ABSOLUTE gain diff +7.67 CI[+2.63,+13.14]
== (4) touches / guard / latch
F0 {'belief_to_cold': 31, 'belief_to_gpu': 39, 'state_priced_build_cold': 58, 'state_deferred_to_guard_epochs': 334, 'guard_active_epochs': 334, 'guard_by_lag': 334, 'guard_by_backlog': 0, 'guard_shed_warming_epochs': 334}
   chosen(touch_considered)=None issued=None refused(considered-issued)=0 | guard consulted=None allowed=None
   robot sessions 21 per-session touch REQUESTS min/med/max 0 0 0 zero-touch sessions 21 | total touch requests 0 | per-session list [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
   LATCH (touches stop >120s before session last request): 0 of 21 sessions
r3 {'belief_to_cold': 38, 'belief_to_gpu': 43, 'completed_touch': 612, 'state_priced_build_cold': 82, 'submitted_touch': 612, 'touch_considered': 612, 'touch_issued': 612, 'touch_issued_gpu': 612, 'touch_price_milli_sum': 1836, 'state_deferred_to_guard_epochs': 2387, 'state_touch_emitted': 612, 'guard_active_epochs': 2387, 'guard_by_lag': 2387, 'guard_by_backlog': 0, 'guard_shed_warming_epochs': 2387}
   chosen(touch_considered)=612 issued=612 refused(considered-issued)=0 | guard consulted=None allowed=None
   robot sessions 21 per-session touch REQUESTS min/med/max 0 0 612 zero-touch sessions 20 | total touch requests 612 | per-session list [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 612]
   LATCH (touches stop >120s before session last request): 0 of 21 sessions
== (5) residency cold
F0 asks reached engine 91 resid-eligible 91 cold<.5 7 <.25 6 | declined recall opps 35
r3 asks reached engine 95 resid-eligible 95 cold<.5 20 <.25 16 | declined recall opps 31
== (6) loss decomposition F0 vs rung3 (states per recall opp)
states {'F0': {'WRONG': 51, 'ONTIME_CORRECT': 32, 'REJECTED': 35, 'LATE_ENGINE': 9}, 'r3': {'WRONG': 35, 'ONTIME_CORRECT': 30, 'LATE_ENGINE': 31, 'REJECTED': 31}}
 on-time LOST by F0 16 F0 failing state {'LATE_ENGINE': 2, 'REJECTED': 14} | of lost, rung3 answer WRONG 8
 on-time GAINED by F0 34 rung3 failing state {'LATE_ENGINE': 18, 'REJECTED': 16} | F0 answer WRONG 23 correct 11
 cbd-differing opps by owner and states
   ('F0+1', 'r3:LATE_ENGINE', 'F0:ONTIME_CORRECT') 2
   ('F0+1', 'r3:REJECTED', 'F0:ONTIME_CORRECT') 3
   ('F0+1', 'r3:WRONG', 'F0:REJECTED') 1
   ('r3+1', 'r3:LATE_ENGINE', 'F0:WRONG') 5
   ('r3+1', 'r3:ONTIME_CORRECT', 'F0:LATE_ENGINE') 1
   ('r3+1', 'r3:ONTIME_CORRECT', 'F0:REJECTED') 2
   ('r3+1', 'r3:ONTIME_CORRECT', 'F0:WRONG') 1
   ('r3+1', 'r3:REJECTED', 'F0:WRONG') 2
== (7) robo003 asks (recall opps of robo003 whose F0/rung3 state or cbd differ; all robo003 count)
robo003 recall opps 19 differing 6
   opp0004443 F0 REJECTED cbd 0 | r3 ONTIME_CORRECT cbd 1
   opp0004919 F0 REJECTED cbd 1 | r3 LATE_ENGINE cbd 1
   opp0004998 F0 LATE_ENGINE cbd 0 | r3 REJECTED cbd 0
   opp0005475 F0 ONTIME_CORRECT cbd 1 | r3 REJECTED cbd 1
   opp0005653 F0 ONTIME_CORRECT cbd 1 | r3 REJECTED cbd 1
   opp0005697 F0 WRONG cbd 0 | r3 REJECTED cbd 0
POOLED half seeds [5] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            -5 CI[-18,+7] incl0
  cloud on-time                  +18 CI[+3,+34] excl0 POS
  cloud-correct                  +2 CI[-8,+12] incl0
  device-route                   -18 CI[-34,-3] excl0 NEG
  dashcam within_L (60s blocks)  +934 CI[+414,+1440] excl0 POS (20 blocks)
  SS cloud on-time               +28 CI[+14,+43] excl0 POS
  FAIR F0 0.7516 rung3 0.6351 RELATIVE diff +0.1165 CI[+0.0437,+0.1828] | ABSOLUTE +7.67 CI[+2.63,+13.14]
HALVED s5: cbd no-harm PASS (point -5 CI[-18,+7]); FAIR gain (CI above 0) PASS (+0.1165 CI[+0.0437,+0.1828])
POOLED half seeds [4, 5] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            -8 CI[-27,+10] incl0
  cloud on-time                  +31 CI[+6,+57] excl0 POS
  cloud-correct                  +10 CI[-7,+29] incl0
  device-route                   -31 CI[-57,-6] excl0 NEG
  dashcam within_L (60s blocks)  +864 CI[-73,+1749] incl0 (40 blocks)
  SS cloud on-time               +22 CI[+0,+43] incl0
  FAIR F0 0.7388 rung3 0.6542 RELATIVE diff +0.0846 CI[+0.0258,+0.1428] | ABSOLUTE +11.27 CI[+3.17,+20.35]
HALVED s4+s5: cbd no-harm PASS (point -8 CI[-27,+10]); FAIR gain (CI above 0) PASS (+0.0846 CI[+0.0258,+0.1428])
touch-latch note: halved s5 F0 issued 0 touches (no touch_considered key) ; see summary
