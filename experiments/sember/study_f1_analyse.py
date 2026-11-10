#!/usr/bin/env python3
"""StudyF1-shortwin analysis (CPU; dashcam venv). Accuracy with video-bootstrap CIs (2,000, seed 0); paired 32B - 4B
per N; vs K3 (32B) / H1 (4B) on the same questions; by stratum (OLDER / OVERLAP / INSIDE / QT_LE_120, StudyClean's
definitions); grey control; checks. Writes results/sember/study_f1/f1_results.json."""
import collections
import gzip
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/sember/study_f1"
NB, SEED = 2000, 0
MODELS, NS = ("4BI", "32BI"), (1, 3, 9)
STRATA = ("OLDER", "OVERLAP", "INSIDE", "QT_LE_120")
REF = {"32BI": ("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "K3"),
       "4BI": ("results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz", "H1")}


def strata():
    M = {}
    for l in open(REPO / "results/sember/study_h/data/sember_mcq.jsonl"):
        r = json.loads(l)
        M[r["question_id"]] = r
    return M


def stratum(m, qt):
    a, b = sorted((float(m["answer_start_time"]), float(m["answer_end_time"])))
    if qt <= 120:
        return "QT_LE_120"
    lo = qt - 120
    return "OLDER" if b < lo else ("OVERLAP" if a < lo else "INSIDE")


def boot(vals_by_v, rng):
    vids = list(vals_by_v)
    est = float(np.mean([x for v in vids for x in vals_by_v[v]]))
    bs = []
    for _ in range(NB):
        idx = rng.integers(0, len(vids), len(vids))
        xs = [x for i in idx for x in vals_by_v[vids[i]]]
        bs.append(np.mean(xs))
    return dict(n=sum(len(vals_by_v[v]) for v in vids), est=est,
                ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])


def by_video(pairs):
    d = collections.defaultdict(list)
    for v, x in pairs:
        d[v].append(x)
    return d


def main():
    rng = np.random.default_rng(SEED)
    M = strata()
    rows = [json.loads(l) for l in open(OUT / "f1_requests_h100nvl.jsonl")]
    ok = {}
    for r in rows:
        if not r["error"]:
            ok[(r["model"], r["n"], r["question_id"], r["grey"])] = r
    man = {(r["question_id"], r["n"]): r for r in map(json.loads, open(OUT / "f1_inputs_manifest.jsonl"))}
    qs = sorted({q for q, _ in man})
    qt = {q: man[(q, 1)]["question_time"] for q in qs}
    vid = {q: man[(q, 1)]["video_id"] for q in qs}
    st = {q: stratum(M[q], qt[q]) for q in qs}
    ref = {}
    for mdl, (p, cell) in REF.items():
        ref[mdl] = {r["question_id"]: r for r in map(json.loads, gzip.open(REPO / p, "rt"))
                    if r["cell"] == cell and r.get("mode", "batched") == "batched" and not r["error"]}
    res = dict(label="StudyF1-shortwin: device-style short windows (last 3 s, N = 1/3/9, 560x560 separate images) on "
               "the H100 GPU 1 vLLM stack; accuracy only", checks={}, accuracy={}, paired_32_minus_4={},
               vs_recent120={}, grey={}, strata_counts=dict(collections.Counter(st.values())))
    # checks
    for mdl in MODELS:
        for n in NS:
            rs = [ok.get((mdl, n, q, False)) for q in qs]
            have = [r for r in rs if r]
            res["checks"][f"{mdl}_N{n}"] = dict(
                rows_ok=len(have), missing=len(qs) - len(have),
                error_rows_retried=sum(1 for r in rows if r["model"] == mdl and r["n"] == n and r["error"]),
                transport_retries=sum(len(r["transport_errors"]) for r in have),
                unparsed_X=sum(r["pred"] == "X" for r in have),
                finish_length=sum(r["finish_reason"] == "length" for r in have),
                cached_tokens_nonzero=sum(bool(r["cached_tokens"]) for r in have),
                prompt_tokens=dict(min=min(r["prompt_tokens"] for r in have),
                                   median=float(np.median([r["prompt_tokens"] for r in have])),
                                   max=max(r["prompt_tokens"] for r in have)),
                frame_sha_ok=all(r["frame_sha256"] == man[(r["question_id"], n)]["frame_sha256"] for r in have),
                letter_mass_top20_median=float(np.median([r["letter_probs"]["total"] for r in have if r["letter_probs"]])))
    # tokens per frame (same question, N9 - N1) / 8
    d = [(ok[("32BI", 9, q, False)]["prompt_tokens"] - ok[("32BI", 1, q, False)]["prompt_tokens"]) / 8 for q in qs
         if ("32BI", 9, q, False) in ok and ("32BI", 1, q, False) in ok]
    res["checks"]["tokens_per_560_frame"] = dict(values=sorted(set(d)), median=float(np.median(d)))
    res["checks"]["same_tokens_4B_32B"] = sum(ok[("4BI", n, q, False)]["prompt_tokens"] == ok[("32BI", n, q, False)]["prompt_tokens"]
                                              for n in NS for q in qs if ("4BI", n, q, False) in ok and ("32BI", n, q, False) in ok)
    # accuracy
    for mdl in MODELS:
        for n in NS:
            for s in ("ALL",) + STRATA:
                sel = [q for q in qs if (s == "ALL" or st[q] == s) and (mdl, n, q, False) in ok]
                res["accuracy"][f"{mdl}/N{n}/{s}"] = boot(by_video((vid[q], float(ok[(mdl, n, q, False)]["correct"])) for q in sel), rng)
            for s in ("ALL",) + STRATA:
                sel = [q for q in qs if (s == "ALL" or st[q] == s) and (mdl, n, q, False) in ok and q in ref[mdl]]
                res["vs_recent120"][f"{mdl}/N{n}-{REF[mdl][1]}/{s}"] = dict(
                    boot(by_video((vid[q], float(ok[(mdl, n, q, False)]["correct"]) - float(ref[mdl][q]["correct"])) for q in sel), rng),
                    ref_acc=float(np.mean([ref[mdl][q]["correct"] for q in sel])),
                    agreement=float(np.mean([ok[(mdl, n, q, False)]["pred"] == ref[mdl][q]["pred"] for q in sel])))
        for s in ("ALL",) + STRATA:
            sel = [q for q in qs if (s == "ALL" or st[q] == s) and q in ref[mdl]]
            res["accuracy"][f"{mdl}/{REF[mdl][1]}_recent120/{s}"] = boot(by_video((vid[q], float(ref[mdl][q]["correct"])) for q in sel), rng)
    for n in NS:
        for s in ("ALL",) + STRATA:
            sel = [q for q in qs if (s == "ALL" or st[q] == s) and ("4BI", n, q, False) in ok and ("32BI", n, q, False) in ok]
            res["paired_32_minus_4"][f"N{n}/{s}"] = dict(
                boot(by_video((vid[q], float(ok[("32BI", n, q, False)]["correct"]) - float(ok[("4BI", n, q, False)]["correct"])) for q in sel), rng),
                agreement=float(np.mean([ok[("32BI", n, q, False)]["pred"] == ok[("4BI", n, q, False)]["pred"] for q in sel])))
    # grey control (same 100 questions)
    for mdl in MODELS:
        for n in NS:
            g = [q for q in qs if (mdl, n, q, True) in ok]
            real = [q for q in g if (mdl, n, q, False) in ok]
            letters = collections.Counter(ok[(mdl, n, q, True)]["pred"] for q in g)
            res["grey"][f"{mdl}/N{n}"] = dict(
                n=len(g), grey_acc=boot(by_video((vid[q], float(ok[(mdl, n, q, True)]["correct"])) for q in g), rng),
                real_acc_same_q=float(np.mean([ok[(mdl, n, q, False)]["correct"] for q in real])),
                real_minus_grey=boot(by_video((vid[q], float(ok[(mdl, n, q, False)]["correct"]) - float(ok[(mdl, n, q, True)]["correct"])) for q in real), rng),
                distinct_letters=dict(letters), distinct_responses=len({ok[(mdl, n, q, True)]["text"] for q in g}))
    for n in NS:
        g = [q for q in qs if ("4BI", n, q, True) in ok and ("32BI", n, q, True) in ok]
        res["grey"][f"32-4/N{n}"] = boot(by_video((vid[q], float(ok[("32BI", n, q, True)]["correct"]) - float(ok[("4BI", n, q, True)]["correct"])) for q in g), rng)
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_f1_analyse.py", model="4BI,32BI", device="cpu", n=len(qs))
    (OUT / "f1_results.json").write_text(json.dumps(res, indent=1, default=float))
    for k, v in res["accuracy"].items():
        if k.endswith("/ALL"):
            print(k, round(v["est"], 4), [round(x, 4) for x in v["ci"]])


if __name__ == "__main__":
    main()
