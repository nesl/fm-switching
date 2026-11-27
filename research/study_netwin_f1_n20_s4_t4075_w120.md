== netwin f1_n20_s4_t4075  outage=covex-v6-fair-final-cand-tl-sync-cf_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link_qp  control=covex-v6-fair-final-cand-tl-sync-cf_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp  t0=407.5 d=188.0 R=595.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 132 (committed robot_headline 0.466431 x n 283 = 132.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 155 (committed 155); within_L(outcomes) 156; dashcam within(1.0) 3935 vs within_L 3935 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 124 (headline 0.438163 x 283); classifier agree 283 of 283; SS on_time 174 (committed 174) within_L 174; dashcam within(1.0) 4321 vs within_L 4321
  same opportunity ids in both cells: robot 283/283, SS 237/237
B_obs DEFINITION (fixed before outcomes): rate_W(t)=sum uncached prompt tokens of robot requests with t_submit in (t-W,t] / W, 1 s grid; ctl(t)=control rate at the same absolute time; sd=sd of control rate over [60,t0). DEF1=first t>=R, after outage rate first exceeds ctl+1sd, at which outage<=ctl+1sd. DEF2=last exceedance+1 s. Rule window = DEF1 at W=10; others sensitivity.
  W= 5: ctl pre mean 1626 sd 2124 tok/s; first exceed R+0; B_obs DEF1 6 s DEF2 584 s
  W=10: ctl pre mean 1625 sd 1530 tok/s; first exceed R+2; B_obs DEF1 12 s DEF2 588 s
  W=20: ctl pre mean 1564 sd 1183 tok/s; first exceed R+2; B_obs DEF1 6 s DEF2 594 s
  rate trace W=10 (t-R,ctl,out): [(-10, 1088, 0), (0, 1010, 0), (0, 1010, 1811), (10, 1224, 3772), (20, 1030, 2173), (30, 370, 982), (40, 1302, 1926), (50, 73, 722), (60, 100, 351), (70, 0, 250), (80, 495, 942), (90, 1680, 1160), (100, 1165, 1406), (110, 116, 226), (120, 259, 649), (130, 310, 1449), (140, 3901, 4117), (150, 710, 655), (160, 3131, 4775), (170, 3965, 1445), (180, 239, 2169), (190, 4387, 3604), (200, 49, 31), (210, 2454, 2687), (220, 329, 1157), (230, 2883, 2195), (240, 22, 3507), (250, 2953, 1894), (260, 1866, 1886), (270, 4153, 2846), (280, 1634, 0), (290, 1863, 5525)]
  drain cross-check from outage log: {'n_deferred_frames': 1312, 'deferred_own_tokens': 118328, 'n_victims': 14, 'uplink_queue_max_max': 1.3, 'last_backlogged_delivery': None, 'n_backlogged': 0, 'last_delayed_submit': None, 'n_delayed_after_R': 0}
  deficit-recovery marker (victim robot uncached tokens, cum out minus ctl from t0): deficit at R -455938 tok; first t>=R with cum out>=ctl: never; end-of-run diff -276596
  DEF1 vs DEF2 vs drain: 12 / 588 / n/a  UNSTABLE: DEF1 differs >50% across W or <30 s (bursty); DEF1(W=10) kept as rule
RULE WINDOW (user ruling, amends D332 item 8): every arm and seed scored over ONE FIXED [R,R+120]; sensitivity [R,R+60], [R,R+300]. B_obs DEF1/DEF2 above are DESCRIPTIVE per arm only (B_obs depends on the arm).
  B_obs descriptive (W=10): DEF1 12 s, DEF2 588 s (outage arm vs control-threshold)
== RULE fixed [R,R+120] [595.5,715.5)  len 120 s
  robot cbd                n=  26 ctl   20 (0.769) out   17 (0.654) harm(ctl-out) +3 CI[+0,+7] clusters=7 (robot questions)
  robot cloud on-time      n=  26 ctl   25 (0.962) out   19 (0.731) harm(ctl-out) +6 CI[+2,+10] clusters=7 (robot questions)
  SS on-time (scorer)      n=  24 ctl   24 (1.000) out   20 (0.833) harm(ctl-out) +4 CI[+1,+8] clusters=24 (SS questions)
  SS within_L (outcome)    n=  24 ctl   24 (1.000) out   20 (0.833) harm(ctl-out) +4 CI[+1,+8] clusters=24 (SS questions)
  dashcam within_L         n= 797 ctl  645 (0.809) out  518 (0.650) harm(ctl-out) +127 CI[-9,+303] clusters=3 (60 s blocks, 797 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+60] [595.5,655.5)  len 60 s
  robot cbd                n=  12 ctl   11 (0.917) out    9 (0.750) harm(ctl-out) +2 CI[+0,+6] clusters=4 (robot questions)
  robot cloud on-time      n=  12 ctl   11 (0.917) out    6 (0.500) harm(ctl-out) +5 CI[+2,+8] clusters=4 (robot questions)
  SS on-time (scorer)      n=  12 ctl   12 (1.000) out    8 (0.667) harm(ctl-out) +4 CI[+1,+7] clusters=12 (SS questions)
  SS within_L (outcome)    n=  12 ctl   12 (1.000) out    8 (0.667) harm(ctl-out) +4 CI[+1,+7] clusters=12 (SS questions)
  dashcam within_L         n= 386 ctl  301 (0.780) out  171 (0.443) harm(ctl-out) +130 CI[+64,+189] clusters=7 (10 s blocks, 386 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+300] [595.5,895.5)  len 300 s
  robot cbd                n=  67 ctl   37 (0.552) out   36 (0.537) harm(ctl-out) +1 CI[-4,+7] clusters=15 (robot questions)
  robot cloud on-time      n=  67 ctl   48 (0.716) out   42 (0.627) harm(ctl-out) +6 CI[-3,+14] clusters=15 (robot questions)
  SS on-time (scorer)      n=  60 ctl   51 (0.850) out   43 (0.717) harm(ctl-out) +8 CI[+0,+16] clusters=60 (SS questions)
  SS within_L (outcome)    n=  60 ctl   51 (0.850) out   43 (0.717) harm(ctl-out) +8 CI[+0,+16] clusters=60 (SS questions)
  dashcam within_L         n=1984 ctl 1196 (0.603) out  887 (0.447) harm(ctl-out) +309 CI[+97,+533] clusters=6 (60 s blocks, 1984 instants; unmatched ctl 0 out 0)
== DURING-OUTAGE [t0,R] (beside) [407.5,595.5)  len 188 s
  robot cbd                n=  40 ctl   18 (0.450) out   16 (0.400) harm(ctl-out) +2 CI[-4,+7] clusters=13 (robot questions)
  robot cloud on-time      n=  40 ctl   14 (0.350) out    0 (0.000) harm(ctl-out) +14 CI[+8,+22] clusters=13 (robot questions)
  SS on-time (scorer)      n=  37 ctl   15 (0.405) out   35 (0.946) harm(ctl-out) -20 CI[-26,-13] clusters=37 (SS questions)
  SS within_L (outcome)    n=  37 ctl   15 (0.405) out   35 (0.946) harm(ctl-out) -20 CI[-26,-13] clusters=37 (SS questions)
  dashcam within_L         n=1251 ctl  492 (0.393) out 1165 (0.931) harm(ctl-out) -673 CI[-1174,-155] clusters=4 (60 s blocks, 1251 instants; unmatched ctl 0 out 0)
== WHOLE RUN (beside) [0.0,1201.0)  len 1201 s
  robot cbd                n= 283 ctl  132 (0.466) out  124 (0.438) harm(ctl-out) +8 CI[-3,+20] clusters=47 (robot questions)
  robot cloud on-time      n= 283 ctl  151 (0.534) out  117 (0.413) harm(ctl-out) +34 CI[+17,+53] clusters=47 (robot questions)
  SS on-time (scorer)      n= 237 ctl  155 (0.654) out  174 (0.734) harm(ctl-out) -19 CI[-36,-2] clusters=237 (SS questions)
  SS within_L (outcome)    n= 237 ctl  156 (0.658) out  174 (0.734) harm(ctl-out) -18 CI[-35,-1] clusters=237 (SS questions)
  dashcam within_L         n=7850 ctl 3935 (0.501) out 4321 (0.550) harm(ctl-out) -386 CI[-1396,+451] clusters=20 (60 s blocks, 7850 instants; unmatched ctl 0 out 0)
CATCH-UP: uncached tokens (robot requests by t_submit)
  [R,R+300]    ctl n=883 tok=434265 | out n=2362 tok=563236 | out-ctl tok +128971 (+29.7%)
  [R,R+B]      ctl n=6 tok=12432 | out n=44 tok=56024 | out-ctl tok +43592 (+350.6%)
  [t0,R]       ctl n=81 tok=449552 | out n=939 tok=2817 | out-ctl tok -446735 (-99.4%)
  [R+B,R+300]  ctl n=877 tok=421833 | out n=2318 tok=507212 | out-ctl tok +85379 (+20.2%)

##### ABS F1 minus F0 (netwin_abs)
ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=out_f1_s4_t4075_w120.json | B=out_f0_s4_t4075_w120.json
seeds in A/B: [4] / [4]
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 17 B 19 | A-B -2 CI[-4,+0] clusters=7 | own control A 20 B 20 (A-B +0)
  robot cloud on-time  nA=26 nB=26 | outage A 19 B 21 | A-B -2 CI[-4,+0] clusters=7 | own control A 25 B 25 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 20 B 21 | A-B -1 CI[-3,+0] clusters=24 | own control A 24 B 24 (A-B +0)
  dashcam within_L     nA=797 nB=797 | outage A 518 B 566 | A-B -48 CI[-147,+3] clusters=3 | own control A 645 B 692 (A-B -47)
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 9 B 10 | A-B -1 CI[-3,+0] clusters=4 | own control A 11 B 11 (A-B +0)
  robot cloud on-time  nA=12 nB=12 | outage A 6 B 7 | A-B -1 CI[-3,+0] clusters=4 | own control A 11 B 11 (A-B +0)
  SS on-time (scorer)  nA=12 nB=12 | outage A 8 B 9 | A-B -1 CI[-3,+0] clusters=12 | own control A 12 B 12 (A-B +0)
  dashcam within_L     nA=386 nB=386 | outage A 171 B 220 | A-B -49 CI[-81,-19] clusters=7 | own control A 301 B 318 (A-B -17)
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 36 B 38 | A-B -2 CI[-5,+0] clusters=15 | own control A 37 B 38 (A-B -1)
  robot cloud on-time  nA=67 nB=67 | outage A 42 B 41 | A-B +1 CI[-6,+9] clusters=15 | own control A 48 B 52 (A-B -4)
  SS on-time (scorer)  nA=60 nB=60 | outage A 43 B 46 | A-B -3 CI[-9,+3] clusters=60 | own control A 51 B 53 (A-B -2)
  dashcam within_L     nA=1984 nB=1984 | outage A 887 B 1054 | A-B -167 CI[-398,+15] clusters=6 | own control A 1196 B 1465 (A-B -269)
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 124 B 134 | A-B -10 CI[-21,+0] clusters=47 | own control A 132 B 154 (A-B -22)
  robot cloud on-time  nA=283 nB=283 | outage A 117 B 133 | A-B -16 CI[-33,-1] clusters=47 | own control A 151 B 181 (A-B -30)
  SS on-time (scorer)  nA=237 nB=237 | outage A 174 B 176 | A-B -2 CI[-17,+12] clusters=237 | own control A 155 B 199 (A-B -44)
  dashcam within_L     nA=7850 nB=7850 | outage A 4321 B 4561 | A-B -240 CI[-856,+238] clusters=20 | own control A 3935 B 5343 (A-B -1408)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 out_f1_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 132/283; cloud[120] 25/26; cloud[whole] 151/283; SS[120] 24/24; SS[whole] 155/237; dashcam[120] 645/797; dashcam[whole] 3935/7850
  B seed 4 out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
##### POOL A=F1 B=F0
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -20 (n=37,cl=37) harmB -3 (n=37,cl=37) A-B -17 CI[-24,-9]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -20 (n=37,cl=37) harmB -3 (n=37,cl=37) A-B -17 CI[-24,-9]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -673 (n=1251,cl=4) harmB -202 (n=1251,cl=4) A-B -471 CI[-989,+143]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +2 (n=40,cl=13) harmB +9 (n=40,cl=13) A-B -7 CI[-20,+4]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +14 (n=40,cl=13) harmB +21 (n=40,cl=13) A-B -7 CI[-20,+6]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +4 (n=24,cl=24) harmB +3 (n=24,cl=24) A-B +1 CI[-4,+6]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +4 (n=24,cl=24) harmB +3 (n=24,cl=24) A-B +1 CI[-4,+6]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +127 (n=797,cl=3) harmB +126 (n=797,cl=3) A-B +1 CI[-144,+176]
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=26,cl=7) harmB +1 (n=26,cl=7) A-B +2 CI[-2,+7]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +6 (n=26,cl=7) harmB +4 (n=26,cl=7) A-B +2 CI[-4,+8]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -19 (n=237,cl=237) harmB +23 (n=237,cl=237) A-B -42 CI[-63,-21]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA -18 (n=237,cl=237) harmB +23 (n=237,cl=237) A-B -41 CI[-62,-20]
== WHOLE RUN (beside)|dashcam within_L                                 harmA -386 (n=7850,cl=20) harmB +782 (n=7850,cl=20) A-B -1168 CI[-2299,-130]
== WHOLE RUN (beside)|robot cbd                                        harmA +8 (n=283,cl=47) harmB +20 (n=283,cl=47) A-B -12 CI[-32,+8]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +34 (n=283,cl=47) harmB +48 (n=283,cl=47) A-B -14 CI[-41,+15]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +8 (n=60,cl=60) harmB +7 (n=60,cl=60) A-B +1 CI[-10,+11]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +8 (n=60,cl=60) harmB +8 (n=60,cl=60) A-B +0 CI[-10,+11]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +309 (n=1984,cl=6) harmB +411 (n=1984,cl=6) A-B -102 CI[-405,+212]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +1 (n=67,cl=15) harmB +0 (n=67,cl=15) A-B +1 CI[-7,+8]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +6 (n=67,cl=15) harmB +11 (n=67,cl=15) A-B -5 CI[-18,+8]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +4 (n=12,cl=12) harmB +3 (n=12,cl=12) A-B +1 CI[-3,+5]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +4 (n=12,cl=12) harmB +3 (n=12,cl=12) A-B +1 CI[-3,+5]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +130 (n=386,cl=7) harmB +98 (n=386,cl=7) A-B +32 CI[-67,+127]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +2 (n=12,cl=4) harmB +1 (n=12,cl=4) A-B +1 CI[-2,+5]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +5 (n=12,cl=4) harmB +4 (n=12,cl=4) A-B +1 CI[-3,+5]
##### POOL A=F1 B=eager
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -20 (n=37,cl=37) harmB -3 (n=37,cl=37) A-B -17 CI[-24,-9]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -20 (n=37,cl=37) harmB -3 (n=37,cl=37) A-B -17 CI[-24,-9]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -673 (n=1251,cl=4) harmB -202 (n=1251,cl=4) A-B -471 CI[-989,+143]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +2 (n=40,cl=13) harmB +9 (n=40,cl=13) A-B -7 CI[-20,+4]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +14 (n=40,cl=13) harmB +21 (n=40,cl=13) A-B -7 CI[-20,+6]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +4 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -4 CI[-10,+2]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +4 (n=24,cl=24) harmB +7 (n=24,cl=24) A-B -3 CI[-9,+3]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +127 (n=797,cl=3) harmB +424 (n=797,cl=3) A-B -297 CI[-621,+40]
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=26,cl=7) harmB +1 (n=26,cl=7) A-B +2 CI[-2,+7]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +6 (n=26,cl=7) harmB +8 (n=26,cl=7) A-B -2 CI[-13,+7]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -19 (n=237,cl=237) harmB +30 (n=237,cl=237) A-B -49 CI[-72,-26]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA -18 (n=237,cl=237) harmB +30 (n=237,cl=237) A-B -48 CI[-71,-25]
== WHOLE RUN (beside)|dashcam within_L                                 harmA -386 (n=7850,cl=20) harmB +999 (n=7850,cl=20) A-B -1385 CI[-2561,-262]
== WHOLE RUN (beside)|robot cbd                                        harmA +8 (n=283,cl=47) harmB +20 (n=283,cl=47) A-B -12 CI[-32,+9]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +34 (n=283,cl=47) harmB +58 (n=283,cl=47) A-B -24 CI[-55,+8]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +8 (n=60,cl=60) harmB +17 (n=60,cl=60) A-B -9 CI[-22,+4]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +8 (n=60,cl=60) harmB +17 (n=60,cl=60) A-B -9 CI[-22,+4]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +309 (n=1984,cl=6) harmB +797 (n=1984,cl=6) A-B -488 CI[-872,-85]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +1 (n=67,cl=15) harmB +1 (n=67,cl=15) A-B +0 CI[-7,+8]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +6 (n=67,cl=15) harmB +15 (n=67,cl=15) A-B -9 CI[-26,+8]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +4 (n=12,cl=12) harmB +6 (n=12,cl=12) A-B -2 CI[-7,+3]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +4 (n=12,cl=12) harmB +5 (n=12,cl=12) A-B -1 CI[-6,+4]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +130 (n=386,cl=7) harmB +265 (n=386,cl=7) A-B -135 CI[-238,-41]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +2 (n=12,cl=4) harmB +1 (n=12,cl=4) A-B +1 CI[-2,+5]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +5 (n=12,cl=4) harmB +4 (n=12,cl=4) A-B +1 CI[-3,+5]
##### POOL A=F1 B=rung3
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -20 (n=37,cl=37) harmB -13 (n=37,cl=37) A-B -7 CI[-16,+2]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -20 (n=37,cl=37) harmB -13 (n=37,cl=37) A-B -7 CI[-15,+2]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -673 (n=1251,cl=4) harmB -659 (n=1251,cl=4) A-B -14 CI[-582,+614]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +2 (n=40,cl=13) harmB +4 (n=40,cl=13) A-B -2 CI[-12,+7]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +14 (n=40,cl=13) harmB +14 (n=40,cl=13) A-B +0 CI[-12,+11]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +4 (n=24,cl=24) harmB +0 (n=24,cl=24) A-B +4 CI[-2,+10]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +4 (n=24,cl=24) harmB +0 (n=24,cl=24) A-B +4 CI[-1,+9]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +127 (n=797,cl=3) harmB +25 (n=797,cl=3) A-B +102 CI[-45,+278]
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=26,cl=7) harmB +2 (n=26,cl=7) A-B +1 CI[-4,+6]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +6 (n=26,cl=7) harmB +2 (n=26,cl=7) A-B +4 CI[-2,+10]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -19 (n=237,cl=237) harmB -5 (n=237,cl=237) A-B -14 CI[-37,+9]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA -18 (n=237,cl=237) harmB -8 (n=237,cl=237) A-B -10 CI[-31,+13]
== WHOLE RUN (beside)|dashcam within_L                                 harmA -386 (n=7850,cl=20) harmB -770 (n=7850,cl=20) A-B +384 CI[-830,+1563]
== WHOLE RUN (beside)|robot cbd                                        harmA +8 (n=283,cl=47) harmB +8 (n=283,cl=47) A-B +0 CI[-19,+18]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +34 (n=283,cl=47) harmB +13 (n=283,cl=47) A-B +21 CI[-7,+51]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +8 (n=60,cl=60) harmB +6 (n=60,cl=60) A-B +2 CI[-9,+13]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +8 (n=60,cl=60) harmB +4 (n=60,cl=60) A-B +4 CI[-6,+14]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +309 (n=1984,cl=6) harmB -69 (n=1984,cl=6) A-B +378 CI[+113,+682]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +1 (n=67,cl=15) harmB +4 (n=67,cl=15) A-B -3 CI[-11,+4]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +6 (n=67,cl=15) harmB -6 (n=67,cl=15) A-B +12 CI[-1,+24]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +4 (n=12,cl=12) harmB +1 (n=12,cl=12) A-B +3 CI[-2,+8]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +4 (n=12,cl=12) harmB +0 (n=12,cl=12) A-B +4 CI[-1,+9]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +130 (n=386,cl=7) harmB +39 (n=386,cl=7) A-B +91 CI[-17,+196]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +2 (n=12,cl=4) harmB +2 (n=12,cl=4) A-B +0 CI[-4,+4]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +5 (n=12,cl=4) harmB +2 (n=12,cl=4) A-B +3 CI[-3,+8]
##### BURST (uncached robot tokens R+60/120/300)
F1 out [117312, 163704, 563236]
F0 out [104789, 150549, 493299]
F1 ctl [41010, 78172, 434265]
