#!/usr/bin/env python3
"""WARM-STATE STUDY PART 2 (user addendum, 2026-11-20): warming that competes for the same GPU.

Section 15 charged warming its GPU-seconds and never queued it. That exclusion is the one the live
edf and llf cells showed to matter (section 15.4), so this part builds it in: every request and every
warming prefill goes through ONE shared server model, and two warming DISCIPLINES are compared under
every placement policy.

  W1  warm immediately on arrival: a batch's prefill joins the queue when the batch arrives and takes
      its place in line against deadline work.
  W2  warm only in spare capacity: a prefill starts only when no deadline work is queued AND nothing
      queued is at risk, where at risk uses the policy's own committed test, laxity < 0.3 x deadline
      (D143 ruling B). Once started a prefill is not preempted, because a prefill is not resumable.

The placement policies are section 15's: P1 LRU, P2 lowest P(question within T) at T = 60 s (the best
horizon there), P3 oracle. P0, no warming, is the floor. A question is warm only if its session is
resident AND the covering batches were actually prefilled, so under W2 a batch the server never had
time for leaves its own history cold: the discipline changes the hit rate, not only the cost.

REGISTERS. TRACE: arrivals, sessions, batches, questions, tokens, deadlines. MEASURED: the per-kind
prompt sizes used for dashcam and single-shot service, and every number in the calibration section.
MODELLED: service times from the committed curves. CONSTRUCTED: the disciplines, the policies, the
capacities below the committed pair.

THE SERVER MODEL AND ITS ONE FREE PARAMETER. c parallel service slots, FIFO by submission time,
service time from the committed cost curve (the same quantity the coordinator charges to the GPU
budget), with a partially resident history composed as in section 15. c is the ONLY fitted number.
It is fitted on the two WARMING-FREE arms, b7-edf-feasibility and hybrid-F-lhreq, by replaying their
own measured submission streams and matching the robot queue wait; edf and llf, which do warm, are
then VALIDATION cells and are not fitted. Fitting on the arms without the mechanism and validating on
the arms with it is deliberate: it is the only split that keeps the calibration from absorbing the
effect under test.
"""
from __future__ import annotations

import gzip
import heapq
import json
import math
import os
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

RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
OUT = REPO / ("results/orchestration/live2/frozen_test/warm_state_contention"
              + ("" if os.environ.get("WARM_ROB_L", "5.0") == "5.0"
                 else "_L" + os.environ["WARM_ROB_L"].replace(".", "p")) + ".json")

GPU_TOKENS, HOST_TOKENS = 62944, 110592
CAP_SCALES = (1.0, 0.5, 0.25)
EVAL_SEEDS, FIT_SEED, SIZES = (4, 5, 6), 0, (16,)
RUN_S, RATIO = 1200.0, "40:40:20"
# D147: the robot deadline is swept. 5.0 s is the deadline the runs were MADE under; a shorter one
# re-scores the same simulated timeline and is a counterfactual on scoring, not on behaviour.
ROB_L = float(os.environ.get("WARM_ROB_L", "5.0"))
# The trace records deadline_s = 5.0 on every robot question, so `r.get("deadline_s") or ROB_L`
# always took 5.0 and a WARM_ROB_L override was INERT. The first run at 3 s returned numbers
# IDENTICAL to 5 s at every capacity and policy, which is the signature of a switch that never
# reached a decision, not of a deadline that costs nothing. The override is explicit now.
ROB_L_OVERRIDE = "WARM_ROB_L" in os.environ
SS_L, DASH_L = 2.0, 1.0
K_FRAC = 0.3                      # D143 ruling B: at risk when laxity < 0.3 x the type's deadline
MON_TOKENS, SS_TOKENS = 378, 1372  # MEASURED medians from the committed request logs
FIT_ARMS = ("b7-edf-feasibility", "hybrid-F-lhreq")
VAL_ARMS = ("edf", "llf")
CAL_CELL = "_n16_s4_1200s_h27_3t"


def jl(p: Path):
    for c in (p, p.with_suffix(p.suffix + ".gz")):
        if c.exists():
            op = gzip.open if str(c).endswith(".gz") else open
            with op(c, "rt") as f:
                return [json.loads(x) for x in f if x.strip()]
    return []


F_KIND = {}      # filled by calibrate(); the study applies it so both halves use one service model


def service_s(tokens, cached=0, tier="cold", kind=None):
    """MODELLED GPU busy time, composed exactly as in section 15."""
    tokens = max(int(tokens), 1)
    cached = max(0, min(int(cached), tokens))
    if cached == 0 or tier == "cold":
        out = C.recall_ttft_s(tokens, "COLD")
    else:
        warm = "GPU-WARM" if tier == "gpu" else "HOST-WARM"
        out = C.recall_ttft_s(cached, warm)
        if tokens - cached > 0:
            out += C.recall_ttft_s(tokens - cached, "COLD")
    return out * (F_KIND.get(kind, 1.0) if kind else 1.0)


def run_queue(items, c):
    """FIFO over c slots, as a DISCRETE-EVENT loop: a slot that frees starts the next queued item
    at once, not at the next arrival.

    The first version of this advanced the server only at arrival instants, which silently capped
    throughput at c items per DISTINCT TIMESTAMP. With 12 dashcam frames arriving on the same
    instant each second that is 2 per second against 12 offered, so the queue grew without bound at
    53 percent true utilisation and every modelled wait was nonsense (queue length p50 386, waits of
    34 s). A saturated model that is not saturated in the data is the shape to watch for here.
    """
    c = max(int(c), 1)
    arr = sorted(items, key=lambda x: x[0])
    wait, pend = {}, []
    busy, i, now = 0, 0, 0.0
    done = []            # heap of completion times
    while i < len(arr) or pend or done:
        nxt = []
        if i < len(arr):
            nxt.append(arr[i][0])
        if done:
            nxt.append(done[0])
        now = min(nxt) if nxt else now
        while i < len(arr) and arr[i][0] <= now:
            pend.append(arr[i])
            i += 1
        while done and done[0] <= now:
            heapq.heappop(done)
            busy -= 1
        while pend and busy < c:
            t, svc, key = pend.pop(0)
            wait[key] = now - t
            heapq.heappush(done, now + svc)
            busy += 1
        if not pend and not done and i >= len(arr):
            break
    return wait


# ----------------------------------------------------------------- calibration
def live_stream(arm):
    """An arm's OWN measured submission stream, with its measured prompt and cached tokens."""
    d = RUNS / (arm + CAL_CELL)
    req = jl(d / "request.jsonl")
    out = {o["opportunity_id"]: o for o in jl(d / "outcomes.jsonl")}
    items, obs = [], {}
    for r in req:
        if r.get("t_submit") is None:
            continue
        pt = int(r.get("prompt_tokens") or 0)
        ct = int(r.get("cached_tokens") or 0)
        tier = "gpu" if (r.get("cache_path") == "WARM" and ct > 0) else "cold"
        svc = service_s(pt or 1, ct, tier)
        key = r["request_id"]
        items.append((float(r["t_submit"]), svc, key))
        o = out.get(r.get("opportunity_id"))
        kind = ("build" if not r.get("opportunity_id")
                else "monitor" if (o or {}).get("kind") == "monitor"
                else "ss" if str((o or {}).get("session_id", "")).startswith("asst") else "robot")
        if r.get("t_first_token") is not None:
            obs[key] = dict(kind=kind, measured_ttft=float(r["t_first_token"]) - float(r["t_submit"]),
                            service=svc)
    return items, obs


def calibrate():
    """Two numbers, and only one of them is fitted.

    f_kind, THE INTERFERENCE FACTOR. The committed curve predicts the GPU-busy time of a request in
    isolation. Measured TTFT at this load is larger, because the engine batches: dashcam frames come
    in at 3.1x the curve, single-shot at 1.5x, robot recall at 1.3x. f_kind is the ratio of the
    measured median TTFT to the modelled service, FITTED on the two warming-free arms only.

    c, THE SLOT COUNT. Not fitted: taken from the engine's own measured concurrency in the same
    cells, the sum of measured TTFT over the run divided by the run length (7,008 s over 1,200 s for
    b7, so about 6 requests in service at once).

    VALIDATION is then edf and llf, which warm, and in particular their BUILD requests, a class that
    never entered the fit at all. A fit that also predicts a class it never saw is the only version
    of this calibration worth reporting.
    """
    streams = {a: live_stream(a) for a in FIT_ARMS + VAL_ARMS}
    # f per kind, from the warming-free arms
    num, den = defaultdict(list), defaultdict(list)
    busy, span = [], []
    for a in FIT_ARMS:
        items, obs = streams[a]
        for o in obs.values():
            num[o["kind"]].append(o["measured_ttft"])
            den[o["kind"]].append(o["service"])
        busy.append(sum(o["measured_ttft"] for o in obs.values()))
        span.append(RUN_S)
    f = {k: round(stat.median(num[k]) / stat.median(den[k]), 4) for k in num}
    c = max(1, int(round(sum(busy) / sum(span))))
    fit = dict(f_by_kind=f, c_measured_concurrency=c,
               c_source="sum of measured TTFT over run length, mean of the two warming-free arms",
               f_source="median measured TTFT over median modelled service, the two warming-free arms",
               fitted_on=list(FIT_ARMS), validated_on=list(VAL_ARMS))
    for a in FIT_ARMS + VAL_ARMS:
        items, obs = streams[a]
        scaled = [(t, svc * f.get(obs[k]["kind"], 1.0) if k in obs else svc, k)
                  for (t, svc, k) in items]
        w = run_queue(scaled, c)
        per = {}
        for kind in ("monitor", "ss", "robot", "build"):
            mm = [o["measured_ttft"] for o in obs.values() if o["kind"] == kind]
            pp = [w.get(k, 0.0) + o["service"] * f.get(kind, 1.0)
                  for k, o in obs.items() if o["kind"] == kind]
            if mm:
                per[kind] = dict(n=len(mm), measured_p50=round(stat.median(mm), 3),
                                 modelled_p50=round(stat.median(pp), 3),
                                 ratio=round(stat.median(pp) / stat.median(mm), 3),
                                 modelled_wait_p50=round(stat.median(
                                     [w.get(k, 0.0) for k, o in obs.items() if o["kind"] == kind]), 4),
                                 f_applied=f.get(kind))
        fit[("fit_" if a in FIT_ARMS else "validation_") + a] = per
    return fit


# ----------------------------------------------------------------- the study
def events(seed, n):
    t = TR.generate_trace(seed, n, RATIO, RUN_S, "A",
                          robot_question_set="lh_req", ss_question_set="ss2")
    recs = t["records"] if isinstance(t, dict) else t
    ses, batches, questions, monitors = {}, [], [], []
    for r in recs:
        dev = str(r.get("device_id", ""))
        k = r.get("kind")
        if k == "monitor_opportunity":
            monitors.append(float(r["t"]))
            continue
        if not dev.startswith(("robo", "asst")):
            continue
        if k == "session_start" and dev.startswith("robo"):
            ses[r["session_id"]] = dict(start=float(r["t"]),
                                        declared_end=float(r["t"]) + float(r.get("duration_s") or 0.0)
                                        - float(r.get("join_offset_s") or 0.0), end=None)
        elif k == "session_end" and r["session_id"] in ses:
            ses[r["session_id"]]["end"] = float(r["t"])
        elif k in ("history_batch", "history_preload") and dev.startswith("robo"):
            batches.append(dict(t=float(r["t"]), sid=r["session_id"], cum=int(r.get("cum_tokens") or 0),
                                new=int(r.get("est_tokens") or 0)))
        elif k == "recall_question":
            questions.append(dict(t=float(r["t"]), sid=r["session_id"], opp=r["opportunity_id"],
                                  h=int(r.get("history_tokens") or 0) if dev.startswith("robo") else SS_TOKENS,
                                  kind="robot" if dev.startswith("robo") else "ss",
                                  deadline=(ROB_L if (dev.startswith("robo") and ROB_L_OVERRIDE)
                                            else float(r.get("deadline_s")
                                                       or (ROB_L if dev.startswith("robo")
                                                           else SS_L)))))
    return ses, sorted(batches, key=lambda x: x["t"]), sorted(questions, key=lambda x: x["t"]), sorted(monitors)


def simulate(ses, batches, questions, monitors, policy, disc, gpu_cap, host_cap, hazard, T=60.0):
    """One (placement policy, warming discipline, capacity) cell, event driven on c slots.

    The server is c slots with FIFO admission among what is ELIGIBLE at the moment a slot frees.
    Deadline work is always eligible. A warming prefill is eligible at once under W1 and only when
    no deadline work is queued and nothing queued is at risk under W2.
    """
    c = int(hazard["c_slots"])
    st = {sid: dict(res=0, tier="cold", last=s["start"], asked=0) for sid, s in ses.items()}
    nextq = defaultdict(list)
    for q in questions:
        if q["kind"] == "robot":
            nextq[q["sid"]].append(q["t"])

    def keep_score(sid, now):
        s, v = ses[sid], st[sid]
        if policy == "P1":
            return v["last"]
        if policy == "P3":
            fut = [t for t in nextq.get(sid, []) if t >= now]
            return -min(fut) if fut else -1e18
        if s["declared_end"] is not None and now > s["declared_end"]:
            return -1.0
        lam = hazard["lam_already_asked"] if v["asked"] else hazard["lam_not_yet_asked"]
        left = max((s["declared_end"] - now) if s["declared_end"] is not None else T, 0.0)
        return 1.0 - math.exp(-lam * min(T, left))

    def enforce(now):
        while sum(v["res"] for v in st.values() if v["tier"] == "gpu") > gpu_cap:
            cand = [k for k, v in st.items() if v["tier"] == "gpu" and v["res"] > 0]
            if not cand:
                break
            st[min(cand, key=lambda k: keep_score(k, now))]["tier"] = "host"
        while sum(v["res"] for v in st.values() if v["tier"] == "host") > host_cap:
            cand = [k for k, v in st.items() if v["tier"] == "host" and v["res"] > 0]
            if not cand:
                break
            v = st[min(cand, key=lambda k: keep_score(k, now))]
            v["tier"], v["res"] = "cold", 0

    # one queue of pending work, one list of free slots
    ev = ([dict(k="mon", t=t) for t in monitors]
          + [dict(k="q", **q) for q in questions]
          + ([] if policy == "P0" else [dict(k="warm", **b) for b in batches]))
    ev.sort(key=lambda x: (x["t"], {"q": 0, "mon": 1, "warm": 2}[x["k"]]))
    done = []            # heap of completion times
    busy = 0
    pend_deadline, pend_warm = [], []
    rows, warm_gpu_s, warmed, skipped = [], 0.0, 0, 0

    def at_risk(now):
        for it in pend_deadline:
            if (it["abs_deadline"] - now) - it["svc"] < K_FRAC * it["deadline"]:
                return True
        return False

    def start_warm(b, now):
        nonlocal warm_gpu_s, warmed
        heapq.heappush(done, now + b["svc"])
        warm_gpu_s += b["svc"]
        warmed += 1
        st[b["sid"]].update(res=int(b["cum"]), tier="gpu", last=b["t"])
        enforce(now)

    def dispatch(now):
        """Start work on free slots under the discipline.

        W1 is ONE FIFO over both classes, which is what "warm immediately on arrival" means: a
        prefill that arrived first holds a slot the next question then waits for. W2 is strict
        priority for deadline work plus the at-risk pause, so a prefill starts only into genuinely
        spare capacity. An earlier version gave deadline work priority in BOTH, which made the two
        disciplines byte-identical in every cell: W1 was yielding by construction and the
        comparison the user asked for could not have come out any other way.
        """
        nonlocal busy
        while busy < c:
            dl = pend_deadline[0] if pend_deadline else None
            wm = pend_warm[0] if pend_warm else None
            pick = None
            if disc == "W1":
                if dl and wm:
                    pick = "d" if dl["t"] <= wm["t"] else "w"
                else:
                    pick = "d" if dl else ("w" if wm else None)
            else:
                if dl:
                    pick = "d"
                elif wm and not at_risk(now):
                    pick = "w"
            if pick is None:
                return
            if pick == "d":
                it = pend_deadline.pop(0)
                it["wait"] = now - it["t"]
                heapq.heappush(done, now + it["svc"])
            else:
                start_warm(pend_warm.pop(0), now)
            busy += 1

    def advance_to(t):
        """Retire completions and start work up to time t, so a slot that frees mid-gap is used."""
        nonlocal busy
        while done and done[0] <= t:
            now = heapq.heappop(done)
            busy -= 1
            dispatch(now)
        dispatch(t)

    for e in ev:
        now = e["t"]
        advance_to(now)
        if e["k"] == "mon":
            pend_deadline.append(dict(t=now, svc=service_s(MON_TOKENS, kind="monitor"), deadline=DASH_L,
                                      abs_deadline=now + DASH_L, wait=None))
        elif e["k"] == "warm":
            sid = e["sid"]
            if sid not in st:
                continue
            base = st[sid]["res"] if st[sid]["tier"] != "cold" else 0
            new = max(int(e["cum"]) - base, 0)
            if new <= 0:
                continue
            pend_warm.append(dict(t=now, sid=sid, cum=e["cum"], svc=service_s(new, kind="build")))
        else:
            sid = e["sid"]
            v = st.get(sid)
            cov = (v["res"] if v and v["tier"] in ("gpu", "host") and policy != "P0" else 0)
            tier = (v["tier"] if v and policy != "P0" else "cold")
            svc = service_s(e["h"], min(cov, e["h"]), tier, kind=e["kind"])
            it = dict(t=now, svc=svc, deadline=e["deadline"], abs_deadline=now + e["deadline"],
                      wait=None, opp=e["opp"], kind=e["kind"], tier=tier if cov else "cold",
                      covered=min(cov, e["h"]), h=e["h"])
            pend_deadline.append(it)
            rows.append(it)
            if v:
                v["asked"] += 1
                v["last"] = now
        dispatch(now)
    advance_to(RUN_S + 3600.0)
    skipped = len(pend_warm)
    done = [r for r in rows if r["wait"] is not None]
    out = {}
    for kind, L in (("robot", ROB_L), ("ss", SS_L)):
        v = [r for r in done if r["kind"] == kind]
        if not v:
            continue
        lat = [r["wait"] + r["svc"] for r in v]
        out[kind] = dict(n=len(v), on_time=sum(1 for x, r in zip(lat, v) if x <= r["deadline"]),
                         on_time_frac=round(sum(1 for x, r in zip(lat, v) if x <= r["deadline"]) / len(v), 4),
                         wait_p50=round(stat.median(r["wait"] for r in v), 3),
                         wait_p90=round(sorted(r["wait"] for r in v)[int(0.9 * (len(v) - 1))], 3),
                         wait_p99=round(sorted(r["wait"] for r in v)[int(0.99 * (len(v) - 1))], 3),
                         wait_max=round(max(r["wait"] for r in v), 3),
                         n_waited=sum(1 for r in v if r["wait"] > 1e-9),
                         wait_sum=round(sum(r["wait"] for r in v), 2),
                         latency_p50=round(stat.median(lat), 3),
                         warm=sum(1 for r in v if r["tier"] in ("gpu", "host")),
                         cold=sum(1 for r in v if r["tier"] == "cold"))
    out["warming"] = dict(gpu_s=round(warm_gpu_s, 1), batches_warmed=warmed, batches_never_warmed=skipped)
    return out


def main():
    cal = calibrate()
    print("CALIBRATION: c = %d slots (measured concurrency), interference f = %s"
          % (cal["c_measured_concurrency"], cal["f_by_kind"]))
    print("   fitted on %s, validated on %s" % (", ".join(FIT_ARMS), ", ".join(VAL_ARMS)))
    for a in FIT_ARMS + VAL_ARMS:
        key = ("fit_" if a in FIT_ARMS else "validation_") + a
        print("   %-20s %s" % (a, "  ".join(
            "%s meas %.3f mod %.3f (x%.2f, n %d)" % (k, v["measured_p50"], v["modelled_p50"],
                                                     v["ratio"], v["n"])
            for k, v in sorted(cal[key].items()))))
    haz = json.loads((REPO / "results/orchestration/live2/frozen_test/warm_state_offline.json").read_text())["hazard_fit"]
    haz["c_slots"] = cal["c_measured_concurrency"]
    F_KIND.update(cal["f_by_kind"])
    traces = {(s, n): events(s, n) for s in EVAL_SEEDS for n in SIZES}
    out = dict(_note=__doc__.strip().splitlines()[0], calibration=cal, hazard_fit=haz, cells=[])
    for n in SIZES:
        for scale in CAP_SCALES:
            g, h = int(GPU_TOKENS * scale), int(HOST_TOKENS * scale)
            print("\nn=%d capacity %.2fx (gpu %d host %d)" % (n, scale, g, h))
            print("   %-10s %-3s | %-36s | %-40s | %s" % ("policy", "W", "robot on time / n, warm, queue",
                                                           "single-shot on time / n, queue", "warming"))
            for pol, disc in ([("P0", "none")] + [(p, d) for p in ("P1", "P2", "P3") for d in ("W1", "W2")]):
                agg = defaultdict(lambda: defaultdict(float))
                tot = defaultdict(int)
                for s in EVAL_SEEDS:
                    ses, batches, qs, mons = traces[(s, n)]
                    r = simulate(ses, batches, qs, mons, pol, disc, g, h, haz)
                    for kind in ("robot", "ss"):
                        if kind in r:
                            tot[kind] += r[kind]["n"]
                            agg[kind]["on_time"] += r[kind]["on_time"]
                            agg[kind]["warm"] += r[kind]["warm"]
                            agg[kind]["wait_p50"] += r[kind]["wait_p50"] / len(EVAL_SEEDS)
                            agg[kind]["wait_p90"] += r[kind]["wait_p90"] / len(EVAL_SEEDS)
                            agg[kind]["wait_max"] = max(agg[kind]["wait_max"], r[kind]["wait_max"])
                            agg[kind]["n_waited"] += r[kind]["n_waited"]
                            agg[kind]["wait_sum"] += r[kind]["wait_sum"]
                            agg[kind]["latency_p50"] += r[kind]["latency_p50"] / len(EVAL_SEEDS)
                    agg["warming"]["gpu_s"] += r["warming"]["gpu_s"]
                    agg["warming"]["never"] += r["warming"]["batches_never_warmed"]
                    agg["warming"]["warmed"] += r["warming"]["batches_warmed"]
                row = dict(n_devices=n, capacity_scale=scale, policy=pol, discipline=disc,
                           robot_n=tot["robot"], robot_on_time=int(agg["robot"]["on_time"]),
                           robot_warm=int(agg["robot"]["warm"]),
                           robot_wait_p50=round(agg["robot"]["wait_p50"], 3),
                           robot_wait_p90=round(agg["robot"]["wait_p90"], 3),
                           robot_wait_max=round(agg["robot"]["wait_max"], 3),
                           robot_n_waited=int(agg["robot"]["n_waited"]),
                           robot_wait_sum=round(agg["robot"]["wait_sum"], 2),
                           robot_latency_p50=round(agg["robot"]["latency_p50"], 3),
                           ss_n=tot["ss"], ss_on_time=int(agg["ss"]["on_time"]),
                           ss_wait_p50=round(agg["ss"]["wait_p50"], 3),
                           ss_wait_p90=round(agg["ss"]["wait_p90"], 3),
                           ss_wait_max=round(agg["ss"]["wait_max"], 3),
                           ss_n_waited=int(agg["ss"]["n_waited"]),
                           ss_wait_sum=round(agg["ss"]["wait_sum"], 2),
                           ss_latency_p50=round(agg["ss"]["latency_p50"], 3),
                           warming_gpu_s=round(agg["warming"]["gpu_s"], 1),
                           batches_warmed=int(agg["warming"]["warmed"]),
                           batches_never_warmed=int(agg["warming"]["never"]))
                out["cells"].append(row)
                print("   %-10s %-3s | %3d/%3d warm %3d  waited %3d, p90 %6.3f max %6.3f | %4d/%4d waited %4d, p90 %6.3f max %6.3f | %7.1f GPU-s"
                      % (pol, disc, row["robot_on_time"], row["robot_n"], row["robot_warm"],
                         row["robot_n_waited"], row["robot_wait_p90"], row["robot_wait_max"],
                         row["ss_on_time"], row["ss_n"], row["ss_n_waited"], row["ss_wait_p90"],
                         row["ss_wait_max"], row["warming_gpu_s"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=float))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
