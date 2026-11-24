# HELD, NOT APPLIED: the D214 items 1 and 3 wiring for `run_live2_real.py`

This directory contains a patch that is **deliberately not applied**. `run_live2_real.py` in this
repository is the committed, un-instrumented runner, and **nothing imports or applies anything
here**. The patch is committed only so the work is durable and reviewable: it previously existed
only in a session scratchpad under `/tmp`, which a reboot or a routine cleanup can clear.

## Why it is held

The user's constraint on the D214 figure instrumentation is **"logging only; must be byte-identical
in decisions for every arm (prove it on dry s4, ALONE)."** The five modules it calls
(`f3_latency_stamps.py`, `network_header.py`, `f14_one_cell.py`,
`f14_decision_latency_driver.py`, `d214_byte_identity_proof.py`) are committed and active, and they
are safe because **no committed runner imports them**. This patch is the one change that would put
code on the live path, so it waits for its paired-cell proof rather than landing on an argument.

Status at the time of writing: the proof is **built and stood down, not failed**. It had no ALONE
window (the box was held by StudyD216-KV025, then by Session B's `FINAL_LADDER_CELLS` proofs and
E1's byte-identity sweep), and it must not run beside another session's cells.

## What the patch does

Three things, all of which run **after `em.run()` has returned**:

1. writes the F3 per-request latency stamps and dumps `links.UplinkQueue.log`;
2. writes the applied link model, read off the emulator object, into `run_meta.json`,
   `header.json` and `cell.json` (D214 item 3);
3. records `speed`, so the register of `t_first_token` and `t_done` is verified rather than assumed.

It adds exactly **two statements inside the run**, both list appends of a reference to an object
that already exists (`_EMU.append(em)`, `_CO.append(co)`), plus one pure rebinding. That claim is
not a comment: `d214_byte_identity_proof.in_run_additions` recomputes it from the two files by AST,
and `check_self_test` injects four decision-changing statements and requires all four to be
rejected.

## To apply it (only after its proof passes)

    git show <base-sha>:experiments/orchestration/live2/run_live2_real.py > /tmp/base.py
    patch /tmp/base.py < run_live2_real.d214_wiring.patch

The patch is against base sha `10dae57ddc6e32acaa4599bba2aa597237119ddb`. The base file's md5 is
`9d4b35e2c59a5b8905f2de509ebc414d` and the patched result's is
`9435b3a7d8039bf27a271c2e596f4d8b`; **verify both** before using it. If `run_live2_real.py` has
moved on origin since that sha, **do not force the patch**: re-apply the three blocks by hand onto
the current file, or the change would silently revert someone else's work.

Full rationale, the register table for every stamp, and the proof design:
`reports/study_d214_figure_instrumentation.md`.
