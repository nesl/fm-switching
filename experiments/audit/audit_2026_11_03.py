#!/usr/bin/env python3
"""Recompute every number quoted in the 2026-11-03 written-record audit.

No inference. Reads committed result files only and writes
results/audit/audit_2026_11_03.json, so reports/audit_2026_11_03.md types no number
by hand. S-EMBER CIs use experiments/sember/study_o_q4_analyze.py's video-clustered
bootstrap at 2,000 resamples, seed 0, per the audit specification.
"""
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "sember"))
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from study_o_q4_analyze import clustered_bootstrap

NBOOT, BSEED = 2000, 0
OUT = ROOT / "results/audit/audit_2026_11_03.json"


def jl(rel):
    p = ROOT / rel
    op = gzip.open if str(p).endswith(".gz") else open
    with op(p, "rt") as f:
        return [json.loads(x) for x in f]


def ci(vals):
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def paired_delta(ids, vids, a_ok, b_ok, label):
    """100*(mean(a)-mean(b)) with a video-clustered bootstrap CI over the same questions."""
    a, b = np.asarray(a_ok, float), np.asarray(b_ok, float)
    v = np.asarray(vids)
    pt = 100.0 * (a.mean() - b.mean())
    boot = clustered_bootstrap(v, lambda idx: 100.0 * (a[idx].mean() - b[idx].mean()),
                               nboot=NBOOT, seed=BSEED)
    disc_a = int(((a == 1) & (b == 0)).sum())
    disc_b = int(((a == 0) & (b == 1)).sum())
    return dict(label=label, n=len(a), delta_pp=round(float(pt), 4), ci=ci(boot),
                mean_a_pct=round(100 * float(a.mean()), 4), mean_b_pct=round(100 * float(b.mean()), 4),
                discordant_a_only=disc_a, discordant_b_only=disc_b)


# ───────────────────────────────────────────────────────── strata ────
def build_strata():
    r1 = [r for r in jl("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")
          if r["mode"] == "batched"]
    K = defaultdict(dict)
    for r in r1:
        K[r["cell"]][r["question_id"]] = r
    c1 = {r["question_id"]: r for r in jl("results/device/accuracy_C1.jsonl")}

    ids = sorted(K["K1"])
    qt = {i: float(K["K1"][i]["question_time"]) for i in ids}
    ast = {i: float(c1[i]["answer_start_time"]) for i in ids}
    cov_k3 = {i: bool(K["K3"][i]["evidence_covered"]) for i in ids}
    vid = {i: K["K1"][i]["video_id"] for i in ids}

    strat = {}
    for i in ids:
        if qt[i] <= 120:
            strat[i] = "QT_LE_120"
        elif not cov_k3[i]:
            strat[i] = "OLDER"
        elif ast[i] < qt[i] - 120:
            strat[i] = "OVERLAP"
        else:
            strat[i] = "INSIDE"
    return ids, qt, ast, cov_k3, vid, strat, K, c1


def main():
    ids, qt, ast, cov_k3, vid, strat, K, c1 = build_strata()
    res = {"_meta": dict(nboot=NBOOT, bootstrap_seed=BSEED,
                         bootstrap="experiments/sember/study_o_q4_analyze.clustered_bootstrap "
                                   "(resamples VIDEOS with replacement)",
                         n_questions=len(ids))}

    counts = Counter(strat.values())
    res["strata"] = dict(
        definition="qt>120 only; OLDER = R1 K3 evidence_covered False; OVERLAP = covered and "
                   "answer_start_time < qt-120; INSIDE = covered and answer_start_time >= qt-120",
        counts={k: int(v) for k, v in counts.items()},
        n_qt_gt_120=int(sum(1 for i in ids if qt[i] > 120)),
        n_k3_uncovered_total=int(sum(1 for i in ids if not cov_k3[i])),
        n_k3_uncovered_with_qt_le_120=int(sum(1 for i in ids if not cov_k3[i] and qt[i] <= 120)),
        answer_start_time_source="results/device/accuracy_C1.jsonl",
        evidence_covered_source="results/sember/study_r1 K3 (batched)")

    def by_strata(fn_a, fn_b, label, subsets=("ALL", "OLDER", "OVERLAP", "INSIDE")):
        out = {}
        for s in subsets:
            sel = ids if s == "ALL" else [i for i in ids if strat[i] == s]
            if not sel:
                continue
            out[s] = paired_delta(sel, [vid[i] for i in sel],
                                  [fn_a(i) for i in sel], [fn_b(i) for i in sel], label)
        return out

    # (a) K1 - K3
    res["a_K1_minus_K3"] = by_strata(lambda i: bool(K["K1"][i]["correct"]),
                                     lambda i: bool(K["K3"][i]["correct"]),
                                     "K1(RICH) - K3(RECENT), 32B-I, H100, batched")
    # (b) C2 - C1
    c2 = {r["question_id"]: r for r in jl("results/device/accuracy_C2.jsonl")}
    res["b_C2_minus_C1"] = by_strata(lambda i: bool(c2[i]["correct"]),
                                     lambda i: bool(c1[i]["correct"]),
                                     "C2 - C1, 4B device (llama.cpp F16)")

    # (c) cross-stack: cloud 32B-I vs device-class 4B-I on the SAME questions
    o_rich = {r["question_id"]: r for r in jl("results/sember/study_o/study_o_q4_trials_4bi_rich_fa2.jsonl")}
    o_rec = {r["question_id"]: r for r in jl("results/sember/study_o/study_o_q4_trials_fa2.jsonl")
             if r["model_arm"] == "4B-I" and r["state_arm"] == "RECENT"}
    cids = sorted(set(ids) & set(o_rich) & set(o_rec))
    res["c_cross_stack"] = dict(
        note="CROSS-STACK: cloud arms are 32B-I on H100 via vLLM at temperature 0.0; the 4B-I "
             "comparators are HF transformers flash_attention_2 runs from Study O. Model size, "
             "serving stack and kernel all differ at once.",
        K1_minus_4BI_RICH=paired_delta(
            cids, [vid[i] for i in cids],
            [bool(K["K1"][i]["correct"]) for i in cids],
            [bool(o_rich[i]["correct"]) for i in cids],
            "K1 (32B-I RICH, H100 vLLM) - 4B-I RICH (Study O, HF fa2) [CROSS-STACK]"),
        K3_minus_4BI_RECENT=paired_delta(
            cids, [vid[i] for i in cids],
            [bool(K["K3"][i]["correct"]) for i in cids],
            [bool(o_rec[i]["correct"]) for i in cids],
            "K3 (32B-I RECENT, H100 vLLM) - 4B-I RECENT (Study O, HF fa2) [CROSS-STACK]"),
        n_frames_K1_median=float(np.median([K["K1"][i]["n_frames"] for i in cids])),
        n_frames_4BI_RICH_median=float(np.median([o_rich[i]["n_frames"] for i in cids])),
        n_frames_K3_median=float(np.median([K["K3"][i]["n_frames"] for i in cids])),
        n_frames_4BI_RECENT_median=float(np.median([o_rec[i]["n_frames"] for i in cids])))

    # (d) ERQA, same host, same kernel, same greedy decoding
    er = defaultdict(dict)
    for r in jl("results/erqa/study_r/study_r_trials_h100nvl.jsonl"):
        er[r["arm"]][r["question_id"]] = r
    eids = sorted(set(er["C"]) & set(er["A_h100"]))
    res["d_erqa_same_host"] = paired_delta(
        eids, eids,  # no video grouping on ERQA: each question is its own cluster
        [bool(er["C"][i]["correct"]) for i in eids],
        [bool(er["A_h100"][i]["correct"]) for i in eids],
        "ERQA 32B-I arm C - 4B-I arm A_h100 (both H100 NVL, sdpa, greedy) [SAME HOST]")
    res["d_erqa_same_host"]["bootstrap"] = "ordinary paired case bootstrap (one cluster per question)"

    # (e) MV-RoboBench, cross-host
    s2 = {r["path"]: r
          for r in jl("results/erqa/study_s2/study_s2_trials_h100nvl.jsonl") if r["arm"] == "C"}
    r4 = {r["qid"]: r
          for r in jl("results/erqa/r4_signals/r4_mvrobo_instruct.jsonl") if not r.get("oom")}
    k2 = sorted(set(s2) & set(r4))
    if k2:
        res["e_mvrobo_cross_host"] = paired_delta(
            k2, k2,
            [bool(s2[i]["correct"]) for i in k2],
            [bool(r4[i]["correct"]) for i in k2],
            "MV-RoboBench 32B-I arm C (H100 NVL, sdpa, greedy) - 4B-I R4 (RTX 3090 Ti, sdpa, "
            "greedy) [CROSS-HOST]")
        res["e_mvrobo_cross_host"]["bootstrap"] = "ordinary paired case bootstrap"
    else:
        res["e_mvrobo_cross_host"] = dict(
            error="no shared question key between study_s2 arm C and r4_mvrobo_instruct",
            s2_keys_sample=sorted(s2)[:3], r4_keys_sample=sorted(r4)[:3],
            s2_n=len(s2), r4_n=len(r4),
            unpaired_s2_acc=round(100 * np.mean([bool(v["correct"]) for v in s2.values()]), 4),
            unpaired_r4_acc=round(100 * np.mean([bool(v["correct"]) for v in r4.values()]), 4))

    # (j) 97 vs 105 uncovered
    dev_unc = {i for i in ids if not bool(c1[i]["evidence_covered"])}
    cl_unc = {i for i in ids if not cov_k3[i]}
    c2f = {r["question_id"]: r for r in jl("results/device/accuracy_C2.jsonl")}
    extra = sorted(dev_unc - cl_unc)
    rows = []
    for i in extra:
        d = c1[i]
        ft = sorted(float(x) for x in d["frame_timestamps"])
        gap = next(((a, b) for a, b in zip(ft, ft[1:])
                    if a <= d["answer_start_time"] and b >= d["answer_end_time"]), None)
        rows.append(dict(question_id=i, question_time=d["question_time"],
                         answer_start_time=d["answer_start_time"],
                         answer_end_time=d["answer_end_time"],
                         answer_duration_s=round(d["answer_end_time"] - d["answer_start_time"], 3),
                         device_n_frames=d["n_frames"], cloud_K3_n_frames=K["K3"][i]["n_frames"],
                         device_mean_stride_s=round(float(np.mean(np.diff(ft))), 3),
                         straddling_device_frame_gap=gap,
                         stratum=strat[i]))
    res["j_uncovered_97_vs_105"] = dict(
        cloud_K3_uncovered=len(cl_unc), device_C1_uncovered=len(dev_unc),
        device_C3_uncovered=int(sum(1 for r in jl("results/device/accuracy_C3.jsonl")
                                    if not r["evidence_covered"])),
        device_RICH_C2_uncovered=int(sum(1 for r in c2f.values() if not r["evidence_covered"])),
        cloud_RICH_K1_uncovered=int(sum(1 for i in ids if not bool(K["K1"][i]["evidence_covered"]))),
        cloud_uncovered_not_in_device=len(cl_unc - dev_unc),
        explanation="Both arms use the same 120 s RECENT window, so the 8 extra are NOT a window "
                    "difference. They are a frame-SAMPLING-DENSITY difference: the device samples "
                    "37 frames across the 120 s window (mean stride 3.33 s) while cloud K3 samples "
                    "121 frames at ~1 fps. All 8 have answer intervals of only 1-2 s, and in every "
                    "case a single device frame gap straddles the whole interval, so the evidence "
                    "lies inside the window but between two sampled frames. evidence_covered is "
                    "therefore a property of the ARM's frame budget, not of the question.",
        extra_8=rows,
        n_answer_intervals_le_2s_all845=int(sum(
            1 for i in ids if c1[i]["answer_end_time"] - c1[i]["answer_start_time"] <= 2)))

    # ---------------------------------------------------------------- RH7 / RH8
    rh7 = jl("results/cost/study_rh7/study_rh7_requests_h100nvl.jsonl.gz")
    rh8 = jl("results/cost/study_rh8/study_rh8_requests_h100nvl.jsonl.gz")
    qt_map = {i: qt[i] for i in ids}

    # (f) EAGER in-window escalation fallbacks
    fcell = {}
    for D in (32, 48, 64, 96):
        e = [x for x in rh7 if x["cell"] == f"RH7_EAGER_D{D}"
             and x["kind"] == "escalation" and x["in_window"]]
        fb = [x for x in e if x["fallback"]]
        g10 = [x for x in e if qt_map.get(x["question_id"], -1) % 10 == 0]
        fb10 = [x for x in g10 if x["fallback"]]
        fcell[f"D{D}"] = dict(
            n_in_window_escalations=len(e), n_fallback=len(fb),
            fallback_share_pct=round(100 * len(fb) / len(e), 2),
            body_mb_total=round(sum(x["body_mb"] or 0 for x in e), 1),
            body_mb_fallback=round(sum(x["body_mb"] or 0 for x in fb), 1),
            fallback_body_share_pct=round(
                100 * sum(x["body_mb"] or 0 for x in fb) / sum(x["body_mb"] or 0 for x in e), 2),
            qt_mod10_eq0_n=len(g10), qt_mod10_eq0_fallback=len(fb10),
            qt_mod10_eq0_fallback_share_pct=round(100 * len(fb10) / len(g10), 2) if g10 else None,
            fallback_set_equals_qt_mod10_set=bool({x["question_id"] for x in fb}
                                                  == {x["question_id"] for x in g10}))
    res["f_rh7_eager_fallbacks"] = dict(
        per_D=fcell,
        n_questions_with_qt_mod10_eq0=int(sum(1 for v in qt_map.values() if v % 10 == 0)),
        n_questions_total=len(qt_map),
        finding="Fallbacks are not spread across questions: at D32/D48/D64 the fallback set is "
                "EXACTLY the set of questions whose question_time is a multiple of 10 s "
                "(45/45, 57/57, 81/81). The fallback is a deterministic property of the "
                "question's frame schedule, not a cache-pressure effect.")

    # (g) RH7 LAZY D64 tail, and RH8 D96 MIX-DEMAND vs best rival
    def tails(rows, cell, origin=None, cut=None):
        e = [x for x in rows if x["cell"] == cell and x["kind"] == "escalation"
             and x["in_window"] and x.get("ttft_s") is not None]
        if cut is not None:
            w = np.array([x[origin] for x in e], float)
            w = w - w.min()
            e = [x for x, keep in zip(e, w >= cut) if keep]
        t = np.array([x["ttft_s"] for x in e], float)
        return dict(n=len(t), p50=round(float(np.percentile(t, 50)), 3),
                    p99=round(float(np.percentile(t, 99)), 3),
                    within_5s_pct=round(100 * float((t <= 5).mean()), 2))

    gres = dict(rh7_LAZY_D64=tails(rh7, "RH7_LAZY_D64"),
                rh7_LAZY_D64_excl_first120s_wallclock=tails(rh7, "RH7_LAZY_D64", "t_submit", 120.0))
    for label, origin, cut in [("all", None, None),
                               ("excl_first_120s_wallclock", "t_submit", 120.0),
                               ("excl_session_t_lt_120", None, None)]:
        cells_ = {}
        for pol in ("ALL-EAGER", "ALL-LAZY", "MIX-RANDOM", "MIX-DEMAND"):
            cn = f"RH8_{pol}_D96"
            if label == "excl_session_t_lt_120":
                e = [x for x in rh8 if x["cell"] == cn and x["kind"] == "escalation"
                     and x["in_window"] and x.get("ttft_s") is not None and x["session_t"] >= 120]
                t = np.array([x["ttft_s"] for x in e], float)
                cells_[pol] = dict(n=len(t), p50=round(float(np.percentile(t, 50)), 3),
                                   p99=round(float(np.percentile(t, 99)), 3),
                                   within_5s_pct=round(100 * float((t <= 5).mean()), 2))
            else:
                cells_[pol] = tails(rh8, cn, origin, cut)
        riv = {k: v["within_5s_pct"] for k, v in cells_.items() if k != "MIX-DEMAND"}
        best = max(riv, key=riv.get)
        gres[f"rh8_D96_{label}"] = dict(
            cells=cells_, best_rival=best,
            mix_demand_minus_best_rival_pp=round(cells_["MIX-DEMAND"]["within_5s_pct"] - riv[best], 2))
    gres["definition_note"] = ("'without the first 120 s' is the WALL-CLOCK window start "
                               "(t_submit minus the cell's first t_submit), which reproduces the "
                               "+6.3 pp figure. Excluding by session_t >= 120 instead gives "
                               "+12.09 pp - a different quantity. The metric is the fraction of "
                               "in-window escalations with TTFT <= 5 s.")
    res["g_rh7_lazy_tail_and_rh8_mix_demand"] = gres

    # (h) DevFast 4B-I TTFT, warm first row of each cell excluded
    hres = {}
    for N in (37, 18, 9):
        rows = jl(f"results/device/devfast_4bi_f16_n{N}.jsonl")
        first, rest = rows[0], rows[1:]
        pm = np.array([x["prefill_ms"] for x in rest], float)
        tt = np.array([x["ttft_s"] for x in rest], float)
        it = np.array([x["input_tokens"] for x in rest], float)
        hres[f"N{N}"] = dict(
            n_rows=len(rows), n_used=len(rest),
            excluded_first_row=dict(ttft_s=first["ttft_s"], input_tokens=first["input_tokens"],
                                    prefill_ms=first["prefill_ms"], n_frames=first["n_frames"]),
            ttft_s_median_excl_first=round(float(np.median(tt)), 3),
            ttft_s_mean_excl_first=round(float(np.mean(tt)), 3),
            ttft_s_median_incl_first=round(float(np.median([x["ttft_s"] for x in rows])), 3),
            ttft_s_mean_incl_first=round(float(np.mean([x["ttft_s"] for x in rows])), 3),
            input_tokens_median=int(np.median(it)),
            prefill_ms_median=round(float(np.median(pm)), 1),
            prefill_ms_per_token_median=round(float(np.median(pm / it)), 4),
            ttft_ms_per_token_median=round(float(np.median(1000 * tt / it)), 4),
            prefill_share_of_ttft_pct=round(100 * float(np.median(pm / (1000 * tt))), 2),
            rows_by_actual_n_frames={str(k): int(v) for k, v in
                                     sorted(Counter(x["n_frames"] for x in rows).items())})
    hres["note"] = ("The first row of every cell has input_tokens = 1 and prefill_ms 57-64 ms: it "
                    "is a warm-up row carrying no frames, not an N-frame prefill. The expected "
                    "16.98 / 7.76 / 3.80 s are MEDIANS with it excluded. n_frames does NOT always "
                    "equal N: at N=37 only 95/120 rows carry 37 frames (20 carry 36, 5 carry "
                    "14-35); at N=18, 119/120; at N=9, 120/120.")
    res["h_devfast_4bi_ttft"] = hres

    # (i) D2 uplink as actually sent
    FRAG_PRE = len(b'{"type": "image_url", "image_url": {"url": "data:image/png;base64,')
    FRAG_SUF = len(b'"}}')
    ires = {}
    for tag, rows in (("RH7", rh7), ("RH8", rh8)):
        ap = [x for x in rows if x["kind"] == "append" and x.get("n_new_frames")
              and x.get("new_frames_mb")]
        nf = np.array([x["n_new_frames"] for x in ap], float)
        nb = np.array([x["new_frames_mb"] for x in ap], float) * 1e6
        per_frame = nb / nf
        b64 = per_frame - (FRAG_PRE + FRAG_SUF)
        dev_tot = defaultdict(float)
        for x in rows:
            if x["in_window"] and x.get("body_mb"):
                dev_tot[(x["cell"], x["device"])] += x["body_mb"]
        per_cell = defaultdict(list)
        for (cell_, _), v in dev_tot.items():
            per_cell[cell_].append(v)
        ires[tag] = dict(
            fmt=sorted({str(x.get("fmt")) for x in rows}),
            body_mode=sorted({str(x.get("body_mode")) for x in rows}),
            n_appends_with_new_frames=len(ap),
            n_new_frames_per_append_median=float(np.median(nf)),
            bytes_per_frame_sent_median_kB=round(float(np.median(per_frame)) / 1e3, 2),
            append_body_MB_median=round(float(np.median([x["body_mb"] for x in ap])), 4),
            new_frames_MB_median=round(float(np.median([x["new_frames_mb"] for x in ap])), 4),
            base64_overhead_share_of_frame_bytes_pct=round(
                100 * float(np.median((b64 / 4) / per_frame)), 2),
            raw_png_bytes_per_frame_median_kB=round(float(np.median(b64 * 0.75)) / 1e3, 2),
            json_envelope_bytes_per_frame=FRAG_PRE + FRAG_SUF,
            mean_uplink_MB_per_active_device={
                k: round(float(np.mean(v)), 1) for k, v in sorted(per_cell.items())})
    ires["note"] = ("body_mb is len(HTTP body)/1e6 - the actual bytes on the wire (MB, not MiB). "
                    "Frames are PNG, base64-encoded into a data: URL "
                    "(study_rh6_offload_knee.py:85), so base64 inflates the raw PNG by 4/3 and "
                    "accounts for 25% of every frame byte sent. All RH7/RH8 records are fmt=D2.")
    res["i_d2_uplink"] = ires

    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps(res, indent=1)[:4000])
    print("->", OUT)


if __name__ == "__main__":
    main()
