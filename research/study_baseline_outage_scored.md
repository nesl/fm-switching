Fri Nov 27 10:05:29 PM PST 2026
COMPARISON cells, NOT part of the D337/D339 freeze verdict. Baseline cells scored with netwin_b.py (netwin.py + guard for t_done=None on abandoned end-of-run requests; classifier cross-check only).
started
Fri Nov 27 09:00:39 PM PST 2026 streamscout_4 scored
restart
Fri Nov 27 09:01:13 PM PST 2026 streamscout_4 scored
Fri Nov 27 09:22:15 PM PST 2026 mooncake_4 scored
Fri Nov 27 09:43:51 PM PST 2026 streamscout_5 scored
Fri Nov 27 10:05:24 PM PST 2026 mooncake_5 scored
Fri Nov 27 10:05:24 PM PST 2026 end done=mooncake_5 mooncake_4 streamscout_4 streamscout_5
OUTAGE-CELL OWN NUMBERS: count/n, windows R+120 | R+300 | whole
 s4 a4          robot 17/26 | 35/67 | 133/283; cloud 21/26 | 50/67 | 149/283; SS 21/24 | 49/60 | 191/237; dashcam 556/797 | 1187/1984 | 5066/7850
 s4 eager       robot 19/26 | 37/67 | 134/283; cloud 17/26 | 37/67 | 123/283; SS 16/24 | 36/60 | 169/237; dashcam 268/797 | 668/1984 | 4344/7850
 s4 f0          robot 19/26 | 38/67 | 134/283; cloud 21/26 | 41/67 | 133/283; SS 21/24 | 46/60 | 176/237; dashcam 566/797 | 1054/1984 | 4561/7850
 s4 mooncake    robot 17/26 | 37/67 | 108/283; cloud 8/26 | 17/67 | 43/283; SS 22/24 | 52/60 | 211/237; dashcam 716/797 | 1696/1984 | 6652/7850
 s4 rung3       robot 17/26 | 35/67 | 123/283; cloud 20/26 | 41/67 | 111/283; SS 21/24 | 40/60 | 168/237; dashcam 563/797 | 1149/1984 | 4518/7850
 s4 streamscout robot 6/26 | 17/67 | 69/283; cloud 26/26 | 67/67 | 243/283; SS 24/24 | 60/60 | 237/237; dashcam 797/797 | 1984/1984 | 7836/7850
 s5 a4          robot 19/26 | 19/28 | 105/222; cloud 19/26 | 19/28 | 127/222; SS 20/24 | 22/26 | 217/240; dashcam 530/790 | 573/865 | 5725/7862
 s5 eager       robot 20/26 | 21/28 | 102/222; cloud 12/26 | 13/28 | 121/222; SS 13/24 | 14/26 | 205/240; dashcam 202/790 | 248/865 | 5351/7862
 s5 f0          robot 19/26 | 19/28 | 105/222; cloud 12/26 | 12/28 | 122/222; SS 15/24 | 15/26 | 216/240; dashcam 180/790 | 225/865 | 5732/7862
 s5 mooncake    robot 19/26 | 19/28 | 83/222; cloud 10/26 | 10/28 | 43/222; SS 22/24 | 24/26 | 223/240; dashcam 674/790 | 745/865 | 7129/7862
 s5 rung3       robot 22/26 | 23/28 | 100/222; cloud 22/26 | 23/28 | 131/222; SS 21/24 | 23/26 | 191/240; dashcam 542/790 | 568/865 | 4916/7862
 s5 streamscout robot 5/26 | 6/28 | 48/222; cloud 26/26 | 28/28 | 193/222; SS 24/24 | 26/26 | 240/240; dashcam 789/790 | 857/865 | 7846/7862

PER-ARM FULL-RUN TABLE (cbd, cloud on-time, total on-time, device-only, accuracy on served, representation, tokens); user refs s4 SS cbd69/dev93/acc0.218, rung3 123/0.640, cand-tl 133 all AGREE
s   arm         | n | cbd | cloud-on-time | total on-time (cloud+device on time) | device-only(cell.json acc*n) | cloud-standing acc (correct/served) | classifier cbd agree | robot req reps (outcomes) | robot req prompt_tokens (n,med,mean,max)
s4 rung3       | 283 | 123 | 111 | 283 | 93 | 71/111=0.640 | see netwin | {'D2': 188} | 188,14374,15241,27034
s4 eager       | 283 | 134 | 123 | 283 | 93 | 77/123=0.626 | see netwin | {'D2': 152} | 151,13334,14955,27034
s4 F0          | 283 | 134 | 133 | 283 | 93 | 84/133=0.632 | see netwin | {'D2': 170} | 170,14371,15374,26777
s4 cand-tl     | 283 | 133 | 149 | 283 | 93 | 99/149=0.664 | see netwin | {'D2': 170} | 170,14492,15095,26823
s4 streamscout | 283 | 69 | 243 | 283 | 93 | 53/243=0.218 | see netwin | {'RECENT': 243} | 242,663,666,782
s4 mooncake    | 283 | 108 | 43 | 283 | 93 | 24/43=0.558 | see netwin | {'D2': 87} | 87,10997,10670,13444
s5 rung3       | 222 | 100 | 131 | 222 | 67 | 69/131=0.527 | see netwin | {'D2': 171} | 171,16680,16543,27039
s5 eager       | 222 | 102 | 121 | 222 | 67 | 65/121=0.537 | see netwin | {'D2': 143} | 143,15143,16170,27074
s5 F0          | 222 | 105 | 122 | 222 | 67 | 71/122=0.582 | see netwin | {'D2': 144} | 144,14147,15687,27039
s5 cand-tl     | 222 | 105 | 127 | 222 | 67 | 74/127=0.583 | see netwin | {'D2': 142} | 142,14316,15832,27039
s5 streamscout | 222 | 48 | 193 | 222 | 67 | 38/193=0.197 | see netwin | {'RECENT': 193} | 193,660,672,782
s5 mooncake    | 222 | 83 | 43 | 222 | 67 | 29/43=0.674 | see netwin | {'D2': 69} | 69,10743,10450,12997
s6 rung3       | 250 | 79 | 111 | 250 | 56 | 55/111=0.495 | see netwin | {'D2': 177} | 177,13543,15434,26989
s6 eager       | 250 | 85 | 112 | 250 | 56 | 61/112=0.545 | see netwin | {'D2': 136} | 136,13023,14683,26989
s6 F0          MISSING on origin
s6 cand-tl     MISSING on origin
s6 streamscout MISSING on origin
s6 mooncake    MISSING on origin
################ SEEDS: 4  (UNR = unrounded 2.5/97.5 pct of 2000 draws, seed 7; strict: CI excludes 0 = whole unrounded interval strictly one side). Baseline cells have NO control except mooncake s4: 'own control' columns for baselines are the outage cell itself (ignore).
==== COVEX f0 minus streamscout (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 6 | A-B +13 CI[-3,+30] UNR[-3.000,30.000] draws<0=139 =0=54 >0=1807 clusters=7
  robot cloud on-time  nA=26 nB=26 | outage A 21 B 26 | A-B -5 CI[-11,-1] UNR[-11.000,-1.000] draws<0=1961 =0=39 >0=0 clusters=7
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 24 | A-B -3 CI[-7,+0] UNR[-7.000,0.000] draws<0=1921 =0=79 >0=0 clusters=24
  dashcam within_L     nA=797 nB=797 | outage A 566 B 797 | A-B -231 CI[-411,-87] UNR[-411.000,-87.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 10 B 3 | A-B +7 CI[+0,+15] UNR[0.000,15.000] draws<0=0 =0=128 >0=1872 clusters=4
  robot cloud on-time  nA=12 nB=12 | outage A 7 B 12 | A-B -5 CI[-10,-1] UNR[-10.000,-1.000] draws<0=1992 =0=8 >0=0 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 12 | A-B -3 CI[-6,+0] UNR[-6.000,0.000] draws<0=1929 =0=71 >0=0 clusters=12
  dashcam within_L     nA=386 nB=386 | outage A 220 B 386 | A-B -166 CI[-250,-80] UNR[-250.000,-80.000] draws<0=2000 =0=0 >0=0 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 38 B 17 | A-B +21 CI[-2,+47] UNR[-2.000,47.000] draws<0=65 =0=14 >0=1921 clusters=15
  robot cloud on-time  nA=67 nB=67 | outage A 41 B 67 | A-B -26 CI[-37,-16] UNR[-37.000,-16.000] draws<0=2000 =0=0 >0=0 clusters=15
  SS on-time (scorer)  nA=60 nB=60 | outage A 46 B 60 | A-B -14 CI[-21,-8] UNR[-21.000,-8.000] draws<0=2000 =0=0 >0=0 clusters=60
  dashcam within_L     nA=1984 nB=1984 | outage A 1054 B 1984 | A-B -930 CI[-1315,-523] UNR[-1315.000,-523.000] draws<0=2000 =0=0 >0=0 clusters=6
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 134 B 69 | A-B +65 CI[+28,+110] UNR[28.000,110.000] draws<0=0 =0=0 >0=2000 clusters=47
  robot cloud on-time  nA=283 nB=283 | outage A 133 B 243 | A-B -110 CI[-142,-80] UNR[-142.000,-80.000] draws<0=2000 =0=0 >0=0 clusters=47
  SS on-time (scorer)  nA=237 nB=237 | outage A 176 B 237 | A-B -61 CI[-74,-47] UNR[-74.000,-47.000] draws<0=2000 =0=0 >0=0 clusters=237
  dashcam within_L     nA=7850 nB=7850 | outage A 4561 B 7836 | A-B -3275 CI[-4342,-2292] UNR[-4342.000,-2292.000] draws<0=2000 =0=0 >0=0 clusters=20
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 out_streamscout_4_w120.json: robot[120] 6/26; robot[whole] 69/283; cloud[120] 26/26; cloud[whole] 243/283; SS[120] 24/24; SS[whole] 237/237; dashcam[120] 797/797; dashcam[whole] 7836/7850
==== COVEX a4 minus streamscout (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 17 B 6 | A-B +11 CI[-7,+29] UNR[-7.000,29.000] draws<0=249 =0=51 >0=1700 clusters=7
  robot cloud on-time  nA=26 nB=26 | outage A 21 B 26 | A-B -5 CI[-12,+0] UNR[-12.000,0.000] draws<0=1801 =0=199 >0=0 clusters=7
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 24 | A-B -3 CI[-7,+0] UNR[-7.000,0.000] draws<0=1920 =0=80 >0=0 clusters=24
  dashcam within_L     nA=797 nB=797 | outage A 556 B 797 | A-B -241 CI[-402,-81] UNR[-402.000,-81.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 8 B 3 | A-B +5 CI[-4,+15] UNR[-4.000,15.000] draws<0=286 =0=148 >0=1566 clusters=4
  robot cloud on-time  nA=12 nB=12 | outage A 7 B 12 | A-B -5 CI[-10,+0] UNR[-10.000,0.000] draws<0=1882 =0=118 >0=0 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 12 | A-B -3 CI[-6,+0] UNR[-6.000,0.000] draws<0=1938 =0=62 >0=0 clusters=12
  dashcam within_L     nA=386 nB=386 | outage A 225 B 386 | A-B -161 CI[-269,-71] UNR[-269.000,-71.000] draws<0=2000 =0=0 >0=0 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 35 B 17 | A-B +18 CI[-8,+46] UNR[-8.000,46.000] draws<0=163 =0=35 >0=1802 clusters=15
  robot cloud on-time  nA=67 nB=67 | outage A 50 B 67 | A-B -17 CI[-26,-8] UNR[-26.000,-8.000] draws<0=2000 =0=0 >0=0 clusters=15
  SS on-time (scorer)  nA=60 nB=60 | outage A 49 B 60 | A-B -11 CI[-17,-5] UNR[-17.000,-5.000] draws<0=2000 =0=0 >0=0 clusters=60
  dashcam within_L     nA=1984 nB=1984 | outage A 1187 B 1984 | A-B -797 CI[-1095,-453] UNR[-1095.000,-453.000] draws<0=2000 =0=0 >0=0 clusters=6
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 133 B 69 | A-B +64 CI[+23,+110] UNR[23.000,110.000] draws<0=1 =0=0 >0=1999 clusters=47
  robot cloud on-time  nA=283 nB=283 | outage A 149 B 243 | A-B -94 CI[-127,-63] UNR[-127.000,-63.000] draws<0=2000 =0=0 >0=0 clusters=47
  SS on-time (scorer)  nA=237 nB=237 | outage A 191 B 237 | A-B -46 CI[-58,-34] UNR[-58.000,-34.000] draws<0=2000 =0=0 >0=0 clusters=237
  dashcam within_L     nA=7850 nB=7850 | outage A 5066 B 7836 | A-B -2770 CI[-3682,-1921] UNR[-3682.000,-1921.000] draws<0=2000 =0=0 >0=0 clusters=20
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 out_streamscout_4_w120.json: robot[120] 6/26; robot[whole] 69/283; cloud[120] 26/26; cloud[whole] 243/283; SS[120] 24/24; SS[whole] 237/237; dashcam[120] 797/797; dashcam[whole] 7836/7850
==== COVEX f0 minus mooncake (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 17 | A-B +2 CI[-3,+9] UNR[-3.000,9.000] draws<0=522 =0=229 >0=1249 clusters=7
  robot cloud on-time  nA=26 nB=26 | outage A 21 B 8 | A-B +13 CI[+6,+21] UNR[6.000,21.000] draws<0=0 =0=0 >0=2000 clusters=7
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 22 | A-B -1 CI[-6,+3] UNR[-6.000,3.000] draws<0=1168 =0=344 >0=488 clusters=24
  dashcam within_L     nA=797 nB=797 | outage A 566 B 716 | A-B -150 CI[-375,-18] UNR[-375.000,-18.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 10 B 10 | A-B +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=4
  robot cloud on-time  nA=12 nB=12 | outage A 7 B 3 | A-B +4 CI[+1,+7] UNR[1.000,7.000] draws<0=0 =0=6 >0=1994 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 12 | A-B -3 CI[-6,+0] UNR[-6.000,0.000] draws<0=1929 =0=71 >0=0 clusters=12
  dashcam within_L     nA=386 nB=386 | outage A 220 B 364 | A-B -144 CI[-216,-67] UNR[-216.000,-67.000] draws<0=2000 =0=0 >0=0 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 38 B 37 | A-B +1 CI[-11,+11] UNR[-11.000,11.000] draws<0=723 =0=159 >0=1118 clusters=15
  robot cloud on-time  nA=67 nB=67 | outage A 41 B 17 | A-B +24 CI[+11,+40] UNR[11.000,40.000] draws<0=0 =0=0 >0=2000 clusters=15
  SS on-time (scorer)  nA=60 nB=60 | outage A 46 B 52 | A-B -6 CI[-14,+2] UNR[-14.000,2.000] draws<0=1847 =0=50 >0=103 clusters=60
  dashcam within_L     nA=1984 nB=1984 | outage A 1054 B 1696 | A-B -642 CI[-926,-327] UNR[-926.000,-327.000] draws<0=2000 =0=0 >0=0 clusters=6
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 134 B 108 | A-B +26 CI[+1,+56] UNR[1.000,56.000] draws<0=33 =0=6 >0=1961 clusters=47
  robot cloud on-time  nA=283 nB=283 | outage A 133 B 43 | A-B +90 CI[+59,+128] UNR[59.000,128.000] draws<0=0 =0=0 >0=2000 clusters=47
  SS on-time (scorer)  nA=237 nB=237 | outage A 176 B 211 | A-B -35 CI[-51,-18] UNR[-51.000,-18.000] draws<0=2000 =0=0 >0=0 clusters=237
  dashcam within_L     nA=7850 nB=7850 | outage A 4561 B 6652 | A-B -2091 CI[-3254,-942] UNR[-3254.000,-942.000] draws<0=1999 =0=0 >0=1 clusters=20
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 out_mooncake_4_w120.json: robot[120] 18/26; robot[whole] 111/283; cloud[120] 9/26; cloud[whole] 53/283; SS[120] 22/24; SS[whole] 211/237; dashcam[120] 735/797; dashcam[whole] 6656/7850
==== COVEX a4 minus mooncake (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 17 B 17 | A-B +0 CI[-7,+8] UNR[-7.000,8.000] draws<0=968 =0=193 >0=839 clusters=7
  robot cloud on-time  nA=26 nB=26 | outage A 21 B 8 | A-B +13 CI[+2,+24] UNR[2.000,24.000] draws<0=16 =0=19 >0=1965 clusters=7
  SS on-time (scorer)  nA=24 nB=24 | outage A 21 B 22 | A-B -1 CI[-5,+3] UNR[-5.000,3.000] draws<0=1161 =0=357 >0=482 clusters=24
  dashcam within_L     nA=797 nB=797 | outage A 556 B 716 | A-B -160 CI[-366,-51] UNR[-366.000,-51.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=12 nB=12 | outage A 8 B 10 | A-B -2 CI[-6,+0] UNR[-6.000,0.000] draws<0=1382 =0=618 >0=0 clusters=4
  robot cloud on-time  nA=12 nB=12 | outage A 7 B 3 | A-B +4 CI[-4,+10] UNR[-4.000,10.000] draws<0=247 =0=149 >0=1604 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 9 B 12 | A-B -3 CI[-6,+0] UNR[-6.000,0.000] draws<0=1938 =0=62 >0=0 clusters=12
  dashcam within_L     nA=386 nB=386 | outage A 225 B 364 | A-B -139 CI[-226,-60] UNR[-226.000,-60.000] draws<0=2000 =0=0 >0=0 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=67 nB=67 | outage A 35 B 37 | A-B -2 CI[-18,+10] UNR[-18.000,10.000] draws<0=1118 =0=121 >0=761 clusters=15
  robot cloud on-time  nA=67 nB=67 | outage A 50 B 17 | A-B +33 CI[+15,+55] UNR[15.000,55.000] draws<0=0 =0=0 >0=2000 clusters=15
  SS on-time (scorer)  nA=60 nB=60 | outage A 49 B 52 | A-B -3 CI[-10,+5] UNR[-10.000,5.000] draws<0=1499 =0=152 >0=349 clusters=60
  dashcam within_L     nA=1984 nB=1984 | outage A 1187 B 1696 | A-B -509 CI[-719,-274] UNR[-719.000,-274.000] draws<0=2000 =0=0 >0=0 clusters=6
== window WHOLE RUN
  robot cbd            nA=283 nB=283 | outage A 133 B 108 | A-B +25 CI[-10,+59] UNR[-10.000,59.000] draws<0=156 =0=13 >0=1831 clusters=47
  robot cloud on-time  nA=283 nB=283 | outage A 149 B 43 | A-B +106 CI[+68,+153] UNR[68.000,153.000] draws<0=0 =0=0 >0=2000 clusters=47
  SS on-time (scorer)  nA=237 nB=237 | outage A 191 B 211 | A-B -20 CI[-35,-5] UNR[-35.000,-5.000] draws<0=1993 =0=4 >0=3 clusters=237
  dashcam within_L     nA=7850 nB=7850 | outage A 5066 B 6652 | A-B -1586 CI[-2523,-645] UNR[-2523.000,-645.000] draws<0=1998 =0=0 >0=2 clusters=20
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  B seed 4 out_mooncake_4_w120.json: robot[120] 18/26; robot[whole] 111/283; cloud[120] 9/26; cloud[whole] 53/283; SS[120] 22/24; SS[whole] 211/237; dashcam[120] 735/797; dashcam[whole] 6656/7850
################ SEEDS: 5  (UNR = unrounded 2.5/97.5 pct of 2000 draws, seed 7; strict: CI excludes 0 = whole unrounded interval strictly one side). Baseline cells have NO control except mooncake s4: 'own control' columns for baselines are the outage cell itself (ignore).
==== COVEX f0 minus streamscout (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 5 | A-B +14 CI[+0,+28] UNR[0.000,28.000] draws<0=33 =0=23 >0=1944 clusters=6
  robot cloud on-time  nA=26 nB=26 | outage A 12 B 26 | A-B -14 CI[-19,-9] UNR[-19.000,-9.000] draws<0=2000 =0=0 >0=0 clusters=6
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 24 | A-B -9 CI[-14,-5] UNR[-14.000,-5.000] draws<0=2000 =0=0 >0=0 clusters=24
  dashcam within_L     nA=790 nB=790 | outage A 180 B 789 | A-B -609 CI[-819,-231] UNR[-819.000,-231.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 6 B 2 | A-B +4 CI[+0,+8] UNR[0.000,8.000] draws<0=0 =0=122 >0=1878 clusters=4
  robot cloud on-time  nA=10 nB=10 | outage A 6 B 10 | A-B -4 CI[-9,+0] UNR[-9.000,0.000] draws<0=1890 =0=110 >0=0 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 6 B 12 | A-B -6 CI[-10,-3] UNR[-10.000,-3.000] draws<0=2000 =0=0 >0=0 clusters=12
  dashcam within_L     nA=393 nB=393 | outage A 121 B 392 | A-B -271 CI[-392,-142] UNR[-392.000,-142.000] draws<0=2000 =0=0 >0=0 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 6 | A-B +13 CI[-2,+28] UNR[-2.000,28.000] draws<0=89 =0=25 >0=1886 clusters=6
  robot cloud on-time  nA=28 nB=28 | outage A 12 B 28 | A-B -16 CI[-21,-11] UNR[-21.000,-11.000] draws<0=2000 =0=0 >0=0 clusters=6
  SS on-time (scorer)  nA=26 nB=26 | outage A 15 B 26 | A-B -11 CI[-16,-6] UNR[-16.000,-6.000] draws<0=2000 =0=0 >0=0 clusters=26
  dashcam within_L     nA=865 nB=865 | outage A 225 B 857 | A-B -632 CI[-846,-231] UNR[-846.000,-231.000] draws<0=2000 =0=0 >0=0 clusters=3
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 48 | A-B +57 CI[+23,+96] UNR[23.000,96.000] draws<0=1 =0=0 >0=1999 clusters=40
  robot cloud on-time  nA=222 nB=222 | outage A 122 B 193 | A-B -71 CI[-111,-41] UNR[-111.000,-41.000] draws<0=2000 =0=0 >0=0 clusters=40
  SS on-time (scorer)  nA=240 nB=240 | outage A 216 B 240 | A-B -24 CI[-34,-15] UNR[-34.000,-15.000] draws<0=2000 =0=0 >0=0 clusters=240
  dashcam within_L     nA=7862 nB=7862 | outage A 5732 B 7846 | A-B -2114 CI[-2881,-1425] UNR[-2881.000,-1425.000] draws<0=2000 =0=0 >0=0 clusters=20
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_streamscout_5_w120.json: robot[120] 5/26; robot[whole] 48/222; cloud[120] 26/26; cloud[whole] 193/222; SS[120] 24/24; SS[whole] 240/240; dashcam[120] 789/790; dashcam[whole] 7846/7862
==== COVEX a4 minus streamscout (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 5 | A-B +14 CI[-3,+30] UNR[-3.000,30.000] draws<0=101 =0=24 >0=1875 clusters=6
  robot cloud on-time  nA=26 nB=26 | outage A 19 B 26 | A-B -7 CI[-12,-2] UNR[-12.000,-2.000] draws<0=1994 =0=6 >0=0 clusters=6
  SS on-time (scorer)  nA=24 nB=24 | outage A 20 B 24 | A-B -4 CI[-8,-1] UNR[-8.000,-1.000] draws<0=1973 =0=27 >0=0 clusters=24
  dashcam within_L     nA=790 nB=790 | outage A 530 B 789 | A-B -259 CI[-420,-126] UNR[-420.000,-126.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 7 B 2 | A-B +5 CI[+2,+8] UNR[2.000,8.000] draws<0=0 =0=6 >0=1994 clusters=4
  robot cloud on-time  nA=10 nB=10 | outage A 5 B 10 | A-B -5 CI[-10,-1] UNR[-10.000,-1.000] draws<0=1991 =0=9 >0=0 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 8 B 12 | A-B -4 CI[-7,-1] UNR[-7.000,-1.000] draws<0=1982 =0=18 >0=0 clusters=12
  dashcam within_L     nA=393 nB=393 | outage A 189 B 392 | A-B -203 CI[-310,-117] UNR[-310.000,-117.000] draws<0=2000 =0=0 >0=0 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 6 | A-B +13 CI[-5,+30] UNR[-5.000,30.000] draws<0=156 =0=23 >0=1821 clusters=6
  robot cloud on-time  nA=28 nB=28 | outage A 19 B 28 | A-B -9 CI[-14,-4] UNR[-14.000,-4.000] draws<0=2000 =0=0 >0=0 clusters=6
  SS on-time (scorer)  nA=26 nB=26 | outage A 22 B 26 | A-B -4 CI[-8,-1] UNR[-8.000,-1.000] draws<0=1969 =0=31 >0=0 clusters=26
  dashcam within_L     nA=865 nB=865 | outage A 573 B 857 | A-B -284 CI[-420,-201] UNR[-420.000,-201.000] draws<0=2000 =0=0 >0=0 clusters=3
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 48 | A-B +57 CI[+24,+93] UNR[24.000,93.000] draws<0=2 =0=0 >0=1998 clusters=40
  robot cloud on-time  nA=222 nB=222 | outage A 127 B 193 | A-B -66 CI[-105,-35] UNR[-105.000,-35.000] draws<0=2000 =0=0 >0=0 clusters=40
  SS on-time (scorer)  nA=240 nB=240 | outage A 217 B 240 | A-B -23 CI[-32,-14] UNR[-32.000,-14.000] draws<0=2000 =0=0 >0=0 clusters=240
  dashcam within_L     nA=7862 nB=7862 | outage A 5725 B 7846 | A-B -2121 CI[-2916,-1455] UNR[-2916.000,-1455.000] draws<0=2000 =0=0 >0=0 clusters=20
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_streamscout_5_w120.json: robot[120] 5/26; robot[whole] 48/222; cloud[120] 26/26; cloud[whole] 193/222; SS[120] 24/24; SS[whole] 240/240; dashcam[120] 789/790; dashcam[whole] 7846/7862
==== COVEX f0 minus mooncake (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 19 | A-B +0 CI[-3,+3] UNR[-3.000,3.000] draws<0=729 =0=582 >0=689 clusters=6
  robot cloud on-time  nA=26 nB=26 | outage A 12 B 10 | A-B +2 CI[-2,+6] UNR[-2.000,6.000] draws<0=298 =0=265 >0=1437 clusters=6
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 22 | A-B -7 CI[-12,-2] UNR[-12.000,-2.000] draws<0=1987 =0=10 >0=3 clusters=24
  dashcam within_L     nA=790 nB=790 | outage A 180 B 674 | A-B -494 CI[-777,-99] UNR[-777.000,-99.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 6 B 6 | A-B +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=4
  robot cloud on-time  nA=10 nB=10 | outage A 6 B 4 | A-B +2 CI[+0,+6] UNR[0.000,6.000] draws<0=0 =0=659 >0=1341 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 6 B 10 | A-B -4 CI[-8,+0] UNR[-8.000,0.000] draws<0=1885 =0=74 >0=41 clusters=12
  dashcam within_L     nA=393 nB=393 | outage A 121 B 308 | A-B -187 CI[-308,-67] UNR[-308.000,-67.000] draws<0=2000 =0=0 >0=0 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 19 | A-B +0 CI[-3,+3] UNR[-3.000,3.000] draws<0=729 =0=582 >0=689 clusters=6
  robot cloud on-time  nA=28 nB=28 | outage A 12 B 10 | A-B +2 CI[-2,+6] UNR[-2.000,6.000] draws<0=298 =0=265 >0=1437 clusters=6
  SS on-time (scorer)  nA=26 nB=26 | outage A 15 B 24 | A-B -9 CI[-15,-4] UNR[-15.000,-4.000] draws<0=1999 =0=1 >0=0 clusters=26
  dashcam within_L     nA=865 nB=865 | outage A 225 B 745 | A-B -520 CI[-855,-99] UNR[-855.000,-99.000] draws<0=2000 =0=0 >0=0 clusters=3
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 83 | A-B +22 CI[+1,+48] UNR[1.000,48.000] draws<0=34 =0=9 >0=1957 clusters=40
  robot cloud on-time  nA=222 nB=222 | outage A 122 B 43 | A-B +79 CI[+47,+119] UNR[47.000,119.000] draws<0=0 =0=0 >0=2000 clusters=40
  SS on-time (scorer)  nA=240 nB=240 | outage A 216 B 223 | A-B -7 CI[-19,+5] UNR[-19.000,5.000] draws<0=1733 =0=66 >0=201 clusters=240
  dashcam within_L     nA=7862 nB=7862 | outage A 5732 B 7129 | A-B -1397 CI[-2225,-607] UNR[-2225.000,-607.000] draws<0=2000 =0=0 >0=0 clusters=20
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_mooncake_5_w120.json: robot[120] 19/26; robot[whole] 83/222; cloud[120] 10/26; cloud[whole] 43/222; SS[120] 22/24; SS[whole] 223/240; dashcam[120] 674/790; dashcam[whole] 7129/7862
==== COVEX a4 minus mooncake (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=26 nB=26 | outage A 19 B 19 | A-B +0 CI[-6,+6] UNR[-6.000,6.000] draws<0=738 =0=541 >0=721 clusters=6
  robot cloud on-time  nA=26 nB=26 | outage A 19 B 10 | A-B +9 CI[+2,+17] UNR[2.000,17.000] draws<0=0 =0=27 >0=1973 clusters=6
  SS on-time (scorer)  nA=24 nB=24 | outage A 20 B 22 | A-B -2 CI[-6,+2] UNR[-6.000,2.000] draws<0=1572 =0=256 >0=172 clusters=24
  dashcam within_L     nA=790 nB=790 | outage A 530 B 674 | A-B -144 CI[-207,-99] UNR[-207.000,-99.000] draws<0=2000 =0=0 >0=0 clusters=3
== window fixed [R,R+60]
  robot cbd            nA=10 nB=10 | outage A 7 B 6 | A-B +1 CI[+0,+3] UNR[0.000,3.000] draws<0=0 =0=612 >0=1388 clusters=4
  robot cloud on-time  nA=10 nB=10 | outage A 5 B 4 | A-B +1 CI[-2,+4] UNR[-2.000,4.000] draws<0=383 =0=399 >0=1218 clusters=4
  SS on-time (scorer)  nA=12 nB=12 | outage A 8 B 10 | A-B -2 CI[-6,+2] UNR[-6.000,2.000] draws<0=1562 =0=258 >0=180 clusters=12
  dashcam within_L     nA=393 nB=393 | outage A 189 B 308 | A-B -119 CI[-170,-56] UNR[-170.000,-56.000] draws<0=1999 =0=0 >0=1 clusters=7
== window fixed [R,R+300]
  robot cbd            nA=28 nB=28 | outage A 19 B 19 | A-B +0 CI[-6,+6] UNR[-6.000,6.000] draws<0=738 =0=541 >0=721 clusters=6
  robot cloud on-time  nA=28 nB=28 | outage A 19 B 10 | A-B +9 CI[+2,+17] UNR[2.000,17.000] draws<0=0 =0=27 >0=1973 clusters=6
  SS on-time (scorer)  nA=26 nB=26 | outage A 22 B 24 | A-B -2 CI[-6,+2] UNR[-6.000,2.000] draws<0=1572 =0=235 >0=193 clusters=26
  dashcam within_L     nA=865 nB=865 | outage A 573 B 745 | A-B -172 CI[-210,-99] UNR[-210.000,-99.000] draws<0=2000 =0=0 >0=0 clusters=3
== window WHOLE RUN
  robot cbd            nA=222 nB=222 | outage A 105 B 83 | A-B +22 CI[+7,+39] UNR[7.000,39.000] draws<0=0 =0=0 >0=2000 clusters=40
  robot cloud on-time  nA=222 nB=222 | outage A 127 B 43 | A-B +84 CI[+53,+117] UNR[53.000,117.000] draws<0=0 =0=0 >0=2000 clusters=40
  SS on-time (scorer)  nA=240 nB=240 | outage A 217 B 223 | A-B -6 CI[-17,+6] UNR[-17.000,6.000] draws<0=1655 =0=91 >0=254 clusters=240
  dashcam within_L     nA=7862 nB=7862 | outage A 5725 B 7129 | A-B -1404 CI[-2278,-624] UNR[-2278.000,-624.000] draws<0=2000 =0=0 >0=0 clusters=20
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 5 out_mooncake_5_w120.json: robot[120] 19/26; robot[whole] 83/222; cloud[120] 10/26; cloud[whole] 43/222; SS[120] 22/24; SS[whole] 223/240; dashcam[120] 674/790; dashcam[whole] 7129/7862
################ SEEDS: 4 5  (UNR = unrounded 2.5/97.5 pct of 2000 draws, seed 7; strict: CI excludes 0 = whole unrounded interval strictly one side). Baseline cells have NO control except mooncake s4: 'own control' columns for baselines are the outage cell itself (ignore).
==== COVEX f0 minus streamscout (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 38 B 11 | A-B +27 CI[+5,+50] UNR[5.000,50.000] draws<0=8 =0=8 >0=1984 clusters=13
  robot cloud on-time  nA=52 nB=52 | outage A 33 B 52 | A-B -19 CI[-28,-10] UNR[-28.000,-10.000] draws<0=2000 =0=0 >0=0 clusters=13
  SS on-time (scorer)  nA=48 nB=48 | outage A 36 B 48 | A-B -12 CI[-18,-6] UNR[-18.000,-6.000] draws<0=2000 =0=0 >0=0 clusters=48
  dashcam within_L     nA=1587 nB=1587 | outage A 746 B 1586 | A-B -840 CI[-1292,-402] UNR[-1292.000,-402.000] draws<0=2000 =0=0 >0=0 clusters=6
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 16 B 5 | A-B +11 CI[+4,+21] UNR[4.000,21.000] draws<0=0 =0=7 >0=1993 clusters=8
  robot cloud on-time  nA=22 nB=22 | outage A 13 B 22 | A-B -9 CI[-16,-3] UNR[-16.000,-3.000] draws<0=1998 =0=2 >0=0 clusters=8
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 24 | A-B -9 CI[-14,-5] UNR[-14.000,-5.000] draws<0=2000 =0=0 >0=0 clusters=24
  dashcam within_L     nA=779 nB=779 | outage A 341 B 778 | A-B -437 CI[-610,-270] UNR[-610.000,-270.000] draws<0=2000 =0=0 >0=0 clusters=14
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 57 B 23 | A-B +34 CI[+8,+62] UNR[8.000,62.000] draws<0=10 =0=2 >0=1988 clusters=21
  robot cloud on-time  nA=95 nB=95 | outage A 53 B 95 | A-B -42 CI[-54,-30] UNR[-54.000,-30.000] draws<0=2000 =0=0 >0=0 clusters=21
  SS on-time (scorer)  nA=86 nB=86 | outage A 61 B 86 | A-B -25 CI[-33,-17] UNR[-33.000,-17.000] draws<0=2000 =0=0 >0=0 clusters=86
  dashcam within_L     nA=2849 nB=2849 | outage A 1279 B 2841 | A-B -1562 CI[-2091,-1024] UNR[-2091.000,-1024.000] draws<0=2000 =0=0 >0=0 clusters=9
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 239 B 117 | A-B +122 CI[+71,+179] UNR[71.000,179.000] draws<0=0 =0=0 >0=2000 clusters=87
  robot cloud on-time  nA=505 nB=505 | outage A 255 B 436 | A-B -181 CI[-232,-136] UNR[-232.000,-136.000] draws<0=2000 =0=0 >0=0 clusters=87
  SS on-time (scorer)  nA=477 nB=477 | outage A 392 B 477 | A-B -85 CI[-102,-69] UNR[-102.000,-69.000] draws<0=2000 =0=0 >0=0 clusters=477
  dashcam within_L     nA=15712 nB=15712 | outage A 10293 B 15682 | A-B -5389 CI[-6654,-4109] UNR[-6654.000,-4109.000] draws<0=2000 =0=0 >0=0 clusters=40
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 out_streamscout_4_w120.json: robot[120] 6/26; robot[whole] 69/283; cloud[120] 26/26; cloud[whole] 243/283; SS[120] 24/24; SS[whole] 237/237; dashcam[120] 797/797; dashcam[whole] 7836/7850
  B seed 5 out_streamscout_5_w120.json: robot[120] 5/26; robot[whole] 48/222; cloud[120] 26/26; cloud[whole] 193/222; SS[120] 24/24; SS[whole] 240/240; dashcam[120] 789/790; dashcam[whole] 7846/7862
==== COVEX a4 minus streamscout (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 36 B 11 | A-B +25 CI[+1,+51] UNR[1.000,51.000] draws<0=45 =0=5 >0=1950 clusters=13
  robot cloud on-time  nA=52 nB=52 | outage A 40 B 52 | A-B -12 CI[-20,-4] UNR[-20.000,-4.000] draws<0=2000 =0=0 >0=0 clusters=13
  SS on-time (scorer)  nA=48 nB=48 | outage A 41 B 48 | A-B -7 CI[-12,-3] UNR[-12.000,-3.000] draws<0=1999 =0=1 >0=0 clusters=48
  dashcam within_L     nA=1587 nB=1587 | outage A 1086 B 1586 | A-B -500 CI[-702,-307] UNR[-702.000,-307.000] draws<0=2000 =0=0 >0=0 clusters=6
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 15 B 5 | A-B +10 CI[+0,+21] UNR[0.000,21.000] draws<0=42 =0=23 >0=1935 clusters=8
  robot cloud on-time  nA=22 nB=22 | outage A 12 B 22 | A-B -10 CI[-17,-4] UNR[-17.000,-4.000] draws<0=1999 =0=1 >0=0 clusters=8
  SS on-time (scorer)  nA=24 nB=24 | outage A 17 B 24 | A-B -7 CI[-12,-3] UNR[-12.000,-3.000] draws<0=1999 =0=1 >0=0 clusters=24
  dashcam within_L     nA=779 nB=779 | outage A 414 B 778 | A-B -364 CI[-519,-229] UNR[-519.000,-229.000] draws<0=2000 =0=0 >0=0 clusters=14
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 54 B 23 | A-B +31 CI[+0,+62] UNR[0.000,62.000] draws<0=47 =0=4 >0=1949 clusters=21
  robot cloud on-time  nA=95 nB=95 | outage A 69 B 95 | A-B -26 CI[-37,-16] UNR[-37.000,-16.000] draws<0=2000 =0=0 >0=0 clusters=21
  SS on-time (scorer)  nA=86 nB=86 | outage A 71 B 86 | A-B -15 CI[-22,-8] UNR[-22.000,-8.000] draws<0=2000 =0=0 >0=0 clusters=86
  dashcam within_L     nA=2849 nB=2849 | outage A 1760 B 2841 | A-B -1081 CI[-1455,-722] UNR[-1455.000,-722.000] draws<0=2000 =0=0 >0=0 clusters=9
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 238 B 117 | A-B +121 CI[+66,+177] UNR[66.000,177.000] draws<0=0 =0=0 >0=2000 clusters=87
  robot cloud on-time  nA=505 nB=505 | outage A 276 B 436 | A-B -160 CI[-213,-115] UNR[-213.000,-115.000] draws<0=2000 =0=0 >0=0 clusters=87
  SS on-time (scorer)  nA=477 nB=477 | outage A 408 B 477 | A-B -69 CI[-85,-54] UNR[-85.000,-54.000] draws<0=2000 =0=0 >0=0 clusters=477
  dashcam within_L     nA=15712 nB=15712 | outage A 10791 B 15682 | A-B -4891 CI[-6011,-3758] UNR[-6011.000,-3758.000] draws<0=2000 =0=0 >0=0 clusters=40
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 out_streamscout_4_w120.json: robot[120] 6/26; robot[whole] 69/283; cloud[120] 26/26; cloud[whole] 243/283; SS[120] 24/24; SS[whole] 237/237; dashcam[120] 797/797; dashcam[whole] 7836/7850
  B seed 5 out_streamscout_5_w120.json: robot[120] 5/26; robot[whole] 48/222; cloud[120] 26/26; cloud[whole] 193/222; SS[120] 24/24; SS[whole] 240/240; dashcam[120] 789/790; dashcam[whole] 7846/7862
==== COVEX f0 minus mooncake (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 38 B 36 | A-B +2 CI[-4,+10] UNR[-4.000,10.000] draws<0=488 =0=239 >0=1273 clusters=13
  robot cloud on-time  nA=52 nB=52 | outage A 33 B 18 | A-B +15 CI[+6,+26] UNR[6.000,26.000] draws<0=0 =0=0 >0=2000 clusters=13
  SS on-time (scorer)  nA=48 nB=48 | outage A 36 B 44 | A-B -8 CI[-15,-1] UNR[-15.000,-1.000] draws<0=1965 =0=18 >0=17 clusters=48
  dashcam within_L     nA=1587 nB=1587 | outage A 746 B 1390 | A-B -644 CI[-1130,-221] UNR[-1130.000,-221.000] draws<0=2000 =0=0 >0=0 clusters=6
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 16 B 16 | A-B +0 CI[+0,+0] UNR[0.000,0.000] draws<0=0 =0=2000 >0=0 clusters=8
  robot cloud on-time  nA=22 nB=22 | outage A 13 B 7 | A-B +6 CI[+2,+11] UNR[2.000,11.000] draws<0=0 =0=5 >0=1995 clusters=8
  SS on-time (scorer)  nA=24 nB=24 | outage A 15 B 22 | A-B -7 CI[-12,-2] UNR[-12.000,-2.000] draws<0=1989 =0=8 >0=3 clusters=24
  dashcam within_L     nA=779 nB=779 | outage A 341 B 672 | A-B -331 CI[-478,-190] UNR[-478.000,-190.000] draws<0=2000 =0=0 >0=0 clusters=14
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 57 B 56 | A-B +1 CI[-10,+11] UNR[-10.000,11.000] draws<0=736 =0=135 >0=1129 clusters=21
  robot cloud on-time  nA=95 nB=95 | outage A 53 B 27 | A-B +26 CI[+12,+43] UNR[12.000,43.000] draws<0=0 =0=0 >0=2000 clusters=21
  SS on-time (scorer)  nA=86 nB=86 | outage A 61 B 76 | A-B -15 CI[-25,-5] UNR[-25.000,-5.000] draws<0=1996 =0=2 >0=2 clusters=86
  dashcam within_L     nA=2849 nB=2849 | outage A 1279 B 2441 | A-B -1162 CI[-1674,-668] UNR[-1674.000,-668.000] draws<0=2000 =0=0 >0=0 clusters=9
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 239 B 191 | A-B +48 CI[+15,+88] UNR[15.000,88.000] draws<0=3 =0=0 >0=1997 clusters=87
  robot cloud on-time  nA=505 nB=505 | outage A 255 B 86 | A-B +169 CI[+122,+221] UNR[122.000,221.000] draws<0=0 =0=0 >0=2000 clusters=87
  SS on-time (scorer)  nA=477 nB=477 | outage A 392 B 434 | A-B -42 CI[-63,-22] UNR[-63.000,-22.000] draws<0=2000 =0=0 >0=0 clusters=477
  dashcam within_L     nA=15712 nB=15712 | outage A 10293 B 13781 | A-B -3488 CI[-4864,-2055] UNR[-4864.000,-2055.000] draws<0=2000 =0=0 >0=0 clusters=40
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_f0_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_f0_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 out_mooncake_4_w120.json: robot[120] 18/26; robot[whole] 111/283; cloud[120] 9/26; cloud[whole] 53/283; SS[120] 22/24; SS[whole] 211/237; dashcam[120] 735/797; dashcam[whole] 6656/7850
  B seed 5 out_mooncake_5_w120.json: robot[120] 19/26; robot[whole] 83/222; cloud[120] 10/26; cloud[whole] 43/222; SS[120] 22/24; SS[whole] 223/240; dashcam[120] 674/790; dashcam[whole] 7129/7862
==== COVEX a4 minus mooncake (absolute, outage cells; positive = COVEX better)
== window fixed [R,R+120]
  robot cbd            nA=52 nB=52 | outage A 36 B 36 | A-B +0 CI[-9,+10] UNR[-9.000,10.000] draws<0=920 =0=173 >0=907 clusters=13
  robot cloud on-time  nA=52 nB=52 | outage A 40 B 18 | A-B +22 CI[+8,+37] UNR[8.000,37.000] draws<0=1 =0=1 >0=1998 clusters=13
  SS on-time (scorer)  nA=48 nB=48 | outage A 41 B 44 | A-B -3 CI[-9,+3] UNR[-9.000,3.000] draws<0=1601 =0=162 >0=237 clusters=48
  dashcam within_L     nA=1587 nB=1587 | outage A 1086 B 1390 | A-B -304 CI[-493,-158] UNR[-493.000,-158.000] draws<0=2000 =0=0 >0=0 clusters=6
== window fixed [R,R+60]
  robot cbd            nA=22 nB=22 | outage A 15 B 16 | A-B -1 CI[-6,+3] UNR[-6.000,3.000] draws<0=1124 =0=351 >0=525 clusters=8
  robot cloud on-time  nA=22 nB=22 | outage A 12 B 7 | A-B +5 CI[-4,+13] UNR[-4.000,13.000] draws<0=204 =0=84 >0=1712 clusters=8
  SS on-time (scorer)  nA=24 nB=24 | outage A 17 B 22 | A-B -5 CI[-10,+0] UNR[-10.000,0.000] draws<0=1948 =0=36 >0=16 clusters=24
  dashcam within_L     nA=779 nB=779 | outage A 414 B 672 | A-B -258 CI[-365,-162] UNR[-365.000,-162.000] draws<0=2000 =0=0 >0=0 clusters=14
== window fixed [R,R+300]
  robot cbd            nA=95 nB=95 | outage A 54 B 56 | A-B -2 CI[-19,+12] UNR[-19.000,12.000] draws<0=1092 =0=106 >0=802 clusters=21
  robot cloud on-time  nA=95 nB=95 | outage A 69 B 27 | A-B +42 CI[+21,+65] UNR[21.000,65.000] draws<0=0 =0=0 >0=2000 clusters=21
  SS on-time (scorer)  nA=86 nB=86 | outage A 71 B 76 | A-B -5 CI[-13,+4] UNR[-13.000,4.000] draws<0=1718 =0=97 >0=185 clusters=86
  dashcam within_L     nA=2849 nB=2849 | outage A 1760 B 2441 | A-B -681 CI[-922,-425] UNR[-922.000,-425.000] draws<0=2000 =0=0 >0=0 clusters=9
== window WHOLE RUN
  robot cbd            nA=505 nB=505 | outage A 238 B 191 | A-B +47 CI[+9,+88] UNR[9.000,88.000] draws<0=16 =0=2 >0=1982 clusters=87
  robot cloud on-time  nA=505 nB=505 | outage A 276 B 86 | A-B +190 CI[+140,+245] UNR[140.000,245.000] draws<0=0 =0=0 >0=2000 clusters=87
  SS on-time (scorer)  nA=477 nB=477 | outage A 408 B 434 | A-B -26 CI[-46,-6] UNR[-46.000,-6.000] draws<0=1987 =0=2 >0=11 clusters=477
  dashcam within_L     nA=15712 nB=15712 | outage A 10791 B 13781 | A-B -2990 CI[-4191,-1752] UNR[-4191.000,-1752.000] draws<0=2000 =0=0 >0=0 clusters=40
  A seed 4 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/netwin/out_a4_s4_t4075_w120.json: robot[120] 20/26; robot[whole] 154/283; cloud[120] 25/26; cloud[whole] 181/283; SS[120] 24/24; SS[whole] 199/237; dashcam[120] 692/797; dashcam[whole] 5343/7850
  A seed 5 /tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/s5net/out_a5_s5_t8805_w120.json: robot[120] 21/26; robot[whole] 109/222; cloud[120] 21/26; cloud[whole] 148/222; SS[120] 21/24; SS[whole] 211/240; dashcam[120] 326/790; dashcam[whole] 5025/7862
  B seed 4 out_mooncake_4_w120.json: robot[120] 18/26; robot[whole] 111/283; cloud[120] 9/26; cloud[whole] 53/283; SS[120] 22/24; SS[whole] 211/237; dashcam[120] 735/797; dashcam[whole] 6656/7850
  B seed 5 out_mooncake_5_w120.json: robot[120] 19/26; robot[whole] 83/222; cloud[120] 10/26; cloud[whole] 43/222; SS[120] 22/24; SS[whole] 223/240; dashcam[120] 674/790; dashcam[whole] 7129/7862
---- out_mooncake_4_w120.txt
== netwin mooncake_4  outage=mooncake_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link  control=mooncake_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30  t0=407.5 d=188.0 R=595.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 111 (committed robot_headline 0.392226 x n 283 = 111.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 211 (committed 211); within_L(outcomes) 216; dashcam within(1.0) 6656 vs within_L 6656 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 108 (headline 0.381625 x 283); classifier agree 283 of 283; SS on_time 211 (committed 211) within_L 217; dashcam within(1.0) 6652 vs within_L 6652
  same opportunity ids in both cells: robot 283/283, SS 237/237
---- out_mooncake_5_w120.txt
== netwin mooncake_5  outage=mooncake_n20_s5_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t8805_link  control=mooncake_n20_s5_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t8805_link  t0=880.5 d=188.0 R=1068.5
POSITIVE CONTROL control: robot cbd rows 222, cbd True 83 (committed robot_headline 0.373874 x n 222 = 83.0); sylib classifier correct==committed cbd on 222 of 222
  control SS: n 240 on_time 223 (committed 223); within_L(outcomes) 225; dashcam within(1.0) 7129 vs within_L 7129 of 7862 monitors
POSITIVE CONTROL outage: robot cbd rows 222 True 83 (headline 0.373874 x 222); classifier agree 222 of 222; SS on_time 223 (committed 223) within_L 225; dashcam within(1.0) 7129 vs within_L 7129
  same opportunity ids in both cells: robot 222/222, SS 240/240
---- out_streamscout_4_w120.txt
== netwin streamscout_4  outage=streamscout_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link  control=streamscout_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link  t0=407.5 d=188.0 R=595.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 69 (committed robot_headline 0.243816 x n 283 = 69.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 237 (committed 237); within_L(outcomes) 237; dashcam within(1.0) 7836 vs within_L 7836 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 69 (headline 0.243816 x 283); classifier agree 283 of 283; SS on_time 237 (committed 237) within_L 237; dashcam within(1.0) 7836 vs within_L 7836
  same opportunity ids in both cells: robot 283/283, SS 237/237
---- out_streamscout_5_w120.txt
== netwin streamscout_5  outage=streamscout_n20_s5_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t8805_link  control=streamscout_n20_s5_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t8805_link  t0=880.5 d=188.0 R=1068.5
POSITIVE CONTROL control: robot cbd rows 222, cbd True 48 (committed robot_headline 0.216216 x n 222 = 48.0); sylib classifier correct==committed cbd on 222 of 222
  control SS: n 240 on_time 240 (committed 240); within_L(outcomes) 240; dashcam within(1.0) 7846 vs within_L 7846 of 7862 monitors
POSITIVE CONTROL outage: robot cbd rows 222 True 48 (headline 0.216216 x 222); classifier agree 222 of 222; SS on_time 240 (committed 240) within_L 240; dashcam within(1.0) 7846 vs within_L 7846
  same opportunity ids in both cells: robot 222/222, SS 240/240
