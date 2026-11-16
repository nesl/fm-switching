#!/usr/bin/env python3
"""StudyPROF1-dev: the DEV-ONLY profile tables the scheduling policy reads, as one JSON.

CPU only; no GPU, no model server, no inference. Pre-registered in `research/EXPERIMENTS.md`
(StudyPROF1-dev) before anything was computed.

THE EVIDENCE RULE THIS FILE ENFORCES (spec D6). Every table here is built from DEV data only:
Nexar / StudyD14b uses the pre-registered 90-clip DEV side (`experiments/dashcam/d14b_split.py`),
and S-EMBER uses the pre-registered 70-video DEV side of StudyB-baselines amendment 2
(`experiments/orchestration/baselines/sember_split.py`). No EVAL clip or EVAL question is read.

EVERY ENTRY CARRIES ONE OF FOUR PROVENANCE KINDS, and the policy is expected to treat them
differently:

  MEASURED        a committed measurement, cited.
  DERIVED RULE    arithmetic over committed measurements, stated here, NOT itself a measurement.
  ASSUMPTION      no measurement exists; the value is declared so the policy can run and is
                  labelled wherever it is used.
  PROPOSAL        a value computed by a stated DEV calibration rule that the user has not yet
                  approved. The policy must not enable it silently.

Entries that StudyENG1 is expected to measure carry `replace_with_eng1: true`.
"""
from __future__ import annotations

import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT / "experiments/dashcam", ROOT / "experiments/orchestration/sim",
          ROOT / "experiments/orchestration/baselines", ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import costs as C                                         # noqa: E402
import d14b_split as SP                                   # noqa: E402
import metrics as M                                       # noqa: E402
import sember_split as SS                                 # noqa: E402

OUT = ROOT / "results/orchestration/prof1"
STEP = 0.25
SETTING = "measured@25"
DELAYS_S = tuple(round(0.25 * k, 2) for k in range(13))
R1 = ROOT / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"
RH4 = ROOT / "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz"
E7 = ROOT / "results/sember/study_e7/e7_requests_h100nvl.jsonl"
F4 = ROOT / "results/device/study_f4/partA_accuracy.jsonl"
E6B = ROOT / "results/orchestration/study_e6b/e6b_traces.npz"
R1_MANIFEST = ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"


def _rows(path: Path):
    op = gzip.open if path.suffix == ".gz" else open
    for ln in op(path, "rt"):
        ln = ln.strip()
        if ln:
            yield json.loads(ln)


# ================================================================ A. u_SH
def u_sh(dev_clips: Sequence[str]) -> Dict[str, Any]:
    """u_SH(cloud, delay d, m frames) and u_SH(device), DEV clips only.

    THE MAPPING FROM AP TO BOUNDED UTILITY, stated as the row requires. StudyE9c's challenge AP
    is ALREADY a probability-like quantity in [0, 1], so the primary mapping is the IDENTITY and
    no transform is invented. Because the usable range is narrow (chance to 1), an affine
    alternative is also computed, mapping the challenge base rate to 0 and the zero-delay cloud
    32B N=1 value to 1, and is marked PROPOSAL: it changes the SCALE on which omega_k trades SH
    against RC, which is a decision for the user, not for this file.
    """
    M._ensure_sklearn_importable()
    import study_e9b_dense as B
    import study_e9d_delay as D
    ctx = B.build(step=STEP)
    sub = SP.subset_ctx(ctx, "DEV")
    ch = D.Challenge(sub)
    base = float(np.mean([ch.base[h] for h in D.CHAL_H]))

    cloud: Dict[str, Any] = {}
    for n in (1, 3):
        for cad in (0.5, 1.0):
            for d in DELAYS_S:
                sh = int(round(d / STEP))
                mc = int(round(cad / STEP))
                st = {c: D.cloud_delivered(ctx["arrs"][("32BI", n)][c], ctx["meta"][c]["G"], mc,
                                           sh) for c in dev_clips}
                pt = ch.point(st)
                cloud["m%d@%s|d%.2f" % (n, cad, d)] = dict(
                    m_frames=n, cadence_s=cad, delay_s=d, u_identity=float(pt["mAP"]),
                    challenge_ap={str(h): float(v) for h, v in pt.items() if h != "mAP"})
    m, Dd, Ld = B.device_schedule(ctx, SETTING)
    dev_stream = {c: B.held_stream(ctx["arrs"][("4BI", 1)][c], ctx["meta"][c]["G"], m, Dd)
                  for c in dev_clips}
    u_dev = float(ch.point(dev_stream)["mAP"])
    best = cloud["m1@0.5|d0.00"]["u_identity"]

    def affine(x: float) -> float:
        return float(min(max((x - base) / (best - base), 0.0), 1.0))

    for k, v in cloud.items():
        v["u_affine_proposal"] = affine(v["u_identity"])
    return dict(
        provenance="MEASURED (committed StudyD14b traces) through StudyE9d's own Challenge",
        n_dev_clips=len(dev_clips), setting=SETTING, grid_step_s=STEP,
        mapping=dict(
            primary="IDENTITY: u_SH = StudyE9c challenge mAP, which is already bounded [0, 1]",
            alternative=("AFFINE PROPOSAL: u = clip((AP - base) / (AP_zero_delay_cloud - base), "
                         "0, 1), with base = the challenge base rate averaged over horizons and "
                         "AP_zero_delay_cloud = 32B N=1 at zero delay on DEV"),
            challenge_base_rate=base, zero_delay_cloud_ap=best,
            warning=("the affine map changes the scale on which omega_k trades SH against RC; it "
                     "is a PROPOSAL and must be approved before use")),
        u_device=dict(u_identity=u_dev, u_affine_proposal=affine(u_dev),
                      cadence_s=m * STEP, hold_shift_s=Dd * STEP, latency_s=Ld,
                      provenance="MEASURED: 4BI N=1 at StudyE9b's saturated duty, StudyD8 latency"),
        cloud=cloud,
        note_on_frames=("StudyFRAMES1 found NO measurable benefit from m = 3 on held-out clips "
                        "and a negative point estimate once m = 3 pays its own upload, while the "
                        "DEV curves here show a positive m = 3 effect at short delay. The m = 3 "
                        "entries are therefore marked DEV-OPTIMISTIC: do not enable merging on "
                        "them (spec 7.9's enabling condition)."))


# ================================================================ B. RC accuracy
CATEGORY_REPRESENTATION_CANDIDATES = ("RICH", "RECENT", "D2")


def rc_tables() -> Dict[str, Any]:
    """acc(question type, representation) for the cloud 32B and the device 4B, DEV videos only.

    Sources, all per-question with a `video_id`, so the DEV restriction is exact:
      32B RICH    StudyR1 cell K1
      32B RECENT  StudyR1 cell K3
      32B D2      StudyRH4 cell D2
      4B D2       StudyE7 Job A (the harness's DEVICE answer configuration, a DEVICE PROXY)
      device N1   StudyF4 Part A on the Jetson Orin, the only true device measurement
    """
    sp = SS.split()
    dev_videos = set(sp["dev_videos"]) if "dev_videos" in sp else set(sp.get("dev", []))
    dev_q = set(sp["dev_questions"]) if "dev_questions" in sp else set()

    def tally(rows, want_cell: Optional[str] = None, construction: Optional[str] = None
              ) -> Dict[str, Any]:
        per_cat: Dict[str, List[int]] = defaultdict(list)
        n_seen = n_dev = n_dup = 0
        # these files carry repeat rows per question (retries, seeds), so ONE row per question is
        # counted: the first usable one in file order. Counting them all would weight a question
        # by how often it was retried.
        taken: set = set()
        for r in rows:
            if r.get("error") or r.get("grey"):
                continue
            if want_cell is not None and r.get("cell") != want_cell:
                continue
            if construction is not None and r.get("construction") != construction:
                continue
            n_seen += 1
            vid = r.get("video_id")
            qid = r.get("question_id")
            in_dev = (vid in dev_videos) if dev_videos else (qid in dev_q)
            if not in_dev:
                continue
            if qid in taken:
                n_dup += 1
                continue
            taken.add(qid)
            n_dev += 1
            per_cat[r["question_category"]].append(1 if r.get("correct") else 0)
        out = {}
        for cat, v in sorted(per_cat.items()):
            a = np.asarray(v, dtype=float)
            out[cat] = dict(n=int(a.size), accuracy=float(a.mean()),
                            unreliable=bool(a.size < 20))
        allv = np.asarray([x for v in per_cat.values() for x in v], dtype=float)
        return dict(by_category=out, n_dev_questions=int(allv.size), n_rows_seen=n_seen,
                    n_duplicate_rows_dropped=n_dup,
                    accuracy=float(allv.mean()) if allv.size else None)

    tables = {
        "32B-RICH": dict(source="StudyR1 cell K1 (32BI, RICH video)", tier="cloud",
                         representation="RICH", provenance="MEASURED",
                         **tally(_rows(R1), want_cell="K1")),
        "32B-RECENT": dict(source="StudyR1 cell K3 (32BI, RECENT video)", tier="cloud",
                           representation="RECENT", provenance="MEASURED",
                           **tally(_rows(R1), want_cell="K3")),
        "32B-D2": dict(source="StudyRH4 cell D2 (32BI, 2-s stride 352x256)", tier="cloud",
                       representation="D2", provenance="MEASURED",
                       **tally(_rows(RH4), want_cell="D2")),
        "4B-D2": dict(source=("StudyE7 Job A (4BI on RH4's D2 input) - DEVICE PROXY, not an "
                              "Orin measurement"), tier="device-proxy", representation="D2",
                      provenance="MEASURED (proxy)", **tally(_rows(E7), want_cell="D2")),
        "device-N1-orin": dict(source="StudyF4 Part A, 1-frame last-3-s window, Jetson Orin",
                               tier="device", representation="RECENT-1frame",
                               provenance="MEASURED",
                               **tally(r for r in _rows(F4) if int(r.get("N", 1)) == 1)),
    }
    # the question type -> representation map, fitted on DEV by argmax over the cloud tables
    rep_map = {}
    cats = sorted({c for t in tables.values() for c in t["by_category"]})
    for cat in cats:
        best, bestv, row = None, -1.0, {}
        for rep, key in (("RICH", "32B-RICH"), ("RECENT", "32B-RECENT"), ("D2", "32B-D2")):
            cell = tables[key]["by_category"].get(cat)
            if not cell:
                continue
            row[rep] = dict(accuracy=cell["accuracy"], n=cell["n"], unreliable=cell["unreliable"])
            if cell["accuracy"] > bestv:
                best, bestv = rep, cell["accuracy"]
        d2 = tables["4B-D2"]["by_category"].get(cat)
        rep_map[cat] = dict(
            representation=best, cloud_accuracy=bestv, candidates=row,
            device_accuracy_4B_D2=(d2["accuracy"] if d2 else None),
            device_minus_cloud=((d2["accuracy"] - bestv) if d2 else None),
            unreliable=any(v.get("unreliable") for v in row.values()),
            provenance="PROPOSAL: DEV argmax over the three committed cloud representations")
    return dict(
        dev_rule=("S-EMBER DEV videos from StudyB-baselines amendment 2 "
                  "(sember_split.py): %d videos, %d questions"
                  % (len(sp.get("dev_videos", [])), len(sp.get("dev_questions", [])))),
        tables=tables, question_type_to_representation=rep_map,
        device_proxy_warning=("4B-D2 is the H100 4B standing in for the device (StudyD15 Part A "
                             "rejected it as an exact numerical stand-in); device-N1-orin is the "
                             "only true device measurement and uses a different input "
                             "(1 frame, last 3 s), so the two are not interchangeable."))


# ================================================================ C. class weights
def omega(u: Dict[str, Any], rc: Dict[str, Any]) -> Dict[str, Any]:
    """A DEV calibration rule for omega_k, COMPUTED AND MARKED AS A PROPOSAL.

    THE RULE, stated before the numbers: at a stated SLO operating point, equalize the MEAN
    UTILITY GAIN PER ELIGIBLE OPPORTUNITY that a successful cloud action produces in each class,
    so that one unit of omega-weighted utility means the same thing in every class and the
    coordinator's DeltaJ comparisons are not dominated by whichever class happens to be measured
    on a wider scale. omega_k = 1 / gain_k, normalized so that the SH class has weight 1.

    THE OPERATING POINT, stated: SH at the committed cloud latency (32B N=1, setting (ii),
    0.3950 s, hold shift 0.50 s) against the device at its own cadence; RC with the DEV-chosen
    representation per question type against the device's D2 answer, averaged over question
    types weighted by their DEV question counts. SS is NOT included: no committed measurement
    gives an SS accuracy pair on this workload, so its weight is left null rather than invented.
    """
    sh_cloud = u["cloud"]["m1@0.5|d0.50"]["u_identity"]
    sh_gain = sh_cloud - u["u_device"]["u_identity"]
    rows = []
    num = den = 0.0
    for cat, v in rc["question_type_to_representation"].items():
        if v["device_accuracy_4B_D2"] is None or v["cloud_accuracy"] is None:
            continue
        n = max((v["candidates"].get(v["representation"]) or {}).get("n", 0), 0)
        g = v["cloud_accuracy"] - v["device_accuracy_4B_D2"]
        rows.append(dict(question_type=cat, n_dev=n, representation=v["representation"],
                         cloud=v["cloud_accuracy"], device=v["device_accuracy_4B_D2"], gain=g))
        num += n * g
        den += n
    rc_gain = num / den if den else None
    out = dict(
        provenance="PROPOSAL - requires user approval before the policy uses it",
        rule=("equalize the mean utility gain per eligible opportunity across classes at the "
              "stated operating point; omega_k = 1 / gain_k normalized to omega_SH = 1"),
        operating_point=dict(
            SH=("32B N=1 at setting (ii), cadence 0.5 s, hold shift 0.50 s, against the device "
                "arm at its own 0.75-s cadence, on DEV clips"),
            RC=("the DEV-chosen representation per question type against the 4B-D2 device answer, "
                "averaged over question types weighted by DEV question counts"),
            SS="EXCLUDED: no committed SS accuracy pair exists on this workload"),
        gains=dict(SH=sh_gain, RC=rc_gain, SS=None), per_question_type=rows)
    if rc_gain and sh_gain:
        out["omega"] = dict(SH=1.0, RC=float(sh_gain / rc_gain), SS=None)
        out["reading"] = ("one point of RC accuracy is worth %.3f points of SH challenge mAP at "
                          "this operating point, so an unweighted coordinator would spend almost "
                          "everything on whichever class is measured on the wider scale."
                          % (sh_gain / rc_gain))
    else:
        out["omega"] = None
    return out


# ================================================================ D. durations
def durations() -> Dict[str, Any]:
    """Every duration the policy needs, from committed studies, each cited and each marked for
    replacement where StudyENG1 is expected to measure it."""
    d2_tok = d2_tokens_per_frame()
    return {
        "episodic_ttft_by_n": dict(
            provenance="MEASURED", replace_with_eng1=True,
            source="StudyD7b (N=1) and StudyD7 (N=3, N=9), open-loop TTFT p50 at 25 % and 75 % "
                   "of peak load",
            values_s={"%s_N%d_load%d" % (m, n, l): C.CLOUD_TTFT[(m, n, l)]
                      for (m, n, l) in sorted(C.CLOUD_TTFT)},
            note="the policy adds RTT and upload itself; see the link model"),
        "episodic_end_to_end_by_n": dict(
            provenance="DERIVED RULE", replace_with_eng1=True,
            rule="RTT + frame bytes / uplink + TTFT, unrounded (StudyE9b setting (ii))",
            values_s={"32BI_N1": C.episodic_cloud_latency_s("32BI", 1, 25),
                      "32BI_N3": C.episodic_cloud_latency_s("32BI", 3, 25),
                      "4BI_N1": C.episodic_cloud_latency_s("4BI", 1, 25)}),
        "recall_ttft_by_readiness": dict(
            provenance="MEASURED", replace_with_eng1=True,
            source="StudyRH5 Part A, isolated reload, D2 format, one request at a time, TTFT "
                   "medians",
            values_s={"%d|%s" % (k[0], k[1]): v for k, v in sorted(C.RECALL_TTFT_S.items())},
            interpolation_rule=("linear in tokens between 11k and 28k for the warm states; COLD "
                                "uses the measured cold prefill rate. STATED RULE, not a "
                                "measurement.")),
        "cold_rebuild_per_token": dict(
            provenance="MEASURED", replace_with_eng1=True,
            source="StudyRH5 cold re-prefill rates",
            tokens_per_s=dict(C.COLD_PREFILL_TOK_S),
            seconds_per_token={str(k): 1.0 / v for k, v in C.COLD_PREFILL_TOK_S.items()}),
        "host_reload_per_token": dict(
            provenance="MEASURED", replace_with_eng1=True,
            source="StudyRH5: 64 layers x 8 KV heads x 128 x {K,V} x bf16 per token, and vLLM's "
                   "own load-time metric",
            bytes_per_token=C.HOST_BYTES_PER_TOKEN,
            gb_per_s=dict(C.HOST_RELOAD_GB_S),
            seconds_per_token={str(k): C.HOST_BYTES_PER_TOKEN / (v * 1e9)
                               for k, v in C.HOST_RELOAD_GB_S.items()}),
        "catchup_per_frame": dict(
            provenance="DERIVED RULE", replace_with_eng1=True,
            rule=("appending s seconds of D2 history is an incremental prefill of its tokens: "
                  "t_catchup = (frames x tokens_per_frame) / prefill_tok_s. NO committed "
                  "video-domain measurement of catch-up exists; StudyE32 measured catch-up on "
                  "LoCoMo text conversations and its numbers are flagged in CLAUDE.md, so they "
                  "are NOT used here."),
            tokens_per_frame_d2=d2_tok,
            prefill_tok_s=dict(C.PREFILL_TOK_S),
            seconds_per_frame={m: d2_tok["median"] / r for m, r in C.PREFILL_TOK_S.items()}
            if d2_tok.get("median") else None,
            d2_stride_s=2.0),
        "answer_time_by_context": dict(
            provenance="MEASURED", replace_with_eng1=True,
            source="StudyE10d: a cold K1 RICH recall is 12,645 prompt tokens, LM prefill about "
                   "2.17 s (~5.8k tok/s), frontend 1.47 s for the PNG body / 0.75 s JPEG / "
                   "0.04 s text-only, vision encoder about 0.2 s",
            k1_rich_tokens=C.K1_RICH_TOKENS, lm_prefill_s=C.K1_RICH_LM_PREFILL_S,
            frontend_s=dict(C.K1_RICH_FRONTEND_S), vision_encoder_s=C.VISION_ENCODER_S),
        "prefix_chained_piece_overhead": dict(
            provenance="MEASURED", replace_with_eng1=False,
            source="StudySLICE1 Part A, 40 chains over RH4 D2 sessions",
            chain_over_monolithic_ratio={"1024": 1.093, "2048": 0.990},
            median_per_link_overhead_s={"1024": 0.015, "2048": -0.004},
            longest_engine_unit_s={"11k_n1024": 0.23, "11k_n2048": 0.39,
                                   "27k_n1024": 0.31, "27k_n2048": 0.55},
            note="Part A's gate passed; the 2,048-token chain is the one StudySLICE1 P3 uses"),
        "episodic_capacity_req_s": dict(
            provenance="MEASURED", replace_with_eng1=True,
            source="StudyE10b, one 32B replica, N = 3, p99 budget met",
            values={"%s|k%d|r%.1f" % k: v for k, v in C.EPISODIC_CAPACITY_REQ_S.items()}),
        "device_answer_latency": dict(
            provenance="MEASURED", replace_with_eng1=False,
            source="StudyD8 arm A, Orin sustained 1 Hz N=1, total latency p50",
            seconds=C.DEV_LAT_S,
            note=("StudyB-baselines amendment 2 charges this as a RULE whenever a policy reads "
                  "the device's answer confidence")),
    }


def d2_tokens_per_frame() -> Dict[str, Any]:
    """Tokens per D2 frame, from StudyRH4's own manifest: prompt tokens / frames per question."""
    per = []
    for r in _rows(RH4):
        if r.get("cell") != "D2" or r.get("error"):
            continue
        n = r.get("n_images") or r.get("n_frames")
        t = r.get("prompt_tokens") or r.get("expected_prompt_tokens")
        if n and t:
            per.append(float(t) / float(n))
    if not per:
        return dict(provenance="NOT AVAILABLE", median=None)
    a = np.asarray(per)
    return dict(provenance="DERIVED RULE from StudyRH4 committed per-question prompt tokens",
                median=float(np.median(a)), p25=float(np.percentile(a, 25)),
                p75=float(np.percentile(a, 75)), n_questions=int(a.size),
                note="prompt tokens include the question text, so this is an upper bound per frame")


# ================================================================ E. link model
def link_model() -> Dict[str, Any]:
    z = np.load(E6B)
    keys = [k for k in z.files if k.startswith("outdoor_driving|")]
    traces = [np.asarray(z[k], dtype=np.int8) for k in keys]
    up = np.concatenate(traces)
    outages: List[int] = []
    for t in traces:
        run = 0
        for v in t:
            if v == 0:
                run += 1
            elif run:
                outages.append(run)
                run = 0
        if run:
            outages.append(run)
    o = np.asarray(outages, dtype=float) if outages else np.zeros(0)
    return dict(
        connectivity=dict(
            provenance="MEASURED", source="StudyE31b outdoor-driving traces as StudyE6b "
            "committed them (`results/orchestration/study_e6b/e6b_traces.npz`), 1 bit per second",
            n_traces=len(traces), seconds=int(up.size),
            fraction_connected=float(up.mean()),
            outage_count=int(o.size),
            outage_length_s=(dict(p50=float(np.median(o)), p90=float(np.percentile(o, 90)),
                                  p99=float(np.percentile(o, 99)), max=float(o.max()),
                                  mean=float(o.mean())) if o.size else None),
            outages_per_minute=float(o.size / (up.size / 60.0)) if up.size else None),
        bandwidth=dict(
            provenance="ASSUMPTION (single committed value, no measured distribution)",
            uplink_bytes_per_s=C.UPLINK_BPS, uplink_mbit_s=C.UPLINK_BPS * 8 / 1e6,
            source="StudyE9 setting (ii) uses a single 13.6 Mbit/s uplink",
            warning=("the committed traces carry CONNECTIVITY (1 bit per second), NOT a "
                     "bandwidth time series, so no percentiles can be computed from them. The "
                     "policy must treat bandwidth as a constant with an outage process on top, "
                     "and spec 4's t_up = payload / b_i uses this constant."),
            percentiles="NOT AVAILABLE from committed data", replace_with_eng1=False),
        rtt=dict(provenance="MEASURED", seconds=C.RTT_S,
                 source="StudyE9 setting (ii); it is a ROUND trip, so an answer's downlink is "
                        "already inside it"),
        jitter=dict(provenance="ASSUMPTION",
                    model=("none: the delivery model is deterministic given the payload and the "
                           "server TTFT, and every committed study uses it that way. A jitter "
                           "term would have to be invented, so it is declared absent rather "
                           "than guessed."),
                    what_would_measure_it=("per-request end-to-end timings on a real link, which "
                                           "StudyENG1's live runs will produce"),
                    replace_with_eng1=True))


# ================================================================ F. demand
def demand() -> Dict[str, Any]:
    """Recall-question arrival statistics per DEV video, and the spec 6.4 conditional-rate test.

    THE 6.4 TEST, as the user specified it: on DEV, test whether S-EMBER recall questions arrive
    more often within W seconds of a device escalation episode than elsewhere, for W in
    {10, 30, 60} s, and report the rate ratio with a CI; if the CI includes 1 at every W, the
    conditional recall rate is NOT used.

    IT CANNOT BE COMPUTED FROM COMMITTED DATA, and the reason is structural rather than a gap in
    one file: escalation episodes exist only on the Nexar dashcam traces (StudyD14b, the SH task),
    and recall questions exist only on S-EMBER videos (the RC task). No committed trace carries
    both on the same stream, and the simulator's pairing of the two is a HARNESS CONSTRUCTION
    (it assigns S-EMBER question arrivals to a timeline), so testing on it would measure our own
    generator and not the world. Nothing is synthesized here.

    THE CONSERVATIVE DEFAULT, applied and flagged: the conditional recall rate is NOT USED. That
    is the same action the user's rule prescribes when the CI includes 1 at every W, and spec 6.4
    already gates the mechanism on DEV support ("only if DEV data supports it").
    """
    sp = SS.split()
    dev_videos = set(sp.get("dev_videos", []))
    dev_q = set(sp.get("dev_questions", []))
    per_video: Dict[str, List[float]] = defaultdict(list)
    cat_of: Dict[str, str] = {}
    seen = set()
    for r in _rows(R1_MANIFEST):
        if r.get("construction") != "RECENT":
            continue
        qid = r["question_id"]
        if qid in seen:
            continue
        seen.add(qid)
        if dev_videos and r["video_id"] not in dev_videos:
            continue
        if not dev_videos and qid not in dev_q:
            continue
        per_video[r["video_id"]].append(float(r["question_time"]))
        cat_of[qid] = r["question_category"]
    rates = []
    gaps: List[float] = []
    for v, ts in per_video.items():
        ts = sorted(ts)
        span = max(ts) if len(ts) else 0.0
        if span > 0:
            rates.append(len(ts) / (span / 60.0))
        gaps += [b - a for a, b in zip(ts, ts[1:])]
    ra = np.asarray(rates) if rates else np.zeros(0)
    ga = np.asarray(gaps) if gaps else np.zeros(0)
    counts = np.asarray([len(v) for v in per_video.values()], dtype=float)
    return dict(
        provenance="MEASURED (S-EMBER DEV videos only)",
        n_dev_videos=len(per_video), n_dev_questions=int(counts.sum()),
        questions_per_video=dict(mean=float(counts.mean()), p50=float(np.median(counts)),
                                 min=float(counts.min()), max=float(counts.max()))
        if counts.size else None,
        arrival_rate_per_video_per_minute=dict(
            mean=float(ra.mean()), p50=float(np.median(ra)), p25=float(np.percentile(ra, 25)),
            p75=float(np.percentile(ra, 75))) if ra.size else None,
        inter_arrival_s=dict(mean=float(ga.mean()), p50=float(np.median(ga)),
                             p25=float(np.percentile(ga, 25)),
                             p75=float(np.percentile(ga, 75))) if ga.size else None,
        lambda_rc_default_per_s=float(ra.mean() / 60.0) if ra.size else None,
        conditional_rate_test_6_4=dict(
            status="NOT COMPUTABLE FROM COMMITTED DATA",
            windows_s=[10, 30, 60], rate_ratio=None, ci=None,
            reason=("escalation episodes exist only on the Nexar dashcam traces (SH) and recall "
                    "questions only on S-EMBER videos (RC); no committed trace carries both on "
                    "the same stream, and the simulator's pairing of the two is a harness "
                    "construction, so a test on it would measure our own generator"),
            decision=("the conditional recall rate is NOT USED, which is the action the user's "
                      "rule prescribes when the CI includes 1 at every W, and which spec 6.4 "
                      "already requires absent DEV support"),
            what_would_make_it_computable=("one stream that carries both: a continuous SH task "
                                           "and timestamped recall questions on the same video, "
                                           "which no current dataset in this project provides")))


# ================================================================ assembly
def main() -> int:
    from _provenance import stamp
    OUT.mkdir(parents=True, exist_ok=True)
    s = SP.split()
    u = u_sh(s["dev"])
    rc = rc_tables()
    res = dict(
        label=("StudyPROF1-dev: the DEV-only profile tables the scheduling policy reads. CPU "
               "only; committed measurements; no inference. Every entry carries a provenance "
               "kind: MEASURED, DERIVED RULE, ASSUMPTION or PROPOSAL."),
        evidence_rule=("spec D6: every table is fitted on DEV only. Nexar DEV = the 90-clip DEV "
                       "side of the pre-registered StudyD14b split; S-EMBER DEV = the 70-video "
                       "DEV side of StudyB-baselines amendment 2. No EVAL clip or question is "
                       "read by this file."),
        nexar_split=dict(rule=s["rule"], n_dev=s["n_dev"], n_eval=s["n_eval"]),
        u_SH=u, RC=rc, class_weights_omega=omega(u, rc), durations=durations(),
        link_model=link_model(), demand=demand())
    res["_provenance"] = stamp(script="prof1_profiles.py", model=None, device="cpu",
                               n=s["n_dev"], args=None)
    (OUT / "profiles_dev.json").write_text(json.dumps(res, indent=1, default=float))

    print("u_SH: device %.4f, cloud m1 at delay 0.50 s %.4f, zero delay %.4f"
          % (u["u_device"]["u_identity"], u["cloud"]["m1@0.5|d0.50"]["u_identity"],
             u["cloud"]["m1@0.5|d0.00"]["u_identity"]))
    for k, t in res["RC"]["tables"].items():
        print("RC %-15s DEV n %3d  accuracy %s" % (k, t["n_dev_questions"],
              ("%.4f" % t["accuracy"]) if t["accuracy"] is not None else "n/a"))
    om = res["class_weights_omega"]
    print("omega PROPOSAL: SH gain %.4f, RC gain %s -> %s"
          % (om["gains"]["SH"], ("%.4f" % om["gains"]["RC"]) if om["gains"]["RC"] else "n/a",
             om["omega"]))
    lm = res["link_model"]["connectivity"]
    print("link: %d traces, %d s, connected %.4f, %d outages, p50 %s s, per minute %.3f"
          % (lm["n_traces"], lm["seconds"], lm["fraction_connected"], lm["outage_count"],
             lm["outage_length_s"]["p50"] if lm["outage_length_s"] else "n/a",
             lm["outages_per_minute"]))
    dm = res["demand"]
    print("demand: %d DEV videos, %d questions, %.3f questions per video-minute; 6.4 test %s"
          % (dm["n_dev_videos"], dm["n_dev_questions"],
             dm["arrival_rate_per_video_per_minute"]["mean"],
             dm["conditional_rate_test_6_4"]["status"]))
    print("wrote", OUT / "profiles_dev.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
