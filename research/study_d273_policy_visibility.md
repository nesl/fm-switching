# D273 (1): WHAT CAN THE POLICY SEE AFTER A RECONNECT, AND CAN IT ACT ON IT

**Requested beside the build. READ-ONLY: NO POLICY CODE WAS CHANGED.** Every claim below is a
`file:line` in the tree read through `origin/main` = `f8ae560d80e69f9028517f8bae08dede625089ba`,
at which all five files the D266 build touches are byte-identical to the sha it was built on.
**The three questions are answered separately because they have three different answers, and
collapsing them would lose the one that matters.**

---

## 1. DOES `Observation` TELL THE POLICY FRAMES WERE LOST? NO. NOTHING DOES.

`Observation` is `experiments/orchestration/baselines/interface.py:225-242` and carries exactly:
`now_s`, `epoch`, `streams`, `recall`, `cloud`, `budget_remaining_gpu_s`, `device_always_warm`,
`live_sessions`. Its nested types are `EpisodicStream` (`:95`), `RecallQuery` (`:193-211`),
`CloudState` (`:214-222`), `EvidenceItem` (`:185-190`) and `NetworkState` (`:88-92`).

**No field in any of them names an outage, a loss, a gap, a dropped frame or an incomplete
history.** The two fields that come closest both point the wrong way:

- **`Observation.device_always_warm` is hard-coded `True`** at `interface.py:234`, and its own
  comment says why it cannot help: "a fixed design assumption, not an observation".
- **`NetworkState.connected` is hard-coded `True`** at `live2/cstate.py:662`:
  `network=NetworkState(connected=True, uplink_bps=..., rtt_s=...)`. There is no other
  construction of `NetworkState` on the live2 path. **So during the outage window the observation
  the policy receives says the victim is CONNECTED.** That is not a missing signal, it is a signal
  whose only value is the wrong one.

## 2. THERE IS A CHANNEL THAT COULD HAVE CARRIED IT, AND IT IS NEVER FIRED

`EPOCH_KINDS` includes **`"connectivity_change"`** (`interface.py:48-51`), and the live2
coordinator repeats it in its own `_EPOCHS` tuple (`live2/coordinator.py:2451-2452`). So the
interface has a named epoch for exactly this event.

**Nothing on the run path ever produces it.** The epoch handed to the observation is built at
`coordinator.py:481` (`epoch = "tick"`), then overwritten only by the return value of `_ingest`
(`:483`, `:486`), and `_ingest` can return only `"stream_arrival"` (`:723`, `:740`, `:745`) or
`"recall_arrival"` (`:749`). `coordinator.py:576` then coerces anything outside `_EPOCHS` to
`"tick"`. **The only emitter of `connectivity_change` in the whole tree is the smoke replay
harness, `baselines/smoke/replay.py:171`, which is not the run path.**

*** SO THE LOST-FRAME SIGNAL IS ABSENT FROM `Observation`, AND THE ONE DECLARED CHANNEL THAT COULD
CARRY IT IS DECLARED, VALIDATED, REPEATED IN THE COORDINATOR, AND NEVER EMITTED. In this project's
own vocabulary that is an UNEXPRESSIBLE channel: the harness discards the channel the mechanism
would act through. It is the same shape as the three findings established today - `host_kv_fraction`
write-only, the declared host size with no read that changes a decision, HOST-WARM unreachable -
and it is a FINDING ABOUT THE HARNESS, not a gap in this build. ***

## 3. BUT THE MAGNITUDE IS VISIBLE, AND THAT IS NOT THE SAME THING AS THE CAUSE

This is the part that would be wrong to report as a flat absence.

`RecallQuery.readiness_tokens` is set at `live2/cstate.py:683` from `tok = max(int(s.est_tokens), 1)`
at `:669`, and `s.est_tokens` is the coordinator's belief about the session's history size, fed from
the wire's `cum_tokens` at `fleet/emulator.py:233-240`. **Under the D273 (1) true-outage switch
`cum_tokens` falls by exactly the lost frames, so `readiness_tokens` is SMALLER for an affected
session, and the `EvidenceItem` for `D2` built at `cstate.py:671-674` carries that same reduced
`tok`.** Measured on the proof traces: 4 to 38 questions per cell see a smaller cloud-side history.

**So the policy can see that a session's history is smaller than it would have been. It cannot see
WHY.** A session short by 60 frames because its uplink was out is indistinguishable, in everything
`Observation` carries, from a session that is simply younger or joined later. There is no field
that separates "this history is small" from "this history is incomplete".

## 4. CAN AN ARM ROUTE AN AFFECTED QUESTION TO THE DEVICE? YES, AND THE ACTION HAS A REAL READ SITE

- **`RECALL_ACTIONS = ("DEVICE", "CLOUD", "DEFER", "REJECT")`** at `interface.py:47`, and
  `validate_action` enforces membership at `interface.py:389-390`. So `DEVICE` is expressible.
- **The coordinator honours it** at `live2/coordinator.py:998-1009`: a `DEVICE` or `REJECT`
  decision sets `o.state = "declined"`, records `served_by="device"`, and sets
  `served_at = o.t_event + self._device_wait_s(o)` when the arm reads device answers. This is a
  read that changes the outcome, not a counter.
- The action is reachable by many arms: `"DEVICE"` appears in `live2/arms.py`, `arms_policy.py`,
  `arms_v6cf_device.py`, `arms_covex_v2.py` and in the `perllm`, `naive`, `constructed`, `ecollm`,
  `inarvl` and `streamscout` baselines.

**And the device side is intact under this ruling by construction**, proved on the artefact in
`d273_true_outage_proofs.py` half B: `device_answers` is byte-identical between switch off and
switch on, so a question routed to the device is answered from a COMPLETE history. **Routing to the
device is therefore the correct response to this condition and it is fully expressible.**

---

## 5. THE ANSWER IN ONE PARAGRAPH, SAID PLAINLY

**The policy cannot respond to a lost-frame condition AS SUCH, even in principle, because nothing
in `Observation` says frames were lost, the one epoch that could say so is never emitted on the run
path, and the only `connected` flag it does carry is hard-coded `True`. What it can respond to is a
SMALLER HISTORY, which it does see, through `readiness_tokens` and the `D2` `EvidenceItem`; and it
can act, because `DEVICE` is in the action space and the coordinator honours it. So an arm could in
principle route a question whose cloud history looks thin to the device, and that would be the right
move here, but it would be reacting to a size and not to a cause, and it could not tell an
outage-shortened session from a young one.** **Any NESTOUT result that depends on an arm
RECOGNISING the outage is therefore unexpressible before it is run; a result that depends only on
an arm reacting to a smaller cloud history is expressible.** That distinction belongs in the
NESTOUT prereg, and it is recorded there.

**NO POLICY CODE WAS CHANGED, and none should be changed on the strength of this note: adding a
lost-frame signal to `Observation` would be a new mechanism, not a fix, and it is the user's to
rule on.**
