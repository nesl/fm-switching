#!/usr/bin/env python3
"""StudyD14b-dense analysis (CPU; dashcam venv). Writes the trace in StudyD14's row format and the summary.

TRACE   results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz: one row per arm x clip x t (t a float on the 0.25-s
        grid) with model, n, file_name, label, t, time_of_event, time_of_alert, duration_s, scene, light, weather, p_yes,
        score (log P(Yes) floored at 1e-12), first_token, prompt_tokens, request_id. Readable by study_e9_episodes.py
        with only a step-size change.
AP      StudyE5 Part G / StudyE9 method (study_e9_episodes.ap_from, zero latency): positive = each positive clip's
        decision nearest time_of_event - h on the grid (clipped to [3, T]); negatives = every negative-clip decision;
        clip bootstrap 2,000, seed 0, stratified by label (one positive and one negative resample per draw, shared by
        all horizons). Horizons 0 / 0.25 / 0.5 / 0.75 / 1.0 / 1.5 / 2.0 s. Computed on the 0.25-s grid and on the
        integer-t subsample (= D14's grid; must reproduce StudyE9's zero-latency AP when determinism holds).
"""
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/lib"))
sys.path.insert(0, str(HERE))
from study_e9_episodes import ap_from  # noqa: E402

OUT = REPO / "results/dashcam/study_d14b"
STEP = 0.25
HORIZONS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
NB, SEED = 2000, 0
ARMS = [("4BI", 1), ("32BI", 1), ("32BI", 3), ("4BI", 3)]


def main():
    man = {r["request_id"]: r for r in map(json.loads, gzip.open(OUT / "d14b_requests_manifest.jsonl.gz", "rt"))}
    rows = [json.loads(l) for l in open(OUT / "d14b_requests_h100nvl.jsonl")]
    meta = json.load(open(OUT / "d14b_run_meta_h100nvl.json"))
    res = dict(label="StudyD14b-dense: 0.25-s Nexar score trace (h100nvl GPU 2, vLLM 0.31.0, batched, prefix caching off)",
               determinism=meta.get("determinism"), prompt_trace=meta.get("prompt_trace"), arms={})
    ok = {}
    for r in rows:
        if not r["error"]:
            ok[(r["model"], r["n"], r["request_id"])] = r
    trace = []
    for (model, n, rid), r in ok.items():
        if r["grey"]:
            continue
        q = man[rid]
        trace.append(dict(model=model, n=n, file_name=q["file_name"], label=q["label"], t=q["t"],
                          time_of_event=q["time_of_event"], time_of_alert=q["time_of_alert"], duration_s=q["duration_s"],
                          scene=q["scene"], light=q["light"], weather=q["weather"], p_yes=r["p_yes"],
                          score=math.log(max(r["p_yes"], 1e-12)) if r["p_yes"] is not None else None,
                          first_token=r["first_token"], prompt_tokens=r["prompt_tokens"], request_id=rid,
                          d14_request_id=q["d14_request_id"]))
    trace.sort(key=lambda x: (x["model"], x["n"], x["file_name"], x["t"]))
    with gzip.open(OUT / "d14b_trace_h100nvl.jsonl.gz", "wt") as f:
        for x in trace:
            f.write(json.dumps(x) + "\n")
    clips = sorted({q["file_name"] for q in man.values()})
    cmeta = {}
    for q in man.values():
        cmeta.setdefault(q["file_name"], dict(label=q["label"], event=q["time_of_event"], dur=q["duration_s"]))
    pos = [c for c in clips if cmeta[c]["label"] == "positive"]
    neg = [c for c in clips if cmeta[c]["label"] == "negative"]
    rng = np.random.default_rng(SEED)
    boots = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg))) for _ in range(NB)]
    by = defaultdict(dict)
    for x in trace:
        by[(x["model"], x["n"])].setdefault(x["file_name"], {})[x["t"]] = x["score"]
    for arm in ARMS:
        if arm not in by:
            continue
        per = by[arm]
        allr = [r for r in rows if r["model"] == arm[0] and r["n"] == arm[1]]
        keys = {r["request_id"] for r in allr}
        okk = {r["request_id"] for r in allr if not r["error"]}
        grey = [r for r in allr if r["grey"] and not r["error"]]
        real = [r for r in allr if not r["grey"] and not r["error"]]
        a = dict(rows=len(allr), error_rows=sum(bool(r["error"]) for r in allr), retried_ok=sum(
                     1 for r in allr if not r["error"] and r["attempt"] > 1), still_failed=len(keys - okk),
                 decisions=len(real), clips=len(per), neither=sum(bool(r["neither"]) for r in real),
                 prompt_tokens=dict(Counter(r["prompt_tokens"] for r in real)),
                 grey=dict(n=len(grey), yes_rate=float(np.mean([r["p_yes"] > 0.5 for r in grey])) if grey else None,
                           median_p_yes=float(np.median([r["p_yes"] for r in grey])) if grey else None),
                 yes_rate_real=float(np.mean([r["p_yes"] > 0.5 for r in real])))
        complete = len(per) == 300 and all(
            sorted(per[c]) == [3.0 + STEP * j for j in range(len(per[c]))] for c in per)
        a["complete_trajectories"] = complete
        for grid, keep in (("dense_0.25s", lambda t: True), ("integer_1s", lambda t: t == int(t))):
            arr = {c: np.array([per[c][t] for t in sorted(per[c]) if keep(t)]) for c in clips if c in per}
            tt = {c: [t for t in sorted(per[c]) if keep(t)] for c in clips if c in per}
            if not all(c in arr for c in clips):
                continue

            step = STEP if grid.startswith("dense") else 1.0

            def idx(c, h):            # E9's rule on this grid: round((event - h) / step) on the absolute grid, clipped to [0, last]
                return int(min(max(round((cmeta[c]["event"] - h) / step) - round(3.0 / step), 0), len(tt[c]) - 1))
            P = [np.array([arr[c][idx(c, h)] for c in pos]) for h in HORIZONS]
            Ncat = np.concatenate([arr[c] for c in neg])
            nl = np.array([len(arr[c]) for c in neg])
            off = np.concatenate([[0], np.cumsum(nl)])
            out = {}
            for i, h in enumerate(HORIZONS):
                bs = []
                for pi, ni in boots:
                    nn = np.concatenate([Ncat[off[j]:off[j + 1]] for j in ni])
                    bs.append(ap_from(P[i][pi], nn))
                out[str(h)] = dict(ap=ap_from(P[i], Ncat), ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])
            a[f"ap_{grid}"] = out
            a[f"negatives_{grid}"] = int(len(Ncat))
            a[f"base_rate_{grid}"] = len(pos) / (len(pos) + len(Ncat))
        res["arms"][f"{arm[0]}_N{arm[1]}"] = a
    from _provenance import stamp
    res["_provenance"] = stamp(script="d14b_analyse.py", model="4BI,32BI", device="cpu", n=len(trace))
    (OUT / "d14b_results_h100nvl.json").write_text(json.dumps(res, indent=1))
    for k, a in res["arms"].items():
        print(k, a["decisions"], a["still_failed"], a["grey"], {g: {h: round(v["ap"], 4) for h, v in a[f"ap_{g}"].items()}
                                                              for g in ("dense_0.25s", "integer_1s") if f"ap_{g}" in a})


if __name__ == "__main__":
    main()
