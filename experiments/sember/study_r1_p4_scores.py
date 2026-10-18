#!/usr/bin/env python3
"""StudyR1: recompute StudyO's P4 escalation predictor scores for the 845-question pool (CPU).

Runs in the isolated venv ~/.venvs/fm-switching-p4 (sentence-transformers 5.1.1, scikit-learn 1.7.2, torch 2.8.0+cpu)
so neither the original .venv nor the vLLM venv is modified. Uses study_o_q4_analyze.train_p4 UNCHANGED (N2 P4:
all-MiniLM-L6-v2 embedding + log(1+qt), StudyO videos excluded from training).

Validation: reproduces StudyO's published 845-pool policy (d) accuracy at e = 0.1/0.2/0.3 for remote = 8B-I x RICH
(reports/study_o_q4_results_845_fa2.md: 33.85% at e = 0.2) before writing scores.
Output: results/sember/study_r1/study_r1_p4_scores.json  {question_id: p_need}
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import study_o_q4_analyze as A  # noqa: E402

A.GROUNDING = REPO / "results/sember/study_h/data/sember_grounding.jsonl"
TRIALS = REPO / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
OUT = REPO / "results/sember/study_r1/study_r1_p4_scores.json"
PUBLISHED_D_8BI = {0.2: 0.3385}


def main():
    by = {}
    for t in map(json.loads, open(TRIALS)):
        by.setdefault(t["model_arm"], {})[t["question_id"]] = t
    qids = sorted(set(by["4B-I"]) & set(by["8B-I"]))
    vids = np.array([by["4B-I"][q]["video_id"] for q in qids])
    qt = np.array([by["4B-I"][q]["question_time"] for q in qids])
    m, sc, clf = A.train_p4(set(vids.tolist()))
    qtext = {r["question_id"]: r["question"] for r in map(json.loads, open(A.GROUNDING))}
    E = m.encode([qtext[q] for q in qids], batch_size=256, show_progress_bar=False)
    p_need = clf.predict_proba(sc.transform(np.hstack([E, np.log1p(qt).reshape(-1, 1)])))[:, 1]
    loc = np.array([by["4B-I"][q]["correct"] for q in qids])
    rem = np.array([by["8B-I"][q]["correct"] for q in qids])
    check = {}
    for e in (0.1, 0.2, 0.3):
        check[e] = A.policy_acc(loc, rem, A.top_e_mask(p_need, e))
        print(f"e={e}: policy (d) acc with 8B-I remote = {check[e] * 100:.2f}%"
              + (f"  (published {PUBLISHED_D_8BI[e] * 100:.2f}%)" if e in PUBLISHED_D_8BI else ""))
    ok = abs(check[0.2] - PUBLISHED_D_8BI[0.2]) < 0.0006
    print("REPRODUCES StudyO published (d) at e=0.2:", ok)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(reproduces_studyo_d_e02=bool(ok), check_8bi_d={str(k): v for k, v in check.items()},
                                   p_need={q: float(p) for q, p in zip(qids, p_need)}), indent=0))


if __name__ == "__main__":
    main()
