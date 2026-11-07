"""StudyB1-grey2: corrected grey-frame control + RTV-Bench Instruct HISTORY remainder.

Fixes exactly one defect in the original control (b1_run.py:428-433): the control used a
single synthetic question with constant gold 'A', submitted 100 times as byte-identical
prompts. Here each grey request carries a REAL question and its option text verbatim from
the annotation, with only the pixel content replaced by uniform grey. Frame count,
resolution, PNG encoding, template and decoding are unchanged from the real arm.

Writes new files only. Nothing in the original run is modified.
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, datetime as dt, gzip, hashlib, json, os
import random, shutil, subprocess, sys, time, urllib.error, urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b1_frames as FR
import b1_parse as PARSE
from b1_run import (MODELS, TEMPLATE_SHA, Out, grey_pngs, load_index, start_server,
                    stop_server, to_messages, wait_ready)

REPO = Path("/home/pragya/Desktop/FM-switching")
RES = REPO / "results/benchmarks/study_b1_flash"
NEW = RES / "grey2"
GREY_N = 100
SEED = 0
# herbench is removed from StudyB1 by user decision 2026-11-06.
DATASETS = ("rtv_bench", "ovo_bench", "streaming_bench")


def now():
    return dt.datetime.now()


def log(m):
    print(f"[{now():%H:%M:%S}] {m}", flush=True)


def read_real_rows():
    """(dataset, mode, model, arm) -> set of qids with a real scored row."""
    have = defaultdict(set)
    for mdir in ("model_4B", "model_8B"):
        for p in sorted((RES / mdir).glob("requests.part*.jsonl.gz")):
            with gzip.open(p, "rt") as f:
                for line in f:
                    r = json.loads(line)
                    if "error" in r or r.get("grey") or r.get("dataset") not in DATASETS:
                        continue
                    have[(r["dataset"], r["mode"], r["model"], r["arm"])].add(r["qid"])
    return have


def grey_question_sets(have, index):
    """One shared grey question set per (dataset, input), so the control is matched
    across every model and arm that has real results there."""
    sets = {}
    for (ds, mode, _m, _a) in list(have):
        if (ds, mode) in sets:
            continue
        cells = [v for (d, md, _, _), v in have.items() if d == ds and md == mode]
        inter = set.intersection(*cells) if cells else set()
        if len(inter) < GREY_N:
            raise RuntimeError(f"{ds}/{mode}: only {len(inter)} qids common to all cells")
        qids = sorted(inter)
        random.Random(SEED).shuffle(qids)
        sets[(ds, mode)] = [index[ds][q] for q in qids[:GREY_N]]
    return sets


def call(port, served, msgs, arm):
    if arm == "Instruct":
        body = {"model": served, "messages": msgs, "temperature": 0.0,
                "max_tokens": 64, "logprobs": True, "top_logprobs": 20, "seed": 0}
    else:
        body = {"model": served, "messages": msgs, "temperature": 1.0, "top_p": 0.95,
                "max_tokens": 16384, "seed": 0, "extra_body": {"top_k": 20}}
        body["top_k"] = 20
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                return json.loads(r.read()), attempt, None
        except urllib.error.HTTPError as e:
            return None, attempt, f"HTTP {e.code}: {e.read()[:400].decode(errors='replace')}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(2 + 3 * attempt)
    return None, 2, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=("4B", "8B"))
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--min-free-gb", type=float, default=50.0)
    a = ap.parse_args()

    outdir = NEW / f"model_{a.model}"
    outdir.mkdir(parents=True, exist_ok=True)
    logdir = REPO / "logs"
    index = {ds: {r["qid"]: r for r in load_index(ds)} for ds in DATASETS}
    have = read_real_rows()
    gsets = grey_question_sets(have, index)
    out = Out(outdir / "requests")
    log(f"resume: {len(out.done)} rows already present")

    counters = {"ok": 0, "fail": 0, "skip": 0}
    meta = {"study": "StudyB1-grey2", "model": a.model, "gpu": a.gpu,
            "supersedes": "grey control of the 2026-11-05/06 run (b1_run.py:428-433)",
            "template_sha256": TEMPLATE_SHA, "frames_sha256": hashlib.sha256(
                (Path(__file__).parent / "b1_frames.py").read_bytes()).hexdigest(),
            "grey_n_per_cell": GREY_N, "seed": SEED, "datasets": list(DATASETS),
            "herbench": "removed from StudyB1 by user decision 2026-11-06",
            "servers": [], "events": []}

    def disk_ok():
        gb = shutil.disk_usage("/mnt/ssd").free / 1e9
        if gb < a.min_free_gb:
            log(f"STOP: free disk {gb:.1f} GB < {a.min_free_gb}")
            return False
        return True

    def one_grey(q, mode, arm, served, port):
        key = f"{a.model}|{arm}|{mode}|GREY2|{q['dataset']}|{q['qid']}"
        if key in out.done:
            counters["skip"] += 1
            return
        n = FR.RECENT_N if mode == "RECENT" else FR.HISTORY_N
        pngs = grey_pngs(n)
        fmeta = {"mode": mode, "grey": True, "n_frames": n,
                 "frame_sha256": [hashlib.sha256(pngs[0]).hexdigest()] * n}
        msgs, _ = to_messages(q, pngs)
        t0 = time.time()
        resp, attempts, err = call(port, served, msgs, arm)
        wall = time.time() - t0
        rec = {"key": key, "study": "grey2", "model": a.model, "arm": arm, "mode": mode,
               "dataset": q["dataset"], "task": q.get("task"), "qid": q["qid"],
               "video_key": q.get("video_key"), "grey": True, "gold": q["gold"],
               "answer_kind": q["answer_kind"], "n_options": len(q.get("options") or {}),
               "wall_s": round(wall, 3), "retries": attempts,
               "ts": now().isoformat(), "frames": fmeta}
        if resp is None:
            rec["error"] = err
            counters["fail"] += 1
        else:
            ch = resp["choices"][0]
            raw = ch["message"]["content"] or ""
            rec["finish_reason"] = ch.get("finish_reason")
            rec["truncated"] = ch.get("finish_reason") == "length"
            u = resp.get("usage") or {}
            rec["gen_tokens"] = u.get("completion_tokens")
            rec["prompt_tokens"] = u.get("prompt_tokens")
            rec["prompt_sha256"] = hashlib.sha256(
                json.dumps(msgs, sort_keys=True).encode()).hexdigest()
            rec.update(PARSE.score(q, raw))
            rec["response"] = raw if arm == "Instruct" else None
            counters["ok"] += 1
        out.write(rec)

    def one_real(q, mode, arm, served, port, tag, verify=None):
        """Real RTV remainder request. If verify is given, compare and do not write."""
        key = f"{a.model}|{arm}|{mode}|{q['dataset']}|{q['qid']}"
        if verify is None and key in out.done:
            counters["skip"] += 1
            return None
        try:
            pngs, fmeta = FR.render(q["video"], mode, q["t"])
        except Exception as e:
            out.write({"key": key, "study": tag, "model": a.model, "arm": arm, "mode": mode,
                       "dataset": q["dataset"], "qid": q["qid"],
                       "error": f"render: {type(e).__name__}: {e}", "ts": now().isoformat()})
            counters["fail"] += 1
            return None
        msgs, _ = to_messages(q, pngs)
        t0 = time.time()
        resp, attempts, err = call(port, served, msgs, arm)
        wall = time.time() - t0
        if resp is None:
            if verify is not None:
                return {"qid": q["qid"], "error": err}
            out.write({"key": key, "study": tag, "model": a.model, "arm": arm, "mode": mode,
                       "dataset": q["dataset"], "qid": q["qid"], "error": err,
                       "ts": now().isoformat()})
            counters["fail"] += 1
            return None
        ch = resp["choices"][0]
        raw = ch["message"]["content"] or ""
        sc = PARSE.score(q, raw)
        if verify is not None:
            return {"qid": q["qid"], "pred_now": sc["pred"], "pred_before": verify["pred"],
                    "pred_match": sc["pred"] == verify["pred"],
                    "frames_match": fmeta["frame_sha256"] == verify["frame_sha256"]}
        u = resp.get("usage") or {}
        rec = {"key": key, "study": tag, "model": a.model, "arm": arm, "mode": mode,
               "dataset": q["dataset"], "task": q.get("task"), "qid": q["qid"],
               "video_key": q.get("video_key"), "grey": False, "gold": q["gold"],
               "answer_kind": q["answer_kind"], "t_query_s": q.get("t"),
               "order": q.get("order"), "wall_s": round(wall, 3), "retries": attempts,
               "ts": now().isoformat(), "frames": fmeta,
               "finish_reason": ch.get("finish_reason"),
               "truncated": ch.get("finish_reason") == "length",
               "gen_tokens": u.get("completion_tokens"),
               "prompt_tokens": u.get("prompt_tokens"),
               "prompt_sha256": hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest(),
               "response": raw}
        rec.update(sc)
        out.write(rec)
        counters["ok"] += 1
        return None

    for arm in ("Instruct", "Thinking"):
        proc, lf, served, cmd, repo, rev = start_server(a.gpu, a.model, arm, a.port, logdir)
        t0 = time.time()
        wait_ready(a.port, proc)
        meta["servers"].append({"arm": arm, "repo": repo, "revision": rev,
                                "cmd": cmd, "startup_s": round(time.time() - t0, 1),
                                "log": lf.name, "started": now().isoformat()})
        (outdir / "run_meta.json").write_text(json.dumps(meta, indent=1))
        log(f"{served} ready in {time.time() - t0:.1f}s")

        with cf.ThreadPoolExecutor(max_workers=a.concurrency) as pool:
            # STEP 3 first on the Instruct server: verify reproducibility, then the remainder.
            if arm == "Instruct":
                done_hist = have[("rtv_bench", "HISTORY", a.model, "Instruct")]
                prior = {}
                for p in sorted((RES / f"model_{a.model}").glob("requests.part*.jsonl.gz")):
                    with gzip.open(p, "rt") as f:
                        for line in f:
                            r = json.loads(line)
                            if (r.get("dataset") == "rtv_bench" and r.get("mode") == "HISTORY"
                                    and r.get("arm") == "Instruct" and "error" not in r
                                    and not r.get("grey")):
                                prior[r["qid"]] = {"pred": r["pred"],
                                                   "frame_sha256": r["frames"]["frame_sha256"]}
                spot = sorted(prior)
                random.Random(SEED).shuffle(spot)
                spot = spot[:20]
                futs = [pool.submit(one_real, index["rtv_bench"][q], "HISTORY", arm,
                                    served, a.port, "spotcheck", prior[q]) for q in spot]
                checks = [f.result() for f in futs]
                nbad = [c for c in checks if c and (not c.get("pred_match")
                        or not c.get("frames_match"))]
                meta["spotcheck"] = {"n": len(checks), "mismatches": nbad,
                                     "all_match": not nbad}
                (outdir / "run_meta.json").write_text(json.dumps(meta, indent=1))
                log(f"spotcheck: {len(checks)} requests, {len(nbad)} mismatches")
                if nbad:
                    log("STOP: spot check failed, not running the remainder")
                    stop_server(proc)
                    return

                todo = [index["rtv_bench"][q] for q in sorted(
                    set(index["rtv_bench"]) - done_hist)]
                todo.sort(key=lambda r: r["order"])
                log(f"RTV Instruct HISTORY remainder: {len(todo)} requests")
                futs = [pool.submit(one_real, q, "HISTORY", arm, served, a.port, "rtv_remainder")
                        for q in todo]
                for f in futs:
                    f.result()
                log(f"RTV remainder done ok={counters['ok']} fail={counters['fail']}")
                if not disk_ok():
                    stop_server(proc)
                    return

            # STEP 2: corrected grey control, every cell that has real results.
            for ds in DATASETS:
                for mode in ("RECENT", "HISTORY"):
                    if (ds, mode, a.model, arm) not in have:
                        continue
                    qs = gsets[(ds, mode)]
                    futs = [pool.submit(one_grey, q, mode, arm, served, a.port) for q in qs]
                    for f in futs:
                        f.result()
                    log(f"grey2 {arm}/{mode}/{ds} n={len(qs)} "
                        f"ok={counters['ok']} fail={counters['fail']} skip={counters['skip']}")
                    if not disk_ok():
                        stop_server(proc)
                        return

        stop_server(proc)
        meta["events"].append({"arm": arm, "stopped": now().isoformat(),
                               "counters": dict(counters)})
        (outdir / "run_meta.json").write_text(json.dumps(meta, indent=1))

    meta["final_counters"] = dict(counters)
    meta["finished"] = now().isoformat()
    (outdir / "run_meta.json").write_text(json.dumps(meta, indent=1))
    log(f"DONE {counters}")


if __name__ == "__main__":
    main()
