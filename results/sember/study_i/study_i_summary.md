# Study I — S-EMBER tier gap: analysis summary

**Trials:** 1600 valid  |  **Configs complete:** 4/4  |  **Generated:** `study_i_analyse.py`

---

## A — Overall accuracy

| config | n | acc | 95% CI |
|--------|---|-----|--------|
| qwen3vl4b_SPARSE | 459 | 26.6% | [22.7%, 30.8%] |
| qwen3vl4b_DENSE | 459 | 29.8% | [25.8%, 34.2%] |
| qwen3vl8b_SPARSE | 459 | 27.2% | [23.4%, 31.5%] |
| qwen3vl8b_DENSE | 223 | 33.6% | [27.8%, 40.1%] |

- **8B−4B gap (SPARSE):** +0.7pp
- **8B−4B gap (DENSE):** +3.8pp
- **DENSE−SPARSE (qwen3vl4b):** +3.3pp
- **DENSE−SPARSE (qwen3vl8b):** +6.4pp

## B — Accuracy by category (SPARSE)

| category | 4B | 8B | gap | p |
|----------|----|----|-----|---|
| time_duration | 23.7% (n=93) | 30.1% (n=93) | +6.5pp | 0.408 |
| visual_detail_recall | 41.5% (n=94) | 43.6% (n=94) | +2.1pp | 0.883 |
| sequential_action | 26.2% (n=61) | 19.7% (n=61) | -6.6pp | 0.519 |
| location_trace | 11.5% (n=52) | 19.2% (n=52) | +7.7pp | 0.416 |
| spatial_aware_reasoning | 16.1% (n=56) | 8.9% (n=56) | -7.1pp | 0.392 |
| object_comparison | 33.9% (n=56) | 30.4% (n=56) | -3.6pp | 0.840 |
| temporal_ordering_recognition | 23.4% (n=47) | 25.5% (n=47) | +2.1pp | 1.000 |

## C — Accuracy vs evidence distance

### nearest_dist_s (qt − aet)

| bin | 4B-SPARSE | 8B-SPARSE | 4B-DENSE | 8B-DENSE |
|-----|-----------|-----------|----------|----------|
| [0,10) | 24.0%(n=171) | 26.9%(n=171) | 22.8%(n=171) | 32.6%(n=86) |
| [10,30) | 31.6%(n=98) | 36.7%(n=98) | 33.7%(n=98) | 35.7%(n=42) |
| [30,60) | 26.2%(n=80) | 27.5%(n=80) | 28.7%(n=80) | 31.8%(n=44) |
| [60,120) | 22.6%(n=62) | 33.9%(n=62) | 25.8%(n=62) | 36.7%(n=30) |
| [120,∞) | 31.2%(n=48) | 25.0%(n=48) | 29.2%(n=48) | 33.3%(n=21) |

### farthest_dist_s (qt − ast, coverage-binding)

| bin | 4B-SPARSE | 8B-SPARSE | 4B-DENSE | 8B-DENSE |
|-----|-----------|-----------|----------|----------|
| [0,10) | 33.3%(n=9) | 22.2%(n=9) | 44.4%(n=9) | 20.0%(n=5) |
| [10,30) | 24.1%(n=58) | 34.5%(n=58) | 20.7%(n=58) | 25.9%(n=27) |
| [30,60) | 29.8%(n=134) | 30.6%(n=134) | 31.3%(n=134) | 35.5%(n=62) |
| [60,120) | 25.0%(n=124) | 32.3%(n=124) | 29.0%(n=124) | 36.7%(n=60) |
| [120,∞) | 25.4%(n=134) | 25.4%(n=134) | 23.1%(n=134) | 33.3%(n=69) |

## D — Latency

| config | lat_med | lat_p90 | lat_p99 | tok_med | tok/ms |
|--------|---------|---------|---------|---------|--------|
| qwen3vl4b_SPARSE | 810ms | 816ms | 822ms | 4747 | 5.86 |
| qwen3vl4b_DENSE | 2176ms | 2214ms | 2304ms | 12587 | 5.78 |
| qwen3vl8b_SPARSE | 1234ms | 1247ms | 1260ms | 4747 | 3.85 |
| qwen3vl8b_DENSE | 3135ms | 3225ms | 3333ms | 12579 | 4.01 |

## E — Coverage (ast-based, farthest_dist_s)

| window k | covered | fraction |
|----------|---------|----------|
| 3s | 0/459 | 0.0% |
| 10s | 10/459 | 2.2% |
| 30s | 75/459 | 16.3% |
| 60s | 204/459 | 44.4% |
| 120s | 327/459 | 71.2% |
| 300s | 428/459 | 93.2% |
| 600s | 455/459 | 99.1% |

## F — DENSE−SPARSE delta per category

| category | 4B Δ | 8B Δ |
|----------|------|------|
| time_duration | +8.6pp | +9.0pp |
| visual_detail_recall | +1.1pp | -6.7pp |
| sequential_action | +3.3pp | +19.0pp |
| location_trace | +9.6pp | +15.8pp |
| spatial_aware_reasoning | +0.0pp | +5.4pp |
| object_comparison | -3.6pp | -2.8pp |
| temporal_ordering_recognition | +2.1pp | +13.6pp |

## G — Placement verdict

Threshold: 5.0pp

- **SPARSE:** +0.65pp → NEGLIGIBLE
- **DENSE:** +3.78pp → NEGLIGIBLE
- Category gap range (SPARSE): [-7.14, 7.69]pp
- Spread: 14.83pp
