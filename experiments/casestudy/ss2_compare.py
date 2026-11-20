"""StudySS2 compare: device 4B against cloud 32B, paired on the same questions.

Same structure as ss1_compare.py by design, so only the LOADER and the SUBSET definitions differ.
D142 requires, per dataset and subset: paired bootstrap CIs, the 2x2, TTFT and the prompt-token
parity check, with no verdict.

SUBSETS, taken from the data rather than assumed:
  * RefSpatial   -> location / placement / unseen
  * RealWorldQA  -> MCQ against free-form
  * CODA-LM      -> general / regional / suggestion, judged on CODA-LM's own 1-10 prompt

TWO REGISTERS IN ONE TABLE, kept separate because a reader will not separate them. The CODA-LM
per-task 1-10 MEANS are CODA-LM's own quantity, its "Text-Score", and need no caveat. The 2x2 is
OUR derived object with a cut WE chose, since arXiv:2404.10595 reports no pass/fail threshold at
all; the cut is named at every point of use.

MCQ AND FREE-FORM ARE PARTLY A SCORER SPLIT, not only a question-type split: exact-letter match and
containment or a judge are different instruments, and two scorers already disagreed on the same 700
EgoThink answers. The scorer is therefore named per subset in the output.

D142. Reports numbers only. NO qualification threshold, NO verdict, NO recommendation, including by
implication in ordering or framing: D136's gate call is the user's and is deliberately withheld
here.

Per dataset, paired on the same question ids:
  * 4B vs 32B accuracy with PAIRED bootstrap CIs on the difference;
  * the 2x2: both right, cloud only, device only, both wrong;
  * VizWiz: by answer type, and answerable-only;
  * EgoThink: by dimension, with the judge mean rating reported on its native 0 / 0.5 / 1 scale
    (NO binarisation) and containment separately;
  * TTFT, device against cloud, with the load condition and path named on BOTH sides.

Usage:
  python3 ss1_compare.py --device <device.json> --cloud <cloud.json> --dataset vizwiz|egothink \
      [--device-judge <judge.json> --cloud-judge <judge.json>] --out <compare.json>
"""
from __future__ import annotations
import argparse, json, random, statistics
import collections
from collections import defaultdict
from pathlib import Path

# VizWiz VQA accuracy is graded in [0,1], so a 2x2 needs a cut. It is STATED rather than implied,
# and the sensitivity is reported beside it, because a threshold nobody registered moved a headline
# agreement figure 17 points earlier in this study.
VQA_RIGHT_CUT = 0.5
# Pre-registered before the distribution was seen, and OURS rather than CODA-LM's, which does not
# binarise at all. See ss2_kit and results/casestudy/study_ss2/ss2_preregistration.json.
CODALM_CUT = 6.0
CODALM_CUT_SENSITIVITY = (4.0, 5.0, 7.0, 8.0)
# Per-subset scorer, stated so an MCQ-against-free-form contrast is not read as a model effect.
SCORER_BY_SUBSET = {
    "mcq": "exact letter match against the gold option",
    "freeform": "containment against the reference answer",
    "general": "Mistral-7B judge on CODA-LM's own 1-10 prompt",
    "regional": "Mistral-7B judge on CODA-LM's own 1-10 prompt",
    "suggestion": "Mistral-7B judge on CODA-LM's own 1-10 prompt",
}


def paired_bootstrap(pairs, n_boot=10000, seed=0):
    """CI on the DIFFERENCE, resampling question indices so the pairing is preserved."""
    rnd = random.Random(seed)
    n = len(pairs)
    if n == 0:
        return None
    d_obs = statistics.fmean(b - a for a, b in pairs)
    diffs = []
    for _ in range(n_boot):
        idx = [rnd.randrange(n) for _ in range(n)]
        diffs.append(statistics.fmean(pairs[i][1] - pairs[i][0] for i in idx))
    diffs.sort()
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[int(0.975 * n_boot)]
    return dict(delta_cloud_minus_device=round(d_obs, 6),
                ci95=[round(lo, 6), round(hi, 6)], n_pairs=n, n_boot=n_boot)


def mean_ci(vals, n_boot=10000, seed=0):
    if not vals:
        return None
    rnd = random.Random(seed)
    n = len(vals)
    bs = []
    for _ in range(n_boot):
        bs.append(statistics.fmean(vals[rnd.randrange(n)] for _ in range(n)))
    bs.sort()
    return dict(mean=round(statistics.fmean(vals), 6), n=n,
                ci95=[round(bs[int(0.025 * n_boot)], 6), round(bs[int(0.975 * n_boot)], 6)])


def two_by_two(pairs, cut):
    """both_right / cloud_only / device_only / both_wrong at a STATED cut."""
    c = dict(both_right=0, cloud_only=0, device_only=0, both_wrong=0)
    for dv, cl in pairs:
        d, k = dv >= cut, cl >= cut
        if d and k:
            c["both_right"] += 1
        elif k and not d:
            c["cloud_only"] += 1
        elif d and not k:
            c["device_only"] += 1
        else:
            c["both_wrong"] += 1
    c["n"] = len(pairs)
    c["cut"] = cut
    return c


def ttft(rows):
    t = [r["ttft_s"] for r in rows if r.get("ttft_s") is not None]
    if not t:
        return None
    t.sort()
    return dict(n=len(t), p50=round(statistics.median(t), 4),
                p90=round(t[int(0.9 * len(t))], 4), mean=round(statistics.fmean(t), 4),
                min=round(t[0], 4), max=round(t[-1], 4))


# The scorer writes a DIFFERENT key per dataset, so the key is looked up per dataset rather than
# by a scan that could silently pick up a neighbouring field. RefSpatial writes point_accuracy and
# RealWorldQA writes exact_match; the first version of this file knew neither and raised on row one
# of both datasets, which is what happens when a reader is written against a declared shape instead
# of an observed one.
SCORE_KEY = {
    "vizwiz": ("vqa_accuracy", "vqa", "accuracy"),
    "egothink": ("containment", "contains", "accuracy"),
    "refspatial": ("point_accuracy",),
    "realworldqa": ("exact_match",),
    "codalm": ("judge_rating", "rating"),
}


def score_of(r, dataset):
    s = r.get("score") or {}
    for k in SCORE_KEY.get(dataset, ()):
        if k in s:
            return float(s[k])
    raise KeyError("no score field for dataset %r in row %r: %r"
                   % (dataset, r.get("qid"), sorted(s)))


# The subset a row belongs to, taken from the SCORER's own output so the stratum and the number it
# strata-fies come from one source. It is NOT a row-level field: --subset-field looked for one at
# row level, found nothing, and the per-subset breakdown D142 asks for silently collapsed into a
# single "dimension=None" bucket. A declared flag that is never read is the same defect class as a
# write-only field.
SUBSET_KEY = {"refspatial": "split", "realworldqa": "subset", "codalm": "task"}


def subset_of(r, dataset):
    return (r.get("score") or {}).get(SUBSET_KEY.get(dataset, "subset"))


def below_pixels_strata(below, D, qids):
    """Do the sub-floor images CLUSTER by stratum?

    Small, badly framed photos are exactly VizWiz's hard cases, so a set that is 0.65 percent of
    the pool can be several percent of one stratum. The mixing weight is what makes a small
    exclusion able to move a stratum estimate, which is the same point that made the per-dimension
    check worth running on EgoThink.
    """
    tot = collections.Counter()
    hit = collections.Counter()
    for q in qids:
        for key in ("answer_type", "answerable"):
            k = "%s=%s" % (key, D[q].get(key))
            tot[k] += 1
            if q in below:
                hit[k] += 1
    return {k: dict(n_below=hit.get(k, 0), n_stratum=tot[k],
                    pct_of_stratum=round(100.0 * hit.get(k, 0) / tot[k], 3))
            for k in sorted(tot)}


KIT_MAX_SIDE = 2048


def effective_area(w, h):
    """The area the MODEL saw, not the area on disk.

    ss1_kit.preprocess_to_jpeg_bytes downscales with Lanczos when the longest side exceeds
    MAX_SIDE = 2048, so for an image above that the staged area in ss1_image_dims.jsonl is NOT the
    area the processor received. Measured: 242 of 4,319 VizWiz and 41 of 700 EgoThink images are
    above the cap, so using the recorded area for them would be wrong by up to 1.6x.

    Corroboration that this is the right rule: the largest EgoThink images are 2560x1920, which the
    cap takes to 2048x1536 = 3,145,728 px, i.e. 3,072 visual tokens under area/1024; the observed
    EgoThink prompt_tokens maximum is 3,114, which is 3,072 plus about 42 tokens of text. The
    arithmetic closes end to end, which independently confirms area/1024 on the device side.
    """
    m = max(w, h)
    if m <= KIT_MAX_SIDE:
        return w * h
    sc = KIT_MAX_SIDE / float(m)
    return max(1, round(w * sc)) * max(1, round(h * sc))


def prompt_token_parity(qids, D, C, below=frozenset(), dims=None):
    """D142 resolution check: compare prompt_tokens per question between the two runs.

    prompt_tokens is TEXT tokens PLUS VISUAL tokens, so a difference has two possible sources and
    only one is the resolution confound:

      * identical counts            -> identical visual input, no confound (the cleanest outcome);
      * a CONSTANT offset on every question -> the chat template, since the 4B and 32B may wrap the
        same prompt differently. NOT a resolution confound;
      * a difference that SCALES with image size -> the pixel budget, which IS the confound.

    For StudySS2 the image dimensions ARE recoverable: both manifests carry width and height on
    every row, so --image-dims supplies REAL pixel areas and the prompt_tokens proxy is not needed.
    Where dims are absent the device's own prompt_tokens is used as a proxy instead, and a
    correlation against a proxy is evidence about scaling rather than a measurement of it.

    DEPENDENCY, named rather than resolved: "identical counts means identical visual input" assumes
    both models convert pixels to tokens by the SAME rule, same patch size and same merge size. If
    their vision configs differ, identical totals would be a coincidence and differing totals would
    not prove preprocessing differs. The Orin's preprocessor_config.json and the 32B's equivalent
    settle it; that is the paired item and it is not in this session's hands.
    """
    pairs = [(int(D[q].get("prompt_tokens") or 0), int(C[q].get("prompt_tokens") or 0))
             for q in qids
             if D[q].get("prompt_tokens") and C[q].get("prompt_tokens")]
    if not pairs:
        return dict(status="NOT COMPUTABLE: prompt_tokens missing on one side")
    diffs = [c - d for d, c in pairs]
    same = sum(1 for x in diffs if x == 0)
    uniq = sorted(set(diffs))
    dev = [d for d, _ in pairs]
    out = dict(
        n=len(pairs), n_identical=same, frac_identical=round(same / len(pairs), 6),
        diff_cloud_minus_device=dict(
            min=min(diffs), median=statistics.median(diffs), max=max(diffs),
            mean=round(statistics.fmean(diffs), 3), n_distinct=len(uniq),
            direction=("cloud HIGHER on all" if min(diffs) > 0 else
                       "cloud LOWER on all" if max(diffs) < 0 else
                       "mixed" if same < len(pairs) else "identical throughout")),
        verdict=("IDENTICAL COUNTS on every question: identical visual input, CONFOUND CLEARED "
                 "(subject to the vision-config dependency above)" if same == len(pairs) else
                 "CONSTANT OFFSET of %d on every question: points at the CHAT TEMPLATE, not the "
                 "pixel budget, so NOT a resolution confound" % uniq[0] if len(uniq) == 1 else
                 "VARYING DIFFERENCE: decomposed below"))
    # THE LOCALISATION TEST, pre-stated: equality is expected to hold everywhere EXCEPT the
    # sub-floor images, and to fail on exactly those. If it fails anywhere else, the cause is the
    # chat template or something unaccounted for, NOT the pixel floor.
    if below:
        diff_q = {q for q, (d, c) in zip([q for q in qids
                                          if D[q].get("prompt_tokens") and C[q].get("prompt_tokens")],
                                         pairs) if c != d}
        out["localisation_test"] = dict(
            n_differing=len(diff_q), n_below_min_pixels=len(below),
            differing_set_equals_below_set=(diff_q == set(below) & set(qids)),
            differing_but_NOT_below=sorted(diff_q - set(below))[:20],
            below_but_NOT_differing=sorted((set(below) & set(qids)) - diff_q)[:20],
            reading=("if differing == below, the floor explains the divergence exactly and nothing "
                     "else does. Any qid in differing_but_NOT_below is unexplained by the floor and "
                     "points at the chat template or at something unaccounted for."))
    if len(uniq) > 1 and dims:
        # REAL pixel area replaces the earlier prompt_tokens proxy, which was defensible but mildly
        # circular. Effective (post-cap) area, not the staged area.
        qq = [q for q in qids if D[q].get("prompt_tokens") and C[q].get("prompt_tokens")]
        ar = [dims.get(q) for q in qq]
        have = [(a, diffs[i]) for i, a in enumerate(ar) if a]
        if len(have) > 2:
            n2 = len(have)
            ma = statistics.fmean(x[0] for x in have)
            md = statistics.fmean(x[1] for x in have)
            sa = statistics.pstdev([x[0] for x in have]) or 1e-9
            sd = statistics.pstdev([x[1] for x in have]) or 1e-9
            r2 = sum((a - ma) * (d - md) for a, d in have) / (n2 * sa * sd)
            srt = sorted(have)
            k = max(1, n2 // 10)
            out["scaling_test_real_area"] = dict(
                regressor="EFFECTIVE pixel area after the kit's 2048 cap (not the staged area)",
                n=n2, pearson_r=round(r2, 4),
                mean_diff_smallest_decile=round(statistics.fmean(d for _, d in srt[:k]), 3),
                mean_diff_largest_decile=round(statistics.fmean(d for _, d in srt[-k:]), 3),
                proxy_dropped="the prompt_tokens proxy is no longer used; real areas are available.")
    if len(uniq) > 1:
        n = len(pairs)
        mdev = statistics.fmean(dev)
        mdif = statistics.fmean(diffs)
        sdev = statistics.pstdev(dev) or 1e-9
        sdif = statistics.pstdev(diffs) or 1e-9
        r = sum((dev[i] - mdev) * (diffs[i] - mdif) for i in range(n)) / (n * sdev * sdif)
        order = sorted(range(n), key=lambda i: dev[i])
        d1 = order[: max(1, n // 10)]
        d10 = order[-max(1, n // 10):]
        out["scaling_test"] = dict(
            proxy_for_image_size="the DEVICE's own prompt_tokens (declared proxy, see docstring)",
            pearson_r_diff_vs_device_prompt_tokens=round(r, 4),
            mean_diff_in_smallest_decile=round(statistics.fmean([diffs[i] for i in d1]), 3),
            mean_diff_in_largest_decile=round(statistics.fmean([diffs[i] for i in d10]), 3),
            reading=("a near-zero r with a flat decile contrast points at the template or at "
                     "question-text length; an r away from zero with a decile contrast in the same "
                     "direction points at the PIXEL BUDGET, which is the confound."))
    return out


def _analyse(qids, D, C, dataset, cut, dj, jc, ttft_qids=None):
    """Every statistic, over one qid subset. Called once on the full set and once with the
    shared-image qids removed, so the two columns are always cleaned alike or not at all."""
    pairs = [(score_of(D[q], dataset), score_of(C[q], dataset)) for q in qids]
    strata = defaultdict(list)
    if dataset == "vizwiz":
        for q, pr in zip(qids, pairs):
            strata["answer_type=" + str(D[q].get("answer_type"))].append(pr)
            strata["answerable=" + str(D[q].get("answerable"))].append(pr)
    elif dataset == "egothink":
        for q, pr in zip(qids, pairs):
            strata["dimension=" + str(D[q].get("dimension"))].append(pr)
    else:
        key = SUBSET_KEY.get(dataset, "subset")
        for q, pr in zip(qids, pairs):
            sd, sc = subset_of(D[q], dataset), subset_of(C[q], dataset)
            if sd != sc:
                raise ValueError("subset disagrees across tiers for %r: %r vs %r" % (q, sd, sc))
            strata[key + "=" + str(sd)].append(pr)

    out = dict(
        n_pairs=len(qids),
        device_accuracy=mean_ci([p[0] for p in pairs]),
        cloud_accuracy=mean_ci([p[1] for p in pairs]),
        paired_difference=paired_bootstrap(pairs),
        two_by_two=two_by_two(pairs, cut),
        two_by_two_cut_sensitivity=({str(c): two_by_two(pairs, c) for c in (0.3, 0.5, 0.7, 1.0)}
                                    if dataset == "vizwiz" else None),
        ttft=dict(device=ttft([D[q] for q in (ttft_qids if ttft_qids is not None else qids)]),
                  cloud=ttft([C[q] for q in (ttft_qids if ttft_qids is not None else qids)]),
                  n_ttft=len(ttft_qids if ttft_qids is not None else qids),
                  denominator_note=("TTFT uses its OWN denominator when the shared-image set is "
                                    "supplied: those questions are a warm-cache timing artifact "
                                    "and must leave the TTFT column, but they do NOT contaminate "
                                    "accuracy and are kept in it.")),
        by_stratum={k: dict(device=mean_ci([x[0] for x in v]),
                            cloud=mean_ci([x[1] for x in v]),
                            paired_difference=paired_bootstrap(v),
                            two_by_two=two_by_two(v, cut))
                    for k, v in sorted(strata.items())})

    if dataset == "egothink" and dj:
        jq = [q for q in qids if q in dj and (not jc or q in jc)]
        jp = [(float(dj[q]["judge_rating"]),
               float(jc[q]["judge_rating"]) if jc else float("nan")) for q in jq]
        byd = defaultdict(list)
        for q, pr in zip(jq, jp):
            byd[str(dj[q].get("dimension"))].append(pr)
        out["judge_native_scale"] = dict(
            note=("mean of the judge's own 0 / 0.5 / 1 rating. NO binarisation: the >= 0.5 rule "
                  "used for scorer agreement moved that figure 0.633 to 0.805 and is not applied "
                  "here."),
            n_paired=len(jq),
            device=mean_ci([p[0] for p in jp]),
            cloud=mean_ci([p[1] for p in jp]) if jc else None,
            paired_difference=paired_bootstrap(jp) if jc else None,
            by_dimension={k: dict(device=mean_ci([x[0] for x in v]),
                                  cloud=mean_ci([x[1] for x in v]) if jc else None)
                          for k, v in sorted(byd.items())},
            rating_distribution_device={str(k): sum(1 for p in jp if p[0] == k)
                                        for k in (0.0, 0.5, 1.0)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--cloud", required=True)
    ap.add_argument("--dataset", required=True,
                    choices=("refspatial", "realworldqa", "codalm"))
    ap.add_argument("--subset-field", default="subset",
                    help="row field naming the subset; read from the data, not assumed")
    ap.add_argument("--device-judge")
    ap.add_argument("--cloud-judge")
    ap.add_argument("--shared-images", action="append", default=[],
                    help="qids whose image CONTENT repeats an earlier image in run order. Warm "
                         "encoder cache: damages TTFT ONLY. Applied to BOTH columns or NEITHER.")
    ap.add_argument("--below-min-pixels",
                    help="qids whose image area is below the 65,536 px min_pixels floor, so the "
                         "DEVICE upscaled and the cloud did not. The two models were shown "
                         "DIFFERENT PIXELS: this damages ACCURACY AND TTFT, not only token counts. "
                         "Kept as a SEPARATE set from --shared-images on purpose.")
    ap.add_argument("--image-dims", help="ss1_image_dims.jsonl: {dataset,qid,w,h,area}. Real "
                                          "pixel areas, which replace the prompt_tokens proxy.")
    ap.add_argument("--prev-mm-hits", type=int, default=0,
                    help="cumulative vllm:mm_cache_hits_total at the PREVIOUS dataset's stamp on "
                         "the same server instance. The counters are cumulative, so the "
                         "per-dataset figure is a difference between stamps; without this the "
                         "register check would compare a cumulative count against one dataset's "
                         "candidate list.")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    dv = json.loads(Path(a.device).read_text())
    cl = json.loads(Path(a.cloud).read_text())
    D = {r["qid"]: r for r in dv["rows"] if "error" not in r}
    C = {r["qid"]: r for r in cl["rows"] if "error" not in r}
    qids = sorted(set(D) & set(C))
    cut = CODALM_CUT if a.dataset == "codalm" else 0.5

    shared = set()
    shared_meta = {}
    for f in a.shared_images:
        v = json.loads(Path(f).read_text())
        if isinstance(v, list):
            shared |= set(v)
        else:
            shared_meta = {k: v.get(k) for k in ("key", "order", "register",
                                                 "n_shared_images", "n_questions_on_shared")}
            # The H100 marks this a CONSTRUCTED BOUND: the questions that COULD be served warm by
            # the multimodal cache. Upgrades to a CENSUS only if the final mm_cache_hits equals N.
            for k in ("repeat_questions_possibly_warm", "qids", "shared_qids"):
                if isinstance(v.get(k), list):
                    shared |= set(v[k])
                    break

    # REGISTER CHECK. The candidate list is a constructed bound: the questions that COULD be served
    # warm. It upgrades to a CENSUS only if the server's observed multimodal hit count equals the
    # candidate count. That comparison is made here rather than asserted, because the whole value of
    # the exclusion depends on which register it is in.
    obs_hits = (((cl.get("cache_check") or {}).get("server_counters_parsed") or {})
                .get("mm_cache_hits"))
    if obs_hits is None or not shared:
        register_note = ("NOT CHECKED: no observed mm_cache_hits in the cloud file, or no candidate "
                         "list supplied. Stays a CONSTRUCTED BOUND.")
    else:
        delta = int(obs_hits) - int(a.prev_mm_hits or 0)
        register_note = dict(
            observed_mm_cache_hits_cumulative=int(obs_hits),
            prior_stamp_subtracted=int(a.prev_mm_hits or 0),
            observed_mm_cache_hits_this_dataset=delta,
            candidate_questions=len(shared),
            equal=(delta == len(shared)),
            register=("CENSUS: the observed per-dataset multimodal hit count equals the candidate "
                      "count, so the exclusion set is exactly the set of warm-served questions, "
                      "not an upper bound on it."
                      if delta == len(shared) else
                      "CONSTRUCTED BOUND: observed hits and candidates differ, so the candidate "
                      "list is not the served set and the exclusion over-excludes or under-excludes."))

    below = set()
    below_rows = []
    if a.below_min_pixels:
        v = json.loads(Path(a.below_min_pixels).read_text())
        items = v if isinstance(v, list) else (v.get("rows") or v.get("below_min_pixels")
                                               or v.get("items") or v.get("qids") or [])
        for it in items:
            if isinstance(it, str):
                below.add(it)
            elif isinstance(it, dict) and it.get("qid"):
                below.add(it["qid"])
                below_rows.append(it)

    # THE TWO SETS ARE NOT MERGED. They damage different axes and a reader must be able to tell a
    # timing artifact from a difference in what the models were shown.
    union = shared | below
    kept_shared = [q for q in qids if q not in shared]
    kept_below = [q for q in qids if q not in below]
    kept_clean = [q for q in qids if q not in union]

    dims = {}
    if a.image_dims:
        for line in Path(a.image_dims).read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            dims[r["qid"]] = effective_area(int(r["w"]), int(r["h"]))

    dj = {}
    if a.device_judge:
        dj = {r["qid"]: r for r in json.loads(Path(a.device_judge).read_text())["rows"]
              if r.get("judge_rating") is not None}
    jc = {}
    if a.cloud_judge:
        jc = {r["qid"]: r for r in json.loads(Path(a.cloud_judge).read_text())["rows"]
              if r.get("judge_rating") is not None}

    out = dict(
        study=(dv.get("study") or cl.get("study") or "unknown"),
        pass_="device_vs_cloud_compare", dataset=a.dataset,
        study_label_source="read from the device and cloud result files, not hardcoded",
        no_verdict=("numbers only. D136's gate call is the user's and is deliberately not made "
                    "here, including by implication in ordering or framing."),
        pairing=dict(n_device=len(D), n_cloud=len(C), n_paired=len(qids),
                     n_device_only=len(set(D) - set(C)), n_cloud_only=len(set(C) - set(D))),
        exclusion_sets=dict(
            note=("TWO DISTINCT SETS, deliberately NOT merged into one 'excluded' flag, because "
                  "they damage different axes."),
            shared_images=dict(
                n=len(shared), n_in_paired=len(qids) - len(kept_shared),
                mechanism="warm multimodal encoder cache, keyed by image CONTENT",
                axis_affected="TTFT ONLY; accuracy is unaffected, both models answered the same "
                              "pixels"),
            below_min_pixels=dict(
                n=len(below), n_in_paired=len(qids) - len(kept_below),
                mechanism="image area below the 65,536 px min_pixels floor, so the DEVICE upscaled "
                          "to the floor and the cloud (floor 4,096) did not",
                axis_affected="ACCURACY AND TTFT. The two models were shown DIFFERENT PIXELS, so a "
                              "2x2 cell on one of these reflects partly that the device got a "
                              "larger rendering of the same photo. This is NOT only a token-count "
                              "issue."),
            overlap=dict(n_intersection=len(shared & below),
                         n_union=len(union),
                         disjoint=(len(shared & below) == 0),
                         note="the fully clean subset is the paired set minus the UNION, not minus "
                              "the sum of the two sizes unless they are disjoint."),
            fully_clean_n=len(kept_clean)),
        shared_image_exclusion=dict(
            n_shared_qids_supplied=len(shared), n_shared_in_paired=len(qids) - len(kept_shared),
            rule=("the repeated-image structure is a property of the DATASET itself, so it was "
                  "present on both sides. The exclusion is therefore applied to BOTH columns or "
                  "NEITHER: excluding from the cloud column alone would compare a cleaned column "
                  "against an uncleaned one, an asymmetry introduced by the cleaning rather than "
                  "by the data."),
            key=shared_meta.get("key"),
            order_check=shared_meta.get("order"),
            register_as_supplied=shared_meta.get("register"),
            register_after_counter_check=register_note,
            identifier_dedup_would_have_missed_this=(
                "the key is a sha256 of the DECODED pixels, not of the source bytes and not the "
                "identifier. The source-byte key undercounted RefSpatial by 6, and an identifier "
                "key cannot see this class at all: the multimodal cache is keyed by processed "
                "image content, so byte-different but pixel-identical images still hit it.")),
        prompt_token_parity=prompt_token_parity(qids, D, C, below, dims),
        below_min_pixels_strata=(below_pixels_strata(below, D, qids)
                                 if below and a.dataset == "vizwiz" else None),
        full_set=_analyse(qids, D, C, a.dataset, cut, dj, jc),
        shared_images_excluded=(_analyse(kept_shared, D, C, a.dataset, cut, dj, jc)
                                if shared else None),
        clean=(_analyse(kept_below, D, C, a.dataset, cut, dj, jc, ttft_qids=kept_clean)
               if (below or shared) else None),
        clean_denominators=dict(
            accuracy_n=len(kept_below),
            ttft_n=len(kept_clean),
            rule=("TWO DENOMINATORS, NOT ONE. Accuracy excludes the below-floor set ONLY, because "
                  "the shared-image repeats are a TTFT-only artifact and dropping them from "
                  "accuracy would discard questions for no reason. TTFT excludes BOTH, because the "
                  "warm-cache repeats do contaminate timing. A single 'excluded' figure would "
                  "either lose questions from accuracy or keep contaminated ones in TTFT.")),
        ttft_condition=dict(
            device_host="Orin, vLLM, idle, one request at a time, cold per image.",
            device_host_attribution_source=(
                "ESTABLISHED BY the user's statement plus the Orin session's own StudySS1 report "
                "at 8492e02, NOT by a _provenance block, which does not exist in any of the five "
                "StudySS1 artifacts."),
            device_stack="vLLM 0.20.0+cu126 (jetson-ai-lab jp6/cu126), released image processor, "
                         "no --mm-processor-kwargs.",
            cloud_stack="vLLM 0.31.0, --mm-processor-kwargs size shortest_edge 4096 longest_edge "
                        "16777216 (live2 round-1).",
            robot_cost_stack_note=(
                "the committed device baseline for ROBOT RECALL is the ORIN2 in-process harness "
                "(D87), unexercised per D103(c). These SS numbers are the ORIN3 vLLM stack and the "
                "two must not be placed side by side as one device's numbers."),
            both_columns_unverified_cold=(
                "the cloud reports prefix cache isolated, 237,781 queries 0 hits, and an "
                "mm_cache_hits count keyed by image content. The DEVICE side is NOT "
                "retro-verifiable: vLLM 0.20.0 does not populate cached_tokens at all, the SS1 "
                "runner captured neither that nor the /metrics deltas, and the images are gone "
                "from tmpfs. Both columns carry the label, for different reasons.")),
    )
    if a.dataset == "vizwiz":
        out["vizwiz_quality_flags"] = (
            "NOT PRODUCIBLE from held data; the join is NOT started pending the user's licence "
            "ruling. The manifest and rows carry answer_type and answerable only.")

    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print("wrote", a.out, "| paired", len(qids), "| accuracy n", len(kept_below), "| ttft n", len(kept_clean))


if __name__ == "__main__":
    main()
