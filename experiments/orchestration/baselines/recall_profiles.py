#!/usr/bin/env python3
"""Recall accuracy profiles per S-EMBER question category x question-time bin x configuration.

StudyB-baselines amendment (2026-11-12) item (b). CPU only: nothing here runs a model, and NO
accuracy is estimated, fitted or interpolated. Every cell is a count of COMMITTED per-question
`correct` flags, read through StudyE6b's own loaders so there is exactly one definition of each
configuration in the repository:

| configuration | source | committed file |
|---|---|---|
| 32B RICH     | StudyR1 K1              | results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz |
| 32B RECENT   | StudyR1 K3              | as above |
| 32B D2       | StudyRH4 D2             | results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz |
| 32B U        | StudyD11 arm U, 32BI    | results/cost/study_d11/study_d11_requests_h100nvl.jsonl |
| 4B RICH      | StudyClean H2           | results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz |
| 4B RECENT    | StudyClean H1           | as above |
| 4B D2        | StudyE7 Job A           | results/sember/study_e7/e7_requests_h100nvl.jsonl |
| device N=1/3/9 | StudyF4 Part A        | results/device/study_f4/partA_accuracy.jsonl |

**4B D2 is the DEVICE PROXY and is labelled as such.** Its letters are the H100 4B's; StudyE8
Part D measured device-vs-H100 agreement at 68/68 warm and 27/27 cold on byte-identical inputs,
and StudyF4 measured per-question agreement 0.972-0.981 with no cell below 90 %. StudyD15 Part A
separately REJECTED the H100-for-Orin proxy as an *exact* numerical stand-in, so these tables may
be used for ordering and for first-order value, never as exact device numbers.

Question-time bins are StudyE6b's: `le120`, `120-480`, `gt480` (seconds of session time). The
category is the S-EMBER `question_category` from StudyR1's inputs manifest.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/orchestration"))
sys.path.insert(0, str(ROOT / "experiments/lib"))

BINS = ("le120", "120-480", "gt480")
SEED, NB = 0, 2000
SMALL_N = 20                 # below this a cell is flagged UNRELIABLE rather than quoted
OUT = ROOT / "results/orchestration/study_b_baselines"

CONFIGS: Tuple[Tuple[str, str, str, str], ...] = (
    ("32B-RICH", "K1", "StudyR1 K1 (32BI, RICH video)", "cloud"),
    ("32B-RECENT", "K3", "StudyR1 K3 (32BI, RECENT video)", "cloud"),
    ("32B-D2", "D2", "StudyRH4 D2 (32BI, 2-s stride 352x256 images)", "cloud"),
    ("32B-U", "U32", "StudyD11 arm U (32BI, union)", "cloud"),
    ("4B-RICH", "H2", "StudyClean H2 (4BI, RICH video)", "cloud"),
    ("4B-RECENT", "H1", "StudyClean H1 (4BI, RECENT video)", "cloud"),
    ("4B-D2", "E7", "StudyE7 Job A (4BI on RH4's D2 input) - DEVICE PROXY", "device-proxy"),
    ("device-N1", "F4N1", "StudyF4 Part A, 1-frame last-3-s window (Jetson Orin)", "device"),
    ("device-N3", "F4N3", "StudyF4 Part A, 3-frame last-3-s window (Jetson Orin)", "device"),
    ("device-N9", "F4N9", "StudyF4 Part A, 9-frame last-3-s window (Jetson Orin)", "device"),
)


def qbin(t: float) -> str:
    """StudyE6b's bins, unchanged."""
    return "le120" if t <= 120 else ("120-480" if t <= 480 else "gt480")


def _load_answers():
    """Per-question `correct` flags and the question metadata, through StudyE6b's own loaders."""
    import study_e6b_mobility as A
    import study_e6b_stageb as Bst
    man, ans, tok = A.load()
    e7, e7tok = Bst.e7_answers()
    ans["E7"], tok["E7"] = e7, e7tok
    meta = {q: dict(video=man[q]["RECENT"]["video_id"],
                    qt=float(man[q]["RECENT"]["question_time"]),
                    cat=man[q]["RECENT"]["question_category"]) for q in sorted(man)}
    assert len(meta) == 845, len(meta)
    return meta, ans, tok


def _boot_ci(correct: List[bool], videos: List[str]) -> Optional[List[float]]:
    """Video-clustered bootstrap CI, 2,000 resamples, seed 0 - StudyE6b's resampling unit, because
    questions from one video are not independent."""
    if not correct:
        return None
    byv = defaultdict(list)
    for c, v in zip(correct, videos):
        byv[v].append(1.0 if c else 0.0)
    vids = sorted(byv)
    arr = [np.array(byv[v]) for v in vids]
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(vids), (NB, len(vids)))
    out = np.empty(NB)
    for b in range(NB):
        pick = np.concatenate([arr[i] for i in idx[b]])
        out[b] = pick.mean()
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def build() -> Dict:
    meta, ans, tok = _load_answers()
    cats = sorted({meta[q]["cat"] for q in meta})
    res: Dict[str, object] = dict(
        label="StudyB-baselines recall accuracy profiles: committed per-question `correct` flags, "
              "counted per S-EMBER question category x question-time bin x configuration. NOTHING "
              "IS ESTIMATED OR INTERPOLATED. CPU only; no model is run.",
        bins=list(BINS), categories=cats, n_questions=len(meta), seed=SEED, n_bootstrap=NB,
        small_n_flag=SMALL_N,
        bin_rule="StudyE6b's: le120 = question_time <= 120 s, 120-480 = (120, 480], gt480 > 480 s",
        ci_rule="video-clustered bootstrap, 2,000 resamples, seed 0 (StudyE6b's unit)",
        device_proxy_note="4B-D2 carries the H100 4B's letters for StudyE7's D2 input. StudyE8 "
                          "Part D: 68/68 warm and 27/27 cold identical on byte-identical inputs; "
                          "StudyF4: per-question agreement 0.972-0.981. StudyD15 Part A rejected "
                          "the H100-for-Orin proxy as an EXACT numerical stand-in, so these "
                          "tables are valid for ordering and first-order value, not as exact "
                          "device numbers.",
        configs={}, cells={})
    for name, key, src, tier in CONFIGS:
        a = ans.get(key, {})
        qs = [q for q in meta if q in a]
        cell = dict(name=name, source=src, tier=tier, n=len(qs),
                    accuracy=(float(np.mean([a[q] for q in qs])) if qs else None),
                    ci=_boot_ci([a[q] for q in qs], [meta[q]["video"] for q in qs]),
                    mean_prompt_tokens=(float(np.mean([tok[key][q] for q in qs
                                                       if tok.get(key, {}).get(q)]))
                                        if qs else None),
                    by_category={}, by_bin={}, by_category_bin={})
        for c in cats:
            sel = [q for q in qs if meta[q]["cat"] == c]
            cell["by_category"][c] = dict(
                n=len(sel), accuracy=(float(np.mean([a[q] for q in sel])) if sel else None),
                ci=_boot_ci([a[q] for q in sel], [meta[q]["video"] for q in sel]),
                unreliable=bool(len(sel) < SMALL_N))
        for b in BINS:
            sel = [q for q in qs if qbin(meta[q]["qt"]) == b]
            cell["by_bin"][b] = dict(
                n=len(sel), accuracy=(float(np.mean([a[q] for q in sel])) if sel else None),
                ci=_boot_ci([a[q] for q in sel], [meta[q]["video"] for q in sel]),
                unreliable=bool(len(sel) < SMALL_N))
        for c in cats:
            for b in BINS:
                sel = [q for q in qs if meta[q]["cat"] == c and qbin(meta[q]["qt"]) == b]
                cell["by_category_bin"][f"{c}|{b}"] = dict(
                    n=len(sel), accuracy=(float(np.mean([a[q] for q in sel])) if sel else None),
                    unreliable=bool(len(sel) < SMALL_N))
        res["configs"][name] = cell
    # the per-question coverage table: which configurations answered which question
    cov = defaultdict(int)
    for q in meta:
        cov[sum(1 for _n, k, _s, _t in CONFIGS if q in ans.get(k, {}))] += 1
    res["coverage_by_n_configs"] = {str(k): v for k, v in sorted(cov.items())}
    return res


# ---------------------------------------------------------------- readers for the baselines
_CACHE: Optional[Dict] = None


def table() -> Dict:
    """The committed profile table. Built on first use and cached on disk."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    f = OUT / "b_recall_accuracy.json"
    _CACHE = json.loads(f.read_text()) if f.exists() else build()
    return _CACHE


def accuracy(config: str, category: Optional[str] = None, question_time_s: Optional[float] = None
             ) -> Optional[float]:
    """Committed accuracy for one configuration, optionally narrowed to a category and a
    question-time bin. Returns None where no committed cell exists - never a guess."""
    t = table()
    c = t["configs"].get(config)
    if c is None:
        return None
    if category is None and question_time_s is None:
        return c["accuracy"]
    if category is not None and question_time_s is not None:
        k = f"{category}|{qbin(question_time_s)}"
        cell = c["by_category_bin"].get(k)
    elif category is not None:
        cell = c["by_category"].get(category)
    else:
        cell = c["by_bin"].get(qbin(question_time_s))
    return None if cell is None else cell["accuracy"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    res = build()
    sys.path.insert(0, str(ROOT / "experiments/lib"))
    from _provenance import stamp
    res["_provenance"] = stamp(script="recall_profiles.py", model=None, device="cpu",
                               n=res["n_questions"], args=None)
    (OUT / "b_recall_accuracy.json").write_text(json.dumps(res, indent=1, default=float))
    with (OUT / "b_recall_accuracy.csv").open("w") as f:
        f.write("configuration,tier,source,category,question_time_bin,n,accuracy,unreliable\n")
        for name, c in res["configs"].items():
            f.write("%s,%s,\"%s\",ALL,ALL,%d,%s,%s\n"
                    % (name, c["tier"], c["source"], c["n"], c["accuracy"], False))
            for cat, v in c["by_category"].items():
                f.write("%s,%s,\"%s\",%s,ALL,%d,%s,%s\n"
                        % (name, c["tier"], c["source"], cat, v["n"], v["accuracy"],
                           v["unreliable"]))
            for b, v in c["by_bin"].items():
                f.write("%s,%s,\"%s\",ALL,%s,%d,%s,%s\n"
                        % (name, c["tier"], c["source"], b, v["n"], v["accuracy"],
                           v["unreliable"]))
            for k, v in c["by_category_bin"].items():
                cat, b = k.split("|")
                f.write("%s,%s,\"%s\",%s,%s,%d,%s,%s\n"
                        % (name, c["tier"], c["source"], cat, b, v["n"], v["accuracy"],
                           v["unreliable"]))
    print("wrote", OUT / "b_recall_accuracy.json")
    for name, c in res["configs"].items():
        print("  %-12s n=%3d acc=%.4f %s" % (name, c["n"], c["accuracy"] or 0.0,
                                             "CI %.3f-%.3f" % tuple(c["ci"]) if c["ci"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
