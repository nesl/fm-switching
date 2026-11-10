#!/usr/bin/env python3
"""StudyE5-nexar-rise — OFFLINE ANALYSIS OF EXISTING SCORES (StudyD14-trace validation traces). CPU only.

For each real crash, which model's score first rises clearly above its own earlier level in the same clip, and by how
much earlier? (When each model notices a change, not when it answers Yes.)
Definitions (pre-registered in research/EXPERIMENTS.md, StudyE5-nexar-rise):
  r: positives time_of_event (d14_sample.json); negatives assigned by the StudyD2 rule (d2_prepare.py): negatives in
     file-name order, random.Random(0).choice over the sorted positive time_of_event values of the same duration bin
     (18-20 s, 38-42 s, other), clipped to [3, D - 2] when D >= 5. Pool = the 150 VALIDATION positives (only
     validation clips may be read). KS test per bin.
  baseline window 3 <= t <= r - 5 (>= 5 seconds required); m = median s; d = max(1.4826 * MAD, 0.5).
  search window r - 5 <= t <= r + 3; rise (primary) = first t with s >= m + 3d; secondary k = 2; k = 3 with 2
  consecutive seconds (rise time = the first of the two). Times relative to r.
Fairness secondary: per model, the multiplier k for a 10 % false-rise rate on negatives, fitted on one half of the
negatives (2 folds by clip, seed 0) and evaluated on the other; swapped and pooled; paired lead at those matched k.
References only: first P(Yes) > 0.5 in the search window; raw Yes rate on negative seconds; D14 event-relative AUROC.
Writes results/orchestration/study_e5/e5_results.json.
"""
import collections
import gzip
import json
import random
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

D14 = ROOT / "results/dashcam/study_d14_trace"
OUT = ROOT / "results/orchestration/study_e5"
ARMS = ["4BI_N1", "4BI_N3", "32BI_N1", "32BI_N3", "32BI_N9"]
PAIRS = [("32BI_N1", "4BI_N1"), ("32BI_N3", "4BI_N3"), ("32BI_N9", "4BI_N3"), ("32BI_N1", "4BI_N3")]
RULES = {"k3": (3.0, 1), "k2": (2.0, 1), "k3_2consec": (3.0, 2)}
NB, SEED, FLOOR_D, WIN = 2000, 0, 0.5, 3.0


def dbin(d):
    return "18-20" if 18.0 <= d < 20.0 else ("38-42" if 38.0 <= d <= 42.0 else "other")


def load():
    sample = json.loads((D14 / "d14_sample.json").read_text())
    labels = {c["file_name"]: c for c in sample["clips"]}
    trace = collections.defaultdict(dict)
    n_grey = 0
    for l in gzip.open(D14 / "d14_trace_h100nvl.jsonl.gz", "rt"):
        r = json.loads(l)
        if r.get("grey") or r.get("label") not in ("positive", "negative"):
            n_grey += 1
            continue
        trace[f"{r['model']}_N{r['n']}"].setdefault(r["file_name"], {})[int(r["t"])] = (r["score"], r["p_yes"])
    clips = sorted(labels)
    return labels, trace, clips, n_grey


def auroc(pos, neg):
    x = np.concatenate([pos, neg])
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    rp = ranks[:len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def assign_refs(labels, clips):
    pos_by_bin = collections.defaultdict(list)
    for c in clips:
        if labels[c]["label"] == "positive":
            pos_by_bin[dbin(labels[c]["duration_s"])].append(float(labels[c]["time_of_event"]))
    rrng = random.Random(0)
    ref = {}
    info = {}
    for c in clips:
        if labels[c]["label"] == "positive":
            ref[c] = float(labels[c]["time_of_event"])
    for c in sorted(c for c in clips if labels[c]["label"] == "negative"):
        d = labels[c]["duration_s"]
        b = dbin(d)
        raw = rrng.choice(sorted(pos_by_bin[b]))
        ref[c] = min(max(raw, WIN), d - 2.0) if d >= WIN + 2.0 else raw
        info[c] = dict(bin=b, sampled=raw, clipped=ref[c] != raw)
    from scipy.stats import ks_2samp
    check = {}
    for b in ("18-20", "38-42", "other"):
        p = [ref[c] for c in clips if labels[c]["label"] == "positive" and dbin(labels[c]["duration_s"]) == b]
        n = [ref[c] for c in clips if labels[c]["label"] == "negative" and dbin(labels[c]["duration_s"]) == b]
        check[b] = dict(n_pos=len(p), n_neg=len(n),
                        pos_q=[float(x) for x in np.percentile(p, [5, 25, 50, 75, 95])] if p else None,
                        neg_q=[float(x) for x in np.percentile(n, [5, 25, 50, 75, 95])] if n else None,
                        ks_p=float(ks_2samp(p, n).pvalue) if len(p) > 1 and len(n) > 1 else None)
    check["clipped"] = sum(v["clipped"] for v in info.values())
    return ref, check


def baseline(series, r):
    """series: {t: (s, p)} -> (m, d_raw, d, n_base) or None if < 5 baseline seconds."""
    b = [series[t][0] for t in sorted(series) if 3 <= t <= r - 5]
    if len(b) < 5:
        return None
    b = np.asarray(b)
    m = float(np.median(b))
    d_raw = float(1.4826 * np.median(np.abs(b - m)))
    return m, d_raw, max(d_raw, FLOOR_D), len(b)


def rise_time(series, r, m, d, k, consec):
    ts = [t for t in sorted(series) if r - 5 <= t <= r + 3]
    hit = [series[t][0] >= m + k * d for t in ts]
    for i, t in enumerate(ts):
        if consec == 1 and hit[i]:
            return t - r
        if consec == 2 and hit[i] and i + 1 < len(ts) and hit[i + 1] and ts[i + 1] == t + 1:
            return t - r
    return None


def first_yes(series, r):
    for t in sorted(series):
        if r - 5 <= t <= r + 3 and series[t][1] > 0.5:
            return t - r
    return None


def boot(vals, fn, rng):
    vals = np.asarray(vals, float)
    if len(vals) == 0:
        return None
    return [float(np.percentile([fn(vals[rng.integers(0, len(vals), len(vals))]) for _ in range(NB)], q)) for q in (2.5, 97.5)]


def q3(x):
    return dict(median=float(np.median(x)), p25=float(np.percentile(x, 25)), p75=float(np.percentile(x, 75))) if x else None


def paired_table(R, pos, big, small, rng):
    A, Bm = R[big], R[small]
    keys = [c for c in pos if c in A and c in Bm]          # clips with a valid baseline in both arms
    both = [c for c in keys if A[c] is not None and Bm[c] is not None]
    d = [A[c] - Bm[c] for c in both]
    return dict(n_valid_both_arms=len(keys), both=len(both),
                only_32B=sum(A[c] is not None and Bm[c] is None for c in keys),
                only_4B=sum(A[c] is None and Bm[c] is not None for c in keys),
                neither=sum(A[c] is None and Bm[c] is None for c in keys),
                mean=float(np.mean(d)) if d else None, mean_ci=boot(d, np.mean, rng),
                median=float(np.median(d)) if d else None, median_ci=boot(d, np.median, rng),
                earlier_32B=sum(x < 0 for x in d), same=sum(x == 0 for x in d), later_32B=sum(x > 0 for x in d))


def who_first(R, pos, big, small):
    out = collections.Counter()
    for c in pos:
        a = R[big].get(c)
        b = R[small].get(c)
        if a is None and b is None:
            out["neither"] += 1
        elif b is None or (a is not None and a < b):
            out["32B_first"] += 1
        elif a is None or b < a:
            out["4B_first"] += 1
        else:
            out["tie"] += 1
    return dict(out)


# ======================= Parts F and G (ADDED after E5's per-clip results were seen) =======================
def part_f(labels, trace, clips, rng):
    """TTA at a fixed false-positive rate per decision second (q = 0.10, 0.01), cross-fitted by clip."""
    from sklearn.model_selection import StratifiedKFold
    pos = [c for c in clips if labels[c]["label"] == "positive"]
    y = [labels[c]["label"] == "positive" for c in clips]
    folds = [([clips[i] for i in tr], [clips[i] for i in te])
             for tr, te in StratifiedKFold(2, shuffle=True, random_state=SEED).split(np.zeros(len(clips)), y)]
    out = dict(note="q per decision second: q = 0.10 -> 360 false alarms per hour, q = 0.01 -> 36 per hour at one "
                    "decision per second (E1's targets were 1-20 per hour)", arms={}, paired={})
    tta = {}
    for q in (0.10, 0.01):
        for a in ARMS:
            ach_n = ach_d = 0
            thr_used = []
            res_c = {}
            for tr, te in folds:
                negs = np.sort(np.asarray([trace[a][c][t][0] for c in tr if labels[c]["label"] == "negative" for t in trace[a][c]]))[::-1]
                # lowest threshold with training fraction >= thr <= q
                vals = np.unique(negs)[::-1]
                thr = np.nextafter(vals[0], np.inf)
                for v in vals:
                    if np.mean(negs >= v) <= q:
                        thr = v
                    else:
                        break
                thr_used.append(float(thr))
                te_neg = [trace[a][c][t][0] for c in te if labels[c]["label"] == "negative" for t in trace[a][c]]
                ach_n += sum(x >= thr for x in te_neg)
                ach_d += len(te_neg)
                for c in te:
                    if labels[c]["label"] != "positive":
                        continue
                    ev = labels[c]["time_of_event"]
                    first = next((t for t in sorted(trace[a][c]) if ev - 5 <= t <= ev and trace[a][c][t][0] >= thr), None)
                    res_c[c] = None if first is None else ev - first
            tta[(q, a)] = res_c
            v = [x for x in res_c.values() if x is not None]
            out["arms"][f"q{q}/{a}"] = dict(thresholds=thr_used, heldout_q=ach_n / ach_d, recall=len(v) / len(pos),
                                             recall_ci=boot([res_c[c] is not None for c in pos], np.mean, rng),
                                             mean_tta=float(np.mean(v)) if v else None, mean_ci=boot(v, np.mean, rng),
                                             median_tta=float(np.median(v)) if v else None, median_ci=boot(v, np.median, rng),
                                             n_anticipated=len(v))
        for big, small in PAIRS:
            A, Bm = tta[(q, big)], tta[(q, small)]
            both = [c for c in pos if A[c] is not None and Bm[c] is not None]
            d = [A[c] - Bm[c] for c in both]                     # positive = 32B earlier
            comp = [(A[c] or 0.0) - (Bm[c] or 0.0) for c in pos]
            out["paired"][f"q{q}/{big}-{small}"] = dict(
                both=len(both), only_32B=sum(A[c] is not None and Bm[c] is None for c in pos),
                only_4B=sum(A[c] is None and Bm[c] is not None for c in pos),
                neither=sum(A[c] is None and Bm[c] is None for c in pos),
                mean=float(np.mean(d)) if d else None, mean_ci=boot(d, np.mean, rng),
                median=float(np.median(d)) if d else None, median_ci=boot(d, np.median, rng),
                earlier_32B=sum(x > 0 for x in d), same=sum(x == 0 for x in d), later_32B=sum(x < 0 for x in d),
                composite_mean_all150=float(np.mean(comp)), composite_ci=boot(comp, np.mean, rng))
    return out


def _ap(y, s):
    from sklearn.metrics import average_precision_score
    return float(average_precision_score(y, s))


def part_g(labels, trace, clips, rng):
    """AP and AUROC at fixed horizons before the event (positives: whole-second t nearest event - h)."""
    pos = [c for c in clips if labels[c]["label"] == "positive"]
    neg = [c for c in clips if labels[c]["label"] == "negative"]
    out = dict(note="D14 decisions are 1 s apart: horizons below 1 s are approximate (nearest whole second); "
                    "validation traces only, not the Nexar challenge's own test clips. Bootstrap resamples positive "
                    "and negative clips (stratified by label) jointly for every arm.", horizons={}, paired={})
    negS = {a: [np.asarray([trace[a][c][t][0] for t in sorted(trace[a][c])]) for c in neg] for a in ARMS}
    for h in (0.0, 0.5, 1.0, 1.5, 2.0):
        posS, moved, clamped = {a: [] for a in ARMS}, 0, 0
        for c in pos:
            target = labels[c]["time_of_event"] - h
            grid = sorted(trace[ARMS[0]][c])
            t = int(round(target))
            if t < grid[0] or t > grid[-1]:
                clamped += 1
            t = min(max(t, grid[0]), grid[-1])
            moved += abs(t - target) > 0.25
            for a in ARMS:
                posS[a].append(trace[a][c][t][0])
        pt = {a: np.asarray(posS[a]) for a in ARMS}
        def metrics(pi, ni):
            m = {}
            for a in ARMS:
                p = pt[a][pi]
                n = np.concatenate([negS[a][j] for j in ni])
                yy = np.r_[np.ones(len(p)), np.zeros(len(n))]
                ss = np.r_[p, n]
                m[a] = (_ap(yy, ss), auroc(p, n))
            return m
        full = metrics(np.arange(len(pos)), np.arange(len(neg)))
        bs = []
        for _ in range(NB):
            bs.append(metrics(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg))))
        ci = lambda xs: [float(np.percentile(xs, 2.5)), float(np.percentile(xs, 97.5))]
        out["horizons"][str(h)] = dict(
            n_pos=len(pos), n_neg_seconds=int(sum(len(x) for x in negS[ARMS[0]])), rounding_moved_gt_025s=int(moved),
            clamped_to_grid=int(clamped), base_rate=len(pos) / (len(pos) + sum(len(x) for x in negS[ARMS[0]])),
            arms={a: dict(ap=full[a][0], ap_ci=ci([b[a][0] for b in bs]), auroc=full[a][1], auroc_ci=ci([b[a][1] for b in bs]))
                  for a in ARMS})
        for big, small in PAIRS:
            out["paired"][f"h{h}/{big}-{small}"] = dict(
                ap_diff=full[big][0] - full[small][0], ap_diff_ci=ci([b[big][0] - b[small][0] for b in bs]),
                auroc_diff=full[big][1] - full[small][1], auroc_diff_ci=ci([b[big][1] - b[small][1] for b in bs]))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    labels, trace, clips, n_grey = load()
    rng = np.random.default_rng(SEED)
    pos = [c for c in clips if labels[c]["label"] == "positive"]
    neg = [c for c in clips if labels[c]["label"] == "negative"]
    res = dict(label="OFFLINE ANALYSIS OF EXISTING SCORES (StudyD14-trace validation traces); no new inference",
               at=datetime.now().isoformat(), checks={})
    # ---- sanity: D14 event-time AUROCs
    d14 = json.loads((D14 / "d14_results_h100nvl.json").read_text())
    rep = {}
    for a in ARMS:
        P = [trace[a][c][min(max(int(round(labels[c]["time_of_event"])), min(trace[a][c])), max(trace[a][c]))][0] for c in pos]
        N = [trace[a][c][t][0] for c in neg for t in trace[a][c]]
        ours = auroc(np.asarray(P), np.asarray(N))
        ref = d14["arms"][a]["b_auroc_event_nearest_t"]["auroc"]
        rep[a] = dict(ours=ours, d14=ref, abs_diff=abs(ours - ref))
    res["checks"]["d14_auroc"] = rep
    res["checks"]["grey_rows"] = n_grey
    res["checks"]["positives_with_time_of_event"] = sum(labels[c]["time_of_event"] is not None for c in pos)
    res["checks"]["n_pos_neg"] = [len(pos), len(neg)]
    if any(v["abs_diff"] > 0.002 for v in rep.values()) or n_grey or res["checks"]["positives_with_time_of_event"] != len(pos):
        (OUT / "e5_results.json").write_text(json.dumps(res, indent=1, default=float))
        raise SystemExit("SANITY CHECK FAILED — stop and ask")
    ref, rcheck = assign_refs(labels, clips)
    res["reference_times"] = rcheck
    res["checks"]["positives_short_baseline_r_minus5_lt_8"] = sorted(c for c in pos if ref[c] - 5 < 8)
    # ---- baselines
    base = {a: {} for a in ARMS}
    excl = {}
    for a in ARMS:
        for c in clips:
            base[a][c] = baseline(trace[a][c], ref[c])
        ex_p = sum(base[a][c] is None for c in pos)
        ex_n = sum(base[a][c] is None for c in neg)
        dvals = [base[a][c][1] for c in clips if base[a][c] is not None]
        excl[a] = dict(excluded_pos=ex_p, excluded_neg=ex_n, frac_excluded=(ex_p + ex_n) / len(clips),
                       floor_applied=sum(base[a][c][1] < FLOOR_D for c in clips if base[a][c] is not None),
                       n_valid=sum(base[a][c] is not None for c in clips),
                       d_raw_quantiles=[float(x) for x in np.percentile(dvals, [5, 25, 50, 75, 95])],
                       baseline_seconds_median=float(np.median([base[a][c][3] for c in clips if base[a][c] is not None])))
    res["baselines"] = excl
    if any(v["frac_excluded"] > 0.20 for v in excl.values()):
        (OUT / "e5_results.json").write_text(json.dumps(res, indent=1, default=float))
        raise SystemExit("more than 20 % of clips lack a valid baseline in some arm — stop and ask")
    # ---- rise times per rule
    rise = {}
    for rule, (k, cons) in RULES.items():
        for a in ARMS:
            rise[(rule, a)] = {c: rise_time(trace[a][c], ref[c], base[a][c][0], base[a][c][2], k, cons)
                               for c in clips if base[a][c] is not None}
    per_arm = {}
    for rule in RULES:
        for a in ARMS:
            R = rise[(rule, a)]
            pv = [c for c in pos if c in R]
            nv = [c for c in neg if c in R]
            rp = [R[c] for c in pv if R[c] is not None]
            ra = [R[c] + ref[c] - labels[c]["time_of_alert"] for c in pv if R[c] is not None]
            rn = [R[c] for c in nv if R[c] is not None]
            per_arm[f"{rule}/{a}"] = dict(n_pos_valid=len(pv), n_neg_valid=len(nv),
                                          pos_rise_frac=len(rp) / len(pv), pos_rise_rel_event=q3(rp),
                                          pos_rise_rel_alert=q3(ra),
                                          false_rise_rate=len(rn) / len(nv), neg_rise_rel_ref=q3(rn))
    res["per_arm"] = per_arm
    paired, wf, fair = {}, {}, {}
    for rule in RULES:
        R = {a: rise[(rule, a)] for a in ARMS}
        for big, small in PAIRS:
            key = f"{rule}/{big}-{small}"
            paired[key] = paired_table(R, pos, big, small, rng)
            wf[key] = who_first(R, pos, big, small)
            fb, fs = per_arm[f"{rule}/{big}"]["false_rise_rate"], per_arm[f"{rule}/{small}"]["false_rise_rate"]
            ratio = (max(fb, fs) / min(fb, fs)) if min(fb, fs) > 0 else (float("inf") if max(fb, fs) > 0 else 1.0)
            fair[key] = dict(false_rise_32B=fb, false_rise_4B=fs, ratio=ratio, fair=ratio <= 2.0)
    res["paired"], res["who_first"], res["fairness"] = paired, wf, fair
    # ---- matched false-rise rates (secondary): k per model for 10 % false rise, cross-fitted on negatives
    from sklearn.model_selection import KFold
    negs = sorted(neg)
    kf = KFold(2, shuffle=True, random_state=SEED)
    folds = [([negs[i] for i in tr], [negs[i] for i in te]) for tr, te in kf.split(negs)]
    kgrid = np.round(np.arange(0.5, 15.0001, 0.05), 3)
    matched_rise, matched_info = {a: {} for a in ARMS}, {}
    for a in ARMS:
        info = []
        held_n, held_r = 0, 0
        for fi, (tr, te) in enumerate(folds):
            trv = [c for c in tr if base[a][c] is not None]
            rates = {k: np.mean([rise_time(trace[a][c], ref[c], base[a][c][0], base[a][c][2], k, 1) is not None for c in trv])
                     for k in kgrid}
            kstar = float(min((k for k in kgrid if rates[k] <= 0.10), default=kgrid[-1]))
            tev = [c for c in te if base[a][c] is not None]
            rr = [rise_time(trace[a][c], ref[c], base[a][c][0], base[a][c][2], kstar, 1) is not None for c in tev]
            held_n += len(tev)
            held_r += sum(rr)
            # positives are evaluated with the k fitted on this fold for half of them (alternating by fold)
            info.append(dict(fold=fi, k=kstar, train_rate=float(rates[kstar]), heldout_rate=float(np.mean(rr))))
        matched_info[a] = dict(folds=info, heldout_false_rise_pooled=held_r / held_n)
        # positives: each positive is assigned to a fold (stratified by order) and uses the other fold's k
        kp = KFold(2, shuffle=True, random_state=SEED)
        ps = sorted(pos)
        for fi, (_, te) in enumerate(kp.split(ps)):
            k_use = info[1 - fi]["k"]
            for i in te:
                c = ps[i]
                if base[a][c] is not None:
                    matched_rise[a][c] = rise_time(trace[a][c], ref[c], base[a][c][0], base[a][c][2], k_use, 1)
    res["matched"] = dict(k_and_rates=matched_info,
                          per_arm={a: dict(pos_rise_frac=float(np.mean([v is not None for v in matched_rise[a].values()])),
                                           pos_rise_rel_event=q3([v for v in matched_rise[a].values() if v is not None]))
                                   for a in ARMS},
                          paired={f"{b}-{s}": paired_table(matched_rise, pos, b, s, rng) for b, s in PAIRS},
                          who_first={f"{b}-{s}": who_first(matched_rise, pos, b, s) for b, s in PAIRS},
                          note=("k per model fitted on one half of the negatives for a 10 % false-rise rate and "
                                "evaluated on the other half (swapped, pooled); each positive uses the k fitted on "
                                "the negative fold opposite to its own positive fold (2 folds by clip, seed 0)"))
    # ---- references
    fy = {a: {c: first_yes(trace[a][c], ref[c]) for c in clips} for a in ARMS}
    res["ref_first_yes"] = dict(
        label="REFERENCE ONLY: biased by each model's willingness to say Yes",
        per_arm={a: dict(pos_frac=float(np.mean([fy[a][c] is not None for c in pos])),
                         pos_rel_event=q3([fy[a][c] for c in pos if fy[a][c] is not None]),
                         neg_frac=float(np.mean([fy[a][c] is not None for c in neg])),
                         raw_yes_rate_negative_seconds=float(np.mean([trace[a][c][t][1] > 0.5 for c in neg for t in trace[a][c]])))
                 for a in ARMS},
        paired={f"{b}-{s}": paired_table(fy, pos, b, s, rng) for b, s in PAIRS})
    curve = {}
    for a in ARMS:
        N = np.asarray([trace[a][c][t][0] for c in neg for t in trace[a][c]])
        cc = {}
        for k in range(-3, 2):
            P = []
            for c in pos:
                t = int(round(labels[c]["time_of_event"])) + k
                t = min(max(t, min(trace[a][c])), max(trace[a][c]))
                P.append(trace[a][c][t][0])
            cc[k] = auroc(np.asarray(P), N)
        curve[a] = cc
    res["ref_auroc_by_offset"] = dict(label="REFERENCE ONLY (D14 definition, clamped to the clip grid)", curve=curve)
    res["partF_tta_fixed_fpr"] = dict(label="ADDED after E5's per-clip results were seen; field convention (TTA at fixed FPR)",
                                      **part_f(labels, trace, clips, np.random.default_rng(SEED)))
    res["partG_ap_horizons"] = dict(label="ADDED after E5's per-clip results were seen; Nexar-challenge-style AP at fixed horizons",
                                    **part_g(labels, trace, clips, np.random.default_rng(SEED)))
    res["_provenance"] = stamp(script="study_e5_nexar_rise.py", model="4BI,32BI (scores)", device="cpu", n=len(clips))
    (OUT / "e5_results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res["checks"], default=float)[:1500])
    print(json.dumps(res["baselines"], default=float)[:2000])


if __name__ == "__main__":
    main()
