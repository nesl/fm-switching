#!/usr/bin/env python3
"""StudySS2 why-analysis: where the cloud-minus-device gain comes from (CPU only, committed rows).

  python3 -I experiments/casestudy/ss2_why.py

Three questions, in the order they have to be asked:

  1. FAILURE TYPES per subset. The RealWorldQA metric is `exact_match`, and for free-form it is exact
     string equality against the gold after lowercasing and dropping one trailing period. A score of
     0 therefore merges "saw the wrong thing" with "said the right thing in the wrong shape", and
     those are different findings about a device.
  2. WELL-FORMEDNESS. If the device answers in prose more often than the cloud does, part of the
     gain is formatting compliance rather than perception, which is CLAUDE.md consistency check 3's
     motivating failure (an accuracy column that ranked arms backwards because every cloud answer was
     an unmatchable placeholder). The gain is therefore recomputed on the questions where BOTH tiers
     produced a well-formed answer.
  3. IMAGE-CLUSTERED CIs. The committed CI resamples QUESTIONS. If several questions share an image,
     questions are not independent and that CI is too narrow. Clustering is by the manifest's
     `image_sha16`, which is the hash of the DECODED pixels, the same key the shared-image exclusion
     uses.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

SS2 = ROOT / "results/casestudy/study_ss2"
SEED, NB = 0, 10000          # the committed compare's own bootstrap count
LETTERS = ("A", "B", "C", "D")
NUM = re.compile(r"^-?\d+(\.\d+)?$")


def load(dataset):
    dev = json.loads((SS2 / f"{dataset}_device.json").read_text())["rows"]
    clo = json.loads((SS2 / f"{dataset}_cloud32b.json").read_text())["rows"]
    man = {}
    with (SS2 / f"{dataset}_manifest.jsonl").open() as fh:
        for ln in fh:
            r = json.loads(ln)
            man[r["qid"]] = r
    c = {r["qid"]: r for r in clo}
    pairs = [(r, c[r["qid"]]) for r in dev if r["qid"] in c]
    return pairs, man


def norm(s):
    return str(s).lower().strip().rstrip(".")


def wellformed(row, subset):
    """Did the tier produce a PARSEABLE CANDIDATE ANSWER, independent of whether it is right?

    mcq: the scorer's own letter extraction found exactly one letter. A row whose extraction failed
    scores 0 for a reason that is not perception.
    free_form: the reply is a bare short answer rather than prose. Measured as at most 4 whitespace
    tokens and not truncated at the generation cap, because a reply that ran into the cap is a
    sentence the scorer could never match.
    """
    if subset == "mcq":
        return bool(str(row["answer"]).strip() in LETTERS)
    cap = int(row.get("completion_tokens") or 0)
    return len(norm(row["answer_raw"]).split()) <= 4 and cap < 16


def free_form_class(row, gold):
    """Why this free-form answer scored 0. Mutually exclusive, checked in order."""
    p, g = norm(row["answer_raw"]), norm(gold)
    if p == g:
        return "correct"
    if g and g in p.split():
        return "contains_gold_as_a_word"      # right answer, extra words
    if g and g in p:
        return "contains_gold_as_a_substring"
    if NUM.match(p) and NUM.match(g):
        if abs(float(p) - float(g)) < 1e-9:
            return "numeric_equal_different_spelling"
        return "numeric_off_by_one" if abs(float(p) - float(g)) == 1 else "numeric_wrong"
    if {p, g} <= {"yes", "no"}:
        return "yes_no_flipped"
    if {p, g} <= {"left", "right"} or {p, g} <= {"up", "down"}:
        return "direction_flipped"
    if len(p.split()) > 4:
        return "prose_reply"
    return "other_wrong"


def boot_delta(d, clusters, rng):
    """Paired bootstrap of mean(cloud - device), resampling CLUSTERS with replacement.

    Passing one cluster per question reproduces the committed question-level bootstrap, so the two
    CIs below differ only in the resampling unit and nothing else.
    """
    keys = sorted(clusters)
    idx = {k: np.array(clusters[k]) for k in keys}
    arr = np.asarray(d, float)
    n = len(keys)
    out = np.empty(NB)
    for b in range(NB):
        take = rng.integers(0, n, n)
        sel = np.concatenate([idx[keys[j]] for j in take])
        out[b] = arr[sel].mean()
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


REFSPATIAL_JSON_XY = re.compile(r'"x"\s*:\s*-?\d+(?:\.\d+)?\s*,\s*"y"\s*:\s*-?\d+(?:\.\d+)?')


def refspatial_class(row):
    """Why this point answer scored what it did. Mutually exclusive, checked in order.

    The distinction that matters is between a model that pointed at the wrong place and a model
    whose answer the PARSER could not read. `ss2_bench_kit._iter_json_points` accepts a coordinate
    only as a 2-element numeric list under a point key, or as a bare 2-element list. It does NOT
    handle `{"x": .., "y": ..}`, which is the form the 32B prefers, and the two text fallbacks need
    brackets or parentheses that this form does not have. So a clean JSON point from the cloud parses
    to zero points and scores 0.
    """
    n, acc = int(row["score"]["n_points"]), float(row["score"]["point_accuracy"])
    if n == 0:
        return ("parser_dropped_a_wellformed_point"
                if REFSPATIAL_JSON_XY.search(row["answer_raw"] or "")
                else "refused_or_no_coordinates")
    if acc >= 1.0:
        return "all_points_inside_mask"
    if acc > 0.0:
        return "some_points_inside_mask_diluted_by_extras"
    return "points_outside_mask"


def analyse_refspatial():
    pairs, man = load("refspatial")
    img = {q: man[q]["image_sha16"] for q in man}
    res = dict(dataset="refspatial", n_pairs=len(pairs), subsets={},
               images=dict(n_questions=len(pairs),
                           n_distinct_images=len({img[d["qid"]] for d, _ in pairs}),
                           questions_per_image=dict(Counter(
                               Counter(img[d["qid"]] for d, _ in pairs).values()))))
    for sub in sorted({d["score"]["split"] for d, _ in pairs}) + ["ALL"]:
        P = [(d, c) for d, c in pairs if sub == "ALL" or d["score"]["split"] == sub]
        dv = np.array([float(d["score"]["point_accuracy"]) for d, _ in P])
        cl = np.array([float(c["score"]["point_accuracy"]) for _, c in P])
        diff = cl - dv
        cl_by_img = defaultdict(list)
        for i, (d, _) in enumerate(P):
            cl_by_img[img[d["qid"]]].append(i)
        # "any point inside the mask" needs no mask: a positive fraction means at least one hit
        any_d = (dv > 0).astype(float)
        any_c = (cl > 0).astype(float)
        wf_d = np.array([int(d["score"]["n_points"]) == 1 for d, _ in P])
        wf_c = np.array([int(c["score"]["n_points"]) == 1 for _, c in P])
        both = wf_d & wf_c
        dropped_c = sum(1 for _, c in P if refspatial_class(c)
                        == "parser_dropped_a_wellformed_point")
        dropped_d = sum(1 for d, _ in P if refspatial_class(d)
                        == "parser_dropped_a_wellformed_point")
        cell = dict(
            n=len(P), device_accuracy=float(dv.mean()), cloud_accuracy=float(cl.mean()),
            delta=float(diff.mean()),
            ci95_question_bootstrap=boot_delta(diff, {i: [i] for i in range(len(P))},
                                               np.random.default_rng(SEED)),
            ci95_image_clustered_bootstrap=boot_delta(
                diff, dict(enumerate(cl_by_img.values())), np.random.default_rng(SEED)),
            n_points=dict(device=dict(Counter(int(d["score"]["n_points"]) for d, _ in P)),
                          cloud=dict(Counter(int(c["score"]["n_points"]) for _, c in P))),
            failure_types={t: dict(device=sum(1 for d, _ in P if refspatial_class(d) == t),
                                   cloud=sum(1 for _, c in P if refspatial_class(c) == t))
                           for t in sorted({refspatial_class(r) for p in P for r in p})},
            any_point_inside_mask=dict(
                device=float(any_d.mean()), cloud=float(any_c.mean()),
                delta=float((any_c - any_d).mean()),
                ci95_question_bootstrap=boot_delta(any_c - any_d,
                                                   {i: [i] for i in range(len(P))},
                                                   np.random.default_rng(SEED)),
                note="CONSTRUCTED from the committed per-question accuracy, not re-scored: a "
                     "positive fraction implies at least one predicted point was inside the mask. "
                     "It removes the multi-point dilution, under which a reply carrying one correct "
                     "point and seven extras scores 0.125."),
            wellformed_exactly_one_point=dict(
                device=int(wf_d.sum()), cloud=int(wf_c.sum()), both=int(both.sum())),
            parser_dropped_wellformed_points=dict(
                device=dropped_d, cloud=dropped_c,
                cloud_accuracy_understated_by_at_most=round(dropped_c / max(len(P), 1), 6),
                register="CONSTRUCTED BOUND, not a measurement: the GT masks are not on this box "
                         "(the run read them from /dev/shm/ss2_data on the Orin), so whether each "
                         "dropped point lands inside its mask cannot be checked here. The true "
                         "correction is between 0 and this bound."))
        if both.sum() and both.sum() < len(P):
            cell["wellformed_both_only"] = dict(
                n=int(both.sum()), device_accuracy=float(dv[both].mean()),
                cloud_accuracy=float(cl[both].mean()), delta=float(diff[both].mean()),
                ci95_question_bootstrap=boot_delta(
                    diff[both], {i: [i] for i in range(int(both.sum()))},
                    np.random.default_rng(SEED)))
        res["subsets"][sub] = cell
    return res


def analyse(dataset):
    pairs, man = load(dataset)
    subsets = sorted({d["score"]["subset"] for d, _ in pairs})
    res = dict(dataset=dataset, n_pairs=len(pairs), subsets={})
    img = {q: man[q]["image_sha16"] for q in man}
    res["images"] = dict(
        n_questions=len(pairs), n_distinct_images=len({img[d["qid"]] for d, _ in pairs}),
        questions_per_image=dict(Counter(Counter(img[d["qid"]] for d, _ in pairs).values())))
    for sub in subsets:
        P = [(d, c) for d, c in pairs if d["score"]["subset"] == sub]
        dv = np.array([d["score"]["exact_match"] for d, _ in P])
        cl = np.array([c["score"]["exact_match"] for _, c in P])
        diff = cl - dv
        rng = np.random.default_rng(SEED)
        by_q = {i: [i] for i in range(len(P))}
        cl_by_img = defaultdict(list)
        for i, (d, _) in enumerate(P):
            cl_by_img[img[d["qid"]]].append(i)
        ci_q = boot_delta(diff, by_q, np.random.default_rng(SEED))
        ci_i = boot_delta(diff, dict(enumerate(cl_by_img.values())), rng)
        wf_d = np.array([wellformed(d, sub) for d, _ in P])
        wf_c = np.array([wellformed(c, sub) for _, c in P])
        both = wf_d & wf_c
        cell = dict(
            n=len(P), device_accuracy=float(dv.mean()), cloud_accuracy=float(cl.mean()),
            delta=float(diff.mean()), ci95_question_bootstrap=ci_q,
            ci95_image_clustered_bootstrap=ci_i,
            two_by_two=dict(both_right=int(((dv == 1) & (cl == 1)).sum()),
                            cloud_only=int(((dv == 0) & (cl == 1)).sum()),
                            device_only=int(((dv == 1) & (cl == 0)).sum()),
                            both_wrong=int(((dv == 0) & (cl == 0)).sum())),
            wellformed=dict(device=int(wf_d.sum()), cloud=int(wf_c.sum()), both=int(both.sum()),
                            device_only_malformed=int((~wf_d & wf_c).sum()),
                            cloud_only_malformed=int((wf_d & ~wf_c).sum())))
        if both.sum() and both.sum() < len(P):
            sub_idx = np.where(both)[0]
            cell["wellformed_both_only"] = dict(
                n=int(both.sum()), device_accuracy=float(dv[both].mean()),
                cloud_accuracy=float(cl[both].mean()), delta=float(diff[both].mean()),
                ci95_question_bootstrap=boot_delta(diff[both],
                                                  {i: [i] for i in range(int(both.sum()))},
                                                  np.random.default_rng(SEED)))
        elif both.sum() == len(P):
            cell["wellformed_both_only"] = dict(
                n=int(both.sum()),
                note="every pair is well formed on both tiers, so this is the headline cell "
                     "unchanged and NO part of the gain is answer formatting")
        if sub == "mcq":
            cell["failure_types"] = {
                t: dict(device=sum(1 for d, _ in P if mcq_class(d) == t),
                        cloud=sum(1 for _, c in P if mcq_class(c) == t))
                for t in ("correct", "wrong_letter", "no_letter_extracted")}
        else:
            kinds = sorted({free_form_class(r, r["references"][0])
                            for side in (0, 1) for r in [p[side] for p in P]})
            cell["failure_types"] = {
                t: dict(device=sum(1 for d, _ in P if free_form_class(d, d["references"][0]) == t),
                        cloud=sum(1 for _, c in P if free_form_class(c, c["references"][0]) == t))
                for t in kinds}
        res["subsets"][sub] = cell
    return res


def mcq_class(row):
    a = str(row["answer"]).strip()
    if a not in LETTERS:
        return "no_letter_extracted"
    return "correct" if row["score"]["exact_match"] == 1.0 else "wrong_letter"


def main():
    out = dict(
        label="StudySS2 why-analysis: failure types per subset, image-clustered CIs, and the gain "
              "restricted to well-formed answers. CPU only on flash; every score is a committed "
              "StudySS2 row; no model, no GPU, no re-scoring.",
        at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB, datasets={})
    for ds in ("realworldqa", "refspatial"):
        if not ((SS2 / f"{ds}_device.json").exists()
                and (SS2 / f"{ds}_cloud32b.json").exists()):
            continue
        out["datasets"][ds] = analyse(ds) if ds == "realworldqa" else analyse_refspatial()
    out["_provenance"] = stamp(script="ss2_why.py", model="none", device="cpu",
                               n=sum(v["n_pairs"] for v in out["datasets"].values()), args=None)
    (SS2 / "ss2_why.json").write_text(json.dumps(out, indent=1))
    for ds, v in out["datasets"].items():
        print(f"== {ds}: {v['n_pairs']} pairs, {v['images']['n_distinct_images']} distinct images, "
              f"questions per image {v['images']['questions_per_image']}")
        for sub, c in v["subsets"].items():
            print(f"  [{sub}] n={c['n']} device={c['device_accuracy']:.4f} "
                  f"cloud={c['cloud_accuracy']:.4f} delta={c['delta']:+.4f}")
            print(f"      CI question {c['ci95_question_bootstrap']}")
            print(f"      CI image    {c['ci95_image_clustered_bootstrap']}")
            if "two_by_two" in c:
                print(f"      2x2 {c['two_by_two']}")
            if "wellformed" in c:
                print(f"      wellformed {c['wellformed']}")
            if "wellformed_both_only" in c:
                w = c["wellformed_both_only"]
                print("      wf-only", {k: (round(x, 4) if isinstance(x, float) else x)
                                         for k, x in w.items()})
            print(f"      failures {c['failure_types']}")
            for k in ("any_point_inside_mask", "parser_dropped_wellformed_points",
                      "wellformed_exactly_one_point", "n_points"):
                if k in c:
                    print(f"      {k} " + json.dumps(
                        {a: (round(b, 4) if isinstance(b, float) else b)
                         for a, b in c[k].items() if a not in ("note", "register")}))
    print("wrote", SS2 / "ss2_why.json")


if __name__ == "__main__":
    main()
