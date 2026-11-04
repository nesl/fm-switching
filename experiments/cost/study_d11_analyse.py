#!/usr/bin/env python3
"""StudyD11 analysis (CPU; .venv). Pre-registered in research/EXPERIMENTS.md (StudyD11 + addenda: arm I, arm F).

Per model (32B-I reference cells K3 / K1 from StudyR1; 4B-I H1 / H2 from StudyClean), overall and per stratum
(OLDER / OVERLAP / INSIDE / QT_LE_120 — ORACLE labels), video-clustered paired bootstrap (2,000, seed 0):
  primary (arm-I addendum): U − I (format-matched: same videos, frame counts, sizes, timestamps; only content differs)
  I − K3 (32B) / I − H1 (4B): effect of adding irrelevant frames (NOT format-matched: 2 videos vs 1)
  U − K3 / U − H1 and U − K1 / U − H2 (NOT format-matched)
  F − K3 / F − H1 on qt > 120 (format control: K3's frames split into 2 videos) + letter agreement + token difference
  interactions (pp and logit; study_d13_interaction.interaction): model × input (U vs K3) and (U vs K1); model × arm
  (U vs I).
Also: the one-question trace (K3 / U / I per-frame sha256), qt ≤ 120 identity (U = I = K3 frames; letters), I vs U
prompt tokens. Writes results/cost/study_d11/study_d11_results_h100nvl.json.
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_clean_analyse as CA  # noqa: E402
import study_d13_interaction as IX  # noqa: E402
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402

D = Path("results/cost/study_d11")
REQ = D / "study_d11_requests_h100nvl.jsonl"
MAN = D / "study_d11_inputs_manifest.jsonl"
OUT = D / "study_d11_results_h100nvl.json"
R1IN = Path.home() / ".cache/fm-switching/r1_inputs"
DIN = Path.home() / ".cache/fm-switching/d11_inputs"


def cells():
    rows = list(read_jsonl(REQ if REQ.exists() else Path(f"{REQ}.gz")))
    return {c: {r["question_id"]: r for r in rows if r["cell"] == c and not r["error"]}
            for c in {r["cell"] for r in rows}}, sum(bool(r["error"]) for r in rows)


def tokdiff(a, b, qs):
    d = [a[q]["prompt_tokens"] - b[q]["prompt_tokens"] for q in qs]
    rel = [x / b[q]["prompt_tokens"] for x, q in zip(d, qs)]
    return dict(n=len(qs), exact=sum(x == 0 for x in d), mean=float(np.mean(d)), min=int(min(d)), max=int(max(d)),
                max_abs_rel=float(max(abs(x) for x in rel)))


def trace(q, man):
    m = man[q]

    def hs(a):
        return [hashlib.sha256(np.ascontiguousarray(f).tobytes()).hexdigest()[:16] for f in a]
    k3 = np.load(R1IN / "RECENT" / f"{q}.npz")["frames"]
    k1 = np.load(R1IN / "RICH" / f"{q}.npz")["frames"][:m["n_old"]]
    iv = np.load(DIN / "I" / f"{q}.npz")["frames"]
    return dict(question_id=q, question_time=m["question_time"], n_old=m["n_old"], donor=m.get("donor"),
                donor_times_first_last=[m["donor_times"][0], m["donor_times"][-1]] if m.get("donor_times") else None,
                k3_frame_sha256_16=hs(k3), u_video1_frame_sha256_16=hs(k1), u_video2="= K3 (identical array)",
                i_video1_frame_sha256_16=hs(iv), i_video2="= K3 (identical array)",
                u_v1_equals_i_v1_any=bool(set(hs(k1)) & set(hs(iv))))


def main():
    C, nerr = cells()
    man = {r["question_id"]: r for r in map(json.loads, open(MAN))}
    ref, strat, vid = IX.load()
    res = dict(errors_logged=nerr, cells={c: len(v) for c, v in C.items()},
               strata_note="ORACLE labels (MCQ answer interval); not observable at request time", models={})
    for s, big in (("32", True), ("4", False)):
        a_rec, a_rich = (ref["K3"], ref["K1"]) if big else (ref["H1"], ref["H2"])
        nm = ("K3", "K1") if big else ("H1", "H2")
        U, I, F = C.get(f"U{s}", {}), C.get(f"I{s}", {}), C.get(f"F{s}", {})
        if not U:
            continue
        q_all = sorted(set(U) & set(a_rec) & set(a_rich) & (set(I) if I else set(U)))
        m = dict(n=len(q_all))
        m[f"U_minus_{nm[0]}"] = CA.contrast(U, a_rec, q_all, vid, strat)
        m[f"U_minus_{nm[1]}"] = CA.contrast(U, a_rich, q_all, vid, strat)
        m[f"tokens_U_minus_{nm[0]}"] = tokdiff(U, a_rec, q_all)
        if I:
            m["U_minus_I"] = CA.contrast(U, I, q_all, vid, strat)
            m[f"I_minus_{nm[0]}"] = CA.contrast(I, a_rec, q_all, vid, strat)
            m["tokens_I_minus_U"] = tokdiff(I, U, q_all)
        if F:
            qf = sorted(set(F) & set(a_rec))
            m[f"F_minus_{nm[0]}"] = CA.contrast(F, a_rec, qf, vid, strat)
            m[f"tokens_F_minus_{nm[0]}"] = tokdiff(F, a_rec, qf)
        le = [q for q in q_all if strat[q] == "QT_LE_120"]
        m["qt_le_120"] = dict(n=len(le), U_letters_eq_ref=sum(U[q]["pred"] == a_rec[q]["pred"] for q in le),
                              I_letters_eq_U=sum(I[q]["pred"] == U[q]["pred"] for q in le) if I else None,
                              U_tokens_eq_ref=sum(U[q]["prompt_tokens"] == a_rec[q]["prompt_tokens"] for q in le),
                              n_old_zero=sum(man[q]["n_old"] == 0 for q in le))
        res["models"][s] = m
    if "32" in res["models"] and "4" in res["models"]:
        q = sorted(set.intersection(*(set(C[c]) for c in ("U32", "U4"))) & set(ref["K3"]) & set(ref["H1"]))
        res["interaction_model_x_input_U_vs_recent"] = IX.interaction(ref["K3"], C["U32"], ref["H1"], C["U4"], q, vid,
                                                                       strat)
        res["interaction_model_x_input_U_vs_rich"] = IX.interaction(ref["K1"], C["U32"], ref["H2"], C["U4"], q, vid,
                                                                     strat)
        if "I32" in C and "I4" in C:
            qi = sorted(set(q) & set(C["I32"]) & set(C["I4"]))
            res["interaction_model_x_arm_U_vs_I"] = IX.interaction(C["I32"], C["U32"], C["I4"], C["U4"], qi, vid,
                                                                   strat)
        res["interaction_definition"] = ("(big_b − big_a) − (small_b − small_a): U vs recent = (U32 − K3) − (U4 − H1); "
                                         "U vs rich = (U32 − K1) − (U4 − H2); U vs I = (U32 − I32) − (U4 − I4)")
    tq = next((q for q, m in man.items() if m.get("i_v1_frame_sha256")), None)
    if tq:
        res["trace"] = trace(tq, man)
    res["format_matching"] = dict(U_minus_I="format-matched (same videos, frame counts, sizes, frames_indices)",
                                  U_minus_K3="NOT format-matched (2 videos vs 1 for qt > 120 with older frames)",
                                  I_minus_K3="NOT format-matched", F_minus_K3="isolates the 2-video format effect")
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d11_analyse.py", model="32BI,4BI", device="cpu", n=845)
    OUT.write_text(json.dumps(res, indent=1, default=float))
    for s, m in res["models"].items():
        for k, v in m.items():
            if isinstance(v, dict) and "ALL" in v:
                print(s, k, {st: (round(x["diff_pp"], 2), [round(c, 2) for c in x["ci95_pp"]]) for st, x in v.items()})


if __name__ == "__main__":
    main()
