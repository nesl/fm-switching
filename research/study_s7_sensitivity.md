POOLED 1x seeds [4, 5, 6, 7] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            +1 CI[-3,+5] incl0 unrounded[-3.000,5.000] draws<0/=0/>0 (485, 363, 1152)
  cloud on-time                  -11 CI[-23,-2] excl0 NEG unrounded[-23.000,-2.000] draws<0/=0/>0 (1985, 10, 5)
  cloud-correct                  +0 CI[-5,+5] incl0 unrounded[-5.000,5.000] draws<0/=0/>0 (839, 322, 839)
  device-route                   +11 CI[+2,+23] excl0 POS unrounded[2.000,23.000] draws<0/=0/>0 (5, 10, 1985)
  dashcam within_L (60s blocks)  +1151 CI[+617,+1703] excl0 POS (80 blocks) unrounded[617.000,1703.000] draws<0/=0/>0 (0, 0, 2000)
  SS cloud on-time               +2 CI[-7,+11] incl0 unrounded[-7.000,11.000] draws<0/=0/>0 (555, 164, 1281)
  FAIR F0 0.9302 rung3 0.9429 RELATIVE diff -0.0128 CI[-0.0274,-0.0021] unrounded[-0.027389,-0.002095] draws<0/=0/>0 (1981, 0, 19) | ABSOLUTE -3.27 CI[-7.01,-0.47]
1X s4+s5+s6+s7: NO-HARM point cbd +1 (rule >= -2: True), on-time -11 / CI cbd [-3,+5] on-time [-23,-2]: MISS
POOLED half seeds [4, 5, 6, 7] (clusters (seed,question)/(seed,block), seed 7, 2000 reps)
  cbd                            -5 CI[-29,+18] incl0 unrounded[-29.000,18.000] draws<0/=0/>0 (1302, 65, 633)
  cloud on-time                  +55 CI[+25,+87] excl0 POS unrounded[25.000,87.000] draws<0/=0/>0 (0, 0, 2000)
  cloud-correct                  +20 CI[+0,+44] incl0 unrounded[0.000,44.000] draws<0/=0/>0 (50, 13, 1937)
  device-route                   -55 CI[-87,-25] excl0 NEG unrounded[-87.000,-25.000] draws<0/=0/>0 (2000, 0, 0)
  dashcam within_L (60s blocks)  +2536 CI[+1214,+3862] excl0 POS (80 blocks) unrounded[1214.000,3862.000] draws<0/=0/>0 (0, 0, 2000)
  SS cloud on-time               +74 CI[+45,+102] excl0 POS unrounded[45.000,102.000] draws<0/=0/>0 (0, 0, 2000)
  FAIR F0 0.7476 rung3 0.6596 RELATIVE diff +0.0880 CI[+0.0513,+0.1257] unrounded[0.051251,0.125694] draws<0/=0/>0 (0, 0, 2000) | ABSOLUTE +22.58 CI[+12.14,+32.62]
HALVED s4+s5+s6+s7: cbd no-harm PASS (point -5 CI[-29,+18]); FAIR gain (CI above 0) PASS (+0.0880 CI[+0.0513,+0.1257])
