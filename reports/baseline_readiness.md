# Baseline readiness for the D164 final workload

Which baseline arms may run on the final workload (16 devices, EP-G default, per-frame upload,
rq30, deadlines 1 / 3 / 2 s, memory 1x, seeds 4 to 7), and what each one is still waiting on.
Status as of 2026-11-21. The driver's own gate is `runs/DEVWAIT_READY`; this file is the reasoning
behind it.

## Released

| arm | released because |
|---|---|
| edf (C_inflight 8), llf, b7-edf-feasibility, always-cloud-fcfs, simplestream, querystream-proactive, mooncake, warm-all-lru, hybrid-F-lhreq | no device wait, no cascade threshold; nothing gates them |
| attentionstore-prefetch | published prefetch proofs PASS (393 prefetch-ahead prefills against the base's 374; Step 2b PASS) |
| r3-streaming, streamscout | device wait fully MEASURED, fallback counter 0, Step 2b moves decisions (`devwait_proofs.json`) |

## Held, with the specific blocker

| arm | blocker |
|---|---|
| confidence-cascade, cascade-routing | device wait is measured (fallback 0), but D164 also requires the pre-registered DEV threshold calibration per card and per confidence type (mcq / free-form / point, point declared weak). NOT committed, so these stay held. |
| kvflow-prefetch | its published prefetch does not pass its own proofs on this harness: characteristic decision UNEXPRESSIBLE (the arm asked for 8,600 fetches and `validate_action` refused all 8,600), Step 2b an ABSENT LINK. CUTOFF 2026-11-28; if unproved by then it is reported as "published mechanism not expressible in this harness" and never run partially. |

## DROPPED

**thinking-qwenvl** is dropped from the live2 baseline list and from the scorer's `CASCADE_ARMS`.

It was **never ported to live2**: `arms.make_arm("thinking-qwenvl")` raises `unknown arm`. It can
therefore be neither run nor released, and while it sat in `CASCADE_ARMS` the cascade list claimed
five arms where four exist, which inflated every per-arm count derived from that list.

Its StudyB artefacts for the EARLIER simulator are deliberately left in place and not deleted
(`baselines/thinking_qwenvl_adapted.py`, `cards/thinking_qwenvl.md`, `registry.yaml`, and the
sim-era tests and reports that reference them). Dropping it from the live2 list is a statement
about what live2 can run, not a retraction of that port.

## Device-wait register, which every cascade-style arm's cells must carry

Cells run BEFORE the measured device wait landed are labelled **proxy-0.567-cross-type** and feed
no headline: the committed code used `DEV_LAT_S = 0.567 s`, a ROBOT RECALL latency, as the wait for
dashcam instants and single-shot questions as well, and on a 300 s 16-device cell that was 14,118
of 14,201 lookups. Affected cells are listed in
`results/orchestration/live2/frozen_test/devwait_cross_type_label.json`.

The measured tables that replaced it are in
`results/device/study_devlat/orin_device_latency_tables.json`, **with a stack caveat recorded
beside them**: the single-shot table is on the Jetson deployment default, while the dashcam and
robot tables were produced with `--mm-processor-kwargs size.shortest_edge 4096` forced for H100
parity, which is not the deployment default. The three tables are therefore not mutually
calibrated.
