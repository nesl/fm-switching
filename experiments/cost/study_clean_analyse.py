#!/usr/bin/env python3
"""StudyClean analysis (CPU). Pre-registered in research/EXPERIMENTS.md (StudyClean); no gates beyond the run's.

S-EMBER contrasts (accuracy, pp; video-clustered paired bootstrap, 2,000 resamples, seed 0) overall and per stratum:
  OLDER    qt > 120 and evidence ends before qt - 120          (asserted == R1 K3 evidence_covered false; 97)
  OVERLAP  qt > 120, evidence starts before qt - 120, ends at or after it    (167)
  INSIDE   qt > 120 and evidence starts at or after qt - 120   (414)
  QT_LE_120                                                     (167)
  H1 - K3 (4B vs 32B on K3's requests), H2 - K1 (on K1's), D2 - H3 (RH4 paired set, 839: value of history).
Input identity: per-question prompt tokens H1 vs K3 and H2 vs K1 (within 1 %); H3 vs D2 tokens per stratum.
MV-RoboBench: arm C sdpa - H4 (paired bootstrap over questions, 2,000, seed 0).
H5: per model x pass x N TTFT / total / prompt tokens / body bytes / GPU 1 SM clock; pass medians > 10 % apart ->
contention-sensitive (both reported); requests overlapping a sharp neighbour-load change (a GPU 0/2/3 SM-utilisation
step >= 50 points between consecutive 1-s dmon samples within [start - 1 s, end + 1 s]) flagged, never dropped;
Orin reference (StudyDevFast N = 37/18/9, StudyDevOne N = 1; 4B-I llama.cpp) minus its warm input_tokens == 1 rows.
"""
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sember"))
sys.path.insert(0, str(ROOT / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_o_q4_analyze import clustered_bootstrap  # noqa: E402

D = Path("results/cost/study_clean")
DEV = "h100nvl"
STRATA = ("OLDER", "OVERLAP", "INSIDE", "QT_LE_120")
COUNTS = dict(OLDER=97, OVERLAP=167, INSIDE=414, QT_LE_120=167)
NBOOT, SEED = 2000, 0
H5_NS = (37, 18, 9, 1)
SHARP = 50
ORIN = {37: "devfast_4bi_f16_n37", 18: "devfast_4bi_f16_n18", 9: "devfast_4bi_f16_n9", 1: "dev_one_n1"}


def stratum(m):
    qt = float(m["question_time"])
    a, b = sorted((float(m["answer_start_time"]), float(m["answer_end_time"])))
    if qt <= 120:
        return "QT_LE_120"
    lo = qt - 120
    return "OLDER" if b < lo else ("OVERLAP" if a < lo else "INSIDE")


def pick(rows, cell):
    return {r["question_id"]: r for r in rows if r["cell"] == cell and r["mode"] == "batched" and not r["error"]}


def contrast(a, b, qids, vids_of, strat):
    """mean(a) - mean(b) in pp on qids, overall and per stratum, with the video-clustered paired bootstrap."""
    out = {}
    for s in ("ALL",) + STRATA:
        q = [x for x in qids if s == "ALL" or strat[x] == s]
        if not q:
            continue
        d = np.array([int(a[x]["correct"]) - int(b[x]["correct"]) for x in q], float)
        v = np.array([vids_of[x] for x in q])
        bs = clustered_bootstrap(v, lambda i: d[i].mean(), nboot=NBOOT, seed=SEED)
        out[s] = dict(n=len(q), a_acc=100 * np.mean([a[x]["correct"] for x in q]),
                      b_acc=100 * np.mean([b[x]["correct"] for x in q]), diff_pp=100 * d.mean(),
                      ci95_pp=[100 * float(np.percentile(bs, 2.5)), 100 * float(np.percentile(bs, 97.5))],
                      answer_agreement=float(np.mean([a[x]["pred"] == b[x]["pred"] for x in q])))
    return out


def token_check(a, b, qids, strat):
    rel = {q: (a[q]["prompt_tokens"] - b[q]["prompt_tokens"]) / b[q]["prompt_tokens"] for q in qids}
    bad = [q for q, r in rel.items() if abs(r) > 0.01]
    return dict(n=len(qids), exact=sum(a[q]["prompt_tokens"] == b[q]["prompt_tokens"] for q in qids),
                within_1pct=len(qids) - len(bad), max_abs_rel=max(abs(r) for r in rel.values()),
                outside_1pct=[dict(question_id=q, stratum=strat[q], a=a[q]["prompt_tokens"], b=b[q]["prompt_tokens"])
                              for q in bad], passed=not bad)


def tokens_by_stratum(cells, qids, strat):
    out = {}
    for s in ("ALL",) + STRATA:
        q = [x for x in qids if s == "ALL" or strat[x] == s]
        out[s] = {c: dict(mean=float(np.mean([cells[c][x]["prompt_tokens"] for x in q])),
                          median=float(np.median([cells[c][x]["prompt_tokens"] for x in q])),
                          min=int(min(cells[c][x]["prompt_tokens"] for x in q)),
                          max=int(max(cells[c][x]["prompt_tokens"] for x in q)),
                          images_mean=float(np.mean([cells[c][x]["n_frames"] for x in q]))) for c in cells}
    return out


def sember():
    mcq = {r["question_id"]: r for r in map(json.loads, open("results/sember/study_h/data/sember_mcq.jsonl"))}
    r1 = list(read_jsonl(Path("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")))
    rh3 = list(read_jsonl(Path("results/sember/study_rh3/study_rh3_requests_h100nvl.jsonl.gz")))
    rh4 = list(read_jsonl(Path("results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz")))
    ours = list(read_jsonl(D / f"study_clean_requests_{DEV}.jsonl"))
    K1, K3 = pick(r1, "K1"), pick(r1, "K3")
    A, B = pick(rh3, "A"), pick(rh3, "B")
    D1, D2 = pick(rh4, "D1"), pick(rh4, "D2")
    SAN, H1, H2, H3 = (pick(ours, c) for c in ("SAN", "H1", "H2", "H3"))
    k3all = {r["question_id"]: r for r in r1 if r["cell"] == "K3" and r["mode"] == "batched"}
    strat = {q: stratum(mcq[q]) for q in k3all}
    counts = {s: sum(v == s for v in strat.values()) for s in STRATA}
    assert counts == COUNTS, counts
    assert {q for q, s in strat.items() if s == "OLDER"} == {q for q, r in k3all.items() if not r["evidence_covered"]}
    vid = {q: r["video_id"] for q, r in k3all.items()}
    out = dict(strata_counts=counts, older_equals_k3_uncovered=True, references_gpu="h100nvl GPU 3",
               this_run_gpu="h100nvl GPU 1", errors={c: sum(1 for r in ours if r["cell"] == c and r["error"])
                                                     for c in ("SAN", "H1", "H2", "H3")})
    # sanity
    out["sanity"] = dict(n=len(SAN), letters_match=sum(SAN[q]["pred"] == K3[q]["pred"] for q in SAN),
                         prompt_tokens_equal=sum(SAN[q]["prompt_tokens"] == K3[q]["prompt_tokens"] for q in SAN),
                         correct_san=sum(SAN[q]["correct"] for q in SAN), correct_k3=sum(K3[q]["correct"] for q in SAN))
    q1 = sorted(set(H1) & set(K3))
    q2 = sorted(set(H2) & set(K1))
    out["H1_vs_K3"] = dict(contrast=contrast(H1, K3, q1, vid, strat), input_identity=token_check(H1, K3, q1, strat),
                           note="H1 - K3: 4B-I minus 32B-I on K3's exact requests (RECENT)")
    out["H2_vs_K1"] = dict(contrast=contrast(H2, K1, q2, vid, strat), input_identity=token_check(H2, K1, q2, strat),
                           note="H2 - K1: 4B-I minus 32B-I on K1's exact requests (RICH)")
    paired = sorted(set.intersection(*(set(m) for m in (K1, K3, A, B, D1, D2))))
    assert len(paired) == 839, len(paired)
    q3 = [q for q in paired if q in H3]
    out["D2_vs_H3"] = dict(paired_set="RH4 paired set (answered without error in K1, K3, A, B, D1, D2)",
                           rh4_paired_n=len(paired), n_with_h3=len(q3),
                           contrast=contrast(D2, H3, q3, vid, strat),
                           tokens=tokens_by_stratum({"D2": D2, "H3": H3}, q3, strat),
                           qt_le_120_identity=dict(
                               n=sum(strat[q] == "QT_LE_120" for q in q3),
                               same_frames=sum(strat[q] == "QT_LE_120" and D2[q]["n_frames"] == H3[q]["n_frames"]
                                               for q in q3),
                               same_prompt_tokens=sum(strat[q] == "QT_LE_120" and D2[q]["prompt_tokens"] ==
                                                      H3[q]["prompt_tokens"] for q in q3),
                               same_letter=sum(strat[q] == "QT_LE_120" and D2[q]["pred"] == H3[q]["pred"] for q in q3)),
                           note="D2 - H3: whole-session vs last-120-s history at the same model/stride/size/format")
    # Context (not pre-registered as contrasts; same stack): K1 - K3 and H2 - H1 per stratum
    out["context"] = dict(K1_minus_K3=contrast(K1, K3, sorted(set(K1) & set(K3)), vid, strat),
                          H2_minus_H1=contrast(H2, H1, sorted(set(H2) & set(H1)), vid, strat))
    return out


def robobench():
    C = {t["path"]: t for t in map(json.loads, open("results/erqa/study_s2/study_s2_trials_h100nvl.jsonl")) if t["arm"] == "C"}
    I = {t["path"]: t for t in read_jsonl(D / "study_clean_h4_trials_h100nvl.jsonl") if t["arm"] == "I"}
    q = sorted(set(C) & set(I))
    d = np.array([int(C[p]["correct"]) - int(I[p]["correct"]) for p in q], float)
    rng = np.random.default_rng(SEED)
    bs = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(NBOOT)])
    out = dict(n=len(q), arm_C_acc=100 * np.mean([C[p]["correct"] for p in q]),
               H4_acc=100 * np.mean([I[p]["correct"] for p in q]), C_minus_H4_pp=100 * d.mean(),
               ci95_pp=[100 * float(np.percentile(bs, 2.5)), 100 * float(np.percentile(bs, 97.5))],
               attn={"C": sorted({C[p].get("attn_implementation", "sdpa (run meta)") for p in q}),
                     "H4": sorted({I[p]["attn_implementation"] for p in q})},
               parse_status_H4={s: sum(I[p]["parse_status"] == s for p in q) for s in {I[p]["parse_status"] for p in q}},
               input_tokens_equal=sum(C[p]["n_input_tokens"] == I[p]["n_input_tokens"] for p in q),
               per_category={})
    for cat in sorted({C[p]["category"] for p in q}):
        qq = [p for p in q if C[p]["category"] == cat]
        out["per_category"][cat] = dict(n=len(qq), C=100 * np.mean([C[p]["correct"] for p in qq]),
                                        H4=100 * np.mean([I[p]["correct"] for p in qq]))
    return out


def dmon_steps():
    """{epoch_second: max SM-util step on GPUs 0/2/3 vs the previous second} from logs/clean_dmon.log (-o T)."""
    p = Path("logs/clean_dmon.log")
    if not p.exists():
        return {}
    day = datetime.now().strftime("%Y-%m-%d")
    prev, steps = {}, {}
    for line in p.read_text().splitlines():
        f = line.split()
        if not f or f[0].startswith("#") or len(f) < 3:
            continue
        try:
            ts = int(datetime.strptime(f"{day} {f[0]}", "%Y-%m-%d %H:%M:%S").timestamp())
            g, sm = int(f[1]), f[2]
        except ValueError:
            continue
        if g == 1 or sm == "-":
            continue
        sm = int(sm)
        if g in prev:
            steps[ts] = max(steps.get(ts, 0), abs(sm - prev[g]))
        prev[g] = sm
    return steps


def h5():
    rows = [r for r in read_jsonl(D / f"study_clean_h5_requests_{DEV}.jsonl")]
    steps = dmon_steps()
    meas = [r for r in rows if not r["warmup"]]
    for r in meas:
        a, b = int(r["wall_start"]) - 1, int(r["wall_end"]) + 1
        r["neighbour_step_max"] = max([steps.get(t, 0) for t in range(a, b + 1)] or [0])
        r["neighbour_flag"] = r["neighbour_step_max"] >= SHARP
    out = dict(label="shared host, GPU 1, localhost, no network", cells={}, warmup={}, orin={}, table=[],
               flagged_requests=[dict(model=r["model"], pss=r["pass"], N=r["N"], question_id=r["question_id"],
                                      ttft_s=r["ttft_s"], neighbour_step=r["neighbour_step_max"])
                                 for r in meas if r["neighbour_flag"]],
               dmon_available=bool(steps))
    q = lambda xs, p: float(np.percentile(xs, p))  # noqa: E731
    for model in ("32BI", "4BI"):
        for N in H5_NS:
            per = {}
            for pss in (1, 2):
                rs = [r for r in meas if r["model"] == model and r["N"] == N and r["pass"] == pss]
                if not rs:
                    continue
                ok = [r for r in rs if not r["error"] and r["ttft_s"]]
                tt = [r["ttft_s"] for r in ok]
                per[pss] = dict(n=len(rs), errors=len(rs) - len(ok), ttft_median=statistics.median(tt),
                                ttft_p10=q(tt, 10), ttft_p90=q(tt, 90), ttft_min=min(tt), ttft_max=max(tt),
                                total_median=statistics.median(r["total_s"] for r in ok),
                                prompt_tokens_median=statistics.median(r["prompt_tokens"] for r in ok),
                                prompt_tokens_min=min(r["prompt_tokens"] for r in ok),
                                prompt_tokens_max=max(r["prompt_tokens"] for r in ok),
                                cached_tokens_nonzero=sum(bool(r["cached_tokens"]) for r in rs),
                                body_bytes_median=statistics.median(r["body_bytes"] for r in rs),
                                sm_mhz_median=statistics.median(r["gpu1"]["sm_mhz_median"] for r in ok if r["gpu1"].get("n")),
                                sm_mhz_min=min(r["gpu1"]["sm_mhz_min"] for r in ok if r["gpu1"].get("n")),
                                acc=sum(r["correct"] for r in rs) / len(rs), n_flagged=sum(r["neighbour_flag"] for r in rs),
                                ttft_median_unflagged=statistics.median([r["ttft_s"] for r in ok if not r["neighbour_flag"]]
                                                                        or [float("nan")]))
            if not per:
                continue
            cell = dict(passes=per)
            if 1 in per and 2 in per:
                m1, m2 = per[1]["ttft_median"], per[2]["ttft_median"]
                cell["pass_rel_diff"] = abs(m1 - m2) / min(m1, m2)
                cell["contention_sensitive"] = cell["pass_rel_diff"] > 0.10
                pr = {r["question_id"]: r["pred"] for r in meas if r["model"] == model and r["N"] == N and r["pass"] == 1}
                cell["pass_letter_agreement"] = float(np.mean([pr.get(r["question_id"]) == r["pred"] for r in meas
                                                               if r["model"] == model and r["N"] == N and r["pass"] == 2]))
            out["cells"][f"{model}_N{N}"] = cell
    for r in rows:
        if r["warmup"]:
            out["warmup"].setdefault(f"{r['model']}_N{r['N']}_p{r['pass']}", []).append(r["ttft_s"])
    for N, f in ORIN.items():
        rs = [json.loads(l) for l in open(f"results/device/{f}.jsonl")]
        warm = [r["question_id"] for r in rs if r["input_tokens"] == 1]
        keep = [r for r in rs if r["input_tokens"] != 1]
        out["orin"][N] = dict(source=f"results/device/{f}.jsonl", n=len(keep), excluded_warm=warm,
                              ttft_median=statistics.median(r["ttft_s"] for r in keep),
                              ttft_p10=q([r["ttft_s"] for r in keep], 10), ttft_p90=q([r["ttft_s"] for r in keep], 90),
                              total_median=statistics.median(r["total_latency_s"] for r in keep),
                              input_tokens_median=statistics.median(r["input_tokens"] for r in keep),
                              acc_all120=sum(r["correct"] for r in rs) / len(rs))
    for N in H5_NS:
        o = out["orin"][N]
        row = dict(N=N, orin_4bi_ttft_median=o["ttft_median"], orin_input_tokens=o["input_tokens_median"],
                   orin_acc=o["acc_all120"])
        for model in ("32BI", "4BI"):
            c = out["cells"].get(f"{model}_N{N}")
            if not c:
                continue
            for pss, p in c["passes"].items():
                row[f"h100_{model}_p{pss}_ttft_median"] = p["ttft_median"]
                row[f"h100_{model}_p{pss}_acc"] = p["acc"]
                row[f"h100_{model}_prompt_tokens"] = p["prompt_tokens_median"]
            row[f"h100_{model}_contention_sensitive"] = c.get("contention_sensitive")
        out["table"].append(row)
    return out


def main():
    out = dict(sember=sember())
    if (D / "study_clean_h4_trials_h100nvl.jsonl").exists():
        out["robobench_h4"] = robobench()
    if (D / f"study_clean_h5_requests_{DEV}.jsonl").exists() or (D / f"study_clean_h5_requests_{DEV}.jsonl.gz").exists():
        out["h5"] = h5()
    out["_provenance"] = stamp(script="study_clean_analyse.py", model="qwen3vl-4b-instruct+qwen3vl-32b-instruct",
                               device=f"{DEV}_gpu1", n=845)
    (D / f"study_clean_results_{DEV}.json").write_text(json.dumps(out, indent=1, default=float))
    s = out["sember"]
    print(json.dumps(dict(sanity=s["sanity"], errors=s["errors"],
                          H1_vs_K3=s["H1_vs_K3"]["contrast"], H1_tokens={k: v for k, v in s["H1_vs_K3"]["input_identity"].items()
                                                                       if k != "outside_1pct"},
                          H2_vs_K1=s["H2_vs_K1"]["contrast"], H2_tokens={k: v for k, v in s["H2_vs_K1"]["input_identity"].items()
                                                                       if k != "outside_1pct"},
                          D2_vs_H3=s["D2_vs_H3"]["contrast"], robobench=out.get("robobench_h4"),
                          h5_table=out.get("h5", {}).get("table")), indent=1, default=float))


if __name__ == "__main__":
    main()
