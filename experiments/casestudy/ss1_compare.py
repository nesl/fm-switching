"""StudySS1 compare: device 4B against cloud 32B, paired on the same questions.

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
from collections import defaultdict
from pathlib import Path

# VizWiz VQA accuracy is graded in [0,1], so a 2x2 needs a cut. It is STATED rather than implied,
# and the sensitivity is reported beside it, because a threshold nobody registered moved a headline
# agreement figure 17 points earlier in this study.
VQA_RIGHT_CUT = 0.5


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


def score_of(r, dataset):
    s = r.get("score") or {}
    if dataset == "vizwiz":
        for k in ("vqa_accuracy", "vqa", "accuracy"):
            if k in s:
                return float(s[k])
    for k in ("containment", "contains", "accuracy"):
        if k in s:
            return float(s[k])
    raise KeyError("no score field in row %r: %r" % (r.get("qid"), sorted(s)))


def _analyse(qids, D, C, dataset, cut, dj, jc):
    """Every statistic, over one qid subset. Called once on the full set and once with the
    shared-image qids removed, so the two columns are always cleaned alike or not at all."""
    pairs = [(score_of(D[q], dataset), score_of(C[q], dataset)) for q in qids]
    strata = defaultdict(list)
    if dataset == "vizwiz":
        for q, pr in zip(qids, pairs):
            strata["answer_type=" + str(D[q].get("answer_type"))].append(pr)
            strata["answerable=" + str(D[q].get("answerable"))].append(pr)
    else:
        for q, pr in zip(qids, pairs):
            strata["dimension=" + str(D[q].get("dimension"))].append(pr)

    out = dict(
        n_pairs=len(qids),
        device_accuracy=mean_ci([p[0] for p in pairs]),
        cloud_accuracy=mean_ci([p[1] for p in pairs]),
        paired_difference=paired_bootstrap(pairs),
        two_by_two=two_by_two(pairs, cut),
        two_by_two_cut_sensitivity=({str(c): two_by_two(pairs, c) for c in (0.3, 0.5, 0.7, 1.0)}
                                    if dataset == "vizwiz" else None),
        ttft=dict(device=ttft([D[q] for q in qids]), cloud=ttft([C[q] for q in qids])),
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
    ap.add_argument("--dataset", required=True, choices=("vizwiz", "egothink"))
    ap.add_argument("--device-judge")
    ap.add_argument("--cloud-judge")
    ap.add_argument("--shared-images", action="append", default=[],
                    help="JSON list of qids whose image CONTENT repeats an earlier image in run "
                         "order. Applied to BOTH columns or NEITHER.")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    dv = json.loads(Path(a.device).read_text())
    cl = json.loads(Path(a.cloud).read_text())
    D = {r["qid"]: r for r in dv["rows"] if "error" not in r}
    C = {r["qid"]: r for r in cl["rows"] if "error" not in r}
    qids = sorted(set(D) & set(C))
    cut = VQA_RIGHT_CUT if a.dataset == "vizwiz" else 0.5

    shared = set()
    for f in a.shared_images:
        v = json.loads(Path(f).read_text())
        shared |= set(v if isinstance(v, list) else v.get("qids", []))
    kept = [q for q in qids if q not in shared]

    dj = {}
    if a.device_judge:
        dj = {r["qid"]: r for r in json.loads(Path(a.device_judge).read_text())["rows"]
              if r.get("judge_rating") is not None}
    jc = {}
    if a.cloud_judge:
        jc = {r["qid"]: r for r in json.loads(Path(a.cloud_judge).read_text())["rows"]
              if r.get("judge_rating") is not None}

    out = dict(
        study="StudySS1", pass_="device_vs_cloud_compare", dataset=a.dataset,
        no_verdict=("numbers only. D136's gate call is the user's and is deliberately not made "
                    "here, including by implication in ordering or framing."),
        pairing=dict(n_device=len(D), n_cloud=len(C), n_paired=len(qids),
                     n_device_only=len(set(D) - set(C)), n_cloud_only=len(set(C) - set(D))),
        shared_image_exclusion=dict(
            n_shared_qids_supplied=len(shared), n_shared_in_paired=len(qids) - len(kept),
            rule=("the duplicate-photo structure is a property of VIZWIZ VAL ITSELF, 34 groups of "
                  "byte-identical photos under different filenames, so it was present on BOTH "
                  "sides. The exclusion is therefore applied to BOTH columns or NEITHER: "
                  "excluding from the cloud column alone would compare a cleaned column against an "
                  "uncleaned one, an asymmetry introduced by the cleaning rather than by the data."),
            order_check=("the device ran in EXACT manifest order for both datasets, verified: "
                         "manifest qid sequence == device row sequence, 4,319 of 4,319 for VizWiz "
                         "and 700 of 700 for EgoThink. 'Repeats an image seen earlier' depends on "
                         "order, so if the cloud also ran manifest order the candidate set is the "
                         "SAME 52 and the matched exclusion is exact rather than a union. The "
                         "cloud's order must be confirmed from its run meta."),
            identifier_dedup_would_have_missed_this=(
                "by image ID VizWiz val is 4,319 unique on 4,319 and passes clean. The duplicates "
                "are in file CONTENT under different filenames, and a cache keyed by content does "
                "not care what the identifier says. Identifier-based deduplication cannot see this "
                "class at all; the stronger form, hashing file contents, is what found it.")),
        full_set=_analyse(qids, D, C, a.dataset, cut, dj, jc),
        shared_images_excluded=(_analyse(kept, D, C, a.dataset, cut, dj, jc) if shared else None),
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
    print("wrote", a.out, "| paired", len(qids), "| shared excluded", len(qids) - len(kept))


if __name__ == "__main__":
    main()
