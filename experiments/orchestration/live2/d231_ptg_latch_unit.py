#!/usr/bin/env python3
"""UNIT TEST of the D166 (3) latch and the D178 (3) per-type entry test, driven directly.

WHY A UNIT TEST WHEN THERE ARE CELLS. The dry cell cannot drive the alert or assistance channels
at all (the dry monitor service time is a constant 0.394966 s), so no cell this box can run
exercises the entry test on two of three channels, nor the exit path, nor the hysteresis BAND. A
cell-only proof would therefore report the latch as working while three of its four branches had
never executed. This drives `guard_state` with a hand-built observation so every branch is
reached, and prints the per-period trace a person can check by hand (CLAUDE.md Step 3).

REGISTER: UNIT, on a constructed observation. It proves the state machine's arithmetic and branch
coverage. It is NOT evidence that any branch is reachable in a real cell; that is the cells' job
and, for the alert channel, the s4 GPU cell's job.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

L = Path(sys.argv[1]).resolve()
for p in (L, L / "v5", L / "fleet", L / "hybrid", L.parent / "baselines", L.parents[1] / "lib"):
    sys.path.insert(0, str(p))

import arms_v5rules2 as R2        # noqa: E402
import share_admission as SA      # noqa: E402


class Cloud:
    def __init__(self, lat, q=None, r=None):
        self.latency_estimate_s = dict(lat)
        self.queued_by_class = dict(q or {})
        self.running_by_class = dict(r or {})


class Obs:
    def __init__(self, t, lat, q=None, r=None):
        self.now_s = float(t)
        self.cloud = Cloud(lat, q, r)


def arm(per_type=True, hyst=True, thresholds=None):
    a = R2.V5Rules2Arm(name="unit", guard_per_type=per_type, guard_hysteresis=hyst,
                       guard_lag_s_by_class=thresholds, guard_log=True)
    return a


OUT = {"study": "D166 (3) latch and D178 (3) per-type entry: UNIT branch coverage",
       "register": "UNIT, constructed observation; not evidence of reachability in a cell",
       "thresholds_under_test": dict(SA.GUARD_LAG_S_BY_CLASS),
       "exit_factor": R2.GUARD_EXIT_FACTOR_D166, "exit_hold_s": R2.GUARD_EXIT_HOLD_S_D166}

# ---------------------------------------------------------------- A: the per-type ENTRY test
# one channel at a time, each just over and just under ITS OWN threshold, with the other two at 0
rows = []
for cls, thr in sorted(SA.GUARD_LAG_S_BY_CLASS.items()):
    for delta, tag in ((+0.01, "just OVER"), (-0.01, "just UNDER")):
        a = arm(hyst=False)
        g = a.guard_state(Obs(1.0, {cls: thr + delta}))
        rows.append({"channel": cls, "threshold_s": thr, "lag_s": round(thr + delta, 4),
                     "case": tag, "by_lag": g["by_lag"], "active": g["active"],
                     "fired_classes": g["per_type"]["fired_classes"]})
OUT["A_per_type_entry_each_channel_alone"] = rows
OUT["A_PASS"] = all(r["by_lag"] == (r["case"] == "just OVER") for r in rows)
# the committed arm must NOT fire on any of these, which is the whole point of the build
ctrl = []
for cls, thr in sorted(SA.GUARD_LAG_S_BY_CLASS.items()):
    a = arm(per_type=False, hyst=False)
    g = a.guard_state(Obs(1.0, {cls: thr + 0.01}))
    ctrl.append({"channel": cls, "lag_s": round(thr + 0.01, 4),
                 "committed_2.0s_guard_fires": g["by_lag"]})
OUT["A_control_the_committed_guard_on_the_same_signals"] = ctrl
OUT["A_control_note"] = (
    "The committed guard fires on the recall channel at 2.41 s because 2.41 >= 2.0, and does NOT "
    "fire on alert at 0.81 s or assistance at 1.61 s. The assistance row is the absent link "
    "d230_guard_107.json found: the committed guard has no assistance channel to read at all, so "
    "it cannot fire on it at ANY value.")
a = arm(per_type=False, hyst=False)
OUT["A_control_committed_guard_blind_to_assistance_at_100s"] = a.guard_state(
    Obs(1.0, {"assistance": 100.0}))["by_lag"]

# ---------------------------------------------------------------- B: the latch, period by period
# a hand-checkable trace: enter on alert, then walk down through the BAND and below the exit bar
a = arm()
thr = dict(SA.GUARD_LAG_S_BY_CLASS)
f, hold = R2.GUARD_EXIT_FACTOR_D166, R2.GUARD_EXIT_HOLD_S_D166
script = [
    (0.0, 0.00, "quiet"),                      # nothing
    (0.1, 0.85, "ENTRY: alert over 0.8"),      # entry
    (0.2, 0.60, "BAND: under entry 0.8, over exit 0.4"),
    (0.3, 0.60, "BAND again"),
    (0.4, 0.30, "BELOW EXIT 0.4: clock starts"),
    (1.0, 0.30, "below exit, 0.6 s elapsed"),
    (2.3, 0.30, "below exit, 1.9 s elapsed: still latched"),
    (2.4, 0.30, "below exit, 2.0 s elapsed: EXIT"),
    (2.5, 0.30, "stays out"),
    (2.6, 0.85, "ENTRY again"),
    (2.7, 0.30, "below exit, clock restarts"),
    (3.0, 0.60, "BAND: clock RESET, so the 2 s must start over"),
    (3.1, 0.30, "below exit, clock starts again"),
    (5.2, 0.30, "2.1 s below exit: EXIT"),
]
trace = []
for t, alert, why in script:
    g = a.guard_state(Obs(t, {"episodic": alert}))
    h = g["hysteresis"]
    trace.append({"t": t, "alert_lag_s": alert, "entry_bar": thr["episodic"],
                  "exit_bar": round(f * thr["episodic"], 4),
                  "entry": h["entry"], "below_exit": h["below_exit"],
                  "below_since": h["below_since"], "latched": h["latched"],
                  "active": g["active"], "why": why})
OUT["B_latch_trace"] = trace
exp = [False, True, True, True, True, True, True, False, False, True, True, True, True, False]
OUT["B_expected_latched"] = exp
OUT["B_observed_latched"] = [r["latched"] for r in trace]
OUT["B_PASS"] = OUT["B_observed_latched"] == exp
OUT["B_counters"] = {k: v for k, v in dict(a.stats).items() if "hyst" in k or "guard_log" in k}

# ---------------------------------------------------------------- C: idempotent within a period
a = arm()
o = Obs(10.0, {"episodic": 0.85})
g1 = a.guard_state(o)
g2 = a.guard_state(o)
g3 = a.guard_state(o)
OUT["C_repeat_reads_in_one_period"] = {
    "_why": ("guard_state is read up to four times per decision period by one rung. A latch "
             "advancing per READ would make the 2 s hold mean 2 s on rung 1 and 0.5 s on rung 4, "
             "and the per-period log's denominator would be the number of consumers."),
    "three_reads_identical": (g1 == g2 == g3),
    "log_rows_written": len(a.guard_log_rows),
    "repeat_reads_counted": dict(a.stats).get("guard_log_repeat_reads"),
    "hyst_repeat_reads_counted": dict(a.stats).get("guard_hyst_repeat_reads")}
OUT["C_PASS"] = bool(g1 == g2 == g3 and len(a.guard_log_rows) == 1)

# ---------------------------------------------------------------- D: backlog entry and its exit
a = arm()
d = []
for t, bl, why in ((0.1, 100, "ENTRY on backlog at the committed 100"),
                   (0.2, 60, "BAND: under 100, over the exit bar 50"),
                   (0.3, 49, "below exit 50: clock starts"),
                   (2.4, 49, "2.1 s below: EXIT")):
    g = a.guard_state(Obs(t, {}, q={"recall": bl}))
    d.append({"t": t, "backlog": bl, "by_backlog": g["by_backlog"],
              "latched": g["hysteresis"]["latched"], "active": g["active"], "why": why})
OUT["D_backlog_latch"] = d
OUT["D_PASS"] = [r["latched"] for r in d] == [True, True, True, False]

OUT["ALL_PASS"] = all(OUT[k] for k in ("A_PASS", "B_PASS", "C_PASS", "D_PASS"))
Path(sys.argv[2]).write_text(json.dumps(OUT, indent=1, default=str))
for k in ("A_PASS", "B_PASS", "C_PASS", "D_PASS", "ALL_PASS"):
    print("%-10s %s" % (k, OUT[k]))
print("committed guard blind to assistance at 100 s lag: by_lag =",
      OUT["A_control_committed_guard_blind_to_assistance_at_100s"])
for r in OUT["B_latch_trace"]:
    print("  t=%5.1f alert=%.2f entry=%-5s below_exit=%-5s since=%-5s latched=%-5s  %s"
          % (r["t"], r["alert_lag_s"], r["entry"], r["below_exit"], r["below_since"],
             r["latched"], r["why"]))
sys.exit(0 if OUT["ALL_PASS"] else 1)
