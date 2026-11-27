Lost-instant classifier (read-only). RULES (fixed before any count was read):
Window [R,R+120), R=595.5. Instant = dashcam monitor outcome keyed (device_id, opportunity_id), matched across cells.
on-time = t_delivered - t_opportunity <= 1.0 (the committed scorer's within(o,1.0)). LOST = on-time in control, not in outage cell.
Per lost instant, in the outage cell, first match wins:
 B  SHED/NOT RELEASED: outcome has no cloud request (cloud_payload.request_id null or absent from request log):
    never sent to the engine (held by the C5 AIMD cap / shares until expiry, or declined). C5 vs shares cannot be split per instant
    (hybrid_arm.py _c5 counts only totals); B is therefore 'not released', an upper bound on C5.
 A  LATE BEHIND CATCH-UP / BURST WORK: dash request D has [Ts, Tf] (t_submit, t_first_token; t_done if none). Another non-monitor
    request X (decision kind release_piece/release_recall/touch, uncached = prompt-cached >= 200 = coordinator C5ATTR_UNCACHED_MIN)
    is AHEAD of D if X.t_submit <= D.Ts and X.prefill_end > D.Ts, prefill_end = X.t_first_token (X.t_done if none).
    A_S2: some X ahead is a release_piece of an outage-robot device with decision t >= R-0.1 (S2 catch-up/backlog piece; in the
          F0/eager cells these are the catch-up pieces; includes ordinary >=200-token pieces of those robots, so it is an upper bound)
    A_oth: X ahead exists, none is such a piece (recall, other-device piece, touch >=200)
    A_S2 takes precedence if both. For rung 3 the same predicate is reported as 'A_burst' (outage-robot piece t>=R: the robot's
    deferred-backlog burst, not S2) and A_oth.
    A_cu9 (F0 only, subset of A_S2): X ahead belongs to a cu_value_decisions release row (same sid, decision t equal within 1 ms).
 C  NEITHER: request exists, nothing ahead. Sub-tag by dominant stage of lateness: uplink (t_frame_arrive-t_opp), release (D.Ts-t_frame_arrive),
    engine (Tf-Ts), deliver (t_delivered-Tf); and 'hard' if the same instant is also late in the rung-3 plain control (intrinsically late).
Context controls: the same A-predicate rate among instants on time in BOTH cells (A should discriminate), and among control-late ones.

===== F0 matched 797 lost 148 gained(reverse) 22 net harm 126
  B         137   92.6%
  A_S2        3    2.0%
  A_oth       1    0.7%
  C           7    4.7%
  sub: {('B', 'no_request'): 137, ('C', 'rel'): 1, ('C', 'eng+hard'): 3, ('A_oth', ''): 1, ('A_S2', 'piece'): 3, ('C', 'eng'): 3}
  A-predicate (anything ahead, S2/burst piece ahead, total) lost: (4, 3, 148) ; both-on-time context: (137, 94, 544)
  stage medians(med,max,n) lost: {'up': (0.057, 0.12, 11), 'rel': (0.107, 0.6, 11), 'eng': (0.888, 1.03, 11), 'dl': (0.022, 0.02, 11)}
  stage medians both-on-time: {'up': (0.057, 0.18, 544), 'rel': (0.089, 0.58, 544), 'eng': (0.294, 0.82, 544), 'dl': (0.022, 0.02, 544)}
  catch-up-class work released in window (outage-robot pieces>=200 uncached, t>=R): n=77 tok=81895
  by 10 s block (t-R): lost | B A_S2/burst A_oth C | pieces released(n, tokens) | last piece t
     0- 10   42 | B 42 S2/burst  0 oth  0 C  0 |  38 pcs  42802 tok
    10- 20   28 | B 27 S2/burst  0 oth  0 C  1 |   7 pcs   7019 tok
    20- 30    4 | B  4 S2/burst  0 oth  0 C  0 |   2 pcs   1994 tok
    30- 40   39 | B 39 S2/burst  0 oth  0 C  0 |   4 pcs   4012 tok
    40- 50    6 | B  5 S2/burst  0 oth  0 C  1 |   5 pcs   5019 tok
    50- 60    0 | B  0 S2/burst  0 oth  0 C  0 |   3 pcs   2925 tok
    60- 70    0 | B  0 S2/burst  0 oth  0 C  0 |   1 pcs   1005 tok
    70- 80    0 | B  0 S2/burst  0 oth  0 C  0 |   5 pcs   4917 tok
    80- 90   18 | B 12 S2/burst  1 oth  1 C  4 |   5 pcs   5003 tok
    90-100   11 | B  8 S2/burst  2 oth  0 C  1 |   3 pcs   2285 tok
   100-110    0 | B  0 S2/burst  0 oth  0 C  0 |   1 pcs   1001 tok
   110-120    0 | B  0 S2/burst  0 oth  0 C  0 |   3 pcs   3913 tok
  cu_value release rows (t, sid): [(606.97, 'robo009'), (607.77, 'robo009'), (609.77, 'robo005'), (610.97, 'robo002'), (615.37, 'robo005'), (623.37, 'robo010'), (628.37, 'robo005'), (629.47, 'robo009'), (631.87, 'robo010')]
  lost instants overlapping cu9 releases: 0
===== eager matched 797 lost 450 gained(reverse) 26 net harm 424
  B         395   87.8%
  A_S2        4    0.9%
  A_oth      12    2.7%
  C          39    8.7%
  sub: {('B', 'no_request'): 395, ('C', 'eng+hard'): 8, ('C', 'eng'): 29, ('A_oth', ''): 12, ('A_S2', 'piece'): 4, ('C', 'rel'): 2}
  A-predicate (anything ahead, S2/burst piece ahead, total) lost: (16, 4, 450) ; both-on-time context: (30, 8, 242)
  stage medians(med,max,n) lost: {'up': (0.053, 0.14, 55), 'rel': (0.08, 0.71, 55), 'eng': (1.106, 8.26, 55), 'dl': (0.022, 0.02, 55)}
  stage medians both-on-time: {'up': (0.05, 0.18, 242), 'rel': (0.098, 0.6, 242), 'eng': (0.318, 0.86, 242), 'dl': (0.022, 0.02, 242)}
  catch-up-class work released in window (outage-robot pieces>=200 uncached, t>=R): n=112 tok=172580
  by 10 s block (t-R): lost | B A_S2/burst A_oth C | pieces released(n, tokens) | last piece t
     0- 10   42 | B 42 S2/burst  0 oth  0 C  0 |  45 pcs  42313 tok
    10- 20   31 | B 31 S2/burst  0 oth  0 C  0 |  12 pcs  11868 tok
    20- 30   51 | B 49 S2/burst  0 oth  0 C  2 |  35 pcs  35979 tok
    30- 40   49 | B 45 S2/burst  2 oth  0 C  2 |  10 pcs   8498 tok
    40- 50   63 | B 50 S2/burst  0 oth  6 C  7 |   2 pcs  19012 tok
    50- 60   40 | B 37 S2/burst  0 oth  1 C  2 |   1 pcs  12791 tok
    60- 70   20 | B 18 S2/burst  0 oth  0 C  2 |   0 pcs      0 tok
    70- 80   15 | B  5 S2/burst  0 oth  0 C 10 |   1 pcs   1091 tok
    80- 90   13 | B 11 S2/burst  0 oth  0 C  2 |   2 pcs  11810 tok
    90-100   32 | B 27 S2/burst  0 oth  3 C  2 |   1 pcs   8909 tok
   100-110   53 | B 49 S2/burst  0 oth  0 C  4 |   2 pcs  18228 tok
   110-120   41 | B 31 S2/burst  2 oth  2 C  6 |   1 pcs   2081 tok
===== rung3 matched 797 lost 109 gained(reverse) 84 net harm 25
  B          99   90.8%
  A_burst     8    7.3%
  A_oth       1    0.9%
  C           1    0.9%
  sub: {('B', 'no_request'): 99, ('A_oth', ''): 1, ('A_burst', 'piece'): 8, ('C', 'eng'): 1}
  A-predicate (anything ahead, S2/burst piece ahead, total) lost: (9, 8, 109) ; both-on-time context: (92, 63, 479)
  stage medians(med,max,n) lost: {'up': (0.061, 0.12, 10), 'rel': (0.109, 0.12, 10), 'eng': (0.969, 1.56, 10), 'dl': (0.022, 0.02, 10)}
  stage medians both-on-time: {'up': (0.056, 0.18, 479), 'rel': (0.094, 0.5, 479), 'eng': (0.215, 0.81, 479), 'dl': (0.022, 0.02, 479)}
  catch-up-class work released in window (outage-robot pieces>=200 uncached, t>=R): n=65 tok=69791
  by 10 s block (t-R): lost | B A_S2/burst A_oth C | pieces released(n, tokens) | last piece t
     0- 10   40 | B 40 S2/burst  0 oth  0 C  0 |  41 pcs  38981 tok
    10- 20   11 | B 10 S2/burst  0 oth  1 C  0 |   2 pcs   2000 tok
    20- 30    0 | B  0 S2/burst  0 oth  0 C  0 |   0 pcs      0 tok
    30- 40   31 | B 30 S2/burst  0 oth  0 C  1 |   2 pcs   1998 tok
    40- 50    4 | B  4 S2/burst  0 oth  0 C  0 |   6 pcs   6008 tok
    50- 60    0 | B  0 S2/burst  0 oth  0 C  0 |   1 pcs    999 tok
    60- 70    0 | B  0 S2/burst  0 oth  0 C  0 |   1 pcs    995 tok
    70- 80    0 | B  0 S2/burst  0 oth  0 C  0 |   3 pcs   2989 tok
    80- 90    7 | B  2 S2/burst  5 oth  0 C  0 |   4 pcs  10804 tok
    90-100   16 | B 13 S2/burst  3 oth  0 C  0 |   3 pcs   2999 tok
   100-110    0 | B  0 S2/burst  0 oth  0 C  0 |   1 pcs   1009 tok
   110-120    0 | B  0 S2/burst  0 oth  0 C  0 |   1 pcs   1009 tok

== B-instant diagnosis (bdiag.py)
F0: B=137 decision kinds on the opportunity: {('release_infeasible',): 121, (): 16}
   dash requests in flight (submit..first token) at the B instant: outage cell mean 0.8 max 5 | control cell same time mean 1.5 max 6 | cap 8
   control released these B instants to cloud: 137 of 137
   window instants with no cloud request: outage 216, control 99 of 797
   >=200-token non-monitor prefill tokens in flight at B instants: outage mean 11111 (share with >0: 0.76) | control same time mean 383 (share >0: 0.26)
eager: B=395 decision kinds on the opportunity: {('release_infeasible',): 338, (): 57}
   dash requests in flight (submit..first token) at the B instant: outage cell mean 1.1 max 6 | control cell same time mean 1.4 max 6 | cap 8
   control released these B instants to cloud: 395 of 395
   window instants with no cloud request: outage 468, control 99 of 797
   >=200-token non-monitor prefill tokens in flight at B instants: outage mean 9435 (share with >0: 0.80) | control same time mean 286 (share >0: 0.25)
rung3: B=99 decision kinds on the opportunity: {('release_infeasible',): 91, (): 8}
   dash requests in flight (submit..first token) at the B instant: outage cell mean 0.9 max 5 | control cell same time mean 1.7 max 6 | cap 8
   control released these B instants to cloud: 99 of 99
   window instants with no cloud request: outage 222, control 190 of 797
   >=200-token non-monitor prefill tokens in flight at B instants: outage mean 13580 (share with >0: 0.80) | control same time mean 381 (share >0: 0.28)

== decomposition of in-flight work at B instants (decomp.py)
== F0: B=137 of 148 lost; ref = median in-flight uncached tokens at control released instants = 0 (n=698)
  mean per B instant, tokens(n in flight): S2 8328 (8.09) | recall 2529 (0.49) | piece_other 0 (0.00) | touch 23 (3.36) | other 0 (0.00)
  mean total 10880 median 8513; S2 share of tokens 76.5%
  B with any S2 in flight 76 (55.5%); S2 >= half of in-flight tokens 62 (45.3%)
  B with in-flight > ref: now 133; after removing S2 89 (so 44 of 137 B would fall to/below ref: 32.1% of B, 29.7% of all lost)
== eager: B=395 of 450 lost; ref = median in-flight uncached tokens at control released instants = 0 (n=698)
  mean per B instant, tokens(n in flight): S2 8297 (8.58) | recall 795 (0.26) | piece_other 0 (0.00) | touch 856 (10.54) | other 0 (0.00)
  mean total 9948 median 9205; S2 share of tokens 83.4%
  B with any S2 in flight 353 (89.4%); S2 >= half of in-flight tokens 317 (80.3%)
  B with in-flight > ref: now 392; after removing S2 349 (so 43 of 395 B would fall to/below ref: 10.9% of B, 9.6% of all lost)
== rung3 (S2 label = outage-robot burst pieces): B=99 of 109 lost; ref = median in-flight uncached tokens at control released instants = 0 (n=607)
  mean per B instant, tokens(n in flight): S2 10055 (10.47) | recall 3278 (1.36) | piece_other 0 (0.00) | touch 11 (2.15) | other 0 (0.00)
  mean total 13343 median 9635; S2 share of tokens 75.4%
  B with any S2 in flight 69 (69.7%); S2 >= half of in-flight tokens 58 (58.6%)
  B with in-flight > ref: now 82; after removing S2 64 (so 18 of 99 B would fall to/below ref: 18.2% of B, 16.5% of all lost)
sensitivity (control in-flight reference percentiles):
F0 thr p90=1005: B above thr 96, after removing S2 43, resolved by S2 removal 53 (38.7% of B)
F0 thr max=3180: B above thr 77, after removing S2 33, resolved by S2 removal 44 (32.1% of B)
eager thr p90=1005: B above thr 301, after removing S2 63, resolved by S2 removal 238 (60.3% of B)
eager thr max=3180: B above thr 251, after removing S2 38, resolved by S2 removal 213 (53.9% of B)
rung3 thr p90=1008: B above thr 72, after removing S2 45, resolved by S2 removal 27 (27.3% of B)
rung3 thr max=11694: B above thr 46, after removing S2 4, resolved by S2 removal 42 (42.4% of B)
