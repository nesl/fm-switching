#!/usr/bin/env python3
"""Host-tier KV turnover per cell (CPU only, read-only, no images; D240 1x and kv0.5r separate).

From each cell's host_counters_d211.log, the STEADY-STATE rate of vllm:kv_offload_store_bytes_total
over the MIDDLE 60% of the run (drop first and last 20% by time). Converted to tokens/s at
262,144 bytes/token; turnover time = 110,592 / rate tokens.

The planner reported 337 tokens/s for BOTH rung-3 1x s4 AND kv0.5r s4, which looks like a parsing
artefact (two memory levels with an identical rate is suspicious); this recomputes it honestly from
the raw counter and reports what the middle-60% slope actually is, with the sample points used.
"""
from __future__ import annotations
import glob, gzip, json, os, re, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

CELL_RE = re.compile(
    r"^(?P<arm>.+)_n16_s(?P<seed>[4-7])_1200s_h27_3t(?P<kv>_kv0\.5r)?_L3_epg_rq30(?P<rerun>_rerun)?$")
BYTES_PER_TOKEN = 262144
TURNOVER_TOKENS = 110592
STORE_RE = re.compile(r"vllm:kv_offload_store_bytes_total=([0-9.eE+]+)")
T_RE = re.compile(r"^t=([0-9.]+)")


def source_agreement(d):
    hp = os.path.join(d, "header.json")
    if not os.path.exists(hp):
        return "ABSENT"
    try:
        sa = json.load(open(hp)).get("source_agreement")
    except Exception:
        return "ABSENT"
    if sa is None:
        return "ABSENT"
    if isinstance(sa, dict):
        v = sa.get("verdict")
        return v if (isinstance(v, str) and v) else "ABSENT"
    return sa if isinstance(sa, str) else str(sa)


def valid_cells():
    groups = {}
    for d in sorted(set(glob.glob(str(RUNS / "*_rq30")) + glob.glob(str(RUNS / "*_rq30_rerun")))):
        m = CELL_RE.match(os.path.basename(d))
        if not m:
            continue
        agree = source_agreement(d)
        has_log = any(os.path.exists(os.path.join(d, f)) for f in
                      ("host_counters_d211.log", "host_counters_d211.log.gz"))
        groups.setdefault((m["arm"], int(m["seed"]), "kv0.5r" if m["kv"] else "1x"), []).append(
            {"dir": d, "name": os.path.basename(d), "agreement": agree,
             "invalid": agree.upper().startswith("INVALID"), "is_rerun": bool(m["rerun"]),
             "has_log": has_log})
    out = {}
    for key, cands in groups.items():
        elig = [c for c in cands if not c["invalid"] and c["has_log"]]
        if not elig:
            continue
        out[key] = sorted(elig, key=lambda c: c["is_rerun"], reverse=True)[0]
    return out


def parse_counter(d):
    """Deduped [(t, store_bytes)] where the counter line is present, sorted by t."""
    path = os.path.join(d, "host_counters_d211.log")
    opener, p = (open, path) if os.path.exists(path) else (gzip.open, path + ".gz")
    seen = {}
    with opener(p, "rt") as f:
        for line in f:
            mt = T_RE.match(line)
            ms = STORE_RE.search(line)
            if mt and ms:
                seen[float(mt.group(1))] = float(ms.group(1))
    return sorted(seen.items())


def middle60_rate(pts):
    """Bytes/s over the middle 60% of the time span (first/last point in that window)."""
    if len(pts) < 3:
        return None, None, None, None, 0
    t0, t1 = pts[0][0], pts[-1][0]
    span = t1 - t0
    lo, hi = t0 + 0.2 * span, t0 + 0.8 * span
    win = [(t, v) for t, v in pts if lo <= t <= hi]
    if len(win) < 2:
        return None, None, None, None, len(win)
    (ta, va), (tb, vb) = win[0], win[-1]
    dt = tb - ta
    rate_bytes = (vb - va) / dt if dt > 0 else None
    return rate_bytes, ta, tb, (vb - va), len(win)


def main():
    cells = valid_cells()
    res = {"1x": {}, "kv0.5r": {}}
    for (arm, seed, mem), info in sorted(cells.items()):
        pts = parse_counter(info["dir"])
        rate_bytes, ta, tb, dbytes, nwin = middle60_rate(pts)
        rate_tok = (rate_bytes / BYTES_PER_TOKEN) if rate_bytes is not None else None
        turnover = (TURNOVER_TOKENS / rate_tok) if (rate_tok and rate_tok > 0) else None
        res[mem][f"{arm}_s{seed}"] = {
            "arm": arm, "seed": seed, "agreement": info["agreement"],
            "n_counter_samples": len(pts), "n_window_samples": nwin,
            "window_t": [round(ta, 3), round(tb, 3)] if ta else None,
            "window_delta_bytes": dbytes,
            "rate_bytes_s": round(rate_bytes, 3) if rate_bytes is not None else None,
            "rate_tokens_s": round(rate_tok, 3) if rate_tok is not None else None,
            "turnover_s": round(turnover, 3) if turnover is not None else None,
            "store_first_last_bytes": [pts[0][1], pts[-1][1]] if pts else None,
        }
    out = {
        "_what": "Host-tier KV offload turnover per cell: steady-state "
                 "vllm:kv_offload_store_bytes_total rate over the middle 60% of the run. "
                 "D240: 1x and kv0.5r reported separately, never pooled.",
        "constants": {"bytes_per_token": BYTES_PER_TOKEN, "turnover_tokens": TURNOVER_TOKENS},
        "planner_claim_to_check": "337 tokens/s for BOTH rung-3 1x s4 and kv0.5r s4 (suspected "
                                  "parsing artefact)",
        "results": res,
    }
    out["_provenance"] = stamp(script="host_turnover.py", model="qwen3vl32b",
                               device="jetson_orin", n=sum(len(v) for v in res.values()))
    outdir = REPO / "results/orchestration/live2/robot_idle"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "host_turnover.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "host_turnover.json")
    for mem in ("1x", "kv0.5r"):
        r = res[mem].get("covex-v6-fair-final_s4")
        if r:
            print(f"  rung3 {mem} s4: rate_tokens_s={r['rate_tokens_s']} turnover_s={r['turnover_s']} "
                  f"(window dbytes={r['window_delta_bytes']}, nwin={r['n_window_samples']})")
    return out


if __name__ == "__main__":
    main()
