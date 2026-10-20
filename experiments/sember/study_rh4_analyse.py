#!/usr/bin/env python3
"""StudyRH4 analysis (original .venv, CPU). Exactly the pre-registered analysis (research/EXPERIMENTS.md, StudyRH4).

D1 (stride 2 s, 288x224) and D2 (stride 2 s, 352x256) paired on question_id with R1's K1 / K3 and RH3's A / B.
Same stack (vLLM 0.31.0, H100, FA3). Video-clustered bootstrap, 2,000 resamples, seed 0; Wilson 95% CIs.
Primary set = questions answered without error in every cell (over-context D questions return HTTP 400 and are
excluded); sensitivity = all 845 with errored D answers counted wrong. History tokens = prompt tokens - the same chat
with R1's question text only (as RH3). Warm devices = floor(thr x KV / mean history tokens), thr 0.55 / 0.85,
KV 65,280 (bf16) / 129,280 (FP8).
DECISION RULE: ACCURATE-WARMABLE FORMAT EXISTS iff Part 0 passed AND D2 - K1 >= -1.5 pp with a 95% CI including 0
AND the CI of (D2 - K1 on RECENT-miss) includes 0. Otherwise INCOMPATIBILITY STANDS.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_r1_analyse import est, wilson  # noqa: E402
from study_rh3_analyse import text_only_tokens  # noqa: E402
import study_rh4_inputs as B  # noqa: E402

D = Path("results/sember/study_rh4")
R1 = Path("results/sember/study_r1")
RH3 = Path("results/sember/study_rh3")
DEV = "h100nvl"
KV = {"bf16": 65280, "fp8": 129280}
THRESH = {"clean_0.55x": 0.55, "degraded_0.85x": 0.85}
ORDER = ("K1", "K3", "A", "B", "D1", "D2")
LIMIT = B.MAX_MODEL_LEN - B.MAX_TOKENS
PARITY_PP = 0.015


def main():
    R = list(read_jsonl(D / f"study_rh4_requests_{DEV}.jsonl"))
    pick = lambda src, c: {r["question_id"]: r for r in src  # noqa: E731
                           if r["cell"] == c and r["mode"] == "batched" and not r["error"]}
    r1 = list(read_jsonl(R1 / f"study_r1_requests_{DEV}.jsonl"))
    rh3 = list(read_jsonl(RH3 / f"study_rh3_requests_{DEV}.jsonl"))
    cell = {c: pick(R, c) for c in ("D1", "D2")}
    cell.update({c: pick(r1, c) for c in ("K1", "K3")})
    cell.update({c: pick(rh3, c) for c in ("A", "B")})
    man = {(r["question_id"], r["cell"]): r for r in read_jsonl(D / "study_rh4_inputs_manifest.jsonl")}
    man1 = {(r["question_id"], r["construction"]): r for r in read_jsonl(R1 / "study_r1_inputs_manifest.jsonl")}
    part0 = json.loads((D / f"study_rh4_part0_{DEV}.json").read_text())
    out = dict(part0_passed=part0["passed"], parity_all={}, over_context={}, cells={}, tests={}, table=[],
               warm_devices={}, sensitivity_errors_wrong={}, coverage_split={})

    all_q = sorted({q for q, _ in man})
    rmiss = {q: not man1[(q, "RECENT")]["evidence_covered"] for q in all_q}
    for c in ("D1", "D2"):
        rr = [r for r in R if r["cell"] == c and r["mode"] == "batched"]
        ok = [r for r in rr if not r["error"]]
        out["parity_all"][c] = dict(n=len(ok), errors=len(rr) - len(ok),
                                    exact=sum(r["prompt_tokens"] == r["expected_prompt_tokens"] for r in ok),
                                    finish_length=sum(r["finish_reason"] == "length" for r in ok),
                                    unparsed=sum(r["pred"] == "X" for r in ok),
                                    error_kinds=sorted({r["error"][:60] for r in rr if r["error"]}))
        oc = [man[(q, c)] for q in all_q if man[(q, c)]["over_context"]]
        tok_img = (B.SIZES[c][0] // 32) * (B.SIZES[c][1] // 32) + 2
        nontext = np.array([man[(q, c)]["n_input_instruct"] - man[(q, c)]["image_tokens"] for q in all_q])
        fmax = lambda base: int((LIMIT - base) // tok_img)  # noqa: E731
        out["over_context"][c] = dict(
            n=len(oc), recent_miss=sum(rmiss[r["question_id"]] for r in oc),
            questions=[dict(question_id=r["question_id"], qt=r["question_time"], prompt_tokens=r["n_input_instruct"],
                            images=r["n_images"], recent_miss=rmiss[r["question_id"]]) for r in oc],
            errored_in_run=sorted(r["question_id"] for r in rr if r["error"]),
            tokens_per_image=tok_img, limit_tokens=LIMIT,
            longest_session_s_mean_text=B.STRIDE_S * (fmax(nontext.mean()) - 1),
            longest_session_s_longest_text=B.STRIDE_S * (fmax(nontext.max()) - 1),
            longest_session_min_mean_text=round(B.STRIDE_S * (fmax(nontext.mean()) - 1) / 60, 1),
            longest_session_min_longest_text=round(B.STRIDE_S * (fmax(nontext.max()) - 1) / 60, 1))

    qids = sorted(set.intersection(*(set(m) for m in cell.values())))
    out["paired_n"] = len(qids)
    vids = np.array([man1[(q, "RICH")]["video_id"] for q in qids])
    A = {c: np.array([cell[c][q]["correct"] for q in qids], float) for c in cell}
    cov = np.array([not rmiss[q] for q in qids])
    out["recent_misses_n"] = int((~cov).sum())
    ntext = text_only_tokens([man1[(q, "RICH")] for q in qids])

    for c in ORDER:
        m = cell[c]
        k = int(sum(m[q]["correct"] for q in qids))
        pt = np.array([m[q]["prompt_tokens"] for q in qids], float)
        hist = pt - np.array([ntext[q] for q in qids], float)
        out["cells"][c] = dict(n=len(qids), acc=k / len(qids), wilson95=wilson(k, len(qids)),
                               prompt_tokens_mean=float(pt.mean()), history_tokens_mean=float(hist.mean()),
                               history_tokens_max=float(hist.max()),
                               frames_mean=float(np.mean([m[q]["n_frames"] for q in qids])),
                               own_evidence_covered=int(sum(m[q]["evidence_covered"] for q in qids)),
                               acc_recent_misses=float(A[c][~cov].mean()), acc_recent_covers=float(A[c][cov].mean()))
        out["table"].append(dict(cell=c, **out["cells"][c]))
        out["warm_devices"][c] = {f"{th}_{kv}": int(np.floor(tv * kvv / hist.mean()))
                                  for th, tv in THRESH.items() for kv, kvv in KV.items()}

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
    for x, ref in [("D2", "K1"), ("D1", "K1"), ("D2", "B"), ("D2", "A"), ("D1", "B"), ("D1", "A"), ("D2", "D1"),
                   ("D2", "K3"), ("D1", "K3")]:
        T[f"{x}_minus_{ref}"] = est(vids, diff(A[x], A[ref]))
        T[f"{x}_minus_{ref}_recent_misses"] = est(vids, diff(A[x], A[ref], ~cov))
        T[f"{x}_minus_{ref}_recent_covers"] = est(vids, diff(A[x], A[ref], cov))
        T[f"{x}_minus_{ref}_DiD"] = est(vids, did(A[x], A[ref]))

    # sensitivity: all 845, errored D answers counted wrong (K1/K3/A/B have no errors)
    vall = np.array([man1[(q, "RICH")]["video_id"] for q in all_q])
    covall = np.array([not rmiss[q] for q in all_q])
    full = {c: np.array([bool(cell[c].get(q, {}).get("correct", False)) for q in all_q], float) for c in cell}
    for x in ("D1", "D2"):
        out["sensitivity_errors_wrong"][x] = dict(
            acc=float(full[x].mean()),
            minus_K1=est(vall, lambda i, x=x: float((full[x][i] - full["K1"][i]).mean())),
            minus_K1_recent_misses=est(vall, lambda i, x=x: float((full[x][i][~covall[i]]
                                                                    - full["K1"][i][~covall[i]]).mean())))
    for c in ("D1", "D2"):
        own = np.array([man[(q, c)]["evidence_covered"] for q in qids])
        out["coverage_split"][c] = dict(n_lost_coverage=int((~own).sum()),
                                        acc_lost=float(A[c][~own].mean()) if (~own).any() else None)
    out["answer_agreement"] = {f"{x}_vs_{y}": float(np.mean([cell[x][q]["pred"] == cell[y][q]["pred"] for q in qids]))
                               for x, y in (("D2", "K1"), ("D1", "K1"), ("D2", "B"), ("D2", "D1"))}

    t, tm = T["D2_minus_K1"], T["D2_minus_K1_recent_misses"]
    conds = dict(part0_passed=bool(part0["passed"]), d2_minus_k1_ge_minus_1p5pp=t["est"] >= -PARITY_PP,
                 d2_minus_k1_ci_includes_0=not t["excludes_0"], recent_miss_ci_includes_0=not tm["excludes_0"])
    out["decision"] = dict(conditions=conds,
                           outcome="ACCURATE-WARMABLE FORMAT EXISTS" if all(conds.values())
                           else "INCOMPATIBILITY STANDS",
                           note_significantly_above=bool(t["excludes_0"] and t["est"] > 0
                                                         or tm["excludes_0"] and tm["est"] > 0))
    out["_provenance"] = stamp(script="study_rh4_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(qids))
    (D / f"study_rh4_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(decision=out["decision"], paired_n=out["paired_n"], parity=out["parity_all"],
                          over_context={c: {k: v for k, v in o.items() if k != "questions"}
                                        for c, o in out["over_context"].items()},
                          sensitivity=out["sensitivity_errors_wrong"], agree=out["answer_agreement"]), indent=1))
    for r in out["table"]:
        print(f"{r['cell']:3s} hist {r['history_tokens_mean']:7.0f} (max {r['history_tokens_max']:6.0f}) acc "
              f"{r['acc'] * 100:5.2f} [{r['wilson95'][0] * 100:.1f}, {r['wilson95'][1] * 100:.1f}] miss "
              f"{r['acc_recent_misses'] * 100:5.1f} cover {r['acc_recent_covers'] * 100:5.1f} "
              f"warm {out['warm_devices'][r['cell']]}")
    for k, v in T.items():
        print(f"{k:28s} {v['est'] * 100:+6.2f} pp CI [{v['ci'][0] * 100:+6.2f}, {v['ci'][1] * 100:+6.2f}]")
    print(json.dumps(out["over_context"], indent=1)[:3000])


if __name__ == "__main__":
    main()
