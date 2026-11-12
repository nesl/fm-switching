#!/usr/bin/env python3
"""StudyE10a-jpeg Job B analysis (CPU; dashcam venv). Per model x N: Pearson / Spearman score correlation JPEG vs PNG,
AUROC and AP (PNG, JPEG, JPEG - PNG) with a paired clip bootstrap (2,000, seed 0), fraction abs(dscore) > 1, and the
same for PNG-resend vs committed D14 scores (determinism floor). S-EMBER: letter agreement with K3's committed
letters, paired accuracy difference (video bootstrap), token parity. Parity verdict by the pre-registered rule.
Writes results/cost/study_e10/e10a_results.json."""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_e10"
NB, SEED = 2000, 0


def boot_clip(clips, y, a, b, rng):
    """Paired clip bootstrap of AUROC / AP for scores a and b (same rows)."""
    uc = sorted(set(clips))
    idx = defaultdict(list)
    for i, c in enumerate(clips):
        idx[c].append(i)
    y, a, b = map(np.asarray, (y, a, b))
    out = {"auroc": [], "ap": []}
    for _ in range(NB):
        pick = rng.integers(0, len(uc), len(uc))
        ii = np.concatenate([idx[uc[j]] for j in pick])
        if len(set(y[ii])) < 2:
            continue
        for k, f in (("auroc", roc_auc_score), ("ap", average_precision_score)):
            out[k].append((f(y[ii], a[ii]), f(y[ii], b[ii]), f(y[ii], b[ii]) - f(y[ii], a[ii])))
    res = {}
    for k, f in (("auroc", roc_auc_score), ("ap", average_precision_score)):
        arr = np.array(out[k])
        res[k] = dict(png=float(f(y, a)), jpeg=float(f(y, b)), diff=float(f(y, b) - f(y, a)),
                      png_ci=[float(np.percentile(arr[:, 0], 2.5)), float(np.percentile(arr[:, 0], 97.5))],
                      jpeg_ci=[float(np.percentile(arr[:, 1], 2.5)), float(np.percentile(arr[:, 1], 97.5))],
                      diff_ci=[float(np.percentile(arr[:, 2], 2.5)), float(np.percentile(arr[:, 2], 97.5))],
                      n_boot=len(arr))
        res[k]["diff_ci_includes_0"] = res[k]["diff_ci"][0] <= 0 <= res[k]["diff_ci"][1]
    return res


def video_boot(pairs, rng):
    by = defaultdict(list)
    for v, x in pairs:
        by[v].append(x)
    vids = sorted(by)
    est = float(np.mean([x for v in vids for x in by[v]]))
    bs = [np.mean([x for i in rng.integers(0, len(vids), len(vids)) for x in by[vids[i]]]) for _ in range(NB)]
    return dict(n=sum(len(by[v]) for v in vids), est=est, ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])


def main():
    rng = np.random.default_rng(SEED)
    res = dict(label="StudyE10a-jpeg Job B: JPEG vs PNG parity (H100 GPU 2, vLLM 0.31.0, batched)")
    rows = [json.loads(l) for l in open(OUT / "e10a_nexar_requests_h100nvl.jsonl")]
    ok = {(r["model"], r["n"], r["enc"], r["request_id"]): r for r in rows if not r["error"]}
    d14 = {(r["model"], r["n"], r["request_id"]): r for r in map(json.loads, gzip.open(
        REPO / "results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz", "rt"))}
    res["nexar_checks"] = dict(rows=len(rows), error_rows=sum(bool(r["error"]) for r in rows),
                               neither_yes_no=sum(r["p_yes"] is None for r in ok.values()),
                               cached_nonzero=sum(bool(r["cached_tokens"]) for r in ok.values()))
    res["nexar"] = {}
    for model in ("4BI", "32BI"):
        for n in (1, 3):
            ids = sorted({k[3] for k in ok if k[0] == model and k[1] == n})
            ids = [i for i in ids if (model, n, "png", i) in ok and (model, n, "jpeg", i) in ok]
            P = [ok[(model, n, "png", i)] for i in ids]
            J = [ok[(model, n, "jpeg", i)] for i in ids]
            sp, sj = np.array([r["score"] for r in P]), np.array([r["score"] for r in J])
            y = np.array([r["label"] == "positive" for r in P], int)
            clips = [r["file_name"] for r in P]
            dd = sj - sp
            cell = dict(n=len(ids), positives=int(y.sum()), clips=len(set(clips)),
                        prompt_tokens_equal=sum(a["prompt_tokens"] == b["prompt_tokens"] for a, b in zip(P, J)),
                        bytes_ratio_jpeg_over_png=float(np.median([b["image_url_chars"] / a["image_url_chars"] for a, b in zip(P, J)])),
                        pearson=float(pearsonr(sp, sj)[0]), spearman=float(spearmanr(sp, sj)[0]),
                        abs_dscore=dict(median=float(np.median(np.abs(dd))), p90=float(np.percentile(np.abs(dd), 90)),
                                        max=float(np.abs(dd).max())),
                        frac_abs_dscore_gt1=float(np.mean(np.abs(dd) > 1)),
                        yes_flip=float(np.mean([(a["p_yes"] > 0.5) != (b["p_yes"] > 0.5) for a, b in zip(P, J)])),
                        **boot_clip(clips, y, sp, sj, rng))
            # determinism floor: PNG re-send vs committed D14 trace
            dk = [(i, d14.get((model, n, i))) for i in ids]
            dk = [(i, r) for i, r in dk if r]
            s14 = np.array([r["score"] for _, r in dk])
            sr = np.array([ok[(model, n, "png", i)]["score"] for i, _ in dk])
            cell["png_resend_vs_d14"] = dict(n=len(dk), pearson=float(pearsonr(s14, sr)[0]),
                                             frac_abs_dscore_gt1=float(np.mean(np.abs(sr - s14) > 1)),
                                             abs_dscore_median=float(np.median(np.abs(sr - s14))),
                                             identical=int(np.sum(np.abs(sr - s14) < 1e-9)))
            res["nexar"][f"{model}/N{n}"] = cell
    # S-EMBER
    s = [json.loads(l) for l in open(OUT / "e10a_sember_requests_h100nvl.jsonl")]
    sok = {r["question_id"]: r for r in s if not r["error"]}
    k3 = {r["question_id"]: r for r in map(json.loads, gzip.open(REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "rt"))
          if r["cell"] == "K3" and r["mode"] == "batched" and not r["error"]}
    q = sorted(set(sok) & set(k3))
    agree = float(np.mean([sok[x]["pred"] == k3[x]["pred"] for x in q]))
    res["sember"] = dict(n=len(q), error_rows=sum(bool(r["error"]) for r in s),
                         prompt_tokens_match_r1=sum(bool(sok[x]["prompt_tokens_match"]) for x in q),
                         letter_agreement=agree, disagreements=[(x[:10], k3[x]["pred"], sok[x]["pred"], sok[x]["correct_letter"]) for x in q
                                                                if sok[x]["pred"] != k3[x]["pred"]],
                         acc_jpeg=float(np.mean([bool(sok[x]["correct"]) for x in q])),
                         acc_k3_png=float(np.mean([bool(k3[x]["correct"]) for x in q])),
                         jpeg_minus_png=video_boot([(sok[x]["video_id"], float(bool(sok[x]["correct"])) - float(bool(k3[x]["correct"]))) for x in q], rng),
                         unparsed=sum(sok[x]["pred"] == "X" for x in q),
                         video_url_mb_median=float(np.median([sok[x]["video_url_chars"] for x in q]) / 1e6))
    nex_ok = all(c[k]["diff_ci_includes_0"] for c in res["nexar"].values() for k in ("auroc", "ap"))
    res["verdict"] = dict(rule="JPEG acceptable iff every model x N AUROC and AP difference CI includes 0 AND S-EMBER "
                               "letter agreement >= 95 %", nexar_all_ci_include_0=nex_ok,
                          sember_agreement_ge_95=agree >= 0.95, acceptable=bool(nex_ok and agree >= 0.95))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e10a_analyse.py", model="4BI,32BI", device="cpu", n=len(rows) + len(s))
    (OUT / "e10a_results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res["verdict"]))


if __name__ == "__main__":
    main()
