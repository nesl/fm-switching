=== F0: instants in [R,R+120)=797 ; victims=14 ; catch-up-like pieces (kind piece, victim, t>=R)=253
lost=148 gained=22 net=-126
  declined_infeasible_W                            121
    of which cu piece in flight at decline         73
  shed_c5_held_never_offered                       16
  neither_overlaps_other_robot                     3
  late_behind_S2_overlap                           8
    of which strict queued-ahead of S2 piece       3
  bin(after R) lost lostS2 pieces_inflight pieces_submitted
     0- 10   42    0   40   40
    10- 20   28    0    7    7
    20- 30    4    0    4    3
    30- 40   39    0    5    4
    40- 50    6    0    5    5
    50- 60    0    0    3    3
    60- 70    0    0    1    1
    70- 80    0    0    6    5
    80- 90   18    5    7    7
    90-100   11    3    8    5
   100-110    0    0    4    4
   110-120    0    0    4    4
  lost-late latency s: min 1.01 med 1.12 max 1.21 (n=11)
  declined: W median 6792, cu in flight tok median 995, other robot tok median 15
=== eager: instants in [R,R+120)=797 ; victims=14 ; catch-up-like pieces (kind piece, victim, t>=R)=479
lost=450 gained=26 net=-424
  declined_infeasible_W                            338
    of which cu piece in flight at decline         306
  shed_c5_held_never_offered                       57
  neither_overlaps_other_robot                     3
  late_behind_S2_overlap                           52
    of which strict queued-ahead of S2 piece       36
  bin(after R) lost lostS2 pieces_inflight pieces_submitted
     0- 10   42    0   48   48
    10- 20   31    0   14   14
    20- 30   51    0   45   45
    30- 40   49    4   57   45
    40- 50   63   13   38   34
    50- 60   40    3   32   27
    60- 70   20    2   35   29
    70- 80   15   10   26   23
    80- 90   13    1   22   18
    90-100   32    5   20   17
   100-110   53    4   19   17
   110-120   41   10   16   14
  lost-late latency s: min 1.01 med 1.33 max 8.40 (n=55)
  declined: W median 10272, cu in flight tok median 9125, other robot tok median 78
=== rung3: instants in [R,R+120)=797 ; victims=14 ; catch-up-like pieces (kind piece, victim, t>=R)=198
lost=109 gained=84 net=-25
  declined_infeasible_W                            91
    of which cu piece in flight at decline         61
  shed_c5_held_never_offered                       8
  late_behind_S2_overlap                           9
  neither_no_robot_overlap                         1
    of which strict queued-ahead of S2 piece       8
  bin(after R) lost lostS2 pieces_inflight pieces_submitted
     0- 10   40    0   43   43
    10- 20   11    1    4    3
    20- 30    0    0    2    1
    30- 40   31    0    2    2
    40- 50    4    0    6    6
    50- 60    0    0    1    1
    60- 70    0    0    1    1
    70- 80    0    0    3    3
    80- 90    7    5    4    4
    90-100   16    3    7    4
   100-110    0    0    1    1
   110-120    0    0    2    1
  lost-late latency s: min 1.01 med 1.22 max 1.75 (n=10)
  declined: W median 6144, cu in flight tok median 1007, other robot tok median 252

=== W composition / counterfactual (w.py)
F0 est_first_token fit a=0.1474 b=1.537e-04 maxresid=0.1256 n=2684
 declined lost n=121; counterfactual feasible if S2 tokens removed from W: 39 (32%); S2 share of W: median 0.20, p25 0.00 p75 0.94; sum tok {'s2': 1137876, 'robot_other': 211139, 'dash': 80794}; reg W sum 1489553
eager est_first_token fit a=0.1507 b=1.537e-04 maxresid=0.1225 n=3007
 declined lost n=338; counterfactual feasible if S2 tokens removed from W: 140 (41%); S2 share of W: median 0.71, p25 0.30 p75 0.95; sum tok {'s2': 3095973, 'robot_other': 282326, 'dash': 212334}; reg W sum 3966526
rung3 est_first_token fit a=0.1356 b=1.547e-04 maxresid=0.1302 n=2548
 declined lost n=91; counterfactual feasible if S2 tokens removed from W: 31 (34%); S2 share of W: median 0.32, p25 0.00 p75 0.84; sum tok {'s2': 836159, 'robot_other': 262725, 'dash': 86106}; reg W sum 1392020
