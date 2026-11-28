== per 60s bin: chosen(state_action)/issued(touch) F0 A4 CT
    0-60    F0    0/   0 | A4    0/   0 | CT    0/   0 
   60-120   F0    0/   0 | A4    0/   0 | CT    0/   0 
  120-180   F0    0/   0 | A4    0/   0 | CT    0/   0 
  180-240   F0    0/   0 | A4    0/   0 | CT    0/   0 
  240-300   F0    0/   0 | A4    0/   0 | CT    0/   0 
  300-360   F0    0/   0 | A4    0/   0 | CT    0/   0 
  360-420   F0    0/   0 | A4    0/   0 | CT    0/   0  t0
  420-480   F0    0/   0 | A4    0/   0 | CT    0/   0 
  480-540   F0    0/   0 | A4    0/   0 | CT    0/   0 
  540-600   F0    0/   0 | A4    0/   0 | CT    0/   0  R
  600-660   F0  484/ 484 | A4  337/ 337 | CT    0/   0 
  660-720   F0  652/ 652 | A4  518/ 518 | CT    0/   0 
  720-780   F0  145/ 122 | A4   40/  40 | CT    0/   0 
  780-840   F0  440/  78 | A4    0/   0 | CT  536/ 536 
  840-900   F0 1136/1136 | A4   30/  30 | CT  596/ 596 
  900-960   F0  889/ 889 | A4  294/ 294 | CT  669/ 669 
  960-1020  F0  220/ 150 | A4   42/  42 | CT   64/  64 
 1020-1080  F0   34/  34 | A4    0/   0 | CT    0/   0 
 1080-1140  F0   62/  62 | A4   30/  30 | CT  382/ 382 
 1140-1200  F0    0/   0 | A4   72/  72 | CT  144/ 144 
 1200-1260  F0    0/   0 | A4    0/   0 | CT    0/   0 
totals {'F0': (4062, 3607), 'A4': (1363, 1363), 'CT': (2391, 2391)}
== touches issued by phase (pre<407.5, outage, post>=595.5)
F0 {'post': 3607}
A4 {'post': 1363}
CT {'post': 2391}
== F0 sessions seen 231 zero-touch 221
   robo005 s001 1190
   robo007 s001 1008
   robo000 s001 491
   robo013 s001 215
   robo001 s001 204
   robo008 s001 191
   robo009 s001 133
   robo010 s001 96
   robo012 s001 68
   robo003 s001 11
  distribution sorted: [1190, 1008, 491, 215, 204, 191, 133, 96, 68, 11]
== A4 sessions seen 245 zero-touch 240
   robo005 s001 895
   robo008 s001 323
   robo002 s002 95
   robo001 s001 43
   robo004 s001 7
  distribution sorted: [895, 323, 95, 43, 7]
== CT sessions seen 247 zero-touch 244
   robo007 s001 1434
   robo006 s002 526
   robo008 s001 431
  distribution sorted: [1434, 526, 431]
== touch cost
F0 n touch reqs 3607 unc tok/touch mean 28.67 med 11 max 21791 sum unc 103395 | robot non-touch unc 1709518 all-non-touch unc 4161202 | touch share of robot unc(touch+robot) 5.703% of all 2.424% | touch ttft mean 2.788s, sum server-s 10125.8 vs all-req server-s 14261.0 (71.0%)
   touch cache_path {'WARM': 3604, 'COLD': 3}
A4 n touch reqs 1363 unc tok/touch mean 33.37 med 3 max 21161 sum unc 45481 | robot non-touch unc 1534520 all-non-touch unc 4212453 | touch share of robot unc(touch+robot) 2.879% of all 1.068% | touch ttft mean 1.192s, sum server-s 1629.4 vs all-req server-s 4859.4 (33.5%)
   touch cache_path {'WARM': 1361, 'COLD': 2}
CT n touch reqs 2391 unc tok/touch mean 4.97 med 3.0 max 15 sum unc 11868 | robot non-touch unc 1416094 all-non-touch unc 4226946 | touch share of robot unc(touch+robot) 0.831% of all 0.280% | touch ttft mean 0.805s, sum server-s 1939.7 vs all-req server-s 4707.0 (41.2%)
   touch cache_path {'WARM': 2390, None: 1}

== per-session (s001 outage sessions + any touched): touches F0 / A4 / CT, F0-A4, post-R pieces F0/A4, post-600 pieces F0/A4, touch span F0 (first-last s)
robo000 s001 T F0/A4/CT 491 0 0 diff 491 | pieces>=R F0/A4 14 8 | >=600 12 5 | F0 span 838-888 | A4 span - 
robo001 s001 T F0/A4/CT 204 43 0 diff 161 | pieces>=R F0/A4 21 12 | >=600 18 9 | F0 span 889-995 | A4 span 897-976 
robo002 s001 T F0/A4/CT 0 0 0 diff 0 | pieces>=R F0/A4 5 5 | >=600 1 1 | F0 span - | A4 span - 
robo002 s002 T F0/A4/CT 0 95 0 diff -95 | pieces>=R F0/A4 11 13 | >=600 11 13 | F0 span - | A4 span 1096-1173 
robo003 s001 T F0/A4/CT 11 0 0 diff 11 | pieces>=R F0/A4 13 11 | >=600 11 9 | F0 span 988-989 | A4 span - 
robo004 s001 T F0/A4/CT 0 7 0 diff -7 | pieces>=R F0/A4 13 15 | >=600 12 14 | F0 span - | A4 span 1185-1185 
robo005 s001 T F0/A4/CT 1190 895 0 diff 295 | pieces>=R F0/A4 13 7 | >=600 9 3 | F0 span 611-732 | A4 span 621-732 
robo006 s001 T F0/A4/CT 0 0 0 diff 0 | pieces>=R F0/A4 5 6 | >=600 1 2 | F0 span - | A4 span - 
robo006 s002 T F0/A4/CT 0 0 526 diff 0 | pieces>=R F0/A4 10 11 | >=600 10 11 | F0 span - | A4 span - 
robo007 s001 T F0/A4/CT 1008 0 1434 diff 1008 | pieces>=R F0/A4 16 11 | >=600 12 7 | F0 span 822-938 | A4 span - 
robo008 s001 T F0/A4/CT 191 323 431 diff -132 | pieces>=R F0/A4 14 10 | >=600 11 8 | F0 span 921-954 | A4 span 917-965 
robo009 s001 T F0/A4/CT 133 0 0 diff 133 | pieces>=R F0/A4 18 10 | >=600 16 8 | F0 span 927-954 | A4 span - 
robo010 s001 T F0/A4/CT 96 0 0 diff 96 | pieces>=R F0/A4 16 14 | >=600 15 13 | F0 span 1040-1122 | A4 span - 
robo011 s001 T F0/A4/CT 0 0 0 diff 0 | pieces>=R F0/A4 8 8 | >=600 4 4 | F0 span - | A4 span - 
robo012 s001 T F0/A4/CT 68 0 0 diff 68 | pieces>=R F0/A4 13 5 | >=600 9 1 | F0 span 715-722 | A4 span - 
robo013 s001 T F0/A4/CT 215 0 0 diff 215 | pieces>=R F0/A4 13 9 | >=600 11 7 | F0 span 900-995 | A4 span - 
net extra F0-A4 2244 sum of positive per-session diffs 2478
G1 sample-released (cu sample release=True) sessions ['robo002', 'robo005', 'robo009', 'robo010'] F0 touches 1419 A4 895 net extra 524 share of net extra 23.4%
G2 F0 post-600 pieces > A4 sessions ['robo000', 'robo001', 'robo003', 'robo005', 'robo007', 'robo008', 'robo009', 'robo010', 'robo012', 'robo013'] F0 touches 3607 A4 1261 net extra 2346 share of net extra 104.5%
G3 all 14 outage s001 sessions (all had a catch-up window opened: reconnects_seen 14) sessions ['robo000', 'robo001', 'robo002', 'robo003', 'robo004', 'robo005', 'robo006', 'robo007', 'robo008', 'robo009', 'robo010', 'robo011', 'robo012', 'robo013'] F0 touches 3607 A4 1268 net extra 2339 share of net extra 104.2%
non-s001 sessions sessions [] F0 touches 0 A4 0 net extra 0 share of net extra 0.0%
F0 touches with >100 uncached tokens: 5 sum 69135 typical (<=100) sum 34260
    [('robo001', 988, 21791), ('robo003', 988, 9911), ('robo013', 988, 19001), ('robo001', 989, 1567), ('robo010', 1115, 16865)]
A4 touches with >100 uncached tokens: 2 sum 39442 typical (<=100) sum 6039
    [('robo001', 975, 21161), ('robo002', 1096, 18281)]
CT touches with >100 uncached tokens: 0 sum 0 typical (<=100) sum 11868
    []
F0 touch TTFT s: median 0.50 p90 3.72 max 38.61
A4 touch TTFT s: median 0.32 p90 2.66 max 21.04
CT touch TTFT s: median 0.36 p90 2.38 max 6.86

== cd state_action 1862 touch issued 1862
 top sessions [('robo006 s001', 1161), ('robo005 s002', 324), ('robo000 s002', 280), ('robo001 s001', 60), ('robo003 s001', 37)] n sessions touched 5
 per-60s issued [(780, 490), (840, 584), (900, 219), (960, 289), (1080, 89), (1140, 191)]
   robo006 s001 first 780.6 last 908.6 n 1161
   robo005 s002 first 907.5 last 1017.2 n 324
   robo000 s002 first 1129.3 last 1167.4 n 280
 touch unc tok sum 46344 mean 24.89 share of (touch+robot non-touch) unc 4.96%
   robo006|s001 touches 1161 state_actions 1161
   robo005|s002 touches 324 state_actions 324
== c2 state_action 2366 touch issued 20
 top sessions [('robo000 s002', 20)] n sessions touched 1
 per-60s issued [(1080, 20)]
   robo000 s002 first 1136.9 last 1138.8 n 20
 touch unc tok sum 100 mean 5.00 share of (touch+robot non-touch) unc 0.01%
   robo006|s001 touches 0 state_actions 1284
   robo005|s002 touches 0 state_actions 1062
touch_price_milli_sum (counts): F0 10821/3607, A4 4089/1363, CT 7173/2391 = 3.0 ms per touch each; budget_spent_gpu_s total F0 746.98, A4 764.8, CT 777.27

=== ADDENDUM (memory hypothesis) ===
bin | GPUkv mean/max % | hostKV mean/max % | offload load GB | store GB | touches  (F0/A4/CT)
   0  0/ 0  0/ 0 L 3.5 S 2.3 t   0 |  0/ 0  0/ 0 L 3.5 S 2.3 t   0 |  8/15  0/ 0 L 3.5 S 2.3 t   0
  60  2/13  1/ 4 L12.1 S 7.3 t   0 |  3/ 9  1/ 4 L12.1 S 7.3 t   0 |  3/ 7  1/ 4 L12.1 S 7.3 t   0
 120 11/18  0/ 0 L28.1 S10.7 t   0 |  9/19  0/ 0 L28.1 S10.7 t   0 | 10/21  0/ 1 L31.1 S10.7 t   0
 180 16/36  2/ 6 L38.9 S26.3 t   0 | 11/27  1/ 4 L39.4 S25.7 t   0 | 17/30  1/ 5 L35.7 S25.5 t   0
 240 17/36  1/ 7 L31.5 S21.8 t   0 | 18/31  5/14 L18.6 S27.5 t   0 |  9/22  5/16 L14.1 S29.0 t   0
 300 27/65  7/19 L20.5 S31.7 t   0 | 16/27  2/13 L34.9 S19.6 t   0 | 13/29  5/14 L40.9 S23.3 t   0
 360 11/24  3/ 7 L28.3 S16.7 t   0 | 17/23  0/ 0 L33.1 S 5.0 t   0 | 12/24  2/ 7 L30.6 S 8.0 t   0
 420  6/22  0/ 0 L 0.0 S 0.0 t   0 |  5/11  0/ 0 L 0.0 S 0.0 t   0 | 13/37  2/13 L54.0 S14.1 t   0
 480  4/15  0/ 0 L 0.0 S 0.0 t   0 |  2/14  0/ 0 L 0.0 S 0.0 t   0 |  5/25  0/ 0 L26.5 S 6.6 t   0
 540  2/ 7  0/ 0 L 0.0 S 0.0 t   0 |  4/10  0/ 0 L 0.0 S 0.0 t   0 |  9/22  0/ 3 L18.7 S12.4 t   0
 600 24/40  1/ 8 L29.5 S26.2 t 484 | 23/61  2/ 7 L28.1 S22.2 t 337 | 11/19  0/ 2 L29.3 S13.6 t   0
 660 27/37  2/ 6 L52.8 S10.0 t 652 |  7/19  1/ 6 L32.5 S11.2 t 518 |  9/20  2/ 5 L29.6 S 9.6 t   0
 720 33/88  6/15 L40.1 S34.9 t 122 | 16/31  7/15 L41.9 S33.0 t  40 | 10/30  0/ 2 L37.1 S12.4 t   0
 780 22/62  5/13 L47.8 S30.9 t  78 | 13/26  4/15 L28.4 S12.9 t   0 | 16/50  3/ 7 L38.8 S24.0 t 536
 840 58/77  0/ 1 L21.2 S12.1 t1136 |  9/23  2/ 7 L16.1 S30.2 t  30 | 24/37  1/ 5 L32.4 S14.0 t 596
 900 34/97  5/25 L62.8 S21.6 t 889 | 20/31  3/ 7 L48.2 S37.8 t 294 | 19/50  2/ 7 L21.7 S34.4 t 669
 960 31/63 14/28 L51.9 S48.5 t 150 | 34/65 10/19 L26.1 S36.7 t  42 | 24/60  5/20 L32.3 S36.5 t  64
1020 36/75 12/26 L51.4 S51.3 t  34 | 35/68  9/15 L32.6 S43.3 t   0 | 13/34  2/ 6 L24.7 S22.3 t   0
1080 19/45  6/15 L47.0 S44.9 t  62 | 12/24  5/22 L21.5 S31.2 t  30 | 16/29  1/ 8 L22.1 S14.4 t 382
1140 27/34 11/21 L14.1 S29.1 t   0 | 29/48  6/22 L56.6 S24.3 t  72 | 16/50  0/ 0 L27.3 S26.0 t 144
== class dash per bin: hit%% / cold n / reqs   (F0 | A4 | CT)
   0  88.2/ 18/260 |  88.2/ 18/260 |  88.2/ 18/260
  60  89.2/ 23/390 |  89.2/ 23/388 |  89.2/ 23/386
 120  88.0/ 24/338 |  87.8/ 26/335 |  87.8/ 24/336
 180  85.8/ 22/217 |  84.6/ 24/212 |  85.3/ 22/205
 240  86.7/ 28/266 |  85.3/ 25/213 |  82.9/ 25/176
 300  86.3/ 20/188 |  87.0/ 25/281 |  87.3/ 24/259
 360  88.3/ 22/302 |  89.0/ 24/378 |  87.6/ 24/324
 420  89.1/ 25/397 |  89.1/ 25/397 |  87.1/ 27/320
 480  89.3/ 23/394 |  89.3/ 23/394 |  88.7/ 24/372
 540  89.5/ 23/375 |  89.5/ 23/377 |  88.1/ 26/333
 600  86.3/ 26/257 |  86.2/ 27/263 |  87.9/ 26/329
 660  88.6/ 27/347 |  87.9/ 29/340 |  88.9/ 28/371
 720  82.3/ 18/115 |  83.6/ 24/153 |  87.1/ 22/254
 780  86.5/ 22/236 |  86.4/ 24/259 |  84.6/ 28/254
 840  82.6/ 25/184 |  86.2/ 23/227 |  87.4/ 23/291
 900  81.4/ 19/145 |  83.3/ 20/156 |  79.7/ 21/141
 960  78.4/ 13/ 65 |  86.4/ 13/129 |  84.9/ 19/157
1020  83.4/  6/ 62 |  83.6/ 13/ 85 |  87.2/ 22/265
1080  79.5/ 18/109 |  84.9/ 20/191 |  86.2/ 27/274
1140  81.4/ 13/ 96 |  84.5/ 24/182 |  84.8/ 22/202
== class asst per bin: hit%% / cold n / reqs   (F0 | A4 | CT)
   0   0.0/  9/  9 |   0.0/  9/  9 |   0.0/  9/  9
  60   0.0/ 12/ 12 |   0.0/ 12/ 12 |   0.0/ 12/ 12
 120   0.0/ 12/ 12 |   0.0/ 12/ 12 |   0.0/ 12/ 12
 180   0.0/ 12/ 12 |   0.0/ 12/ 12 |   0.0/ 12/ 12
 240   0.0/ 10/ 10 |   0.0/  7/  7 |   0.0/  8/  8
 300   0.0/  7/  7 |   0.0/ 10/ 10 |   0.0/ 10/ 10
 360   0.0/ 12/ 12 |   0.0/ 12/ 12 |   0.0/ 12/ 12
 420   0.7/ 12/ 12 |   0.0/ 12/ 12 |   2.4/ 11/ 11
 480   1.0/ 12/ 12 |   0.0/ 12/ 12 |   2.2/ 12/ 12
 540   1.1/ 10/ 10 |   0.0/ 10/ 10 |   2.7/ 10/ 10
 600   0.0/ 12/ 12 |   0.0/ 12/ 12 |   2.4/ 12/ 12
 660   0.3/ 12/ 12 |   0.0/ 12/ 12 |   1.9/ 12/ 12
 720   0.0/  8/  8 |   0.0/  8/  8 |   0.5/  8/  8
 780   0.0/ 10/ 10 |   0.0/ 12/ 12 |   0.0/ 12/ 12
 840   0.0/  9/  9 |   0.0/ 11/ 11 |   0.0/  9/  9
 900   0.0/ 10/ 10 |   0.0/  9/  9 |   0.0/  8/  8
 960   0.0/  4/  4 |   2.0/  5/  5 |   0.0/  8/  8
1020   0.0/  4/  4 |   0.7/  7/  7 |   0.0/ 10/ 10
1080   0.0/  7/  7 |   1.0/  8/  8 |   0.0/ 10/ 10
1140   0.0/  5/  5 |   0.2/ 10/ 10 |   0.0/  7/  7
== class robo per bin: hit%% / cold n / reqs   (F0 | A4 | CT)
   0  38.9/ 24/ 26 |  38.9/ 24/ 26 |  38.9/ 24/ 26
  60  70.6/  6/ 19 |  70.6/  6/ 19 |  70.6/  6/ 19
 120  79.3/  3/ 28 |  79.3/  3/ 28 |  79.3/  3/ 28
 180  69.4/ 13/ 37 |  69.2/ 13/ 37 |  68.6/ 12/ 36
 240  72.2/  8/ 26 |  57.9/ 12/ 25 |  58.5/ 12/ 25
 300  56.7/ 14/ 25 |  80.3/  8/ 25 |  75.4/  9/ 24
 360  82.2/  7/ 23 |  91.4/  3/ 19 |  85.8/  9/ 30
 420   0.0/  0/  0 |   0.0/  0/  0 |  81.5/  7/ 22
 480   0.0/  0/  0 |   0.0/  0/  0 |  84.4/  8/ 20
 540  64.4/ 19/ 40 |  71.0/ 16/ 40 |  62.5/  6/ 19
 600  98.8/  7/515 |  98.4/  7/360 |  81.5/  6/ 29
 660  99.4/  7/692 |  99.2/  6/549 |  85.5/  5/ 29
 720  93.2/ 16/168 |  84.2/ 15/ 73 |  72.0/ 11/ 28
 780  93.0/ 14/111 |  73.6/ 11/ 30 |  98.5/ 14/564
 840  99.6/  5/1161 |  81.6/ 15/ 48 |  98.8/  6/614
 900  99.1/ 12/919 |  96.0/ 12/319 |  98.3/ 13/693
 960  94.3/ 15/169 |  77.7/ 16/ 66 |  85.4/ 14/ 92
1020  79.5/ 12/ 65 |  51.3/ 12/ 21 |  67.6/  9/ 21
1080  91.4/ 18/ 87 |  85.9/ 14/ 50 |  98.4/ 12/401
1140  50.9/ 14/ 23 |  94.5/ 17/104 |  93.7/ 15/168
== class dash within_L / n by t_opportunity bin (F0 | A4 | CT)
   0 259/277 | 259/277 | 259/277
  60 385/404 | 385/404 | 385/404
 120 329/394 | 321/394 | 324/394
 180 211/396 | 201/396 | 197/396
 240 256/409 | 207/409 | 173/409
 300 185/394 | 265/394 | 253/394
 360 302/396 | 373/396 | 319/396
 420 398/398 | 398/398 | 308/398
 480 394/394 | 394/394 | 369/394
 540 374/403 | 376/403 | 331/403
 600 253/390 | 256/390 | 322/390
 660 326/409 | 329/409 | 372/409
 720 104/385 | 144/385 | 243/385
 780 229/413 | 256/413 | 240/413
 840 148/385 | 208/385 | 268/385
 900 111/414 | 140/414 | 133/414
 960  53/386 | 118/386 | 146/386
1020  50/410 |  79/410 | 254/410
1080 103/388 | 186/388 | 259/388
1140  91/405 | 171/405 | 188/405
== class asst within_L / n by t_opportunity bin (F0 | A4 | CT)
   0   9/  9 |   9/  9 |   9/  9
  60  12/ 12 |  12/ 12 |  12/ 12
 120  12/ 12 |  12/ 12 |  12/ 12
 180  12/ 12 |  12/ 12 |  12/ 12
 240   8/ 12 |   7/ 12 |   8/ 12
 300   7/ 12 |  10/ 12 |  10/ 12
 360  12/ 12 |  12/ 12 |  12/ 12
 420  12/ 12 |  12/ 12 |  11/ 12
 480  12/ 12 |  12/ 12 |  12/ 12
 540  10/ 12 |  10/ 12 |  10/ 12
 600  11/ 12 |  11/ 12 |  12/ 12
 660  11/ 12 |  12/ 12 |  12/ 12
 720   6/ 12 |   8/ 12 |   8/ 12
 780  10/ 12 |  12/ 12 |  12/ 12
 840   9/ 12 |   7/ 12 |   9/ 12
 900   8/ 12 |   8/ 12 |   6/ 12
 960   4/ 12 |   4/ 12 |   6/ 12
1020   4/ 12 |   5/ 12 |  10/ 12
1080   5/ 12 |   8/ 12 |  10/ 12
1140   3/ 12 |   8/ 12 |   7/ 12
== class robo within_L / n by t_opportunity bin (F0 | A4 | CT)
   0   3/  3 |   3/  3 |   3/  3
  60   5/  5 |   5/  5 |   5/  5
 120  15/ 15 |  15/ 15 |  15/ 15
 180  20/ 20 |  20/ 20 |  20/ 20
 240  11/ 13 |   9/ 13 |  12/ 13
 300   9/ 20 |  14/ 20 |  11/ 20
 360  12/ 22 |  10/ 22 |  14/ 22
 420   0/ 20 |   0/ 20 |   9/ 20
 480   0/  9 |   0/  9 |   5/  9
 540   0/  6 |   0/  6 |   5/  6
 600   8/ 11 |   7/ 11 |  10/ 11
 660  14/ 14 |  14/ 14 |  14/ 14
 720   8/ 16 |  12/ 16 |  11/ 16
 780  10/ 20 |  18/ 20 |  13/ 20
 840   3/  6 |   1/  6 |   3/  6
 900   5/ 18 |  10/ 18 |   5/ 18
 960   2/ 23 |   4/ 23 |   9/ 23
1020   6/ 21 |   4/ 21 |   9/ 21
1080   3/  8 |   3/  8 |   4/  8
1140   3/ 13 |   2/ 13 |   7/ 13
== residency belief rows per bin by tier (cold/gpu/host) F0|A4|CT
   0 23/9/0 | 23/9/0 | 23/9/0
  60 12/14/0 | 12/14/0 | 12/14/0
 120 12/13/0 | 12/13/0 | 12/13/0
 180 19/12/0 | 18/13/0 | 18/12/0
 240 19/8/0 | 17/11/0 | 20/6/0
 300 22/3/0 | 17/6/0 | 19/5/0
 360 17/8/0 | 14/9/0 | 18/11/0
 420 16/0/0 | 16/0/0 | 17/11/0
 480 14/0/0 | 14/0/0 | 15/14/0
 540 18/11/0 | 20/15/0 | 15/13/0
 600 18/42/0 | 15/32/0 | 14/17/0
 660 14/26/0 | 14/16/0 | 13/15/0
 720 25/14/0 | 21/12/0 | 17/11/0
 780 25/14/0 | 19/7/0 | 22/5/0
 840 15/18/0 | 22/3/0 | 15/9/0
 900 20/10/0 | 24/4/0 | 23/6/0
 960 24/6/0 | 23/5/0 | 24/4/0
1020 26/11/0 | 24/6/0 | 21/6/0
1080 26/8/0 | 27/5/0 | 16/15/0
1140 25/6/0 | 26/14/0 | 25/6/0
F0-A4 per-bin diffs: within_L dash/asst/robo ; dGPU mean ; dHost mean/max ; dash cold ; robo cold; dash hit ; touches
   0 wlD    0 asst   0 robo   0 | gpu   0.0 host   0.0/  0.0 | cold dash   0 robo   0 | hit dash   0.0 robo    0.0 | resCold   0 | loadGB   0.0 | touch     0
  60 wlD    0 asst   0 robo   0 | gpu  -0.4 host   0.0/  0.0 | cold dash   0 robo   0 | hit dash   0.0 robo    0.0 | resCold   0 | loadGB   0.0 | touch     0
 120 wlD    8 asst   0 robo   0 | gpu   1.6 host   0.0/  0.0 | cold dash  -2 robo   0 | hit dash   0.2 robo    0.0 | resCold   0 | loadGB   0.0 | touch     0
 180 wlD   10 asst   0 robo   0 | gpu   4.5 host   0.4/  2.3 | cold dash  -2 robo   0 | hit dash   1.1 robo    0.1 | resCold   1 | loadGB  -0.5 | touch     0
 240 wlD   49 asst   1 robo   2 | gpu  -0.9 host  -4.1/ -7.2 | cold dash   3 robo  -4 | hit dash   1.4 robo   14.3 | resCold   2 | loadGB  12.9 | touch     0
 300 wlD  -80 asst  -3 robo  -5 | gpu  11.4 host   4.9/  6.9 | cold dash  -5 robo   6 | hit dash  -0.7 robo  -23.6 | resCold   5 | loadGB -14.4 | touch     0
 360 wlD  -71 asst   0 robo   2 | gpu  -5.3 host   2.9/  7.4 | cold dash  -2 robo   4 | hit dash  -0.7 robo   -9.2 | resCold   3 | loadGB  -4.8 | touch     0
 420 wlD    0 asst   0 robo   0 | gpu   0.9 host   0.0/  0.0 | cold dash   0 robo   0 | hit dash   0.0 robo    0.0 | resCold   0 | loadGB   0.0 | touch     0
 480 wlD    0 asst   0 robo   0 | gpu   1.3 host   0.0/  0.0 | cold dash   0 robo   0 | hit dash   0.0 robo    0.0 | resCold   0 | loadGB   0.0 | touch     0
 540 wlD   -2 asst   0 robo   0 | gpu  -1.3 host   0.0/  0.0 | cold dash   0 robo   3 | hit dash   0.0 robo   -6.5 | resCold  -2 | loadGB   0.0 | touch     0
 600 wlD   -3 asst   0 robo   1 | gpu   1.0 host  -0.2/  0.5 | cold dash  -1 robo   0 | hit dash   0.1 robo    0.4 | resCold   3 | loadGB   1.4 | touch   147
 660 wlD   -3 asst  -1 robo   0 | gpu  20.1 host   0.7/ -0.2 | cold dash  -2 robo   1 | hit dash   0.7 robo    0.2 | resCold   0 | loadGB  20.3 | touch   134
 720 wlD  -40 asst  -2 robo  -4 | gpu  17.2 host  -0.9/  0.0 | cold dash  -6 robo   1 | hit dash  -1.4 robo    9.1 | resCold   4 | loadGB  -1.8 | touch    82
 780 wlD  -27 asst  -2 robo  -8 | gpu   8.8 host   1.0/ -1.4 | cold dash  -2 robo   3 | hit dash   0.2 robo   19.4 | resCold   6 | loadGB  19.4 | touch    78
 840 wlD  -60 asst   2 robo   2 | gpu  49.7 host  -1.9/ -6.1 | cold dash   2 robo -10 | hit dash  -3.5 robo   18.0 | resCold  -7 | loadGB   5.0 | touch  1106
 900 wlD  -29 asst   0 robo  -5 | gpu  14.4 host   1.6/ 17.6 | cold dash  -1 robo   0 | hit dash  -2.0 robo    3.1 | resCold  -4 | loadGB  14.6 | touch   595
 960 wlD  -65 asst   0 robo  -2 | gpu  -2.3 host   3.4/  9.2 | cold dash   0 robo  -1 | hit dash  -7.9 robo   16.6 | resCold   1 | loadGB  25.8 | touch   108
1020 wlD  -29 asst  -1 robo   2 | gpu   0.8 host   3.2/ 10.8 | cold dash  -7 robo   0 | hit dash  -0.2 robo   28.1 | resCold   2 | loadGB  18.8 | touch    34
1080 wlD  -83 asst  -3 robo   0 | gpu   7.1 host   0.7/ -7.4 | cold dash  -2 robo   4 | hit dash  -5.4 robo    5.5 | resCold  -1 | loadGB  25.5 | touch    32
1140 wlD  -80 asst  -5 robo   1 | gpu  -2.0 host   4.6/ -0.8 | cold dash -11 robo  -3 | hit dash  -3.1 robo  -43.6 | resCold  -1 | loadGB -42.5 | touch   -72
pre-R F0-A4 within_L dash: mean -10.8 sd 40.4 range -80..49 (bins 120-540); post-R mean -41.9
totals post-R (bins 600-1199) F0-A4: dash wl -419, asst wl -12, robo wl -13; pre-R(0-599): dash -86 asst -2 robo -1
Spearman rho: loss series (F0-A4 within_L) at bin k vs X diff (F0-A4) at bin k-lag (lag>0: X leads); bins k in 600-1199, n shown
-- Y = wl_dash
  gpu_mean           lag-1  0.66(n9) lag+0  0.32(n10) lag+1 -0.09(n10) lag+2  0.12(n10)
  gpu_max            lag-1  0.38(n9) lag+0 -0.03(n10) lag+1 -0.38(n10) lag+2 -0.11(n10)
  host_mean          lag-1 -0.82(n9) lag+0 -0.30(n10) lag+1 -0.62(n10) lag+2 -0.21(n10)
  host_max           lag-1 -0.24(n9) lag+0  0.37(n10) lag+1 -0.03(n10) lag+2 -0.33(n10)
  off_load_GB        lag-1  0.22(n9) lag+0 -0.04(n10) lag+1 -0.60(n10) lag+2 -0.35(n10)
  off_store_GB       lag-1 -0.29(n9) lag+0 -0.23(n10) lag+1 -0.28(n10) lag+2 -0.34(n10)
  local_compute_Mtok lag-1 -0.03(n9) lag+0  0.07(n10) lag+1 -0.24(n10) lag+2 -0.16(n10)
  res_cold           lag-1  0.07(n9) lag+0  0.45(n10) lag+1  0.07(n10) lag+2 -0.22(n10)
  cold_dash          lag-1  0.40(n9) lag+0  0.09(n10) lag+1  0.51(n10) lag+2  0.14(n10)
  cold_robo          lag-1  0.25(n9) lag+0  0.22(n10) lag+1 -0.12(n10) lag+2  0.61(n10)
  cold_asst          lag-1  0.57(n9) lag+0  0.42(n10) lag+1  0.42(n10) lag+2  0.58(n10)
  hit_dash           lag-1  0.08(n9) lag+0  0.90(n10) lag+1  0.17(n10) lag+2  0.63(n10)
  hit_robo           lag-1 -0.03(n9) lag+0 -0.02(n10) lag+1 -0.50(n10) lag+2 -0.78(n10)
  touch              lag-1  0.52(n9) lag+0  0.45(n10) lag+1  0.15(n10) lag+2 -0.39(n10)
-- Y = wl_asst
  gpu_mean           lag-1 -0.01(n9) lag+0  0.25(n10) lag+1  0.09(n10) lag+2  0.56(n10)
  gpu_max            lag-1  0.19(n9) lag+0  0.11(n10) lag+1  0.15(n10) lag+2  0.51(n10)
  host_mean          lag-1  0.10(n9) lag+0 -0.33(n10) lag+1 -0.10(n10) lag+2 -0.66(n10)
  host_max           lag-1  0.75(n9) lag+0  0.40(n10) lag+1  0.00(n10) lag+2 -0.53(n10)
  off_load_GB        lag-1  0.45(n9) lag+0  0.11(n10) lag+1 -0.25(n10) lag+2 -0.61(n10)
  off_store_GB       lag-1 -0.19(n9) lag+0 -0.55(n10) lag+1 -0.23(n10) lag+2 -0.27(n10)
  local_compute_Mtok lag-1  0.06(n9) lag+0 -0.28(n10) lag+1 -0.12(n10) lag+2 -0.44(n10)
  res_cold           lag-1 -0.01(n9) lag+0 -0.27(n10) lag+1 -0.13(n10) lag+2  0.02(n10)
  cold_dash          lag-1  0.26(n9) lag+0  0.84(n10) lag+1  0.59(n10) lag+2  0.15(n10)
  cold_robo          lag-1  0.13(n9) lag+0 -0.50(n10) lag+1 -0.16(n10) lag+2  0.26(n10)
  cold_asst          lag-1  0.66(n9) lag+0  0.35(n10) lag+1  0.10(n10) lag+2  0.20(n10)
  hit_dash           lag-1  0.11(n9) lag+0 -0.08(n10) lag+1  0.19(n10) lag+2 -0.02(n10)
  hit_robo           lag-1  0.00(n9) lag+0  0.23(n10) lag+1 -0.01(n10) lag+2 -0.11(n10)
  touch              lag-1  0.41(n9) lag+0  0.90(n10) lag+1  0.30(n10) lag+2 -0.04(n10)
-- Y = wl_robo
  gpu_mean           lag-1  0.06(n9) lag+0 -0.11(n10) lag+1 -0.76(n10) lag+2 -0.13(n10)
  gpu_max            lag-1  0.21(n9) lag+0 -0.48(n10) lag+1 -0.49(n10) lag+2  0.34(n10)
  host_mean          lag-1  0.03(n9) lag+0 -0.10(n10) lag+1  0.62(n10) lag+2  0.08(n10)
  host_max           lag-1  0.12(n9) lag+0 -0.12(n10) lag+1 -0.04(n10) lag+2  0.63(n10)
  off_load_GB        lag-1  0.03(n9) lag+0 -0.26(n10) lag+1  0.54(n10) lag+2 -0.48(n10)
  off_store_GB       lag-1 -0.06(n9) lag+0 -0.24(n10) lag+1  0.75(n10) lag+2 -0.13(n10)
  local_compute_Mtok lag-1 -0.12(n9) lag+0 -0.31(n10) lag+1  0.88(n10) lag+2 -0.32(n10)
  res_cold           lag-1 -0.20(n9) lag+0 -0.35(n10) lag+1  0.23(n10) lag+2 -0.12(n10)
  cold_dash          lag-1 -0.31(n9) lag+0 -0.06(n10) lag+1  0.14(n10) lag+2 -0.11(n10)
  cold_robo          lag-1  0.53(n9) lag+0 -0.54(n10) lag+1  0.30(n10) lag+2 -0.17(n10)
  cold_asst          lag-1  0.52(n9) lag+0 -0.49(n10) lag+1 -0.31(n10) lag+2  0.29(n10)
  hit_dash           lag-1  0.16(n9) lag+0 -0.13(n10) lag+1 -0.07(n10) lag+2 -0.61(n10)
  hit_robo           lag-1 -0.66(n9) lag+0  0.00(n10) lag+1  0.12(n10) lag+2  0.01(n10)
  touch              lag-1 -0.22(n9) lag+0 -0.01(n10) lag+1 -0.52(n10) lag+2 -0.19(n10)
-- Y=dash within_L fraction vs touch count, within F0 bins 600+: rho 0.61 ; A4 0.30 ; CT -0.46
F0 {'pb_evictions_shadow': 376731, 'pb_host_evictions': 110701, 'pb_pinned_overshoot': 50970, 'pb_resyncs': 8175, 'pb_resync_changed': 6867} {'kv_capacity_enforced': True, 'gpu_kv_tokens': 62944, 'pressure': {'epochs': 11996, 'epochs_over_cap': 11, 'peak_tokens': 64973, 'intervals': [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 'host_peak_tokens': 70114, 'host_epochs_over_cap': 0, 'intervals_n': 11}, 'enact_placement_totals': {'calls': 11996, 'offloaded': 0, 'kept_warm': 6363, 'evicted': 12, 'resident': 42}} {'n_cached': 17976, 'held_bytes': 1080289200, 'cap_bytes': 1500000000, 'hits': 19474, 'misses': 17976, 'encoded_bytes': 1080289200, 'hit_fraction': 0.52}
   dash post-R reqs 1616 hit% 84.7 cold 187 cold frac 0.116
   dash pre-R reqs 3127 hit% 88.3 cold 228 cold frac 0.073
   asst post-R reqs 81 hit% 0.0 cold 81 cold frac 1.000
   asst pre-R reqs 108 hit% 0.3 cold 108 cold frac 1.000
   robo post-R reqs 3910 hit% 97.8 cold 120 cold frac 0.031
   robo pre-R reqs 224 hit% 69.8 cold 94 cold frac 0.420
A4 {'pb_evictions_shadow': 376492, 'pb_host_evictions': 90484, 'pb_pinned_overshoot': 25620, 'pb_resyncs': 6370, 'pb_resync_changed': 6183} {'kv_capacity_enforced': True, 'gpu_kv_tokens': 62944, 'pressure': {'epochs': 11996, 'epochs_over_cap': 9, 'peak_tokens': 65958, 'intervals': [1, 1, 1, 1, 1, 1, 1, 1, 1], 'host_peak_tokens': 44243, 'host_epochs_over_cap': 0, 'intervals_n': 9}, 'enact_placement_totals': {'calls': 11996, 'offloaded': 0, 'kept_warm': 6117, 'evicted': 10, 'resident': 43}} {'n_cached': 17976, 'held_bytes': 1080289200, 'cap_bytes': 1500000000, 'hits': 19656, 'misses': 17976, 'encoded_bytes': 1080289200, 'hit_fraction': 0.522321}
   dash post-R reqs 1985 hit% 85.8 cold 217 cold frac 0.109
   dash pre-R reqs 3235 hit% 88.3 cold 236 cold frac 0.073
   asst post-R reqs 94 hit% 0.2 cold 94 cold frac 1.000
   asst pre-R reqs 108 hit% 0.0 cold 108 cold frac 1.000
   robo post-R reqs 1620 hit% 93.4 cold 125 cold frac 0.077
   robo pre-R reqs 219 hit% 72.9 cold 85 cold frac 0.388
CT {'pb_evictions_shadow': 394602, 'pb_host_evictions': 77806, 'pb_pinned_overshoot': 788, 'pb_resyncs': 7658, 'pb_resync_changed': 7611} {'kv_capacity_enforced': True, 'gpu_kv_tokens': 62944, 'pressure': {'epochs': 12000, 'epochs_over_cap': 9, 'peak_tokens': 63916, 'intervals': [1, 1, 1, 1, 1, 1, 1, 1, 1], 'host_peak_tokens': 33252, 'host_epochs_over_cap': 0, 'intervals_n': 9}, 'enact_placement_totals': {'calls': 12000, 'offloaded': 0, 'kept_warm': 4556, 'evicted': 10, 'resident': 43}} {'n_cached': 17976, 'held_bytes': 1080289200, 'cap_bytes': 1500000000, 'hits': 20663, 'misses': 17976, 'encoded_bytes': 1080289200, 'hit_fraction': 0.534771}
   dash post-R reqs 2538 hit% 86.5 cold 238 cold frac 0.094
   dash pre-R reqs 2971 hit% 87.6 cold 237 cold frac 0.080
   asst post-R reqs 96 hit% 0.2 cold 96 cold frac 1.000
   asst pre-R reqs 108 hit% 0.3 cold 108 cold frac 1.000
   robo post-R reqs 2639 hit% 96.7 cold 105 cold frac 0.040
   robo pre-R reqs 249 hit% 73.7 cold 96 cold frac 0.386
