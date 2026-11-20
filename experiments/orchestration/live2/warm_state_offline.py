#!/usr/bin/env python3
"""OFFLINE WARM-STATE STUDY (user, 2026-11-20): what a warming policy could have bought.

CPU only, committed traces, no engine and no policy code. This is a DESIGN INPUT for the C6
redesign, not a result about any arm that ran.

THE QUESTION. Section 12 measured that no robot question in the whole grid was ever served warm
(0 prefix-cache hits against 5.2 to 5.6 million queries per cell, cached_tokens 0 on every robot
request), that robot misses are dominated by history prefill, and that a prefill-on-arrival of each
30 s upload batch would have had 97.8 to 98.7 percent of each question's history already in cache.
This asks the next question: under real memory capacities, how much of that is actually keepable,
and how much does WHICH history you keep matter.

REGISTERS, stated once and then marked per column.
  MEASURED    nothing here. Not one number in this file was produced by running an arm.
  TRACE       taken from the committed trace: session starts and ends, the 30 s history batches with
              their own token counts, and each robot question's history tokens and deadline. The
              traces are regenerated locally and are byte-identical in these fields to the ones the
              grid ran (the same regeneration reproduced the H100's robot opportunity ids exactly,
              section 14).
  MODELLED    time and cost from the committed cost curves (costs.recall_ttft_s / recall_gpu_s,
              StudyRH5), never a measured latency.
  CONSTRUCTED the policies themselves, the capacities below the committed pair, and the oracle.

THE COMPOSITION RULE for a partially resident history, which is the one modelling choice that is
not simply the committed curve. A history of h tokens with c of them resident at tier X costs
    recall_ttft_s(c, X) + recall_ttft_s(h - c, "COLD")
so it reduces to the committed warm number at c = h and to the committed cold number at c = 0. The
HOST-WARM curve already includes the reload (StudyRH5 measured it that way), so a host hit is
charged its reload here.

WHAT THE SIMULATION IS GENEROUS ABOUT, so that the numbers are read as an upper bound on warming's
value rather than a prediction:
  1. The whole GPU pool and the whole host tier are given to robot histories. In the live runs they
     also hold the dashcam and single-shot working set.
  2. A prefill of a batch is charged its GPU seconds but never queues behind anything: warming is
     free in TIME here, and only its GPU-seconds total is reported.
  3. On-time is TTFT against the 5 s deadline, with a second column that adds the measured 0.74 s
     p50 of waiting plus queueing from section 12.1. Decode is excluded in both.

POLICIES.
  P0  no warming, as the grid ran: every question pays a cold rebuild.
  P1  warm every batch on arrival, evict by LEAST RECENTLY USED, GPU to host to cold.
  P2  warm every batch, evict the session with the lowest P(question within T), T in 60, 120, 300 s.
      P comes from a two-parameter hazard fitted on SEED 0, which is NOT in the evaluation set
      (seeds 4, 5, 6), so the fit and the score never share data (D6). The policy also reads each
      session's own declared duration, which `session_start` carries in the trace, so a session past
      its end has probability 0. That is an assumption about what a deployed policy would know and
      it is stated rather than hidden: without it P2 cannot distinguish a dead session from a quiet
      one, and with it P2 gets information LRU does not have.
  P3  oracle: keeps exactly the histories whose next question is soonest. An upper bound, not a
      policy; it reads the future.
"""
from __future__ import annotations

import json
import math
import statistics as stat
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (HERE, HERE / "fleet", REPO / "experiments/orchestration/baselines",
           REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import costs as C                                                            # noqa: E402
import trace as TR                                                           # noqa: E402

OUT = REPO / "results/orchestration/live2/frozen_test/warm_state_offline.json"

GPU_TOKENS, HOST_TOKENS = 62944, 110592        # the committed pair
CAP_SCALES = (1.0, 0.5, 0.25)                  # D56: capacities are inputs
EVAL_SEEDS = (4, 5, 6)
FIT_SEED = 0
SIZES = (16, 18)
RUN_S, RATIO = 1200.0, "40:40:20"
ROB_L = 5.0
QUEUE_ALLOWANCE_S = 0.74       # section 12.1: p50 wait 0.12 plus p50 queue residual 0.62, on-time rows
T_HORIZONS = (60.0, 120.0, 300.0)


def events(seed, n):
    """TRACE: the robot sessions, their 30 s batches and their questions."""
    t = TR.generate_trace(seed, n, RATIO, RUN_S, "A",
                          robot_question_set="lh_req", ss_question_set="ss2")
    recs = t["records"] if isinstance(t, dict) else t
    ses, batches, questions = {}, [], []
    for r in recs:
        if not str(r.get("device_id", "")).startswith("robo"):
            continue
        k = r.get("kind")
        if k == "session_start":
            ses[r["session_id"]] = dict(start=float(r["t"]), end=None,
                                        declared_end=float(r["t"]) + float(r.get("duration_s") or 0.0)
                                        - float(r.get("join_offset_s") or 0.0))
        elif k == "session_end":
            if r["session_id"] in ses:
                ses[r["session_id"]]["end"] = float(r["t"])
        elif k == "history_preload":
            batches.append(dict(t=float(r["t"]), sid=r["session_id"], new=int(r.get("est_tokens") or 0),
                                cum=int(r.get("cum_tokens") or 0), preload=True))
        elif k == "history_batch":
            batches.append(dict(t=float(r["t"]), sid=r["session_id"], new=int(r.get("est_tokens") or 0),
                                cum=int(r.get("cum_tokens") or 0), preload=False))
        elif k == "recall_question":
            questions.append(dict(t=float(r["t"]), sid=r["session_id"], opp=r["opportunity_id"],
                                  h=int(r.get("history_tokens") or 0),
                                  deadline=float(r.get("deadline_s") or ROB_L)))
    return ses, sorted(batches, key=lambda x: x["t"]), sorted(questions, key=lambda x: x["t"])


def fit_hazard():
    """P2's question process, fitted on SEED 0 only (never on 4, 5, 6).

    Two rates, because the only conditioning variable the trace offers at decision time is how many
    questions a session has already had: lam0 for a session not yet asked, lam1 for one already
    asked. Each is questions per active session-second, so P(question within T) = 1 - exp(-lam T).
    """
    num = {0: 0, 1: 0}
    den = {0: 0.0, 1: 0.0}
    for n in SIZES:
        ses, _, qs = events(FIT_SEED, n)
        byses = defaultdict(list)
        for q in qs:
            byses[q["sid"]].append(q["t"])
        for sid, s in ses.items():
            end = s["end"] if s["end"] is not None else RUN_S
            ts = sorted(byses.get(sid, []))
            # the stretch before the first question is exposure for lam0, the rest for lam1
            first = ts[0] if ts else end
            den[0] += max(first - s["start"], 0.0)
            num[0] += 1 if ts else 0
            den[1] += max(end - first, 0.0)
            num[1] += max(len(ts) - 1, 0)
    lam = {k: (num[k] / den[k] if den[k] > 0 else 0.0) for k in (0, 1)}
    return dict(lam_not_yet_asked=lam[0], lam_already_asked=lam[1],
                n_first_questions=num[0], exposure_before_first_s=round(den[0], 1),
                n_later_questions=num[1], exposure_after_first_s=round(den[1], 1),
                fit_seed=FIT_SEED, sizes=list(SIZES))


def ttft(h, c, tier):
    """MODELLED, by the composition rule in the docstring."""
    if h <= 0:
        return 0.0
    c = max(0, min(c, h))
    if tier == "cold" or c == 0:
        return C.recall_ttft_s(h, "COLD")
    warm = "GPU-WARM" if tier == "gpu" else "HOST-WARM"
    out = C.recall_ttft_s(c, warm)
    if h - c > 0:
        out += C.recall_ttft_s(h - c, "COLD")
    return out


def simulate(ses, batches, questions, policy, gpu_cap, host_cap, hazard, T=120.0):
    """One (policy, capacity) run over one trace. Returns the per-question records and the cost."""
    st = {sid: dict(res=0, tier="cold", last=s["start"], asked=0) for sid, s in ses.items()}
    nextq = defaultdict(list)
    for q in sorted(questions, key=lambda x: -x["t"]):
        nextq[q["sid"]].append(q["t"])          # ascending when popped from the end
    warm_gpu_s = 0.0
    peak_gpu = peak_host = 0
    rows = []
    ev = ([dict(kind="b", **b) for b in batches] + [dict(kind="q", **q) for q in questions])
    ev.sort(key=lambda x: (x["t"], 0 if x["kind"] == "b" else 1))

    def resident(tier):
        return sum(v["res"] for v in st.values() if v["tier"] == tier)

    def keep_score(sid, now):
        """Lower score is evicted first."""
        s, v = ses[sid], st[sid]
        if policy == "P1":
            return v["last"]
        if policy == "P3":
            future = [t for t in nextq.get(sid, []) if t >= now]
            return -min(future) if future else -1e18      # soonest next question kept
        dead = s["declared_end"] is not None and now > s["declared_end"]
        if dead:
            return -1.0
        lam = hazard["lam_already_asked"] if v["asked"] else hazard["lam_not_yet_asked"]
        # The horizon is clipped by the session's own declared remaining life, which is what makes T
        # read anything: with a two-rate hazard and no clipping the ranking is monotone in lam alone,
        # so every T gives the SAME order and the parameter is inert. Clipped, a session that ends in
        # 40 s is worth less at T = 300 than at T = 60.
        left = max((s["declared_end"] - now) if s["declared_end"] is not None else T, 0.0)
        return 1.0 - math.exp(-lam * min(T, left))

    def enforce(now):
        nonlocal peak_gpu, peak_host
        while resident("gpu") > gpu_cap:
            cand = [k for k, v in st.items() if v["tier"] == "gpu" and v["res"] > 0]
            if not cand:
                break
            st[min(cand, key=lambda k: keep_score(k, now))]["tier"] = "host"
        while resident("host") > host_cap:
            cand = [k for k, v in st.items() if v["tier"] == "host" and v["res"] > 0]
            if not cand:
                break
            v = st[min(cand, key=lambda k: keep_score(k, now))]
            v["tier"], v["res"] = "cold", 0          # D56: demoted to cold, frames stay on disk
        peak_gpu, peak_host = max(peak_gpu, resident("gpu")), max(peak_host, resident("host"))

    for e in ev:
        sid = e["sid"]
        if sid not in st:
            continue
        if e["kind"] == "b":
            if policy == "P0":
                continue
            new = max(int(e["cum"]) - st[sid]["res"], 0) if st[sid]["tier"] != "cold" else int(e["cum"])
            warm_gpu_s += C.recall_gpu_s(max(new, 1), "COLD") if new > 0 else 0.0
            st[sid].update(res=int(e["cum"]), tier="gpu", last=e["t"])
            enforce(e["t"])
            continue
        v = st[sid]
        tier = v["tier"] if policy != "P0" else "cold"
        cov = v["res"] if policy != "P0" else 0
        tf = ttft(e["h"], cov, tier)
        rows.append(dict(opp=e["opp"], sid=sid, t=e["t"], h=e["h"], tier=tier,
                         covered=min(cov, e["h"]), ttft_s=tf,
                         on_time_ttft=tf <= e["deadline"],
                         on_time_with_queue=tf + QUEUE_ALLOWANCE_S <= e["deadline"]))
        v["asked"] += 1
        v["last"] = e["t"]
        if policy != "P0":
            v.update(res=max(v["res"], 0), tier="gpu" if v["res"] > 0 else "cold")
            enforce(e["t"])
    return rows, dict(warming_gpu_s=round(warm_gpu_s, 2), peak_gpu_tokens=peak_gpu,
                      peak_host_tokens=peak_host)


def summarize(rows):
    n = len(rows)
    if not n:
        return None
    tf = [r["ttft_s"] for r in rows]
    return dict(questions=n,
                gpu=sum(1 for r in rows if r["tier"] == "gpu"),
                host=sum(1 for r in rows if r["tier"] == "host"),
                cold=sum(1 for r in rows if r["tier"] == "cold"),
                covered_fraction_p50=round(stat.median(
                    (r["covered"] / r["h"]) if r["h"] else 0.0 for r in rows), 4),
                ttft_p50=round(stat.median(tf), 3), ttft_p90=round(sorted(tf)[int(0.9 * (n - 1))], 3),
                ttft_mean=round(sum(tf) / n, 3),
                on_time_ttft=sum(1 for r in rows if r["on_time_ttft"]),
                on_time_ttft_frac=round(sum(1 for r in rows if r["on_time_ttft"]) / n, 4),
                on_time_with_queue=sum(1 for r in rows if r["on_time_with_queue"]),
                on_time_with_queue_frac=round(sum(1 for r in rows if r["on_time_with_queue"]) / n, 4),
                # why the two on-time columns can be equal: nothing sits in the window the allowance
                # moves across. Reported so an equality is not read as a copy of the other column.
                in_queue_flip_window=sum(1 for r in rows
                                         if r["ttft_s"] <= ROB_L and r["ttft_s"] > ROB_L - QUEUE_ALLOWANCE_S),
                ttft_over_deadline=sum(1 for r in rows if r["ttft_s"] > ROB_L))


def main():
    hazard = fit_hazard()
    print("P2 hazard fitted on seed %d: lam(not yet asked) %.3e /s, lam(already asked) %.3e /s"
          % (FIT_SEED, hazard["lam_not_yet_asked"], hazard["lam_already_asked"]))
    print("   from %d first questions over %.0f s of exposure and %d later questions over %.0f s"
          % (hazard["n_first_questions"], hazard["exposure_before_first_s"],
             hazard["n_later_questions"], hazard["exposure_after_first_s"]))
    traces = {(s, n): events(s, n) for s in EVAL_SEEDS for n in SIZES}
    out = dict(_note=__doc__.strip().splitlines()[0], hazard_fit=hazard,
               capacities=dict(gpu_tokens=GPU_TOKENS, host_tokens=HOST_TOKENS, scales=list(CAP_SCALES)),
               queue_allowance_s=QUEUE_ALLOWANCE_S, eval_seeds=list(EVAL_SEEDS), fit_seed=FIT_SEED,
               cells=[])
    policies = [("P0", None), ("P1", None)] + [("P2", T) for T in T_HORIZONS] + [("P3", None)]
    for n in SIZES:
        for scale in CAP_SCALES:
            g, h = int(GPU_TOKENS * scale), int(HOST_TOKENS * scale)
            print("\nn=%d, capacity %.2fx (gpu %d, host %d tokens)" % (n, scale, g, h))
            print("   %-10s %5s %5s %5s %5s  %7s %7s %7s  %8s %8s  %9s" %
                  ("policy", "q", "gpu", "host", "cold", "p50", "p90", "mean",
                   "ontime", "ontime+q", "warm GPU-s"))
            for pol, T in policies:
                allrows, cost = [], dict(warming_gpu_s=0.0, peak_gpu_tokens=0, peak_host_tokens=0)
                for s in EVAL_SEEDS:
                    ses, batches, qs = traces[(s, n)]
                    rr, cc = simulate(ses, batches, qs, pol, g, h, hazard, T or 120.0)
                    allrows += rr
                    cost["warming_gpu_s"] += cc["warming_gpu_s"]
                    cost["peak_gpu_tokens"] = max(cost["peak_gpu_tokens"], cc["peak_gpu_tokens"])
                    cost["peak_host_tokens"] = max(cost["peak_host_tokens"], cc["peak_host_tokens"])
                sm = summarize(allrows)
                label = pol if T is None else "%s T=%d" % (pol, int(T))
                out["cells"].append(dict(n_devices=n, capacity_scale=scale, gpu_tokens=g,
                                         host_tokens=h, policy=label, **sm, **cost))
                print("   %-10s %5d %5d %5d %5d  %7.3f %7.3f %7.3f  %4d %.3f %4d %.3f  %9.1f" %
                      (label, sm["questions"], sm["gpu"], sm["host"], sm["cold"], sm["ttft_p50"],
                       sm["ttft_p90"], sm["ttft_mean"], sm["on_time_ttft"], sm["on_time_ttft_frac"],
                       sm["on_time_with_queue"], sm["on_time_with_queue_frac"],
                       round(cost["warming_gpu_s"], 1)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=float))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
