POOLED 1x seeds [4, 5, 6] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            +1 CI[-3,+6] incl0 unrounded[-3.000,6.000] draws<0/=0/>0 (488, 365, 1147)
  cloud on-time                  -5 CI[-11,+0] incl0 unrounded[-11.000,0.000] draws<0/=0/>0 (1913, 56, 31)
  cloud-correct                  +0 CI[-5,+5] incl0 unrounded[-5.000,5.000] draws<0/=0/>0 (841, 364, 795)
  device-route                   +5 CI[+0,+11] incl0 unrounded[0.000,11.000] draws<0/=0/>0 (31, 56, 1913)
  dashcam within_L (60s blocks)  +935 CI[+428,+1465] excl0 POS (60 blocks) unrounded[428.000,1465.000] draws<0/=0/>0 (0, 0, 2000)
  SS cloud on-time               +2 CI[-6,+10] incl0 unrounded[-6.000,10.000] draws<0/=0/>0 (532, 156, 1312)
  FAIR F0 0.9522 rung3 0.9593 RELATIVE diff -0.0071 CI[-0.0179,+0.0019] unrounded[-0.017937,0.001856] draws<0/=0/>0 (1885, 2, 113) | ABSOLUTE -1.41 CI[-3.63,+0.37]
1X s4+s5+s6: NO-HARM point cbd +1 (rule >= -2: True), on-time -5 / CI cbd [-3,+6] on-time [-11,+0]: PASS
POOLED half seeds [4, 5, 6] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            -4 CI[-28,+17] incl0 unrounded[-28.000,17.000] draws<0/=0/>0 (1253, 51, 696)
  cloud on-time                  +47 CI[+21,+74] excl0 POS unrounded[21.000,74.000] draws<0/=0/>0 (0, 0, 2000)
  cloud-correct                  +17 CI[-3,+38] incl0 unrounded[-3.000,38.000] draws<0/=0/>0 (76, 23, 1901)
  device-route                   -47 CI[-74,-21] excl0 NEG unrounded[-74.000,-21.000] draws<0/=0/>0 (2000, 0, 0)
  dashcam within_L (60s blocks)  +1465 CI[+340,+2512] excl0 POS (60 blocks) unrounded[340.000,2512.000] draws<0/=0/>0 (15, 0, 1985)
  SS cloud on-time               +43 CI[+18,+68] excl0 POS unrounded[18.000,68.000] draws<0/=0/>0 (2, 2, 1996)
  FAIR F0 0.7546 rung3 0.6644 RELATIVE diff +0.0902 CI[+0.0482,+0.1302] unrounded[0.048155,0.130203] draws<0/=0/>0 (0, 0, 2000) | ABSOLUTE +17.80 CI[+9.24,+27.13]
HALVED s4+s5+s6: cbd no-harm PASS (point -4 CI[-28,+17]); FAIR gain (CI above 0) PASS (+0.0902 CI[+0.0482,+0.1302])
