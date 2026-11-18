#!/usr/bin/env python3
"""StudyLIVE2-harness: reproduce the pilot's lateness on flash, then measure the fix. CPU only.

Not a measurement of anything about the policy: every cell runs against the fake streaming
server (`fakestream.py`) over the byte-exact fixture store (`harness_fixture.py`), so
`server_kind` is "fake" throughout and the scorer treats every run as a non-measurement.

  step1  one cell per configuration with lateness and a per-phase profile of the emulator loop
  accept the acceptance grid: p99 lateness at 8 and 64 devices, edf and policy-core, modes A and B

The one quantity that matters is the emulator's p99 lateness, which the emulator itself computes
(`fleet/emulator.py::Lateness`) in the process that owns the wall clock, and which it already
uses to set `run_valid` against `MAX_P99_LATENESS_MS`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"),
           str(REPO / "experiments/orchestration/live"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cachekeys as CK                                                  # noqa: E402
import cstate as CS                                                     # noqa: E402
import fakestream as FS                                                 # noqa: E402
import framecache as FC                                                 # noqa: E402
import harness_fixture as HF                                            # noqa: E402
import trace as TR                                                      # noqa: E402

SEED, RATIO = 0, "50:50"
GPU_KV, HOST_GIB = 62944, 27.0
LATENESS_LIMIT_MS = 50.0


def _work(root: Optional[Path] = None) -> Path:
    p = Path(root or os.environ.get("LIVE2_HARNESS_WORK")
             or (Path.home() / "data/live2/harness"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def prepare(n_devices: int, run_s: float, mode: str, work: Path) -> Dict[str, Any]:
    """Trace plus the byte-exact fixture store for exactly the frames that trace needs."""
    sizes = HF.manifest_bytes()
    man = HF.write_plain_manifest(work / "frame_manifest.jsonl", sizes)
    tdir = work / "traces" / f"n{n_devices}_{int(run_s)}s_{mode}"
    if not (tdir / "trace.jsonl").exists():
        TR.write_trace(tdir, TR.generate_trace(SEED, n_devices, RATIO, run_s, mode,
                                               frame_manifest=man))
    refs = HF.refs_in_trace(tdir)
    store = work / "store"
    info = HF.build_store(store, refs, sizes)
    return dict(tdir=tdir, store=store, manifest=str(man), n_refs=len(refs), store_info=info)


def cell(arm_name: str, n_devices: int, run_s: float, mode: str, *, fix: bool,
         out: Path, work: Path, concurrency: int = 4, warm_cache: bool = True,
         profile: bool = False, detail: bool = False,
         split: bool = False) -> Dict[str, Any]:
    """One real-server-shaped cell. `fix=False` is the pilot's wiring, `fix=True` is the fix."""
    import arms as A
    import emulator as EM
    import run_live2_cell as RC
    from asyncbackend import AsyncLive2Backend
    from backend import Live2Backend
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs

    prep = prepare(n_devices, run_s, mode, work)
    tdir, store = prep["tdir"], prep["store"]
    rdir = Path(out) / f"{arm_name}_n{n_devices}_{mode}_{'fix' if fix else 'pilot'}"
    rdir.mkdir(parents=True, exist_ok=True)
    kw = (dict(cost_model="pol4", h_s=0.5, mu_mode="ewma", mu_fixed=None, impl="fast",
               cap_k=None) if arm_name == "policy-core" else {})
    arm = A.make_arm(arm_name, **kw)
    htok = RC.host_tokens(HOST_GIB)
    arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=htok,
                        targets=CS.TARGETS)
    cache = FC.FrameCache(store) if (fix and not split) else None
    if cache is not None and warm_cache:
        cache.warm(HF.refs_in_trace(tdir))
    logs = Logs(rdir).open() if not split else None
    with FS.serve(0, concurrency=concurrency) as url:
        if split:
            import procsplit as PS
            cfg = dict(run_dir=str(rdir), arm=arm_name, arm_kwargs=kw, mode=mode, run_s=run_s,
                       drain_s=10.0, decision_period_s=0.1, gpu_kv_tokens=GPU_KV,
                       host_tier_gib=HOST_GIB, host_tier_tokens=htok, seed=SEED,
                       run_tag=CK.run_tag(SEED, arm_name), frames_root=str(store),
                       server_url=url, model="32BI", strip_hints=True, defer_images=True,
                       warm_refs=(HF.refs_in_trace(tdir) if warm_cache else None))
            split_run = PS.SplitRun(cfg, kind="fake")
            br = split_run.__enter__()
            be = None
        else:
            be = (AsyncLive2Backend(url, model="32BI", strip_hints=True, cache=cache)
                  if fix else Live2Backend(url, workers=64, model="32BI", strip_hints=True))
            co = Live2Coordinator(arm, be, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                  host_tier_tokens=htok, upload_mode=mode, window_s=run_s,
                                  drain_s=10.0, decision_period_s=0.1, seed=SEED, logs=logs,
                                  run_tag=CK.run_tag(SEED, arm_name),
                                  frames_root=store, frame_cache=cache, defer_images=fix,
                                  targets=CS.TARGETS)
            br = EmulatorBridge(co)
            br.kind = "fake"
        em = EM.FleetEmulator(tdir, br, mode, realtime=True)
        if detail:
            em.lateness.detail = []
        t0 = time.time()
        cpu0 = time.process_time()
        err = None
        prof = None
        try:
            if profile:
                import cProfile
                import pstats
                import io as _io
                pr = cProfile.Profile()
                pr.enable()
                meta = em.run(rdir)
                pr.disable()
                buf = _io.StringIO()
                pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(28)
                prof = buf.getvalue()
            else:
                meta = em.run(rdir)
        except Exception as e:                                        # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            meta = (json.loads((rdir / "run_meta.json").read_text())
                    if (rdir / "run_meta.json").exists() else {})
        wall = time.time() - t0
        srv_stats = FS.serve.stats()
        if split:
            split_run.__exit__()
            res = dict(br.stats())
            bem = res.get("backend")
        else:
            res = co._result(cpu0, wall)
            bem = be.metrics() if hasattr(be, "metrics") else None
            be.close()
    if logs is not None:
        logs.close()
    lat = meta.get("lateness") or {}
    row = dict(arm=arm_name, n_devices=n_devices, mode=mode, fix=fix, split=split,
               run_s=run_s, concurrency=concurrency, err=err,
               lateness_p50_ms=lat.get("p50_ms"), lateness_p90_ms=lat.get("p90_ms"),
               lateness_p99_ms=lat.get("p99_ms"), lateness_max_ms=lat.get("max_ms"),
               lateness_n=lat.get("n"), run_valid=meta.get("run_valid"),
               digests_equal=meta.get("digests_equal"),
               fairness_digest=meta.get("fairness_digest"),
               sent_stream_digest=meta.get("sent_stream_digest"),
               n_requests=res.get("n_requests"), n_errors=res.get("n_errors"),
               decision_p50_ms=(res.get("decision_latency_ms") or {}).get("p50"),
               decision_p99_ms=(res.get("decision_latency_ms") or {}).get("p99"),
               cpu_s=res.get("cpu_s"), wall_s=round(wall, 3),
               emulator_cpu_fraction=meta.get("cpu_fraction"),
               server=srv_stats, backend=bem, rdir=str(rdir),
               is_measurement=False,
               label="FIXTURE SERVER, NOT A MEASUREMENT")
    if detail and em.lateness.detail is not None:
        import collections
        dd = em.lateness.detail
        with open(rdir / "lateness_detail.jsonl", "w") as fh:
            for due, what, ms in dd:
                fh.write(json.dumps(dict(due=due, what=what, late_ms=ms)) + "\n")
        late = [(due, what, ms) for due, what, ms in dd if ms > 10.0]
        by_due = collections.Counter(due for due, _w, _m in dd)
        row["late_over_10ms"] = len(late)
        row["late_by_kind"] = dict(collections.Counter(w for _d, w, _m in late).most_common())
        row["max_actions_sharing_a_due_instant"] = max(by_due.values()) if by_due else 0
        row["late_worst"] = sorted(late, key=lambda x: -x[2])[:6]
        row["lateness_detail"] = str(rdir / "lateness_detail.jsonl")
    if prof:
        (rdir / "profile.txt").write_text(prof)
        row["profile"] = str(rdir / "profile.txt")
    (rdir / "harness_cell.json").write_text(json.dumps(row, indent=1, default=str) + "\n")
    return row


def step1(out: Path, work: Path, run_s: float = 120.0) -> Dict[str, Any]:
    rows = [cell("edf", 8, run_s, "A", fix=False, out=out, work=work, profile=True)]
    return dict(check="harness_step1_reproduction", is_measurement=False,
                lateness_limit_p99_ms=LATENESS_LIMIT_MS, rows=rows)


def accept(out: Path, work: Path, run_s: float = 120.0,
           sizes=(8, 64), arms=("edf", "policy-core"), modes=("A", "B")) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for n in sizes:
        for arm in arms:
            for mode in modes:
                rows.append(cell(arm, n, run_s, mode, fix=True, split=True, out=out,
                                 work=work))
    ok = all((r["lateness_p99_ms"] is None or r["lateness_p99_ms"] <= LATENESS_LIMIT_MS)
             and not r["err"] for r in rows)
    digests: Dict[str, set] = {}
    for r in rows:
        digests.setdefault(f"{r['n_devices']}|{r['mode']}", set()).add(r["fairness_digest"])
    return dict(check="harness_acceptance", is_measurement=False, all_within_limit=ok,
                lateness_limit_p99_ms=LATENESS_LIMIT_MS,
                digest_identical_across_arms={k: (len(v) == 1) for k, v in digests.items()},
                rows=rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=("prep", "step1", "accept", "cell"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--run-s", type=float, default=120.0)
    ap.add_argument("--arm", default="edf")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--mode", default="A", choices=("A", "B"))
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--split", action="store_true")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--sizes", default="8,64")
    a = ap.parse_args(argv)
    work = _work(Path(a.work) if a.work else None)
    out = Path(a.out) if a.out else (work / "out")
    out.mkdir(parents=True, exist_ok=True)
    if a.what == "prep":
        res: Dict[str, Any] = prepare(a.n, a.run_s, a.mode, work)
    elif a.what == "step1":
        res = step1(out, work, a.run_s)
    elif a.what == "accept":
        res = accept(out, work, a.run_s, tuple(int(x) for x in a.sizes.split(",")))
    else:
        res = cell(a.arm, a.n, a.run_s, a.mode, fix=a.fix, out=out, work=work,
                   concurrency=a.concurrency, profile=a.profile, detail=a.detail,
                   split=a.split)
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
