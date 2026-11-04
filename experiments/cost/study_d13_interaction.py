#!/usr/bin/env python3
"""EXPLORATORY (computed after the data were seen; requested 2026-11-04 with StudyD11) — model x input 2x2 interaction.

Cells (all canonical, same vLLM 0.31.0 stack, greedy, max 512; inputs identical within a column):
              RECENT (K3's requests)   RICH (K1's requests)
   32B-I      K3  (StudyR1)            K1  (StudyR1)
   4B-I       H1  (StudyClean)         H2  (StudyClean)
Interaction (pp) = (K1 - K3) - (H2 - H1): how much more (or less) the 32B gains from RICH than the 4B does.
Logit scale: [logit acc(K1) - logit acc(K3)] - [logit acc(H2) - logit acc(H1)], accuracies on the same question set.
Video-clustered paired bootstrap (2,000, seed 0) on the 845 questions answered in all four cells; per stratum
(OLDER / OVERLAP / INSIDE / QT_LE_120; oracle labels from the MCQ answer interval).
`interaction()` is reused by study_d11_analyse.py.
Run: .venv/bin/python experiments/cost/study_d13_interaction.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "sember"))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_clean_analyse as CA  # noqa: E402
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_o_q4_analyze import clustered_bootstrap  # noqa: E402

OUT = Path("results/cost/study_d11/study_d13_interaction_exploratory_h100nvl.json")


def _logit(p, n):
    p = (p * n + 0.5) / (n + 1.0)                 # continuity-corrected so 0 / 1 stay finite
    return np.log(p / (1 - p))


def interaction(big_a, big_b, small_a, small_b, qids, vids_of, strat):
    """(big_b - big_a) - (small_b - small_a) in pp and on the logit scale, overall and per stratum.
    Each argument maps question_id -> row with a boolean 'correct'."""
    out = {}
    for s in ("ALL",) + CA.STRATA:
        q = [x for x in qids if s == "ALL" or strat[x] == s]
        if not q:
            continue
        M = np.array([[int(c[x]["correct"]) for c in (big_a, big_b, small_a, small_b)] for x in q], float)
        v = np.array([vids_of[x] for x in q])
        n = len(q)

        def pp(i):
            m = M[i].mean(0)
            return (m[1] - m[0]) - (m[3] - m[2])

        def lg(i):
            m = M[i].mean(0)
            k = len(i)
            L = [_logit(x, k) for x in m]
            return (L[1] - L[0]) - (L[3] - L[2])
        idx = np.arange(n)
        bp = clustered_bootstrap(v, pp, nboot=CA.NBOOT, seed=CA.SEED)
        bl = clustered_bootstrap(v, lg, nboot=CA.NBOOT, seed=CA.SEED)
        acc = M.mean(0) * 100
        out[s] = dict(n=n, acc_pct=dict(big_a=acc[0], big_b=acc[1], small_a=acc[2], small_b=acc[3]),
                      big_gain_pp=acc[1] - acc[0], small_gain_pp=acc[3] - acc[2],
                      interaction_pp=100 * pp(idx), ci95_pp=[100 * float(np.percentile(bp, 2.5)),
                                                             100 * float(np.percentile(bp, 97.5))],
                      interaction_logit=float(lg(idx)), ci95_logit=[float(np.percentile(bl, 2.5)),
                                                                     float(np.percentile(bl, 97.5))])
    return out


def load():
    mcq = {r["question_id"]: r for r in map(json.loads, open("results/sember/study_h/data/sember_mcq.jsonl"))}
    r1 = list(read_jsonl(Path("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")))
    cl = list(read_jsonl(Path("results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")))
    K1, K3 = CA.pick(r1, "K1"), CA.pick(r1, "K3")
    H1, H2 = CA.pick(cl, "H1"), CA.pick(cl, "H2")
    k3all = {r["question_id"]: r for r in r1 if r["cell"] == "K3" and r["mode"] == "batched"}
    strat = {q: CA.stratum(mcq[q]) for q in k3all}
    assert {s: sum(v == s for v in strat.values()) for s in CA.STRATA} == CA.COUNTS
    vid = {q: r["video_id"] for q, r in k3all.items()}
    return dict(K1=K1, K3=K3, H1=H1, H2=H2), strat, vid


def main():
    c, strat, vid = load()
    q = sorted(set.intersection(*(set(v) for v in c.values())))
    res = dict(label="EXPLORATORY — computed after the data were seen (not pre-registered)",
               definition="interaction = (K1 - K3) - (H2 - H1); big = 32B-I, small = 4B-I; a = RECENT, b = RICH",
               strata_note="strata are oracle labels from the MCQ answer interval (not observable at request time)",
               n=len(q), result=interaction(c["K3"], c["K1"], c["H1"], c["H2"], q, vid, strat),
               at=datetime.now().isoformat())
    res["_provenance"] = stamp(script="study_d13_interaction.py", model="32BI,4BI", device="cpu", n=len(q))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=float))
    for s, r in res["result"].items():
        print(f"{s:10s} n={r['n']:3d} 32B gain {r['big_gain_pp']:+6.2f}  4B gain {r['small_gain_pp']:+6.2f}  "
              f"interaction {r['interaction_pp']:+6.2f} pp [{r['ci95_pp'][0]:+.2f}, {r['ci95_pp'][1]:+.2f}]  "
              f"logit {r['interaction_logit']:+.3f} [{r['ci95_logit'][0]:+.3f}, {r['ci95_logit'][1]:+.3f}]")


if __name__ == "__main__":
    main()
