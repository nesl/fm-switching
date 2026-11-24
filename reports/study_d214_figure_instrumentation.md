# StudyD214-FIGINSTR - F3 latency stamps, F14 decision-latency sweep, and the network header

Session F on flash, 2026-11-23, under the user ruling of 2026-11-23 (D214 FIGURE INSTRUMENTATION)
and D107 / D115 / D214 / D215 / D216. CPU only. No GPU, no model, no server. No cells posted to the
H100.

**READ SITES AND LINE NUMBERS IN THIS REPORT ARE AT ORIGIN
`10dae57ddc6e32acaa4599bba2aa597237119ddb`**, resolved once at the start of the session and
re-resolved immediately before the commit. They are **not** at the local checkout, which is over
1,200 commits behind origin and carries other sessions' uncommitted work: measured, the local
`experiments/orchestration/live2/run_live2_real.py` has md5 `48e3ea7e...` while origin's at this sha
is `9d4b35e2...`, and `git status` calls the local file clean because it is clean relative to a
stale HEAD. Every file read, every edit and both proof trees are `git archive` extracts of that one
literal sha.

**THE OVERRIDING CONSTRAINT, in the user's words:** *"Logging only; must be byte-identical in
decisions for every arm (prove it on dry s4, ALONE)."* Nothing here may move a decision for any
arm. Section 4 is the proof, not an assertion, and it carries its own control.

**WHAT FILLS A RECORDED GAP.** `research/EXPERIMENTS.md` StudyFIGDATA (STANDING, D214) records
exactly two instrumentation gaps: *"F3 upload/hold/queue/return stamps absent (only t_submit,
t_first_token, t_done recorded), F14 dry latency absent (flash)"*. Items 1 and 2 of this session are
those two gaps. Item 3 is the direct remedy for the StudyNET-TIER1 N1 finding and the
main-operating-point mislabelling.

---

## 0. What was emitted and where

| item | what it emits | where | file I used | ownership |
|---|---|---|---|---|
| 1 (F3) | `uplink_transfers.jsonl.gz` (every uplink transfer with t_offer / t_start / t_arrive / queue_s), `f3_latency_stamps.jsonl` (one joined, register-marked row per request), `f3_stamp_registers.json` (the register summary and the absence census) | the cell's own run directory | NEW `experiments/orchestration/live2/f3_latency_stamps.py`; called from `run_live2_real.py` | `run_live2_real.py` edited DIRECTLY (unowned, as the brief states). **The edit is HELD, not committed, until the section 4 proof passes: see 5.6** |
| 2 (F14) | per-cell `*.json` (committed digest recipe), `*.lat.json` (the full distribution), `*.rec.json` (alone status and loadavg), and the assembled `f14_decision_latency.json` | `results/orchestration/live2/d214_figures/f14/` | NEW `f14_one_cell.py`, NEW `f14_decision_latency_driver.py` | new files only |
| 3 (network) | `run_meta.json["network"]`, `header.json["network"]` and `["network_summary"]`, and three summary fields on `cell.json` | the cell's own run directory | NEW `experiments/orchestration/live2/network_header.py`; called from `run_live2_real.py` | `run_live2_real.py` edited DIRECTLY |
| proof | the byte-identity proof with its control | `results/orchestration/live2/d214_figures/byte_identity/` | NEW `d214_byte_identity_proof.py` | new file only |

**NO FILE I DO NOT OWN WAS WRITTEN, AND NO PATCH SCRIPT WAS NEEDED.** The ownership collision the
brief asked me to pre-empt did not arise: `coordinator.py`, `cstate.py` and `baselines/interface.py`
are untouched, and so are `asyncbackend.py`, `arms*.py`, `v5/*`, `arms_final_ladder.py`,
`fleet/trace.py`, `fleet/emulator.py` and `fleet/links.py`. The reason is section 1: **every stamp
F3 needs already exists**, and the one that was never written out lives on an object the live runner
already holds. The full tree diff between a clean archive of the base sha and the tree I built is
**six files**: five new, and `run_live2_real.py`.

I did **not** need `fleet/emulator.py` or `fleet/links.py` either, so the question the brief flagged
for item 3 (whether Session N's files are clear) **does not need answering**: the applied link is
read off the live emulator INSTANCE from the runner, not by editing the emulator.

---

## 1. Item 1, F3: which stamps are EMULATED and which are MEASURED

This is the requirement that makes the figure honest, so it is the first section rather than a
footnote. **A latency CDF on this harness mixes two registers**, and three of them once the
answer's return is counted properly.

| stamp | register | reused from (origin sha) | why that register |
|---|---|---|---|
| frame upload START (per referenced frame) | **EMULATED** | `links.UplinkQueue.log[].t_start` = `max(t_offer, free_at)` (`fleet/links.py:113`) | the harness's own arithmetic on a per-device FIFO. No packet is sent |
| frame upload END (per referenced frame) | **EMULATED** | the same transfer's `t_arrive` = `t_start + bytes * 8 / uplink + RTT / 2` (`links.py:116-118`) | ditto. A 63,898 B dashcam JPEG "takes" 0.0376 s because D75 says so |
| frame upload OFFER and queue delay | **EMULATED** | `t_offer`, `queue_s` on the same transfer | ditto |
| COORDINATOR RECEIVE | **EMULATED** | the same transfer's `t_arrive`, which is the instant `emulator.py` pushes `frame_arrived` / `question_arrived` and calls `coord.on_event` (`:386-391`, `:418-419`); for a monitor it is also `outcomes.jsonl t_frame_arrive` | the instant is produced by the link arithmetic, not observed |
| COORDINATOR RELEASE | **MEASURED** (run clock) | `decision.jsonl t`, which is exactly `sub.meta.nominal_t` at `coordinator.py:1524` | the epoch's nominal instant, read in the coordinator process |
| ENGINE SUBMIT | **MEASURED** | `request.jsonl t_submit` = `sub.sent_s`, stamped AT THE WIRE (`asyncbackend.py:250-258`) | D107 (2) |
| FIRST TOKEN | **MEASURED** | `request.jsonl t_first_token` = `sent_s + ttft_s * speed` | off the real server |
| DONE | **MEASURED** | `request.jsonl t_done` = `sent_s + total_s * speed` | off the real server |
| ANSWER RETURN TO DEVICE | **DERIVED** | `outcomes.jsonl t_delivered` = the forwarded answer's instant + `links.deliver_s(RTT/2 + payload / downlink)` (`emulator.py:349-353`) | a MEASURED cloud instant plus an EMULATED downlink term. It is **not** measured because its larger part is |

**The register is carried in the emitted record itself**, as the brief requires: every stamp in
`f3_latency_stamps.jsonl` is an object `{"t": ..., "register": "EMULATED"|"MEASURED"|"DERIVED",
"source": "<file and code site>"}`, and `frame_uploads[]` carries one such object per transfer with
the uplink rate and RTT that were actually applied to it. `f3_stamp_registers.json` is the summary,
not the source of truth.

### D107 is reused, not contradicted

Both of D107's rulings are load-bearing here and neither is re-implemented:

1. **Answers are forwarded at the FIRST CONTENT TOKEN, not at stream end.** So the emulated
   downlink term runs from `t_first_token`, and the row reports `forward_to_device_s` =
   `t_answer_return - t_first_token`. A first version differenced against `t_done` and produced a
   **negative** "downlink time" on every request whose stream outlived its first token, which is
   most of them. A negative latency component in an F3 CDF reads as an instrumentation fault rather
   than as the forwarding rule it actually is. `done_to_return_s` is kept beside it, labelled, for
   the register only.
2. **Every request is stamped at the wire with its epoch's nominal instant in meta, so the
   policy's own decision time is charged as submit delay.** So RELEASE and SUBMIT are two separate
   stamps and `submit_delay_s = submit - release` is reported as D107 (2)'s own quantity, with both
   ends MEASURED. `hold_s = release - receive` is reported separately and marked DERIVED, because it
   spans an EMULATED end and a MEASURED one.

**Which stamps I reused rather than added:** all of them. `decision.jsonl t`, `request.jsonl
t_submit / t_first_token / t_done`, `outcomes.jsonl t_opportunity / t_frame_arrive / t_delivered`,
and `links.UplinkQueue.log`'s three instants. **Nothing was added to `coordinator.py` and no second
source of truth was created for any instant.**

### The one thing that was genuinely missing, and it was not a stamp

`links.UplinkQueue` has recorded `t_offer`, `t_start`, `t_arrive` and `queue_s` per transfer since
StudyLIVE2-fleet and keeps them in `self.log`. **`run_meta.json` carries only `stats()` over them**
(n, busy_s and three queue quantiles, `emulator.py:617-618`), so the per-frame upload start and end
existed on the object and had never been written out. `dump_uplink_transfers` writes them. That is
why item 1 needed no change to the emulator and no patch script.

### Honest limits of the join, stated rather than discovered later

- **`SC.RequestRecord` carries no `kind` field** (`schema.py:364-381`), so a request's kind comes
  from its opportunity. A first version read `r["kind"]`, which silently made every row a
  non-recall and **dropped every history upload from the join**. Found by a synthetic-log test
  before any cell ran, fixed, and recorded here because the failure was invisible in the output: the
  rows looked complete and were missing a whole upload class.
- A recall's history uploads are joined by `(session_id, t_arrive <= t_submit)` through
  `trace.jsonl`'s `history_batch` records, because the uplink log row carries `batch_id` and not
  `session_id`. This is a **declared join, not a measurement**, and every unresolved ref says so in
  `frame_refs_source`.
- `outcomes.jsonl t_delivered` is keyed on the OPPORTUNITY, not the request, and under D107 (1) it
  belongs to whichever answer was forwarded. Each row carries
  `n_requests_on_this_opportunity` so a reader can see when that is more than one instead of
  assuming a one-to-one join.
- `t_first_token` and `t_done` are `sent_s + ttft_s|total_s * speed`. At `speed == 1.0` they are
  the measured instants; at any other value they are **scaled** measurements.
  `f3_stamp_registers.json` reports `speed` from `run_meta.json` and says plainly that a null makes
  the register of those two stamps unverified.
- **LIVE CELLS ONLY**, as the brief asks. A dry cell has no server, so nothing in its
  `request.jsonl` is MEASURED. `f3_stamp_registers.json` carries `live_cell` with its test (any
  integer `http_status`), and a dry cell's rows must not enter an F3 CDF.
- Every unjoinable stamp is emitted as `{"t": null, ..., "absent_reason": ...}` and counted in
  `absent_stamps`, so a CDF built from the rows can state its own coverage instead of quietly
  dropping requests.

---

## 2. Item 3, network header: read from the emulator, never from the config

`network_header.read_from_emulator(em)` is called from `run_live2_real.py` **after `em.run()`
returns**, and reads two things off the object:

- `FleetEmulator.links`, the dict its own `link()` accessor consults (`emulator.py:303-306`), which
  is what the RTT terms for pulls and answer delivery read directly (`:346`, `:349-352`);
- `UplinkQueue.spec`, the object `links.serialise_s` is actually called with (`links.py:114`).

It must be read **after** the run: `links` is filled lazily by `link()`, so a pre-run read reports
`model = "none"` on every cell. It emits:

- `link_model_applied`: `none` | `uniform` | `per-device`, decided by the number of **distinct
  specs actually applied**, not by any flag;
- `per_device_specs_applied` and `distinct_specs_applied`, the specs themselves;
- `queue_spec_is_link_object` **per device**: the identity of the two channels checked rather than
  assumed. A future per-device injection that replaced `links[d]` after a queue had been built would
  leave the queue on the old spec, and the uplink and RTT channels would silently disagree;
- `is_committed_main_operating_point` and, **only where that holds**, the corrected label verbatim:

  > uniform 13.6 Mbit/s / 44 ms uplink: best-performing US carrier's 5G median (Ookla H2 2025),
  > close to the 12 Mbit/s Bay Area 5G median (Khan et al. 2024)

  A cell at any other uniform spec does **not** carry the label and says why: the label names one
  measured operating point and is not a generic description of a uniform link. Measured on the
  smoke test, a uniform 12.0 Mbit/s cell correctly carries no label.

**Why this is not a style preference.** Two failures in this repository have the same shape and a
config-derived header would have reproduced both: the main operating point was mislabelled "a US
median" for weeks (numbers right, label wrong), and `link_by_device` has exactly **two** production
references (`fleet/emulator.py:245` declaration, `:291` write) and **no caller**, so a config field
could say "per-device" while one process-wide `LinkSpec` is applied fleet-wide. The header therefore
also carries that absence, as OBSERVED at this sha and attributed to StudyNET-TIER1 N1, so a reader
meeting `link_model_applied: "uniform"` sees that it is uniform **by construction** and not by
configuration.

The header is written into `run_meta.json["network"]`, **appended to `header.json`** (which is
necessarily written before the run, so it now carries both what was asked for and what was applied,
and a disagreement between them is visible rather than silently resolved), and summarised on
`cell.json` as `network`, `network_spec` and `main_operating_point_label`.

---

## 3. Item 2, F14: the decision-latency sweep

**STATUS: see section 5.** The instrument is built, its positive control is pre-registered, and the
cells are queued behind an ALONE window.

`f14_one_cell.py` adds exactly one thing to the committed runner: **registration of the final
rungs**. `arms_final_ladder.register()` is called by no committed runner, so `covex-v6-fair-final`
and `covex-v6-final` do not resolve in `cf_pd_one_cell` without it; registration goes through
`register()` itself so D208's collision check against the committed names runs. Everything else is
reused by import: `cf_pd_one_cell.main` for the posted knobs, the seed allowlist, the planner
wall-clock patch and **the committed digest recipe** (there is no `sha256` and no `json.dumps` of a
decision row in my files), and `d210_kv025_one_cell` for the latency-keeping patch (`test_hybrid`
strips `decision_latency_ms` from every row it returns, so the quantity the 20 ms budget is judged
against is not recoverable from a dry cell at all) and for the distribution report.

**The regime is a choice and it is stated:** `--kv-scale 1.0`, coordinator eviction **off**, posted
workload, seed 4, 1,200 s, `--cutoff-off`. Eviction off matches the 1x final-ladder bar cells the
concurrent StudyD216-KV025 chain is producing at n=16, which makes this sweep's n=16 rungs
**cross-checkable against those cells on the digest and the row count**. `--cutoff-off` is not a
convenience: with the planner wall-clock cutoff on, a long decision is TRUNCATED, so the decisions
depend on how fast the host was that minute and two runs of one cell are not the same cell.

### Why this sweep may not rank arms, said before any number is read

A prior sweep found **the same arm** giving p99 **4.345 / 2.571 / 1.968 ms** across three
byte-identical runs as the host emptied.

> **BETWEEN-CELL LATENCY MEASURES HOST CONTENTION AND MAY NOT RANK ARMS.**

Two cells run at different times on a shared host, so any arm ordering read off them would be a
**host-load ordering with an arm's name on it**: a plausible spread deriving from a quantity that
cannot carry the meaning claimed, which is CLAUDE.md check 3's artefact-spread shape exactly. The
driver therefore reports the two arms side by side and **emits `"RANKING": "REFUSED"`** with that
reason on every size pair, carrying each cell's loadavg beside its p99. The sweep's readable claim
is about **SIZE** - does p99 cross 20 ms, and where - not about which arm is faster. Each cell runs
ALONE under D216 (1) precisely so the size trend is readable at all.

### The D115 factor is beside the table and never inside it

`flash_to_h100_cpu_factor = 2.2`, from D115 (1): the H100 host CPU is about 2.2x slower than flash
on the committed policy benchmark, and pinned to an idle core it matches the unpinned run within
1 %, so the gap is the CPU and not contention. D115 (3) permits a normalised latency to be
**reported as a labelled derived quantity** and forbids rescaling run outcomes. So the report
carries:

- the **MEASURED flash** columns (min, p25, median, p75, IQR, p90, p99, max, mean, n, n_distinct),
- the **factor**, as its own field with its source, and
- `DERIVED_h100_*_ms` columns, explicitly labelled derived,

and **never a single merged number**. Nothing in any cell output is rescaled.

### Distribution, not quantiles, and the constant flag

Every cell emits min / p25 / median / p75 / IQR / p90 / p99 / max / mean / n / `n_distinct`, a
per-decision-kind breakdown, `n_over_budget` and `frac_over_budget` against the 20 ms budget, and
`constant_where_a_distribution_is_expected`. The assembler raises a flag line for any cell whose
latencies collapse to one distinct value, and for any cell that did not run alone.

---

## 4. The byte-identity proof

Three proofs, increasing in strength, and the weakest is not skipped because the strongest exists.

**(a) Structural. Register: CONSTRUCTED.** Every added line in `run_live2_real.py` runs **after
`em.run()` has returned**: the emulator's loop has ended, the coordinator is closed, every log file
is written, and there is no decision left to make. **Exactly two statements are added inside the
run**, and both are list appends of a reference to an object that already exists:
`_EMU.append(em)` in `_emulator` and `_CO.append(co)` in `_inprocess`. Neither mutates any state a
decision reads, and neither is read until after the run. One further change is a pure rebinding:
`_emulator`'s `return EM.FleetEmulator(...)` became `em = EM.FleetEmulator(...); _EMU.append(em);
return em`, the same call bound to a local.

**That claim is checked mechanically rather than asserted.** `diff` of the held wiring against a
clean archive of the base sha, with comments and blank lines filtered out, enumerates every added
executable line; the only ones not inside the post-run block or the post-run `out` dict are those
two appends and the rebinding. The enumeration is short enough to read in full and is reproduced in
the session handoff.

This is an argument from reading code, so it is marked CONSTRUCTED and is not offered as a
measurement. It is also **not a switch that is off by default**, which the brief asked us not to
ship.

**(b) Import closure. Register: OBSERVED.** A decision path that never imports a module cannot be
changed by it. The proof runs one dry cell on the after-tree and prints the census of `sys.modules`
for `network_header`, `f3_latency_stamps`, `f14_one_cell`, `f14_decision_latency_driver`,
`run_live2_real` and `d214_byte_identity_proof`. The census is printed in full; no absence is
claimed from a truncated view.

**(c) Paired cells, and this is the one the brief asks for. Register: OBSERVED.** The same cell is
run on a clean `git archive` of the base sha and on the after-tree, and the two `decision.jsonl`
files are compared with the TIMING fields removed (`arm`, `decision_latency_ms`, `decision_id`:
exactly `test_hybrid.STRIP`), because a wall-clock latency is not a decision. The raw file sha is
reported beside it, labelled, for the register only.

**(c) has its own control, and without it the comparison is unreadable.**
`run_live2_real.py` runs the emulator in REAL TIME and ticks the coordinator on the wall clock while
it waits, so two runs of one cell on one tree are not guaranteed to reproduce. **So each tree is run
twice.** A/A and B/B establish the harness's own repeatability FIRST; only if both are identical
does A-vs-B mean anything. If they are not, the report says so and **refuses to call the A-vs-B
result a byte-identity proof**. A comparison whose control is never audited is the blindness
CLAUDE.md check 7 is about, and here the control is the harness's own repeatability.

**ALONE, and loadavg as a magnitude (D216 (1)).** Every cell in section 3 and section 4 waits for a
window with no other live2 process, re-checks that none started during it, and records
`/proc/loadavg` at the start and the end **as the number**. A cell with `alone: false` is recorded as
such and its digest is not reported as a bar. The guard identifies its own child by an
**environment marker**, never by a command-line pattern: `pgrep -f` on a self-matching pattern kills
the session shell with exit 144, and a cmdline match cannot tell this driver's cell from another
session's anyway.

**The proof cell is dry-but-real-path.** There is no server on flash, so it runs
`run_live2_real.py` with no `--server`: the real `Live2Coordinator`, the real `EmulatorBridge`, the
real emulator and the real post-run block, with `dry_run=True` inside the coordinator. That is the
path the instrumentation sits on. It is **not** a measurement of anything, `is_measurement` is false
in its own header, and no latency from it is reportable.

---

## 5. Results

### 5.1 The absence claim item 3 rests on, with the exact command and its full output

Not from a truncated view. Run on a clean `git archive` of the base sha:

```
$ grep -rn "link_by_device" experiments/
experiments/orchestration/live2/n3_tier1_cell_definitions.py:10
experiments/orchestration/live2/n3_tier1_cell_definitions.py:268
experiments/orchestration/live2/n3_tier1_cell_definitions.py:320
experiments/orchestration/live2/n1_link_emulation_probe.py:7
experiments/orchestration/live2/n1_link_emulation_probe.py:69
experiments/orchestration/live2/n1_link_emulation_probe.py:73
experiments/orchestration/live2/n1_link_emulation_probe.py:76
experiments/orchestration/live2/n1_link_emulation_probe.py:154
experiments/orchestration/live2/n1_link_emulation_probe.py:158
experiments/orchestration/live2/n1_link_emulation_probe.py:159
experiments/orchestration/live2/n1_link_emulation_probe.py:160
experiments/orchestration/live2/n1_link_emulation_probe.py:161
experiments/orchestration/live2/fleet/emulator.py:245
experiments/orchestration/live2/fleet/emulator.py:291

$ grep -rn -- '"--uplink"\|"--rtt"\|"--link"' experiments/orchestration/live2/*.py
experiments/orchestration/live2/n1_link_emulation_probe.py:168
experiments/orchestration/live2/n1_link_emulation_probe.py:169
```

That is the whole output of both commands. **OBSERVED:** the only two references outside the two
diagnostic probes are `fleet/emulator.py:245` (the parameter declaration) and `:291` (the write),
and the only two `--uplink` / `--rtt` / `--link` occurrences are inside `n1_link_emulation_probe.py`
measuring their own absence. So StudyNET-TIER1 N1's finding holds unchanged at this sha, and the
header's `link_by_device_injection` block is accurate.

### 5.2 The network header on a uniform cell. OBSERVED on a smoke test

`network_header` was exercised against real `links.LinkSpec` objects:

| applied specs | `link_model_applied` | `main_operating_point_label` |
|---|---|---|
| two devices at the D75 default | `uniform` 13.6 Mbit/s / 44 ms / 13.6 Mbit/s | **carried** |
| one at 13.6, one at 0.9 | `per-device`, 2 distinct specs over 2 devices | not carried |
| none | `none` (no device uploaded) | not carried |
| one device at 12.0 Mbit/s | `uniform` 12.0 Mbit/s / 44 ms | **not carried**, and it says why |

The last row is the one that matters: a uniform cell that is **not** the committed operating point
does not inherit the corrected label. The label names one measured operating point; it is not a
generic description of a uniform link, and attaching it to a 12 Mbit/s median cell would reproduce
the original mislabelling in the opposite direction.

### 5.3 F3 on synthetic logs, built from the committed link arithmetic. OBSERVED

The join was exercised against a real `links.UplinkQueue` (so the EMULATED stamps come from the
committed arithmetic, not from invented numbers) plus synthetic `request.jsonl`, `decision.jsonl`,
`outcomes.jsonl` and `trace.jsonl`. Three transfers in, three joined; both request rows emitted with
every stamp register-marked. The monitor row's upload reproduces the committed figure exactly:
**63,898 B at 13.6 Mbit/s, start 10.000000, end 10.059587**, i.e. 0.037587 s of serialisation plus
22 ms of RTT/2, which is the D75 number StudyNET-TIER1 N1 also reproduces. The recall row joins its
session's `history_batch` upload (start 10.037587, end 10.177234, three frame refs resolved from
`trace.jsonl`) ahead of its own 1,200 B question text, which is the FIFO uplink behaving as
`links.py` documents.

**One real defect was found by this test and fixed before any cell ran**, and it is recorded because
the broken output looked complete: `SC.RequestRecord` carries no `kind` field, so reading
`r["kind"]` made every row a non-recall and **silently dropped every history upload from the join**.
The rows still validated, still had registers, and were simply missing a whole upload class. It was
caught by checking that the counts matched (three transfers in, three joined), not by looking at the
output.

### 5.4 The F14 wrapper resolves the final rungs with its declared type. OBSERVED

Not merely that a name was passed:

| arm | resolves | built class | first MRO entries |
|---|---|---|---|
| `covex-v6-fair-final` | yes | `V6FairFinalWired` | `_PlannerFeedMixin`, `V6FairFinal`, `_AlertRecheckMixin`, `V6FairFeed_covex_v6_state_final`, `DeficitFeedMixin`, `V6StateFinal` |
| `covex-v6-final` | yes | `V6Final` | `_Rung4Mixin`, `_ProtectDeferMixin`, `V6FairFinalWired`, `_PlannerFeedMixin`, `V6FairFinal` |

`arms_final_ladder.register()` returned all three rung names and D208's collision check passed.

### 5.5 F14: the n=16 rungs, from the concurrent StudyD216-KV025 chain

**These are not my cells and they are attributed.** The StudyD216-KV025 chain (another task of this
session, already running when this work began) produced exactly the two cells my sweep's n=16 rungs
would be: same arms, seed 4, n=16, 1,200 s, posted workload, `--kv-scale 1.0`, eviction off,
`--cutoff-off`, through `d216_final_kv025_one_cell.py`, which is the same
`cf_pd_one_cell` + `d210` latency-patch lineage my `f14_one_cell.py` uses. **Both ran ALONE** under
that driver's own D216 (1) guard. Re-running them would have been a duplicate, so they are cited and
my own sweep re-runs n=16 independently as a cross-check.

Decision latency in **milliseconds**, flash CPU wall-clock inside the arm's `decide`
(`coordinator.py:2127`), DRY. Budget 20 ms.

| arm | n | rows | digest | min | p25 | median | p75 | IQR | p90 | **p99** | **max** | mean | n_distinct | over budget | alone | loadavg 1m start / end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `covex-v6-fair-final` (rung 3) | 16 | 14,539 | `5a03c2807da3681a` | 0.1069 | 0.7572 | **0.8911** | 0.9396 | 0.1824 | 0.9651 | **1.8776** | **3.8911** | 0.8489 | 3,601 | 0 of 14,539 | yes | 1.16 / 1.46 |
| `covex-v6-final` (rung 4) | 16 | 14,509 | `57bed6ace2eb07d1` | 0.1148 | 0.7858 | **0.9037** | 0.9480 | 0.1622 | 0.9718 | **1.9474** | **4.1080** | 0.8626 | 3,564 | 0 of 14,509 | yes | 1.46 / 1.08 |

**Against the 20 ms budget: p50, p99 AND MAX are all inside it at n=16, by a factor of about 5 on
the max.** `n_over_budget` is 0 for both.

**No constant where a distribution is expected:** 3,601 and 3,564 distinct values over ~14,500
decisions, `constant_where_a_distribution_is_expected: false` on both.

**The two arms are NOT ranked.** p99 1.8776 against 1.9474 ms is a gap of 0.07 ms between two cells
that ran at different times at 1m loadavg 1.16 and 1.46 on a shared host. A prior sweep moved **the
same arm** by 2.4 ms of p99 (4.345 to 1.968) across three byte-identical runs as the host emptied.
**The observed gap here is roughly 34x smaller than that known contention swing**, so it carries no
information about the arms at all. Any ordering read off it would be a host-load ordering with an
arm's name on it. The driver emits `"RANKING": "REFUSED"` for exactly this reason.

**The D115 factor, stated separately and never multiplied in.** Measured flash p99 at n=16 is
**1.8776 / 1.9474 ms**. The flash-to-H100 host-CPU factor is **2.2x** (D115 (1)). The labelled
derived quantity, which is a projection and not a measurement, is therefore
`DERIVED_h100_p99_ms` = 4.13 / 4.28 ms. **Run outcomes are never rescaled** (D115 (3)); no number in
any cell file is scaled, and a claim about a faster or slower coordinator host requires a rerun on
that host.

### 5.6 F14 at 24, 32 and 48 devices, and the byte-identity proof

**RUNNING, NOT DONE, AND THE WIRING IS HELD BACK BECAUSE OF IT.** See section 7.

**WHAT IS LANDED AND WHAT IS HELD, AND WHY THE LINE IS DRAWN THERE.** The five new modules are
landed. The one-file wiring in `run_live2_real.py` that calls them is **NOT**, and will not be until
the byte-identity proof in section 4 has passed. The reason is that the entire risk lives in that
one file: the new modules are not imported by any committed runner, so by the import-closure
argument they cannot change anything, while `run_live2_real.py` is on the live path. Landing the
modules now makes the work reviewable and unblocks nothing else; landing the wiring on an argument
instead of a proof is what the user's constraint forbids, and the brief's own sequencing ("land these
before FINAL_LADDER_CELLS if they can be proven in time; otherwise from the first cells after")
anticipates exactly this split.

Until the wiring lands, items 1 and 3 are reachable as a **post-hoc CLI** on any existing cell
directory, which needs no change to any runner:

```
python experiments/orchestration/live2/f3_latency_stamps.py --run-dir <cell dir> [--trace-dir <dir>]
```

That path cannot emit `uplink_transfers.jsonl.gz` for a cell that has already finished (the emulator
object is gone), so on an old cell the EMULATED upload stamps are absent.

**THAT ABSENCE IS NOW LOUD, AND THE DISTINCTION IT MAKES IS THE POINT.** A reader meeting a null
assumes an instrumentation gap, i.e. something that could be fixed by better code. The upload
stamps are not that: they live on `links.UplinkQueue.log`, on the emulator **object**, which exists
only while the run is in progress. A post-hoc cell therefore **can never** have them and
**re-running the script will never produce them**. So the output separates the two causes and says
which it has, at three levels:

| level | what it says |
|---|---|
| `f3_stamp_registers.json`, top-level | `uplink_transfers: "ABSENT, STRUCTURALLY, AND NOT RECOVERABLE FOR THIS CELL"`, a paragraph-length `uplink_transfers_reason`, and `emulated_upload_leg_usable_for_a_cdf: false` |
| every row of `f3_latency_stamps.jsonl` | `frame_uploads_absent` carries **`STRUCTURAL:`** (no transfer log in this cell at all) or **`JOIN:`** (the log exists with N transfers and none matched *this* request, naming its opportunity, kind and session). The second is a real gap worth investigating; the first is not |
| stderr of the CLI | the verdict line plus the full reason, so it cannot be missed by someone reading the console rather than the JSON |

`absent_stamps` also carries a note telling a reader to read `uplink_transfers` **first**, because
under a structural absence `frame_uploads` necessarily equals `n_rows` and says nothing about the
join. And the reason explicitly warns against the failure mode that matters for F3: **do not plot a
CDF from such a cell as though its upload leg were measured at zero** - the upload leg is simply not
in that cell. Both paths are tested (transfers present, and transfers removed to simulate a finished
cell).

---

## 6. Mechanism verification and the consistency check

**Items 1 and 3 test no causal claim.** They are instrumentation: they add stamps and a provenance
field and are required to change nothing. The applicable protocol for them is the byte-identity
proof in section 4, which is the negative-control shape (disable the mechanism - here, remove the
instrumentation - and confirm the outcome is identical), run with its own positive control on
repeatability. No conclusion about any policy is drawn from them.

**Item 2 measures a quantity and so takes the consistency check.** Recorded per cell:

1. **Cross-check against committed measurements.** The positive control is the check on the
   wrapper: `covex-v6-base` at n=16 seed 4 must reproduce its committed digest
   `af8befb9420ad86a` / 12,085 rows (`results/orchestration/live2/frozen_test/c5attr_digest_proofs.json`).
   **If a known-good committed arm fails here, the wrapper is broken and not the arm.** The n=16
   rungs are additionally cross-checked against the concurrent StudyD216-KV025 1x bar cells, same
   arm, same seed, same n, same regime.
2. **Physical plausibility.** Not applicable in the usual form: no latency here is a transfer rate.
   The committed comparison point is the measured in-run decision latency (D109: p99 100.6 / 252.5 /
   994.8 ms at 32 / 64 / 128 devices on flash for policy-core; D115 (1): flash about 2.2x faster
   than the H100 host CPU), and a dry figure far below those is expected because the final rungs are
   not policy-core.
3. **Distribution sanity.** The full distribution is reported for every cell, with `n_distinct` and
   an explicit `constant_where_a_distribution_is_expected` flag. The artefact-spread shape is
   pre-registered as the sweep's main hazard in section 3 and the cross-arm ranking is REFUSED
   rather than reported.
4. **Definition audit.** "decision latency" means `coordinator.py:2127`'s
   `decision_latency_ms`: flash CPU wall-clock inside the arm's `decide`, in a DRY cell. Not an H100
   number, not an engine number, not the in-run live figure D109 reports. The 20 ms budget is D214's
   decision budget. A "cell" is one dry run of one arm at one fleet size in its own process
   (`cf_pd_one_cell`'s one-cell-per-process rule, because a second dry run inside one process does
   not reproduce the first).
5. **Claim linkage.** F14 bears on the decision-latency budget, i.e. whether the policy is
   implementable at fleet size; it bears on no accuracy claim. F3 and the network header bear on
   figure provenance and on no claim about any policy. All three fill gaps that StudyFIGDATA names.
6. **Proxy validity.** One proxy is declared: a **dry** decision latency stands for the live one.
   It is valid for the arm's own compute cost and is **not** valid for a live coordinator under
   HTTP load, where D107 (2)'s submit delay is the quantity that matters; the dry figure is
   therefore a lower bound on the live one and is labelled as such in every output.
7. **Validate the control, not only the result.** Both controls are in place before any comparison
   is read: the committed-digest positive control on the F14 wrapper, and the A/A and B/B
   repeatability control on the byte-identity proof. The A/A control is read **first** and the
   A-vs-B comparison is refused if it fails.

---

## 7. Outstanding, named plainly

0. **THE PROOF CHAIN WAS STOOD DOWN ON INSTRUCTION, AND IS NO LONGER POLLING.** Three things wanted
   the same free window: this proof, and Session B's proofs (b) and (c), which gate
   `FINAL_LADDER_CELLS` and so the paper's critical path. **Session B goes first**, and this work
   yields by construction: the user's own sequencing is "land these before `FINAL_LADDER_CELLS` runs
   if they can be proven in time; otherwise from the first cells after." A poller that fires the
   instant the box frees would beat a session that has to be resumed and then decide, so leaving it
   armed would have been claiming priority by reflex. It was stopped cleanly rather than left
   waiting: the chain wrapper was killed **first** so the sequence could not advance to the F14
   sweep, then the poller. Verified afterwards by scanning `/proc` (never a `pgrep -f` on a
   self-matching pattern) that **no Session F process remains**, that the three StudyD216-KV025
   processes are untouched, and that **no cell of mine ever started**: both result directories are
   empty, so there is no partial or half-written output to distrust. Re-arm is:
   `bash <scratchpad>/d214sessF/chain.sh`, which runs the proof and then the sweep, each cell
   waiting for its own alone window.

1. **THE BYTE-IDENTITY PROOF HAS NOT RUN. It is built and stood down, not armed.** The host
   was held throughout this session by the StudyD216-KV025 chain (and, earlier, by a StudyD213
   digest chain), and running a cell alongside them would have made their digests contention-measured
   without their guards seeing it: that driver identifies foreign live2 processes by the basenames
   under its own tree snapshot, and my new files are not in it, so **my processes are invisible to
   their alone-guard**. Waiting was the only correct option.

   **THIS IS AN OPERATIONAL HAZARD, NOT A QUIRK OF MY SESSION, AND IT IS THE MOST CONSEQUENTIAL
   THING IN THIS REPORT.** The guard enumerates foreign live2 processes by the `.py` basenames found
   under its **own tree snapshot**, so a file it does not know about is invisible to it. A cell can
   therefore record `alone: true` **truthfully by the guard and falsely in fact**. The guard is not
   broken; its census is simply bounded by a tree that may be older than the processes it is trying
   to see, which is the same register error as reading a config instead of reading the object. A
   separate session hit this independently and also waited. The remedy that does not depend on the
   guard being complete: check `ps` and `/proc/<pid>/cwd` directly and **record what you SAW**, not
   what the guard said. My own guards have the same bound, which is why every cell record carries
   the foreign-process census and the loadavg beside the boolean, so a later reader can
   re-adjudicate `alone` from the evidence instead of trusting the flag.

   When it runs it will write
   `results/orchestration/live2/d214_figures/byte_identity/d214_byte_identity.json`.
   **Consequence: the `run_live2_real.py` wiring is NOT committed.** See 5.6.
2. **F14 at 24, 32 and 48 devices has not run**, behind the same window and also stood down. The
   sweep is queued after the proof in the same chain and will write
   `results/orchestration/live2/d214_figures/f14/f14_decision_latency.json`. The n=16 rungs are in
   5.5 and both are comfortably inside the 20 ms budget; **whether p99 crosses 20 ms at 48 devices
   is open and this report does not guess.** Extrapolating from one size would be exactly the
   register error of generalising a single cell's delta to a direction.
3. **F3 has never been exercised on a real live cell**, only on synthetic logs built from the
   committed link arithmetic (5.3). There is no server on flash, so it cannot be: the MEASURED
   stamps only exist on a cell that talked to the real engine. The first H100 live cell run after
   the wiring lands is the test, and `f3_stamp_registers.json` is designed to make its own coverage
   legible on that first cell (`live_cell`, `absent_stamps`, `speed`).
4. **`speed` is now recorded, in `run_live2_real.py`, and it ships in the same held wiring.**
   Resolved rather than left open, but **the two paths differ in register and are not merged**:
   - `--no-split`: the coordinator is in this process, so `co.speed` is **READ BACK OFF THE
     INSTANCE** (`_CO.append(co)` and `type_read_back` beside the value). That is the strong
     register, the same discipline `network_header` uses for the link.
   - **split, which is the default**: the coordinator is in a child process and
     `Live2Coordinator._result()` does not expose `speed`, so **no instance read is available to
     the parent**. Closing that fully would need a field in `coordinator.py` (owned by the H100) or
     in `procsplit.py` (unowned, but on every live cell's hot path, so editing it would widen the
     byte-identity surface for a provenance field). Instead the record proves the weaker but
     **checkable** statement: *this runner never passes `speed`, therefore the applied value is the
     constructor default.* Both halves are verified, not asserted: `speed` is shown absent from the
     `cfg` dict the parent sends (`cfg_keys_checked` lists what was inspected) and the default is
     read out of `Live2Coordinator.__init__`'s signature by introspection. It is labelled
     `DEFAULT, PROVED NOT OVERRIDDEN BY THIS RUNNER`, **not** as a measurement, because
     a default read from a signature is not an instance read, and conflating the two is exactly
     what item 3 exists to prevent.
   - If a runner ever **does** pass `speed`, the record emits
     `UNKNOWN: THE RUNNER PASSED speed AND THE CHILD'S VALUE IS NOT READABLE FROM HERE` with a null
     value, i.e. it **refuses to report a number it cannot see**. Tested, along with a `WARNING`
     that fires when the value is not 1.0 so scaled stamps can never be plotted as observed.

   **Remaining limitation, named:** on the default path the value is a proved default, not an
   observation. One field in `coordinator.py`'s `_result()` would upgrade it, and that file is not
   mine.
5. **The per-request upload join for recalls is a declared join, not a measurement** (section 1).
   It is correct for the committed trace shape and would need revisiting if a question ever carries
   frames; StudyNET-TIER1 N1 records that query delta upload is ABSENT today.
6. **No `research/*.md` or `results/INDEX.md` row was written**, per the ownership list. The row
   text I propose for `research/EXPERIMENTS.md` (a new `StudyD214-FIGINSTR` row) and for
   `results/INDEX.md` is in the session handoff, with the fields that depend on items 1 and 2
   marked as pending.
7. **`fleet/emulator.py` and `fleet/links.py` were NOT needed**, so the question of whether Session
   N's files are clear to write does not need answering.
