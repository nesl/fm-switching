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



# ---------------------------------------------------------------------------
# External-audit sections (added 2026-10-17). These do NOT replace the
# pre-registered K4 test above; they sit alongside it. All CIs here use
# seed 0 and 2,000 video-clustered resamples, per the audit specification.
# ---------------------------------------------------------------------------
AUDIT_SEED = 0


def auroc(y, s):
    """Rank-based AUROC with tie correction (Mann-Whitney U)."""
    y = np.asarray(y).astype(bool)
    s = np.asarray(s, dtype=float)
    npos, nneg = int(y.sum()), int((~y).sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    sorted_s = s[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and sorted_s[j + 1] == sorted_s[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return (ranks[y].sum() - npos * (npos + 1) / 2.0) / (npos * nneg)


def audit_interaction(loc, rem, vids, covered, far, label):
    """(a) Local/remote accuracy split by a binary stratifier, plus the DiD."""
    print("\n" + "-" * 72)
    print(f"AUDIT (a) INTERACTION — {label}")
    print("-" * 72)
    for sname, strat in (("evidence_covered (local arm flag)", covered),
                         (f"farthest > {L:.0f}s", far > L)):
        # group A = stratifier False (uncovered / near), group B = True
        print(f"\n  split: {sname}")
        cells = {}
        for gname, g in ((f"{sname} = False", ~strat), (f"{sname} = True", strat)):
            if g.sum() == 0:
                print(f"    {gname:38s} n=0 — empty stratum, DiD undefined")
                cells[bool(gname.endswith('True'))] = None
                continue
            la, ra = float(loc[g].mean()), float(rem[g].mean())
            cells[gname.endswith("True")] = (int(g.sum()), la, ra)
            print(f"    {gname:38s} n={int(g.sum()):4d}  local {la*100:5.1f}%  "
                  f"remote {ra*100:5.1f}%  gain {(ra-la)*100:+6.1f}pp")
        if cells.get(False) is None or cells.get(True) is None:
            continue

        def did(idx):
            g = strat[idx]
            if g.sum() == 0 or (~g).sum() == 0:
                return np.nan
            gain_f = rem[idx][~g].mean() - loc[idx][~g].mean()
            gain_t = rem[idx][g].mean() - loc[idx][g].mean()
            return float(gain_f - gain_t)

        obs = did(np.arange(len(loc)))
        boot = clustered_bootstrap(vids, did, nboot=NBOOT, seed=AUDIT_SEED)
        boot = boot[~np.isnan(boot)]
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"    DiD (gain where False - gain where True) = {obs*100:+.1f}pp")
        print(f"      95% CI [{lo*100:+.1f}, {hi*100:+.1f}]pp "
              f"({len(boot)} usable resamples, clustered by video, seed {AUDIT_SEED})")
        print(f"      CI excludes 0: {'YES' if (lo > 0 or hi < 0) else 'NO'}")


def audit_evidence_oracle(loc, rem, vids, far, label):
    """(b) Evidence-distance oracle (policy e) vs random (policy c), paired."""
    print("\n" + "-" * 72)
    print(f"AUDIT (b) EVIDENCE-DISTANCE ORACLE vs RANDOM — {label}")
    print("-" * 72)
    for e in E_GRID:
        def stat(idx, e=e):
            l_, r_, f_ = loc[idx], rem[idx], far[idx]
            a_ = float(l_.mean()); b_ = float(r_.mean())
            c_ = (1 - e) * a_ + e * b_
            return policy_acc(l_, r_, top_e_mask(f_, e)) - c_
        obs = stat(np.arange(len(loc)))
        boot = clustered_bootstrap(vids, stat, nboot=NBOOT, seed=AUDIT_SEED)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"  e={e:.1f}  (e)oracle-d - (c)random = {obs*100:+.2f}pp  "
              f"95% CI [{lo*100:+.2f}, {hi*100:+.2f}]pp  "
              f"excludes 0: {'YES' if (lo > 0 or hi < 0) else 'NO'}")


def audit_auroc_and_mde(p_need, qt, far, loc, rem, vids, label):
    """(c) Predictor AUROC on Study O, question_time alone, and the MDE."""
    print("\n" + "-" * 72)
    print(f"AUDIT (c) PREDICTOR AUROC AND MINIMUM DETECTABLE EFFECT — {label}")
    print("-" * 72)
    y = (far > L)
    a_p4 = auroc(y, p_need)
    a_qt = auroc(y, qt)
    print(f"  target: farthest > {L:.0f}s   (base rate {y.mean()*100:.1f}%, n={len(y)})")
    print(f"  AUROC, P4 predictor on Study O questions : {a_p4:.3f}")
    print(f"  AUROC, question_time alone               : {a_qt:.3f}")
    print(f"  N2 reported OOF AUROC                    : 0.766")
    print(f"  -> P4 on Study O is {a_p4-0.766:+.3f} vs the N2 figure; "
          f"the log(1+qt) feature alone reaches {a_qt:.3f}")

    e = E_PRIMARY

    def stat(idx):
        l_, r_, p_ = loc[idx], rem[idx], p_need[idx]
        a_ = float(l_.mean()); b_ = float(r_.mean())
        c_ = (1 - e) * a_ + e * b_
        return policy_acc(l_, r_, top_e_mask(p_, e)) - c_

    boot = clustered_bootstrap(vids, stat, nboot=NBOOT, seed=AUDIT_SEED)
    se = float(boot.std(ddof=1))
    mde = 2.802 * se      # 80% power, two-sided alpha = 0.05
    obs = stat(np.arange(len(loc)))
    print(f"\n  predictor vs random at e={e}: observed {obs*100:+.2f}pp, "
          f"bootstrap SE {se*100:.2f}pp")
    print(f"  minimum detectable effect (80% power, two-sided alpha=0.05) "
          f"= {mde*100:.2f}pp")
    print(f"  the K4 threshold is 1.00pp, which is {1.0/(mde*100):.2f}x the MDE "
          f"-> a true effect at the K4 threshold would be detected "
          f"{'reliably' if mde*100 < 1.0 else 'LESS THAN 80% of the time'}")


def audit_flip_rate():
    """(d) Correctness flip rate between the two 4B-T runs on shared questions."""
    print("\n" + "-" * 72)
    print("AUDIT (d) 4B-T RUN-TO-RUN FLIP RATE (accuracy-oracle noise floor)")
    print("-" * 72)
    f520 = ROOT / "results/sember/study_o/study_o_q4_trials.jsonl"
    f845 = ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
    if not (f520.exists() and f845.exists()):
        print("  one of the two trial files is missing — skipped")
        return
    def load(f):
        d = {}
        for l in open(f):
            r = json.loads(l)
            if r["model_arm"] == "4B-T":
                d[r["question_id"]] = bool(r["correct"])
        return d
    a, b = load(f520), load(f845)
    shared = sorted(set(a) & set(b))
    av = np.array([a[q] for q in shared])
    bv = np.array([b[q] for q in shared])
    flips = int((av != bv).sum())
    b_ = int(((~av) & bv).sum()); c_ = int((av & (~bv)).sum())
    print(f"  shared questions: {len(shared)}")
    print(f"  run A (520 pool, SDPA)  accuracy = {av.mean()*100:.2f}%")
    print(f"  run B (845 pool, FA2)   accuracy = {bv.mean()*100:.2f}%")
    print(f"  flips: {flips}/{len(shared)} = {flips/len(shared)*100:.1f}%  "
          f"(B-rescues {b_}, B-breaks {c_}, net {(b_-c_)/len(shared)*100:+.2f}pp)")
    print(f"  NOTE: the two runs differ in pool AND backend, so this is an upper")
    print(f"        bound on per-attempt stochasticity, not a clean seed replicate.")
    print(f"  -> any accuracy-oracle headroom below ~{flips/len(shared)*100:.1f}pp is")
    print(f"     within the run-to-run flip rate of a single sampled arm.")


# ---------------------------------------------------------------------------
# Part 2 (2026-10-17): the separating cell, 4B-I x RICH.
# Pre-registered in research/EXPERIMENTS.md as StudyO-q4-sep BEFORE the run.
# Decision rules are fixed there and are applied verbatim below.
# ---------------------------------------------------------------------------
SEP_TRIALS = ROOT / "results/sember/study_o/study_o_q4_trials_4bi_rich_fa2.jsonl"


def wilson(k, n, z=1.959963985):
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def did_with_ci(a_lo, a_hi, strat, vids, nboot=NBOOT, seed=AUDIT_SEED):
    """DiD of (a_hi - a_lo) between strat=False and strat=True, clustered CI."""
    def fn(idx):
        g = strat[idx]
        if g.sum() == 0 or (~g).sum() == 0:
            return np.nan
        gf = a_hi[idx][~g].mean() - a_lo[idx][~g].mean()
        gt = a_hi[idx][g].mean() - a_lo[idx][g].mean()
        return float(gf - gt)
    obs = fn(np.arange(len(a_lo)))
    boot = clustered_bootstrap(vids, fn, nboot=nboot, seed=seed)
    boot = boot[~np.isnan(boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return obs, lo, hi, float(boot.std(ddof=1))


def run_separating():
    print("=" * 72)
    print("PART 2 — THE SEPARATING CELL (4B-I x RICH)")
    print("pre-registered as StudyO-q4-sep in research/EXPERIMENTS.md before the run")
    print("=" * 72)
    if not SEP_TRIALS.exists():
        print(f"  {SEP_TRIALS} not found — run the cell first."); return

    main_rows = [json.loads(l) for l in
                 open(ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl")]
    by = defaultdict(dict)
    for r in main_rows:
        by[r["model_arm"]][r["question_id"]] = r
    sep = {}
    for l in open(SEP_TRIALS):
        r = json.loads(l)
        assert r["model_arm"] == "4B-I" and r["state_arm"] == "RICH", r["question_id"]
        sep[r["question_id"]] = r
    print(f"  4B-I x RICH trials: {len(sep)}  "
          f"attn={ {r['attn_implementation'] for r in sep.values()} }")

    qids = sorted(set(by["4B-I"]) & set(by["8B-I"]) & set(sep))
    print(f"  paired on all four cells: n = {len(qids)}")

    recent4 = np.array([by["4B-I"][q]["correct"] for q in qids])
    rich4   = np.array([sep[q]["correct"] for q in qids])
    rich8   = np.array([by["8B-I"][q]["correct"] for q in qids])
    richT   = np.array([by["4B-T"][q]["correct"] for q in qids])
    vids    = np.array([by["4B-I"][q]["video_id"] for q in qids])
    covered = np.array([bool(by["4B-I"][q]["evidence_covered"]) for q in qids])
    far     = np.array([by["4B-I"][q]["farthest"] for q in qids])

    # ---- contrast 3: four-cell accuracy with Wilson CIs ----
    print("\n--- CONTRAST 3: overall accuracy, Wilson 95% CIs ---")
    for name, arr in (("4B-I x RECENT (local)", recent4), ("4B-I x RICH  (NEW)", rich4),
                      ("8B-I x RICH", rich8), ("4B-T x RICH", richT)):
        k = int(arr.sum()); n = len(arr); lo, hi = wilson(k, n)
        print(f"  {name:24s} {k:4d}/{n}  {k/n*100:5.2f}%  "
              f"Wilson [{lo*100:5.2f}, {hi*100:5.2f}]")

    # ---- contrasts 1 and 2 ----
    out = {}
    for tag, lo_arm, hi_arm, label in (
            ("C1", recent4, rich4, "STATE effect at fixed model: (4B-I x RICH) - (4B-I x RECENT)"),
            ("C2", rich4,   rich8, "MODEL effect at fixed state: (8B-I x RICH) - (4B-I x RICH)")):
        print(f"\n--- CONTRAST {tag[1]}: {label} ---")
        for sname, g in (("uncovered", ~covered), ("covered", covered)):
            lo_a, hi_a = lo_arm[g].mean(), hi_arm[g].mean()
            print(f"  {sname:10s} n={int(g.sum()):4d}  "
                  f"{lo_a*100:5.1f}% -> {hi_a*100:5.1f}%  gain {(hi_a-lo_a)*100:+6.1f}pp")
        obs, l, h, se = did_with_ci(lo_arm, hi_arm, covered, vids)
        excl = (l > 0 or h < 0)
        out[tag] = (obs, l, h, se, excl)
        print(f"  DiD (uncovered - covered) = {obs*100:+.1f}pp  "
              f"95% CI [{l*100:+.1f}, {h*100:+.1f}]pp   excludes 0: {'YES' if excl else 'NO'}")
        print(f"  bootstrap SE {se*100:.2f}pp -> MDE {2.802*se*100:.2f}pp "
              f"(80% power, two-sided alpha=0.05)")

    # ---- pre-registered decision rule ----
    c1x, c2x = out["C1"][4], out["C2"][4]
    verdict = ("STATE CARRIES IT" if (c1x and not c2x) else
               "MODEL CARRIES IT" if (c2x and not c1x) else
               "BOTH" if (c1x and c2x) else "NEITHER")
    print("\n" + "=" * 72)
    print(f"PRE-REGISTERED DECISION: **{verdict}**")
    print(f"  C1 (state) CI excludes 0: {c1x};  C2 (model) CI excludes 0: {c2x}")
    if verdict == "NEITHER":
        print(f"  MDE required by the rule — C1 {2.802*out['C1'][3]*100:.2f}pp, "
              f"C2 {2.802*out['C2'][3]*100:.2f}pp")
    print("=" * 72)

    # ---- contrast 4: escalation with 4B-I x RICH as remote ----
    print("\n--- CONTRAST 4: escalation grid, remote = 4B-I x RICH (no model change) ---")
    qt = np.array([by["4B-I"][q]["question_time"] for q in qids])
    study_o_vids = set(vids.tolist())
    m, sc, clf = train_p4(study_o_vids)
    qtext = {}
    for l in open(GROUNDING):
        r = json.loads(l)
        qtext[r["question_id"]] = r["question"]
    E = m.encode([qtext[q] for q in qids], batch_size=256, show_progress_bar=False)
    p_need = clf.predict_proba(sc.transform(
        np.hstack([E, np.log1p(qt).reshape(-1, 1)])))[:, 1]

    loc, rem = recent4, rich4
    print(f"\n{'e':>5} {'(a)never':>9} {'(b)always':>10} {'(c)random':>10} "
          f"{'(d)pred':>9} {'(e)oracle-d':>12} {'(f)acc-oracle':>14} {'d-c':>8}")
    for e in E_GRID:
        a_ = float(loc.mean()); b_ = float(rem.mean())
        c_ = (1 - e) * a_ + e * b_
        d_ = policy_acc(loc, rem, top_e_mask(p_need, e))
        eo = policy_acc(loc, rem, top_e_mask(far, e))
        f_ = policy_acc(loc, rem, oracle_acc_mask(loc, rem, e))
        print(f"{e:>5.1f} {a_*100:>8.2f}% {b_*100:>9.2f}% {c_*100:>9.2f}% "
              f"{d_*100:>8.2f}% {eo*100:>11.2f}% {f_*100:>13.2f}% {(d_-c_)*100:>+7.2f}pp")

    for pol_name, score in (("evidence oracle", far), ("P4 predictor", p_need)):
        print(f"\n  {pol_name} vs random, video-clustered CI:")
        for e in E_GRID:
            def stat(idx, e=e, score=score):
                l_, r_, s_ = loc[idx], rem[idx], score[idx]
                a2 = float(l_.mean()); b2 = float(r_.mean())
                return policy_acc(l_, r_, top_e_mask(s_, e)) - ((1 - e) * a2 + e * b2)
            obs = stat(np.arange(len(loc)))
            boot = clustered_bootstrap(vids, stat, nboot=NBOOT, seed=AUDIT_SEED)
            l2, h2 = np.percentile(boot, [2.5, 97.5])
            print(f"    e={e:.1f}  {obs*100:+.2f}pp  CI [{l2*100:+.2f}, {h2*100:+.2f}]pp  "
                  f"excludes 0: {'YES' if (l2 > 0 or h2 < 0) else 'NO'}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sep", action="store_true",
                    help="Part 2: analyse the separating cell 4B-I x RICH and stop.")
    ap.add_argument("--fa2", action="store_true",
                    help="analyse the flash-attn / 845-pool trials instead of the committed 520-pool file")
    args = ap.parse_args()
    global TRIALS
    if args.fa2:
        TRIALS = ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
    if args.sep:
        run_separating()
        return
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

        covered = np.array([bool(by["4B-I"][q]["evidence_covered"]) for q in qids])
        audit_interaction(loc, rem, vids, covered, far, label)
        audit_evidence_oracle(loc, rem, vids, far, label)
        audit_auroc_and_mde(p_need, qt, far, loc, rem, vids, label)

        acc_f = results[e][5]; acc_c = results[e][2]
        print(f"  gap_closed_accuracy = {results[e][6]*100:.1f}% "
              f"(acc_f - acc_c = {(acc_f-acc_c)*100:+.2f}pp headroom)")

        k4 = (abs(obs) < 0.01) and (lo <= 0 <= hi)
        print(f"\nK4: {'FIRES' if k4 else 'does not fire'} "
              f"— rule: (d)-(c) < 1pp AND CI includes 0")
        if k4:
            # NOTE (external audit, 2026-10-17): the reason below is selected
            # MECHANICALLY by a hard-coded 2pp threshold on |acc_b - acc_a|.
            # It is a label, not a test: no hypothesis about the predictor's
            # coverage ranking is evaluated here, and nothing distinguishes
            # reason (ii) from "the test was underpowered to tell".
            print("  [reason below is a mechanical label from a 2pp threshold, "
                  "not a statistical test — see audit sections]")
            if abs(acc_b - acc_a) < 0.02:
                print("  reason (i): local and remote accuracy are too similar "
                      f"({acc_a*100:.2f}% vs {acc_b*100:.2f}%) — model routing "
                      "does not matter")
            else:
                print("  reason (ii): the predictor's coverage ranking does not "
                      "correlate with local-vs-remote accuracy differences")

    audit_flip_rate()


if __name__ == "__main__":
    main()
