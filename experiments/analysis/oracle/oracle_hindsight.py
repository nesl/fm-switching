#!/usr/bin/env python3
"""StudyORACLE stage 3: recall + single-shot HINDSIGHT valuation beside FAIR (CPU, read-only, no
images). D240: 1x and kv0.5r separate (recall/ss correctness does not vary with memory; reported for
both). HINDSIGHT per-unit gain of serving = [cloud correct] - [device correct] in {-1,0,1}; device
floor = sum [device correct]. FAIR per-unit gain = acc_cloud - acc_device (stage 1), a flat per-type
expected gain. HINDSIGHT and FAIR therefore differ per unit, as required.

Recall per-question correctness (device_correct, cloud_correct) is arm-independent (same device and
cloud model on the same question); harvested from the committed robot_rows, taking the union over
arms for coverage (always-cloud-fcfs first, it delivers nearly all). Single-shot correctness from
the SS2 box (episodic_lib.ss2_correctness), mapped to the trace's single-shot questions per seed.
"""
from __future__ import annotations
import json, os, sys, glob, collections
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/orchestration/live2/fleet"))
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
sys.path.insert(0, str(REPO / "experiments/lib"))
import trace as TR  # noqa: E402
import episodic_lib as E  # noqa: E402
from _provenance import stamp  # noqa: E402
SEEDS = [4, 5, 6, 7]


def recall_correctness(seed, tag):
    """opportunity_id -> (device_correct, cloud_correct) over robot recall, union across arms."""
    out = {}
    pat = str(RUNS / f"*_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30")
    cells = sorted(glob.glob(pat) + glob.glob(pat + "_rerun"))
    # always-cloud-fcfs first for best cloud coverage
    cells.sort(key=lambda c: (0 if "always-cloud-fcfs" in c else 1))
    for c in cells:
        p = os.path.join(c, "cell.json")
        if not os.path.exists(p):
            continue
        try:
            rows = (((json.load(open(p)).get("score") or {}).get("score") or {}).get("robot_rows")) or []
        except Exception:
            continue
        for r in rows:
            if not str(r.get("device_id", "")).startswith("robo"):
                continue
            oid = r.get("opportunity_id")
            dc = bool(r.get("device_correct"))
            cl = r.get("cloud_letter")
            cc = (None if cl is None else bool(r.get("cloud_correct")))
            if oid not in out:
                out[oid] = [dc, cc]
            elif out[oid][1] is None and cc is not None:
                out[oid][1] = cc            # fill cloud from another arm that delivered it
    return out


def main():
    ss = E.ss2_correctness()
    result = {"1x": {}, "kv0.5r": {}}
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        for s in SEEDS:
            b = TR.generate_trace(seed=s, n_devices=16, ratio="40:40:20", run_s=1200.0, mode="A",
                                  robot_question_set="lh_req", ss_question_set="ss2",
                                  dashcam_format="epg", robot_upload="per-frame",
                                  robot_reask_mean_s=30.0)
            recs = b["records"]
            rc = recall_correctness(s, tag)
            # recall units: one per robot recall opportunity
            rob = [r for r in recs if r["kind"] == "recall_question"
                   and str(r["device_id"]).startswith("robo")]
            r_floor = r_improv = r_cloudwrong = 0
            r_n = 0; r_nocloud = 0
            for r in rob:
                oid = r["opportunity_id"]
                dc_cc = rc.get(oid)
                if dc_cc is None:
                    continue
                r_n += 1
                dc, cc = dc_cc
                if dc:
                    r_floor += 1
                if cc is None:
                    r_nocloud += 1
                    continue
                g = int(cc) - int(dc)
                if g > 0:
                    r_improv += 1          # cloud right, device wrong (served helps)
                elif g < 0:
                    r_cloudwrong += 1       # cloud wrong, device right (serving would HURT)
            # single-shot units: one per asst recall opportunity, correctness from the box
            sss = [r for r in recs if r["kind"] == "recall_question"
                   and str(r["device_id"]).startswith("asst")]
            s_floor = s_improv = s_cloudwrong = 0; s_n = 0; s_nobox = 0
            for r in sss:
                qid = r.get("question_id")
                v = ss.get(qid)
                if not v or "device" not in v or "cloud" not in v:
                    s_nobox += 1
                    continue
                s_n += 1
                dc, cc = int(v["device"]), int(v["cloud"])
                if dc:
                    s_floor += 1
                g = cc - dc
                if g > 0:
                    s_improv += 1
                elif g < 0:
                    s_cloudwrong += 1
            result[mem][f"s{s}"] = {
                "recall": {"n": r_n, "device_floor": r_floor, "n_cloud_right_device_wrong": r_improv,
                           "n_cloud_wrong_device_right": r_cloudwrong, "n_no_cloud_answer": r_nocloud,
                           "hindsight_net_gain_if_served_all": r_improv - r_cloudwrong,
                           "hindsight_oracle_gain_serve_only_helpful": r_improv},
                "single_shot": {"n": s_n, "device_floor": s_floor,
                                "n_cloud_right_device_wrong": s_improv,
                                "n_cloud_wrong_device_right": s_cloudwrong, "n_no_box": s_nobox,
                                "hindsight_oracle_gain_serve_only_helpful": s_improv},
            }
    out = {"_what": "StudyORACLE stage 3: recall + single-shot HINDSIGHT valuation (actual per-unit "
                    "cloud/device correctness) beside FAIR. D240 1x/kv0.5r separate. The HINDSIGHT "
                    "oracle gain (serve only where cloud right and device wrong) is reported; FAIR "
                    "gain is the flat per-type expected gain from stage 1.",
           "results": result}
    out["_provenance"] = stamp(script="oracle_hindsight.py", model="qwen3vl32b", device="jetson_orin")
    outdir = REPO / "results/orchestration/live2/oracle"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "oracle_hindsight.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "oracle_hindsight.json")
    for mem in ("1x", "kv0.5r"):
        for s, r in result[mem].items():
            rr, sr = r["recall"], r["single_shot"]
            print(f"  {mem} {s}: recall n={rr['n']} floor={rr['device_floor']} "
                  f"cloud+dev-={rr['n_cloud_right_device_wrong']} cloud-dev+={rr['n_cloud_wrong_device_right']} "
                  f"nocloud={rr['n_no_cloud_answer']} | ss n={sr['n']} floor={sr['device_floor']} "
                  f"cloud+dev-={sr['n_cloud_right_device_wrong']}")
    return out


if __name__ == "__main__":
    main()
