#!/usr/bin/env python3
"""StudyB1-h100 analysis (CPU). No thresholds, no policies, no latency.

Primary correctness = upstream scorer (b1_common.upstream_correct), recorded per row; unparsed / empty / truncated are
counted WRONG and also reported separately. For Thinking, truncated = finish_reason "length" (or `</think>` never
closed); the answer region is the text after `</think>`.
Per dataset x task x input x arm: n, coverage (n / planned for that cell), guessing floor (mean of 1 / options; 0.5 for
Yes / No; none for REC), accuracy with 95 % bootstrap by VIDEO (2,000, seed 0), truncation rate, unparsed rate (strict
parser: unparsed + ambiguous + empty + no answer region), generated tokens p50 / p90 / max.
Paired: Thinking − Instruct (32BT − 32BI) on matched (item, input); HISTORY − RECENT on matched items per arm (a
comparison of inputs at a fixed frame count; prompt tokens reported); bridge 4BI vs 32BI on matched items.
Video bootstrap: resample videos with replacement, recompute the mean difference over their items.
Grey: accuracy and answer distribution against the guessing floor. Identity checks: frame SHA-256 lists and prompt
tokens equal across arms on matched (item, input). Repeat control (mv): per-question agreement of the two runs.
Writes results/benchmarks/study_b1_h100/b1_results_h100nvl.json.
"""
import collections
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))
import b1_common as B  # noqa: E402
from b1_infer_vllm import read_rows, plan  # noqa: E402
from _provenance import stamp  # noqa: E402

OUT = HERE.parents[1] / "results/benchmarks/study_b1_h100"
NB, SEED = 2000, 0


def latest(rows):
    d = {}
    for r in rows:
        k = (r["tag"], r["item_id"], r["input"])
        if not r["error"] or k not in d:
            d[k] = r
    return d


def truncated(r):
    return r.get("finish_reason") == "length" or (r["arm"] == "32BT" and r.get("think_closed") is False)


def unparsed(r):
    return r["strict_status"] != "ok"


def vboot(vals_by_video, rng):
    vids = list(vals_by_video)
    if not vids:
        return None
    arr = [np.asarray(vals_by_video[v], float) for v in vids]
    bs = []
    for _ in range(NB):
        idx = rng.integers(0, len(vids), len(vids))
        x = np.concatenate([arr[i] for i in idx])
        bs.append(x.mean())
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def q(x):
    x = [v for v in x if v is not None]
    if not x:
        return None
    return dict(p50=float(np.percentile(x, 50)), p90=float(np.percentile(x, 90)), max=float(max(x)))


def strict_correct(r, items):
    """Strict: exactly one valid answer token equal to the ground truth (OVO yes/no: Yes <-> type 1)."""
    it = items[r["item_id"]]
    a = r["strict_answer"]
    if a is None:
        return False
    if it["parser"] == "ovo_yn":
        return a == ("Yes" if it["gt"] == 1 else "No")
    return str(a) == str(it["gt"])


def cell(rs, items, planned, rng):
    by_v = collections.defaultdict(list)
    for r in rs:
        by_v[r["video_key"]].append(float(bool(r["correct_upstream"])))
    floors = [B.guess_floor(items[r["item_id"]]) for r in rs]
    floors = [f for f in floors if f is not None]
    return dict(n=len(rs), planned=planned, coverage=len(rs) / planned if planned else None,
                guess_floor=float(np.mean(floors)) if floors else None, guess_floor_n=len(floors),
                accuracy=float(np.mean([bool(r["correct_upstream"]) for r in rs])) if rs else None,
                accuracy_strict=float(np.mean([strict_correct(r, items) for r in rs])) if rs else None,
                ci95_video=vboot(by_v, rng) if rs else None, n_videos=len(by_v),
                truncation_rate=float(np.mean([truncated(r) for r in rs])) if rs else None,
                unparsed_rate=float(np.mean([unparsed(r) for r in rs])) if rs else None,
                empty=sum(r["strict_status"] == "empty" for r in rs),
                no_answer_region=sum(r["strict_status"] == "no_answer_region" for r in rs),
                ambiguous=sum(r["strict_status"] == "ambiguous" for r in rs),
                acc_parsed_only=float(np.mean([bool(r["correct_upstream"]) for r in rs if not unparsed(r)]))
                if any(not unparsed(r) for r in rs) else None,
                completion_tokens=q([r["completion_tokens"] for r in rs]),
                prompt_tokens=q([r["prompt_tokens"] for r in rs]))


def paired(a_rows, b_rows, rng):
    """Mean of (a correct − b correct) on matched (item, input) keys; video bootstrap."""
    keys = sorted(set(a_rows) & set(b_rows))
    by_v = collections.defaultdict(list)
    for k in keys:
        by_v[a_rows[k]["video_key"]].append(float(bool(a_rows[k]["correct_upstream"])) -
                                            float(bool(b_rows[k]["correct_upstream"])))
    if not keys:
        return dict(n=0)
    d = [x for v in by_v.values() for x in v]
    return dict(n=len(keys), n_videos=len(by_v), diff=float(np.mean(d)), ci95_video=vboot(by_v, rng),
                acc_a=float(np.mean([bool(a_rows[k]["correct_upstream"]) for k in keys])),
                acc_b=float(np.mean([bool(b_rows[k]["correct_upstream"]) for k in keys])),
                disagree=float(np.mean([a_rows[k]["correct_upstream"] != b_rows[k]["correct_upstream"] for k in keys])))


def main():
    items = {it["item_id"]: it for it in B.build_items()}
    order = B.fixed_order(list(items.values()))
    rng = np.random.default_rng(SEED)
    res = dict(arms={}, paired={}, grey={}, checks={})
    arms = {}
    for m in ("4BI", "32BI", "32BT"):
        p = OUT / f"b1_rows_{m}.jsonl.gz"
        if p.exists():
            rows = read_rows(p)
            arms[m] = dict(rows=rows, last=latest(rows))
    planned = {m: plan({"4BI": "bridge", "32BI": "instruct", "32BT": "thinking"}[m], order) for m in arms}
    for m, A in arms.items():
        main_ok = {(k[1], k[2]): r for k, r in A["last"].items() if k[0] == "main" and not r["error"]}
        pl = collections.Counter((items[q[1]]["dataset"], items[q[1]]["task"], q[2]) for q in planned[m] if q[0] == "main")
        pl_ds = collections.Counter((items[q[1]]["dataset"], q[2]) for q in planned[m] if q[0] == "main")
        out = dict(rows=len(A["rows"]), error_rows=sum(bool(r["error"]) for r in A["rows"]),
                   still_failed=sum(1 for k, r in A["last"].items() if r["error"]), main_ok=len(main_ok),
                   main_planned=sum(pl_ds.values()), by_dataset={}, by_task={})
        for (ds, inp), n in sorted(pl_ds.items()):
            rs = [r for (iid, i2), r in main_ok.items() if i2 == inp and items[iid]["dataset"] == ds]
            out["by_dataset"][f"{ds}/{inp}"] = cell(rs, items, n, rng)
            for part in ("ovo_forward", "ovo_other") if ds == "ovo_bench" else ():
                rp = [r for r in rs if r["part"] == part]
                npl = sum(1 for q in planned[m] if q[0] == "main" and q[2] == inp and items[q[1]]["part"] == part)
                out["by_dataset"][f"{ds}:{part}/{inp}"] = cell(rp, items, npl, rng)
        for (ds, task, inp), n in sorted(pl.items()):
            rs = [r for (iid, i2), r in main_ok.items() if i2 == inp and items[iid]["task"] == task and items[iid]["dataset"] == ds]
            out["by_task"][f"{ds}/{task}/{inp}"] = cell(rs, items, n, rng)
        res["arms"][m] = out
        A["main_ok"] = main_ok
        for inp in ("RECENT", "HISTORY"):
            g = [r for k, r in A["last"].items() if k[0] == "grey" and k[2] == inp and not r["error"]]
            if g:
                res["grey"][f"{m}/{inp}"] = dict(
                    n=len(g), accuracy=float(np.mean([bool(r["correct_upstream"]) for r in g])),
                    guess_floor=float(np.mean([f for f in (B.guess_floor(items[r["item_id"]]) for r in g) if f is not None])),
                    answers=dict(collections.Counter(str(r["strict_answer"]) for r in g).most_common(12)),
                    unparsed=sum(unparsed(r) for r in g), truncated=sum(truncated(r) for r in g))
        # HISTORY − RECENT on matched items, per dataset
        for ds in ("ovo_bench", "rtv_bench"):
            h = {(iid,): r for (iid, i2), r in main_ok.items() if i2 == "HISTORY" and items[iid]["dataset"] == ds}
            rr = {(iid,): r for (iid, i2), r in main_ok.items() if i2 == "RECENT" and items[iid]["dataset"] == ds}
            pr = paired(h, rr, rng)
            pr["prompt_tokens_HISTORY"] = q([r["prompt_tokens"] for r in h.values()])
            pr["prompt_tokens_RECENT"] = q([r["prompt_tokens"] for r in rr.values()])
            pr["label"] = "comparison of INPUTS at a fixed frame count (37 over [0, t] vs 9 over the last 3 s)"
            res["paired"][f"{m}/{ds}/HISTORY-RECENT"] = pr
    for a, b in (("32BT", "32BI"), ("32BI", "4BI"), ("32BT", "4BI")):
        if a in arms and b in arms:
            for ds in ("ovo_bench", "rtv_bench"):
                for inp in ("RECENT", "HISTORY"):
                    ka = {k: r for k, r in arms[a]["main_ok"].items() if k[1] == inp and items[k[0]]["dataset"] == ds}
                    kb = {k: r for k, r in arms[b]["main_ok"].items() if k[1] == inp and items[k[0]]["dataset"] == ds}
                    res["paired"][f"{a}-{b}/{ds}/{inp}"] = paired(ka, kb, rng)
    # identity of input across arms on matched (item, input)
    ident = {}
    ms = list(arms)
    for i, a in enumerate(ms):
        for b in ms[i + 1:]:
            keys = set(arms[a]["main_ok"]) & set(arms[b]["main_ok"])
            ident[f"{a}|{b}"] = dict(compared=len(keys),
                                     frame_sha_mismatch=sum(arms[a]["main_ok"][k]["frame_sha256"] != arms[b]["main_ok"][k]["frame_sha256"] for k in keys),
                                     prompt_token_mismatch=sum(arms[a]["main_ok"][k]["prompt_tokens"] != arms[b]["main_ok"][k]["prompt_tokens"] for k in keys),
                                     # a constant offset = chat-template difference (Thinking's generation prefix), not an input difference
                                     prompt_token_offset_b_minus_a=dict(collections.Counter(
                                         str(arms[b]["main_ok"][k]["prompt_tokens"] - arms[a]["main_ok"][k]["prompt_tokens"]) for k in keys)))
    res["checks"]["identical_input_across_arms"] = ident
    allrows = [r for A in arms.values() for r in A["rows"] if not r["error"] and not r["grey"]]
    res["checks"]["frames_le_t"] = all(max(p for p in r["frame_pts"] if p is not None) <= r["t"] + 1e-6 for r in allrows)
    res["checks"]["fewer_distinct_frames_than_N"] = dict(collections.Counter(
        f"{r['arm']}/{r['input']}" for r in allrows if r["n_distinct"] < B.INPUTS[r["input"]]))
    res["checks"]["short_span_RECENT"] = sum(r["short_span"] for r in allrows)
    res["checks"]["target_before_first_frame"] = sum(r.get("before_first_frame", 0) > 0 for r in allrows)
    mv = OUT / "b1_mv_32BI.jsonl.gz"
    if mv.exists():
        L = latest(read_rows(mv))
        r1 = {k[1]: r for k, r in L.items() if k[0] == "mv_repeat1"}
        r2 = {k[1]: r for k, r in L.items() if k[0] == "mv_repeat2"}
        ks = sorted(set(r1) & set(r2))
        res["checks"]["repeat_control"] = dict(n=len(ks), same_text=sum(r1[k]["text"] == r2[k]["text"] for k in ks),
                                               same_correct=sum(r1[k]["correct_upstream"] == r2[k]["correct_upstream"] for k in ks),
                                               same_frames=sum(r1[k]["frame_sha256"] == r2[k]["frame_sha256"] for k in ks))
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="b1_analyse.py", model=",".join(arms), device="cpu", n=len(allrows))
    (OUT / "b1_results_h100nvl.json").write_text(json.dumps(res, indent=1, default=float))
    for m, o in res["arms"].items():
        print(m, "rows", o["rows"], "main", o["main_ok"], "/", o["main_planned"], "err", o["error_rows"], "failed", o["still_failed"])
        for k, c in o["by_dataset"].items():
            if c["n"]:
                print(f"  {k:32s} n {c['n']:5d} cov {c['coverage']:.3f} acc {c['accuracy']:.3f} {c['ci95_video']} floor "
                      f"{c['guess_floor']} trunc {c['truncation_rate']:.3f} unp {c['unparsed_rate']:.3f} tok {c['completion_tokens']}")
    for k, v in res["paired"].items():
        if v.get("n"):
            print("paired", k, v["n"], round(v["diff"], 3), v["ci95_video"])
    print("grey", json.dumps(res["grey"])[:800])
    print("checks", json.dumps(res["checks"])[:800])


if __name__ == "__main__":
    main()
