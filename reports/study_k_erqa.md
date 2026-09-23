# Study K — Reasoning Gate on ERQA

## 1. Arm Accuracies

| Arm | Seeds | Mean acc | Per-seed |
|---|---|---|---|
| INSTRUCT | 1 | **42.0%** | None=42.0% |
| INSTRUCT_PERMUTED | 1 | **38.8%** | None=38.8% |
| THINKING | 3 | **45.1%** | 123=45.8%, 42=44.5%, 456=45.0% |
| THINKING-QUICK | 3 | **45.8%** | 123=46.0%, 42=45.0%, 456=46.2% |
| THINKING_PERMUTED | 3 | **41.3%** | 123=41.5%, 42=41.0%, 456=41.5% |

## 2. Replication Check (vs arXiv 2511.21631 Table 4: INSTRUCT=41.3, THINKING=47.3)

| Arm | Ours (mean) | Published | Diff | Pass |
|---|---|---|---|---|
| INSTRUCT | 42.0% | 41.3% | +0.7pp | ✓ |
| THINKING | 45.1% | 47.3% | -2.2pp | ✓ |

Replication check PASS.

## 3. Gate Test — THINKING vs INSTRUCT (McNemar, majority vote)

Paired McNemar, n=400: diff=+2.50pp, 95%CI=[-4.2,+9.2], b=59,c=49, p=0.3865 (chisq_continuity), p≥0.05

**PRE-REGISTERED VERDICT: FAILS — THINKING ≤ INSTRUCT under McNemar's test**

## 4. Breakdown by Group (BH corrected)

| Group | n | diff | 95%CI | p | p_BH | sig |
|---|---|---|---|---|---|---|
| single_image | 287 | +1.7pp | [-6.3,+10.1] | 0.6442 | 1.0000 | — |
| multi_image | 113 | +4.4pp | [-8.0,+16.8] | 0.4862 | 1.0000 | — |
| Action Reasoning | 72 | +1.4pp | [-13.9,+18.1] | 1.0000 | 1.0000 | — |
| Multi-view Reasoning | 37 | +2.7pp | [-18.9,+24.3] | 1.0000 | 1.0000 | — |
| Other | 14 | +7.1pp | [-28.6,+42.9] | 1.0000 | 1.0000 | — |
| Pointing | 34 | +2.9pp | [-20.6,+26.5] | 1.0000 | 1.0000 | — |
| Spatial Reasoning | 84 | +11.9pp | [-3.6,+26.2] | 0.0213 | 0.2130 | — |
| State Estimation | 55 | +9.1pp | [-9.1,+27.3] | 0.2668 | 0.8893 | — |
| Task Reasoning | 38 | -2.6pp | [-26.3,+21.1] | 1.0000 | 1.0000 | — |
| Trajectory Reasoning | 66 | -12.1pp | [-28.8,+4.5] | 0.1338 | 0.6690 | — |

## 5. Reasoning Spend (all seeds pooled)

| Arm | Group | n | median tok | IQR | min | max | IQR/median |
|---|---|---|---|---|---|---|---|
| THINKING | overall | 1200 | 523.0 | 1068.8 | 0 | 14464 | 2.043 |
| THINKING | single | 861 | 402.0 | 898.0 | 0 | 14464 | 2.234 |
| THINKING | multi | 339 | 875.0 | 1240.5 | 0 | 8122 | 1.418 |
| THINKING | Action Reasoning | 216 | 489.5 | 777.0 | 0 | 7244 | 1.587 |
| THINKING | Multi-view Reasoning | 111 | 685.0 | 794.5 | 0 | 4983 | 1.16 |
| THINKING | Other | 42 | 541.0 | 1665.0 | 0 | 4277 | 3.078 |
| THINKING | Pointing | 102 | 335.5 | 626.0 | 0 | 11880 | 1.866 |
| THINKING | Spatial Reasoning | 252 | 768.0 | 1506.2 | 0 | 14464 | 1.961 |
| THINKING | State Estimation | 165 | 268.0 | 613.0 | 46 | 5954 | 2.287 |
| THINKING | Task Reasoning | 114 | 692.0 | 1510.8 | 0 | 6236 | 2.183 |
| THINKING | Trajectory Reasoning | 198 | 623.0 | 969.5 | 0 | 7392 | 1.556 |
| THINKING-QUICK | overall | 1200 | 407.5 | 801.8 | 0 | 10441 | 1.967 |
| THINKING-QUICK | single | 861 | 317.0 | 630.0 | 0 | 10441 | 1.987 |
| THINKING-QUICK | multi | 339 | 743.0 | 1072.5 | 0 | 6315 | 1.443 |
| THINKING-QUICK | Action Reasoning | 216 | 331.0 | 487.2 | 0 | 5797 | 1.472 |
| THINKING-QUICK | Multi-view Reasoning | 111 | 485.0 | 784.0 | 0 | 6315 | 1.616 |
| THINKING-QUICK | Other | 42 | 509.5 | 1855.2 | 0 | 4859 | 3.641 |
| THINKING-QUICK | Pointing | 102 | 317.0 | 676.5 | 0 | 10441 | 2.134 |
| THINKING-QUICK | Spatial Reasoning | 252 | 603.5 | 1107.5 | 0 | 9234 | 1.835 |
| THINKING-QUICK | State Estimation | 165 | 208.0 | 405.0 | 0 | 7281 | 1.947 |
| THINKING-QUICK | Task Reasoning | 114 | 672.5 | 1335.5 | 59 | 4607 | 1.986 |
| THINKING-QUICK | Trajectory Reasoning | 198 | 447.5 | 625.2 | 61 | 5156 | 1.397 |

## 6. Non-Termination

| Arm | Budget hits (total) | Per 400q | Single | Multi |
|---|---|---|---|---|
| INSTRUCT | 0/400 | 0.0 | 0 | 0 |
| THINKING | 15/1200 | 5.0 | 9 | 6 |
| THINKING-QUICK | 8/1200 | 2.7 | 4 | 4 |

## 7. Think Tokens vs Correctness (point-biserial r, THINKING arm)

| Group | n | r | p |
|---|---|---|---|
| overall | 1200 | -0.1228 | 0.0000 |
| single | 861 | -0.1259 | 0.0002 |
| multi | 339 | -0.1032 | 0.0577 |
| Action Reasoning | 216 | -0.0604 | 0.3771 |
| Multi-view Reasoning | 111 | 0.0306 | 0.7498 |
| Other | 42 | 0.0201 | 0.8992 |
| Pointing | 102 | -0.1175 | 0.2395 |
| Spatial Reasoning | 252 | -0.2575 | 0.0000 |
| State Estimation | 165 | -0.0023 | 0.9764 |
| Task Reasoning | 114 | -0.3210 | 0.0005 |
| Trajectory Reasoning | 198 | -0.0812 | 0.2557 |

## 8. THINKING-QUICK vs THINKING

THINKING mean=45.1%  THINKING-QUICK mean=45.8%

Paired McNemar (QUICK vs THINKING, majority vote): diff=+0.25pp, 95%CI=[-6.5,+7.2], b=21,c=20, p=1.0000 (chisq_continuity), p≥0.05

| | THINKING | THINKING-QUICK |
|---|---|---|
| Median latency (ms) | 11110.6 | 8528.3 |
| Median think tokens | 523.0 | 407.5 |

## 9. Position Bias

**INSTRUCT:** original=42.0%, permuted=38.8%, diff=-3.2pp → **MATERIAL BIAS**
  Letter dist (original): {'D': 60, 'C': 105, 'A': 137, 'B': 98}
  Letter dist (permuted): {'A': 120, 'D': 69, 'B': 88, 'C': 121}

**THINKING:** original=44.5%, permuted=41.5%, diff=-3.0pp → **MATERIAL BIAS**
  Letter dist (original): {'D': 274, 'C': 310, 'A': 276, 'B': 333}
  Letter dist (permuted): {'B': 310, 'D': 291, 'C': 288, 'A': 298}

## 10. Plain-Language Summary

**Replication:** INSTRUCT=42.0% (+0.7pp vs 41.3), THINKING=45.1% (-2.2pp vs 47.3). Both within 5pp. ✓
**Gate:** diff=+2.50pp, p=0.3865. FAILS — THINKING ≤ INSTRUCT under McNemar's test
**THINKING-QUICK vs THINKING:** diff=+0.25pp, p=1.0000.
