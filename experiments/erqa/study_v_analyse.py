"""StudyV analysis — size-ladder timing on h100nvl, HF, flash_attention_2, batch 1. No accuracy.

Models: 4BI, 4BT, 8BI from StudyV; 8BT REUSED from StudyU (phase "natural", flash_attention_2); 32BI/32BT reference
rows from the committed StudyR-fa2 trials (same machine, same backend; no per-step stamps, so no position curve).
tok/s = n_generated / latency, bucketed by the trial's own n_generated. Position curves from per-step stamps.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402

BUCKETS = [("<2k", 0, 2000), ("2-8k", 2000, 8001), (">8k", 8001, 10**9)]
POS = [("0-500", 0, 500), ("500-2k", 500, 2000), ("2k-4k", 2000, 4000), ("4k-8k", 4000, 8000), ("8k+", 8000, 10**9)]
OUT = Path("results/erqa/study_v/study_v_results_h100nvl.json")


def q(x, p):
    return round(float(np.percentile(x, p)), 3) if len(x) else None


def main():
    trials, steps = [], {}
    for tp, sp, keep in (("results/erqa/study_v/study_v_trials_h100nvl.jsonl", "results/erqa/study_v/study_v_steps_h100nvl.jsonl",
                          lambda t: True),
                         ("results/erqa/study_u/study_u_trials_h100nvl.jsonl", "results/erqa/study_u/study_u_steps_h100nvl.jsonl",
                          lambda t: t["phase"] == "natural" and t["attn_implementation"] == "flash_attention_2")):
        ts = [t for t in map(json.loads, open(tp)) if keep(t)]
        ids = {t["trial_id"] for t in ts}
        trials += ts
        for s in read_jsonl(sp):
            if s["trial_id"] in ids:
                steps[s["trial_id"]] = np.array(s["step_ms"])
    assert all(t["attn_implementation"] == "flash_attention_2" for t in trials)
    ref32 = {}
    for r in map(json.loads, open("results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl")):
        ref32.setdefault({"C": "32BI", "D": "32BT"}[r["arm"]], []).append(
            dict(n=r["n_generated"], lat=r["total_latency_ms"] / 1000))
    res = {"models": {}}
    for m in ("4BI", "4BT", "8BI", "8BT"):
        v = [t for t in trials if t["model"] == m]
        x = np.array([t["n_generated"] for t in v])
        row = dict(n=len(v), source="StudyU natural (reused)" if m == "8BT" else "StudyV",
                   decoding=v[0]["decoding"], gen_p50=q(x, 50), gen_p90=q(x, 90), gen_max=int(x.max()),
                   budget_hits=sum(t["budget_hit"] for t in v), ttft_ms_p50=q([t["ttft_ms"] for t in v], 50),
                   decode_step_ms_p50=q([t["decode_ms_per_token_median"] for t in v if t["decode_ms_per_token_median"]], 50),
                   buckets={}, position={})
        for nm, lo, hi in BUCKETS:
            b = [t for t in v if lo <= t["n_generated"] < hi]
            row["buckets"][nm] = dict(n=len(b), tok_s=q([t["tok_s"] for t in b], 50),
                                      ms_per_token=q([t["ms_per_token"] for t in b], 50))
        for nm, lo, hi in POS:
            per = []
            for t in v:
                s = steps[t["trial_id"]]
                pos = np.arange(1, len(s) + 1)
                mk = (pos >= lo) & (pos < hi)
                if mk.sum() >= 20:
                    per.append(float(np.median(s[mk])))
            row["position"][nm] = dict(n=len(per), ms=q(per, 50))
        res["models"][m] = row
    for m, v in ref32.items():
        res["models"][m] = dict(n=len(v), source="StudyR-fa2 (committed; no per-step stamps)",
                                gen_p50=q([x["n"] for x in v], 50),
                                buckets={nm: dict(n=len(b), tok_s=q([x["n"] / x["lat"] for x in b], 50),
                                                  ms_per_token=q([x["lat"] * 1000 / x["n"] for x in b], 50))
                                         for nm, lo, hi in BUCKETS for b in [[x for x in v if lo <= x["n"] < hi]]})
    OUT.write_text(json.dumps(res, indent=1))
    print("| model | n | gen p50/max | <2k tok/s (n) | 2-8k tok/s (n) | >8k tok/s (n) | decode step ms p50 | TTFT ms |")
    for m, r in res["models"].items():
        b = r["buckets"]
        print(f"| {m} | {r['n']} | {r['gen_p50']}/{r.get('gen_max')} | " + " | ".join(
            f"{b[k]['tok_s']} ({b[k]['n']})" for k in ("<2k", "2-8k", ">8k")) +
            f" | {r.get('decode_step_ms_p50')} | {r.get('ttft_ms_p50')} |")
    print("\n| model | " + " | ".join(nm for nm, _, _ in POS) + " |")
    for m, r in res["models"].items():
        if "position" in r:
            print(f"| {m} | " + " | ".join(f"{c['ms']} ({c['n']})" for c in r["position"].values()) + " |")


if __name__ == "__main__":
    main()
