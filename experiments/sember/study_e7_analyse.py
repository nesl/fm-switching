#!/usr/bin/env python3
"""StudyE7-d2-4b analysis (CPU; dashcam venv). Job A: 4B D2 accuracy with video-bootstrap CIs (2,000, seed 0) on all
845 (infeasible = wrong) and on RH4's paired 839; paired vs 32B D2 (RH4), H1 / H2 (StudyClean), U4 (D11); strata
(StudyClean's); grey control; INSIDE accuracy by prompt-token tercile (Step 5); checks.
Job B: per-cell latency quantiles, fits (TTFT / total vs prompt tokens COLD; vs uncached tokens WARM; never pooled),
WARM first-in-session vs cold curve, pairing with F3's 32B c_D2 / d_D2_WARM rows. Writes
results/sember/study_e7/e7_results.json."""
import collections
import gzip
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
sys.path.insert(0, str(REPO / "experiments/sember"))
sys.path.insert(0, str(REPO / "experiments/cost"))
from study_f1_analyse import boot, by_video, stratum, strata, STRATA, SEED  # noqa: E402
from study_f3_analyse import q as quant, fit  # noqa: E402

OUT = REPO / "results/sember/study_e7"
REFS = {"32B_D2": ("results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz", "D2"),
        "H1": ("results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz", "H1"),
        "H2": ("results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz", "H2"),
        "U4": ("results/cost/study_d11/study_d11_requests_h100nvl.jsonl", "U4")}


def load_ref(p, cell):
    op = gzip.open if p.endswith(".gz") else open
    out = {}
    for l in op(REPO / p, "rt"):
        r = json.loads(l)
        if r.get("cell") == cell and r.get("mode", "batched") == "batched" and not r["error"]:
            out[r["question_id"]] = r
    return out


def job_a(res, rng):
    M = strata()
    rows = [json.loads(l) for l in open(OUT / "e7_requests_h100nvl.jsonl")]
    real = {r["question_id"]: r for r in rows if not r["grey"] and (not r["error"] or r["infeasible"])}
    grey = {r["question_id"]: r for r in rows if r["grey"] and not r["error"]}
    qs = sorted(real)
    vid = {q: real[q]["video_id"] for q in qs}
    st = {q: stratum(M[q], float(real[q]["question_time"])) for q in qs}
    ok = [real[q] for q in qs if not real[q]["error"]]
    refs = {k: load_ref(*v) for k, v in REFS.items()}
    paired839 = sorted(set(refs["32B_D2"]) & set(q for q in qs if not real[q]["error"]))
    res["checks"] = dict(
        rows=len(rows), real_answered=len(ok), infeasible=sorted([(real[q]["question_time"], q[:10]) for q in qs if real[q]["infeasible"]]),
        error_rows_retried=sum(1 for r in rows if r["error"] and not r["infeasible"]),
        transport_retries=sum(len(r["transport_errors"]) for r in rows),
        unparsed_X=sum(r["pred"] == "X" for r in ok), finish_length=sum(r["finish_reason"] == "length" for r in ok),
        cached_tokens_nonzero=sum(bool(r["cached_tokens"]) for r in ok),
        prompt_tokens_match_rh4=sum(bool(r["prompt_tokens_match"]) for r in ok),
        prompt_tokens=quant([r["prompt_tokens"] for r in ok]),
        letter_mass_top20=quant([r["letter_probs"]["total"] for r in ok if r["letter_probs"]]),
        pred_letters=dict(collections.Counter(r["pred"] for r in ok)),
        gold_letters=dict(collections.Counter(r["correct_letter"] for r in ok)),
        paired839=len(paired839), grey_n=len(grey))
    res["strata_counts"] = dict(collections.Counter(st.values()))
    cor = lambda q: float(bool(real[q]["correct"]))  # noqa: E731  (infeasible -> wrong)
    acc, paired = {}, {}
    for s in ("ALL",) + STRATA:
        all_s = [q for q in qs if s == "ALL" or st[q] == s]
        p_s = [q for q in paired839 if s == "ALL" or st[q] == s]
        acc[f"4B_D2/all845/{s}"] = boot(by_video((vid[q], cor(q)) for q in all_s), rng)
        acc[f"4B_D2/paired839/{s}"] = boot(by_video((vid[q], cor(q)) for q in p_s), rng)
        for k, ref in refs.items():
            sel = [q for q in p_s if q in ref]
            acc[f"{k}/paired839/{s}"] = boot(by_video((vid[q], float(ref[q]["correct"])) for q in sel), rng)
            paired[f"4B_D2-{k}/{s}"] = dict(
                boot(by_video((vid[q], cor(q) - float(ref[q]["correct"])) for q in sel), rng),
                agreement=float(np.mean([real[q]["pred"] == ref[q]["pred"] for q in sel])),
                ref_prompt_tokens_median=float(np.median([ref[q]["prompt_tokens"] for q in sel])))
    # infeasible counted wrong in the 32B reference too (RH4 sensitivity convention)
    ref32 = refs["32B_D2"]
    paired["4B_D2-32B_D2/all845_infeasible_wrong"] = boot(by_video(
        (vid[q], cor(q) - float(bool(ref32.get(q, {}).get("correct")))) for q in qs), rng)
    res["accuracy"], res["paired"] = acc, paired
    # Step 5: INSIDE accuracy by D2 prompt-token tercile (4B and 32B, same questions)
    ins = [q for q in paired839 if st[q] == "INSIDE"]
    edges = np.percentile([real[q]["prompt_tokens"] for q in ins], [33.33, 66.67])
    terc = {}
    for i, (lo, hi) in enumerate([(-1, edges[0]), (edges[0], edges[1]), (edges[1], 1e9)]):
        sel = [q for q in ins if lo < real[q]["prompt_tokens"] <= hi]
        terc[f"T{i + 1}"] = dict(tokens=[float(min(real[q]["prompt_tokens"] for q in sel)), float(max(real[q]["prompt_tokens"] for q in sel))],
                                 acc_4B=boot(by_video((vid[q], cor(q)) for q in sel), rng),
                                 acc_32B=boot(by_video((vid[q], float(ref32[q]["correct"])) for q in sel), rng))
    res["inside_by_token_tercile"] = terc
    # grey
    g = sorted(grey)
    res["grey"] = dict(n=len(g), grey_acc=boot(by_video((vid[q], float(bool(grey[q]["correct"]))) for q in g), rng),
                       real_acc_same_q=float(np.mean([cor(q) for q in g])),
                       real_minus_grey=boot(by_video((vid[q], cor(q) - float(bool(grey[q]["correct"]))) for q in g), rng),
                       letters=dict(collections.Counter(grey[q]["pred"] for q in g)),
                       distinct_responses=len({grey[q]["text"] for q in g}),
                       prompt_tokens_equal_real=sum(grey[q]["prompt_tokens"] == real[q]["prompt_tokens"] for q in g))
    trace_q = "18C977EDB2"
    t = next(r for r in ok if r["question_id"].startswith(trace_q))
    res["trace"] = {k: t[k] for k in ("question_id", "question_time", "n_images", "prompt_tokens",
                                      "expected_prompt_tokens", "body_sha256", "pred", "correct_letter", "letter_probs",
                                      "completion_tokens", "finish_reason")}
    res["trace"]["pred_32B_D2"] = ref32[t["question_id"]]["pred"]


def job_b(res):
    rows = [json.loads(l) for l in open(OUT / "e7_latency_requests_h100nvl.jsonl")]
    rows = [r for r in rows if not r.get("superseded")]
    meta = json.loads((OUT / "e7_latency_run_meta_h100nvl.json").read_text())
    good = [r for r in rows if not r["discarded"] and not r["error"]]
    b = dict(void=meta.get("void"), checks=dict(
        rows=len(rows), discarded=sum(r["discarded"] for r in rows), errors=sum(bool(r["error"]) for r in rows),
        cold_with_cached_tokens=sum(1 for r in good if r["label"] == "cold" and r["cached_tokens"]),
        warm_later_with_cached_zero=sum(1 for r in good if r["label"] == "WARM" and r["pos"] > 0 and not r["cached_tokens"]),
        sm_clock_at_send=sorted({r["sm_at_send"].split(",")[0] for r in good})), cells={}, bins={}, curves={})
    for cell in sorted({r["cell"] for r in good}):
        rs = [r for r in good if r["cell"] == cell]
        b["cells"][cell] = dict(cache="WARM" if rs[0]["prefix_caching"] else "COLD", n=len(rs),
                                prompt_tokens=quant([r["prompt_tokens"] for r in rs]),
                                cached_tokens=quant([r["cached_tokens"] or 0 for r in rs]),
                                ttft_s=quant([r["ttft_s"] for r in rs]), total_s=quant([r["total_s"] for r in rs]))
    for i in sorted({r["bin"] for r in good if "bin" in r}):
        rb = [r for r in good if r.get("bin") == i]
        b["bins"][f"bin{i}"] = dict(prompt_tokens=quant([r["prompt_tokens"] for r in rb]), ttft_s=quant([r["ttft_s"] for r in rb]),
                                    total_s=quant([r["total_s"] for r in rb]))
    cold = [r for r in good if r["label"] == "cold"]
    warm = [r for r in good if r["label"] == "WARM"]
    b["curves"]["4B/images/COLD"] = dict(n=len(cold), ttft=fit([r["prompt_tokens"] for r in cold], [r["ttft_s"] for r in cold]),
                                         total=fit([r["prompt_tokens"] for r in cold], [r["total_s"] for r in cold]))
    b["curves"]["4B/images/WARM"] = dict(n=len(warm), ttft=fit([r["prompt_tokens"] for r in warm], [r["ttft_s"] for r in warm]),
                                         ttft_vs_uncached_tokens=fit([r["prompt_tokens"] - (r["cached_tokens"] or 0) for r in warm],
                                                                     [r["ttft_s"] for r in warm]))
    c2 = b["curves"]["4B/images/COLD"]["ttft"]["deg2"]["coef_high_to_low"]
    for name, sel in (("first_in_session", [r for r in warm if r["pos"] == 0]), ("later_in_session", [r for r in warm if r["pos"] > 0])):
        d = [r["ttft_s"] - float(np.polyval(c2, r["prompt_tokens"])) for r in sel]
        b["cells"]["b2_D2_WARM"][name] = dict(n=len(sel), ttft=quant([r["ttft_s"] for r in sel]),
                                              cached_tokens=quant([r["cached_tokens"] or 0 for r in sel]),
                                              uncached_tokens=quant([r["prompt_tokens"] - (r["cached_tokens"] or 0) for r in sel]),
                                              ttft_minus_cold_fit=quant(d))
    # pairing with F3's 32B rows (same questions / sessions)
    f3 = [json.loads(l) for l in open(REPO / "results/cost/study_f3/f3_requests_h100nvl.jsonl")]
    f3 = [r for r in f3 if not r.get("superseded") and not r["discarded"] and not r["error"] and r["model"] == "32BI"]
    pair = {}
    for mine, theirs in (("b1_D2", "c_D2"), ("b2_D2_WARM", "d_D2_WARM")):
        a = {r["question_id"]: r for r in good if r["cell"] == mine}
        t = {r["question_id"]: r for r in f3 if r["cell"] == theirs}
        k = sorted(set(a) & set(t))
        pair[f"{mine}_vs_32B_{theirs}"] = dict(
            n=len(k), same_prompt_tokens=sum(a[x]["prompt_tokens"] == t[x]["prompt_tokens"] for x in k),
            same_cached_tokens=sum((a[x]["cached_tokens"] or 0) == (t[x]["cached_tokens"] or 0) for x in k),
            ttft_ratio_32B_over_4B=quant([t[x]["ttft_s"] / a[x]["ttft_s"] for x in k]),
            ttft_4B=quant([a[x]["ttft_s"] for x in k]), ttft_32B=quant([t[x]["ttft_s"] for x in k]))
    b["pair_with_f3_32B"] = pair
    mon = [json.loads(l) for l in open(OUT / "e7_latency_monitor_h100nvl.jsonl")]
    b["exclusivity"] = dict(snapshots=len(mon), ours_outside_job=sum(bool(m["ours_outside_job"]) for m in mon),
                            foreign_on_gpu=sum(bool(m["foreign_on_gpu"]) for m in mon),
                            other_users_gpu=sorted({(p["user"], p["gpu_uuid"][:12]) for m in mon for p in m["gpu_procs"]}),
                            gpu_sm_clock_values=sorted({m["gpu_sm_util_mem"].split(",")[0] for m in mon}, key=int),
                            first=mon[0]["at"], last=mon[-1]["at"])
    res["job_b"] = b


def main():
    rng = np.random.default_rng(SEED)
    res = dict(label="StudyE7-d2-4b: 4B-Instruct on RH4 D2 (H100 GPU 2, vLLM 0.31.0); Job A accuracy, Job B latency "
               "(single request, localhost, max_tokens 8)")
    job_a(res, rng)
    if (OUT / "e7_latency_requests_h100nvl.jsonl").exists():
        job_b(res)
    arc = OUT / "e7_archive_summary.json"
    if arc.exists():
        res["job_c"] = {k: v for k, v in json.loads(arc.read_text()).items() if k != "_provenance"}
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e7_analyse.py", model="4BI", device="cpu", n=845)
    (OUT / "e7_results.json").write_text(json.dumps(res, indent=1, default=float))
    for k, v in res["accuracy"].items():
        if "/ALL" in k:
            print(k, round(v["est"] * 100, 1), [round(x * 100, 1) for x in v["ci"]], v["n"])


if __name__ == "__main__":
    main()
