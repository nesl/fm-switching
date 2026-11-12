#!/usr/bin/env python3
"""StudyE10a-full analysis (CPU). Per cell (K3, K1): JPEG q88 rows vs R1's committed batched PNG rows on the same
question: accuracy each, paired difference JPEG - PNG with a video bootstrap (2,000, seed 0), letter agreement,
prompt-token parity, unparsed, data-URL size. Verdict by the pre-registered rule: acceptable iff for EACH of K3 and K1
the 95 % CI of the paired accuracy difference lies inside [-2, +2] pp. Writes e10a_full_results.json."""
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_e10"
NB, SEED, BAND = 2000, 0, 0.02


def video_boot(pairs, rng):
    by = defaultdict(list)
    for v, x in pairs:
        by[v].append(x)
    vids = sorted(by)
    est = float(np.mean([x for v in vids for x in by[v]]))
    bs = []
    for _ in range(NB):
        pick = rng.integers(0, len(vids), len(vids))
        bs.append(np.mean([x for i in pick for x in by[vids[i]]]))
    return dict(n=sum(len(by[v]) for v in vids), videos=len(vids), est=est,
                ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])


def main():
    rng = np.random.default_rng(SEED)
    rows = [json.loads(l) for l in open(OUT / "e10a_full_requests_h100nvl.jsonl")]
    r1 = {(r["cell"], r["question_id"]): r for r in map(json.loads, gzip.open(
        REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "rt")) if r["mode"] == "batched" and not r["error"]}
    sizes = json.load(open(OUT / "e10a_sizes.json"))["sember"]["request_bytes"]
    res = dict(label="StudyE10a-full: JPEG q88 vs PNG on all 845 S-EMBER questions, 32B-I K3 / K1 (H100 GPU 2, "
                     "vLLM 0.31.0, batched, prefix caching off, processor cache 0)", cells={})
    ok_all = True
    for cell in ("K3", "K1"):
        rs = [r for r in rows if r["cell"] == cell]
        ok = {r["question_id"]: r for r in rs if not r["error"]}
        q = sorted(set(ok) & {k[1] for k in r1 if k[0] == cell})
        J, P = [ok[x] for x in q], [r1[(cell, x)] for x in q]
        diff = video_boot([(j["video_id"], float(bool(j["correct"])) - float(bool(p["correct"]))) for j, p in zip(J, P)], rng)
        inside = -BAND <= diff["ci"][0] and diff["ci"][1] <= BAND
        ok_all &= inside
        flips = Counter(("png_right" if p["correct"] and not j["correct"] else "jpeg_right" if j["correct"] and not p["correct"]
                         else "both_wrong") for j, p in zip(J, P) if j["pred"] != p["pred"])
        res["cells"][cell] = dict(
            n=len(q), rows=len(rs), error_rows=sum(bool(r["error"]) for r in rs), retried=sum(1 for r in rs if (r.get("attempts") or 1) > 1),
            still_failed=len({r["question_id"] for r in rs} - set(ok)),
            prompt_tokens_match_r1=sum(bool(ok[x]["prompt_tokens_match"]) for x in q),
            r1_prompt_tokens_match=sum(P[i]["prompt_tokens"] == J[i]["prompt_tokens"] for i in range(len(q))),
            cached_nonzero=sum(bool(ok[x]["cached_tokens"]) for x in q),
            unparsed_jpeg=sum(ok[x]["pred"] in (None, "X") for x in q), unparsed_png=sum(p["pred"] in (None, "X") for p in P),
            acc_png_r1=float(np.mean([bool(p["correct"]) for p in P])), acc_jpeg=float(np.mean([bool(j["correct"]) for j in J])),
            acc_png_r1_video_ci=video_boot([(p["video_id"], float(bool(p["correct"]))) for p in P], rng)["ci"],
            acc_jpeg_video_ci=video_boot([(j["video_id"], float(bool(j["correct"]))) for j in J], rng)["ci"],
            jpeg_minus_png=diff, ci_inside_pm2pp=inside,
            letter_agreement=float(np.mean([j["pred"] == p["pred"] for j, p in zip(J, P)])),
            disagreements=sum(j["pred"] != p["pred"] for j, p in zip(J, P)), disagreement_kinds=dict(flips),
            by_category={c: dict(n=sum(1 for p in P if p["question_category"] == c),
                                 png=float(np.mean([bool(p["correct"]) for p in P if p["question_category"] == c])),
                                 jpeg=float(np.mean([bool(j["correct"]) for j, p in zip(J, P) if p["question_category"] == c])))
                         for c in sorted({p["question_category"] for p in P})},
            video_url_mb_median=float(np.median([ok[x]["video_url_chars"] for x in q]) / 1e6),
            png_request_mb_median_jobA=sizes["RECENT" if cell == "K3" else "RICH"]["png"]["median"] / 1e6,
            n_frames_median=float(np.median([ok[x]["n_frames"] for x in q])))
    res["e10a_subset_check"] = None
    try:
        sub = {r["question_id"]: r for r in map(json.loads, open(OUT / "e10a_sember_requests_h100nvl.jsonl")) if not r["error"]}
        k3 = {r["question_id"]: r for r in rows if r["cell"] == "K3" and not r["error"]}
        both = sorted(set(sub) & set(k3))
        res["e10a_subset_check"] = dict(n=len(both), same_letter=sum(sub[x]["pred"] == k3[x]["pred"] for x in both))
    except FileNotFoundError:
        pass
    res["verdict"] = dict(rule="JPEG acceptable for S-EMBER iff, for EACH of K3 and K1, the 95 % CI of the paired accuracy "
                               "difference (JPEG - PNG, video bootstrap 2,000, seed 0) lies inside [-2, +2] pp",
                          K3_inside=res["cells"]["K3"]["ci_inside_pm2pp"], K1_inside=res["cells"]["K1"]["ci_inside_pm2pp"],
                          acceptable=bool(ok_all))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e10a_full_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / "e10a_full_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["verdict"]))
    for c, v in res["cells"].items():
        print(c, v["n"], round(v["acc_png_r1"], 4), round(v["acc_jpeg"], 4), v["jpeg_minus_png"], v["letter_agreement"])


if __name__ == "__main__":
    main()
