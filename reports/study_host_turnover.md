# Host-tier KV offload turnover per cell

CPU only, read-only, no images. D240: 1x and kv0.5r reported separately, never pooled. Steady-state rate of vllm:kv_offload_store_bytes_total over the MIDDLE 60% of the run, at 262,144 bytes/token; turnover = 110,592 / rate tokens.

## The planner "337 tokens/s for BOTH rung-3 1x s4 and kv0.5r s4"

Recomputed honestly over the middle 60%: 1x s4 = **342.577 tok/s** (turnover 322.823 s), kv0.5r s4 = **343.362 tok/s** (turnover 322.086 s). They are NOT identical (they differ by about 0.2 percent), so the planner's EXACTLY equal 337 for both was the artefact: a genuinely distinct pair cannot both be 337 to the digit. The true rates are close because the host-offload store fills to about 1.05e11 bytes at both memory levels over the run, but they are distinct cells with distinct slopes. Window: 69 samples each; store first/last 1x [2940207104.0, 105407053824.0], kv0.5r [1300234240.0, 104865988608.0].

## 1x: per cell

| arm | seed | agreement | rate tok/s | turnover s | n window | window dbytes |
|---|---|---|---|---|---|---|
| cascade-routing | 4 | ABSENT | 4062.786 | 27.221 | 69 | 741758468096.0 |
| cascade-routing | 5 | ABSENT | 4049.304 | 27.311 | 69 | 740273684480.0 |
| cascade-routing | 6 | ABSENT | 4058.857 | 27.247 | 69 | 741263540224.0 |
| cascade-routing | 7 | ABSENT | 4073.294 | 27.151 | 69 | 744392491008.0 |
| confidence-cascade | 4 | ABSENT | 2369.316 | 46.677 | 70 | 430151041024.0 |
| confidence-cascade | 5 | ABSENT | 2562.07 | 43.165 | 69 | 468143046656.0 |
| confidence-cascade | 6 | ABSENT | 2678.902 | 41.283 | 69 | 488858714112.0 |
| confidence-cascade | 7 | ABSENT | 2678.874 | 41.283 | 69 | 488753856512.0 |
| covex-v6-fair-final-stateoff | 4 | OK | 4353.55 | 25.403 | 69 | 796397666304.0 |
| covex-v6-fair-final | 4 | ABSENT | 342.577 | 322.823 | 69 | 62583209984.0 |
| covex-v6-fair-final | 5 | ABSENT | 348.601 | 317.246 | 69 | 63686311936.0 |
| covex-v6-fair-final | 6 | ABSENT | 407.346 | 271.494 | 69 | 74432118784.0 |
| covex-v6-fair-final | 7 | ABSENT | 240.796 | 459.276 | 69 | 43994054656.0 |
| covex-v6-final-nqd | 4 | OK | 328.848 | 336.301 | 69 | 60079210496.0 |
| covex-v6-final | 4 | OK | 342.169 | 323.209 | 69 | 62574821376.0 |
| covex-v6-final | 5 | ABSENT | 364.848 | 303.118 | 69 | 66672656384.0 |
| covex-v6-final | 6 | ABSENT | 404.36 | 273.499 | 69 | 73895247872.0 |
| covex-v6-final | 7 | ABSENT | 238.507 | 463.684 | 69 | 43557847040.0 |
| covex-v6-state-final | 4 | ABSENT | 341.181 | 324.144 | 69 | 62318968832.0 |
| covex-v6-state-final | 5 | ABSENT | 355.236 | 311.32 | 69 | 64869105664.0 |
| covex-v6-state-final | 6 | ABSENT | 407.428 | 271.439 | 69 | 74482450432.0 |
| covex-v6-state-final | 7 | ABSENT | 240.928 | 459.025 | 69 | 43994054656.0 |
| eco-llm | 4 | ABSENT | 3302.728 | 33.485 | 70 | 612477435904.0 |
| eco-llm | 5 | ABSENT | None | None | 0 | None |
| eco-llm | 6 | ABSENT | 4189.789 | 26.396 | 69 | 766211260416.0 |
| eco-llm | 7 | OK | 4584.493 | 24.123 | 69 | 838130991104.0 |
| simplestream | 4 | ABSENT | 4387.583 | 25.206 | 69 | 801942536192.0 |
| simplestream | 5 | ABSENT | 4370.325 | 25.305 | 69 | 798050222080.0 |
| simplestream | 6 | ABSENT | 4388.125 | 25.203 | 69 | 801384693760.0 |
| simplestream | 7 | ABSENT | 4379.949 | 25.25 | 69 | 800386449408.0 |

## kv0.5r: per cell

| arm | seed | agreement | rate tok/s | turnover s | n window | window dbytes |
|---|---|---|---|---|---|---|
| confidence-cascade | 4 | ABSENT | 2368.037 | 46.702 | 70 | 438409625600.0 |
| confidence-cascade | 5 | OK | 2563.658 | 43.138 | 70 | 474577108992.0 |
| covex-v6-base | 4 | ABSENT | 4471.493 | 24.733 | 69 | 817297883136.0 |
| covex-v6-base | 5 | WARNING moved_after_import | 4475.761 | 24.709 | 69 | 819508281344.0 |
| covex-v6-fair-final-notouch | 4 | OK | 348.087 | 317.714 | 69 | 63615008768.0 |
| covex-v6-fair-final-stateoff | 4 | OK | 4293.765 | 25.756 | 69 | 784615866368.0 |
| covex-v6-fair-final | 4 | ABSENT | 343.362 | 322.086 | 69 | 62688067584.0 |
| covex-v6-fair-final | 5 | ABSENT | 357.316 | 309.507 | 69 | 65338867712.0 |
| covex-v6-fair-final | 6 | WARNING moved_after_import | 405.988 | 272.402 | 69 | 74205626368.0 |
| covex-v6-fair-final | 7 | OK | 240.554 | 459.739 | 69 | 43994054656.0 |
| covex-v6-final-nqd | 4 | OK | 308.085 | 358.966 | 69 | 56274976768.0 |
| covex-v6-rules | 4 | ABSENT | 4736.914 | 23.347 | 69 | 865419132928.0 |
| eco-llm | 4 | ABSENT | 4732.881 | 23.367 | 69 | 864659963904.0 |
| eco-llm | 5 | WARNING moved_after_import | 4640.647 | 23.831 | 69 | 848620945408.0 |
| eco-llm | 6 | OK | 4683.333 | 23.614 | 69 | 856619483136.0 |
| llf | 4 | ABSENT | 4510.179 | 24.521 | 69 | 824419811328.0 |
| llf | 5 | OK | 4474.385 | 24.717 | 68 | 807302856704.0 |
| llf | 6 | OK | 4527.86 | 24.425 | 69 | 827703951360.0 |
| mooncake | 4 | ABSENT | 4677.751 | 23.642 | 70 | 868405477376.0 |
| mooncake | 5 | OK | 4572.006 | 24.189 | 69 | 835111092224.0 |
| mooncake | 6 | OK | 4658.935 | 23.738 | 69 | 851926056960.0 |
| simplestream | 4 | ABSENT | 4384.534 | 25.223 | 69 | 799778275328.0 |
| simplestream | 5 | OK | 4365.456 | 25.333 | 69 | 798524178432.0 |
| simplestream | 6 | WARNING moved_after_import | 4384.041 | 25.226 | 69 | 801778958336.0 |

Full data: results/orchestration/live2/robot_idle/host_turnover.json
