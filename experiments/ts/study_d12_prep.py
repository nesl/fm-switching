"""
StudyD12-prep: can Qwen3-VL run time-series tasks, and does the input FORM matter?

Two arms per item, built from the SAME data window:
  TEXT  numeric series inline, stated precision and channel names
  PLOT  fixed-format line plot PNG, identical axes style for every item

Datasets: STARK (its own questions/answers, verbatim), WISDM (our formulation),
MIT-BIH (our formulation). Prep only by default; --pilot runs the 50-item screen.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments"))

RAW = Path("/mnt/ssd/hf_models/ts_raw")
OUT = REPO / "results" / "ts" / "study_d12_prep"
PLOTS = OUT / "plots"

MODELS = {
    "4b": ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17"),
    "8b": ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"),
}

# ---------------------------------------------------------------- WISDM

WISDM_FS = 20.0
WISDM_WIN_S = 10.0
WISDM_WIN_N = int(WISDM_FS * WISDM_WIN_S)   # 200 samples
WISDM_DP = 2
WISDM_ACTIVITIES = {
    "A": "walking", "B": "jogging", "C": "stairs", "D": "sitting", "E": "standing",
    "F": "typing", "G": "brushing teeth", "H": "eating soup", "I": "eating chips",
    "J": "eating pasta", "K": "drinking from a cup", "L": "eating a sandwich",
    "M": "kicking a soccer ball", "O": "playing catch with a tennis ball",
    "P": "dribbling a basketball", "Q": "writing", "R": "clapping", "S": "folding clothes",
}

# -------------------------------------------------------------- MIT-BIH

MITDB_FS = 360
MITDB_WIN_N = 360           # 1.0 s centred on the annotated R peak
MITDB_DP = 3
MITDB_LEAD = "MLII"
# AAMI EC57 beat superclasses (standard mapping; our choice of formulation)
AAMI = {
    **{s: "N" for s in ["N", "L", "R", "e", "j"]},
    **{s: "S" for s in ["A", "a", "J", "S"]},
    **{s: "V" for s in ["V", "E"]},
    "F": "F",
    **{s: "Q" for s in ["/", "f", "Q"]},
}
AAMI_DESC = {
    "N": "Normal beat, or left/right bundle-branch block beat, or nodal/atrial escape beat",
    "S": "Supraventricular ectopic beat (atrial or nodal premature, aberrated atrial premature)",
    "V": "Ventricular ectopic beat (premature ventricular contraction or ventricular escape)",
    "F": "Fusion of a ventricular and a normal beat",
    "Q": "Unclassifiable or paced beat",
}

PILOT_N = 50
SEED = 0


def _fmt(vals, dp):
    return ", ".join(f"{v:.{dp}f}" for v in vals)


# ----------------------------------------------------------- item build

def build_wisdm(n=PILOT_N, seed=SEED):
    """One non-overlapping window per item, stratified over the 18 activities."""
    acc = RAW / "wisdm" / "wisdm-dataset" / "raw" / "phone" / "accel"
    files = sorted(acc.glob("data_*_accel_phone.txt"))
    if not files:
        raise SystemExit(f"WISDM raw not found under {acc}")

    # subject -> activity -> list of windows (as float arrays)
    pool = defaultdict(list)
    for fp in files:
        subj = fp.name.split("_")[1]
        rows = defaultdict(list)
        for line in fp.read_text().splitlines():
            line = line.strip().rstrip(";")
            if not line:
                continue
            p = line.split(",")
            if len(p) != 6:
                continue
            try:
                rows[p[1]].append((int(p[2]), float(p[3]), float(p[4]), float(p[5])))
            except ValueError:
                continue
        for act, recs in rows.items():
            if act not in WISDM_ACTIVITIES:
                continue
            recs.sort(key=lambda r: r[0])
            arr = np.asarray([[r[1], r[2], r[3]] for r in recs], dtype=np.float64)
            nwin = len(arr) // WISDM_WIN_N
            for w in range(nwin):
                pool[act].append((subj, w, arr[w * WISDM_WIN_N:(w + 1) * WISDM_WIN_N]))

    rng = np.random.default_rng(seed)
    acts = sorted(pool)
    picked = []
    # round-robin over activities so the 50 are as balanced as 18 classes allow
    idx = {a: rng.permutation(len(pool[a])).tolist() for a in acts}
    cur = {a: 0 for a in acts}
    while len(picked) < n:
        progressed = False
        for a in acts:
            if len(picked) >= n:
                break
            if cur[a] < len(idx[a]):
                subj, w, arr = pool[a][idx[a][cur[a]]]
                cur[a] += 1
                picked.append(dict(dataset="wisdm", label=a, label_name=WISDM_ACTIVITIES[a],
                                   subject=subj, window=w, series=arr))
                progressed = True
        if not progressed:
            break

    opts = [(a, WISDM_ACTIVITIES[a]) for a in acts]
    for i, it in enumerate(picked):
        it["item_id"] = f"wisdm_{i:03d}"
        it["options"] = opts
        it["answer_index"] = [a for a, _ in opts].index(it["label"]) + 1
    return picked


def build_mitdb(n=PILOT_N, seed=SEED):
    """One beat per item, stratified over the 5 AAMI superclasses."""
    import wfdb
    d = RAW / "mitdb"
    recs = [r.strip() for r in (d / "RECORDS").read_text().split() if r.strip()]
    pool = defaultdict(list)
    for r in recs:
        rec = wfdb.rdrecord(str(d / r))
        if MITDB_LEAD not in rec.sig_name:
            continue              # records 102/104 carry V5+V2, no MLII
        ch = rec.sig_name.index(MITDB_LEAD)
        sig = rec.p_signal[:, ch]
        ann = wfdb.rdann(str(d / r), "atr")
        half = MITDB_WIN_N // 2
        for s, sym in zip(ann.sample, ann.symbol):
            cls = AAMI.get(sym)
            if cls is None:
                continue          # rhythm/quality markers, not beats
            if s - half < 0 or s + half > len(sig):
                continue
            pool[cls].append((r, int(s), sym))

    rng = np.random.default_rng(seed)
    classes = ["N", "S", "V", "F", "Q"]
    avail = [c for c in classes if pool[c]]
    idx = {c: rng.permutation(len(pool[c])).tolist() for c in avail}
    cur = {c: 0 for c in avail}
    picked = []
    while len(picked) < n:
        progressed = False
        for c in avail:
            if len(picked) >= n:
                break
            if cur[c] < len(idx[c]):
                r, s, sym = pool[c][idx[c][cur[c]]]
                cur[c] += 1
                picked.append(dict(dataset="mitdb", label=c, symbol=sym, record=r, sample=s))
                progressed = True
        if not progressed:
            break

    # attach signal windows (reopen each record once)
    by_rec = defaultdict(list)
    for it in picked:
        by_rec[it["record"]].append(it)
    for r, its in by_rec.items():
        rec = wfdb.rdrecord(str(d / r))
        ch = rec.sig_name.index(MITDB_LEAD)
        sig = rec.p_signal[:, ch]
        half = MITDB_WIN_N // 2
        for it in its:
            it["series"] = sig[it["sample"] - half: it["sample"] + half].reshape(-1, 1)

    opts = [(c, AAMI_DESC[c]) for c in classes]
    for i, it in enumerate(picked):
        it["item_id"] = f"mitdb_{i:03d}"
        it["options"] = opts
        it["answer_index"] = classes.index(it["label"]) + 1
    return picked


# STARK task families by tier, from Table 2 of arXiv 2505.11618
STARK_TIERS = {
    1: ["loc_range", "loc_bearing", "loc_range_bearing", "loc_region",
        "loc_event_spatio", "loc_event_temp",
        "track_range_online", "track_bearing_online", "track_range_bearing_online",
        "track_region_online", "track_event_spatio_online", "track_event_temp_online",
        "spatial_impute", "temporal_impute", "spatiotemporal_impute",
        "spatiotemporal_forecast"],
    2: ["contains", "during", "finishes", "finished_by", "is_equal_to", "meets",
        "is_met_by", "overlaps_with", "is_overlapped_by", "precedes", "is_preceded_by",
        "starts", "is_started_by",
        "Point_Point_equals", "Linestring_Point_intersects", "Polygon_Point_contains",
        "Polygon_Polygon_overlaps", "Linestring_Polygon_crosses"],
    3: ["landmark_questions", "direction_questions", "route_planning",
        "travel_questions", "subroute_duration", "poi_pred", "intent_pred"],
}
# families whose answer is categorical -> accuracy is defined
STARK_CATEGORICAL = {"landmark_questions", "direction_questions", "route_planning",
                     "travel_questions", "subroute_duration", "poi_pred", "intent_pred",
                     "contains", "during", "finishes", "finished_by", "is_equal_to",
                     "meets", "is_met_by", "overlaps_with", "is_overlapped_by",
                     "precedes", "is_preceded_by", "starts", "is_started_by",
                     "Point_Point_equals", "Linestring_Point_intersects",
                     "Polygon_Point_contains", "Polygon_Polygon_overlaps",
                     "Linestring_Polygon_crosses"}


def build_stark(n=PILOT_N, seed=SEED):
    """STARK items use the benchmark's own `query` and `answer` columns, verbatim."""
    import pandas as pd
    d = RAW / "stark"
    csvs = sorted(d.rglob("*.csv"))
    if not csvs:
        raise SystemExit(f"STARK CSVs not found under {d} - run --fetch-stark first")
    by_fam = defaultdict(list)
    for p in csvs:
        by_fam[p.parent.name].append(p)

    rng = np.random.default_rng(seed)
    fams = sorted(by_fam)
    idx = {f: rng.permutation(len(by_fam[f])).tolist() for f in fams}
    cur = {f: 0 for f in fams}
    picked = []
    while len(picked) < n:
        progressed = False
        for f in fams:
            if len(picked) >= n:
                break
            if cur[f] < len(idx[f]):
                p = by_fam[f][idx[f][cur[f]]]
                cur[f] += 1
                df = pd.read_csv(p)
                tier = next((t for t, fl in STARK_TIERS.items() if f in fl), None)
                picked.append(dict(dataset="stark", family=f, tier=tier, path=str(p),
                                   query=str(df["query"].iloc[0]),
                                   answer=str(df["answer"].iloc[0]),
                                   categorical=f in STARK_CATEGORICAL))
                progressed = True
        if not progressed:
            break
    for i, it in enumerate(picked):
        it["item_id"] = f"stark_{i:03d}"
    return picked


# -------------------------------------------------------------- prompts

WISDM_PREAMBLE = (
    f"You are given a {WISDM_WIN_S:.1f}-second window of accelerometer data recorded by a "
    f"smartphone in the subject's front trouser pocket, sampled at {WISDM_FS:.0f} Hz "
    f"({WISDM_WIN_N} samples per channel). The three channels are the x, y and z linear "
    f"acceleration axes in m/s^2, rounded to {WISDM_DP} decimal places."
)
WISDM_QUESTION = "Which single activity below is the subject performing during this window?"

MITDB_PREAMBLE = (
    f"You are given a {MITDB_WIN_N / MITDB_FS:.1f}-second window of a single-lead "
    f"electrocardiogram (lead {MITDB_LEAD}) sampled at {MITDB_FS} Hz ({MITDB_WIN_N} samples), "
    f"in millivolts rounded to {MITDB_DP} decimal places. The window is centred on one "
    f"annotated heartbeat: its R peak is at the midpoint of the window "
    f"(sample {MITDB_WIN_N // 2} of {MITDB_WIN_N})."
)
MITDB_QUESTION = (
    "Classify the heartbeat at the centre of this window into one of the AAMI EC57 classes below."
)

TEXT_CLAUSE = "The window is given below as numeric samples, one line per channel."
PLOT_CLAUSE = ("The window is given as the attached line plot image, one coloured trace per "
               "channel, with time in seconds on the x axis and amplitude on the y axis.")


def _series_block(it):
    arr = it["series"]
    dp = WISDM_DP if it["dataset"] == "wisdm" else MITDB_DP
    names = ["x", "y", "z"] if it["dataset"] == "wisdm" else [MITDB_LEAD]
    return "\n".join(f"{nm}: {_fmt(arr[:, i], dp)}" for i, nm in enumerate(names))


def make_prompt(it, arm):
    """Same text in both arms except the clause naming the input form."""
    if it["dataset"] == "stark":
        return it["query"]            # verbatim, never rewritten
    pre = WISDM_PREAMBLE if it["dataset"] == "wisdm" else MITDB_PREAMBLE
    qn = WISDM_QUESTION if it["dataset"] == "wisdm" else MITDB_QUESTION
    clause = TEXT_CLAUSE if arm == "text" else PLOT_CLAUSE
    parts = [pre, clause, ""]
    if arm == "text":
        parts += [_series_block(it), ""]
    parts += [qn, ""]
    for i, (code, name) in enumerate(it["options"], 1):
        parts.append(f"{i}. {name}" if it["dataset"] == "wisdm" else f"{i}. {code} - {name}")
    parts += [
        "",
        "Answer with the number of the single best option, in exactly this format:",
        "[ANSWER] <number> [/ANSWER]",
        "You may reason beforehand, but put nothing except the number between the tags.",
    ]
    return "\n".join(parts)


# ----------------------------------------------------------------- plot

def render_plot(it, path):
    """Fixed format for every item: same figure size, dpi, grid, colours, no title."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arr = it["series"]
    fs = WISDM_FS if it["dataset"] == "wisdm" else MITDB_FS
    names = ["x", "y", "z"] if it["dataset"] == "wisdm" else [MITDB_LEAD]
    unit = "m/s^2" if it["dataset"] == "wisdm" else "mV"
    colours = ["#1f77b4", "#d62728", "#2ca02c"]
    t = np.arange(len(arr)) / fs

    fig, ax = plt.subplots(figsize=(8.0, 3.0), dpi=100)
    for i, nm in enumerate(names):
        ax.plot(t, arr[:, i], linewidth=0.9, color=colours[i], label=nm)
    ax.set_xlabel("time (s)")
    ax.set_ylabel(f"amplitude ({unit})")
    ax.set_xlim(0, len(arr) / fs)
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png")
    plt.close(fig)


# ----------------------------------------------------------- token count

def count_tokens(items, model_key="4b"):
    """Prompt tokens per arm, including image tokens for the PLOT arm."""
    from transformers import AutoProcessor
    from PIL import Image

    repo, rev = MODELS[model_key]
    proc = AutoProcessor.from_pretrained(repo, revision=rev, cache_dir=str(RAW.parent))
    out = {}
    for it in items:
        rec = {}
        for arm in ("text", "plot"):
            if it["dataset"] == "stark" and arm == "plot":
                continue
            prompt = make_prompt(it, arm)
            content = [{"type": "text", "text": prompt}]
            images = None
            if arm == "plot":
                png = PLOTS / it["dataset"] / f"{it['item_id']}.png"
                images = [Image.open(png).convert("RGB")]
                content = [{"type": "image"}, {"type": "text", "text": prompt}]
            chat = proc.apply_chat_template(
                [{"role": "user", "content": content}],
                tokenize=False, add_generation_prompt=True)
            enc = proc(text=[chat], images=images, return_tensors="pt")
            rec[arm] = int(enc["input_ids"].shape[1])
        out[it["item_id"]] = rec
    return out


# ---------------------------------------------------------------- stages

def stage_prep(args):
    OUT.mkdir(parents=True, exist_ok=True)
    built = {}
    if "wisdm" in args.datasets:
        built["wisdm"] = build_wisdm(args.n, args.seed)
    if "mitdb" in args.datasets:
        built["mitdb"] = build_mitdb(args.n, args.seed)
    if "stark" in args.datasets:
        built["stark"] = build_stark(args.n, args.seed)

    manifest = {}
    for name, items in built.items():
        if name != "stark":
            for it in items:
                render_plot(it, PLOTS / name / f"{it['item_id']}.png")
        toks = count_tokens(items, args.model) if not args.no_tokens else {}
        recs = []
        for it in items:
            r = {k: v for k, v in it.items() if k != "series"}
            if "series" in it:
                r["series_shape"] = list(it["series"].shape)
            r["prompt_tokens"] = toks.get(it["item_id"], {})
            r["prompt_text"] = make_prompt(it, "text")
            if name != "stark":
                r["prompt_plot"] = make_prompt(it, "plot")
                r["plot_png"] = f"plots/{name}/{it['item_id']}.png"
            recs.append(r)
        manifest[name] = recs
        lab = Counter(it.get("label") or it.get("family") for it in items)
        print(f"{name}: {len(items)} items, {len(lab)} classes/families, "
              f"most common {lab.most_common(3)}")
        if toks:
            for arm in ("text", "plot"):
                v = [t[arm] for t in toks.values() if arm in t]
                if v:
                    print(f"   {arm:5s} tokens median {int(np.median(v))} max {max(v)}")

    # keep the window arrays out of git-tracked JSON; they live in one npz
    arrs = {f"{n}/{it['item_id']}": it["series"]
            for n, its in built.items() for it in its if "series" in it}
    if arrs:
        np.savez_compressed(OUT / "windows.npz", **arrs)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"-> {OUT/'manifest.json'}")


def stage_pilot(args):
    raise SystemExit(
        "Pilot not run. Blocked pre-run on two items the task says to stop for:\n"
        "  1. target GPU busy (A6000 at 100% with another user's CarlaUE4 + ollama)\n"
        "  2. flash's vLLM 0.8.5 has no Qwen3VLForConditionalGeneration; HF transformers\n"
        "     5.12.1 would be a stack change, which needs sign-off first.\n"
        "Re-run with --force-pilot once both are resolved."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prep", "pilot"])
    ap.add_argument("--datasets", nargs="+", default=["wisdm", "mitdb", "stark"])
    ap.add_argument("--n", type=int, default=PILOT_N)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--model", default="4b", choices=list(MODELS))
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--force-pilot", action="store_true")
    args = ap.parse_args()
    (stage_prep if args.stage == "prep" else stage_pilot)(args)


if __name__ == "__main__":
    main()
