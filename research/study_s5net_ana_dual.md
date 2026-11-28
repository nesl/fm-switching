################ SEEDS: 4   (UNR[lo,hi] = unrounded percentiles 2.5/97.5 of 2000 draws, seed 7; draws<0/=0/>0 counted)
==== ARM f0 (D337)
---- (a) ABS f0 minus rung3 (outage cells); no-harm = CI includes 0 or positive
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 17 | A-B +2 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=663 >0=1337 clusters=7 | own control A 20 B 19 (A-B +1)
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 21 | A-B +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=24 | own control A 24 B 21 (A-B +3)
  dashcam within_L     nA=797 nB=797 | outage A 566 B 563 | A-B +3 CI[-12,+21] UNR[-12.000,21.000] draws<0=744 =0=72 >0=1184 clusters=3 | own control A 692 B 588 (A-B +104)
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 10 B 8 | A-B +2 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=618 >0=1382 clusters=4 | own control A 11 B 10 (A-B +1)
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 9 | A-B +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=12 | own control A 12 B 10 (A-B +2)
  dashcam within_L     nA=386 nB=386 | outage A 220 B 224 | A-B -4 CI[-25,+21] UNR[-25.000,21.000] draws<0=1204 =0=74 >0=722 clusters=7 | own control A 318 B 263 (A-B +55)
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 38 B 35 | A-B +3 CI[-2,+9] UNR[-2.000,9.000] draws<0=185 =0=189 >0=1626 clusters=15 | own control A 38 B 39 (A-B -1)
  SS on-time (scorer)  nA=60 nB=60 | outage A 46 B 40 | A-B +6 CI[-1,+13] UNR[-1.000,13.000] draws<0=76 =0=63 >0=1861 clusters=60 | own control A 53 B 46 (A-B +7)
  dashcam within_L     nA=1984 nB=1984 | outage A 1054 B 1149 | A-B -95 CI[-257,+10] UNR[-257.000,10.000] draws<0=1881 =0=15 >0=104 clusters=6 | own control A 1465 B 1080 (A-B +385)
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 134 B 123 | A-B +11 CI[-1,+24] UNR[-1.000,24.000] draws<0=64 =0=25 >0=1911 clusters=47 | own control A 154 B 131 (A-B +23)
  SS on-time (scorer)  nA=237 nB=237 | outage A 176 B 168 | A-B +8 CI[-4,+20] UNR[-4.000,20.000] draws<0=179 =0=63 >0=1758 clusters=237 | own control A 199 B 163 (A-B +36)
  dashcam within_L     nA=7850 nB=7850 | outage A 4561 B 4518 | A-B +43 CI[-196,+301] UNR[-196.000,301.000] draws<0=718 =0=2 >0=1280 clusters=20 | own control A 5343 B 3748 (A-B +1595)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 ../netwin/out_rung3_s4_t4075_w120.json: robot[120] 19/26; robot[whole] 131/283; cloud[120] 22/26; cloud[whole] 124/283; SS[120] 21/24; SS[whole] 163/237; dashcam[120] 588/797; dashcam[whole] 3748/7850
---- (b) HARM f0 vs eager (A=f0,B=eager); no worse = A-B CI includes 0 or negative
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +3 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -5 CI[-10,+0] UNR[-10.000,0.000] draws<0=1903 =0=57 >0=40
== RULE fixed [R,R+120]|dashcam within_L                               harmA +126 (n=797,cl=3) harmB +424 (n=797,cl=3) A-B -298 CI[-620,+38] UNR[-620.000,38.000] draws<0=1937 =0=3 >0=60
== RULE fixed [R,R+120]|robot cbd                                      harmA +1 (n=26,cl=7) harmB +1 (n=26,cl=7) A-B +0 CI[-2,+3] UNR[-2.000,3.000] draws<0=684 =0=650 >0=666
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +23 (n=237,cl=237) harmB +30 (n=237,cl=237) A-B -7 CI[-27,+13] UNR[-27.000,13.000] draws<0=1471 =0=66 >0=463
== WHOLE RUN (beside)|dashcam within_L                                 harmA +782 (n=7850,cl=20) harmB +999 (n=7850,cl=20) A-B -217 CI[-1182,+743] UNR[-1182.000,743.000] draws<0=1316 =0=1 >0=683
== WHOLE RUN (beside)|robot cbd                                        harmA +20 (n=283,cl=47) harmB +20 (n=283,cl=47) A-B +0 CI[-23,+25] UNR[-23.000,25.000] draws<0=959 =0=59 >0=982
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +7 (n=60,cl=60) harmB +17 (n=60,cl=60) A-B -10 CI[-21,+1] UNR[-21.000,1.000] draws<0=1902 =0=34 >0=64
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +411 (n=1984,cl=6) harmB +797 (n=1984,cl=6) A-B -386 CI[-782,+15] UNR[-782.000,15.000] draws<0=1942 =0=0 >0=58
== sensitivity fixed [R,R+300]|robot cbd                               harmA +0 (n=67,cl=15) harmB +1 (n=67,cl=15) A-B -1 CI[-8,+7] UNR[-8.000,7.000] draws<0=1128 =0=182 >0=690
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +6 (n=12,cl=12) A-B -3 CI[-7,+2] UNR[-7.000,2.000] draws<0=1732 =0=138 >0=130
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +98 (n=386,cl=7) harmB +265 (n=386,cl=7) A-B -167 CI[-277,-66] UNR[-277.000,-66.000] draws<0=1999 =0=0 >0=1
== sensitivity fixed [R,R+60]|robot cbd                                harmA +1 (n=12,cl=4) harmB +1 (n=12,cl=4) A-B +0 CI[-2,+2] UNR[-2.000,2.000] draws<0=668 =0=668 >0=664
---- robustness old D332: harm f0 vs harm rung3
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +3 (n=24,cl=24) harmB +0 (n=24,cl=24) A-B +3 CI[-3,+9] UNR[-3.000,9.000] draws<0=224 =0=172 >0=1604
== RULE fixed [R,R+120]|dashcam within_L                               harmA +126 (n=797,cl=3) harmB +25 (n=797,cl=3) A-B +101 CI[+17,+185] UNR[17.000,185.000] draws<0=26 =0=3 >0=1971
== RULE fixed [R,R+120]|robot cbd                                      harmA +1 (n=26,cl=7) harmB +2 (n=26,cl=7) A-B -1 CI[-6,+3] UNR[-6.000,3.000] draws<0=1120 =0=391 >0=489
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +23 (n=237,cl=237) harmB -5 (n=237,cl=237) A-B +28 CI[+9,+49] UNR[9.000,49.000] draws<0=7 =0=1 >0=1992
== WHOLE RUN (beside)|dashcam within_L                                 harmA +782 (n=7850,cl=20) harmB -770 (n=7850,cl=20) A-B +1552 CI[+595,+2578] UNR[595.000,2578.000] draws<0=1 =0=0 >0=1999
== WHOLE RUN (beside)|robot cbd                                        harmA +20 (n=283,cl=47) harmB +8 (n=283,cl=47) A-B +12 CI[-10,+34] UNR[-10.000,34.000] draws<0=281 =0=36 >0=1683
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +7 (n=60,cl=60) harmB +6 (n=60,cl=60) A-B +1 CI[-8,+10] UNR[-8.000,10.000] draws<0=753 =0=162 >0=1085
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +411 (n=1984,cl=6) harmB -69 (n=1984,cl=6) A-B +480 CI[+200,+776] UNR[200.000,776.000] draws<0=0 =0=0 >0=2000
== sensitivity fixed [R,R+300]|robot cbd                               harmA +0 (n=67,cl=15) harmB +4 (n=67,cl=15) A-B -4 CI[-12,+3] UNR[-12.000,3.000] draws<0=1652 =0=120 >0=228
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +1 (n=12,cl=12) A-B +2 CI[-3,+7] UNR[-3.000,7.000] draws<0=345 =0=230 >0=1425
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +98 (n=386,cl=7) harmB +39 (n=386,cl=7) A-B +59 CI[-55,+175] UNR[-55.000,175.000] draws<0=275 =0=7 >0=1718
== sensitivity fixed [R,R+60]|robot cbd                                harmA +1 (n=12,cl=4) harmB +2 (n=12,cl=4) A-B -1 CI[-5,+2] UNR[-5.000,2.000] draws<0=1138 =0=399 >0=463
==== ARM A (D337)
---- (a) ABS A minus rung3 (outage cells); no-harm = CI includes 0 or positive
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 17 B 17 | A-B +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=7 | own control A 20 B 19 (A-B +1)
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 21 | A-B +0 CI[-3,+3] UNR[-3.000,3.000] draws<0=694 =0=605 >0=701 clusters=24 | own control A 24 B 21 (A-B +3)
  dashcam within_L     nA=797 nB=797 | outage A 556 B 563 | A-B -7 CI[-24,+6] UNR[-24.000,6.000] draws<0=1485 =0=235 >0=280 clusters=3 | own control A 692 B 588 (A-B +104)
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 8 B 8 | A-B +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=4 | own control A 11 B 10 (A-B +1)
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 9 | A-B +0 CI[-3,+3] UNR[-3.000,3.000] draws<0=679 =0=588 >0=733 clusters=12 | own control A 12 B 10 (A-B +2)
  dashcam within_L     nA=386 nB=386 | outage A 225 B 224 | A-B +1 CI[-4,+6] UNR[-4.000,6.000] draws<0=614 =0=270 >0=1116 clusters=7 | own control A 318 B 263 (A-B +55)
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 35 B 35 | A-B +0 CI[-8,+7] UNR[-8.000,7.000] draws<0=836 =0=222 >0=942 clusters=15 | own control A 38 B 39 (A-B -1)
  SS on-time (scorer)  nA=60 nB=60 | outage A 49 B 40 | A-B +9 CI[+1,+17] UNR[1.000,17.000] draws<0=19 =0=15 >0=1966 clusters=60 | own control A 53 B 46 (A-B +7)
  dashcam within_L     nA=1984 nB=1984 | outage A 1187 B 1149 | A-B +38 CI[-55,+139] UNR[-55.000,139.000] draws<0=455 =0=12 >0=1533 clusters=6 | own control A 1465 B 1080 (A-B +385)
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 133 B 123 | A-B +10 CI[-7,+25] UNR[-7.000,25.000] draws<0=192 =0=46 >0=1762 clusters=47 | own control A 154 B 131 (A-B +23)
  SS on-time (scorer)  nA=237 nB=237 | outage A 191 B 168 | A-B +23 CI[+9,+36] UNR[9.000,36.000] draws<0=1 =0=1 >0=1998 clusters=237 | own control A 199 B 163 (A-B +36)
  dashcam within_L     nA=7850 nB=7850 | outage A 5066 B 4518 | A-B +548 CI[+161,+1007] UNR[161.000,1007.000] draws<0=2 =0=0 >0=1998 clusters=20 | own control A 5343 B 3748 (A-B +1595)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 ../netwin/out_rung3_s4_t4075_w120.json: robot[120] 19/26; robot[whole] 131/283; cloud[120] 22/26; cloud[whole] 124/283; SS[120] 21/24; SS[whole] 163/237; dashcam[120] 588/797; dashcam[whole] 3748/7850
---- (b) HARM A vs eager (A=A,B=eager); no worse = A-B CI includes 0 or negative
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +3 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -5 CI[-10,+0] UNR[-10.000,0.000] draws<0=1903 =0=55 >0=42
== RULE fixed [R,R+120]|dashcam within_L                               harmA +136 (n=797,cl=3) harmB +424 (n=797,cl=3) A-B -288 CI[-595,+33] UNR[-595.000,33.000] draws<0=1920 =0=0 >0=80
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=26,cl=7) harmB +1 (n=26,cl=7) A-B +2 CI[-2,+9] UNR[-2.000,9.000] draws<0=470 =0=292 >0=1238
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +8 (n=237,cl=237) harmB +30 (n=237,cl=237) A-B -22 CI[-42,-2] UNR[-42.000,-2.000] draws<0=1963 =0=7 >0=30
== WHOLE RUN (beside)|dashcam within_L                                 harmA +277 (n=7850,cl=20) harmB +999 (n=7850,cl=20) A-B -722 CI[-1598,+215] UNR[-1598.000,215.000] draws<0=1876 =0=1 >0=123
== WHOLE RUN (beside)|robot cbd                                        harmA +21 (n=283,cl=47) harmB +20 (n=283,cl=47) A-B +1 CI[-23,+26] UNR[-23.000,26.000] draws<0=897 =0=76 >0=1027
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +4 (n=60,cl=60) harmB +17 (n=60,cl=60) A-B -13 CI[-24,-2] UNR[-24.000,-2.000] draws<0=1968 =0=15 >0=17
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +278 (n=1984,cl=6) harmB +797 (n=1984,cl=6) A-B -519 CI[-900,-147] UNR[-900.000,-147.000] draws<0=1996 =0=0 >0=4
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=67,cl=15) harmB +1 (n=67,cl=15) A-B +2 CI[-6,+11] UNR[-6.000,11.000] draws<0=622 =0=173 >0=1205
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +6 (n=12,cl=12) A-B -3 CI[-7,+1] UNR[-7.000,1.000] draws<0=1689 =0=179 >0=132
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +93 (n=386,cl=7) harmB +265 (n=386,cl=7) A-B -172 CI[-284,-70] UNR[-284.000,-70.000] draws<0=1995 =0=0 >0=5
== sensitivity fixed [R,R+60]|robot cbd                                harmA +3 (n=12,cl=4) harmB +1 (n=12,cl=4) A-B +2 CI[-2,+8] UNR[-2.000,8.000] draws<0=457 =0=258 >0=1285
---- robustness old D332: harm A vs harm rung3
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +3 (n=24,cl=24) harmB +0 (n=24,cl=24) A-B +3 CI[-3,+9] UNR[-3.000,9.000] draws<0=213 =0=203 >0=1584
== RULE fixed [R,R+120]|dashcam within_L                               harmA +136 (n=797,cl=3) harmB +25 (n=797,cl=3) A-B +111 CI[+29,+193] UNR[29.000,193.000] draws<0=3 =0=0 >0=1997
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=26,cl=7) harmB +2 (n=26,cl=7) A-B +1 CI[-4,+9] UNR[-4.000,9.000] draws<0=671 =0=250 >0=1079
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +8 (n=237,cl=237) harmB -5 (n=237,cl=237) A-B +13 CI[-8,+35] UNR[-8.000,35.000] draws<0=184 =0=25 >0=1791
== WHOLE RUN (beside)|dashcam within_L                                 harmA +277 (n=7850,cl=20) harmB -770 (n=7850,cl=20) A-B +1047 CI[+187,+1980] UNR[187.000,1980.000] draws<0=17 =0=1 >0=1982
== WHOLE RUN (beside)|robot cbd                                        harmA +21 (n=283,cl=47) harmB +8 (n=283,cl=47) A-B +13 CI[-10,+36] UNR[-10.000,36.000] draws<0=266 =0=32 >0=1702
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +4 (n=60,cl=60) harmB +6 (n=60,cl=60) A-B -2 CI[-12,+8] UNR[-12.000,8.000] draws<0=1200 =0=171 >0=629
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +278 (n=1984,cl=6) harmB -69 (n=1984,cl=6) A-B +347 CI[+103,+597] UNR[103.000,597.000] draws<0=4 =0=0 >0=1996
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=67,cl=15) harmB +4 (n=67,cl=15) A-B -1 CI[-9,+8] UNR[-9.000,8.000] draws<0=1151 =0=176 >0=673
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +1 (n=12,cl=12) A-B +2 CI[-3,+7] UNR[-3.000,7.000] draws<0=338 =0=227 >0=1435
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +93 (n=386,cl=7) harmB +39 (n=386,cl=7) A-B +54 CI[-62,+174] UNR[-62.000,174.000] draws<0=340 =0=12 >0=1648
== sensitivity fixed [R,R+60]|robot cbd                                harmA +3 (n=12,cl=4) harmB +2 (n=12,cl=4) A-B +1 CI[-4,+7] UNR[-4.000,7.000] draws<0=651 =0=236 >0=1113
==== (B) D339 F0 minus A (S2 on minus off), absolute
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 17 | A-B +2 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=663 >0=1337 clusters=7 | own control A 20 B 20 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 21 | A-B +0 CI[-3,+3] UNR[-3.000,3.000] draws<0=701 =0=605 >0=694 clusters=24 | own control A 24 B 24 (A-B +0)
  dashcam within_L     nA=797 nB=797 | outage A 566 B 556 | A-B +10 CI[-9,+45] UNR[-9.000,45.000] draws<0=599 =0=0 >0=1401 clusters=3 | own control A 692 B 692 (A-B +0)
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 10 B 8 | A-B +2 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=618 >0=1382 clusters=4 | own control A 11 B 11 (A-B +0)
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 9 | A-B +0 CI[-3,+3] UNR[-3.000,3.000] draws<0=733 =0=588 >0=679 clusters=12 | own control A 12 B 12 (A-B +0)
  dashcam within_L     nA=386 nB=386 | outage A 220 B 225 | A-B -5 CI[-29,+24] UNR[-29.000,24.000] draws<0=1252 =0=60 >0=688 clusters=7 | own control A 318 B 318 (A-B +0)
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 38 B 35 | A-B +3 CI[-2,+9] UNR[-2.000,9.000] draws<0=189 =0=188 >0=1623 clusters=15 | own control A 38 B 38 (A-B +0)
  SS on-time (scorer)  nA=60 nB=60 | outage A 46 B 49 | A-B -3 CI[-9,+3] UNR[-9.000,3.000] draws<0=1519 =0=180 >0=301 clusters=60 | own control A 53 B 53 (A-B +0)
  dashcam within_L     nA=1984 nB=1984 | outage A 1054 B 1187 | A-B -133 CI[-232,-40] UNR[-232.000,-40.000] draws<0=2000 =0=0 >0=0 clusters=6 | own control A 1465 B 1465 (A-B +0)
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 134 B 133 | A-B +1 CI[-13,+17] UNR[-13.000,17.000] draws<0=840 =0=101 >0=1059 clusters=47 | own control A 154 B 154 (A-B +0)
  SS on-time (scorer)  nA=237 nB=237 | outage A 176 B 191 | A-B -15 CI[-28,-2] UNR[-28.000,-2.000] draws<0=1970 =0=5 >0=25 clusters=237 | own control A 199 B 199 (A-B +0)
  dashcam within_L     nA=7850 nB=7850 | outage A 4561 B 5066 | A-B -505 CI[-836,-193] UNR[-836.000,-193.000] draws<0=2000 =0=0 >0=0 clusters=20 | own control A 5343 B 5343 (A-B +0)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 ../netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
################ SEEDS: 5   (UNR[lo,hi] = unrounded percentiles 2.5/97.5 of 2000 draws, seed 7; draws<0/=0/>0 counted)
==== ARM f0 (D337)
---- (a) ABS f0 minus rung3 (outage cells); no-harm = CI includes 0 or positive
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 22 | A-B -3 CI[-11,+4] UNR[-11.000,4.000] draws<0=1469 =0=180 >0=351 clusters=6 | own control A 21 B 23 (A-B -2)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 21 | A-B -6 CI[-11,-1] UNR[-11.000,-1.000] draws<0=1966 =0=26 >0=8 clusters=24 | own control A 21 B 24 (A-B -3)
  dashcam within_L     nA=790 nB=790 | outage A 180 B 542 | A-B -362 CI[-597,-3] UNR[-597.000,-3.000] draws<0=2000 =0=0 >0=0 clusters=3 | own control A 326 B 579 (A-B -253)
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 6 B 9 | A-B -3 CI[-6,+0] UNR[-6.000,0.000] draws<0=1890 =0=110 >0=0 clusters=4 | own control A 8 B 10 (A-B -2)
  SS on-time (scorer)  nA=12 nB=12 | outage A 6 B 9 | A-B -3 CI[-7,+1] UNR[-7.000,1.000] draws<0=1781 =0=114 >0=105 clusters=12 | own control A 9 B 12 (A-B -3)
  dashcam within_L     nA=393 nB=393 | outage A 121 B 207 | A-B -86 CI[-200,+4] UNR[-200.000,4.000] draws<0=1915 =0=0 >0=85 clusters=7 | own control A 100 B 275 (A-B -175)
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 23 | A-B -4 CI[-14,+4] UNR[-14.000,4.000] draws<0=1479 =0=254 >0=267 clusters=6 | own control A 22 B 23 (A-B -1)
  SS on-time (scorer)  nA=26 nB=26 | outage A 15 B 23 | A-B -8 CI[-13,-3] UNR[-13.000,-3.000] draws<0=1998 =0=2 >0=0 clusters=26 | own control A 21 B 24 (A-B -3)
  dashcam within_L     nA=865 nB=865 | outage A 225 B 568 | A-B -343 CI[-540,-3] UNR[-540.000,-3.000] draws<0=2000 =0=0 >0=0 clusters=3 | own control A 339 B 591 (A-B -252)
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 100 | A-B +5 CI[-10,+20] UNR[-10.000,20.000] draws<0=452 =0=86 >0=1462 clusters=40 | own control A 109 B 106 (A-B +3)
  SS on-time (scorer)  nA=240 nB=240 | outage A 216 B 191 | A-B +25 CI[+10,+40] UNR[10.000,40.000] draws<0=1 =0=0 >0=1999 clusters=240 | own control A 211 B 187 (A-B +24)
  dashcam within_L     nA=7862 nB=7862 | outage A 5732 B 4916 | A-B +816 CI[-86,+1744] UNR[-86.000,1744.000] draws<0=80 =0=0 >0=1920 clusters=20 | own control A 5025 B 4489 (A-B +536)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_rung3_s5_t8805_w120.json: robot[120] 23/26; robot[whole] 106/222; cloud[120] 24/26; cloud[whole] 145/222; SS[120] 24/24; SS[whole] 187/240; dashcam[120] 579/790; dashcam[whole] 4489/7862
---- (b) HARM f0 vs eager (A=f0,B=eager); no worse = A-B CI includes 0 or negative
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +6 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -2 CI[-9,+5] UNR[-9.000,5.000] draws<0=1332 =0=202 >0=466
== RULE fixed [R,R+120]|dashcam within_L                               harmA +146 (n=790,cl=3) harmB +124 (n=790,cl=3) A-B +22 CI[-232,+276] UNR[-232.000,276.000] draws<0=860 =0=5 >0=1135
== RULE fixed [R,R+120]|robot cbd                                      harmA +2 (n=26,cl=6) harmB +1 (n=26,cl=6) A-B +1 CI[-8,+10] UNR[-8.000,10.000] draws<0=788 =0=170 >0=1042
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -5 (n=240,cl=240) harmB +6 (n=240,cl=240) A-B -11 CI[-28,+6] UNR[-28.000,6.000] draws<0=1785 =0=45 >0=170
== WHOLE RUN (beside)|dashcam within_L                                 harmA -707 (n=7862,cl=20) harmB -326 (n=7862,cl=20) A-B -381 CI[-1398,+721] UNR[-1398.000,721.000] draws<0=1514 =0=0 >0=486
== WHOLE RUN (beside)|robot cbd                                        harmA +4 (n=222,cl=40) harmB +7 (n=222,cl=40) A-B -3 CI[-24,+19] UNR[-24.000,19.000] draws<0=1192 =0=69 >0=739
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +6 (n=26,cl=26) harmB +7 (n=26,cl=26) A-B -1 CI[-8,+7] UNR[-8.000,7.000] draws<0=1089 =0=218 >0=693
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +114 (n=865,cl=3) harmB +91 (n=865,cl=3) A-B +23 CI[-163,+212] UNR[-163.000,212.000] draws<0=777 =0=4 >0=1219
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=28,cl=6) harmB +1 (n=28,cl=6) A-B +2 CI[-7,+11] UNR[-7.000,11.000] draws<0=607 =0=157 >0=1236
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +2 (n=12,cl=12) A-B +1 CI[-4,+6] UNR[-4.000,6.000] draws<0=570 =0=325 >0=1105
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA -21 (n=393,cl=7) harmB +24 (n=393,cl=7) A-B -45 CI[-152,+66] UNR[-152.000,66.000] draws<0=1575 =0=14 >0=411
== sensitivity fixed [R,R+60]|robot cbd                                harmA +2 (n=10,cl=4) harmB +2 (n=10,cl=4) A-B +0 CI[-5,+7] UNR[-5.000,7.000] draws<0=897 =0=284 >0=819
---- robustness old D332: harm f0 vs harm rung3
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +6 (n=24,cl=24) harmB +3 (n=24,cl=24) A-B +3 CI[-2,+8] UNR[-2.000,8.000] draws<0=180 =0=154 >0=1666
== RULE fixed [R,R+120]|dashcam within_L                               harmA +146 (n=790,cl=3) harmB +37 (n=790,cl=3) A-B +109 CI[-121,+339] UNR[-121.000,339.000] draws<0=374 =0=0 >0=1626
== RULE fixed [R,R+120]|robot cbd                                      harmA +2 (n=26,cl=6) harmB +1 (n=26,cl=6) A-B +1 CI[-6,+9] UNR[-6.000,9.000] draws<0=723 =0=188 >0=1089
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -5 (n=240,cl=240) harmB -4 (n=240,cl=240) A-B -1 CI[-17,+15] UNR[-17.000,15.000] draws<0=1046 =0=107 >0=847
== WHOLE RUN (beside)|dashcam within_L                                 harmA -707 (n=7862,cl=20) harmB -427 (n=7862,cl=20) A-B -280 CI[-1115,+546] UNR[-1115.000,546.000] draws<0=1474 =0=2 >0=524
== WHOLE RUN (beside)|robot cbd                                        harmA +4 (n=222,cl=40) harmB +6 (n=222,cl=40) A-B -2 CI[-22,+19] UNR[-22.000,19.000] draws<0=1103 =0=86 >0=811
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +6 (n=26,cl=26) harmB +1 (n=26,cl=26) A-B +5 CI[-1,+11] UNR[-1.000,11.000] draws<0=62 =0=69 >0=1869
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +114 (n=865,cl=3) harmB +23 (n=865,cl=3) A-B +91 CI[-121,+303] UNR[-121.000,303.000] draws<0=409 =0=10 >0=1581
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=28,cl=6) harmB +0 (n=28,cl=6) A-B +3 CI[-5,+11] UNR[-5.000,11.000] draws<0=394 =0=159 >0=1447
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +3 (n=12,cl=12) harmB +3 (n=12,cl=12) A-B +0 CI[-4,+4] UNR[-4.000,4.000] draws<0=833 =0=427 >0=740
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA -21 (n=393,cl=7) harmB +68 (n=393,cl=7) A-B -89 CI[-257,+74] UNR[-257.000,74.000] draws<0=1680 =0=6 >0=314
== sensitivity fixed [R,R+60]|robot cbd                                harmA +2 (n=10,cl=4) harmB +1 (n=10,cl=4) A-B +1 CI[-4,+8] UNR[-4.000,8.000] draws<0=659 =0=240 >0=1101
==== ARM A (D337)
---- (a) ABS A minus rung3 (outage cells); no-harm = CI includes 0 or positive
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 22 | A-B -3 CI[-7,+0] UNR[-7.000,0.000] draws<0=1819 =0=181 >0=0 clusters=6 | own control A 21 B 23 (A-B -2)
  SS on-time (scorer)  nA=24 nB=24 | outage A 20 B 21 | A-B -1 CI[-4,+2] UNR[-4.000,2.000] draws<0=1220 =0=432 >0=348 clusters=24 | own control A 21 B 24 (A-B -3)
  dashcam within_L     nA=790 nB=790 | outage A 530 B 542 | A-B -12 CI[-87,+54] UNR[-87.000,54.000] draws<0=1265 =0=0 >0=735 clusters=3 | own control A 326 B 579 (A-B -253)
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 7 B 9 | A-B -2 CI[-6,+0] UNR[-6.000,0.000] draws<0=1382 =0=618 >0=0 clusters=4 | own control A 8 B 10 (A-B -2)
  SS on-time (scorer)  nA=12 nB=12 | outage A 8 B 9 | A-B -1 CI[-5,+2] UNR[-5.000,2.000] draws<0=1239 =0=390 >0=371 clusters=12 | own control A 9 B 12 (A-B -3)
  dashcam within_L     nA=393 nB=393 | outage A 189 B 207 | A-B -18 CI[-113,+90] UNR[-113.000,90.000] draws<0=1298 =0=18 >0=684 clusters=7 | own control A 100 B 275 (A-B -175)
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 23 | A-B -4 CI[-8,-1] UNR[-8.000,-1.000] draws<0=1976 =0=24 >0=0 clusters=6 | own control A 22 B 23 (A-B -1)
  SS on-time (scorer)  nA=26 nB=26 | outage A 22 B 23 | A-B -1 CI[-4,+2] UNR[-4.000,2.000] draws<0=1226 =0=394 >0=380 clusters=26 | own control A 21 B 24 (A-B -3)
  dashcam within_L     nA=865 nB=865 | outage A 573 B 568 | A-B +5 CI[-87,+105] UNR[-87.000,105.000] draws<0=800 =0=0 >0=1200 clusters=3 | own control A 339 B 591 (A-B -252)
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 100 | A-B +5 CI[-4,+17] UNR[-4.000,17.000] draws<0=261 =0=108 >0=1631 clusters=40 | own control A 109 B 106 (A-B +3)
  SS on-time (scorer)  nA=240 nB=240 | outage A 217 B 191 | A-B +26 CI[+13,+39] UNR[13.000,39.000] draws<0=0 =0=0 >0=2000 clusters=240 | own control A 211 B 187 (A-B +24)
  dashcam within_L     nA=7862 nB=7862 | outage A 5725 B 4916 | A-B +809 CI[+286,+1361] UNR[286.000,1361.000] draws<0=2 =0=0 >0=1998 clusters=20 | own control A 5025 B 4489 (A-B +536)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 5 out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_rung3_s5_t8805_w120.json: robot[120] 23/26; robot[whole] 106/222; cloud[120] 24/26; cloud[whole] 145/222; SS[120] 24/24; SS[whole] 187/240; dashcam[120] 579/790; dashcam[whole] 4489/7862
---- (b) HARM A vs eager (A=A,B=eager); no worse = A-B CI includes 0 or negative
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +1 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -7 CI[-13,-1] UNR[-13.000,-1.000] draws<0=1973 =0=11 >0=16
== RULE fixed [R,R+120]|dashcam within_L                               harmA -204 (n=790,cl=3) harmB +124 (n=790,cl=3) A-B -328 CI[-625,-25] UNR[-625.000,-25.000] draws<0=1965 =0=5 >0=30
== RULE fixed [R,R+120]|robot cbd                                      harmA +2 (n=26,cl=6) harmB +1 (n=26,cl=6) A-B +1 CI[-8,+11] UNR[-8.000,11.000] draws<0=774 =0=177 >0=1049
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -6 (n=240,cl=240) harmB +6 (n=240,cl=240) A-B -12 CI[-28,+4] UNR[-28.000,4.000] draws<0=1844 =0=32 >0=124
== WHOLE RUN (beside)|dashcam within_L                                 harmA -700 (n=7862,cl=20) harmB -326 (n=7862,cl=20) A-B -374 CI[-1331,+613] UNR[-1331.000,613.000] draws<0=1541 =0=0 >0=459
== WHOLE RUN (beside)|robot cbd                                        harmA +4 (n=222,cl=40) harmB +7 (n=222,cl=40) A-B -3 CI[-24,+21] UNR[-24.000,21.000] draws<0=1193 =0=62 >0=745
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA -1 (n=26,cl=26) harmB +7 (n=26,cl=26) A-B -8 CI[-15,+0] UNR[-15.000,0.000] draws<0=1945 =0=29 >0=26
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA -234 (n=865,cl=3) harmB +91 (n=865,cl=3) A-B -325 CI[-570,-13] UNR[-570.000,-13.000] draws<0=1952 =0=4 >0=44
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=28,cl=6) harmB +1 (n=28,cl=6) A-B +2 CI[-8,+12] UNR[-8.000,12.000] draws<0=658 =0=153 >0=1189
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +1 (n=12,cl=12) harmB +2 (n=12,cl=12) A-B -1 CI[-6,+4] UNR[-6.000,4.000] draws<0=1206 =0=251 >0=543
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA -89 (n=393,cl=7) harmB +24 (n=393,cl=7) A-B -113 CI[-251,+23] UNR[-251.000,23.000] draws<0=1898 =0=3 >0=99
== sensitivity fixed [R,R+60]|robot cbd                                harmA +1 (n=10,cl=4) harmB +2 (n=10,cl=4) A-B -1 CI[-8,+7] UNR[-8.000,7.000] draws<0=1120 =0=198 >0=682
---- robustness old D332: harm A vs harm rung3
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +1 (n=24,cl=24) harmB +3 (n=24,cl=24) A-B -2 CI[-7,+3] UNR[-7.000,3.000] draws<0=1451 =0=270 >0=279
== RULE fixed [R,R+120]|dashcam within_L                               harmA -204 (n=790,cl=3) harmB +37 (n=790,cl=3) A-B -241 CI[-514,+53] UNR[-514.000,53.000] draws<0=1872 =0=0 >0=128
== RULE fixed [R,R+120]|robot cbd                                      harmA +2 (n=26,cl=6) harmB +1 (n=26,cl=6) A-B +1 CI[-7,+9] UNR[-7.000,9.000] draws<0=723 =0=195 >0=1082
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA -6 (n=240,cl=240) harmB -4 (n=240,cl=240) A-B -2 CI[-18,+13] UNR[-18.000,13.000] draws<0=1134 =0=92 >0=774
== WHOLE RUN (beside)|dashcam within_L                                 harmA -700 (n=7862,cl=20) harmB -427 (n=7862,cl=20) A-B -273 CI[-1015,+466] UNR[-1015.000,466.000] draws<0=1535 =0=1 >0=464
== WHOLE RUN (beside)|robot cbd                                        harmA +4 (n=222,cl=40) harmB +6 (n=222,cl=40) A-B -2 CI[-23,+19] UNR[-23.000,19.000] draws<0=1067 =0=83 >0=850
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA -1 (n=26,cl=26) harmB +1 (n=26,cl=26) A-B -2 CI[-8,+4] UNR[-8.000,4.000] draws<0=1342 =0=224 >0=434
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA -234 (n=865,cl=3) harmB +23 (n=865,cl=3) A-B -257 CI[-544,+76] UNR[-544.000,76.000] draws<0=1848 =0=10 >0=142
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=28,cl=6) harmB +0 (n=28,cl=6) A-B +3 CI[-6,+12] UNR[-6.000,12.000] draws<0=425 =0=165 >0=1410
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +1 (n=12,cl=12) harmB +3 (n=12,cl=12) A-B -2 CI[-7,+2] UNR[-7.000,2.000] draws<0=1541 =0=226 >0=233
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA -89 (n=393,cl=7) harmB +68 (n=393,cl=7) A-B -157 CI[-347,+19] UNR[-347.000,19.000] draws<0=1914 =0=3 >0=83
== sensitivity fixed [R,R+60]|robot cbd                                harmA +1 (n=10,cl=4) harmB +1 (n=10,cl=4) A-B +0 CI[-7,+7] UNR[-7.000,7.000] draws<0=895 =0=235 >0=870
==== (B) D339 F0 minus A (S2 on minus off), absolute
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 19 | A-B +0 CI[-8,+6] UNR[-8.000,6.000] draws<0=847 =0=223 >0=930 clusters=6 | own control A 21 B 21 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 20 | A-B -5 CI[-9,-1] UNR[-9.000,-1.000] draws<0=1991 =0=9 >0=0 clusters=24 | own control A 21 B 21 (A-B +0)
  dashcam within_L     nA=790 nB=790 | outage A 180 B 530 | A-B -350 CI[-651,+0] UNR[-651.000,0.000] draws<0=1916 =0=84 >0=0 clusters=3 | own control A 326 B 326 (A-B +0)
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 6 B 7 | A-B -1 CI[-3,+0] UNR[-3.000,0.000] draws<0=1388 =0=612 >0=0 clusters=4 | own control A 8 B 8 (A-B +0)
  SS on-time (scorer)  nA=12 nB=12 | outage A 6 B 8 | A-B -2 CI[-5,+0] UNR[-5.000,0.000] draws<0=1765 =0=235 >0=0 clusters=12 | own control A 9 B 9 (A-B +0)
  dashcam within_L     nA=393 nB=393 | outage A 121 B 189 | A-B -68 CI[-161,+21] UNR[-161.000,21.000] draws<0=1836 =0=9 >0=155 clusters=7 | own control A 100 B 100 (A-B +0)
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 19 | A-B +0 CI[-8,+6] UNR[-8.000,6.000] draws<0=847 =0=223 >0=930 clusters=6 | own control A 22 B 22 (A-B +0)
  SS on-time (scorer)  nA=26 nB=26 | outage A 15 B 22 | A-B -7 CI[-12,-3] UNR[-12.000,-3.000] draws<0=1998 =0=2 >0=0 clusters=26 | own control A 21 B 21 (A-B +0)
  dashcam within_L     nA=865 nB=865 | outage A 225 B 573 | A-B -348 CI[-645,+0] UNR[-645.000,0.000] draws<0=1916 =0=84 >0=0 clusters=3 | own control A 339 B 339 (A-B +0)
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 105 | A-B +0 CI[-15,+16] UNR[-15.000,16.000] draws<0=983 =0=121 >0=896 clusters=40 | own control A 109 B 109 (A-B +0)
  SS on-time (scorer)  nA=240 nB=240 | outage A 216 B 217 | A-B -1 CI[-11,+9] UNR[-11.000,9.000] draws<0=1129 =0=130 >0=741 clusters=240 | own control A 211 B 211 (A-B +0)
  dashcam within_L     nA=7862 nB=7862 | outage A 5732 B 5725 | A-B +7 CI[-694,+682] UNR[-694.000,682.000] draws<0=965 =0=3 >0=1032 clusters=20 | own control A 5025 B 5025 (A-B +0)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
################ SEEDS: 4 5   (UNR[lo,hi] = unrounded percentiles 2.5/97.5 of 2000 draws, seed 7; draws<0/=0/>0 counted)
==== ARM f0 (D337)
---- (a) ABS f0 minus rung3 (outage cells); no-harm = CI includes 0 or positive
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 38 B 39 | A-B -1 CI[-10,+8] UNR[-10.000,8.000] draws<0=1093 =0=171 >0=736 clusters=13 | own control A 41 B 42 (A-B -1)
  SS on-time (scorer)  nA=48 nB=48 | outage A 36 B 42 | A-B -6 CI[-11,-1] UNR[-11.000,-1.000] draws<0=1960 =0=27 >0=13 clusters=48 | own control A 45 B 45 (A-B +0)
  dashcam within_L     nA=1587 nB=1587 | outage A 746 B 1105 | A-B -359 CI[-764,+8] UNR[-764.000,8.000] draws<0=1890 =0=4 >0=106 clusters=6 | own control A 1018 B 1167 (A-B -149)
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 16 B 17 | A-B -1 CI[-7,+5] UNR[-7.000,5.000] draws<0=1109 =0=267 >0=624 clusters=8 | own control A 19 B 20 (A-B -1)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 18 | A-B -3 CI[-8,+1] UNR[-8.000,1.000] draws<0=1799 =0=127 >0=74 clusters=24 | own control A 21 B 22 (A-B -1)
  dashcam within_L     nA=779 nB=779 | outage A 341 B 431 | A-B -90 CI[-207,+5] UNR[-207.000,5.000] draws<0=1926 =0=9 >0=65 clusters=14 | own control A 418 B 538 (A-B -120)
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 57 B 58 | A-B -1 CI[-13,+9] UNR[-13.000,9.000] draws<0=1040 =0=170 >0=790 clusters=21 | own control A 60 B 62 (A-B -2)
  SS on-time (scorer)  nA=86 nB=86 | outage A 61 B 63 | A-B -2 CI[-11,+8] UNR[-11.000,8.000] draws<0=1250 =0=152 >0=598 clusters=86 | own control A 74 B 70 (A-B +4)
  dashcam within_L     nA=2849 nB=2849 | outage A 1279 B 1717 | A-B -438 CI[-874,-52] UNR[-874.000,-52.000] draws<0=1988 =0=1 >0=11 clusters=9 | own control A 1804 B 1671 (A-B +133)
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 239 B 223 | A-B +16 CI[-3,+36] UNR[-3.000,36.000] draws<0=89 =0=28 >0=1883 clusters=87 | own control A 263 B 237 (A-B +26)
  SS on-time (scorer)  nA=477 nB=477 | outage A 392 B 359 | A-B +33 CI[+14,+52] UNR[14.000,52.000] draws<0=1 =0=0 >0=1999 clusters=477 | own control A 410 B 350 (A-B +60)
  dashcam within_L     nA=15712 nB=15712 | outage A 10293 B 9434 | A-B +859 CI[-87,+1900] UNR[-87.000,1900.000] draws<0=71 =0=0 >0=1929 clusters=40 | own control A 10368 B 8237 (A-B +2131)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 ../netwin/out_rung3_s4_t4075_w120.json: robot[120] 19/26; robot[whole] 131/283; cloud[120] 22/26; cloud[whole] 124/283; SS[120] 21/24; SS[whole] 163/237; dashcam[120] 588/797; dashcam[whole] 3748/7850
  B seed 5 out_rung3_s5_t8805_w120.json: robot[120] 23/26; robot[whole] 106/222; cloud[120] 24/26; cloud[whole] 145/222; SS[120] 24/24; SS[whole] 187/240; dashcam[120] 579/790; dashcam[whole] 4489/7862
---- (b) HARM f0 vs eager (A=f0,B=eager); no worse = A-B CI includes 0 or negative
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +9 (n=48,cl=48) harmB +16 (n=48,cl=48) A-B -7 CI[-15,+2] UNR[-15.000,2.000] draws<0=1860 =0=47 >0=93
== RULE fixed [R,R+120]|dashcam within_L                               harmA +272 (n=1587,cl=6) harmB +548 (n=1587,cl=6) A-B -276 CI[-761,+162] UNR[-761.000,162.000] draws<0=1759 =0=1 >0=240
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=52,cl=13) harmB +2 (n=52,cl=13) A-B +1 CI[-9,+10] UNR[-9.000,10.000] draws<0=786 =0=164 >0=1050
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +18 (n=477,cl=477) harmB +36 (n=477,cl=477) A-B -18 CI[-45,+10] UNR[-45.000,10.000] draws<0=1795 =0=23 >0=182
== WHOLE RUN (beside)|dashcam within_L                                 harmA +75 (n=15712,cl=40) harmB +673 (n=15712,cl=40) A-B -598 CI[-2229,+1067] UNR[-2229.000,1067.000] draws<0=1500 =0=1 >0=499
== WHOLE RUN (beside)|robot cbd                                        harmA +24 (n=505,cl=87) harmB +27 (n=505,cl=87) A-B -3 CI[-36,+32] UNR[-36.000,32.000] draws<0=1098 =0=45 >0=857
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +13 (n=86,cl=86) harmB +24 (n=86,cl=86) A-B -11 CI[-25,+2] UNR[-25.000,2.000] draws<0=1878 =0=33 >0=89
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +525 (n=2849,cl=9) harmB +888 (n=2849,cl=9) A-B -363 CI[-895,+149] UNR[-895.000,149.000] draws<0=1819 =0=1 >0=180
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=95,cl=21) harmB +2 (n=95,cl=21) A-B +1 CI[-11,+14] UNR[-11.000,14.000] draws<0=869 =0=114 >0=1017
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +6 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -2 CI[-9,+5] UNR[-9.000,5.000] draws<0=1351 =0=185 >0=464
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +77 (n=779,cl=14) harmB +289 (n=779,cl=14) A-B -212 CI[-416,-1] UNR[-416.000,-1.000] draws<0=1951 =0=3 >0=46
== sensitivity fixed [R,R+60]|robot cbd                                harmA +3 (n=22,cl=8) harmB +3 (n=22,cl=8) A-B +0 CI[-6,+7] UNR[-6.000,7.000] draws<0=942 =0=226 >0=832
---- robustness old D332: harm f0 vs harm rung3
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +9 (n=48,cl=48) harmB +3 (n=48,cl=48) A-B +6 CI[-1,+14] UNR[-1.000,14.000] draws<0=81 =0=80 >0=1839
== RULE fixed [R,R+120]|dashcam within_L                               harmA +272 (n=1587,cl=6) harmB +62 (n=1587,cl=6) A-B +210 CI[-44,+458] UNR[-44.000,458.000] draws<0=119 =0=4 >0=1877
== RULE fixed [R,R+120]|robot cbd                                      harmA +3 (n=52,cl=13) harmB +3 (n=52,cl=13) A-B +0 CI[-9,+9] UNR[-9.000,9.000] draws<0=932 =0=183 >0=885
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +18 (n=477,cl=477) harmB -9 (n=477,cl=477) A-B +27 CI[+2,+52] UNR[2.000,52.000] draws<0=31 =0=10 >0=1959
== WHOLE RUN (beside)|dashcam within_L                                 harmA +75 (n=15712,cl=40) harmB -1197 (n=15712,cl=40) A-B +1272 CI[-41,+2743] UNR[-41.000,2743.000] draws<0=65 =0=0 >0=1935
== WHOLE RUN (beside)|robot cbd                                        harmA +24 (n=505,cl=87) harmB +14 (n=505,cl=87) A-B +10 CI[-20,+40] UNR[-20.000,40.000] draws<0=506 =0=44 >0=1450
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +13 (n=86,cl=86) harmB +7 (n=86,cl=86) A-B +6 CI[-5,+17] UNR[-5.000,17.000] draws<0=284 =0=80 >0=1636
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +525 (n=2849,cl=9) harmB -46 (n=2849,cl=9) A-B +571 CI[+227,+936] UNR[227.000,936.000] draws<0=0 =0=0 >0=2000
== sensitivity fixed [R,R+300]|robot cbd                               harmA +3 (n=95,cl=21) harmB +4 (n=95,cl=21) A-B -1 CI[-12,+10] UNR[-12.000,10.000] draws<0=1070 =0=139 >0=791
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +6 (n=24,cl=24) harmB +4 (n=24,cl=24) A-B +2 CI[-5,+9] UNR[-5.000,9.000] draws<0=458 =0=181 >0=1361
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +77 (n=779,cl=14) harmB +107 (n=779,cl=14) A-B -30 CI[-245,+182] UNR[-245.000,182.000] draws<0=1199 =0=5 >0=796
== sensitivity fixed [R,R+60]|robot cbd                                harmA +3 (n=22,cl=8) harmB +3 (n=22,cl=8) A-B +0 CI[-7,+8] UNR[-7.000,8.000] draws<0=910 =0=189 >0=901
==== ARM A (D337)
---- (a) ABS A minus rung3 (outage cells); no-harm = CI includes 0 or positive
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 36 B 39 | A-B -3 CI[-8,+0] UNR[-8.000,0.000] draws<0=1766 =0=234 >0=0 clusters=13 | own control A 41 B 42 (A-B -1)
  SS on-time (scorer)  nA=48 nB=48 | outage A 41 B 42 | A-B -1 CI[-5,+3] UNR[-5.000,3.000] draws<0=1160 =0=341 >0=499 clusters=48 | own control A 45 B 45 (A-B +0)
  dashcam within_L     nA=1587 nB=1587 | outage A 1086 B 1105 | A-B -19 CI[-85,+47] UNR[-85.000,47.000] draws<0=1363 =0=34 >0=603 clusters=6 | own control A 1018 B 1167 (A-B -149)
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 15 B 17 | A-B -2 CI[-6,+0] UNR[-6.000,0.000] draws<0=1295 =0=705 >0=0 clusters=8 | own control A 19 B 20 (A-B -1)
  SS on-time (scorer)  nA=24 nB=24 | outage A 17 B 18 | A-B -1 CI[-6,+3] UNR[-6.000,3.000] draws<0=1223 =0=320 >0=457 clusters=24 | own control A 21 B 22 (A-B -1)
  dashcam within_L     nA=779 nB=779 | outage A 414 B 431 | A-B -17 CI[-110,+83] UNR[-110.000,83.000] draws<0=1285 =0=14 >0=701 clusters=14 | own control A 418 B 538 (A-B -120)
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 54 B 58 | A-B -4 CI[-13,+4] UNR[-13.000,4.000] draws<0=1555 =0=131 >0=314 clusters=21 | own control A 60 B 62 (A-B -2)
  SS on-time (scorer)  nA=86 nB=86 | outage A 71 B 63 | A-B +8 CI[+0,+16] UNR[0.000,16.000] draws<0=42 =0=32 >0=1926 clusters=86 | own control A 74 B 70 (A-B +4)
  dashcam within_L     nA=2849 nB=2849 | outage A 1760 B 1717 | A-B +43 CI[-94,+181] UNR[-94.000,181.000] draws<0=493 =0=10 >0=1497 clusters=9 | own control A 1804 B 1671 (A-B +133)
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 238 B 223 | A-B +15 CI[-4,+33] UNR[-4.000,33.000] draws<0=122 =0=30 >0=1848 clusters=87 | own control A 263 B 237 (A-B +26)
  SS on-time (scorer)  nA=477 nB=477 | outage A 408 B 359 | A-B +49 CI[+31,+67] UNR[31.000,67.000] draws<0=0 =0=0 >0=2000 clusters=477 | own control A 410 B 350 (A-B +60)
  dashcam within_L     nA=15712 nB=15712 | outage A 10791 B 9434 | A-B +1357 CI[+669,+2056] UNR[669.000,2056.000] draws<0=0 =0=0 >0=2000 clusters=40 | own control A 10368 B 8237 (A-B +2131)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 ../netwin/out_rung3_s4_t4075_w120.json: robot[120] 19/26; robot[whole] 131/283; cloud[120] 22/26; cloud[whole] 124/283; SS[120] 21/24; SS[whole] 163/237; dashcam[120] 588/797; dashcam[whole] 3748/7850
  B seed 5 out_rung3_s5_t8805_w120.json: robot[120] 23/26; robot[whole] 106/222; cloud[120] 24/26; cloud[whole] 145/222; SS[120] 24/24; SS[whole] 187/240; dashcam[120] 579/790; dashcam[whole] 4489/7862
---- (b) HARM A vs eager (A=A,B=eager); no worse = A-B CI includes 0 or negative
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +4 (n=48,cl=48) harmB +16 (n=48,cl=48) A-B -12 CI[-20,-3] UNR[-20.000,-3.000] draws<0=1992 =0=4 >0=4
== RULE fixed [R,R+120]|dashcam within_L                               harmA -68 (n=1587,cl=6) harmB +548 (n=1587,cl=6) A-B -616 CI[-1216,-72] UNR[-1216.000,-72.000] draws<0=1981 =0=0 >0=19
== RULE fixed [R,R+120]|robot cbd                                      harmA +5 (n=52,cl=13) harmB +2 (n=52,cl=13) A-B +3 CI[-8,+14] UNR[-8.000,14.000] draws<0=525 =0=142 >0=1333
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +2 (n=477,cl=477) harmB +36 (n=477,cl=477) A-B -34 CI[-60,-6] UNR[-60.000,-6.000] draws<0=1985 =0=1 >0=14
== WHOLE RUN (beside)|dashcam within_L                                 harmA -423 (n=15712,cl=40) harmB +673 (n=15712,cl=40) A-B -1096 CI[-2612,+394] UNR[-2612.000,394.000] draws<0=1855 =0=1 >0=144
== WHOLE RUN (beside)|robot cbd                                        harmA +25 (n=505,cl=87) harmB +27 (n=505,cl=87) A-B -2 CI[-36,+33] UNR[-36.000,33.000] draws<0=1086 =0=41 >0=873
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +3 (n=86,cl=86) harmB +24 (n=86,cl=86) A-B -21 CI[-35,-7] UNR[-35.000,-7.000] draws<0=1999 =0=0 >0=1
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +44 (n=2849,cl=9) harmB +888 (n=2849,cl=9) A-B -844 CI[-1490,-208] UNR[-1490.000,-208.000] draws<0=1990 =0=0 >0=10
== sensitivity fixed [R,R+300]|robot cbd                               harmA +6 (n=95,cl=21) harmB +2 (n=95,cl=21) A-B +4 CI[-8,+18] UNR[-8.000,18.000] draws<0=484 =0=109 >0=1407
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +4 (n=24,cl=24) harmB +8 (n=24,cl=24) A-B -4 CI[-11,+3] UNR[-11.000,3.000] draws<0=1687 =0=98 >0=215
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +4 (n=779,cl=14) harmB +289 (n=779,cl=14) A-B -285 CI[-520,-44] UNR[-520.000,-44.000] draws<0=1977 =0=0 >0=23
== sensitivity fixed [R,R+60]|robot cbd                                harmA +4 (n=22,cl=8) harmB +3 (n=22,cl=8) A-B +1 CI[-8,+11] UNR[-8.000,11.000] draws<0=779 =0=144 >0=1077
---- robustness old D332: harm A vs harm rung3
== RULE fixed [R,R+120]|SS on-time (scorer)                            harmA +4 (n=48,cl=48) harmB +3 (n=48,cl=48) A-B +1 CI[-6,+9] UNR[-6.000,9.000] draws<0=708 =0=216 >0=1076
== RULE fixed [R,R+120]|dashcam within_L                               harmA -68 (n=1587,cl=6) harmB +62 (n=1587,cl=6) A-B -130 CI[-556,+254] UNR[-556.000,254.000] draws<0=1405 =0=1 >0=594
== RULE fixed [R,R+120]|robot cbd                                      harmA +5 (n=52,cl=13) harmB +3 (n=52,cl=13) A-B +2 CI[-8,+13] UNR[-8.000,13.000] draws<0=638 =0=127 >0=1235
== WHOLE RUN (beside)|SS on-time (scorer)                              harmA +2 (n=477,cl=477) harmB -9 (n=477,cl=477) A-B +11 CI[-14,+38] UNR[-14.000,38.000] draws<0=375 =0=20 >0=1605
== WHOLE RUN (beside)|dashcam within_L                                 harmA -423 (n=15712,cl=40) harmB -1197 (n=15712,cl=40) A-B +774 CI[-408,+2081] UNR[-408.000,2081.000] draws<0=213 =0=1 >0=1786
== WHOLE RUN (beside)|robot cbd                                        harmA +25 (n=505,cl=87) harmB +14 (n=505,cl=87) A-B +11 CI[-20,+43] UNR[-20.000,43.000] draws<0=474 =0=37 >0=1489
== sensitivity fixed [R,R+300]|SS on-time (scorer)                     harmA +3 (n=86,cl=86) harmB +7 (n=86,cl=86) A-B -4 CI[-16,+7] UNR[-16.000,7.000] draws<0=1458 =0=112 >0=430
== sensitivity fixed [R,R+300]|dashcam within_L                        harmA +44 (n=2849,cl=9) harmB -46 (n=2849,cl=9) A-B +90 CI[-453,+589] UNR[-453.000,589.000] draws<0=672 =0=2 >0=1326
== sensitivity fixed [R,R+300]|robot cbd                               harmA +6 (n=95,cl=21) harmB +4 (n=95,cl=21) A-B +2 CI[-10,+14] UNR[-10.000,14.000] draws<0=656 =0=155 >0=1189
== sensitivity fixed [R,R+60]|SS on-time (scorer)                      harmA +4 (n=24,cl=24) harmB +4 (n=24,cl=24) A-B +0 CI[-7,+7] UNR[-7.000,7.000] draws<0=908 =0=219 >0=873
== sensitivity fixed [R,R+60]|dashcam within_L                         harmA +4 (n=779,cl=14) harmB +107 (n=779,cl=14) A-B -103 CI[-357,+140] UNR[-357.000,140.000] draws<0=1594 =0=2 >0=404
== sensitivity fixed [R,R+60]|robot cbd                                harmA +4 (n=22,cl=8) harmB +3 (n=22,cl=8) A-B +1 CI[-8,+11] UNR[-8.000,11.000] draws<0=772 =0=151 >0=1077
==== (B) D339 F0 minus A (S2 on minus off), absolute
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 38 B 36 | A-B +2 CI[-7,+10] UNR[-7.000,10.000] draws<0=556 =0=155 >0=1289 clusters=13 | own control A 41 B 41 (A-B +0)
  SS on-time (scorer)  nA=48 nB=48 | outage A 36 B 41 | A-B -5 CI[-10,+0] UNR[-10.000,0.000] draws<0=1929 =0=45 >0=26 clusters=48 | own control A 45 B 45 (A-B +0)
  dashcam within_L     nA=1587 nB=1587 | outage A 746 B 1086 | A-B -340 CI[-787,+25] UNR[-787.000,25.000] draws<0=1843 =0=0 >0=157 clusters=6 | own control A 1018 B 1018 (A-B +0)
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 16 B 15 | A-B +1 CI[-3,+6] UNR[-3.000,6.000] draws<0=525 =0=351 >0=1124 clusters=8 | own control A 19 B 19 (A-B +0)
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 17 | A-B -2 CI[-6,+2] UNR[-6.000,2.000] draws<0=1578 =0=241 >0=181 clusters=24 | own control A 21 B 21 (A-B +0)
  dashcam within_L     nA=779 nB=779 | outage A 341 B 414 | A-B -73 CI[-186,+19] UNR[-186.000,19.000] draws<0=1845 =0=10 >0=145 clusters=14 | own control A 418 B 418 (A-B +0)
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 57 B 54 | A-B +3 CI[-7,+12] UNR[-7.000,12.000] draws<0=503 =0=121 >0=1376 clusters=21 | own control A 60 B 60 (A-B +0)
  SS on-time (scorer)  nA=86 nB=86 | outage A 61 B 71 | A-B -10 CI[-18,-2] UNR[-18.000,-2.000] draws<0=1979 =0=11 >0=10 clusters=86 | own control A 74 B 74 (A-B +0)
  dashcam within_L     nA=2849 nB=2849 | outage A 1279 B 1760 | A-B -481 CI[-924,-124] UNR[-924.000,-124.000] draws<0=2000 =0=0 >0=0 clusters=9 | own control A 1804 B 1804 (A-B +0)
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 239 B 238 | A-B +1 CI[-20,+23] UNR[-20.000,23.000] draws<0=892 =0=84 >0=1024 clusters=87 | own control A 263 B 263 (A-B +0)
  SS on-time (scorer)  nA=477 nB=477 | outage A 392 B 408 | A-B -16 CI[-32,+0] UNR[-32.000,0.000] draws<0=1939 =0=15 >0=46 clusters=477 | own control A 410 B 410 (A-B +0)
  dashcam within_L     nA=15712 nB=15712 | outage A 10293 B 10791 | A-B -498 CI[-1301,+429] UNR[-1301.000,429.000] draws<0=1748 =0=0 >0=252 clusters=40 | own control A 10368 B 10368 (A-B +0)
== CONTROL LEVELS per seed per arm (own no-outage control counts; n = units) : window 120 | whole run
  A seed 4 ../netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 ../netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 5 out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862

######## COMPACT F0 vs cand-tl TABLE (dual_table.txt)
D337 per seed and pooled: F0 | cand-tl(A).  (a) = X minus rung3 absolute; (b) = harm X minus harm eager. point[unrounded lo,hi] R120 / whole
SEEDS 4 ARM f0
   a R120 SS: +0[0.000,0.000]; R120 cbd: +2[0.000,6.000]; R120 dash: +3[-12.000,21.000]; p300 SS: +6[-1.000,13.000]; p300 cbd: +3[-2.000,9.000]; p300 dash: -95[-257.000,10.000]; p60 SS: +0[0.000,0.000]; p60 cbd: +2[0.000,6.000]; p60 dash: -4[-25.000,21.000]; whole SS: +8[-4.000,20.000]; whole cbd: +11[-1.000,24.000]; whole dash: +43[-196.000,301.000]
   b R120 SS: -5[-10.000,0.000]; R120 cbd: +0[-2.000,3.000]; R120 dash: -298[-620.000,38.000]; whole SS: -7[-27.000,13.000]; whole cbd: +0[-23.000,25.000]; whole dash: -217[-1182.000,743.000]
   rob R120 SS: +3[-3.000,9.000]; R120 cbd: -1[-6.000,3.000]; R120 dash: +101[17.000,185.000]; whole SS: +28[9.000,49.000]; whole cbd: +12[-10.000,34.000]; whole dash: +1552[595.000,2578.000]
SEEDS 4 ARM A
   a R120 SS: +0[-3.000,3.000]; R120 cbd: +0[0.000,0.000]; R120 dash: -7[-24.000,6.000]; p300 SS: +9[1.000,17.000]; p300 cbd: +0[-8.000,7.000]; p300 dash: +38[-55.000,139.000]; p60 SS: +0[-3.000,3.000]; p60 cbd: +0[0.000,0.000]; p60 dash: +1[-4.000,6.000]; whole SS: +23[9.000,36.000]; whole cbd: +10[-7.000,25.000]; whole dash: +548[161.000,1007.000]
   b R120 SS: -5[-10.000,0.000]; R120 cbd: +2[-2.000,9.000]; R120 dash: -288[-595.000,33.000]; whole SS: -22[-42.000,-2.000]; whole cbd: +1[-23.000,26.000]; whole dash: -722[-1598.000,215.000]
   rob R120 SS: +3[-3.000,9.000]; R120 cbd: +1[-4.000,9.000]; R120 dash: +111[29.000,193.000]; whole SS: +13[-8.000,35.000]; whole cbd: +13[-10.000,36.000]; whole dash: +1047[187.000,1980.000]
SEEDS 5 ARM f0
   a R120 SS: -6[-11.000,-1.000]; R120 cbd: -3[-11.000,4.000]; R120 dash: -362[-597.000,-3.000]; p300 SS: -8[-13.000,-3.000]; p300 cbd: -4[-14.000,4.000]; p300 dash: -343[-540.000,-3.000]; p60 SS: -3[-7.000,1.000]; p60 cbd: -3[-6.000,0.000]; p60 dash: -86[-200.000,4.000]; whole SS: +25[10.000,40.000]; whole cbd: +5[-10.000,20.000]; whole dash: +816[-86.000,1744.000]
   b R120 SS: -2[-9.000,5.000]; R120 cbd: +1[-8.000,10.000]; R120 dash: +22[-232.000,276.000]; whole SS: -11[-28.000,6.000]; whole cbd: -3[-24.000,19.000]; whole dash: -381[-1398.000,721.000]
   rob R120 SS: +3[-2.000,8.000]; R120 cbd: +1[-6.000,9.000]; R120 dash: +109[-121.000,339.000]; whole SS: -1[-17.000,15.000]; whole cbd: -2[-22.000,19.000]; whole dash: -280[-1115.000,546.000]
SEEDS 5 ARM A
   a R120 SS: -1[-4.000,2.000]; R120 cbd: -3[-7.000,0.000]; R120 dash: -12[-87.000,54.000]; p300 SS: -1[-4.000,2.000]; p300 cbd: -4[-8.000,-1.000]; p300 dash: +5[-87.000,105.000]; p60 SS: -1[-5.000,2.000]; p60 cbd: -2[-6.000,0.000]; p60 dash: -18[-113.000,90.000]; whole SS: +26[13.000,39.000]; whole cbd: +5[-4.000,17.000]; whole dash: +809[286.000,1361.000]
   b R120 SS: -7[-13.000,-1.000]; R120 cbd: +1[-8.000,11.000]; R120 dash: -328[-625.000,-25.000]; whole SS: -12[-28.000,4.000]; whole cbd: -3[-24.000,21.000]; whole dash: -374[-1331.000,613.000]
   rob R120 SS: -2[-7.000,3.000]; R120 cbd: +1[-7.000,9.000]; R120 dash: -241[-514.000,53.000]; whole SS: -2[-18.000,13.000]; whole cbd: -2[-23.000,19.000]; whole dash: -273[-1015.000,466.000]
SEEDS 4 5 ARM f0
   a R120 SS: -6[-11.000,-1.000]; R120 cbd: -1[-10.000,8.000]; R120 dash: -359[-764.000,8.000]; p300 SS: -2[-11.000,8.000]; p300 cbd: -1[-13.000,9.000]; p300 dash: -438[-874.000,-52.000]; p60 SS: -3[-8.000,1.000]; p60 cbd: -1[-7.000,5.000]; p60 dash: -90[-207.000,5.000]; whole SS: +33[14.000,52.000]; whole cbd: +16[-3.000,36.000]; whole dash: +859[-87.000,1900.000]
   b R120 SS: -7[-15.000,2.000]; R120 cbd: +1[-9.000,10.000]; R120 dash: -276[-761.000,162.000]; whole SS: -18[-45.000,10.000]; whole cbd: -3[-36.000,32.000]; whole dash: -598[-2229.000,1067.000]
   rob R120 SS: +6[-1.000,14.000]; R120 cbd: +0[-9.000,9.000]; R120 dash: +210[-44.000,458.000]; whole SS: +27[2.000,52.000]; whole cbd: +10[-20.000,40.000]; whole dash: +1272[-41.000,2743.000]
SEEDS 4 5 ARM A
   a R120 SS: -1[-5.000,3.000]; R120 cbd: -3[-8.000,0.000]; R120 dash: -19[-85.000,47.000]; p300 SS: +8[0.000,16.000]; p300 cbd: -4[-13.000,4.000]; p300 dash: +43[-94.000,181.000]; p60 SS: -1[-6.000,3.000]; p60 cbd: -2[-6.000,0.000]; p60 dash: -17[-110.000,83.000]; whole SS: +49[31.000,67.000]; whole cbd: +15[-4.000,33.000]; whole dash: +1357[669.000,2056.000]
   b R120 SS: -12[-20.000,-3.000]; R120 cbd: +3[-8.000,14.000]; R120 dash: -616[-1216.000,-72.000]; whole SS: -34[-60.000,-6.000]; whole cbd: -2[-36.000,33.000]; whole dash: -1096[-2612.000,394.000]
   rob R120 SS: +1[-6.000,9.000]; R120 cbd: +2[-8.000,13.000]; R120 dash: -130[-556.000,254.000]; whole SS: +11[-14.000,38.000]; whole cbd: +11[-20.000,43.000]; whole dash: +774[-408.000,2081.000]

Add s6: ./score_s6.sh && ./ana_dual.sh '4' '5' '6' '4 5' '4 5 6' > ana_dual.txt
