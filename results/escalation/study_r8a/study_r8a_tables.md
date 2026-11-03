# StudyR8a — generated tables

From `results/escalation/study_r8a/study_r8a_results.json`. Every value computed; none typed.

## Gate

**NOT SHOWN**

| workload | best query+prefix router, k <= 100 | rank | k | acc @ e=0.2 | delta vs query-only | 95% CI | >= 2 pp and CI excludes 0 |
|---|---|---|---|---|---|---|---|
| sember | `query+prefix_hand_k100` | by_gain | 100 | 35.86% | +0.95 pp | [-0.12, +2.22] | no |
| erqa | `query+prefix_hand_k50` | by_gain | 50 | 47.25% | +1.75 pp | [-0.25, +3.75] | no |


# SEMBER  (n = 845)

Device 33.37% · cloud 39.53% · gain counts {'-1': 102, '0': 589, '1': 154} · 5 folds

## Decision latency (Orin, standalone, uncontended)

| k | median s to the k-th reasoning token |
|---|---|
| 0 | 0.00 |
| 25 | 18.69 |
| 50 | 20.20 |
| 100 | 23.20 |
| 200 | 29.16 |
| 400 | 37.50 |
| full | 38.25 |

n = 120 Orin questions (`tokens_4bt_f16_F16.jsonl.gz`). k = 0 is 0 s: decidable before generation starts.

## Part 1 — held-out AUROC for `device_incorrect`

| router | k | latency s | AUROC | 95% CI | delta vs query-only | paired 95% CI |
|---|---|---|---|---|---|---|
| `prefix_tfidf_k200` | 200 | 29.2 | 0.6538 | [0.6144, 0.6941] | +0.0333 | [-0.0088, +0.0772] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.6534 | [0.6145, 0.6917] | +0.0330 | [-0.0073, +0.0726] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.6495 | [0.6106, 0.6887] | +0.0291 | [+0.0120, +0.0460] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.6489 | [0.6097, 0.6893] | +0.0284 | [+0.0133, +0.0440] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.6450 | [0.6052, 0.6862] | +0.0246 | [+0.0086, +0.0404] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.6449 | [0.6042, 0.6860] | +0.0244 | [-0.0139, +0.0655] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.6400 | [0.5985, 0.6821] | +0.0195 | [+0.0075, +0.0327] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.6365 | [0.5953, 0.6795] | +0.0160 | [-0.0260, +0.0614] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.6346 | [0.5962, 0.6728] | +0.0141 | [-0.0117, +0.0394] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.6341 | [0.5943, 0.6734] | +0.0136 | [-0.0074, +0.0346] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.6307 | [0.5889, 0.6721] | +0.0103 | [-0.0007, +0.0213] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.6293 | [0.5874, 0.6703] | +0.0089 | [-0.0085, +0.0251] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.6281 | [0.5886, 0.6683] | +0.0076 | [-0.0222, +0.0368] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.6279 | [0.5867, 0.6689] | +0.0074 | [-0.0023, +0.0174] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.6252 | [0.5856, 0.6662] | +0.0047 | [-0.0186, +0.0278] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.6243 | [0.5847, 0.6643] | +0.0039 | [-0.0218, +0.0297] |
| `query_only` | None | 0.0 | 0.6204 | [0.5790, 0.6623] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.6204 | [0.5790, 0.6623] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.6204 | [0.5790, 0.6623] | +0.0000 | [+0.0000, +0.0000] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.6195 | [0.5765, 0.6622] | -0.0009 | [-0.0431, +0.0437] |
| `prefix_hand_k400` | 400 | 37.5 | 0.6188 | [0.5829, 0.6597] | -0.0016 | [-0.0473, +0.0455] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.6157 | [0.5740, 0.6571] | -0.0047 | [-0.0113, +0.0018] |
| `prefix_hand_k100` | 100 | 23.2 | 0.6147 | [0.5738, 0.6540] | -0.0057 | [-0.0560, +0.0436] |
| `prefix_hand_kfull` | full | 38.2 | 0.6100 | [0.5711, 0.6488] | -0.0104 | [-0.0554, +0.0350] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.6050 | [0.5615, 0.6472] | -0.0155 | [-0.0602, +0.0324] |
| `length_only_kfull` | full | 38.2 | 0.6044 | [0.5669, 0.6402] | -0.0160 | [-0.0631, +0.0316] |
| `prefix_hand_k200` | 200 | 29.2 | 0.6022 | [0.5631, 0.6436] | -0.0183 | [-0.0689, +0.0350] |
| `prefix_hand_k50` | 50 | 20.2 | 0.5970 | [0.5568, 0.6360] | -0.0234 | [-0.0751, +0.0259] |
| `length_only_k400` | 400 | 37.5 | 0.5952 | [0.5547, 0.6337] | -0.0252 | [-0.0698, +0.0229] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.5941 | [0.5531, 0.6359] | -0.0264 | [-0.0383, -0.0136] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5696 | [0.5268, 0.6099] | -0.0508 | [-0.1068, +0.0025] |
| `length_only_k200` | 200 | 29.2 | 0.5692 | [0.5267, 0.6084] | -0.0512 | [-0.0992, -0.0023] |
| `length_only_k100` | 100 | 23.2 | 0.5433 | [0.5026, 0.5833] | -0.0771 | [-0.1269, -0.0245] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.5385 | [0.4950, 0.5829] | -0.0819 | [-0.1294, -0.0326] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.5322 | [0.4920, 0.5714] | -0.0883 | [-0.1347, -0.0376] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.5321 | [0.4920, 0.5714] | -0.0883 | [-0.1347, -0.0376] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.5228 | [0.4845, 0.5624] | -0.0977 | [-0.1458, -0.0454] |
| `prefix_emb_k400` | 400 | 37.5 | 0.5226 | [0.4828, 0.5645] | -0.0978 | [-0.1505, -0.0434] |
| `prefix_emb_kfull` | full | 38.2 | 0.5226 | [0.4828, 0.5646] | -0.0978 | [-0.1504, -0.0434] |
| `prefix_emb_k200` | 200 | 29.2 | 0.5165 | [0.4754, 0.5571] | -0.1040 | [-0.1583, -0.0472] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.5160 | [0.4752, 0.5568] | -0.1044 | [-0.1543, -0.0544] |
| `prefix_emb_k50` | 50 | 20.2 | 0.5157 | [0.4723, 0.5621] | -0.1048 | [-0.1564, -0.0500] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4997 | [0.4573, 0.5424] | -0.1207 | [-0.1756, -0.0669] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.4996 | [0.4571, 0.5415] | -0.1209 | [-0.1734, -0.0711] |
| `prefix_emb_k25` | 25 | 18.7 | 0.4841 | [0.4421, 0.5242] | -0.1364 | [-0.1933, -0.0821] |
| `length_only_k50` | 50 | 20.2 | 0.4818 | [0.4397, 0.5251] | -0.1387 | [-0.1919, -0.0821] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4663 | [0.4254, 0.5085] | -0.1541 | [-0.2076, -0.0979] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4663 | [0.4254, 0.5085] | -0.1541 | [-0.2076, -0.0979] |
| `length_only_k0` | 0 | 0.0 | 0.4663 | [0.4254, 0.5085] | -0.1541 | [-0.2076, -0.0979] |
| `length_only_k25` | 25 | 18.7 | 0.4663 | [0.4254, 0.5085] | -0.1541 | [-0.2076, -0.0979] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4471 | [0.4065, 0.4871] | -0.1733 | [-0.2284, -0.1165] |

## Part 1 — held-out AUROC for `evidence_outside_window`

| router | k | latency s | AUROC | 95% CI | delta vs query-only | paired 95% CI |
|---|---|---|---|---|---|---|
| `prefix_hand_k100` | 100 | 23.2 | 0.6247 | [0.5658, 0.6835] | +0.1506 | [+0.0770, +0.2244] |
| `prefix_hand_k50` | 50 | 20.2 | 0.6160 | [0.5537, 0.6753] | +0.1418 | [+0.0660, +0.2167] |
| `prefix_hand_k200` | 200 | 29.2 | 0.6004 | [0.5401, 0.6620] | +0.1263 | [+0.0468, +0.2098] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.5860 | [0.5282, 0.6394] | +0.1119 | [+0.0488, +0.1754] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.5830 | [0.5245, 0.6411] | +0.1088 | [+0.0603, +0.1625] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5800 | [0.5159, 0.6440] | +0.1059 | [+0.0200, +0.1943] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.5787 | [0.5236, 0.6309] | +0.1046 | [+0.0415, +0.1659] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.5699 | [0.5153, 0.6249] | +0.0957 | [+0.0298, +0.1637] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.5620 | [0.5047, 0.6168] | +0.0879 | [+0.0188, +0.1552] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.5587 | [0.4984, 0.6192] | +0.0846 | [+0.0074, +0.1573] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.5571 | [0.4941, 0.6200] | +0.0829 | [+0.0417, +0.1257] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.5554 | [0.4947, 0.6150] | +0.0813 | [+0.0345, +0.1309] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.5452 | [0.4884, 0.5993] | +0.0711 | [+0.0016, +0.1395] |
| `prefix_hand_k400` | 400 | 37.5 | 0.5338 | [0.4733, 0.5967] | +0.0597 | [-0.0147, +0.1424] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.5316 | [0.4696, 0.5895] | +0.0575 | [+0.0264, +0.0937] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.5273 | [0.4685, 0.5844] | +0.0532 | [+0.0273, +0.0797] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.5269 | [0.4673, 0.5842] | +0.0528 | [+0.0256, +0.0811] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.5145 | [0.4525, 0.5749] | +0.0404 | [+0.0015, +0.0807] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.5142 | [0.4546, 0.5717] | +0.0401 | [+0.0189, +0.0620] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.5048 | [0.4516, 0.5577] | +0.0307 | [-0.0427, +0.1033] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.5038 | [0.4452, 0.5620] | +0.0297 | [+0.0115, +0.0471] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.4976 | [0.4376, 0.5551] | +0.0235 | [+0.0089, +0.0378] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.4938 | [0.4264, 0.5565] | +0.0196 | [-0.0188, +0.0596] |
| `prefix_emb_k50` | 50 | 20.2 | 0.4917 | [0.4236, 0.5546] | +0.0175 | [-0.0717, +0.1053] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.4909 | [0.4255, 0.5527] | +0.0168 | [-0.0701, +0.1003] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.4898 | [0.4316, 0.5488] | +0.0157 | [-0.0587, +0.0955] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.4898 | [0.4316, 0.5489] | +0.0157 | [-0.0587, +0.0955] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.4888 | [0.4306, 0.5481] | +0.0147 | [-0.0171, +0.0511] |
| `prefix_emb_k200` | 200 | 29.2 | 0.4862 | [0.4299, 0.5391] | +0.0121 | [-0.0663, +0.0883] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.4775 | [0.4229, 0.5323] | +0.0034 | [-0.0629, +0.0730] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.4747 | [0.4161, 0.5315] | +0.0006 | [-0.0077, +0.0121] |
| `query_only` | None | 0.0 | 0.4741 | [0.4150, 0.5318] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.4741 | [0.4150, 0.5318] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.4741 | [0.4150, 0.5318] | +0.0000 | [+0.0000, +0.0000] |
| `prefix_emb_k400` | 400 | 37.5 | 0.4740 | [0.4143, 0.5336] | -0.0001 | [-0.0847, +0.0856] |
| `prefix_emb_kfull` | full | 38.2 | 0.4740 | [0.4143, 0.5335] | -0.0001 | [-0.0847, +0.0856] |
| `prefix_emb_k25` | 25 | 18.7 | 0.4698 | [0.4122, 0.5306] | -0.0043 | [-0.0852, +0.0772] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4673 | [0.4113, 0.5224] | -0.0068 | [-0.0836, +0.0724] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.4654 | [0.4095, 0.5230] | -0.0087 | [-0.0840, +0.0655] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.4638 | [0.4066, 0.5197] | -0.0104 | [-0.0237, +0.0028] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4589 | [0.3947, 0.5277] | -0.0152 | [-0.1102, +0.0785] |
| `length_only_k200` | 200 | 29.2 | 0.4443 | [0.3853, 0.5085] | -0.0298 | [-0.1136, +0.0579] |
| `length_only_k100` | 100 | 23.2 | 0.4418 | [0.3768, 0.5043] | -0.0323 | [-0.1092, +0.0457] |
| `prefix_hand_kfull` | full | 38.2 | 0.4396 | [0.3825, 0.5008] | -0.0345 | [-0.1113, +0.0475] |
| `length_only_k400` | 400 | 37.5 | 0.4382 | [0.3785, 0.5008] | -0.0359 | [-0.1125, +0.0399] |
| `length_only_k50` | 50 | 20.2 | 0.4379 | [0.3704, 0.5035] | -0.0363 | [-0.1197, +0.0494] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4306 | [0.3648, 0.4965] | -0.0435 | [-0.1269, +0.0431] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4306 | [0.3648, 0.4965] | -0.0435 | [-0.1269, +0.0431] |
| `length_only_k0` | 0 | 0.0 | 0.4306 | [0.3648, 0.4965] | -0.0435 | [-0.1269, +0.0431] |
| `length_only_k25` | 25 | 18.7 | 0.4306 | [0.3648, 0.4965] | -0.0435 | [-0.1269, +0.0431] |
| `length_only_kfull` | full | 38.2 | 0.4284 | [0.3657, 0.4976] | -0.0457 | [-0.1224, +0.0374] |

## Part 2 — escalation utility

| e | random | perfect oracle | always-local | always-cloud |
|---|---|---|---|---|
| 0.1 | 33.99 | 43.31 | 33.37 | 39.53 |
| 0.2 | 34.59 | 51.60 | 33.37 | 39.53 |
| 0.3 | 35.27 | 51.60 | 33.37 | 39.53 |
| 0.5 | 36.56 | 51.60 | 33.37 | 39.53 |
| 1.0 | 39.53 | 39.53 | 33.37 | 39.53 |

### At e = 0.2, every router, both rankings

| router | k | latency s | rank | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|---|
| `length_only_kfull` | full | 38.2 | by_failure | 36.21 | +2.72 | [+0.82, +4.85] |
| `prefix_hand_kfull` | full | 38.2 | by_failure | 36.09 | +2.60 | [+0.81, +4.68] |
| `prefix_hand_k400` | 400 | 37.5 | by_failure | 36.09 | +2.60 | [+0.80, +4.67] |
| `prefix_tfidf_kfull` | full | 38.2 | by_gain | 37.28 | +2.37 | [+0.35, +4.52] |
| `prefix_hand_k25` | 25 | 18.7 | by_failure | 35.50 | +2.01 | [-0.00, +4.14] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_gain | 36.80 | +1.89 | [+0.00, +3.50] |
| `length_only_k400` | 400 | 37.5 | by_failure | 35.38 | +1.89 | [+0.00, +4.07] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_gain | 36.69 | +1.77 | [+0.00, +3.32] |
| `prefix_hand_k50` | 50 | 20.2 | by_failure | 35.15 | +1.66 | [-0.23, +4.00] |
| `prefix_hand_k100` | 100 | 23.2 | by_failure | 35.15 | +1.66 | [-0.24, +3.82] |
| `prefix_hand_k200` | 200 | 29.2 | by_failure | 34.91 | +1.42 | [-0.48, +3.64] |
| `prefix_tfidf_kfull` | full | 38.2 | by_failure | 34.79 | +1.30 | [-0.24, +2.98] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_gain | 36.21 | +1.30 | [-0.60, +3.17] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_failure | 34.79 | +1.30 | [-0.24, +2.98] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_failure | 34.79 | +1.30 | [-0.34, +3.03] |
| `length_only_kfull` | full | 38.2 | by_gain | 36.21 | +1.30 | [-1.05, +3.23] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_failure | 34.67 | +1.18 | [-0.23, +2.80] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_failure | 34.67 | +1.18 | [-0.95, +3.63] |
| `prefix_hand_k400` | 400 | 37.5 | by_gain | 36.09 | +1.18 | [-1.05, +3.00] |
| `prefix_hand_k0` | 0 | 0.0 | by_failure | 34.67 | +1.18 | [-0.95, +3.63] |
| `length_only_k25` | 25 | 18.7 | by_failure | 34.67 | +1.18 | [-0.95, +3.63] |
| `length_only_k200` | 200 | 29.2 | by_failure | 34.67 | +1.18 | [-0.59, +3.72] |
| `length_only_k0` | 0 | 0.0 | by_failure | 34.67 | +1.18 | [-0.95, +3.63] |
| `prefix_emb_k200` | 200 | 29.2 | by_failure | 34.56 | +1.06 | [-0.96, +3.35] |
| `prefix_emb_k0` | 0 | 0.0 | by_failure | 34.56 | +1.06 | [-1.20, +3.21] |
| `length_only_k50` | 50 | 20.2 | by_failure | 34.56 | +1.06 | [-0.95, +3.67] |
| `length_only_k100` | 100 | 23.2 | by_failure | 34.56 | +1.06 | [-1.15, +3.37] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_gain | 35.86 | +0.95 | [-0.12, +2.22] |
| `query+prefix_emb_kfull` | full | 38.2 | by_failure | 34.44 | +0.95 | [-0.96, +3.11] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_failure | 34.44 | +0.95 | [-0.96, +3.11] |
| `prefix_hand_kfull` | full | 38.2 | by_gain | 35.86 | +0.95 | [-1.26, +2.94] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_gain | 35.74 | +0.83 | [-0.73, +2.06] |
| `prefix_emb_k50` | 50 | 20.2 | by_gain | 35.74 | +0.83 | [-1.57, +2.84] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_failure | 34.20 | +0.71 | [-0.46, +2.48] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_gain | 35.62 | +0.71 | [-1.42, +2.74] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_gain | 35.50 | +0.59 | [-1.09, +1.91] |
| `query+prefix_hand_kfull` | full | 38.2 | by_gain | 35.50 | +0.59 | [-0.48, +1.87] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_failure | 34.08 | +0.59 | [-0.48, +1.68] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_gain | 35.50 | +0.59 | [-1.78, +2.45] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_gain | 35.50 | +0.59 | [-0.36, +1.39] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_failure | 34.08 | +0.59 | [-0.87, +2.33] |
| `prefix_emb_k50` | 50 | 20.2 | by_failure | 34.08 | +0.59 | [-1.17, +2.23] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_failure | 33.96 | +0.47 | [-0.69, +2.01] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_gain | 35.38 | +0.47 | [-1.05, +1.66] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_failure | 33.85 | +0.35 | [-0.36, +1.04] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_failure | 33.85 | +0.35 | [-1.21, +2.58] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_failure | 33.85 | +0.35 | [-1.16, +2.23] |
| `prefix_emb_kfull` | full | 38.2 | by_failure | 33.85 | +0.35 | [-1.63, +2.80] |
| `prefix_emb_k400` | 400 | 37.5 | by_failure | 33.85 | +0.35 | [-1.63, +2.80] |
| `query+prefix_hand_kfull` | full | 38.2 | by_failure | 33.73 | +0.24 | [-0.80, +1.93] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_failure | 33.73 | +0.24 | [-0.96, +2.05] |
| `prefix_hand_k100` | 100 | 23.2 | by_gain | 35.15 | +0.24 | [-1.98, +2.01] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_gain | 35.03 | +0.12 | [-0.92, +1.22] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_gain | 35.03 | +0.12 | [-0.94, +1.19] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_failure | 33.61 | +0.12 | [-1.53, +2.02] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_failure | 33.61 | +0.12 | [-0.46, +0.95] |
| `query_only` | None | 0.0 | by_gain | 34.91 | +0.00 | [+0.00, +0.00] |
| `query_only` | None | 0.0 | by_failure | 33.49 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_failure | 33.49 | +0.00 | [-0.84, +1.16] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_failure | 33.49 | +0.00 | [-0.94, +1.25] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_failure | 33.49 | +0.00 | [-0.93, +1.23] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_gain | 34.91 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_failure | 33.49 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_gain | 34.91 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_failure | 33.49 | +0.00 | [+0.00, +0.00] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_gain | 34.91 | +0.00 | [-2.17, +1.95] |
| `prefix_hand_k200` | 200 | 29.2 | by_gain | 34.91 | +0.00 | [-2.33, +1.91] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_gain | 34.79 | -0.12 | [-1.33, +1.28] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_failure | 33.37 | -0.12 | [-1.17, +0.96] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_failure | 33.37 | -0.12 | [-0.96, +0.80] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_failure | 33.37 | -0.12 | [-1.90, +2.20] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_failure | 33.37 | -0.12 | [-1.56, +1.92] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_failure | 33.37 | -0.12 | [-0.93, +1.29] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_gain | 34.67 | -0.24 | [-1.78, +1.28] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_gain | 34.67 | -0.24 | [-1.39, +0.94] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_gain | 34.67 | -0.24 | [-2.51, +1.66] |
| `prefix_emb_k200` | 200 | 29.2 | by_gain | 34.67 | -0.24 | [-2.75, +1.76] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_gain | 34.67 | -0.24 | [-1.31, +0.61] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_gain | 34.56 | -0.35 | [-2.52, +1.52] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_gain | 34.56 | -0.35 | [-2.22, +1.51] |
| `prefix_hand_k25` | 25 | 18.7 | by_gain | 34.56 | -0.35 | [-2.40, +1.63] |
| `prefix_emb_k25` | 25 | 18.7 | by_failure | 33.14 | -0.35 | [-2.42, +1.89] |
| `prefix_emb_k100` | 100 | 23.2 | by_gain | 34.56 | -0.35 | [-2.46, +1.65] |
| `prefix_emb_k100` | 100 | 23.2 | by_failure | 33.14 | -0.35 | [-2.20, +2.16] |
| `query+prefix_emb_kfull` | full | 38.2 | by_gain | 34.44 | -0.47 | [-2.83, +1.31] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_gain | 34.44 | -0.47 | [-2.83, +1.31] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_gain | 34.44 | -0.47 | [-2.44, +1.44] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_gain | 34.44 | -0.47 | [-2.60, +1.38] |
| `length_only_k200` | 200 | 29.2 | by_gain | 34.44 | -0.47 | [-2.72, +1.40] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_failure | 32.90 | -0.59 | [-2.37, +1.51] |
| `prefix_emb_k25` | 25 | 18.7 | by_gain | 34.32 | -0.59 | [-2.82, +1.53] |
| `prefix_hand_k50` | 50 | 20.2 | by_gain | 34.20 | -0.71 | [-2.97, +1.30] |
| `prefix_emb_k0` | 0 | 0.0 | by_gain | 34.20 | -0.71 | [-2.84, +1.59] |
| `length_only_k100` | 100 | 23.2 | by_gain | 34.20 | -0.71 | [-3.04, +0.96] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_gain | 33.96 | -0.95 | [-3.08, +1.19] |
| `prefix_hand_k0` | 0 | 0.0 | by_gain | 33.96 | -0.95 | [-3.08, +1.19] |
| `length_only_k50` | 50 | 20.2 | by_gain | 33.96 | -0.95 | [-3.08, +1.19] |
| `length_only_k25` | 25 | 18.7 | by_gain | 33.96 | -0.95 | [-3.08, +1.19] |
| `length_only_k0` | 0 | 0.0 | by_gain | 33.96 | -0.95 | [-3.08, +1.19] |
| `length_only_k400` | 400 | 37.5 | by_gain | 33.61 | -1.30 | [-3.43, +0.48] |
| `prefix_emb_kfull` | full | 38.2 | by_gain | 33.37 | -1.54 | [-3.65, +0.68] |
| `prefix_emb_k400` | 400 | 37.5 | by_gain | 33.37 | -1.54 | [-3.65, +0.68] |

### Best router at each budget e (by_gain)

| e | best router | k | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|
| 0.1 | `prefix_tfidf_kfull` | full | 35.50 | +1.66 | [+0.34, +2.90] |
| 0.2 | `prefix_tfidf_kfull` | full | 37.28 | +2.37 | [+0.35, +4.52] |
| 0.3 | `query+prefix_tfidf_kfull` | full | 38.23 | +1.06 | [-0.83, +3.13] |
| 0.5 | `query+prefix_hand_k400` | 400 | 39.76 | +2.84 | [+0.71, +4.51] |
| 1.0 | `query_only` | None | 39.53 | +0.00 | [+0.00, +0.00] |

## Part 3 — rescue matrix

| category | n |
|---|---|
| device_fails | 579 |
| history_rescuable_device | 57 |
| history_rescuable_cloud | 68 |
| history_rescuable_either | 106 |
| capability_rescuable | 137 |
| both_needed | 38 |
| none | 367 |

| overlap | n |
|---|---|
| history_and_capability | 20 |
| history_and_both | 38 |
| capability_and_both | 0 |

AUROC for capability-rescuable vs the rest, among the 579 device failures (137 positive):

| router | AUROC |
|---|---|
| `length_only_k50` | 0.5464 |
| `prefix_hand_k0` | 0.5444 |
| `prefix_tfidf_k0` | 0.5444 |
| `length_only_k0` | 0.5444 |
| `length_only_k25` | 0.5444 |
| `length_only_k400` | 0.5366 |
| `prefix_emb_k0` | 0.5320 |
| `length_only_k100` | 0.5231 |
| `prefix_emb_k25` | 0.5214 |
| `query+prefix_emb_k25` | 0.5083 |
| `length_only_k200` | 0.5070 |
| `length_only_kfull` | 0.5062 |
| `prefix_hand_k400` | 0.5045 |
| `prefix_emb_k50` | 0.4913 |
| `prefix_hand_k25` | 0.4871 |
| `prefix_emb_k200` | 0.4811 |
| `prefix_emb_k400` | 0.4809 |
| `prefix_emb_kfull` | 0.4808 |
| `prefix_hand_kfull` | 0.4801 |
| `prefix_emb_k100` | 0.4793 |
| `prefix_hand_k100` | 0.4762 |
| `query+prefix_emb_k50` | 0.4756 |
| `query+prefix_emb_k200` | 0.4697 |
| `prefix_tfidf_k400` | 0.4683 |
| `prefix_tfidf_kfull` | 0.4683 |
| `query+prefix_emb_k400` | 0.4661 |
| `query+prefix_emb_kfull` | 0.4661 |
| `query+prefix_emb_k100` | 0.4653 |
| `prefix_hand_k200` | 0.4629 |
| `prefix_tfidf_k200` | 0.4536 |
| `query+prefix_hand_k400` | 0.4513 |
| `prefix_hand_k50` | 0.4419 |
| `prefix_tfidf_k25` | 0.4415 |
| `prefix_tfidf_k50` | 0.4278 |
| `query+prefix_hand_kfull` | 0.4259 |
| `prefix_tfidf_k100` | 0.4252 |
| `query+prefix_tfidf_kfull` | 0.4186 |
| `query+prefix_hand_k200` | 0.4184 |
| `query+prefix_tfidf_k400` | 0.4163 |
| `query+prefix_hand_k100` | 0.4154 |
| `query+prefix_tfidf_k200` | 0.4120 |
| `query+prefix_hand_k25` | 0.4059 |
| `query+prefix_tfidf_k25` | 0.4046 |
| `query_only` | 0.4037 |
| `query+prefix_hand_k0` | 0.4037 |
| `query+prefix_tfidf_k0` | 0.4037 |
| `query+prefix_tfidf_k50` | 0.4033 |
| `query+prefix_tfidf_k100` | 0.4000 |
| `query+prefix_emb_k0` | 0.3998 |
| `query+prefix_hand_k50` | 0.3921 |

## Mechanism Step 2 — feature audit (CONSTANT entries are stopping flags)

| k | features CONSTANT across questions |
|---|---|
| 0 | 31: hesitation_wait, hesitation_but, hesitation_total, n_letter_mentions, n_letter_changes, letter_appears, rep3_total, rep3_max, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, n_prefix_chars |
| 25 | 21: n_letter_changes, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, trace_closed_by_k, n_prefix_tokens |
| 50 | 18: repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine |
| 100 | 13: phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine |
| 200 | 10: phrase::cannot see, phrase::not shown, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::cannot determine |
| 400 | 8: phrase::cannot see, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::not enough information, phrase::cannot determine |
| full | 8: letter_appears, phrase::cannot see, phrase::before the clip, phrase::do not see, phrase::no visible, phrase::not enough information, phrase::cannot determine, trace_closed_by_k |

## Mechanism Step 3 — one traced unit

Question `00ac6f932f407123e3c689635c4e36561000dc2903d5d6ede74b7012de8ab225` (group `941275014627762_start_0.0_end_307.589`), device WRONG, cloud correct, gain 1.

| k | prefix tokens | non-zero features | predicted gain | rank | escalated at e=0.2 |
|---|---|---|---|---|---|
| 0 | 0 | trace_closed_by_k=1 | +0.09627 | 323/845 | no |
| 25 | 25 | rep3_max=1, repsent_max=1, n_prefix_tokens=25, n_prefix_chars=100 | +0.11330 | 316/845 | no |
| 50 | 50 | rep3_max=1, repsent_max=1, n_prefix_tokens=50, n_prefix_chars=178 | +0.06901 | 399/845 | no |
| 100 | 100 | hesitation_wait=2, hesitation_total=2, rep3_max=1, repsent_max=1, n_prefix_tokens=100, n_prefix_chars=385 | +0.11584 | 329/845 | no |
| 200 | 200 | hesitation_wait=4, hesitation_total=4, rep3_total=6, rep3_max=2, repsent_max=1, n_prefix_tokens=200 | +0.05282 | 435/845 | no |
| 400 | 400 | hesitation_wait=7, hesitation_but=2, hesitation_total=9, n_letter_mentions=1, letter_appears=1, rep3_total=35 | +0.07193 | 381/845 | no |


# ERQA  (n = 400)

Device 45.00% · cloud 46.75% · gain counts {'-1': 57, '0': 279, '1': 64} · 5 folds

## Decision latency (Orin, standalone, uncontended)

| k | median s to the k-th reasoning token |
|---|---|
| 0 | 0.00 |
| 25 | 18.69 |
| 50 | 20.20 |
| 100 | 23.20 |
| 200 | 29.16 |
| 400 | 37.50 |
| full | 38.25 |

n = 120 Orin questions (`tokens_4bt_f16_F16.jsonl.gz`). k = 0 is 0 s: decidable before generation starts.

## Part 1 — held-out AUROC for `device_incorrect`

| router | k | latency s | AUROC | 95% CI | delta vs query-only | paired 95% CI |
|---|---|---|---|---|---|---|
| `query+prefix_hand_k200` | 200 | 29.2 | 0.6208 | [0.5617, 0.6767] | +0.0501 | [-0.0027, +0.0979] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.6199 | [0.5604, 0.6733] | +0.0492 | [-0.0002, +0.0959] |
| `prefix_hand_k400` | 400 | 37.5 | 0.5996 | [0.5413, 0.6544] | +0.0289 | [-0.0527, +0.1075] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.5944 | [0.5362, 0.6509] | +0.0237 | [-0.0052, +0.0516] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.5918 | [0.5344, 0.6471] | +0.0212 | [-0.0050, +0.0465] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.5898 | [0.5323, 0.6471] | +0.0192 | [-0.0327, +0.0690] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.5880 | [0.5312, 0.6478] | +0.0173 | [-0.0342, +0.0648] |
| `prefix_hand_k200` | 200 | 29.2 | 0.5856 | [0.5267, 0.6401] | +0.0150 | [-0.0666, +0.0974] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.5846 | [0.5292, 0.6391] | +0.0139 | [-0.0282, +0.0549] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.5841 | [0.5267, 0.6423] | +0.0135 | [-0.0124, +0.0400] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.5760 | [0.5175, 0.6324] | +0.0054 | [-0.0318, +0.0444] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.5725 | [0.5140, 0.6293] | +0.0018 | [-0.0398, +0.0413] |
| `prefix_hand_kfull` | full | 38.2 | 0.5715 | [0.5146, 0.6275] | +0.0008 | [-0.0772, +0.0788] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.5711 | [0.5119, 0.6274] | +0.0004 | [-0.0145, +0.0155] |
| `query_only` | None | 0.0 | 0.5707 | [0.5123, 0.6286] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.5707 | [0.5123, 0.6286] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.5707 | [0.5123, 0.6286] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.5697 | [0.5127, 0.6255] | -0.0010 | [-0.0252, +0.0231] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.5674 | [0.5098, 0.6212] | -0.0033 | [-0.0324, +0.0257] |
| `answer_confidence` | full | 38.2 | 0.5666 | [0.5098, 0.6236] | -0.0041 | [-0.0872, +0.0825] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.5663 | [0.5082, 0.6207] | -0.0044 | [-0.0236, +0.0138] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.5639 | [0.5052, 0.6209] | -0.0068 | [-0.0277, +0.0143] |
| `prefix_hand_k100` | 100 | 23.2 | 0.5568 | [0.4990, 0.6176] | -0.0139 | [-0.0934, +0.0649] |
| `length_only_kfull` | full | 38.2 | 0.5519 | [0.4972, 0.6107] | -0.0188 | [-0.0949, +0.0645] |
| `length_only_k400` | 400 | 37.5 | 0.5472 | [0.4901, 0.6036] | -0.0235 | [-0.0987, +0.0551] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.5426 | [0.4819, 0.5997] | -0.0281 | [-0.0830, +0.0228] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.5417 | [0.4835, 0.6011] | -0.0289 | [-0.0697, +0.0146] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.5400 | [0.4817, 0.5990] | -0.0306 | [-0.0938, +0.0306] |
| `length_only_k200` | 200 | 29.2 | 0.5390 | [0.4808, 0.5941] | -0.0317 | [-0.1116, +0.0443] |
| `prefix_emb_k400` | 400 | 37.5 | 0.5312 | [0.4726, 0.5852] | -0.0395 | [-0.1085, +0.0307] |
| `prefix_emb_kfull` | full | 38.2 | 0.5312 | [0.4726, 0.5852] | -0.0395 | [-0.1085, +0.0307] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5295 | [0.4746, 0.5853] | -0.0412 | [-0.1117, +0.0335] |
| `prefix_hand_k50` | 50 | 20.2 | 0.5259 | [0.4680, 0.5845] | -0.0447 | [-0.1205, +0.0379] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.5258 | [0.4673, 0.5810] | -0.0449 | [-0.1128, +0.0210] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.5258 | [0.4673, 0.5810] | -0.0449 | [-0.1128, +0.0210] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.5193 | [0.4627, 0.5760] | -0.0513 | [-0.1055, +0.0023] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.5124 | [0.4540, 0.5712] | -0.0582 | [-0.1152, -0.0026] |
| `length_only_k100` | 100 | 23.2 | 0.5090 | [0.4518, 0.5644] | -0.0617 | [-0.1396, +0.0178] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.5066 | [0.4500, 0.5612] | -0.0640 | [-0.1314, +0.0075] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4942 | [0.4375, 0.5494] | -0.0764 | [-0.1453, -0.0062] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.4927 | [0.4350, 0.5475] | -0.0780 | [-0.1458, -0.0121] |
| `prefix_emb_k25` | 25 | 18.7 | 0.4920 | [0.4351, 0.5473] | -0.0787 | [-0.1500, -0.0027] |
| `prefix_emb_k200` | 200 | 29.2 | 0.4845 | [0.4251, 0.5415] | -0.0862 | [-0.1597, -0.0166] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.4778 | [0.4206, 0.5342] | -0.0929 | [-0.1586, -0.0254] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.4771 | [0.4170, 0.5331] | -0.0935 | [-0.1645, -0.0281] |
| `prefix_emb_k50` | 50 | 20.2 | 0.4733 | [0.4166, 0.5293] | -0.0974 | [-0.1668, -0.0261] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4657 | [0.4118, 0.5234] | -0.1050 | [-0.1830, -0.0269] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4657 | [0.4118, 0.5234] | -0.1050 | [-0.1830, -0.0269] |
| `length_only_k0` | 0 | 0.0 | 0.4657 | [0.4118, 0.5234] | -0.1050 | [-0.1830, -0.0269] |
| `length_only_k25` | 25 | 18.7 | 0.4657 | [0.4118, 0.5234] | -0.1050 | [-0.1830, -0.0269] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4649 | [0.4064, 0.5221] | -0.1057 | [-0.1872, -0.0203] |
| `length_only_k50` | 50 | 20.2 | 0.4567 | [0.4029, 0.5143] | -0.1140 | [-0.1926, -0.0365] |

## Part 2 — escalation utility

| e | random | perfect oracle | always-local | always-cloud |
|---|---|---|---|---|
| 0.1 | 45.22 | 55.00 | 45.00 | 46.75 |
| 0.2 | 45.42 | 61.00 | 45.00 | 46.75 |
| 0.3 | 45.52 | 61.00 | 45.00 | 46.75 |
| 0.5 | 45.78 | 61.00 | 45.00 | 46.75 |
| 1.0 | 46.75 | 46.75 | 45.00 | 46.75 |

### At e = 0.2, every router, both rankings

| router | k | latency s | rank | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|---|
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_failure | 47.50 | +2.00 | [+0.25, +4.00] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_gain | 47.25 | +1.75 | [-0.25, +3.75] |
| `prefix_hand_k200` | 200 | 29.2 | by_failure | 47.25 | +1.75 | [-1.50, +4.50] |
| `length_only_k400` | 400 | 37.5 | by_failure | 47.00 | +1.50 | [-1.25, +4.75] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_failure | 46.75 | +1.25 | [-0.75, +2.75] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_failure | 46.75 | +1.25 | [-1.50, +3.50] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_failure | 46.75 | +1.25 | [-1.25, +3.75] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_failure | 46.75 | +1.25 | [-1.00, +3.75] |
| `prefix_hand_k50` | 50 | 20.2 | by_gain | 46.75 | +1.25 | [-2.00, +4.25] |
| `prefix_hand_k50` | 50 | 20.2 | by_failure | 46.75 | +1.25 | [-1.50, +4.00] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_failure | 46.50 | +1.00 | [-0.75, +3.00] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_gain | 46.50 | +1.00 | [-0.50, +2.75] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_gain | 46.50 | +1.00 | [-1.00, +3.25] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_failure | 46.50 | +1.00 | [-0.75, +3.25] |
| `prefix_tfidf_kfull` | full | 38.2 | by_failure | 46.50 | +1.00 | [-1.25, +3.50] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_failure | 46.25 | +0.75 | [-0.75, +2.50] |
| `query+prefix_hand_kfull` | full | 38.2 | by_gain | 46.25 | +0.75 | [-0.50, +2.00] |
| `query+prefix_hand_kfull` | full | 38.2 | by_failure | 46.25 | +0.75 | [-1.25, +3.00] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_failure | 46.25 | +0.75 | [-1.00, +2.75] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_failure | 46.25 | +0.75 | [-1.50, +2.00] |
| `prefix_hand_k400` | 400 | 37.5 | by_failure | 46.25 | +0.75 | [-2.00, +4.00] |
| `prefix_hand_k100` | 100 | 23.2 | by_gain | 46.25 | +0.75 | [-2.00, +4.00] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_gain | 46.00 | +0.50 | [-1.00, +2.25] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_failure | 46.00 | +0.50 | [-0.75, +2.00] |
| `prefix_hand_k25` | 25 | 18.7 | by_failure | 46.00 | +0.50 | [-2.25, +3.00] |
| `prefix_emb_kfull` | full | 38.2 | by_failure | 46.00 | +0.50 | [-2.25, +3.25] |
| `prefix_emb_k400` | 400 | 37.5 | by_failure | 46.00 | +0.50 | [-2.25, +3.25] |
| `prefix_emb_k25` | 25 | 18.7 | by_failure | 46.00 | +0.50 | [-2.75, +3.50] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_gain | 46.00 | +0.50 | [-1.00, +1.75] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_gain | 45.75 | +0.25 | [+0.00, +1.75] |
| `query+prefix_emb_kfull` | full | 38.2 | by_failure | 45.75 | +0.25 | [-2.25, +2.75] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_failure | 45.75 | +0.25 | [-2.50, +3.00] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_failure | 45.75 | +0.25 | [-2.25, +2.75] |
| `prefix_tfidf_kfull` | full | 38.2 | by_gain | 45.75 | +0.25 | [-2.00, +2.75] |
| `prefix_emb_k50` | 50 | 20.2 | by_gain | 45.75 | +0.25 | [-2.75, +3.25] |
| `query_only` | None | 0.0 | by_gain | 45.50 | +0.00 | [+0.00, +0.00] |
| `query_only` | None | 0.0 | by_failure | 45.50 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_gain | 45.50 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_failure | 45.50 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_gain | 45.50 | +0.00 | [-1.75, +2.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_gain | 45.50 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_failure | 45.50 | +0.00 | [+0.00, +0.00] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_failure | 45.50 | +0.00 | [-3.00, +3.00] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_gain | 45.50 | +0.00 | [-0.76, +1.00] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_failure | 45.50 | +0.00 | [-1.25, +1.75] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_gain | 45.50 | +0.00 | [-2.50, +2.50] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_failure | 45.50 | +0.00 | [-2.00, +2.75] |
| `prefix_emb_k50` | 50 | 20.2 | by_failure | 45.50 | +0.00 | [-2.75, +3.00] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_gain | 45.25 | -0.25 | [-2.25, +2.25] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_failure | 45.25 | -0.25 | [-1.50, +1.75] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_gain | 45.25 | -0.25 | [-2.00, +1.75] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_gain | 45.25 | -0.25 | [-1.75, +1.26] |
| `prefix_hand_k100` | 100 | 23.2 | by_failure | 45.25 | -0.25 | [-3.50, +2.50] |
| `length_only_kfull` | full | 38.2 | by_failure | 45.25 | -0.25 | [-3.50, +3.25] |
| `length_only_k200` | 200 | 29.2 | by_failure | 45.25 | -0.25 | [-3.50, +2.75] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_failure | 45.25 | -0.25 | [-2.00, +2.01] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_gain | 45.00 | -0.50 | [-2.25, +1.50] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_failure | 45.00 | -0.50 | [-3.00, +2.00] |
| `prefix_hand_kfull` | full | 38.2 | by_failure | 45.00 | -0.50 | [-4.00, +2.25] |
| `prefix_emb_k200` | 200 | 29.2 | by_failure | 45.00 | -0.50 | [-3.00, +2.25] |
| `length_only_k100` | 100 | 23.2 | by_failure | 45.00 | -0.50 | [-3.75, +2.00] |
| `answer_confidence` | full | 38.2 | by_gain | 45.00 | -0.50 | [-3.50, +2.75] |
| `answer_confidence` | full | 38.2 | by_failure | 45.00 | -0.50 | [-3.50, +2.75] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_gain | 44.75 | -0.75 | [-3.50, +2.50] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_gain | 44.75 | -0.75 | [-3.50, +1.50] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_failure | 44.75 | -0.75 | [-3.50, +2.00] |
| `prefix_hand_kfull` | full | 38.2 | by_gain | 44.75 | -0.75 | [-3.75, +2.25] |
| `prefix_hand_k25` | 25 | 18.7 | by_gain | 44.75 | -0.75 | [-3.75, +2.25] |
| `prefix_hand_k200` | 200 | 29.2 | by_gain | 44.75 | -0.75 | [-3.75, +2.25] |
| `prefix_hand_k0` | 0 | 0.0 | by_failure | 44.75 | -0.75 | [-3.50, +2.00] |
| `prefix_emb_k0` | 0 | 0.0 | by_failure | 44.75 | -0.75 | [-3.50, +2.00] |
| `length_only_k25` | 25 | 18.7 | by_failure | 44.75 | -0.75 | [-3.50, +2.00] |
| `length_only_k0` | 0 | 0.0 | by_failure | 44.75 | -0.75 | [-3.50, +2.00] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_failure | 44.50 | -1.00 | [-3.26, +1.50] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_failure | 44.50 | -1.00 | [-3.75, +1.50] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_failure | 44.50 | -1.00 | [-3.75, +1.75] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_failure | 44.50 | -1.00 | [-3.50, +1.75] |
| `length_only_k50` | 50 | 20.2 | by_failure | 44.50 | -1.00 | [-3.75, +1.75] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_gain | 44.25 | -1.25 | [-2.75, +1.00] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_gain | 44.25 | -1.25 | [-4.00, +1.50] |
| `prefix_emb_k25` | 25 | 18.7 | by_gain | 44.25 | -1.25 | [-4.00, +1.25] |
| `prefix_emb_k200` | 200 | 29.2 | by_gain | 44.25 | -1.25 | [-3.75, +1.75] |
| `prefix_emb_k100` | 100 | 23.2 | by_failure | 44.25 | -1.25 | [-4.00, +1.50] |
| `length_only_kfull` | full | 38.2 | by_gain | 44.25 | -1.25 | [-4.25, +1.50] |
| `query+prefix_emb_kfull` | full | 38.2 | by_gain | 43.75 | -1.75 | [-4.25, +1.00] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_gain | 43.75 | -1.75 | [-4.25, +1.00] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_gain | 43.75 | -1.75 | [-4.25, +1.00] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_gain | 43.75 | -1.75 | [-4.25, +1.00] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_gain | 43.75 | -1.75 | [-4.50, +1.25] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_gain | 43.75 | -1.75 | [-4.00, +1.25] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_gain | 43.50 | -2.00 | [-4.75, +1.25] |
| `prefix_hand_k400` | 400 | 37.5 | by_gain | 43.50 | -2.00 | [-4.50, +1.00] |
| `length_only_k100` | 100 | 23.2 | by_gain | 43.50 | -2.00 | [-5.00, +0.75] |
| `prefix_emb_k100` | 100 | 23.2 | by_gain | 43.25 | -2.25 | [-5.00, +1.50] |
| `prefix_emb_k0` | 0 | 0.0 | by_gain | 43.00 | -2.50 | [-5.25, +1.01] |
| `length_only_k50` | 50 | 20.2 | by_gain | 43.00 | -2.50 | [-5.75, +0.50] |
| `length_only_k200` | 200 | 29.2 | by_gain | 43.00 | -2.50 | [-5.25, +0.50] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_gain | 42.75 | -2.75 | [-5.50, +0.50] |
| `prefix_hand_k0` | 0 | 0.0 | by_gain | 42.75 | -2.75 | [-5.50, +0.50] |
| `prefix_emb_kfull` | full | 38.2 | by_gain | 42.75 | -2.75 | [-5.25, +0.75] |
| `prefix_emb_k400` | 400 | 37.5 | by_gain | 42.75 | -2.75 | [-5.25, +0.75] |
| `length_only_k400` | 400 | 37.5 | by_gain | 42.75 | -2.75 | [-5.01, +0.25] |
| `length_only_k25` | 25 | 18.7 | by_gain | 42.75 | -2.75 | [-5.50, +0.50] |
| `length_only_k0` | 0 | 0.0 | by_gain | 42.75 | -2.75 | [-5.50, +0.50] |

### Best router at each budget e (by_gain)

| e | best router | k | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|
| 0.1 | `query+prefix_emb_k50` | 50 | 46.00 | +1.00 | [-1.51, +3.00] |
| 0.2 | `query+prefix_hand_k50` | 50 | 47.25 | +1.75 | [-0.25, +3.75] |
| 0.3 | `prefix_hand_k50` | 50 | 48.50 | +2.00 | [-1.50, +5.50] |
| 0.5 | `query+prefix_hand_k100` | 100 | 48.50 | +2.50 | [-0.50, +5.25] |
| 1.0 | `query_only` | None | 46.75 | +0.00 | [+0.00, +0.00] |

## Mechanism Step 2 — feature audit (CONSTANT entries are stopping flags)

| k | features CONSTANT across questions |
|---|---|
| 0 | 31: hesitation_wait, hesitation_but, hesitation_total, n_letter_mentions, n_letter_changes, letter_appears, rep3_total, rep3_max, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, n_prefix_chars |
| 25 | 22: repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens |
| 50 | 17: repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine |
| 100 | 14: phrase::can't see, phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine |
| 200 | 11: phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine |
| 400 | 11: phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine |
| full | 10: phrase::cannot see, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine, trace_closed_by_k |

## Mechanism Step 3 — one traced unit

Question `2` (group `2`), device WRONG, cloud correct, gain 1.

| k | prefix tokens | non-zero features | predicted gain | rank | escalated at e=0.2 |
|---|---|---|---|---|---|
| 0 | 0 | trace_closed_by_k=1 | +0.16020 | 88/400 | no |
| 25 | 25 | rep3_max=1, repsent_max=1, n_prefix_tokens=25, n_prefix_chars=104 | +0.14972 | 101/400 | no |
| 50 | 50 | hesitation_wait=2, hesitation_total=2, rep3_max=1, repsent_max=1, n_prefix_tokens=50, n_prefix_chars=196 | +0.22970 | 70/400 | yes |
| 100 | 100 | hesitation_wait=5, hesitation_total=5, rep3_total=3, rep3_max=2, repsent_max=1, n_prefix_tokens=100 | +0.39278 | 20/400 | yes |
| 200 | 200 | hesitation_wait=8, hesitation_total=8, n_letter_mentions=4, n_letter_changes=3, letter_appears=1, rep3_total=17 | +0.29020 | 51/400 | yes |
| 400 | 383 | hesitation_wait=12, hesitation_but=1, hesitation_total=13, n_letter_mentions=5, n_letter_changes=4, letter_appears=1 | +0.17892 | 85/400 | no |

