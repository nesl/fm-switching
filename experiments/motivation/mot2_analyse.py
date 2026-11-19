#!/usr/bin/env python3
"""StudyMOT2-dayinlife episode analysis (rules fixed in the EXPERIMENTS.md row at cffdbb2, BEFORE any run). CPU only,
run after the servers are stopped.

Definitions used to implement the pre-registered rules (stated in the report):
- robot request: a request with a session_id (whole rebuild, piece or recall); its kind is read from the decision log
  (`release_whole` / `release_recall`); a whole rebuild carries no opportunity and is tied to its question through its
  decision's opportunity_ids.
- measured tier of a request: COLD if cached_tokens <= 16, WARM if cached >= 0.5 x prompt, else PARTIAL; the measured
  tier AT a question is that of the first robot request for its session submitted at or after the question.
- a question is SERVED BY A COLD REBUILD when that first request is COLD with prompt >= 4,000 tokens; its measured
  rebuild time (= its GPU time) is that request's t_done - t_submit.
- dashcam instant: a monitor opportunity; its deadline instant is t_opportunity + deadline_s; it is MISSED when the
  emulator's `within_L` is false (the cloud answer did not reach the device within L), the same notion as StudyMOT1.
- robot question on time: `within_L` of the recall outcome (L = 5 s).
- GPU idle fraction (PROXY): fraction of the run window with no request of any kind in flight.
"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/motivation/mot2"
R1 = REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"
RUN_S = 600.0
WIN_S, STEP_S, WIN0 = 180.0, 10.0, 60.0
TYPES = ("SHAPE", "VALUE", "LOCATION", "TIMING")


def jl(p):
    return [json.loads(l) for l in open(p)]


def tier(r):
    ct, pt = r.get("cached_tokens") or 0, r.get("prompt_tokens") or 0
    if ct <= 16:
        return "COLD"
    return "WARM" if pt and ct >= 0.5 * pt else "PARTIAL"


def covered_flags():
    rows = [json.loads(l) for l in gzip.open(R1, "rt")]
    return {r["question_id"]: r["evidence_covered"] for r in rows
            if r["mode"] == "batched" and r["construction"] == "RECENT"}


def union_len(iv, lo, hi):
    iv = sorted((max(a, lo), min(b, hi)) for a, b in iv if b > lo and a < hi)
    tot, cur_a, cur_b = 0.0, None, None
    for a, b in iv:
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                tot += cur_b - cur_a
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        tot += cur_b - cur_a
    return tot


def analyse(seed, cov):
    d = OUT / "runs" / f"seed{seed}"
    req = jl(d / "request.jsonl")
    dec = {x["decision_id"]: x for x in jl(d / "decision.jsonl")}
    res = jl(d / "residency.jsonl")
    out = jl(d / "outcomes.jsonl")
    meta = json.loads((d / "run_meta.json").read_text())
    header = json.loads((d / "header.json").read_text())
    mon = [o for o in out if o["kind"] == "monitor"]
    rq = [o for o in out if o["kind"] == "recall"]
    for o in mon:
        o["t_deadline"] = o["t_opportunity"] + o["deadline_s"]
        o["missed"] = not o["within_L"]
    rob = [r for r in req if r.get("session_id")]
    for r in rob:
        k = (dec.get(r["decision_id"]) or {}).get("kind", "")
        r["rkind"] = "whole" if k == "release_whole" else ("recall" if k == "release_recall" else k or "?")
        r["answers"] = list((dec.get(r["decision_id"]) or {}).get("opportunity_ids") or [])
        r["tier"] = tier(r)
        r["rebuild_s"] = r["t_done"] - r["t_submit"]

    def misses_in(lo, hi):
        return sum(1 for o in mon if lo <= o["t_deadline"] <= hi and o["missed"])

    eps = []
    # (1) SHAPE
    for r in rob:
        if (r.get("cached_tokens") or 0) <= 16 and (r.get("prompt_tokens") or 0) >= 4000:
            lo, hi = r["t_submit"], r["t_done"] + 2.0
            n = misses_in(lo, hi)
            span = hi - lo
            base = misses_in(lo - 60.0, lo) / 60.0 * span
            excess = n - base
            if excess >= 3:
                eps.append(dict(type="SHAPE", t=lo, t_end=hi, request_id=r["request_id"], rkind=r["rkind"],
                                session_id=r["session_id"], tier=r["tier"], cached=r["cached_tokens"],
                                prompt=r["prompt_tokens"], rebuild_s=round(r["rebuild_s"], 4),
                                dashcam_misses=n, baseline=round(base, 3), excess=round(excess, 3),
                                label=f"cold rebuild in one go: {round(excess)} extra dashcam misses"))
    # per question: first robot request for its session at or after the question
    qrows = []
    for o in rq:
        tq = o["t_opportunity"]
        first = sorted((r for r in rob if r["session_id"] == o["session_id"] and r["t_submit"] >= tq - 1e-6),
                       key=lambda r: r["t_submit"])
        f = first[0] if first else None
        qrows.append(dict(o=o, tq=tq, first=f, inside=cov.get(o["question_id"]),
                          tier=(f["tier"] if f else "NOT-SENT"),
                          cold_rebuild=bool(f and f["tier"] == "COLD" and (f.get("prompt_tokens") or 0) >= 4000)))
    for q in qrows:
        o, tq, f = q["o"], q["tq"], q["first"]
        base = dict(t=tq, question_id=o["question_id"], session_id=o["session_id"], device_id=o["device_id"],
                    tier=q["tier"], cached=(f["cached_tokens"] if f else None),
                    rebuild_s=(round(f["rebuild_s"], 4) if f else None), inside_window=q["inside"])
        # (2) VALUE
        if q["cold_rebuild"] and q["inside"] is True:
            n = misses_in(f["t_submit"], f["t_done"])
            eps.append(dict(base, type="VALUE", t_end=f["t_done"], gpu_s=round(f["rebuild_s"], 4), dashcam_misses=n,
                            label=f"cloud rebuilt {f['prompt_tokens']:,} tokens ({f['rebuild_s']:.1f} s of GPU) for a "
                                  f"question the device's own window covered; {n} dashcam misses meanwhile"))
        # (3) LOCATION
        if q["tier"] == "COLD":
            warm = [x["t"] for x in res if x["session_id"] == o["session_id"] and tq - 60.0 <= x["t"] < tq
                    and x.get("believed_tier") in ("gpu", "host")]
            warm += [r["t_done"] for r in rob if r["session_id"] == o["session_id"] and tq - 60.0 <= r["t_done"] < tq
                     and r["tier"] == "WARM"]
            if warm:
                lw = max(warm)
                written = sum(max(0, (r.get("prompt_tokens") or 0) - (r.get("cached_tokens") or 0)) for r in req
                              if lw <= r["t_done"] <= tq)
                eps.append(dict(base, type="LOCATION", t_end=tq, last_warm_t=round(lw, 3),
                                warm_before_s=round(tq - lw, 3), tokens_written_since=written,
                                label=f"history warm {tq - lw:.0f} s before the question, evicted by then "
                                      f"({written:,} tokens written since)"))
        # (4) TIMING
        if q["cold_rebuild"]:
            busy = union_len([(r["t_submit"], r["t_done"]) for r in rob], tq - 30.0, tq)
            idle = 30.0 - busy
            if idle >= f["rebuild_s"]:
                eps.append(dict(base, type="TIMING", t=tq - 30.0, t_end=tq, idle_s=round(idle, 3),
                                label=f"GPU had {idle:.1f} s free of prefill in the 30 s before a cold question "
                                      f"that then needed {f['rebuild_s']:.1f} s"))
    counts = {t: sum(1 for e in eps if e["type"] == t) for t in TYPES}
    busy_all = union_len([(r["t_submit"], r["t_done"]) for r in req], 0.0, RUN_S)
    run = dict(seed=seed, git_commit=header.get("git_commit"), git_working_tree=header.get("git_working_tree"),
               server_command=(header.get("server") or {}).get("command"),
               trace_digest=meta.get("fairness_digest"), trace_fairness_digest=meta.get("trace_fairness_digest"),
               digests_equal=meta.get("digests_equal"), run_valid=meta.get("run_valid"),
               lateness=meta.get("lateness"), lateness_by_kind=meta.get("lateness_by_kind"),
               n_requests=len(req), http_errors=sum(1 for r in req if (r.get("http_status") or 200) != 200),
               dashcam_on_time=round(sum(1 for o in mon if not o["missed"]) / len(mon), 5),
               n_dashcam_instants=len(mon), robot_on_time=round(sum(1 for o in rq if o["within_L"]) / len(rq), 5) if rq else None,
               n_robot_questions=len(rq), gpu_idle_fraction_proxy=round(1 - busy_all / RUN_S, 5),
               counts=counts,
               questions=[dict(t=round(q["tq"], 3), answer_t=q["o"].get("t_delivered"), on_time=q["o"]["within_L"],
                               tier=q["tier"], inside_window=q["inside"], device_id=q["o"]["device_id"],
                               session_id=q["o"]["session_id"], cached=(q["first"]["cached_tokens"] if q["first"] else None),
                               prompt=(q["first"]["prompt_tokens"] if q["first"] else None),
                               first_request_kind=(q["first"]["rkind"] if q["first"] else None))
                          for q in qrows],
               episodes=sorted(eps, key=lambda e: (e["t"], e["type"])))
    run["_mon"], run["_res"], run["_rob"] = mon, res, rob
    return run


def choose_window(run):
    present = [t for t in TYPES if run["counts"][t] > 0]
    best = None
    w = WIN0
    while w + WIN_S <= RUN_S + 1e-9:
        types_in = {e["type"] for e in run["episodes"] if w <= e["t"] < w + WIN_S}
        k = len(types_in & set(present))
        if k == len(present):
            return dict(start=w, end=w + WIN_S, types=sorted(types_in & set(present)), all_present=True,
                        present_in_run=present, missing=[])
        if best is None or k > best[0]:
            best = (k, w, sorted(types_in & set(present)))
        w += STEP_S
    k, w, ts = best
    return dict(start=w, end=w + WIN_S, types=ts, all_present=False, present_in_run=present,
                missing=sorted(set(present) - set(ts)))


def figdata(run, win):
    lo, hi = win["start"], win["end"]
    bins = []
    t = lo
    while t < hi - 1e-9:
        ins = [o for o in run["_mon"] if t <= o["t_opportunity"] < t + 2.0]
        bins.append(dict(t0=round(t, 3), n=len(ins), on_time_frac=(round(sum(1 for o in ins if not o["missed"]) / len(ins), 4)
                                                                  if ins else None)))
        t += 2.0
    qs = [q for q in run["questions"] if lo <= q["t"] < hi]
    hist = defaultdict(list)
    for x in run["_res"]:
        if lo - 60 <= x["t"] < hi:
            hist[x["session_id"]].append(dict(t=x["t"], source="residency_log", believed=x.get("believed_tier"),
                                              telemetry_cached=x.get("telemetry_cached_tokens")))
    for r in run["_rob"]:
        if lo - 60 <= r["t_submit"] < hi:
            hist[r["session_id"]].append(dict(t=round(r["t_submit"], 3), source="request", measured=r["tier"],
                                              cached=r.get("cached_tokens"), prompt=r.get("prompt_tokens"),
                                              kind=r["rkind"]))
    for k in hist:
        hist[k].sort(key=lambda x: x["t"])
    eps = [dict(type=e["type"], t_start=round(e["t"], 3), t_end=round(e["t_end"], 3), label=e["label"])
           for e in run["episodes"] if lo <= e["t"] < hi]
    return dict(window=win, dashcam_on_time_per_2s_bin=bins, robot_questions=qs, history_tiers=dict(hist),
                episodes=eps)


def main():
    cov = covered_flags()
    runs = {s: analyse(s, cov) for s in (9, 10)}
    win = choose_window(runs[9])
    fd = dict(label="StudyMOT2-dayinlife figure data (motivation; edf, 12 devices 50:50, mode A, 27 GiB host)",
              figure_seed=9, window_rule="first 180 s window (10 s steps from t = 60 s) of seed 9 containing every "
                                         "episode type that occurs anywhere in seed 9's run; else most types, "
                                         "earliest on ties",
              **figdata(runs[9], win),
              counts_table={f"seed{s}": dict(r["counts"], dashcam_on_time=r["dashcam_on_time"],
                                             robot_on_time=r["robot_on_time"], n_robot_questions=r["n_robot_questions"],
                                             gpu_idle_fraction_proxy=r["gpu_idle_fraction_proxy"])
                            for s, r in runs.items()},
              value_flag_source=f"{R1.relative_to(REPO)}: evidence_covered, batched RECENT construction (figM1's source)")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mot2_figdata.json").write_text(json.dumps(fd, indent=1, default=str) + "\n")
    full = {f"seed{s}": {k: v for k, v in r.items() if not k.startswith("_")} for s, r in runs.items()}
    (OUT / "mot2_results.json").write_text(json.dumps(dict(runs=full, window=win), indent=1, default=str) + "\n")
    for s, r in runs.items():
        print(s, r["counts"], "dash", r["dashcam_on_time"], "robot", r["robot_on_time"], "idle", r["gpu_idle_fraction_proxy"],
              "valid", r["run_valid"], "p99", (r["lateness"] or {}).get("p99_ms"))
    print("window", win)


if __name__ == "__main__":
    sys.exit(main())
