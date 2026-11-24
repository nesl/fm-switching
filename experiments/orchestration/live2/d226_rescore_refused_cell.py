#!/usr/bin/env python3
"""D226 (3) re-score of ONE refused cell with the committed three-way scorer, on flash.

The cell `covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` carries a no-rows stub
`score` block: the PRE-D226 (3) guard refused it because one delivered cloud answer (`r10175`)
has no row in the request log. D226 (3) replaced that refusal with a three-way classification
read from the OUTCOME, and the committed scorer keeps such an answer when it is a real delivery.

WHAT IS AND IS NOT COMMITTED ON THIS BOX. The cell's own recorded artefacts are committed and are
read byte-identical from origin. `device_answers.jsonl.gz` for this trace is committed (and its
sha256 is checked here against the committed D192 provenance). `trace.jsonl` and `trace_meta.json`
for this trace are NOT committed and the frozen-grid working tree is not on flash: the committed
D192 provenance records that `/home/pragya/data/live2/frozen_grid/work/traces/` is the H100's disk.
`score.load` opens both unconditionally, so a `trace_meta.json` carrying this trace's committed
knobs and an EMPTY `trace.jsonl` stand in for them. That is sound for exactly the three scorers
called here -- `attainment`, `robot_value`, `assistive_value` -- because none of them reads
`Loaded.records` or `Loaded.meta`; `Loaded.records` is read only by `_ap_streams`,
`device_only_value` and `history_preload`, which are NOT called and whose outputs are NOT written.
The dashcam streaming AP therefore stays absent from this cell and is reported as still owed.

Nothing here reimplements scoring or grading. Every number comes from the committed functions.

HOW TO RE-RUN IT. One argument, a staging directory, which must hold:

  BASE_SHA                     one line, the origin/main sha every committed input is read from
  repo/experiments/            `git archive <BASE_SHA> experiments | tar -x -C repo`
  repo/results/...             the four committed files data_sources reads:
                               results/sember/study_orin_rec/orin_rec_warm.jsonl
                               results/device/study_devlat/orin_device_latency_tables.json
                               results/orchestration/live2/lh_req/lh_req_definition.json
                               results/dashcam/study_orin2/orin2_calibration.json
  run/outcomes.jsonl           decompressed from the cell's committed outcomes.jsonl.gz
  run/request.jsonl            decompressed from the cell's committed request.jsonl.gz
  run/run_meta.json            the cell's committed run_meta.json
  trace/device_answers.jsonl(.gz)  the committed device_answers for this cell's trace

`conda run -n fmtk python -I <this file> <staging dir>`. It writes new_score_block.json there and
changes nothing else. No GPU, no model, no network.
"""
from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

W = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
     else Path(__file__).resolve().parent)
REAL_REPO = Path("/home/pragya/Desktop/FM-switching")
sys.path.insert(0, str(REAL_REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

sys.path.insert(0, str(W / "repo/experiments/orchestration/live2/scorer"))
import score as SC  # noqa: E402  the committed three-way scorer, imported unmodified

CELL = ("results/orchestration/live2/frozen_test/runs/"
        "covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30")
TRACE = ("results/orchestration/live2/frozen_test/traces/"
         "seed4_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30")
BASE_SHA = (W / "BASE_SHA").read_text().strip()
SCORER_COMMIT = "35e3c57e85c802a1c3c23887adfba42c778da20d"
DEVICE_ANSWERS_SHA256 = "66395e5ccf1b7059c6bf628608c62f02624effe1059ca0f9c6c11b05ffeb2585"


def die(msg):
    print("STOP: " + msg)
    raise SystemExit(1)


def show(path):
    return subprocess.check_output(["git", "-C", str(REAL_REPO), "cat-file", "blob",
                                    "%s:%s" % (BASE_SHA, path)])


# ---- the scorer code this run used is the committed one, byte for byte
blob_origin = subprocess.check_output(
    ["git", "-C", str(REAL_REPO), "rev-parse",
     "%s:experiments/orchestration/live2/scorer/score.py" % BASE_SHA], text=True).strip()
blob_local = subprocess.check_output(
    ["git", "-C", str(REAL_REPO), "hash-object",
     str(W / "repo/experiments/orchestration/live2/scorer/score.py")], text=True).strip()
blob_at_scorer_commit = subprocess.check_output(
    ["git", "-C", str(REAL_REPO), "rev-parse",
     "%s:experiments/orchestration/live2/scorer/score.py" % SCORER_COMMIT], text=True).strip()
if not (blob_local == blob_origin == blob_at_scorer_commit):
    die("the score.py this run imported is not the committed one: local %s origin %s at-%s %s"
        % (blob_local, blob_origin, SCORER_COMMIT[:8], blob_at_scorer_commit))
print("scorer score.py blob   %s (identical at %s and at origin base %s)"
      % (blob_local, SCORER_COMMIT[:8], BASE_SHA[:8]))
print("scorer DELIVERY        %s" % SC.DELIVERY)
print("scorer L_rob / L_dash / L_ss  %s / %s / %s" % (SC.ROB_L_S, SC.DASH_L_S, SC.SS_L_S))

# ---- the device answers (robot gold) are the committed artefact
import hashlib  # noqa: E402
h = hashlib.sha256((W / "trace/device_answers.jsonl.gz").read_bytes()).hexdigest()
if h != DEVICE_ANSWERS_SHA256:
    die("device_answers.jsonl.gz sha256 %s != committed D192 provenance %s"
        % (h, DEVICE_ANSWERS_SHA256))
print("device_answers sha256  %s (matches committed D192 provenance, seed 4)" % h[:16])

# ---- capture-time fairness evidence, in place of the absent trace digest
rm = json.loads((W / "run/run_meta.json").read_text())
if not rm.get("run_valid"):
    die("run_meta.run_valid is not true")
if not rm.get("digests_equal"):
    die("run_meta.digests_equal is not true")
if rm.get("fairness_digest") != rm.get("trace_fairness_digest"):
    die("run_meta fairness digests differ")
print("run_valid              %s" % rm["run_valid"])
print("fairness_digest        %s == trace_fairness_digest (capture time, D96 (2))"
      % rm["fairness_digest"][:16])

# ---- the stand-in trace_meta, carrying this trace's committed knobs
knobs = json.loads(show(TRACE.rsplit("/", 1)[0] + "/d192_device_scores_provenance.json")
                   .decode())["knobs"]
meta = dict(knobs)
meta.update(seed=rm["seed"], n_devices=rm["n_devices"], ratio=rm["ratio"], run_s=rm["run_s"],
            mode=rm["mode"])
meta["_stand_in"] = (
    "NOT the capture-time trace_meta.json, which is not committed and whose frozen-grid working "
    "copy is the H100's disk (committed d192_device_scores_provenance.json). The knobs are the "
    "committed D192 provenance for this trace; seed / n_devices / ratio / run_s / mode are this "
    "run's own run_meta.json. No fairness digest is placed here: fabricating one would make "
    "score.load's digest check compare a value written by this script, so the check is left "
    "SKIPPED and the capture-time record (run_meta.digests_equal and fairness_digest == "
    "trace_fairness_digest) is asserted above instead.")
(W / "trace/trace_meta.json").write_text(json.dumps(meta, indent=1))
(W / "trace/trace.jsonl").write_text("")   # score.load opens it; records are never read below

# ---- load, which is where D144, D226 (3) and D146 are applied
lo = SC.load(W / "trace", W / "run")
print("\n=== d226_rowless ===")
print(json.dumps(lo.rowless_counts))
if lo.rowless_counts != dict(delivered=1, refused=0, undetermined=0):
    die("d226_rowless is %r, expected {delivered: 1, refused: 0, undetermined: 0}"
        % (lo.rowless_counts,))
kept = [o for o in lo.outcomes.values() if o.get("d226_rowless_delivered")]
if len(kept) != 1:
    die("expected exactly one kept rowless delivery, got %d" % len(kept))
k = kept[0]
print("kept rowless delivery  opp=%s dev=%s rid=%s letter=%r t_opp=%.6f t_cloud_done=%.6f "
      "dt=%.6f within_L=%s"
      % (k["opportunity_id"], k["device_id"], (k["cloud_payload"] or {}).get("request_id"),
         (k["cloud_payload"] or {}).get("cloud_letter"), k["t_opportunity"], k["t_cloud_done"],
         float(k["t_cloud_done"]) - float(k["t_opportunity"]), k["within_L"]))
if len(lo.records) != 0:
    die("records is not empty, so the stand-in trace is being read as data")

# ---- the three committed scorers
att = SC.attainment(lo)
rv = SC.robot_value(lo, SC.ROB_L_S)
rrows = rv.pop("rows")
av = SC.assistive_value(lo)
arows = av.pop("rows")

print("\n=== single-shot within %.1f s (the Orin's first figure) ===" % SC.SS_L_S)
print("attainment      ss_pool_on_time/ss_pool_n = %s/%s = %s"
      % (att.ss_pool_on_time, att.ss_pool_n, att.ss_pool_fraction))
print("assistive_value on_time/n                 = %s/%s = %s"
      % (av["on_time"], av["n"], av["on_time_fraction"]))
print("ss_classified_by: %s" % att.ss_classified_by)

print("\n=== robot, every count with its denominator ===")
print("robot_pool_n (denominator)        %s" % att.robot_pool_n)
print("robot_pool_on_time                %s / %s = %s"
      % (att.robot_pool_on_time, att.robot_pool_n, att.robot_pool_fraction))
print("robot correct-by-deadline         %s  over n_by_deadline %s"
      % (rv["standing_accuracy_by_deadline"], rv["standing_accuracy_by_deadline_n"]))
print("robot correct any-time (beside)   %s  over n %s"
      % (rv["standing_accuracy"], rv["standing_accuracy_n"]))
print("n_rows robot / assistive          %s / %s" % (len(rrows), len(arows)))
if len(rrows) != att.robot_pool_n:
    die("robot_rows %d != robot_pool_n %d" % (len(rrows), att.robot_pool_n))
if len(arows) != att.ss_pool_n:
    die("assistive_rows %d != ss_pool_n %d" % (len(arows), att.ss_pool_n))

# ---- hazard: question_id is NOT unique. Key on (device_id, opportunity_id) and prove it.
print("\n=== join-key check (question_id is not unique) ===")
for name, rows in (("robot_rows", rrows), ("assistive_rows", arows)):
    n = len(rows)
    qids = {r.get("question_id") for r in rows}
    keys = {(r["device_id"], r["opportunity_id"]) for r in rows}
    opps = {r["opportunity_id"] for r in rows}
    print("%-15s n=%d  distinct question_id=%d  distinct (device_id,opportunity_id)=%d  "
          "distinct opportunity_id=%d" % (name, n, len(qids), len(keys), len(opps)))
    if len(keys) != n:
        die("%s: (device_id, opportunity_id) is not unique (%d keys for %d rows)"
            % (name, len(keys), n))
# the join that matters: robot_rows against the outcomes they came from, on the compound key
out_by_key = {(o["device_id"], o["opportunity_id"]): o for o in lo.outcomes.values()}
joined = [(r, out_by_key[(r["device_id"], r["opportunity_id"])]) for r in rrows
          if (r["device_id"], r["opportunity_id"]) in out_by_key]
if len(joined) != len(rrows):
    die("robot_rows -> outcomes join changed the row count: %d -> %d" % (len(rrows), len(joined)))
print("robot_rows -> outcomes join on (device_id, opportunity_id): %d -> %d rows, unchanged"
      % (len(rrows), len(joined)))

# ---- hazard: a plausible spread does not advertise breakage. Are the letters real, and CAN the
# ---- gold comparison fail?
print("\n=== positive control: the gold comparison can fail ===")
cl = [r for r in rrows if r["cloud_letter"] is not None]
nX = sum(1 for r in cl if r["cloud_letter"] == "X")
nnull = sum(1 for r in rrows if r["cloud_letter"] is None)
differ = [r for r in cl if r["cloud_letter"] != r["gold"]]
agree = [r for r in cl if r["cloud_letter"] == r["gold"]]
print("robot rows with a cloud letter    %d / %d (null: %d)" % (len(cl), len(rrows), nnull))
print("placeholder 'X' letters           %d" % nX)
print("distinct cloud letters            %s" % sorted({r["cloud_letter"] for r in cl}))
print("distinct gold letters             %s" % sorted({r["gold"] for r in rrows}))
print("cloud_letter != gold              %d of %d  <-- the comparison CAN fail"
      % (len(differ), len(cl)))
print("cloud_letter == gold              %d of %d  <-- and CAN succeed" % (len(agree), len(cl)))
for r in differ[:3]:
    print("   FAIL example  opp=%s dev=%s qid=%s cloud=%r gold=%r cloud_correct=%s"
          % (r["opportunity_id"], r["device_id"], r["question_id"], r["cloud_letter"],
             r["gold"], r["cloud_correct"]))
for r in agree[:2]:
    print("   PASS example  opp=%s dev=%s qid=%s cloud=%r gold=%r cloud_correct=%s"
          % (r["opportunity_id"], r["device_id"], r["question_id"], r["cloud_letter"],
             r["gold"], r["cloud_correct"]))
if not differ:
    die("no robot row has cloud_letter != gold: the gold comparison cannot be shown to fail")
if not agree:
    die("no robot row has cloud_letter == gold: the gold comparison cannot be shown to succeed")
if nX or nnull:
    print("NOTE: %d 'X' and %d null cloud letters are present and are NOT silently correct"
          % (nX, nnull))

# ---- robot denominator moves between seeds: report the per-device breakdown
print("\n=== robot per-device (the denominator moves between seeds) ===")
for d in sorted(att.robot_per_device):
    v = att.robot_per_device[d]
    print("   %-9s on_time %3d / %3d = %s" % (d, v["on_time"], v["n_questions"], v["fraction"]))

# ---- assemble the new score block
score_block = dict(
    ok=True,
    score=dict(
        arm="covex-v6-fair-final", seed=rm["seed"], n_devices=rm["n_devices"], ratio=rm["ratio"],
        run_s=rm["run_s"], mode=rm["mode"], server_kind=rm["server_kind"],
        memory=rm.get("memory_setting"),
        trace_dir=rm["trace_dir"], run_dir=rm["out_dir"],
        d226_rowless=lo.rowless_counts,
        delivery_rule=SC.DELIVERY,
        on_time_rule=("an answer is delivered at COMPLETION, prefill plus decode (D146, the "
                      "default from 2026-11-20); a dashcam Yes/No stays at first token"),
        sweep=[dict(L_dash=SC.DASH_L_S, p_dash=SC.DASH_P, L_rob=SC.ROB_L_S, p_rob=SC.ROB_P,
                    **{k: v for k, v in att.__dict__.items() if k != "dashcam_per_device"},
                    dashcam_per_device=att.dashcam_per_device)],
        robot_value=rv, robot_rows=rrows,
        robot_headline=dict(
            metric="correct_answers_delivered_by_deadline",
            correct_answers_delivered_by_deadline=rv.get("standing_accuracy_by_deadline"),
            n_by_deadline=rv.get("standing_accuracy_by_deadline_n"),
            beside_it_any_time=dict(
                metric="correct_answers_delivered_any_time",
                correct_answers_delivered_any_time=rv.get("standing_accuracy"),
                n=rv.get("standing_accuracy_n")),
            device_only_accuracy=rv.get("device_only_accuracy"),
            cloud_accuracy_on_served=rv.get("cloud_accuracy_on_served"),
            on_time_beside_it=dict(robot_pool_on_time=att.robot_pool_on_time,
                                   robot_pool_n=att.robot_pool_n,
                                   robot_pool_fraction=att.robot_pool_fraction),
            source="D152 as amended by D155 (3)"),
        assistive_value=av, assistive_rows=arows,
        target_defaults=dict(L_dash=SC.DASH_L_S, p_dash=SC.DASH_P,
                             min_dash_instants=SC.DASH_MIN_INSTANTS, L_rob=SC.ROB_L_S,
                             p_rob=SC.ROB_P, min_rob_questions_pooled=SC.ROB_MIN_QUESTIONS,
                             source="D71 as amended by D82"),
        caveats=[SC.DS.AP_CAVEAT, SC.DS.DEVICE_ANSWER_CAVEAT, SC.DS.SEMBER_JPEG_CAVEAT,
                 SC.DS.CACHE_PATH_CAVEAT],
        scorer=dict(
            source="experiments/orchestration/live2/scorer/score.py",
            score_py_blob=blob_local,
            score_py_commit=SCORER_COMMIT,
            d226="D226 (3), the three-way rowless delivery rule; D166 for the frozen-test cell set",
            functions_called=["load", "attainment", "robot_value", "assistive_value"],
            invoked="imported unmodified; no scoring or grading reimplemented here"),
        partial=dict(
            complete=["sweep (attainment)", "robot_value", "robot_rows", "robot_headline",
                      "assistive_value", "assistive_rows"],
            absent=["dashcam_value", "device_only", "history_preload", "diagnostics",
                    "frame_bytes_source", "calibration", "is_measurement"],
            why=("the absent fields are the only ones that read Loaded.records (trace.jsonl) or "
                 "the calibration map. trace.jsonl and trace_meta.json for this trace are not "
                 "committed and the frozen-grid working copy is the H100's disk, per the "
                 "committed d192_device_scores_provenance.json. They are left ABSENT rather "
                 "than filled from a stand-in trace. The dashcam streaming AP for this cell is "
                 "still owed and must come from a box that holds the trace."),
            trace_meta_stand_in=meta["_stand_in"]),
    ))
score_block["score"]["_provenance"] = stamp(
    script="rescore_cell.py", model="n/a-offline-scorer", device="a6000",
    n=len(rrows) + len(arows), seed=rm["seed"],
    args=dict(cell=CELL, trace=TRACE, origin_base_sha=BASE_SHA,
              scorer_commit=SCORER_COMMIT, score_py_blob=blob_local,
              decisions="D226 (3), D166"))
(W / "new_score_block.json").write_text(json.dumps(score_block, indent=1, sort_keys=True))
print("\nwrote %s (%d bytes)" % (W / "new_score_block.json",
                                 (W / "new_score_block.json").stat().st_size))
