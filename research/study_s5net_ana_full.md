################ SEEDS: 4
---- (a) ABS F0 minus rung3 (outage cells)
ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=../netwin/out_f0_s4_t4075_w120.json | B=../netwin/out_rung3_s4_t4075_w120.json
seeds in A/B: [4] / [4]
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 17 | A-B +2 CI[+0,+6] clusters=7 | own control A 20 B 19 (A-B +1)
  robot cloud on-time  nA=26 nB=26 | outage A 21 B 20 | A-B +1 CI[-2,+6] clusters=7 | own control A 25 B 22 (A-B +3)
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 21 | A-B +0 CI[+0,+0] clusters=24 | own control A 24 B 21 (A-B +3)
  dashcam within_L     nA=797 nB=797 | outage A 566 B 563 | A-B +3 CI[-12,+21] clusters=3 | own control A 692 B 588 (A-B +104)
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 10 B 8 | A-B +2 CI[+0,+6] clusters=4 | own control A 11 B 10 (A-B +1)
  robot cloud on-time  nA=12 nB=12 | outage A 7 B 6 | A-B +1 CI[-3,+6] clusters=4 | own control A 11 B 8 (A-B +3)
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 9 | A-B +0 CI[+0,+0] clusters=12 | own control A 12 B 10 (A-B +2)
  dashcam within_L     nA=386 nB=386 | outage A 220 B 224 | A-B -4 CI[-25,+21] clusters=7 | own control A 318 B 263 (A-B +55)
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 38 B 35 | A-B +3 CI[-2,+9] clusters=15 | own control A 38 B 39 (A-B -1)
  robot cloud on-time  nA=67 nB=67 | outage A 41 B 41 | A-B +0 CI[-11,+10] clusters=15 | own control A 52 B 35 (A-B +17)
  SS on-time (scorer)  nA=60 nB=60 | outage A 46 B 40 | A-B +6 CI[-1,+13] clusters=60 | own control A 53 B 46 (A-B +7)
  dashcam within_L     nA=1984 nB=1984 | outage A 1054 B 1149 | A-B -95 CI[-257,+10] clusters=6 | own control A 1465 B 1080 (A-B +385)
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 134 B 123 | A-B +11 CI[-1,+24] clusters=47 | own control A 154 B 131 (A-B +23)
  robot cloud on-time  nA=283 nB=283 | outage A 133 B 111 | A-B +22 CI[+3,+40] clusters=47 | own control A 181 B 124 (A-B +57)
  SS on-time (scorer)  nA=237 nB=237 | outage A 176 B 168 | A-B +8 CI[-4,+20] clusters=237 | own control A 199 B 163 (A-B +36)
  dashcam within_L     nA=7850 nB=7850 | outage A 4561 B 4518 | A-B +43 CI[-196,+301] clusters=20 | own control A 5343 B 3748 (A-B +1595)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 ../netwin/out_rung3_s4_t4075_w120.json: robot[120] 19/26; robot[whole] 131/283; cloud[120] 22/26; cloud[whole] 124/283; SS[120] 21/24; SS[whole] 163/237; dashcam[120] 588/797; dashcam[whole] 3748/7850
---- (b) HARM F0 vs eager (A=F0,B=eager)
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -3 (n=37,cl=37) harmB -3 (n=37,cl=37) A-B +0 CI[-4,+5]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -3 (n=37,cl=37) harmB -3 (n=37,cl=37) A-B +0 CI[-5,+5]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -202 (n=1251,cl=4) harmB -202 (n=1251,cl=4) A-B +0 CI[-169,+177]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +9 (n=40,cl=13) harmB +9 (n=40,cl=13) A-B +0 CI[-14,+14]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +21 (n=40,cl=13) harmB +21 (n=40,cl=13) A-B +0 CI[-16,+17]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +3 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -5 CI[-10,+0]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +3 (n=24,cl=24) harmB +7 (n=24,cl=24) A-B -4 CI[-9,+1]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +126 (n=797,cl=3) harmB +424 (n=797,cl=3) A-B -298 CI[-620,+38]
== RULE fixed [R,R+120]|robot cbd                                      harmA +1 (n=26,cl=7) harmB +1 (n=26,cl=7) A-B +0 CI[-2,+3]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +4 (n=26,cl=7) harmB +8 (n=26,cl=7) A-B -4 CI[-14,+5]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +23 (n=237,cl=237) harmB +30 (n=237,cl=237) A-B -7 CI[-27,+13]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA +23 (n=237,cl=237) harmB +30 (n=237,cl=237) A-B -7 CI[-27,+14]
== WHOLE RUN (beside)|dashcam within_L                                 harmA +782 (n=7850,cl=20) harmB +999 (n=7850,cl=20) A-B -217 CI[-1182,+743]
== WHOLE RUN (beside)|robot cbd                                        harmA +20 (n=283,cl=47) harmB +20 (n=283,cl=47) A-B +0 CI[-23,+25]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +48 (n=283,cl=47) harmB +58 (n=283,cl=47) A-B -10 CI[-44,+24]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +7 (n=60,cl=60) harmB +17 (n=60,cl=60) A-B -10 CI[-21,+1]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +8 (n=60,cl=60) harmB +17 (n=60,cl=60) A-B -9 CI[-20,+2]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +411 (n=1984,cl=6) harmB +797 (n=1984,cl=6) A-B -386 CI[-782,+15]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +0 (n=67,cl=15) harmB +1 (n=67,cl=15) A-B -1 CI[-8,+7]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +11 (n=67,cl=15) harmB +15 (n=67,cl=15) A-B -4 CI[-21,+12]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +6 (n=12,cl=12) A-B -3 CI[-7,+2]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +3 (n=12,cl=12) harmB +5 (n=12,cl=12) A-B -2 CI[-6,+3]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +98 (n=386,cl=7) harmB +265 (n=386,cl=7) A-B -167 CI[-277,-66]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +1 (n=12,cl=4) harmB +1 (n=12,cl=4) A-B +0 CI[-2,+2]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +4 (n=12,cl=4) harmB +4 (n=12,cl=4) A-B +0 CI[-4,+4]
---- robustness HARM F0 vs rung3
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -3 (n=37,cl=37) harmB -13 (n=37,cl=37) A-B +10 CI[+3,+17]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -3 (n=37,cl=37) harmB -13 (n=37,cl=37) A-B +10 CI[+3,+16]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -202 (n=1251,cl=4) harmB -659 (n=1251,cl=4) A-B +457 CI[+133,+744]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +9 (n=40,cl=13) harmB +4 (n=40,cl=13) A-B +5 CI[-7,+18]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +21 (n=40,cl=13) harmB +14 (n=40,cl=13) A-B +7 CI[-8,+23]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +3 (n=24,cl=24) harmB +0 (n=24,cl=24) A-B +3 CI[-3,+9]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +3 (n=24,cl=24) harmB +0 (n=24,cl=24) A-B +3 CI[-2,+8]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +126 (n=797,cl=3) harmB +25 (n=797,cl=3) A-B +101 CI[+17,+185]
== RULE fixed [R,R+120]|robot cbd                                      harmA +1 (n=26,cl=7) harmB +2 (n=26,cl=7) A-B -1 CI[-6,+3]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +4 (n=26,cl=7) harmB +2 (n=26,cl=7) A-B +2 CI[-3,+8]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +23 (n=237,cl=237) harmB -5 (n=237,cl=237) A-B +28 CI[+9,+49]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA +23 (n=237,cl=237) harmB -8 (n=237,cl=237) A-B +31 CI[+12,+51]
== WHOLE RUN (beside)|dashcam within_L                                 harmA +782 (n=7850,cl=20) harmB -770 (n=7850,cl=20) A-B +1552 CI[+595,+2578]
== WHOLE RUN (beside)|robot cbd                                        harmA +20 (n=283,cl=47) harmB +8 (n=283,cl=47) A-B +12 CI[-10,+34]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +48 (n=283,cl=47) harmB +13 (n=283,cl=47) A-B +35 CI[+4,+68]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +7 (n=60,cl=60) harmB +6 (n=60,cl=60) A-B +1 CI[-8,+10]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +8 (n=60,cl=60) harmB +4 (n=60,cl=60) A-B +4 CI[-5,+12]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +411 (n=1984,cl=6) harmB -69 (n=1984,cl=6) A-B +480 CI[+200,+776]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +0 (n=67,cl=15) harmB +4 (n=67,cl=15) A-B -4 CI[-12,+3]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +11 (n=67,cl=15) harmB -6 (n=67,cl=15) A-B +17 CI[+4,+30]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +1 (n=12,cl=12) A-B +2 CI[-3,+7]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +3 (n=12,cl=12) harmB +0 (n=12,cl=12) A-B +3 CI[-2,+8]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +98 (n=386,cl=7) harmB +39 (n=386,cl=7) A-B +59 CI[-55,+175]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +1 (n=12,cl=4) harmB +2 (n=12,cl=4) A-B -1 CI[-5,+2]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +4 (n=12,cl=4) harmB +2 (n=12,cl=4) A-B +2 CI[-3,+7]
---- eager pooled harm
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   n=37 ctl 34 out 37 harm -3 CI[-6,+0] clusters=37
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 n=37 ctl 34 out 37 harm -3 CI[-6,+0] clusters=37
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      n=1251 ctl 1049 out 1251 harm -202 CI[-342,-80] clusters=4
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             n=40 ctl 25 out 16 harm +9 CI[+0,+20] clusters=13
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   n=40 ctl 21 out 0 harm +21 CI[+10,+34] clusters=13
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 24 out 16 harm +8 CI[+4,+13] clusters=24
== RULE fixed [R,R+120]|SS within_L (outcome)                          n=24 ctl 24 out 17 harm +7 CI[+3,+12] clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 692 out 268 harm +424 CI[+87,+747] clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 20 out 19 harm +1 CI[+0,+3] clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 25 out 17 harm +8 CI[+1,+18] clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 199 out 169 harm +30 CI[+14,+46] clusters=237
== WHOLE RUN (beside)|SS within_L (outcome)                            n=237 ctl 200 out 170 harm +30 CI[+14,+46] clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 5343 out 4344 harm +999 CI[+261,+1791] clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 154 out 134 harm +20 CI[+4,+37] clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 181 out 123 harm +58 CI[+34,+85] clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 53 out 36 harm +17 CI[+8,+26] clusters=60
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   n=60 ctl 54 out 37 harm +17 CI[+8,+26] clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1465 out 668 harm +797 CI[+475,+1135] clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 38 out 37 harm +1 CI[-5,+5] clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 52 out 37 harm +15 CI[+2,+29] clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 12 out 6 harm +6 CI[+3,+9] clusters=12
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    n=12 ctl 12 out 7 harm +5 CI[+2,+8] clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 318 out 53 harm +265 CI[+189,+350] clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 11 out 10 harm +1 CI[+0,+3] clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 11 out 7 harm +4 CI[+1,+7] clusters=4
---- rung3 pooled harm
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   n=37 ctl 24 out 37 harm -13 CI[-19,-7] clusters=37
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 n=37 ctl 24 out 37 harm -13 CI[-19,-8] clusters=37
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      n=1251 ctl 592 out 1251 harm -659 CI[-916,-402] clusters=4
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             n=40 ctl 20 out 16 harm +4 CI[-3,+12] clusters=13
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   n=40 ctl 14 out 0 harm +14 CI[+6,+23] clusters=13
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 21 out 21 harm +0 CI[-5,+5] clusters=24
== RULE fixed [R,R+120]|SS within_L (outcome)                          n=24 ctl 22 out 22 harm +0 CI[-4,+4] clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=797 ctl 588 out 563 harm +25 CI[-42,+87] clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 19 out 17 harm +2 CI[+0,+6] clusters=7
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 22 out 20 harm +2 CI[-2,+7] clusters=7
== WHOLE RUN (beside)|SS on-time (scorer)                              n=237 ctl 163 out 168 harm -5 CI[-21,+11] clusters=237
== WHOLE RUN (beside)|SS within_L (outcome)                            n=237 ctl 165 out 173 harm -8 CI[-23,+6] clusters=237
== WHOLE RUN (beside)|dashcam within_L                                 n=7850 ctl 3748 out 4518 harm -770 CI[-1567,-49] clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=283 ctl 131 out 123 harm +8 CI[-5,+24] clusters=47
== WHOLE RUN (beside)|robot cloud on-time                              n=283 ctl 124 out 111 harm +13 CI[-9,+38] clusters=47
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=60 ctl 46 out 40 harm +6 CI[-1,+13] clusters=60
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   n=60 ctl 47 out 43 harm +4 CI[-2,+10] clusters=60
== sensitivity fixed [R,R+300]|dashcam within_L                        n=1984 ctl 1080 out 1149 harm -69 CI[-260,+89] clusters=6
== sensitivity fixed [R,R+300]|robot cbd                               n=67 ctl 39 out 35 harm +4 CI[+0,+10] clusters=15
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=67 ctl 35 out 41 harm -6 CI[-15,+4] clusters=15
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 10 out 9 harm +1 CI[-3,+5] clusters=12
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    n=12 ctl 10 out 10 harm +0 CI[-4,+4] clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=386 ctl 263 out 224 harm +39 CI[-50,+125] clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=12 ctl 10 out 8 harm +2 CI[+0,+6] clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=12 ctl 8 out 6 harm +2 CI[-2,+6] clusters=4
---- (B) SYNC ABS F0 minus A
ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=../netwin/out_f0_s4_t4075_w120.json | B=../netwin/out_a4_s4_t4075_w120.json
seeds in A/B: [4] / [4]
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 17 | A-B +2 CI[+0,+6] clusters=7 | own control A 20 B 20 (A-B +0)
  robot cloud on-time  nA=26 nB=26 | outage A 21 B 21 | A-B +0 CI[-4,+5] clusters=7 | own control A 25 B 25 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 21 | A-B +0 CI[-3,+3] clusters=24 | own control A 24 B 24 (A-B +0)
  dashcam within_L     nA=797 nB=797 | outage A 566 B 556 | A-B +10 CI[-9,+45] clusters=3 | own control A 692 B 692 (A-B +0)
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 10 B 8 | A-B +2 CI[+0,+6] clusters=4 | own control A 11 B 11 (A-B +0)
  robot cloud on-time  nA=12 nB=12 | outage A 7 B 7 | A-B +0 CI[-4,+5] clusters=4 | own control A 11 B 11 (A-B +0)
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 9 | A-B +0 CI[-3,+3] clusters=12 | own control A 12 B 12 (A-B +0)
  dashcam within_L     nA=386 nB=386 | outage A 220 B 225 | A-B -5 CI[-29,+24] clusters=7 | own control A 318 B 318 (A-B +0)
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 38 B 35 | A-B +3 CI[-2,+9] clusters=15 | own control A 38 B 38 (A-B +0)
  robot cloud on-time  nA=67 nB=67 | outage A 41 B 50 | A-B -9 CI[-22,+1] clusters=15 | own control A 52 B 52 (A-B +0)
  SS on-time (scorer)  nA=60 nB=60 | outage A 46 B 49 | A-B -3 CI[-9,+3] clusters=60 | own control A 53 B 53 (A-B +0)
  dashcam within_L     nA=1984 nB=1984 | outage A 1054 B 1187 | A-B -133 CI[-232,-40] clusters=6 | own control A 1465 B 1465 (A-B +0)
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 134 B 133 | A-B +1 CI[-13,+17] clusters=47 | own control A 154 B 154 (A-B +0)
  robot cloud on-time  nA=283 nB=283 | outage A 133 B 149 | A-B -16 CI[-38,+3] clusters=47 | own control A 181 B 181 (A-B +0)
  SS on-time (scorer)  nA=237 nB=237 | outage A 176 B 191 | A-B -15 CI[-28,-2] clusters=237 | own control A 199 B 199 (A-B +0)
  dashcam within_L     nA=7850 nB=7850 | outage A 4561 B 5066 | A-B -505 CI[-836,-193] clusters=20 | own control A 5343 B 5343 (A-B +0)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 ../netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
################ SEEDS: 5
---- (a) ABS F0 minus rung3 (outage cells)
ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=out_f0_s5_t8805_w120.json | B=out_rung3_s5_t8805_w120.json
seeds in A/B: [5] / [5]
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 22 | A-B -3 CI[-11,+4] clusters=6 | own control A 21 B 23 (A-B -2)
  robot cloud on-time  nA=26 nB=26 | outage A 12 B 22 | A-B -10 CI[-16,-4] clusters=6 | own control A 21 B 24 (A-B -3)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 21 | A-B -6 CI[-11,-1] clusters=24 | own control A 21 B 24 (A-B -3)
  dashcam within_L     nA=790 nB=790 | outage A 180 B 542 | A-B -362 CI[-597,-3] clusters=3 | own control A 326 B 579 (A-B -253)
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 6 B 9 | A-B -3 CI[-6,+0] clusters=4 | own control A 8 B 10 (A-B -2)
  robot cloud on-time  nA=10 nB=10 | outage A 6 B 8 | A-B -2 CI[-6,+2] clusters=4 | own control A 7 B 10 (A-B -3)
  SS on-time (scorer)  nA=12 nB=12 | outage A 6 B 9 | A-B -3 CI[-7,+1] clusters=12 | own control A 9 B 12 (A-B -3)
  dashcam within_L     nA=393 nB=393 | outage A 121 B 207 | A-B -86 CI[-200,+4] clusters=7 | own control A 100 B 275 (A-B -175)
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 23 | A-B -4 CI[-14,+4] clusters=6 | own control A 22 B 23 (A-B -1)
  robot cloud on-time  nA=28 nB=28 | outage A 12 B 23 | A-B -11 CI[-18,-4] clusters=6 | own control A 22 B 24 (A-B -2)
  SS on-time (scorer)  nA=26 nB=26 | outage A 15 B 23 | A-B -8 CI[-13,-3] clusters=26 | own control A 21 B 24 (A-B -3)
  dashcam within_L     nA=865 nB=865 | outage A 225 B 568 | A-B -343 CI[-540,-3] clusters=3 | own control A 339 B 591 (A-B -252)
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 100 | A-B +5 CI[-10,+20] clusters=40 | own control A 109 B 106 (A-B +3)
  robot cloud on-time  nA=222 nB=222 | outage A 122 B 131 | A-B -9 CI[-48,+22] clusters=40 | own control A 148 B 145 (A-B +3)
  SS on-time (scorer)  nA=240 nB=240 | outage A 216 B 191 | A-B +25 CI[+10,+40] clusters=240 | own control A 211 B 187 (A-B +24)
  dashcam within_L     nA=7862 nB=7862 | outage A 5732 B 4916 | A-B +816 CI[-86,+1744] clusters=20 | own control A 5025 B 4489 (A-B +536)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_rung3_s5_t8805_w120.json: robot[120] 23/26; robot[whole] 106/222; cloud[120] 24/26; cloud[whole] 145/222; SS[120] 24/24; SS[whole] 187/240; dashcam[120] 579/790; dashcam[whole] 4489/7862
---- (b) HARM F0 vs eager (A=F0,B=eager)
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -5 (n=38,cl=38) harmB -5 (n=38,cl=38) A-B +0 CI[-6,+6]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -4 (n=38,cl=38) harmB -4 (n=38,cl=38) A-B +0 CI[-5,+5]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -472 (n=1249,cl=4) harmB -484 (n=1249,cl=4) A-B +12 CI[-257,+246]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +3 (n=29,cl=11) harmB +3 (n=29,cl=11) A-B +0 CI[-12,+13]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +21 (n=29,cl=11) harmB +21 (n=29,cl=11) A-B +0 CI[-19,+19]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +6 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -2 CI[-9,+5]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +6 (n=24,cl=24) harmB +7 (n=24,cl=24) A-B -1 CI[-8,+5]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +146 (n=790,cl=3) harmB +124 (n=790,cl=3) A-B +22 CI[-232,+276]
== RULE fixed [R,R+120]|robot cbd                                      harmA +2 (n=26,cl=6) harmB +1 (n=26,cl=6) A-B +1 CI[-8,+10]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +9 (n=26,cl=6) harmB +9 (n=26,cl=6) A-B +0 CI[-6,+6]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -5 (n=240,cl=240) harmB +6 (n=240,cl=240) A-B -11 CI[-28,+6]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA -5 (n=240,cl=240) harmB +6 (n=240,cl=240) A-B -11 CI[-27,+5]
== WHOLE RUN (beside)|dashcam within_L                                 harmA -707 (n=7862,cl=20) harmB -326 (n=7862,cl=20) A-B -381 CI[-1398,+721]
== WHOLE RUN (beside)|robot cbd                                        harmA +4 (n=222,cl=40) harmB +7 (n=222,cl=40) A-B -3 CI[-24,+19]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +26 (n=222,cl=40) harmB +27 (n=222,cl=40) A-B -1 CI[-38,+46]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +6 (n=26,cl=26) harmB +7 (n=26,cl=26) A-B -1 CI[-8,+7]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +6 (n=26,cl=26) harmB +6 (n=26,cl=26) A-B +0 CI[-7,+7]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +114 (n=865,cl=3) harmB +91 (n=865,cl=3) A-B +23 CI[-163,+212]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=28,cl=6) harmB +1 (n=28,cl=6) A-B +2 CI[-7,+11]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +10 (n=28,cl=6) harmB +9 (n=28,cl=6) A-B +1 CI[-4,+6]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +2 (n=12,cl=12) A-B +1 CI[-4,+6]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +3 (n=12,cl=12) harmB +2 (n=12,cl=12) A-B +1 CI[-4,+6]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA -21 (n=393,cl=7) harmB +24 (n=393,cl=7) A-B -45 CI[-152,+66]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +2 (n=10,cl=4) harmB +2 (n=10,cl=4) A-B +0 CI[-5,+7]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +1 (n=10,cl=4) harmB +1 (n=10,cl=4) A-B +0 CI[-6,+8]
---- robustness HARM F0 vs rung3
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -5 (n=38,cl=38) harmB -7 (n=38,cl=38) A-B +2 CI[-5,+9]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -4 (n=38,cl=38) harmB -6 (n=38,cl=38) A-B +2 CI[-5,+9]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -472 (n=1249,cl=4) harmB -421 (n=1249,cl=4) A-B -51 CI[-385,+312]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +3 (n=29,cl=11) harmB +2 (n=29,cl=11) A-B +1 CI[-10,+13]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +21 (n=29,cl=11) harmB +12 (n=29,cl=11) A-B +9 CI[-8,+26]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +6 (n=24,cl=24) harmB +3 (n=24,cl=24) A-B +3 CI[-2,+8]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +6 (n=24,cl=24) harmB +3 (n=24,cl=24) A-B +3 CI[-2,+8]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +146 (n=790,cl=3) harmB +37 (n=790,cl=3) A-B +109 CI[-121,+339]
== RULE fixed [R,R+120]|robot cbd                                      harmA +2 (n=26,cl=6) harmB +1 (n=26,cl=6) A-B +1 CI[-6,+9]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +9 (n=26,cl=6) harmB +2 (n=26,cl=6) A-B +7 CI[+2,+12]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -5 (n=240,cl=240) harmB -4 (n=240,cl=240) A-B -1 CI[-17,+15]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA -5 (n=240,cl=240) harmB -2 (n=240,cl=240) A-B -3 CI[-20,+14]
== WHOLE RUN (beside)|dashcam within_L                                 harmA -707 (n=7862,cl=20) harmB -427 (n=7862,cl=20) A-B -280 CI[-1115,+546]
== WHOLE RUN (beside)|robot cbd                                        harmA +4 (n=222,cl=40) harmB +6 (n=222,cl=40) A-B -2 CI[-22,+19]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +26 (n=222,cl=40) harmB +14 (n=222,cl=40) A-B +12 CI[-16,+41]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +6 (n=26,cl=26) harmB +1 (n=26,cl=26) A-B +5 CI[-1,+11]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +6 (n=26,cl=26) harmB +1 (n=26,cl=26) A-B +5 CI[-1,+11]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +114 (n=865,cl=3) harmB +23 (n=865,cl=3) A-B +91 CI[-121,+303]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=28,cl=6) harmB +0 (n=28,cl=6) A-B +3 CI[-5,+11]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +10 (n=28,cl=6) harmB +1 (n=28,cl=6) A-B +9 CI[+5,+14]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +3 (n=12,cl=12) A-B +0 CI[-4,+4]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +3 (n=12,cl=12) harmB +3 (n=12,cl=12) A-B +0 CI[-4,+4]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA -21 (n=393,cl=7) harmB +68 (n=393,cl=7) A-B -89 CI[-257,+74]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +2 (n=10,cl=4) harmB +1 (n=10,cl=4) A-B +1 CI[-4,+8]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +1 (n=10,cl=4) harmB +2 (n=10,cl=4) A-B -1 CI[-7,+6]
---- eager pooled harm
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   n=38 ctl 33 out 38 harm -5 CI[-9,-1] clusters=38
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 n=38 ctl 34 out 38 harm -4 CI[-8,-1] clusters=38
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      n=1249 ctl 736 out 1220 harm -484 CI[-660,-310] clusters=4
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             n=29 ctl 13 out 10 harm +3 CI[-6,+13] clusters=11
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   n=29 ctl 21 out 0 harm +21 CI[+8,+36] clusters=11
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 21 out 13 harm +8 CI[+3,+13] clusters=24
== RULE fixed [R,R+120]|SS within_L (outcome)                          n=24 ctl 21 out 14 harm +7 CI[+2,+12] clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=790 ctl 326 out 202 harm +124 CI[-45,+318] clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 21 out 20 harm +1 CI[-5,+7] clusters=6
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 21 out 12 harm +9 CI[+5,+12] clusters=6
== WHOLE RUN (beside)|SS on-time (scorer)                              n=240 ctl 211 out 205 harm +6 CI[-7,+19] clusters=240
== WHOLE RUN (beside)|SS within_L (outcome)                            n=240 ctl 213 out 207 harm +6 CI[-7,+20] clusters=240
== WHOLE RUN (beside)|dashcam within_L                                 n=7862 ctl 5025 out 5351 harm -326 CI[-1168,+477] clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=222 ctl 109 out 102 harm +7 CI[-6,+22] clusters=40
== WHOLE RUN (beside)|robot cloud on-time                              n=222 ctl 148 out 121 harm +27 CI[-11,+58] clusters=40
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=26 ctl 21 out 14 harm +7 CI[+1,+13] clusters=26
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   n=26 ctl 21 out 15 harm +6 CI[+0,+12] clusters=26
== sensitivity fixed [R,R+300]|dashcam within_L                        n=865 ctl 339 out 248 harm +91 CI[-45,+219] clusters=3
== sensitivity fixed [R,R+300]|robot cbd                               n=28 ctl 22 out 21 harm +1 CI[-5,+6] clusters=6
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=28 ctl 22 out 13 harm +9 CI[+5,+12] clusters=6
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 9 out 7 harm +2 CI[-2,+6] clusters=12
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    n=12 ctl 9 out 7 harm +2 CI[-2,+6] clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=393 ctl 100 out 76 harm +24 CI[-59,+103] clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=10 ctl 8 out 6 harm +2 CI[+0,+4] clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=10 ctl 7 out 6 harm +1 CI[-2,+4] clusters=4
---- rung3 pooled harm
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   n=38 ctl 27 out 34 harm -7 CI[-13,-1] clusters=38
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 n=38 ctl 28 out 34 harm -6 CI[-12,+0] clusters=38
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      n=1249 ctl 598 out 1019 harm -421 CI[-748,-143] clusters=4
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             n=29 ctl 12 out 10 harm +2 CI[-5,+10] clusters=11
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   n=29 ctl 12 out 0 harm +12 CI[+3,+23] clusters=11
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=24 ctl 24 out 21 harm +3 CI[+0,+7] clusters=24
== RULE fixed [R,R+120]|SS within_L (outcome)                          n=24 ctl 24 out 21 harm +3 CI[+0,+6] clusters=24
== RULE fixed [R,R+120]|dashcam within_L                               n=790 ctl 579 out 542 harm +37 CI[-81,+210] clusters=3
== RULE fixed [R,R+120]|robot cbd                                      n=26 ctl 23 out 22 harm +1 CI[+0,+3] clusters=6
== RULE fixed [R,R+120]|robot cloud on-time                            n=26 ctl 24 out 22 harm +2 CI[+0,+4] clusters=6
== WHOLE RUN (beside)|SS on-time (scorer)                              n=240 ctl 187 out 191 harm -4 CI[-17,+8] clusters=240
== WHOLE RUN (beside)|SS within_L (outcome)                            n=240 ctl 190 out 192 harm -2 CI[-14,+10] clusters=240
== WHOLE RUN (beside)|dashcam within_L                                 n=7862 ctl 4489 out 4916 harm -427 CI[-1031,+71] clusters=20
== WHOLE RUN (beside)|robot cbd                                        n=222 ctl 106 out 100 harm +6 CI[-4,+18] clusters=40
== WHOLE RUN (beside)|robot cloud on-time                              n=222 ctl 145 out 131 harm +14 CI[-1,+32] clusters=40
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=26 ctl 24 out 23 harm +1 CI[-3,+5] clusters=26
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   n=26 ctl 24 out 23 harm +1 CI[-4,+6] clusters=26
== sensitivity fixed [R,R+300]|dashcam within_L                        n=865 ctl 591 out 568 harm +23 CI[-123,+210] clusters=3
== sensitivity fixed [R,R+300]|robot cbd                               n=28 ctl 23 out 23 harm +0 CI[-3,+3] clusters=6
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=28 ctl 24 out 23 harm +1 CI[-2,+4] clusters=6
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=12 ctl 12 out 9 harm +3 CI[+0,+6] clusters=12
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    n=12 ctl 12 out 9 harm +3 CI[+0,+6] clusters=12
== sensitivity fixed [R,R+60]|dashcam within_L                         n=393 ctl 275 out 207 harm +68 CI[-74,+229] clusters=7
== sensitivity fixed [R,R+60]|robot cbd                                n=10 ctl 10 out 9 harm +1 CI[+0,+3] clusters=4
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=10 ctl 10 out 8 harm +2 CI[+0,+4] clusters=4
---- (B) SYNC ABS F0 minus A
ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=out_f0_s5_t8805_w120.json | B=out_a5_s5_t8805_w120.json
seeds in A/B: [5] / [5]
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 19 | A-B +0 CI[-8,+6] clusters=6 | own control A 21 B 21 (A-B +0)
  robot cloud on-time  nA=26 nB=26 | outage A 12 B 19 | A-B -7 CI[-14,+0] clusters=6 | own control A 21 B 21 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 20 | A-B -5 CI[-9,-1] clusters=24 | own control A 21 B 21 (A-B +0)
  dashcam within_L     nA=790 nB=790 | outage A 180 B 530 | A-B -350 CI[-651,+0] clusters=3 | own control A 326 B 326 (A-B +0)
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 6 B 7 | A-B -1 CI[-3,+0] clusters=4 | own control A 8 B 8 (A-B +0)
  robot cloud on-time  nA=10 nB=10 | outage A 6 B 5 | A-B +1 CI[-2,+4] clusters=4 | own control A 7 B 7 (A-B +0)
  SS on-time (scorer)  nA=12 nB=12 | outage A 6 B 8 | A-B -2 CI[-5,+0] clusters=12 | own control A 9 B 9 (A-B +0)
  dashcam within_L     nA=393 nB=393 | outage A 121 B 189 | A-B -68 CI[-161,+21] clusters=7 | own control A 100 B 100 (A-B +0)
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 19 | A-B +0 CI[-8,+6] clusters=6 | own control A 22 B 22 (A-B +0)
  robot cloud on-time  nA=28 nB=28 | outage A 12 B 19 | A-B -7 CI[-14,+0] clusters=6 | own control A 22 B 22 (A-B +0)
  SS on-time (scorer)  nA=26 nB=26 | outage A 15 B 22 | A-B -7 CI[-12,-3] clusters=26 | own control A 21 B 21 (A-B +0)
  dashcam within_L     nA=865 nB=865 | outage A 225 B 573 | A-B -348 CI[-645,+0] clusters=3 | own control A 339 B 339 (A-B +0)
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 105 | A-B +0 CI[-15,+16] clusters=40 | own control A 109 B 109 (A-B +0)
  robot cloud on-time  nA=222 nB=222 | outage A 122 B 127 | A-B -5 CI[-27,+18] clusters=40 | own control A 148 B 148 (A-B +0)
  SS on-time (scorer)  nA=240 nB=240 | outage A 216 B 217 | A-B -1 CI[-11,+9] clusters=240 | own control A 211 B 211 (A-B +0)
  dashcam within_L     nA=7862 nB=7862 | outage A 5732 B 5725 | A-B +7 CI[-694,+682] clusters=20 | own control A 5025 B 5025 (A-B +0)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
################ SEEDS: 4 5
---- (a) ABS F0 minus rung3 (outage cells)
ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=../netwin/out_f0_s4_t4075_w120.json,out_f0_s5_t8805_w120.json | B=../netwin/out_rung3_s4_t4075_w120.json,out_rung3_s5_t8805_w120.json
seeds in A/B: [4, 5] / [4, 5]
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 38 B 39 | A-B -1 CI[-10,+8] clusters=13 | own control A 41 B 42 (A-B -1)
  robot cloud on-time  nA=52 nB=52 | outage A 33 B 42 | A-B -9 CI[-19,+0] clusters=13 | own control A 46 B 46 (A-B +0)
  SS on-time (scorer)  nA=48 nB=48 | outage A 36 B 42 | A-B -6 CI[-11,-1] clusters=48 | own control A 45 B 45 (A-B +0)
  dashcam within_L     nA=1587 nB=1587 | outage A 746 B 1105 | A-B -359 CI[-764,+8] clusters=6 | own control A 1018 B 1167 (A-B -149)
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 16 B 17 | A-B -1 CI[-7,+5] clusters=8 | own control A 19 B 20 (A-B -1)
  robot cloud on-time  nA=22 nB=22 | outage A 13 B 14 | A-B -1 CI[-7,+6] clusters=8 | own control A 18 B 18 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 18 | A-B -3 CI[-8,+1] clusters=24 | own control A 21 B 22 (A-B -1)
  dashcam within_L     nA=779 nB=779 | outage A 341 B 431 | A-B -90 CI[-207,+5] clusters=14 | own control A 418 B 538 (A-B -120)
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 57 B 58 | A-B -1 CI[-13,+9] clusters=21 | own control A 60 B 62 (A-B -2)
  robot cloud on-time  nA=95 nB=95 | outage A 53 B 64 | A-B -11 CI[-26,+3] clusters=21 | own control A 74 B 59 (A-B +15)
  SS on-time (scorer)  nA=86 nB=86 | outage A 61 B 63 | A-B -2 CI[-11,+8] clusters=86 | own control A 74 B 70 (A-B +4)
  dashcam within_L     nA=2849 nB=2849 | outage A 1279 B 1717 | A-B -438 CI[-874,-52] clusters=9 | own control A 1804 B 1671 (A-B +133)
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 239 B 223 | A-B +16 CI[-3,+36] clusters=87 | own control A 263 B 237 (A-B +26)
  robot cloud on-time  nA=505 nB=505 | outage A 255 B 242 | A-B +13 CI[-31,+49] clusters=87 | own control A 329 B 269 (A-B +60)
  SS on-time (scorer)  nA=477 nB=477 | outage A 392 B 359 | A-B +33 CI[+14,+52] clusters=477 | own control A 410 B 350 (A-B +60)
  dashcam within_L     nA=15712 nB=15712 | outage A 10293 B 9434 | A-B +859 CI[-87,+1900] clusters=40 | own control A 10368 B 8237 (A-B +2131)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 ../netwin/out_rung3_s4_t4075_w120.json: robot[120] 19/26; robot[whole] 131/283; cloud[120] 22/26; cloud[whole] 124/283; SS[120] 21/24; SS[whole] 163/237; dashcam[120] 588/797; dashcam[whole] 3748/7850
  B seed 5 out_rung3_s5_t8805_w120.json: robot[120] 23/26; robot[whole] 106/222; cloud[120] 24/26; cloud[whole] 145/222; SS[120] 24/24; SS[whole] 187/240; dashcam[120] 579/790; dashcam[whole] 4489/7862
---- (b) HARM F0 vs eager (A=F0,B=eager)
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -8 (n=75,cl=75) harmB -8 (n=75,cl=75) A-B +0 CI[-7,+8]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -7 (n=75,cl=75) harmB -7 (n=75,cl=75) A-B +0 CI[-7,+7]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -674 (n=2500,cl=8) harmB -686 (n=2500,cl=8) A-B +12 CI[-378,+443]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +12 (n=69,cl=24) harmB +12 (n=69,cl=24) A-B +0 CI[-20,+20]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +42 (n=69,cl=24) harmB +42 (n=69,cl=24) A-B +0 CI[-25,+26]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +9 (n=48,cl=48) harmB +16 (n=48,cl=48) A-B -7 CI[-15,+2]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +9 (n=48,cl=48) harmB +14 (n=48,cl=48) A-B -5 CI[-14,+3]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +272 (n=1587,cl=6) harmB +548 (n=1587,cl=6) A-B -276 CI[-761,+162]
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=52,cl=13) harmB +2 (n=52,cl=13) A-B +1 CI[-9,+10]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +13 (n=52,cl=13) harmB +17 (n=52,cl=13) A-B -4 CI[-17,+7]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +18 (n=477,cl=477) harmB +36 (n=477,cl=477) A-B -18 CI[-45,+10]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA +18 (n=477,cl=477) harmB +36 (n=477,cl=477) A-B -18 CI[-45,+8]
== WHOLE RUN (beside)|dashcam within_L                                 harmA +75 (n=15712,cl=40) harmB +673 (n=15712,cl=40) A-B -598 CI[-2229,+1067]
== WHOLE RUN (beside)|robot cbd                                        harmA +24 (n=505,cl=87) harmB +27 (n=505,cl=87) A-B -3 CI[-36,+32]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +74 (n=505,cl=87) harmB +85 (n=505,cl=87) A-B -11 CI[-62,+45]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +13 (n=86,cl=86) harmB +24 (n=86,cl=86) A-B -11 CI[-25,+2]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +14 (n=86,cl=86) harmB +23 (n=86,cl=86) A-B -9 CI[-22,+4]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +525 (n=2849,cl=9) harmB +888 (n=2849,cl=9) A-B -363 CI[-895,+149]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=95,cl=21) harmB +2 (n=95,cl=21) A-B +1 CI[-11,+14]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +21 (n=95,cl=21) harmB +24 (n=95,cl=21) A-B -3 CI[-21,+14]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +6 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -2 CI[-9,+5]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +6 (n=24,cl=24) harmB +7 (n=24,cl=24) A-B -1 CI[-7,+6]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +77 (n=779,cl=14) harmB +289 (n=779,cl=14) A-B -212 CI[-416,-1]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +3 (n=22,cl=8) harmB +3 (n=22,cl=8) A-B +0 CI[-6,+7]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +5 (n=22,cl=8) harmB +5 (n=22,cl=8) A-B +0 CI[-8,+9]
---- robustness HARM F0 vs rung3
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   harmA -8 (n=75,cl=75) harmB -20 (n=75,cl=75) A-B +12 CI[+2,+22]
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 harmA -7 (n=75,cl=75) harmB -19 (n=75,cl=75) A-B +12 CI[+2,+22]
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      harmA -674 (n=2500,cl=8) harmB -1080 (n=2500,cl=8) A-B +406 CI[-119,+934]
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             harmA +12 (n=69,cl=24) harmB +6 (n=69,cl=24) A-B +6 CI[-10,+24]
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   harmA +42 (n=69,cl=24) harmB +26 (n=69,cl=24) A-B +16 CI[-6,+40]
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +9 (n=48,cl=48) harmB +3 (n=48,cl=48) A-B +6 CI[-1,+14]
== RULE fixed [R,R+120]|SS within_L (outcome)                          harmA +9 (n=48,cl=48) harmB +3 (n=48,cl=48) A-B +6 CI[-1,+13]
== RULE fixed [R,R+120]|dashcam within_L                               harmA +272 (n=1587,cl=6) harmB +62 (n=1587,cl=6) A-B +210 CI[-44,+458]
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=52,cl=13) harmB +3 (n=52,cl=13) A-B +0 CI[-9,+9]
== RULE fixed [R,R+120]|robot cloud on-time                            harmA +13 (n=52,cl=13) harmB +4 (n=52,cl=13) A-B +9 CI[+0,+18]
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +18 (n=477,cl=477) harmB -9 (n=477,cl=477) A-B +27 CI[+2,+52]
== WHOLE RUN (beside)|SS within_L (outcome)                            harmA +18 (n=477,cl=477) harmB -10 (n=477,cl=477) A-B +28 CI[+2,+53]
== WHOLE RUN (beside)|dashcam within_L                                 harmA +75 (n=15712,cl=40) harmB -1197 (n=15712,cl=40) A-B +1272 CI[-41,+2743]
== WHOLE RUN (beside)|robot cbd                                        harmA +24 (n=505,cl=87) harmB +14 (n=505,cl=87) A-B +10 CI[-20,+40]
== WHOLE RUN (beside)|robot cloud on-time                              harmA +74 (n=505,cl=87) harmB +27 (n=505,cl=87) A-B +47 CI[+2,+92]
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +13 (n=86,cl=86) harmB +7 (n=86,cl=86) A-B +6 CI[-5,+17]
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   harmA +14 (n=86,cl=86) harmB +5 (n=86,cl=86) A-B +9 CI[-1,+19]
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +525 (n=2849,cl=9) harmB -46 (n=2849,cl=9) A-B +571 CI[+227,+936]
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=95,cl=21) harmB +4 (n=95,cl=21) A-B -1 CI[-12,+10]
== sensitivity fixed [R,R+300]|robot cloud on-time                     harmA +21 (n=95,cl=21) harmB -5 (n=95,cl=21) A-B +26 CI[+12,+41]
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +6 (n=24,cl=24) harmB +4 (n=24,cl=24) A-B +2 CI[-5,+9]
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    harmA +6 (n=24,cl=24) harmB +3 (n=24,cl=24) A-B +3 CI[-3,+10]
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +77 (n=779,cl=14) harmB +107 (n=779,cl=14) A-B -30 CI[-245,+182]
== sensitivity fixed [R,R+60]|robot cbd                                harmA +3 (n=22,cl=8) harmB +3 (n=22,cl=8) A-B +0 CI[-7,+8]
== sensitivity fixed [R,R+60]|robot cloud on-time                      harmA +5 (n=22,cl=8) harmB +4 (n=22,cl=8) A-B +1 CI[-7,+11]
---- eager pooled harm
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   n=75 ctl 67 out 75 harm -8 CI[-14,-3] clusters=75
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 n=75 ctl 68 out 75 harm -7 CI[-12,-3] clusters=75
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      n=2500 ctl 1785 out 2471 harm -686 CI[-986,-411] clusters=8
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             n=69 ctl 38 out 26 harm +12 CI[-1,+26] clusters=24
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   n=69 ctl 42 out 0 harm +42 CI[+25,+62] clusters=24
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=48 ctl 45 out 29 harm +16 CI[+9,+23] clusters=48
== RULE fixed [R,R+120]|SS within_L (outcome)                          n=48 ctl 45 out 31 harm +14 CI[+8,+21] clusters=48
== RULE fixed [R,R+120]|dashcam within_L                               n=1587 ctl 1018 out 470 harm +548 CI[+146,+1002] clusters=6
== RULE fixed [R,R+120]|robot cbd                                      n=52 ctl 41 out 39 harm +2 CI[-4,+8] clusters=13
== RULE fixed [R,R+120]|robot cloud on-time                            n=52 ctl 46 out 29 harm +17 CI[+8,+27] clusters=13
== WHOLE RUN (beside)|SS on-time (scorer)                              n=477 ctl 410 out 374 harm +36 CI[+15,+57] clusters=477
== WHOLE RUN (beside)|SS within_L (outcome)                            n=477 ctl 413 out 377 harm +36 CI[+14,+56] clusters=477
== WHOLE RUN (beside)|dashcam within_L                                 n=15712 ctl 10368 out 9695 harm +673 CI[-574,+1900] clusters=40
== WHOLE RUN (beside)|robot cbd                                        n=505 ctl 263 out 236 harm +27 CI[+5,+50] clusters=87
== WHOLE RUN (beside)|robot cloud on-time                              n=505 ctl 329 out 244 harm +85 CI[+38,+126] clusters=87
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=86 ctl 74 out 50 harm +24 CI[+13,+35] clusters=86
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   n=86 ctl 75 out 52 harm +23 CI[+12,+33] clusters=86
== sensitivity fixed [R,R+300]|dashcam within_L                        n=2849 ctl 1804 out 916 harm +888 CI[+470,+1362] clusters=9
== sensitivity fixed [R,R+300]|robot cbd                               n=95 ctl 60 out 58 harm +2 CI[-6,+9] clusters=21
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=95 ctl 74 out 50 harm +24 CI[+10,+39] clusters=21
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=24 ctl 21 out 13 harm +8 CI[+3,+13] clusters=24
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    n=24 ctl 21 out 14 harm +7 CI[+2,+12] clusters=24
== sensitivity fixed [R,R+60]|dashcam within_L                         n=779 ctl 418 out 129 harm +289 CI[+113,+472] clusters=14
== sensitivity fixed [R,R+60]|robot cbd                                n=22 ctl 19 out 16 harm +3 CI[+0,+6] clusters=8
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=22 ctl 18 out 13 harm +5 CI[+0,+10] clusters=8
---- rung3 pooled harm
== DURING-OUTAGE [t0,R] (beside)|SS on-time (scorer)                   n=75 ctl 51 out 71 harm -20 CI[-28,-12] clusters=75
== DURING-OUTAGE [t0,R] (beside)|SS within_L (outcome)                 n=75 ctl 52 out 71 harm -19 CI[-28,-11] clusters=75
== DURING-OUTAGE [t0,R] (beside)|dashcam within_L                      n=2500 ctl 1190 out 2270 harm -1080 CI[-1543,-665] clusters=8
== DURING-OUTAGE [t0,R] (beside)|robot cbd                             n=69 ctl 32 out 26 harm +6 CI[-4,+17] clusters=24
== DURING-OUTAGE [t0,R] (beside)|robot cloud on-time                   n=69 ctl 26 out 0 harm +26 CI[+14,+40] clusters=24
== RULE fixed [R,R+120]|SS on-time (scorer)                            n=48 ctl 45 out 42 harm +3 CI[-3,+9] clusters=48
== RULE fixed [R,R+120]|SS within_L (outcome)                          n=48 ctl 46 out 43 harm +3 CI[-2,+8] clusters=48
== RULE fixed [R,R+120]|dashcam within_L                               n=1587 ctl 1167 out 1105 harm +62 CI[-80,+222] clusters=6
== RULE fixed [R,R+120]|robot cbd                                      n=52 ctl 42 out 39 harm +3 CI[+0,+8] clusters=13
== RULE fixed [R,R+120]|robot cloud on-time                            n=52 ctl 46 out 42 harm +4 CI[-1,+9] clusters=13
== WHOLE RUN (beside)|SS on-time (scorer)                              n=477 ctl 350 out 359 harm -9 CI[-29,+11] clusters=477
== WHOLE RUN (beside)|SS within_L (outcome)                            n=477 ctl 355 out 365 harm -10 CI[-28,+9] clusters=477
== WHOLE RUN (beside)|dashcam within_L                                 n=15712 ctl 8237 out 9434 harm -1197 CI[-2176,-337] clusters=40
== WHOLE RUN (beside)|robot cbd                                        n=505 ctl 237 out 223 harm +14 CI[-4,+34] clusters=87
== WHOLE RUN (beside)|robot cloud on-time                              n=505 ctl 269 out 242 harm +27 CI[+1,+55] clusters=87
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     n=86 ctl 70 out 63 harm +7 CI[-1,+16] clusters=86
== sensitivity fixed [R,R+300]|SS within_L (outcome)                   n=86 ctl 71 out 66 harm +5 CI[-2,+13] clusters=86
== sensitivity fixed [R,R+300]|dashcam within_L                        n=2849 ctl 1671 out 1717 harm -46 CI[-287,+198] clusters=9
== sensitivity fixed [R,R+300]|robot cbd                               n=95 ctl 62 out 58 harm +4 CI[-1,+10] clusters=21
== sensitivity fixed [R,R+300]|robot cloud on-time                     n=95 ctl 59 out 64 harm -5 CI[-16,+5] clusters=21
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      n=24 ctl 22 out 18 harm +4 CI[-1,+9] clusters=24
== sensitivity fixed [R,R+60]|SS within_L (outcome)                    n=24 ctl 22 out 19 harm +3 CI[-2,+8] clusters=24
== sensitivity fixed [R,R+60]|dashcam within_L                         n=779 ctl 538 out 431 harm +107 CI[-58,+288] clusters=14
== sensitivity fixed [R,R+60]|robot cbd                                n=22 ctl 20 out 17 harm +3 CI[+0,+7] clusters=8
== sensitivity fixed [R,R+60]|robot cloud on-time                      n=22 ctl 18 out 14 harm +4 CI[-1,+9] clusters=8
---- (B) SYNC ABS F0 minus A
ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=../netwin/out_f0_s4_t4075_w120.json,out_f0_s5_t8805_w120.json | B=../netwin/out_a4_s4_t4075_w120.json,out_a5_s5_t8805_w120.json
seeds in A/B: [4, 5] / [4, 5]
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 38 B 36 | A-B +2 CI[-7,+10] clusters=13 | own control A 41 B 41 (A-B +0)
  robot cloud on-time  nA=52 nB=52 | outage A 33 B 40 | A-B -7 CI[-17,+2] clusters=13 | own control A 46 B 46 (A-B +0)
  SS on-time (scorer)  nA=48 nB=48 | outage A 36 B 41 | A-B -5 CI[-10,+0] clusters=48 | own control A 45 B 45 (A-B +0)
  dashcam within_L     nA=1587 nB=1587 | outage A 746 B 1086 | A-B -340 CI[-787,+25] clusters=6 | own control A 1018 B 1018 (A-B +0)
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 16 B 15 | A-B +1 CI[-3,+6] clusters=8 | own control A 19 B 19 (A-B +0)
  robot cloud on-time  nA=22 nB=22 | outage A 13 B 12 | A-B +1 CI[-5,+7] clusters=8 | own control A 18 B 18 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 17 | A-B -2 CI[-6,+2] clusters=24 | own control A 21 B 21 (A-B +0)
  dashcam within_L     nA=779 nB=779 | outage A 341 B 414 | A-B -73 CI[-186,+19] clusters=14 | own control A 418 B 418 (A-B +0)
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 57 B 54 | A-B +3 CI[-7,+12] clusters=21 | own control A 60 B 60 (A-B +0)
  robot cloud on-time  nA=95 nB=95 | outage A 53 B 69 | A-B -16 CI[-31,-3] clusters=21 | own control A 74 B 74 (A-B +0)
  SS on-time (scorer)  nA=86 nB=86 | outage A 61 B 71 | A-B -10 CI[-18,-2] clusters=86 | own control A 74 B 74 (A-B +0)
  dashcam within_L     nA=2849 nB=2849 | outage A 1279 B 1760 | A-B -481 CI[-924,-124] clusters=9 | own control A 1804 B 1804 (A-B +0)
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 239 B 238 | A-B +1 CI[-20,+23] clusters=87 | own control A 263 B 263 (A-B +0)
  robot cloud on-time  nA=505 nB=505 | outage A 255 B 276 | A-B -21 CI[-49,+7] clusters=87 | own control A 329 B 329 (A-B +0)
  SS on-time (scorer)  nA=477 nB=477 | outage A 392 B 408 | A-B -16 CI[-32,+0] clusters=477 | own control A 410 B 410 (A-B +0)
  dashcam within_L     nA=15712 nB=15712 | outage A 10293 B 10791 | A-B -498 CI[-1301,+429] clusters=40 | own control A 10368 B 10368 (A-B +0)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 ../netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 5 out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
