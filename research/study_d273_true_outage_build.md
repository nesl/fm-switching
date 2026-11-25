# D273 (1): TRUE OUTAGE SEMANTICS BUILT AND PROVED. NO DOSE IS ZERO. AND A LOST-FRAME SIGNAL IS UNEXPRESSIBLE, WHICH IS THE FOURTH INDEPENDENT BLINDNESS FOUND TODAY.

**CPU only, no cells, no GPU, nothing committed to `experiments/`. D = 120 s, the centred window at 540.0 to
660.0 and the nested victims are ALL UNTOUCHED. The buffered variant is the named CLOSED ALTERNATIVE at
`722c449f`.**

## 1. THE DOSE, IN THE CONDITION THAT WILL RUN. NO DOSE IS ZERO.

| pair | added victims | **DISTINCT questions** | ask instances |
|---|---|---|---|
| s4, k 1 to 3 | robo003, robo009 | **1** | 5 |
| s4, k 3 to 5 | robo004, robo010 | **2** | 9 |
| s5, k 1 to 3 | robo007, robo009 | **1** | 1 |
| s5, k 3 to 5 | robo006, robo008 | **3** | 22 |
**The drain-bounded column that was zero everywhere is now marked NOT APPLICABLE in the artefact and in the
tool's own output, because under true semantics the frames NEVER ARRIVE and reporting zeros there would read
as "no dose", which is exactly backwards.**
*** IT REMAINS A WEAK DOSE AND THE TOOL SAYS SO ON EVERY PAIR: one to three distinct questions out of 229.
THE USER HAS SINCE RULED THAT THE FLEET TOTAL CANNOT CARRY THE RESULT, BECAUSE THESE COUNTS SIT BELOW THE
ROBOT cbd SAME-CODE OBSERVATION OF 2, AND THE PRIMARY READOUT IS NOW PER AFFECTED QUESTION. ***

## 2. THE SWITCH, AND ONE THING THE PROOF CAUGHT THAT ASSUMPTION WOULD HAVE GOT WRONG

**`outage_semantics`, DEFAULT `buffered`, so every committed cell and every other study is untouched.
`trace.py:1087-1102` marks a victim's in-window batch for REMOVAL instead of re-timing it; `:1109-1229`
removes the records and corrects the cloud's accounting so every later `cum_tokens` and every later
`history_tokens` falls by exactly the lost frames. The READ that makes it causal is `emulator.py:233-240`,
which forwards `cum_tokens` to the coordinator as the session's history size. THE DEVICE IS UNTOUCHED BY
CONSTRUCTION: `device_answers` is built before the block and never read by it.**
*** THE D2 HEADER IS NOT A FRAME. At this design point some victim sessions START INSIDE the window, so the
batch carrying that session's one-off 31-token D2 header is itself lost, and subtracting the lost records'
own `est_tokens` took the header out of the cloud's history too. THE CUT IS NOW 90 TOKENS PER LOST FRAME AND
THE HEADER IS RE-ATTRIBUTED TO THE FIRST SURVIVING BATCH, which also preserves the committed invariant that
`cum_tokens` is the running sum of `est_tokens`. The affected sessions and the re-attribution are listed in
the meta rather than left silent. ***

## 3. BOTH PROOF HALVES PASS AT ALL SIX CELLS

| cell | half A | **half B** | neg control | lost frames | lost tokens | 90/frame exactly |
|---|---|---|---|---|---|---|
| s4 k1 / k3 / k5 | PASS | **PASS** | PASS | 60 / 180 / 298 | 5,400 / 16,200 / 26,820 | yes |
| s5 k1 / k3 / k5 | PASS | **PASS** | PASS | 60 / 180 / 299 | 5,400 / 16,200 / 26,910 | yes |
**Half A checks the missing set is EXACTLY the victims' in-window records, by SET EQUALITY and not a count,
that nothing else moved, that `cum_tokens` and every later `history_tokens` fall by exactly the frames lost
at or before their own time, and that ask times do not move.**
*** HALF B IS THE ONE FLAGGED AS THE SILENT-FAILURE RISK AND IT PASSES: `device_answers` IS BYTE-IDENTICAL
between switch off and switch on, with `history_tokens`, `device_latency_s`, `device_answer`,
`device_correct` and `gold_letter` CHECKED ROW BY ROW. Had the switch shortened the device history too, every
cell would have been invalid WITHOUT failing the off-identity proof. ***
**And the lost counts equal the buffered variant's DEFERRED counts exactly, which cross-checks the two
semantics against each other.**
**Switch off: 0 mismatches for six arms at BOTH mixes, with the instrument's own determinism control passing
first, plus trace-level byte identity and the committed band cells still identical.**

*** AND THE FIRST VERSION OF THIS PROOF FAILED FOR A REASON WORTH MORE THAN THE PASS: it compared TRUE
against BUFFERED and found 0 expected-missing against 298 actually missing. THE COMPARATOR WAS WRONG, NOT
THE SWITCH, because under buffered those records had ALREADY been re-timed so no offer time was inside the
window any more. The reference is now the NO-OUTAGE trace, the only one whose offers still carry their
original times, and the proof certifies the buffered arm on the way past. THAT IS THE "ONE SIDE OF THE
COMPARISON NEVER AUDITED" SHAPE, CAUGHT BY THE PROOF RATHER THAN BY A SUSPICIOUS RESULT. ***

## *** 4. THE POLICY CANNOT SEE THAT FRAMES WERE LOST. THIS IS THE FOURTH INDEPENDENT BLINDNESS FOUND TODAY. ***

**NO policy code was changed and none is recommended on the strength of it.**
- **`Observation` and its nested `RecallQuery`, `CloudState`, `EvidenceItem` and `NetworkState` carry NO
  field naming an outage, a loss, a gap or an incomplete history.**
- *** WORSE THAN SILENT: `NetworkState.connected` IS HARD-CODED `True` AT `cstate.py:662`, the only
  construction on the live2 path, SO DURING THE OUTAGE THE OBSERVATION SAYS THE VICTIM IS CONNECTED. And
  `Observation.device_always_warm` is hard-coded `True` at `interface.py:234`, documented as "a fixed design
  assumption, not an observation". ***
- *** THERE IS A DECLARED CHANNEL AND IT IS NEVER FIRED: `"connectivity_change"` is in `EPOCH_KINDS`
  (`interface.py:48-51`) and repeated in the coordinator's own `_EPOCHS` (`coordinator.py:2451-2452`), but
  the epoch is set to `"tick"` at `coordinator.py:481` and overwritten only by `_ingest`, which returns only
  `"stream_arrival"` or `"recall_arrival"`, with `:576` COERCING ANYTHING ELSE TO `"tick"`. THE ONLY EMITTER
  IN THE TREE IS THE SMOKE HARNESS. Declared, validated, repeated, and never emitted. ***
**So with `host_kv_fraction` write-only, the declared host size never read, and HOST-WARM unreachable, THIS
IS THE FOURTH INDEPENDENT WAY THE HARNESS IS BLIND TO THE TIER AND THE LINK IT IS SUPPOSED TO BE STUDYING.**

### BUT THE MAGNITUDE IS VISIBLE, AND ROUTING TO THE DEVICE IS FULLY EXPRESSIBLE
**`RecallQuery.readiness_tokens` comes from `cstate.py:683` via `cstate.py:669`, fed from `cum_tokens`, and
under this switch IT FALLS for affected sessions, 4 to 38 questions per cell, with the `D2` `EvidenceItem`
carrying the same reduced value.** *** SO THE POLICY SEES A SMALLER HISTORY BUT CANNOT TELL AN
OUTAGE-SHORTENED SESSION FROM A YOUNG ONE. ***
**And `DEVICE` is in `RECALL_ACTIONS`, enforced at `interface.py:389-390` and honoured at
`coordinator.py:998-1009`, reachable from six baselines and four arm families. UNDER THIS RULING THE DEVICE
HISTORY IS COMPLETE, SO A QUESTION ROUTED THERE IS ANSWERED FROM FULL EVIDENCE: ROUTING TO THE DEVICE IS THE
CORRECT RESPONSE AND IT IS FULLY EXPRESSIBLE.**
*** INVALIDATION CONDITION 13, NOW IN THE PREREG: A CLAIM THAT DEPENDS ON AN ARM **RECOGNISING** THE OUTAGE
IS UNEXPRESSIBLE BEFORE IT IS RUN. A CLAIM THAT DEPENDS ONLY ON AN ARM REACTING TO A **SMALLER CLOUD
HISTORY** IS EXPRESSIBLE. NO RESULT MAY BE WRITTEN WITHOUT SAYING WHICH OF THE TWO IT RESTS ON. ***
**Adding a lost-frame signal to `Observation` would be a NEW MECHANISM, not a fix, and is the user's to
rule on.**

## 5. THE ABANDON CHECK IS REPOINTED, AND THE DEMOTED METRIC IS LABELLED
**It now scores on `correct_answers_delivered_by_deadline` AND `cloud_accuracy_on_served`, the latter with
its own arm-dependent `cloud_answers_available` denominator quoted beside it. `robot_pool_on_time` is still
reported but tagged DECIDES_NOTHING and excluded from the verdict, since it read 121/132 at BOTH k. The dose
it uses is the MISSED-EVIDENCE dose, because both deciding metrics are correctness measures; the forced
device-only count survives only as the floor for the demoted metric.**
**The driver's `_lost` token is refused without an outage, without the flag in the launch arguments, without
`outage.semantics == "true"` in the cell's own `trace_meta`, and UNLESS THE META SHOWS FRAMES ACTUALLY LOST
AT 90 TOKENS PER FRAME.** *** A TRUE-OUTAGE CELL THAT LOST NOTHING IS AN ABSENT LINK WEARING A LOST-FRAMES
NAME, AND THE DRIVER NOW REFUSES IT RATHER THAN RUNNING IT. ***
