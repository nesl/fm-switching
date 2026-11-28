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
