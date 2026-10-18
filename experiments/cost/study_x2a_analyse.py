"""StudyX2a analysis (original .venv; CPU only). Metrics exactly as pre-registered in research/EXPERIMENTS.md (StudyX2a).

  cap hit       = completion_tokens >= 24,576 AND no </think> (never closed); Wilson 95% CI
  closed_capped = closed </think> but hit 24,576 in the answer (counted separately)
  overdispersion: chi-square homogeneity across signs, permutation p (10,000), only if >= 2 cap hits
  leave-one-seed-out: score = sign's cap-hit rate on its other seeds; AUROC + Brier vs LOO base rate (>= 2 hits)
  loop vs progress: 8-gram repetition rate over the last 4,096 tokens (model tokenizer); >= 0.5 labelled "loop"
  natural length of terminating traces: median / p90 / p95
"""
import json
import sys
from math import sqrt
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402

D = Path("results/cost/study_x2a")
DEV = "h100nvl"
CAP = 24576
SNAP = (Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Thinking/snapshots/"
        "7edd10ffd1196091948fb245ff63e406ccb2d4d1")
LOOP_TAIL, LOOP_THR, NGRAM = 4096, 0.5, 8


def wilson(k, n, z=1.959964):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def chi2_stat(y, g):
    tot = y.mean()
    if tot in (0, 1):
        return 0.0
    s = 0.0
    for v in np.unique(g):
        m = g == v
        n = m.sum()
        o = y[m].sum()
        e = n * tot
        s += (o - e) ** 2 / e + ((n - o) - n * (1 - tot)) ** 2 / (n * (1 - tot))
    return s


def auroc(score, y):
    pos, neg = score[y], score[~y]
    if len(pos) == 0 or len(neg) == 0:
        return None
    return float(np.mean([(p > neg).mean() + 0.5 * (p == neg).mean() for p in pos]))


def rep_rate(ids):
    ids = ids[-LOOP_TAIL:]
    seen, rep, n = set(), 0, 0
    for i in range(len(ids) - NGRAM + 1):
        g = tuple(ids[i:i + NGRAM])
        n += 1
        rep += g in seen
        seen.add(g)
    return rep / n if n else None


def main():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(SNAP))
    recs = list(read_jsonl(D / f"study_x2a_requests_{DEV}.jsonl"))
    out = dict(n_records=len(recs), arms={})
    for arm in ("T1.0", "T0.8", "T0.6"):
        R = [r for r in recs if r["tag"] == f"X2a_{arm}"]
        if not R:
            continue
        err = [r for r in R if r["error"]]
        R = [r for r in R if not r["error"]]
        ntok = np.array([r["completion_tokens"] or 0 for r in R])
        closed = np.array([r["think_closed"] for r in R])
        cap = (ntok >= CAP) & ~closed
        closed_capped = (ntok >= CAP) & closed
        term = ~(ntok >= CAP)
        k, n = int(cap.sum()), len(R)
        lo, hi = wilson(k, n)
        sign = np.array([r["id"] for r in R])
        per_sign = {s: dict(cap_hits=int(cap[sign == s].sum()), n=int((sign == s).sum()),
                            seeds_hit=[R[i]["seed"] for i in np.where((sign == s) & cap)[0]]) for s in sorted(set(sign))}
        # overdispersion
        od = None
        if k >= 2:
            rng = np.random.default_rng(0)
            obs = chi2_stat(cap.astype(float), sign)
            perm = np.array([chi2_stat(rng.permutation(cap).astype(float), sign) for _ in range(10000)])
            od = dict(chi2=round(float(obs), 2), df=len(per_sign) - 1, perm_p=float((perm >= obs).mean()),
                      n_perm=10000)
        # leave-one-seed-out predictability
        loso = None
        if k >= 2:
            sc = np.array([cap[(sign == sign[i]) & (np.arange(n) != i)].mean() for i in range(n)])
            base = np.array([cap[np.arange(n) != i].mean() for i in range(n)])
            loso = dict(auroc=auroc(sc, cap), brier_sign=float(np.mean((sc - cap) ** 2)),
                        brier_base=float(np.mean((base - cap) ** 2)))
        # loop vs progress
        reps = []
        for i, r in enumerate(R):
            if cap[i] or closed_capped[i]:
                kind = "cap_hit" if cap[i] else "closed_capped"
            else:
                kind = "terminating"
            ids = tok(r.get("text") or "", add_special_tokens=False)["input_ids"]
            reps.append(dict(id=r["id"], seed=r["seed"], kind=kind, tokens=int(ntok[i]),
                             rep8_last4096=rep_rate(ids)))
        cap_reps = [x["rep8_last4096"] for x in reps if x["kind"] == "cap_hit"]
        term_reps = [x["rep8_last4096"] for x in reps if x["kind"] == "terminating" and x["rep8_last4096"] is not None]
        tl = ntok[term]
        out["arms"][arm] = dict(
            n=n, errors=len(err), cap_hits=k, cap_hit_rate=k / n, wilson95=[lo, hi],
            closed_but_capped=int(closed_capped.sum()),
            decision_rule_met=(k / n < 0.02 and hi < 0.05) if arm == "T1.0" else None,
            per_sign=per_sign, overdispersion=od, leave_one_seed_out=loso,
            loop=dict(cap_hit_rep8=[round(x, 3) for x in cap_reps],
                      cap_hit_loops=int(sum(x >= LOOP_THR for x in cap_reps)),
                      terminating_rep8_median=float(np.median(term_reps)) if term_reps else None,
                      terminating_rep8_p90=float(np.percentile(term_reps, 90)) if term_reps else None),
            terminating_length=dict(n=int(term.sum()), median=float(np.median(tl)), p90=float(np.percentile(tl, 90)),
                                    p95=float(np.percentile(tl, 95)), max=int(tl.max())) if len(tl) else None,
            all_length=dict(mean=float(ntok.mean()), median=float(np.median(ntok))),
            traces=reps)
    out["_provenance"] = stamp(script="study_x2a_analyse.py", model="qwen3vl-32b-thinking", device=DEV,
                               n=len(recs))
    (D / f"study_x2a_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    for arm, a in out["arms"].items():
        print(arm, {k: a[k] for k in ("n", "errors", "cap_hits", "cap_hit_rate", "wilson95", "closed_but_capped",
                                      "decision_rule_met", "overdispersion", "leave_one_seed_out",
                                      "terminating_length")}, "loops", a["loop"]["cap_hit_loops"])


if __name__ == "__main__":
    main()
