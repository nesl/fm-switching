#!/usr/bin/env python3
"""StudyB2-h100 analysis (CPU only; never while a latency step runs). No thresholds, no policies.

--dataset ovo_rtv: arms 4BI / 8BI / 4BT / 8BT from StudyB2 rows, 32BI / 32BT from StudyB1 rows (not rerun).
Correctness: upstream scorer (b1_common.upstream_correct, recorded per row) and strict scorer (exactly one valid answer
token equal to the ground truth). Unparsed / empty / truncated are counted WRONG and reported separately; for Thinking,
truncated = finish_reason "length" or `</think>` never closed; the answer region is the text after `</think>`.
Per dataset x part x task x input x arm: n, coverage, guessing floor, both accuracies with 95 % bootstrap by VIDEO
(2,000, seed 0), truncation, unparsed, empty, no answer region, ambiguous, generated tokens p50 / p90 / max.
Paired on matched (item, input), BOTH scorers, video bootstrap: 32B − 4B and 32B − 8B within each mode; Thinking −
Instruct per size; HISTORY − RECENT per arm (a comparison of inputs; prompt tokens reported).
Grey control vs floor. Identity: frame SHA-256 lists and prompt-token offsets across every arm pair on matched keys.
Latency (if present): per arm x sub-dataset x input, TTFT / total / tokens / GPU-2 SM clock; neighbour flag = a >= 50
point step in SM utilisation on any other GPU between consecutive seconds within [start - 1 s, end + 1 s] (flagged,
never dropped); warm-ups excluded and counted.
Writes results/benchmarks/study_b2_<dataset>/b2_results_h100nvl.json.
"""
import argparse
import collections
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))
import b2_common as C2  # noqa: E402

C2.check_b1_common()
import b1_common as B  # noqa: E402
from _provenance import stamp  # noqa: E402

ROOT = HERE.parents[1]
B1_OUT = ROOT / "results/benchmarks/study_b1_h100"
NB, SEED = 2000, 0
SUBS = {"ovo_rtv": ("ovo_bench", "rtv_bench"), "streaming_bench": ("streaming_bench",), "herbench": ("herbench",)}
PARTS = {"ovo_bench": ("ovo_forward", "ovo_other"), "rtv_bench": (),
         "streaming_bench": ("sb_realtime", "sb_contextual", "sb_sequential"), "herbench": ("her_lite_v2", "her_full")}
FLOOR = B.guess_floor  # replaced by the dataset adapter's floor in main()


def truncated(r):
    return r.get("finish_reason") == "length" or (C2.is_thinking(r["arm"]) and r.get("think_closed") is False)


def unparsed(r):
    return r["strict_status"] != "ok"


def strict_correct(r, items):
    it = items[r["item_id"]]
    a = r["strict_answer"]
    if a is None:
        return False
    if it["parser"] == "ovo_yn":
        return a == ("Yes" if it["gt"] == 1 else "No")
    return str(a) == str(it["gt"])


def vboot(vals_by_video, rng):
    vids = list(vals_by_video)
    if not vids:
        return None
    arr = [np.asarray(vals_by_video[v], float) for v in vids]
    sums = np.array([a.sum() for a in arr])
    cnts = np.array([len(a) for a in arr])
    bs = []
    for _ in range(NB):
        idx = rng.integers(0, len(vids), len(vids))
        bs.append(sums[idx].sum() / cnts[idx].sum())
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def q(x):
    x = [v for v in x if v is not None]
    if not x:
        return None
    return dict(p50=float(np.percentile(x, 50)), p90=float(np.percentile(x, 90)), max=float(max(x)),
                min=float(min(x)))


def cell(rs, items, planned, rng):
    if not rs:
        return dict(n=0, planned=planned, coverage=0.0 if planned else None)
    up = collections.defaultdict(list)
    st = collections.defaultdict(list)
    for r in rs:
        up[r["video_key"]].append(float(bool(r["correct_upstream"])))
        st[r["video_key"]].append(float(strict_correct(r, items)))
    floors = [f for f in (FLOOR(items[r["item_id"]]) for r in rs) if f is not None]
    return dict(n=len(rs), planned=planned, coverage=len(rs) / planned if planned else None,
                guess_floor=float(np.mean(floors)) if floors else None, guess_floor_n=len(floors),
                accuracy=float(np.mean([bool(r["correct_upstream"]) for r in rs])), ci95_video=vboot(up, rng),
                accuracy_strict=float(np.mean([strict_correct(r, items) for r in rs])), ci95_video_strict=vboot(st, rng),
                n_videos=len(up), truncated=sum(truncated(r) for r in rs),
                truncation_rate=float(np.mean([truncated(r) for r in rs])),
                unparsed=sum(unparsed(r) for r in rs), unparsed_rate=float(np.mean([unparsed(r) for r in rs])),
                empty=sum(r["strict_status"] == "empty" for r in rs),
                no_answer_region=sum(r["strict_status"] == "no_answer_region" for r in rs),
                ambiguous=sum(r["strict_status"] == "ambiguous" for r in rs),
                acc_parsed_only=float(np.mean([bool(r["correct_upstream"]) for r in rs if not unparsed(r)]))
                if any(not unparsed(r) for r in rs) else None,
                completion_tokens=q([r["completion_tokens"] for r in rs]),
                prompt_tokens=q([r["prompt_tokens"] for r in rs]))


def paired(a_rows, b_rows, items, rng):
    keys = sorted(set(a_rows) & set(b_rows))
    if not keys:
        return dict(n=0)
    out = dict(n=len(keys))
    for name, f in (("upstream", lambda r: float(bool(r["correct_upstream"]))),
                    ("strict", lambda r: float(strict_correct(r, items)))):
        by_v = collections.defaultdict(list)
        for k in keys:
            by_v[a_rows[k]["video_key"]].append(f(a_rows[k]) - f(b_rows[k]))
        d = [x for v in by_v.values() for x in v]
        out[name] = dict(diff=float(np.mean(d)), ci95_video=vboot(by_v, rng),
                         acc_a=float(np.mean([f(a_rows[k]) for k in keys])),
                         acc_b=float(np.mean([f(b_rows[k]) for k in keys])),
                         disagree=float(np.mean([f(a_rows[k]) != f(b_rows[k]) for k in keys])))
        out["n_videos"] = len(by_v)
    out["answer_disagree"] = float(np.mean([(a_rows[k]["strict_answer"], a_rows[k]["strict_status"]) !=
                                            (b_rows[k]["strict_answer"], b_rows[k]["strict_status"]) for k in keys]))
    return out


def load_arms(dataset):
    out_dir = ROOT / f"results/benchmarks/study_b2_{dataset}"
    arms = {}
    for m in C2.MODELS:
        if dataset == "ovo_rtv" and m in ("32BI", "32BT"):
            rows = C2.read_rows_file(B1_OUT / f"b1_rows_{m}.jsonl.gz")
            src = f"StudyB1 b1_rows_{m}.jsonl.gz"
        else:
            rows = C2.read_rows(out_dir, f"b2_rows_{m}")
            src = f"StudyB2 b2_rows_{m}"
        if rows:
            last = {}
            for r in rows:
                k = (r["tag"], r["item_id"], r["input"])
                if not r["error"] or k not in last:
                    last[k] = r
            arms[m] = dict(rows=rows, last=last, source=src)
    return out_dir, arms


def gpu2_index():
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"], capture_output=True,
                         text=True).stdout
    for l in out.splitlines():
        i, u = [x.strip() for x in l.split(",")]
        if u == "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c":
            return int(i)
    return 2


def dmon_steps(path, ours):
    """{second (epoch int) -> max |step| in SM util on any other GPU vs the previous second}."""
    if not path.exists():
        return {}
    util = collections.defaultdict(dict)
    for l in open(path, errors="replace"):
        if l.startswith("#") or not l.strip():
            continue
        f = l.split()
        try:
            ts = int(datetime.strptime(f[0] + f[1], "%Y%m%d%H:%M:%S").timestamp())
            g, sm = int(f[2]), f[3]
        except (ValueError, IndexError):
            continue
        if g != ours and sm.isdigit():
            util[g][ts] = int(sm)
    step = collections.defaultdict(int)
    for g, d in util.items():
        for ts, v in d.items():
            if ts - 1 in d:
                step[ts] = max(step[ts], abs(v - d[ts - 1]))
    return step


def latency(dataset, out_dir):
    p = out_dir / "b2_latency_requests_h100nvl.jsonl"
    pg = out_dir / "b2_latency_requests_h100nvl.jsonl.gz"   # gzipped after the latency step (per-request rows rule)
    if not p.exists() and not pg.exists():
        return None
    import gzip
    rows = [json.loads(l) for l in (open(p) if p.exists() else gzip.open(pg, "rt"))]
    steps = dmon_steps(ROOT / f"logs/b2_latency_{dataset}_dmon.log", gpu2_index())
    meta = json.loads((out_dir / "b2_latency_meta_h100nvl.json").read_text()) if (out_dir / "b2_latency_meta_h100nvl.json").exists() else {}
    res = dict(warmups=sum(r["warmup"] for r in rows), isolation=meta.get("isolation"),
               cache_checks=meta.get("cache_checks"), cells={}, label="localhost (127.0.0.1), no network; single "
               "request at a time, cold (prefix caching and mm processor cache off)")
    g = collections.defaultdict(list)
    for r in rows:
        if r["warmup"]:
            continue
        a, b = int(r["wall_start"]) - 1, int(r["wall_end"]) + 1
        r["neighbour_flag"] = any(steps.get(s, 0) >= 50 for s in range(a, b + 1))
        g[(r["arm"], r["sub_dataset"], r["input"])].append(r)
    for (arm, sub, inp), rs in sorted(g.items()):
        ok = [r for r in rs if not r["error"]]
        res["cells"][f"{arm}/{sub}/{inp}"] = dict(
            n=len(rs), errors=len(rs) - len(ok), ttft_s=q([r["ttft_s"] for r in ok]),
            total_s=q([r["total_s"] for r in ok]),
            time_to_think_end_s=q([r.get("time_to_think_end_s") for r in ok]) if C2.is_thinking(arm) else None,
            prompt_tokens=q([r["prompt_tokens"] for r in ok]), completion_tokens=q([r["completion_tokens"] for r in ok]),
            sm_mhz_median=q([(r.get("gpu2") or {}).get("sm_mhz_median") for r in ok]),
            sm_mhz_at_send=q([r.get("sm_mhz_at_send") for r in ok]),
            neighbour_flagged=sum(r["neighbour_flag"] for r in rs), cached_tokens_nonzero=sum(bool(r.get("cached_tokens")) for r in ok),
            truncated=sum(r.get("finish_reason") == "length" for r in ok))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="ovo_rtv", choices=list(SUBS))
    a = ap.parse_args()
    global FLOOR
    import b2_infer_vllm as I
    dsa = I.DATASETS[a.dataset](None)
    FLOOR = dsa.guess_floor
    items = dsa.items
    INPUTS = getattr(dsa, "inputs", ("RECENT", "HISTORY"))
    # planned = runnable questions that are run (HERBench: not on a missing video, not a duplicate of a Lite-v2 question)
    plannable = {k: it for k, it in items.items() if it.get("runnable", True) and not it.get("duplicate_of")}
    tkey = lambda it: (it["dataset"], it["part"] if it["dataset"] == "herbench" else None, it["task"])
    planned_main = collections.Counter(tkey(it) for it in plannable.values())
    rng = np.random.default_rng(SEED)
    out_dir, arms = load_arms(a.dataset)
    res = dict(arms={}, paired={}, grey={}, checks={}, sources={m: A["source"] for m, A in arms.items()})
    for m, A in arms.items():
        main_ok = {(k[1], k[2]): r for k, r in A["last"].items() if k[0] == "main" and not r["error"]}
        A["main_ok"] = main_ok
        out = dict(rows=len(A["rows"]), error_rows=sum(bool(r["error"]) for r in A["rows"]),
                   still_failed=sum(1 for r in A["last"].values() if r["error"]), main_ok=len(main_ok),
                   main_planned=len(INPUTS) * len(plannable), by_dataset={}, by_task={})
        for ds in SUBS[a.dataset]:
            n_ds = sum(1 for it in plannable.values() if it["dataset"] == ds)
            for inp in INPUTS:
                rs = [r for (iid, i2), r in main_ok.items() if i2 == inp and items[iid]["dataset"] == ds]
                out["by_dataset"][f"{ds}/{inp}"] = cell(rs, items, n_ds, rng)
                for part in PARTS[ds]:
                    npl = sum(1 for it in plannable.values() if it["part"] == part and it["dataset"] == ds)
                    out["by_dataset"][f"{ds}:{part}/{inp}"] = cell([r for r in rs if r["part"] == part], items, npl, rng)
        for (ds, part, task), n in sorted(planned_main.items(), key=lambda x: (x[0][0], x[0][1] or "", x[0][2])):
            for inp in INPUTS:
                rs = [r for (iid, i2), r in main_ok.items() if i2 == inp and tkey(items[iid]) == (ds, part, task)]
                out["by_task"][f"{ds}{':' + part if part else ''}/{task}/{inp}"] = cell(rs, items, n, rng)
        res["arms"][m] = out
        for inp in INPUTS:
            g = [r for k, r in A["last"].items() if k[0] == "grey" and k[2] == inp and not r["error"]]
            if g:
                res["grey"][f"{m}/{inp}"] = dict(
                    n=len(g), accuracy=float(np.mean([bool(r["correct_upstream"]) for r in g])),
                    accuracy_strict=float(np.mean([strict_correct(r, items) for r in g])),
                    guess_floor=float(np.mean([f for f in (FLOOR(items[r["item_id"]]) for r in g) if f is not None])),
                    answers=dict(collections.Counter(str(r["strict_answer"]) for r in g).most_common(12)),
                    unparsed=sum(unparsed(r) for r in g), truncated=sum(truncated(r) for r in g))
        for ds in (SUBS[a.dataset] if "RECENT" in INPUTS else ()):
            h = {(iid,): r for (iid, i2), r in main_ok.items() if i2 == "HISTORY" and items[iid]["dataset"] == ds}
            rr = {(iid,): r for (iid, i2), r in main_ok.items() if i2 == "RECENT" and items[iid]["dataset"] == ds}
            pr = paired(h, rr, items, rng)
            pr["prompt_tokens_HISTORY"] = q([r["prompt_tokens"] for r in h.values()])
            pr["prompt_tokens_RECENT"] = q([r["prompt_tokens"] for r in rr.values()])
            pr["label"] = "comparison of INPUTS at a fixed frame count (37 over [0, t] vs 9 over the last 3 s)"
            res["paired"][f"{m}/{ds}/HISTORY-RECENT"] = pr
    pairs = [("32BI", "4BI"), ("32BI", "8BI"), ("8BI", "4BI"), ("32BT", "4BT"), ("32BT", "8BT"), ("8BT", "4BT"),
             ("4BT", "4BI"), ("8BT", "8BI"), ("32BT", "32BI")]
    for x, y in pairs:
        if x in arms and y in arms:
            for ds in SUBS[a.dataset]:
                for inp in INPUTS:
                    ka = {k: r for k, r in arms[x]["main_ok"].items() if k[1] == inp and items[k[0]]["dataset"] == ds}
                    kb = {k: r for k, r in arms[y]["main_ok"].items() if k[1] == inp and items[k[0]]["dataset"] == ds}
                    res["paired"][f"{x}-{y}/{ds}/{inp}"] = paired(ka, kb, items, rng)
                    for part in (PARTS[ds] if ds == "herbench" else ()):
                        kpa = {k: r for k, r in ka.items() if items[k[0]]["part"] == part}
                        kpb = {k: r for k, r in kb.items() if items[k[0]]["part"] == part}
                        res["paired"][f"{x}-{y}/{ds}:{part}/{inp}"] = paired(kpa, kpb, items, rng)
    ident = {}
    ms = list(arms)
    for i, x in enumerate(ms):
        for y in ms[i + 1:]:
            keys = set(arms[x]["main_ok"]) & set(arms[y]["main_ok"])
            ident[f"{x}|{y}"] = dict(
                compared=len(keys),
                frame_sha_mismatch=sum(arms[x]["main_ok"][k]["frame_sha256"] != arms[y]["main_ok"][k]["frame_sha256"] for k in keys),
                prompt_token_offset_b_minus_a=dict(collections.Counter(
                    str(arms[y]["main_ok"][k]["prompt_tokens"] - arms[x]["main_ok"][k]["prompt_tokens"]) for k in keys)))
    res["checks"]["identical_input_across_arms"] = ident
    allrows = [r for A in arms.values() for r in A["main_ok"].values()]
    res["checks"]["frames_le_t"] = all(max(p for p in r["frame_pts"] if p is not None) <= r["t"] + 1e-6 for r in allrows)
    res["checks"]["fewer_distinct_frames_than_N"] = dict(collections.Counter(
        f"{r['arm']}/{r['input']}" for r in allrows if r["n_distinct"] < B.INPUTS[r["input"]]))
    rc = out_dir / "b2_repeat_control_4BI.json"
    if rc.exists():
        j = json.loads(rc.read_text())
        res["checks"]["repeat_control_4BI"] = {k: {kk: vv for kk, vv in v.items() if kk != "differing"}
                                               for k, v in j.items() if isinstance(v, dict)}
    smoke = {}
    for m in C2.MODELS:
        rs = C2.read_rows(out_dir, f"b2_smoke_{m}")
        if rs:
            smoke[m] = dict(rows=len(rs), errors=sum(bool(r["error"]) for r in rs),
                            completion_tokens=q([r["completion_tokens"] for r in rs if not r["error"]]))
    res["checks"]["smoke"] = smoke
    res["latency"] = latency(a.dataset, out_dir)
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="b2_analyse.py", model=",".join(arms), device="cpu", n=len(allrows), args=a)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "b2_results_h100nvl.json").write_text(json.dumps(res, indent=1, default=float))
    for m, o in res["arms"].items():
        print(m, arms[m]["source"], "main", o["main_ok"], "/", o["main_planned"], "err", o["error_rows"], "failed", o["still_failed"])
        for k, c in o["by_dataset"].items():
            if c["n"]:
                print(f"  {k:32s} n {c['n']:5d} cov {c['coverage']:.3f} acc {c['accuracy']:.3f} strict "
                      f"{c['accuracy_strict']:.3f} trunc {c['truncation_rate']:.3f} unp {c['unparsed_rate']:.3f}")
    print("checks", json.dumps({k: v for k, v in res["checks"].items()})[:1500])


if __name__ == "__main__":
    main()
