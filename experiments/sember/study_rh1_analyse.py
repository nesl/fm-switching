#!/usr/bin/env python3
"""StudyRH1 analysis (original .venv, CPU). Exactly the pre-registered analysis (research/EXPERIMENTS.md, StudyRH1).

Pairs H1a (RICH 50% frames), H1b (RICH 25%), H1c (full RICH, FP8 KV) with StudyR1's K1 (full RICH, bf16) and K3
(RECENT) on question_id. Same stack (vLLM 0.31.0, H100), so no cross-stack caveat. Video-clustered bootstrap, 2,000
resamples, seed 0; Wilson 95% CIs. RECENT evidence split from R1's RECENT construction (evidence_covered).
FP8 PARITY rule: |H1c - K1| <= 1.5 pp and the 95% CI includes 0.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_r1_analyse import est, wilson  # noqa: E402  (same bootstrap / Wilson code as R1)

D = Path("results/sember/study_rh1")
R1 = Path("results/sember/study_r1")
DEV = "h100nvl"
PARITY_PP = 0.015


def main():
    R = list(read_jsonl(D / f"study_rh1_requests_{DEV}.jsonl"))
    r1 = list(read_jsonl(R1 / f"study_r1_requests_{DEV}.jsonl"))
    cell = {c: {r["question_id"]: r for r in R if r["cell"] == c and r["mode"] == "batched" and not r["error"]}
            for c in ("H1a", "H1b", "H1c")}
    cell.update({c: {r["question_id"]: r for r in r1 if r["cell"] == c and r["mode"] == "batched" and not r["error"]}
                 for c in ("K1", "K3")})
    man1 = {(r["question_id"], r["construction"]): r for r in read_jsonl(R1 / "study_r1_inputs_manifest.jsonl")}
    manh = {(r["question_id"], r["construction"]): r for r in read_jsonl(D / "study_rh1_inputs_manifest.jsonl")}
    out = dict(cells={}, parity_all={}, tests={}, ladder=[], coverage_split={}, fp8={})

    for c in ("H1a", "H1b", "H1c"):
        rr = [r for r in R if r["cell"] == c and r["mode"] == "batched"]
        ok = [r for r in rr if not r["error"]]
        out["parity_all"][c] = dict(n=len(ok), errors=len(rr) - len(ok),
                                    exact=sum(r["prompt_tokens"] == r["expected_prompt_tokens"] for r in ok))
    k1_pt = {q: r["prompt_tokens"] for q, r in cell["K1"].items()}
    out["parity_all"]["H1c_vs_K1_prompt_tokens_equal"] = sum(r["prompt_tokens"] == k1_pt.get(q)
                                                             for q, r in cell["H1c"].items())

    qids = sorted(set.intersection(*(set(m) for m in cell.values())))
    out["paired_n"] = len(qids)
    vids = np.array([cell["K1"][q]["video_id"] for q in qids])
    A = {c: np.array([cell[c][q]["correct"] for q in qids], float) for c in cell}
    cov = np.array([man1[(q, "RECENT")]["evidence_covered"] for q in qids])
    out["recent_misses_n"] = int((~cov).sum())

    for c in ("K3", "H1b", "H1a", "K1", "H1c"):
        m = cell[c]
        k = sum(r["correct"] for r in m.values())
        pt = np.array([r["prompt_tokens"] for r in m.values()], float)
        nf = np.array([r["n_frames"] for r in m.values()], float)
        own_cov = [r["evidence_covered"] for r in m.values()]
        out["cells"][c] = dict(n=len(m), acc=k / len(m), wilson95=wilson(k, len(m)),
                               prompt_tokens_mean=float(pt.mean()), prompt_tokens_median=float(np.median(pt)),
                               prompt_tokens_min=float(pt.min()), prompt_tokens_max=float(pt.max()),
                               frames_median=float(np.median(nf)), own_evidence_covered=int(sum(own_cov)),
                               acc_recent_misses=float(A[c][~cov].mean()), acc_recent_covers=float(A[c][cov].mean()))
        out["ladder"].append(dict(cell=c, **{k_: out["cells"][c][k_] for k_ in
                                             ("prompt_tokens_mean", "frames_median", "acc", "wilson95",
                                              "acc_recent_misses", "acc_recent_covers")}))

    def diff(a, b, mask=None):
        def f(i):
            j = i if mask is None else i[mask[i]]
            return float((a[j] - b[j]).mean())
        return f

    def did(a, b):
        def f(i):
            m, c_ = ~cov[i], cov[i]
            return float((a[i][m] - b[i][m]).mean() - (a[i][c_] - b[i][c_]).mean())
        return f

    T = out["tests"]
    for x in ("H1a", "H1b", "H1c"):
        for ref in ("K1", "K3"):
            T[f"{x}_minus_{ref}"] = est(vids, diff(A[x], A[ref]))
            T[f"{x}_minus_{ref}_recent_misses"] = est(vids, diff(A[x], A[ref], ~cov))
            T[f"{x}_minus_{ref}_recent_covers"] = est(vids, diff(A[x], A[ref], cov))
            T[f"{x}_minus_{ref}_DiD"] = est(vids, did(A[x], A[ref]))
    T["H1a_minus_H1b"] = est(vids, diff(A["H1a"], A["H1b"]))

    # within-construction coverage split (does the thinned set still contain an evidence frame?)
    for x in ("H1a", "H1b"):
        own = np.array([manh[(q, "HALF" if x == "H1a" else "QUARTER")]["evidence_covered"] for q in qids])
        lost = ~own
        out["coverage_split"][x] = dict(n_lost_coverage=int(lost.sum()),
                                        acc_lost=float(A[x][lost].mean()) if lost.any() else None,
                                        k1_acc_on_lost=float(A["K1"][lost].mean()) if lost.any() else None,
                                        acc_kept=float(A[x][~lost].mean()), k1_acc_on_kept=float(A["K1"][~lost].mean()))

    # FP8 parity
    agree = np.array([cell["H1c"][q]["pred"] == cell["K1"][q]["pred"] for q in qids])
    t = est(vids, diff(A["H1c"], A["K1"]))
    flips = dict(both_right=int(((A["H1c"] == 1) & (A["K1"] == 1)).sum()),
                 fp8_only=int(((A["H1c"] == 1) & (A["K1"] == 0)).sum()),
                 bf16_only=int(((A["H1c"] == 0) & (A["K1"] == 1)).sum()),
                 both_wrong=int(((A["H1c"] == 0) & (A["K1"] == 0)).sum()))
    text_same = float(np.mean([cell["H1c"][q]["text"] == cell["K1"][q]["text"] for q in qids]))
    # same-stack bf16 noise reference: R1's K1 single-request latency run (first 50 questions, concurrency 1) vs K1
    # batched (concurrency 8) — same inputs, same server config, different batch composition.
    single = {r["question_id"]: r for r in r1 if r["cell"] == "K1" and r["mode"] == "single" and not r["error"]}
    ref = [q for q in single if q in cell["K1"]]
    out["fp8"] = dict(diff=t, within_1p5pp=abs(t["est"]) <= PARITY_PP, ci_includes_0=not t["excludes_0"],
                      verdict="FP8 PARITY" if (abs(t["est"]) <= PARITY_PP and not t["excludes_0"]) else "NO PARITY",
                      answer_agreement=float(agree.mean()), n_disagree=int((~agree).sum()), flips=flips,
                      text_identical_frac=text_same,
                      bf16_reference_K1_single_vs_batched=dict(
                          n=len(ref), answer_agreement=float(np.mean([single[q]["pred"] == cell["K1"][q]["pred"]
                                                                      for q in ref])) if ref else None,
                          text_identical_frac=float(np.mean([single[q]["text"] == cell["K1"][q]["text"]
                                                             for q in ref])) if ref else None))
    out["_provenance"] = stamp(script="study_rh1_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(qids))
    (D / f"study_rh1_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(paired_n=out["paired_n"], parity=out["parity_all"], fp8=out["fp8"]), indent=1))
    for row in out["ladder"]:
        print(f"{row['cell']:4s} tok {row['prompt_tokens_mean']:7.0f} frames {row['frames_median']:5.0f} acc "
              f"{row['acc'] * 100:5.2f} miss {row['acc_recent_misses'] * 100:5.1f} cover {row['acc_recent_covers'] * 100:5.1f}")
    for k, v in T.items():
        print(f"{k:34s} {v['est'] * 100:+6.2f} pp CI [{v['ci'][0] * 100:+6.2f}, {v['ci'][1] * 100:+6.2f}]")
    print(json.dumps(out["coverage_split"], indent=1))


if __name__ == "__main__":
    main()
