#!/usr/bin/env python3
"""StudySLICE1 Part A analysis (CPU). Per session: monolithic engine time / rate (median of 5 repeats). Per chain (n):
total engine time, ratio to monolithic, computed tokens vs monolithic, wall time, longest single engine unit, final
letter vs monolithic. Per slice: overhead = engine time - computed tokens / the session's monolithic prefill rate;
prefix gap = previous prompt - cached. Gate (pre-registered): at n = 1,024 or 2,048 (same n): median per-slice
overhead <= 0.10 s AND median chain / monolithic engine ratio <= 1.25; AND final letters identical to monolithic in
>= 98 % of 40 sessions x 4 n. Writes results/cost/study_slice1/slice1_gate_results.json."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_slice1"
NS = (512, 1024, 2048, 4096)


def pct(x, q):
    x = [v for v in x if v is not None]
    return float(np.percentile(x, q)) if x else None


def main(prefix="slice1_gate"):
    rows = [json.loads(l) for l in open(OUT / f"{prefix}_requests_h100nvl.jsonl")]
    meta = json.load(open(OUT / f"{prefix}_run_meta_h100nvl.json"))
    by = defaultdict(list)
    for r in rows:
        by[(r["video_id"], r["target"])].append(r)       # one video can appear in both targets
    sess, slices = [], []
    for (vid, _tgt), rr in by.items():
        mono = [r for r in rr if r["mode"] == "mono"]
        if not mono:
            continue
        m_eng = float(np.median([r["engine_s"] for r in mono]))
        m_comp = float(np.median([r["computed_tokens"] for r in mono]))
        rate = m_comp / m_eng
        s = dict(video_id=vid, target=mono[0]["target"], prompt_tokens=mono[0]["prompt_tokens"],
                 n_frames=mono[0]["n_frames_total"], mono_engine_s=m_eng, mono_engine_all=[r["engine_s"] for r in mono],
                 mono_ttft_s=float(np.median([r["ttft_s"] for r in mono])), mono_rate_tok_s=rate,
                 mono_body_mb=mono[0]["body_bytes"] / 1e6, mono_letters=[r["letter"] for r in mono],
                 mono_cached_max=max(r["cached_tokens"] or 0 for r in mono), chains={})
        ref = mono[0]["letter"]
        for n in NS:
            ch = sorted([r for r in rr if r["mode"] == "chain" and r["n"] == n], key=lambda r: r["slice"])
            if not ch:
                continue
            eng = sum(r["engine_s"] or 0 for r in ch)
            gaps = [ch[i - 1]["prompt_tokens"] - (ch[i]["cached_tokens"] or 0) for i in range(1, len(ch))]
            for i, r in enumerate(ch):
                ov = r["engine_s"] - r["computed_tokens"] / rate if r["engine_s"] is not None else None
                slices.append(dict(video_id=vid, target=s["target"], n=n, slice=i, final=r["final"],
                                   engine_s=r["engine_s"], computed=r["computed_tokens"], overhead_s=ov,
                                   gap=gaps[i - 1] if i else None, body_mb=r["body_bytes"] / 1e6,
                                   queue_s=r["request_queue_time_s"]))
            s["chains"][str(n)] = dict(
                n_slices=len(ch), complete=ch[-1]["final"] and not any(r["error"] for r in ch),
                engine_s=eng, ratio=eng / m_eng, computed=sum(r["computed_tokens"] or 0 for r in ch),
                computed_ratio=sum(r["computed_tokens"] or 0 for r in ch) / m_comp,
                wall_s=ch[-1]["t_send"] + ch[-1]["latency_s"] - ch[0]["t_send"],
                wall_minus_pauses_s=sum(r["latency_s"] for r in ch),
                longest_unit_s=max(r["engine_s"] or 0 for r in ch),
                first_cached=ch[0]["cached_tokens"], gap_max=max(gaps) if gaps else None,
                gap_min=min(gaps) if gaps else None, letter=ch[-1]["letter"], letter_equal=ch[-1]["letter"] == ref,
                body_mb_total=sum(r["body_bytes"] for r in ch) / 1e6, errors=sum(bool(r["error"]) for r in ch))
        sess.append(s)
    per_n = {}
    for n in NS:
        cs = [s["chains"][str(n)] for s in sess if str(n) in s["chains"]]
        sl = [x for x in slices if x["n"] == n]
        per_n[str(n)] = dict(
            chains=len(cs), slices=len(sl),
            overhead_median_s=pct([x["overhead_s"] for x in sl], 50),
            overhead_p10_p90=[pct([x["overhead_s"] for x in sl], 10), pct([x["overhead_s"] for x in sl], 90)],
            overhead_median_nonfinal_s=pct([x["overhead_s"] for x in sl if not x["final"]], 50),
            ratio_median=pct([c["ratio"] for c in cs], 50), ratio_p90=pct([c["ratio"] for c in cs], 90),
            ratio_max=max(c["ratio"] for c in cs), frac_ratio_le_1p25=float(np.mean([c["ratio"] <= 1.25 for c in cs])),
            computed_ratio_median=pct([c["computed_ratio"] for c in cs], 50),
            longest_unit_median_s=pct([c["longest_unit_s"] for c in cs], 50),
            longest_unit_max_s=max(c["longest_unit_s"] for c in cs),
            wall_minus_pauses_ratio_median=pct([c["wall_minus_pauses_s"] / s["mono_ttft_s"] for s in sess
                                                 for c in [s["chains"].get(str(n))] if c], 50),
            letters_equal=sum(c["letter_equal"] for c in cs), gap_max=max(c["gap_max"] or 0 for c in cs),
            first_cached_max=max(c["first_cached"] or 0 for c in cs), errors=sum(c["errors"] for c in cs),
            by_target={str(t): dict(ratio_median=pct([s["chains"][str(n)]["ratio"] for s in sess
                                                       if s["target"] == t and str(n) in s["chains"]], 50),
                                    overhead_median_s=pct([x["overhead_s"] for x in sl if x["target"] == t], 50),
                                    longest_unit_median_s=pct([s["chains"][str(n)]["longest_unit_s"] for s in sess
                                                               if s["target"] == t and str(n) in s["chains"]], 50))
                       for t in (11000, 28000)})
    tot = sum(per_n[str(n)]["chains"] for n in NS)
    eq = sum(per_n[str(n)]["letters_equal"] for n in NS)
    cond = {str(n): dict(overhead_ok=per_n[str(n)]["overhead_median_s"] <= 0.10,
                         ratio_ok=per_n[str(n)]["ratio_median"] <= 1.25) for n in (1024, 2048) if str(n) in per_n}
    gate = dict(per_n_conditions=cond,
                cost_ok_at=[n for n, c in cond.items() if c["overhead_ok"] and c["ratio_ok"]],
                letters_equal=eq, letters_total=tot, letters_frac=eq / tot if tot else None,
                letters_ok=tot > 0 and eq / tot >= 0.98,
                mono_repeat_letters_consistent=sum(len(set(s["mono_letters"])) == 1 for s in sess), sessions=len(sess))
    gate["passed"] = bool(gate["cost_ok_at"]) and gate["letters_ok"]
    res = dict(label="StudySLICE1 Part A gate: prefix-chained slices vs monolithic cold D2 history prefill, 32B-I, "
                     "vLLM 0.31.0 E0, H100 GPU 2", sessions=sess, per_n=per_n, gate=gate, void=meta.get("void"),
               stack=meta.get("stack"))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_slice1_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / f"{prefix}_results.json").write_text(json.dumps(res, indent=1, default=float))
    for n in NS:
        p = per_n.get(str(n))
        if p:
            print(n, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items() if k != "by_target"})
            print("   ", p["by_target"])
    print("gate", json.dumps(gate))


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
