# StudyE6b-mobility — mechanism verification (CLAUDE.md Steps 1–5)

**Recorded 2026-11-11, BEFORE the Stage A sweep ran.** The quantities below come from two
single-regime probe runs (`indoor`, `outdoor_driving`, `synthetic_0pct`) made to instantiate the
links, not from the sweep. Offline replay of committed results; CPU only; no GPU, no server, no
inference.

## Step 1 — the causal chain (Stage A)

If a mobile device must send evidence to a cloud model before that model can answer
(FORMULATION §Constraints 2, *serving feasibility*: the serving node must hold an object fresh
enough to serve within the latency SLO, or pay materialization first), and transfers are possible
only while the device is attached to the network (§Constraints 3, *reachability*: transfers only
along edges of G_i(t) at B(t)), then **how** the evidence is shipped decides what can be answered
in time. Under ON-DEMAND the whole input is sent at question time, so the delivered latency is
dominated by payload size. Under STREAM the device ships frames continuously, so at question time
only the newest frame plus whatever an outage queued is pending — but an outage both (i) makes the
cloud unanswerable at that instant and (ii) leaves a backlog that must clear before a later
question is served, which is FORMULATION's §Objective statement that *handoff latency on a mobility
event is the binding term*. Therefore: **outage seconds → queued bytes → upload delay at the next
question → deadline missed → the cloud configuration scores zero, and only a device configuration
can answer**; and because the two deployment modes charge the same session differently, the mode
must be fixed for all cloud arms, which is exactly the error StudyE4 and StudyE6 setting (b) made.

Stage A tests this chain and nothing else. It does **not** test the keep-warm claim; that chain
needs the device-warm link, which is ABSENT until StudyE7 and StudyE8 are committed (see Step 2),
and therefore no Stage A result is reported as evidence for or against keeping a tier warm.

## Step 2 — instantiate each link

| causal link | implementing quantity | value / range in the probe | varies as expected? | evidence |
|---|---|---|---|---|
| the network drops out | outage fraction per regime | outdoor-driving **0.1438**; indoor **0.0074**; synthetic 0.0000 / 0.0197 / 0.0494 / 0.1013 / 0.2012 / 0.2998 | yes, by construction and by trace | `e6b_traces.json` |
| outages have duration | outage run length | Irish p50 1 s, p95 2 s, max 3 s (3,829 runs); indoor one run of 26 s | yes | `e6b_traces.json` |
| outage → queued bytes | pending bytes at question time vs one frame | fraction of questions with pending > 1 frame = **0.14** at 13.6 Mbit/s (= the outage fraction); RECENT pending p50 276,307 B, p95 552,614 B, max 828,921 B | yes, and only during/after outages | `cells[*].upload_diagnostics` |
| queued bytes → upload delay | upload seconds at question time | RECENT p50 **0.025 / 0.163 / 0.442 s** at 88 / 13.6 / 5 Mbit/s; U p95 **0.063 / 0.407 / 1.108 s**; U never-uploaded **5.1 %** at 5 Mbit/s | yes, scales with uplink and with arm rate | same |
| upload delay + compute → deadline met or missed | delivered total vs deadline | per-configuration utility moves from 0.395 (32B RICH, 13.6 Mbit/s STREAM, 5 s) to 0.005 (same arm, 5 Mbit/s, 2 s) | yes | `cells[*].per_config` |
| unreachable at question time → only the device can answer | reachable fraction; P1 device-fallback fraction | reachable 0.861 (outdoor), 0.9938 (indoor), 1.0 (synthetic 0 %); fallback fraction equals 1 − reachable | yes | `cells[*]` |
| the device fallback has value | device configuration accuracy | short windows **0.1538 / 0.1373 / 0.1515** (N = 1/3/9, StudyF4), all at or below the 0.20 chance floor; device RECENT 120 s cold = 0.3254 accuracy but ~17 s latency, delivered on **0.1 %** of questions at a 10 s deadline | **WEAK, and reported as such** — present and non-zero, but every device option is either near chance or undeliverable | StudyF4, StudyD4-orin/DevFast curve |
| **device-warm history changes the fallback's value** | device D2 warm accuracy and warm/cold latency | **ABSENT** — needs StudyE7 (4B D2 letters) and StudyE8 (Part D parity, Part B warm-up curve, Parts A/C energy) | — | not committed |

**No ABSENT link is on Stage A's chain.** The one ABSENT entry is the Stage B link, and it is the
reason Stage B is not run here: per CLAUDE.md, the keep-warm sweep does not proceed until StudyE7
and StudyE8 exist. The "device fallback has value" link is present but weak; it is flagged in the
report and no Stage A conclusion depends on the fallback being good.

## Step 3 — trace one unit

The runner writes one instrumented video-through-an-outage trace to
`e6b_results.json → trace_example`: for every question of one (video, trace offset) pair it records
the question time, the trace second, whether the link was up, the outage seconds in the preceding
60 s, and then per configuration the queue backlog in bytes, the newest-frame charge, total pending
bytes, upload seconds, RTT, compute seconds, total seconds, whether it met the deadline, the
committed correctness, and the resulting utility — plus the arm stream rates and the uplink MB per
hour. The arithmetic is checkable by hand from those columns.

## Step 4 — negative control

**Control (a), pre-registered:** set the outage fraction to 0 (`synthetic_0pct`). P1 must never
fall back to the device, so its device-fallback fraction must be 0 and its utility must equal the
always-cloud decomposed policy's. Probe outcome: reachable fraction **1.0**, device-fallback
fraction **0.0**, P1 = **0.40355** at the 5 s and 10 s deadlines — identical to StudyE6 setting
(a)'s evidence-only F1 accuracy (0.4036), which is the correct always-cloud value. **PASS.**

A second control falls out of the design: at 88 Mbit/s the upload term is ~0.025 s, so utility must
be set by compute and correctness alone; it is, and the per-configuration utilities there equal the
committed accuracies of the arms that fit the deadline.

Control (b) (device-warm accuracy set to device short-window accuracy) belongs to Stage B and is
not run, because the quantity it would disable does not exist yet.

## Step 5 — alternative explanations

1. **"Cloud arms lose because of outages" vs "cloud arms lose because of compute."** Both predict
   low utility at a short deadline. They are separated by the 88 Mbit/s column, where upload is
   0.025 s: anything that still fails there fails on compute (32B video ≈ 3.7–3.8 s, 32B U ≈ 5.3 s,
   device RECENT ≈ 17 s). The report attributes losses with that column and with the
   connected-vs-outage utility split, not by assertion.
2. **"P1 beats static because placement helps" vs "P1 beats static because StudyE6's evidence rule
   picks a better cell."** Separated by the outage-fraction-0 control: there P1 carries no placement
   decision at all, so any P1 − static difference there is the evidence rule alone, and the
   placement contribution is the change in that difference as the outage fraction rises.
3. **"The mode correction changes the answer" vs "the curve correction changes the answer."** The
   two corrections are applied and reported separately: the E4 table 4.1 recompute is given under
   both deployment modes with the same corrected curves, so the mode term and the curve term can be
   read off independently.
4. **Alignment artefact.** A video mapped to an unusually bad or good stretch of trace could drive
   a difference. Twenty offsets per video with a video-and-offset bootstrap is the control; the
   indoor regime additionally reports how few sessions are long enough to host a video, because
   there the alignment is concentrated.
