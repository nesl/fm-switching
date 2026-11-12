#!/usr/bin/env python3
"""
StudyD15 analysis — Part A (Orin vs H100 Nexar score stand-in validation) and
Part B (TTFT overhead decomposition). CPU only; reads committed results.

Part A:
  1. score agreement device(Orin) vs H100 4BI_N1 (Pearson, Spearman, median
     abs diff in log P(Yes), fraction abs>1);
  2. streaming AP at h=0/0.5/1/1.5/2 s (E9/E5 Part G method), Orin vs H100,
     paired clip bootstrap (2000, seed 0, stratified by label) -> diff CI/horizon;
  3. trigger agreement at E9's committed 4BI_N1 fold thresholds (5/10/20/40%);
  4. E9 primary escalation rerun with Orin device scores (study_e9_episodes run
     against an Orin-substituted trace), side by side with the committed E9;
     decision rules 1 and 2 recomputed.
  acceptance: adequate stand-in iff every AP diff CI includes 0 and E9's two
  decision-rule outcomes are unchanged.

Part B: TTFT decomposition per history size; per-frame handling vs microbench.
"""
import gzip, json, math, os, sys, tempfile, shutil
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
sys.path.insert(0, str(ROOT / "experiments/lib"))
import study_e9_episodes as e9  # noqa: E402

D15 = ROOT / "results/device/study_d15"
PARTA = D15 / "partA_scores.jsonl"
GREY = D15 / "partA_grey.jsonl"
PARTB = D15 / "partB_overhead.jsonl"
H100TRACE = ROOT / "results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz"
E9RESULTS = ROOT / "results/dashcam/study_e9/e9_results.json"
HORIZONS = (0.0, 0.5, 1.0, 1.5, 2.0)
SEED, NB = 0, 2000
TRIG_RATES = (0.05, 0.10, 0.20, 0.40)


def rankdata(a):
    a = np.asarray(a, float)
    sorter = np.argsort(a, kind="mergesort")
    inv = np.empty(len(a), int); inv[sorter] = np.arange(len(a))
    a_sorted = a[sorter]
    obs = np.r_[True, a_sorted[1:] != a_sorted[:-1]]
    dense = obs.cumsum()[inv]
    count = np.r_[np.nonzero(obs)[0], len(a)]
    return 0.5 * (count[dense] + count[dense - 1] + 1)


def pearson(x, y):
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    return pearson(rankdata(x), rankdata(y))


# ── load ─────────────────────────────────────────────────────────────────────
def load_device():
    rows = {}
    for l in open(PARTA):
        r = json.loads(l)
        rows[(r["file_name"], r["t"])] = r
    return rows


def load_h100_n1():
    h = {}
    with gzip.open(H100TRACE, "rt") as f:
        for line in f:
            r = json.loads(line)
            if str(r["model"]) == "4BI" and str(r["n"]) == "1":
                h[(r["file_name"], int(r["t"]))] = {"score": float(r["score"]), "p_yes": float(r["p_yes"])}
    return h


# ── Part A.1 score agreement ─────────────────────────────────────────────────
def score_agreement(dev, h100):
    keys = [k for k in h100 if k in dev]
    dv = []; hv = []; neither = 0; missing = 0
    for k in keys:
        drow = dev[k]
        if drow["score"] is None:
            neither += 1; continue
        dv.append(drow["score"]); hv.append(h100[k]["score"])
    dv = np.array(dv); hv = np.array(hv)
    diff = np.abs(dv - hv)
    return {
        "n_matched": len(keys), "n_scored": len(dv),
        "n_device_neither": neither,
        "pearson": round(pearson(dv, hv), 4), "spearman": round(spearman(dv, hv), 4),
        "median_abs_diff_logP": round(float(np.median(diff)), 4),
        "mean_abs_diff_logP": round(float(np.mean(diff)), 4),
        "frac_abs_diff_gt1": round(float(np.mean(diff > 1.0)), 4),
        "device_score_mean": round(float(dv.mean()), 4), "h100_score_mean": round(float(hv.mean()), 4),
    }


# ── build per-clip arrays + meta from the H100 trace (E9's exact structures) ──
def e9_structures():
    arrs, meta, clips = e9.load()           # uses committed H100 trace
    fold = e9.folds(clips, meta)
    return arrs, meta, clips, fold


def orin_arrays(dev, meta, clips):
    """Orin 4BI_N1 per-clip score arrays indexed from t=3 (must be complete/contiguous)."""
    a = {}
    miss = []
    for c in clips:
        T = meta[c]["T"]
        vals = []
        ok = True
        for t in range(3, T + 1):
            row = dev.get((c, t))
            if row is None or row["score"] is None:
                ok = False; break
            vals.append(row["score"])
        if ok:
            a[c] = np.array(vals)
        else:
            miss.append(c)
    return a, miss


# ── Part A.2 AP paired bootstrap (E9 method) ────────────────────────────────
def ap_paired(orin, h100arr, meta, clips):
    pos = [c for c in clips if meta[c]["label"] == "positive"]
    neg = [c for c in clips if meta[c]["label"] == "negative"]

    def tgt(c, h):
        T = meta[c]["T"]
        return int(min(max(round(meta[c]["event"] - h), 3), T)) - 3

    # positives per horizon, negatives concatenated (per arm)
    def arm_vecs(arr):
        P = [np.array([arr[c][tgt(c, h)] for c in pos]) for h in HORIZONS]
        N = np.concatenate([arr[c] for c in neg])
        return P, N
    Po, No = arm_vecs(orin)
    Ph, Nh = arm_vecs(h100arr)
    neg_len = np.array([len(orin[c]) for c in neg])
    off = np.concatenate([[0], np.cumsum(neg_len)])

    rng = np.random.default_rng(SEED)
    boots = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg))) for _ in range(NB)]
    neg_take = [np.concatenate([np.arange(off[j], off[j + 1]) for j in ni]) for _, ni in boots]

    out = {}
    for i, h in enumerate(HORIZONS):
        ap_o = e9.ap_from(Po[i], No); ap_h = e9.ap_from(Ph[i], Nh)
        diffs = np.empty(NB); bo = np.empty(NB); bh = np.empty(NB)
        for b, (pi, _ni) in enumerate(boots):
            nt = neg_take[b]
            o = e9.ap_from(Po[i][pi], No[nt]); hh = e9.ap_from(Ph[i][pi], Nh[nt])
            bo[b] = o; bh[b] = hh; diffs[b] = o - hh
        out[h] = {
            "ap_orin": round(ap_o, 5), "ci_orin": [round(float(np.percentile(bo, 2.5)), 5), round(float(np.percentile(bo, 97.5)), 5)],
            "ap_h100": round(ap_h, 5), "ci_h100": [round(float(np.percentile(bh, 2.5)), 5), round(float(np.percentile(bh, 97.5)), 5)],
            "diff_orin_minus_h100": round(ap_o - ap_h, 5),
            "diff_ci": [round(float(np.percentile(diffs, 2.5)), 5), round(float(np.percentile(diffs, 97.5)), 5)],
            "ci_includes_0": bool(np.percentile(diffs, 2.5) <= 0 <= np.percentile(diffs, 97.5)),
        }
    return out


# ── Part A.3 trigger agreement at committed E9 thresholds ───────────────────
def trigger_agreement(dev, h100, meta, clips, fold):
    e9res = json.load(open(E9RESULTS))
    thr = e9res["thresholds"]  # keys "4BI_N1/fold0", "fold1"
    out = {}
    for rate in TRIG_RATES:
        same = 0; tot = 0; both_hi = 0; dev_hi = 0; h100_hi = 0
        for c in clips:
            T = meta[c]["T"]
            tfold = thr[f"4BI_N1/fold{fold[c]}"]["trig"][str(rate)]
            for t in range(3, T + 1):
                drow = dev.get((c, t)); hrow = h100.get((c, t))
                if drow is None or hrow is None or drow["score"] is None:
                    continue
                do = drow["score"] >= tfold; dh = hrow["score"] >= tfold
                tot += 1; same += (do == dh)
                both_hi += (do and dh); dev_hi += do; h100_hi += dh
        out[f"{int(rate*100)}%"] = {
            "threshold_fold0": round(thr["4BI_N1/fold0"]["trig"][str(rate)], 4),
            "n_decisions": tot, "frac_same_side": round(same / tot, 4),
            "device_fire_rate": round(dev_hi / tot, 4), "h100_fire_rate": round(h100_hi / tot, 4),
            "both_fire_rate": round(both_hi / tot, 4),
        }
    return out


# ── Part A.4 E9 rerun with Orin device scores ───────────────────────────────
def build_orin_trace(dev, out_gz):
    """Copy the H100 trace; for 4BI N=1 rows, swap score+p_yes with Orin values."""
    n_sub = 0; n_miss = 0
    with gzip.open(H100TRACE, "rt") as f, gzip.open(out_gz, "wt") as g:
        for line in f:
            r = json.loads(line)
            if str(r["model"]) == "4BI" and str(r["n"]) == "1":
                k = (r["file_name"], int(r["t"]))
                drow = dev.get(k)
                if drow is None or drow["score"] is None:
                    n_miss += 1
                else:
                    r["score"] = drow["score"]
                    r["p_yes"] = drow["p_yes"] if drow["p_yes"] is not None else math.exp(drow["score"])
                    n_sub += 1
            g.write(json.dumps(r) + "\n")
    return n_sub, n_miss


def rule1_met_cells(e9res):
    """Decision rule 1: escalation-32B fewer invocations than escalation-4B,
    paired CI excluding 0, >=2 of 3 alarm-FPR, under measured@75 (setting ii)."""
    r1 = e9res["decision_rule_1_capability_shortens_episodes"]
    met = {}
    # group by (resolver, st, trig): count alarm-FPR levels with CI fully < 0 (32B fewer => diff<0)
    from collections import defaultdict
    groups = defaultdict(list)
    for key, v in r1.items():
        # key = "{rmodel}_N{rn}|{st}|far{far}|trig{trig}|q..|k..|L..|c.."
        parts = key.split("|")
        resolver = parts[0]; st = parts[1]; far = parts[2]; trig = parts[3]
        ci = v["all"]["ci"]
        excl0 = ci[1] < 0  # 32B strictly fewer invocations
        groups[(resolver, st, trig)].append(excl0)
    for (resolver, st, trig), flags in groups.items():
        met[f"{resolver}|{st}|{trig}"] = {"n_far_excl0": int(sum(flags)), "n_far": len(flags),
                                          "met_2of3": bool(sum(flags) >= 2)}
    return met


def rule2_met_count(e9res):
    """Decision rule 2 (report §8, pre-registered): escalation is efficient if it keeps AP
    within 0.01 of always-cloud at h <= 1 s (CIs overlapping) while using <= 50 % of
    always-cloud's cloud work, for a 32B resolver. 108 cells = 3 latency x 3 N x 3 FPR x 4 trig."""
    cells = e9res["cells"]; base = e9res["baselines"]
    met = 0; total = 0; met_keys = []
    for key, c in cells.items():
        if not c.get("is_primary_config") or "ap" not in c:
            continue
        resolver = c["resolver"]
        if not resolver.startswith("32BI"):
            continue
        st = c["latency"]; far = c["alarm_fpr"]
        ac_key = f"always-cloud/{resolver}|{st}|far{int(far*100)}"
        ac = base.get(ac_key)
        if ac is None:
            continue
        total += 1
        ok = True
        for h in (0.0, 0.5, 1.0):
            hk = str(float(h))
            ec = c["ap"].get(hk); ac_ap = ac["ap"].get(hk)
            if ec is None or ac_ap is None:
                ok = False; break
            gap = ec["ap"] - ac_ap["ap"]                       # escalation - always-cloud
            within = abs(gap) <= 0.01                           # within 0.01 of always-cloud
            overlap = (ec["ci"][1] >= ac_ap["ci"][0]) and (ac_ap["ci"][1] >= ec["ci"][0])
            if not (within and overlap):
                ok = False; break
        inv_esc = c["episodes"]["positive"]["invocations"] + c["episodes"]["negative"]["invocations"]
        inv_ac = ac["cloud"]["invocations"]
        work_ok = inv_ac > 0 and inv_esc <= 0.5 * inv_ac
        if ok and work_ok:
            met += 1; met_keys.append(key)
    return {"met": met, "total_cells_32B": total, "met_keys": met_keys}


def run_e9_orin(dev):
    tmpdir = D15 / "e9_orin"
    tmpdir.mkdir(exist_ok=True)
    orin_trace = tmpdir / "orin_trace.jsonl.gz"
    n_sub, n_miss = build_orin_trace(dev, orin_trace)
    print(f"[A4] orin trace: substituted {n_sub} 4BI_N1 rows, {n_miss} missing", flush=True)
    # redirect e9 to the orin trace + a temp OUT
    e9.TRACE = orin_trace
    e9.OUT = tmpdir
    e9.OUTFILE = "e9_results_orin.json"
    e9.main()
    orin_res = json.load(open(tmpdir / "e9_results_orin.json"))
    committed = json.load(open(E9RESULTS))
    r1_committed = rule1_met_cells(committed)
    r1_orin = rule1_met_cells(orin_res)
    r2_committed = rule2_met_count(committed)
    r2_orin = rule2_met_count(orin_res)
    # rule1 unchanged?
    r1_changes = []
    for k in r1_committed:
        if k in r1_orin and r1_committed[k]["met_2of3"] != r1_orin[k]["met_2of3"]:
            r1_changes.append({"cell": k, "committed": r1_committed[k], "orin": r1_orin[k]})
    # device-only baseline AP compare (measured@75 far5)
    def dev_only_ap(res):
        out = {}
        for key, v in res["baselines"].items():
            if key.startswith("device-only|"):
                out[key] = {h: v["ap"][h]["ap"] if h in v["ap"] else v["ap"].get(str(h)) for h in v["ap"]}
        return out
    return {
        "n_substituted": n_sub, "n_missing": n_miss,
        "rule1_committed": r1_committed, "rule1_orin": r1_orin,
        "rule1_met_changes": r1_changes, "rule1_unchanged": len(r1_changes) == 0,
        "rule2_committed": r2_committed, "rule2_orin": r2_orin,
        "rule2_unchanged": r2_committed["met"] == r2_orin["met"],
        "device_only_ap_committed": dev_only_ap(committed),
        "device_only_ap_orin": dev_only_ap(orin_res),
    }


# ── grey + latency + sanity ─────────────────────────────────────────────────
def grey_control():
    if not GREY.exists():
        return None
    rows = [json.loads(l) for l in open(GREY)]
    pys = [r["p_yes"] for r in rows if r["p_yes"] is not None]
    yes = sum(1 for r in rows if (r["first_token"] or "").strip().lower() == "yes")
    return {"n": len(rows), "yes_rate": round(yes / len(rows), 4),
            "median_p_yes": round(float(np.median(pys)), 8) if pys else None,
            "max_p_yes": round(max(pys), 6) if pys else None}


def latency_sanity(dev):
    rows = [r for r in dev.values()]
    ttft = sorted(r["ttft_s"] for r in rows if r["ttft_s"])
    total = sorted(r["total_s"] for r in rows if r["total_s"])
    cache_nonzero = sum(1 for r in rows if r.get("cache_n"))
    clk_bad = sum(1 for r in rows if not r.get("clock_ok"))
    neither = sum(1 for r in rows if r.get("neither"))
    toks = set(r["prompt_tokens"] for r in rows)

    def p(xs, q):
        return round(xs[min(len(xs) - 1, int(q * len(xs)))], 4) if xs else None
    return {
        "n": len(rows), "ttft_p50": p(ttft, .5), "ttft_p90": p(ttft, .9), "ttft_p99": p(ttft, .99),
        "total_p50": p(total, .5), "total_p90": p(total, .9),
        "d8_n1_ttft_p50_ref": 0.513, "d8_n1_total_p50_ref": 0.567,
        "cache_n_nonzero_rows": cache_nonzero, "clock_not_pinned_rows": clk_bad,
        "neither_rows": neither, "neither_frac": round(neither / len(rows), 5),
        "prompt_tokens_distinct": sorted(toks),
    }


# ── Part B ──────────────────────────────────────────────────────────────────
def part_b_analysis():
    if not PARTB.exists():
        return None
    import collections
    rows = [json.loads(l) for l in open(PARTB)]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["hist_frames"]].append(r)
    mb = None
    summ = json.load(open(D15 / "study_d15_summary.json")) if (D15 / "study_d15_summary.json").exists() else {}
    if summ.get("partB"):
        mb = summ["partB"].get("microbench")
    out = {"microbench": mb, "by_history": {}}
    for h in sorted(by):
        rs = by[h]
        def med(key):
            xs = sorted(x[key] for x in rs if x.get(key) is not None)
            return round(xs[len(xs) // 2], 4) if xs else None
        ttft = med("ttft_s"); prompt_ms = med("prompt_ms"); serialize = med("build_serialize_s")
        evaluated = med("evaluated"); cache_n = med("cache_n"); body_bytes = med("body_bytes")
        prompt_s = (prompt_ms / 1000.0) if prompt_ms is not None else None
        residual = None
        if ttft is not None and prompt_s is not None and serialize is not None:
            residual = round(ttft - prompt_s - serialize, 4)
        predicted = round(h * mb["median_s"], 4) if mb else None
        out["by_history"][h] = {
            "n": len(rs), "ttft_s": ttft, "build_serialize_s": serialize,
            "server_prompt_ms": prompt_ms, "evaluated_tok": evaluated, "cache_n": cache_n,
            "body_bytes": body_bytes, "residual_server_s": residual,
            "predicted_decode_s_n_frames_x_microbench": predicted,
            "residual_minus_predicted_s": (round(residual - predicted, 4) if (residual is not None and predicted is not None) else None),
            "ms_per_held_frame": (round(1000.0 * residual / h, 3) if residual is not None else None),
        }
    return out


def main():
    dev = load_device()
    h100 = load_h100_n1()
    print(f"device rows={len(dev)} h100 4BI_N1={len(h100)}", flush=True)
    arrs, meta, clips, fold = e9_structures()
    orin_arr, miss = orin_arrays(dev, meta, clips)
    print(f"orin per-clip arrays={len(orin_arr)} (missing {len(miss)})", flush=True)

    out = {"part_a": {}, "part_b": {}}
    out["part_a"]["score_agreement"] = score_agreement(dev, h100)
    print("agreement:", out["part_a"]["score_agreement"], flush=True)
    if len(miss) == 0:
        out["part_a"]["ap_paired"] = ap_paired(orin_arr, arrs[("4BI", 1)], meta, clips)
        out["part_a"]["ap_acceptance_all_ci_include_0"] = all(
            v["ci_includes_0"] for v in out["part_a"]["ap_paired"].values())
    out["part_a"]["trigger_agreement"] = trigger_agreement(dev, h100, meta, clips, fold)
    out["part_a"]["grey_control"] = grey_control()
    out["part_a"]["latency_sanity"] = latency_sanity(dev)
    out["part_a"]["escalation_rerun"] = run_e9_orin(dev)
    acc = (out["part_a"].get("ap_acceptance_all_ci_include_0", False)
           and out["part_a"]["escalation_rerun"]["rule1_unchanged"]
           and out["part_a"]["escalation_rerun"]["rule2_unchanged"])
    out["part_a"]["ACCEPTANCE_adequate_standin"] = bool(acc)

    out["part_b"] = part_b_analysis()

    json.dump(out, open(D15 / "study_d15_analysis.json", "w"), indent=2, default=str)
    print("\n=== ACCEPTANCE:", out["part_a"]["ACCEPTANCE_adequate_standin"], "===", flush=True)
    print("wrote", D15 / "study_d15_analysis.json", flush=True)


if __name__ == "__main__":
    main()
