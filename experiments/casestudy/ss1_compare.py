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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--cloud", required=True)
    ap.add_argument("--dataset", required=True, choices=("vizwiz", "egothink"))
    ap.add_argument("--device-judge")
    ap.add_argument("--cloud-judge")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    dv = json.loads(Path(a.device).read_text())
    cl = json.loads(Path(a.cloud).read_text())
    D = {r["qid"]: r for r in dv["rows"] if "error" not in r}
    C = {r["qid"]: r for r in cl["rows"] if "error" not in r}
    qids = sorted(set(D) & set(C))

    pairs = [(score_of(D[q], a.dataset), score_of(C[q], a.dataset)) for q in qids]
    cut = VQA_RIGHT_CUT if a.dataset == "vizwiz" else 0.5

    out = dict(
        study="StudySS1", pass_="device_vs_cloud_compare", dataset=a.dataset,
        no_verdict=("numbers only. D136's gate call is the user's and is deliberately not made "
                    "here, including by implication."),
        pairing=dict(n_device=len(D), n_cloud=len(C), n_paired=len(qids),
                     n_device_only=len(set(D) - set(C)), n_cloud_only=len(set(C) - set(D))),
        device_accuracy=mean_ci([p[0] for p in pairs]),
        cloud_accuracy=mean_ci([p[1] for p in pairs]),
        paired_difference=paired_bootstrap(pairs),
        two_by_two=two_by_two(pairs, cut),
        two_by_two_cut_sensitivity={str(c): two_by_two(pairs, c) for c in (0.3, 0.5, 0.7, 1.0)}
        if a.dataset == "vizwiz" else None,
        ttft=dict(device=ttft([D[q] for q in qids]), cloud=ttft([C[q] for q in qids]),
                  device_path_and_load=dv.get("caching"), device_decoding=dv.get("decoding"),
                  cloud_path_and_load=cl.get("caching"), cloud_decoding=cl.get("decoding"),
                  device_host="Orin, vLLM, idle, one request at a time.",
                  device_host_attribution_source=(
                      "ESTABLISHED BY the user's statement plus the Orin session's own StudySS1 "
                      "report at 8492e02, NOT by a _provenance block, which does not exist in any "
                      "of the five StudySS1 artifacts. Recorded because a later reader checking "
                      "the convention will find the block missing and otherwise have no way back "
                      "to the attribution."),
                  device_stack=(
                      "ORIN3 vLLM server on the Orin's localhost:8000, cold per image. NOTE THE "
                      "STACK: the committed device baseline for robot recall is the ORIN2 "
                      "IN-PROCESS harness (D87 fixes robot device recall cost to it and calls the "
                      "server path an API artifact; D94 records the ORIN3 vLLM numbers as a "
                      "serving-stack sensitivity result rather than the device baseline). So this "
                      "TTFT is measured on a DIFFERENT stack from the committed robot device cost "
                      "and the two must not be placed side by side as one device's numbers."),
                  resend_path_not_applicable=(
                      "the D61 / D94 re-send concern does not apply: single-image requests carry "
                      "no history, so there is no history to re-send."),
                  cloud_condition_to_state_the_same_way=(
                      "the 32B side must state path, concurrency and what was cached before "
                      "measurement in the same phrase form, so the two conditions are comparable "
                      "on their face rather than by inference (CLAUDE.md treats caching as a "
                      "methodological parameter).")),
    )

    strata = defaultdict(list)
    if a.dataset == "vizwiz":
        for q, p in zip(qids, pairs):
            strata["answer_type=" + str(D[q].get("answer_type"))].append(p)
            strata["answerable=" + str(D[q].get("answerable"))].append(p)
        out["vizwiz_quality_flags"] = (
            "NOT PRODUCIBLE from held data. The manifest and rows carry answer_type and answerable "
            "only; blur / framing / obstruction flags come from a separate VizWiz release that is "
            "not present locally. Reported as a gap rather than acquired, per CLAUDE.md on new "
            "datasets.")
    else:
        for q, p in zip(qids, pairs):
            strata["dimension=" + str(D[q].get("dimension"))].append(p)

    out["by_stratum"] = {
        k: dict(device=mean_ci([x[0] for x in v]), cloud=mean_ci([x[1] for x in v]),
                paired_difference=paired_bootstrap(v), two_by_two=two_by_two(v, cut))
        for k, v in sorted(strata.items())}

    # EgoThink: the judge on its NATIVE scale, no binarisation, device and cloud side by side
    if a.dataset == "egothink" and a.device_judge:
        jd = {r["qid"]: r for r in json.loads(Path(a.device_judge).read_text())["rows"]
              if r.get("judge_rating") is not None}
        jc = {}
        if a.cloud_judge:
            jc = {r["qid"]: r for r in json.loads(Path(a.cloud_judge).read_text())["rows"]
                  if r.get("judge_rating") is not None}
        jq = sorted(set(jd) & (set(jc) if jc else set(jd)))
        jp = [(float(jd[q]["judge_rating"]),
               float(jc[q]["judge_rating"]) if jc else float("nan")) for q in jq]
        byd = defaultdict(list)
        for q, p in zip(jq, jp):
            byd[str(jd[q].get("dimension"))].append(p)
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

    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print("wrote", a.out, "| paired", len(qids))


if __name__ == "__main__":
    main()
