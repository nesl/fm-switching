#!/usr/bin/env python3
"""StudyD12-pilot analysis (CPU). INDICATIVE (n = 50 per dataset). WISDM and MIT-BIH tasks are OUR OWN formulations;
STARK's questions and answers are the benchmark's own, verbatim.

Scoring:
  WISDM / MIT-BIH: last `[ANSWER] <int> [/ANSWER]` in the output; correct iff int == answer_index (1-based option).
  STARK: last `[RESULTS_START] ... [RESULTS_END]`; numbers parsed from the span. Categorical families (all 0/1 in this
  sample): correct iff the first parsed value equals the answer's value. Continuous families: no accuracy (scored by
  RMSE / RMSPE in the paper, no chance or majority baseline) — parse rate and, where the shapes match, RMSE reported.
Per dataset x model x arm: accuracy, Wilson 95 %, always-majority baseline (most common label among the 50 items),
chance (WISDM 1/18, MIT-BIH 1/5, STARK categorical 1/2), prompt tokens median / max (and vs the prep's 4B count),
failures (no parse), empty answers, finish_reason length.
Main-sweep estimate for 32B Thinking (T 1.0, top_p 0.95, top_k 20, max 16384): from this pilot's 32B-Instruct prompt
sizes and StudyD9 / StudyD10's measured 32B-Thinking rates on the same vLLM stack (stated in the output).
"""
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from _provenance import stamp  # noqa: E402

PREP = Path("results/ts/study_d12_prep")
D = Path("results/ts/study_d12_pilot")
REQ = D / "study_d12_pilot_requests_h100nvl.jsonl"
OUT = D / "study_d12_pilot_results_h100nvl.json"
CHANCE = {"wisdm": 1 / 18, "mitdb": 1 / 5, "stark": 1 / 2}
NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?")


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [100 * (c - h), 100 * (c + h)]


def score(r, it):
    t = r["text"] or ""
    if r["dataset"] in ("wisdm", "mitdb"):
        m = re.findall(r"\[ANSWER\]\s*(\d+)\s*\[/ANSWER\]", t)
        if not m:
            return dict(parsed=False, correct=False)
        return dict(parsed=True, pred=int(m[-1]), correct=int(m[-1]) == int(it["answer_index"]))
    m = re.findall(r"\[RESULTS_START\](.*?)\[RESULTS_END\]", t, re.S)
    if not m:
        return dict(parsed=False, correct=False)
    vals = [float(x) for x in NUM.findall(m[-1])]
    ans = [float(x) for x in NUM.findall(it["answer"])]
    if not vals:
        return dict(parsed=False, correct=False)
    if it["categorical"]:
        return dict(parsed=True, pred=vals[0], correct=vals[0] == ans[0])
    rmse = float(np.sqrt(np.mean((np.array(vals) - np.array(ans)) ** 2))) if len(vals) == len(ans) else None
    return dict(parsed=True, pred=vals[:8], correct=None, rmse=rmse, shape_match=len(vals) == len(ans))


def main():
    man = json.load(open(PREP / "manifest.json"))
    items = {(ds, it["item_id"]): it for ds in man for it in man[ds]}
    rows = [json.loads(l) for l in open(REQ)]
    res = dict(label="INDICATIVE (n = 50 per dataset)",
               own_formulations="WISDM (18-way activity) and MIT-BIH (5-way AAMI beat class) are OUR OWN task "
                                "formulations; STARK questions/answers are the benchmark's, verbatim",
               errors=sum(bool(r["error"]) for r in rows), cells={})
    for (model, ds, arm) in sorted({(r["model"], r["dataset"], r["arm"]) for r in rows}):
        rs = [r for r in rows if (r["model"], r["dataset"], r["arm"]) == (model, ds, arm) and not r["error"]]
        sc = [(r, items[(ds, r["item_id"])], score(r, items[(ds, r["item_id"])])) for r in rs]
        pt = [r["prompt_tokens"] for r in rs if r["prompt_tokens"]]
        cell = dict(n=len(rs), errors=sum(1 for r in rows if (r["model"], r["dataset"], r["arm"]) == (model, ds, arm)
                                         and r["error"]),
                    failures_no_parse=sum(not s["parsed"] for _, _, s in sc),
                    empty_answers=sum(not (r["text"] or "").strip() for r, _, _ in sc),
                    finish_length=sum(r["finish_reason"] == "length" for r, _, _ in sc),
                    prompt_tokens=dict(median=float(np.median(pt)), max=int(max(pt))) if pt else None,
                    prompt_tokens_vs_prep_4b=dict(
                        equal=sum(r["prompt_tokens"] == r["prep_prompt_tokens_4b"] for r in rs),
                        max_abs_diff=max(abs((r["prompt_tokens"] or 0) - (r["prep_prompt_tokens_4b"] or 0)) for r in rs)),
                    completion_tokens_median=float(np.median([r["completion_tokens"] for r in rs if r["completion_tokens"]])))
        if ds in ("wisdm", "mitdb"):
            k = sum(s["correct"] for _, _, s in sc)
            labs = Counter(it["answer_index"] for _, it, _ in sc)
            cell.update(accuracy_pct=100 * k / len(sc), correct=k, wilson95_pct=wilson(k, len(sc)),
                        majority_baseline_pct=100 * labs.most_common(1)[0][1] / len(sc), chance_pct=100 * CHANCE[ds],
                        pred_distribution=dict(Counter(s.get("pred") for _, _, s in sc).most_common(6)))
        else:
            cat = [(r, it, s) for r, it, s in sc if it["categorical"]]
            con = [(r, it, s) for r, it, s in sc if not it["categorical"]]
            k = sum(bool(s["correct"]) for _, _, s in cat)
            labs = Counter(json.loads(it["answer"])[0] for _, it, _ in cat)
            cell.update(categorical=dict(n=len(cat), accuracy_pct=100 * k / len(cat), correct=k,
                                         wilson95_pct=wilson(k, len(cat)),
                                         majority_baseline_pct=100 * labs.most_common(1)[0][1] / len(cat),
                                         chance_pct=100 * CHANCE["stark"], answer_distribution=dict(labs)),
                        continuous=dict(n=len(con), parsed=sum(s["parsed"] for _, _, s in con),
                                        shape_match=sum(bool(s.get("shape_match")) for _, _, s in con),
                                        rmse_per_item={it["family"]: s.get("rmse") for _, it, s in con},
                                        note="no accuracy for continuous families (paper scores RMSE/RMSPE)"))
        res["cells"][f"{model}/{ds}/{arm}"] = cell
    # main-sweep estimate (32B Thinking), stated assumptions
    res["main_sweep_estimate_32B_thinking"] = dict(
        basis=("StudyD9 32B-Thinking, same vLLM stack, conc 8: 801 image questions per seed in ~43 min (ERQA / "
               "MV-RoboBench prompts ~1.0-3.5k tokens; median 570 completion tokens, max 10.1k) = ~3.2 s per item at "
               "conc 8; StudyD10 single-request decode ~43 tok/s. Time-series prompts here are 0.5-4k tokens, "
               "comparable; completion length on these tasks is UNKNOWN until measured (it dominates)."),
        per_1000_items_h_at_conc8=dict(if_median_570_tok=round(1000 * 3.2 / 3600, 2),
                                       if_median_2000_tok=round(1000 * 3.2 * 2000 / 570 / 3600, 2),
                                       if_median_4000_tok=round(1000 * 3.2 * 4000 / 570 / 3600, 2)),
        note="not run; a 30-item 32B-Thinking timing probe would pin the completion length")
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d12_pilot_analyse.py", model="4BI,32BI", device="cpu", n=len(rows))
    OUT.write_text(json.dumps(res, indent=1, default=float))
    for k, c in res["cells"].items():
        if "accuracy_pct" in c:
            print(k, f"acc {c['accuracy_pct']:.0f}% {[round(x) for x in c['wilson95_pct']]} maj {c['majority_baseline_pct']:.0f} "
                     f"chance {c['chance_pct']:.1f} fail {c['failures_no_parse']} empty {c['empty_answers']} "
                     f"tok {c['prompt_tokens']} prep= {c['prompt_tokens_vs_prep_4b']}")
        else:
            cc = c["categorical"]
            print(k, f"cat acc {cc['accuracy_pct']:.0f}% ({cc['n']}) {[round(x) for x in cc['wilson95_pct']]} "
                     f"maj {cc['majority_baseline_pct']:.0f} fail {c['failures_no_parse']} empty {c['empty_answers']} "
                     f"cont parsed {c['continuous']['parsed']}/{c['continuous']['n']} tok {c['prompt_tokens']}")


if __name__ == "__main__":
    main()
