# GPU runbook: E-engine-hosttier (H100 session, GPU 3, driver-idle block)

Scripts: experiments/orchestration/live2/engine_hosttier_probe.py and engine_hosttier_probe_analyse.py (pushed first).
Env: the vLLM venv the cells use (/home/pragya/.venvs/fm-switching-vllm/bin/vllm is argv[0] of the committed command; pass
--vllm-bin if the path differs, it is printed in the flag diff). Probe port 8131 (cells use 8031).

## 0. Abort conditions (check ALL, any one = do not start, release the claim, report)
1. Any cell start-up in progress or due before the block ends (the probe is a ~45 min DRIVER-IDLE BLOCK: hold the driver idle, GPU 2 is the cell GPU).
2. GPU 3 not idle: `nvidia-smi -i 3` shows memory.used > 1000 MiB, util > 5 percent, or any compute process on GPU 3 (research/HOST_H100.md Rule 1: stop and ask; never fall back to GPUs 0-2).
3. Another `vllm serve` process alive (the script refuses unless --allow-other-vllm).
4. Free host memory below the margin: MemAvailable < 30 GB at 13.5 GiB (45 GB for --host-gib 27). Derivation: mmap 14.5 GB x 1.25 (shm file plus mapped pages) = 18.1 GB, plus 8 GB for pinned buffers, mm cache (text prompts leave it empty) and weight staging, rounded up to 30 GB. Also /dev/shm free must exceed 1.05 x the mmap size (the script checks both).
5. The flag diff printed at start is not exactly "argv[6]: committed='8031' probe='8131'" (plus argv[0] only if --vllm-bin is given). The script aborts by itself; do not override.
6. Part A: connector is not OffloadingConnector, the mmap is not a whole number of 4,194,304-byte chunks, or GPU blocks missing: the script aborts (Step 0 invalidators).

## 1. Claim and check
```
cd <repo>; git fetch origin; git rev-parse origin/main   # run from a tree at origin's tip
# claim: add a row to research/HOSTS.md (host sn4622120321, GPU H100 (GPU 3), CC, E-engine-hosttier host-tier probe, <date>, in progress); this is a docs change for the next push window
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv
free -g; grep -E "MemAvailable|HugePages_Total" /proc/meminfo; df -h /dev/shm
ls -la /dev/shm/vllm_offload_*.mmap 2>/dev/null   # stale files from a crashed launch: delete only your own, never a running cell's
ps -eo pid,args | grep -E "vllm serve|vllm.entrypoints" | grep -v grep
```
## 2. Run order A, P1, P2, P3 (one launch, 13.5 GiB, the script does A then P1 x3, P2 x3, P3 x3 in this order)
```
export CUDA_VISIBLE_DEVICES=3
taskset -c 0-31,64-95 conda run -n fmtk --no-capture-output python experiments/orchestration/live2/engine_hosttier_probe.py --host-gib 13.5 --gpu 3 --port 8131 > /tmp/engine_probe_h135.out 2>&1
```
(Use the repo's run_in_background mechanism, never `&` inside conda run. The server child inherits the taskset affinity and CUDA_VISIBLE_DEVICES.) Add `--p4` for the optional concurrent part (7 chains x n=1,164, adds about 5 min). Dry check before the real run: `--dry-run --out-dir /tmp/x` needs no GPU.
Optional 27 GiB repeat (only if Part A or P1 at 13.5 is not explained by the formula; P1 + P3 only, P2 is skipped by design): same command with `--host-gib 27`; it launches WITHOUT --num-gpu-blocks-override, with the 1x max-model-len, as the committed 1x header says.
Outputs: results/orchestration/live2/engine_probe/hosttier_probe_h135_h100nvl{.json,_requests.jsonl,_metrics.jsonl,_server.log.gz} (and _h27_ for the repeat).
## 3. Analysis (CPU, after the server is gone)
```
conda run -n fmtk python -I experiments/orchestration/live2/engine_hosttier_probe_analyse.py results/orchestration/live2/engine_probe/hosttier_probe_h135_h100nvl | tee results/orchestration/live2/engine_probe/hosttier_probe_h135_h100nvl_analysis.txt
```
Read: A lines, P1 per-chain list and DIAGNOSIS, P2 R-host PASS/MISMATCH plus R-gpu and R-gone INFO, P3 lines, the rival table with OVERALL DIAGNOSIS, SHADOW PARAMETERS. Any MISMATCH is a finding about the engine, not a failure of the probe, provided the controls passed (P1 negative control reads 0, positive control reads n blocks).
## 4. Exit
The script removes /dev/shm/vllm_offload_*.mmap files that appeared during its launch, gzips the server log, and kills the server process group. Then check: `ps -eo pid,args | grep "vllm serve" | grep -v grep` (no probe server on 8131), `ls /dev/shm/vllm_offload_*` (nothing of yours), `nvidia-smi -i 3` back to idle. Release the HOSTS.md claim (status done, time). Stop and ask the user to commit the scoped list: the 4 or 5 files under results/orchestration/live2/engine_probe/, the INDEX.md row, the EXPERIMENTS.md row update (verdict, consistency_check, mechanism_verification), the STATUS.md date.

## Expected wall-clock (13.5 GiB launch; design estimate, prefill 5,600 tok/s from StudyD7, not measured on this probe)
Start-up about 65 s (committed startup_s 63.7 to 66.7); requests about 201 (P1 3 x 34, P2 3 x 25, P3 3 x 8, all incl. flushes and the P1 control; the 201-request dry-run count) with about 0.9M prefill tokens = about 3 min pure prefill plus 2 s drain-stable wait per request plus polling = about 12 to 20 min; with P4 add about 5 min. Budget the block at 45 minutes (design), 1.2 GPU-hours with the 27 GiB repeat (about 228 requests, about 15 min plus launch).
Median generation length: 1 token (one request per P3 trial generates 256 tokens); prefill-dominated; no decode-latency claim is made from this probe.

## Caching statement (CLAUDE.md rule)
Prefix caching ON (committed flags); host tier ON. Cache state is the thing under test: "cold" means a never-sent chain (control, reads 0). GPU local hits and host hits are separated per request by prompt_tokens_by_source deltas. Flush requests (31,361 tokens, max_offload_tokens 0) displace the GPU pool without storing to host.

## 5. Addendum (loop, 2026-11-26): RUN BOTH MODES; deviations from the design; what to report
The user APPROVED this probe (E-engine-hosttier, PROPOSED-APPROVED in research/EXPERIMENTS.md): GPU 3, a DRIVER-IDLE BLOCK, never overlapping a cell start-up. The scripts are on origin (window V, origin 4de37c5e: blobs d2eaed6d and 9499100e); they were CPU-tested against a fake engine only: **the first real launch is their test** (the log regexes for the GPU block count and the `ignore_eos` request field are unconfirmed against real vLLM 0.31.0 output; if the engine start-up regex fails the script falls back to the metrics: report what failed rather than editing the script mid-run).
Run order: (1) the DEFAULT mode (P2 and P4 read-backs carry `max_offload_tokens: 0`, so a re-store does not evict the third chain's tail: C should read 1,164); (2) the LITERAL mode `--reads-store` (design-literal reads: C reads 1,128 in the source-rule model); each is about 12 to 20 minutes of requests plus about 65 s start-up; outputs from the second run need a different file stem: pass `--tag reads_store` if the script has the option, else copy the first run's outputs aside before the second launch (state which). Deviations from the design, flagged: P1 adds a negative-control chain (34 requests); P1 chain length n = 256 at 13.5 GiB and 250 at 27 GiB; the R-gpu step is a mixed GPU-plus-host hit (the pure-GPU-hit hypothesis is not isolated); scheduler.py:1182-1185 has a comment that reads differently from the code under it: the probe follows the design's reading and tests it.
Report back (to the flash session): the analysis output verbatim (A lines, P1 per-chain list and DIAGNOSIS, P2 R-host PASS/MISMATCH and R-gpu / R-gone INFO, P3 lines, the rival table OVERALL DIAGNOSIS, SHADOW PARAMETERS), both modes; any abort; the server-log gz path; GPU 3 release time. A MISMATCH is a finding about the engine, not a failure of the probe. Acceptance of any shadow change that follows is under the committed rule (c82e2289), unchanged.
