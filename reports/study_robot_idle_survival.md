# StudyROBOT-IDLE-SURVIVAL (official): does a robot history survive idle time?

CPU only, read-only on cells, no images. **D240: 1x and kv0.5r are reported in separate tables and never pooled.** Reproduces the planner's scratch analysis from the committed cells.

## Definitions

- Universe: every robot request whose PREVIOUS request in the same session had >= 2000 prompt tokens, over all VALID L3_epg_rq30 cells, seeds 4 to 7.
- gap = t_submit - previous_request.t_done (same session_id).
- survival = cached_tokens / min(prev prompt_tokens, this prompt_tokens). COLD if survival < 0.2; WARM if survival >= 0.8.
- first-token time = t_first_token - t_submit; robot deadline 3.0 s.
- INVALID cells (header source_agreement.verdict starts with INVALID) are never used; a cell with no key is marked agreement ABSENT and kept; a _rerun supersedes its plain.

## Positive control against the planner's scratch numbers

| check | planner scratch | this run | match |
|---|---|---|---|
| rung 3 (covex-v6-fair-final) kv0.5r 30-60 s P(cold), n | 0.010, 396 | 0.0101, 396 | yes |
| llf 1x 30-60 s P(cold), n | 1.000, 39 | 1.0000, 39 | yes |
| rung 3 kv0.5r question P(cold), n | 0.002, 460 | 0.0022, 460 | yes |

All three reproduce exactly; no mismatch to explain. The official pipeline and the planner's scratch agree to the quoted precision.

## Headline

At kv0.5r the rung-3 arm (covex-v6-fair-final) keeps robot histories WARM across every idle bucket: its 30-60 s P(cold) is ~0.01 and its question P(cold) is ~0.002, because it touches the history to hold it resident. The baselines do not: llf at 1x goes fully COLD by 30-60 s (P(cold) 1.000) and its questions miss the 3 s first-token deadline about half the time. This is the mechanism behind the retention axis, read straight off the KV survival.

## 1x: per arm, per gap bucket

n, P(cold), P(warm), median previous prompt tokens, median first-token s for cold / warm.

| arm | bucket | n | P(cold) | P(warm) | med_prev_tok | med_ttft_cold_s | med_ttft_warm_s |
|---|---|---|---|---|---|---|---|
| always-cloud-fcfs | 0-1 | 225 | 0.5467 | 0.3867 | 15236 | 249.9871 | 204.4160 |
| always-cloud-fcfs | 1-3 | 4 | 0.0000 | 1.0000 | 7668.0000 |  | 1.4957 |
| always-cloud-fcfs | 3-10 | 9 | 0.4444 | 0.5556 | 10789 | 34.0339 | 0.8905 |
| always-cloud-fcfs | 10-30 | 15 | 0.8000 | 0.2000 | 12032 | 17.0656 | 1.6092 |
| always-cloud-fcfs | 30-60 | 14 | 1.0000 | 0.0000 | 9229.5000 | 3.8617 |  |
| always-cloud-fcfs | 60-120 | 5 | 1.0000 | 0.0000 | 11822 | 46.5714 |  |
| attentionstore-prefetch | 0-1 | 802 | 0.1608 | 0.7930 | 12341.0000 | 257.0332 | 258.9032 |
| attentionstore-prefetch | 1-3 | 4 | 0.0000 | 1.0000 | 8261.5000 |  | 1.1613 |
| attentionstore-prefetch | 3-10 | 9 | 0.2222 | 0.6667 | 7858 | 37.8813 | 0.6231 |
| attentionstore-prefetch | 10-30 | 16 | 0.8125 | 0.1875 | 12682.0000 | 9.1453 | 2.1826 |
| attentionstore-prefetch | 30-60 | 18 | 1.0000 | 0.0000 | 9610.5000 | 5.5831 |  |
| attentionstore-prefetch | 60-120 | 11 | 1.0000 | 0.0000 | 7751 | 3.4481 |  |
| attentionstore-prefetch | 120+ | 11 | 1.0000 | 0.0000 | 6221 | 34.9276 |  |
| b7-edf-feasibility | 0-1 | 53 | 0.4340 | 0.5094 | 10237 | 169.3928 | 16.1697 |
| b7-edf-feasibility | 1-3 | 7 | 0.1429 | 0.8571 | 9020 | 9.1050 | 1.6723 |
| b7-edf-feasibility | 3-10 | 12 | 0.0000 | 0.9167 | 9772.5000 |  | 6.7207 |
| b7-edf-feasibility | 10-30 | 21 | 0.7619 | 0.1905 | 9914 | 5.0275 | 1.3991 |
| b7-edf-feasibility | 30-60 | 19 | 1.0000 | 0.0000 | 9200 | 3.2163 |  |
| b7-edf-feasibility | 60-120 | 1 | 1.0000 | 0.0000 | 7892 | 3.2952 |  |
| confidence-cascade | 0-1 | 20 | 0.0000 | 1.0000 | 17384.5000 |  | 3.8158 |
| confidence-cascade | 1-3 | 7 | 0.0000 | 1.0000 | 16952 |  | 0.3373 |
| confidence-cascade | 3-10 | 26 | 0.0000 | 1.0000 | 18343.0000 |  | 0.3823 |
| confidence-cascade | 10-30 | 47 | 0.0851 | 0.8723 | 16607 | 4.2592 | 0.6877 |
| confidence-cascade | 30-60 | 26 | 0.5385 | 0.3462 | 16685.0000 | 5.9160 | 0.9618 |
| confidence-cascade | 60-120 | 14 | 1.0000 | 0.0000 | 17644.5000 | 5.8065 |  |
| confidence-cascade | 120+ | 4 | 1.0000 | 0.0000 | 15211.5000 | 6.5076 |  |
| covex-v6-fair-c5attr | 0-1 | 5322 | 0.0000 | 1.0000 | 10001.0000 |  | 0.3552 |
| covex-v6-fair-c5attr | 1-3 | 37 | 0.0000 | 1.0000 | 12727 |  | 0.8006 |
| covex-v6-fair-c5attr | 3-10 | 115 | 0.0000 | 0.9826 | 15851 |  | 0.7229 |
| covex-v6-fair-c5attr | 10-30 | 196 | 0.0102 | 0.9847 | 13868.0000 | 4.3775 | 0.9214 |
| covex-v6-fair-c5attr | 30-60 | 390 | 0.0026 | 0.9795 | 7031.0000 | 5.6851 | 1.1078 |
| covex-v6-fair-c5attr | 60-120 | 10 | 0.1000 | 0.9000 | 8966.0000 | 1.1167 | 1.2103 |
| covex-v6-fair-c5attr | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| covex-v6-fair-c5attr-gain0 | 0-1 | 5086 | 0.0000 | 1.0000 | 10001.0000 |  | 0.5322 |
| covex-v6-fair-c5attr-gain0 | 1-3 | 35 | 0.0000 | 1.0000 | 12514 |  | 1.0166 |
| covex-v6-fair-c5attr-gain0 | 3-10 | 115 | 0.0000 | 0.9913 | 15131 |  | 0.7741 |
| covex-v6-fair-c5attr-gain0 | 10-30 | 196 | 0.0102 | 0.9847 | 13585.5000 | 5.5221 | 1.0758 |
| covex-v6-fair-c5attr-gain0 | 30-60 | 385 | 0.0104 | 0.9714 | 7031 | 1.4656 | 1.2606 |
| covex-v6-fair-c5attr-gain0 | 60-120 | 11 | 0.0909 | 0.9091 | 6041 | 1.7474 | 1.3721 |
| covex-v6-fair-c5attr-gain0 | 120+ | 2 | 0.0000 | 0.5000 | 8487.0000 |  | 1.2389 |
| covex-v6-fair-c5attr-rr | 0-1 | 5518 | 0.0000 | 1.0000 | 10001.0000 |  | 0.3285 |
| covex-v6-fair-c5attr-rr | 1-3 | 32 | 0.0000 | 1.0000 | 11643.0000 |  | 0.5488 |
| covex-v6-fair-c5attr-rr | 3-10 | 112 | 0.0000 | 0.9821 | 15756.5000 |  | 0.5401 |
| covex-v6-fair-c5attr-rr | 10-30 | 204 | 0.0098 | 0.9853 | 13986.5000 | 4.0591 | 0.8426 |
| covex-v6-fair-c5attr-rr | 30-60 | 394 | 0.0051 | 0.9772 | 7031.0000 | 3.3089 | 0.9915 |
| covex-v6-fair-c5attr-rr | 60-120 | 9 | 0.1111 | 0.8889 | 11891 | 0.9332 | 0.9508 |
| covex-v6-fair-c5attr-rr | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| covex-v6-fair-final | 0-1 | 5515 | 0.0000 | 1.0000 | 10001 |  | 0.3366 |
| covex-v6-fair-final | 1-3 | 31 | 0.0000 | 1.0000 | 12514 |  | 0.5487 |
| covex-v6-fair-final | 3-10 | 113 | 0.0000 | 0.9823 | 15662 |  | 0.5734 |
| covex-v6-fair-final | 10-30 | 204 | 0.0098 | 0.9853 | 13585.5000 | 4.1206 | 0.8294 |
| covex-v6-fair-final | 30-60 | 394 | 0.0051 | 0.9772 | 7031.0000 | 3.3619 | 0.9859 |
| covex-v6-fair-final | 60-120 | 8 | 0.1250 | 0.8750 | 12386.0000 | 1.0940 | 0.8215 |
| covex-v6-fair-final | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| covex-v6-fair-final-stateoff | 0-1 | 19 | 0.0000 | 1.0000 | 16751 |  | 2.4605 |
| covex-v6-fair-final-stateoff | 1-3 | 18 | 0.0000 | 1.0000 | 12138.5000 |  | 0.8776 |
| covex-v6-fair-final-stateoff | 3-10 | 23 | 0.0000 | 0.9565 | 17303 |  | 0.8901 |
| covex-v6-fair-final-stateoff | 10-30 | 39 | 0.5128 | 0.4872 | 10994 | 3.1545 | 0.7635 |
| covex-v6-fair-final-stateoff | 30-60 | 92 | 1.0000 | 0.0000 | 7031.0000 | 2.4834 |  |
| covex-v6-fair-final-stateoff | 60-120 | 2 | 1.0000 | 0.0000 | 15266.0000 | 4.0942 |  |
| covex-v6-final | 0-1 | 5864 | 0.0000 | 1.0000 | 10001.0000 |  | 0.3233 |
| covex-v6-final | 1-3 | 29 | 0.0000 | 1.0000 | 11990 |  | 0.5207 |
| covex-v6-final | 3-10 | 110 | 0.0000 | 0.9909 | 15086.0000 |  | 0.5492 |
| covex-v6-final | 10-30 | 190 | 0.0105 | 0.9789 | 13318.5000 | 3.9294 | 0.8151 |
| covex-v6-final | 30-60 | 397 | 0.0076 | 0.9798 | 7031 | 3.8928 | 0.9811 |
| covex-v6-final | 60-120 | 11 | 0.0909 | 0.9091 | 11891 | 0.7649 | 0.8612 |
| covex-v6-final | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| covex-v6-final-nqd | 0-1 | 2689 | 0.0000 | 1.0000 | 10001 |  | 0.3230 |
| covex-v6-final-nqd | 1-3 | 13 | 0.0000 | 1.0000 | 13325 |  | 0.5507 |
| covex-v6-final-nqd | 3-10 | 31 | 0.0000 | 1.0000 | 16142 |  | 0.6108 |
| covex-v6-final-nqd | 10-30 | 56 | 0.0000 | 1.0000 | 12858.0000 |  | 0.8376 |
| covex-v6-final-nqd | 30-60 | 92 | 0.0109 | 0.9674 | 6986.0000 | 0.9450 | 0.9437 |
| covex-v6-final-nqd | 60-120 | 1 | 0.0000 | 1.0000 | 18641 |  | 0.7186 |
| covex-v6-state | 0-1 | 1444 | 0.0000 | 1.0000 | 10001.0000 |  | 0.5218 |
| covex-v6-state | 1-3 | 19 | 0.0000 | 1.0000 | 7835 |  | 0.9525 |
| covex-v6-state | 3-10 | 61 | 0.0000 | 1.0000 | 15041 |  | 0.7539 |
| covex-v6-state | 10-30 | 97 | 0.0000 | 0.9897 | 12832 |  | 0.9991 |
| covex-v6-state | 30-60 | 199 | 0.0050 | 0.9849 | 6941 | 5.5212 | 1.1884 |
| covex-v6-state | 60-120 | 1 | 0.0000 | 1.0000 | 21251 |  | 1.0289 |
| covex-v6-state-final | 0-1 | 5066 | 0.0000 | 1.0000 | 10001.0000 |  | 0.5074 |
| covex-v6-state-final | 1-3 | 36 | 0.0000 | 1.0000 | 12620.5000 |  | 0.7941 |
| covex-v6-state-final | 3-10 | 120 | 0.0000 | 0.9833 | 15486.5000 |  | 0.8356 |
| covex-v6-state-final | 10-30 | 196 | 0.0102 | 0.9847 | 13585.5000 | 4.8463 | 1.0603 |
| covex-v6-state-final | 30-60 | 384 | 0.0078 | 0.9766 | 7031.0000 | 4.2021 | 1.2365 |
| covex-v6-state-final | 60-120 | 12 | 0.0833 | 0.9167 | 6041.0000 | 1.1610 | 1.4533 |
| covex-v6-state-final | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| covex-v6-state-shares | 0-1 | 3601 | 0.0000 | 1.0000 | 9011 |  | 0.3005 |
| covex-v6-state-shares | 1-3 | 17 | 0.0000 | 1.0000 | 8477 |  | 0.4750 |
| covex-v6-state-shares | 3-10 | 50 | 0.0000 | 1.0000 | 11011.0000 |  | 0.4718 |
| covex-v6-state-shares | 10-30 | 108 | 0.0000 | 1.0000 | 11193.0000 |  | 0.7048 |
| covex-v6-state-shares | 30-60 | 229 | 0.0000 | 1.0000 | 5951 |  | 0.9205 |
| covex-v6-state-shares | 60-120 | 53 | 0.0000 | 1.0000 | 7417 |  | 0.9873 |
| covex-v6-state-shares | 120+ | 8 | 0.0000 | 1.0000 | 9731.0000 |  | 1.0755 |
| covex-v6-state-shares-r1 | 0-1 | 2090 | 0.0000 | 1.0000 | 9011.0000 |  | 0.3094 |
| covex-v6-state-shares-r1 | 1-3 | 25 | 0.0000 | 1.0000 | 12514 |  | 0.4190 |
| covex-v6-state-shares-r1 | 3-10 | 87 | 0.0000 | 1.0000 | 14737 |  | 0.5450 |
| covex-v6-state-shares-r1 | 10-30 | 167 | 0.0000 | 0.9940 | 12536 |  | 0.7848 |
| covex-v6-state-shares-r1 | 30-60 | 257 | 0.0000 | 0.9922 | 7867 |  | 0.9539 |
| covex-v6-state-shares-r1 | 60-120 | 43 | 0.0465 | 0.9302 | 6041 | 1.8705 | 1.0320 |
| covex-v6-state-shares-r1 | 120+ | 5 | 0.0000 | 1.0000 | 4061 |  | 0.9465 |
| covex-v6-state-shares-r2 | 0-1 | 2527 | 0.0000 | 1.0000 | 10001 |  | 0.3034 |
| covex-v6-state-shares-r2 | 1-3 | 20 | 0.0000 | 1.0000 | 10050.5000 |  | 0.4533 |
| covex-v6-state-shares-r2 | 3-10 | 87 | 0.0000 | 1.0000 | 14737 |  | 0.5454 |
| covex-v6-state-shares-r2 | 10-30 | 151 | 0.0000 | 0.9934 | 12727 |  | 0.8107 |
| covex-v6-state-shares-r2 | 30-60 | 249 | 0.0000 | 0.9960 | 8522 |  | 0.9791 |
| covex-v6-state-shares-r2 | 60-120 | 36 | 0.0833 | 0.8889 | 4061.0000 | 1.8200 | 1.0263 |
| covex-v6-state-shares-r2 | 120+ | 8 | 0.1250 | 0.8750 | 4556.0000 | 2.5284 | 1.1146 |
| covex-v6-state-uo | 0-1 | 5301 | 0.0000 | 1.0000 | 10001 |  | 0.4903 |
| covex-v6-state-uo | 1-3 | 37 | 0.0000 | 1.0000 | 10985 |  | 0.8090 |
| covex-v6-state-uo | 3-10 | 116 | 0.0000 | 0.9828 | 16023.0000 |  | 0.7577 |
| covex-v6-state-uo | 10-30 | 199 | 0.0100 | 0.9849 | 13775 | 5.6501 | 1.0609 |
| covex-v6-state-uo | 30-60 | 389 | 0.0051 | 0.9769 | 7031 | 3.3686 | 1.1631 |
| covex-v6-state-uo | 60-120 | 11 | 0.0909 | 0.9091 | 6041 | 0.9646 | 1.2877 |
| covex-v6-state-uo | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| covex-v6-state-uo-c5attr | 0-1 | 5096 | 0.0000 | 1.0000 | 10001.0000 |  | 0.5224 |
| covex-v6-state-uo-c5attr | 1-3 | 38 | 0.0000 | 1.0000 | 12635.5000 |  | 0.9433 |
| covex-v6-state-uo-c5attr | 3-10 | 115 | 0.0000 | 0.9826 | 15662 |  | 0.9052 |
| covex-v6-state-uo-c5attr | 10-30 | 198 | 0.0101 | 0.9848 | 13868.0000 | 5.4697 | 1.0549 |
| covex-v6-state-uo-c5attr | 30-60 | 388 | 0.0052 | 0.9768 | 7031.0000 | 3.3065 | 1.2572 |
| covex-v6-state-uo-c5attr | 60-120 | 9 | 0.1111 | 0.8889 | 6041 | 1.3136 | 1.4895 |
| covex-v6-state-uo-c5attr | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| eco-llm | 0-1 | 65 | 0.5385 | 0.4462 | 10918 | 153.5544 | 13.3133 |
| eco-llm | 1-3 | 8 | 0.0000 | 1.0000 | 8890.5000 |  | 1.4519 |
| eco-llm | 3-10 | 14 | 0.2143 | 0.7143 | 10828.0000 | 0.7479 | 6.6221 |
| eco-llm | 10-30 | 25 | 0.8000 | 0.1600 | 9928 | 5.8423 | 1.3973 |
| eco-llm | 30-60 | 24 | 1.0000 | 0.0000 | 9250.5000 | 3.1629 |  |
| eco-llm | 60-120 | 7 | 1.0000 | 0.0000 | 11822 | 8.9432 |  |
| eco-llm | 120+ | 1 | 1.0000 | 0.0000 | 7534 | 0.5046 |  |
| edf | 0-1 | 49 | 0.0000 | 1.0000 | 13331 |  | 0.6407 |
| edf | 1-3 | 3 | 0.0000 | 1.0000 | 16481 |  | 0.7770 |
| edf | 3-10 | 35 | 0.0286 | 0.9429 | 12611 | 6.0469 | 0.9444 |
| edf | 10-30 | 77 | 0.5844 | 0.3117 | 13486 | 4.2393 | 0.9649 |
| edf | 30-60 | 66 | 1.0000 | 0.0000 | 13383.5000 | 4.4621 |  |
| edf | 60-120 | 37 | 1.0000 | 0.0000 | 16661 | 5.7558 |  |
| edf | 120+ | 10 | 1.0000 | 0.0000 | 11223.5000 | 6.4490 |  |
| hybrid-F-lhreq | 0-1 | 17 | 0.0588 | 0.9412 | 11822 | 2.9476 | 1.3607 |
| hybrid-F-lhreq | 1-3 | 14 | 0.0000 | 1.0000 | 9430.0000 |  | 0.6934 |
| hybrid-F-lhreq | 3-10 | 24 | 0.1667 | 0.8333 | 10887.0000 | 0.5230 | 0.5477 |
| hybrid-F-lhreq | 10-30 | 55 | 0.6182 | 0.3455 | 10646 | 2.5042 | 0.6945 |
| hybrid-F-lhreq | 30-60 | 46 | 1.0000 | 0.0000 | 9798.5000 | 2.4879 |  |
| hybrid-F-lhreq | 60-120 | 14 | 1.0000 | 0.0000 | 10743.0000 | 0.8008 |  |
| hybrid-F-lhreq | 120+ | 1 | 1.0000 | 0.0000 | 7534 | 0.4798 |  |
| hybrid-F-lhreq-noc3 | 0-1 | 14 | 0.0000 | 1.0000 | 11827.0000 |  | 1.7132 |
| hybrid-F-lhreq-noc3 | 1-3 | 16 | 0.0000 | 1.0000 | 9430.0000 |  | 0.7429 |
| hybrid-F-lhreq-noc3 | 3-10 | 21 | 0.0476 | 0.9524 | 10312 | 2.7366 | 0.4951 |
| hybrid-F-lhreq-noc3 | 10-30 | 45 | 0.5333 | 0.4222 | 10159 | 2.8741 | 0.6952 |
| hybrid-F-lhreq-noc3 | 30-60 | 36 | 1.0000 | 0.0000 | 9146.0000 | 2.5900 |  |
| hybrid-F-lhreq-noc3 | 60-120 | 4 | 1.0000 | 0.0000 | 7700.0000 | 2.8193 |  |
| kvflow-prefetch | 0-1 | 589 | 0.2241 | 0.7402 | 14051 | 208.6208 | 162.7445 |
| kvflow-prefetch | 1-3 | 2 | 0.0000 | 1.0000 | 8141.0000 |  | 1.3672 |
| kvflow-prefetch | 3-10 | 11 | 0.4545 | 0.5455 | 10108 | 36.5660 | 0.4819 |
| kvflow-prefetch | 10-30 | 19 | 0.7368 | 0.2105 | 10994 | 8.9773 | 1.7870 |
| kvflow-prefetch | 30-60 | 13 | 1.0000 | 0.0000 | 9962 | 10.6945 |  |
| kvflow-prefetch | 60-120 | 5 | 1.0000 | 0.0000 | 10144 | 26.5142 |  |
| llf | 0-1 | 27 | 0.0000 | 1.0000 | 10181 |  | 1.0125 |
| llf | 1-3 | 6 | 0.0000 | 1.0000 | 8966.0000 |  | 0.5489 |
| llf | 3-10 | 21 | 0.0476 | 0.9524 | 10879 | 5.1359 | 0.6549 |
| llf | 10-30 | 37 | 0.6216 | 0.2432 | 10445 | 3.2552 | 0.9877 |
| llf | 30-60 | 39 | 1.0000 | 0.0000 | 9371 | 2.9504 |  |
| llf | 60-120 | 12 | 1.0000 | 0.0000 | 13651.5000 | 4.7449 |  |
| llf | 120+ | 2 | 1.0000 | 0.0000 | 12868.5000 | 5.4010 |  |
| lmcache | 0-1 | 275 | 0.5382 | 0.4218 | 15004 | 270.3297 | 137.3235 |
| lmcache | 1-3 | 2 | 0.5000 | 0.5000 | 12636.5000 | 23.3820 | 0.4999 |
| lmcache | 3-10 | 9 | 0.4444 | 0.5556 | 8899 | 41.0364 | 0.7506 |
| lmcache | 10-30 | 15 | 0.8000 | 0.2000 | 12032 | 7.3327 | 1.9967 |
| lmcache | 30-60 | 15 | 1.0000 | 0.0000 | 9962 | 10.7007 |  |
| lmcache | 60-120 | 4 | 1.0000 | 0.0000 | 10927.5000 | 21.2821 |  |
| mooncake | 0-1 | 52 | 0.4423 | 0.5192 | 10544.0000 | 186.6833 | 15.0608 |
| mooncake | 1-3 | 9 | 0.0000 | 1.0000 | 8899 |  | 1.6972 |
| mooncake | 3-10 | 12 | 0.1667 | 0.8333 | 10717.5000 | 28.0328 | 7.0538 |
| mooncake | 10-30 | 20 | 0.7500 | 0.1500 | 9921.0000 | 6.0213 | 1.0083 |
| mooncake | 30-60 | 22 | 1.0000 | 0.0000 | 8273.0000 | 3.3697 |  |
| mooncake | 60-120 | 1 | 1.0000 | 0.0000 | 7892 | 3.2642 |  |
| querystream-proactive | 0-1 | 216 | 0.5231 | 0.4028 | 15795.0000 | 229.0896 | 166.5515 |
| querystream-proactive | 1-3 | 6 | 0.1667 | 0.8333 | 8350.5000 | 33.0422 | 1.3019 |
| querystream-proactive | 3-10 | 6 | 0.3333 | 0.6667 | 9773.5000 | 38.7186 | 7.5280 |
| querystream-proactive | 10-30 | 15 | 0.8000 | 0.2000 | 12681 | 16.4198 | 2.0503 |
| querystream-proactive | 30-60 | 15 | 1.0000 | 0.0000 | 9200 | 4.5606 |  |
| querystream-proactive | 60-120 | 5 | 1.0000 | 0.0000 | 11822 | 42.0783 |  |
| v5-rules | 0-1 | 8878 | 0.0024 | 0.9866 | 11081.0000 | 19.8202 | 4.4797 |
| v5-rules | 1-3 | 294 | 0.0000 | 0.9966 | 7841.0000 |  | 0.5823 |
| v5-rules | 3-10 | 372 | 0.0349 | 0.9328 | 10696.5000 | 7.9123 | 1.4452 |
| v5-rules | 10-30 | 307 | 0.6547 | 0.2443 | 10541 | 5.0690 | 1.5541 |
| v5-rules | 30-60 | 123 | 1.0000 | 0.0000 | 10991 | 5.1679 |  |
| v5-rules | 60-120 | 54 | 1.0000 | 0.0000 | 10631.0000 | 3.9023 |  |
| v5-rules | 120+ | 8 | 1.0000 | 0.0000 | 10046.0000 | 4.1374 |  |
| v5-rules-2 | 0-1 | 93 | 0.0000 | 0.9892 | 13691 |  | 4.1426 |
| v5-rules-2 | 1-3 | 25 | 0.0400 | 0.9600 | 11852 | 7.0364 | 1.4062 |
| v5-rules-2 | 3-10 | 101 | 0.0594 | 0.9010 | 12614 | 6.2455 | 2.1056 |
| v5-rules-2 | 10-30 | 159 | 0.6352 | 0.2830 | 12007 | 5.2901 | 2.2131 |
| v5-rules-2 | 30-60 | 336 | 1.0000 | 0.0000 | 5951.0000 | 2.7348 |  |
| v5-rules-2 | 60-120 | 17 | 1.0000 | 0.0000 | 11981 | 4.1530 |  |
| v5-rules-2 | 120+ | 2 | 1.0000 | 0.0000 | 13006.0000 | 3.5510 |  |
| warm-all-lru | 0-1 | 3960 | 0.0745 | 0.8788 | 9191.0000 | 241.7569 | 88.6114 |
| warm-all-lru | 1-3 | 30 | 0.1000 | 0.9000 | 2891.0000 | 26.3891 | 0.4963 |
| warm-all-lru | 3-10 | 27 | 0.2593 | 0.7037 | 5951 | 23.7470 | 0.6630 |
| warm-all-lru | 10-30 | 21 | 0.6667 | 0.3333 | 6131 | 13.9144 | 1.3802 |
| warm-all-lru | 30-60 | 16 | 1.0000 | 0.0000 | 9540.0000 | 25.2298 |  |
| warm-all-lru | 60-120 | 22 | 1.0000 | 0.0000 | 6401.0000 | 5.8439 |  |
| warm-all-lru | 120+ | 9 | 1.0000 | 0.0000 | 11981 | 112.8099 |  |

### 1x: robot QUESTION requests only (opportunity_id not null)

| arm | n | P(cold) | P(first token within 3 s) |
|---|---|---|---|
| always-cloud-fcfs | 272 | 0.5809 | 0.0588 |
| attentionstore-prefetch | 226 | 0.5354 | 0.0929 |
| b7-edf-feasibility | 113 | 0.5310 | 0.2566 |
| confidence-cascade | 144 | 0.2500 | 0.6042 |
| covex-v6-fair-c5attr | 458 | 0.0044 | 0.9454 |
| covex-v6-fair-c5attr-gain0 | 457 | 0.0044 | 0.9278 |
| covex-v6-fair-c5attr-rr | 458 | 0.0044 | 0.9563 |
| covex-v6-fair-final | 458 | 0.0044 | 0.9563 |
| covex-v6-fair-final-stateoff | 101 | 0.3168 | 0.7129 |
| covex-v6-final | 441 | 0.0045 | 0.9546 |
| covex-v6-final-nqd | 129 | 0.0000 | 0.9612 |
| covex-v6-state | 230 | 0.0000 | 0.9609 |
| covex-v6-state-final | 457 | 0.0066 | 0.9344 |
| covex-v6-state-shares | 233 | 0.0000 | 0.9700 |
| covex-v6-state-shares-r1 | 371 | 0.0000 | 0.9838 |
| covex-v6-state-shares-r2 | 354 | 0.0000 | 0.9802 |
| covex-v6-state-uo | 457 | 0.0044 | 0.9409 |
| covex-v6-state-uo-c5attr | 456 | 0.0044 | 0.9364 |
| eco-llm | 144 | 0.6250 | 0.3056 |
| edf | 133 | 0.4887 | 0.5188 |
| hybrid-F-lhreq | 171 | 0.5848 | 0.8830 |
| hybrid-F-lhreq-noc3 | 136 | 0.4779 | 0.8309 |
| kvflow-prefetch | 273 | 0.5531 | 0.0586 |
| llf | 103 | 0.5243 | 0.5049 |
| lmcache | 151 | 0.5430 | 0.1126 |
| mooncake | 116 | 0.5431 | 0.2672 |
| querystream-proactive | 263 | 0.5627 | 0.0532 |
| v5-rules | 461 | 0.2516 | 0.3905 |
| v5-rules-2 | 292 | 0.3493 | 0.5103 |
| warm-all-lru | 221 | 0.5656 | 0.0633 |

## kv0.5r: per arm, per gap bucket

n, P(cold), P(warm), median previous prompt tokens, median first-token s for cold / warm.

| arm | bucket | n | P(cold) | P(warm) | med_prev_tok | med_ttft_cold_s | med_ttft_warm_s |
|---|---|---|---|---|---|---|---|
| confidence-cascade | 0-1 | 9 | 0.0000 | 1.0000 | 22260 |  | 3.7440 |
| confidence-cascade | 1-3 | 4 | 0.0000 | 1.0000 | 18904.5000 |  | 0.5253 |
| confidence-cascade | 3-10 | 11 | 0.0000 | 0.9091 | 21766 |  | 0.6071 |
| confidence-cascade | 10-30 | 17 | 0.0588 | 0.8824 | 21127 | 6.9300 | 0.8074 |
| confidence-cascade | 30-60 | 12 | 0.4167 | 0.3333 | 14721.0000 | 4.9030 | 0.9333 |
| confidence-cascade | 60-120 | 6 | 1.0000 | 0.0000 | 17391.5000 | 5.8182 |  |
| confidence-cascade | 120+ | 3 | 1.0000 | 0.0000 | 16496 | 6.0417 |  |
| covex-v6-base | 0-1 | 9 | 0.0000 | 1.0000 | 11900 |  | 1.4593 |
| covex-v6-base | 1-3 | 9 | 0.0000 | 1.0000 | 8477 |  | 1.0734 |
| covex-v6-base | 3-10 | 12 | 0.0000 | 1.0000 | 11531.5000 |  | 0.6878 |
| covex-v6-base | 10-30 | 22 | 0.5909 | 0.4091 | 10133.5000 | 2.9523 | 0.6908 |
| covex-v6-base | 30-60 | 19 | 1.0000 | 0.0000 | 9092 | 2.6304 |  |
| covex-v6-base | 60-120 | 4 | 1.0000 | 0.0000 | 7700.0000 | 2.8592 |  |
| covex-v6-fair-final | 0-1 | 5096 | 0.0000 | 1.0000 | 10001.0000 |  | 0.4099 |
| covex-v6-fair-final | 1-3 | 46 | 0.0000 | 1.0000 | 13041.0000 |  | 0.7308 |
| covex-v6-fair-final | 3-10 | 121 | 0.0000 | 0.9752 | 15662 |  | 0.7820 |
| covex-v6-fair-final | 10-30 | 198 | 0.0051 | 0.9899 | 13134.0000 | 5.0805 | 0.9519 |
| covex-v6-fair-final | 30-60 | 396 | 0.0101 | 0.9798 | 7031.0000 | 5.4714 | 1.0594 |
| covex-v6-fair-final | 60-120 | 7 | 0.1429 | 0.8571 | 11891 | 0.9311 | 0.7330 |
| covex-v6-fair-final | 120+ | 1 | 0.0000 | 0.0000 | 13543 |  |  |
| covex-v6-fair-final-notouch | 0-1 | 14 | 0.0000 | 1.0000 | 16997.0000 |  | 0.9196 |
| covex-v6-fair-final-notouch | 1-3 | 14 | 0.0000 | 1.0000 | 13041.0000 |  | 1.2660 |
| covex-v6-fair-final-notouch | 3-10 | 31 | 0.0000 | 1.0000 | 16592 |  | 0.7791 |
| covex-v6-fair-final-notouch | 10-30 | 54 | 0.0000 | 0.9815 | 12858.0000 |  | 0.9375 |
| covex-v6-fair-final-notouch | 30-60 | 100 | 0.0200 | 0.9700 | 7972.5000 | 5.0579 | 0.8873 |
| covex-v6-fair-final-notouch | 60-120 | 1 | 0.0000 | 1.0000 | 18641 |  | 0.4859 |
| covex-v6-fair-final-stateoff | 0-1 | 19 | 0.0000 | 1.0000 | 13691 |  | 1.4705 |
| covex-v6-fair-final-stateoff | 1-3 | 18 | 0.0000 | 1.0000 | 12138.5000 |  | 1.1450 |
| covex-v6-fair-final-stateoff | 3-10 | 25 | 0.0000 | 0.9600 | 20074 |  | 0.9996 |
| covex-v6-fair-final-stateoff | 10-30 | 40 | 0.5000 | 0.5000 | 10992.5000 | 3.2602 | 0.7055 |
| covex-v6-fair-final-stateoff | 30-60 | 90 | 1.0000 | 0.0000 | 7031.0000 | 2.2553 |  |
| covex-v6-fair-final-stateoff | 60-120 | 2 | 1.0000 | 0.0000 | 15266.0000 | 3.8488 |  |
| covex-v6-final-nqd | 0-1 | 1271 | 0.0000 | 1.0000 | 10001 |  | 0.4135 |
| covex-v6-final-nqd | 1-3 | 14 | 0.0000 | 1.0000 | 9818.0000 |  | 1.2290 |
| covex-v6-final-nqd | 3-10 | 34 | 0.0000 | 1.0000 | 9334.5000 |  | 1.2050 |
| covex-v6-final-nqd | 10-30 | 36 | 0.0000 | 0.9722 | 10011.0000 |  | 1.0228 |
| covex-v6-final-nqd | 30-60 | 86 | 0.0000 | 1.0000 | 6941.0000 |  | 0.9671 |
| covex-v6-final-nqd | 60-120 | 8 | 0.1250 | 0.8750 | 11401.5000 | 2.1144 | 1.2317 |
| covex-v6-rules | 0-1 | 24 | 0.0417 | 0.9583 | 15983.0000 | 26.3879 | 4.4479 |
| covex-v6-rules | 1-3 | 15 | 0.0000 | 0.9333 | 11852 |  | 1.7906 |
| covex-v6-rules | 3-10 | 19 | 0.0526 | 0.7895 | 12614 | 20.8666 | 2.0139 |
| covex-v6-rules | 10-30 | 41 | 0.5366 | 0.3171 | 10879 | 3.5834 | 1.7408 |
| covex-v6-rules | 30-60 | 75 | 1.0000 | 0.0000 | 6041 | 2.3488 |  |
| covex-v6-rules | 60-120 | 8 | 1.0000 | 0.0000 | 12774.0000 | 4.4727 |  |
| covex-v6-rules | 120+ | 1 | 1.0000 | 0.0000 | 7031 | 3.3044 |  |
| eco-llm | 0-1 | 21 | 0.0000 | 1.0000 | 11458 |  | 4.5445 |
| eco-llm | 1-3 | 9 | 0.1111 | 0.8889 | 7835 | 12.4990 | 2.9787 |
| eco-llm | 3-10 | 29 | 0.0345 | 0.9655 | 10789 | 13.4380 | 4.7229 |
| eco-llm | 10-30 | 37 | 0.8378 | 0.1351 | 10730 | 3.8083 | 2.6029 |
| eco-llm | 30-60 | 36 | 1.0000 | 0.0000 | 9559.5000 | 2.9719 |  |
| eco-llm | 60-120 | 12 | 1.0000 | 0.0000 | 11282.5000 | 1.8776 |  |
| llf | 0-1 | 16 | 0.0000 | 1.0000 | 8606.0000 |  | 0.7057 |
| llf | 1-3 | 7 | 0.0000 | 1.0000 | 8381 |  | 1.0254 |
| llf | 3-10 | 16 | 0.0000 | 1.0000 | 10021.5000 |  | 1.0329 |
| llf | 10-30 | 31 | 0.6774 | 0.3226 | 11255 | 3.3214 | 0.8172 |
| llf | 30-60 | 29 | 1.0000 | 0.0000 | 9101 | 2.6649 |  |
| llf | 60-120 | 5 | 1.0000 | 0.0000 | 12515 | 4.7459 |  |
| llf | 120+ | 2 | 1.0000 | 0.0000 | 12589.5000 | 5.0174 |  |
| mooncake | 0-1 | 20 | 0.0000 | 1.0000 | 11640.0000 |  | 4.0819 |
| mooncake | 1-3 | 9 | 0.0000 | 1.0000 | 7835 |  | 2.9680 |
| mooncake | 3-10 | 28 | 0.0000 | 0.9286 | 10717.5000 |  | 4.0890 |
| mooncake | 10-30 | 30 | 0.7667 | 0.1667 | 10139.5000 | 3.8494 | 1.6404 |
| mooncake | 30-60 | 31 | 1.0000 | 0.0000 | 9242 | 3.1676 |  |
| mooncake | 60-120 | 3 | 1.0000 | 0.0000 | 7508 | 3.1567 |  |

### kv0.5r: robot QUESTION requests only (opportunity_id not null)

| arm | n | P(cold) | P(first token within 3 s) |
|---|---|---|---|
| confidence-cascade | 62 | 0.2419 | 0.5968 |
| covex-v6-base | 75 | 0.4800 | 0.8400 |
| covex-v6-fair-final | 460 | 0.0022 | 0.9391 |
| covex-v6-fair-final-notouch | 130 | 0.0000 | 0.9308 |
| covex-v6-fair-final-stateoff | 101 | 0.3267 | 0.7228 |
| covex-v6-final-nqd | 74 | 0.0000 | 0.9189 |
| covex-v6-rules | 90 | 0.3333 | 0.5333 |
| eco-llm | 144 | 0.5625 | 0.4028 |
| llf | 67 | 0.5522 | 0.5522 |
| mooncake | 121 | 0.4711 | 0.3719 |

## Cells used

152 cells. Any with agreement ABSENT are marked here; INVALID cells were excluded (never used).

- agreement ABSENT: 133 cells.
- _rerun cells used (superseding a plain): always-cloud-fcfs s5 1x, confidence-cascade s4 1x, confidence-cascade s5 1x, confidence-cascade s6 1x, confidence-cascade s7 1x, covex-v6-fair-final-stateoff s4 kv0.5r, covex-v6-final s4 1x, covex-v6-state s4 1x, eco-llm s4 1x, eco-llm s6 1x, eco-llm s7 1x, simplestream s4 1x, simplestream s5 1x, simplestream s6 1x, simplestream s7 1x, v5-rules s7 1x.

Full per-cell and per-bucket data: results/orchestration/live2/robot_idle/robot_idle_survival.json
