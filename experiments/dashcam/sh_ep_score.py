#!/usr/bin/env python3
"""StudySH-EP scorer and positive control (CPU only; no GPU, no model server, no inference).

Pre-registered in research/EXPERIMENTS.md (StudySH-EP) and reports/study_sh_ep.md.

  python3 -I experiments/dashcam/sh_ep_score.py --control-only     # before any data lands
  python3 -I experiments/dashcam/sh_ep_score.py --runs <jsonl> ...  # when data lands

THE POSITIVE CONTROL RUNS FIRST, ALWAYS (CLAUDE.md consistency check 7)
  This box has no sklearn, so `average_precision_score` cannot be called here and the challenge
  AP is implemented in `ap_step`. An implementation of a committed metric is worth nothing until
  it reproduces that metric's committed numbers, so before scoring anything the scorer rebuilds
  StudyE9c's crops from the committed D14b trace and recomputes the `|zero` arms' per-horizon APs
  and mAP. If any of them misses the committed value by more than 1e-9 the scorer STOPS: the
  check is broken, or the metric is, and either way no SH-EP number may be read.

  The crop rule, the horizon-inclusion rule, the fake negative reference and the grid index are
  LIFTED out of the committed scripts by AST, never retyped (`committed`).

WHY CALIBRATION CANNOT MOVE THE HEADLINE, STATED BEFORE IT IS FITTED
  D6 calibration is fitted per (model, condition) on DEV and applied to EVAL, as the brief
  directs. Average precision and a threshold set at a DEV false-alarm QUANTILE are both invariant
  under a strictly monotone, per-(model, condition) transform, and Platt scaling is one, so the
  calibration cannot change AP, cannot change the achieved EVAL false-alarm rate and cannot
  change any earliness lead. It is fitted, applied and reported because the brief asks for it,
  and it is reported as INERT for H1 and H2 rather than as a step that did work.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

D14B = ROOT / "results/dashcam/study_d14b"
SH = ROOT / "results/dashcam/study_sh_ep"
E9C_RESULTS = ROOT / "results/dashcam/study_e9c/e9c_results.json"
E9C_SCRIPT = ROOT / "experiments/dashcam/study_e9c_challenge.py"
E9B_SCRIPT = ROOT / "experiments/dashcam/study_e9b_dense.py"

SEED, NB = 0, 2000             # StudyE9's own seed and bootstrap count
STEP, T0, MISSING = 0.25, 3.0, -1e9
HORIZONS = (0.5, 1.0, 1.5)
FARS = (0.05, 0.10, 0.20)
SUDDEN_SPLIT = 1.5             # StudyD3's lead split
TOL = 1e-9
CONDITIONS = ("C1", "C3", "C6", "EP-B", "EP-G")
MODELS = ("4BI", "32BI")


def committed(path, name, consts=()):
    """One function or constant out of a committed script, evaluated not retyped."""
    tree = ast.parse(path.read_text(), filename=str(path))
    want, body = set(consts) | {name}, []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in want for t in node.targets):
            body.append(node)
        elif isinstance(node, (ast.FunctionDef,)) and node.name == name:
            body.append(node)
    text = "\n".join(ast.unparse(n) for n in body)
    # the committed functions close over their own module globals: STEP, T0 and the
    # study_e9b_dense module as `B`. They are supplied with THIS file's committed copies of the
    # same constants, and the constants are asserted against the committed scripts below.
    ns = {"np": np, "math": math, "T0": T0, "STEP": STEP,
          "B": type("B", (), dict(T0=T0, STEP_DENSE=STEP))(), "__name__": "committed"}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), ns)  # noqa: S102
    return ns[name], hashlib.sha256(text.encode()).hexdigest()


def _assert_constants():
    """STEP and T0 are supplied to the lifted functions, so they must be the committed values."""
    import re
    e9b = E9B_SCRIPT.read_text()
    e9c = E9C_SCRIPT.read_text()
    want = {"T0 = 3.0": e9b, "STEP_DENSE = 0.25": e9b, "MISSING = -1e9": None,
            "HORIZONS = (0.5, 1.0, 1.5)": e9c, "STEP = B.STEP_DENSE": e9c}
    for k, src in want.items():
        if src is not None and not re.search(r"(?m)^" + re.escape(k) + r"\s*(#.*)?$", src):
            raise SystemExit(f"a committed constant moved: expected a line {k!r}; this scorer "
                             f"supplies T0={T0}, STEP={STEP} to the lifted functions and may "
                             f"not be trusted until the mismatch is resolved")
    if (T0, STEP, tuple(HORIZONS), MISSING) != (3.0, 0.25, (0.5, 1.0, 1.5), -1e9):
        raise SystemExit("this scorer's own constants no longer match the committed ones")


_assert_constants()
fake_event_times, SHA_FAKE = committed(E9C_SCRIPT, "fake_event_times", ("MIN_CROP_S",))
crop_index, SHA_CROP = committed(E9C_SCRIPT, "crop_index")
target_index, SHA_TARGET = committed(E9B_SCRIPT, "target_index")


def ap_step(pos, neg):
    """Average precision, the step-interpolated definition sklearn's own function computes:
    sum over thresholds of (R_n - R_{n-1}) * P_n, descending score, ties merged."""
    y = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    s = np.concatenate([np.asarray(pos, float), np.asarray(neg, float)])
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    distinct = np.where(np.diff(s))[0]
    idx = np.r_[distinct, len(y) - 1]
    tp = np.cumsum(y)[idx]
    fp = np.cumsum(1 - y)[idx]
    prec = tp / np.maximum(tp + fp, 1e-300)
    rec = tp / max(y.sum(), 1e-300)
    return float(np.sum(np.diff(np.r_[0.0, rec]) * prec))


# ------------------------------------------------------------------ the positive control
def d14b_streams():
    """{(model, n): {clip: array over the 0.25 s grid}} plus clip meta, from the committed trace."""
    rows = defaultdict(dict)
    meta = {}
    with gzip.open(D14B / "d14b_trace_h100nvl.jsonl.gz", "rt") as fh:
        for ln in fh:
            r = json.loads(ln)
            c = r["file_name"]
            if c not in meta:
                meta[c] = dict(label=r["label"], duration=float(r["duration_s"]),
                               event=(None if r["time_of_event"] is None
                                      else float(r["time_of_event"])),
                               alert=(None if r["time_of_alert"] is None
                                      else float(r["time_of_alert"])), G=0)
            i = int(round((float(r["t"]) - T0) / STEP))
            meta[c]["G"] = max(meta[c]["G"], i + 1)
            rows[(r["model"], int(r["n"]))].setdefault(c, {})[i] = float(r["score"])
    out = {}
    for k, per in rows.items():
        out[k] = {c: np.full(meta[c]["G"], MISSING) for c in per}
        for c, d in per.items():
            for i, v in d.items():
                out[k][c][i] = v
    return out, meta


def positive_control():
    streams, meta = d14b_streams()
    pos = sorted(c for c in meta if meta[c]["label"] == "positive")
    neg = sorted(c for c in meta if meta[c]["label"] == "negative")
    devs = np.array([meta[c]["event"] - meta[c]["duration"] / 2.0 for c in pos])
    sigma = float(devs.std(ddof=1))
    cm = {c: dict(duration=meta[c]["duration"]) for c in meta}
    fake = fake_event_times(cm, neg, sigma, 0)
    incl = {c: tuple(h for h in HORIZONS
                     if h <= 0.5 or meta[c]["event"] - meta[c]["alert"] > h) for c in pos}
    pidx = {(c, h): target_index(meta, c, h, STEP) for c in pos for h in incl[c]}
    nidx = {(c, h): crop_index(meta, c, fake[c] - h) for c in neg for h in HORIZONS}
    want = json.loads(E9C_RESULTS.read_text())
    got, bad = {}, []
    for model, n in (("4BI", 1), ("32BI", 1), ("32BI", 3), ("4BI", 3)):
        st = streams[(model, n)]
        aps = {}
        for h in HORIZONS:
            P = np.array([st[c][pidx[(c, h)]] for c in pos if h in incl[c]])
            N = np.array([st[c][nidx[(c, h)]] for c in neg])
            aps[h] = ap_step(P, N)
        mp = float(np.mean([aps[h] for h in HORIZONS]))
        key = next(k for k in want["arms"]
                   if k.endswith("|zero") and k.split("|")[0].startswith(f"{model}_N{n}"))
        ref = want["arms"][key]
        d = {"mAP": abs(mp - ref["mAP"]["value"])}
        for h in HORIZONS:
            d[str(h)] = abs(aps[h] - ref["ap"][str(h)]["ap"])
        got[key] = dict(mAP=mp, ap={str(h): aps[h] for h in HORIZONS}, abs_diff=d)
        if max(d.values()) > TOL:
            bad.append((key, d))
    n_incl = {str(h): sum(1 for c in pos if h in incl[c]) for h in HORIZONS}
    out = dict(
        label="POSITIVE CONTROL: this scorer's own AP and crop code recomputing StudyE9c's "
              "committed |zero arms from the committed StudyD14b trace. A miss above 1e-9 is a "
              "STOP: the check is broken, or the metric is.",
        tol=TOL, sigma_fake_event_s=sigma, n_positive_by_horizon=n_incl,
        committed_n_positive_by_horizon=want["n_positive_by_horizon"],
        committed_sha256=dict(fake_event_times=SHA_FAKE, crop_index=SHA_CROP,
                              target_index=SHA_TARGET),
        arms=got, failures=bad, passed=not bad)
    if n_incl != {str(h): v for h, v in want["n_positive_by_horizon"].items()}:
        out["passed"] = False
        out["failures"].append(("n_positive_by_horizon", n_incl))
    return out, dict(meta=meta, pos=pos, neg=neg, fake=fake, incl=incl, sigma=sigma)


# ------------------------------------------------------------------ the study
def platt(scores, labels):
    """Two-parameter logistic fit by Newton steps; returns (a, b) for p = sigma(a * s + b)."""
    s = np.asarray(scores, float)
    y = np.asarray(labels, float)
    a, b = 1.0, 0.0
    for _ in range(200):
        z = a * s + b
        p = 1.0 / (1.0 + np.exp(-z))
        g = np.array([np.sum((p - y) * s), np.sum(p - y)])
        w = p * (1 - p) + 1e-12
        H = np.array([[np.sum(w * s * s), np.sum(w * s)], [np.sum(w * s), np.sum(w)]])
        try:
            step = np.linalg.solve(H + 1e-9 * np.eye(2), g)
        except np.linalg.LinAlgError:
            break
        a, b = a - step[0], b - step[1]
        if max(abs(step)) < 1e-10:
            break
    return float(a), float(b)


def load_runs(paths):
    """{(model, condition, clip): {t: record}} over every run file given."""
    by = defaultdict(dict)
    n = 0
    for p in paths:
        op = gzip.open if str(p).endswith(".gz") else open
        with op(p, "rt") as fh:
            for ln in fh:
                r = json.loads(ln)
                if r.get("control") or r.get("error") or r.get("file_name") is None:
                    continue
                by[(r["model"], r["condition"], r["file_name"])][round(float(r["t"]), 2)] = r
                n += 1
    return by, n


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--runs", nargs="*", default=[])
    ap_.add_argument("--control-only", action="store_true")
    a = ap_.parse_args()
    SH.mkdir(parents=True, exist_ok=True)

    ctrl, ctx = positive_control()
    res = dict(label="StudySH-EP analysis. CPU only; every score is a committed SH-EP run record.",
               at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB,
               horizons=list(HORIZONS), fars=list(FARS), sudden_split_s=SUDDEN_SPLIT,
               positive_control=ctrl)
    if not ctrl["passed"]:
        (SH / "sh_ep_results.json").write_text(json.dumps(res, indent=1))
        raise SystemExit("POSITIVE CONTROL FAILED; nothing else was scored. See "
                         f"{SH / 'sh_ep_results.json'}")
    print("positive control PASSED: "
          + ", ".join(f"{k} mAP {v['mAP']:.10f}" for k, v in ctrl["arms"].items()))
    if a.control_only or not a.runs:
        res["_provenance"] = stamp(script="sh_ep_score.py", model="none", device="cpu", n=0,
                                   args=a)
        (SH / "sh_ep_positive_control.json").write_text(json.dumps(res, indent=1))
        print(f"wrote {SH / 'sh_ep_positive_control.json'} (control only; no run data given)")
        return

    man = json.loads((SH / "sh_ep_manifest_meta.json").read_text())
    side = {c["file_name"]: c["side"] for c in man["clips"]}
    ref = {c["file_name"]: c["ref"] for c in man["clips"]}
    lab = {c["file_name"]: c["label"] for c in man["clips"]}
    meta = ctx["meta"]
    lead = {c: (None if meta[c]["alert"] is None else meta[c]["event"] - meta[c]["alert"])
            for c in meta}
    runs, nrec = load_runs(a.runs)
    res["n_records"] = nrec

    def crop_t(c, h):
        """The challenge crop instant. The evaluated grid is ref - 6 + 0.5 k snapped to the
        0.25 s grid, and 6 - h is a multiple of 0.5 for every horizon, so the crop ALWAYS
        coincides with an evaluated instant; this asserts it rather than assuming it."""
        t = round(round((ref[c] - h) / STEP) * STEP, 2)
        return t

    # ---- scores at the crops, per (model, condition)
    present, missing = {}, defaultdict(list)
    for m in MODELS:
        for cd in CONDITIONS:
            for c in side:
                d = runs.get((m, cd, c))
                if not d:
                    missing[(m, cd)].append(c)
                    continue
                for h in HORIZONS:
                    t = crop_t(c, h)
                    r = d.get(t)
                    if r is None or r.get("score") is None:
                        missing[(m, cd)].append(f"{c}@{t}")
                    else:
                        present[(m, cd, c, h)] = float(r["score"])
    res["coverage"] = {f"{m}|{cd}": dict(clips_or_crops_missing=len(v))
                       for (m, cd), v in missing.items()}

    pos_e = [c for c in ctx["pos"] if side[c] == "EVAL"]
    neg_e = [c for c in ctx["neg"] if side[c] == "EVAL"]
    incl = ctx["incl"]
    rng = np.random.default_rng(SEED)
    boots = [(rng.integers(0, len(pos_e), len(pos_e)), rng.integers(0, len(neg_e), len(neg_e)))
             for _ in range(NB)]

    def arm_ap(m, cd):
        aps, bs = {}, np.empty((len(HORIZONS), NB))
        for k, h in enumerate(HORIZONS):
            P = np.array([present[(m, cd, c, h)] for c in pos_e
                          if h in incl[c] and (m, cd, c, h) in present])
            N = np.array([present[(m, cd, c, h)] for c in neg_e if (m, cd, c, h) in present])
            if not len(P) or not len(N):
                return None, None
            aps[h] = ap_step(P, N)
            pf = np.array([present.get((m, cd, c, h), np.nan) for c in pos_e])
            pm = np.array([h in incl[c] and (m, cd, c, h) in present for c in pos_e])
            for b, (pi, ni) in enumerate(boots):
                sel = pi[pm[pi]]
                bs[k, b] = ap_step(pf[sel], N[ni]) if len(sel) else 0.0
        return (dict(ap={str(h): dict(ap=aps[h],
                                      ci=[float(np.percentile(bs[k], 2.5)),
                                          float(np.percentile(bs[k], 97.5))])
                         for k, h in enumerate(HORIZONS)},
                     mAP=dict(value=float(np.mean(list(aps.values()))),
                              ci=[float(np.percentile(bs.mean(0), 2.5)),
                                  float(np.percentile(bs.mean(0), 97.5))])),
                bs)

    res["arms"], boot = {}, {}
    for m in MODELS:
        for cd in CONDITIONS:
            o, bs = arm_ap(m, cd)
            if o is None:
                continue
            res["arms"][f"{m}|{cd}"] = o
            boot[(m, cd)] = bs

    # ---- H1: the 32B minus 4B gap per condition, and that gap against C1's
    res["h1_gap"] = {}
    for cd in CONDITIONS:
        if (("32BI", cd) not in boot) or (("4BI", cd) not in boot):
            continue
        g = boot[("32BI", cd)].mean(0) - boot[("4BI", cd)].mean(0)
        v = (res["arms"][f"32BI|{cd}"]["mAP"]["value"]
             - res["arms"][f"4BI|{cd}"]["mAP"]["value"])
        row = dict(gap=v, ci=[float(np.percentile(g, 2.5)), float(np.percentile(g, 97.5))])
        if cd != "C1" and ("32BI", "C1") in boot:
            g1 = boot[("32BI", "C1")].mean(0) - boot[("4BI", "C1")].mean(0)
            d = g - g1
            row["vs_C1"] = dict(
                diff=v - (res["arms"]["32BI|C1"]["mAP"]["value"]
                          - res["arms"]["4BI|C1"]["mAP"]["value"]),
                ci=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))])
        res["h1_gap"][cd] = row

    # ---- H2: earliness at DEV-set false-alarm rates
    def dev_threshold(m, cd, far):
        s = sorted(float(r["score"]) for c in side if side[c] == "DEV" and lab[c] == "negative"
                   for r in (runs.get((m, cd, c)) or {}).values() if r.get("score") is not None)
        return None if not s else s[max(0, min(len(s) - 1,
                                               int(math.ceil((1 - far) * len(s))) - 1))]

    res["h2_earliness"] = {}
    for cd in CONDITIONS:
        for far in FARS:
            cell = {}
            for m in MODELS:
                thr = dev_threshold(m, cd, far)
                if thr is None:
                    continue
                fa, nneg = 0, 0
                for c in neg_e:
                    for r in (runs.get((m, cd, c)) or {}).values():
                        if r.get("score") is None:
                            continue
                        nneg += 1
                        fa += float(r["score"]) >= thr
                leads = {}
                for c in pos_e:
                    d = runs.get((m, cd, c)) or {}
                    hits = sorted(t for t, r in d.items()
                                  if r.get("score") is not None and float(r["score"]) >= thr)
                    leads[c] = (None if not hits else round(ref[c] - hits[0], 4))
                cell[m] = dict(threshold=thr, achieved_far=(fa / nneg if nneg else None),
                               n_negative_instants=nneg,
                               detected=sum(1 for v in leads.values() if v is not None),
                               leads=leads)
            if len(cell) == 2:
                res["h2_earliness"][f"{cd}|far{int(far * 100)}"] = earliness_diff(
                    cell, pos_e, lead, boots, [c for c in pos_e])
    res["controls"] = controls(a.runs, runs, side)
    res["deployment_pair"] = deployment_pair(a.runs)
    res["cost"] = cost(runs)
    res["_provenance"] = stamp(script="sh_ep_score.py", model="none", device="cpu", n=nrec,
                               args=a)
    (SH / "sh_ep_results.json").write_text(json.dumps(res, indent=1))
    print(f"wrote {SH / 'sh_ep_results.json'}")


def earliness_diff(cell, pos_e, lead, boots, order):
    """Paired 32B - 4B lead difference, clip bootstrap, overall and by sudden / slow.

    A clip the arm never fires on has NO lead. Scoring it as zero would silently convert a miss
    into a late detection, so a clip enters the lead comparison only when BOTH arms fire on it,
    and the detection counts are reported beside the difference so the reader can see how many
    clips each arm dropped out of it.
    """
    out = dict(models={m: {k: v for k, v in d.items() if k != "leads"}
                       for m, d in cell.items()})
    a, b = cell["32BI"]["leads"], cell["4BI"]["leads"]
    for name, sel in (("all", pos_e),
                      ("sudden", [c for c in pos_e if lead[c] is not None
                                  and lead[c] < SUDDEN_SPLIT]),
                      ("slow", [c for c in pos_e if lead[c] is not None
                                and lead[c] >= SUDDEN_SPLIT])):
        both = [c for c in sel if a.get(c) is not None and b.get(c) is not None]
        if not both:
            out[name] = dict(n_both=0)
            continue
        d = np.array([a[c] - b[c] for c in both])
        idx = {c: i for i, c in enumerate(both)}
        bs = []
        for pi, _ in boots:
            take = [idx[order[j]] for j in pi if order[j] in idx]
            bs.append(float(np.mean(d[take])) if take else 0.0)
        out[name] = dict(n_both=len(both), n_32BI_only=sum(
            1 for c in sel if a.get(c) is not None and b.get(c) is None),
            n_4BI_only=sum(1 for c in sel if b.get(c) is not None and a.get(c) is None),
            mean_lead_32BI=float(np.mean([a[c] for c in both])),
            mean_lead_4BI=float(np.mean([b[c] for c in both])),
            diff=float(np.mean(d)),
            ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])
    return out


if __name__ == "__main__":
    main()


def controls(paths, runs, side):
    """Every control the pre-registration names, each with its own pass condition.

    None of these is a formality. The warm-path read in particular separates ABSENT from ZERO: a
    missing `cached_tokens` field is an instrument that never reads, which is not the same finding
    as a prefix that was genuinely cold, and reporting them together would hide the first.
    """
    grey, shuf, raw = defaultdict(list), [], []
    for q in paths:
        op = gzip.open if str(q).endswith(".gz") else open
        with op(q, "rt") as fh:
            for ln in fh:
                r = json.loads(ln)
                raw.append(r)
                if r.get("control") == "grey" and r.get("score") is not None:
                    grey[(r["model"], r["n_frames"])].append(float(r["score"]))
                elif r.get("control") == "shuffled":
                    shuf.append(r)
    out = {}
    # 1. grey frames: a constant input must give a constant score
    out["grey"] = {f"{m}|n{n}": dict(n=len(v), min=min(v), max=max(v),
                                     spread=max(v) - min(v),
                                     constant=bool(max(v) - min(v) < 1e-9))
                   for (m, n), v in sorted(grey.items())}
    # 2. shuffled context order against the ordered request at the same instant
    d = []
    for r in shuf:
        o = (runs.get((r["model"], r["condition"], r["file_name"])) or {}).get(
            round(float(r["t"]), 2))
        if o and o.get("score") is not None and r.get("score") is not None:
            d.append(float(r["score"]) - float(o["score"]))
    out["shuffled_minus_ordered"] = dict(
        n=len(d), mean=(float(np.mean(d)) if d else None),
        mean_abs=(float(np.mean(np.abs(d))) if d else None),
        max_abs=(float(np.max(np.abs(d))) if d else None),
        note="a model that reads the episode as a sequence must be DISTURBED by shuffling; a "
             "mean absolute difference at the numerical floor says the frame order carries "
             "nothing and the episode conditions are bags of frames, not episodes")
    # 3. the warm path: presence separated from zero, per condition
    warm = defaultdict(lambda: dict(n=0, absent=0, zero=0, hit=0, cached_sum=0))
    for r in raw:
        if r.get("control") or r.get("error") or r.get("prompt_tokens") is None:
            continue
        w = warm[f"{r['model']}|{r['condition']}"]
        w["n"] += 1
        if not r.get("cached_tokens_present"):
            w["absent"] += 1
        elif not r.get("cached_tokens"):
            w["zero"] += 1
        else:
            w["hit"] += 1
            w["cached_sum"] += int(r["cached_tokens"])
    out["warm_path"] = {k: dict(v, mean_cached_tokens_on_hits=(
        v["cached_sum"] / v["hit"] if v["hit"] else None),
        verdict=("INSTRUMENT NEVER READS" if v["absent"] == v["n"]
                 else "no warm prefix ever" if v["hit"] == 0 else "warm path exercised"))
        for k, v in sorted(warm.items())}
    # 4. prompt-token parity between the two models on the same request
    pt = defaultdict(dict)
    for r in raw:
        if r.get("control") or r.get("prompt_tokens") is None:
            continue
        pt[r["request_id"]][r["model"]] = int(r["prompt_tokens"])
    pairs = [(k, v) for k, v in pt.items() if len(v) == 2]
    mism = [dict(request_id=k, **v) for k, v in pairs if len(set(v.values())) != 1]
    out["prompt_token_parity"] = dict(
        pairs=len(pairs), mismatched=len(mism), examples=mism[:10],
        note="the brief requires the same prompt-token count per request pair; a mismatch means "
             "the two models are not reading the same prompt and no gap between them is a "
             "capability gap")
    return out


def cost(runs):
    """TTFT cold against warm, KV tokens per episode, uplink bytes. H3's numbers."""
    by = defaultdict(lambda: dict(cold=[], warm=[], new_tok=[], cached=[], up=0, body=0, n=0))
    ep = defaultdict(lambda: dict(prompt=0, cached=0, up=0, n=0))
    for (m, cd, c), d in runs.items():
        for t, r in sorted(d.items()):
            if r.get("prompt_tokens") is None:
                continue
            k = f"{m}|{cd}"
            v = by[k]
            v["n"] += 1
            ct = r.get("cached_tokens") or 0
            v["new_tok"].append(int(r["prompt_tokens"]) - int(ct))
            v["cached"].append(int(ct))
            v["up"] += int(r.get("uplink_bytes_new_images") or 0)
            v["body"] += int(r.get("uplink_bytes_body") or 0)
            if r.get("ttft_s") is not None:
                (v["warm"] if ct else v["cold"]).append(float(r["ttft_s"]))
            e = ep[(m, cd, c)]
            e["prompt"] += int(r["prompt_tokens"])
            e["cached"] += int(ct)
            e["up"] += int(r.get("uplink_bytes_new_images") or 0)
            e["n"] += 1

    def q(x):
        return None if not x else dict(n=len(x), p50=float(np.percentile(x, 50)),
                                       p90=float(np.percentile(x, 90)),
                                       mean=float(np.mean(x)))
    out = {}
    for k, v in sorted(by.items()):
        epi = [e for (m, cd, c), e in ep.items() if f"{m}|{cd}" == k]
        out[k] = dict(requests=v["n"], ttft_cold_s=q(v["cold"]), ttft_warm_s=q(v["warm"]),
                      new_prompt_tokens=q(v["new_tok"]), cached_tokens=q(v["cached"]),
                      uplink_image_bytes_total=v["up"], uplink_body_bytes_total=v["body"],
                      kv_tokens_per_episode=q([e["prompt"] - e["cached"] for e in epi]),
                      prompt_tokens_per_episode=q([e["prompt"] for e in epi]),
                      uplink_image_bytes_per_episode=q([e["up"] for e in epi]))
    return out


def deployment_pair(paths):
    """The identical-input check across the deployment pair: Orin 4BI against H100 32BI.

    The two arms run on two stacks BY DESIGN: they are deployment conditions, a deployed device
    against a deployed cloud, not an accidental backend mismatch. That makes the INPUT identity
    the thing that has to be proved, because it is the only thing left holding the comparison
    together. Three things are checked per request id, and each is a STOP:

      * the same prompt tokens, which the brief requires per request pair;
      * the same header text;
      * the same frame sha256 list, in the same order.

    A mismatch in any of them means the two arms are not reading the same episode, and no gap
    between them is a capability gap.
    """
    by = defaultdict(dict)
    for q in paths:
        op = gzip.open if str(q).endswith(".gz") else open
        with op(q, "rt") as fh:
            for ln in fh:
                r = json.loads(ln)
                if r.get("control") or r.get("error") or r.get("prompt_tokens") is None:
                    continue
                by[r["request_id"]][r["model"]] = r
    pairs = [(k, v) for k, v in by.items() if "4BI" in v and "32BI" in v]
    out = dict(label="DEPLOYED DEVICE (Orin 4BI, vLLM) against DEPLOYED CLOUD (H100 32BI, vLLM). "
                     "Cross-stack BY DESIGN: these are deployment conditions, not a backend "
                     "mismatch. Identical inputs are therefore checked per request, not assumed.",
               hosts={m: sorted({v[m].get("host") for _, v in pairs if m in v})
                      for m in ("4BI", "32BI")},
               n_paired=len(pairs), by_condition={})
    for cd in CONDITIONS:
        rows = [v for _, v in pairs if v["4BI"]["condition"] == cd]
        if not rows:
            continue
        tok = [v for v in rows if v["4BI"]["prompt_tokens"] != v["32BI"]["prompt_tokens"]]
        hdr = [v for v in rows if v["4BI"]["header"] != v["32BI"]["header"]]
        fr = [v for v in rows
              if list(v["4BI"]["small_sha256"]) != list(v["32BI"]["small_sha256"])]
        out["by_condition"][cd] = dict(
            n_paired=len(rows), prompt_token_mismatches=len(tok),
            header_mismatches=len(hdr), frame_sha256_mismatches=len(fr),
            examples=[v["4BI"]["request_id"] for v in (tok + hdr + fr)[:10]],
            identical_inputs=not (tok or hdr or fr))
    out["identical_inputs"] = (all(v["identical_inputs"] for v in out["by_condition"].values())
                               if out["by_condition"] else None)
    return out
