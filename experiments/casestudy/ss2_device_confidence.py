#!/usr/bin/env python3
"""Per-question DEVICE answer confidence for the StudySS2 single-shot items (CPU only).

  python3 -I experiments/casestudy/ss2_device_confidence.py \
      --runs results/casestudy/study_ss2/realworldqa_device_logprobs.json \
             results/casestudy/study_ss2/refspatial_device_logprobs.json

User ruling 2026-11-20. StudySS1 and StudySS2 recorded no answer probabilities, so the five
cascade-style arms received None for every single-shot question even after the wiring fix. This
turns a re-recorded run (same kit, same prompts, `logprobs` on) into the table the wiring reads.

THE RULE, as ruled, and WHY IT IS THE COMMITTED ONE FOR MCQ
  mcq          the chosen letter's probability, computed by the COMMITTED
               `study_f_common.letter_probs`, imported and not retyped, taking mass on the letter
               the model actually emitted. That is exactly what StudyE7's robot confidences are
               (`baselines/device_confidence._load_primary` reads `mass[first_token]`), so the
               single-shot and robot values entering the same field are the same quantity and not
               two different notions of confidence sharing one name.
  free_form    the GEOMETRIC MEAN token probability of the answer, exp(mean(token logprobs)).
  points       the same rule as free_form, and LABELLED A WEAK SIGNAL: a coordinate's token
               probabilities say how confidently the model emitted those digits, which is not the
               same as how likely the point is to be right. Every row carries
               `signal_strength: "weak"` so no consumer can treat it as the mcq value's equal.

Length is the reason the two rules differ. A letter is one token, so its probability IS the
answer's probability. A free-form answer is several tokens, and a product over them falls with
length, which would make a long correct answer look less confident than a short wrong one; the
geometric mean removes that length dependence.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "experiments/lib"), str(ROOT / "experiments/sember"),
           str(ROOT / "experiments/casestudy")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from _provenance import stamp  # noqa: E402

OUT = ROOT / "results/casestudy/study_ss2/ss2_device_confidence.json"


def committed_letter_probs():
    """`study_f_common.letter_probs`, lifted by AST so importing it pulls in no server path."""
    import ast
    src = (ROOT / "experiments/sember/study_f_common.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "letter_probs")
    ns = {"math": math}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "study_f_common.py", "exec"), ns)  # noqa: S102
    import hashlib
    return ns["letter_probs"], hashlib.sha256(ast.unparse(fn).encode()).hexdigest()


def geometric_mean_prob(lp):
    """exp(mean(token logprob)) over the answer's own tokens, or None if there are none."""
    vals = [float(t["logprob"]) for t in (lp or []) if t.get("logprob") is not None]
    if not vals:
        return None
    return float(math.exp(statistics.fmean(vals)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    a = ap.parse_args()
    letter_probs, lp_sha = committed_letter_probs()
    conf, rows, skipped = {}, [], []
    for path in a.runs:
        doc = json.loads(Path(path).read_text())
        for r in doc["rows"]:
            qid = r["qid"]
            lp = r.get("token_logprobs") or r.get("logprobs")
            if not lp:
                skipped.append(dict(qid=qid, why="no token logprobs in this row"))
                continue
            sub = (r.get("score") or {}).get("subset")
            if sub == "mcq":
                pr = letter_probs(lp)
                tok = (pr or {}).get("first_token")
                v = None if not pr or tok is None else pr["mass"].get(str(tok).strip())
                kind, strength = "mcq_chosen_letter_mass", "primary"
            elif r["dataset"] == "refspatial":
                v, kind, strength = geometric_mean_prob(lp), "geometric_mean_token_prob", "weak"
            else:
                v, kind, strength = geometric_mean_prob(lp), "geometric_mean_token_prob", "primary"
            if v is None:
                skipped.append(dict(qid=qid, why=f"rule {kind} produced no value"))
                continue
            v = max(0.0, min(float(v), 1.0))
            conf[qid] = v
            rows.append(dict(qid=qid, dataset=r["dataset"], subset=sub, confidence=v,
                             rule=kind, signal_strength=strength,
                             n_answer_tokens=len(lp)))
    by_rule = {}
    for r in rows:
        b = by_rule.setdefault(r["rule"], dict(n=0, values=[]))
        b["n"] += 1
        b["values"].append(r["confidence"])
    summary = {k: dict(n=v["n"], median=round(statistics.median(v["values"]), 6),
                       min=round(min(v["values"]), 6), max=round(max(v["values"]), 6))
               for k, v in by_rule.items()}
    out = dict(
        label="StudySS2 single-shot DEVICE answer confidence, per question, from a re-recorded "
              "Orin 4B pass with logprobs. CPU only; nothing here runs a model.",
        at=datetime.now().isoformat(),
        rule=dict(mcq="committed study_f_common.letter_probs, mass on the emitted letter, the "
                      "same quantity StudyE7 supplies for robot questions",
                  free_form="geometric mean token probability, exp(mean(token logprob))",
                  points="the same rule as free_form, LABELLED WEAK: token confidence in the "
                         "digits of a coordinate is not confidence that the point is right",
                  committed_letter_probs_sha256=lp_sha),
        n_questions=len(conf), by_rule=summary, skipped=skipped[:50], n_skipped=len(skipped),
        confidence=conf, rows=rows)
    out["_provenance"] = stamp(script="ss2_device_confidence.py", model="none", device="cpu",
                               n=len(conf), args=a)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT}: {len(conf)} questions, {len(skipped)} skipped")
    for k, v in summary.items():
        print(f"  {k}: n {v['n']} median {v['median']} range {v['min']} to {v['max']}")


if __name__ == "__main__":
    main()
