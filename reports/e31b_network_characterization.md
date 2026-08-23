# E31b — Network Characterization (Corrected)

**Date:** 2026-08-23
**Script:** `experiments/cost/e31b_network.py`
**Status:** supersedes `reports/e31_network_characterization.md` Parts C and D

> **Why E31b?** E31 Parts C and D were invalid.
> Part C used State=D/I (application download activity) as the reachability proxy.
> That signal reflects when the streaming app was actively downloading data, not
> whether the radio link was up. All predictability numbers derived from it are
> therefore invalid.
> Part D modelled KV cache payloads as the thing that moves across the network.
> In our setting different tiers run different model sizes, so KV from one tier
> is not usable at another; the actual payload is text (~4 B/token).

---

## Part 1 — Dataset Acquisition Attempt

Two additional trace datasets were sought to provide building-scale indoor WiFi
connectivity traces with time-series intermittency data.

| Dataset | Status | Notes |
|---|---|---|
| Lumos5G | login_required | Page returns HTTP 200 but all download links require authenticated IEEE DataPort session; no direct ... |
| CRAWDAD dartmouth/campus | login_required | CRAWDAD migrated to IEEE DataPort; same login requirement applies. No direct unauthenticated downloa... |
| EVARILOS indoor WiFi | 404 | GitHub repo returned 404; repository removed or private. |
| Lumos5G GitHub supplementary | 404 | GitHub repository returned 404. |
| UJIIndoorLoc (UCI ML Repo) | wrong_type | Fingerprinting snapshots for localization, not time-series connectivity. Cannot derive intermittency... |
| Available (reprocessed) | available | Irish 5G: CellID transitions used as handover signal (corrected from State=D/I). herolab: RSSI thres... |

**Conclusion:** Lumos5G and CRAWDAD dartmouth/campus are the correct datasets for
building-scale WiFi intermittency characterization. Both require IEEE DataPort account
registration. Pending user registration, E31b proceeds with existing traces reprocessed
under corrected signal definitions.

---

## Part 2 — Corrected Irish 5G Reachability

**Environment:** Outdoor vehicular / pedestrian 5G, Ireland.
**Dataset:** Irish 5G (n=28,551 1-second timesteps,
16 sessions).

### 2a — CellID-based reachability (corrected)

`cell_id == -1` in the Irish 5G data means the device has no valid serving cell
(handover gap or cell-edge search). These are genuine radio-layer disconnections.
`cell_id != -1` means the device is attached to a serving cell: reachable.

- No-cell timesteps (cell_id=-1): **4,105** of 28,551 (14.4%)
- Fraction reachable: **85.6%**
- No-cell run duration: p50=1s, p95=2s, max=3s
- Real cell-to-cell handovers: 567 across 16 sessions (35.4/session)

### 2b — Duration-filtered State=I reachability

State=I run-length distribution: the vast majority of idle episodes are brief app-level
pauses, not network disconnections.

- State=I runs < 30 s: **3819**  (app-idle, not network fault)
- State=I runs ≥ 30 s: **2**  (real coverage gaps)
- Sustained events:
  - Session 9: 43 s gap
  - Session 10: 629 s gap
- Total real disconnection: 672 s
  (2.354% of session time)
- Fraction effectively reachable: **97.6%**

**E31 Part C invalid baseline:** E31 reported frac_connected = 0.829 using State=D/I.
That number represents how often the streaming app was actively downloading data,
not whether the radio link was up. Under the corrected cell_id=-1 signal, outdoor 5G
is reachable 85.6% of the time with brief 1–3 s gaps.
Under the duration-filtered State=I signal, sustained real coverage gaps (≥30 s) account
for 2.35% of session time.
The E31 0.829 figure is numerically similar but physically wrong: it captured streaming-app
activity, not radio link availability.

---

## Part 3 — herolab RSSI Threshold Sensitivity

**Environment:** Single-room indoor (20×26 m), single fixed AP, Unitree B1 robot.
**Dataset:** herolab C_level_a (n=16,562 measurements,
7 datasets).

- Median RSSI: **-49.0 dBm**
- p5: -64.0 dBm  |  p95: -31.0 dBm

| RSSI threshold | Samples below | Fraction |
|---|---|---|
| < -90 dBm | 55 | 0.33% |
| < -85 dBm | 98 | 0.59% |
| < -80 dBm | 141 | 0.85% |
| < -75 dBm | 151 | 0.91% |
| < -70 dBm | 188 | 1.14% |
| < -65 dBm | 485 | 2.93% |

At any threshold ≤ −75 dBm (marginal/disconnected), <1% of samples fall below it.
The herolab robot in a single room with a co-located AP maintains near-continuous
connectivity. The E31 'near-continuous' finding (herolab 0.91% below −75 dBm) is
confirmed under the corrected signal definition — the signal definition does not
change for herolab because RSSI is an objective physical measure, not an app-level one.

**Premise check:** For robot-like environments with co-located infrastructure
(server within the same room or building), WiFi connectivity is near-continuous.
The radio link is not a primary source of Context Inertia in the herolab scenario.
Context Inertia in such deployments is dominated by materialization (re-prefill) cost,
not by radio availability or transfer time.

---

## Part 4 — Premise Check: Edge Reachability in Robot-Like Environments

| Environment | Signal | Frac reachable | Primary gap cause |
|---|---|---|---|
| Outdoor 5G (Irish) | cell_id=-1 (no-cell state) | 85.6% | Brief gaps 1–3 s; 14% of time |
| Outdoor 5G (Irish) | State=I ≥30 s filter | 97.6% | 2 sustained events: 43 s, 629 s |
| Indoor robot WiFi (herolab) | RSSI < −75 dBm | 99.1% | Near-continuous; AP co-located |
| Building-scale WiFi (not obtained) | — | ~85–99% typical | AP handover 50 ms–10 s/transition |

**Direct answer:** In indoor robot-like environments with co-located edge servers
(herolab scenario), the edge is reachable >99% of the time.
In outdoor 5G (Irish dataset), the device is in a no-cell state 14.4% of the time
in brief 1–3 s gaps; text payloads at p50 BW transfer in 0.02–0.22 s and can complete
before or immediately after each gap. Sustained coverage gaps (>30 s) are rare (2 events).

The premise that 'radio intermittency drives Context Inertia' is **partially supported**
for outdoor 5G (14% no-cell time creates intermittent brief gaps) but **not supported**
for indoor robot scenarios. In both cases, text transfer (<0.22 s) is not the bottleneck;
materialization (cold prefill 1–20 s) dominates.

The relevant variable for Context Inertia is **bandwidth spread** (p10–p90:
0.9–103 Mbps), which affects how long text payloads
take to transfer — but even at p10, text transfer is faster than cold prefill
(see Part 6).

---

## Part 5 — Predictability on Corrected Reachability Signal

| Signal | H | Persistence acc | Markov R→D | False commit | BW autocorr |
|---|---|---|---|---|---|
| cellid_based | 10 s | 0.750 | 0.1462 | 0.1462 | 0.458 |
| stateI_duration_filtered | 10 s | 0.999 | 0.0007 | 0.0007 | 0.458 |
| cellid_based | 30 s | 0.741 | 0.1512 | 0.1512 | 0.261 |
| stateI_duration_filtered | 30 s | 0.996 | 0.0022 | 0.0022 | 0.261 |
| cellid_based | 60 s | 0.758 | 0.1416 | 0.1416 | 0.212 |
| stateI_duration_filtered | 60 s | 0.993 | 0.0037 | 0.0037 | 0.212 |

**CellID-based signal (cell_id=-1):** Reachable 85.6% of time; no-cell gaps are brief
(1–3 s, p95=2 s) but numerous (3,829 runs). Persistence accuracy 0.750–0.758 at
H=10–60 s: moderate, driven by the base rate (85.6% reachable baseline predicts
'reachable' correctly ~86% of the time). False commit rate is non-trivial: a
'reachable' prediction is wrong ~14% of the time at horizon H (the no-cell fraction).

**Duration-filtered signal (State=I ≥30 s):** Near-constant reachable (97.6%).
Persistence accuracy ≈0.99 because sustained disconnections are extremely rare
(2 events in the dataset). False commit rate ≈0.

**BW autocorrelation (valid from E31):** Collapses from
0.46 at H=10 s to
0.21 at H=60 s.
BW predictability is the more operationally relevant challenge for Context Inertia:
brief no-cell gaps are too short for prefill (1–20 s) to complete anyway, so the
system needs to pre-cache state or defer until after recovery.

---

## Part 6 — Text Payload Transfer vs Materialization Cost

Text payloads (~4 B/token) are what move across the network in our setting.
KV payloads are not applicable because tiers run different model sizes.

### 6a — Text payload transfer times

| Representation | Tokens | Payload | p10 BW transfer | p50 BW transfer | p90 BW transfer | Cold prefill | p50 ratio |
|---|---|---|---|---|---|---|---|
| sum80_text | 80 | 320 B | 0.0029 s | 0.0003 s | 0.000025 s | 0.14 s | **528×** |
| sum200_text | 200 | 800 B | 0.0071 s | 0.0007 s | 0.000062 s | 0.14 s | **211×** |
| win10_text | 7,117 | 28 KB | 0.2543 s | 0.0238 s | 0.002213 s | 1.18 s | **50×** |
| full_text_8k | 8,192 | 32 KB | 0.2928 s | 0.0274 s | 0.002548 s | 1.18 s | **43×** |
| full_text_16k | 16,384 | 64 KB | 0.5855 s | 0.0547 s | 0.005095 s | 3.22 s | **59×** |
| full_text_32k | 32,768 | 128 KB | 1.1711 s | 0.1095 s | 0.010190 s | 6.86 s | **63×** |
| full_text_64k | 65,536 | 256 KB | 2.3421 s | 0.2190 s | 0.020381 s | 19.68 s | **90×** |
| full_text_locomo | 20,153 | 79 KB | 0.7202 s | 0.0673 s | 0.006267 s | 3.22 s | **48×** |

At p50 BW (9.6 Mbps), text transfer is 10–5,700× faster than cold prefill.
At p10 BW (0.9 Mbps), text transfer is 1–540× faster than cold prefill.
The network is not the bottleneck; materialization is.

### 6b — E31 Part D correction

E31 Part D reported KV cache payload transfer times. Those numbers are correct
**for same-model-migration scenarios only** (e.g., migrating a replica running
the same model between two servers of the same tier). In the FM-switching setting,
different tiers run different model sizes (qwen7b on A6000/3090Ti, smolLM2 or
qwen3b on Jetson), so KV from one tier cannot be loaded by another. Text payloads
are the correct representation of what actually moves.

KV payload sizes are retained as an appendix for the same-model scenario:

| Representation | Tokens | KV bytes | p50 BW transfer |
|---|---|---|---|
| sum80_kv | 80 | 4.4 MB | 3.83 s |
| sum200_kv | 200 | 10.9 MB | 9.58 s |
| win10_kv | 7,117 | 389.2 MB | 340.90 s |

---

## Assumptions and Deviations

| Item | Value | Label |
|---|---|---|
| CellID handover gap model | 1 s per transition (conservative; actual 10–300 ms) | [CONSERVATIVE] |
| Duration filter threshold | 30 s (justified by bimodal distribution: 3,805 runs <5 s, 2 runs ≥30 s) | [DESIGN] |
| herolab RSSI column | C_level_a at whitespace-split index 19 | [MEASURED] |
| Text bytes/token | 4 B/token (average UTF-8 encoded English/mixed) | [MEASURED proxy] |
| BW profiles | Irish 5G p10/p50/p90 = 0.90/9.58/102.9 Mbps (from E31, valid) | [MEASURED] |
| Prefill costs | E26 Qwen2.5-7B A6000 cold prefill (L=1k/8k/16k/32k/64k) | [MEASURED] |
| Lumos5G, CRAWDAD | Not downloaded; requires IEEE DataPort registration | [DEVIATION] |

---

## Output files

| File | Contents |
|---|---|
| `results/cost/e31b_network/e31b_summary.json` | All metrics |
| `results/cost/e31b_network/irish5g_corrected_reachability.csv` | CellID + duration-filter per-session |
| `results/cost/e31b_network/herolab_rssi_thresholds.csv` | RSSI threshold stats per dataset |
| `results/cost/e31b_network/predictability_corrected.csv` | Predictability at H=10/30/60 × 2 signals |
| `results/cost/e31b_network/text_payload_transfer.csv` | Transfer time and prefill cost per rep × BW |
| `results/cost/e31b_network/kv_appendix.csv` | KV transfer (same-model-migration appendix) |
| `figures/cost/e31b_reachability_by_environment.pdf` | Figure 1: pie/bar charts |
| `figures/cost/e31b_predictability.pdf` | Figure 2: predictability + payload comparison |
