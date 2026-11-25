#!/usr/bin/env python3
"""D242 correlated multi-robot outage screen (1x ONLY; CPU, read-only, no images).

A MODEL-BASED SCREEN, NOT A MEASUREMENT: first-token times are predicted by the committed D162
model; the engine is not run. Extends reconnect_replay to k robots losing the link together.

For each rung-3 (covex-v6-fair-final) 1x cell, seeds 4 to 7, k in {1,3,5,7}, D in {60,120,180} s:
  - >=20 outage windows per cell, start times deterministic from the seed.
  - inside the window the k offline robots' questions are device-only (counted).
  - at reconnect each offline robot i has history H_i (its last prompt_tokens before the window) and
    backlog B_i = (D/2)*90 tokens.
  - GPU pool 62,944 tokens minus the measured non-robot working set at reconnect (resident KV of
    the live dashcam/single-shot sessions, estimated as the last prompt_tokens of each non-robot
    session active at that time). A robot history that does not fit the remaining pool is RELOADED
    from host and charged as uncached (reload = recompute; see assumption below).
  - D162: first_token = 0.0678 + 0.000182*uncached + 0.000154*queued_ahead, serving the k robots'
    catch-up IN ORDER; queued_ahead = the uncached catch-up of robots served before this one.
  Orderings:
    (a) FIFO by reconnect (robot-id order; all reconnect at the same instant);
    (b) earliest next question first (true next-question time, an ORACLE bound);
    (c) largest deficit first (1 - fraction of the robot's questions on time so far in the cell);
    (d) all histories evicted (baseline): U_i = H_i + B_i for every robot, FIFO order.
  Report P(first token within 3 s) per ordering, the (b) minus (a) gap (the most the counterfactual
  ordering can add), and the fraction of robot-windows where H_i + B_i exceeds the 32,768 context
  limit.

Reload-rate assumption: the cells DO show external-KV transfer activity (prompt_tokens_by_source
external_kv_transfer reaches ~1.8e6 tokens over a run), so an external-KV reload path exists and
would be CHEAPER than recompute. This screen deliberately charges a reloaded history as a full
uncached RE-PREFILL (H_i added to uncached), the WORST case, so the reload/evict P(within 3 s) is a
LOWER bound; the external-KV path would only raise it. Stated, not guessed.
"""
from __future__ import annotations
import glob, gzip, json, os, random, statistics, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

RUNG3 = "covex-v6-fair-final"
SEEDS = [4, 5, 6, 7]
KS = [1, 3, 5, 7]
OUTAGES = [60.0, 120.0, 180.0]
TOK_PER_FRAME = 90.0
GPU_POOL = 62944
CONTEXT_LIMIT = 32768
DEADLINE_S = 3.0
N_WINDOWS = 20
D162 = lambda unc, qa: 0.0678 + 0.000182 * unc + 0.000154 * qa  # noqa: E731


def agree(d):
    hp = os.path.join(d, "header.json")
    if not os.path.exists(hp):
        return "ABSENT"
    try:
        sa = json.load(open(hp)).get("source_agreement")
    except Exception:
        return "ABSENT"
    if sa is None:
        return "ABSENT"
    return (sa.get("verdict") or "ABSENT") if isinstance(sa, dict) else str(sa)


def cell_dir(seed):
    base = f"{RUNG3}_n16_s{seed}_1200s_h27_3t_L3_epg_rq30"
    for suf in ("_rerun", ""):
        d = RUNS / (base + suf)
        if (d / "request.jsonl.gz").exists() or (d / "request.jsonl").exists():
            return str(d) if not agree(str(d)).upper().startswith("INVALID") else None
    return None


def read_requests(d):
    for cand, op in ((os.path.join(d, "request.jsonl.gz"), gzip.open),
                     (os.path.join(d, "request.jsonl"), open)):
        if os.path.exists(cand):
            with op(cand, "rt") as f:
                return [json.loads(l) for l in f if l.strip()]
    return []


def non_robot_working_set(reqs, t):
    """Resident KV of live dashcam/single-shot sessions at t: last prompt_tokens of each non-robot
    session whose activity spans t. An ESTIMATE from the request log (stated in the header)."""
    sess = {}
    for r in reqs:
        dev = str(r.get("device_id", ""))
        if dev.startswith("robo"):
            continue
        sess.setdefault(r.get("session_id"), []).append(r)
    total = 0
    for rs in sess.values():
        rs.sort(key=lambda r: r["t_submit"])
        if rs[0]["t_submit"] <= t <= rs[-1].get("t_done", rs[-1]["t_submit"]):
            last = max((r for r in rs if r["t_submit"] <= t), key=lambda r: r["t_submit"],
                       default=None)
            if last:
                total += last.get("prompt_tokens") or 0
    return total


def main():
    per_cell = {}
    pooled = {}   # (k, D, ordering) -> [bool within3s]; and context-exceed list
    ctx_exceed = {}  # (k, D) -> [bool]
    device_only_counts = {}  # (k, D) -> [int]
    for seed in SEEDS:
        d = cell_dir(seed)
        if d is None:
            continue
        reqs = read_requests(d)
        robots = sorted({str(r["device_id"]) for r in reqs if str(r.get("device_id", "")).startswith("robo")})
        # per robot: sorted requests, and question list (opportunity_id not null)
        rq = {rb: sorted([r for r in reqs if str(r.get("device_id")) == rb], key=lambda r: r["t_submit"])
              for rb in robots}
        rqn = {rb: [r for r in rq[rb] if r.get("opportunity_id") is not None] for rb in robots}
        t_run = max((r.get("t_done", r["t_submit"]) for r in reqs), default=1200.0)
        rng = random.Random(seed)
        # >=20 deterministic window starts in the run interior; outage [t0, t0+D], reconnect t0+D
        starts = sorted(rng.uniform(60.0, t_run - max(OUTAGES) - 60.0) for _ in range(N_WINDOWS))
        for k in KS:
            offline = robots[:k]   # deterministic k-subset (robo000..)
            for D in OUTAGES:
                for t0 in starts:
                    rec = t0 + D
                    # per offline robot at this window
                    items = []
                    dev_only = 0
                    for rb in offline:
                        dev_only += sum(1 for r in rqn[rb] if t0 <= r["t_submit"] < rec)
                        before = [r for r in rq[rb] if r["t_submit"] < t0]
                        H = (before[-1].get("prompt_tokens") or 0) if before else 0
                        nxt = next((r for r in rqn[rb] if r["t_submit"] >= rec), None)
                        if nxt is None:
                            continue
                        # deficit so far: fraction of this robot's questions before t0 on time
                        prior = [r for r in rqn[rb] if r["t_submit"] < t0]
                        ontime = sum(1 for r in prior
                                     if ((r.get("t_first_token") or r.get("t_done")) - r["t_submit"]) <= DEADLINE_S)
                        deficit = 1.0 - (ontime / len(prior)) if prior else 1.0
                        items.append({"rb": rb, "H": H, "B": (D / 2.0) * TOK_PER_FRAME,
                                      "next_t": nxt["t_submit"], "deficit": deficit})
                    device_only_counts.setdefault((k, D), []).append(dev_only)
                    if not items:
                        continue
                    nrws = non_robot_working_set(reqs, rec)
                    pool_for_robots = max(0, GPU_POOL - nrws)
                    for it in items:
                        ctx_exceed.setdefault((k, D), []).append((it["H"] + it["B"]) > CONTEXT_LIMIT)

                    def serve(order_items, evict_all):
                        resident = 0
                        qa = 0.0
                        out = []
                        for it in order_items:
                            if evict_all:
                                U = it["H"] + it["B"]
                            else:
                                if resident + it["H"] <= pool_for_robots:
                                    U = it["B"]; resident += it["H"]       # warm
                                else:
                                    U = it["H"] + it["B"]                   # reload (re-prefill)
                            ft = D162(U, qa)
                            out.append(ft <= DEADLINE_S)
                            qa += U
                        return out

                    orders = {
                        "a_fifo": list(items),
                        "b_earliest_next_oracle": sorted(items, key=lambda x: x["next_t"]),
                        "c_largest_deficit": sorted(items, key=lambda x: -x["deficit"]),
                    }
                    for name, oi in orders.items():
                        for ok in serve(oi, evict_all=False):
                            pooled.setdefault((k, D, name), []).append(ok)
                    for ok in serve(list(items), evict_all=True):
                        pooled.setdefault((k, D, "d_all_evicted"), []).append(ok)

    def frac(xs):
        return round(sum(xs) / len(xs), 6) if xs else None

    results = {}
    for k in KS:
        for D in OUTAGES:
            key = f"k{k}_D{int(D)}"
            row = {ordr: frac(pooled.get((k, D, ordr), []))
                   for ordr in ("a_fifo", "b_earliest_next_oracle", "c_largest_deficit", "d_all_evicted")}
            pa, pb = row["a_fifo"], row["b_earliest_next_oracle"]
            row["b_minus_a_gap"] = (round(pb - pa, 6) if (pa is not None and pb is not None) else None)
            row["n_robot_windows"] = len(pooled.get((k, D, "a_fifo"), []))
            row["frac_ctx_exceeded"] = frac(ctx_exceed.get((k, D), []))
            row["mean_device_only_questions_in_window"] = (
                round(statistics.mean(device_only_counts.get((k, D), [0])), 3))
            results[key] = row

    out = {
        "_what": "D242 correlated multi-robot outage screen (rung-3 1x). MODEL-BASED SCREEN, NOT A "
                 "MEASUREMENT (D162 prediction, engine not run). 1x only.",
        "model": {"d162": "0.0678 + 0.000182*uncached + 0.000154*queued_ahead", "deadline_s": DEADLINE_S,
                  "gpu_pool_tokens": GPU_POOL, "context_limit": CONTEXT_LIMIT,
                  "tok_per_frame": TOK_PER_FRAME, "backlog": "(D/2)*90",
                  "non_robot_working_set": "sum of last prompt_tokens of live dashcam/ss sessions at "
                                           "reconnect (estimate from request log)",
                  "reload_assumption": "external-KV transfer path exists (external_kv_transfer ~1.8e6 "
                                       "tokens/run) and would be cheaper, but a history that does not "
                                       "fit is charged as full uncached re-prefill (worst case), so "
                                       "reload/evict P(within 3s) is a LOWER bound",
                  "queued_ahead": "uncached catch-up of robots served earlier in the order",
                  "orderings": {"a": "FIFO by reconnect (robot-id)", "b": "earliest next question "
                                "(oracle bound)", "c": "largest deficit first", "d": "all evicted"}},
        "n_windows_per_cell": N_WINDOWS, "seeds": SEEDS, "results": results,
    }
    out["_provenance"] = stamp(script="d242_correlated_outage.py", model="qwen3vl32b",
                               device="jetson_orin", n=sum(len(v) for v in pooled.values()))
    outdir = REPO / "results/orchestration/live2/robot_idle"
    (outdir / "d242_correlated_outage.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "d242_correlated_outage.json")
    for k in KS:
        for D in OUTAGES:
            r = results[f"k{k}_D{int(D)}"]
            print(f"  k={k} D={int(D)}: a={r['a_fifo']} b={r['b_earliest_next_oracle']} "
                  f"c={r['c_largest_deficit']} d={r['d_all_evicted']} b-a={r['b_minus_a_gap']} "
                  f"ctx_exceed={r['frac_ctx_exceeded']} n={r['n_robot_windows']}")
    return out


if __name__ == "__main__":
    main()
