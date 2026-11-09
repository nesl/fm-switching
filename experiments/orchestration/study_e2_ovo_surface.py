#!/usr/bin/env python3
"""StudyE2-ovo-surface — OFFLINE ANALYSIS OF EXISTING SCORES (StudyB1 32BI rows, StudyB2-ovo-rtv 4BI / 8BI rows). CPU.

On OVO-Bench forward-active tasks (CRR, SSR, REC), does 32B become correct earlier than 4B within an entry, and does
HISTORY change that? Instruct only (greedy everywhere); no Thinking rows.
Structure first: entries per task, sub-queries per entry, how gold changes across sub-queries, time gaps; a task whose
sub-queries are not the same question asked at different times is STOPPED (reported, not analysed further).
Per (task, model, input, sub-query index): accuracy (upstream scorer as recorded) with video bootstrap 95 % CI.
Per entry: the "settle" index k* = the smallest sub-query index such that the model is correct at every sub-query
>= k*; its time = that sub-query's realtime (absolute) and relative to the entry's first sub-query; entries where the
model is wrong at the last sub-query never settle (counted separately).
Paired 32B - 4B settle time (entries where both settle), per input; interaction (32B - 4B)HISTORY - (32B - 4B)RECENT
on entries where all four settle; video bootstrap (2,000, seed 0). 8B secondary (32B - 8B, 8B - 4B).
Frame identity re-verified on these rows (frame SHA-256 lists equal across 4B / 8B / 32B per (item, input)).
RECENT vs HISTORY: 9 frames over the last 3 s vs 37 over [0, t], ~3.1k vs ~12.6k prompt tokens (~4x).
Writes results/orchestration/study_e2/e2_results.json.
"""
import collections
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/benchmarks"))
sys.path.insert(0, str(ROOT / "experiments/lib"))
import b2_common as C2  # noqa: E402

C2.check_b1_common()
import b1_common as B  # noqa: E402
from _provenance import stamp  # noqa: E402

OUT = ROOT / "results/orchestration/study_e2"
NB, SEED = 2000, 0
SRC = {"4BI": (ROOT / "results/benchmarks/study_b2_ovo_rtv", "b2_rows_4BI"),
       "8BI": (ROOT / "results/benchmarks/study_b2_ovo_rtv", "b2_rows_8BI"),
       "32BI": (ROOT / "results/benchmarks/study_b1_h100", "b1_rows_32BI")}
TASKS = ("CRR", "SSR", "REC")
INPUTS = ("RECENT", "HISTORY")


def rows_for(m):
    d, stem = SRC[m]
    rows = C2.read_rows(d, stem) if m != "32BI" else C2.read_rows_file(d / f"{stem}.jsonl.gz")
    ok = {}
    for r in rows:
        if r["tag"] == "main" and not r["error"] and r["task"] in TASKS:
            ok[(r["item_id"], r["input"])] = r
    return ok


def vboot(by_v, fn, rng):
    vids = list(by_v)
    if not vids:
        return None
    bs = []
    for _ in range(NB):
        idx = rng.integers(0, len(vids), len(vids))
        x = [v for i in idx for v in by_v[vids[i]]]
        bs.append(fn(x))
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    items = {it["item_id"]: it for it in B.build_items() if it["dataset"] == "ovo_bench" and it["task"] in TASKS}
    ent = collections.defaultdict(list)                     # (task, entry id) -> [(j, item)]
    for iid, it in items.items():
        m = re.match(r"^ovo_(\d+)_(\d+)$", iid)
        ent[(it["task"], m.group(1))].append((int(m.group(2)), it))
    for k in ent:
        ent[k].sort(key=lambda x: x[0])
    res = dict(label="OFFLINE ANALYSIS OF EXISTING SCORES (StudyB1 / StudyB2-ovo-rtv rows); no new inference",
               at=datetime.now().isoformat(), structure={}, stopped={}, checks={})
    # ---- structure
    for task in TASKS:
        es = [v for (t, _), v in ent.items() if t == task]
        nq = [len(v) for v in es]
        same_q = sum(len({it["text"] for _, it in v}) == 1 for v in es)
        gaps = [b[1]["t"] - a[1]["t"] for v in es for a, b in zip(v, v[1:])]
        mono_t = all(all(b[1]["t"] >= a[1]["t"] for a, b in zip(v, v[1:])) for v in es)
        gold_changes = collections.Counter(sum(a[1]["gt"] != b[1]["gt"] for a, b in zip(v, v[1:])) for v in es)
        gold_pattern = collections.Counter(tuple(str(it["gt"]) for _, it in v)[:6] for v in es).most_common(6)
        res["structure"][task] = dict(entries=len(es), subqueries=sum(nq), per_entry=dict(min=min(nq), median=float(np.median(nq)), max=max(nq)),
                                      entries_same_question_text=same_q, times_non_decreasing=mono_t,
                                      gap_s=dict(min=float(min(gaps)), median=float(np.median(gaps)), max=float(max(gaps))) if gaps else None,
                                      gold_changes_per_entry=dict(sorted(gold_changes.items())),
                                      common_gold_sequences_first6=[[list(p), n] for p, n in gold_pattern],
                                      example_texts=[it["text"][-160:] for _, it in es[0][:2]])
        if same_q < len(es):
            res["stopped"][task] = (f"sub-queries are not the same question asked at different times: "
                                    f"{len(es) - same_q} of {len(es)} entries have more than one distinct question text "
                                    f"(SSR asks whether a different procedure step has been done at each sub-query)")
    run_tasks = [t for t in TASKS if t not in res["stopped"]]
    # ---- rows and identity
    R = {m: rows_for(m) for m in SRC}
    ident = {}
    for a, b in (("4BI", "32BI"), ("8BI", "32BI"), ("4BI", "8BI")):
        keys = set(R[a]) & set(R[b])
        ident[f"{a}|{b}"] = dict(compared=len(keys), frame_sha_mismatch=sum(R[a][k]["frame_sha256"] != R[b][k]["frame_sha256"] for k in keys),
                                 t_mismatch=sum(abs(R[a][k]["t"] - R[b][k]["t"]) > 1e-9 for k in keys))
    res["checks"]["identical_frames_across_arms"] = ident
    res["checks"]["rows_present"] = {m: {inp: sum(1 for k in R[m] if k[1] == inp) for inp in INPUTS} for m in SRC}
    res["checks"]["subquery_time_recorded_in_rows"] = all("t" in r for m in R for r in R[m].values())
    res["input_note"] = ("RECENT = 9 frames over [max(0, t-3), t] (~3.1k prompt tokens); HISTORY = 37 frames over [0, t] "
                         "(~12.6k tokens): ~4x the tokens. Input, stack and decoding identical across models within an input.")
    # ---- per (task, model, input, j) accuracy
    acc = {}
    for task in run_tasks:
        es = {k: v for k, v in ent.items() if k[0] == task}
        maxj = max(len(v) for v in es.values())
        for m in SRC:
            for inp in INPUTS:
                for j in range(maxj):
                    by_v = collections.defaultdict(list)
                    for (t, e), v in es.items():
                        if j < len(v):
                            it = v[j][1]
                            r = R[m].get((it["item_id"], inp))
                            if r is not None:
                                by_v[it["video_key"]].append(float(bool(r["correct_upstream"])))
                    n = sum(len(x) for x in by_v.values())
                    if n >= 10:
                        acc[f"{task}/{m}/{inp}/j{j}"] = dict(n=n, accuracy=float(np.mean([x for v in by_v.values() for x in v])),
                                                             ci95_video=vboot(by_v, np.mean, rng))
    res["accuracy_by_subquery"] = acc
    # ---- settle times
    settle = {}
    for task in run_tasks:
        es = {k: v for k, v in ent.items() if k[0] == task}
        for m in SRC:
            for inp in INPUTS:
                d = {}
                for (t, e), v in es.items():
                    corr = []
                    for j, it in v:
                        r = R[m].get((it["item_id"], inp))
                        corr.append(None if r is None else bool(r["correct_upstream"]))
                    if None in corr:
                        d[e] = ("missing", None, None, v[0][1]["video_key"])
                        continue
                    k = len(corr)
                    while k > 0 and corr[k - 1]:
                        k -= 1
                    if k == len(corr):
                        d[e] = ("never", None, None, v[0][1]["video_key"])
                    else:
                        d[e] = ("settles", v[k][1]["t"], v[k][1]["t"] - v[0][1]["t"], v[0][1]["video_key"], k)
                settle[(task, m, inp)] = d
    summ, paired = {}, {}
    for (task, m, inp), d in settle.items():
        s = [x for x in d.values() if x[0] == "settles"]
        summ[f"{task}/{m}/{inp}"] = dict(entries=len(d), settle=len(s), never=sum(x[0] == "never" for x in d.values()),
                                         missing=sum(x[0] == "missing" for x in d.values()),
                                         settle_at_first_subquery=sum(1 for x in s if x[4] == 0),
                                         median_settle_rel_s=float(np.median([x[2] for x in s])) if s else None,
                                         median_settle_index=float(np.median([x[4] for x in s])) if s else None)
    for task in run_tasks:
        for big, small in (("32BI", "4BI"), ("32BI", "8BI"), ("8BI", "4BI")):
            per_inp = {}
            for inp in INPUTS:
                A, Bm = settle[(task, big, inp)], settle[(task, small, inp)]
                both = [e for e in A if A[e][0] == "settles" and Bm[e][0] == "settles"]
                by_v = collections.defaultdict(list)
                for e in both:
                    by_v[A[e][3]].append(A[e][1] - Bm[e][1])
                d = [x for v in by_v.values() for x in v]
                per_inp[inp] = {e: A[e][1] - Bm[e][1] for e in both}
                paired[f"{task}/{big}-{small}/{inp}"] = dict(
                    n_both_settle=len(both), only_big_settles=sum(A[e][0] == "settles" and Bm[e][0] != "settles" for e in A),
                    only_small_settles=sum(A[e][0] != "settles" and Bm[e][0] == "settles" for e in A),
                    mean_diff_s=float(np.mean(d)) if d else None, mean_ci=vboot(by_v, np.mean, rng),
                    median_diff_s=float(np.median(d)) if d else None,
                    frac_big_earlier=float(np.mean([x < 0 for x in d])) if d else None,
                    frac_same=float(np.mean([x == 0 for x in d])) if d else None)
            common = set(per_inp["RECENT"]) & set(per_inp["HISTORY"])
            by_v = collections.defaultdict(list)
            for e in common:
                vk = settle[(task, big, "RECENT")][e][3]
                by_v[vk].append(per_inp["HISTORY"][e] - per_inp["RECENT"][e])
            d = [x for v in by_v.values() for x in v]
            paired[f"{task}/{big}-{small}/HISTORY-RECENT interaction"] = dict(
                n=len(common), mean=float(np.mean(d)) if d else None, mean_ci=vboot(by_v, np.mean, rng),
                note="(big - small settle time under HISTORY) - (same under RECENT); inputs differ ~4x in tokens")
    res["settle_summary"] = summ
    res["paired"] = paired
    res["_provenance"] = stamp(script="study_e2_ovo_surface.py", model="4BI,8BI,32BI (rows)", device="cpu",
                               n=sum(len(v) for v in ent.values()))
    (OUT / "e2_results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in ("structure", "stopped", "checks")}, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
