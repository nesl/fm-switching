== netwin rung3_n20_s4  outage=covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4835_link  control=covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30  t0=483.5 d=188.0 R=671.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 131 (committed robot_headline 0.462898 x n 283 = 131.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 163 (committed 163); within_L(outcomes) 165; dashcam within(1.0) 3748 vs within_L 3748 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 133 (headline 0.469965 x 283); classifier agree 283 of 283; SS on_time 165 (committed 165) within_L 168; dashcam within(1.0) 3974 vs within_L 3974
  same opportunity ids in both cells: robot 283/283, SS 237/237
B_obs DEFINITION (fixed before outcomes): rate_W(t)=sum uncached prompt tokens of robot requests with t_submit in (t-W,t] / W, 1 s grid; ctl(t)=control rate at the same absolute time; sd=sd of control rate over [60,t0). DEF1=first t>=R, after outage rate first exceeds ctl+1sd, at which outage<=ctl+1sd. DEF2=last exceedance+1 s. Rule window = DEF1 at W=10; others sensitivity.
  W= 5: ctl pre mean 1896 sd 3307 tok/s; first exceed R+2; B_obs DEF1 6 s DEF2 512 s
  W=10: ctl pre mean 1817 sd 2171 tok/s; first exceed R+2; B_obs DEF1 12 s DEF2 516 s
  W=20: ctl pre mean 1759 sd 1331 tok/s; first exceed R+2; B_obs DEF1 22 s DEF2 516 s
  rate trace W=10 (t-R,ctl,out): [(-10, 399, 0), (0, 309, 0), (0, 310, 1101), (10, 1370, 6493), (20, 1250, 2333), (30, 646, 443), (40, 467, 67), (50, 102, 1206), (60, 467, 280), (70, 3389, 1374), (80, 3234, 5123), (90, 5402, 2691), (100, 62, 2114), (110, 4505, 4351), (120, 2744, 4896), (130, 4965, 1158), (140, 1182, 3684), (150, 3963, 757), (160, 54, 1336), (170, 126, 873), (180, 1882, 1502), (190, 454, 218), (200, 1950, 2745), (210, 220, 1215), (220, 2762, 2298), (230, 207, 3350), (240, 5384, 3385), (250, 1430, 4290), (260, 49, 74), (270, 7310, 4585), (280, 1757, 7579), (290, 185, 3639)]
  drain cross-check from outage log: {'n_deferred_frames': 1313, 'deferred_own_tokens': 118325, 'n_victims': 14, 'uplink_queue_max_max': 1.3, 'last_backlogged_delivery': None, 'n_backlogged': 0, 'last_delayed_submit': None, 'n_delayed_after_R': 0}
  deficit-recovery marker (victim robot uncached tokens, cum out minus ctl from t0): deficit at R -217434 tok; first t>=R with cum out>=ctl: never; end-of-run diff -114960
  DEF1 vs DEF2 vs drain: 12 / 516 / n/a  UNSTABLE: DEF1 differs >50% across W or <30 s (bursty); DEF1(W=10) kept as rule
== PRIMARY windowed [R,R+B_obs DEF1 W=10] [671.5,683.0)  len 12 s
  robot cbd                n=   5 ctl    5 (1.000) out    3 (0.600) harm(ctl-out) +2 CI[+0,+4] clusters=2 (robot questions)
  robot cloud on-time      n=   5 ctl    5 (1.000) out    0 (0.000) harm(ctl-out) +5 CI[+4,+6] clusters=2 (robot questions)
  SS on-time (scorer)      n=   2 ctl    1 (0.500) out    0 (0.000) harm(ctl-out) +1 CI[+0,+2] clusters=2 (SS questions)
  SS within_L (outcome)    n=   2 ctl    2 (1.000) out    0 (0.000) harm(ctl-out) +2 CI[+2,+2] clusters=2 (SS questions)
  dashcam within_L         n=  77 ctl   40 (0.519) out    2 (0.026) harm(ctl-out) +38 CI[+22,+54] clusters=2 (10 s blocks, 77 instants; unmatched ctl 0 out 0)
== sensitivity W=5 DEF1=6 [671.5,678.0)  len 6 s
  robot cbd                n=   4 ctl    4 (1.000) out    2 (0.500) harm(ctl-out) +2 CI[+0,+4] clusters=2 (robot questions)
  robot cloud on-time      n=   4 ctl    4 (1.000) out    0 (0.000) harm(ctl-out) +4 CI[+4,+4] clusters=2 (robot questions)
  SS on-time (scorer)      n=   2 ctl    1 (0.500) out    0 (0.000) harm(ctl-out) +1 CI[+0,+2] clusters=2 (SS questions)
  SS within_L (outcome)    n=   2 ctl    2 (1.000) out    0 (0.000) harm(ctl-out) +2 CI[+2,+2] clusters=2 (SS questions)
  dashcam within_L         n=  44 ctl   26 (0.591) out    2 (0.045) harm(ctl-out) +24 CI[+24,+24] clusters=1 (10 s blocks, 44 instants; unmatched ctl 0 out 0)
== sensitivity W=20 DEF1=22 [671.5,693.0)  len 22 s
  robot cbd                n=  10 ctl    8 (0.800) out    5 (0.500) harm(ctl-out) +3 CI[+0,+9] clusters=5 (robot questions)
  robot cloud on-time      n=  10 ctl   10 (1.000) out    3 (0.300) harm(ctl-out) +7 CI[+1,+13] clusters=5 (robot questions)
  SS on-time (scorer)      n=   4 ctl    3 (0.750) out    2 (0.500) harm(ctl-out) +1 CI[+0,+3] clusters=4 (SS questions)
  SS within_L (outcome)    n=   4 ctl    4 (1.000) out    2 (0.500) harm(ctl-out) +2 CI[+0,+4] clusters=4 (SS questions)
  dashcam within_L         n= 140 ctl   84 (0.600) out    3 (0.021) harm(ctl-out) +81 CI[+9,+153] clusters=3 (10 s blocks, 140 instants; unmatched ctl 0 out 0)
== sensitivity DEF2 sustained=516 [671.5,1188.0)  len 516 s
  robot cbd                n= 135 ctl   54 (0.400) out   50 (0.370) harm(ctl-out) +4 CI[-10,+17] clusters=26 (robot questions)
  robot cloud on-time      n= 135 ctl   42 (0.311) out   38 (0.281) harm(ctl-out) +4 CI[-12,+19] clusters=26 (robot questions)
  SS on-time (scorer)      n= 104 ctl   58 (0.558) out   51 (0.490) harm(ctl-out) +7 CI[-5,+19] clusters=104 (SS questions)
  SS within_L (outcome)    n= 104 ctl   60 (0.577) out   52 (0.500) harm(ctl-out) +8 CI[-4,+20] clusters=104 (SS questions)
  dashcam within_L         n=3427 ctl 1170 (0.341) out 1026 (0.299) harm(ctl-out) +144 CI[-90,+409] clusters=9 (60 s blocks, 3427 instants; unmatched ctl 0 out 0)
== DURING-OUTAGE [t0,R] (beside) [483.5,671.5)  len 188 s
  robot cbd                n=  26 ctl   21 (0.808) out   17 (0.654) harm(ctl-out) +4 CI[-3,+15] clusters=8 (robot questions)
  robot cloud on-time      n=  26 ctl   16 (0.615) out    0 (0.000) harm(ctl-out) +16 CI[+5,+29] clusters=8 (robot questions)
  SS on-time (scorer)      n=  38 ctl   32 (0.842) out   38 (1.000) harm(ctl-out) -6 CI[-10,-2] clusters=38 (SS questions)
  SS within_L (outcome)    n=  38 ctl   32 (0.842) out   38 (1.000) harm(ctl-out) -6 CI[-10,-2] clusters=38 (SS questions)
  dashcam within_L         n=1251 ctl  805 (0.643) out 1240 (0.991) harm(ctl-out) -435 CI[-657,-134] clusters=4 (60 s blocks, 1251 instants; unmatched ctl 0 out 0)
== WHOLE RUN (beside) [0.0,1201.0)  len 1201 s
  robot cbd                n= 283 ctl  131 (0.463) out  133 (0.470) harm(ctl-out) -2 CI[-23,+19] clusters=47 (robot questions)
  robot cloud on-time      n= 283 ctl  124 (0.438) out  114 (0.403) harm(ctl-out) +10 CI[-17,+39] clusters=47 (robot questions)
  SS on-time (scorer)      n= 237 ctl  163 (0.688) out  165 (0.696) harm(ctl-out) -2 CI[-18,+13] clusters=237 (SS questions)
  SS within_L (outcome)    n= 237 ctl  165 (0.696) out  168 (0.709) harm(ctl-out) -3 CI[-18,+13] clusters=237 (SS questions)
  dashcam within_L         n=7850 ctl 3748 (0.477) out 3974 (0.506) harm(ctl-out) -226 CI[-819,+337] clusters=20 (60 s blocks, 7850 instants; unmatched ctl 0 out 0)
== fixed [R,R+60] (reference) [671.5,731.5)  len 60 s
  robot cbd                n=  15 ctl   10 (0.667) out    7 (0.467) harm(ctl-out) +3 CI[+0,+9] clusters=5 (robot questions)
  robot cloud on-time      n=  15 ctl   15 (1.000) out    8 (0.533) harm(ctl-out) +7 CI[+1,+13] clusters=5 (robot questions)
  SS on-time (scorer)      n=  12 ctl   11 (0.917) out   10 (0.833) harm(ctl-out) +1 CI[+0,+3] clusters=12 (SS questions)
  SS within_L (outcome)    n=  12 ctl   12 (1.000) out   10 (0.833) harm(ctl-out) +2 CI[+0,+5] clusters=12 (SS questions)
  dashcam within_L         n= 399 ctl  309 (0.774) out  212 (0.531) harm(ctl-out) +97 CI[+19,+199] clusters=7 (10 s blocks, 399 instants; unmatched ctl 0 out 0)
CATCH-UP: uncached tokens (robot requests by t_submit)
  [R,R+300]    ctl n=1996 tok=616510 | out n=1055 tok=751734 | out-ctl tok +135224 (+21.9%)
  [R,R+B]      ctl n=122 tok=13722 | out n=53 tok=75947 | out-ctl tok +62225 (+453.5%)
  [t0,R]       ctl n=169 tok=180567 | out n=814 tok=12012 | out-ctl tok -168555 (-93.3%)
  [R+B,R+300]  ctl n=1874 tok=602788 | out n=1002 tok=675787 | out-ctl tok +72999 (+12.1%)
