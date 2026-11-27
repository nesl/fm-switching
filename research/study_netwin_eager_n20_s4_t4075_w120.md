== netwin eager_n20_s4_t4075  outage=covex-v6-fair-final-cand-tl-sync-eager_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link_qp  control=covex-v6-fair-final-cand-tl_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp  t0=407.5 d=188.0 R=595.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 154 (committed robot_headline 0.544170 x n 283 = 154.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 199 (committed 199); within_L(outcomes) 200; dashcam within(1.0) 5343 vs within_L 5343 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 134 (headline 0.473498 x 283); classifier agree 283 of 283; SS on_time 169 (committed 169) within_L 170; dashcam within(1.0) 4344 vs within_L 4344
  same opportunity ids in both cells: robot 283/283, SS 237/237
B_obs DEFINITION (fixed before outcomes): rate_W(t)=sum uncached prompt tokens of robot requests with t_submit in (t-W,t] / W, 1 s grid; ctl(t)=control rate at the same absolute time; sd=sd of control rate over [60,t0). DEF1=first t>=R, after outage rate first exceeds ctl+1sd, at which outage<=ctl+1sd. DEF2=last exceedance+1 s. Rule window = DEF1 at W=10; others sensitivity.
  W= 5: ctl pre mean 1179 sd 1474 tok/s; first exceed R+0; B_obs DEF1 6 s DEF2 594 s
  W=10: ctl pre mean 1177 sd 1010 tok/s; first exceed R+0; B_obs DEF1 12 s DEF2 598 s
  W=20: ctl pre mean 1180 sd 758 tok/s; first exceed R+2; B_obs DEF1 22 s DEF2 606 s
  rate trace W=10 (t-R,ctl,out): [(-10, 859, 0), (0, 111, 0), (0, 111, 1215), (10, 1426, 3661), (20, 1032, 2931), (30, 713, 3820), (40, 546, 1294), (50, 73, 2609), (60, 1104, 1662), (70, 301, 446), (80, 392, 485), (90, 967, 1802), (100, 1450, 1436), (110, 317, 2177), (120, 259, 3021), (130, 411, 432), (140, 200, 480), (150, 2119, 6580), (160, 2351, 484), (170, 446, 7125), (180, 1385, 0), (190, 2715, 6486), (200, 793, 96), (210, 2580, 2466), (220, 869, 4483), (230, 1836, 127), (240, 437, 2597), (250, 158, 374), (260, 614, 200), (270, 605, 3421), (280, 802, 0), (290, 2208, 3947)]
  drain cross-check from outage log: {'n_deferred_frames': 1312, 'deferred_own_tokens': 118328, 'n_victims': 14, 'uplink_queue_max_max': 1.3, 'last_backlogged_delivery': None, 'n_backlogged': 0, 'last_delayed_submit': None, 'n_delayed_after_R': 0}
  deficit-recovery marker (victim robot uncached tokens, cum out minus ctl from t0): deficit at R -166717 tok; first t>=R with cum out>=ctl: R+118 s; end-of-run diff +448565
  DEF1 vs DEF2 vs drain: 12 / 598 / n/a  UNSTABLE: DEF1 differs >50% across W or <30 s (bursty); DEF1(W=10) kept as rule
RULE WINDOW (user ruling, amends D332 item 8): every arm and seed scored over ONE FIXED [R,R+120]; sensitivity [R,R+60], [R,R+300]. B_obs DEF1/DEF2 above are DESCRIPTIVE per arm only (B_obs depends on the arm).
  B_obs descriptive (W=10): DEF1 12 s, DEF2 598 s (outage arm vs control-threshold)
== RULE fixed [R,R+120] [595.5,715.5)  len 120 s
  robot cbd                n=  26 ctl   20 (0.769) out   19 (0.731) harm(ctl-out) +1 CI[+0,+3] clusters=7 (robot questions)
  robot cloud on-time      n=  26 ctl   25 (0.962) out   17 (0.654) harm(ctl-out) +8 CI[+1,+17] clusters=7 (robot questions)
  SS on-time (scorer)      n=  24 ctl   24 (1.000) out   16 (0.667) harm(ctl-out) +8 CI[+4,+13] clusters=24 (SS questions)
  SS within_L (outcome)    n=  24 ctl   24 (1.000) out   17 (0.708) harm(ctl-out) +7 CI[+3,+12] clusters=24 (SS questions)
  dashcam within_L         n= 797 ctl  692 (0.868) out  268 (0.336) harm(ctl-out) +424 CI[+87,+747] clusters=3 (60 s blocks, 797 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+60] [595.5,655.5)  len 60 s
  robot cbd                n=  12 ctl   11 (0.917) out   10 (0.833) harm(ctl-out) +1 CI[+0,+3] clusters=4 (robot questions)
  robot cloud on-time      n=  12 ctl   11 (0.917) out    7 (0.583) harm(ctl-out) +4 CI[+1,+7] clusters=4 (robot questions)
  SS on-time (scorer)      n=  12 ctl   12 (1.000) out    6 (0.500) harm(ctl-out) +6 CI[+3,+9] clusters=12 (SS questions)
  SS within_L (outcome)    n=  12 ctl   12 (1.000) out    7 (0.583) harm(ctl-out) +5 CI[+2,+8] clusters=12 (SS questions)
  dashcam within_L         n= 386 ctl  318 (0.824) out   53 (0.137) harm(ctl-out) +265 CI[+189,+334] clusters=7 (10 s blocks, 386 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+300] [595.5,895.5)  len 300 s
  robot cbd                n=  67 ctl   38 (0.567) out   37 (0.552) harm(ctl-out) +1 CI[-5,+6] clusters=15 (robot questions)
  robot cloud on-time      n=  67 ctl   52 (0.776) out   37 (0.552) harm(ctl-out) +15 CI[+2,+29] clusters=15 (robot questions)
  SS on-time (scorer)      n=  60 ctl   53 (0.883) out   36 (0.600) harm(ctl-out) +17 CI[+7,+26] clusters=60 (SS questions)
  SS within_L (outcome)    n=  60 ctl   54 (0.900) out   37 (0.617) harm(ctl-out) +17 CI[+7,+26] clusters=60 (SS questions)
  dashcam within_L         n=1984 ctl 1465 (0.738) out  668 (0.337) harm(ctl-out) +797 CI[+484,+1135] clusters=6 (60 s blocks, 1984 instants; unmatched ctl 0 out 0)
== DURING-OUTAGE [t0,R] (beside) [407.5,595.5)  len 188 s
  robot cbd                n=  40 ctl   25 (0.625) out   16 (0.400) harm(ctl-out) +9 CI[+0,+20] clusters=13 (robot questions)
  robot cloud on-time      n=  40 ctl   21 (0.525) out    0 (0.000) harm(ctl-out) +21 CI[+10,+33] clusters=13 (robot questions)
  SS on-time (scorer)      n=  37 ctl   34 (0.919) out   37 (1.000) harm(ctl-out) -3 CI[-6,+0] clusters=37 (SS questions)
  SS within_L (outcome)    n=  37 ctl   34 (0.919) out   37 (1.000) harm(ctl-out) -3 CI[-6,+0] clusters=37 (SS questions)
  dashcam within_L         n=1251 ctl 1049 (0.839) out 1251 (1.000) harm(ctl-out) -202 CI[-324,-80] clusters=4 (60 s blocks, 1251 instants; unmatched ctl 0 out 0)
== WHOLE RUN (beside) [0.0,1201.0)  len 1201 s
  robot cbd                n= 283 ctl  154 (0.544) out  134 (0.473) harm(ctl-out) +20 CI[+3,+37] clusters=47 (robot questions)
  robot cloud on-time      n= 283 ctl  181 (0.640) out  123 (0.435) harm(ctl-out) +58 CI[+33,+86] clusters=47 (robot questions)
  SS on-time (scorer)      n= 237 ctl  199 (0.840) out  169 (0.713) harm(ctl-out) +30 CI[+14,+45] clusters=237 (SS questions)
  SS within_L (outcome)    n= 237 ctl  200 (0.844) out  170 (0.717) harm(ctl-out) +30 CI[+14,+45] clusters=237 (SS questions)
  dashcam within_L         n=7850 ctl 5343 (0.681) out 4344 (0.553) harm(ctl-out) +999 CI[+246,+1785] clusters=20 (60 s blocks, 7850 instants; unmatched ctl 0 out 0)
CATCH-UP: uncached tokens (robot requests by t_submit)
  [R,R+300]    ctl n=1218 tok=304438 | out n=2332 tok=664015 | out-ctl tok +359577 (+118.1%)
  [R,R+B]      ctl n=10 tok=15458 | out n=51 tok=48961 | out-ctl tok +33503 (+216.7%)
  [t0,R]       ctl n=69 tok=134597 | out n=0 tok=0 | out-ctl tok -134597 (-100.0%)
  [R+B,R+300]  ctl n=1208 tok=288980 | out n=2281 tok=615054 | out-ctl tok +326074 (+112.8%)
