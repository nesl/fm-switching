D347 STEP 1 POSITIVE CONTROL (origin c6691372). CPU only. STOPPED at the positive control: check (2) does not reproduce.

Trace regeneration: lib.gen() with the harness's own generator call (trace.py on origin, DS.ROBOT_DEADLINE_S=3.0, lh_req/ss2/epg f3/per-frame/rq30, k14 d188 evidence t0, link marks). fairness_digest equals the committed run_meta.json digest for all 9 cells: s4 c7c74faee1af067c, s5 667b9d684c2ee368, s6 958cd65d5047cf74.

== posctl.py ==
s4 t0 407.5 R 595.5 victims 14  backlog frames min/med/max 93/94/94  tokens med 8460  bytes med 2309580  serialise_s min/med/max 1.34/1.36/1.36  (sum frames 1312, meta backlog_tokens_d2 118080)
   victim qs in [R,R+120): 26 ; post-R victim qs 151, in interrupted sessions 120
   rung3    n 26 on_time 21  cached_fraction n 26 median 0.948
   cand-tl  n 26 on_time 21  cached_fraction n 22 median 0.938
   F0       n 26 on_time 22  cached_fraction n 23 median 0.942
s5 t0 880.5 R 1068.5 victims 14  backlog frames min/med/max 93/94/94  tokens med 8460  bytes med 2309580  serialise_s min/med/max 1.34/1.36/1.36  (sum frames 1313, meta backlog_tokens_d2 118170)
   victim qs in [R,R+120): 26 ; post-R victim qs 28, in interrupted sessions 28
   rung3    n 26 on_time 22  cached_fraction n 26 median 0.944
   cand-tl  n 26 on_time 21  cached_fraction n 23 median 0.949
   F0       n 26 on_time 12  cached_fraction n 18 median 0.917
s6 t0 261.5 R 449.5 victims 14  backlog frames min/med/max 93/94/94  tokens med 8460  bytes med 2309580  serialise_s min/med/max 1.34/1.36/1.36  (sum frames 1311, meta backlog_tokens_d2 117990)
   victim qs in [R,R+120): 26 ; post-R victim qs 182, in interrupted sessions 101
   rung3    n 26 on_time 18  cached_fraction n 26 median 0.857
   cand-tl  n 26 on_time 20  cached_fraction n 22 median 0.858
   F0       n 26 on_time 14  cached_fraction n 19 median 0.839

== posctl2.py (on-time variants; within_L == cloud_payload.on_time everywhere) ==
s4 rung3    {'within_L': 21, 'cloud_on_time': 21, 'has_cloud': 26, 'presented': 26}
s4 cand-tl  {'within_L': 21, 'cloud_on_time': 21, 'has_cloud': 22, 'presented': 26}
s4 F0       {'within_L': 22, 'cloud_on_time': 22, 'has_cloud': 23, 'presented': 26}
s5 rung3    {'within_L': 22, 'cloud_on_time': 22, 'has_cloud': 26, 'presented': 26}
s5 cand-tl  {'within_L': 21, 'cloud_on_time': 21, 'has_cloud': 23, 'presented': 26}
s5 F0       {'within_L': 12, 'cloud_on_time': 12, 'has_cloud': 18, 'presented': 26}
s6 rung3    {'within_L': 18, 'cloud_on_time': 18, 'has_cloud': 26, 'presented': 26}
s6 cand-tl  {'within_L': 20, 'cloud_on_time': 20, 'has_cloud': 22, 'presented': 26}
s6 F0       {'within_L': 14, 'cloud_on_time': 14, 'has_cloud': 19, 'presented': 26}

== posctl3.py: F0 s5 window questions not within_L ==
robo003 1071.3 deliv None upq 0.0 req None tok None path None
robo003 1109.6 deliv 3.42 upq 0.0 req r10049 tok 14071 path None
robo003 1110.0 deliv 3.09 upq 0.0 req r10059 tok 14071 path None
robo005 1115.9 deliv None upq 0.0 req None tok None path None
robo010 1134.5 deliv 4.54 upq 0.0 req r10578 tok 10291 path None
robo005 1135.3 deliv 4.23 upq 0.0 req r10603 tok 10831 path None
robo005 1136.9 deliv 3.24 upq 0.0 req r10652 tok 10921 path None
robo001 1138.1 deliv None upq 0.0 req None tok None path None
robo001 1163.4 deliv None upq 0.0 req None tok None path None
robo001 1166.8 deliv None upq 0.0 req None tok None path None
robo001 1169.8 deliv None upq 0.0 req None tok None path None
robo001 1176.8 deliv None upq 0.0 req None tok None path None
robo001 1183.7 deliv 4.16 upq 0.0 req r11282 tok 24151 path None
robo002 1185.6 deliv None upq 0.0 req None tok None path None

Serialise time = frame bytes x 8 / 13.6e6 (links.serialise_s); upload_s adds RTT/2 = 0.022 s -> 1.38 s.

=================== STEP 1 (resumed on coordinator instruction) ===================
Definitions used. Candidate t0: 0.5 s grid on [0, 750] (outage inside the run, at least 150 s after R = t0 + 300). Victims: all 14 robots
(k = 14 of the outage-perm prefix). Interrupted session: a victim session with >= 1 history_batch offered in [t0, t0 + 300) (exactly the
sessions holding deferred frames in the generated trace; validated equal on the generated d300 trace per seed). Affected ask: a victim
recall_question in an interrupted session asked at t >= R. Q = affected asks with R + 10 <= t <= R + 120. Over-limit: history_tokens at the
ask (which under buffered semantics already includes the backlog frames) + a conservative question bound (chars/3 + 20) > 32,768.
NEVER trimmed. Tie-break: earliest t0 among the maxima with zero over-limit asks. Rebuild: costs.py COLD_PREFILL_TOK_S {11000: 4500,
28000: 3800} with the committed nearest-size rule (recall_ttft_s, costs.py:106-117); 'lazy from warm' = tokens since t0 (prefix cached to
t0, backlog and post-R frames prefilled at the ask); 'cold' = whole prompt; 'backlog only' = only the session's deferred frames uncached.
s4 grid [0,750.0] n=1501  maxQ 46  chosen t0 622.0  #t0 at max 3 (first 622.0 last 625.5)  over-limit any t0: 0  max prompt bound 27061
   top {'t0': 622.0, 'R': 922.0, 'Q': 46, 'pre10': 1, 'r120_300': 29, 'whole_postR': 76, 'during': 65, 'over': 0, 'max_prompt': 26885}
   top {'t0': 625.0, 'R': 925.0, 'Q': 46, 'pre10': 2, 'r120_300': 28, 'whole_postR': 76, 'during': 64, 'over': 0, 'max_prompt': 26885}
   top {'t0': 625.5, 'R': 925.5, 'Q': 46, 'pre10': 2, 'r120_300': 28, 'whole_postR': 76, 'during': 64, 'over': 0, 'max_prompt': 26885}
   top {'t0': 619.0, 'R': 919.0, 'Q': 45, 'pre10': 1, 'r120_300': 31, 'whole_postR': 77, 'during': 64, 'over': 0, 'max_prompt': 26885}
   top {'t0': 619.5, 'R': 919.5, 'Q': 45, 'pre10': 1, 'r120_300': 31, 'whole_postR': 77, 'during': 64, 'over': 0, 'max_prompt': 26885}
   top {'t0': 620.0, 'R': 920.0, 'Q': 45, 'pre10': 1, 'r120_300': 31, 'whole_postR': 77, 'during': 64, 'over': 0, 'max_prompt': 26885}
   top {'t0': 620.5, 'R': 920.5, 'Q': 45, 'pre10': 1, 'r120_300': 31, 'whole_postR': 77, 'during': 64, 'over': 0, 'max_prompt': 26885}
   top {'t0': 621.5, 'R': 921.5, 'Q': 45, 'pre10': 1, 'r120_300': 30, 'whole_postR': 76, 'during': 65, 'over': 0, 'max_prompt': 26885}
   top {'t0': 622.5, 'R': 922.5, 'Q': 45, 'pre10': 2, 'r120_300': 29, 'whole_postR': 76, 'during': 65, 'over': 0, 'max_prompt': 26885}
   top {'t0': 623.0, 'R': 923.0, 'Q': 45, 'pre10': 2, 'r120_300': 29, 'whole_postR': 76, 'during': 65, 'over': 0, 'max_prompt': 26885}
s5 grid [0,750.0] n=1501  maxQ 29  chosen t0 401.0  #t0 at max 2 (first 401.0 last 401.5)  over-limit any t0: 0  max prompt bound 27147
   top {'t0': 401.0, 'R': 701.0, 'Q': 29, 'pre10': 1, 'r120_300': 30, 'whole_postR': 75, 'during': 54, 'over': 0, 'max_prompt': 27147}
   top {'t0': 401.5, 'R': 701.5, 'Q': 29, 'pre10': 0, 'r120_300': 30, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
   top {'t0': 400.5, 'R': 700.5, 'Q': 28, 'pre10': 2, 'r120_300': 31, 'whole_postR': 76, 'during': 53, 'over': 0, 'max_prompt': 27147}
   top {'t0': 402.0, 'R': 702.0, 'Q': 28, 'pre10': 1, 'r120_300': 30, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
   top {'t0': 402.5, 'R': 702.5, 'Q': 28, 'pre10': 1, 'r120_300': 30, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
   top {'t0': 403.0, 'R': 703.0, 'Q': 28, 'pre10': 1, 'r120_300': 30, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
   top {'t0': 403.5, 'R': 703.5, 'Q': 28, 'pre10': 1, 'r120_300': 30, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
   top {'t0': 404.0, 'R': 704.0, 'Q': 28, 'pre10': 1, 'r120_300': 30, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
   top {'t0': 404.5, 'R': 704.5, 'Q': 28, 'pre10': 1, 'r120_300': 30, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
   top {'t0': 405.0, 'R': 705.0, 'Q': 28, 'pre10': 1, 'r120_300': 31, 'whole_postR': 74, 'during': 55, 'over': 0, 'max_prompt': 27147}
s6 grid [0,750.0] n=1501  maxQ 37  chosen t0 736.0  #t0 at max 14 (first 736.0 last 742.5)  over-limit any t0: 0  max prompt bound 27019
   top {'t0': 736.0, 'R': 1036.0, 'Q': 37, 'pre10': 1, 'r120_300': 8, 'whole_postR': 46, 'during': 69, 'over': 0, 'max_prompt': 27019}
   top {'t0': 736.5, 'R': 1036.5, 'Q': 37, 'pre10': 1, 'r120_300': 8, 'whole_postR': 46, 'during': 69, 'over': 0, 'max_prompt': 27019}
   top {'t0': 737.0, 'R': 1037.0, 'Q': 37, 'pre10': 1, 'r120_300': 8, 'whole_postR': 46, 'during': 69, 'over': 0, 'max_prompt': 27019}
   top {'t0': 737.5, 'R': 1037.5, 'Q': 37, 'pre10': 1, 'r120_300': 8, 'whole_postR': 46, 'during': 69, 'over': 0, 'max_prompt': 27019}
   top {'t0': 738.0, 'R': 1038.0, 'Q': 37, 'pre10': 1, 'r120_300': 8, 'whole_postR': 46, 'during': 69, 'over': 0, 'max_prompt': 27019}
   top {'t0': 738.5, 'R': 1038.5, 'Q': 37, 'pre10': 1, 'r120_300': 8, 'whole_postR': 46, 'during': 69, 'over': 0, 'max_prompt': 27019}
   top {'t0': 739.0, 'R': 1039.0, 'Q': 37, 'pre10': 0, 'r120_300': 8, 'whole_postR': 45, 'during': 70, 'over': 0, 'max_prompt': 27019}
   top {'t0': 739.5, 'R': 1039.5, 'Q': 37, 'pre10': 0, 'r120_300': 8, 'whole_postR': 45, 'during': 70, 'over': 0, 'max_prompt': 27019}
   top {'t0': 740.0, 'R': 1040.0, 'Q': 37, 'pre10': 0, 'r120_300': 8, 'whole_postR': 45, 'during': 70, 'over': 0, 'max_prompt': 27019}
   top {'t0': 740.5, 'R': 1040.5, 'Q': 37, 'pre10': 0, 'r120_300': 8, 'whole_postR': 45, 'during': 70, 'over': 0, 'max_prompt': 27019}

=== s4 chosen t0 622.0 R 922.0  Q 46 | affected [R,R+10) 1  (R+120,R+300) 29  whole post-R 76  during outage 65  over-limit 0 (max prompt bound 26885)
   committed d188 t0 407.5: Q(d188) 21 ; Q(d300 at committed t0) 34
   VALIDATION on generated d300 trace: victims 14, interrupted sessions gen 19 vs search 19 equal=True, Q gen 46, digest 5e627f35cc0778f9
   backlog per victim frames min/med/max 149 / 150 / 150 ; tokens 13410 / 13500 / 13500 ; upload_s at 13.6 Mbps 2.18..2.19
   session-local time at t0 (device, local s, session duration s): [('robo000', 315.2, 600.0), ('robo001', 156.1, 600.0), ('robo002', 2.7, 600.0), ('robo003', 156.7, 600.0), ('robo004', 37.3, 600.5), ('robo005', 436.8, 600.0), ('robo006', 259.6, 322.0), ('robo007', 253.8, 600.2), ('robo008', 129.7, 600.0), ('robo009', 91.0, 600.0), ('robo010', 52.7, 600.0), ('robo011', 189.0, 334.4), ('robo012', 436.1, 600.0), ('robo013', 142.2, 600.0)]
   victims with no active session at t0: []
   Q window [R+10,R+120] n 46: history tokens min/med/max 7411 / 19876 / 26671 ; uncached since t0 7411 / 15885 / 18900 (no warm prefix: 7 asks, session started in-window) ; lazy-from-warm s min/med/max 1.65/3.93/4.97 MISS>3s 39 ; cold s 1.65/5.23/7.02 MISS>3s 39
   Q kinds: robot MCQ 46 ({'original': 6, 'reask': 40}) ; categories {'sequential_action': 18, 'visual_detail_recall': 11, 'location_trace': 8, 'temporal_ordering_recognition': 5, 'spatial_aware_reasoning': 1, 'time_duration': 3} ; per device {'robo011': 5, 'robo002': 7, 'robo001': 6, 'robo013': 5, 'robo007': 3, 'robo010': 3, 'robo008': 3, 'robo009': 7, 'robo004': 4, 'robo012': 2, 'robo003': 1}
   all post-R affected n 76: history tokens min/med/max 7411 / 20866 / 26671 ; uncached since t0 7411 / 16710 / 24300 (no warm prefix: 21 asks, session started in-window) ; lazy-from-warm s min/med/max 1.65/4.10/6.39 MISS>3s 63 ; cold s 1.65/5.49/7.02 MISS>3s 63
   Q neighbourhood t0-10..t0+10 (0.5 s): 612.0:41 612.5:41 613.0:42 613.5:43 614.0:43 614.5:43 615.0:44 615.5:44 616.0:44 616.5:44 617.0:44 617.5:44 618.0:44 618.5:44 619.0:45 619.5:45 620.0:45 620.5:45 621.0:44 621.5:45 622.0:46 622.5:45 623.0:45 623.5:45 624.0:45 624.5:45 625.0:46 625.5:46 626.0:45 626.5:44 627.0:44 627.5:44 628.0:44 628.5:43 629.0:41 629.5:41 630.0:41 630.5:41 631.0:42 631.5:41 632.0:41
   Q coarse every 25 s: 0:38 25:37 50:34 75:36 100:30 125:24 150:19 175:13 200:19 225:17 250:15 275:23 300:19 325:19 350:27 375:30 400:32 425:34 450:27 475:21 500:17 525:23 550:28 575:32 600:38 625:46 650:42 675:34 700:30 725:21 750:20
   top-10 t0 (Q, over-limit): 622.0(Q46,ol0) 625.0(Q46,ol0) 625.5(Q46,ol0) 619.0(Q45,ol0) 619.5(Q45,ol0) 620.0(Q45,ol0) 620.5(Q45,ol0) 621.5(Q45,ol0) 622.5(Q45,ol0) 623.0(Q45,ol0)
   #t0 with Q>=15: 1475 of 1501 ; Q>=0.9*max: 67
=== s5 chosen t0 401.0 R 701.0  Q 29 | affected [R,R+10) 1  (R+120,R+300) 30  whole post-R 75  during outage 54  over-limit 0 (max prompt bound 27147)
   committed d188 t0 880.5: Q(d188) 25 ; Q(d300 at committed t0) IMPOSSIBLE (t0+300+150 > 1200)
   VALIDATION on generated d300 trace: victims 14, interrupted sessions gen 22 vs search 22 equal=True, Q gen 29, digest 5e0827ea90e3f5be
   backlog per victim frames min/med/max 149 / 150 / 150 ; tokens 13410 / 13500 / 13500 ; upload_s at 13.6 Mbps 2.18..2.19
   session-local time at t0 (device, local s, session duration s): [('robo000', 169.1, 386.1), ('robo001', 59.3, 304.4), ('robo002', 406.1, 600.0), ('robo003', 203.9, 600.0), ('robo004', 549.9, 600.0), ('robo005', 106.1, 600.0), ('robo006', 61.5, 600.0), ('robo007', 49.2, 600.5), ('robo008', 456.8, 600.0), ('robo009', 574.9, 599.4), ('robo010', 95.2, 600.0), ('robo011', 113.3, 317.5), ('robo012', 37.9, 600.1), ('robo013', 432.4, 600.0)]
   victims with no active session at t0: []
   Q window [R+10,R+120] n 29: history tokens min/med/max 6421 / 20641 / 26761 ; uncached since t0 6421 / 16470 / 18900 (no warm prefix: 8 asks, session started in-window) ; lazy-from-warm s min/med/max 1.43/4.33/4.97 MISS>3s 23 ; cold s 1.43/5.43/7.04 MISS>3s 23
   Q kinds: robot MCQ 29 ({'reask': 25, 'original': 4}) ; categories {'time_duration': 4, 'sequential_action': 14, 'visual_detail_recall': 6, 'location_trace': 4, 'temporal_ordering_recognition': 1} ; per device {'robo003': 4, 'robo007': 6, 'robo010': 6, 'robo009': 2, 'robo013': 4, 'robo005': 5, 'robo001': 2}
   all post-R affected n 75: history tokens min/med/max 6421 / 21091 / 26941 ; uncached since t0 6421 / 17401 / 26941 (no warm prefix: 41 asks, session started in-window) ; lazy-from-warm s min/med/max 1.43/4.55/7.09 MISS>3s 65 ; cold s 1.43/5.55/7.09 MISS>3s 65
   Q neighbourhood t0-10..t0+10 (0.5 s): 391.0:24 391.5:23 392.0:23 392.5:23 393.0:24 393.5:24 394.0:24 394.5:24 395.0:25 395.5:25 396.0:25 396.5:25 397.0:25 397.5:25 398.0:25 398.5:25 399.0:26 399.5:27 400.0:27 400.5:28 401.0:29 401.5:29 402.0:28 402.5:28 403.0:28 403.5:28 404.0:28 404.5:28 405.0:28 405.5:28 406.0:28 406.5:27 407.0:27 407.5:27 408.0:27 408.5:27 409.0:27 409.5:27 410.0:27 410.5:27 411.0:27
   Q coarse every 25 s: 0:15 25:12 50:13 75:16 100:23 125:24 150:26 175:22 200:20 225:16 250:16 275:18 300:19 325:20 350:23 375:23 400:27 425:25 450:25 475:27 500:24 525:23 550:23 575:19 600:20 625:16 650:13 675:11 700:13 725:17 750:22
   top-10 t0 (Q, over-limit): 401.0(Q29,ol0) 401.5(Q29,ol0) 400.5(Q28,ol0) 402.0(Q28,ol0) 402.5(Q28,ol0) 403.0(Q28,ol0) 403.5(Q28,ol0) 404.0(Q28,ol0) 404.5(Q28,ol0) 405.0(Q28,ol0)
   #t0 with Q>=15: 1240 of 1501 ; Q>=0.9*max: 69
=== s6 chosen t0 736.0 R 1036.0  Q 37 | affected [R,R+10) 1  (R+120,R+300) 8  whole post-R 46  during outage 69  over-limit 0 (max prompt bound 27019)
   committed d188 t0 261.5: Q(d188) 22 ; Q(d300 at committed t0) 25
   VALIDATION on generated d300 trace: victims 14, interrupted sessions gen 24 vs search 24 equal=True, Q gen 37, digest 2dee9af97a6ceba1
   backlog per victim frames min/med/max 149 / 150 / 150 ; tokens 13410 / 13500 / 13500 ; upload_s at 13.6 Mbps 2.18..2.19
   session-local time at t0 (device, local s, session duration s): [('robo000', 307.5, 402.6), ('robo001', 194.0, 600.0), ('robo002', 447.3, 600.0), ('robo003', 572.8, 600.0), ('robo004', 385.4, 600.0), ('robo005', 287.2, 600.0), ('robo006', 28.7, 300.0), ('robo007', 386.0, 600.0), ('robo008', 431.2, 600.0), ('robo009', 350.8, 588.6), ('robo010', 32.8, 600.2), ('robo011', 431.9, 600.0), ('robo012', 183.6, 600.0), ('robo013', 517.7, 600.5)]
   victims with no active session at t0: []
   Q window [R+10,R+120] n 37: history tokens min/med/max 5791 / 13351 / 26851 ; uncached since t0 5791 / 13351 / 18630 (no warm prefix: 26 asks, session started in-window) ; lazy-from-warm s min/med/max 1.29/2.97/4.90 MISS>3s 18 ; cold s 1.29/2.97/7.07 MISS>3s 18
   Q kinds: robot MCQ 37 ({'reask': 28, 'original': 9}) ; categories {'sequential_action': 15, 'visual_detail_recall': 15, 'temporal_ordering_recognition': 1, 'location_trace': 6} ; per device {'robo012': 8, 'robo002': 4, 'robo011': 4, 'robo000': 4, 'robo004': 6, 'robo001': 3, 'robo003': 3, 'robo013': 3, 'robo009': 2}
   all post-R affected n 46: history tokens min/med/max 5791 / 13711 / 26851 ; uncached since t0 5791 / 13650 / 18661 (no warm prefix: 34 asks, session started in-window) ; lazy-from-warm s min/med/max 1.29/3.05/4.90 MISS>3s 24 ; cold s 1.29/3.05/7.07 MISS>3s 24
   Q neighbourhood t0-10..t0+10 (0.5 s): 726.0:32 726.5:32 727.0:33 727.5:33 728.0:33 728.5:33 729.0:33 729.5:33 730.0:35 730.5:35 731.0:35 731.5:35 732.0:35 732.5:35 733.0:35 733.5:35 734.0:35 734.5:36 735.0:36 735.5:36 736.0:37 736.5:37 737.0:37 737.5:37 738.0:37 738.5:37 739.0:37 739.5:37 740.0:37 740.5:37 741.0:37 741.5:37 742.0:37 742.5:37 743.0:36 743.5:36 744.0:35 744.5:35 745.0:35 745.5:35 746.0:35
   Q coarse every 25 s: 0:16 25:12 50:13 75:15 100:15 125:21 150:22 175:24 200:23 225:18 250:22 275:27 300:30 325:31 350:30 375:26 400:23 425:25 450:25 475:26 500:33 525:30 550:34 575:30 600:22 625:20 650:18 675:22 700:27 725:32 750:36
   top-10 t0 (Q, over-limit): 736.0(Q37,ol0) 736.5(Q37,ol0) 737.0(Q37,ol0) 737.5(Q37,ol0) 738.0(Q37,ol0) 738.5(Q37,ol0) 739.0(Q37,ol0) 739.5(Q37,ol0) 740.0(Q37,ol0) 740.5(Q37,ol0)
   #t0 with Q>=15: 1390 of 1501 ; Q>=0.9*max: 102

s4: if t0 in (750, 780] were allowed (only R+120 <= 1200): max Q 20 at t0 750.5 (post-R span 150 s)
   backlog-only rebuild (prefix warm to t0, post-R frames appended live): backlog tok 6120..13500 ; s min/med/max 1.36/3.55/3.55 ; MISS>3s 28 of 46 ; rate rows used {11000: 4500.0, 28000: 3800.0}
s5: if t0 in (750, 780] were allowed (only R+120 <= 1200): max Q 26 at t0 771.0 (post-R span 129 s)
   backlog-only rebuild (prefix warm to t0, post-R frames appended live): backlog tok 2430..13500 ; s min/med/max 0.54/3.55/3.55 ; MISS>3s 19 of 29 ; rate rows used {11000: 4500.0, 28000: 3800.0}
s6: if t0 in (750, 780] were allowed (only R+120 <= 1200): max Q 37 at t0 751.5 (post-R span 148 s)
   backlog-only rebuild (prefix warm to t0, post-R frames appended live): backlog tok 2790..13500 ; s min/med/max 0.62/2.04/3.55 ; MISS>3s 11 of 37 ; rate rows used {11000: 4500.0, 28000: 3800.0}

== DRIVER ==
Staged study_frozen_grid_driver_v49.sh = v48 + 5 comment lines after line 1; every non-comment line identical (diff of non-comment
lines empty); bash -n OK. Enumeration (enum.sh): 6 arms (covex-v6-fair-final, -cand-tl, -cand-tl-sync, streamscout, r3-streaming,
mooncake) x n {16, 20, 32} x seeds 1-7 x 17 tags (no-outage, _qp, d188 t4075/t8805/t2615 with and without _qp, d300 t6220/t4010/t7360
_link_qp, d300 _link without _qp, _rerun, _qpx, t622 typo, d300.5, _lnk typo, _kv0.5r_h0.5): v48 1,428 admitted lines, v49 1,428,
byte-identical including the parsed launch flags. The d300 COVEX tags are ALREADY admitted and parsed by v48 (filter restricts only
r3-streaming/streamscout; integer D parses; t0 from tenths). Wrong-suffix variants pass the filter under BOTH versions and are refused
later by cell()'s guards (_qpx: QP mismatch; d300.5: _out mismatch) except the t622 typo (runs at t0 62.2) and _lnk (runs without link
events): list-writing hazards, unchanged from v48.
Trace dirs: created by run_live2_real.py::_trace on first use from the flags (no pre-build), names
seed<S>_n20_1200s_A_r3-11-2_lh_req_ss2_L3_epg_perframe_rq30_outk14d300pevidencet<t0 %g>_lnk : t622 (s4), t401 (s5), t736 (s6).
Watchdog: h100_overnight_watchdog.sh line 24 DRIVER=...v48.sh must move to v49 only if v49 is deployed; since v49 is comment-only,
deploying it is optional.
