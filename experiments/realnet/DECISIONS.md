# StudyREAL-NET: decision log

Where every number in this harness came from, what the architecture is, and which choices are
still open. Written 2026-11-25. Each measurement says who made it, on what, and when; each
external number names its source and whether it is a measurement or an assumption.

---

## 1. The architecture

A rendered version of this diagram is in `architecture.svg` beside this file.

```
  REAL DEVICES                    SHAPING                 H100
  ------------------------        -----------------       -----------------------------
  4x Jetson AGX Orin                                      net_fleet_server.py
    device_agent.py                                         owns the ONE run clock
      trace slice (local disk)    Mininet-WiFi              stamps t_arrive on receipt
      profiled answer table         or tc netem             barrier: holds t=0 until all
      UplinkSender (FIFO)         per-host offset:          expected devices register
        |                           target - floor p50      validates via events.make()
        |  real JPEG bytes   ---------------------->        routes replies to the owner
        |  one persistent TCP connection                             |
        v                                                            v
   cloud_answer <------------------------------------------  EmulatorBridge  (UNCHANGED)
   if it arrives by deadline_s: use it                               |
   else: profiled device answer (D165 B)                             v
                                                            Live2Coordinator (UNCHANGED)
  EMULATED DEVICES                                            + all 200+ arms  (UNCHANGED)
  ------------------------                                             |
  12x on flash (A6000)                                                 v
    emulated_fleet_client.py      same shaping             vLLM 32B on GPU
      one thread + one            as the real devices        the ONLY model that runs
      connection per device  ----------------------->        anywhere in the system
```

### The one seam

Everything new sits on the fleet side of a two-method Protocol
(`orchestration/live2/fleet/emulator.py:76-78`):

    on_event(event, t) -> Sequence[reply]
    tick(t)            -> Sequence[reply]

`net_fleet_server.py` is the real-network counterpart of `FleetEmulator`: it owns the run
clock and calls that Protocol, so `bridge.py`, `coordinator.py` and every `arms_*.py` stay
byte-identical. `bridge.py` already holds no clock of its own ("every call carries the
emulator's `t` ... it therefore cannot drift from the fleet") and already enforces D99 (1)
one-decision-per-period on the caller's clock, so honouring the Protocol inherits both.

### Why `experiments/realnet/` and not `experiments/orchestration/`

`experiments/orchestration/` and `experiments/lib/` are the run-path identity used for
same-code pairing. Adding a directory to either would change that identity for every committed
cell, so this tree sits outside both.

### What is real and what is profiled

| Quantity | Status | Why |
|---|---|---|
| frame bytes on the wire | **REAL** | the point of the study |
| send schedule, transport, arrival time | **REAL** | |
| deadline comparison and which branch is taken | **REAL** | |
| uplink queueing (FIFO, `queue_s`) | **REAL** | D75 / `links.py` semantics |
| cloud model (32B) | **REAL** | runs on the H100 GPU |
| device's own answer | **PROFILED** | D177: within a type the accuracy gap is a positive constant that never changes a policy decision, so replaying it is correct treatment of a profiled input. D201: a missing `device_score` RAISES, never a neutral value. |
| device-side inference | **NOT RUN** | only P21 claims this; orin-1/2 need a physical reflash for vLLM |

---

## 2. Where the network numbers came from

### 2.1 Measured by us: the wired floor

Measured 2026-11-25 by this session. Method: a dual-stack TCP echo server on each host, a
real 59,601 B payload pushed from the H100 (StudyD4 JPEG q90 N=1 request bytes), a 400 B
reply, 200 timed rounds after 20 discarded warm-up rounds, one persistent connection with
`TCP_NODELAY`. Scripts removed from every host afterwards.

| Host | p50 | p90 | p99 | min | max | stdev | connect | link |
|---|---|---|---|---|---|---|---|---|
| flash (A6000) | 0.761 | 0.816 | 0.862 | 0.712 | 0.879 | 0.032 | 0.492 | 10 GbE, 1 hop |
| orin-4 | 0.546 | 1.223 | 1.248 | 0.196 | 1.273 | 0.332 | 0.906 | 10 GbE direct cable |
| orin-3 | 0.967 | 1.186 | 1.260 | 0.745 | 1.269 | 0.134 | 1.375 | 1 GbE switch |
| orin-2 | 1.073 | 1.647 | 2.069 | 0.702 | 2.328 | 0.313 | 2.070 | 1 GbE switch |
| orin-1 | 1.366 | 1.861 | 2.354 | 0.760 | 2.393 | 0.369 | 2.750 | 1 GbE switch |

Round trip, milliseconds. ICMP, separately: 0/200 loss on every host; flash 0.243 ms p50,
single hop.

Hardware facts that matter and are easy to get wrong:

- **orin-4's MTU is 1466**, not 1500. Nothing else on the fabric is.
- **orin-3 has a 10G NIC but reaches the H100 through a 1G port** (`ens6f1` is 1000 Mbit), so
  the switch path is 1 GbE for orin-1/2/3 regardless. Only orin-4's direct cable is 10G end to
  end. Do not report orin-3 as a 10G device.
- **TCP connection setup costs 0.9 to 2.8 ms**, i.e. 1.5 to 4x a whole payload round trip, and
  `links.py` models no connection lifecycle at all. This is why the device holds ONE
  persistent connection: reconnecting per frame would invent a cost the emulator never charges.

### 2.2 A correction worth recording

An earlier note in this work compared the committed 44 ms against an "observed RTT p50 of
80 ms" and concluded the committed constant was too LOW. That was wrong. The 80 ms figure is
the harness's end-to-end request budget (including H100 queueing and serving), not wire RTT.
On the wire the lab fabric is about 1 ms, so the committed link is roughly 34 to 64x too HIGH
on latency and 74x too LOW on bandwidth. The direction of the error was inverted.

Consequence: a real-fleet run on this fabric is not a harsher network, it is an almost-ideal
one, which is precisely why shaping is required rather than optional.

### 2.3 Measured vs computed

Real transfers came in 17 to 40 percent FASTER than the repo's own formula predicts
(`bytes*8/uplink + RTT/2` each way). Two reasons: the formula charges a full `RTT/2` in each
direction as if flight were serial with serialisation, whereas TCP pipelines them; and ICMP is
handled on a slower kernel path than established-connection TCP. The arithmetic was
conservative, not optimistic.

One thing we could NOT separate, and do not claim: uplink serialisation alone. Subtracting a
1-byte round trip from the 59,601 B round trip gave NEGATIVE values on two of four boards,
which is physically impossible. At 1 to 10 GbE, serialising 59,601 B costs 0.048 to 0.477 ms,
below the path's own jitter (stdev 0.13 to 0.37 ms). The payload term is under the noise floor
and cannot be recovered by subtraction at this sample size. Separating it would need
synchronised clocks (P21 calls for chrony/PTP) or receiver-side one-way stamping. Neither
exists.

That failure is itself the finding: **on this fabric, payload size is not measurable above
noise**, so the policy's upload-scheduling tradeoff acts on a quantity the unshaped testbed
has pushed below its own measurement floor.

### 2.4 The 5G profile: committed, from the repo

`5g-committed` is D75's committed pair, used by StudyE4, StudyE9/E9b and StudyCTRL1/1b/1c:
**uplink 13.6 Mbit/s, RTT 44 ms**. The matching downlink rate is an ASSUMPTION, which
`links.py` states plainly: "No committed downlink rate exists in this repository." A cloud
answer is a few hundred bytes, so that term is about 0.2 ms against 22 ms of RTT/2 and cannot
change an outcome.

`5g-irish-p50` and `5g-irish-p10` come from the Irish 5G dataset (uccmisl/5Gdataset,
GPL-3.0, 16 driving sessions, 28,551 session-seconds) as reprocessed by StudyE31/E31b:
bandwidth **p10/p50/p90 = 0.90 / 9.58 / 102.9 Mbit/s**, no-cell 14.4 percent of time in 1 to
3 s gaps.

**OPEN ITEM carried from D215:** those percentiles still need confirming as UPLINK.
`experiments/cost/e31_network.py:84` reads `DL_bitrate`, so as committed they are DOWNLINK
figures. This matters more now that two wireless profiles are being compared, because uplink
is the direction the policy actually spends.

### 2.5 The Wi-Fi 6 profiles: external, one-way, and NOT a replayed distribution

Source: **Liu & Choi, "A First Look at Wi-Fi 6 in Action: Throughput, Latency, Energy
Efficiency, and Security", Proc. ACM Meas. Anal. Comput. Syst. 7(1) Article 25, March 2023
(SIGMETRICS'23), doi:10.1145/3579451.** Chosen because it is REAL COMMODITY HARDWARE, not
simulation: ASUS RT-AX58U AP, Intel AX210 NICs, Galaxy S10, 1 to 8 clients, 20/40/80 MHz,
OFDMA on and off, with a deliberately deployed Wi-Fi 5 interferer at controlled rates.

**Their latency is ONE-WAY, not RTT.** The paper rejects ping explicitly: "the results combine
uplink and downlink latency". They sniff instead, per direction: `t0` entering the stack, `t1`
at delivery. Every value below is one-way and is doubled in `mnwifi_profiles.py` for a round
trip. Conflating the two is an easy and serious error; it was made once in this work and
corrected.

| Condition | One-way | Source |
|---|---|---|
| UL CSMA/CA, 2 clients, no external contention | **1.8 ms** | Fig 10(d), the lowest in the paper |
| DL OFDMA and CSMA, 2 to 8 clients, no contention | below 4 ms | Fig 10(a), a BOUND not a mean |
| UL CSMA/CA, 8 clients (internal contention) | 22.4 ms | Fig 10(d) |
| DL OFDMA maximum, external contention | 35.58 ms | Fig 10(b) |
| DL CSMA average, 25 Mbit/s + 64 Mbit/s contention | 48.5 ms | Fig 10(c) |
| UL OFDMA, heavy external contention | 60.2 ms | Fig 10(e) |
| DL CSMA average, 112 Mbit/s contention | 170.5 ms | Fig 10(c) |

**There is no public per-packet Wi-Fi 6 latency trace.** What exists is these condition-level
summary values. Their own dataset (github.com/liux4189/wifi-ax-measurement, 3 stars, last
commit 2023-05-02, no licence) holds throughput `.log`, Wireshark `.pcap` and power `.csv`
files and **no latency files**; latency is in the paper's title but was never released as
data. The per-packet distributions exist only as CDF and surface plots (Fig 10a-f), which were
not read as values.

So every Wi-Fi 6 profile here is a **measured per-condition mean with an ASSUMED jitter
shape**, recorded in each profile's own `provenance` field. The paper must not describe this as
replaying a measured Wi-Fi 6 distribution.

Sources considered and rejected as primary:

- **Suer et al., GLOBECOM 2022**, "Experimental Evaluation of IEEE 802.11ax": despite
  "Experimental" in the title it is **simulation** ("extensive simulation based evaluation").
  Its headline, OFDMA cutting median latency from about 5 ms to below 1 ms in non-saturation,
  is simulated AND below our wired floor, so that regime could not be synthesized even if we
  wanted it.
- **Lopez-Perez et al., arXiv:2111.09281**, 802.11be MLO: trace-based **simulation** over the
  WACA spectrum-occupancy dataset. Useful corroboration that real Wi-Fi tails are tens of ms
  (SLO average delay 2 to 18 ms, 95th percentile above 100 ms at 40 percent occupancy), not a
  primary source.
- **CableLabs WMM study**: has P90/P99 uplink tables but returned HTTP 403 and was never read.
  Cited by nobody here.

### 2.6 The Wi-Fi hardware reality

Our Orins carry **Realtek RTL8822CE** radios: 802.11ac (Wi-Fi 5), no HE capability
(`iw phy` shows Bands 1 and 2 and no HE), all four soft-blocked and unassociated. Every hop
measured in section 2.1 was Ethernet; no Wi-Fi was involved in any of it, which matches the
agreed topology (Ethernet for experiments, Wi-Fi for setup only).

So **the Wi-Fi 6 condition cannot be measured on our own radios** and is emulated on the
wired path. That is defensible because **Jetson AGX Thor (Aug 2025) ships Wi-Fi 6E /
802.11ax** per NVIDIA's own devkit datasheet, so the condition is representative of the
current Jetson platform class even though our 2022 boards are a generation behind. The paper
must say the condition is emulated from published 802.11ax measurements and never that our
devices ran Wi-Fi 6.

### 2.7 The feasibility test, and why it is `floor p99 < target`

A shaped link ADDS to a path that already costs something, so the injected delay is
`target - floor p50`. The binding constraint on whether a host can represent a profile at all
is `max(floor) < min(target)`: if the floor's worst case ever exceeded the target, that sample
would need negative delay. `mnwifi_profiles.feasible()` uses the measured **p99** as "max" and
reports the headroom.

An earlier version of this reasoning asked whether the floor was a small FRACTION of the
target and called 17 percent uncomfortable. That was the wrong test. The requirement is only
that the floor be BELOW the target, because the difference is exactly what gets added.

Residual error after shaping is the floor's own JITTER, which adds in quadrature to the
injected jitter:

| Target | flash contributes | orin-1 contributes |
|---|---|---|
| Wi-Fi 6 quiet, 3.6 ms RT | 0.89 percent | 10.25 percent |
| Wi-Fi 6 8-client, 44.8 ms RT | 0.07 percent | 0.82 percent |
| 5G committed, 44 ms | 0.07 percent | 0.84 percent |

This is why the emulated fleet lives on flash: its jitter is 11.6x lower than orin-1's, so
emulated devices contribute roughly a tenth as much measurement noise as a real board, which
is the right way round.

---

## 3. Network emulation: Mininet-WiFi, via CADET

`tc netem` was the first choice and was replaced on the user's instruction with Mininet-WiFi,
following the user's own prior work.

**Citation, with a discrepancy resolved rather than assumed.** CADET (Sharma, Wang &
Srivastava, *CADET: A Modular Platform for Evaluating Distributed Cooperative Autonomy in
Connected Autonomous Vehicles*, arXiv:2606.04072v1, 2 Jun 2026, UCLA;
https://nesl.github.io/cadet-web) describes its NetWaggle layer as "a network emulation layer
built on Mininet [20]", which reads as plain Mininet. But its reference **[20] is Fontes,
Afzal, Brito, Santos & Rothenberg, "Mininet-WiFi: Emulating software-defined wireless
networks" (CNSM 2015)**. So the underlying tool IS Mininet-WiFi and citing it through CADET is
correct. **Cite both**: CADET for the emulation methodology, Fontes et al. for the tool.

CADET's own figures, recorded for reference and NOT reused here: cloud perception modelled at
30 ms p50 / 100 ms p99 "consistent with 5G"; V2V after DSRC at 20 ms baseline / 50 ms tail;
20 repetitions of identical scenarios with under 5 percent variance in safety metrics and
under 3 ms stdev in end-to-end latency.

`tc` is given **HALF** the round-trip offset, because netem delays egress only and the reply
traverses the peer's own qdisc.

Mininet-WiFi was **not installed** on flash or the H100 as of 2026-11-25. Installing it is a
prerequisite, and it needs root plus the ability to create network namespaces and virtual
interfaces.

---

## 4. Why the emulated fleet runs on flash

The emulated devices originally ran in-process on the H100, as `FleetEmulator` does today.
They were moved to flash (A6000) on the user's instruction.

**The stated reason was H100 CPU contention, and measurement does not support it.** The H100
has 128 cores (2x AMD EPYC 9354) at load average 4.53, about 3.5 percent utilisation. Its
**GPUs** are saturated (all four H100 NVL at 74 to 100 percent, the rung-4 queue running) but
its CPUs are nearly idle. Twelve emulated devices, which are a scheduled-event heap plus
arithmetic, would not have loaded it.

**The move is still right, for three better reasons:**

1. **Uniform transport, and this is the strongest.** With the fleet on flash, all sixteen
   devices' events arrive over a real shaped network. In the in-process design, twelve devices
   got zero-latency Python-call delivery while four paid a real network cost: a confound
   sitting directly inside the quantity the study measures.
2. **Isolation.** Mininet-WiFi needs root and creates namespaces and virtual interfaces. Doing
   that on the shared H100 during live rung-4 runs is a real risk; on flash it is contained.
3. **Headroom.** flash's GPUs (A6000 49 GB, 3090 Ti 24 GB) are idle if the emulated side ever
   needs compute.

Reason 1 belongs in the paper. Reason "CPU contention" does not, because it is not true.

---

## 5. Dataset decisions

**The trace is the frozen production trace**, not a new one:
`results/orchestration/live2/frozen_test/traces/seed4_n16_1200s_A_r40-40-20_lh_req_ss2`.
16 devices (6 dashcam, 7 robot, 3 assistive), 1200 s, 14,985 records, 13,570 opportunities,
deadlines 1.0 s dashcam and 5.0 s robot, JPEG wire format with frame p50 66.6 KB
(min 19 KB, max 119 KB), and a committed D96 (2) fairness digest. **16 devices was already the
target fleet size**, so no trace generation was needed.

**Per-device payload, measured:** dashcam about 140 MB, robot about 14 MB, assistive about
2.9 MB; 0.95 GB across the fleet. An early concern that orin-1's free disk could not hold
frames was wrong in unit: the whole JPEG store is 4.2 GB, but a device needs only ITS OWN
SLICE. Every board can host any role.

**The slicer is a filter, never a generator.** D96 (1): `opportunity_id` is assigned by the
trace generator and echoed unchanged by both sides, so nothing here mints, renumbers or
reorders an id. Gate 1 proves it: the union of slices must equal the input record for record,
with a matching fairness digest. Verified digest `9ab834ec` over the frozen trace, reproduced
identically on two hosts and two Python versions.

**The lookup table already existed.** `device_answers.jsonl` carries one `device_score` per
monitor instant from StudyORIN1's dense per-instant set, and D201 already made the emulator
load it and put it on the wire, raising if it is absent. So "the device answers from a profiled
table instead of running a model" is not a new mechanism; the real device does the same read
on the far side of a real socket.

**Frames are named, not copied.** A slice writes `frames.txt` listing the refs it needs; a
separate staging step moves the bytes. This keeps the slicer pure and re-runnable in seconds,
and is why a slice directory is metadata-sized rather than 140 MB.

---

## 6. Decisions still open

| # | Open item | Blocks |
|---|---|---|
| 1 | **D92 pre-registration**: StudyREAL-NET needs its row in `research/EXPERIMENTS.md` before any cell runs | every cell |
| 2 | Irish 5G percentiles still unconfirmed as UPLINK (D215; `e31_network.py:84` reads `DL_bitrate`) | the 5G-vs-Wi-Fi comparison |
| 3 | Mininet-WiFi not installed on flash or the H100; needs root | cells C and D |
| 4 | sudo on the Orins for their shaping side | cells C and D |
| 5 | **The `EmulatorBridge` path has never been run.** `--coordinator` accepts `stub` only. `bridge.py` calls `SC.parse()` on every event and is stricter than the stub | the first measured cell |
| 6 | Mode B (pull) is not implemented; the server and the cell loader both refuse it | any mode-B study |
| 7 | Gate 7, the negative control (real devices swapped for emulated, same slices and shaping, results must match within noise), needs two cells so it is not a unit test | interpreting cells C and D |
| 8 | Clock sync (chrony/PTP) deliberately NOT used; server-side `t_arrive` stamping makes it unnecessary for the coordinator's view, but one-way timing cannot be separated without it | separating uplink from downlink |

Item 7 is the one that distinguishes "real devices changed the result" from "our new code
changed the result", and it should not be skipped.

---

## 7. What a cell may and may not claim

**May claim:** real devices, real JPEG bytes on a real NIC, real serialisation and uplink
queueing with `queue_s` recorded separately, real arrival jitter, real per-device concurrency,
real deadline misses and real fallbacks, the policy and the 32B live, under two named wireless
conditions.

**May not claim:** device-side model inference (no vLLM on orin-1/2; that is P21's claim),
Wi-Fi 6 measured on our own radios (they are 802.11ac), or a replayed per-packet Wi-Fi 6
distribution (none is public).

Per D209 parity, a real-fleet cell is a NEW measurement class and is not comparable to a
committed emulated cell. These are additive, clearly labelled cells, never a replacement for
any committed result.

The honest one-line framing: **the device is real, the network is real, the link budget is
cited, and the device's answer is profiled.**
