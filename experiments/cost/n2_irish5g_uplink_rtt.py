#!/usr/bin/env python3
"""N2 (D215, D75): are the committed Irish 5G bandwidth percentiles UPLINK or DOWNLINK?

D75 carries the caveat "after confirming they are uplink figures" and it has never been
confirmed. `experiments/cost/e31_network.py:84` reads the column `DL_bitrate`, so the committed
0.8954 / 9.5775 / 102.898 are DOWNLINK. This script reproduces that number as a POSITIVE
CONTROL (if the pipeline cannot reproduce the committed DL percentiles, the pipeline is broken,
not the committed value), then extracts the UPLINK percentiles from `UL_bitrate`, the RTT
percentiles from `PINGAVG`, and the no-cell gap schedule per session from `CellID == -1`.

Binning follows e31_network.py exactly: per-integer-second bins, mean within the bin, NaN for an
empty second, NaN dropped before percentiles. Percentiles use numpy's linear interpolation, as
e31 does.

Every figure in the output is marked OBSERVED (read from the dataset) or CONSTRUCTED (derived).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
IRISH = REPO / "results/cost/e31_network/raw/irish5g/5G-production-dataset"


def parse_ts(ts: str) -> float:
    return datetime.datetime.strptime(ts, "%Y.%m.%d_%H.%M.%S").timestamp()


def load(path: Path):
    """Return per-second binned (dl, ul, ping, cell) lists for one session CSV."""
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                t = parse_ts(row["Timestamp"])
            except (ValueError, KeyError):
                continue
            def num(col):
                v = (row.get(col) or "").strip()
                try:
                    return float(v)
                except ValueError:
                    return float("nan")
            cell_raw = (row.get("CellID") or "").strip()
            cell = int(cell_raw) if cell_raw.lstrip("-").isdigit() else -1
            state = 1.0 if (row.get("State") or "").strip() == "D" else 0.0
            rows.append((t, num("DL_bitrate"), num("UL_bitrate"), num("PINGAVG"), cell, state))
    if not rows:
        return None
    times = np.array([r[0] for r in rows])
    cols = {k: np.array([r[i] for r in rows]) for i, k in
            ((1, "dl"), (2, "ul"), (3, "ping"))}
    cells = np.array([r[4] for r in rows])
    states = np.array([r[5] for r in rows])
    t0, t1 = int(times[0]), int(times[-1])
    out = {k: [] for k in cols}
    cell_b, state_b = [], []
    for tb in np.arange(t0, t1 + 1):
        m = (times >= tb) & (times < tb + 1)
        if m.any():
            for k, v in cols.items():
                vv = v[m]
                vv = vv[~np.isnan(vv)]
                out[k].append(float(np.mean(vv)) if vv.size else float("nan"))
            cell_b.append(int(np.median(cells[m])))
            state_b.append(int(np.round(np.mean(states[m]))))
        else:
            for k in cols:
                out[k].append(float("nan"))
            cell_b.append(-1)
            state_b.append(0)
    out["cell"] = cell_b
    out["state"] = state_b
    out["n_binned_s"] = len(cell_b)
    out["duration_s"] = t1 - t0 + 1
    return out


def pct(vals, ps=(10, 50, 90, 25, 75, 95, 99)):
    a = np.array([v for v in vals if not np.isnan(v)], dtype=float)
    if a.size == 0:
        return dict(n=0)
    d = dict(n=int(a.size), min=round(float(a.min()), 4), max=round(float(a.max()), 4),
             mean=round(float(a.mean()), 4))
    for p in ps:
        d["p%d" % p] = round(float(np.percentile(a, p)), 4)
    return d


def gap_runs(cells):
    """Runs of CellID == -1 (no serving cell), in seconds, with their start offsets."""
    runs, start = [], None
    for i, c in enumerate(cells):
        if c == -1 and start is None:
            start = i
        elif c != -1 and start is not None:
            runs.append((start, i - start))
            start = None
    if start is not None:
        runs.append((start, len(cells) - start))
    return runs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--subset", default="Download/Driving")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    files = sorted((IRISH / a.subset).glob("*.csv"))
    if not files:
        raise SystemExit("no CSVs under %s" % (IRISH / a.subset))

    allc = {k: [] for k in ("dl", "ul", "ping", "dl_e31", "ul_e31")}
    per_session, sched = [], []
    total_bins = 0
    for sid, f in enumerate(files):
        s = load(f)
        if s is None:
            continue
        for k in ("dl", "ul", "ping"):
            allc[k].extend(s[k])
        for k, dst in (("dl", "dl_e31"), ("ul", "ul_e31")):
            for i, v in enumerate(s[k]):
                if s["state"][i] == 1 and not np.isnan(v) and v > 0:
                    allc[dst].append(v / 1000.0)
        total_bins += s["n_binned_s"]
        runs = gap_runs(s["cell"])
        per_session.append(dict(
            session_id=sid, file=f.name, binned_s=s["n_binned_s"],
            no_cell_s=sum(1 for c in s["cell"] if c == -1),
            n_gap_runs=len(runs),
            dl=pct(s["dl"], (10, 50, 90)), ul=pct(s["ul"], (10, 50, 90)),
            ping=pct(s["ping"], (50, 90, 99))))
        sched.append(dict(session_id=sid, file=f.name, binned_s=s["n_binned_s"],
                          gaps=[dict(start_s=st, dur_s=d) for st, d in runs]))

    gaps_all = [d for s in sched for d in (g["dur_s"] for g in s["gaps"])]
    nocell = sum(s["no_cell_s"] for s in per_session)
    res = dict(
        question="N2 (D215, D75): UPLINK or DOWNLINK percentiles, plus RTT and the no-cell gaps",
        dataset=dict(path=str(IRISH / a.subset), n_files=len(files),
                     columns_present=["DL_bitrate", "UL_bitrate", "PINGAVG", "CellID", "State"],
                     register="OBSERVED"),
        verdict=dict(
            committed_percentiles_are="DOWNLINK",
            evidence="experiments/cost/e31_network.py:84 reads row['DL_bitrate']; "
                     "experiments/cost/e31b_network.py:56-58 hard-codes the resulting "
                     "0.8954 / 9.5775 / 102.898 as BW_P10/P50/P90_MBPS",
            d75_caveat="REFUTED: the figures are not uplink",
            register="OBSERVED"),
        positive_control=dict(
            note="this pipeline must reproduce the COMMITTED DL percentiles or the pipeline is "
                 "broken, not the committed value",
            committed=dict(p10=0.8954, p50=9.5775, p90=102.898, n=28551,
                           source="results/cost/e31b_network/e31b_summary.json"),
            reproduced_dl_e31_recipe_mbit_s=pct(allc["dl_e31"]),
            raw_dl_kbit_s_all_bins=pct(allc["dl"]),
            recipe="State==D only, value>0 only, kbit/s divided by 1000 "
                   "(e31_network.py:293 '# kbps -> Mbps', :399 percentiles)",
            total_binned_s=total_bins, register="OBSERVED"),
        uplink=dict(
            e31_recipe_mbit_s=pct(allc["ul_e31"]),
            raw_ul_kbit_s_all_bins=pct(allc["ul"]),
            column="UL_bitrate", register="OBSERVED",
            VALIDITY=("THE COLUMN EXISTS BUT IS NOT AN UPLINK CAPACITY MEASURE. Every subset of "
                      "this dataset (Download, Netflix, Amazon_Prime) is a DOWNLOAD workload, so "
                      "UL_bitrate is the ACK and control traffic of a downloading app, not an "
                      "uplink-saturating transfer. DL_bitrate is near capacity because the app "
                      "saturates the downlink; UL_bitrate is not, and must NOT be used as a "
                      "per-device uplink for Tier 1."),
            register_validity="CONSTRUCTED judgement about an OBSERVED column"),
        rtt_ms=dict(values=pct(allc["ping"]), column="PINGAVG",
                    note="PINGAVG is '-' on most rows of this subset; n is the populated count",
                    register="OBSERVED"),
        no_cell_gaps=dict(
            total_no_cell_s=nocell, total_binned_s=total_bins,
            frac_no_cell=(round(nocell / total_bins, 6) if total_bins else None),
            n_runs=len(gaps_all),
            run_len_s=pct([float(x) for x in gaps_all], (50, 90, 95, 99)),
            histogram_s={str(k): int(sum(1 for x in gaps_all if x == k))
                         for k in sorted(set(gaps_all))},
            register="OBSERVED"),
        per_session=per_session,
        replayable_schedule=dict(
            definition="per session: offsets in BINNED SECONDS from that session's first sample "
                       "at which CellID == -1 begins, and the run length; a device replays its "
                       "assigned session's list, wrapping at binned_s",
            register="OBSERVED (offsets and lengths read from the data); the ASSIGNMENT of a "
                     "session to a device is CONSTRUCTED",
            sessions=sched),
    )
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("verdict", "positive_control", "uplink",
                                          "rtt_ms", "no_cell_gaps")}, indent=2, sort_keys=True))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
