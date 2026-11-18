# scale_64: what is kept, and how to regenerate the rest

Check (g) of StudyLIVE2-fleet: 64 devices, 180 s, both upload modes, stub coordinator, CPU only
on flash. **NOT A MEASUREMENT.** It is a property of this box: scheduling lateness and the
emulator's own CPU use. Re-run after the D95 / D96 amendment, so it exercises the
generator-assigned `opportunity_id`s (D96 (1)) and the canonical per-mode fairness digest
(D96 (2)).

Kept: `scale_summary.json`, `trace/trace_meta.json`, `run_A/run_meta.json`, `run_B/run_meta.json`.

Deleted because they are byte-for-byte regenerable from the seed and were 17 MB of stub output:
`trace/trace.jsonl`, `trace/device_answers.jsonl`, and each run's `outcomes.jsonl` and
`requests.jsonl`. `trace/trace_meta.json` carries `trace_sha256`, `fairness_digest_A` and
`fairness_digest_B`, so a regenerated trace is verifiable against what was run.

To regenerate:

    cd experiments/orchestration/live2/fleet/tests
    python3 test_scale.py --devices 64 --run-s 180 --ratio 50:50 --seed 1 \
        --out results/orchestration/live2/fleet/scale_64
