# StudyR8a — generated tables

From `results/escalation/study_r8a/study_r8a_results_v2s2.json`. Every value computed; none typed.

## Gate

**PARTIAL REASONING ADDS VALUE**

| workload | best query+prefix router, k <= 100 | rank | k | acc @ e=0.2 | delta vs query-only | 95% CI | >= 2 pp and CI excludes 0 |
|---|---|---|---|---|---|---|---|
| sember | `query+prefix_hand_k100` | by_gain | 100 | 35.50% | +2.13 pp | [+0.23, +3.35] | YES |
| erqa | `query+prefix_emb_k50` | by_gain | 50 | 47.25% | +1.00 pp | [-2.25, +3.75] | no |


# SEMBER  (n = 845)

Device 32.07% · cloud 39.53% · gain counts {'-1': 97, '0': 588, '1': 160} · 5 folds

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
| `query+prefix_unc_kfull` | full | 38.2 | 0.6530 | [0.6122, 0.6938] | +0.0299 | [+0.0014, +0.0576] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.6529 | [0.6154, 0.6913] | +0.0298 | [-0.0004, +0.0594] |
| `query+prefix_unc_k200` | 200 | 29.2 | 0.6522 | [0.6098, 0.6927] | +0.0291 | [+0.0001, +0.0561] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.6492 | [0.6101, 0.6888] | +0.0261 | [+0.0099, +0.0423] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.6477 | [0.6059, 0.6929] | +0.0246 | [-0.0114, +0.0623] |
| `query+prefix_handunc_k400` | 400 | 37.5 | 0.6450 | [0.6028, 0.6858] | +0.0219 | [-0.0114, +0.0539] |
| `query+prefix_handunc_kfull` | full | 38.2 | 0.6429 | [0.6014, 0.6842] | +0.0198 | [-0.0114, +0.0489] |
| `query+prefix_unc_k400` | 400 | 37.5 | 0.6416 | [0.5994, 0.6829] | +0.0185 | [-0.0108, +0.0464] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.6416 | [0.6041, 0.6791] | +0.0185 | [-0.0029, +0.0410] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.6413 | [0.6026, 0.6803] | +0.0182 | [+0.0037, +0.0328] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.6401 | [0.6015, 0.6786] | +0.0170 | [+0.0036, +0.0305] |
| `prefix_hand_k400` | 400 | 37.5 | 0.6395 | [0.5965, 0.6825] | +0.0164 | [-0.0345, +0.0675] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.6376 | [0.5998, 0.6774] | +0.0145 | [-0.0010, +0.0295] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.6361 | [0.5965, 0.6767] | +0.0130 | [-0.0071, +0.0329] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.6347 | [0.5940, 0.6788] | +0.0116 | [-0.0254, +0.0493] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.6340 | [0.5933, 0.6742] | +0.0109 | [+0.0010, +0.0215] |
| `query+prefix_unc_k100` | 100 | 23.2 | 0.6332 | [0.5907, 0.6730] | +0.0101 | [-0.0148, +0.0343] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.6331 | [0.5935, 0.6731] | +0.0100 | [+0.0013, +0.0193] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.6326 | [0.5899, 0.6726] | +0.0095 | [-0.0151, +0.0338] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.6323 | [0.5924, 0.6716] | +0.0092 | [-0.0024, +0.0213] |
| `query+prefix_handunc_k100` | 100 | 23.2 | 0.6309 | [0.5861, 0.6734] | +0.0078 | [-0.0224, +0.0362] |
| `query+prefix_handunc_k200` | 200 | 29.2 | 0.6302 | [0.5865, 0.6720] | +0.0071 | [-0.0266, +0.0385] |
| `query+prefix_handunc_k50` | 50 | 20.2 | 0.6296 | [0.5909, 0.6693] | +0.0065 | [-0.0214, +0.0329] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.6282 | [0.5860, 0.6718] | +0.0051 | [-0.0313, +0.0414] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.6278 | [0.5871, 0.6685] | +0.0047 | [-0.0272, +0.0336] |
| `query+prefix_unc_k50` | 50 | 20.2 | 0.6244 | [0.5879, 0.6633] | +0.0012 | [-0.0206, +0.0222] |
| `query_only` | None | 0.0 | 0.6231 | [0.5844, 0.6618] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.6231 | [0.5844, 0.6618] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.6231 | [0.5844, 0.6618] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_unc_k0` | 0 | 0.0 | 0.6231 | [0.5844, 0.6618] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_handunc_k0` | 0 | 0.0 | 0.6231 | [0.5844, 0.6618] | +0.0000 | [+0.0000, +0.0000] |
| `length_only_kfull` | full | 38.2 | 0.6210 | [0.5816, 0.6623] | -0.0021 | [-0.0510, +0.0468] |
| `prefix_hand_kfull` | full | 38.2 | 0.6204 | [0.5807, 0.6603] | -0.0027 | [-0.0496, +0.0442] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.6186 | [0.5801, 0.6568] | -0.0045 | [-0.0086, -0.0006] |
| `prefix_handunc_k400` | 400 | 37.5 | 0.6170 | [0.5703, 0.6606] | -0.0061 | [-0.0588, +0.0463] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.6167 | [0.5745, 0.6604] | -0.0064 | [-0.0466, +0.0360] |
| `query+prefix_handunc_k25` | 25 | 18.7 | 0.6162 | [0.5784, 0.6569] | -0.0069 | [-0.0282, +0.0142] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.6123 | [0.5695, 0.6565] | -0.0109 | [-0.0491, +0.0269] |
| `length_only_k400` | 400 | 37.5 | 0.6109 | [0.5696, 0.6529] | -0.0122 | [-0.0636, +0.0380] |
| `prefix_unc_k200` | 200 | 29.2 | 0.6107 | [0.5644, 0.6555] | -0.0124 | [-0.0632, +0.0335] |
| `prefix_handunc_kfull` | full | 38.2 | 0.6088 | [0.5623, 0.6526] | -0.0143 | [-0.0643, +0.0354] |
| `length_only_k200` | 200 | 29.2 | 0.6028 | [0.5600, 0.6455] | -0.0203 | [-0.0714, +0.0295] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.6020 | [0.5634, 0.6410] | -0.0212 | [-0.0384, -0.0046] |
| `query+prefix_unc_k25` | 25 | 18.7 | 0.6007 | [0.5618, 0.6398] | -0.0224 | [-0.0364, -0.0087] |
| `prefix_unc_kfull` | full | 38.2 | 0.5995 | [0.5544, 0.6430] | -0.0236 | [-0.0761, +0.0273] |
| `prefix_hand_k100` | 100 | 23.2 | 0.5990 | [0.5535, 0.6406] | -0.0241 | [-0.0700, +0.0205] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.5970 | [0.5516, 0.6425] | -0.0261 | [-0.0675, +0.0192] |
| `prefix_handunc_k50` | 50 | 20.2 | 0.5966 | [0.5552, 0.6348] | -0.0265 | [-0.0777, +0.0232] |
| `prefix_handunc_k200` | 200 | 29.2 | 0.5945 | [0.5469, 0.6409] | -0.0286 | [-0.0829, +0.0202] |
| `prefix_handunc_k100` | 100 | 23.2 | 0.5925 | [0.5451, 0.6358] | -0.0306 | [-0.0791, +0.0151] |
| `prefix_hand_k200` | 200 | 29.2 | 0.5920 | [0.5437, 0.6363] | -0.0311 | [-0.0844, +0.0190] |
| `prefix_unc_k400` | 400 | 37.5 | 0.5819 | [0.5361, 0.6271] | -0.0412 | [-0.0947, +0.0111] |
| `prefix_unc_k50` | 50 | 20.2 | 0.5811 | [0.5431, 0.6187] | -0.0420 | [-0.0937, +0.0052] |
| `prefix_unc_k100` | 100 | 23.2 | 0.5802 | [0.5340, 0.6255] | -0.0429 | [-0.0958, +0.0070] |
| `prefix_hand_k50` | 50 | 20.2 | 0.5781 | [0.5369, 0.6182] | -0.0450 | [-0.0925, +0.0040] |
| `length_only_k100` | 100 | 23.2 | 0.5624 | [0.5201, 0.6025] | -0.0608 | [-0.1130, -0.0120] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5529 | [0.5081, 0.5985] | -0.0702 | [-0.1251, -0.0136] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.5393 | [0.4952, 0.5825] | -0.0838 | [-0.1326, -0.0379] |
| `prefix_emb_k25` | 25 | 18.7 | 0.5327 | [0.4897, 0.5764] | -0.0904 | [-0.1425, -0.0399] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.5301 | [0.4886, 0.5720] | -0.0930 | [-0.1388, -0.0462] |
| `prefix_emb_k400` | 400 | 37.5 | 0.5300 | [0.4848, 0.5762] | -0.0931 | [-0.1428, -0.0428] |
| `prefix_emb_kfull` | full | 38.2 | 0.5300 | [0.4848, 0.5762] | -0.0931 | [-0.1428, -0.0428] |
| `prefix_emb_k200` | 200 | 29.2 | 0.5282 | [0.4857, 0.5695] | -0.0949 | [-0.1460, -0.0459] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.5257 | [0.4824, 0.5667] | -0.0975 | [-0.1454, -0.0505] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.5249 | [0.4785, 0.5697] | -0.0982 | [-0.1452, -0.0509] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.5249 | [0.4785, 0.5697] | -0.0982 | [-0.1452, -0.0509] |
| `prefix_emb_k50` | 50 | 20.2 | 0.5092 | [0.4671, 0.5534] | -0.1139 | [-0.1630, -0.0643] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.4953 | [0.4513, 0.5373] | -0.1278 | [-0.1772, -0.0803] |
| `prefix_handunc_k25` | 25 | 18.7 | 0.4943 | [0.4501, 0.5389] | -0.1288 | [-0.1891, -0.0703] |
| `length_only_k50` | 50 | 20.2 | 0.4910 | [0.4485, 0.5337] | -0.1321 | [-0.1826, -0.0828] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4804 | [0.4349, 0.5246] | -0.1427 | [-0.1970, -0.0911] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4750 | [0.4322, 0.5187] | -0.1481 | [-0.2017, -0.0959] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4750 | [0.4322, 0.5187] | -0.1481 | [-0.2017, -0.0959] |
| `prefix_unc_k0` | 0 | 0.0 | 0.4750 | [0.4322, 0.5187] | -0.1481 | [-0.2017, -0.0959] |
| `prefix_handunc_k0` | 0 | 0.0 | 0.4750 | [0.4322, 0.5187] | -0.1481 | [-0.2017, -0.0959] |
| `length_only_k0` | 0 | 0.0 | 0.4750 | [0.4322, 0.5187] | -0.1481 | [-0.2017, -0.0959] |
| `length_only_k25` | 25 | 18.7 | 0.4750 | [0.4322, 0.5187] | -0.1481 | [-0.2017, -0.0959] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4468 | [0.4085, 0.4854] | -0.1764 | [-0.2265, -0.1266] |
| `prefix_unc_k25` | 25 | 18.7 | 0.4429 | [0.4013, 0.4855] | -0.1802 | [-0.2392, -0.1233] |

## Part 1 — held-out AUROC for `evidence_outside_window`

| router | k | latency s | AUROC | 95% CI | delta vs query-only | paired 95% CI |
|---|---|---|---|---|---|---|
| `prefix_tfidf_k50` | 50 | 20.2 | 0.5765 | [0.5162, 0.6348] | +0.0678 | [-0.0026, +0.1409] |
| `prefix_hand_k50` | 50 | 20.2 | 0.5757 | [0.5200, 0.6336] | +0.0670 | [-0.0066, +0.1448] |
| `prefix_handunc_k50` | 50 | 20.2 | 0.5740 | [0.5183, 0.6342] | +0.0653 | [-0.0093, +0.1452] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.5673 | [0.5042, 0.6312] | +0.0586 | [-0.0048, +0.1242] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.5664 | [0.5043, 0.6266] | +0.0577 | [-0.0097, +0.1288] |
| `query+prefix_handunc_k200` | 200 | 29.2 | 0.5595 | [0.4882, 0.6276] | +0.0508 | [-0.0006, +0.1023] |
| `query+prefix_handunc_k50` | 50 | 20.2 | 0.5587 | [0.5004, 0.6156] | +0.0501 | [+0.0074, +0.0941] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.5504 | [0.4782, 0.6192] | +0.0417 | [-0.0094, +0.0935] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.5483 | [0.4846, 0.6090] | +0.0397 | [-0.0265, +0.1066] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.5482 | [0.4909, 0.6066] | +0.0395 | [+0.0095, +0.0708] |
| `query+prefix_unc_k200` | 200 | 29.2 | 0.5474 | [0.4825, 0.6141] | +0.0388 | [-0.0055, +0.0843] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.5459 | [0.4798, 0.6093] | +0.0372 | [+0.0039, +0.0758] |
| `prefix_unc_k50` | 50 | 20.2 | 0.5420 | [0.4849, 0.6003] | +0.0333 | [-0.0426, +0.1141] |
| `query+prefix_handunc_kfull` | full | 38.2 | 0.5414 | [0.4828, 0.5995] | +0.0327 | [-0.0176, +0.0882] |
| `prefix_tfidf_kfull` | full | 38.2 | 0.5413 | [0.4795, 0.6018] | +0.0326 | [-0.0365, +0.1057] |
| `query+prefix_unc_k50` | 50 | 20.2 | 0.5386 | [0.4786, 0.5981] | +0.0299 | [-0.0041, +0.0638] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.5375 | [0.4721, 0.6002] | +0.0288 | [-0.0004, +0.0587] |
| `query+prefix_handunc_k400` | 400 | 37.5 | 0.5375 | [0.4740, 0.6012] | +0.0288 | [-0.0222, +0.0785] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.5371 | [0.4734, 0.5990] | +0.0284 | [+0.0017, +0.0547] |
| `query+prefix_unc_k400` | 400 | 37.5 | 0.5339 | [0.4704, 0.5982] | +0.0252 | [-0.0155, +0.0683] |
| `query+prefix_handunc_k100` | 100 | 23.2 | 0.5338 | [0.4726, 0.5992] | +0.0251 | [-0.0197, +0.0723] |
| `query+prefix_unc_kfull` | full | 38.2 | 0.5310 | [0.4723, 0.5906] | +0.0223 | [-0.0195, +0.0691] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.5308 | [0.4651, 0.5949] | +0.0221 | [-0.0260, +0.0746] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.5300 | [0.4665, 0.5924] | +0.0213 | [-0.0001, +0.0409] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.5299 | [0.4686, 0.5900] | +0.0212 | [+0.0050, +0.0371] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.5293 | [0.4753, 0.5841] | +0.0206 | [-0.0482, +0.0913] |
| `query+prefix_unc_k100` | 100 | 23.2 | 0.5273 | [0.4654, 0.5902] | +0.0186 | [-0.0194, +0.0568] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.5270 | [0.4622, 0.5912] | +0.0183 | [-0.0230, +0.0626] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.5266 | [0.4633, 0.5858] | +0.0179 | [-0.0266, +0.0688] |
| `query+prefix_handunc_k25` | 25 | 18.7 | 0.5251 | [0.4643, 0.5834] | +0.0164 | [-0.0218, +0.0552] |
| `prefix_handunc_k200` | 200 | 29.2 | 0.5249 | [0.4541, 0.5893] | +0.0162 | [-0.0663, +0.0955] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5232 | [0.4595, 0.5868] | +0.0145 | [-0.0788, +0.1096] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.5221 | [0.4577, 0.5802] | +0.0134 | [-0.0208, +0.0492] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.5189 | [0.4560, 0.5794] | +0.0102 | [-0.0036, +0.0232] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.5169 | [0.4611, 0.5724] | +0.0082 | [-0.0610, +0.0748] |
| `prefix_emb_k50` | 50 | 20.2 | 0.5144 | [0.4566, 0.5702] | +0.0057 | [-0.0768, +0.0869] |
| `query+prefix_unc_k25` | 25 | 18.7 | 0.5111 | [0.4523, 0.5729] | +0.0024 | [-0.0188, +0.0245] |
| `query_only` | None | 0.0 | 0.5087 | [0.4464, 0.5705] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.5087 | [0.4464, 0.5705] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.5087 | [0.4464, 0.5705] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_unc_k0` | 0 | 0.0 | 0.5087 | [0.4464, 0.5705] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_handunc_k0` | 0 | 0.0 | 0.5087 | [0.4464, 0.5705] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.5084 | [0.4467, 0.5710] | -0.0002 | [-0.0055, +0.0045] |
| `prefix_hand_k200` | 200 | 29.2 | 0.5073 | [0.4340, 0.5767] | -0.0014 | [-0.0835, +0.0795] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.4974 | [0.4350, 0.5596] | -0.0113 | [-0.0335, +0.0112] |
| `prefix_handunc_k25` | 25 | 18.7 | 0.4933 | [0.4307, 0.5576] | -0.0153 | [-0.1110, +0.0822] |
| `prefix_handunc_k100` | 100 | 23.2 | 0.4885 | [0.4273, 0.5520] | -0.0201 | [-0.0961, +0.0628] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.4875 | [0.4255, 0.5491] | -0.0212 | [-0.0829, +0.0405] |
| `prefix_unc_k100` | 100 | 23.2 | 0.4874 | [0.4228, 0.5539] | -0.0213 | [-0.1054, +0.0599] |
| `prefix_emb_k25` | 25 | 18.7 | 0.4870 | [0.4259, 0.5487] | -0.0217 | [-0.0920, +0.0435] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.4837 | [0.4232, 0.5447] | -0.0250 | [-0.0928, +0.0447] |
| `prefix_handunc_k400` | 400 | 37.5 | 0.4836 | [0.4204, 0.5472] | -0.0251 | [-0.1055, +0.0548] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.4832 | [0.4188, 0.5506] | -0.0255 | [-0.0970, +0.0532] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.4832 | [0.4188, 0.5506] | -0.0255 | [-0.0970, +0.0532] |
| `prefix_unc_k200` | 200 | 29.2 | 0.4761 | [0.4083, 0.5437] | -0.0326 | [-0.1187, +0.0545] |
| `prefix_hand_k100` | 100 | 23.2 | 0.4739 | [0.4132, 0.5371] | -0.0348 | [-0.1119, +0.0471] |
| `prefix_unc_k25` | 25 | 18.7 | 0.4710 | [0.4090, 0.5329] | -0.0377 | [-0.1305, +0.0559] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.4686 | [0.4127, 0.5284] | -0.0401 | [-0.1082, +0.0285] |
| `prefix_hand_k400` | 400 | 37.5 | 0.4682 | [0.4021, 0.5350] | -0.0405 | [-0.1199, +0.0414] |
| `length_only_k50` | 50 | 20.2 | 0.4669 | [0.3961, 0.5334] | -0.0417 | [-0.1363, +0.0518] |
| `prefix_emb_k400` | 400 | 37.5 | 0.4660 | [0.4022, 0.5304] | -0.0427 | [-0.1179, +0.0394] |
| `prefix_emb_kfull` | full | 38.2 | 0.4660 | [0.4022, 0.5304] | -0.0427 | [-0.1179, +0.0394] |
| `length_only_k100` | 100 | 23.2 | 0.4637 | [0.3933, 0.5328] | -0.0450 | [-0.1310, +0.0437] |
| `prefix_emb_k200` | 200 | 29.2 | 0.4595 | [0.4024, 0.5176] | -0.0492 | [-0.1220, +0.0241] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4587 | [0.3879, 0.5261] | -0.0499 | [-0.1447, +0.0428] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4587 | [0.3879, 0.5261] | -0.0499 | [-0.1447, +0.0428] |
| `prefix_unc_k0` | 0 | 0.0 | 0.4587 | [0.3879, 0.5261] | -0.0499 | [-0.1447, +0.0428] |
| `prefix_handunc_k0` | 0 | 0.0 | 0.4587 | [0.3879, 0.5261] | -0.0499 | [-0.1447, +0.0428] |
| `length_only_k0` | 0 | 0.0 | 0.4587 | [0.3879, 0.5261] | -0.0499 | [-0.1447, +0.0428] |
| `length_only_k25` | 25 | 18.7 | 0.4587 | [0.3879, 0.5261] | -0.0499 | [-0.1447, +0.0428] |
| `prefix_unc_kfull` | full | 38.2 | 0.4529 | [0.3886, 0.5173] | -0.0558 | [-0.1449, +0.0353] |
| `length_only_k200` | 200 | 29.2 | 0.4518 | [0.3779, 0.5250] | -0.0569 | [-0.1423, +0.0293] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4475 | [0.3924, 0.5050] | -0.0612 | [-0.1371, +0.0181] |
| `prefix_handunc_kfull` | full | 38.2 | 0.4474 | [0.3875, 0.5070] | -0.0613 | [-0.1502, +0.0289] |
| `length_only_k400` | 400 | 37.5 | 0.4402 | [0.3660, 0.5151] | -0.0684 | [-0.1550, +0.0208] |
| `prefix_unc_k400` | 400 | 37.5 | 0.4394 | [0.3749, 0.5041] | -0.0692 | [-0.1549, +0.0171] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4369 | [0.3710, 0.4993] | -0.0718 | [-0.1647, +0.0193] |
| `prefix_hand_kfull` | full | 38.2 | 0.4140 | [0.3481, 0.4784] | -0.0947 | [-0.1810, -0.0031] |
| `length_only_kfull` | full | 38.2 | 0.3940 | [0.3270, 0.4600] | -0.1146 | [-0.2018, -0.0178] |

## Part 2 — escalation utility

| e | random | perfect oracle | always-local | always-cloud |
|---|---|---|---|---|
| 0.1 | 32.85 | 42.01 | 32.07 | 39.53 |
| 0.2 | 33.59 | 51.01 | 32.07 | 39.53 |
| 0.3 | 34.40 | 51.01 | 32.07 | 39.53 |
| 0.5 | 35.94 | 51.01 | 32.07 | 39.53 |
| 1.0 | 39.53 | 39.53 | 32.07 | 39.53 |

### At e = 0.2, every router, both rankings

| router | k | latency s | rank | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|---|
| `length_only_kfull` | full | 38.2 | by_failure | 35.74 | +3.90 | [+1.52, +5.76] |
| `prefix_hand_kfull` | full | 38.2 | by_failure | 35.50 | +3.67 | [+1.43, +5.56] |
| `prefix_handunc_kfull` | full | 38.2 | by_failure | 34.91 | +3.08 | [+0.81, +4.87] |
| `prefix_hand_k400` | 400 | 37.5 | by_failure | 34.91 | +3.08 | [+0.94, +5.08] |
| `prefix_unc_kfull` | full | 38.2 | by_failure | 34.79 | +2.96 | [+0.95, +5.10] |
| `prefix_handunc_k400` | 400 | 37.5 | by_failure | 34.44 | +2.60 | [+0.47, +4.68] |
| `length_only_k100` | 100 | 23.2 | by_failure | 34.44 | +2.60 | [+0.47, +4.61] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_gain | 35.86 | +2.48 | [+0.34, +4.21] |
| `length_only_k200` | 200 | 29.2 | by_failure | 34.32 | +2.48 | [+0.37, +4.52] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_failure | 34.20 | +2.37 | [+0.71, +3.89] |
| `prefix_tfidf_kfull` | full | 38.2 | by_failure | 34.20 | +2.37 | [+0.35, +3.72] |
| `length_only_k400` | 400 | 37.5 | by_failure | 34.20 | +2.37 | [+0.35, +4.62] |
| `query+prefix_unc_kfull` | full | 38.2 | by_failure | 34.08 | +2.25 | [+0.85, +3.44] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_failure | 34.08 | +2.25 | [+0.80, +3.56] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_failure | 34.08 | +2.25 | [+0.71, +3.76] |
| `prefix_unc_k0` | 0 | 0.0 | by_failure | 34.08 | +2.25 | [+0.00, +3.95] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_failure | 34.08 | +2.25 | [+0.00, +3.95] |
| `prefix_handunc_k0` | 0 | 0.0 | by_failure | 34.08 | +2.25 | [+0.00, +3.95] |
| `prefix_hand_k0` | 0 | 0.0 | by_failure | 34.08 | +2.25 | [+0.00, +3.95] |
| `length_only_k50` | 50 | 20.2 | by_failure | 34.08 | +2.25 | [+0.12, +4.02] |
| `length_only_k25` | 25 | 18.7 | by_failure | 34.08 | +2.25 | [+0.00, +3.95] |
| `length_only_k0` | 0 | 0.0 | by_failure | 34.08 | +2.25 | [+0.00, +3.95] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_gain | 35.50 | +2.13 | [+0.23, +3.35] |
| `prefix_hand_k50` | 50 | 20.2 | by_failure | 33.96 | +2.13 | [-0.35, +4.04] |
| `prefix_hand_k25` | 25 | 18.7 | by_failure | 33.96 | +2.13 | [-0.35, +4.25] |
| `prefix_tfidf_kfull` | full | 38.2 | by_gain | 35.38 | +2.01 | [-0.12, +4.00] |
| `prefix_hand_k200` | 200 | 29.2 | by_failure | 33.85 | +2.01 | [-0.24, +3.95] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_failure | 33.73 | +1.89 | [+0.49, +3.16] |
| `prefix_unc_k50` | 50 | 20.2 | by_failure | 33.73 | +1.89 | [-0.12, +3.73] |
| `prefix_hand_k100` | 100 | 23.2 | by_failure | 33.73 | +1.89 | [-0.24, +3.56] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_gain | 35.15 | +1.77 | [+0.00, +3.08] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_gain | 35.15 | +1.77 | [-0.12, +3.49] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_failure | 33.61 | +1.77 | [+0.00, +3.34] |
| `length_only_kfull` | full | 38.2 | by_gain | 35.15 | +1.77 | [-0.59, +3.95] |
| `prefix_handunc_k25` | 25 | 18.7 | by_failure | 33.49 | +1.66 | [-0.60, +3.56] |
| `query+prefix_unc_kfull` | full | 38.2 | by_gain | 34.91 | +1.54 | [+0.12, +3.07] |
| `query+prefix_unc_k400` | 400 | 37.5 | by_gain | 34.91 | +1.54 | [-0.23, +3.13] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_gain | 34.91 | +1.54 | [-0.12, +2.80] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_gain | 34.91 | +1.54 | [-0.24, +2.86] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_failure | 33.37 | +1.54 | [-0.12, +2.77] |
| `query+prefix_hand_kfull` | full | 38.2 | by_gain | 34.91 | +1.54 | [-0.23, +2.85] |
| `query+prefix_hand_kfull` | full | 38.2 | by_failure | 33.37 | +1.54 | [+0.12, +2.85] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_failure | 33.37 | +1.54 | [+0.00, +2.99] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_failure | 33.37 | +1.54 | [-0.24, +2.89] |
| `prefix_handunc_k200` | 200 | 29.2 | by_failure | 33.37 | +1.54 | [-0.35, +3.53] |
| `prefix_hand_k400` | 400 | 37.5 | by_gain | 34.91 | +1.54 | [-0.72, +3.72] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_gain | 34.79 | +1.42 | [-0.46, +2.96] |
| `prefix_unc_k25` | 25 | 18.7 | by_failure | 33.25 | +1.42 | [-0.87, +3.59] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_gain | 34.79 | +1.42 | [-0.59, +3.35] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_failure | 33.25 | +1.42 | [-0.46, +2.96] |
| `prefix_emb_k0` | 0 | 0.0 | by_failure | 33.25 | +1.42 | [-0.58, +3.74] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_failure | 33.14 | +1.30 | [-0.23, +2.47] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_gain | 34.67 | +1.30 | [-0.58, +2.83] |
| `prefix_unc_kfull` | full | 38.2 | by_gain | 34.67 | +1.30 | [-0.96, +3.25] |
| `prefix_unc_k200` | 200 | 29.2 | by_failure | 33.14 | +1.30 | [-0.67, +2.85] |
| `prefix_handunc_k100` | 100 | 23.2 | by_failure | 33.14 | +1.30 | [-0.81, +3.36] |
| `prefix_hand_kfull` | full | 38.2 | by_gain | 34.67 | +1.30 | [-1.06, +3.53] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_gain | 34.56 | +1.18 | [-0.48, +2.57] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_gain | 34.56 | +1.18 | [-0.95, +3.35] |
| `prefix_handunc_k50` | 50 | 20.2 | by_failure | 33.02 | +1.18 | [-1.06, +2.95] |
| `prefix_hand_k200` | 200 | 29.2 | by_gain | 34.56 | +1.18 | [-1.15, +3.02] |
| `prefix_emb_k50` | 50 | 20.2 | by_failure | 33.02 | +1.18 | [-0.95, +3.07] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_gain | 34.44 | +1.06 | [-0.94, +2.90] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_gain | 34.44 | +1.06 | [-0.83, +2.55] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_failure | 32.90 | +1.06 | [-0.36, +2.11] |
| `prefix_unc_k400` | 400 | 37.5 | by_failure | 32.90 | +1.06 | [-1.17, +3.08] |
| `prefix_emb_kfull` | full | 38.2 | by_failure | 32.90 | +1.06 | [-1.14, +2.95] |
| `prefix_emb_k400` | 400 | 37.5 | by_failure | 32.90 | +1.06 | [-1.14, +2.95] |
| `prefix_emb_k200` | 200 | 29.2 | by_failure | 32.90 | +1.06 | [-1.19, +2.80] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_failure | 32.78 | +0.95 | [-0.47, +1.77] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_failure | 32.78 | +0.95 | [-1.06, +2.79] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_gain | 34.32 | +0.95 | [-1.18, +2.73] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_gain | 34.32 | +0.95 | [-1.30, +2.73] |
| `prefix_handunc_k400` | 400 | 37.5 | by_gain | 34.32 | +0.95 | [-1.21, +3.23] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_gain | 34.20 | +0.83 | [-0.81, +2.14] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_gain | 34.20 | +0.83 | [-0.83, +2.71] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_failure | 32.66 | +0.83 | [+0.00, +1.56] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_gain | 34.20 | +0.83 | [-1.20, +2.88] |
| `prefix_handunc_k200` | 200 | 29.2 | by_gain | 34.20 | +0.83 | [-1.28, +2.67] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_failure | 32.54 | +0.71 | [-0.59, +1.81] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_gain | 34.08 | +0.71 | [-0.95, +1.95] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_gain | 34.08 | +0.71 | [-1.06, +1.76] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_failure | 32.54 | +0.71 | [-0.36, +1.44] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_gain | 34.08 | +0.71 | [-0.35, +1.47] |
| `prefix_unc_k100` | 100 | 23.2 | by_failure | 32.54 | +0.71 | [-1.54, +2.41] |
| `prefix_handunc_k50` | 50 | 20.2 | by_gain | 34.08 | +0.71 | [-1.70, +2.71] |
| `prefix_emb_k25` | 25 | 18.7 | by_failure | 32.54 | +0.71 | [-1.55, +2.74] |
| `query+prefix_unc_k400` | 400 | 37.5 | by_failure | 32.43 | +0.59 | [-0.58, +1.88] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_failure | 32.43 | +0.59 | [-0.73, +1.07] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_gain | 33.96 | +0.59 | [-1.07, +2.13] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_gain | 33.96 | +0.59 | [-0.58, +1.42] |
| `query+prefix_emb_kfull` | full | 38.2 | by_failure | 32.43 | +0.59 | [-1.44, +2.42] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_failure | 32.43 | +0.59 | [-1.44, +2.42] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_failure | 32.43 | +0.59 | [-1.65, +2.47] |
| `prefix_unc_k50` | 50 | 20.2 | by_gain | 33.96 | +0.59 | [-1.53, +2.45] |
| `prefix_emb_k100` | 100 | 23.2 | by_failure | 32.43 | +0.59 | [-1.79, +2.39] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_failure | 32.31 | +0.47 | [-0.98, +1.68] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_failure | 32.31 | +0.47 | [-1.05, +1.64] |
| `prefix_emb_k25` | 25 | 18.7 | by_gain | 33.85 | +0.47 | [-1.55, +2.39] |
| `prefix_emb_k100` | 100 | 23.2 | by_gain | 33.85 | +0.47 | [-1.65, +2.39] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_failure | 32.19 | +0.35 | [-0.82, +1.35] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_failure | 32.19 | +0.35 | [-0.61, +1.40] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_failure | 32.19 | +0.35 | [-0.81, +0.95] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_gain | 33.73 | +0.35 | [-1.61, +2.50] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_failure | 32.19 | +0.35 | [-0.48, +0.48] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_failure | 32.19 | +0.35 | [-1.21, +1.93] |
| `prefix_emb_k50` | 50 | 20.2 | by_gain | 33.73 | +0.35 | [-2.00, +2.31] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_gain | 33.61 | +0.24 | [-1.15, +1.59] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_failure | 32.07 | +0.24 | [-0.71, +0.83] |
| `query+prefix_emb_kfull` | full | 38.2 | by_gain | 33.61 | +0.24 | [-1.75, +2.16] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_gain | 33.61 | +0.24 | [-1.75, +2.16] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_failure | 31.95 | +0.12 | [-1.12, +0.94] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_failure | 31.95 | +0.12 | [-0.82, +1.02] |
| `prefix_hand_k50` | 50 | 20.2 | by_gain | 33.49 | +0.12 | [-2.13, +2.41] |
| `prefix_hand_k25` | 25 | 18.7 | by_gain | 33.49 | +0.12 | [-2.46, +1.78] |
| `prefix_emb_k200` | 200 | 29.2 | by_gain | 33.49 | +0.12 | [-2.02, +2.16] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_failure | 31.95 | +0.12 | [-1.23, +1.15] |
| `query_only` | None | 0.0 | by_gain | 33.37 | +0.00 | [+0.00, +0.00] |
| `query_only` | None | 0.0 | by_failure | 31.83 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_gain | 33.37 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_failure | 31.83 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_gain | 33.37 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_failure | 31.83 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_gain | 33.37 | +0.00 | [-1.38, +1.35] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_gain | 33.37 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_failure | 31.83 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_gain | 33.37 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_failure | 31.83 | +0.00 | [+0.00, +0.00] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_failure | 31.83 | +0.00 | [-1.90, +1.79] |
| `prefix_unc_k400` | 400 | 37.5 | by_gain | 33.37 | +0.00 | [-2.37, +1.97] |
| `prefix_emb_kfull` | full | 38.2 | by_gain | 33.37 | +0.00 | [-2.10, +2.03] |
| `prefix_emb_k400` | 400 | 37.5 | by_gain | 33.37 | +0.00 | [-2.10, +2.03] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_gain | 33.37 | +0.00 | [-1.47, +0.95] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_gain | 33.25 | -0.12 | [-1.63, +0.84] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_failure | 31.72 | -0.12 | [-0.96, +1.07] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_gain | 33.25 | -0.12 | [-2.35, +2.00] |
| `prefix_handunc_kfull` | full | 38.2 | by_gain | 33.25 | -0.12 | [-2.39, +1.91] |
| `prefix_emb_k0` | 0 | 0.0 | by_gain | 33.25 | -0.12 | [-2.21, +2.02] |
| `length_only_k400` | 400 | 37.5 | by_gain | 33.25 | -0.12 | [-2.53, +1.95] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_gain | 33.14 | -0.24 | [-1.34, +1.04] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_gain | 33.14 | -0.24 | [-2.08, +1.91] |
| `prefix_handunc_k25` | 25 | 18.7 | by_gain | 33.14 | -0.24 | [-2.56, +1.78] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_failure | 31.48 | -0.35 | [-2.46, +1.18] |
| `prefix_unc_k200` | 200 | 29.2 | by_gain | 33.02 | -0.35 | [-2.74, +1.31] |
| `prefix_unc_k100` | 100 | 23.2 | by_gain | 32.90 | -0.47 | [-2.84, +1.64] |
| `prefix_unc_k0` | 0 | 0.0 | by_gain | 32.90 | -0.47 | [-2.61, +1.52] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_gain | 32.90 | -0.47 | [-2.61, +1.52] |
| `prefix_handunc_k0` | 0 | 0.0 | by_gain | 32.90 | -0.47 | [-2.61, +1.52] |
| `prefix_hand_k0` | 0 | 0.0 | by_gain | 32.90 | -0.47 | [-2.61, +1.52] |
| `length_only_k25` | 25 | 18.7 | by_gain | 32.90 | -0.47 | [-2.61, +1.52] |
| `length_only_k0` | 0 | 0.0 | by_gain | 32.90 | -0.47 | [-2.61, +1.52] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_gain | 32.78 | -0.59 | [-2.61, +1.61] |
| `length_only_k50` | 50 | 20.2 | by_gain | 32.78 | -0.59 | [-2.71, +1.34] |
| `prefix_unc_k25` | 25 | 18.7 | by_gain | 32.43 | -0.95 | [-3.17, +1.47] |
| `prefix_handunc_k100` | 100 | 23.2 | by_gain | 32.43 | -0.95 | [-3.19, +1.08] |
| `prefix_hand_k100` | 100 | 23.2 | by_gain | 32.43 | -0.95 | [-3.24, +1.19] |
| `length_only_k200` | 200 | 29.2 | by_gain | 32.43 | -0.95 | [-2.82, +1.39] |
| `length_only_k100` | 100 | 23.2 | by_gain | 32.43 | -0.95 | [-2.42, +1.64] |

### Best router at each budget e (by_gain)

| e | best router | k | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|
| 0.1 | `query+prefix_hand_k400` | 400 | 34.67 | +1.42 | [-0.25, +2.74] |
| 0.2 | `query+prefix_tfidf_kfull` | full | 35.86 | +2.48 | [+0.34, +4.21] |
| 0.3 | `prefix_hand_k400` | 400 | 37.16 | +3.31 | [+0.83, +5.84] |
| 0.5 | `prefix_hand_k400` | 400 | 38.58 | +2.84 | [+0.11, +5.44] |
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
| `prefix_unc_k25` | 0.5501 |
| `length_only_k100` | 0.5448 |
| `prefix_hand_k0` | 0.5379 |
| `prefix_tfidf_k0` | 0.5379 |
| `prefix_unc_k0` | 0.5379 |
| `prefix_handunc_k0` | 0.5379 |
| `length_only_k0` | 0.5379 |
| `length_only_k25` | 0.5379 |
| `prefix_emb_k0` | 0.5374 |
| `length_only_k50` | 0.5371 |
| `prefix_unc_k100` | 0.5296 |
| `prefix_handunc_k25` | 0.5294 |
| `prefix_unc_kfull` | 0.5267 |
| `prefix_unc_k200` | 0.5206 |
| `prefix_unc_k400` | 0.5169 |
| `length_only_k200` | 0.5161 |
| `prefix_emb_k25` | 0.5115 |
| `length_only_kfull` | 0.5059 |
| `prefix_handunc_k200` | 0.5056 |
| `length_only_k400` | 0.5045 |
| `prefix_emb_k400` | 0.5018 |
| `prefix_emb_kfull` | 0.5018 |
| `query+prefix_emb_k200` | 0.5007 |
| `prefix_emb_k200` | 0.5005 |
| `prefix_handunc_k400` | 0.5001 |
| `prefix_emb_k50` | 0.4992 |
| `prefix_hand_k25` | 0.4966 |
| `query+prefix_emb_k25` | 0.4963 |
| `prefix_handunc_k50` | 0.4963 |
| `query+prefix_emb_k400` | 0.4956 |
| `query+prefix_emb_kfull` | 0.4956 |
| `prefix_hand_k50` | 0.4945 |
| `prefix_handunc_kfull` | 0.4940 |
| `query+prefix_emb_k50` | 0.4938 |
| `prefix_hand_k400` | 0.4922 |
| `prefix_emb_k100` | 0.4842 |
| `prefix_tfidf_k400` | 0.4839 |
| `prefix_hand_kfull` | 0.4839 |
| `prefix_hand_k200` | 0.4808 |
| `prefix_unc_k50` | 0.4781 |
| `prefix_handunc_k100` | 0.4760 |
| `prefix_tfidf_kfull` | 0.4760 |
| `query+prefix_emb_k100` | 0.4720 |
| `query+prefix_handunc_k400` | 0.4623 |
| `query+prefix_handunc_k200` | 0.4602 |
| `prefix_tfidf_k200` | 0.4536 |
| `prefix_hand_k100` | 0.4529 |
| `query+prefix_hand_k400` | 0.4519 |
| `query+prefix_unc_kfull` | 0.4502 |
| `query+prefix_unc_k200` | 0.4496 |
| `prefix_tfidf_k50` | 0.4427 |
| `query+prefix_unc_k400` | 0.4425 |
| `query+prefix_handunc_kfull` | 0.4412 |
| `query+prefix_handunc_k25` | 0.4410 |
| `prefix_tfidf_k100` | 0.4378 |
| `query+prefix_handunc_k100` | 0.4378 |
| `prefix_tfidf_k25` | 0.4338 |
| `query+prefix_unc_k100` | 0.4332 |
| `query+prefix_hand_k200` | 0.4326 |
| `query+prefix_tfidf_kfull` | 0.4321 |
| `query+prefix_tfidf_k400` | 0.4303 |
| `query+prefix_handunc_k50` | 0.4292 |
| `query+prefix_hand_k25` | 0.4272 |
| `query+prefix_hand_kfull` | 0.4219 |
| `query+prefix_tfidf_k200` | 0.4216 |
| `query+prefix_hand_k50` | 0.4205 |
| `query+prefix_unc_k25` | 0.4185 |
| `query+prefix_hand_k100` | 0.4149 |
| `query+prefix_tfidf_k100` | 0.4130 |
| `query+prefix_tfidf_k50` | 0.4123 |
| `query+prefix_tfidf_k25` | 0.4075 |
| `query+prefix_unc_k50` | 0.4046 |
| `query+prefix_emb_k0` | 0.4005 |
| `query_only` | 0.4003 |
| `query+prefix_hand_k0` | 0.4003 |
| `query+prefix_tfidf_k0` | 0.4003 |
| `query+prefix_unc_k0` | 0.4003 |
| `query+prefix_handunc_k0` | 0.4003 |

## Mechanism Step 2 — feature audit (CONSTANT entries are stopping flags)

| k | features CONSTANT across questions |
|---|---|
| 0 | 45: hesitation_wait, hesitation_but, hesitation_total, n_letter_mentions, n_letter_changes, letter_appears, rep3_total, rep3_max, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, n_prefix_chars, unc_mean, unc_sd, unc_max, unc_min, unc_last, unc_sum, unc_slope, unc_mean_firsthalf, unc_mean_secondhalf, unc_n, unc_frac_gt_0.1, unc_frac_gt_0.5, unc_frac_gt_1.0, unc_frac_gt_2.0 |
| 25 | 23: n_letter_changes, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, trace_closed_by_k, n_prefix_tokens, unc_min, unc_n |
| 50 | 17: repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 100 | 14: phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 200 | 12: phrase::can't see, phrase::cannot see, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 400 | 9: phrase::cannot see, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::cannot determine, unc_min |
| full | 9: phrase::cannot see, phrase::before the video, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::not enough information, phrase::cannot determine, trace_closed_by_k, unc_min |

## Mechanism Step 3 — one traced unit

Question `00ac6f932f407123e3c689635c4e36561000dc2903d5d6ede74b7012de8ab225` (group `941275014627762_start_0.0_end_307.589`), device WRONG, cloud correct, gain 1.

| k | prefix tokens | non-zero features | predicted gain | rank | escalated at e=0.2 |
|---|---|---|---|---|---|
| 0 | 0 | trace_closed_by_k=1 | +0.35763 | 30/845 | yes |
| 25 | 25 | rep3_max=1, repsent_max=1, n_prefix_tokens=25, n_prefix_chars=99 | +0.35188 | 42/845 | yes |
| 50 | 50 | rep3_max=1, repsent_max=1, n_prefix_tokens=50, n_prefix_chars=221 | +0.37548 | 42/845 | yes |
| 100 | 100 | rep3_total=1, rep3_max=2, repsent_max=1, n_prefix_tokens=100, n_prefix_chars=358 | +0.39482 | 31/845 | yes |
| 200 | 200 | n_letter_mentions=4, n_letter_changes=3, letter_appears=1, rep3_total=1, rep3_max=2, repsent_max=1 | +0.32136 | 75/845 | yes |
| 400 | 219 | n_letter_mentions=6, n_letter_changes=5, letter_appears=1, rep3_total=1, rep3_max=2, repsent_max=1 | +0.30804 | 91/845 | yes |


# ERQA  (n = 400)

Device 45.25% · cloud 46.75% · gain counts {'-1': 59, '0': 276, '1': 65} · 5 folds

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
| `prefix_tfidf_kfull` | full | 38.2 | 0.6493 | [0.5939, 0.7034] | +0.0905 | [+0.0418, +0.1368] |
| `answer_confidence` | full | 38.2 | 0.6251 | [0.5698, 0.6769] | +0.0662 | [-0.0101, +0.1341] |
| `prefix_tfidf_k400` | 400 | 37.5 | 0.6249 | [0.5703, 0.6785] | +0.0660 | [+0.0217, +0.1122] |
| `query+prefix_unc_kfull` | full | 38.2 | 0.6098 | [0.5529, 0.6630] | +0.0510 | [+0.0014, +0.0983] |
| `prefix_tfidf_k200` | 200 | 29.2 | 0.6042 | [0.5480, 0.6585] | +0.0453 | [-0.0008, +0.0920] |
| `length_only_kfull` | full | 38.2 | 0.5975 | [0.5391, 0.6523] | +0.0386 | [-0.0371, +0.1150] |
| `prefix_tfidf_k25` | 25 | 18.7 | 0.5943 | [0.5353, 0.6510] | +0.0354 | [-0.0265, +0.0994] |
| `prefix_unc_kfull` | full | 38.2 | 0.5891 | [0.5309, 0.6444] | +0.0302 | [-0.0458, +0.1064] |
| `query+prefix_tfidf_kfull` | full | 38.2 | 0.5880 | [0.5304, 0.6429] | +0.0292 | [-0.0017, +0.0603] |
| `prefix_hand_k400` | 400 | 37.5 | 0.5879 | [0.5327, 0.6412] | +0.0291 | [-0.0434, +0.0993] |
| `query+prefix_hand_k400` | 400 | 37.5 | 0.5862 | [0.5269, 0.6422] | +0.0274 | [-0.0185, +0.0764] |
| `query+prefix_hand_kfull` | full | 38.2 | 0.5837 | [0.5264, 0.6376] | +0.0248 | [-0.0213, +0.0718] |
| `query+prefix_handunc_kfull` | full | 38.2 | 0.5822 | [0.5249, 0.6370] | +0.0233 | [-0.0315, +0.0739] |
| `prefix_hand_k200` | 200 | 29.2 | 0.5812 | [0.5224, 0.6368] | +0.0224 | [-0.0478, +0.0930] |
| `prefix_hand_kfull` | full | 38.2 | 0.5785 | [0.5240, 0.6326] | +0.0197 | [-0.0560, +0.0922] |
| `query+prefix_unc_k400` | 400 | 37.5 | 0.5770 | [0.5176, 0.6325] | +0.0182 | [-0.0257, +0.0612] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | 0.5756 | [0.5162, 0.6292] | +0.0168 | [-0.0099, +0.0449] |
| `query+prefix_hand_k200` | 200 | 29.2 | 0.5749 | [0.5139, 0.6332] | +0.0161 | [-0.0313, +0.0636] |
| `prefix_handunc_kfull` | full | 38.2 | 0.5734 | [0.5155, 0.6265] | +0.0146 | [-0.0611, +0.0857] |
| `query+prefix_handunc_k400` | 400 | 37.5 | 0.5700 | [0.5106, 0.6284] | +0.0112 | [-0.0417, +0.0613] |
| `prefix_handunc_k400` | 400 | 37.5 | 0.5686 | [0.5089, 0.6236] | +0.0097 | [-0.0626, +0.0790] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | 0.5666 | [0.5070, 0.6206] | +0.0077 | [-0.0176, +0.0332] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | 0.5662 | [0.5075, 0.6236] | +0.0073 | [-0.0104, +0.0265] |
| `query+prefix_unc_k200` | 200 | 29.2 | 0.5636 | [0.5026, 0.6195] | +0.0048 | [-0.0389, +0.0474] |
| `query+prefix_unc_k50` | 50 | 20.2 | 0.5633 | [0.5072, 0.6213] | +0.0045 | [-0.0359, +0.0483] |
| `prefix_tfidf_k100` | 100 | 23.2 | 0.5621 | [0.5042, 0.6186] | +0.0033 | [-0.0494, +0.0581] |
| `query_only` | None | 0.0 | 0.5588 | [0.4993, 0.6155] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_hand_k0` | 0 | 0.0 | 0.5588 | [0.4993, 0.6155] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | 0.5588 | [0.4993, 0.6155] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_unc_k0` | 0 | 0.0 | 0.5588 | [0.4993, 0.6155] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_handunc_k0` | 0 | 0.0 | 0.5588 | [0.4993, 0.6155] | +0.0000 | [+0.0000, +0.0000] |
| `query+prefix_emb_k0` | 0 | 0.0 | 0.5578 | [0.4999, 0.6154] | -0.0010 | [-0.0228, +0.0206] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | 0.5544 | [0.4955, 0.6106] | -0.0044 | [-0.0249, +0.0160] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | 0.5540 | [0.4951, 0.6100] | -0.0049 | [-0.0299, +0.0202] |
| `prefix_unc_k400` | 400 | 37.5 | 0.5522 | [0.4925, 0.6052] | -0.0066 | [-0.0819, +0.0657] |
| `length_only_k400` | 400 | 37.5 | 0.5521 | [0.4929, 0.6070] | -0.0067 | [-0.0809, +0.0650] |
| `query+prefix_handunc_k200` | 200 | 29.2 | 0.5516 | [0.4889, 0.6090] | -0.0072 | [-0.0610, +0.0456] |
| `prefix_handunc_k200` | 200 | 29.2 | 0.5461 | [0.4843, 0.6013] | -0.0128 | [-0.0845, +0.0606] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | 0.5459 | [0.4896, 0.6057] | -0.0129 | [-0.0606, +0.0346] |
| `query+prefix_hand_k25` | 25 | 18.7 | 0.5433 | [0.4853, 0.6000] | -0.0156 | [-0.0393, +0.0079] |
| `prefix_unc_k200` | 200 | 29.2 | 0.5405 | [0.4795, 0.5950] | -0.0183 | [-0.0931, +0.0536] |
| `query+prefix_unc_k25` | 25 | 18.7 | 0.5378 | [0.4791, 0.5968] | -0.0211 | [-0.0565, +0.0164] |
| `prefix_tfidf_k50` | 50 | 20.2 | 0.5364 | [0.4784, 0.5922] | -0.0225 | [-0.0810, +0.0374] |
| `query+prefix_unc_k100` | 100 | 23.2 | 0.5342 | [0.4782, 0.5924] | -0.0246 | [-0.0607, +0.0126] |
| `query+prefix_handunc_k50` | 50 | 20.2 | 0.5317 | [0.4724, 0.5898] | -0.0271 | [-0.0728, +0.0241] |
| `prefix_emb_k400` | 400 | 37.5 | 0.5310 | [0.4720, 0.5855] | -0.0278 | [-0.1014, +0.0469] |
| `prefix_emb_kfull` | full | 38.2 | 0.5310 | [0.4720, 0.5855] | -0.0278 | [-0.1014, +0.0469] |
| `query+prefix_emb_k400` | 400 | 37.5 | 0.5291 | [0.4701, 0.5843] | -0.0297 | [-0.1008, +0.0420] |
| `query+prefix_emb_kfull` | full | 38.2 | 0.5291 | [0.4701, 0.5843] | -0.0297 | [-0.1008, +0.0420] |
| `prefix_unc_k50` | 50 | 20.2 | 0.5278 | [0.4718, 0.5853] | -0.0310 | [-0.1085, +0.0489] |
| `length_only_k200` | 200 | 29.2 | 0.5247 | [0.4619, 0.5814] | -0.0341 | [-0.1073, +0.0368] |
| `query+prefix_hand_k100` | 100 | 23.2 | 0.5243 | [0.4650, 0.5790] | -0.0345 | [-0.0724, +0.0045] |
| `prefix_handunc_k50` | 50 | 20.2 | 0.5225 | [0.4677, 0.5823] | -0.0363 | [-0.1082, +0.0421] |
| `prefix_emb_k25` | 25 | 18.7 | 0.5216 | [0.4614, 0.5792] | -0.0372 | [-0.1123, +0.0370] |
| `query+prefix_hand_k50` | 50 | 20.2 | 0.5200 | [0.4594, 0.5769] | -0.0388 | [-0.0747, -0.0010] |
| `query+prefix_handunc_k25` | 25 | 18.7 | 0.5197 | [0.4617, 0.5773] | -0.0392 | [-0.0795, +0.0044] |
| `prefix_hand_k100` | 100 | 23.2 | 0.5188 | [0.4607, 0.5749] | -0.0400 | [-0.1149, +0.0348] |
| `query+prefix_emb_k25` | 25 | 18.7 | 0.5145 | [0.4556, 0.5708] | -0.0444 | [-0.1153, +0.0274] |
| `prefix_hand_k50` | 50 | 20.2 | 0.5144 | [0.4576, 0.5722] | -0.0444 | [-0.1162, +0.0355] |
| `prefix_hand_k25` | 25 | 18.7 | 0.5062 | [0.4508, 0.5623] | -0.0527 | [-0.1269, +0.0218] |
| `query+prefix_emb_k50` | 50 | 20.2 | 0.5000 | [0.4469, 0.5600] | -0.0588 | [-0.1264, +0.0134] |
| `prefix_emb_k200` | 200 | 29.2 | 0.4999 | [0.4402, 0.5570] | -0.0589 | [-0.1336, +0.0179] |
| `prefix_emb_k50` | 50 | 20.2 | 0.4991 | [0.4469, 0.5569] | -0.0597 | [-0.1302, +0.0154] |
| `query+prefix_handunc_k100` | 100 | 23.2 | 0.4979 | [0.4403, 0.5549] | -0.0609 | [-0.1043, -0.0147] |
| `query+prefix_emb_k200` | 200 | 29.2 | 0.4977 | [0.4374, 0.5529] | -0.0612 | [-0.1340, +0.0111] |
| `query+prefix_emb_k100` | 100 | 23.2 | 0.4902 | [0.4309, 0.5458] | -0.0686 | [-0.1428, +0.0050] |
| `prefix_emb_k100` | 100 | 23.2 | 0.4866 | [0.4286, 0.5423] | -0.0722 | [-0.1503, +0.0078] |
| `prefix_handunc_k100` | 100 | 23.2 | 0.4832 | [0.4254, 0.5396] | -0.0757 | [-0.1476, +0.0005] |
| `prefix_unc_k25` | 25 | 18.7 | 0.4801 | [0.4239, 0.5383] | -0.0787 | [-0.1524, -0.0022] |
| `prefix_unc_k100` | 100 | 23.2 | 0.4793 | [0.4228, 0.5356] | -0.0796 | [-0.1537, -0.0058] |
| `prefix_handunc_k25` | 25 | 18.7 | 0.4769 | [0.4185, 0.5346] | -0.0819 | [-0.1532, -0.0059] |
| `length_only_k100` | 100 | 23.2 | 0.4749 | [0.4188, 0.5328] | -0.0839 | [-0.1592, -0.0092] |
| `prefix_hand_k0` | 0 | 0.0 | 0.4475 | [0.3921, 0.5049] | -0.1113 | [-0.1900, -0.0315] |
| `prefix_tfidf_k0` | 0 | 0.0 | 0.4475 | [0.3921, 0.5049] | -0.1113 | [-0.1900, -0.0315] |
| `prefix_unc_k0` | 0 | 0.0 | 0.4475 | [0.3921, 0.5049] | -0.1113 | [-0.1900, -0.0315] |
| `prefix_handunc_k0` | 0 | 0.0 | 0.4475 | [0.3921, 0.5049] | -0.1113 | [-0.1900, -0.0315] |
| `length_only_k0` | 0 | 0.0 | 0.4475 | [0.3921, 0.5049] | -0.1113 | [-0.1900, -0.0315] |
| `length_only_k25` | 25 | 18.7 | 0.4475 | [0.3921, 0.5049] | -0.1113 | [-0.1900, -0.0315] |
| `length_only_k50` | 50 | 20.2 | 0.4475 | [0.3921, 0.5049] | -0.1113 | [-0.1900, -0.0315] |
| `prefix_emb_k0` | 0 | 0.0 | 0.4337 | [0.3758, 0.4901] | -0.1252 | [-0.2065, -0.0457] |

## Part 2 — escalation utility

| e | random | perfect oracle | always-local | always-cloud |
|---|---|---|---|---|
| 0.1 | 45.46 | 55.25 | 45.25 | 46.75 |
| 0.2 | 45.65 | 61.50 | 45.25 | 46.75 |
| 0.3 | 45.74 | 61.50 | 45.25 | 46.75 |
| 0.5 | 45.88 | 61.50 | 45.25 | 46.75 |
| 1.0 | 46.75 | 46.75 | 45.25 | 46.75 |

### At e = 0.2, every router, both rankings

| router | k | latency s | rank | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|---|
| `answer_confidence` | full | 38.2 | by_gain | 48.00 | +1.75 | [-1.00, +5.00] |
| `prefix_emb_k50` | 50 | 20.2 | by_gain | 47.75 | +1.50 | [-1.50, +4.50] |
| `answer_confidence` | full | 38.2 | by_failure | 48.00 | +1.25 | [-1.75, +4.75] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_gain | 47.25 | +1.00 | [-2.25, +3.75] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_failure | 47.75 | +1.00 | [-1.50, +3.75] |
| `prefix_handunc_k50` | 50 | 20.2 | by_failure | 47.75 | +1.00 | [-2.00, +4.00] |
| `prefix_emb_k50` | 50 | 20.2 | by_failure | 47.75 | +1.00 | [-1.75, +4.25] |
| `prefix_emb_k200` | 200 | 29.2 | by_gain | 47.25 | +1.00 | [-2.00, +3.25] |
| `query+prefix_unc_kfull` | full | 38.2 | by_failure | 47.50 | +0.75 | [-2.50, +3.50] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_gain | 47.00 | +0.75 | [-2.00, +3.50] |
| `prefix_hand_k400` | 400 | 37.5 | by_failure | 47.50 | +0.75 | [-2.25, +4.00] |
| `prefix_hand_k100` | 100 | 23.2 | by_gain | 47.00 | +0.75 | [-2.50, +3.76] |
| `query+prefix_unc_kfull` | full | 38.2 | by_gain | 46.75 | +0.50 | [-1.00, +2.25] |
| `query+prefix_hand_kfull` | full | 38.2 | by_failure | 47.25 | +0.50 | [-2.00, +3.25] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_failure | 47.25 | +0.50 | [-2.26, +3.25] |
| `query+prefix_emb_k50` | 50 | 20.2 | by_failure | 47.25 | +0.50 | [-2.00, +4.00] |
| `prefix_tfidf_kfull` | full | 38.2 | by_failure | 47.25 | +0.50 | [-2.00, +3.26] |
| `prefix_emb_k200` | 200 | 29.2 | by_failure | 47.25 | +0.50 | [-2.50, +3.51] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_failure | 47.00 | +0.25 | [-1.51, +1.50] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_failure | 47.00 | +0.25 | [-2.50, +3.25] |
| `prefix_unc_kfull` | full | 38.2 | by_failure | 47.00 | +0.25 | [-2.76, +3.75] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_failure | 47.00 | +0.25 | [-2.25, +2.75] |
| `query_only` | None | 0.0 | by_gain | 46.25 | +0.00 | [+0.00, +0.00] |
| `query_only` | None | 0.0 | by_failure | 46.75 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_gain | 46.25 | +0.00 | [+0.00, +0.00] |
| `query+prefix_unc_k0` | 0 | 0.0 | by_failure | 46.75 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k50` | 50 | 20.2 | by_gain | 46.25 | +0.00 | [-1.50, +1.75] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_failure | 46.75 | +0.00 | [-2.00, +1.75] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_failure | 46.75 | +0.00 | [-2.00, +1.75] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_gain | 46.25 | +0.00 | [+0.00, +0.00] |
| `query+prefix_tfidf_k0` | 0 | 0.0 | by_failure | 46.75 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_gain | 46.25 | +0.00 | [-2.25, +2.50] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_gain | 46.25 | +0.00 | [+0.00, +0.00] |
| `query+prefix_handunc_k0` | 0 | 0.0 | by_failure | 46.75 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_gain | 46.25 | +0.00 | [-1.50, +2.25] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_gain | 46.25 | +0.00 | [-2.00, +1.75] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_gain | 46.25 | +0.00 | [+0.00, +0.00] |
| `query+prefix_hand_k0` | 0 | 0.0 | by_failure | 46.75 | +0.00 | [+0.00, +0.00] |
| `query+prefix_emb_kfull` | full | 38.2 | by_failure | 46.75 | +0.00 | [-3.25, +3.00] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_failure | 46.75 | +0.00 | [-3.25, +3.00] |
| `query+prefix_emb_k200` | 200 | 29.2 | by_failure | 46.75 | +0.00 | [-2.75, +3.25] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_gain | 46.25 | +0.00 | [-1.25, +0.75] |
| `prefix_unc_k50` | 50 | 20.2 | by_failure | 46.75 | +0.00 | [-3.25, +3.00] |
| `prefix_emb_kfull` | full | 38.2 | by_gain | 46.25 | +0.00 | [-3.00, +3.25] |
| `prefix_emb_k400` | 400 | 37.5 | by_gain | 46.25 | +0.00 | [-3.00, +3.25] |
| `length_only_kfull` | full | 38.2 | by_failure | 46.75 | +0.00 | [-3.00, +3.50] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_gain | 46.00 | -0.25 | [-1.75, +1.50] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_gain | 46.00 | -0.25 | [-2.00, +1.75] |
| `query+prefix_tfidf_k400` | 400 | 37.5 | by_gain | 46.00 | -0.25 | [-2.25, +2.00] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_gain | 46.00 | -0.25 | [-3.25, +2.51] |
| `query+prefix_emb_k25` | 25 | 18.7 | by_failure | 46.50 | -0.25 | [-3.50, +2.75] |
| `prefix_unc_k50` | 50 | 20.2 | by_gain | 46.00 | -0.25 | [-3.25, +3.25] |
| `prefix_unc_k400` | 400 | 37.5 | by_failure | 46.50 | -0.25 | [-3.50, +2.50] |
| `prefix_tfidf_kfull` | full | 38.2 | by_gain | 46.00 | -0.25 | [-2.00, +2.25] |
| `prefix_handunc_k400` | 400 | 37.5 | by_failure | 46.50 | -0.25 | [-3.25, +3.00] |
| `prefix_emb_k25` | 25 | 18.7 | by_failure | 46.50 | -0.25 | [-3.25, +3.25] |
| `prefix_emb_k100` | 100 | 23.2 | by_failure | 46.50 | -0.25 | [-3.25, +3.25] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_failure | 46.50 | -0.25 | [-2.75, +2.00] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_gain | 45.75 | -0.50 | [-1.75, +1.75] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_failure | 46.25 | -0.50 | [-2.50, +2.00] |
| `query+prefix_tfidf_kfull` | full | 38.2 | by_failure | 46.25 | -0.50 | [-2.75, +1.75] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_failure | 46.25 | -0.50 | [-2.25, +1.25] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_gain | 45.75 | -0.50 | [-2.75, +1.25] |
| `prefix_unc_kfull` | full | 38.2 | by_gain | 45.75 | -0.50 | [-3.50, +2.50] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_failure | 46.25 | -0.50 | [-3.50, +1.75] |
| `prefix_handunc_kfull` | full | 38.2 | by_failure | 46.25 | -0.50 | [-3.75, +2.50] |
| `prefix_handunc_k50` | 50 | 20.2 | by_gain | 45.75 | -0.50 | [-3.75, +3.00] |
| `prefix_handunc_k25` | 25 | 18.7 | by_failure | 46.25 | -0.50 | [-4.00, +2.75] |
| `prefix_emb_k25` | 25 | 18.7 | by_gain | 45.75 | -0.50 | [-3.50, +2.75] |
| `length_only_kfull` | full | 38.2 | by_gain | 45.75 | -0.50 | [-3.50, +2.75] |
| `CONTROL_shuffled_prefix_k100` | 100 | 23.2 | by_gain | 45.75 | -0.50 | [-2.25, +1.25] |
| `query+prefix_unc_k400` | 400 | 37.5 | by_gain | 45.50 | -0.75 | [-1.75, +1.25] |
| `query+prefix_unc_k400` | 400 | 37.5 | by_failure | 46.00 | -0.75 | [-3.00, +1.75] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_failure | 46.00 | -0.75 | [-2.00, +0.75] |
| `query+prefix_tfidf_k200` | 200 | 29.2 | by_gain | 45.50 | -0.75 | [-2.75, +1.75] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_gain | 45.50 | -0.75 | [-3.00, +1.25] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_gain | 45.50 | -0.75 | [-2.50, +1.00] |
| `query+prefix_handunc_k200` | 200 | 29.2 | by_failure | 46.00 | -0.75 | [-3.50, +2.00] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_gain | 45.50 | -0.75 | [-2.25, +1.50] |
| `query+prefix_hand_k400` | 400 | 37.5 | by_gain | 45.50 | -0.75 | [-2.25, +1.01] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_failure | 46.00 | -0.75 | [-2.50, +1.25] |
| `query+prefix_emb_k0` | 0 | 0.0 | by_failure | 46.00 | -0.75 | [-2.50, +0.75] |
| `prefix_unc_k200` | 200 | 29.2 | by_failure | 46.00 | -0.75 | [-3.75, +1.75] |
| `prefix_tfidf_k400` | 400 | 37.5 | by_gain | 45.50 | -0.75 | [-2.50, +1.75] |
| `prefix_tfidf_k200` | 200 | 29.2 | by_gain | 45.50 | -0.75 | [-3.00, +1.75] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_gain | 45.50 | -0.75 | [-3.26, +1.50] |
| `prefix_tfidf_k100` | 100 | 23.2 | by_failure | 46.00 | -0.75 | [-3.25, +2.00] |
| `prefix_handunc_k400` | 400 | 37.5 | by_gain | 45.50 | -0.75 | [-3.50, +2.50] |
| `prefix_handunc_k200` | 200 | 29.2 | by_failure | 46.00 | -0.75 | [-3.50, +2.25] |
| `prefix_hand_kfull` | full | 38.2 | by_failure | 46.00 | -0.75 | [-3.75, +2.26] |
| `prefix_emb_kfull` | full | 38.2 | by_failure | 46.00 | -0.75 | [-3.75, +2.26] |
| `prefix_emb_k400` | 400 | 37.5 | by_failure | 46.00 | -0.75 | [-3.75, +2.26] |
| `query+prefix_unc_k25` | 25 | 18.7 | by_failure | 45.75 | -1.00 | [-2.75, +1.50] |
| `query+prefix_tfidf_k100` | 100 | 23.2 | by_gain | 45.25 | -1.00 | [-2.50, +1.50] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_gain | 45.25 | -1.00 | [-2.50, +0.50] |
| `query+prefix_hand_k25` | 25 | 18.7 | by_gain | 45.25 | -1.00 | [-2.00, +0.51] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_gain | 45.25 | -1.00 | [-3.00, +1.00] |
| `query+prefix_hand_k100` | 100 | 23.2 | by_failure | 45.75 | -1.00 | [-3.00, +1.75] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_failure | 45.75 | -1.00 | [-4.00, +1.75] |
| `prefix_handunc_k25` | 25 | 18.7 | by_gain | 45.25 | -1.00 | [-3.26, +2.25] |
| `prefix_handunc_k100` | 100 | 23.2 | by_gain | 45.25 | -1.00 | [-4.00, +2.50] |
| `prefix_handunc_k100` | 100 | 23.2 | by_failure | 45.75 | -1.00 | [-3.75, +2.00] |
| `prefix_hand_k25` | 25 | 18.7 | by_failure | 45.75 | -1.00 | [-4.01, +2.00] |
| `prefix_hand_k200` | 200 | 29.2 | by_failure | 45.75 | -1.00 | [-4.00, +2.26] |
| `query+prefix_tfidf_k25` | 25 | 18.7 | by_gain | 45.00 | -1.25 | [-3.00, +0.25] |
| `query+prefix_handunc_kfull` | full | 38.2 | by_failure | 45.50 | -1.25 | [-3.50, +2.00] |
| `query+prefix_handunc_k400` | 400 | 37.5 | by_failure | 45.50 | -1.25 | [-3.75, +1.75] |
| `query+prefix_handunc_k25` | 25 | 18.7 | by_failure | 45.50 | -1.25 | [-3.50, +1.25] |
| `query+prefix_handunc_k100` | 100 | 23.2 | by_failure | 45.50 | -1.25 | [-4.00, +1.00] |
| `query+prefix_emb_kfull` | full | 38.2 | by_gain | 45.00 | -1.25 | [-3.75, +2.25] |
| `query+prefix_emb_k400` | 400 | 37.5 | by_gain | 45.00 | -1.25 | [-3.75, +2.25] |
| `prefix_tfidf_k50` | 50 | 20.2 | by_gain | 45.00 | -1.25 | [-3.75, +1.75] |
| `prefix_hand_k50` | 50 | 20.2 | by_gain | 45.00 | -1.25 | [-4.50, +1.76] |
| `query+prefix_unc_k200` | 200 | 29.2 | by_gain | 44.75 | -1.50 | [-2.75, +0.50] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_gain | 44.75 | -1.50 | [-3.00, +0.25] |
| `query+prefix_handunc_k50` | 50 | 20.2 | by_failure | 45.25 | -1.50 | [-4.00, +0.75] |
| `query+prefix_hand_kfull` | full | 38.2 | by_gain | 44.75 | -1.50 | [-3.50, +0.75] |
| `query+prefix_hand_k200` | 200 | 29.2 | by_failure | 45.25 | -1.50 | [-3.75, +1.25] |
| `query+prefix_emb_k100` | 100 | 23.2 | by_gain | 44.75 | -1.50 | [-4.00, +1.75] |
| `prefix_unc_k25` | 25 | 18.7 | by_gain | 44.75 | -1.50 | [-4.25, +1.50] |
| `prefix_unc_k25` | 25 | 18.7 | by_failure | 45.25 | -1.50 | [-4.75, +1.75] |
| `prefix_tfidf_k25` | 25 | 18.7 | by_gain | 44.75 | -1.50 | [-4.00, +1.00] |
| `prefix_hand_k400` | 400 | 37.5 | by_gain | 44.75 | -1.50 | [-4.25, +1.50] |
| `prefix_emb_k100` | 100 | 23.2 | by_gain | 44.75 | -1.50 | [-4.50, +1.50] |
| `query+prefix_hand_k50` | 50 | 20.2 | by_failure | 45.00 | -1.75 | [-3.50, +1.01] |
| `prefix_unc_k100` | 100 | 23.2 | by_failure | 45.00 | -1.75 | [-5.00, +1.75] |
| `prefix_hand_kfull` | full | 38.2 | by_gain | 44.50 | -1.75 | [-5.00, +1.25] |
| `query+prefix_unc_k50` | 50 | 20.2 | by_failure | 44.75 | -2.00 | [-4.50, +0.25] |
| `query+prefix_unc_k100` | 100 | 23.2 | by_failure | 44.75 | -2.00 | [-4.50, +0.75] |
| `prefix_hand_k50` | 50 | 20.2 | by_failure | 44.75 | -2.00 | [-4.50, +1.25] |
| `prefix_hand_k100` | 100 | 23.2 | by_failure | 44.75 | -2.00 | [-4.75, +1.50] |
| `length_only_k400` | 400 | 37.5 | by_gain | 44.25 | -2.00 | [-4.75, +1.00] |
| `prefix_handunc_kfull` | full | 38.2 | by_gain | 44.00 | -2.25 | [-5.00, +1.25] |
| `prefix_hand_k25` | 25 | 18.7 | by_gain | 44.00 | -2.25 | [-5.25, +0.75] |
| `prefix_hand_k200` | 200 | 29.2 | by_gain | 44.00 | -2.25 | [-5.00, +1.25] |
| `prefix_emb_k0` | 0 | 0.0 | by_failure | 44.25 | -2.50 | [-5.50, +0.25] |
| `prefix_unc_k400` | 400 | 37.5 | by_gain | 43.50 | -2.75 | [-5.25, +1.25] |
| `prefix_unc_k200` | 200 | 29.2 | by_gain | 43.50 | -2.75 | [-5.75, +0.25] |
| `prefix_unc_k0` | 0 | 0.0 | by_failure | 44.00 | -2.75 | [-5.50, +0.00] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_failure | 44.00 | -2.75 | [-5.50, +0.00] |
| `prefix_handunc_k0` | 0 | 0.0 | by_failure | 44.00 | -2.75 | [-5.50, +0.00] |
| `prefix_hand_k0` | 0 | 0.0 | by_failure | 44.00 | -2.75 | [-5.50, +0.00] |
| `length_only_k50` | 50 | 20.2 | by_failure | 44.00 | -2.75 | [-5.50, +0.00] |
| `length_only_k25` | 25 | 18.7 | by_failure | 44.00 | -2.75 | [-5.50, +0.00] |
| `length_only_k0` | 0 | 0.0 | by_failure | 44.00 | -2.75 | [-5.50, +0.00] |
| `prefix_handunc_k200` | 200 | 29.2 | by_gain | 43.25 | -3.00 | [-6.00, +0.50] |
| `length_only_k400` | 400 | 37.5 | by_failure | 43.75 | -3.00 | [-5.75, +0.00] |
| `prefix_unc_k0` | 0 | 0.0 | by_gain | 43.00 | -3.25 | [-6.50, +0.25] |
| `prefix_tfidf_k0` | 0 | 0.0 | by_gain | 43.00 | -3.25 | [-6.50, +0.25] |
| `prefix_handunc_k0` | 0 | 0.0 | by_gain | 43.00 | -3.25 | [-6.50, +0.25] |
| `prefix_hand_k0` | 0 | 0.0 | by_gain | 43.00 | -3.25 | [-6.50, +0.25] |
| `length_only_k50` | 50 | 20.2 | by_gain | 43.00 | -3.25 | [-6.50, +0.25] |
| `length_only_k25` | 25 | 18.7 | by_gain | 43.00 | -3.25 | [-6.50, +0.25] |
| `length_only_k100` | 100 | 23.2 | by_failure | 43.50 | -3.25 | [-5.75, -0.25] |
| `length_only_k0` | 0 | 0.0 | by_gain | 43.00 | -3.25 | [-6.50, +0.25] |
| `prefix_unc_k100` | 100 | 23.2 | by_gain | 42.75 | -3.50 | [-6.75, +0.00] |
| `length_only_k200` | 200 | 29.2 | by_gain | 42.75 | -3.50 | [-6.25, +0.00] |
| `length_only_k100` | 100 | 23.2 | by_gain | 42.75 | -3.50 | [-6.25, +0.01] |
| `length_only_k200` | 200 | 29.2 | by_failure | 43.00 | -3.75 | [-6.50, -0.75] |
| `prefix_emb_k0` | 0 | 0.0 | by_gain | 42.00 | -4.25 | [-6.76, -0.50] |

### Best router at each budget e (by_gain)

| e | best router | k | acc % | delta vs query-only | 95% CI |
|---|---|---|---|---|---|
| 0.1 | `query+prefix_emb_k50` | 50 | 47.75 | +2.50 | [+0.00, +4.75] |
| 0.2 | `answer_confidence` | full | 48.00 | +1.75 | [-1.00, +5.00] |
| 0.3 | `answer_confidence` | full | 48.50 | +3.50 | [+0.00, +6.75] |
| 0.5 | `prefix_tfidf_k400` | 400 | 49.50 | +4.00 | [+1.25, +7.00] |
| 1.0 | `query_only` | None | 46.75 | +0.00 | [+0.00, +0.00] |

## Mechanism Step 2 — feature audit (CONSTANT entries are stopping flags)

| k | features CONSTANT across questions |
|---|---|
| 0 | 45: hesitation_wait, hesitation_but, hesitation_total, n_letter_mentions, n_letter_changes, letter_appears, rep3_total, rep3_max, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, n_prefix_chars, unc_mean, unc_sd, unc_max, unc_min, unc_last, unc_sum, unc_slope, unc_mean_firsthalf, unc_mean_secondhalf, unc_n, unc_frac_gt_0.1, unc_frac_gt_0.5, unc_frac_gt_1.0, unc_frac_gt_2.0 |
| 25 | 25: rep3_total, rep3_max, repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::not in the, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::outside the, phrase::don't see, phrase::do not see, phrase::no visible, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, missing_evidence_total, trace_closed_by_k, n_prefix_tokens, unc_n |
| 50 | 16: repsent_total, repsent_max, phrase::not visible, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 100 | 15: repsent_total, repsent_max, phrase::can't see, phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 200 | 12: phrase::cannot see, phrase::not shown, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| 400 | 11: phrase::cannot see, phrase::earlier, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::hard to tell, phrase::unclear, phrase::not enough information, phrase::can't determine, phrase::cannot determine, unc_min |
| full | 10: phrase::cannot see, phrase::before the clip, phrase::before the video, phrase::do not see, phrase::hard to tell, phrase::not enough information, phrase::can't determine, phrase::cannot determine, trace_closed_by_k, unc_min |

## Mechanism Step 3 — one traced unit

Question `2` (group `2`), device WRONG, cloud correct, gain 1.

| k | prefix tokens | non-zero features | predicted gain | rank | escalated at e=0.2 |
|---|---|---|---|---|---|
| 0 | 0 | trace_closed_by_k=1 | +0.11501 | 127/400 | no |
| 25 | 25 | rep3_max=1, repsent_max=1, n_prefix_tokens=25, n_prefix_chars=96 | +0.11530 | 124/400 | no |
| 50 | 50 | hesitation_but=1, hesitation_total=1, rep3_max=1, repsent_max=1, n_prefix_tokens=50, n_prefix_chars=201 | +0.23881 | 55/400 | yes |
| 100 | 100 | hesitation_wait=2, hesitation_but=1, hesitation_total=3, rep3_total=3, rep3_max=2, repsent_max=1 | +0.18853 | 89/400 | no |
| 200 | 200 | hesitation_wait=5, hesitation_but=2, hesitation_total=7, rep3_total=15, rep3_max=5, repsent_max=1 | +0.24606 | 64/400 | yes |
| 400 | 400 | hesitation_wait=14, hesitation_but=2, hesitation_total=16, rep3_total=79, rep3_max=11, repsent_max=1 | +0.09948 | 158/400 | no |

