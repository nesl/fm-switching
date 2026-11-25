# StudyREAL-NET testbed

Real-device live experiment harness for the COVEX policy: 4 real Jetson Orins + 12 emulated
devices on flash, both over a shaped network, against the **unchanged** live2 coordinator.

## Why this lives at `experiments/realnet/`

Deliberately **outside** `experiments/orchestration/` and `experiments/lib/`. Those two trees
are the run-path identity used for same-code pairing, so adding a directory to either would
change that identity for every committed cell.

## The invariant

`orchestration/live2/coordinator.py`, `bridge.py`, `fleet/links.py` and every `arms_*.py` are
**byte-identical to main**. D214 is a byte-identity proof and D225 reads switch state out of
code; changing the coordinator forfeits every committed cell.

Everything here sits on the **fleet side** of the 2-method Protocol
(`orchestration/live2/fleet/emulator.py:76-78`):

    on_event(event, t) -> Sequence[reply]
    tick(t)            -> Sequence[reply]

`bridge.py` already holds no clock of its own ("every call carries the emulator's `t` ... it
therefore cannot drift from the fleet") and already enforces D99 (1) one-decision-per-period on
the caller's clock, so a new loop owner that honours the Protocol inherits both.

## Components

| File | Host | Role |
|---|---|---|
| `slice_trace.py` | anywhere, offline | split a frozen trace into per-device slices |
| `wire.py` | shared | NDJSON + length-prefixed raw blobs, one persistent connection |
| `events_check.py` | shared | build events through the REPO's own `events.py`; report drift |
| `device_agent.py` | the 4 Orins | workload manager: replay a slice, fall back on deadline miss |
| `net_fleet_server.py` | H100 | network front end; owns the run clock, drives the Protocol |
| `emulated_fleet_client.py` | flash | the 12 emulated devices as real network clients |
| `mnwifi_profiles.py` | flash + Orins | shaping profiles and per-host feasibility |

## Verification gates

Each is a check that CAN FAIL, per D92/D225 — not a demonstration.

| # | Gate | Where |
|---|---|---|
| 1 | slice reunion: records, multiset, digest, opportunity ids | `slice_trace.py --trace-dir` |
| 2 | schema identity + malformed events fail loudly | `tests/test_realnet.py` |
| 3 | per-device slice selftest | `device_agent.py --selftest` |
| 4 | tick lateness p99 < 50 ms | run-time, **judge on the H100, not a laptop** |
| 5 | no `opportunity_id` invented at run time (D96(1)) | integration test |
| 6 | a stub run is not a measurement | integration test |
| 7 | negative control: real devices swapped for emulated must match | **run time, 2 cells** |

Gate 7 is the one that distinguishes "real devices changed the result" from "our new code
changed the result". It needs two cells and is not a unit test.

## Running the tests (no lab device is touched)

    cd experiments/realnet
    python3 tests/test_realnet.py \
      --trace-dir ../../results/orchestration/live2/frozen_test/traces/seed4_n16_1200s_A_r40-40-20_lh_req_ss2

Add `--skip-integration` for the unit gates alone.

## What is real and what is profiled

**Real:** the frame bytes on the wire, the send schedule, the transport, arrival timing, the
deadline comparison, and which branch the application takes.

**Profiled:** the device's own answer, read from `device_answers.jsonl` (StudyORIN1's dense
per-instant set). Per D177 the device accuracy gap is a positive constant within a type that
never changes a policy decision, so replaying it is the correct treatment of a profiled input.
D201: a missing `device_score` RAISES; it is never replaced with a neutral value.

## Measured network floors (2026-11-25)

Real 59,601 B round trips, 200 samples per host, to the H100:

| Host | p50 | p99 | stdev | link |
|---|---|---|---|---|
| flash (A6000) | 0.761 | 0.862 | 0.032 | 10 GbE, 1 hop |
| orin-4 | 0.546 | 1.248 | 0.332 | 10 GbE direct, **MTU 1466** |
| orin-3 | 0.967 | 1.260 | 0.134 | 1 GbE switch |
| orin-2 | 1.073 | 2.069 | 0.313 | 1 GbE switch |
| orin-1 | 1.366 | 2.354 | 0.369 | 1 GbE switch |

Shaping targets `(target - floor p50)`; feasibility tests `floor p99 < target`.

## Citations

- Emulation methodology: **CADET**, Sharma, Wang & Srivastava, arXiv:2606.04072 (2026)
- Mininet-WiFi: **Fontes et al.**, CNSM 2015 (CADET's reference [20])
- Wi-Fi 6 latency: **Liu & Choi**, Proc. ACM Meas. Anal. Comput. Syst. 7(1) Art. 25 (2023) —
  real commodity hardware; values are **one-way**, measured by sniffer, and are doubled here
  for a round trip

No public per-packet Wi-Fi 6 latency trace exists. These profiles are condition-level measured
means with an **assumed** jitter shape, recorded in each profile's `provenance`. The paper must
not describe this as replaying a measured Wi-Fi 6 distribution.

## Status

**PRE-REGISTRATION PENDING (D92).** No cell may run until StudyREAL-NET has its row in
`research/EXPERIMENTS.md`. Steps that produce no cell — slicing, unit tests, loopback against
`StubCoordinator` — are safe before that.

Hardware note: the Orins carry Realtek RTL8822CE radios, which are **802.11ac (Wi-Fi 5)** and
have no HE capability. The Wi-Fi 6 condition is therefore emulated on the wired path from
published 802.11ax measurements; it was never measured on our own radios. Jetson AGX Thor
(Aug 2025) does ship Wi-Fi 6E, which is what makes the condition representative of the
platform class.
