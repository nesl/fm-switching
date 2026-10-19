#!/usr/bin/env python3
"""R4 prep analysis: do device-side confidence signals predict when the cloud is needed?

Reads the r4_device_signals.py trials and answers three things:
  1. consistency -- device accuracy and per-question predictions against the committed
     runs these pair with (CLAUDE.md results-consistency check 1);
  2. discrimination -- AUROC of each confidence signal for device correctness;
  3. escalation value -- accuracy when the least-confident fraction e is sent to the
     32B cloud arm, against random escalation and the accuracy oracle.

Cloud tier: ERQA = StudyR arm D (Qwen3-VL-32B-Thinking, h100nvl);
            MV-RoboBench = StudyS2 arm D (Qwen3-VL-32B-Thinking, h100nvl).
"""
import argparse, json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SIG = ROOT / "results/erqa/r4_signals"
BOOT = 2000
SEED = 0
RATES = [0.1, 0.2, 0.3, 0.5]


def load(name):
    p = SIG / f"r4_{name}.jsonl"
    return [json.loads(l) for l in open(p)] if p.exists() else []


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def auroc(score, label):
    """Mann-Whitney U with tie-corrected average ranks. score high => predicts label=1."""
    score = np.asarray(score, float)
    label = np.asarray(label, bool)
    n1, n0 = label.sum(), (~label).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), float)
    s = score[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return (ranks[label].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def boot_ci(fn, n, rng, reps=BOOT):
    vals = [fn(rng.integers(0, n, n)) for _ in range(reps)]
    vals = [v for v in vals if np.isfinite(v)]
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (float("nan"),) * 2


def signals_for(rows, arm):
    """name -> array, oriented so HIGHER means MORE confident."""
    out = {
        "neg_entropy_bits": np.array([-r["option_entropy_bits"] for r in rows]),
        "margin_norm": np.array([r["option_margin_norm"] for r in rows]),
        "max_option_prob": np.array([max(r["option_prob_norm"].values()) for r in rows]),
        "option_mass": np.array([r["option_mass"] for r in rows]),
    }
    if arm == "thinking":
        out.update({
            "neg_think_tokens": np.array([-(r["n_think_tokens"] or 0) for r in rows]),
            "neg_hesitation_total": np.array([-(r["hesitation_total"] or 0) for r in rows]),
            "neg_hesitation_wait": np.array([-(r["hesitation_wait"] or 0) for r in rows]),
            "neg_letter_changes": np.array([-(r["n_letter_changes"] or 0) for r in rows]),
        })
    return out


def escalation(conf, dev_ok, cloud_ok, rng):
    """Accuracy when the least-confident fraction e goes to the cloud."""
    n = len(conf)
    order = np.argsort(conf, kind="mergesort")   # least confident first
    base = dev_ok.mean()
    rows = []
    for e in RATES:
        k = int(round(e * n))
        esc = np.zeros(n, bool)
        esc[order[:k]] = True
        acc_sig = np.where(esc, cloud_ok, dev_ok).mean()
        rand = [np.where(np.isin(np.arange(n), rng.choice(n, k, replace=False)),
                         cloud_ok, dev_ok).mean() for _ in range(200)]
        # oracle: escalate the k questions where the cloud helps most
        helps = (cloud_ok.astype(int) - dev_ok.astype(int))
        oracle_idx = np.argsort(-helps, kind="mergesort")[:k]
        eo = np.zeros(n, bool); eo[oracle_idx] = True
        acc_or = np.where(eo, cloud_ok, dev_ok).mean()
        rows.append(dict(e=e, k=k, signal=acc_sig, random=float(np.mean(rand)),
                         oracle=acc_or, base=base,
                         closed=(acc_sig - np.mean(rand)) / (acc_or - np.mean(rand))
                         if acc_or > np.mean(rand) else float("nan")))
    return rows


def cloud_erqa():
    f = ROOT / "results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl"
    return {t["question_id"]: bool(t["correct"])
            for t in map(json.loads, open(f)) if t["arm"] == "D"}


def cloud_mvrobo():
    f = ROOT / "results/erqa/study_s2/study_s2_trials_h100nvl_fa2.jsonl"
    return {t["path"]: bool(t["correct"])
            for t in map(json.loads, open(f)) if t["arm"] == "D"}


def report(workload, arm, cloud, rng):
    rows = load(f"{workload}_{arm}")
    if not rows:
        print(f"\n### {workload}/{arm}: NOT RUN\n")
        return
    rows = [r for r in rows if not r.get("oom")]
    dev_ok = np.array([bool(r["correct"]) for r in rows])
    k, n = int(dev_ok.sum()), len(dev_ok)
    p, lo, hi = wilson(k, n)
    print(f"\n### {workload} / 4B-{arm}   n={n}  acc={k}/{n} = {100*p:.1f}%  "
          f"Wilson [{100*lo:.1f}, {100*hi:.1f}]")
    n_oom = sum(1 for r in load(f'{workload}_{arm}') if r.get('oom'))
    if n_oom:
        print(f"  OOM (excluded, NOT silently dropped): {n_oom}")
    if arm == "thinking":
        bh = sum(1 for r in rows if r.get("budget_hit"))
        tc = sum(1 for r in rows if r.get("think_closed"))
        print(f"  think_closed {tc}/{n}   budget_hit {bh}/{n}   "
              f"median think tokens {int(np.median([r['n_think_tokens'] or 0 for r in rows]))}")

    print(f"\n  {'signal':24} {'AUROC':>7}  {'95% CI':>18}")
    sigs = signals_for(rows, arm)
    for name, s in sigs.items():
        a = auroc(s, dev_ok)
        ci = boot_ci(lambda idx: auroc(s[idx], dev_ok[idx]), n, rng)
        print(f"  {name:24} {a:7.4f}  [{ci[0]:6.4f}, {ci[1]:6.4f}]")

    key = "qid"
    paired = [(r, cloud[r[key]]) for r in rows if r[key] in cloud]
    if not paired:
        print("\n  no cloud pairing available")
        return
    pr = [x[0] for x in paired]
    cl = np.array([x[1] for x in paired])
    dv = np.array([bool(r["correct"]) for r in pr])
    ck, cn = int(cl.sum()), len(cl)
    cp, clo, chi = wilson(ck, cn)
    print(f"\n  cloud (32B-Thinking) on the same {cn}: {ck}/{cn} = {100*cp:.1f}% "
          f"Wilson [{100*clo:.1f}, {100*chi:.1f}]   device {100*dv.mean():.1f}%")
    best = max(signals_for(pr, arm).items(),
               key=lambda kv: (auroc(kv[1], dv) if np.isfinite(auroc(kv[1], dv)) else 0))
    print(f"  escalation by best signal '{best[0]}' (AUROC {auroc(best[1], dv):.4f}):")
    print(f"    {'e':>5} {'k':>5} {'signal':>8} {'random':>8} {'oracle':>8} {'gap closed':>11}")
    for row in escalation(best[1], dv, cl, rng):
        print(f"    {row['e']:5.1f} {row['k']:5d} {100*row['signal']:8.1f} "
              f"{100*row['random']:8.1f} {100*row['oracle']:8.1f} {row['closed']:11.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", default="both", choices=["erqa", "mvrobo", "both"])
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)
    print("# R4 device-signal analysis")
    todo = ["erqa", "mvrobo"] if args.workload == "both" else [args.workload]
    for w in todo:
        cloud = cloud_erqa() if w == "erqa" else cloud_mvrobo()
        for arm in ("instruct", "thinking"):
            report(w, arm, cloud, rng)


if __name__ == "__main__":
    main()
