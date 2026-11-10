#!/usr/bin/env python3
"""StudyE2b-ovo-crr-score — OFFLINE ANALYSIS OF EXISTING SCORES (StudyB1 32B-I, StudyB2-ovo-rtv 4B-I / 8B-I rows). CPU.

On OVO-Bench CRR, does 32B become correct earlier than 4B once each model's willingness to say "Yes" is controlled?
Score: first-token top-20 logprobs; Yes mass = sum of p over tokens whose whitespace-stripped lower-case form is
"yes" or "y"; No mass likewise ("no", "n"); p = Yes / (Yes + No); log p floored at 1e-12.
Checks (stop if failed): StudyE2 HISTORY settle counts (4B 9, 8B 16, 32B 27) reproduce from recorded answers;
neither-in-top-20 <= 5 % per arm x input; (p > 0.5) implies the recorded upstream correctness on >= 98 % of sub-queries.
Parts: (1) AUROC of p post-clue vs pre-clue, pooled and mean within-entry; (2) per-entry rise above the sub-query-0
baseline by delta = 1 / 2 (primary) / 3; (3) matched Yes-bias thresholds (10 % of pre-clue sub-queries >= threshold,
2 folds by video, seed 0; 0 % secondary) and the StudyE2 settle point on thresholded answers.
Paired 32B - 4B (primary), 32B - 8B, 8B - 4B; video bootstrap 2,000, seed 0, videos resampled jointly for both models.
Writes results/orchestration/study_e2b/e2b_results.json.
"""
import collections
import json
import math
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

OUT = ROOT / "results/orchestration/study_e2b"
NB, SEED = 2000, 0
MODELS = ("4BI", "8BI", "32BI")
INPUTS = ("RECENT", "HISTORY")
PAIRS = (("32BI", "4BI"), ("32BI", "8BI"), ("8BI", "4BI"))
SRC = {"4BI": (ROOT / "results/benchmarks/study_b2_ovo_rtv", "b2_rows_4BI"),
       "8BI": (ROOT / "results/benchmarks/study_b2_ovo_rtv", "b2_rows_8BI"),
       "32BI": (ROOT / "results/benchmarks/study_b1_h100", "b1_rows_32BI")}
YES, NO = {"yes", "y"}, {"no", "n"}


def norm(tok):
    return tok.strip().lower()


def score(row):
    lp = row.get("logprobs") or {}
    top = lp.get("top20") or []
    ym = sum(math.exp(l) for t, l in top if norm(t) in YES)
    nm = sum(math.exp(l) for t, l in top if norm(t) in NO)
    ft = norm(lp.get("first_token", "")) if lp else None
    kind = "yes" if ft in YES else ("no" if ft in NO else "neither")
    if ym + nm == 0:
        return None, kind, lp.get("first_token") if lp else None, bool(top)
    p = ym / (ym + nm)
    return p, kind, lp.get("first_token"), True


def logp(p):
    return math.log(max(p, 1e-12))


def settle(corr):
    k = len(corr)
    while k > 0 and corr[k - 1]:
        k -= 1
    return None if k == len(corr) else k


def auroc(pos, neg):
    if not pos or not neg:
        return None
    pos, neg = np.asarray(pos), np.asarray(neg)
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    items = {iid: it for iid, it in ((it["item_id"], it) for it in B.build_items()) if it["task"] == "CRR"}
    ent = collections.defaultdict(list)
    for iid, it in items.items():
        m = re.match(r"^ovo_(\d+)_(\d+)$", iid)
        ent[m.group(1)].append((int(m.group(2)), it))
    for e in ent:
        ent[e].sort(key=lambda x: x[0])
    E = sorted(ent)
    video = {e: ent[e][0][1]["video_key"] for e in E}
    gold = {e: [int(it["gt"]) for _, it in ent[e]] for e in E}
    times = {e: [it["t"] for _, it in ent[e]] for e in E}
    cidx = {e: next((j for j, g in enumerate(gold[e]) if g == 1), None) for e in E}
    res = dict(label="OFFLINE ANALYSIS OF EXISTING SCORES (StudyB1 / StudyB2-ovo-rtv rows); Instruct only; no new inference",
               at=datetime.now().isoformat(), checks={}, structure={})
    res["structure"] = dict(entries=len(E), subqueries_per_entry=sorted({len(ent[e]) for e in E}),
                            gold_patterns=dict(collections.Counter("".join(map(str, gold[e])) for e in E)),
                            clue_index=dict(collections.Counter(cidx[e] for e in E)),
                            gap_before_clue_s=dict(zip(("min", "median", "max"), np.percentile(
                                [times[e][cidx[e]] - times[e][cidx[e] - 1] for e in E if cidx[e]], [0, 50, 100]).tolist())),
                            gap_after_clue_s=dict(zip(("min", "median", "max"), np.percentile(
                                [times[e][cidx[e] + 1] - times[e][cidx[e]] for e in E if cidx[e] is not None and cidx[e] + 1 < len(times[e])], [0, 50, 100]).tolist())),
                            videos=len(set(video.values())))
    rows = {}
    for m in MODELS:
        d, stem = SRC[m]
        rs = C2.read_rows(d, stem) if m != "32BI" else C2.read_rows_file(d / f"{stem}.jsonl.gz")
        rows[m] = {(r["item_id"], r["input"]): r for r in rs if r["tag"] == "main" and not r["error"] and r["task"] == "CRR"}
    # ---- check 4 first: StudyE2 HISTORY settle counts from recorded answers
    rep = {}
    for m in MODELS:
        for inp in INPUTS:
            rep[f"{m}/{inp}"] = sum(settle([bool(rows[m][(it["item_id"], inp)]["correct_upstream"]) for _, it in ent[e]]) is not None for e in E)
    res["checks"]["e2_settle_counts_recorded"] = rep
    want = {"4BI": 9, "8BI": 16, "32BI": 27}
    if any(rep[f"{m}/HISTORY"] != want[m] for m in MODELS):
        (OUT / "e2b_results.json").write_text(json.dumps(res, indent=1, default=float))
        raise SystemExit(f"StudyE2 settle counts do not reproduce: {rep} — stop and ask")
    # ---- score checks
    P = {}
    sc = {}
    for m in MODELS:
        for inp in INPUTS:
            kinds, neither_ex, agree, n, missing_lp, undefined = collections.Counter(), [], 0, 0, 0, 0
            for e in E:
                for j, it in ent[e]:
                    r = rows[m][(it["item_id"], inp)]
                    if not r.get("logprobs"):
                        missing_lp += 1
                        continue
                    p, kind, ft, _ = score(r)
                    kinds[kind] += 1
                    if kind == "neither" and len(neither_ex) < 10:
                        neither_ex.append(ft)
                    if p is None:
                        undefined += 1
                        continue
                    P[(m, inp, e, j)] = p
                    n += 1
                    agree += ((p > 0.5) == (gold[e][j] == 1)) == bool(r["correct_upstream"])
            tot = sum(kinds.values())
            sc[f"{m}/{inp}"] = dict(n=tot, first_token_yes=kinds["yes"], first_token_no=kinds["no"],
                                    first_token_neither=kinds["neither"], neither_in_top20=undefined,
                                    neither_in_top20_frac=undefined / max(tot, 1), missing_logprobs=missing_lp,
                                    examples_first_token_neither=neither_ex,
                                    agreement_p05_vs_recorded=agree / max(n, 1))
    res["checks"]["score"] = sc
    bad = [k for k, v in sc.items() if v["missing_logprobs"] or v["neither_in_top20_frac"] > 0.05 or v["agreement_p05_vs_recorded"] < 0.98]
    if bad:
        (OUT / "e2b_results.json").write_text(json.dumps(res, indent=1, default=float))
        raise SystemExit(f"score check failed for {bad} — stop and ask")
    vids = sorted(set(video.values()))
    ents_by_v = collections.defaultdict(list)
    for e in E:
        ents_by_v[video[e]].append(e)

    def resample():
        return [e for v in rng.choice(vids, len(vids), replace=True) for e in ents_by_v[v]]

    def ci(xs):
        xs = [x for x in xs if x is not None]
        return [float(np.percentile(xs, 2.5)), float(np.percentile(xs, 97.5))] if xs else None

    # ---- Part 1: AUROC
    def pooled(m, inp, es):
        pos = [P[(m, inp, e, j)] for e in es for j in range(5) if gold[e][j] == 1 and (m, inp, e, j) in P]
        neg = [P[(m, inp, e, j)] for e in es for j in range(5) if gold[e][j] == 0 and (m, inp, e, j) in P]
        return auroc(pos, neg)

    def within(m, inp, es):
        a = [auroc([P[(m, inp, e, j)] for j in range(5) if gold[e][j] == 1 and (m, inp, e, j) in P],
                   [P[(m, inp, e, j)] for j in range(5) if gold[e][j] == 0 and (m, inp, e, j) in P]) for e in es]
        a = [x for x in a if x is not None]
        return float(np.mean(a)) if a else None

    boots = [resample() for _ in range(NB)]
    p1 = {}
    for inp in INPUTS:
        for m in MODELS:
            p1[f"{m}/{inp}"] = dict(pooled=pooled(m, inp, E), pooled_ci=ci([pooled(m, inp, b) for b in boots]),
                                    within=within(m, inp, E), within_ci=ci([within(m, inp, b) for b in boots]))
        for a, b in PAIRS:
            p1[f"{a}-{b}/{inp}"] = dict(pooled_diff=pooled(a, inp, E) - pooled(b, inp, E),
                                        pooled_diff_ci=ci([pooled(a, inp, s) - pooled(b, inp, s) for s in boots]),
                                        within_diff=within(a, inp, E) - within(b, inp, E),
                                        within_diff_ci=ci([within(a, inp, s) - within(b, inp, s) for s in boots]))
    res["part1_auroc"] = p1

    # ---- Part 2: rise above the sub-query-0 baseline
    p2 = {}
    for delta in (1, 2, 3):
        rise = {}
        for m in MODELS:
            for inp in INPUTS:
                d = {}
                for e in E:
                    if any((m, inp, e, j) not in P for j in range(5)):
                        d[e] = ("missing", None)
                        continue
                    base = logp(P[(m, inp, e, 0)])
                    k = next((j for j in range(1, 5) if logp(P[(m, inp, e, j)]) >= base + delta), None)
                    d[e] = ("none", None) if k is None else (("correct", k) if k >= cidx[e] else ("false", k))
                rise[(m, inp)] = d
                p2[f"d{delta}/{m}/{inp}"] = dict(collections.Counter(v[0] for v in d.values()))
        for inp in INPUTS:
            for a, b in PAIRS:
                both = [e for e in E if rise[(a, inp)][e][0] == "correct" and rise[(b, inp)][e][0] == "correct"]
                diff = {e: rise[(a, inp)][e][1] - rise[(b, inp)][e][1] for e in both}

                def mean_of(es):
                    x = [diff[e] for e in es if e in diff]
                    return float(np.mean(x)) if x else None
                p2[f"d{delta}/{a}-{b}/{inp}"] = dict(
                    both_correct_rise=len(both), mean_diff_subqueries=mean_of(E), mean_ci=ci([mean_of(s) for s in boots]),
                    earlier=sum(v < 0 for v in diff.values()), same=sum(v == 0 for v in diff.values()),
                    later=sum(v > 0 for v in diff.values()),
                    only_big_correct=sum(rise[(a, inp)][e][0] == "correct" and rise[(b, inp)][e][0] != "correct" for e in E),
                    only_small_correct=sum(rise[(a, inp)][e][0] != "correct" and rise[(b, inp)][e][0] == "correct" for e in E))
    res["part2_rise"] = dict(note="rise index - c, in sub-queries; only 1-2 pre-clue sub-queries per entry, so the baseline is noisy",
                             results=p2)

    # ---- Part 3: matched Yes-bias thresholds, settle point on thresholded answers
    from sklearn.model_selection import KFold
    kf = KFold(2, shuffle=True, random_state=SEED)
    vfold = {}
    for fi, (_, te) in enumerate(kf.split(vids)):
        for i in te:
            vfold[vids[i]] = fi
    p3 = {}
    for target in (0.10, 0.0):
        st = {}
        for m in MODELS:
            for inp in INPUTS:
                thr, held_fy, held_n = {}, 0, 0
                for fi in (0, 1):
                    train = [P[(m, inp, e, j)] for e in E if vfold[video[e]] != fi for j in range(5)
                             if gold[e][j] == 0 and (m, inp, e, j) in P]
                    vals = np.unique(train)[::-1]
                    th = np.nextafter(vals[0], np.inf)          # 0 %: above every training pre-clue score
                    if target > 0:
                        for v in vals:
                            if np.mean(np.asarray(train) >= v) <= target:
                                th = v
                            else:
                                break
                    thr[fi] = float(th)
                    test_pre = [P[(m, inp, e, j)] for e in E if vfold[video[e]] == fi for j in range(5)
                                if gold[e][j] == 0 and (m, inp, e, j) in P]
                    held_fy += sum(x >= th for x in test_pre)
                    held_n += len(test_pre)
                d = {}
                for e in E:
                    th = thr[vfold[video[e]]]
                    corr = [((P[(m, inp, e, j)] >= th) == (gold[e][j] == 1)) for j in range(5)]
                    k = settle(corr)
                    d[e] = None if k is None else (k, times[e][k] - times[e][0])
                st[(m, inp)] = d
                p3[f"t{int(target * 100)}/{m}/{inp}"] = dict(thresholds=thr, heldout_false_yes=held_fy / held_n,
                                                              settle=sum(v is not None for v in d.values()), entries=len(E))
        for inp in INPUTS:
            for a, b in PAIRS:
                A, Bm = st[(a, inp)], st[(b, inp)]
                both = [e for e in E if A[e] is not None and Bm[e] is not None]

                def m_s(es, idx):
                    x = [A[e][idx] - Bm[e][idx] for e in es if e in both]
                    return float(np.mean(x)) if x else None
                p3[f"t{int(target * 100)}/{a}-{b}/{inp}"] = dict(
                    both_settle=len(both), only_big=sum(A[e] is not None and Bm[e] is None for e in E),
                    only_small=sum(A[e] is None and Bm[e] is not None for e in E),
                    mean_diff_s=m_s(E, 1), mean_diff_s_ci=ci([m_s(s, 1) for s in boots]),
                    mean_diff_subq=m_s(E, 0), mean_diff_subq_ci=ci([m_s(s, 0) for s in boots]),
                    earlier=sum(A[e][0] < Bm[e][0] for e in both), same=sum(A[e][0] == Bm[e][0] for e in both),
                    later=sum(A[e][0] > Bm[e][0] for e in both))
    res["part3_matched_bias"] = p3
    res["input_note"] = "RECENT = 9 frames over the last 3 s (~3.1k tokens); HISTORY = 37 frames over [0, t] (~12.6k): ~4x the tokens"
    res["_provenance"] = stamp(script="study_e2b_ovo_crr_score.py", model="4BI,8BI,32BI (rows)", device="cpu", n=len(E) * 5)
    (OUT / "e2b_results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in ("structure", "checks")}, indent=1, default=float)[:5000])


if __name__ == "__main__":
    main()
