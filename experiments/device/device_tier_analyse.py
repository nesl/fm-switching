#!/usr/bin/env python3
"""Analyses A-E for the device-tier accuracy run, exactly as pre-registered.

Statistical machinery is IMPORTED from experiments/sember/study_o_q4_analyze.py
(clustered_bootstrap, policy_acc, top_e_mask, oracle_acc_mask, train_p4, wilson,
did_with_ci, auroc) so the device replication uses the same code as the Study O
result it is replicating, not a reimplementation of it.

Primary denominator for the construction contrast is the 678 questions with
question_time > 120 s. Below that, [0, qt] and [max(0, qt-120), qt] are the SAME
interval, so DEV-RICH and DEV-RECENT are byte-identical inputs and contribute an
exact zero to C2 - C1 under greedy decoding. All 845 are reported alongside.
"""
import argparse, json, math, os, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "sember"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import study_o_q4_analyze as O
import dev_inputs as DI

RES = ROOT / "results/device"
# The Orin's latency rows live in results/device/ once its commit is pulled. Until
# then ORIN_DIR can point at a copy extracted with `git show origin/main:<path>`.
ORIN_DIR = Path(os.environ.get("ORIN_DIR", RES))
E_PRIMARY = 0.2
RATES = [0.1, 0.2, 0.3, 0.5]
NBOOT = 2000
SEED = 0
MDE_K = 2.802   # 80% power, two-sided alpha=0.05


def load_cell(cell, tag=""):
    p = RES / f"accuracy_{cell}{('_' + tag) if tag else ''}.jsonl"
    if not p.exists():
        return {}
    return {t["question_id"]: t for t in map(json.loads, open(p))}


def common(cells):
    sets = [set(c) for c in cells if c]
    return sorted(set.intersection(*sets)) if sets else []


def arrays(cell, qids):
    ok = np.array([bool(cell[q]["correct"]) for q in qids])
    vid = np.array([cell[q]["video_id"] for q in qids])
    cov = np.array([bool(cell[q]["evidence_covered"]) for q in qids])
    qt = np.array([float(cell[q]["question_time"]) for q in qids])
    return ok, vid, cov, qt


def analysis_A(loaded):
    print("\n## A. Accuracy per cell (Wilson 95%)\n")
    print(f"{'cell':6} {'model':6} {'constr':8} {'n':>5} {'acc':>8} {'Wilson 95%':>18}")
    for cell, rows in loaded.items():
        if not rows:
            print(f"{cell:6} {'-':6} {'-':8} {'0':>5}   NOT RUN")
            continue
        n = len(rows); k = sum(bool(t["correct"]) for t in rows.values())
        lo, hi = O.wilson(k, n)
        p = k / n
        any_row = next(iter(rows.values()))
        print(f"{cell:6} {any_row['model']:6} {any_row['construction']:8} {n:5} "
              f"{100*p:7.1f}% [{100*lo:5.1f}, {100*hi:5.1f}]")


def analysis_B(a, b, label, restrict=None):
    """Crossover: (b - a) split by evidence_covered under DEV-RECENT, DiD with CI."""
    qids = common([a, b])
    if not qids:
        print(f"\n### B [{label}]: cells not both present\n")
        return
    if restrict is not None:
        qids = [q for q in qids if restrict(a[q])]
    ok_a, vid, cov_recent, qt = arrays(a, qids)
    ok_b = np.array([bool(b[q]["correct"]) for q in qids])

    print(f"\n### B [{label}]  n={len(qids)}")
    for name, m in (("evidence_covered=False (RECENT)", ~cov_recent),
                    ("evidence_covered=True  (RECENT)", cov_recent)):
        if m.sum() == 0:
            print(f"  {name}: n=0"); continue
        print(f"  {name}: n={m.sum():4d}  RECENT {100*ok_a[m].mean():5.1f}%  "
              f"RICH {100*ok_b[m].mean():5.1f}%  diff {100*(ok_b[m].mean()-ok_a[m].mean()):+6.2f} pp")

    def did(idx):
        c = cov_recent[idx]
        if c.sum() == 0 or (~c).sum() == 0:
            return np.nan
        return ((ok_b[idx][~c].mean() - ok_a[idx][~c].mean())
                - (ok_b[idx][c].mean() - ok_a[idx][c].mean()))
    obs = did(np.arange(len(qids)))
    boot = O.clustered_bootstrap(vid, did, nboot=NBOOT, seed=SEED)
    boot = boot[np.isfinite(boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    se = boot.std(ddof=1)
    print(f"  DiD (uncovered - covered) = {100*obs:+.2f} pp  "
          f"CI [{100*lo:+.2f}, {100*hi:+.2f}]  SE {100*se:.2f}  "
          f"MDE {100*MDE_K*se:.2f} pp")
    verdict = ("CROSSOVER REPLICATES" if lo > 0 else
               "opposite direction" if hi < 0 else
               f"INCONCLUSIVE (MDE {100*MDE_K*se:.2f} pp)")
    print(f"  -> {verdict}")


def analysis_C(a, b, label, restrict=None):
    """Selection policies choosing RECENT vs RICH per question, no remote model."""
    qids = common([a, b])
    if not qids:
        print(f"\n### C [{label}]: cells not both present\n"); return
    if restrict is not None:
        qids = [q for q in qids if restrict(a[q])]
    ok_a, vid, _, qt = arrays(a, qids)
    ok_b = np.array([bool(b[q]["correct"]) for q in qids])
    recs = DI.load_mcq()
    far = np.array([float(recs[q]["question_time"])
                    - min(float(recs[q]["answer_start_time"]),
                          float(recs[q]["answer_end_time"])) for q in qids])

    study_o_vids = {recs[q]["video_id"] for q in qids}
    m, sc, clf = O.train_p4(study_o_vids)
    E = m.encode([recs[q]["question"] for q in qids], batch_size=256, show_progress_bar=False)
    X = np.hstack([E, np.log1p(qt).reshape(-1, 1)])
    p_need = clf.predict_proba(sc.transform(X))[:, 1]

    print(f"\n### C [{label}]  n={len(qids)}   (escalate = use RICH)")
    print(f"  always-RECENT {100*ok_a.mean():5.1f}%    always-RICH {100*ok_b.mean():5.1f}%")
    rng = np.random.default_rng(SEED)
    print(f"\n  {'e':>5} {'random':>8} {'P4':>8} {'qt-only':>8} {'ev-oracle':>10} "
          f"{'acc-oracle':>10} {'P4-rand':>8}")
    for e in RATES:
        rnd = np.mean([O.policy_acc(ok_a, ok_b,
                       np.isin(np.arange(len(qids)), rng.choice(len(qids),
                               int(round(e*len(qids))), replace=False)))
                       for _ in range(200)])
        p4 = O.policy_acc(ok_a, ok_b, O.top_e_mask(p_need, e))
        qto = O.policy_acc(ok_a, ok_b, O.top_e_mask(qt, e))
        evo = O.policy_acc(ok_a, ok_b, O.top_e_mask(far, e))
        aco = O.oracle_acc_mask(ok_a, ok_b, e)
        aco = O.policy_acc(ok_a, ok_b, aco) if isinstance(aco, np.ndarray) else aco
        print(f"  {e:5.1f} {100*rnd:8.1f} {100*p4:8.1f} {100*qto:8.1f} {100*evo:10.1f} "
              f"{100*aco:10.1f} {100*(p4-rnd):+8.2f}")

    def contrast(idx):
        la, lb, pn = ok_a[idx], ok_b[idx], p_need[idx]
        n = len(idx); k = int(round(E_PRIMARY * n))
        mask = np.zeros(n, bool); mask[np.argsort(-pn)[:k]] = True
        rndm = np.zeros(n, bool); rndm[:k] = True
        np.random.default_rng(SEED).shuffle(rndm)
        return O.policy_acc(la, lb, mask) - O.policy_acc(la, lb, rndm)
    obs = contrast(np.arange(len(qids)))
    boot = O.clustered_bootstrap(vid, contrast, nboot=NBOOT, seed=SEED)
    boot = boot[np.isfinite(boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5]); se = boot.std(ddof=1)
    print(f"\n  PRIMARY: P4 - random at e={E_PRIMARY}: {100*obs:+.2f} pp "
          f"CI [{100*lo:+.2f}, {100*hi:+.2f}]  MDE {100*MDE_K*se:.2f} pp")
    print(f"  -> {'SELECTION SIGNAL' if (lo>0 or hi<0) else 'INCONCLUSIVE (underpowered)'}")


def analysis_E(c1, c3):
    """Cross-machine: C1 vs the Orin's 4B-I F16; C3 vs the Orin's 4B-T F16."""
    print("\n## E. Cross-machine check against the Orin\n")
    for cell, rows, orin_file, lab in (
            ("C1", c1, "latency_sember_4bi_f16_F16.jsonl", "4B-Instruct F16"),
            ("C3", c3, "latency_sember_4bt_f16_F16.jsonl", "4B-Thinking F16")):
        p = ORIN_DIR / orin_file
        if not p.exists() or not rows:
            print(f"  {cell} vs Orin {lab}: not available "
                  f"({'orin file missing' if not p.exists() else 'cell not run'})")
            continue
        orin = {t["question_id"]: t for t in map(json.loads, open(p))}
        both = [q for q in orin if q in rows]
        if not both:
            print(f"  {cell}: no overlap with the Orin sample"); continue
        tok = sum(rows[q]["n_input_tokens"] == orin[q]["input_tokens"] for q in both)
        pm = sum(rows[q]["predicted_letter"] == orin[q]["pred"] for q in both)
        am = sum(bool(rows[q]["correct"]) for q in both)
        ao = sum(bool(orin[q]["correct"]) for q in both)
        print(f"  {cell} vs Orin {lab}  n={len(both)}")
        print(f"    input-token agreement : {tok}/{len(both)} = {100*tok/len(both):.1f}%")
        print(f"    prediction agreement  : {pm}/{len(both)} = {100*pm/len(both):.1f}%")
        print(f"    accuracy A6000 {100*am/len(both):.1f}%  vs Orin {100*ao/len(both):.1f}%")
        if cell == "C3":
            ta = np.median([rows[q]["n_output_tokens"] for q in both])
            to = np.median([orin[q]["n_gen"] for q in both])
            print(f"    median generated tokens A6000 {ta:.0f} vs Orin {to:.0f} "
                  f"(both sampled at temperature 1.0 -- different draws, not paired)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated analyses, e.g. A,B")
    args = ap.parse_args()
    want = set(args.only.split(",")) if args.only else set("ABCDE")

    loaded = {c: load_cell(c) for c in ("C1", "C2", "C3", "C4")}
    print("# Device-tier accuracy — analyses A–E")
    for c, r in loaded.items():
        print(f"  {c}: {len(r)} trials")

    gt120 = lambda t: float(t["question_time"]) > 120.0
    if "A" in want:
        analysis_A(loaded)
    if "B" in want:
        print("\n## B. Crossover replication (Instruct)")
        analysis_B(loaded["C1"], loaded["C2"], "Instruct, qt>120 PRIMARY", gt120)
        analysis_B(loaded["C1"], loaded["C2"], "Instruct, all 845 (attenuated)")
    if "C" in want:
        print("\n## C. Selection policies (Instruct)")
        analysis_C(loaded["C1"], loaded["C2"], "Instruct, qt>120 PRIMARY", gt120)
    if "D" in want:
        print("\n## D. Thinking")
        analysis_B(loaded["C3"], loaded["C4"], "Thinking, qt>120 PRIMARY", gt120)
        analysis_C(loaded["C3"], loaded["C4"], "Thinking, qt>120 PRIMARY", gt120)
    if "E" in want:
        analysis_E(loaded["C1"], loaded["C3"])


if __name__ == "__main__":
    main()
