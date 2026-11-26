# StudyORACLE results, PROVISIONAL (robot and single-shot scope)

**PROVISIONAL: recomputed on the current policy arm `covex-v6-fair-final` (row `fair-final-rung3`).** 1x, seeds 4-7 pooled. Dashcam excluded (oracle share dropped, 82f5d019). kv0.5r and h0.5 excluded (kv0.5r retired; h0.5 not in this block).

| arm | role | FAIR share (95% CI) | HINDSIGHT share (95% CI) | units |
|---|---|---|---|---|
| always-cloud-fcfs | paper baseline | 0.062 (0.045, 0.084) | 0.004 (-0.046, 0.047) | 1900 |
| attentionstore-prefetch | paper baseline | 0.052 (0.035, 0.071) | -0.009 (-0.052, 0.026) | 1898 |
| b7-edf-feasibility | paper baseline | 0.189 (0.159, 0.226) | 0.078 (0.005, 0.141) | 1914 |
| base | other arm (ablation) | 0.550 (0.492, 0.626) | 0.312 (0.151, 0.445) | 1914 |
| confidence-cascade | paper baseline | 0.290 (0.235, 0.356) | 0.159 (0.013, 0.289) | 1914 |
| eco-llm | paper baseline | 0.216 (0.172, 0.272) | 0.119 (0.024, 0.211) | 1431 |
| edf | paper baseline | 0.100 (0.080, 0.124) | 0.025 (-0.031, 0.073) | 1902 |
| fair-c5attr | other arm (ablation) | 0.918 (0.876, 0.948) | 0.460 (0.255, 0.605) | 1914 |
| fair-c5attr-gain0 | other arm (ablation) | 0.910 (0.868, 0.943) | 0.449 (0.241, 0.597) | 1914 |
| fair-c5attr-rr | other arm (ablation) | 0.943 (0.900, 0.973) | 0.478 (0.265, 0.626) | 1914 |
| fair-final-rung3 | policy | 0.944 (0.901, 0.974) | 0.475 (0.265, 0.625) | 1914 |
| kvflow-prefetch | paper baseline | 0.064 (0.045, 0.088) | 0.007 (-0.047, 0.052) | 1897 |
| llf | paper baseline | 0.254 (0.216, 0.303) | 0.096 (0.000, 0.180) | 1914 |
| lmcache | paper baseline | 0.049 (0.032, 0.070) | -0.013 (-0.059, 0.021) | 1896 |
| mooncake | paper baseline | 0.191 (0.161, 0.230) | 0.087 (0.013, 0.151) | 1914 |
| querystream-proactive | paper baseline | 0.055 (0.038, 0.076) | -0.009 (-0.053, 0.029) | 1898 |
| rules | other arm (ablation) | 0.471 (0.419, 0.531) | 0.221 (0.085, 0.334) | 1914 |
| simplestream | paper baseline | 0.326 (0.244, 0.443) | 0.147 (-0.109, 0.347) | 1914 |
| state-shares | other arm (ablation) | 0.687 (0.627, 0.753) | 0.386 (0.222, 0.509) | 1914 |
| state-shares-r1 | other arm (ablation) | 0.864 (0.805, 0.916) | 0.429 (0.217, 0.585) | 1914 |
| state-shares-r2 | other arm (ablation) | 0.841 (0.780, 0.897) | 0.400 (0.192, 0.553) | 1914 |
| state-uo | other arm (ablation) | 0.916 (0.873, 0.949) | 0.460 (0.254, 0.608) | 1914 |
| state-uo-c5attr | other arm (ablation) | 0.904 (0.861, 0.937) | 0.440 (0.234, 0.588) | 1914 |
| streamscout | paper baseline | 0.329 (0.246, 0.444) | 0.159 (-0.102, 0.357) | 1914 |
| warm-all-lru | paper baseline | 0.043 (0.027, 0.062) | -0.002 (-0.042, 0.033) | 1902 |

Paper baseline set is D213; ladder rungs and ablations are labelled 'other arm (ablation)'.
Not in this block: `device-only` (offline by design (D217 (3)); scored by the Orin, not in this block); `cascade-routing` (reported, port-rule fail (D217 (2)); not counted as a baseline).
confidence-cascade uses its post-D205 `_rerun` cells (cloud-served robot share 0.11 to 0.22 per seed, against 0 to 0.02 pre-fix): s4 confidence-cascade_n16_s4_1200s_h27_3t_L3_epg_rq30_rerun, s5 confidence-cascade_n16_s5_1200s_h27_3t_L3_epg_rq30_rerun, s6 confidence-cascade_n16_s6_1200s_h27_3t_L3_epg_rq30_rerun, s7 confidence-cascade_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun.

Policy arm `fair-final-rung3` FAIR 0.944, best paper baseline by FAIR: `streamscout` 0.329.

Limits: s6 recall device accuracy rests on 20 to 25 distinct questions per seed (flagged in every per-seed row). Capacity T does not bind in value (oracle_lp_d270.json). The FAIR table is pooled over the 1x and kv0.5r cells (D268).
