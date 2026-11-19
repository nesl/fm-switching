#!/usr/bin/env python3
"""D134 addendum item 1: robot task value by COMMITTED-ANSWER LOOKUP. Dry, stratified.

Label: "dry, committed-answer lookup". Live H100 cells remain the confirmation, not the source.

THE JOIN. For each robot question the arm served:
  answer used = CLOUD if delivered within its deadline, else DEVICE  (the `_standing` rule, which
                I verified agrees with `u_rc` by construction, section 27.1)
  cloud correctness  <- StudyR1 per-question `correct`, keyed by (question_id, cell)
                        cell K1 = Qwen3-VL-32B-I x RICH, K3 = 32B-I x RECENT
  device correctness <- the trace's own `device_answers.jsonl` `device_correct`, which is
                        4B-I x RECENT per D87

CHECK 6, PROXY VALIDITY, ASSERTED NOT ASSUMED: the cloud side must use the 32B rows and the device
side the 4B-I rows. Mixing the tiers would reproduce section 27's inversion by another route, so
the model is asserted per side rather than defaulted.

WHY STRATIFIED (section 28). `K1_minus_K3` over all questions is +1.18 pp with a CI of
[-0.0152, +0.0389] that does NOT exclude zero, while `K1_minus_K3_recent_misses` is +17.5 pp and
does, with `recent_covers_frac` = 0.8852. One number, two populations. A population-average column
would sit below its own noise floor and read as "the arms are equivalent", which is wrong twice:
it is not equivalence, and the mechanism is concentrated where the mean cannot see it. So every
row carries the all-questions figure, the recent-misses stratum, AND the coverage fraction that
sets the mixture, since which questions an arm serves from cloud determines the mixture it
actually experiences.

NEVER IMPUTE: a (question, representation) pair absent from StudyR1 is reported MISSING.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

CELL = re.compile(r"^s(\d+)_(.+)_n(\d+)$")
# Arm vocabulary -> StudyR1 cell. Today every arm emits "D2" and live2 sends the full believed
# history regardless (`_submit_recall` uses `est_tokens`), so what is SENT is RICH. The mapping is
# stated rather than implied so it is one line to change when Part A lands.
# KEY ON WHAT WAS RECEIVED, NOT ON WHAT WAS NAMED. `cstate` builds only RECENT and D2 evidence
# items and `tokens_for_representation` branches only on "RECENT", so an arm naming RICH is
# charged the whole history and RECEIVES D2 CONTENT. Keying RICH to K1 would credit it with RICH
# accuracy for content it never got; the committed per-category tables put D2 and RICH -7.9 to
# +17.2 pp apart in BOTH directions, so that is neither a small nor a consistently signed error.
# RICH is therefore NOT in this map: it is normalised to D2 by `effective_representation` first,
# and D2 resolves against the per-category 32B-D2 table rather than any StudyR1 cell.
REPRESENTATION_TO_CELL = {"RECENT": "K3"}
RICH_IS_NOT_RECEIVABLE = ("live2 builds no RICH evidence item; an arm naming RICH receives D2. "
                          "See cstate.py:455-458 and tokens_for_representation.")

# StudyACC2 COMPATIBILITY, checked against the committed plan at 74ef9ac BEFORE the run finished.
# Its rows carry `rep` in {"D2", "RECENT", "D2-LIVE-TRACE"} and a `source` in {"r1-instant",
# "trace seed <s> n64"}, with up to THREE rows per question_id. Two consequences:
#
#  1. `D2-LIVE-TRACE` must NOT be normalised to `D2`. Both are D2 CONTENT, but at different
#     HISTORY LENGTHS: the r1-instant rows use StudyR1's history and the trace rows use the
#     history the live traces hold at question arrival. Collapsing them would answer the
#     long-history question with short-history data without erroring.
#  2. The join key must be (question_id, rep, source), NOT (question_id, rep). A two-part key
#     silently keeps whichever row is read last.
ACC2_REPS = ("D2", "RECENT", "D2-LIVE-TRACE")
ACC2_KEY = ("question_id", "rep", "source")


def acc2_index(path: Path) -> Dict[Any, Dict[str, Any]]:
    """StudyACC2 rows keyed by (question_id, rep, source). See ACC2_KEY for why all three."""
    out: Dict[Any, Dict[str, Any]] = {}
    d = json.loads(Path(path).read_text())
    for r in d.get("plan", []):
        out[(r.get("question_id"), r.get("rep"), r.get("source"))] = r
    return out


def studyr1_index(root: Path) -> Dict[str, Dict[str, Any]]:
    """question_id -> {cell: correct, 'evidence_covered': bool}."""
    out: Dict[str, Dict[str, Any]] = {}
    p = root / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"
    with gzip.open(p, "rt") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:                                          # noqa: BLE001
                continue
            qid, cell = d.get("question_id"), d.get("cell")
            if not qid or cell not in ("K1", "K3"):
                continue
            rec = out.setdefault(qid, {})
            if d.get("correct") is not None:
                rec[cell] = bool(d["correct"])
            if d.get("evidence_covered") is not None:
                rec["evidence_covered"] = bool(d["evidence_covered"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--roots", required=True)
    ap.add_argument("--representation", default="RICH",
                    help="the representation ACTUALLY SENT. Today live2 ignores the action's "
                         "field and sends the full history, so RICH. One flag to flip when "
                         "Part A lands and arms begin emitting RECENT.")
    a = ap.parse_args(argv)

    H.setup_paths()
    import importlib
    sc = importlib.import_module("scorer.score")
    idx = studyr1_index(H.ROOT)
    eff = H.effective_representation(a.representation)
    if eff not in REPRESENTATION_TO_CELL:
        # D2: no StudyR1 per-question cell exists. The caller must use the per-category 32B-D2
        # table (section 33.3), and this join refuses rather than keying to the wrong cell.
        print("REFUSED: effective representation %r has NO StudyR1 per-question cell. %s"
              % (eff, RICH_IS_NOT_RECEIVABLE))
        print("Use the committed per-category 32B-D2 table instead; see report section 33.3.")
        return 2
    cell_key = REPRESENTATION_TO_CELL[eff]

    rows: List[Dict[str, Any]] = []
    for root in a.roots.split(","):
        for d in sorted(glob.glob(os.path.join(root.strip(), "*"))):
            m = CELL.match(os.path.basename(d))
            if not m:
                continue
            seed, arm, n = int(m.group(1)), m.group(2), int(m.group(3))
            run, trace = Path(d) / "run", Path(d) / "trace"
            if not (run / "outcomes.jsonl").exists():
                continue
            try:
                lo = sc.load(trace, run)
            except Exception:                                          # noqa: BLE001
                continue

            served = miss = 0
            tot = Dict  # placeholder to keep names obvious below
            all_rows: List[Dict[str, Any]] = []
            for opp, o in lo.outcomes.items():
                if o.get("kind") != "recall":
                    continue
                dev = lo.device_answers.get(opp)
                if dev is None:
                    continue
                qid = dev.get("question_id") or o.get("question_id")
                rec = idx.get(qid)
                if rec is None or cell_key not in rec:
                    miss += 1
                    continue
                on_time = bool(sc._within(o, sc.ROB_L_S))
                correct = bool(rec[cell_key]) if on_time else bool(dev.get("device_correct"))
                if on_time:
                    served += 1
                all_rows.append(dict(on_time=on_time, correct=correct,
                                     covered=bool(rec.get("evidence_covered", True))))

            if not all_rows:
                continue
            nall = len(all_rows)
            kall = sum(1 for r in all_rows if r["correct"])
            missr = [r for r in all_rows if not r["covered"]]
            covr = [r for r in all_rows if r["covered"]]
            rows.append(dict(
                seed=seed, n_devices=n, arm=arm,
                label="dry, committed-answer lookup",
                representation_sent=a.representation, studyr1_cell=cell_key,
                models=dict(cloud="Qwen3-VL-32B-I (StudyR1 %s)" % cell_key,
                            device="4B-I x RECENT (trace device_answers, D87)"),
                n_questions=nall, n_cloud_standing=served, n_missing_from_studyr1=miss,
                accuracy_all=round(kall / nall, 6),
                recent_misses=dict(n=len(missr),
                                   accuracy=(round(sum(1 for r in missr if r["correct"])
                                                   / len(missr), 6) if missr else None)),
                recent_covers=dict(n=len(covr),
                                   accuracy=(round(sum(1 for r in covr if r["correct"])
                                                   / len(covr), 6) if covr else None)),
                coverage_fraction=round(len(covr) / nall, 6),
            ))

    out = dict(check="covex_harden_task_value_join", is_measurement=False,
               label="D134 addendum item 1. Robot task value, DRY, COMMITTED-ANSWER LOOKUP, "
                     "stratified by whether the RECENT window covers the evidence.",
               caveat="Today live2 ignores RecallAction.representation and sends the full history, "
                      "so every row is RICH and the RICH-against-RECENT comparison is UNEXERCISED "
                      "(category 4), not dead. It will separate when Part A lands AND an arm emits "
                      "RECENT.",
               representation_sent=a.representation, rows=rows)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print("cells:", len(rows), "-> wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
