# StudyE6b-mobility STAGE B — mechanism verification (CLAUDE.md Steps 1–5)

**Recorded 2026-11-11, BEFORE the Stage B sweep ran.** Every quantity below is read from a
committed result file of StudyE7-d2-4b or StudyE8-device-warm (both committed 2026-11-11) or from
Stage A's own committed outputs. No policy number appears here. Offline replay of committed
results; CPU only on the flash host; no GPU, no model server, no inference.

Stage A declared the device-warm link **ABSENT** and stopped before P2/P3. This document is the
re-verification that the link is now present, which is the condition Stage A set for Stage B.

## Step 1 — the causal chain (Stage B)

FORMULATION §Constraints 2 (*serving feasibility*: a serving node must hold an object fresh enough
to answer within the latency SLO, or pay materialization first) and §Constraints 3 (*reachability*:
transfers only along edges of G_i(t)) give the chain Stage B tests:

If the cloud is unreachable at question time, only a node that already holds the session state can
answer (§Constraints 3). The device can hold that state in two ways: **cold**, in which case
answering costs a full reconstruction of the D2 history (the physical component of Context
Inertia, §refresh), or **warm**, in which case the KV prefix is already resident and answering
costs only the question tail. Therefore: *if* holding the history warm on the device is (i)
possible on the device runtime, (ii) materially more accurate than any state the device can reach
without pre-warming, and (iii) fast enough to meet the deadline, *then* a policy that decides
**when** to hold it warm converts outage seconds — which Stage A showed are where the entire
policy margin lives — from unanswerable into answerable, at a keep-warm power cost that a
connectivity-aware policy can avoid paying when no outage is coming. The counter-chain the
experiment must leave room for is that warming is either too slow to start (the mid-session
warm-up is a full cold prefill, §refresh) or too cheap to bother scheduling, in which case the
keep-warm decision is static, not dynamic.

## Step 2 — instantiate each link

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| the cloud is unreachable for part of a session | per-second reachability from the committed traces | outdoor-driving 14.38 % outage (3,829 runs, p50 1 s, max 3 s); indoor 0.74 %; synthetic 0/2/5/10/20/30 % | **yes**, by construction across 8 regimes | `e6b_traces.json` (Stage A, committed) |
| the device runtime can hold a KV prefix warm | llama.cpp c0fd786 `evaluated` / `reused` per append | evaluated **95** tokens constant, reused rising to **40,849**; reused fraction p50 **0.991** | **yes** — reuse grows with history while work per append stays at one frame | StudyE8 Part 0 + Part A (`study_e8_analysis.json`) |
| warm device state is more accurate than the no-pre-warm device state | accuracy of the configuration the device can answer with | device-warm D2 **0.309** (StudyE7 4B D2, 839 q) vs device short windows **0.154 / 0.137 / 0.152** (StudyF4 N=1/3/9) and device RECENT 120 s | **yes**, a 15.5 pp gap — this is the link Stage A recorded ABSENT | `e7_results.json`; `results/device/study_f4/partA_accuracy.jsonl` |
| the device-warm accuracy proxy is valid | device vs H100 4B letter agreement on byte-identical inputs | warm **68/68 = 1.000**, cold **27/27 = 1.000**, no cell below the 90 % flag | **yes** — exact, not approximate | StudyE8 Part D |
| warm answering is fast enough to meet a deadline | device warm-question total latency vs history tokens | **0.84 s** at 4,648 tok → **1.80 s** at 12,816 → **3.03 s** at 25,264 → **5.75 s** at 45,699 | **yes**, monotone and deadline-separating (meets 2 s below ~14 k tok, 5 s below ~40 k) | StudyE8 Part A question table |
| cold device state is *not* fast enough | device cold D2 total latency | **3.24 s** at 761 tok → **162.8 s** at 52,127 tok (super-linear; prefill falls 647 → 336 tok/s) | **yes**, and it is 16× slower than warm at matched history | StudyE8 Part B |
| keeping warm costs power | board power above loaded idle while keeping warm at the 2 s cadence | **5.21 W** (15.14 W warm vs 9.94 W idle) = **15.1 Wh per warm-hour** | **yes**, non-zero and the quantity the decision rule trades against | StudyE8 Part C |
| turning warm mid-session costs a reconstruction | cold prefill of the history held at the moment of warming | the Part B curve, e.g. ≈ 3.2 s at 761 tok, ≈ 40 s at ~13 k tok, 162.8 s at 52 k tok | **yes**, and it grows with session time — this is what can make P3 lose to P2 | StudyE8 Part B |
| keeping warm has a throughput ceiling | append latency vs the 2 s frame cadence | append total crosses 2 s at **167 frames ≈ 15,069 tok ≈ 334 s** into a session; 95 of 266 appends over 2 s in the real-time run | **yes** — the device falls behind on long sessions, which Stage B must model, not assume away | StudyE8 Part C |
| a 4B cloud D2 arm now exists | StudyE7 Job A letters + Job B curves | accuracy **0.309** (839 answered, 6 infeasible); cold 95.7 ms/1k over 2.2k–30.7k tok; warm fit over 529–13,824 uncached tok | **yes** | `e7_results.json` |

**No link is ABSENT or CONSTANT.** The two links Stage A marked ABSENT (device-warm accuracy,
device-warm cost) are now instantiated by direct measurement, so the Stage A stopping condition is
cleared and the sweep may proceed.

**Two links are instantiated but weak, and are flagged here before the sweep, not after:**

1. **4B cloud WARM latency tracks uncached tokens poorly.** StudyE7 Job B fits TTFT against
   uncached tokens at **R² = 0.325** (32B's equivalent in StudyF3 is 0.78), with a 0.53 s intercept
   at zero uncached tokens. The `cl-4B-D2-warm` configuration therefore carries more latency
   uncertainty than any other cloud arm, and any result that turns on it is reported as such.
2. **Cold-prefill *energy* on the device was not measured.** StudyE8 measured power while keeping
   warm (Part C) but not during a Part B cold prefill. Stage B charges the warm-up at Part C's
   measured 5.21 W delta, because a cold prefill is the same prefill work on the same clocked
   hardware; this is labelled an assumption everywhere it is used, and it makes P3's energy a
   **lower bound**, i.e. it biases in favour of P3, against the conclusion Stage B is most likely
   to reach.

## Step 3 — trace one representative unit

The sweep writes `trace_example_stageb` to `e6b_stageb_results.json`: one video × one trace offset
through an outage, listing per question the trace second, the connectivity, the device's warm
state, the frames it has ingested, its ingest lag, the history tokens it holds, the append backlog,
every latency charged (upload, RTT, compute) for each configuration, every budget charged (uplink
MB, device joules, cloud warm-session seconds), which constraint bound the answer, and the
resulting utility. The per-question arithmetic in that trace is checkable by hand against the
curves named in Step 2.

## Step 4 — negative controls (both pre-specified, run in the sweep)

- **(a) Outage fraction 0** (`synthetic_0pct`): the cloud is always reachable, so P3's predicted
  outage risk must stay below any sensible threshold, its warm fraction must go to ≈ 0, and P3's
  utility must equal P1's wherever the device is never the faster deliverable. Stage A already
  passed this for P1 exactly (0.000 fallback, 0.000000 difference); Stage B extends it to P2/P3.
- **(b) Device-warm accuracy set to the device short-window accuracy** (`F4N1` letters substituted
  for the `E7D2` letters on `dev-4B-D2-warm`, every latency and cost unchanged): if the P2/P3
  margin comes from the warm *state's* accuracy rather than from its speed or from the scheduling,
  the margin must collapse. If it does not collapse, the gain is a latency effect and must be
  reported as one.

## Step 5 — alternative explanations

1. **"P2 beats P1 because the device is warm"** (the claimed mechanism) versus **"P2 beats P1
   because D2 is simply a better device representation than a 3-second window, warm or cold."**
   Distinguished by the `dev-4B-D2-cold` configuration, which carries the *same letters* and the
   same representation but pays the Part B reconstruction: if cold D2 also beats P1's fallback, the
   gain is representational, not a warm-state gain. The two differ only in latency, so the deadline
   sweep separates them.
2. **"P3 ≈ P2 because the predictor works"** versus **"P3 ≈ P2 because the device is warm almost
   all the time anyway."** Distinguished by P3's reported warm fraction and by the P3-noncausal
   sanity policy: if P3's warm fraction is near 1, the predictor is not doing the work.
3. **"P3 loses to P2 because outages are unpredictable"** versus **"P3 loses because the
   mid-session warm-up is a full cold prefill that cannot finish before the outage ends."**
   Distinguished by the Irish outage-duration distribution (p50 **1 s**, max **3 s**) against the
   Part B warm-up cost at the same session time (tens of seconds): if the warm-up exceeds the
   outage it was called for, no predictor of any quality can help, and the correct conclusion is
   about the warm-up cost, not about predictability.
4. **An accuracy artefact:** the device-warm arm's letters are the H100 4B's. Ruled out by Step 2's
   parity row (68/68 and 27/27 exact on byte-identical inputs), which is measurement, not proxy
   argument — the one remaining gap being that parity was measured on 74 archive questions, not all
   845, and that is reported as the proxy's scope.
