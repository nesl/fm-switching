# Working on the shared H100 host

Host: `sn4622120321` · device slug: `h100nvl` · recorded 2026-10-14.

This is a **shared multi-user machine**. Other users run long jobs on it. Treat every
GPU as someone else's unless you have checked it is free, and treat every latency
number from this host as measured under possible interference unless the run log
proves otherwise.

---

## Hardware

| item | value |
|---|---|
| GPUs | 4 × NVIDIA H100 NVL, 95,830 MiB (≈94 GiB) HBM each, driver 570.86.15 |
| NVLink | GPU0↔GPU1 bridged (NV12); GPU2↔GPU3 bridged (NV12); pairs connect over PCIe (NODE) |
| CPU | AMD EPYC 9354, 2 sockets × 32 cores, SMT → 128 threads |
| NUMA | all four GPUs attach to NUMA node 0 (CPUs 0–31, 64–95) |
| RAM | 1.5 TB |
| arch / OS | x86_64, Linux 5.15, Python 3.10 |

Observed 2026-10-14: GPUs 0–2 fully occupied by other users' training jobs
(~400 W, 77–81 °C each); **GPU 3 idle**.

---

## Rule 1 — Use GPU 3 by default

GPU 3 is the preferred device for this project. Before any GPU run:

```bash
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv
```

If GPU 3 shows any process or non-trivial memory use, **do not start** — stop and
ask. Do not fall back to GPUs 0–2 without the user's sign-off.

Claim the GPU in `research/HOSTS.md` (host `sn4622120321`, GPU `H100 (GPU 3)`)
before a long run and mark it done afterwards.

## Rule 2 — Select the device via CUDA_VISIBLE_DEVICES

Scripts written for flash hard-code `cuda:1` (the A6000 there). On this host
`cuda:1` is a busy GPU. Remap instead of editing scripts:

| script uses | launch with | effect |
|---|---|---|
| `cuda:0` / `"cuda"` / `device_map="auto"` | `CUDA_VISIBLE_DEVICES=3` | only GPU 3 visible |
| hard-coded `cuda:1` | `CUDA_VISIBLE_DEVICES=1,3` | logical `cuda:1` = physical GPU 3 |

With `1,3`, physical GPU 1 is also visible to the process — make sure nothing in the
script touches `cuda:0`, and never use `device_map="auto"` in that mode (it would
spread weights onto the busy GPU). Verify at startup:

```python
import torch; print(torch.cuda.get_device_name(1), torch.cuda.mem_get_info(1))
```

`mem_get_info` should report ≈93+ GiB free on the device you intend to use.

## Rule 3 — Pin CPU and memory to NUMA node 0

All GPUs hang off node 0. Keep the host-side process there. `numactl` is not
installed on this host (2026-10-14); use `taskset` with node 0's CPUs:

```bash
CUDA_VISIBLE_DEVICES=3 taskset -c 0-31,64-95 \
    .venv/bin/python experiments/<purpose>/<script>.py ...
```

`taskset` pins CPUs only, not memory; first-touch allocation keeps host memory
mostly on node 0 as a result. If `numactl` becomes available, prefer
`numactl --cpunodebind=0 --membind=0`.

## Rule 4 — Environment

Use the project venv: `source .venv/bin/activate` (torch 2.8.0+cu128,
transformers 5.10.2). `requirements.txt` is pinned for Jetson/aarch64; on this host
`nvidia-cusparselt-cu12==0.8.1` is dropped (conflicts with x86 torch 2.8.0) and
`qwen-vl-utils scipy datasets scikit-learn av` are added, with
`huggingface_hub==1.18.0` held (newer breaks transformers 5.10.2). Not installed:
`vllm`, `flash_attn`, `sentence-transformers`, `open_clip`. Installing `vllm` will
replace torch — use a separate venv if needed.

Note: without `flash_attn`, models fall back to SDPA. Latency is not comparable to
flash's flash-attn numbers until this is resolved or stated (see Rule 6).

---

## Latency measurements on a shared host

Neighbouring jobs do **not** share GPU 3's SMs or HBM. They **do** share:

| shared resource | when it matters | mitigation |
|---|---|---|
| CPU cores | HF `generate()` at small batch is kernel-launch / CPU bound | NUMA pinning (Rule 3); log load average |
| PCIe host bridge, host RAM | host↔device copies (load, input transfer), not on-GPU prefill/decode | keep timed regions on-GPU; exclude loading |
| chassis airflow | sustained runs next to ~400 W neighbours → thermal clock-down | log clocks + throttle reasons |
| the GPU itself | another user may start a job on GPU 3 mid-run | log per-second process list; discard contaminated runs |

### Required for every latency experiment on this host

1. **Run a monitor alongside the experiment** and keep its log with the results:

   ```bash
   nvidia-smi -i 3 --query-gpu=timestamp,utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.sm,clocks_event_reasons.active \
       --format=csv -l 1 > logs/<eid>_gpu3_monitor.csv &
   nvidia-smi --query-compute-apps=timestamp,gpu_uuid,pid,used_memory \
       --format=csv -l 5 > logs/<eid>_gpu_procs.csv &
   ```

   GPU 3 UUID: `GPU-b3c6399e-00c9-2ba7-8bd4-88570c884250`. Any row in
   `_gpu_procs.csv` on that UUID with a PID that is not yours marks the overlapping
   trials as contaminated — rerun them, do not average them in.
   `logs/` is gitignored; summarise the monitor (max temp, min SM clock, any
   throttle reason, any foreign process) in the report.

2. **Warm up** (≥1 discarded rep per condition), then ≥5 timed reps; report spread,
   not just the median (CLAUDE.md consistency check 3).

3. **Interleave conditions** (round-robin over L / fidelity) rather than running
   each condition as a block, so slow drift (thermal, neighbour load) cannot alias
   onto a condition difference.

4. **State caching** explicitly (CLAUDE.md: caching is a methodological parameter).

5. **Provenance**: `stamp(..., device="h100nvl", ...)`, and record in the report
   that the host is shared, which GPU was used, and the monitor summary.

## Rule 6 — Comparability

`h100nvl` is a **new tier**, not a substitute for `a6000`, `rtx3090ti`, or
`jetson_orin`. Do not mix H100 timings into `results/cost/cost_matrix.csv` rows for
other tiers or compare them to committed curves without labelling the hardware and
attention-backend difference. Result files carry the `h100nvl` tier slug per the
naming schema in CLAUDE.md.

Fidelity / accuracy experiments (device-independent outputs) may run here freely;
note the host in provenance.
