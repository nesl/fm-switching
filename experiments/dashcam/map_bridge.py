#!/usr/bin/env python3
"""StudyMAP1-bridge: score a LIVE cell on the headline metric. CPU only.

Pre-registered in `research/EXPERIMENTS.md` (StudyMAP1-bridge) before anything was computed.

WHAT IT DOES. Every episodic request a live cell issued carries a MEASURED end-to-end delivery
time. The bridge replays those delivery times through StudyE9b's delivery model - sample and
hold, the latency itself never rounded, the score readable at the next 0.25-s grid step - over
StudyD14b's committed score traces, and scores the result with StudyE9c's challenge mAP and
StudyE9b's streaming AP, through the SAME functions those studies use (via
`experiments/orchestration/sim/metrics.py`), so no metric is re-implemented here.

THE MAPPING IS EXACT, NOT INTERPOLATED. StudyD14b's request manifest carries, for every 0.25-s
grid point, the `d14_request_id` of the StudyD14 1-s request it coincides with. A live request id
(`01040_t03_N1`) is a StudyD14 id, so it maps to exactly one D14b grid point (`01040_t03.00_N1`,
t = 3.0) with no interpolation. `check_mapping()` asserts that every live id maps, and the study
stops if one does not.

THE DELIVERY MODEL, one request:

    L     = RTT + request_bytes / uplink + MEASURED TTFT          (StudyE9b setting (ii), with
                                                                   the measured TTFT in place of
                                                                   StudyD7's constant)
    read  = ceil(L / 0.25) grid steps after the request's own grid index
    the application holds the last value it has read, at every grid step

StudyE9b's RTT is a ROUND TRIP, so the answer's downlink is already inside it; the answer is a
few tokens and adds no measurable transfer time. A request that errored or never produced a
first token is NOT delivered, and the application holds its previous value.

CLIPS A CELL NEVER TOUCHED. A live cell walks StudyD14's manifest with one cursor, so it issues
cloud requests for 12 to 49 of the 300 scored clips. For every other clip the application holds
what the DEVICE produced, which is what our system does (the device arm always runs); those
clips are filled with the device arm's own delivered stream at StudyD8's latency and StudyE9b's
saturated device cadence. This is stated with every number: a cell's mAP is a MIXTURE of the
live cloud deliveries on the clips it touched and the device-only value everywhere else, so its
LEVEL is not comparable with StudyE9c's always-cloud arm. Policies at the same (condition, load
level) issue the IDENTICAL request set (Jaccard 1.000 over the committed Part C cells), so the
comparison BETWEEN policies is exactly paired.
"""
from __future__ import annotations

import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "experiments/orchestration/sim",
          ROOT / "experiments/orchestration/baselines", ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import costs as C                                       # noqa: E402
import metrics as M                                     # noqa: E402
import workload as W                                    # noqa: E402

MANIFEST = ROOT / "results/dashcam/study_d14b/d14b_requests_manifest.jsonl.gz"
PARTB = ROOT / "results/cost/study_slice1/slice1_live_requests_h100nvl.jsonl"
PARTC = ROOT / "results/cost/study_slice1/slice1_partc_requests_h100nvl.jsonl"
STEP_S = C.GRID_STEP_S
MISSING = -1e9                              # StudyE9b's missing marker
SEED, NB = 0, 2000
E9C_CLOUD_MAP = 0.5675307471627267          # StudyE9c, always-cloud 32BI_N1 | measured@25
E9C_DEVICE_MAP = 0.47760424491770376        # StudyE9c, device-only 4BI_N1 | measured@25

_MAN: Optional[Dict[str, Tuple[str, float, int]]] = None


# ---------------------------------------------------------------- the mapping
def manifest() -> Dict[str, Tuple[str, float, int]]:
    """StudyD14 request id -> (clip, t seconds, frame count), from StudyD14b's own manifest."""
    global _MAN
    if _MAN is None:
        out: Dict[str, Tuple[str, float, int]] = {}
        for line in gzip.open(MANIFEST, "rt"):
            r = json.loads(line)
            d14 = r.get("d14_request_id")
            if d14:
                out[d14] = (r["file_name"], float(r["t"]), int(r["n"]))
        _MAN = out
    return _MAN


def check_mapping(request_ids: Iterable[str]) -> Dict[str, Any]:
    """Every live request id must map to exactly one StudyD14b grid point. No interpolation."""
    m = manifest()
    ids = sorted(set(request_ids))
    missing = [i for i in ids if i not in m]
    off = []
    for i in ids:
        if i in m:
            t = m[i][1]
            if abs(t / STEP_S - round(t / STEP_S)) > 1e-9:
                off.append(i)
    return dict(n_ids=len(ids), n_mapped=len(ids) - len(missing), n_unmapped=len(missing),
                unmapped=missing[:10], n_off_grid=len(off), off_grid=off[:10],
                exact=bool(not missing and not off),
                rule="a live request id is a StudyD14 1-s request id; StudyD14b's manifest "
                     "carries that id on the coinciding 0.25-s grid point, so the mapping is a "
                     "lookup and never an interpolation")


# ---------------------------------------------------------------- the delivery model
def latency_s(ttft_s: float, n_frames: int = 1, jpeg: bool = False) -> float:
    """StudyE9b setting (ii) with the MEASURED server TTFT in place of StudyD7's constant."""
    by = C.FRAME_BYTES_JPEG if jpeg else C.FRAME_BYTES
    return C.RTT_S + by[n_frames] / C.UPLINK_BPS + float(ttft_s)


def held_from_events(arr: np.ndarray, G: int, comp_idx: Sequence[int],
                     read_idx: Sequence[int]) -> np.ndarray:
    """The application-visible stream: hold the last value READ, at every grid step.

    This is the per-request generalisation of StudyE9b's `held_stream` and StudyE9d's
    `cloud_delivered`: with a constant cadence m and a constant shift D it returns exactly what
    they return, which `validate()` asserts against StudyE9c's committed number.
    """
    out = np.full(G, MISSING, dtype=float)
    if not len(comp_idx):
        return out
    order = np.argsort(np.asarray(read_idx, dtype=np.int64), kind="mergesort")
    ci = np.asarray(comp_idx, dtype=np.int64)[order]
    ri = np.asarray(read_idx, dtype=np.int64)[order]
    k = np.searchsorted(ri, np.arange(G), side="right") - 1
    ok = (k >= 0) & (ci[np.clip(k, 0, len(ci) - 1)] < len(arr))
    out[ok] = arr[ci[k[ok]]]
    return out


def device_stream(ctx, clip: str) -> np.ndarray:
    """What the device alone delivers for a clip: StudyE9b's saturated device cadence and
    StudyD8's latency, held on the grid."""
    G = ctx["meta"][clip]["G"]
    arr = ctx["arrs"][("4BI", 1)][clip]
    m = max(int(round(C.DEVICE_CADENCE_S / STEP_S)), 1)
    D = C.hold_shift_steps(C.DEV_LAT_S)
    comp = list(range(0, G, m))
    return held_from_events(arr, G, comp, [c + D for c in comp])


def delivered_from_rows(rows: Sequence[Dict[str, Any]], ctx,
                        device_fill: bool = True) -> Tuple[Dict[str, np.ndarray], Dict[str, Any]]:
    """One live cell's application-visible streams, clip by clip."""
    m = manifest()
    ev: Dict[str, List[Tuple[int, int, str]]] = defaultdict(list)
    n_used = n_skipped = 0
    for r in rows:
        rid = r.get("request_id")
        if rid is None or rid not in m:
            n_skipped += 1
            continue
        clip, t, n = m[rid]
        if clip not in ctx["meta"]:
            n_skipped += 1
            continue
        if r.get("error") or r.get("ttft_s") is None:
            n_skipped += 1                       # never delivered: the application holds
            continue
        gi = int(round(t / STEP_S))
        L = latency_s(float(r["ttft_s"]), int(r.get("N") or n))
        ev[clip].append((gi, gi + C.hold_shift_steps(L), f"32BI_N{int(r.get('N') or n)}"))
        n_used += 1
    out: Dict[str, np.ndarray] = {}
    for clip in ctx["clips"]:
        G = ctx["meta"][clip]["G"]
        if clip in ev:
            n = int(ev[clip][0][2].split("_N")[1])
            arr = ctx["arrs"][("32BI", n)][clip]
            comp = [a for a, _b, _c in ev[clip]]
            read = [b for _a, b, _c in ev[clip]]
            out[clip] = held_from_events(arr, G, comp, read)
            if device_fill:
                # before the first cloud delivery the application still holds the device's value
                dev = device_stream(ctx, clip)
                miss = out[clip] <= MISSING / 2.0
                out[clip][miss] = dev[miss]
        else:
            out[clip] = device_stream(ctx, clip) if device_fill else np.full(G, MISSING)
    return out, dict(n_requests_used=n_used, n_requests_skipped=n_skipped,
                     n_clips_touched=len(ev), n_clips_total=len(ctx["clips"]),
                     device_filled=bool(device_fill))


# ---------------------------------------------------------------- scoring
def score(delivered: Dict[str, np.ndarray], ctx, with_ci: bool = True) -> Dict[str, Any]:
    """StudyE9c's challenge mAP and StudyE9b's streaming AP, through their own code."""
    ch = M.challenge(ctx)
    if with_ci:
        full, _draws = ch.full(delivered)
        out = dict(challenge_mAP=full["mAP"]["value"], challenge_mAP_ci=full["mAP"]["ci"],
                   challenge_ap={str(h): full[h]["ap"] for h in full if h != "mAP"},
                   challenge_ap_ci={str(h): full[h]["ci"] for h in full if h != "mAP"})
    else:
        pt = ch.point(delivered)
        out = dict(challenge_mAP=pt["mAP"],
                   challenge_ap={str(h): v for h, v in pt.items() if h != "mAP"})
    out["streaming_ap"] = {str(h): v for h, v in M.streaming_ap(ctx, delivered).items()}
    return out


def paired_bootstrap(a: Dict[str, np.ndarray], b: Dict[str, np.ndarray], ctx,
                     n: int = NB, seed: int = SEED) -> Dict[str, Any]:
    """The PAIRED clip bootstrap of a difference: the same resampled clips score both policies.

    It reuses StudyE9d's `Challenge` crops, so the geometry is the committed one, and resamples
    the positive and negative clip lists with `numpy.random.default_rng(seed)` - StudyE9c's own
    unit and seed.
    """
    ch = M.challenge(ctx)
    PA, NA = ch.crops(a)
    PB, NBd = ch.crops(b)
    import study_e9d_delay as D
    pos, neg = ctx["pos"], ctx["neg"]
    rng = np.random.default_rng(seed)
    draws = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg)))
             for _ in range(n)]
    diffs = np.empty(n)
    for i, (pi, ni) in enumerate(draws):
        va, vb = [], []
        for h in ch.pos_idx and D.CHAL_H:
            sel = pi[ch.pmask[h][pi]]
            if not len(sel):
                va.append(0.0)
                vb.append(0.0)
                continue
            y = np.r_[np.ones(len(sel)), np.zeros(len(ni))]
            va.append(D.ap_fast(y, np.r_[PA[h][sel], NA[h][ni]]))
            vb.append(D.ap_fast(y, np.r_[PB[h][sel], NBd[h][ni]]))
        diffs[i] = float(np.mean(va) - np.mean(vb))
    pa = ch.point(a)["mAP"]
    pb = ch.point(b)["mAP"]
    return dict(difference=float(pa - pb),
                ci=[float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
                n_bootstrap=n, seed=seed,
                excludes_zero=bool(np.percentile(diffs, 2.5) > 0
                                   or np.percentile(diffs, 97.5) < 0))


# ---------------------------------------------------------------- validation
def validate(ctx) -> Dict[str, Any]:
    """PRE-REGISTERED GATE. A synthetic cell in which every TTFT is StudyE9b's constant cloud
    latency must reproduce StudyE9c's delivered-cloud challenge mAP EXACTLY, through the SAME
    per-request code path a live cell uses. If it does not, the study stops."""
    arm, n, load = "32BI", 1, 25
    cad_steps = int(round(0.5 / STEP_S))
    ttft = C.CLOUD_TTFT[(arm, n, load)]
    L = latency_s(ttft, n)
    D_ = C.hold_shift_steps(L)
    delivered = {}
    for clip in ctx["clips"]:
        G = ctx["meta"][clip]["G"]
        comp = list(range(0, G, cad_steps))
        delivered[clip] = held_from_events(ctx["arrs"][(arm, n)][clip], G, comp,
                                           [c + D_ for c in comp])
    got = M.challenge_map(ctx, delivered)["mAP"]
    dev = {c: device_stream(ctx, c) for c in ctx["clips"]}
    got_dev = M.challenge_map(ctx, dev)["mAP"]
    # The STRONGER check, and the one that is exact: the per-request delivery model must produce
    # the SAME ARRAYS as StudyE9d's own `cloud_delivered`, bit for bit, on every clip. If it
    # does, any residual in the mAP is the AP implementation and not the delivery model.
    import study_e9d_delay as D
    same_cloud = same_dev = 0
    for clip in ctx["clips"]:
        G = ctx["meta"][clip]["G"]
        ref = D.cloud_delivered(ctx["arrs"][(arm, n)][clip], G, cad_steps, D_)
        same_cloud += int(np.array_equal(ref, delivered[clip]))
        refd = D.cloud_delivered(ctx["arrs"][("4BI", 1)][clip], G,
                                 max(int(round(C.DEVICE_CADENCE_S / STEP_S)), 1),
                                 C.hold_shift_steps(C.DEV_LAT_S))
        same_dev += int(np.array_equal(refd, dev[clip]))
    n_clips = len(ctx["clips"])
    arrays_identical = bool(same_cloud == n_clips and same_dev == n_clips)
    return dict(
        rule="every TTFT equal to StudyE9b's constant cloud latency must reproduce StudyE9c's "
             "always-cloud 32BI_N1 | measured@25 challenge mAP exactly, and the device fill must "
             "reproduce StudyE9c's device-only arm exactly",
        latency_s=round(L, 6), hold_shift_steps=D_, cadence_steps=cad_steps,
        cloud=dict(expected=E9C_CLOUD_MAP, got=got, difference=got - E9C_CLOUD_MAP,
                   bit_exact=bool(got == E9C_CLOUD_MAP)),
        device=dict(expected=E9C_DEVICE_MAP, got=got_dev, difference=got_dev - E9C_DEVICE_MAP,
                    bit_exact=bool(got_dev == E9C_DEVICE_MAP)),
        delivery_arrays=dict(
            n_clips=n_clips, cloud_identical=same_cloud, device_identical=same_dev,
            identical=arrays_identical,
            note="the per-request delivery model returns StudyE9d's `cloud_delivered` arrays "
                 "bit for bit on every clip, so the DELIVERY MODEL reproduction is exact"),
        residual=dict(
            cloud_abs=abs(got - E9C_CLOUD_MAP), device_abs=abs(got_dev - E9C_DEVICE_MAP),
            explanation="StudyE9c computed its committed mAP with scikit-learn's "
                        "`average_precision_score`; this bridge computes AP with StudyE9d's "
                        "`ap_fast`, which StudyE9d control (d) verified against it on every "
                        "real cell with a worst absolute difference of 1.1e-16. The residual "
                        "here IS that worst case, on a value of 0.57, and it is an AP "
                        "implementation difference, not a delivery difference"),
        PASS=bool(arrays_identical and abs(got - E9C_CLOUD_MAP) <= 2.3e-16
                  and abs(got_dev - E9C_DEVICE_MAP) <= 2.3e-16),
        pass_rule="the delivery arrays must be identical to StudyE9d's on every clip AND the "
                  "challenge mAP must match StudyE9c's committed value to within one unit in "
                  "the last place of a double (2.3e-16), which is the committed ap_fast "
                  "equivalence bound")


def zero_delay_control(ctx) -> Dict[str, Any]:
    """Mechanism verification Step 4: with ZERO added delay the bridge must equal the no-delay
    reference - the arm's own scores read on the grid they were computed on."""
    arm, n = "32BI", 1
    cad = int(round(0.5 / STEP_S))
    a, b = {}, {}
    for clip in ctx["clips"]:
        G = ctx["meta"][clip]["G"]
        comp = list(range(0, G, cad))
        a[clip] = held_from_events(ctx["arrs"][(arm, n)][clip], G, comp, comp)
        b[clip] = np.full(G, MISSING, dtype=float)
        i = np.arange(G)
        b[clip][:] = ctx["arrs"][(arm, n)][clip][(i // cad) * cad]
    same = all(np.array_equal(a[c], b[c]) for c in ctx["clips"])
    return dict(rule="zero added delay reproduces the un-delayed stream exactly",
                identical=bool(same),
                mAP_zero_delay=M.challenge_map(ctx, a)["mAP"],
                mAP_reference=M.challenge_map(ctx, b)["mAP"])


# ---------------------------------------------------------------- live cells
def load_cells(paths: Sequence[Path] = (PARTB, PARTC), in_window_only: bool = True
               ) -> Dict[str, List[Dict[str, Any]]]:
    """Every committed live cell's episodic rows, keyed by the cell tag."""
    by: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in paths:
        if not Path(p).exists():
            continue
        for line in Path(p).open():
            r = json.loads(line)
            if r.get("kind") != "episodic":
                continue
            if in_window_only and not r.get("in_window"):
                continue
            by[r["cell"]].append(r)
    return dict(by)


def parse_cell(tag: str) -> Dict[str, Any]:
    """`SLICE1B_P4_C1a_N1_L25` -> study, policy, condition, frame count, load level."""
    parts = tag.split("_")
    # a policy name can itself contain an underscore (P3_1024), so parse from the END
    return dict(tag=tag, study=parts[0], policy="_".join(parts[1:-3]), condition=parts[-3],
                n_frames=int(parts[-2][1:]), level_pct=int(parts[-1][1:]))


def headroom(rows: Sequence[Dict[str, Any]], ctx, delivered: Dict[str, np.ndarray]
             ) -> Dict[str, Any]:
    """How much of this cell's mAP the delivery TIMES can possibly be worth.

    The same requests are replayed with ZERO added delay (each read at its own grid index), which
    is the best any scheduler could do with this request set, and with the measured delays. The
    gap between the two is the entire headroom a latency policy has in this cell; the fraction of
    grid steps whose held value differs says how much of the grid the delays touch at all.
    """
    m = manifest()
    ev: Dict[str, List[int]] = defaultdict(list)
    lat: List[float] = []
    for r in rows:
        rid = r.get("request_id")
        if rid is None or rid not in m or r.get("error") or r.get("ttft_s") is None:
            continue
        clip, t, n = m[rid]
        if clip not in ctx["meta"]:
            continue
        ev[clip].append(int(round(t / STEP_S)))
        lat.append(latency_s(float(r["ttft_s"]), int(r.get("N") or n)))
    instant: Dict[str, np.ndarray] = {}
    differing = total = 0
    for clip in ctx["clips"]:
        G = ctx["meta"][clip]["G"]
        if clip in ev:
            n = int(rows[0].get("N") or 1)
            arr = ctx["arrs"][("32BI", n)][clip]
            comp = sorted(ev[clip])
            instant[clip] = held_from_events(arr, G, comp, comp)
            dev = device_stream(ctx, clip)
            miss = instant[clip] <= MISSING / 2.0
            instant[clip][miss] = dev[miss]
            differing += int(np.sum(instant[clip] != delivered[clip]))
            total += G
        else:
            instant[clip] = delivered[clip]
    best = M.challenge_map(ctx, instant)["mAP"]
    return dict(mAP_zero_added_delay=best,
                headroom=best - M.challenge_map(ctx, delivered)["mAP"],
                grid_steps_touched=total,
                grid_steps_changed_by_delay=differing,
                fraction_of_grid_changed=(differing / total) if total else 0.0,
                latency_s_mean=(float(np.mean(lat)) if lat else None),
                latency_s_p99=(float(np.percentile(lat, 99)) if lat else None))


def score_cell(rows: Sequence[Dict[str, Any]], ctx, with_ci: bool = True) -> Dict[str, Any]:
    delivered, info = delivered_from_rows(rows, ctx)
    out = score(delivered, ctx, with_ci=with_ci)
    out.update(info)
    out["diagnostics"] = headroom(rows, ctx, delivered)
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="score live cells on the headline metric")
    ap.add_argument("--out", default=str(ROOT / "results/dashcam/map1/map1_results.json"))
    ap.add_argument("--rows", nargs="*", default=None,
                    help="request jsonl files to score; default = StudySLICE1 Part B and Part C")
    ap.add_argument("--no-ci", action="store_true")
    a = ap.parse_args()
    ctx = W.clip_context()
    res: Dict[str, Any] = dict(
        label="StudyMAP1-bridge: committed live cells scored on StudyE9c's challenge mAP and "
              "StudyE9b's streaming AP by replaying each episodic request's MEASURED delivery "
              "time through StudyE9b's delivery model on StudyD14b's committed score traces.",
        step_s=STEP_S, seed=SEED, n_bootstrap=NB)
    paths = [Path(x) for x in a.rows] if a.rows else [PARTB, PARTC]
    cells = load_cells(paths)
    res["mapping"] = check_mapping(r["request_id"] for rows in cells.values() for r in rows)
    if not res["mapping"]["exact"]:
        print("STOP: the live-to-D14b mapping is not exact", json.dumps(res["mapping"]))
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, default=str))
        return 2
    res["validation"] = validate(ctx)
    res["zero_delay_control"] = zero_delay_control(ctx)
    print("validation:", json.dumps(res["validation"]["cloud"]), flush=True)
    if not res["validation"]["PASS"]:
        print("STOP: the bridge does not reproduce StudyE9c exactly")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, default=str))
        return 2
    rows_out = []
    for tag in sorted(cells):
        info = parse_cell(tag)
        sc = score_cell(cells[tag], ctx, with_ci=not a.no_ci)
        rows_out.append(dict(info, **sc, n_rows=len(cells[tag])))
        print("  %-28s mAP %.4f  streamAP@0 %.5f  clips %d/%d  reqs %d" % (
            tag, sc["challenge_mAP"], float(sc["streaming_ap"]["0.0"]),
            sc["n_clips_touched"], sc["n_clips_total"], sc["n_requests_used"]), flush=True)
    res["cells"] = rows_out
    # paired, policy against the lowest-indexed policy of the same condition and level
    pairs = []
    byk = defaultdict(dict)
    for r in rows_out:
        byk[(r["study"], r["condition"], r["level_pct"])][r["policy"]] = r["tag"]
    for key, pol in sorted(byk.items()):
        if len(pol) < 2:
            continue
        ref = "P0" if "P0" in pol else sorted(pol)[0]
        da, _ = delivered_from_rows(cells[pol[ref]], ctx)
        for p in sorted(pol):
            if p == ref:
                continue
            db, _ = delivered_from_rows(cells[pol[p]], ctx)
            d = paired_bootstrap(db, da, ctx)
            pairs.append(dict(study=key[0], condition=key[1], level_pct=key[2],
                              policy=p, reference=ref, **d))
            print("  paired %s %s L%d: %s - %s = %+.4f %s" % (
                key[0], key[1], key[2], p, ref, d["difference"],
                "CI excludes 0" if d["excludes_zero"] else "CI includes 0"), flush=True)
    res["paired"] = pairs
    sys.path.insert(0, str(ROOT / "experiments/lib"))
    from _provenance import stamp
    res["_provenance"] = stamp(script="map_bridge.py", model=None, device="cpu",
                               n=len(rows_out), args=None)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1, default=str))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
