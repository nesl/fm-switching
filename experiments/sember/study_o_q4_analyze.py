#!/usr/bin/env python3
"""Study O Q4 — escalation-policy evaluation (plan §7).

Primary test: acc(policy d, predictor top-e) - acc(policy c, random at rate e)
at e=0.2, paired bootstrap clustered by video_id (2000 resamples).
Plus gap_closed_accuracy = (acc_d - acc_c)/(acc_f - acc_c), and the K4 verdict.

The P4 predictor (N2: all-MiniLM-L6-v2 embedding + log(1+qt)) is retrained with
ALL Study O video_ids removed from the training set, per plan §7.
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path("/home/pragya/Desktop/FM-switching")
TRIALS = ROOT / "results/sember/study_o/study_o_q4_trials.jsonl"  # --fa2 redirects this
GROUNDING = ROOT / "results/sember/study_h/data/sember_grounding.jsonl"
SEED = 42
L = 120.0           # N2 primary cell
E_GRID = (0.1, 0.2, 0.3)
E_PRIMARY = 0.2
NBOOT = 2000
EMBED_MODEL_ID = "all-MiniLM-L6-v2"


def load_trials():
    ts = [json.loads(l) for l in open(TRIALS)]
    by = defaultdict(dict)
    for t in ts:
        by[t["model_arm"]][t["question_id"]] = t
    return by


def train_p4(study_o_vids):
    """N2 P4 retrained on S-EMBER with Study O videos EXCLUDED from training."""
    from sentence_transformers import SentenceTransformer
    rows = []
    for l in open(GROUNDING):
        r = json.loads(l)
        if r.get("answer_start_time") is None:
            continue
        qt = float(r["question_time"])
        far = qt - min(float(r["answer_start_time"]), float(r["answer_end_time"]))
        if far < 0:
            continue
        rows.append({"qid": r["question_id"], "vid": r["video_id"],
                     "question": r["question"], "qt": qt, "far": far})

    train = [r for r in rows if r["vid"] not in study_o_vids]
    print(f"  P4 training rows: {len(train)} "
          f"(excluded {len(rows)-len(train)} on {len(study_o_vids)} Study O videos)")
    assert not ({r["vid"] for r in train} & study_o_vids), "Study O leakage into P4 training"

    m = SentenceTransformer(EMBED_MODEL_ID)
    Etr = m.encode([r["question"] for r in train], batch_size=256,
                   show_progress_bar=False)
    Xtr = np.hstack([Etr, np.array([[math.log(1 + r["qt"])] for r in train])])
    ytr = np.array([int(r["far"] > L) for r in train])
    sc = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=1000).fit(sc.transform(Xtr), ytr)
    print(f"  P4 trained; P(needs_escalation) base rate = {ytr.mean():.3f}")
    return m, sc, clf


def policy_acc(loc, rem, escalate_mask):
    """End-to-end accuracy: local where not escalated, remote where escalated."""
    return float(np.mean(np.where(escalate_mask, rem, loc)))


def top_e_mask(score, e):
    n = len(score)
    k = int(round(e * n))
    m = np.zeros(n, dtype=bool)
    if k > 0:
        m[np.argsort(-score)[:k]] = True
    return m


def oracle_acc_mask(loc, rem, e):
    """Policy (f): escalate the e-fraction where remote right and local wrong."""
    n = len(loc)
    k = int(round(e * n))
    gain = rem.astype(int) - loc.astype(int)   # +1 only where remote rescues
    m = np.zeros(n, dtype=bool)
    if k > 0:
        m[np.argsort(-gain, kind="stable")[:k]] = True
    return m


def clustered_bootstrap(vids, fn, nboot=NBOOT, seed=SEED):
    """Resample VIDEOS with replacement; recompute fn on the resampled rows."""
    rng = np.random.default_rng(seed)
    uv = np.unique(vids)
    idx_by_v = {v: np.where(vids == v)[0] for v in uv}
    out = []
    for _ in range(nboot):
        pick = rng.choice(uv, size=len(uv), replace=True)
        idx = np.concatenate([idx_by_v[v] for v in pick])
        out.append(fn(idx))
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fa2", action="store_true",
                    help="analyse the flash-attn / 845-pool trials instead of the committed 520-pool file")
    args = ap.parse_args()
    global TRIALS
    if args.fa2:
        TRIALS = ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
    print(f"trials: {TRIALS.name}")
    by = load_trials()
    have_T = len(by.get("4B-T", {}))
    print(f"cells: 4B-I={len(by.get('4B-I',{}))}, 8B-I={len(by.get('8B-I',{}))}, "
          f"4B-T={have_T}")

    remotes = [("8B-I x RICH", "8B-I")]
    if have_T >= 100:
        remotes.append(("4B-T x RICH", "4B-T"))
    else:
        print(f"  (4B-T has {have_T} trials — reported separately when complete)")

    for label, rkey in remotes:
        qids = sorted(set(by["4B-I"]) & set(by[rkey]))
        print("\n" + "=" * 72)
        print(f"REMOTE CONFIGURATION: {label}   (paired n = {len(qids)})")
        print("=" * 72)

        loc = np.array([by["4B-I"][q]["correct"] for q in qids])
        rem = np.array([by[rkey][q]["correct"] for q in qids])
        vids = np.array([by["4B-I"][q]["video_id"] for q in qids])
        qt = np.array([by["4B-I"][q]["question_time"] for q in qids])
        far = np.array([by["4B-I"][q]["farthest"] for q in qids])

        print(f"local  (4B-I x RECENT) acc = {loc.mean()*100:.2f}%")
        print(f"remote ({label})       acc = {rem.mean()*100:.2f}%")
        b = int(((~loc) & rem).sum()); c = int((loc & (~rem)).sum())
        print(f"discordance: remote-rescues b={b} ({b/len(qids)*100:.1f}%), "
              f"remote-breaks c={c} ({c/len(qids)*100:.1f}%), "
              f"net {((b-c)/len(qids))*100:+.2f}pp")

        study_o_vids = set(vids.tolist())
        m, sc, clf = train_p4(study_o_vids)
        # question text is not stored in the trial rows; pull it from grounding
        qtext = {}
        for l in open(GROUNDING):
            r = json.loads(l)
            qtext[r["question_id"]] = r["question"]
        E = m.encode([qtext[q] for q in qids], batch_size=256,
                     show_progress_bar=False)
        X = np.hstack([E, np.log1p(qt).reshape(-1, 1)])
        p_need = clf.predict_proba(sc.transform(X))[:, 1]

        p_far = float((far > L).mean())
        print(f"\nP(farthest > {L:.0f}s) in Study O = {p_far*100:.1f}%")

        print(f"\n{'e':>5} {'(a)never':>9} {'(b)always':>10} {'(c)random':>10} "
              f"{'(d)pred':>9} {'(e)oracle-d':>12} {'(f)acc-oracle':>14} "
              f"{'d-c':>8} {'gap_closed':>11}")
        results = {}
        for e in E_GRID:
            acc_a = float(loc.mean())
            acc_b = float(rem.mean())
            acc_c = (1 - e) * acc_a + e * acc_b        # analytic random
            acc_d = policy_acc(loc, rem, top_e_mask(p_need, e))
            acc_e = policy_acc(loc, rem, top_e_mask(far, e))
            acc_f = policy_acc(loc, rem, oracle_acc_mask(loc, rem, e))
            gap = (acc_d - acc_c) / (acc_f - acc_c) if acc_f > acc_c else float("nan")
            results[e] = (acc_a, acc_b, acc_c, acc_d, acc_e, acc_f, gap)
            print(f"{e:>5.1f} {acc_a*100:>8.2f}% {acc_b*100:>9.2f}% "
                  f"{acc_c*100:>9.2f}% {acc_d*100:>8.2f}% {acc_e*100:>11.2f}% "
                  f"{acc_f*100:>13.2f}% {(acc_d-acc_c)*100:>+7.2f}pp "
                  f"{gap*100:>10.1f}%")

        # ---- primary test at e = 0.2, clustered bootstrap ----
        e = E_PRIMARY

        def stat(idx):
            l_, r_, p_ = loc[idx], rem[idx], p_need[idx]
            a_ = float(l_.mean()); b_ = float(r_.mean())
            c_ = (1 - e) * a_ + e * b_
            d_ = policy_acc(l_, r_, top_e_mask(p_, e))
            return d_ - c_

        boot = clustered_bootstrap(vids, stat)
        obs = stat(np.arange(len(qids)))
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"\nPRIMARY (e={e}): acc(d) - acc(c) = {obs*100:+.2f}pp")
        print(f"  clustered bootstrap 95% CI [{lo*100:+.2f}, {hi*100:+.2f}]pp "
              f"({NBOOT} resamples, clustered by video_id, "
              f"{len(np.unique(vids))} videos)")
        print(f"  CI excludes 0: {'YES' if (lo > 0 or hi < 0) else 'NO'}")

        acc_f = results[e][5]; acc_c = results[e][2]
        print(f"  gap_closed_accuracy = {results[e][6]*100:.1f}% "
              f"(acc_f - acc_c = {(acc_f-acc_c)*100:+.2f}pp headroom)")

        k4 = (abs(obs) < 0.01) and (lo <= 0 <= hi)
        print(f"\nK4: {'FIRES' if k4 else 'does not fire'} "
              f"— rule: (d)-(c) < 1pp AND CI includes 0")
        if k4:
            if abs(acc_b - acc_a) < 0.02:
                print("  reason (i): local and remote accuracy are too similar "
                      f"({acc_a*100:.2f}% vs {acc_b*100:.2f}%) — model routing "
                      "does not matter")
            else:
                print("  reason (ii): the predictor's coverage ranking does not "
                      "correlate with local-vs-remote accuracy differences")


if __name__ == "__main__":
    main()
