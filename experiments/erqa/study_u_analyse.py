"""StudyU analysis — timing only (no accuracy). CPU.

  * bucket table: tok/s and ms/token per trial (n_generated / latency), bucketed by the trial's OWN n_generated
    (<2k, 2-8k, >8k); natural traces only (forced probes are never pooled)
  * same-trial paired fa2/sdpa ratio (as for 32B)
  * ms/token vs generation POSITION (per-step timestamps): per trial, median step time in each position bin
    (0-500, 500-2k, 2k-4k, 4k-8k, 8k+), then median across trials (n = trials reaching the bin); per model, per
    backend, per phase (natural8 / forced8 / forced32)
  * per-trial slope of step time vs position (ms per 1k tokens of context), median across trials
  * weight-streaming floor = parameter bytes / HBM bandwidth (H100 NVL 3.9 TB/s)
Writes results/erqa/study_u/study_u_results_h100nvl.json and prints markdown tables.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402

D = Path("results/erqa/study_u")
TRIALS = D / "study_u_trials_h100nvl.jsonl"
STEPS = D / "study_u_steps_h100nvl.jsonl"
META = D / "study_u_run_meta_h100nvl.json"
OUT = D / "study_u_results_h100nvl.json"
BE = ("sdpa", "flash_attention_2")
SHORT = {"sdpa": "SDPA", "flash_attention_2": "FA2"}
LEN_BUCKETS = [("<2k", 0, 2000), ("2-8k", 2000, 8001), (">8k", 8001, 10**9)]
POS_BINS = [("0-500", 0, 500), ("500-2k", 500, 2000), ("2k-4k", 2000, 4000), ("4k-8k", 4000, 8000),
            ("8k+", 8000, 10**9)]
HBM_TBS = 3.9
PARAM_GB = {"8BT": 17.53, "32BT": None}  # filled from run meta when present


def q(x, p):
    return round(float(np.percentile(x, p)), 3) if len(x) else None


def main():
    trials = [json.loads(l) for l in open(TRIALS)]
    steps = {s["trial_id"]: np.array(s["step_ms"]) for s in read_jsonl(STEPS)}
    groups = {"natural8": [t for t in trials if t["phase"] == "natural"],
              "forced8": [t for t in trials if t["phase"] == "forced8"],
              "forced32": [t for t in trials if t["phase"] == "forced32"]}
    res = {"n_trials": {g: {b: sum(t["attn_implementation"] == b for t in v) for b in BE}
                        for g, v in groups.items()}}
    # data completeness
    res["missing"] = sum(1 for t in trials if t.get("n_generated") is None or not t.get("latency_ms"))
    res["step_count_mismatch"] = [t["trial_id"] for t in trials if t["n_step_stamps"] != t["n_generated"]]

    # ---- length distribution obtained (natural)
    nat = groups["natural8"]
    res["length_distribution_natural8"] = {
        SHORT[b]: dict(n=len(x), p10=q(x, 10), median=q(x, 50), p90=q(x, 90), max=int(max(x)) if len(x) else None,
                       n_budget_hit=sum(t["budget_hit"] for t in nat if t["attn_implementation"] == b),
                       n_by_bucket={nm: int(((x >= lo) & (x < hi)).sum()) for nm, lo, hi in LEN_BUCKETS})
        for b in BE for x in [np.array([t["n_generated"] for t in nat if t["attn_implementation"] == b])]}

    # ---- bucket table by own length
    tab = {}
    for nm, lo, hi in LEN_BUCKETS:
        row = {}
        for b in BE:
            v = [t for t in nat if t["attn_implementation"] == b and lo <= t["n_generated"] < hi]
            tps = np.array([t["tok_s"] for t in v])
            mpt = np.array([t["ms_per_token"] for t in v])
            dec = np.array([t["decode_ms_per_token_median"] for t in v if t["decode_ms_per_token_median"]])
            row[SHORT[b]] = dict(n=len(v), tok_s_median=q(tps, 50), tok_s_iqr=[q(tps, 25), q(tps, 75)],
                                 ms_per_token_median=q(mpt, 50), ms_per_token_iqr=[q(mpt, 25), q(mpt, 75)],
                                 decode_step_ms_median=q(dec, 50))
        if row["SDPA"]["n"] and row["FA2"]["n"]:
            row["fa2_over_sdpa_tok_s"] = round(row["FA2"]["tok_s_median"] / row["SDPA"]["tok_s_median"], 3)
        tab[nm] = row
    res["bucket_table_natural8"] = tab

    # ---- paired same-trial ratio
    idx = {b: {t["question_id"]: t for t in nat if t["attn_implementation"] == b} for b in BE}
    common = sorted(set(idx["sdpa"]) & set(idx["flash_attention_2"]))
    pr = {}

    def bk(n):
        return next(nm for nm, lo, hi in LEN_BUCKETS if lo <= n < hi)
    for mode in ("sdpa_len", "fa2_len", "same_bucket"):
        pr[mode] = {}
        for nm, _, _ in LEN_BUCKETS:
            sel = []
            for qid in common:
                s, f = idx["sdpa"][qid], idx["flash_attention_2"][qid]
                ok = {"sdpa_len": bk(s["n_generated"]) == nm, "fa2_len": bk(f["n_generated"]) == nm,
                      "same_bucket": bk(s["n_generated"]) == nm == bk(f["n_generated"])}[mode]
                if ok:
                    sel.append((f["tok_s"] / s["tok_s"], f["latency_ms"] / s["latency_ms"]))
            if sel:
                r = np.array(sel)
                pr[mode][nm] = dict(n=len(sel), tok_s_ratio_median=q(r[:, 0], 50),
                                    tok_s_ratio_iqr=[q(r[:, 0], 25), q(r[:, 0], 75)],
                                    wall_time_ratio_median=q(r[:, 1], 50))
    allr = np.array([idx["flash_attention_2"][k]["tok_s"] / idx["sdpa"][k]["tok_s"] for k in common])
    pr["all"] = dict(n=len(common), tok_s_ratio_median=q(allr, 50), iqr=[q(allr, 25), q(allr, 75)],
                     min=q(allr, 0), max=q(allr, 100))
    res["paired_natural8"] = pr

    # ---- position curves
    curves, slopes = {}, {}
    for g, v in groups.items():
        curves[g], slopes[g] = {}, {}
        for b in BE:
            vv = [t for t in v if t["attn_implementation"] == b]
            row = {}
            for nm, lo, hi in POS_BINS:
                per_trial = []
                pooled = []
                for t in vv:
                    s = steps[t["trial_id"]]          # s[j] = time to produce token j+2 (position j+1)
                    pos = np.arange(1, len(s) + 1)
                    m = (pos >= lo) & (pos < hi)
                    if m.sum() >= 20:
                        per_trial.append(float(np.median(s[m])))
                        pooled.append(s[m])
                pooled = np.concatenate(pooled) if pooled else np.array([])
                row[nm] = dict(n_trials=len(per_trial), median_ms=q(per_trial, 50),
                               trial_range=[q(per_trial, 0), q(per_trial, 100)],
                               pooled_steps=len(pooled), pooled_p10=q(pooled, 10), pooled_p90=q(pooled, 90))
            curves[g][SHORT[b]] = row
            sl = []
            for t in vv:
                s = steps[t["trial_id"]]
                if len(s) >= 1000:
                    pos = np.arange(1, len(s) + 1)
                    sl.append(np.polyfit(pos, s, 1)[0] * 1000)   # ms per 1k positions
            slopes[g][SHORT[b]] = dict(n_trials_ge1k=len(sl), median_ms_per_1k=q(sl, 50),
                                       range=[q(sl, 0), q(sl, 100)])
    res["position_curves"] = curves
    res["slopes_ms_per_1k_tokens"] = slopes

    # ---- weight floor
    meta = json.loads(META.read_text()) if META.exists() else {}
    for ph, key in (("eight", "8BT"), ("forced32", "32BT")):
        try:
            PARAM_GB[key] = meta[ph]["models"]["sdpa"]["param_bytes_gb"]
        except KeyError:
            pass
    res["weight_floor_ms"] = {k: (round(v / (HBM_TBS * 1e3) * 1e3, 2) if v else None) for k, v in PARAM_GB.items()}
    res["param_gb"] = PARAM_GB
    OUT.write_text(json.dumps(res, indent=1))

    # ---- print
    print("n trials:", res["n_trials"], "missing:", res["missing"], "step mismatch:", res["step_count_mismatch"])
    print("length distribution (natural 8B):", json.dumps(res["length_distribution_natural8"]))
    print("\n| bucket | SDPA n | SDPA tok/s | SDPA ms/tok | FA2 n | FA2 tok/s | FA2 ms/tok | FA2/SDPA |")
    print("|---|---|---|---|---|---|---|---|")
    for nm, r in tab.items():
        s, f = r["SDPA"], r["FA2"]
        print(f"| {nm} | {s['n']} | {s['tok_s_median']} | {s['ms_per_token_median']} | {f['n']} | "
              f"{f['tok_s_median']} | {f['ms_per_token_median']} | {r.get('fa2_over_sdpa_tok_s', '—')} |")
    print("\npaired:", json.dumps(pr, indent=None))
    for g in curves:
        print(f"\n### position curve {g} (median of per-trial median step ms; n trials)")
        print("| backend | " + " | ".join(nm for nm, _, _ in POS_BINS) + " | slope ms/1k |")
        for b in curves[g]:
            print(f"| {b} | " + " | ".join(f"{c['median_ms']} ({c['n_trials']})" for c in curves[g][b].values())
                  + f" | {slopes[g][b]['median_ms_per_1k']} (n={slopes[g][b]['n_trials_ge1k']}) |")
    print("\nweight floor ms/token:", res["weight_floor_ms"])


if __name__ == "__main__":
    main()
