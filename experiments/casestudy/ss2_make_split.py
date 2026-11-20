"""D143 ruling A for single-shot: a seeded 30 / 70 DEV / EVAL split of each SS2 dataset.

The quality table is filled from the DEV part and SS devices draw from the EVAL part, so no number
the policy is fitted on is also a number it is scored on. This mirrors the robot rule, where the
table is fitted on the S-EMBER DEV split and LH-REQ robots draw only from EVAL.

The split is written to a COMMITTED FILE and read from there, never re-derived at use time. The
LH-REQ work established why: two independently written derivations of the same partition differ
somewhere and nothing catches it. A file can be diffed.

STRATIFIED BY SUBSET, and this is a PROVISIONAL choice recorded as such. The ruling says "a seeded
30/70 split of each SS dataset" and does not say whether to stratify. An unstratified draw over
RefSpatial would put a random 30 percent of 277 into DEV and could leave `unseen` (77 items) badly
represented in either part, which would make the fitted SS value a statement about a subset mix the
EVAL part does not share. Stratifying within each dataset keeps every subset's proportion in both
parts. Unstratified is one line away if the user prefers it.

The seed is a fixed STRING, not the run seed: the split must be identical in every run, at every
fleet size and under every arm, or the DEV / EVAL boundary would move between cells.
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SS2 = ROOT / "results/casestudy/study_ss2"

DEV_FRACTION = 0.30
SPLIT_SEED = "ss2|dev-eval|D143"
SOURCES = (("refspatial", SS2 / "refspatial_manifest.jsonl", "split"),
           ("realworldqa", SS2 / "realworldqa_manifest.jsonl", "subset"))
OUT = SS2 / "ss2_dev_eval_split.json"


def main():
    per_dataset = {}
    for name, man, subset_field in SOURCES:
        if not man.exists():
            raise SystemExit("missing manifest: %s" % man)
        rows = [json.loads(l) for l in man.read_text().splitlines() if l.strip()]
        by_subset = {}
        for r in rows:
            by_subset.setdefault(str(r[subset_field]), []).append(r["qid"])
        dev, ev, strata = [], [], {}
        for sub in sorted(by_subset):
            qids = sorted(by_subset[sub])
            rng = random.Random("%s|%s|%s" % (SPLIT_SEED, name, sub))
            order = list(qids)
            rng.shuffle(order)
            # round-half-up on the DEV count, so a subset of 1 still contributes a DEV item rather
            # than silently vanishing from the fit.
            k = int(len(order) * DEV_FRACTION + 0.5)
            d, e = sorted(order[:k]), sorted(order[k:])
            dev += d
            ev += e
            strata[sub] = dict(n=len(qids), n_dev=len(d), n_eval=len(e),
                               dev_fraction=round(len(d) / len(qids), 6))
        assert not (set(dev) & set(ev))
        assert len(dev) + len(ev) == len(rows)
        per_dataset[name] = dict(
            n=len(rows), subset_field=subset_field,
            n_dev=len(dev), n_eval=len(ev),
            dev_fraction=round(len(dev) / len(rows), 6),
            per_subset=strata,
            dev_qids=sorted(dev), eval_qids=sorted(ev))

    out = dict(
        _what="D143 ruling A: the seeded 30 / 70 DEV / EVAL split of each StudySS2 dataset. The SS "
              "quality table is FITTED on the DEV part; SS devices DRAW from the EVAL part.",
        _register="CENSUS over both manifests: every question is in exactly one part, asserted.",
        _seed=SPLIT_SEED,
        _seed_note="a fixed STRING, never the run seed, so the DEV / EVAL boundary is identical in "
                   "every run, at every fleet size and under every arm.",
        _dev_fraction_target=DEV_FRACTION,
        _stratified="PROVISIONAL: stratified by each dataset's own subset field (RefSpatial "
                    "`split`, RealWorldQA `subset`) so every subset keeps its proportion in both "
                    "parts. The ruling did not say whether to stratify; an unstratified draw could "
                    "leave RefSpatial `unseen` (77 items) badly represented and make the fitted SS "
                    "value a statement about a subset mix the EVAL part does not share.",
        _rounding="round-half-up on the DEV count per subset, so a subset of one still contributes "
                  "a DEV item rather than vanishing from the fit.",
        _script="experiments/casestudy/ss2_make_split.py",
        per_dataset=per_dataset)
    OUT.write_text(json.dumps(out, indent=1))
    print("wrote", OUT)
    for name, d in per_dataset.items():
        print("  %-12s n=%-4d dev=%-4d eval=%-4d frac=%.4f  %s"
              % (name, d["n"], d["n_dev"], d["n_eval"], d["dev_fraction"],
                 {k: (v["n_dev"], v["n_eval"]) for k, v in d["per_subset"].items()}))


if __name__ == "__main__":
    main()
