== netwin rung3_n20_s4_t4075  outage=covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link  control=covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30  t0=407.5 d=188.0 R=595.5
POSITIVE CONTROL control: robot cbd rows 283, cbd True 131 (committed robot_headline 0.462898 x n 283 = 131.0); sylib classifier correct==committed cbd on 283 of 283
  control SS: n 237 on_time 163 (committed 163); within_L(outcomes) 165; dashcam within(1.0) 3748 vs within_L 3748 of 7850 monitors
POSITIVE CONTROL outage: robot cbd rows 283 True 123 (headline 0.434629 x 283); classifier agree 283 of 283; SS on_time 168 (committed 168) within_L 173; dashcam within(1.0) 4518 vs within_L 4518
  same opportunity ids in both cells: robot 283/283, SS 237/237
B_obs DEFINITION (fixed before outcomes): rate_W(t)=sum uncached prompt tokens of robot requests with t_submit in (t-W,t] / W, 1 s grid; ctl(t)=control rate at the same absolute time; sd=sd of control rate over [60,t0). DEF1=first t>=R, after outage rate first exceeds ctl+1sd, at which outage<=ctl+1sd. DEF2=last exceedance+1 s. Rule window = DEF1 at W=10; others sensitivity.
  W= 5: ctl pre mean 1602 sd 2483 tok/s; first exceed R+2; B_obs DEF1 6 s DEF2 578 s
  W=10: ctl pre mean 1602 sd 1684 tok/s; first exceed R+2; B_obs DEF1 12 s DEF2 582 s
  W=20: ctl pre mean 1606 sd 1086 tok/s; first exceed R+8; B_obs DEF1 20 s DEF2 592 s
  rate trace W=10 (t-R,ctl,out): [(-10, 1942, 0), (0, 572, 0), (0, 572, 740), (10, 2016, 4995), (20, 2209, 1141), (30, 1653, 117), (40, 981, 1220), (50, 63, 673), (60, 200, 99), (70, 504, 99), (80, 303, 491), (90, 1177, 1818), (100, 1174, 1481), (110, 722, 217), (120, 365, 158), (130, 568, 410), (140, 3389, 3293), (150, 2137, 2677), (160, 6498, 5529), (170, 62, 369), (180, 4454, 2156), (190, 2754, 5026), (200, 41, 41), (210, 5003, 6315), (220, 1191, 255), (230, 3971, 757), (240, 0, 0), (250, 1516, 3907), (260, 556, 0), (270, 2237, 1220), (280, 191, 0), (290, 316, 1493)]
  drain cross-check from outage log: {'n_deferred_frames': 1312, 'deferred_own_tokens': 118328, 'n_victims': 14, 'uplink_queue_max_max': 1.3, 'last_backlogged_delivery': None, 'n_backlogged': 0, 'last_delayed_submit': None, 'n_delayed_after_R': 0}
  deficit-recovery marker (victim robot uncached tokens, cum out minus ctl from t0): deficit at R -439572 tok; first t>=R with cum out>=ctl: never; end-of-run diff -355427
  DEF1 vs DEF2 vs drain: 12 / 582 / n/a  UNSTABLE: DEF1 differs >50% across W or <30 s (bursty); DEF1(W=10) kept as rule
RULE WINDOW (user ruling, amends D332 item 8): every arm and seed scored over ONE FIXED [R,R+120]; sensitivity [R,R+60], [R,R+300]. B_obs DEF1/DEF2 above are DESCRIPTIVE per arm only (B_obs depends on the arm).
  B_obs descriptive (W=10): DEF1 12 s, DEF2 582 s (outage arm vs control-threshold)
== RULE fixed [R,R+120] [595.5,715.5)  len 120 s
  robot cbd                n=  26 ctl   19 (0.731) out   17 (0.654) harm(ctl-out) +2 CI[+0,+6] clusters=7 (robot questions)
  robot cloud on-time      n=  26 ctl   22 (0.846) out   20 (0.769) harm(ctl-out) +2 CI[-2,+7] clusters=7 (robot questions)
  SS on-time (scorer)      n=  24 ctl   21 (0.875) out   21 (0.875) harm(ctl-out) +0 CI[-5,+5] clusters=24 (SS questions)
  SS within_L (outcome)    n=  24 ctl   22 (0.917) out   22 (0.917) harm(ctl-out) +0 CI[-4,+4] clusters=24 (SS questions)
  dashcam within_L         n= 797 ctl  588 (0.738) out  563 (0.706) harm(ctl-out) +25 CI[-42,+87] clusters=3 (60 s blocks, 797 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+60] [595.5,655.5)  len 60 s
  robot cbd                n=  12 ctl   10 (0.833) out    8 (0.667) harm(ctl-out) +2 CI[+0,+6] clusters=4 (robot questions)
  robot cloud on-time      n=  12 ctl    8 (0.667) out    6 (0.500) harm(ctl-out) +2 CI[-2,+6] clusters=4 (robot questions)
  SS on-time (scorer)      n=  12 ctl   10 (0.833) out    9 (0.750) harm(ctl-out) +1 CI[-4,+6] clusters=12 (SS questions)
  SS within_L (outcome)    n=  12 ctl   10 (0.833) out   10 (0.833) harm(ctl-out) +0 CI[-4,+4] clusters=12 (SS questions)
  dashcam within_L         n= 386 ctl  263 (0.681) out  224 (0.580) harm(ctl-out) +39 CI[-46,+122] clusters=7 (10 s blocks, 386 instants; unmatched ctl 0 out 0)
== sensitivity fixed [R,R+300] [595.5,895.5)  len 300 s
  robot cbd                n=  67 ctl   39 (0.582) out   35 (0.522) harm(ctl-out) +4 CI[+0,+10] clusters=15 (robot questions)
  robot cloud on-time      n=  67 ctl   35 (0.522) out   41 (0.612) harm(ctl-out) -6 CI[-16,+4] clusters=15 (robot questions)
  SS on-time (scorer)      n=  60 ctl   46 (0.767) out   40 (0.667) harm(ctl-out) +6 CI[-1,+13] clusters=60 (SS questions)
  SS within_L (outcome)    n=  60 ctl   47 (0.783) out   43 (0.717) harm(ctl-out) +4 CI[-2,+10] clusters=60 (SS questions)
  dashcam within_L         n=1984 ctl 1080 (0.544) out 1149 (0.579) harm(ctl-out) -69 CI[-261,+87] clusters=6 (60 s blocks, 1984 instants; unmatched ctl 0 out 0)
== DURING-OUTAGE [t0,R] (beside) [407.5,595.5)  len 188 s
  robot cbd                n=  40 ctl   20 (0.500) out   16 (0.400) harm(ctl-out) +4 CI[-3,+12] clusters=13 (robot questions)
  robot cloud on-time      n=  40 ctl   14 (0.350) out    0 (0.000) harm(ctl-out) +14 CI[+5,+23] clusters=13 (robot questions)
  SS on-time (scorer)      n=  37 ctl   24 (0.649) out   37 (1.000) harm(ctl-out) -13 CI[-19,-7] clusters=37 (SS questions)
  SS within_L (outcome)    n=  37 ctl   24 (0.649) out   37 (1.000) harm(ctl-out) -13 CI[-19,-7] clusters=37 (SS questions)
  dashcam within_L         n=1251 ctl  592 (0.473) out 1251 (1.000) harm(ctl-out) -659 CI[-916,-402] clusters=4 (60 s blocks, 1251 instants; unmatched ctl 0 out 0)
== WHOLE RUN (beside) [0.0,1201.0)  len 1201 s
  robot cbd                n= 283 ctl  131 (0.463) out  123 (0.435) harm(ctl-out) +8 CI[-6,+25] clusters=47 (robot questions)
  robot cloud on-time      n= 283 ctl  124 (0.438) out  111 (0.392) harm(ctl-out) +13 CI[-9,+37] clusters=47 (robot questions)
  SS on-time (scorer)      n= 237 ctl  163 (0.688) out  168 (0.709) harm(ctl-out) -5 CI[-21,+10] clusters=237 (SS questions)
  SS within_L (outcome)    n= 237 ctl  165 (0.696) out  173 (0.730) harm(ctl-out) -8 CI[-23,+6] clusters=237 (SS questions)
  dashcam within_L         n=7850 ctl 3748 (0.477) out 4518 (0.576) harm(ctl-out) -770 CI[-1597,-54] clusters=20 (60 s blocks, 7850 instants; unmatched ctl 0 out 0)
CATCH-UP: uncached tokens (robot requests by t_submit)
  [R,R+300]    ctl n=1598 tok=489556 | out n=281 tok=533835 | out-ctl tok +44279 (+9.0%)
  [R,R+B]      ctl n=7 tok=21349 | out n=49 tok=57555 | out-ctl tok +36206 (+169.6%)
  [t0,R]       ctl n=136 tok=353967 | out n=1235 tok=3705 | out-ctl tok -350262 (-99.0%)
  [R+B,R+300]  ctl n=1591 tok=468207 | out n=232 tok=476280 | out-ctl tok +8073 (+1.7%)
