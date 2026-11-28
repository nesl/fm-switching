SS s4 own-control harm scoring Sat Nov 28 12:37:32 AM PST 2026. harm = control MINUS outage (positive = outage hurt; negative = outage cell better). seed 7, 2000 reps, strict (CI excludes 0 = unrounded interval strictly one side), bounds 3 dp. NO control exists for StreamScout s5 or Mooncake s5 (their 'control' columns in baseline_out/out_*_5_* are the outage cell itself; not harm).

##### StreamScout s4 netwin_b (positive controls etc.), outage=...out-k14-d188_evid-t4075_link, control=streamscout_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30
== netwin streamscout_4ctl  outage=streamscout_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link  control=streamscout_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30  t0=407.5 d=188.0 R=595.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 59 (committed robot_headline 0.208481 x n 283 = 59.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 237 (committed 237); within_L(outcomes) 237; dashcam within(1.0) 7827 vs within_L 7827 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 69 (headline 0.243816 x 283); classifier agree 283 of 283; SS on_time 237 (committed 237) within_L 237; dashcam within(1.0) 7836 vs within_L 7836
  same opportunity ids in both cells: robot 283/283, SS 237/237
same-opportunity-id check: robot 283/283 SS 237/237 (line 5 above); classifier==committed cbd 283/283 in control (cbd 59 = committed 0.208481x283) and outage (cbd 69)
Control cbd 59 = cloud 59 + device 0 per H100 report: see cell.json check below
control robot rows 283 cbd 59 cloud on-time 283 cbd via cloud-source 59 cbd via non-cloud 0

##### HARM per arm at s4 (single group pool3.py --a, clusters (seed,question)/(seed,block))
=== streamscout
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 24 out 24 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 797 out 797 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 6 out 6 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 26 out 26 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 237 out 237 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 7827 out 7836 harm -9 CI[-27,+5] UNR[-27.000,5.000] draws<0=1696 =0=61 >0=243 clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 59 out 69 harm -10 CI[-32,+8] UNR[-32.000,8.000] draws<0=1686 =0=51 >0=263 clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 283 out 243 harm +40 CI[+20,+63] UNR[20.000,63.000] draws<0=0 =0=0 >0=2000 clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 60 out 60 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1984 out 1984 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 17 out 17 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 67 out 67 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 12 out 12 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 386 out 386 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 3 out 3 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 12 out 12 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=4
=== mooncake
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 22 out 22 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 735 out 716 harm +19 CI[-9,+36] UNR[-9.000,36.000] draws<0=75 =0=0 >0=1925 clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 18 out 17 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=625 >0=1375 clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 9 out 8 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=702 >0=1298 clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 211 out 211 harm +0 CI[-3,+3] UNR[-3.000,3.000] draws<0=697 =0=628 >0=675 clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 6656 out 6652 harm +4 CI[-213,+187] UNR[-213.000,187.000] draws<0=912 =0=5 >0=1083 clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 111 out 108 harm +3 CI[+0,+7] UNR[0.000,7.000] draws<0=0 =0=103 >0=1897 clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 53 out 43 harm +10 CI[+2,+22] UNR[2.000,22.000] draws<0=0 =0=5 >0=1995 clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 52 out 52 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1747 out 1696 harm +51 CI[+3,+116] UNR[3.000,116.000] draws<0=25 =0=4 >0=1971 clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 38 out 37 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=703 >0=1297 clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 19 out 17 harm +2 CI[+0,+5] UNR[0.000,5.000] draws<0=0 =0=224 >0=1776 clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 12 out 12 harm +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 386 out 364 harm +22 CI[+0,+50] UNR[0.000,50.000] draws<0=0 =0=201 >0=1799 clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 11 out 10 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=614 >0=1386 clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 4 out 3 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=624 >0=1376 clusters=4
=== rung3
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 21 out 21 harm +0 CI[-5,+5] UNR[-5.000,5.000] draws<0=850 =0=333 >0=817 clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 588 out 563 harm +25 CI[-42,+87] UNR[-42.000,87.000] draws<0=299 =0=0 >0=1701 clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 19 out 17 harm +2 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=625 >0=1375 clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 22 out 20 harm +2 CI[-2,+7] UNR[-2.000,7.000] draws<0=301 =0=285 >0=1414 clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 163 out 168 harm -5 CI[-21,+11] UNR[-21.000,11.000] draws<0=1427 =0=81 >0=492 clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 3748 out 4518 harm -770 CI[-1567,-49] UNR[-1567.000,-49.000] draws<0=1965 =0=0 >0=35 clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 131 out 123 harm +8 CI[-5,+24] UNR[-5.000,24.000] draws<0=236 =0=81 >0=1683 clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 124 out 111 harm +13 CI[-9,+38] UNR[-9.000,38.000] draws<0=227 =0=39 >0=1734 clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 46 out 40 harm +6 CI[-1,+13] UNR[-1.000,13.000] draws<0=69 =0=58 >0=1873 clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1080 out 1149 harm -69 CI[-260,+89] UNR[-260.000,89.000] draws<0=1472 =0=3 >0=525 clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 39 out 35 harm +4 CI[+0,+10] UNR[0.000,10.000] draws<0=0 =0=224 >0=1776 clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 35 out 41 harm -6 CI[-15,+4] UNR[-15.000,4.000] draws<0=1723 =0=79 >0=198 clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 10 out 9 harm +1 CI[-3,+5] UNR[-3.000,5.000] draws<0=454 =0=329 >0=1217 clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 263 out 224 harm +39 CI[-50,+125] UNR[-50.000,125.000] draws<0=361 =0=0 >0=1639 clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 10 out 8 harm +2 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=614 >0=1386 clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 8 out 6 harm +2 CI[-2,+6] UNR[-2.000,6.000] draws<0=273 =0=237 >0=1490 clusters=4
=== eager
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 24 out 16 harm +8 CI[+4,+13] UNR[4.000,13.000] draws<0=0 =0=0 >0=2000 clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 692 out 268 harm +424 CI[+87,+747] UNR[87.000,747.000] draws<0=0 =0=0 >0=2000 clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 20 out 19 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=625 >0=1375 clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 25 out 17 harm +8 CI[+1,+18] UNR[1.000,18.000] draws<0=0 =0=37 >0=1963 clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 199 out 169 harm +30 CI[+14,+46] UNR[14.000,46.000] draws<0=0 =0=0 >0=2000 clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 5343 out 4344 harm +999 CI[+261,+1791] UNR[261.000,1791.000] draws<0=7 =0=0 >0=1993 clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 154 out 134 harm +20 CI[+4,+37] UNR[4.000,37.000] draws<0=12 =0=7 >0=1981 clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 181 out 123 harm +58 CI[+34,+85] UNR[34.000,85.000] draws<0=0 =0=0 >0=2000 clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 53 out 36 harm +17 CI[+8,+26] UNR[8.000,26.000] draws<0=0 =0=1 >0=1999 clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1465 out 668 harm +797 CI[+475,+1135] UNR[475.000,1135.000] draws<0=0 =0=0 >0=2000 clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 38 out 37 harm +1 CI[-5,+5] UNR[-5.000,5.000] draws<0=575 =0=274 >0=1151 clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 52 out 37 harm +15 CI[+2,+29] UNR[2.000,29.000] draws<0=17 =0=9 >0=1974 clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 12 out 6 harm +6 CI[+3,+9] UNR[3.000,9.000] draws<0=0 =0=0 >0=2000 clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 318 out 53 harm +265 CI[+189,+350] UNR[189.000,350.000] draws<0=0 =0=0 >0=2000 clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 11 out 10 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=614 >0=1386 clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 11 out 7 harm +4 CI[+1,+7] UNR[1.000,7.000] draws<0=0 =0=3 >0=1997 clusters=4
=== F0
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 24 out 21 harm +3 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=82 >0=1918 clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 692 out 566 harm +126 CI[+84,+207] UNR[84.000,207.000] draws<0=0 =0=0 >0=2000 clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 20 out 19 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=625 >0=1375 clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 25 out 21 harm +4 CI[+1,+8] UNR[1.000,8.000] draws<0=0 =0=37 >0=1963 clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 199 out 176 harm +23 CI[+10,+36] UNR[10.000,36.000] draws<0=0 =0=0 >0=2000 clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 5343 out 4561 harm +782 CI[+132,+1442] UNR[132.000,1442.000] draws<0=16 =0=0 >0=1984 clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 154 out 134 harm +20 CI[+4,+38] UNR[4.000,38.000] draws<0=12 =0=7 >0=1981 clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 181 out 133 harm +48 CI[+26,+71] UNR[26.000,71.000] draws<0=0 =0=0 >0=2000 clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 53 out 46 harm +7 CI[+1,+14] UNR[1.000,14.000] draws<0=14 =0=18 >0=1968 clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1465 out 1054 harm +411 CI[+195,+632] UNR[195.000,632.000] draws<0=0 =0=0 >0=2000 clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 38 out 38 harm +0 CI[-5,+6] UNR[-5.000,6.000] draws<0=951 =0=270 >0=779 clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 52 out 41 harm +11 CI[+2,+20] UNR[2.000,20.000] draws<0=10 =0=10 >0=1980 clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 12 out 9 harm +3 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=62 >0=1938 clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 318 out 220 harm +98 CI[+26,+166] UNR[26.000,166.000] draws<0=9 =0=1 >0=1990 clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 11 out 10 harm +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=614 >0=1386 clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 11 out 7 harm +4 CI[+1,+7] UNR[1.000,7.000] draws<0=0 =0=3 >0=1997 clusters=4
=== cand-tl
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 24 out 21 harm +3 CI[+0,+7] UNR[0.000,7.000] draws<0=0 =0=78 >0=1922 clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 692 out 556 harm +136 CI[+81,+198] UNR[81.000,198.000] draws<0=0 =0=0 >0=2000 clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 20 out 17 harm +3 CI[+0,+9] UNR[0.000,9.000] draws<0=0 =0=625 >0=1375 clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 25 out 21 harm +4 CI[+0,+10] UNR[0.000,10.000] draws<0=0 =0=201 >0=1799 clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 199 out 191 harm +8 CI[-5,+21] UNR[-5.000,21.000] draws<0=225 =0=63 >0=1712 clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 5343 out 5066 harm +277 CI[-209,+816] UNR[-209.000,816.000] draws<0=290 =0=2 >0=1708 clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 154 out 133 harm +21 CI[+5,+40] UNR[5.000,40.000] draws<0=8 =0=6 >0=1986 clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 181 out 149 harm +32 CI[+5,+59] UNR[5.000,59.000] draws<0=18 =0=5 >0=1977 clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 53 out 49 harm +4 CI[-3,+11] UNR[-3.000,11.000] draws<0=192 =0=117 >0=1691 clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1465 out 1187 harm +278 CI[+104,+433] UNR[104.000,433.000] draws<0=0 =0=0 >0=2000 clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 38 out 35 harm +3 CI[-3,+10] UNR[-3.000,10.000] draws<0=331 =0=175 >0=1494 clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 52 out 50 harm +2 CI[-10,+14] UNR[-10.000,14.000] draws<0=623 =0=139 >0=1238 clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 12 out 9 harm +3 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=54 >0=1946 clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 318 out 225 harm +93 CI[+18,+171] UNR[18.000,171.000] draws<0=12 =0=2 >0=1986 clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 11 out 8 harm +3 CI[+0,+9] UNR[0.000,9.000] draws<0=0 =0=614 >0=1386 clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 11 out 7 harm +4 CI[+0,+9] UNR[0.000,9.000] draws<0=0 =0=118 >0=1882 clusters=4

##### WHOLE-RUN COVEX minus StreamScout, outage cells, abs3 with NEW ss json (B file differs only by control; outage column unchanged)
== f0
  robot cbd            nA=283 nB=283 | outage A 134 B 69 | A-B +65 CI[+28,+110] UNR[28.000,110.000] draws<0=0 =0=0 >0=2000 clusters=47 | own control A 154 B 59 (A-B +95)
  robot cloud on-time  nA=283 nB=283 | outage A 133 B 243 | A-B -110 CI[-142,-80] UNR[-142.000,-80.000] draws<0=2000 =0=0 >0=0 clusters=47 | own control A 181 B 283 (A-B -102)
  SS on-time (scorer)  nA=237 nB=237 | outage A 176 B 237 | A-B -61 CI[-74,-47] UNR[-74.000,-47.000] draws<0=2000 =0=0 >0=0 clusters=237 | own control A 199 B 237 (A-B -38)
  dashcam within_L     nA=7850 nB=7850 | outage A 4561 B 7836 | A-B -3275 CI[-4342,-2292] UNR[-4342.000,-2292.000] draws<0=2000 =0=0 >0=0 clusters=20 | own control A 5343 B 7827 (A-B -2484)
  A seed 4 netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 ss_ctrl/out_ss4ctl_w120.json: robot[120] 6/26; robot[whole] 59/283; cloud[120] 26/26; cloud[whole] 283/283; SS[120] 24/24; SS[whole] 237/237; dashcam[120] 797/797; dashcam[whole] 7827/7850
== a4
  robot cbd            nA=283 nB=283 | outage A 133 B 69 | A-B +64 CI[+23,+110] UNR[23.000,110.000] draws<0=1 =0=0 >0=1999 clusters=47 | own control A 154 B 59 (A-B +95)
  robot cloud on-time  nA=283 nB=283 | outage A 149 B 243 | A-B -94 CI[-127,-63] UNR[-127.000,-63.000] draws<0=2000 =0=0 >0=0 clusters=47 | own control A 181 B 283 (A-B -102)
  SS on-time (scorer)  nA=237 nB=237 | outage A 191 B 237 | A-B -46 CI[-58,-34] UNR[-58.000,-34.000] draws<0=2000 =0=0 >0=0 clusters=237 | own control A 199 B 237 (A-B -38)
  dashcam within_L     nA=7850 nB=7850 | outage A 5066 B 7836 | A-B -2770 CI[-3682,-1921] UNR[-3682.000,-1921.000] draws<0=2000 =0=0 >0=0 clusters=20 | own control A 5343 B 7827 (A-B -2484)
  A seed 4 netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 ss_ctrl/out_ss4ctl_w120.json: robot[120] 6/26; robot[whole] 59/283; cloud[120] 26/26; cloud[whole] 283/283; SS[120] 24/24; SS[whole] 237/237; dashcam[120] 797/797; dashcam[whole] 7827/7850
OLD (baseline_out/out.txt) f0 whole robot cbd: A-B +65 CI[+28,+110]
