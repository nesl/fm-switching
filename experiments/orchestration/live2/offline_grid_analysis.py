"""OFFLINE ANALYSIS of the overnight three-type grid (user, 2026-11-20). CPU only, no new runs.

Five questions, all answered from the committed run directories under
results/orchestration/live2/frozen_test/runs. Nothing here runs an engine or a policy, so nothing
here can change a recorded number; where a quantity is MODELLED rather than measured it says so at
the point of use, because the five answers mix the two registers and the mixture is the easiest
thing to misread.

  1. ROBOT MISS DECOMPOSITION. Arrival to first token per robot question, split into waiting before
     release, engine queueing, prefill of the history, and delivery after the first token, split
     again by on time against missed. MEASURED except the prefill term, which is the committed cost
     curve (costs.recall_ttft_s at COLD) evaluated on the measured uncached prompt; the queueing
     term is then the RESIDUAL and carries the model's error.

  2. IS "PEAK GPU-RESIDENT HISTORY 0" AN OBSERVATION OR AN INSTRUMENT THAT NEVER READS. Three
     independent instruments are reported side by side with their read sites named, per the Step 2
     rule, because the belief-side zero alone cannot distinguish "nothing was resident" from
     "nothing was measured".

  3. REUSE. Questions per robot history, the gap between questions on one history, and the warm
     prefix a prefill-on-arrival policy could have had. The last is a CONSTRUCTED bound, not an
     observation: it asks what the cache would have held, under a stated batch size, had the policy
     prefilled every upload.

  4. WARMING BUDGET. GPU-seconds and KV tokens to keep every robot history warm by prefilling each
     30 s batch, at 16 devices MEASURED and at 18 PROJECTED per robot device, against the 62,944
     token GPU pool and the 27 GiB host tier.

  5. CROSS-TYPE VALUE PER GPU-SECOND from the committed tables. The four values do NOT share a
     unit (MCQ accuracy, challenge mAP, point-in-mask fraction, exact match), so the ranking is a
     CONVENTION and is reported as one; see ss_quality.json _metric_incomparability.
"""
from __future__ import annotations

import gzip
import json
import statistics as stat
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (REPO / "experiments/orchestration/baselines", REPO / "experiments/lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import costs as C                                                            # noqa: E402

RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
OUT = REPO / "results/orchestration/live2/frozen_test/offline_grid_analysis.json"

ROB_L_S = 5.0            # the committed robot deadline the scorer uses
GPU_POOL_TOKENS = 62944  # the live2 GPU KV pool
HOST_GIB = 27
BATCH_S = 30.0           # the upload batch the warming question names
HOST_BYTES_PER_TOKEN = 262144            # StudyRH5, committed in costs.py
HOST_TIER_TOKENS = int(HOST_GIB * 1024 ** 3 / HOST_BYTES_PER_TOKEN)
WIRE_S = 0.022176        # the measured constant delivery delay (see item1b)
SS_L_S, ROB_L2_S = 2.0, 5.0


def _load(d: Path, name: str):
    p = d / (name + ".jsonl.gz")
    if p.exists():
        return [json.loads(l) for l in gzip.open(p, "rt")]
    p = d / (name + ".jsonl")
    return [json.loads(l) for l in open(p)] if p.exists() else []


def _cells(sizes=(16,), seeds=(4, 5, 6)):
    out = []
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir() or "REFUSED" in d.name or "_rerun" in d.name:
            continue
        for n in sizes:
            for s in seeds:
                tag = "_n%d_s%d_1200s_h27_3t" % (n, s)
                if d.name.endswith(tag):
                    out.append((d.name[:-len(tag)], n, s, d))
    return out


def _q(xs, p):
    xs = sorted(xs)
    return None if not xs else (xs[0] if len(xs) == 1 else
                                xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))])


def _summ(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return dict(n=len(xs), p50=round(_q(xs, 0.5), 4), p90=round(_q(xs, 0.9), 4),
                mean=round(sum(xs) / len(xs), 4), max=round(max(xs), 4))


def robot_rows(d: Path):
    """One row per robot question, joined to the request that served it (if any)."""
    req = {r["request_id"]: r for r in _load(d, "request")}
    rows = []
    for o in _load(d, "outcomes"):
        if o["kind"] != "recall" or not str(o.get("session_id", "")).startswith("robo"):
            continue
        cp = o.get("cloud_payload") or {}
        r = req.get(cp.get("request_id"))
        td = o.get("t_delivered")
        within = td is not None and (float(td) - float(o["t_opportunity"])) <= ROB_L_S + 1e-9
        bad = bool(r is not None and r.get("http_status") not in (200, None))
        rows.append(dict(opp=o["opportunity_id"], session=o["session_id"],
                         t_opp=float(o["t_opportunity"]), t_delivered=td, within=bool(within),
                         served=bool(r is not None), bad_status=bad,
                         on_time=bool(within and not bad),
                         representation=cp.get("representation"),
                         tokens_charged=cp.get("tokens_charged"),
                         letter=cp.get("cloud_letter"),
                         t_submit=(r or {}).get("t_submit"),
                         t_first=(r or {}).get("t_first_token"),
                         t_done=(r or {}).get("t_done"),
                         prompt_tokens=(r or {}).get("prompt_tokens"),
                         cached_tokens=(r or {}).get("cached_tokens"),
                         n_frames=len((r or {}).get("mm_uuids") or [])))
    return rows


def item1():
    print("\n1. ROBOT MISS DECOMPOSITION, 16 devices, seeds 4 5 6, seconds")
    print("   %-22s %-8s %4s %8s %8s %8s %8s %8s" % ("arm", "outcome", "n", "wait", "queue",
                                                      "prefill", "after1st", "arr->1st"))
    res = {}
    for arm in sorted({a for a, _, _, _ in _cells()}):
        pools = defaultdict(lambda: defaultdict(list))
        for a, n, s, d in _cells():
            if a != arm:
                continue
            for r in robot_rows(d):
                grp = "on_time" if r["on_time"] else "missed"
                if not r["served"]:
                    pools[grp]["never_sent"].append(1.0)
                    continue
                wait = r["t_submit"] - r["t_opp"]
                unc = max(int(r["prompt_tokens"] or 0) - int(r["cached_tokens"] or 0), 0)
                pre = C.recall_ttft_s(max(unc, 1), "COLD") if unc else 0.0
                ttft = (r["t_first"] - r["t_submit"]) if r["t_first"] else None
                pools[grp]["wait"].append(wait)
                pools[grp]["prefill_model"].append(pre)
                if ttft is not None:
                    pools[grp]["queue_residual"].append(max(ttft - pre, 0.0))
                    pools[grp]["model_over_measured"].append(1.0 if pre > ttft else 0.0)
                    pools[grp]["arrival_to_first"].append(r["t_first"] - r["t_opp"])
                    if r["t_delivered"]:
                        pools[grp]["after_first"].append(r["t_delivered"] - r["t_first"])
        res[arm] = {}
        for grp in ("on_time", "missed"):
            p = pools[grp]
            nq = len(p["wait"]) + len(p["never_sent"])
            if not nq:
                continue
            row = dict(n=nq, never_sent=len(p["never_sent"]),
                       wait=_summ(p["wait"]), queue_residual=_summ(p["queue_residual"]),
                       prefill_model=_summ(p["prefill_model"]), after_first=_summ(p["after_first"]),
                       arrival_to_first=_summ(p["arrival_to_first"]),
                       model_exceeded_measured_ttft=int(sum(p["model_over_measured"])))
            res[arm][grp] = row
            g = lambda k: (row[k] or {}).get("p50")                          # noqa: E731
            print("   %-22s %-8s %4d %8s %8s %8s %8s %8s" % (
                arm, grp, nq, g("wait"), g("queue_residual"), g("prefill_model"),
                g("after_first"), g("arrival_to_first")))
            if row["never_sent"]:
                print("   %-22s %-8s      never sent to the cloud at all: %d" % ("", "", row["never_sent"]))
    return res


def item2():
    print("\n2. IS PEAK GPU-RESIDENT HISTORY 0 AN OBSERVATION")
    print("   %-22s %4s %8s %8s %10s %10s %8s %8s" % ("arm cell", "rob", "cach>0", "resid",
                                                       "pfx_hits", "pfx_q", "mm_hits", "tel"))
    res = {}
    for a, n, s, d in _cells(seeds=(4, 5, 6)):
        rows = [r for r in robot_rows(d) if r["served"]]
        res_k = "%s_n%d_s%d" % (a, n, s)
        resid = _load(d, "residency")
        tel = sum(1 for r in resid if r.get("telemetry_cached_tokens") is not None)
        tiers = {}
        for r in resid:
            tiers[r["believed_tier"]] = tiers.get(r["believed_tier"], 0) + 1
        hits = q = mm = None
        snap = d / "metrics_snapshots.log"
        if snap.exists():
            last = [l for l in open(snap) if "prefix_cache" in l]
            if last:
                kv = dict(x.split("=") for x in last[-1].split() if "=" in x)
                hits = int(kv.get("vllm:prefix_cache_hits_total", 0))
                q = int(kv.get("vllm:prefix_cache_queries_total", 0))
                mm = int(kv.get("vllm:mm_cache_hits_total", 0))
        res[res_k] = dict(robot_requests=len(rows),
                          robot_cached_tokens_gt0=sum(1 for r in rows if (r["cached_tokens"] or 0) > 0),
                          residency_rows=len(resid), residency_tiers=tiers,
                          telemetry_cached_tokens_non_null=tel,
                          prefix_cache_hits=hits, prefix_cache_queries=q, mm_cache_hits=mm)
        print("   %-22s %4d %8d %8d %10s %10s %8s %8s" % (
            res_k, len(rows), res[res_k]["robot_cached_tokens_gt0"], len(resid), hits, q, mm, tel))
    res["_read_sites"] = {
        "charges_from_residency": "coordinator.py:575 cost = C.recall_gpu_s(tokens, s.residency_readiness()) "
                                  "(a real read: it sets the GPU seconds charged for the request)",
        "offered_to_arms": "cstate.py:525-526 builds obs.cloud.gpu_warm_sessions / host_warm_sessions, "
                           "the lists an arm reads to know what is warm",
        "build_path": "coordinator.py:481 if s.built_tokens < s.est_tokens and s.believed_tier() != 'gpu'",
        "telemetry_into_belief": "residency.jsonl field telemetry_cached_tokens, written at "
                                 "coordinator.py:901; NULL in every row of every cell, so the "
                                 "engine's own cached_tokens never feeds the belief",
    }
    return res


def item3():
    print("\n3. REUSE PER ROBOT HISTORY, 16 devices, seeds 4 5 6")
    res = {}
    for arm in sorted({a for a, _, _, _ in _cells()}):
        per_q, gaps, cov, hit = [], [], [], []
        for a, n, s, d in _cells():
            if a != arm:
                continue
            by = defaultdict(list)
            for r in robot_rows(d):
                by[r["session"]].append(r)
            for ses, rs in by.items():
                per_q.append(len(rs))
                ts = sorted(x["t_opp"] for x in rs)
                gaps += [b - a2 for a2, b in zip(ts, ts[1:])]
                for r in rs:
                    if not r["served"] or not r["n_frames"]:
                        continue
                    # CONSTRUCTED: frames arrive at the session's own measured cadence; a 30 s
                    # batch prefilled on arrival would hold every completed batch at question time.
                    cad = r["t_opp"] / max(r["n_frames"], 1)
                    per_batch = max(int(round(BATCH_S / cad)), 1)
                    warm = (r["n_frames"] // per_batch) * per_batch
                    cov.append(warm / r["n_frames"])
                    hit.append(1.0 if warm > 0 else 0.0)
        if not per_q:
            continue
        res[arm] = dict(sessions=len(per_q), questions_per_history=_summ(per_q),
                        gap_s_between_questions_same_history=_summ(gaps),
                        constructed_warm_prefix_fraction=_summ(cov),
                        constructed_fraction_with_any_warm_prefix=(round(sum(hit) / len(hit), 4)
                                                                   if hit else None))
        qp = res[arm]["questions_per_history"] or {}
        wp = res[arm]["constructed_warm_prefix_fraction"] or {}
        print("   %-22s sessions %4d  q/history p50 %s max %s  gaps n %d  warm-prefix frac p50 %s  any-warm %s"
              % (arm, len(per_q), qp.get("p50"), qp.get("max"), len(gaps), wp.get("p50"),
                 res[arm]["constructed_fraction_with_any_warm_prefix"]))
    return res


def item4():
    """Warming budget. MEASURED at 16 devices from the robot sessions the runs actually carried;
    PROJECTED at 18 by scaling per robot device, because no 18-device cell exists yet."""
    print("\n4. WARMING BUDGET, prefill every %.0f s batch of every robot history" % BATCH_S)
    # One arm is enough for the workload side: the sessions and their frames come from the trace,
    # not from the policy. b7 is used because it sends the fewest, so its frame counts are the
    # ones no policy choice inflated; the sessions themselves are identical across arms.
    cells = [(a, n, s, d) for a, n, s, d in _cells() if a == "b7-edf-feasibility"]
    per_cell = {}
    for a, n, s, d in cells:
        rows = [r for r in robot_rows(d) if r["served"] and r["n_frames"]]
        devs = sorted({r["session"].split("|")[0] for r in robot_rows(d)})
        tok_per_frame, gpu_s, peak_tokens = [], 0.0, 0
        hist = {}
        for r in rows:
            tpf = (r["prompt_tokens"] or 0) / max(r["n_frames"], 1)
            tok_per_frame.append(tpf)
            cad = r["t_opp"] / max(r["n_frames"], 1)
            per_batch = max(int(round(BATCH_S / cad)), 1)
            n_batches = max(r["n_frames"] // per_batch, 1)
            new_tokens = per_batch * tpf
            # Each batch is a prefill of its own new tokens on top of a warm prefix, charged with
            # the committed COLD curve on the NEW tokens only. MODEL, not a measurement.
            gpu_s += n_batches * C.recall_gpu_s(max(int(new_tokens), 1), "COLD")
            hist[r["session"]] = max(hist.get(r["session"], 0), int(r["prompt_tokens"] or 0))
        peak_tokens = sum(hist.values())
        per_cell["%s_n%d_s%d" % (a, n, s)] = dict(
            robot_devices=len([x for x in devs if x.startswith("robo")]),
            robot_sessions_with_questions=len(hist),
            tokens_per_frame=_summ(tok_per_frame),
            warming_gpu_s_total=round(gpu_s, 2),
            warming_gpu_s_per_1200s_run_fraction=round(gpu_s / 1200.0, 4),
            peak_resident_tokens_if_all_kept=peak_tokens,
            gpu_pool_tokens=GPU_POOL_TOKENS,
            peak_over_gpu_pool=round(peak_tokens / GPU_POOL_TOKENS, 3),
            host_tier_tokens=HOST_TIER_TOKENS,
            peak_over_host_tier=round(peak_tokens / HOST_TIER_TOKENS, 3),
            peak_over_gpu_plus_host=round(peak_tokens / (GPU_POOL_TOKENS + HOST_TIER_TOKENS), 3),
            peak_gib=round(peak_tokens * HOST_BYTES_PER_TOKEN / 1024 ** 3, 2))
        c = per_cell["%s_n%d_s%d" % (a, n, s)]
        print("   %-22s robots %2d sessions %3d  warm GPU-s %8.1f (%.1f%% of the run)  peak KV %7d tokens = %.2fx the pool"
              % ("n%d s%d" % (n, s), c["robot_devices"], c["robot_sessions_with_questions"],
                 c["warming_gpu_s_total"], 100.0 * c["warming_gpu_s_per_1200s_run_fraction"],
                 c["peak_resident_tokens_if_all_kept"], c["peak_over_gpu_pool"]))
    # PROJECTION to 18 devices: the ratio of robot devices, nothing else.
    base = [v for v in per_cell.values()]
    if base:
        rd = stat.median([v["robot_devices"] for v in base]) or 1
        gs = stat.median([v["warming_gpu_s_total"] for v in base])
        pk = stat.median([v["peak_resident_tokens_if_all_kept"] for v in base])
        proj = {}
        for n_dev in (16, 18):
            k = round(rd * n_dev / 16.0)
            proj["n%d" % n_dev] = dict(robot_devices_assumed=k,
                                       warming_gpu_s=round(gs * k / rd, 1),
                                       peak_resident_tokens=int(pk * k / rd),
                                       over_gpu_pool=round(pk * k / rd / GPU_POOL_TOKENS, 3))
            print("   PROJECTED n=%d: %d robot devices, warm GPU-s %.1f, peak KV %d tokens, %.2fx the pool"
                  % (n_dev, k, proj["n%d" % n_dev]["warming_gpu_s"],
                     proj["n%d" % n_dev]["peak_resident_tokens"], proj["n%d" % n_dev]["over_gpu_pool"]))
        return dict(measured_cells=per_cell, projection=proj,
                    _host_tier_gib=HOST_GIB,
                    _note="peak_resident_tokens sums the LARGEST history per robot session that "
                          "carried a question; it is an upper bound on what keeping every history "
                          "warm would hold, and it ignores sessions that never asked anything.")
    return dict(measured_cells=per_cell)


def item5():
    """Value per GPU-second from the committed tables. The values do NOT share a unit."""
    print("\n5. CROSS-TYPE VALUE PER GPU-SECOND (committed tables; units differ, see the note)")
    ssq = json.loads((REPO / "results/orchestration/prof1/ss_quality.json").read_text())
    lhq = json.loads((REPO / "results/orchestration/live2/lh_req/lh_req_quality.json").read_text())
    c1 = ssq["_c1_ordering_consequence"]["c1_values"]
    ev = lhq["per_split"]["EVAL"]
    dv = lhq["per_split"]["DEV"]
    q = ssq["question_type_to_representation"]
    # Measured prompt sizes per type, pooled over the seeds 4 5 6 cells of every arm.
    tok = defaultdict(list)
    for a, n, s, d in _cells():
        req = {r["request_id"]: r for r in _load(d, "request")}
        for o in _load(d, "outcomes"):
            cp = o.get("cloud_payload") or {}
            r = req.get(cp.get("request_id"))
            if r is None or not r.get("prompt_tokens"):
                continue
            ses = str(o.get("session_id") or "")
            kind = ("robot" if ses.startswith("robo") else
                    "single_shot" if ses.startswith("asst") else "dashcam")
            tok[kind].append(int(r["prompt_tokens"]))
    rows = []
    gains = dict(robot_eval=(ev["cloud_D2"]["accuracy"] - ev["device_4B_RECENT"]["accuracy"]),
                 robot_dev=(dv["cloud_D2"]["accuracy"] - dv["device_4B_RECENT"]["accuracy"]),
                 ss_refspatial=(q["refspatial"]["cloud_accuracy"] - q["refspatial"]["_device_accuracy"]),
                 ss_realworldqa=(q["realworldqa"]["cloud_accuracy"] - q["realworldqa"]["_device_accuracy"]),
                 dashcam_c1_value=c1["dashcam"])
    for label, gain, kind in (("robot LH-REQ EVAL", gains["robot_eval"], "robot"),
                              ("robot LH-REQ DEV", gains["robot_dev"], "robot"),
                              ("SS refspatial", gains["ss_refspatial"], "single_shot"),
                              ("SS realworldqa", gains["ss_realworldqa"], "single_shot"),
                              ("dashcam (c1 value)", gains["dashcam_c1_value"], "dashcam")):
        med = _q(tok[kind], 0.5) or 1
        gpu = C.recall_gpu_s(int(med), "COLD")
        rows.append(dict(axis=label, gain=round(gain, 6), median_prompt_tokens=int(med),
                         modelled_gpu_s=round(gpu, 4),
                         gain_per_gpu_s=round(gain / gpu, 6) if gpu else None))
        print("   %-20s gain %8.5f  median prompt %6d tok  GPU-s %7.4f  gain per GPU-s %8.4f"
              % (label, gain, med, gpu, gain / gpu))
    return dict(rows=rows, c1_values=c1,
                _metric_incomparability=ssq["_metric_incomparability"],
                _gpu_s_register="MODELLED: the committed COLD curve (costs.recall_gpu_s) on the "
                                "MEASURED median prompt of that type in these cells, not a "
                                "measured GPU time.")


def item1b():
    """What the committed delivery stamp is worth. The runs were launched with forward_at = "first"
    (run_meta.json), so an answer is stamped delivered at its FIRST TOKEN plus a constant wire
    delay: measured as exactly 0.022176 s in 13,558 of 13,558 answers of one cell, which is why
    the "after the first token" column of item 1 is a constant rather than a distribution. The
    generation that follows is real (t_done - t_first_token, p50 0.058 s, max 2.715 s) and is not
    charged to any deadline. This reports how many questions would change verdict if delivery were
    stamped at COMPLETION instead, which is the same question the first-token flag already exposes.
    It is a DEFINITION AUDIT (consistency check 4), not a defect: for an MCQ letter the first token
    IS the answer, and for RefSpatial coordinates it is not."""
    print("\n1b. DELIVERY STAMP: first token (committed) against completion")
    print("   %-26s %-12s %5s %8s %8s %6s" % ("cell", "type", "n", "on_time", "at_done", "flip"))
    res = {}
    for a, n, s_, d in _cells(seeds=(4, 5)):
        req = {r["request_id"]: r for r in _load(d, "request")}
        agg = defaultdict(lambda: [0, 0, 0])
        for o in _load(d, "outcomes"):
            if o["kind"] != "recall":
                continue
            ses = str(o.get("session_id") or "")
            kind = "robot" if ses.startswith("robo") else "single_shot"
            cp = o.get("cloud_payload") or {}
            r = req.get(cp.get("request_id"))
            if r is None or not o.get("t_delivered"):
                continue
            lim = ROB_L2_S if kind == "robot" else SS_L_S
            ok = (o["t_delivered"] - o["t_opportunity"]) <= lim + 1e-9
            ok2 = ((r["t_done"] + WIRE_S - o["t_opportunity"]) <= lim + 1e-9
                   and r.get("http_status") in (200, None))
            v = agg[kind]
            v[0] += 1
            v[1] += int(ok)
            v[2] += int(ok2)
        for kind, (nn, ok, ok2) in sorted(agg.items()):
            res["%s_n%d_s%d_%s" % (a, n, s_, kind)] = dict(n=nn, on_time_committed=ok,
                                                           on_time_at_completion=ok2, flip=ok - ok2)
            print("   %-26s %-12s %5d %8d %8d %6d" % ("%s n%d s%d" % (a, n, s_), kind, nn, ok, ok2,
                                                      ok - ok2))
    return res


def item6():
    """The over-context question, every arm's decision for it, from the live logs."""
    print("\n6. THE OVER-CONTEXT QUESTION (opp0010837, robo002, session 1848337166005249)")
    res = {}
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir() or not d.name.endswith("_n16_s0_1200s_h27_3t") or "REFUSED" in d.name:
            continue
        req = {r["request_id"]: r for r in _load(d, "request")}
        for o in _load(d, "outcomes"):
            if o["opportunity_id"] != "opp0010837":
                continue
            cp = o.get("cloud_payload") or {}
            r = req.get(cp.get("request_id"))
            res[d.name] = dict(sent=bool(r), representation=cp.get("representation"),
                               tokens_charged=cp.get("tokens_charged"),
                               frames_on_the_wire=len((r or {}).get("mm_uuids") or []),
                               http_status=(r or {}).get("http_status"),
                               prompt_tokens=(r or {}).get("prompt_tokens"),
                               letter=cp.get("cloud_letter"), on_time_recorded=cp.get("on_time"))
            print("   %-40s sent %-5s rep %-7s charged %-5s frames %-4s status %-5s letter %-4s on_time %s"
                  % (d.name[:40], bool(r), cp.get("representation"), cp.get("tokens_charged"),
                     len((r or {}).get("mm_uuids") or []), (r or {}).get("http_status"),
                     cp.get("cloud_letter"), cp.get("on_time")))
    res["_mechanism"] = {
        "b7_and_mooncake": "REJECT. The feasibility test predicts a COLD prefill of the whole "
                           "history (33,781 tokens) against a 5 s deadline and rejects, so the "
                           "question is answered on the device and never reaches the cloud.",
        "hybrid_F_and_eco_llm": "CLOUD at representation RECENT. hybrid_arm.py:315-318 converts "
                                "exactly the rejected case into a send, promising the 467-token "
                                "recent window, which the committed curve says is feasible.",
        "why_the_promise_is_not_kept": "coordinator.py:574 charges tokens_for_representation "
                                       "(467), while coordinator.py:593-597 builds the body from "
                                       "s.frames, the WHOLE session: 375 image parts went on the "
                                       "wire and the server refused the request with HTTP 400. "
                                       "C3's RECENT is expressible in the accounting and "
                                       "unexpressible in the payload.",
        "scoring_consequence": "coordinator.py:781 computes ontime from the completion time alone, "
                               "so the refused request was recorded as an on-time cloud answer with "
                               "the placeholder letter X. D144 ruling 3 makes it a miss.",
    }
    return res


if __name__ == "__main__":
    out = dict(_note=__doc__.strip().splitlines()[0])
    out["item1_robot_miss_decomposition"] = item1()
    out["item1b_delivery_stamp"] = item1b()
    out["item2_gpu_resident_history"] = item2()
    out["item3_reuse"] = item3()
    out["item4_warming_budget"] = item4()
    out["item5_value_per_gpu_s"] = item5()
    out["item6_over_context_question"] = item6()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=float))
    print("\nwrote", OUT)
