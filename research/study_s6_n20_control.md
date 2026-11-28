STATUS Fri Nov 27 10:30:12 PM PST 2026: n20 s6 landed (19:56). MISSING at poll end (>150 min): n16 s6 1x, n16 s6 halved, n16 s7 halved, n16 s7 1x cand-tl cells (not on origin; origin shows the cluster running other cand-tl-sync n20 s6 cells instead).
#### n20 seed 6  F0=covex-v6-fair-final-cand-tl_n20_s6_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp
     r3=covex-v6-fair-final_n20_s6_1200s_h27_3t_c3-11-2_L3_epg_rq30
== (0) headline
F0 robot cloud on-time 162 / 250 acc_on_served 0.518519 SS 189 / 238 dash within_L 4766 worst (0.588, 'dash001') | decisions {'release_piece': 326, 'release_recall': 379, 'release_monitor': 4994, 'release_infeasible': 2533, 'defer': 19, 'decline': 109, 'state_action': 1689, 'touch': 1689}
r3 robot cloud on-time 128 / 250 acc_on_served 0.546875 SS 180 / 238 dash within_L 4003 worst (0.483, 'dash003') | decisions {'release_piece': 342, 'release_recall': 437, 'release_monitor': 4261, 'release_infeasible': 2908, 'decline': 51, 'defer': 9, 'state_action': 1260, 'touch': 1078}
== (1) POSITIVE CONTROL: classifier cbd vs committed cbd per opportunity
F0 committed cbd 104 classifier cbd 104 per-opp agree 250 / 250 | cloud-correct 84 device-correct 20 device-route n 88
r3 committed cbd 99 classifier cbd 99 per-opp agree 250 / 250 | cloud-correct 70 device-correct 29 device-route n 122
POSITIVE CONTROL PASS
== (2) paired F0 minus rung3, question-clustered, seed 7, 2000 reps
  cbd                            +5 CI[-8,+18] incl0 unrounded[-8.000,18.000] draws<0/=0/>0 (446, 87, 1467)
  cloud on-time                  +34 CI[+16,+52] excl0 POS unrounded[16.000,52.000] draws<0/=0/>0 (0, 0, 2000)
  cloud-correct                  +14 CI[+2,+26] excl0 POS unrounded[2.000,26.000] draws<0/=0/>0 (11, 11, 1978)
  device-route                   -34 CI[-52,-16] excl0 NEG unrounded[-52.000,-16.000] draws<0/=0/>0 (2000, 0, 0)
  dashcam within_L (60s blocks)  +764 CI[+429,+1177] excl0 POS (20 blocks) unrounded[429.000,1177.000] draws<0/=0/>0 (0, 0, 2000)
  SS cloud on-time               +9 CI[-5,+25] incl0 unrounded[-5.000,25.000] draws<0/=0/>0 (199, 58, 1743)
== (3) FAIR (frozen table)
FAIR CONSTANTS F0: A_RC_H=0.568799 A_RC_N=0.212222 CR=0.257732 A_SC=0.621881 A_SD=0.547985
  source results/orchestration/live2/oracle/oracle_fair_table.json @origin/main blob 947ad92a102581a9fcf0e30f7ac936832a15f511 sha256 f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562 (D268 corrected conditioned FAIR table, commit d6b24cb9; FROZEN)
  robot_rows=250 ss_rows(all assistive rows)=238 oracle_total=250*(A_RC_H-CR)+238*(A_SC-A_SD)=95.35
FAIR CONSTANTS r3: A_RC_H=0.568799 A_RC_N=0.212222 CR=0.257732 A_SC=0.621881 A_SD=0.547985
  source results/orchestration/live2/oracle/oracle_fair_table.json @origin/main blob 947ad92a102581a9fcf0e30f7ac936832a15f511 sha256 f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562 (D268 corrected conditioned FAIR table, commit d6b24cb9; FROZEN)
  robot_rows=250 ss_rows(all assistive rows)=238 oracle_total=250*(A_RC_H-CR)+238*(A_SC-A_SD)=95.35
F0 combined rel 0.6750 (abs gain 64.36 of oracle 95.35)
r3 combined rel 0.5571 (abs gain 53.12 of oracle 95.35)
FAIR F0 0.6750 rung3 0.5571 RELATIVE diff +0.1179 CI[+0.0601,+0.1835] unrounded[0.060129,0.183473] draws<0/=0/>0 (0, 0, 2000) | ABSOLUTE gain diff +11.24 CI[+5.60,+17.91]
== (4) touches / guard / latch
F0 {'belief_to_cold': 60, 'belief_to_gpu': 80, 'completed_touch': 1685, 'state_priced_build_cold': 138, 'submitted_touch': 1689, 'touch_considered': 1689, 'touch_guard_p_allowed': 3, 'touch_guard_p_consulted': 3, 'touch_issued': 1689, 'touch_issued_gpu': 1689, 'touch_price_milli_sum': 5067, 'state_deferred_to_guard_epochs': 2351, 'state_touch_emitted': 1689, 'guard_active_epochs': 2351, 'guard_by_lag': 2351, 'guard_by_backlog': 0, 'guard_shed_warming_epochs': 2351}
   chosen(touch_considered)=1689 issued=1689 refused(considered-issued)=0 | guard consulted=3 allowed=3
   robot sessions 44 per-session touch REQUESTS min/med/max 0 0.0 600 zero-touch sessions 38 | total touch requests 1689 | per-session list [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 9, 54, 219, 268, 539, 600]
   LATCH (touches stop >120s before session last request): 0 of 44 sessions
r3 {'belief_to_cold': 67, 'belief_to_gpu': 88, 'completed_touch': 1078, 'state_priced_build_cold': 186, 'submitted_touch': 1078, 'touch_considered': 1260, 'touch_issued': 1078, 'touch_issued_gpu': 1078, 'touch_price_milli_sum': 3234, 'touch_refused': 182, 'touch_refused_guard': 182, 'state_deferred_to_guard_epochs': 5039, 'state_touch_emitted': 1260, 'guard_active_epochs': 5039, 'guard_by_lag': 5039, 'guard_by_backlog': 0, 'guard_shed_warming_epochs': 5039}
   chosen(touch_considered)=1260 issued=1078 refused(considered-issued)=182 | guard consulted=None allowed=None
   robot sessions 44 per-session touch REQUESTS min/med/max 0 0.0 495 zero-touch sessions 40 | total touch requests 1078 | per-session list [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 128, 156, 299, 495]
   LATCH (touches stop >120s before session last request): 0 of 44 sessions
== (5) residency cold
F0 asks reached engine 185 resid-eligible 185 cold<.5 13 <.25 9 | declined recall opps 65
r3 asks reached engine 199 resid-eligible 199 cold<.5 31 <.25 29 | declined recall opps 51
== (6) loss decomposition F0 vs rung3 (states per recall opp)
states {'F0': {'ONTIME_CORRECT': 84, 'WRONG': 78, 'LATE_ENGINE': 23, 'REJECTED': 65}, 'r3': {'ONTIME_CORRECT': 70, 'WRONG': 58, 'LATE_ENGINE': 71, 'REJECTED': 51}}
 on-time LOST by F0 22 F0 failing state {'REJECTED': 18, 'LATE_ENGINE': 4} | of lost, rung3 answer WRONG 12
 on-time GAINED by F0 56 rung3 failing state {'LATE_ENGINE': 33, 'REJECTED': 23} | F0 answer WRONG 33 correct 23
 cbd-differing opps by owner and states
   ('F0+1', 'r3:LATE_ENGINE', 'F0:ONTIME_CORRECT') 16
   ('F0+1', 'r3:REJECTED', 'F0:ONTIME_CORRECT') 5
   ('F0+1', 'r3:WRONG', 'F0:ONTIME_CORRECT') 1
   ('F0+1', 'r3:WRONG', 'F0:REJECTED') 1
   ('r3+1', 'r3:LATE_ENGINE', 'F0:WRONG') 5
   ('r3+1', 'r3:ONTIME_CORRECT', 'F0:LATE_ENGINE') 3
   ('r3+1', 'r3:ONTIME_CORRECT', 'F0:REJECTED') 7
   ('r3+1', 'r3:REJECTED', 'F0:WRONG') 3
== (7) robo003 asks (recall opps of robo003 whose F0/rung3 state or cbd differ; all robo003 count)
robo003 recall opps 13 differing 4
   opp0007948 F0 WRONG cbd 0 | r3 REJECTED cbd 0
   opp0008035 F0 WRONG cbd 0 | r3 REJECTED cbd 0
   opp0008120 F0 WRONG cbd 0 | r3 REJECTED cbd 0
   opp0008196 F0 WRONG cbd 0 | r3 REJECTED cbd 0

POOLED n20 seeds [4, 5, 6] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            +31 CI[+6,+57] excl0 POS unrounded[6.000,57.000] draws<0/=0/>0 (13, 2, 1985)
  cloud on-time                  +94 CI[+51,+135] excl0 POS unrounded[51.000,135.000] draws<0/=0/>0 (0, 0, 2000)
  cloud-correct                  +50 CI[+25,+77] excl0 POS unrounded[25.000,77.000] draws<0/=0/>0 (0, 0, 2000)
  device-route                   -94 CI[-135,-51] excl0 NEG unrounded[-135.000,-51.000] draws<0/=0/>0 (2000, 0, 0)
  dashcam within_L (60s blocks)  +2895 CI[+1825,+3879] excl0 POS (60 blocks) unrounded[1825.000,3879.000] draws<0/=0/>0 (0, 0, 2000)
  SS cloud on-time               +69 CI[+43,+95] excl0 POS unrounded[43.000,95.000] draws<0/=0/>0 (0, 0, 2000)
  FAIR F0 0.6848 rung3 0.5654 RELATIVE diff +0.1194 CI[+0.0669,+0.1658] unrounded[0.066933,0.165781] draws<0/=0/>0 (0, 0, 2000) | ABSOLUTE +34.34 CI[+18.70,+48.63]
N20 s4+s5+s6 control: cbd +31 CI[+6.000,+57.000] draws (13, 2, 1985); on-time +94 CI[+51.000,+135.000]; FAIR rel +0.1194 CI[+0.066933,+0.165781] draws (0, 0, 2000)

--- pooled 1x/half s4+s5 (prior, unchanged; s6/s7 missing) ---
POOLED 1x seeds [4, 5] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            +2 CI[-2,+6] incl0 unrounded[-2.000,6.000] draws<0/=0/>0 (193, 263, 1544)
  cloud on-time                  -2 CI[-6,+2] incl0 unrounded[-6.000,2.000] draws<0/=0/>0 (1560, 259, 181)
  cloud-correct                  +1 CI[-3,+5] incl0 unrounded[-3.000,5.000] draws<0/=0/>0 (506, 326, 1168)
  device-route                   +2 CI[-2,+6] incl0 unrounded[-2.000,6.000] draws<0/=0/>0 (181, 259, 1560)
  dashcam within_L (60s blocks)  +347 CI[-24,+729] incl0 (40 blocks) unrounded[-24.000,729.000] draws<0/=0/>0 (65, 1, 1934)
  SS cloud on-time               +1 CI[-7,+9] incl0 unrounded[-7.000,9.000] draws<0/=0/>0 (718, 202, 1080)
  FAIR F0 0.9629 rung3 0.9670 RELATIVE diff -0.0041 CI[-0.0146,+0.0059] unrounded[-0.014593,0.005884] draws<0/=0/>0 (1568, 29, 403) | ABSOLUTE -0.55 CI[-1.94,+0.75]
1X s4+s5: NO-HARM point cbd +2 (rule >= -2: True), on-time -2 / CI cbd [-2,+6] on-time [-6,+2]: PASS
POOLED half seeds [4, 5] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            -8 CI[-28,+10] incl0 unrounded[-28.000,10.000] draws<0/=0/>0 (1590, 67, 343)
  cloud on-time                  +31 CI[+7,+57] excl0 POS unrounded[7.000,57.000] draws<0/=0/>0 (10, 2, 1988)
  cloud-correct                  +10 CI[-7,+29] incl0 unrounded[-7.000,29.000] draws<0/=0/>0 (264, 53, 1683)
  device-route                   -31 CI[-57,-7] excl0 NEG unrounded[-57.000,-7.000] draws<0/=0/>0 (1988, 2, 10)
  dashcam within_L (60s blocks)  +864 CI[-83,+1779] incl0 (40 blocks) unrounded[-83.000,1779.000] draws<0/=0/>0 (71, 0, 1929)
  SS cloud on-time               +22 CI[-1,+44] incl0 unrounded[-1.000,44.000] draws<0/=0/>0 (68, 10, 1922)
  FAIR F0 0.7388 rung3 0.6542 RELATIVE diff +0.0846 CI[+0.0258,+0.1428] unrounded[0.025802,0.142763] draws<0/=0/>0 (3, 0, 1997) | ABSOLUTE +11.27 CI[+3.17,+20.35]
HALVED s4+s5: cbd no-harm PASS (point -8 CI[-28,+10]); FAIR gain (CI above 0) PASS (+0.0846 CI[+0.0258,+0.1428])
