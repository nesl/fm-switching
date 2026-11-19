"""StudySS1-judge: agreement between the LLM judge and the containment scorer.

SEPARATE FROM `ss1_judge.py` ON PURPOSE. The judge script is run unchanged on both the 4B and the
32B answers, because any prompt or scorer drift between those two runs would turn a model
comparison into a scorer comparison and would be invisible in the numbers. So the extra analysis
the brief asks for -- per-dimension agreement with CIs, and the disagreement cases -- lives here
rather than as an edit to the shared script.

Reports:
  * agreement overall and PER EgoThink DIMENSION, with Wilson 95% intervals;
  * the judge and containment means per dimension, so a low agreement can be read as which scorer
    is the lenient one;
  * the DISAGREEMENT CASES themselves, split by direction, because an agreement rate alone does not
    say which scorer is right.

Usage:
  python3 ss1_judge_agreement.py --judge <judge.json> --out <agreement.json> [--sample 12]
"""
from __future__ import annotations
import argparse, json, math, random
from collections import defaultdict
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.959963985):
    """Wilson score interval. Correct at the small per-dimension n here, where the normal
    approximation is not."""
    if n == 0:
        return (None, None)
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - half) / d, (c + half) / d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    j = json.loads(Path(a.judge).read_text())
    rows = [r for r in j["rows"] if r.get("judge_rating") is not None]

    def agree(r):
        return (float(r["judge_rating"]) >= 0.5) == (float(r["containment"]) >= 0.5)

    by = defaultdict(list)
    for r in rows:
        by[r.get("dimension") or "UNKNOWN"].append(r)

    dims = {}
    for d, rs in sorted(by.items()):
        k = sum(1 for r in rs if agree(r))
        lo, hi = wilson(k, len(rs))
        jm = sum(float(r["judge_rating"]) for r in rs) / len(rs)
        cm = sum(float(r["containment"]) for r in rs) / len(rs)
        dims[d] = dict(n=len(rs), agree=k, agreement=k / len(rs),
                       ci95=[None if lo is None else round(lo, 4),
                             None if hi is None else round(hi, 4)],
                       judge_mean=round(jm, 4), containment_mean=round(cm, 4),
                       judge_minus_containment=round(jm - cm, 4))

    k_all = sum(1 for r in rows if agree(r))
    lo, hi = wilson(k_all, len(rows))

    # the disagreements, split by direction: which scorer called it correct
    judge_yes = [r for r in rows if float(r["judge_rating"]) >= 0.5 > float(r["containment"])]
    cont_yes = [r for r in rows if float(r["containment"]) >= 0.5 > float(r["judge_rating"])]
    rnd = random.Random(a.seed)

    def sample(rs):
        s = list(rs)
        rnd.shuffle(s)
        return [dict(qid=r["qid"], dimension=r.get("dimension"), question=r["question"],
                     reference=r["reference"], answer=r["answer"],
                     judge_rating=r["judge_rating"], containment=r["containment"],
                     judge_raw=(r.get("judge_raw") or "")[:400]) for r in s[:a.sample]]

    out = dict(
        study="StudySS1", pass_="judge_vs_containment_agreement",
        source_judge_file=a.judge, judge_model=j.get("judge_model"),
        source_run=j.get("source_run"),
        n=len(rows), n_unparsed=j.get("n_unparsed"),
        overall=dict(agree=k_all, agreement=k_all / len(rows) if rows else None,
                     ci95=[None if lo is None else round(lo, 4),
                           None if hi is None else round(hi, 4)],
                     judge_mean=j.get("judge_mean"),
                     containment_mean=j.get("containment_mean")),
        by_dimension=dims,
        disagreements=dict(
            judge_correct_containment_zero=len(judge_yes),
            containment_correct_judge_zero=len(cont_yes),
            note=("direction matters: the first is containment missing a correct answer whose "
                  "wording differs from the reference, the second is the judge rejecting an answer "
                  "that literally contains the reference."),
            sample_judge_yes_containment_no=sample(judge_yes),
            sample_containment_yes_judge_no=sample(cont_yes)))
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print("wrote", a.out)
    print("overall agreement %.4f  CI [%.4f, %.4f]  n=%d" %
          (out["overall"]["agreement"], lo, hi, len(rows)))
    print("%-24s %5s %9s %18s %8s %8s" % ("dimension", "n", "agree", "ci95", "judge", "contain"))
    for d, v in sorted(dims.items(), key=lambda kv: kv[1]["agreement"]):
        print("%-24s %5d %9.4f  [%.3f, %.3f] %8.3f %8.3f" %
              (d, v["n"], v["agreement"], v["ci95"][0], v["ci95"][1],
               v["judge_mean"], v["containment_mean"]))


if __name__ == "__main__":
    main()
