# StudyR8a — generated tables

From `results/escalation/study_r8a/study_r8a_results_v2.json`. Every value computed; none typed.

## Gate

**PARTIAL REASONING ADDS VALUE**

| workload | best query+prefix router, k <= 100 | rank | k | acc @ e=0.2 | delta vs query-only | 95% CI | >= 2 pp and CI excludes 0 |
|---|---|---|---|---|---|---|---|
| sember | `query+prefix_hand_k50` | by_gain | 50 | 36.21% | +2.01 pp | [+0.37, +3.11] | YES |
| erqa | `query+prefix_handunc_k25` | by_gain | 25 | 48.00% | +1.00 pp | [-1.25, +2.25] | no |


# SEMBER  (n = 845)

Device 32.31% · cloud 39.53% · gain counts {'-1': 104, '0': 576, '1': 165} · 5 folds

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
| `query+prefix_handunc_kfull` | full | 38.2 | 0.6923 | [0.6562, 0.7311] | +0.0277 | [+0.0023, +0.0556] |
| `query+prefix_unc_kfull` | full | 38.2 | 0.6921 | [0.6557, 0.7277] | +0.0275 | [+0.0025, +0.0519] |
| `query+prefix_unc_k200` | 200 | 29.2 | 0.6881 | [0.6496, 0.7239] | +0.0235 | [+0.0003, +0.0475] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.6856 | [0.6452, 0.7259] | +0.0209 | [+0.0067, +0.0366] |
| `query+prefix_unc_k400` | 400 | 37.5 | 0.6833 | [0.6444, 0.7197] | +0.0187 | [-0.0055, +0.0425] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.6817 | [0.6423, 0.7226] | +0.0171 | [-0.0046, +0.0393] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.6811 | [0.6380, 0.7216] | +0.0165 | [-0.0245, +0.0561] |
| `query+prefix_unc_k100` | 100 | 23.2 | 0.6784 | [0.6396, 0.7147] | +0.0138 | [-0.0095, +0.0362] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.6779 | [0.6364, 0.7188] | +0.0133 | [-0.0006, +0.0276] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.6772 | [0.6379, 0.7168] | +0.0126 | [+0.0001, +0.0253] |
| `query+prefix_handunc_k400` | 400 | 37.5 | 0.6755 | [0.6347, 0.7158] | +0.0109 | [-0.0183, +0.0395] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.6751 | [0.6343, 0.7179] | +0.0105 | [-0.0155, +0.0370] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.6747 | [0.6358, 0.7117] | +0.0101 | [-0.0113, +0.0328] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.6740 | [0.6347, 0.7141] | +0.0093 | [-0.0009, +0.0196] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.6740 | [0.6331, 0.7149] | +0.0094 | [-0.0048, +0.0237] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.6704 | [0.6274, 0.7125] | +0.0058 | [-0.0355, +0.0466] |
| `query+prefix_handunc_k100` | 100 | 23.2 | 0.6701 | [0.6281, 0.7094] | +0.0055 | [-0.0223, +0.0310] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.6698 | [0.6274, 0.7095] | +0.0052 | [-0.0190, +0.0274] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.6697 | [0.6304, 0.7099] | +0.0051 | [-0.0039, +0.0143] |
| `query+prefix_handunc_k200` | 200 | 29.2 | 0.6655 | [0.6238, 0.7062] | +0.0009 | [-0.0267, +0.0277] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.6650 | [0.6257, 0.7051] | +0.0004 | [-0.0064, +0.0077] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.6649 | [0.6230, 0.7072] | +0.0003 | [-0.0245, +0.0263] |
| `query_only` | None | 0.0 | 0.6646 | [0.6251, 0.7049] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.6646 | [0.6251, 0.7049] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.6646 | [0.6251, 0.7049] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_unc_k0` | 0 | 0.0 | 0.6646 | [0.6251, 0.7049] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_handunc_k0` | 0 | 0.0 | 0.6646 | [0.6251, 0.7049] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.6624 | [0.6235, 0.7014] | -0.0022 | [-0.0159, +0.0105] |
| `query+prefix_handunc_k50` | 50 | 20.2 | 0.6608 | [0.6238, 0.6978] | -0.0038 | [-0.0306, +0.0204] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.6588 | [0.6213, 0.6966] | -0.0058 | [-0.0279, +0.0145] |
| `query+prefix_unc_k50` | 50 | 20.2 | 0.6576 | [0.6216, 0.6940] | -0.0070 | [-0.0280, +0.0123] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.6538 | [0.6092, 0.6978] | -0.0108 | [-0.0544, +0.0310] |
| `query+prefix_unc_k25` | 25 | 18.7 | 0.6522 | [0.6128, 0.6936] | -0.0124 | [-0.0226, -0.0018] |
| `query+prefix_handunc_k25` | 25 | 18.7 | 0.6514 | [0.6110, 0.6909] | -0.0132 | [-0.0315, +0.0042] |
| `prefix_handunc_kfull` | full | 38.2 | 0.6452 | [0.6092, 0.6839] | -0.0194 | [-0.0631, +0.0252] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.6412 | [0.5965, 0.6855] | -0.0234 | [-0.0685, +0.0240] |
| `prefix_unc_k200` | 200 | 29.2 | 0.6393 | [0.5973, 0.6787] | -0.0254 | [-0.0733, +0.0223] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.6375 | [0.5965, 0.6793] | -0.0272 | [-0.0692, +0.0160] |
| `prefix_handunc_k400` | 400 | 37.5 | 0.6358 | [0.5943, 0.6784] | -0.0288 | [-0.0730, +0.0161] |
| `prefix_hand_k400` | 400 | 37.5 | 0.6345 | [0.5908, 0.6788] | -0.0301 | [-0.0747, +0.0160] |
| `prefix_unc_kfull` | full | 38.2 | 0.6333 | [0.5922, 0.6749] | -0.0313 | [-0.0824, +0.0183] |
| `prefix_unc_k400` | 400 | 37.5 | 0.6281 | [0.5849, 0.6697] | -0.0365 | [-0.0868, +0.0116] |
| `prefix_hand_kfull` | full | 38.2 | 0.6270 | [0.5850, 0.6679] | -0.0377 | [-0.0816, +0.0087] |
| `prefix_hand_k200` | 200 | 29.2 | 0.6263 | [0.5828, 0.6709] | -0.0384 | [-0.0841, +0.0085] |
| `prefix_handunc_k200` | 200 | 29.2 | 0.6230 | [0.5803, 0.6674] | -0.0416 | [-0.0876, +0.0039] |
| `prefix_unc_k100` | 100 | 23.2 | 0.6139 | [0.5750, 0.6518] | -0.0507 | [-0.1002, -0.0023] |
| `length_only_kfull` | full | 38.2 | 0.6130 | [0.5707, 0.6550] | -0.0516 | [-0.0995, -0.0037] |
| `length_only_k400` | 400 | 37.5 | 0.6114 | [0.5710, 0.6527] | -0.0532 | [-0.0964, -0.0071] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.6098 | [0.5678, 0.6526] | -0.0548 | [-0.0984, -0.0107] |
| `prefix_handunc_k100` | 100 | 23.2 | 0.6092 | [0.5652, 0.6511] | -0.0554 | [-0.1046, -0.0081] |
| `length_only_k200` | 200 | 29.2 | 0.6014 | [0.5606, 0.6427] | -0.0632 | [-0.1101, -0.0160] |
| `prefix_hand_k100` | 100 | 23.2 | 0.6002 | [0.5535, 0.6452] | -0.0645 | [-0.1147, -0.0171] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.5959 | [0.5521, 0.6410] | -0.0687 | [-0.1094, -0.0247] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.5841 | [0.5451, 0.6261] | -0.0805 | [-0.1273, -0.0335] |
| `prefix_handunc_k50` | 50 | 20.2 | 0.5767 | [0.5375, 0.6149] | -0.0879 | [-0.1405, -0.0378] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.5724 | [0.5324, 0.6131] | -0.0922 | [-0.1373, -0.0456] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.5713 | [0.5302, 0.6140] | -0.0933 | [-0.1400, -0.0463] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.5713 | [0.5302, 0.6140] | -0.0933 | [-0.1400, -0.0463] |
| `prefix_emb_k50` | 50 | 20.2 | 0.5640 | [0.5209, 0.6086] | -0.1006 | [-0.1477, -0.0490] |
| `prefix_emb_k200` | 200 | 29.2 | 0.5637 | [0.5250, 0.6051] | -0.1009 | [-0.1530, -0.0483] |
| `prefix_hand_k50` | 50 | 20.2 | 0.5603 | [0.5194, 0.6019] | -0.1043 | [-0.1582, -0.0497] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.5588 | [0.5170, 0.6007] | -0.1058 | [-0.1518, -0.0570] |
| `length_only_k100` | 100 | 23.2 | 0.5537 | [0.5134, 0.5934] | -0.1109 | [-0.1620, -0.0625] |
| `prefix_unc_k50` | 50 | 20.2 | 0.5533 | [0.5146, 0.5897] | -0.1113 | [-0.1652, -0.0584] |
| `prefix_emb_k400` | 400 | 37.5 | 0.5478 | [0.5087, 0.5912] | -0.1168 | [-0.1671, -0.0640] |
| `prefix_emb_kfull` | full | 38.2 | 0.5478 | [0.5087, 0.5912] | -0.1168 | [-0.1671, -0.0640] |
| `prefix_emb_k25` | 25 | 18.7 | 0.5412 | [0.5002, 0.5828] | -0.1234 | [-0.1781, -0.0693] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5391 | [0.4955, 0.5832] | -0.1255 | [-0.1788, -0.0717] |
| `prefix_handunc_k25` | 25 | 18.7 | 0.5355 | [0.4911, 0.5788] | -0.1291 | [-0.1786, -0.0790] |
| `prefix_emb_k100` | 100 | 23.2 | 0.5303 | [0.4887, 0.5721] | -0.1343 | [-0.1858, -0.0817] |
| `prefix_unc_k25` | 25 | 18.7 | 0.5169 | [0.4739, 0.5612] | -0.1477 | [-0.1990, -0.0941] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4829 | [0.4426, 0.5251] | -0.1817 | [-0.2365, -0.1238] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4795 | [0.4361, 0.5220] | -0.1851 | [-0.2444, -0.1264] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4795 | [0.4361, 0.5220] | -0.1851 | [-0.2444, -0.1264] |
| `prefix_unc_k0` | 0 | 0.0 | 0.4795 | [0.4361, 0.5220] | -0.1851 | [-0.2444, -0.1264] |
| `prefix_handunc_k0` | 0 | 0.0 | 0.4795 | [0.4361, 0.5220] | -0.1851 | [-0.2444, -0.1264] |
| `length_only_k0` | 0 | 0.0 | 0.4795 | [0.4361, 0.5220] | -0.1851 | [-0.2444, -0.1264] |
| `length_only_k25` | 25 | 18.7 | 0.4795 | [0.4361, 0.5220] | -0.1851 | [-0.2444, -0.1264] |
| `length_only_k50` | 50 | 20.2 | 0.4756 | [0.4337, 0.5177] | -0.1890 | [-0.2478, -0.1315] |

## Part 1 — held-out AUROC for `evidence_outside_window`

| router | k | latency s | AUROC | 95% CI | delta vs query-only | paired 95% CI |
|---|---|---|---|---|---|---|
| `prefix_hand_k50` | 50 | 20.2 | 0.6018 | [0.5402, 0.6621] | +0.1290 | [+0.0611, +0.2038] |
| `prefix_handunc_k50` | 50 | 20.2 | 0.5777 | [0.5232, 0.6324] | +0.1048 | [+0.0338, +0.1788] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.5681 | [0.5116, 0.6236] | +0.0953 | [+0.0244, +0.1640] |
| `prefix_hand_k100` | 100 | 23.2 | 0.5433 | [0.4815, 0.6065] | +0.0705 | [-0.0055, +0.1490] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.5433 | [0.4851, 0.5996] | +0.0704 | [+0.0036, +0.1366] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.5370 | [0.4766, 0.5974] | +0.0642 | [-0.0059, +0.1321] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5353 | [0.4744, 0.5931] | +0.0624 | [-0.0129, +0.1388] |
| `prefix_unc_k50` | 50 | 20.2 | 0.5336 | [0.4761, 0.5901] | +0.0608 | [-0.0208, +0.1410] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.5288 | [0.4670, 0.5882] | +0.0560 | [-0.0149, +0.1247] |
| `query+prefix_handunc_k400` | 400 | 37.5 | 0.5269 | [0.4699, 0.5813] | +0.0541 | [+0.0012, +0.1055] |
| `query+prefix_handunc_k200` | 200 | 29.2 | 0.5255 | [0.4666, 0.5823] | +0.0526 | [+0.0066, +0.0974] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.5253 | [0.4653, 0.5845] | +0.0525 | [+0.0150, +0.0919] |
| `query+prefix_handunc_k50` | 50 | 20.2 | 0.5248 | [0.4678, 0.5789] | +0.0520 | [+0.0098, +0.0956] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.5248 | [0.4649, 0.5827] | +0.0520 | [-0.0128, +0.1165] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.5228 | [0.4638, 0.5820] | +0.0500 | [-0.0217, +0.1214] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.5227 | [0.4650, 0.5800] | +0.0498 | [+0.0156, +0.0852] |
| `prefix_handunc_k25` | 25 | 18.7 | 0.5224 | [0.4568, 0.5923] | +0.0496 | [-0.0314, +0.1322] |
| `prefix_emb_k25` | 25 | 18.7 | 0.5219 | [0.4585, 0.5859] | +0.0491 | [-0.0272, +0.1235] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.5213 | [0.4657, 0.5756] | +0.0484 | [+0.0041, +0.0926] |
| `query+prefix_handunc_kfull` | full | 38.2 | 0.5193 | [0.4614, 0.5756] | +0.0464 | [-0.0037, +0.1025] |
| `query+prefix_unc_k400` | 400 | 37.5 | 0.5153 | [0.4567, 0.5724] | +0.0425 | [+0.0025, +0.0808] |
| `prefix_unc_k25` | 25 | 18.7 | 0.5131 | [0.4503, 0.5796] | +0.0403 | [-0.0413, +0.1238] |
| `query+prefix_unc_k200` | 200 | 29.2 | 0.5117 | [0.4536, 0.5686] | +0.0388 | [-0.0000, +0.0775] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.5106 | [0.4559, 0.5631] | +0.0378 | [-0.0110, +0.0861] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.5083 | [0.4455, 0.5695] | +0.0355 | [-0.0361, +0.1080] |
| `query+prefix_handunc_k100` | 100 | 23.2 | 0.5082 | [0.4475, 0.5672] | +0.0354 | [-0.0056, +0.0763] |
| `prefix_handunc_k100` | 100 | 23.2 | 0.5081 | [0.4490, 0.5648] | +0.0352 | [-0.0395, +0.1113] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.5072 | [0.4525, 0.5639] | +0.0344 | [+0.0059, +0.0675] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.5036 | [0.4481, 0.5604] | +0.0308 | [+0.0097, +0.0521] |
| `query+prefix_unc_kfull` | full | 38.2 | 0.5036 | [0.4449, 0.5574] | +0.0307 | [-0.0064, +0.0684] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.5029 | [0.4474, 0.5597] | +0.0301 | [+0.0084, +0.0514] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.4986 | [0.4425, 0.5571] | +0.0257 | [+0.0101, +0.0414] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.4969 | [0.4406, 0.5557] | +0.0240 | [+0.0068, +0.0414] |
| `prefix_hand_k200` | 200 | 29.2 | 0.4937 | [0.4329, 0.5533] | +0.0209 | [-0.0609, +0.1032] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.4910 | [0.4314, 0.5506] | +0.0182 | [-0.0563, +0.0932] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.4907 | [0.4309, 0.5505] | +0.0179 | [-0.0269, +0.0710] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.4892 | [0.4273, 0.5474] | +0.0163 | [-0.0541, +0.0878] |
| `prefix_handunc_k200` | 200 | 29.2 | 0.4880 | [0.4260, 0.5486] | +0.0151 | [-0.0656, +0.0945] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.4876 | [0.4287, 0.5441] | +0.0147 | [-0.0137, +0.0447] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.4870 | [0.4292, 0.5448] | +0.0141 | [+0.0010, +0.0276] |
| `query+prefix_unc_k100` | 100 | 23.2 | 0.4850 | [0.4294, 0.5369] | +0.0122 | [-0.0207, +0.0446] |
| `query+prefix_unc_k50` | 50 | 20.2 | 0.4845 | [0.4314, 0.5396] | +0.0117 | [-0.0187, +0.0432] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4799 | [0.4180, 0.5426] | +0.0071 | [-0.0845, +0.0958] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4799 | [0.4180, 0.5426] | +0.0071 | [-0.0845, +0.0958] |
| `prefix_unc_k0` | 0 | 0.0 | 0.4799 | [0.4180, 0.5426] | +0.0071 | [-0.0845, +0.0958] |
| `prefix_handunc_k0` | 0 | 0.0 | 0.4799 | [0.4180, 0.5426] | +0.0071 | [-0.0845, +0.0958] |
| `length_only_k0` | 0 | 0.0 | 0.4799 | [0.4180, 0.5426] | +0.0071 | [-0.0845, +0.0958] |
| `length_only_k25` | 25 | 18.7 | 0.4799 | [0.4180, 0.5426] | +0.0071 | [-0.0845, +0.0958] |
| `prefix_emb_k50` | 50 | 20.2 | 0.4789 | [0.4129, 0.5414] | +0.0061 | [-0.0780, +0.0867] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.4788 | [0.4199, 0.5367] | +0.0060 | [-0.0025, +0.0136] |
| `prefix_emb_k200` | 200 | 29.2 | 0.4776 | [0.4180, 0.5354] | +0.0048 | [-0.0809, +0.0852] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.4771 | [0.4213, 0.5360] | +0.0043 | [-0.0610, +0.0742] |
| `length_only_k100` | 100 | 23.2 | 0.4731 | [0.4191, 0.5285] | +0.0002 | [-0.0813, +0.0865] |
| `prefix_handunc_kfull` | full | 38.2 | 0.4730 | [0.4139, 0.5308] | +0.0002 | [-0.0800, +0.0832] |
| `query_only` | None | 0.0 | 0.4728 | [0.4136, 0.5310] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.4728 | [0.4136, 0.5310] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.4728 | [0.4136, 0.5310] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_unc_k0` | 0 | 0.0 | 0.4728 | [0.4136, 0.5310] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_handunc_k0` | 0 | 0.0 | 0.4728 | [0.4136, 0.5310] | +0.0000 | [+0.0000, +0.0000] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4722 | [0.4174, 0.5291] | -0.0006 | [-0.0705, +0.0744] |
| `query+prefix_unc_k25` | 25 | 18.7 | 0.4711 | [0.4143, 0.5272] | -0.0018 | [-0.0194, +0.0153] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.4706 | [0.4101, 0.5341] | -0.0022 | [-0.0784, +0.0785] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.4706 | [0.4101, 0.5341] | -0.0023 | [-0.0784, +0.0785] |
| `query+prefix_handunc_k25` | 25 | 18.7 | 0.4698 | [0.4090, 0.5281] | -0.0030 | [-0.0361, +0.0316] |
| `prefix_unc_k100` | 100 | 23.2 | 0.4686 | [0.4122, 0.5241] | -0.0043 | [-0.0844, +0.0783] |
| `prefix_handunc_k400` | 400 | 37.5 | 0.4686 | [0.4082, 0.5273] | -0.0042 | [-0.0852, +0.0754] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.4677 | [0.4078, 0.5277] | -0.0051 | [-0.0298, +0.0215] |
| `prefix_hand_k400` | 400 | 37.5 | 0.4653 | [0.4042, 0.5250] | -0.0076 | [-0.0870, +0.0736] |
| `prefix_emb_k400` | 400 | 37.5 | 0.4615 | [0.3992, 0.5262] | -0.0114 | [-0.0947, +0.0731] |
| `prefix_emb_kfull` | full | 38.2 | 0.4615 | [0.3992, 0.5261] | -0.0114 | [-0.0947, +0.0732] |
| `prefix_unc_k200` | 200 | 29.2 | 0.4580 | [0.4009, 0.5196] | -0.0149 | [-0.0956, +0.0651] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4560 | [0.3943, 0.5194] | -0.0168 | [-0.1070, +0.0728] |
| `prefix_unc_kfull` | full | 38.2 | 0.4541 | [0.3983, 0.5118] | -0.0188 | [-0.0977, +0.0625] |
| `prefix_unc_k400` | 400 | 37.5 | 0.4538 | [0.3921, 0.5163] | -0.0191 | [-0.1002, +0.0609] |
| `length_only_k200` | 200 | 29.2 | 0.4476 | [0.3867, 0.5085] | -0.0253 | [-0.1113, +0.0641] |
| `length_only_k400` | 400 | 37.5 | 0.4460 | [0.3815, 0.5094] | -0.0268 | [-0.1089, +0.0570] |
| `length_only_k50` | 50 | 20.2 | 0.4263 | [0.3605, 0.4922] | -0.0465 | [-0.1347, +0.0406] |
| `prefix_hand_kfull` | full | 38.2 | 0.4207 | [0.3604, 0.4857] | -0.0522 | [-0.1330, +0.0370] |
| `length_only_kfull` | full | 38.2 | 0.3900 | [0.3272, 0.4550] | -0.0828 | [-0.1641, +0.0036] |

## Part 2 — escalation utility

| e | random | perfect oracle | always-local | always-cloud |
|---|---|---|---|---|
| 0.1 | 33.00 | 42.25 | 32.31 | 39.53 |
| 0.2 | 33.72 | 51.83 | 32.31 | 39.53 |
| 0.3 | 34.48 | 51.83 | 32.31 | 39.53 |
| 0.5 | 35.99 | 51.83 | 32.31 | 39.53 |
| 1.0 | 39.53 | 39.53 | 32.31 | 39.53 |

### At e = 0.2, every router, both rankings

| router | k | latency s | rank | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|---|
| `prefix_unc_k50` | 50 | 20.2 | by_failure | 36.33 | +3.43 | [+1.44, +5.19] |
| `prefix_handunc_k50` | 50 | 20.2 | by_failure | 36.09 | +3.19 | [+1.41, +5.03] |
| `prefix_handunc_k50` | 50 | 20.2 | by_gain | 36.69 | +2.48 | [+0.36, +4.48] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_failure | 34.91 | +2.01 | [+0.79, +3.42] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_gain | 36.21 | +2.01 | [+0.37, +3.11] |
| `prefix_handunc_kfull` | full | 38.2 | by_failure | 34.79 | +1.89 | [+0.00, +3.92] |
| `prefix_hand_kfull` | full | 38.2 | by_failure | 34.79 | +1.89 | [+0.00, +4.18] |
| `length_only_k200` | 200 | 29.2 | by_failure | 34.79 | +1.89 | [-0.34, +3.88] |
| `prefix_unc_kfull` | full | 38.2 | by_failure | 34.67 | +1.77 | [-0.35, +3.90] |
| `prefix_hand_k50` | 50 | 20.2 | by_gain | 35.98 | +1.77 | [-0.36, +3.62] |
| `prefix_hand_k50` | 50 | 20.2 | by_failure | 34.67 | +1.77 | [+0.00, +4.12] |
| `length_only_kfull` | full | 38.2 | by_failure | 34.67 | +1.77 | [-0.12, +4.24] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_failure | 34.44 | +1.54 | [+0.47, +2.75] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_failure | 34.44 | +1.54 | [+0.12, +2.99] |
| `prefix_emb_k0` | 0 | 0.0 | by_failure | 34.44 | +1.54 | [-0.95, +3.50] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_gain | 35.62 | +1.42 | [-0.12, +2.84] |
| `prefix_unc_k100` | 100 | 23.2 | by_failure | 34.32 | +1.42 | [-0.36, +3.40] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_gain | 35.50 | +1.30 | [-0.37, +2.48] |
| `prefix_unc_k400` | 400 | 37.5 | by_failure | 34.20 | +1.30 | [-0.73, +3.37] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_gain | 35.38 | +1.18 | [-0.23, +2.67] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_gain | 35.38 | +1.18 | [-0.37, +2.70] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_gain | 35.38 | +1.18 | [-0.37, +2.33] |
| `prefix_unc_k200` | 200 | 29.2 | by_failure | 34.08 | +1.18 | [-0.87, +3.38] |
| `prefix_emb_kfull` | full | 38.2 | by_failure | 34.08 | +1.18 | [-0.82, +3.29] |
| `prefix_emb_k50` | 50 | 20.2 | by_failure | 34.08 | +1.18 | [-0.60, +3.08] |
| `prefix_emb_k400` | 400 | 37.5 | by_failure | 34.08 | +1.18 | [-0.81, +3.29] |
| `prefix_emb_k25` | 25 | 18.7 | by_gain | 35.38 | +1.18 | [-1.06, +3.15] |
| `length_only_k100` | 100 | 23.2 | by_failure | 34.08 | +1.18 | [-1.28, +2.94] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_gain | 35.27 | +1.06 | [-0.48, +2.50] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_gain | 35.27 | +1.06 | [-0.72, +2.60] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_failure | 33.96 | +1.06 | [-0.58, +2.45] |
| `query+prefix_hand_kfull` | full | 38.2 | by_failure | 33.96 | +1.06 | [-0.23, +2.48] |
| `prefix_unc_k50` | 50 | 20.2 | by_gain | 35.27 | +1.06 | [-1.22, +3.03] |
| `prefix_unc_k0` | 0 | 0.0 | by_failure | 33.96 | +1.06 | [-1.12, +3.39] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_failure | 33.96 | +1.06 | [-1.12, +3.39] |
| `prefix_handunc_k0` | 0 | 0.0 | by_failure | 33.96 | +1.06 | [-1.12, +3.39] |
| `prefix_hand_k0` | 0 | 0.0 | by_failure | 33.96 | +1.06 | [-1.12, +3.39] |
| `length_only_k50` | 50 | 20.2 | by_failure | 33.96 | +1.06 | [-1.22, +3.16] |
| `length_only_k25` | 25 | 18.7 | by_failure | 33.96 | +1.06 | [-1.12, +3.39] |
| `length_only_k0` | 0 | 0.0 | by_failure | 33.96 | +1.06 | [-1.12, +3.39] |
| `query+prefix_unc_kfull` | full | 38.2 | by_gain | 35.15 | +0.95 | [-0.71, +2.47] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_gain | 35.15 | +0.95 | [-1.16, +2.91] |
| `prefix_unc_kfull` | full | 38.2 | by_gain | 35.15 | +0.95 | [-1.20, +2.83] |
| `prefix_unc_k400` | 400 | 37.5 | by_gain | 35.15 | +0.95 | [-1.18, +2.89] |
| `prefix_unc_k100` | 100 | 23.2 | by_gain | 35.15 | +0.95 | [-1.30, +2.93] |
| `prefix_emb_k200` | 200 | 29.2 | by_failure | 33.85 | +0.95 | [-1.19, +2.91] |
| `query+prefix_unc_kfull` | full | 38.2 | by_failure | 33.73 | +0.83 | [-0.35, +2.21] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_gain | 35.03 | +0.83 | [-0.36, +1.83] |
| `query+prefix_emb_kfull` | full | 38.2 | by_failure | 33.73 | +0.83 | [-0.94, +2.85] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_failure | 33.73 | +0.83 | [-0.94, +2.85] |
| `prefix_handunc_k400` | 400 | 37.5 | by_gain | 35.03 | +0.83 | [-1.20, +2.87] |
| `prefix_handunc_k400` | 400 | 37.5 | by_failure | 33.73 | +0.83 | [-1.06, +3.04] |
| `prefix_handunc_k100` | 100 | 23.2 | by_gain | 35.03 | +0.83 | [-1.40, +2.90] |
| `prefix_hand_k400` | 400 | 37.5 | by_failure | 33.73 | +0.83 | [-1.34, +2.93] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_gain | 34.91 | +0.71 | [-0.60, +2.13] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_failure | 33.61 | +0.71 | [-0.96, +2.62] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_failure | 33.61 | +0.71 | [-1.26, +2.57] |
| `prefix_tfidf_kfull` | full | 38.2 | by_failure | 33.61 | +0.71 | [-0.61, +2.40] |
| `prefix_handunc_k25` | 25 | 18.7 | by_failure | 33.61 | +0.71 | [-1.29, +3.05] |
| `prefix_handunc_k200` | 200 | 29.2 | by_failure | 33.61 | +0.71 | [-0.95, +2.87] |
| `prefix_hand_kfull` | full | 38.2 | by_gain | 34.91 | +0.71 | [-1.40, +2.73] |
| `prefix_hand_k25` | 25 | 18.7 | by_failure | 33.61 | +0.71 | [-1.44, +2.69] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_failure | 33.61 | +0.71 | [-0.47, +1.97] |
| `query+prefix_unc_k400` | 400 | 37.5 | by_failure | 33.49 | +0.59 | [-0.59, +1.75] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_gain | 34.79 | +0.59 | [-1.02, +2.10] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_failure | 33.49 | +0.59 | [-0.38, +1.76] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_gain | 34.79 | +0.59 | [-0.93, +2.09] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_gain | 34.79 | +0.59 | [-0.70, +1.96] |
| `query+prefix_hand_kfull` | full | 38.2 | by_gain | 34.67 | +0.47 | [-0.96, +2.29] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_failure | 33.37 | +0.47 | [-1.06, +2.15] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_failure | 33.37 | +0.47 | [-1.16, +2.57] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_failure | 33.37 | +0.47 | [-1.04, +1.89] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_failure | 33.37 | +0.47 | [-1.28, +2.00] |
| `prefix_handunc_k100` | 100 | 23.2 | by_failure | 33.37 | +0.47 | [-1.16, +2.33] |
| `length_only_kfull` | full | 38.2 | by_gain | 34.67 | +0.47 | [-1.89, +2.59] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_gain | 34.56 | +0.35 | [-0.71, +0.94] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_failure | 33.25 | +0.35 | [-1.40, +2.18] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_failure | 33.25 | +0.35 | [-1.08, +1.85] |
| `prefix_handunc_k25` | 25 | 18.7 | by_gain | 34.56 | +0.35 | [-1.96, +2.62] |
| `prefix_emb_k100` | 100 | 23.2 | by_failure | 33.25 | +0.35 | [-1.29, +2.33] |
| `query+prefix_unc_k400` | 400 | 37.5 | by_gain | 34.44 | +0.24 | [-1.20, +1.70] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_failure | 33.14 | +0.24 | [-0.97, +1.07] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_failure | 33.14 | +0.24 | [-0.47, +0.95] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_gain | 34.44 | +0.24 | [-1.32, +2.06] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_failure | 33.14 | +0.24 | [-0.83, +1.57] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_gain | 34.44 | +0.24 | [-0.59, +1.06] |
| `prefix_unc_k25` | 25 | 18.7 | by_gain | 34.44 | +0.24 | [-2.26, +2.52] |
| `prefix_emb_k25` | 25 | 18.7 | by_failure | 33.14 | +0.24 | [-1.31, +2.38] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_gain | 34.32 | +0.12 | [-1.29, +1.31] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_failure | 33.02 | +0.12 | [-0.61, +1.15] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_gain | 34.32 | +0.12 | [-1.99, +1.80] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_failure | 33.02 | +0.12 | [-0.36, +0.48] |
| `prefix_handunc_kfull` | full | 38.2 | by_gain | 34.32 | +0.12 | [-1.75, +2.16] |
| `prefix_hand_k200` | 200 | 29.2 | by_failure | 33.02 | +0.12 | [-1.58, +2.15] |
| `query_only` | None | 0.0 | by_gain | 34.20 | +0.00 | [+0.00, +0.00] |
| `query_only` | None | 0.0 | by_failure | 32.90 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_gain | 34.20 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_failure | 32.90 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_failure | 32.90 | +0.00 | [-1.04, +0.95] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_failure | 32.90 | +0.00 | [-1.18, +0.70] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_gain | 34.20 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_failure | 32.90 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_failure | 32.90 | +0.00 | [-1.07, +1.05] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_failure | 32.90 | +0.00 | [-1.05, +1.50] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_gain | 34.20 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_failure | 32.90 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_failure | 32.90 | +0.00 | [-1.17, +1.03] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_gain | 34.20 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_failure | 32.90 | +0.00 | [+0.00, +0.00] |
| `prefix_unc_k25` | 25 | 18.7 | by_failure | 32.90 | +0.00 | [-1.75, +2.15] |
| `prefix_hand_k400` | 400 | 37.5 | by_gain | 34.20 | +0.00 | [-2.26, +1.91] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_failure | 32.78 | -0.12 | [-1.14, +1.06] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_gain | 34.08 | -0.12 | [-1.80, +1.55] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_failure | 32.78 | -0.12 | [-1.69, +1.94] |
| `prefix_unc_k200` | 200 | 29.2 | by_gain | 34.08 | -0.12 | [-2.20, +1.84] |
| `prefix_tfidf_kfull` | full | 38.2 | by_gain | 34.08 | -0.12 | [-2.19, +2.04] |
| `prefix_handunc_k200` | 200 | 29.2 | by_gain | 34.08 | -0.12 | [-1.91, +1.96] |
| `prefix_hand_k100` | 100 | 23.2 | by_failure | 32.78 | -0.12 | [-2.02, +2.00] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_failure | 32.66 | -0.24 | [-1.05, +0.59] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_failure | 32.66 | -0.24 | [-1.32, +1.18] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_gain | 33.96 | -0.24 | [-2.39, +1.60] |
| `prefix_hand_k200` | 200 | 29.2 | by_gain | 33.96 | -0.24 | [-2.02, +1.91] |
| `prefix_hand_k100` | 100 | 23.2 | by_gain | 33.96 | -0.24 | [-2.08, +1.61] |
| `prefix_emb_k100` | 100 | 23.2 | by_gain | 33.96 | -0.24 | [-2.16, +1.80] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_gain | 33.85 | -0.35 | [-2.10, +0.80] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_failure | 32.54 | -0.35 | [-0.97, +0.59] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_failure | 32.54 | -0.35 | [-1.21, +0.62] |
| `length_only_k400` | 400 | 37.5 | by_failure | 32.43 | -0.47 | [-2.27, +1.79] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_failure | 32.31 | -0.59 | [-1.32, +0.12] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_gain | 33.61 | -0.59 | [-1.99, +0.92] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_gain | 33.61 | -0.59 | [-2.39, +0.95] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_failure | 32.31 | -0.59 | [-2.33, +1.30] |
| `prefix_emb_k50` | 50 | 20.2 | by_gain | 33.61 | -0.59 | [-2.58, +1.51] |
| `length_only_k400` | 400 | 37.5 | by_gain | 33.61 | -0.59 | [-3.23, +1.44] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_gain | 33.37 | -0.83 | [-2.61, +0.49] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_gain | 33.37 | -0.83 | [-2.44, +0.47] |
| `prefix_emb_k0` | 0 | 0.0 | by_gain | 33.37 | -0.83 | [-2.74, +1.17] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_gain | 33.25 | -0.95 | [-3.14, +0.99] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_gain | 33.02 | -1.18 | [-3.16, +0.58] |
| `length_only_k50` | 50 | 20.2 | by_gain | 32.90 | -1.30 | [-3.21, +0.58] |
| `prefix_unc_k0` | 0 | 0.0 | by_gain | 32.66 | -1.54 | [-3.44, +0.36] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_gain | 32.66 | -1.54 | [-3.44, +0.36] |
| `prefix_handunc_k0` | 0 | 0.0 | by_gain | 32.66 | -1.54 | [-3.44, +0.36] |
| `prefix_hand_k0` | 0 | 0.0 | by_gain | 32.66 | -1.54 | [-3.44, +0.36] |
| `prefix_emb_k200` | 200 | 29.2 | by_gain | 32.66 | -1.54 | [-3.59, +0.24] |
| `length_only_k25` | 25 | 18.7 | by_gain | 32.66 | -1.54 | [-3.44, +0.36] |
| `length_only_k0` | 0 | 0.0 | by_gain | 32.66 | -1.54 | [-3.44, +0.36] |
| `prefix_hand_k25` | 25 | 18.7 | by_gain | 32.54 | -1.66 | [-3.48, +0.36] |
| `length_only_k100` | 100 | 23.2 | by_gain | 32.54 | -1.66 | [-3.74, +0.12] |
| `length_only_k200` | 200 | 29.2 | by_gain | 32.43 | -1.77 | [-3.27, +0.83] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_gain | 32.31 | -1.89 | [-3.92, +0.12] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_gain | 32.31 | -1.89 | [-3.90, +0.46] |
| `query+prefix_emb_kfull` | full | 38.2 | by_gain | 31.72 | -2.48 | [-4.37, -0.61] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_gain | 31.72 | -2.48 | [-4.37, -0.61] |
| `prefix_emb_kfull` | full | 38.2 | by_gain | 31.72 | -2.48 | [-4.64, -0.51] |
| `prefix_emb_k400` | 400 | 37.5 | by_gain | 31.72 | -2.48 | [-4.64, -0.51] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_gain | 31.48 | -2.72 | [-4.76, -0.70] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_gain | 31.12 | -3.08 | [-5.01, -0.98] |

### Best router at each budget e (by_gain)

| e | best router | k | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|
| 0.1 | `query+prefix_handunc_k50` | 50 | 35.15 | +1.18 | [+0.12, +2.41] |
| 0.2 | `prefix_handunc_k50` | 50 | 36.69 | +2.48 | [+0.36, +4.48] |
| 0.3 | `prefix_handunc_k50` | 50 | 37.28 | +1.77 | [-0.60, +4.45] |
| 0.5 | `query+prefix_unc_k400` | 400 | 38.58 | +1.77 | [+0.00, +3.32] |
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
| `length_only_k50` | 0.5450 |
| `prefix_emb_k0` | 0.5439 |
| `length_only_k200` | 0.5433 |
| `prefix_hand_k0` | 0.5374 |
| `prefix_tfidf_k0` | 0.5374 |
| `prefix_unc_k0` | 0.5374 |
| `prefix_handunc_k0` | 0.5374 |
| `length_only_k0` | 0.5374 |
| `length_only_k25` | 0.5374 |
| `length_only_k100` | 0.5371 |
| `prefix_unc_k50` | 0.5341 |
| `prefix_unc_k400` | 0.5206 |
| `prefix_handunc_k200` | 0.5154 |
| `length_only_kfull` | 0.5138 |
| `prefix_hand_kfull` | 0.5067 |
| `prefix_unc_k100` | 0.5048 |
| `length_only_k400` | 0.5043 |
| `prefix_hand_k200` | 0.5034 |
| `prefix_unc_kfull` | 0.5030 |
| `prefix_unc_k200` | 0.5022 |
| `prefix_emb_k25` | 0.5013 |
| `prefix_emb_k200` | 0.4986 |
| `prefix_emb_k100` | 0.4973 |
| `prefix_emb_k400` | 0.4925 |
| `prefix_emb_kfull` | 0.4925 |
| `prefix_handunc_kfull` | 0.4918 |
| `prefix_handunc_k50` | 0.4895 |
| `prefix_handunc_k400` | 0.4882 |
| `query+prefix_emb_k200` | 0.4867 |
| `prefix_hand_k25` | 0.4845 |
| `query+prefix_emb_k100` | 0.4831 |
| `prefix_emb_k50` | 0.4823 |
| `prefix_hand_k400` | 0.4802 |
| `query+prefix_emb_k400` | 0.4785 |
| `query+prefix_emb_kfull` | 0.4784 |
| `prefix_handunc_k100` | 0.4773 |
| `query+prefix_emb_k50` | 0.4733 |
| `query+prefix_emb_k25` | 0.4715 |
| `prefix_hand_k100` | 0.4695 |
| `prefix_hand_k50` | 0.4637 |
| `prefix_handunc_k25` | 0.4562 |
| `prefix_tfidf_k200` | 0.4559 |
| `query+prefix_handunc_k200` | 0.4559 |
| `prefix_unc_k25` | 0.4518 |
| `prefix_tfidf_kfull` | 0.4472 |
| `prefix_tfidf_k100` | 0.4469 |
| `query+prefix_hand_k200` | 0.4464 |
| `prefix_tfidf_k400` | 0.4397 |
| `prefix_tfidf_k25` | 0.4338 |
| `query+prefix_hand_kfull` | 0.4301 |
| `query+prefix_unc_k400` | 0.4271 |
| `query+prefix_handunc_k400` | 0.4247 |
| `query+prefix_unc_k50` | 0.4242 |
| `query+prefix_handunc_kfull` | 0.4217 |
| `query+prefix_hand_k25` | 0.4202 |
| `query+prefix_unc_k200` | 0.4187 |
| `query+prefix_tfidf_kfull` | 0.4168 |
| `query+prefix_handunc_k50` | 0.4159 |
| `query+prefix_handunc_k25` | 0.4139 |
| `query+prefix_hand_k400` | 0.4115 |
| `query+prefix_tfidf_k200` | 0.4088 |
| `prefix_tfidf_k50` | 0.4086 |
| `query+prefix_handunc_k100` | 0.4082 |
| `query+prefix_tfidf_k400` | 0.4078 |
| `query+prefix_hand_k100` | 0.4075 |
| `query+prefix_emb_k0` | 0.4056 |
| `query+prefix_unc_k100` | 0.4053 |
| `query+prefix_tfidf_k100` | 0.4052 |
| `query+prefix_tfidf_k25` | 0.4037 |
| `query+prefix_unc_kfull` | 0.4031 |
| `query_only` | 0.4019 |
| `query+prefix_hand_k0` | 0.4019 |
| `query+prefix_tfidf_k0` | 0.4019 |
| `query+prefix_unc_k0` | 0.4019 |
| `query+prefix_handunc_k0` | 0.4019 |
| `query+prefix_hand_k50` | 0.4002 |
| `query+prefix_tfidf_k50` | 0.3982 |
| `query+prefix_unc_k25` | 0.3974 |

## Mechanism Step 2 — feature audit (CONSTANT entries are stopping flags)

| k | features CONSTANT across questions |
|---|---|
| 0 | 45: hesitation_wait, hesitation_but, hesitation_total, n_letter_mentions, n_letter_changes, letter_appears, rep3_total, rep3_max, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, n_prefix_chars, unc_mean, unc_sd, unc_max, unc_min, unc_last, unc_sum, unc_slope, unc_mean_firsthalf, unc_mean_secondhalf, unc_n, unc_frac_gt_0.1, unc_frac_gt_0.5, unc_frac_gt_1.0, unc_frac_gt_2.0 |
| 25 | 23: n_letter_changes, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, trace_closed_by_k, n_prefix_tokens, unc_min, unc_n |
| 50 | 19: repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 100 | 14: phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 200 | 12: phrase::cannot see, phrase::not shown, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 400 | 12: phrase::cannot see, phrase::not shown, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| full | 10: phrase::cannot see, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine, trace_closed_by_k, unc_min |

## Mechanism Step 3 — one traced unit

Question `00c92b5c1e8ba39009169cebd31c1aa1be792c4300d01481f4a02b526c43b59d` (group `1430582088252106_start_0.0_end_599.981`), device WRONG, cloud correct, gain 1.

| k | prefix tokens | non-zero features | predicted gain | rank | escalated at e=0.2 |
|---|---|---|---|---|---|
| 0 | 0 | trace_closed_by_k=1 | +0.22615 | 136/845 | yes |
| 25 | 25 | rep3_max=1, repsent_max=1, n_prefix_tokens=25, n_prefix_chars=119 | +0.11354 | 322/845 | no |
| 50 | 50 | hesitation_wait=1, hesitation_total=1, rep3_max=1, repsent_max=1, n_prefix_tokens=50, n_prefix_chars=208 | +0.07838 | 412/845 | no |
| 100 | 100 | hesitation_wait=1, hesitation_total=1, rep3_total=5, rep3_max=3, repsent_max=1, n_prefix_tokens=100 | +0.17044 | 235/845 | no |
| 200 | 200 | hesitation_wait=3, hesitation_but=1, hesitation_total=4, rep3_total=14, rep3_max=4, repsent_max=1 | +0.16854 | 253/845 | no |
| 400 | 400 | hesitation_wait=7, hesitation_but=1, hesitation_total=8, rep3_total=39, rep3_max=7, repsent_max=1 | +0.24430 | 149/845 | yes |


# ERQA  (n = 400)

Device 45.75% · cloud 46.75% · gain counts {'-1': 60, '0': 276, '1': 64} · 5 folds

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
| `query+prefix_unc_kfull` | full | 38.2 | 0.6487 | [0.5929, 0.7019] | +0.0543 | [+0.0081, +0.0989] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.6388 | [0.5803, 0.6911] | +0.0445 | [-0.0055, +0.0947] |
| `query+prefix_handunc_kfull` | full | 38.2 | 0.6376 | [0.5816, 0.6936] | +0.0433 | [-0.0074, +0.0906] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.6258 | [0.5685, 0.6789] | +0.0315 | [-0.0132, +0.0780] |
| `answer_confidence` | full | 38.2 | 0.6255 | [0.5688, 0.6773] | +0.0312 | [-0.0431, +0.1081] |
| `prefix_handunc_kfull` | full | 38.2 | 0.6239 | [0.5671, 0.6783] | +0.0296 | [-0.0509, +0.1089] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.6230 | [0.5637, 0.6783] | +0.0287 | [+0.0015, +0.0534] |
| `query+prefix_unc_k400` | 400 | 37.5 | 0.6217 | [0.5680, 0.6770] | +0.0273 | [-0.0138, +0.0676] |
| `prefix_unc_kfull` | full | 38.2 | 0.6214 | [0.5679, 0.6760] | +0.0271 | [-0.0519, +0.1064] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.6179 | [0.5608, 0.6746] | +0.0236 | [-0.0208, +0.0657] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.6175 | [0.5572, 0.6723] | +0.0232 | [-0.0001, +0.0440] |
| `query+prefix_unc_k100` | 100 | 23.2 | 0.6082 | [0.5501, 0.6658] | +0.0139 | [-0.0173, +0.0460] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.6059 | [0.5451, 0.6603] | +0.0115 | [-0.0087, +0.0316] |
| `query+prefix_handunc_k400` | 400 | 37.5 | 0.6052 | [0.5489, 0.6597] | +0.0109 | [-0.0353, +0.0583] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.6048 | [0.5463, 0.6577] | +0.0104 | [-0.0332, +0.0549] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.6008 | [0.5424, 0.6565] | +0.0065 | [-0.0057, +0.0198] |
| `prefix_unc_k400` | 400 | 37.5 | 0.5991 | [0.5425, 0.6533] | +0.0047 | [-0.0723, +0.0812] |
| `prefix_hand_kfull` | full | 38.2 | 0.5971 | [0.5391, 0.6529] | +0.0028 | [-0.0719, +0.0794] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.5956 | [0.5372, 0.6514] | +0.0013 | [-0.0158, +0.0186] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.5953 | [0.5356, 0.6524] | +0.0009 | [-0.0188, +0.0205] |
| `query_only` | None | 0.0 | 0.5943 | [0.5345, 0.6511] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.5943 | [0.5345, 0.6511] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.5943 | [0.5345, 0.6511] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_unc_k0` | 0 | 0.0 | 0.5943 | [0.5345, 0.6511] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_handunc_k0` | 0 | 0.0 | 0.5943 | [0.5345, 0.6511] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_unc_k200` | 200 | 29.2 | 0.5925 | [0.5326, 0.6499] | -0.0018 | [-0.0376, +0.0343] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.5920 | [0.5317, 0.6486] | -0.0024 | [-0.0338, +0.0306] |
| `length_only_kfull` | full | 38.2 | 0.5916 | [0.5360, 0.6464] | -0.0027 | [-0.0812, +0.0776] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.5883 | [0.5294, 0.6458] | -0.0061 | [-0.0216, +0.0080] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.5883 | [0.5289, 0.6432] | -0.0060 | [-0.0521, +0.0430] |
| `prefix_hand_k400` | 400 | 37.5 | 0.5877 | [0.5327, 0.6430] | -0.0067 | [-0.0793, +0.0669] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.5860 | [0.5264, 0.6434] | -0.0083 | [-0.0431, +0.0273] |
| `query+prefix_handunc_k100` | 100 | 23.2 | 0.5856 | [0.5272, 0.6438] | -0.0088 | [-0.0501, +0.0336] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.5852 | [0.5244, 0.6396] | -0.0092 | [-0.0478, +0.0300] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.5825 | [0.5240, 0.6414] | -0.0118 | [-0.0796, +0.0591] |
| `prefix_handunc_k400` | 400 | 37.5 | 0.5822 | [0.5248, 0.6370] | -0.0122 | [-0.0867, +0.0650] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.5787 | [0.5204, 0.6344] | -0.0156 | [-0.0371, +0.0050] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.5783 | [0.5186, 0.6301] | -0.0160 | [-0.0566, +0.0218] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.5726 | [0.5129, 0.6282] | -0.0217 | [-0.0738, +0.0317] |
| `query+prefix_unc_k50` | 50 | 20.2 | 0.5725 | [0.5144, 0.6309] | -0.0218 | [-0.0522, +0.0095] |
| `query+prefix_handunc_k50` | 50 | 20.2 | 0.5705 | [0.5111, 0.6285] | -0.0238 | [-0.0637, +0.0191] |
| `query+prefix_handunc_k200` | 200 | 29.2 | 0.5682 | [0.5086, 0.6246] | -0.0261 | [-0.0688, +0.0177] |
| `length_only_k400` | 400 | 37.5 | 0.5676 | [0.5103, 0.6226] | -0.0268 | [-0.1063, +0.0535] |
| `prefix_emb_k25` | 25 | 18.7 | 0.5669 | [0.5086, 0.6256] | -0.0275 | [-0.0991, +0.0483] |
| `prefix_unc_k100` | 100 | 23.2 | 0.5612 | [0.5048, 0.6169] | -0.0331 | [-0.1103, +0.0485] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.5547 | [0.4986, 0.6124] | -0.0396 | [-0.0947, +0.0173] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.5536 | [0.4979, 0.6131] | -0.0407 | [-0.1000, +0.0236] |
| `query+prefix_unc_k25` | 25 | 18.7 | 0.5527 | [0.4922, 0.6109] | -0.0417 | [-0.0656, -0.0187] |
| `length_only_k200` | 200 | 29.2 | 0.5485 | [0.4903, 0.6027] | -0.0459 | [-0.1243, +0.0312] |
| `prefix_hand_k200` | 200 | 29.2 | 0.5480 | [0.4903, 0.6016] | -0.0463 | [-0.1192, +0.0244] |
| `query+prefix_handunc_k25` | 25 | 18.7 | 0.5419 | [0.4831, 0.5985] | -0.0524 | [-0.0830, -0.0237] |
| `prefix_handunc_k100` | 100 | 23.2 | 0.5348 | [0.4769, 0.5905] | -0.0595 | [-0.1360, +0.0175] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.5294 | [0.4719, 0.5845] | -0.0650 | [-0.1315, +0.0056] |
| `prefix_hand_k100` | 100 | 23.2 | 0.5291 | [0.4742, 0.5870] | -0.0652 | [-0.1423, +0.0128] |
| `prefix_unc_k200` | 200 | 29.2 | 0.5261 | [0.4691, 0.5807] | -0.0682 | [-0.1496, +0.0129] |
| `prefix_handunc_k200` | 200 | 29.2 | 0.5206 | [0.4647, 0.5743] | -0.0737 | [-0.1468, -0.0008] |
| `prefix_emb_k50` | 50 | 20.2 | 0.5151 | [0.4589, 0.5690] | -0.0792 | [-0.1480, -0.0054] |
| `prefix_emb_k400` | 400 | 37.5 | 0.5103 | [0.4527, 0.5692] | -0.0841 | [-0.1544, -0.0161] |
| `prefix_emb_kfull` | full | 38.2 | 0.5103 | [0.4527, 0.5692] | -0.0841 | [-0.1544, -0.0161] |
| `length_only_k100` | 100 | 23.2 | 0.5053 | [0.4479, 0.5612] | -0.0891 | [-0.1696, -0.0151] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.5017 | [0.4428, 0.5605] | -0.0927 | [-0.1595, -0.0269] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.5017 | [0.4428, 0.5605] | -0.0927 | [-0.1595, -0.0269] |
| `prefix_hand_k50` | 50 | 20.2 | 0.5002 | [0.4435, 0.5575] | -0.0941 | [-0.1728, -0.0171] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.4774 | [0.4193, 0.5339] | -0.1169 | [-0.1856, -0.0452] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4738 | [0.4202, 0.5297] | -0.1205 | [-0.2002, -0.0411] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4738 | [0.4202, 0.5297] | -0.1205 | [-0.2002, -0.0411] |
| `prefix_unc_k0` | 0 | 0.0 | 0.4738 | [0.4202, 0.5297] | -0.1205 | [-0.2002, -0.0411] |
| `prefix_handunc_k0` | 0 | 0.0 | 0.4738 | [0.4202, 0.5297] | -0.1205 | [-0.2002, -0.0411] |
| `length_only_k0` | 0 | 0.0 | 0.4738 | [0.4202, 0.5297] | -0.1205 | [-0.2002, -0.0411] |
| `length_only_k25` | 25 | 18.7 | 0.4738 | [0.4202, 0.5297] | -0.1205 | [-0.2002, -0.0411] |
| `length_only_k50` | 50 | 20.2 | 0.4738 | [0.4202, 0.5297] | -0.1205 | [-0.2002, -0.0411] |
| `prefix_handunc_k50` | 50 | 20.2 | 0.4685 | [0.4137, 0.5270] | -0.1258 | [-0.2030, -0.0446] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4685 | [0.4092, 0.5257] | -0.1259 | [-0.1985, -0.0517] |
| `prefix_unc_k50` | 50 | 20.2 | 0.4614 | [0.4040, 0.5187] | -0.1329 | [-0.2136, -0.0491] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4587 | [0.4024, 0.5153] | -0.1357 | [-0.2166, -0.0549] |
| `prefix_emb_k200` | 200 | 29.2 | 0.4534 | [0.3999, 0.5124] | -0.1409 | [-0.2106, -0.0715] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.4529 | [0.3977, 0.5116] | -0.1414 | [-0.2084, -0.0758] |
| `prefix_hand_k25` | 25 | 18.7 | 0.4326 | [0.3765, 0.4875] | -0.1618 | [-0.2352, -0.0875] |
| `prefix_unc_k25` | 25 | 18.7 | 0.3965 | [0.3406, 0.4549] | -0.1978 | [-0.2723, -0.1192] |
| `prefix_handunc_k25` | 25 | 18.7 | 0.3962 | [0.3447, 0.4573] | -0.1981 | [-0.2697, -0.1265] |

## Part 2 — escalation utility

| e | random | perfect oracle | always-local | always-cloud |
|---|---|---|---|---|
| 0.1 | 45.96 | 55.75 | 45.75 | 46.75 |
| 0.2 | 46.06 | 61.75 | 45.75 | 46.75 |
| 0.3 | 46.10 | 61.75 | 45.75 | 46.75 |
| 0.5 | 46.20 | 61.75 | 45.75 | 46.75 |
| 1.0 | 46.75 | 46.75 | 45.75 | 46.75 |

### At e = 0.2, every router, both rankings

| router | k | latency s | rank | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|---|
| `query+prefix_unc_k400` | 400 | 37.5 | by_gain | 48.25 | +1.25 | [-1.00, +2.50] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_gain | 48.25 | +1.25 | [-0.50, +2.75] |
| `query+prefix_unc_kfull` | full | 38.2 | by_gain | 48.00 | +1.00 | [-0.50, +2.50] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_gain | 48.00 | +1.00 | [-1.25, +2.25] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_gain | 47.75 | +0.75 | [-0.75, +2.25] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_gain | 47.50 | +0.50 | [-1.25, +2.25] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_gain | 47.50 | +0.50 | [-1.00, +1.75] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_gain | 47.50 | +0.50 | [-1.25, +2.00] |
| `prefix_tfidf_kfull` | full | 38.2 | by_failure | 48.50 | +0.50 | [-2.25, +3.00] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_failure | 48.50 | +0.50 | [-1.75, +2.50] |
| `query+prefix_unc_kfull` | full | 38.2 | by_failure | 48.25 | +0.25 | [-1.75, +3.25] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_gain | 47.25 | +0.25 | [-1.50, +2.00] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_failure | 48.25 | +0.25 | [-1.50, +2.50] |
| `query+prefix_hand_kfull` | full | 38.2 | by_failure | 48.25 | +0.25 | [-1.75, +2.75] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_failure | 48.25 | +0.25 | [-0.75, +1.75] |
| `prefix_unc_kfull` | full | 38.2 | by_failure | 48.25 | +0.25 | [-3.00, +3.50] |
| `query_only` | None | 0.0 | by_gain | 47.00 | +0.00 | [+0.00, +0.00] |
| `query_only` | None | 0.0 | by_failure | 48.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_gain | 47.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_failure | 48.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_gain | 47.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_failure | 48.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_failure | 48.00 | +0.00 | [-2.00, +2.75] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_gain | 47.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_failure | 48.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_kfull` | full | 38.2 | by_gain | 47.00 | +0.00 | [-1.75, +1.26] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_gain | 47.00 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_failure | 48.00 | +0.00 | [+0.00, +0.00] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_gain | 47.00 | +0.00 | [-3.00, +2.50] |
| `answer_confidence` | full | 38.2 | by_gain | 47.00 | +0.00 | [-2.75, +2.75] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_failure | 47.75 | -0.25 | [-1.50, +2.00] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_failure | 47.75 | -0.25 | [-1.50, +1.50] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_failure | 47.75 | -0.25 | [-1.50, +1.50] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_gain | 46.75 | -0.25 | [-3.00, +1.25] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_gain | 46.75 | -0.25 | [-2.50, +1.00] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_gain | 46.75 | -0.25 | [-1.00, +0.25] |
| `prefix_unc_k200` | 200 | 29.2 | by_gain | 46.75 | -0.25 | [-3.26, +2.25] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_failure | 47.75 | -0.25 | [-2.25, +2.25] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_gain | 46.50 | -0.50 | [-1.75, +0.75] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_failure | 47.50 | -0.50 | [-1.75, +1.50] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_gain | 46.50 | -0.50 | [-2.25, +1.50] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_failure | 47.50 | -0.50 | [-1.50, +0.76] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_failure | 47.50 | -0.50 | [-1.50, +1.50] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_gain | 46.50 | -0.50 | [-2.75, +1.50] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_failure | 47.50 | -0.50 | [-1.50, +1.50] |
| `prefix_unc_k400` | 400 | 37.5 | by_gain | 46.50 | -0.50 | [-3.25, +1.50] |
| `prefix_unc_k100` | 100 | 23.2 | by_gain | 46.50 | -0.50 | [-3.50, +2.00] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_failure | 47.25 | -0.75 | [-2.00, +1.50] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_failure | 47.25 | -0.75 | [-2.50, +1.50] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_failure | 47.25 | -0.75 | [-1.75, +1.50] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_gain | 46.25 | -0.75 | [-2.75, +1.50] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_gain | 46.25 | -0.75 | [-2.50, +1.01] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_failure | 47.25 | -0.75 | [-2.00, +0.75] |
| `query+prefix_emb_kfull` | full | 38.2 | by_gain | 46.25 | -0.75 | [-3.51, +1.75] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_gain | 46.25 | -0.75 | [-3.75, +1.51] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_gain | 46.25 | -0.75 | [-3.51, +1.75] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_failure | 47.25 | -0.75 | [-2.00, +0.25] |
| `prefix_tfidf_kfull` | full | 38.2 | by_gain | 46.25 | -0.75 | [-3.75, +1.50] |
| `prefix_handunc_k25` | 25 | 18.7 | by_gain | 46.25 | -0.75 | [-4.25, +1.75] |
| `prefix_hand_k50` | 50 | 20.2 | by_gain | 46.25 | -0.75 | [-4.25, +2.00] |
| `length_only_kfull` | full | 38.2 | by_gain | 46.25 | -0.75 | [-4.00, +2.25] |
| `query+prefix_unc_k400` | 400 | 37.5 | by_failure | 47.00 | -1.00 | [-2.75, +1.50] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_gain | 46.00 | -1.00 | [-2.75, +1.00] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_failure | 47.00 | -1.00 | [-2.50, +1.00] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_failure | 47.00 | -1.00 | [-4.00, +2.00] |
| `prefix_unc_kfull` | full | 38.2 | by_gain | 46.00 | -1.00 | [-4.00, +2.00] |
| `prefix_unc_k50` | 50 | 20.2 | by_gain | 46.00 | -1.00 | [-4.00, +2.50] |
| `prefix_unc_k50` | 50 | 20.2 | by_failure | 47.00 | -1.00 | [-4.00, +2.00] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_gain | 46.00 | -1.00 | [-3.75, +1.75] |
| `prefix_handunc_k50` | 50 | 20.2 | by_gain | 46.00 | -1.00 | [-4.00, +2.01] |
| `prefix_emb_kfull` | full | 38.2 | by_gain | 46.00 | -1.00 | [-3.75, +1.50] |
| `prefix_emb_k50` | 50 | 20.2 | by_gain | 46.00 | -1.00 | [-3.75, +1.75] |
| `prefix_emb_k400` | 400 | 37.5 | by_gain | 46.00 | -1.00 | [-3.75, +1.50] |
| `answer_confidence` | full | 38.2 | by_failure | 47.00 | -1.00 | [-4.00, +2.75] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_failure | 46.75 | -1.25 | [-2.25, +0.75] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_gain | 45.75 | -1.25 | [-3.50, +1.00] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_failure | 46.75 | -1.25 | [-3.75, +1.00] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_failure | 46.75 | -1.25 | [-3.00, +0.75] |
| `prefix_unc_k200` | 200 | 29.2 | by_failure | 46.75 | -1.25 | [-4.50, +2.25] |
| `prefix_hand_kfull` | full | 38.2 | by_failure | 46.75 | -1.25 | [-3.75, +2.50] |
| `prefix_hand_k25` | 25 | 18.7 | by_failure | 46.75 | -1.25 | [-3.50, +1.75] |
| `prefix_emb_k50` | 50 | 20.2 | by_failure | 46.75 | -1.25 | [-4.00, +2.00] |
| `prefix_emb_k25` | 25 | 18.7 | by_failure | 46.75 | -1.25 | [-4.00, +2.25] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_gain | 45.50 | -1.50 | [-3.25, +0.25] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_gain | 45.50 | -1.50 | [-3.00, +0.00] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_failure | 46.50 | -1.50 | [-3.75, +1.75] |
| `prefix_unc_k100` | 100 | 23.2 | by_failure | 46.50 | -1.50 | [-4.00, +1.76] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_failure | 46.50 | -1.50 | [-4.00, +1.25] |
| `prefix_hand_k50` | 50 | 20.2 | by_failure | 46.50 | -1.50 | [-4.25, +1.75] |
| `length_only_k100` | 100 | 23.2 | by_failure | 46.50 | -1.50 | [-4.75, +0.75] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_failure | 46.50 | -1.50 | [-3.50, +0.50] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_gain | 45.25 | -1.75 | [-3.50, +0.00] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_failure | 46.25 | -1.75 | [-3.50, +0.50] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_failure | 46.25 | -1.75 | [-3.75, +0.50] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_gain | 45.25 | -1.75 | [-3.50, +0.00] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_gain | 45.25 | -1.75 | [-3.75, -0.25] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_failure | 46.25 | -1.75 | [-4.00, +1.75] |
| `prefix_unc_k25` | 25 | 18.7 | by_gain | 45.25 | -1.75 | [-5.00, +1.00] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_failure | 46.25 | -1.75 | [-4.01, +1.25] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_failure | 46.25 | -1.75 | [-4.75, +1.25] |
| `prefix_handunc_kfull` | full | 38.2 | by_gain | 45.25 | -1.75 | [-4.50, +1.00] |
| `prefix_handunc_k50` | 50 | 20.2 | by_failure | 46.25 | -1.75 | [-4.75, +1.50] |
| `prefix_emb_kfull` | full | 38.2 | by_failure | 46.25 | -1.75 | [-4.26, +1.75] |
| `prefix_emb_k400` | 400 | 37.5 | by_failure | 46.25 | -1.75 | [-4.26, +1.75] |
| `length_only_k200` | 200 | 29.2 | by_failure | 46.25 | -1.75 | [-4.75, +1.26] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_gain | 45.25 | -1.75 | [-3.75, +0.00] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_failure | 46.00 | -2.00 | [-3.75, +0.75] |
| `query+prefix_emb_kfull` | full | 38.2 | by_failure | 46.00 | -2.00 | [-4.50, +1.50] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_failure | 46.00 | -2.00 | [-4.50, +1.50] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_gain | 45.00 | -2.00 | [-4.75, +0.25] |
| `prefix_hand_k400` | 400 | 37.5 | by_failure | 46.00 | -2.00 | [-5.25, +1.00] |
| `length_only_kfull` | full | 38.2 | by_failure | 46.00 | -2.00 | [-4.51, +1.75] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_failure | 45.75 | -2.25 | [-5.00, +0.75] |
| `prefix_unc_k0` | 0 | 0.0 | by_failure | 45.75 | -2.25 | [-4.75, +0.75] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_gain | 44.75 | -2.25 | [-4.50, +0.25] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_gain | 44.75 | -2.25 | [-5.00, +0.00] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_failure | 45.75 | -2.25 | [-4.75, +0.75] |
| `prefix_handunc_kfull` | full | 38.2 | by_failure | 45.75 | -2.25 | [-4.50, +1.50] |
| `prefix_handunc_k100` | 100 | 23.2 | by_failure | 45.75 | -2.25 | [-5.00, +1.00] |
| `prefix_handunc_k0` | 0 | 0.0 | by_failure | 45.75 | -2.25 | [-4.75, +0.75] |
| `prefix_hand_kfull` | full | 38.2 | by_gain | 44.75 | -2.25 | [-5.00, +0.50] |
| `prefix_hand_k0` | 0 | 0.0 | by_failure | 45.75 | -2.25 | [-4.75, +0.75] |
| `prefix_emb_k200` | 200 | 29.2 | by_failure | 45.75 | -2.25 | [-5.00, +1.00] |
| `prefix_emb_k0` | 0 | 0.0 | by_failure | 45.75 | -2.25 | [-5.00, +0.50] |
| `length_only_k50` | 50 | 20.2 | by_failure | 45.75 | -2.25 | [-4.75, +0.75] |
| `length_only_k25` | 25 | 18.7 | by_failure | 45.75 | -2.25 | [-4.75, +0.75] |
| `length_only_k0` | 0 | 0.0 | by_failure | 45.75 | -2.25 | [-4.75, +0.75] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_gain | 44.50 | -2.50 | [-5.50, +0.00] |
| `prefix_unc_k400` | 400 | 37.5 | by_failure | 45.50 | -2.50 | [-6.00, +1.00] |
| `prefix_handunc_k200` | 200 | 29.2 | by_failure | 45.50 | -2.50 | [-5.50, +0.50] |
| `prefix_handunc_k200` | 200 | 29.2 | by_gain | 44.25 | -2.75 | [-5.75, +0.01] |
| `prefix_emb_k100` | 100 | 23.2 | by_gain | 44.25 | -2.75 | [-5.50, +0.00] |
| `prefix_emb_k100` | 100 | 23.2 | by_failure | 45.25 | -2.75 | [-5.50, +0.25] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_gain | 44.00 | -3.00 | [-5.76, -0.25] |
| `prefix_handunc_k400` | 400 | 37.5 | by_failure | 45.00 | -3.00 | [-6.25, +0.00] |
| `prefix_hand_k100` | 100 | 23.2 | by_failure | 45.00 | -3.00 | [-5.75, +0.00] |
| `prefix_emb_k25` | 25 | 18.7 | by_gain | 44.00 | -3.00 | [-5.75, +0.00] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_gain | 43.75 | -3.25 | [-6.00, -0.50] |
| `prefix_handunc_k100` | 100 | 23.2 | by_gain | 43.75 | -3.25 | [-6.00, +0.00] |
| `prefix_hand_k25` | 25 | 18.7 | by_gain | 43.75 | -3.25 | [-6.25, -0.25] |
| `prefix_emb_k200` | 200 | 29.2 | by_gain | 43.75 | -3.25 | [-5.75, +0.00] |
| `length_only_k400` | 400 | 37.5 | by_gain | 43.75 | -3.25 | [-6.25, -0.75] |
| `length_only_k200` | 200 | 29.2 | by_gain | 43.75 | -3.25 | [-5.75, -0.25] |
| `prefix_handunc_k400` | 400 | 37.5 | by_gain | 43.50 | -3.50 | [-6.50, -1.25] |
| `prefix_hand_k200` | 200 | 29.2 | by_failure | 44.50 | -3.50 | [-6.00, +0.00] |
| `prefix_hand_k100` | 100 | 23.2 | by_gain | 43.50 | -3.50 | [-6.50, -0.75] |
| `prefix_unc_k0` | 0 | 0.0 | by_gain | 43.25 | -3.75 | [-6.50, -1.00] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_gain | 43.25 | -3.75 | [-6.50, -1.00] |
| `prefix_handunc_k0` | 0 | 0.0 | by_gain | 43.25 | -3.75 | [-6.50, -1.00] |
| `prefix_hand_k0` | 0 | 0.0 | by_gain | 43.25 | -3.75 | [-6.50, -1.00] |
| `length_only_k50` | 50 | 20.2 | by_gain | 43.25 | -3.75 | [-6.50, -1.00] |
| `length_only_k25` | 25 | 18.7 | by_gain | 43.25 | -3.75 | [-6.50, -1.00] |
| `length_only_k100` | 100 | 23.2 | by_gain | 43.25 | -3.75 | [-6.25, -0.99] |
| `length_only_k0` | 0 | 0.0 | by_gain | 43.25 | -3.75 | [-6.50, -1.00] |
| `prefix_hand_k200` | 200 | 29.2 | by_gain | 43.00 | -4.00 | [-7.50, -1.24] |
| `prefix_handunc_k25` | 25 | 18.7 | by_failure | 43.75 | -4.25 | [-6.75, -1.25] |
| `prefix_emb_k0` | 0 | 0.0 | by_gain | 42.75 | -4.25 | [-6.75, -1.00] |
| `length_only_k400` | 400 | 37.5 | by_failure | 43.25 | -4.75 | [-7.50, -1.75] |
| `prefix_unc_k25` | 25 | 18.7 | by_failure | 42.00 | -6.00 | [-8.50, -2.75] |
| `prefix_hand_k400` | 400 | 37.5 | by_gain | 40.75 | -6.25 | [-9.25, -3.00] |

### Best router at each budget e (by_gain)

| e | best router | k | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|
| 0.1 | `query+prefix_unc_k50` | 50 | 47.25 | +0.75 | [-0.75, +2.00] |
| 0.2 | `query+prefix_unc_k400` | 400 | 48.25 | +1.25 | [-1.00, +2.50] |
| 0.3 | `query+prefix_unc_k50` | 50 | 48.75 | +2.00 | [-0.75, +4.50] |
| 0.5 | `prefix_unc_k400` | 400 | 49.00 | +4.75 | [+0.75, +8.25] |
| 1.0 | `query_only` | None | 46.75 | +0.00 | [+0.00, +0.00] |

## Mechanism Step 2 — feature audit (CONSTANT entries are stopping flags)

| k | features CONSTANT across questions |
|---|---|
| 0 | 45: hesitation_wait, hesitation_but, hesitation_total, n_letter_mentions, n_letter_changes, letter_appears, rep3_total, rep3_max, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, n_prefix_chars, unc_mean, unc_sd, unc_max, unc_min, unc_last, unc_sum, unc_slope, unc_mean_firsthalf, unc_mean_secondhalf, unc_n, unc_frac_gt_0.1, unc_frac_gt_0.5, unc_frac_gt_1.0, unc_frac_gt_2.0 |
| 25 | 25: n_letter_changes, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, unc_min, unc_n |
| 50 | 17: repsent_total, repsent_max, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 100 | 15: repsent_total, repsent_max, phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 200 | 12: phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 400 | 12: phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| full | 12: phrase::cannot see, phrase::not shown, phrase::before the clip, phrase::before the video, phrase::don't see, phrase::do not see, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine, trace_closed_by_k, unc_min |

## Mechanism Step 3 — one traced unit

Question `2` (group `2`), device WRONG, cloud correct, gain 1.

| k | prefix tokens | non-zero features | predicted gain | rank | escalated at e=0.2 |
|---|---|---|---|---|---|
| 0 | 0 | trace_closed_by_k=1 | +0.02122 | 196/400 | no |
| 25 | 25 | rep3_max=1, repsent_max=1, n_prefix_tokens=25, n_prefix_chars=99 | +0.04598 | 166/400 | no |
| 50 | 50 | hesitation_wait=1, hesitation_total=1, rep3_max=1, repsent_max=1, n_prefix_tokens=50, n_prefix_chars=195 | +0.00218 | 216/400 | no |
| 100 | 100 | hesitation_wait=5, hesitation_total=5, rep3_total=4, rep3_max=3, repsent_max=1, n_prefix_tokens=100 | +0.02168 | 206/400 | no |
| 200 | 200 | hesitation_wait=7, hesitation_but=1, hesitation_total=8, rep3_total=21, rep3_max=5, repsent_max=1 | -0.00792 | 221/400 | no |
| 400 | 400 | hesitation_wait=12, hesitation_but=2, hesitation_total=14, rep3_total=75, rep3_max=7, repsent_max=1 | -0.01832 | 234/400 | no |

