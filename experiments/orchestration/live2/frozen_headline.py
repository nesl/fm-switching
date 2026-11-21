#!/usr/bin/env python3
"""StudyFROZEN-test headline (user ruling 2026-11-20): pooled per-arm rates across seeds with PAIRED-BY-SEED bootstrap CIs.

Rates per arm, pooled over the seeds where EVERY listed arm has a kept run (common support):
  robot on time over FEASIBLE questions (D133; flash's feasibility rule per robot question from the run's own trace),
  SS on time within 2 s, dashcam all-meet (share of runs).
On time = delivered within the deadline by a request that returned HTTP 200 (D144 as corrected 2026-11-20).
Pairing: every arm runs the SAME trace per seed, so a question is the same opportunity across arms. Bootstrap resamples
opportunities WITHIN each seed (stratified), the same draw applied to every arm, B = 10,000; differences against b7 use
the same draws. Measurability (D82): >= 20 robot questions per run (all robot questions), feasible count reported beside.
The first attempt of a cell is the cell (reruns ignored). Read-only; run only when no live run's preflight can overlap.

Usage: python frozen_headline.py <runs dir> <n_devices> <out json>
"""
import gzip
import json
import os
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, HERE / "fleet", HERE / "scorer", REPO / "experiments/orchestration/baselines",
          REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    sys.path.insert(0, str(p))
import costs as C          # noqa: E402
import traces as TRC       # noqa: E402
import trace as TR         # noqa: E402
import data_sources as DS  # noqa: E402
# D155 (3): the DEVICE side of the delivery rule is IMPORTED from the production scorer, never
# re-implemented here and never read from an environment variable of this file's own. The D146
# `DELIVERY` switch was module-level in score.py and local in this file, the two scorers
# disagreed, and it had to be hoisted by hand. `device_within` and `device_delivery_rule` have
# exactly one definition, so the two scorers cannot drift apart on which device answers count.
import score as SC         # noqa: E402

ARMS = ["b7-edf-feasibility", "eco-llm", "mooncake", "hybrid-F-lhreq", "hybrid-F6-lhreq"]
if os.environ.get("FROZEN_HEADLINE_ARMS"):
    ARMS = [a for a in os.environ["FROZEN_HEADLINE_ARMS"].split(",") if a]
B = 10000
SS_L = 2.0
P_ROB = 0.9              # the scorer's robot pool threshold, from the run's own sweep block
FRAGILE_MARGIN = 1       # a verdict is FRAGILE when this many questions would flip it


def local_trace(trace_dir_name):
    """Regenerate a run's trace from its directory name, for a box that does not hold the H100's
    trace tree. The generator is deterministic in (seed, n, ratio, run_s, mode) by its own
    docstring, and the control is in the caller: the regenerated robot opportunity ids must equal
    the ids the run's own outcomes carry, or the run is skipped rather than scored on a guess.

    Name shape: seed6_n16_1200s_A_r40-40-20_lh_req_ss2
    """
    parts = str(trace_dir_name).split("_")
    # A trailing _L<x> is the D147 robot deadline, not part of the question-set name. The
    # generator takes no deadline argument: run_live2_real.py:447 sets DS.ROBOT_DEADLINE_S before
    # generating, so a 3 s trace is reproduced by setting the same global here. Getting this wrong
    # is caught rather than scored, by the caller's id-equality control.
    # B3 made 3.0 the DEFAULT `DS.ROBOT_DEADLINE_S`, so "leave the global alone when there is no
    # _L tag" stopped being safe: an UN-SUFFIXED directory means 5 s by the trace-name anchor, and
    # regenerating it under a 3.0 global would have written 3 s deadlines into a 5 s cell's
    # questions and scored the whole committed 5 s family against the wrong bound with nothing
    # looking wrong. The absent tag is therefore resolved EXPLICITLY to the anchor.
    deadline = DS.TRACE_NAME_ANCHOR_DEADLINE_S
    if parts and parts[-1].startswith("L") and parts[-1][1:].replace(".", "", 1).isdigit():
        deadline = float(parts[-1][1:])
        parts = parts[:-1]
    kw = dict(seed=int(parts[0][4:]), n=int(parts[1][1:]), run_s=float(parts[2][:-1]),
              mode=parts[3], ratio=parts[4][1:].replace("-", ":"),
              robot_question_set="_".join(parts[5:-1]), ss_question_set=parts[-1])
    prev = DS.ROBOT_DEADLINE_S
    try:
        DS.ROBOT_DEADLINE_S = float(deadline)
        t = TR.generate_trace(kw["seed"], kw["n"], kw["ratio"], kw["run_s"], kw["mode"],
                              robot_question_set=kw["robot_question_set"],
                              ss_question_set=kw["ss_question_set"])
    finally:
        DS.ROBOT_DEADLINE_S = prev
    return t["records"] if isinstance(t, dict) else t


DELIVERY = os.environ.get("FROZEN_HEADLINE_DELIVERY", "completion")
if DELIVERY not in ("completion", "first_token"):
    raise SystemExit("FROZEN_HEADLINE_DELIVERY must be completion or first_token")


def jl(p):
    for c in (p, p.with_name(p.name + ".gz")):
        if c.exists():
            op = gzip.open if c.suffix == ".gz" else open
            with op(c, "rt") as f:
                return [json.loads(x) for x in f if x.strip()]
    raise FileNotFoundError(p)


_ANS = {}


def device_answers_for(seed, trace_dir):
    """{opportunity_id: the device answer ROW} for one cell's robot questions.

    It returns the whole row, not a (gold, correct) pair, because D155 (3) needs the row's
    `device_latency_s` and `question_id` as well, and `score.device_latency_s` reads them from the
    row itself. The pair was the committed shape; widening it to the row keeps one join key.

    Read from the run's own trace directory when it is present, and regenerated otherwise, because
    only one trace is committed. The regeneration is verified rather than assumed: regenerating
    seed 4 reproduces the committed `device_answers.jsonl` sha256 EXACTLY. The regenerated
    `trace.jsonl` does not match, in one field only, `frame_bytes` on monitor records (the D103 (h)
    median fallback), which is why this helper reads ONLY device answers and never frame bytes.
    """
    ap = Path(trace_dir) / "device_answers.jsonl"
    rows = None
    if ap.exists() or ap.with_name(ap.name + ".gz").exists():
        rows = jl(ap)
    else:
        if seed in _ANS:
            return _ANS[seed]
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            b = TR.generate_trace(seed, 16, "40:40:20", 1200.0, "A",
                                  robot_question_set="lh_req", ss_question_set="ss2")
            TR.write_trace(Path(d) / "t", b)
            rows = [json.loads(x) for x in open(Path(d) / "t" / "device_answers.jsonl")]
    out = {r["opportunity_id"]: r for r in rows
           if r.get("kind") == "recall" and r.get("gold_letter") is not None}
    _ANS[seed] = out
    return out


def run_flags(d):
    c = json.loads((d / "cell.json").read_text())
    tp = Path(c["trace_dir"]) / "trace.jsonl"
    tr = jl(tp) if (tp.exists() or tp.with_name(tp.name + ".gz").exists()) \
        else local_trace(Path(c["trace_dir"]).name)
    link = TRC.RTT_MS / 1000.0
    feas, ssq = {}, set()
    dls = {}        # D155 (3): the per-question deadline, which the DEVICE is now held to as well
    for r in tr:
        if r.get("kind") != "recall_question":
            continue
        dev = str(r.get("device_id", ""))
        if dev.startswith("robo"):
            h = int(r.get("history_tokens") or 0)
            # D147: the deadline comes from the QUESTION, never from a literal. A silent 5.0
            # here would score a 3 s run against a 5 s bound and nothing would look wrong, so an
            # absent deadline raises instead.
            if r.get("deadline_s") is None:
                raise AssertionError("recall_question %s carries no deadline_s; refusing to "
                                     "assume one" % r.get("opportunity_id"))
            feas[r["opportunity_id"]] = (C.recall_ttft_s(h, "COLD") + C.recall_ttft_s(h, "GPU-WARM") + link) <= float(r["deadline_s"])
            dls[r["opportunity_id"]] = float(r["deadline_s"])
        elif dev.startswith("asst"):
            ssq.add(r["opportunity_id"])
    failed = {r.get("request_id") for r in jl(d / "request.jsonl") if r.get("http_status") != 200}
    # D146: a robot or single-shot answer is delivered at COMPLETION, prefill plus decode, and
    # COMPLETION IS NOW THE DEFAULT. The committed `t_delivered` is first-token based: in all 40
    # frozen-grid runs `outcomes.t_cloud_done` equals the request log's `t_first_token` exactly,
    # and `t_delivered` is that plus a per-row forward delay. The completion stamp is therefore
    # the request's `t_done` plus the SAME per-row forward delay, which is taken from the data
    # rather than assumed to be the 0.0222 s constant it turns out to be.
    done = {}
    for r in jl(d / "request.jsonl"):
        if r.get("opportunity_id") and r.get("t_done") is not None:
            done[r["opportunity_id"]] = float(r["t_done"])
    ont = {}
    for o in jl(d / "outcomes.jsonl"):
        if o.get("kind") != "recall":
            continue
        td = o.get("t_delivered")
        if DELIVERY == "completion" and td is not None and o.get("t_cloud_done") is not None \
                and o["opportunity_id"] in done:
            td = done[o["opportunity_id"]] + (float(td) - float(o["t_cloud_done"]))
        rid = (o.get("cloud_payload") or {}).get("request_id")
        if o["opportunity_id"] not in ssq and o.get("deadline_s") is None:
            raise AssertionError("recall outcome %s carries no deadline_s; refusing to assume one"
                                 % o["opportunity_id"])
        L = SS_L if o["opportunity_id"] in ssq else float(o["deadline_s"])
        ont[o["opportunity_id"]] = bool(td is not None and rid not in failed and float(td) - float(o["t_opportunity"]) <= L)
    sw = (((c.get("score") or {}).get("score") or {}).get("sweep") or [{}])[0]
    # CONTROL: the regenerated trace must name the same robot questions the run itself recorded.
    robot_in_run = {o["opportunity_id"] for o in jl(d / "outcomes.jsonl")
                    if o.get("kind") == "recall" and str(o.get("session_id", "")).startswith("robo")}
    if robot_in_run != set(feas):
        raise AssertionError("%s: trace and run disagree on the robot questions (%d vs %d)"
                             % (d.name, len(feas), len(robot_in_run)))
    # D152: the robot headline is CORRECT ANSWERS DELIVERED, the cloud's answer when it arrives
    # on time and the device's otherwise, scored on the representation actually sent. On time is
    # reported beside it. The cloud letter actually produced is compared to the gold letter, so a
    # release made as RECENT is scored as RECENT and no accuracy table is consulted.
    #
    # D155 (3) AMENDS D152 (1). A DEVICE answer now counts only if it ARRIVES WITHIN THE DEADLINE
    # (`corr_bd`, the headline); the D152 (1) behaviour that credits a device answer regardless of
    # when it lands is kept as `corr_any` and REPORTED BESIDE IT. The two never share a column.
    # Whether a device answer is on time is decided by `score.device_within`, imported above, so
    # this file and the production scorer apply one rule to one latency source.
    ans = device_answers_for(int(c["seed"]), c["trace_dir"])
    cl = {}
    for o in jl(d / "outcomes.jsonl"):
        if o.get("kind") == "recall":
            cl[o["opportunity_id"]] = (o.get("cloud_payload") or {}).get("cloud_letter")
    corr_any, corr_bd, dev_late = {}, {}, {}
    # D152 (1)'s headline CREDITS the device answer as the fallback, so the fallback's own
    # standalone number belongs beside every arm rather than being inferred from the arms. These
    # two maps are ARM-INDEPENDENT (one trace per seed, shared by every arm), which is exactly why
    # they are a usable floor: they say what the device alone would deliver.
    dev_only_any, dev_only_bd, dev_lat = {}, {}, {}
    for k in feas:
        dev = ans.get(k)
        if dev is None:
            continue
        gold, dev_ok = dev["gold_letter"], bool(dev["device_correct"])
        cloud_stands = bool(ont.get(k) and cl.get(k))
        # the committed D152 (1) expression, unchanged
        corr_any[k] = bool((cl.get(k) == gold) if cloud_stands else dev_ok)
        on_t = SC.device_within({}, dev, dls[k])
        dev_late[k] = not on_t
        corr_bd[k] = bool((cl.get(k) == gold) if cloud_stands else (dev_ok and on_t))
        dev_only_any[k] = dev_ok
        dev_only_bd[k] = bool(dev_ok and on_t)
        # the latency the SCORER used, which under the measured source is NOT the trace's own
        # `device_latency_s` field. Reading the trace field here would report the superseded D87
        # interpolation in a run scored on the measured table, and nothing would look wrong.
        dev_lat[k] = round(SC.device_latency_s(dev), 6)
    nfeas = sum(1 for v in feas.values() if v)
    hits_f = sum(1 for k, v in feas.items() if v and ont.get(k))
    # D133 verdict per run, with its margin. p_rob is read from the run's own sweep where present.
    p_rob = float(sw.get("p_rob") or P_ROB)
    # The smallest number of on-time questions that MEETS the bar: ceil(p_rob x n), not round().
    need = (math.ceil(p_rob * nfeas - 1e-9) if nfeas else 0)
    return dict(robot_correct_by_deadline=dict(corr_bd),
                robot_correct_any_time=dict(corr_any),
                device_only_by_deadline=dict(dev_only_bd),
                device_only_any_time=dict(dev_only_any),
                device_latency_s=dict(dev_lat),
                device_late_n=sum(1 for v in dev_late.values() if v),
                device_latency_s_range=([round(min(dev_lat.values()), 6),
                                         round(max(dev_lat.values()), 6)]
                                        if dev_lat else None),
                deadline_s_range=([min(dls.values()), max(dls.values())] if dls else None),
                robot_feasible={k: ont.get(k, False) for k, v in feas.items() if v},
                robot_all_map={k: ont.get(k, False) for k in feas}, robot_all=len(feas),
                ss={k: ont.get(k, False) for k in ssq}, dash=bool(sw.get("dashcam_all_meet")),
                errors=c.get("n_errors"), requests=c.get("n_requests"),
                d133=dict(p_rob=p_rob, feasible=nfeas, on_time=hits_f,
                          robot_pool_meets=bool(nfeas and hits_f >= need),
                          need_to_meet=need, margin_questions=(hits_f - need if nfeas else None),
                          fragile=bool(nfeas and abs(hits_f - need) <= FRAGILE_MARGIN),
                          capacity_met=bool(sw.get("capacity_met")),
                          scorer_robot_pool_meets=sw.get("robot_pool_meets")))


def main(runs_dir, n, out):
    n = int(n)
    R = Path(runs_dir)
    runs = {}
    # D145 / user ruling 2026-11-20: eco-llm and hybrid-F-lhreq were REDONE after the RECENT-send
    # fix, so their post-fix cells are the ones to score. hybrid-F6 is NOT redone (D145 option b)
    # and stays pre-fix, labelled. b7 and mooncake have no post-fix cells and are unchanged.
    # FROZEN_HEADLINE_CELLS=prefix scores the pre-fix cells for every arm, which is what section
    # 18.3 did, so the two can be compared.
    POSTFIX = ({} if os.environ.get("FROZEN_HEADLINE_CELLS") == "prefix"
               else {"eco-llm": "_postfix", "hybrid-F-lhreq": "_postfix"})
    for a in ARMS:
        for s in (0, 4, 5, 6):
            # FROZEN_HEADLINE_SUFFIX scores a different deadline family of cells, e.g. _L3
            # for the D147 3 s handful. POSTFIX does not apply to those: they are new cells.
            _sfx = os.environ.get("FROZEN_HEADLINE_SUFFIX", "")
            d = R / (f"{a}_n{n}_s{s}_1200s_h27_3t" + (_sfx or POSTFIX.get(a, "")))
            if (d / "cell.json").exists():
                c = json.loads((d / "cell.json").read_text())
                if c.get("err") is None and c.get("run_valid") and c.get("digests_equal"):
                    runs[(a, s)] = run_flags(d)
    seeds = [s for s in (0, 4, 5, 6) if all((a, s) in runs for a in ARMS)]
    # the opportunity sets per seed are shared across arms (same trace); take them from b7
    rob_ids = {s: sorted(runs[("b7-edf-feasibility", s)]["robot_feasible"]) for s in seeds}
    all_ids = {s: sorted(runs[("b7-edf-feasibility", s)]["robot_all_map"]) for s in seeds}
    ss_ids = {s: sorted(runs[("b7-edf-feasibility", s)]["ss"]) for s in seeds}
    for s in seeds:
        for a in ARMS:
            assert sorted(runs[(a, s)]["robot_feasible"]) == rob_ids[s] and sorted(runs[(a, s)]["ss"]) == ss_ids[s], (a, s)
            assert sorted(runs[(a, s)]["robot_all_map"]) == all_ids[s], (a, s)

    def pooled(a, rdraw, adraw, sdraw):
        rn = sum(runs[(a, s)]["robot_feasible"][k] for s in seeds for k in rdraw[s])
        rd = sum(len(rdraw[s]) for s in seeds)
        an = sum(runs[(a, s)]["robot_all_map"][k] for s in seeds for k in adraw[s])
        ad = sum(len(adraw[s]) for s in seeds)
        sn = sum(runs[(a, s)]["ss"][k] for s in seeds for k in sdraw[s])
        sd = sum(len(sdraw[s]) for s in seeds)
        # D152 / D155: correct answers delivered, over the SAME denominator as robot_all (every
        # robot question). Under D155 (3) a question where neither the cloud nor the device makes
        # the deadline stays in that denominator and counts as a miss, which is why the
        # denominator does not change between the two columns.
        cb = sum(runs[(a, s)]["robot_correct_by_deadline"].get(k, False)
                 for s in seeds for k in adraw[s])
        ca = sum(runs[(a, s)]["robot_correct_any_time"].get(k, False)
                 for s in seeds for k in adraw[s])
        return rn / rd, an / ad, sn / sd, cb / ad, ca / ad

    import numpy as np
    point = {a: pooled(a, rob_ids, all_ids, ss_ids) for a in ARMS}
    rng = np.random.default_rng(0)
    # per seed: an arms x questions 0/1 matrix; one index draw per seed per replicate, shared by every arm (paired)
    rob_num = np.zeros((len(ARMS), B)); ss_num = np.zeros((len(ARMS), B))
    all_num = np.zeros((len(ARMS), B))
    cbd_num = np.zeros((len(ARMS), B)); cat_num = np.zeros((len(ARMS), B))
    rob_den = sum(len(rob_ids[s]) for s in seeds); ss_den = sum(len(ss_ids[s]) for s in seeds)
    all_den = sum(len(all_ids[s]) for s in seeds)
    for s in seeds:
        # the correctness draw must be the SAME index draw as robot_all, so the two columns are
        # paired question by question and their difference is meaningful
        draws = {}
        for ids, num, key in ((rob_ids[s], rob_num, "robot_feasible"), (ss_ids[s], ss_num, "ss"),
                              (all_ids[s], all_num, "robot_all_map")):
            if not ids:
                continue
            M = np.array([[runs[(a, s)][key][k] for k in ids] for a in ARMS], dtype=float)
            idx = rng.integers(0, len(ids), size=(B, len(ids)))
            draws[key] = idx
            num += M[:, idx].sum(axis=2)
        if all_ids[s]:
            # both correctness columns use the SAME index draw as robot_all, so the three are
            # paired question by question and any difference between them is the rule, not the draw
            for key, num in (("robot_correct_by_deadline", cbd_num),
                             ("robot_correct_any_time", cat_num)):
                M = np.array([[runs[(a, s)][key].get(k, False) for k in all_ids[s]]
                              for a in ARMS], dtype=float)
                num += M[:, draws["robot_all_map"]].sum(axis=2)
    boots = {a: list(zip(rob_num[i] / rob_den, all_num[i] / all_den, ss_num[i] / ss_den,
                         cbd_num[i] / all_den, cat_num[i] / all_den))
             for i, a in enumerate(ARMS)}

    def ci(xs):
        xs = sorted(float(x) for x in xs)
        return [round(xs[int(0.025 * B)], 4), round(xs[int(0.975 * B)], 4)]

    # ------------------------------------------------------------ THE DEVICE-ONLY ROW.
    # D152 (1)'s headline credits the device answer as the fallback whenever the cloud misses, so
    # the fallback's own standalone number belongs beside every arm: it is the floor any arm has to
    # beat, and an arm below it is worse than not asking the cloud at all. It is taken from b7's
    # run because the maps are arm-independent (one trace per seed), and that is ASSERTED below
    # rather than assumed, so a map that ever became arm-dependent would stop the run.
    A0 = ARMS[0]
    for s in seeds:
        for a in ARMS:
            for key in ("device_only_by_deadline", "device_only_any_time", "device_latency_s"):
                assert runs[(a, s)][key] == runs[(A0, s)][key], (key, a, s)
    dev_bd_hits = sum(runs[(A0, s)]["device_only_by_deadline"][k] for s in seeds for k in all_ids[s])
    dev_at_hits = sum(runs[(A0, s)]["device_only_any_time"][k] for s in seeds for k in all_ids[s])
    dev_lat_all = sorted(runs[(A0, s)]["device_latency_s"][k] for s in seeds for k in all_ids[s])
    def _q(p):
        return round(float(np.percentile(np.array(dev_lat_all, dtype=float), p)), 4)
    device_only = dict(
        label="DEVICE ONLY: the measured warm device answers alone, no cloud",
        by_deadline_hits=dev_bd_hits, any_time_hits=dev_at_hits,
        n=sum(len(all_ids[s]) for s in seeds),
        by_deadline=round(dev_bd_hits / all_den, 4), any_time=round(dev_at_hits / all_den, 4),
        device_answers_late=sum(runs[(A0, s)]["device_late_n"] for s in seeds),
        device_latency_s=dict(n=len(dev_lat_all), min=round(dev_lat_all[0], 4), p10=_q(10),
                              p25=_q(25), p50=_q(50), p75=_q(75), p90=_q(90),
                              max=round(dev_lat_all[-1], 4),
                              iqr=round(_q(75) - _q(25), 4)),
        correctness_source=("the device ANSWERS are still D87's 4B-I x RECENT StudyO-Q4 set "
                            "(A6000-produced, `data_sources.device_recall_answers`), written by "
                            "fleet/trace.py. Only the LATENCY is the Orin's measured warm value, "
                            "so this row MIXES a measured latency with a proxy correctness and is "
                            "labelled, not silently pooled. Changing the correctness source is a "
                            "methodological change and is not made here."),
        answer_length=("robot answers are 2 OUTPUT TOKENS, so the P20 answer cap is not the "
                       "device's latency lever and the measured completion is almost entirely "
                       "prefill plus fixed overhead."))

    rows = []
    for a in ARMS:
        rows.append(dict(arm=a,
                         # D155 (3): THE HEADLINE. A device answer counts only if it arrives
                         # within the deadline. On time follows it.
                         robot_correct_delivered_by_deadline=round(point[a][3], 4),
                         robot_correct_by_deadline_ci95=ci([x[3] for x in boots[a]]),
                         robot_correct_by_deadline_hits=sum(
                             runs[(a, s)]["robot_correct_by_deadline"].get(k, False)
                             for s in seeds for k in all_ids[s]),
                         # D152 (1), REPORTED BESIDE IT and never mixed with it: a device answer
                         # counts whenever it lands.
                         robot_correct_delivered_any_time=round(point[a][4], 4),
                         robot_correct_any_time_ci95=ci([x[4] for x in boots[a]]),
                         robot_correct_any_time_hits=sum(
                             runs[(a, s)]["robot_correct_any_time"].get(k, False)
                             for s in seeds for k in all_ids[s]),
                         robot_correct_n=sum(len(all_ids[s]) for s in seeds),
                         robot_correct_by_deadline_minus_any_time=round(
                             point[a][3] - point[a][4], 4),
                         device_late_n=sum(runs[(a, s)]["device_late_n"] for s in seeds),
                         robot_feasible_on_time=round(point[a][0], 4), robot_ci95=ci([x[0] for x in boots[a]]),
                         robot_feasible_n=sum(len(rob_ids[s]) for s in seeds),
                         robot_feasible_hits=sum(runs[(a, s)]["robot_feasible"][k] for s in seeds for k in rob_ids[s]),
                         robot_all_on_time=round(point[a][1], 4), robot_all_ci95=ci([x[1] for x in boots[a]]),
                         robot_all_n=sum(len(all_ids[s]) for s in seeds),
                         robot_all_hits=sum(runs[(a, s)]["robot_all_map"][k] for s in seeds for k in all_ids[s]),
                         ss_on_time=round(point[a][2], 4), ss_ci95=ci([x[2] for x in boots[a]]),
                         ss_n=sum(len(ss_ids[s]) for s in seeds),
                         ss_hits=sum(runs[(a, s)]["ss"][k] for s in seeds for k in ss_ids[s]),
                         dashcam_all_meet_runs=f"{sum(runs[(a, s)]['dash'] for s in seeds)} of {len(seeds)}",
                         robot_minus_b7_ci95=ci([x[0] - y[0] for x, y in zip(boots[a], boots['b7-edf-feasibility'])]),
                         robot_all_minus_b7_ci95=ci([x[1] - y[1] for x, y
                                                     in zip(boots[a], boots['b7-edf-feasibility'])]),
                         ss_minus_b7_ci95=ci([x[2] - y[2] for x, y
                                              in zip(boots[a], boots['b7-edf-feasibility'])]),
                         robot_correct_by_deadline_minus_b7_ci95=ci(
                             [x[3] - y[3] for x, y
                              in zip(boots[a], boots['b7-edf-feasibility'])]),
                         robot_correct_any_time_minus_b7_ci95=ci(
                             [x[4] - y[4] for x, y
                              in zip(boots[a], boots['b7-edf-feasibility'])]),
                         per_run=[dict(seed=s, robot_all=runs[(a, s)]["robot_all"], robot_feasible=len(rob_ids[s]),
                                       robot_feasible_hits=sum(runs[(a, s)]["robot_feasible"].values()),
                                       robot_all_hits=sum(runs[(a, s)]["robot_all_map"].values()),
                                       ss_hits=sum(runs[(a, s)]["ss"].values()), ss_n=len(ss_ids[s]),
                                       # D155 (3): the two headline columns PER CELL, so a reader
                                       # can see where they part company without pooling first
                                       robot_correct_by_deadline_hits=sum(
                                           runs[(a, s)]["robot_correct_by_deadline"].get(k, False)
                                           for k in all_ids[s]),
                                       robot_correct_any_time_hits=sum(
                                           runs[(a, s)]["robot_correct_any_time"].get(k, False)
                                           for k in all_ids[s]),
                                       robot_correct_n=len(all_ids[s]),
                                       dash=runs[(a, s)]["dash"], errors=runs[(a, s)]["errors"],
                                       device_late_n=runs[(a, s)]["device_late_n"],
                                       device_latency_s_range=runs[(a, s)]["device_latency_s_range"],
                                       deadline_s_range=runs[(a, s)]["deadline_s_range"],
                                       d133=runs[(a, s)]["d133"]) for s in seeds]))
    res = dict(n_devices=n, seeds_common_support=seeds, bootstrap=f"paired by seed: opportunities resampled within each seed, same draw for every arm, B={B}",
               headline="D155 (3), amending D152 (1): CORRECT ANSWERS DELIVERED BY THE DEADLINE "
                        "(the cloud's answer if it is on time, else the DEVICE's answer IF IT TOO "
                        "ARRIVES WITHIN THE DEADLINE, else no answer and the question is a miss; "
                        "scored on the representation actually sent). On time is reported beside "
                        "it, not as the headline.",
               headline_beside_it="D152 (1): CORRECT ANSWERS DELIVERED AT ANY TIME, which credits "
                                  "the device's answer regardless of when it lands. Reported "
                                  "BESIDE the headline and never mixed with it in one column or "
                                  "one sentence (D155 (3)).",
               device_delivery_rule=SC.device_delivery_rule(),
               device_only=device_only,
               on_time_rule=("delivered within the deadline (robot 5 s, SS 2 s) by an HTTP 200 "
                             "request, stamped at " + ("COMPLETION, prefill plus decode (D146; "
                             "the default from 2026-11-20)" if DELIVERY == "completion"
                             else "FIRST TOKEN (the pre-D146 rule, kept for comparison)")),
               delivery=DELIVERY,
               cells=("pre-fix for every arm"
                      if os.environ.get("FROZEN_HEADLINE_CELLS") == "prefix" else
                      "POST-FIX for eco-llm and hybrid-F-lhreq; pre-fix for b7, mooncake and "
                      "hybrid-F6-lhreq, which is not redone (D145)"),
               rows=rows)
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    print("seeds", seeds)
    print("device latency source:", SC.DEVICE_LATENCY_SOURCE, " device wait s:", SC.DEVICE_WAIT_S)
    print("\nD155 (3) HEADLINE (by deadline) and D152 (1) BESIDE IT (any time), never mixed:")
    for r in rows:
        print("   %-20s by-deadline %2d/%2d = %.4f %s  |  any-time %2d/%2d = %.4f %s  |  "
              "device answers late %d"
              % (r["arm"], r["robot_correct_by_deadline_hits"], r["robot_correct_n"],
                 r["robot_correct_delivered_by_deadline"], r["robot_correct_by_deadline_ci95"],
                 r["robot_correct_any_time_hits"], r["robot_correct_n"],
                 r["robot_correct_delivered_any_time"], r["robot_correct_any_time_ci95"],
                 r["device_late_n"]))
    do = device_only
    print("   %-20s by-deadline %2d/%2d = %.4f %-16s|  any-time %2d/%2d = %.4f %-16s|  "
          "device answers late %d"
          % ("DEVICE ONLY", do["by_deadline_hits"], do["n"], do["by_deadline"], "",
             do["any_time_hits"], do["n"], do["any_time"], "", do["device_answers_late"]))
    print("   device latency (the scorer's source, %s): n %d  min %.4f  p25 %.4f  p50 %.4f  "
          "p75 %.4f  p90 %.4f  max %.4f  IQR %.4f"
          % ((SC.DEVICE_LATENCY_SOURCE,) + tuple(
              do["device_latency_s"][k] for k in
              ("n", "min", "p25", "p50", "p75", "p90", "max", "iqr"))))
    print("\non-time tables, unchanged and labelled:")
    for r in rows:
        print(f"{r['arm']:20s} feas {r['robot_feasible_hits']}/{r['robot_feasible_n']} = {r['robot_feasible_on_time']} {r['robot_ci95']} "
              f"d {r['robot_minus_b7_ci95']} | all {r['robot_all_hits']}/{r['robot_all_n']} = {r['robot_all_on_time']} "
              f"d {r['robot_all_minus_b7_ci95']} | SS {r['ss_hits']}/{r['ss_n']} = {r['ss_on_time']} {r['ss_ci95']} "
              f"d {r['ss_minus_b7_ci95']} | dash {r['dashcam_all_meet_runs']}")
    print("\nper-run D133 (feasible pool, p_rob from the run's own sweep):")
    for r in rows:
        for pr in r["per_run"]:
            w = pr["d133"]
            print("   %-20s seed %d  %2d of %2d feasible on time, needs %2d  D133 meets %-5s "
                  "(scorer, ALL questions: %-5s)  margin %+d%s"
                  % (r["arm"], pr["seed"], w["on_time"], w["feasible"], w["need_to_meet"],
                     w["robot_pool_meets"], w["scorer_robot_pool_meets"], w["margin_questions"],
                     "  FRAGILE" if w["fragile"] else ""))


if __name__ == "__main__":
    main(*sys.argv[1:4])
