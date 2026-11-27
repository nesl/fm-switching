== netwin f0_n20_s4_t4075  outage=covex-v6-fair-final-cand-tl-sync_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link_qp  control=covex-v6-fair-final-cand-tl_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp  t0=407.5 d=188.0 R=595.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 154 (committed robot_headline 0.544170 x n 283 = 154.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 199 (committed 199); within_L(outcomes) 200; dashcam within(1.0) 5343 vs within_L 5343 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 134 (headline 0.473498 x 283); classifier agree 283 of 283; SS on_time 176 (committed 176) within_L 177; dashcam within(1.0) 4561 vs within_L 4561
  same opportunity ids in both cells: robot 283/283, SS 237/237
B_obs DEFINITION (fixed before outcomes): rate_W(t)=sum uncached prompt tokens of robot requests with t_submit in (t-W,t] / W, 1 s grid; ctl(t)=control rate at the same absolute time; sd=sd of control rate over [60,t0). DEF1=first t>=R, after outage rate first exceeds ctl+1sd, at which outage<=ctl+1sd. DEF2=last exceedance+1 s. Rule window = DEF1 at W=10; others sensitivity.
  W= 5: ctl pre mean 1179 sd 1474 tok/s; first exceed R+0; B_obs DEF1 6 s DEF2 578 s
  W=10: ctl pre mean 1177 sd 1010 tok/s; first exceed R+0; B_obs DEF1 12 s DEF2 582 s
  W=20: ctl pre mean 1180 sd 758 tok/s; first exceed R+2; B_obs DEF1 22 s DEF2 592 s
  rate trace W=10 (t-R,ctl,out): [(-10, 859, 0), (0, 111, 0), (0, 111, 1132), (10, 1426, 3863), (20, 1032, 2528), (30, 713, 303), (40, 546, 1491), (50, 73, 723), (60, 1104, 441), (70, 301, 250), (80, 392, 814), (90, 967, 1396), (100, 1450, 1251), (110, 317, 360), (120, 259, 502), (130, 411, 1218), (140, 200, 4761), (150, 2119, 646), (160, 2351, 7385), (170, 446, 184), (180, 1385, 1981), (190, 2715, 3292), (200, 793, 110), (210, 2580, 2736), (220, 869, 1770), (230, 1836, 2614), (240, 437, 804), (250, 158, 670), (260, 614, 359), (270, 605, 1440), (280, 802, 931), (290, 2208, 2771)]
  drain cross-check from outage log: {'n_deferred_frames': 1312, 'deferred_own_tokens': 118328, 'n_victims': 14, 'uplink_queue_max_max': 1.3, 'last_backlogged_delivery': None, 'n_backlogged': 0, 'last_delayed_submit': None, 'n_delayed_after_R': 0}
  deficit-recovery marker (victim robot uncached tokens, cum out minus ctl from t0): deficit at R -92008 tok; first t>=R with cum out>=ctl: R+137 s; end-of-run diff +384951
  DEF1 vs DEF2 vs drain: 12 / 582 / n/a  UNSTABLE: DEF1 differs >50% across W or <30 s (bursty); DEF1(W=10) kept as rule
RULE WINDOW (user ruling, amends D332 item 8): every arm and seed scored over ONE FIXED [R,R+120]; sensitivity [R,R+60], [R,R+300]. B_obs DEF1/DEF2 above are DESCRIPTIVE per arm only (B_obs depends on the arm).
  B_obs descriptive (W=10): DEF1 12 s, DEF2 582 s (outage arm vs control-threshold)
== RULE fixed [R,R+120] [595.5,715.5)  len 120 s
  robot cbd                n=  26 ctl   20 (0.769) out   19 (0.731) harm(ctl-out) +1 CI[+0,+3] clusters=7 (robot questions)
  robot cloud on-time      n=  26 ctl   25 (0.962) out   21 (0.808) harm(ctl-out) +4 CI[+1,+8] clusters=7 (robot questions)
  SS on-time (scorer)      n=  24 ctl   24 (1.000) out   21 (0.875) harm(ctl-out) +3 CI[+0,+7] clusters=24 (SS questions)
  SS within_L (outcome)    n=  24 ctl   24 (1.000) out   21 (0.875) harm(ctl-out) +3 CI[+0,+7] clusters=24 (SS questions)
  dashcam within_L         n= 797 ctl  692 (0.868) out  566 (0.710) harm(ctl-out) +126 CI[+84,+207] clusters=3 (60 s blocks, 797 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+60] [595.5,655.5)  len 60 s
  robot cbd                n=  12 ctl   11 (0.917) out   10 (0.833) harm(ctl-out) +1 CI[+0,+3] clusters=4 (robot questions)
  robot cloud on-time      n=  12 ctl   11 (0.917) out    7 (0.583) harm(ctl-out) +4 CI[+1,+7] clusters=4 (robot questions)
  SS on-time (scorer)      n=  12 ctl   12 (1.000) out    9 (0.750) harm(ctl-out) +3 CI[+0,+6] clusters=12 (SS questions)
  SS within_L (outcome)    n=  12 ctl   12 (1.000) out    9 (0.750) harm(ctl-out) +3 CI[+0,+6] clusters=12 (SS questions)
  dashcam within_L         n= 386 ctl  318 (0.824) out  220 (0.570) harm(ctl-out) +98 CI[+25,+165] clusters=7 (10 s blocks, 386 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+300] [595.5,895.5)  len 300 s
  robot cbd                n=  67 ctl   38 (0.567) out   38 (0.567) harm(ctl-out) +0 CI[-5,+6] clusters=15 (robot questions)
  robot cloud on-time      n=  67 ctl   52 (0.776) out   41 (0.612) harm(ctl-out) +11 CI[+2,+20] clusters=15 (robot questions)
  SS on-time (scorer)      n=  60 ctl   53 (0.883) out   46 (0.767) harm(ctl-out) +7 CI[+1,+13] clusters=60 (SS questions)
  SS within_L (outcome)    n=  60 ctl   54 (0.900) out   46 (0.767) harm(ctl-out) +8 CI[+2,+14] clusters=60 (SS questions)
  dashcam within_L         n=1984 ctl 1465 (0.738) out 1054 (0.531) harm(ctl-out) +411 CI[+212,+628] clusters=6 (60 s blocks, 1984 instants; unmatched ctl 0 out 0)
== DURING-OUTAGE [t0,R] (beside) [407.5,595.5)  len 188 s
  robot cbd                n=  40 ctl   25 (0.625) out   16 (0.400) harm(ctl-out) +9 CI[+0,+20] clusters=13 (robot questions)
  robot cloud on-time      n=  40 ctl   21 (0.525) out    0 (0.000) harm(ctl-out) +21 CI[+10,+33] clusters=13 (robot questions)
  SS on-time (scorer)      n=  37 ctl   34 (0.919) out   37 (1.000) harm(ctl-out) -3 CI[-6,+0] clusters=37 (SS questions)
  SS within_L (outcome)    n=  37 ctl   34 (0.919) out   37 (1.000) harm(ctl-out) -3 CI[-6,+0] clusters=37 (SS questions)
  dashcam within_L         n=1251 ctl 1049 (0.839) out 1251 (1.000) harm(ctl-out) -202 CI[-324,-80] clusters=4 (60 s blocks, 1251 instants; unmatched ctl 0 out 0)
== WHOLE RUN (beside) [0.0,1201.0)  len 1201 s
  robot cbd                n= 283 ctl  154 (0.544) out  134 (0.473) harm(ctl-out) +20 CI[+4,+39] clusters=47 (robot questions)
  robot cloud on-time      n= 283 ctl  181 (0.640) out  133 (0.470) harm(ctl-out) +48 CI[+27,+72] clusters=47 (robot questions)
  SS on-time (scorer)      n= 237 ctl  199 (0.840) out  176 (0.743) harm(ctl-out) +23 CI[+10,+36] clusters=237 (SS questions)
  SS within_L (outcome)    n= 237 ctl  200 (0.844) out  177 (0.747) harm(ctl-out) +23 CI[+10,+36] clusters=237 (SS questions)
  dashcam within_L         n=7850 ctl 5343 (0.681) out 4561 (0.581) harm(ctl-out) +782 CI[+133,+1447] clusters=20 (60 s blocks, 7850 instants; unmatched ctl 0 out 0)
CATCH-UP: uncached tokens (robot requests by t_submit)
  [R,R+300]    ctl n=1218 tok=304438 | out n=2604 tok=493299 | out-ctl tok +188861 (+62.0%)
  [R,R+B]      ctl n=10 tok=15458 | out n=43 tok=50155 | out-ctl tok +34697 (+224.5%)
  [t0,R]       ctl n=69 tok=134597 | out n=0 tok=0 | out-ctl tok -134597 (-100.0%)
  [R+B,R+300]  ctl n=1208 tok=288980 | out n=2561 tok=443144 | out-ctl tok +154164 (+53.3%)
