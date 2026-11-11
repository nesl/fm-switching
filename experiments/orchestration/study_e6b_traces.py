#!/usr/bin/env python3
"""StudyE6b-mobility — network outage traces. OFFLINE; CPU only; no GPU, no server, no inference.

Builds per-second reachability series for three regimes and writes them to
results/orchestration/study_e6b/e6b_traces.npz plus a JSON summary.

  outdoor_driving : Irish 5G, outage second == (cell_id == -1). E31b's valid signal.
                    State=D/I is NEVER used (E31 Part C is INVALID).
  indoor          : herolab per-sample datalog, C_level_a (whitespace index 19) median per
                    second; outage second == median RSSI < -75 dBm.
  synthetic_<f>   : two-state process, outage runs drawn from the Irish empirical
                    gap-duration distribution, connected runs geometric with the mean that
                    makes the stationary outage fraction f. LABELLED SYNTHETIC.
"""
import json, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

OUT = ROOT / "results/orchestration/study_e6b"
SEED = 0
RSSI_OUTAGE_DBM = -75.0
SYNTH_FRACTIONS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.30)
SYNTH_N_SESSIONS, SYNTH_LEN_S = 16, 3600


def runs_of(x, val):
    """Lengths of maximal runs equal to val in a 1-D 0/1 array."""
    out, n = [], 0
    for v in x:
        if v == val:
            n += 1
        elif n:
            out.append(n); n = 0
    if n:
        out.append(n)
    return out


def irish():
    import csv
    rows = list(csv.DictReader(open(ROOT / "results/cost/e31_network/reachability_series.csv")))
    by = defaultdict(list)
    for r in rows:
        by[int(r["session_id"])].append((int(r["unix_t"]), r["cell_id"]))
    sess = {}
    for sid, v in by.items():
        v.sort()
        t0 = v[0][0]
        # the series is 1 Hz; assert it is contiguous so index == seconds since session start
        assert [t - t0 for t, _ in v] == list(range(len(v))), f"irish session {sid} not contiguous"
        sess[sid] = np.array([0 if c == "-1" else 1 for _, c in v], dtype=np.int8)
    return sess


def herolab():
    sess = {}
    for i in range(1, 8):
        p = ROOT / f"results/cost/e31_network/raw/herolab_rssi/Dataset{i}.datalog"
        per_s = defaultdict(list)
        for ln, line in enumerate(open(p)):
            f = line.split()
            if ln == 0 or len(f) < 20:
                continue
            per_s[int(f[1])].append(float(f[19]))
        ts = sorted(per_s)
        if not ts:
            continue
        t0, t1 = ts[0], ts[-1]
        a = np.ones(t1 - t0 + 1, dtype=np.int8)       # seconds with no sample inherit "connected"
        gaps = 0
        for t in range(t0, t1 + 1):
            v = per_s.get(t)
            if v is None:
                gaps += 1
                continue
            a[t - t0] = 0 if float(np.median(v)) < RSSI_OUTAGE_DBM else 1
        sess[i] = a
        sess.setdefault("_gaps", {})
        sess["_gaps"][i] = gaps
    return sess


def synthetic(out_runs, frac, rng):
    """Two-state process; outage runs resampled from out_runs, connected runs geometric."""
    if frac <= 0:
        return {s: np.ones(SYNTH_LEN_S, dtype=np.int8) for s in range(SYNTH_N_SESSIONS)}
    mu_out = float(np.mean(out_runs))
    mu_con = mu_out * (1.0 - frac) / frac
    p = 1.0 / max(mu_con, 1.0)
    sess = {}
    for s in range(SYNTH_N_SESSIONS):
        a, i = np.ones(SYNTH_LEN_S, dtype=np.int8), 0
        i += int(rng.geometric(p))
        while i < SYNTH_LEN_S:
            d = int(rng.choice(out_runs))
            a[i:i + d] = 0
            i += d + int(rng.geometric(p))
        sess[s] = a
    return sess


def summarise(sess):
    tot = sum(len(a) for a in sess.values())
    out = sum(int((a == 0).sum()) for a in sess.values())
    r = [n for a in sess.values() for n in runs_of(a, 0)]
    return dict(n_sessions=len(sess), total_s=tot, outage_s=out,
                outage_fraction=out / tot if tot else 0.0, n_outage_runs=len(r),
                outage_run_s=dict(p50=float(np.median(r)) if r else 0.0,
                                  p95=float(np.percentile(r, 95)) if r else 0.0,
                                  max=int(max(r)) if r else 0, mean=float(np.mean(r)) if r else 0.0),
                session_lengths=sorted(len(a) for a in sess.values()))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    regimes, summary = {}, {}

    ir = irish()
    regimes["outdoor_driving"] = ir
    summary["outdoor_driving"] = summarise(ir)
    summary["outdoor_driving"]["signal"] = "Irish 5G cell_id == -1 (E31b corrected signal; State=D/I never used)"

    hl = herolab()
    gaps = hl.pop("_gaps", {})
    regimes["indoor"] = hl
    summary["indoor"] = summarise(hl)
    summary["indoor"]["signal"] = f"herolab C_level_a median per second < {RSSI_OUTAGE_DBM} dBm"
    summary["indoor"]["seconds_without_a_sample_treated_connected"] = gaps

    out_runs = np.array([n for a in ir.values() for n in runs_of(a, 0)], dtype=int)
    rng = np.random.default_rng(SEED)
    for f in SYNTH_FRACTIONS:
        k = f"synthetic_{int(round(f * 100))}pct"
        s = synthetic(out_runs, f, rng)
        regimes[k] = s
        summary[k] = summarise(s)
        summary[k]["signal"] = ("SYNTHETIC two-state; outage runs resampled from the Irish empirical "
                                f"gap-duration distribution (n={len(out_runs)}), connected runs geometric; "
                                f"target outage fraction {f}")

    flat = {}
    for rg, sess in regimes.items():
        for sid, a in sess.items():
            flat[f"{rg}|{sid}"] = a
    np.savez_compressed(OUT / "e6b_traces.npz", **flat)
    res = dict(label="StudyE6b-mobility network traces. OFFLINE; CPU only; no GPU, no inference.",
               at=datetime.now().isoformat(), seed=SEED, regimes=summary,
               irish_outage_run_distribution=dict(n=int(len(out_runs)),
                                                  counts={str(int(v)): int((out_runs == v).sum())
                                                          for v in np.unique(out_runs)}))
    res["_provenance"] = stamp(script="study_e6b_traces.py", model=None, device="cpu",
                               n=sum(len(a) for s in regimes.values() for a in s.values()), args=None)
    (OUT / "e6b_traces.json").write_text(json.dumps(res, indent=1))
    for k, v in summary.items():
        print(f"{k:22s} sessions={v['n_sessions']:3d} total_s={v['total_s']:7d} "
              f"outage={v['outage_fraction']:.4f} runs={v['n_outage_runs']:5d} "
              f"p50={v['outage_run_s']['p50']:.0f} max={v['outage_run_s']['max']}")


if __name__ == "__main__":
    main()
