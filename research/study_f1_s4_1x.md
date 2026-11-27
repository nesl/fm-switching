F1 1x s4 scoring; see score_out.txt b_out.txt asks_out.txt; summary in report
== (0) headline per cell; decision kinds
f1 robot cloud on-time 125 / 132 acc_on_served 0.656 n_dev_standing 7 SS 350 / 357 dash within_L 8334 worst (0.684, 'dash004') | decisions {'release_piece': 145, 'release_monitor': 8809, 'release_recall': 484, 'release_infeasible': 2084, 'defer': 1, 'decline': 5, 'state_action': 2676, 'touch': 2676}
tl robot cloud on-time 124 / 132 acc_on_served 0.66129 n_dev_standing 8 SS 353 / 357 dash within_L 8621 worst (0.699, 'dash003') | decisions {'release_piece': 146, 'release_monitor': 9114, 'release_recall': 484, 'release_infeasible': 1778, 'decline': 5, 'defer': 1, 'state_action': 2671, 'touch': 2671}
cd robot cloud on-time 123 / 132 acc_on_served 0.650407 n_dev_standing 9 SS 349 / 357 dash within_L 8519 worst (0.668, 'dash001') | decisions {'release_piece': 143, 'release_monitor': 9054, 'release_recall': 480, 'release_infeasible': 1852, 'defer': 6, 'decline': 9, 'state_action': 2676, 'touch': 2676}
pw robot cloud on-time 122 / 132 acc_on_served 0.655738 n_dev_standing 10 SS 351 / 357 dash within_L 8363 worst (0.686, 'dash001') | decisions {'release_piece': 142, 'release_monitor': 8895, 'release_recall': 484, 'release_infeasible': 1971, 'defer': 3, 'decline': 5, 'state_action': 2670, 'touch': 2670}
la robot cloud on-time 120 / 132 acc_on_served 0.641667 n_dev_standing 12 SS 351 / 357 dash within_L 8493 worst (0.687, 'dash001') | decisions {'release_piece': 146, 'release_monitor': 9002, 'release_recall': 480, 'release_infeasible': 1926, 'decline': 9, 'defer': 5, 'state_action': 2666, 'touch': 2666}
e robot cloud on-time 126 / 132 acc_on_served 0.65873 n_dev_standing 6 SS 351 / 357 dash within_L 8281 worst (0.663, 'dash004') | decisions {'release_piece': 145, 'release_monitor': 8810, 'release_recall': 489, 'release_infeasible': 2049, 'state_action': 2675, 'touch': 2675}
r3 robot cloud on-time 126 / 132 acc_on_served 0.650794 n_dev_standing 6 SS 351 / 357 dash within_L 8377 worst (0.68, 'dash002') | decisions {'release_piece': 145, 'release_monitor': 8885, 'release_recall': 489, 'release_infeasible': 2028, 'state_action': 2674, 'touch': 2674}
rp robot cloud on-time 127 / 132 acc_on_served 0.661417 n_dev_standing 5 SS 351 / 357 dash within_L 8323 worst (0.656, 'dash001') | decisions {'release_piece': 144, 'release_monitor': 8868, 'release_recall': 489, 'release_infeasible': 1979, 'state_action': 2676, 'touch': 2676}
== (1) positive control: classifier vs committed rows
f1 committed cbd 84 classifier cbd 84 per-opp agree 132 / 132 | cloud-correct 82 device-correct 2 device-route n 7 cloud stands 125 | committed cloud-correct 82 device-correct 2
tl committed cbd 84 classifier cbd 84 per-opp agree 132 / 132 | cloud-correct 82 device-correct 2 device-route n 8 cloud stands 124 | committed cloud-correct 82 device-correct 2
cd committed cbd 81 classifier cbd 81 per-opp agree 132 / 132 | cloud-correct 80 device-correct 1 device-route n 9 cloud stands 123 | committed cloud-correct 80 device-correct 1
pw committed cbd 83 classifier cbd 83 per-opp agree 132 / 132 | cloud-correct 80 device-correct 3 device-route n 10 cloud stands 122 | committed cloud-correct 80 device-correct 3
la committed cbd 79 classifier cbd 79 per-opp agree 132 / 132 | cloud-correct 78 device-correct 1 device-route n 11 cloud stands 121 | committed cloud-correct 77 device-correct 2
e committed cbd 85 classifier cbd 85 per-opp agree 132 / 132 | cloud-correct 83 device-correct 2 device-route n 6 cloud stands 126 | committed cloud-correct 83 device-correct 2
r3 committed cbd 83 classifier cbd 83 per-opp agree 132 / 132 | cloud-correct 82 device-correct 1 device-route n 6 cloud stands 126 | committed cloud-correct 82 device-correct 1
rp committed cbd 85 classifier cbd 85 per-opp agree 132 / 132 | cloud-correct 84 device-correct 1 device-route n 5 cloud stands 127 | committed cloud-correct 84 device-correct 1
== (2) paired diffs f1 minus tl; opps overlap 132 132 132
distinct questions 20
cbd                            +0 CI[-3,+3] incl0
cloud on-time                  +1 CI[-2,+4] incl0
cloud-correct                  +0 CI[-3,+3] incl0
device-route (not cloud)       -1 CI[-4,+2] incl0
dashcam within_L -286 CI[-530,-56] (20 60s blocks; instants 11764/11764/11764)
SS cloud on-time f1 350 tl 353 diff -3 CI[-9,+2] (357 questions)
== (2) paired diffs f1 minus r3; opps overlap 132 132 132
distinct questions 20
cbd                            +1 CI[+0,+3] incl0
cloud on-time                  -1 CI[-3,+0] incl0
cloud-correct                  +0 CI[-3,+3] incl0
device-route (not cloud)       +1 CI[+0,+3] incl0
dashcam within_L -43 CI[-289,+188] (20 60s blocks; instants 11764/11764/11764)
SS cloud on-time f1 350 r3 351 diff -1 CI[-4,+2] (357 questions)
== (2) paired diffs f1 minus cd; opps overlap 132 132 132
distinct questions 20
cbd                            +3 CI[+0,+8] incl0
cloud on-time                  +2 CI[-2,+7] incl0
cloud-correct                  +2 CI[-2,+7] incl0
device-route (not cloud)       -2 CI[-7,+2] incl0
dashcam within_L -184 CI[-452,+53] (20 60s blocks; instants 11764/11764/11764)
SS cloud on-time f1 350 cd 349 diff +1 CI[-2,+5] (357 questions)
== (2) paired diffs f1 minus pw; opps overlap 132 132 132
distinct questions 20
cbd                            +1 CI[+0,+3] incl0
cloud on-time                  +3 CI[+0,+6] incl0
cloud-correct                  +2 CI[+0,+5] incl0
device-route (not cloud)       -3 CI[-6,+0] incl0
dashcam within_L -28 CI[-248,+174] (20 60s blocks; instants 11764/11764/11764)
SS cloud on-time f1 350 pw 351 diff -1 CI[-7,+4] (357 questions)
== (2) paired diffs f1 minus rp; opps overlap 132 132 132
distinct questions 20
cbd                            -1 CI[-3,+0] incl0
cloud on-time                  -2 CI[-5,+0] incl0
cloud-correct                  -2 CI[-5,+0] incl0
device-route (not cloud)       +2 CI[+0,+5] incl0
dashcam within_L +12 CI[-149,+164] (20 60s blocks; instants 11764/11764/11764)
SS cloud on-time f1 350 rp 351 diff -1 CI[-4,+2] (357 questions)
== (3) loss decomposition e vs tl ; states {'f1': {'WRONG': 43, 'ONTIME_CORRECT': 82, 'LATE_ENGINE': 7}, 'tl': {'WRONG': 42, 'ONTIME_CORRECT': 82, 'LATE_ENGINE': 6, 'REJECTED': 2}}
 on-time LOST by e 1 failing side (e state) {'LATE_ENGINE': 1} | of lost, tl answer WRONG 0
 on-time GAINED by e 2 failing side (tl state) {'REJECTED': 1, 'LATE_ENGINE': 1} | e answer WRONG 1 correct 1
 cbd-differing opps by owner and states
   ('e+1', 'tl:LATE_ENGINE', 'e:ONTIME_CORRECT') 1
   ('tl+1', 'tl:ONTIME_CORRECT', 'e:LATE_ENGINE') 1
== (3) loss decomposition e vs r3 ; states {'f1': {'WRONG': 43, 'ONTIME_CORRECT': 82, 'LATE_ENGINE': 7}, 'r3': {'WRONG': 44, 'ONTIME_CORRECT': 82, 'LATE_ENGINE': 6}}
 on-time LOST by e 1 failing side (e state) {'LATE_ENGINE': 1} | of lost, r3 answer WRONG 0
 on-time GAINED by e 0 failing side (r3 state) {} | e answer WRONG 0 correct 0
 cbd-differing opps by owner and states
   ('e+1', 'r3:WRONG', 'e:ONTIME_CORRECT') 1
== (3) loss decomposition e vs cd ; states {'f1': {'WRONG': 43, 'ONTIME_CORRECT': 82, 'LATE_ENGINE': 7}, 'cd': {'WRONG': 43, 'ONTIME_CORRECT': 80, 'LATE_ENGINE': 5, 'REJECTED': 4}}
 on-time LOST by e 1 failing side (e state) {'LATE_ENGINE': 1} | of lost, cd answer WRONG 0
 on-time GAINED by e 3 failing side (cd state) {'LATE_ENGINE': 1, 'REJECTED': 2} | e answer WRONG 0 correct 3
 cbd-differing opps by owner and states
   ('e+1', 'cd:LATE_ENGINE', 'e:ONTIME_CORRECT') 1
   ('e+1', 'cd:REJECTED', 'e:ONTIME_CORRECT') 2
== (3) loss decomposition e vs pw ; states {'f1': {'WRONG': 43, 'ONTIME_CORRECT': 82, 'LATE_ENGINE': 7}, 'pw': {'WRONG': 42, 'ONTIME_CORRECT': 80, 'LATE_ENGINE': 8, 'REJECTED': 2}}
 on-time LOST by e 0 failing side (e state) {} | of lost, pw answer WRONG 0
 on-time GAINED by e 3 failing side (pw state) {'REJECTED': 1, 'LATE_ENGINE': 2} | e answer WRONG 1 correct 2
 cbd-differing opps by owner and states
   ('e+1', 'pw:LATE_ENGINE', 'e:ONTIME_CORRECT') 1
== (3) loss decomposition e vs rp ; states {'f1': {'WRONG': 43, 'ONTIME_CORRECT': 82, 'LATE_ENGINE': 7}, 'rp': {'WRONG': 43, 'ONTIME_CORRECT': 84, 'LATE_ENGINE': 5}}
 on-time LOST by e 2 failing side (e state) {'LATE_ENGINE': 2} | of lost, rp answer WRONG 0
 on-time GAINED by e 0 failing side (rp state) {} | e answer WRONG 0 correct 0
 cbd-differing opps by owner and states
   ('rp+1', 'rp:ONTIME_CORRECT', 'e:LATE_ENGINE') 1
== (9) per-opportunity flips f1 vs tl
cbd flips 2 ['opp0006611', 'opp0009518'] | on-time flips 3 ['opp0004451', 'opp0006611', 'opp0009518']
== (9) per-opportunity flips f1 vs cd
cbd flips 3 ['opp0006611', 'opp0009620', 'opp0009672'] | on-time flips 4 ['opp0006611', 'opp0009524', 'opp0009620', 'opp0009672']
== (9) per-opportunity flips f1 vs pw
cbd flips 1 ['opp0006611'] | on-time flips 3 ['opp0004451', 'opp0006611', 'opp0009530']
== (9) per-opportunity flips tl vs cd
cbd flips 3 ['opp0009518', 'opp0009620', 'opp0009672'] | on-time flips 5 ['opp0004451', 'opp0009518', 'opp0009524', 'opp0009620', 'opp0009672']
== (9) per-opportunity flips tl vs pw
cbd flips 1 ['opp0009518'] | on-time flips 2 ['opp0009518', 'opp0009530']
cbd flips 2 (cd+1 0 pw+1 2) | on-time(source cloud) flips 5 (cd on-time only 3, pw only 2) | of 132
== (4) residency cold (analyse with opp ids)
f1 asks reached engine 132 resid-eligible 132 cold<.5 1 <.25 1 | declined recall opps 0
tl asks reached engine 130 resid-eligible 130 cold<.5 1 <.25 1 | declined recall opps 2
cd asks reached engine 128 resid-eligible 128 cold<.5 0 <.25 0 | declined recall opps 4
pw asks reached engine 130 resid-eligible 130 cold<.5 1 <.25 1 | declined recall opps 2
la asks reached engine 126 resid-eligible 126 cold<.5 1 <.25 1 | declined recall opps 6
e asks reached engine 132 resid-eligible 132 cold<.5 1 <.25 1 | declined recall opps 0
r3 asks reached engine 132 resid-eligible 132 cold<.5 1 <.25 1 | declined recall opps 0
rp asks reached engine 132 resid-eligible 132 cold<.5 1 <.25 1 | declined recall opps 0
RESID <.5 e-tl all q      n_q=20 e=1 tl=1 diff +0 CI[+0,+0]
RESID <.5 e-tl asked both n_q=19 e=1 tl=1 diff +0 CI[+0,+0]
RESID <.25 e-tl all q      n_q=20 e=1 tl=1 diff +0 CI[+0,+0]
RESID <.25 e-tl asked both n_q=19 e=1 tl=1 diff +0 CI[+0,+0]
 opps cold(<.5) in tl (1): fate in e {'sent in e: still cold': 1}
 opps cold(<.5) in E (1): same opp in tl {'tl: cold': 1}
RESID <.5 e-r3 all q      n_q=20 e=1 r3=1 diff +0 CI[+0,+0]
RESID <.5 e-r3 asked both n_q=20 e=1 r3=1 diff +0 CI[+0,+0]
RESID <.25 e-r3 all q      n_q=20 e=1 r3=1 diff +0 CI[+0,+0]
RESID <.25 e-r3 asked both n_q=20 e=1 r3=1 diff +0 CI[+0,+0]
 opps cold(<.5) in r3 (1): fate in e {'sent in e: still cold': 1}
 opps cold(<.5) in E (1): same opp in r3 {'r3: cold': 1}
RESID <.5 e-cd all q      n_q=20 e=1 cd=0 diff +1 CI[+0,+3]
RESID <.5 e-cd asked both n_q=19 e=1 cd=0 diff +1 CI[+0,+3]
RESID <.25 e-cd all q      n_q=20 e=1 cd=0 diff +1 CI[+0,+3]
RESID <.25 e-cd asked both n_q=19 e=1 cd=0 diff +1 CI[+0,+3]
 opps cold(<.5) in cd (0): fate in e {}
 opps cold(<.5) in E (1): same opp in cd {'cd: warm': 1}
RESID <.5 e-pw all q      n_q=20 e=1 pw=1 diff +0 CI[+0,+0]
RESID <.5 e-pw asked both n_q=19 e=1 pw=1 diff +0 CI[+0,+0]
RESID <.25 e-pw all q      n_q=20 e=1 pw=1 diff +0 CI[+0,+0]
RESID <.25 e-pw asked both n_q=19 e=1 pw=1 diff +0 CI[+0,+0]
 opps cold(<.5) in pw (1): fate in e {'sent in e: still cold': 1}
 opps cold(<.5) in E (1): same opp in pw {'pw: cold': 1}
RESID <.5 e-rp all q      n_q=20 e=1 rp=1 diff +0 CI[+0,+0]
RESID <.5 e-rp asked both n_q=20 e=1 rp=1 diff +0 CI[+0,+0]
RESID <.25 e-rp all q      n_q=20 e=1 rp=1 diff +0 CI[+0,+0]
RESID <.25 e-rp asked both n_q=20 e=1 rp=1 diff +0 CI[+0,+0]
 opps cold(<.5) in rp (1): fate in e {'sent in e: still cold': 1}
 opps cold(<.5) in E (1): same opp in rp {'rp: cold': 1}
== (7) FAIR share (RE-IMPLEMENTATION: robot+SS rows, oracle all-cloud with history, floors A_RD/A_SD; no over-32k exclusion, no question dedup)
f1 combined rel 0.9600 (abs gain 64.75 of oracle 67.44) | robot rel 0.9470 (38.88 of 41.06) | ss rel 0.9804 (25.86 of 26.38)
tl combined rel 0.9587 (abs gain 64.66 of oracle 67.44) | robot rel 0.9394 (38.57 of 41.06) | ss rel 0.9888 (26.09 of 26.38)
cd combined rel 0.9497 (abs gain 64.05 of oracle 67.44) | robot rel 0.9318 (38.26 of 41.06) | ss rel 0.9776 (25.79 of 26.38)
pw combined rel 0.9473 (abs gain 63.89 of oracle 67.44) | robot rel 0.9242 (37.95 of 41.06) | ss rel 0.9832 (25.94 of 26.38)
la combined rel 0.9381 (abs gain 63.27 of oracle 67.44) | robot rel 0.9091 (37.33 of 41.06) | ss rel 0.9832 (25.94 of 26.38)
e combined rel 0.9658 (abs gain 65.13 of oracle 67.44) | robot rel 0.9545 (39.19 of 41.06) | ss rel 0.9832 (25.94 of 26.38)
r3 combined rel 0.9658 (abs gain 65.13 of oracle 67.44) | robot rel 0.9545 (39.19 of 41.06) | ss rel 0.9832 (25.94 of 26.38)
rp combined rel 0.9704 (abs gain 65.44 of oracle 67.44) | robot rel 0.9621 (39.51 of 41.06) | ss rel 0.9832 (25.94 of 26.38)
FAIR f1-tl rel diff +0.0013 CI[-0.0154,+0.0192] | abs gain diff +0.09 CI[-0.99,+1.24]
FAIR f1-r3 rel diff -0.0057 CI[-0.0166,+0.0015] | abs gain diff -0.38 CI[-1.15,+0.07]
FAIR f1-cd rel diff +0.0103 CI[-0.0089,+0.0367] | abs gain diff +0.70 CI[-0.62,+2.47]
FAIR f1-pw rel diff +0.0127 CI[-0.0022,+0.0298] | abs gain diff +0.86 CI[-0.13,+2.09]
FAIR f1-rp rel diff -0.0103 CI[-0.0242,+0.0009] | abs gain diff -0.70 CI[-1.70,+0.07]
== (8) touches per robot session
f1 touch requests 2676 sessions 22 per-session min/med/max 0 0.0 1348 zero-touch sessions 19
tl touch requests 2671 sessions 22 per-session min/med/max 0 0.0 1348 zero-touch sessions 19
cd touch requests 2676 sessions 22 per-session min/med/max 0 0.0 1343 zero-touch sessions 19
pw touch requests 2670 sessions 22 per-session min/med/max 0 0.0 1348 zero-touch sessions 19
la touch requests 2666 sessions 22 per-session min/med/max 0 0.0 1345 zero-touch sessions 19
e touch requests 2675 sessions 22 per-session min/med/max 0 0.0 1346 zero-touch sessions 19
r3 touch requests 2674 sessions 22 per-session min/med/max 0 0.0 1346 zero-touch sessions 19
rp touch requests 2676 sessions 22 per-session min/med/max 0 0.0 1347 zero-touch sessions 19

== B decisions F1 vs F0
== (A) B decisions by direction (la_decisions rows; robot vs SS)
  ('SS', 'CLOUD', 'CLOUD', False) 352
  ('SS', 'CLOUD', 'DEFER', True) 1
  ('SS', 'CLOUD', 'REJECT', True) 5
  ('robot', 'CLOUD', 'CLOUD', False) 132
queries 489 rows 490 multi-eval queries 1
DEFER chains (first la decisions then re-evals, joined by query_id/eval_seq): {'DEFER>REJECT iso:CLOUD': 1}
final decision by group Counter({('SS', 'CLOUD'): 352, ('robot', 'CLOUD'): 132, ('SS', 'REJECT'): 5})
declines in decision log 5 = final REJECT queries 5
== (B) robot B-reject (isolated CLOUD at some eval, final REJECT) and b7-equivalent (isolated REJECT) outcome in r3 and z
 B-reject detail (opp, kind, r3 state, z state, iso/la est, slack, u, Pfrac, queued_ahead, device_correct):
 B-reject net by cbd: opps 0, device correct 0; comparator r3 cloud-correct-on-time 0 (rp 0)

== THE FIVE ASKS (pw live)
opp0004451
  pw eval1 t=445.8 dec=DEFER iso=CLOUD P=0.379(9904 tok) u=16227 est_iso=0.82 est_la=3.03 slack=2.89 qa=0 prompt=26131 sid=_end_600.122
  pw eval2 t=446.3 dec=REJECT iso=CLOUD P=0.379(9904 tok) u=16227 est_iso=0.82 est_la=3.35 slack=2.39 qa=2070 prompt=26131 sid=_end_600.122
  la eval1 dec=REJECT iso=CLOUD P=0.379 u=16227 est_la=3.61 slack=2.96 qa=3802
  f1: state=WRONG cbd=0 engine_cached=0.952 ttft=0.98 | tl: state=REJECTED cbd=0 engine_cached=None ttft=- | cd: state=WRONG cbd=0 engine_cached=0.948 ttft=1.01 | pw: state=REJECTED cbd=0 engine_cached=None ttft=- | la: state=REJECTED cbd=0 engine_cached=None ttft=- | e: state=WRONG cbd=0 engine_cached=0.952 ttft=0.97 | r3: state=WRONG cbd=0 engine_cached=0.952 ttft=1.30 | rp: state=WRONG cbd=0 engine_cached=0.952 ttft=1.11
   pw session prev sent cached=0.899 next sent cached=None (n sess reqs 10)
   la session prev sent cached=0.899 next sent cached=None (n sess reqs 10)
   r3 session prev sent cached=0.396 next sent cached=None (n sess reqs 12)
opp0010346
  pw eval1 t=1015.0 dec=CLOUD iso=CLOUD P=0.791(19536 tok) u=5155 est_iso=0.78 est_la=1.25 slack=2.92 qa=1550 prompt=24691 sid=0_end_599.96
  la eval1 dec=DEFER iso=CLOUD P=0.336 u=16387 est_la=3.30 slack=2.97 qa=1550
  la eval2 dec=REJECT iso=CLOUD P=0.335 u=16477 est_la=3.32 slack=2.47 qa=1580
  f1: state=ONTIME_CORRECT cbd=1 engine_cached=0.789 ttft=2.05 | tl: state=ONTIME_CORRECT cbd=1 engine_cached=0.832 ttft=1.79 | cd: state=ONTIME_CORRECT cbd=1 engine_cached=0.828 ttft=1.76 | pw: state=ONTIME_CORRECT cbd=1 engine_cached=0.789 ttft=2.03 | la: state=REJECTED cbd=0 engine_cached=None ttft=- | e: state=ONTIME_CORRECT cbd=1 engine_cached=0.789 ttft=2.00 | r3: state=ONTIME_CORRECT cbd=1 engine_cached=0.736 ttft=2.29 | rp: state=ONTIME_CORRECT cbd=1 engine_cached=0.736 ttft=2.32
   pw session prev sent cached=0.949 next sent cached=0.975 (n sess reqs 22)
   la session prev sent cached=0.949 next sent cached=None (n sess reqs 18)
   r3 session prev sent cached=0.949 next sent cached=0.975 (n sess reqs 22)
opp0010459
  pw eval1 t=1026.0 dec=CLOUD iso=CLOUD P=0.664(16752 tok) u=8479 est_iso=0.79 est_la=1.62 slack=2.93 qa=30 prompt=25231 sid=0_end_599.96
  la eval1 dec=DEFER iso=CLOUD P=0.329 u=16927 est_la=3.16 slack=2.88 qa=15
  la eval2 dec=REJECT iso=CLOUD P=0.329 u=16927 est_la=3.38 slack=2.38 qa=1481
  f1: state=ONTIME_CORRECT cbd=1 engine_cached=0.736 ttft=2.44 | tl: state=ONTIME_CORRECT cbd=1 engine_cached=0.975 ttft=0.96 | cd: state=ONTIME_CORRECT cbd=1 engine_cached=0.975 ttft=0.89 | pw: state=ONTIME_CORRECT cbd=1 engine_cached=0.975 ttft=0.51 | la: state=REJECTED cbd=0 engine_cached=None ttft=- | e: state=ONTIME_CORRECT cbd=1 engine_cached=0.712 ttft=2.48 | r3: state=ONTIME_CORRECT cbd=1 engine_cached=0.975 ttft=0.55 | rp: state=ONTIME_CORRECT cbd=1 engine_cached=0.975 ttft=0.55
   pw session prev sent cached=0.789 next sent cached=0.999 (n sess reqs 22)
   la session prev sent cached=0.949 next sent cached=None (n sess reqs 18)
   r3 session prev sent cached=0.736 next sent cached=0.999 (n sess reqs 22)
opp0010467
  pw eval1 t=1026.8 dec=CLOUD iso=CLOUD P=0.999(25216 tok) u=15 est_iso=0.79 est_la=0.19 slack=2.95 qa=775 prompt=25231 sid=0_end_599.96
  la eval1 dec=DEFER iso=CLOUD P=0.329 u=16927 est_la=3.28 slack=2.90 qa=805
  la eval2 dec=REJECT iso=CLOUD P=0.329 u=16927 est_la=3.40 slack=2.40 qa=1565
  f1: state=ONTIME_CORRECT cbd=1 engine_cached=0.999 ttft=2.33 | tl: state=ONTIME_CORRECT cbd=1 engine_cached=0.999 ttft=0.33 | cd: state=ONTIME_CORRECT cbd=1 engine_cached=0.999 ttft=0.49 | pw: state=ONTIME_CORRECT cbd=1 engine_cached=0.999 ttft=0.22 | la: state=REJECTED cbd=0 engine_cached=None ttft=- | e: state=ONTIME_CORRECT cbd=1 engine_cached=0.999 ttft=2.19 | r3: state=ONTIME_CORRECT cbd=1 engine_cached=0.999 ttft=0.28 | rp: state=ONTIME_CORRECT cbd=1 engine_cached=0.999 ttft=0.27
   pw session prev sent cached=0.975 next sent cached=0.993 (n sess reqs 22)
   la session prev sent cached=0.949 next sent cached=None (n sess reqs 18)
   r3 session prev sent cached=0.975 next sent cached=0.993 (n sess reqs 22)
opp0010481
  pw eval1 t=1028.2 dec=CLOUD iso=CLOUD P=0.996(25216 tok) u=105 est_iso=0.80 est_la=0.58 slack=2.93 qa=3213 prompt=25321 sid=0_end_599.96
  la eval1 dec=DEFER iso=CLOUD P=0.328 u=17017 est_la=3.30 slack=2.88 qa=820
  la eval2 dec=REJECT iso=CLOUD P=0.328 u=17017 est_la=3.24 slack=2.38 qa=410
  f1: state=ONTIME_CORRECT cbd=1 engine_cached=0.993 ttft=0.84 | tl: state=ONTIME_CORRECT cbd=1 engine_cached=0.993 ttft=0.50 | cd: state=ONTIME_CORRECT cbd=1 engine_cached=0.993 ttft=0.22 | pw: state=ONTIME_CORRECT cbd=1 engine_cached=0.993 ttft=0.70 | la: state=REJECTED cbd=0 engine_cached=None ttft=- | e: state=ONTIME_CORRECT cbd=1 engine_cached=0.993 ttft=0.71 | r3: state=ONTIME_CORRECT cbd=1 engine_cached=0.993 ttft=0.38 | rp: state=ONTIME_CORRECT cbd=1 engine_cached=0.993 ttft=0.42
   pw session prev sent cached=0.999 next sent cached=None (n sess reqs 22)
   la session prev sent cached=0.949 next sent cached=None (n sess reqs 18)
   r3 session prev sent cached=0.999 next sent cached=None (n sess reqs 22)
== D3: |P_pw(first eval) - ref| <= 0.15 ; refs: (a) r3 twin engine cached frac, (b) pw/la cell own engine cached (own if sent else session prev sent; la own)
opp0004451 P=0.379 | (a) r3 twin 0.952 -> within0.15 False ; rep2 twin 0.952 -> False | (b) pw session prev sent 0.899 -> False ; la-er own sent None -> None
opp0010346 P=0.791 | (a) r3 twin 0.736 -> within0.15 True ; rep2 twin 0.736 -> True | (b) pw own sent 0.789 -> True ; la-er own sent None -> None
opp0010459 P=0.664 | (a) r3 twin 0.975 -> within0.15 False ; rep2 twin 0.975 -> False | (b) pw own sent 0.975 -> False ; la-er own sent None -> None
opp0010467 P=0.999 | (a) r3 twin 0.999 -> within0.15 True ; rep2 twin 0.999 -> True | (b) pw own sent 0.999 -> True ; la-er own sent None -> None
opp0010481 P=0.996 | (a) r3 twin 0.993 -> within0.15 True ; rep2 twin 0.993 -> True | (b) pw own sent 0.993 -> True ; la-er own sent None -> None
== la-er B-rejects and their fate in pw
opp0004175 la-er P=0.40 est_la=3.06 slack=2.44 | la-er state REJECTED r3 state LATE_ENGINE | pw: REJECT P=0.40 est_la=3.11 state=REJECTED
opp0004451 la-er P=0.38 est_la=3.61 slack=2.96 | la-er state REJECTED r3 state WRONG | pw: REJECT P=0.38 est_la=3.35 state=REJECTED
opp0010346 la-er P=0.34 est_la=3.32 slack=2.47 | la-er state REJECTED r3 state ONTIME_CORRECT | pw: CLOUD P=0.79 est_la=1.25 state=ONTIME_CORRECT
opp0010459 la-er P=0.33 est_la=3.38 slack=2.38 | la-er state REJECTED r3 state ONTIME_CORRECT | pw: CLOUD P=0.66 est_la=1.62 state=ONTIME_CORRECT
opp0010467 la-er P=0.33 est_la=3.40 slack=2.40 | la-er state REJECTED r3 state ONTIME_CORRECT | pw: CLOUD P=1.00 est_la=0.19 state=ONTIME_CORRECT
opp0010481 la-er P=0.33 est_la=3.24 slack=2.38 | la-er state REJECTED r3 state ONTIME_CORRECT | pw: CLOUD P=1.00 est_la=0.58 state=ONTIME_CORRECT
== P vs engine preceding cached frac, ALL robot B decisions
pw n 132 MAE vs preceding engine cached 0.149 |err| q50/90/99 [0.054, 0.52, 0.676] P more than 0.3 below 11 above 16 | rejects (opp,P,prec): [('opp0004175', 0.397, 0.899), ('opp0004451', 0.379, 0.899)] | MAE vs own engine cached (sent) 0.015 n=130 q50/90/99 [0.006, 0.014, 0.311]
la n 132 MAE vs preceding engine cached 0.169 |err| q50/90/99 [0.082, 0.531, 0.687] P more than 0.3 below 15 above 14 | rejects (opp,P,prec): [('opp0004175', 0.397, 0.899), ('opp0004451', 0.379, 0.899), ('opp0010346', 0.336, 0.949), ('opp0010459', 0.329, 0.949), ('opp0010467', 0.329, 0.949), ('opp0010481', 0.328, 0.949)] | MAE vs own engine cached (sent) 0.022 n=126 q50/90/99 [0.007, 0.06, 0.141]
