# StudyENG1f-disk: a disk tier for computed KV blocks (open question Q12)

Status: COMPLETE 2026-11-18 06:36 (overnight, unattended, under the user's protocol). **Verdict: D2 SUPPORTED by the concurrency condition alone; disk reload dominates recompute solo and under load; write-through costs +18.8 % TTFT at P40.** Pre-registered in research/EXPERIMENTS.md
(StudyENG1f-disk) before any run.

## 0. Pre-flight (items 1 to 4) and its gate

**Item 1, mechanism (vLLM 0.31.0 as installed, `~/.venvs/fm-switching-vllm`).**

| way to persist KV to local disk | works with 0.31.0 as installed | extra packages | engine change beyond the connector | source |
|---|---|---|---|---|
| native offloading connector, `TieringOffloadingSpec` with a `fs` secondary tier | yes, in-tree (`vllm/v1/kv_offload/tiering/fs/manager.py`, registered in `tiering/factory.py` as "fs") | none | the same `OffloadingConnector`; the CPU primary tier is `CPUPrimaryTierOffloadingManager`, a subclass of the native `CPUOffloadingManager` with the same LRU policy; every chunk stored to the CPU tier is cascaded (written through) to disk by 16 + 16 I/O threads in the engine process; no eviction on the disk tier; O_DIRECT when the filesystem supports it (`tiering/fs/io.py: probe_o_direct`) | `vllm/v1/kv_offload/tiering/spec.py` lines 1 to 50; `vllm/config/vllm.py` lines 1124 to 1157 (the native flags build `OffloadingConnector` with `{"cpu_bytes_to_use": size x 2^30}` and the default `CPUOffloadingSpec`) |
| LMCache (`lmcache_connector.py`, `lmcache_mp_connector.py`, local-disk backend) | connector code present; the `lmcache` package is NOT installed | yes (`lmcache`, which pins its own vLLM / torch builds) | external cache server process; not pursued (a separate venv would be needed and it changes the serving stack) | `vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py` |
| other in-tree tiers (`p2p`, `obj`, `kvcr`, `example`) | present | network / object-store backends | not local disk | `tiering/factory.py` |

Chosen: the native fs tier. The flag diff against ENG1c's DE_c38 server is exactly
`--kv-offloading-backend native --kv-offloading-size 38` replaced by `--kv-transfer-config` for the same connector with
`spec_name TieringOffloadingSpec`, `cpu_bytes_to_use` 38 GiB and `secondary_tiers [{"type": "fs", "root_dir":
~/data/eng1f_kv/fs}]`; logged per server. Item 2: no new package, no other vLLM version, main environment untouched.

**Item 3, disk.** The KV files live on the root filesystem: ext4 on `/dev/nvme0n1p4`, a Samsung SSD 990 PRO 4TB (NVMe,
non-rotational), 92 % full, 293 GB free at the start. (A 28 TB RAID0 of four Samsung PM9A3 NVMe at `/data` has 4.6 TB
free but has no directory this user can write; not used.) Raw sequential bandwidth on the KV directory with direct I/O
(8 GiB file, 16 MiB blocks): write 2.5 GB/s (`dd oflag=direct conv=fsync`), read 3.7 and 3.6 GB/s
(`dd iflag=direct`, twice); `fincore` showed 0 bytes resident after the reads. Page cache: dropping caches is not
permitted (no root) and files larger than RAM headroom are impossible (about 1.46 TB of RAM free), so the measurement
keeps the page cache out by (i) the disk tier's own O_DIRECT I/O (a server whose log shows the buffered fallback is
stopped) and (ii) `fincore` showing 0 bytes resident for the targets' KV files before every disk-state measurement.
Disk budget: the tier writes through EVERY stored chunk (256 KiB per token, about 95 MB per 378-token background
request, 2.9 GB per 11k history) and never evicts, so the runner deletes this study's own unprotected KV files after
each filler history and each run, keeps the KV directory <= 100 GB and the filesystem >= 150 GB free (hard stop).

**Item 4, time.** Equivalence gate and Part 1 about 45 min; Part 2 about 45 min per load; Part 3 about 30 min; Part 4
about 30 min; server starts about 2 min each: about 3.5 to 4 h in total, under 6 h, so the full order runs (reduced
order kept as the fallback).

**Gate (pre-registered in the EXPERIMENTS.md row, F1 to F3 and F7): PASS** on items 1 to 4 as above; F3 is re-checked
per server (O_DIRECT) and per disk-state batch (fincore).

## 1. Fixed before any Part 1 data (written 2026-11-17 22:25, while the equivalence gate was running)

Part 1 sanity rule (the prompt: host-warm and cold reproduce committed values within noise, stop if not), at 11k:
host-warm median TTFT within 0.17 +/- 0.10 s (StudyENG1: host 0.17 s, GPU 0.10 s) and cold median TTFT within 0.8x to
1.25x of 2.74 s (StudyENG1 cold, 11,184 tokens). Both measured on the same disk-tier server as the disk state.

Construction details fixed before data: the disk-only state is built by natural eviction with the server running
(targets built, then fresh filler of 1.4 x (host capacity + GPU pool) tokens); the host-warm state by 1.25 x the GPU
pool of fresh filler after the target; recalls for host and disk use uuid references (images in the processor cache),
cold uses image bytes; every recall carries the question with ESC_MAX_TOKENS. Part 2 acts on 11k targets only; Part 3
uses 10 repetitions per concurrency level; Part 4 uses 10 P40 and 10 P25 background-only traces per server.

## 2. D1 vs D2 decision rule (fixed 2026-11-17 23:55, after Part 1 and before any Part 2 disk or host result was looked at; one cold Part 2 pair had been logged)

The prompt states the hypotheses but no thresholds; these are fixed here and not changed afterwards.

- **D1 SUPPORTED** if all three hold: (i) Part 1, disk-only median TTFT <= 0.5x cold median TTFT at both 11k and 28k;
  (ii) Part 2, at each load run, the disk state's median imposed latency sum (FIT) is <= 0.25x the cold state's AND
  at most the host state's median plus max(1 s, 2x the cell's median repeat noise); (iii) Part 3, with 4 concurrent
  disk loads (unloaded) the median per-load TTFT is below Part 1's cold median TTFT at 11k.
- **D2 SUPPORTED** if any of: disk median TTFT > 0.5x cold at either size (Part 1); disk median imposed latency >=
  0.5x cold's at any load (Part 2); median per-load TTFT with 4 concurrent disk loads >= cold's solo median (Part 3).
- Otherwise **MIXED**, with the failing condition named. Part 4 (write cost) is reported alongside: if the disk tier's
  write-through fails the Part 4 rule (F6), the verdict carries that cost explicitly.

## 3. Run record (all on h100nvl GPU 2, exclusive; ENG1 plugin loaded; no per-step add-on)

| stage | server(s) | time | VOID |
|---|---|---|---|
| equivalence gate + Part 1 | EQ_P1 (disk tier) | 2026-11-17 22:27 to 23:20 | no |
| Part 2, P25 | P2_P25 (disk tier) | 2026-11-18 01:13 to 02:54 | no |
| Part 2, P40 | P2_P40 (disk tier) | 02:54 to 04:45 | no |
| Part 3, unloaded | P3_U (disk tier) | 04:45 to 05:14 | no |
| Part 3, P25 | P3_P25 (disk tier) | 05:14 to 06:00 | no |
| Part 4 | P4_OFF1, P4_ON1, P4_ON2, P4_OFF2 (ABBA; OFF = ENG1c's native command exactly) | 06:00 to 06:36 | no |

Every disk-tier server: flag diff vs DE_c38 = the native offloading pair replaced by `--kv-transfer-config` (section
0), GPU pool 62,944, host mmap 40.8 GB (38 GiB), no O_DIRECT fallback. The disk guard never fired (KV directory peak
about 72 GB, free space never below 241 GB); the study's KV files were deleted at the end. At every part boundary the
pilot's precondition P2 was re-checked (`git fetch`): StudyLIVE2-fix absent and design-log rows D98 to D105 absent at
every check, so ENG1f never paused and the pilot did not run.

**OVERNIGHT DECISIONS and incidents (recorded as required; affected items PROVISIONAL where stated).**
1. 22:25, first EQ_P1 start VOIDed before any measurement: the exclusivity monitor listed our own vLLM venv's Triton
   `ptxas` (kernel compilation at start) as "ours outside the job", the list-before-tree race ENG1d fixed for the
   cpuinfo probe. The narrow exemption was extended to that binary from our venv, only when exited or inside our tree;
   VOID files kept as `eng1f_equiv_p1_void1_*`, not used.
2. 22:23, a crash before any server start (the KV directory was created after the disk guard first ran); fixed, no data.
3. 23:20 to 23:51, the ENG1f driver waited on itself (a tmux name prefix match); 31 minutes lost, no data affected.
4. 01:12, the first P2_P25 run VOIDed: the harness's own `find` over the study's KV directory (pruning) hit the same
   race. Exemption extended to this harness's own `find` / `du` / `rm` / `fincore` calls on the study's KV directory,
   only when exited or inside our tree. The whole VOID run (its cold and host cells included) is kept as
   `eng1f_p2_P25_void1_*` and NOT used; P2_P25 was rerun from the start.
5. **PROTOCOL DEVIATION, 06:14:27 to 06:14:39:** a mis-specified wait condition let an analysis process run on the host
   for about 12 s while P4_ON1 was up. Part 4 trace 805 (P40) overlapped it and is excluded from every condition
   (paired by trace); P25 had no overlapping trace. Part 4 is therefore 9 P40 and 10 P25 traces.

## 4. Equivalence gate (F4): PASS

10 histories (11k), resident path (built, recalled at once from GPU) vs disk path (pushed out of GPU and host, recalled
from disk: 10 of 10 read from the disk tier, cached tokens equal to the resident path's, for example 11,008 of
11,161), greedy, 32 answer tokens, first-token top-20 log-probabilities: answer tokens identical 10 of 10; maximum
|delta log-prob| over the shared top-20 tokens 0.0000 (bit-identical). The resident-vs-resident repeat, intended as the
noise reference, differs by 0.07 to 0.13 with identical tokens: the repeat reuses a longer cached prefix (it includes
the question blocks of the first answer), so it computes fewer tokens on a different numeric path; it is therefore not
a noise floor for the disk comparison, which computes exactly the same tokens as the first resident answer.

## 5. Part 1: solo latency (unloaded; 20 repetitions per state and size)

| size | state | TTFT median [p10, p90] s | read from disk per recall | disk read rate | sanity (section 1) |
|---|---|---|---|---|---|
| 11k | cold (recompute) | 2.687 [2.650, 2.782] | 0 | | PASS (0.8x to 1.25x of 2.74 s) |
| 11k | host-warm | 0.203 [0.178, 0.215] | 0 (11,008 tokens from the host tier) | | PASS (0.17 +/- 0.10 s) |
| 11k | disk-only | 1.149 [1.125, 1.212] | 2.86 GB, 20 of 20 from disk | 3.07 GB/s | |
| 28k | cold | 7.572 [7.413, 7.771] | 0 | | |
| 28k | host-warm | 0.350 [0.335, 0.371] | 0 | | |
| 28k | disk-only | 2.693 [2.654, 2.715] | 6.99 GB, 20 of 20 from disk | 3.07 GB/s | |

A disk load costs 0.43x (11k) and 0.36x (28k) of a recompute, and 5.7x (11k) and 7.7x (28k) of a host reload. Its
time is the disk read: 2.86 GB at 3.07 GB/s is 0.93 s of the 1.15 s, close to the raw 3.6 to 3.7 GB/s direct-I/O
read of the device. Caching state: GPU cold for all three; host warm only for host-warm; disk holds the KV only for
disk-only; page cache 0 bytes resident for every disk-only target (fincore, O_DIRECT tier I/O).

## 6. Part 2: delay imposed on others (11k recall; 15 FIT pairs per cell, 5 HOLDOUT recorded, 3 repeats)

| load | state | imposed latency sum median [p10, p90] s | 95 % CI | imposed TTFT sum median s | noise |repeat - without| median s | recall TTFT median [p10, p90] s | with-runs reading disk |
|---|---|---|---|---|---|---|---|
| P25 | cold | 23.59 [16.72, 28.63] | [19.35, 28.07] | 22.14 | 0.04 | 2.88 [2.74, 3.02] | 0 |
| P25 | host | 0.07 [-0.08, 0.14] | [-0.07, 0.12] | 0.02 | 0.09 | 0.26 [0.21, 0.37] | 0 |
| P25 | disk | 0.03 [-0.08, 0.20] | [-0.05, 0.09] | 0.00 | 0.07 | 1.28 [1.20, 1.42] | 15 |
| P40 | cold | 36.54 [19.75, 57.22] | [21.96, 46.11] | 32.87 | 0.12 | 2.95 [2.79, 3.02] | 0 |
| P40 | host | 0.14 [-0.04, 0.49] | [0.04, 0.23] | 0.15 | 0.09 | 0.34 [0.19, 0.48] | 0 |
| P40 | disk | 0.10 [-0.05, 0.29] | [-0.02, 0.20] | 0.11 | 0.14 | 1.44 [1.19, 1.89] | 15 |

0 cached-token mismatches in every cell. Every trial is flagged on the GPU criterion (other users' GPUs 0, 1, 3 busy
all night, as in ENG1d / ENG1e); host CPU flags 0. Cold under load matches StudyENG1e mode A mono at the same loads
(P25 27.10 s, P40 39.59 s latency sums) and ENG1d's mono11k TTFT sums (P25 16.69, P40 44.87 s): ratios 0.87, 0.92,
1.33, 0.73, all within 2x.

## 7. Part 3: concurrent disk loads (11k; 10 repetitions per k)

| condition | k simultaneous disk loads | per-load TTFT median [p10, p90] s | slowest of the group, median s | imposed latency sum median [p10, p90] s |
|---|---|---|---|---|
| unloaded | 1 | 1.121 [1.101, 1.205] | 1.121 | |
| unloaded | 2 | 1.858 [1.800, 1.923] | 1.887 | |
| unloaded | 4 | 3.530 [3.255, 3.634] | 3.571 | |
| P25 | 1 | 2.237 [1.291, 4.000] | | -0.01 [-0.16, 0.38] |
| P25 | 2 | 1.944 [1.866, 2.039] | | 0.06 [-0.03, 0.18] |
| P25 | 4 | 3.768 [3.584, 4.111] | | 0.62 [0.26, 1.41] |

The loads share the disk bandwidth: 4 x 2.86 GB at about 3.2 GB/s is 3.6 s, so each of four simultaneous loads takes
about as long as the four in series. Others still pay almost nothing (0.62 s for four loads at P25, against 23.6 s for
ONE cold recompute). The P25 k = 1 spread (1.29 to 4.00 s) is the load arriving behind background prefills.

## 8. Part 4: write cost of the disk tier (ABBA, identical traces, 5 discarded warm-ups per server)

| load | quantity | ON / OFF | 95 % CI | instance OFF2 / OFF1, ON2 / ON1 | rule (F6) | result |
|---|---|---|---|---|---|---|
| P40 (9 traces) | median step elapsed_ms | 0.9827 | [0.980, 0.987] | 1.0004, 0.9983 | within 1 % + 0.17 % | FAIL (ON shorter) |
| P40 | median TTFT | **1.1880** | [1.157, 1.206] | 0.9913, 1.0070 | CI includes 1 | **FAIL (+18.8 %)** |
| P25 (10 traces) | median step elapsed_ms | 0.9819 | [0.980, 0.983] | 1.0000, 0.9992 | within 1 % + 0.08 % | FAIL (ON shorter) |
| P25 | median TTFT | 1.0220 | [1.015, 1.043] | 0.9883, 1.0100 | CI includes 1 | FAIL (+2.2 %) |

The write-through is not free: with the disk tier on, ordinary background requests' TTFT rises by 18.8 % at P40 and
2.2 % at P25, well outside the instance noise (at most 1.2 %). The step-time ratio below 1 is the elapsed_ms
artefact StudyENG1e documented (the engine's timed wait excludes CPU work done before it; the disk tier's 32 I/O
threads add CPU work in the engine process), so the TTFT ratio is the meaningful one. Every chunk any request computes
is written to disk (about 95 MB per 378-token background request).

## 9. Verdict under the pre-registered rule (section 2)

- D1 (i): disk / cold TTFT 0.43 (11k), 0.36 (28k) <= 0.5: holds.
- D1 (ii): disk imposed latency 0.03 s (P25) and 0.10 s (P40) <= 0.25x cold (5.90 / 9.14 s) and <= host + max(1 s,
  2x noise): holds.
- D1 (iii) / D2 trigger: 4 concurrent disk loads, median per-load TTFT 3.53 s >= cold's solo median 2.69 s: FAILS
  for D1 and TRIGGERS D2.

**Verdict: D2 SUPPORTED, by the concurrency condition alone.** Solo and under load, a disk reload dominates recompute
by a wide margin (2.3x to 2.8x faster, and an imposed delay of 0.03 to 0.10 s, indistinguishable from a host reload, against 23.6 to 36.5 s for a recompute); with four simultaneous
disk loads each one is slower than a solo recompute, because the loads are bound by the shared disk bandwidth.
Separately, the disk tier's write-through raises ordinary requests' TTFT by 18.8 % at P40 (Part 4 FAIL).

## 10. Results consistency check

1. Cross-check: host-warm 0.203 s vs ENG1 0.17 s (1.19); cold 2.687 s vs ENG1 2.74 s (0.98); cold imposed under load
   vs ENG1e mode A and ENG1d (0.73 to 1.33, section 6); no disagreement over 2x.
2. Physical plausibility: the disk-only recall's read rate (3.07 GB/s) is below the device's raw direct-I/O read (3.6 to
   3.7 GB/s); four concurrent loads are bandwidth-additive (section 7); nothing faster than the committed curves.
3. Distribution sanity: p10 / p90 everywhere; no constant where inputs vary.
4. Definition audit: "cold" = image bytes, no KV anywhere (as ENG1 cold); "host-warm" = ENG1c PF construction;
   "disk-only" = new (section 1); imposed delay = ENG1c latency sum (primary), TTFT sum (secondary).
5. Claim linkage: FORMULATION.md section Scoping and spec v4 section 7 treat COLD as raw frames rebuilt by prefill;
   this study measures a fourth tier (disk-saved KV) that the formulation does not yet have (open question Q12).
6. Proxy validity: secondary-tier read bytes (connector counter) are the proof of a disk load; page-cache residency is
   measured directly (fincore); no proxy used for a headline.

All six checks PASS.

## 11. HOLDOUT

30 pairs (5 per Part 2 cell) recorded with `holdout: true` in the Part 2 request files, not analysed; split in
`eng1f_holdout_split.json` (written 2026-11-17 23:51, before any Part 2 run).

## 12. Implications (separate from the findings)

- For Q12: a disk tier would make a cold history roughly 2.3x to 2.8x cheaper to restore for the device that needs it,
  and almost free for everyone else, as long as restores are rare enough not to queue on the disk; it costs about 2.9
  GB of disk per 11k history, write bandwidth for EVERY computed chunk, and (measured) up to +19 % TTFT for ordinary
  traffic at P40 from the write-through. A policy using it would model a fourth readiness tier with restore time about
  0.33 s per GB (0.93 s per 11k history) plus queueing on disk bandwidth, and near-zero imposed delay.
- The concurrency result means disk restores must be admitted like a bandwidth-limited resource (the policy's
  coordinator would serialise or ration them); four at once is worse for each than recomputing one.
- The write-through cost argues for writing to disk selectively (only histories likely to be recalled), which the
  native fs tier does not support (it cascades every chunk); that would need a different tier or a filter.
- This host's only writable disk is a 92 %-full consumer NVMe; the RAID at /data would need a directory from an admin.

## 13. Files

New: `experiments/cost/study_eng1f_disk.py`, `experiments/cost/study_eng1f_analyse.py`, `reports/study_eng1f_disk.md`,
`results/cost/study_eng1f/` (equivalence, holdout split, per-stage request / machine / monitor / frontend rows,
plugin rows per server, run metas, `eng1f_results.json`, VOID runs kept as `*_void1_*`). Changed: `research/
EXPERIMENTS.md` (pre-registration row, verdict in place), `results/INDEX.md`, `research/STATUS.md`. The study's KV
files under `~/data/eng1f_kv/` were deleted at the end (this study's own files only).
Note: plugin step files over 5 MB gzipped (EQ_P1, P2_P25, P2_P40 and the VOID P2_P25) are committed as three gzipped parts each (`<server>.partNN.jsonl.gz`, rows in order; concatenate to regenerate); request / frontend / machine files over 1 MB are committed gzipped.
