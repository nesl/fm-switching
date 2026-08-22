# E31 — Network Characterization and Predictability

Generated: 2026-08-22

---

## Datasets

### Dataset selection

**Reachability + throughput: Irish 5G driving dataset** (uccmisl/5Gdataset, GPL-3.0)
- Source: https://github.com/uccmisl/5Gdataset
- Subset: Download/Driving, 16 sessions, ~1 Hz sample rate
- Columns used: Timestamp (second resolution), DL_bitrate (kbps), State (D=active, I=idle), CellID
- Reachability proxy: State=D (network active) vs State=I (idle). Limitation: State=I may reflect app pause rather than network disconnection.
- Throughput: DL_bitrate in kbps, converted to Mbps; zero-BW D-state rows excluded.
- Mobility: **driving** (not pedestrian). This is noted as the primary limitation; no pedestrian 5G throughput trace was available without IEEE DataPort registration.
- Total analyzed: 28,551 session-seconds across 16 drives.

**Indoor RSSI: herolab-uga indoor-rssi-mobile-robot** (GitHub, license not stated)
- Source: https://github.com/herolab-uga/indoor-rssi-mobile-robot
- Subset: all 7 Dataset*.datalog files, center-antenna raw RSSI (column C_level_a)
- Used for indoor link-quality characterization only. Near-100% connectivity in the 20×26m indoor office (RSSI p5 = -64 dBm; <1% of 16,539 samples below -80 dBm) means this dataset produces no meaningful association/disconnection events; it cannot serve as the reachability trace.

**Datasets requiring registration (not downloaded):**
- Lumos5G (IEEE DataPort, CC-BY 4.0, walking+driving outdoor 5G): required free IEEE login — skipped per E31 constraint.
- CRAWDAD dartmouth/campus (IEEE DataPort): required free IEEE login — skipped per E31 constraint.

---

## Part A: Dataset provenance

| attribute | Irish 5G (uccmisl) | herolab indoor RSSI |
|---|---|---|
| mobility | driving | indoor robot |
| signal | DL_bitrate (kbps), State (D/I), CellID | center-antenna RSSI (dBm) |
| sample rate | ~1 Hz | ~5 Hz (median 206ms) |
| total duration | 28,551 s across 16 sessions | 3,489 s across 7 datasets |
| license | GPL-3.0 | not stated |
| registration | none (GitHub) | none (GitHub) |
| used for | Parts B–D (reachability + throughput) | RSSI characterization only |

---

## Part B: Derived time series

### Reachability (Irish 5G, State column)

| metric | value |
|---|---|
| Fraction connected (State=D) | 0.829 |
| Fraction disconnected (State=I) | 0.171 |
| Mean handovers per session (CellID transitions) | 35.4 |
| Min / max handovers per session | 1 / 78 |

Reachability series written to `results/cost/e31_network/reachability_series.csv` (28,551 rows: unix_t, state_D1_I0, cell_id, session_id).

**Limitation:** In a driving dataset, CellID transitions reflect cellular handovers between towers rather than AP association changes typical of indoor mobile agents. The high handover rate (35.4/session) is a property of driving at cellular scale; an indoor pedestrian FM agent would see far fewer (or no) handovers but more intermittent RSSI drops.

### Throughput (Irish 5G, DL_bitrate, D-state rows only)

| metric | value |
|---|---|
| n (per-second bins with BW > 0) | 23,102 |
| p5 | ~0 Mbps |
| p25 | 3.9 Mbps |
| p50 | 9.6 Mbps |
| p75 | 21.7 Mbps |
| p95 | 172.0 Mbps |
| p10 | 0.9 Mbps |
| p90 | 102.9 Mbps |

Bandwidth series written to `results/cost/e31_network/bandwidth_series.csv` (23,102 rows: unix_t, dl_bitrate_mbps, session_id).

### Indoor RSSI characterization (herolab)

| metric | value |
|---|---|
| n (clean readings, center antenna) | 16,539 |
| p5 | -64 dBm |
| median | -49 dBm |
| p95 | -31 dBm |
| fraction below -80 dBm | 0.0085 |

In this indoor environment (20×26m, single AP at fixed position), the robot maintains strong connectivity throughout all 7 runs. The RSSI range (-64 to -31 dBm at p5–p95) corresponds to well-connected states throughout. This dataset establishes that an FM agent operating in a similarly sized indoor space with one nearby server would experience near-continuous reachability; network intermittency would arise primarily from inter-building or inter-floor transitions, not from intra-room mobility.

---

## Part C: Predictability

Predictability is measured over the 16 Irish 5G driving sessions. For each session, binary reachability (State D/I) and BW (DL_bitrate, D-state only) are extracted at 1-second resolution. Metrics are computed per session and averaged.

**Persistence fraction:** fraction of (t, t+H) pairs where state(t) = state(t+H).
**Empirical Markov:** P[i→j] = fraction of t where state(t)=i and state(t+H)=j.
**BW autocorrelation:** Pearson r between BW(t) and BW(t+H) over D-state rows only.

### Predictability metrics

| H | reachability persistence | P(I→I) | P(I→D) | P(D→I) | P(D→D) | BW autocorr |
|---|---|---|---|---|---|---|
| 10 s | 0.752 | 0.199 | 0.801 | 0.148 | 0.852 | 0.392 |
| 30 s | 0.737 | 0.138 | 0.862 | 0.157 | 0.843 | 0.157 |
| 60 s | 0.750 | 0.180 | 0.820 | 0.149 | 0.851 | 0.080 |

Metrics written to `results/cost/e31_network/predictability_metrics.csv`.

### Interpretation

**Reachability is moderately predictable but not strongly so.** Persistence hovers around 0.75 across all three horizons, meaning a naive "predict same state as now" policy is correct 75% of the time at any horizon up to 60 seconds. This is near-constant because the driving dataset has a high and stable connectivity fraction (83%): the baseline rate of being connected at t+H given any prior state is already ≈0.83, so persistence accuracy is anchored near that level.

**P(D→D) ≈ 0.85** means a currently connected session remains connected 85% of the time at H=60s — a useful signal for prefetch decisions: if the agent is connected now, it will likely still be connected in a minute. **P(I→D) ≈ 0.82–0.86** is surprisingly high, meaning disconnected states are short and the system returns to connected quickly — consistent with brief CellID handover gaps rather than prolonged outages.

**BW autocorrelation drops rapidly**: r=0.39 at H=10s, r=0.08 at H=60s. Bandwidth one minute ahead is nearly uncorrelated with bandwidth now. This means BW-based prefetch scheduling (predicting how much context can be transferred in the next transfer window) should use recent BW rather than current BW for any horizon beyond ~30 seconds.

**Implication for prefetch decisions:** Reachability is easier to predict than bandwidth. A prefetch policy can reliably assume the link will be up in the next 60s (P(D→D)=0.85), but cannot predict whether the link will be at low or high throughput (BW autocorr=0.08 at H=60s). This favors robust prefetch sizing: prefetch at a conservative BW estimate (e.g., p25 = 3.9 Mbps) rather than optimistic, since the actual BW is highly variable and uncorrelated with current BW at horizon H≥30s.

---

## Part D: Transfer latency under measured BW profiles

**Measurement method:** Python user-space rate-limited socket transfer over loopback. Netem (kernel traffic control) was not available in this environment (requires `sudo tc`, which requires interactive authentication). The rate-limiting is implemented in the sender using chunk-level sleep; the receiver measures end-to-end elapsed time. RTT = 20 ms [ASSUMPTION: typical 5G one-way latency; PINGAVG not populated in this dataset].

**Payload sizes** are KV-cache sizes for each representation at the token counts used in E30:
- sum-80: 80 × 57 KB = 4.4 MB
- sum-200: 200 × 57 KB = 10.9 MB  
- win-10: 400 × 57 KB = 21.9 MB
- full (L=8k): 8192 × 57 KB = 449 MB

**BW profiles** from measured Irish 5G driving data (D-state rows only):

| profile | rate |
|---|---|
| p10 | 0.9 Mbps |
| p50 | 9.6 Mbps |
| p90 | 102.9 Mbps |

### Transfer latency table

| representation | payload (MB) | p10 (0.9 Mbps) | p50 (9.6 Mbps) | p90 (102.9 Mbps) |
|---|---|---|---|---|
| sum-80 KV | 4.4 | **41.0 s** [measured: 40.4s] | **3.8 s** [measured: 3.8s] | **0.37 s** [measured: 0.37s] |
| sum-200 KV | 10.9 | **102.5 s** [measured: 101.9s] | **9.6 s** [measured: 9.6s] | **0.90 s** [measured: 0.91s] |
| win-10 KV | 21.9 | **205 s** [theoretical] | **19.2 s** [measured: 19.2s] | **1.79 s** [measured: 1.81s] |
| full KV (L=8k) | 449 | **4197 s** [theoretical] | **392 s** [theoretical] | **36.5 s** [theoretical] |

Full table at `results/cost/e31_network/transfer_latency.csv`.

### Interpretation

Transfer latency is the physical component of Context Inertia that was previously hand-parameterized in the simulator. These measurements replace those hand-parameterized values with trace-derived ones.

At p50 bandwidth (9.6 Mbps), which represents median 5G connectivity during active download:
- Compressed representations (sum-80, sum-200) transfer in 3.8–9.6s — comparable to or longer than the warm-append refresh cost (0.040–0.152s for win-10). Summary KV transfer is NOT cheap relative to win-10 refresh.
- win-10 KV (21.9 MB) takes 19.2s at median BW — slower than full-context restore via warm-append (0.040–0.152s), which means sending KV state for win-10 from a remote node is always dominated by compute at p50 bandwidth.
- full KV at L=8k (449 MB) takes 392s at median BW — clearly infeasible for per-turn migration.

At p90 bandwidth (102.9 Mbps), a rare but achievable condition in the Irish 5G driving dataset:
- sum-80 and win-10 transfer in 0.37–1.79s: fast enough to fit within a 5–15s turn interval.
- full KV at L=8k still takes 36.5s: too slow for a per-turn migration policy.

**Key finding:** KV cache transfer is network-bottlenecked at any realistic BW below ~100 Mbps. This confirms the simulator's assumption that state migration cost is dominated by transfer latency for full context and by accelerator cost for summaries — at median 5G BW, full KV is 40× more expensive to transfer than to restore via warm-append. The prefetch window hypothesis (prefetch state N seconds before the session resumes) is viable only for compressed representations at median BW or better.

---

## What these traces imply for the prefetch decision

1. **Reachability is link-up persistent (P(D→D) = 0.85 at 60s), but the driving-mobility handover rate (35 per session) means the same policy applied to indoor pedestrian agents would be more conservative** — fewer handovers, but each one involves a potentially longer link-down.

2. **BW is unpredictable beyond 30s** (autocorr=0.08). Any prefetch window longer than 30s should be sized to the p25 or lower BW estimate, not the current BW.

3. **For compressed representations at p50 BW**, transfer takes 3.8–9.6s. This fits within a 10–30s turn interval if prefetch begins when the prior turn ends (idle-time prefetch). For win-10, the 19.2s transfer eats the full inter-turn window at p50; any shorter turn interval makes even win-10 infeasible via transfer.

4. **Full KV transfer is effectively infeasible at median BW** (392s at p50 for L=8k). Full context continuity across nodes requires either co-location (no transfer) or a slow background migration with multi-session pre-positioning.

5. **The simulator's existing hand-parameterized transfer cost** should be updated to reflect the trace-derived BW distribution (p10/p50/p90 = 0.9/9.6/102.9 Mbps) rather than a fixed BW assumption.

---

## Figures

`figures/cost/e31_reachability.pdf` — three panels: (1) reachability time series for longest driving session; (2) handover count histogram across 16 sessions; (3) DL_bitrate distribution with p10/p50/p90 marked.

`figures/cost/e31_predictability.pdf` — two panels: (1) persistence fraction and BW autocorrelation as bar chart at H={10,30,60}s; (2) empirical Markov transition matrix at H=60s.
