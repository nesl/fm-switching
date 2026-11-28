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
