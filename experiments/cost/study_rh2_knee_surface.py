#!/usr/bin/env python3
"""StudyRH2 — latency surface near R5's knee, with partial warm state (vLLM venv). Systems construction; no accuracy.

Everything not listed here is R5's, reused from study_r5_fleet (server: 32B-I @0cfaf481, vLLM 0.31.0, prefix caching
ON, bf16 KV, --enable-prompt-tokens-details, images <= 640 per prompt, 160x128 frames = 22 tok/frame, per-cell /
device / session text header; device plans: 234 videos shuffled with Random(0) and dealt round-robin over D, start
offsets from the same Random(0); 1x real-time replay; append every 10 s of session time = header + all frames so far,
max_tokens 1; escalation = header + frames + question, greedy, max_tokens 4; 15-minute window, then drain).

New in H2:
  P-HALF   devices with EVEN index are warm (warm-up upload + appends); ODD-index devices never append and escalate
           cold. Every record carries warm_device.
  rate 0.2 for each device, a random 20% (k = round(0.2 n)) of ALL the questions in its plan, drawn with Random(0)
           device by device. The subset depends only on D, so it is the same across policies.
  rep2     a second run of all three policies at D=12, rate 1.0, with the SAME seed (assignment, offsets, subset):
           pure run-to-run variance. (R5's rep2 used seed 1.)
  calib    before the grid: isolated (one at a time) requests on 4 sessions to price prefill on this server: a cold
           history upload, a 10-s append, and an escalation per session. A least-squares fit
           latency = a + b * computed_tokens gives the per-append GPU-time estimate (append GPU time is not observable
           per request under batching; the summed contended append latency is reported too).
Mechanism check (the first grid cell, P-HALF D=8 rate 1.0): warm devices' escalation token hit >= 0.80; cold devices
show no append-derived hits: every cold-device escalation's cached_tokens <= the prompt_tokens of the same device's
previous escalation in the same session (the only prefix a cold device creates; the R5 caveat), and <= 32 tokens on a
session's first escalation (at most the two 16-token blocks of chat template + cell-tag header that all devices in a
cell share; no frame content). Otherwise STOP.
"""
import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r5_fleet as F  # noqa: E402
import study_x_vllm as X  # noqa: E402
from rawio import read_jsonl  # noqa: E402

OUT = Path("results/cost/study_rh2")
REQ = OUT / f"study_rh2_requests_{X.DEV}.jsonl"
MET = OUT / f"study_rh2_metrics_{X.DEV}.jsonl"
X.META_PATH = OUT / f"study_rh2_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh2_current.json")
BUDGET_S = 9 * 3600
DS, RATES, POLICIES = (8, 12, 16, 24), (1.0, 0.2), ("COLD", "WARM", "HALF")


def tag(pol, D, rate, rep=1):
    return f"RH2_{pol}_D{D}_r{int(rate * 100):03d}" + (f"_rep{rep}" if rep > 1 else "")


MECH = ("HALF", 8, 1.0, 1)
GRID = [MECH] + [(p, D, r, 1) for D in DS for r in RATES for p in POLICIES if (p, D, r, 1) != MECH]
REP2 = [(p, 12, 1.0, 2) for p in POLICIES]


def warm(policy, d):
    return policy == "WARM" or (policy == "HALF" and d % 2 == 0)


class Cell(F.Cell):
    async def post(self, kind, dev, sess_i, sess, upto_s, question=None, qid=None, in_window=True):
        rec = await super().post(kind, dev, sess_i, sess, upto_s, question, qid, in_window)
        rec["warm_device"] = warm(self.policy, dev)
        return rec


def plan(D, seed=0):
    S = F.sessions()
    rng = random.Random(seed)
    order = list(range(len(S)))
    rng.shuffle(order)
    plans = [[S[order[j]] for j in range(d, len(order), D)] for d in range(D)]
    offsets = [rng.uniform(0, p[0]["duration"]) for p in plans]
    return plans, offsets


def esc_subset(plans, rate, seed=0):
    if rate >= 1.0:
        return None
    rng = random.Random(seed)
    sub = set()
    for p in plans:
        qs = [q["qid"] for s in p for q in s["questions"]]
        sub |= set(rng.sample(qs, int(round(rate * len(qs)))))
    return sub


async def device(cell, dev, plan_d, offset, window_end, subset):
    """F.device with a per-device warm flag and a fixed escalation subset."""
    s_i, sess, start_s = 0, plan_d[0], offset
    t_start = time.time()
    is_warm = warm(cell.policy, dev)
    while True:
        ev = []
        if is_warm:
            k0 = int(start_s // F.APPEND_EVERY_S) + 1
            ev += [(k * F.APPEND_EVERY_S, "append", None)
                   for k in range(k0, int(sess["duration"] // F.APPEND_EVERY_S) + 1)]
        ev += [(q["qt"], "escalation", q) for q in sess["questions"] if q["qt"] > start_s + 1e-6
               and (subset is None or q["qid"] in subset)]
        ev.sort(key=lambda e: (e[0], e[1] != "append"))
        for st, kind, q in ev:
            wall = t_start + (st - start_s)
            if wall > window_end:
                return
            await asyncio.sleep(max(0.0, wall - time.time()))
            cell.spawn(cell.post(kind, dev, s_i, sess, st, question=q and q["text"], qid=q and q["qid"]))
        t_start = t_start + (sess["duration"] - start_s)
        s_i += 1
        # implementation fix (2026-10-18 22:58, after cell 16): without this, a device whose remaining sessions hold
        # no events (common for cold devices at rate 0.2) slept through whole sessions after the window closed —
        # no requests were sent (each event checks window_end), but up to ~40 min of idle wall time per cell.
        if s_i >= len(plan_d) or t_start > window_end:
            return
        sess, start_s = plan_d[s_i], 0.0
        await asyncio.sleep(max(0.0, t_start - time.time()))


async def run_cell(pol, D, rate, rep, seed=0):
    t = tag(pol, D, rate, rep)
    plans, offsets = plan(D, seed)
    subset = esc_subset(plans, rate, seed)
    cell = Cell(t, pol, D, rate, seed)
    cell.t0 = time.time()
    stop = asyncio.Event()
    scr = asyncio.create_task(cell.scrape(stop))
    warm_devs = [d for d in range(D) if warm(pol, d)]
    if warm_devs:
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False)
                               for d in warm_devs))
    t_w0 = time.time()
    X.log(f"{t}: warm-up {t_w0 - cell.t0:.1f}s ({len(warm_devs)} warm devices); window starts")
    window_end = t_w0 + F.WINDOW_S
    await asyncio.gather(*(device(cell, d, plans[d], offsets[d], window_end, subset) for d in range(D)))
    n_inflight = len(cell.inflight)
    t_drain0 = time.time()
    if cell.inflight:
        await asyncio.gather(*list(cell.inflight))
    drain = time.time() - t_drain0
    stop.set()
    await scr
    await cell.client.aclose()
    meta = dict(policy=pol, D=D, esc_frac=rate, rep=rep, seed=seed, window_s=F.WINDOW_S,
                window_start=round(t_w0 - cell.t0, 2), warmup_s=round(t_w0 - cell.t0, 2),
                inflight_at_window_end=n_inflight, drain_s=round(drain, 1), warm_devices=warm_devs,
                n_subset=None if subset is None else len(subset),
                devices=[dict(device=d, videos=[s["video_id"] for s in plans[d]][:6], offset_s=round(offsets[d], 1))
                         for d in range(D)])
    with open(REQ, "a") as f:
        for r in cell.records:
            f.write(json.dumps(r) + "\n")
    with open(MET, "a") as f:
        f.write(json.dumps(dict(cell=t, timeline=cell.timeline)) + "\n")
    summ = {}
    for grp, wflag in (("warm", True), ("cold", False)):
        esc = [r for r in cell.records if r["kind"] == "escalation" and r["in_window"] and not r["error"]
               and r["warm_device"] == wflag]
        if esc:
            summ[grp] = dict(n=len(esc), hit=round(sum(r["cached_tokens"] or 0 for r in esc)
                                                   / max(1, sum(r["prompt_tokens"] or 0 for r in esc)), 4),
                             ttft_median=float(np.median([r["ttft_s"] for r in esc if r["ttft_s"]] or [np.nan])))
    X.log(f"{t}: {len(cell.records)} requests; {summ}; errors {sum(bool(r['error']) for r in cell.records)}; "
          f"inflight at end {n_inflight}; drain {drain:.0f}s")
    X.mark_done(t, **meta, summary=summ)
    return cell.records, summ


def mechanism_check(records, summ):
    esc = sorted((r for r in records if r["kind"] == "escalation" and not r["error"]),
                 key=lambda r: r["t_submit"])
    prev, viol, firsts = {}, [], []
    for r in esc:
        if r["warm_device"]:
            continue
        k = (r["device"], r["session"])
        if k in prev:
            if (r["cached_tokens"] or 0) > prev[k]:
                viol.append(r)
        else:
            firsts.append(r["cached_tokens"] or 0)
        prev[k] = r["prompt_tokens"] or 0
    warm_hit = summ.get("warm", {}).get("hit", 0)
    ok = warm_hit >= 0.80 and not viol and all(c <= 32 for c in firsts)
    res = dict(passed=ok, warm_escalation_token_hit=warm_hit,
               cold_escalation_token_hit=summ.get("cold", {}).get("hit"),
               cold_escalations=sum(1 for r in esc if not r["warm_device"]),
               cold_violations_cached_gt_prev_own_prompt=len(viol), cold_first_in_session_cached=firsts,
               warm_ttft_median=summ.get("warm", {}).get("ttft_median"),
               cold_ttft_median=summ.get("cold", {}).get("ttft_median"))
    X.log(f"MECHANISM CHECK (P-HALF D=8 rate 1.0): {res}")
    m = X.meta_load()
    m["mechanism_check"] = res
    X.meta_save(m)
    return ok


async def calib():
    """Isolated prefill pricing: per session, a cold upload at 300 s, a +10 s append, then an escalation."""
    S = F.sessions()
    long = [s for s in S if s["duration"] >= 320][:4]
    cell = Cell("RH2_calib", "WARM", 1, 1.0)
    cell.t0 = time.time()
    rows = []
    for i, s in enumerate(long):
        for kind, upto, q in (("calib_upload", 300.0, None), ("calib_append", 310.0, None),
                              ("calib_escalation", 310.0, s["questions"][-1]["text"])):
            r = await cell.post(kind, i, 0, s, upto, question=q, in_window=False)
            rows.append(r)
    await cell.client.aclose()
    ok = [r for r in rows if not r["error"]]
    x = np.array([(r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in ok], float)
    y = np.array([r["latency_s"] for r in ok], float)
    b, a = np.polyfit(x, y, 1)
    res = dict(a_s=float(a), b_s_per_token=float(b), prefill_tok_per_s=float(1 / b) if b > 0 else None,
               rows=[{k: r[k] for k in ("kind", "n_frames", "prompt_tokens", "cached_tokens", "ttft_s", "latency_s",
                                        "error")} for r in rows])
    X.log(f"calib: a={a:.3f}s b={b * 1e3:.4f} ms/token -> {res['prefill_tok_per_s']} tok/s; "
          f"{[(r['kind'], r['prompt_tokens'], r['cached_tokens'], r['latency_s']) for r in rows]}")
    m = X.meta_load()
    m["calib"] = res
    with open(REQ, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    X.meta_save(m)


def estimate(cells):
    """cells x (warm-up + 15 min + drain), drains from R5 (study_r5_run_meta): WARM D -> R5 WARM at D (linear in D
    between R5's points), HALF D -> R5 WARM at D/2 (its warm half), COLD -> R5 COLD at the nearest D; rate 0.2 uses
    the rate-1.0 drain (R5 D32: 1,330 vs 1,330 s)."""
    r5 = json.loads(Path("results/cost/study_r5/study_r5_run_meta_h100nvl.json").read_text())["experiments"]
    pts = {p: sorted((e["D"], e["drain_s"], e["warmup_s"]) for t, e in r5.items() if t.startswith(f"R5_{p}_D")
                     and e["esc_frac"] == 1.0 and "rep" not in t) for p in ("WARM", "COLD")}

    def interp(p, D):
        xs, ds, ws = zip(*pts[p])
        return float(np.interp(D, xs, ds)), float(np.interp(D, xs, ws))
    per = {}
    for pol, D, rate, rep in cells:
        drain, wu = interp("WARM", D) if pol == "WARM" else interp("WARM", D / 2) if pol == "HALF" else \
            interp("COLD", D)
        per[tag(pol, D, rate, rep)] = wu + F.WINDOW_S + drain
    return dict(per_cell_s=per, total_s=sum(per.values()) + 600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["estimate", "run"], required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cells = GRID + REP2
    est = estimate(cells)
    dropped = []
    while est["total_s"] > BUDGET_S and cells:
        drop = [c for c in cells if c[1] == 24 and c[2] == 0.2] or [c for c in cells if c[3] == 2]
        if not drop:
            break
        dropped += [tag(*c) for c in drop]
        cells = [c for c in cells if c not in drop]
        est = estimate(cells)
    X.log(f"RUNTIME ESTIMATE: {est['total_s'] / 3600:.2f} h for {len(cells)} cells; dropped {dropped}")
    m = X.meta_load()
    m["estimate"] = dict(est, n_cells=len(cells), dropped=dropped)
    X.meta_save(m)
    if args.stage == "estimate":
        return
    srv = X.Server("32BI", F.SERVER_EXTRA)
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        X.log(f"KV cache capacity: {info.get('kv_cache_tokens')} tokens")
        if "calib" not in X.meta_load():
            asyncio.run(calib())
        for c in cells:
            t = tag(*c)
            if X.is_done(t):
                continue
            recs, summ = asyncio.run(run_cell(*c))
            if c == MECH and not mechanism_check(recs, summ):
                raise SystemExit("MECHANISM CHECK FAILED (P-HALF D=8) — STOP")
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh2_knee_surface.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
