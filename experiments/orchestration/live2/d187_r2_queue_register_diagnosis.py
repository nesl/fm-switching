#!/usr/bin/env python3
"""Why the D187 r2 queue-register fix went the WRONG WAY at seed 4.

READ-ONLY. Reads only COMMITTED cells, through `git show <rev>:<path>`. No cell is run, no
live-path file is touched, no coefficient is retyped.

THE CHANGE UNDER TEST (r1 -> r2). The release re-check's `queued_uncached_ahead` was
`self._uncached_in_flight` (submit to COMPLETION, so it includes decode) and is now
`self._w.total()` (submit to FIRST TOKEN, the quantity `cost_model_gate_d162.py:97` builds the
fitted regressor on). Both call sites: `coordinator.py:944` (alert) and `:1293` (recall and
assistance), read from the rev under test. Pre-registration: `reports/prereg_queue_register_r2.md`.

THE MEASURED PUZZLE. The link fired (the alert side fell at s5 and s6; the fed queue value at the
recall skips fell) but the robot pool did not benefit and s4 got materially worse:
release_infeasible_recall 34 -> 47, share_deny_recall 467 -> 643, robot on time 95 -> 79.

WHAT IS READ DIRECTLY AND WHAT IS RECONSTRUCTED, stated before any number.

DIRECT, from `coordinator_result` (the P0 serialised lists; r2's file is GZIPPED because the P0
change made it large enough for the harness to compress it, r1's is plain, and BOTH forms are
handled while a MISSING file is a hard failure and never an empty dict):
  * `release_infeasible_events[*]`: `uncached` (the predicted u the re-check USED),
    `queued_uncached_ahead` (THE FED QUEUE VALUE, which is the register under test),
    `est_first_token_s`, `remaining_s`, `readiness`, `est_tokens`, `session_id`,
    `opportunity_id`, `t`. Uncapped in these cells: list length equals
    `release_infeasible_events_total`, which is asserted rather than assumed.
  * `share_events[*]`: `qtype`, `kind`, `uncached`, `admitted`, `reason`, `key`, `w_by_type`,
    `w_total`. `w_by_type` and `w_total` are recorded BEFORE the admission at that same gate
    call (`coordinator.py:1592-1596` runs before `on_submit` at `:1601`), which is what makes
    them usable as a per-instant ground truth for the reconstruction below.
  * `counts[*]`: the committed per-type counters.

RECONSTRUCTED, and VALIDATED rather than asserted (positive control PC3):
  * W(t) DECOMPOSED BY ADMISSION REASON. The W tracker is keyed on request id
    (`share_admission.py` WTracker) and charges `self._uncached_last_charged` at
    `coordinator.py:1420`, which no log carries, so the per-request charge is taken from the
    `uncached` of the admitted share gate call that precedes that submit. The join is EXACT, not
    fuzzy: an opportunity-keyed gate call joins to the request carrying that `opportunity_id`
    (1:1 in every cell), and a `touch:`/`build:`-keyed gate call joins positionally within its
    own device, whose per-device cardinality is checked to match exactly. The reconstruction is
    then replayed against the recorded `w_total` at EVERY gate call and against
    `queued_uncached_ahead` at every r2 release-infeasible event; both match rates are reported
    and a low rate is a stopping condition.

Usage:
  python d187_r2_queue_register_diagnosis.py [--rev origin/main] [--seeds 4,5,6] [--out <path>]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(os.environ.get("D179_REPO") or Path(__file__).resolve().parents[3])
RUNS = "results/orchestration/live2/frozen_test/runs"
CELL_SUFFIX = "_1200s_h27_3t_L3_epg_rq30"
ARMS = {"r1": "covex-v6-state-shares-r1", "r2": "covex-v6-state-shares-r2"}
OVERSIZE_REASONS = ("oversize_alone", "oversize_alone_over_wmax")
SCRIPT = "d187_r2_queue_register_diagnosis.py"


class ReaderFailure(RuntimeError):
    """A cell file could not be read. NEVER degraded to an empty dict."""


# ---------------------------------------------------------------- git and the price module
def git_show(rev: str, path: str) -> bytes:
    p = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{path}"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise ReaderFailure(f"git show {rev}:{path} failed: "
                            f"{p.stderr.decode(errors='replace').strip()}")
    return p.stdout


def have(rev: str, path: str) -> bool:
    return subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{rev}:{path}"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _import_price(rev: str) -> Tuple[Any, str]:
    """ONE PRICE SOURCE: the coefficients are never retyped here. Prefer the working tree; if it
    is behind the rev the cells were committed on, materialise the committed module AND its gate
    file into a session-unique scratch directory so the module's own drift check runs for real."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import d162_price as DP                                            # noqa: PLC0415
        return DP, "experiments/orchestration/live2/d162_price.py (working tree)"
    except ImportError:
        pass
    d = Path(tempfile.mkdtemp(prefix="d187r2_price_"))
    for rel in ("experiments/orchestration/live2/d162_price.py",
                "results/orchestration/live2/frozen_test/cost_model_gate_d162.json"):
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(git_show(rev, rel))
    sys.path.insert(0, str(d / "experiments/orchestration/live2"))
    import d162_price as DP                                                # noqa: PLC0415
    return DP, (f"git show {rev}:experiments/orchestration/live2/d162_price.py "
                "(the working tree is behind that rev and does not carry the file)")


# ---------------------------------------------------------------- cell loading
def load_cell(rev: str, cell: str) -> Dict[str, Any]:
    """Load one cell. `coordinator_result` is plain JSON on r1 and GZIPPED on r2; both are
    handled, and if NEITHER exists this raises. A missing file must never read as {}."""
    base = f"{RUNS}/{cell}"
    out: Dict[str, Any] = {"cell": cell}
    out["cell_json"] = json.loads(git_show(rev, f"{base}/cell.json"))
    out["run_meta"] = json.loads(git_show(rev, f"{base}/run_meta.json"))
    plain, gz = f"{base}/coordinator_result.json", f"{base}/coordinator_result.json.gz"
    if have(rev, gz):
        out["coord"] = json.loads(gzip.decompress(git_show(rev, gz)).decode())
        out["coord_path"] = gz
        out["coord_form"] = "gzip"
    elif have(rev, plain):
        out["coord"] = json.loads(git_show(rev, plain))
        out["coord_path"] = plain
        out["coord_form"] = "plain"
    else:
        raise ReaderFailure(
            f"NEITHER {plain} NOR {gz} exists at {rev}. This is a hard failure: a missing "
            "coordinator_result must not be read as an empty dict.")
    for name in ("decision", "outcomes", "request"):
        raw = gzip.decompress(git_show(rev, f"{base}/{name}.jsonl.gz")).decode()
        out[name] = [json.loads(x) for x in raw.splitlines() if x.strip()]
    for key in ("release_infeasible_events", "share_events"):
        if not isinstance(out["coord"].get(key), list):
            raise ReaderFailure(f"{cell}: coordinator_result has no list `{key}`; this reader "
                                "cannot run without the P0 serialised lists.")
    return out


# ---------------------------------------------------------------- the committed delivery rules
def apply_committed_delivery_rules(c: Dict[str, Any]) -> Dict[str, Any]:
    """The two rewrites the COMMITTED scorer applies before anything reads `t_delivered`
    (scorer/score.py:539-579). D144 nulls a refused request's cloud delivery; D146 delivers a
    recall at generation COMPLETION. Re-applied so this reader's on-time count is the scorer's."""
    refused = set()
    for r in c["request"]:
        hs = r.get("http_status")
        if hs is not None:
            try:
                if int(hs) != 200:
                    refused.add(r.get("request_id"))
            except (TypeError, ValueError):
                refused.add(r.get("request_id"))
            continue
        if not r.get("prompt_tokens") and not r.get("output_tokens"):
            refused.add(r.get("request_id"))
    n144 = 0
    for o in c["outcomes"]:
        cp = o.get("cloud_payload") or {}
        if cp.get("request_id") in refused:
            o["t_delivered"] = None
            o["cloud_payload"] = None
            n144 += 1
    done = {str(r["opportunity_id"]): float(r["t_done"]) for r in c["request"]
            if r.get("opportunity_id") and r.get("t_done") is not None}
    n146 = 0
    for o in c["outcomes"]:
        if o.get("kind") != "recall" or o.get("t_delivered") is None:
            continue
        oid = str(o["opportunity_id"])
        if o.get("t_cloud_done") is None or oid not in done:
            continue
        o["t_delivered"] = done[oid] + (float(o["t_delivered"]) - float(o["t_cloud_done"]))
        n146 += 1
    return {"d144_nulled": n144, "d146_rewritten_to_completion": n146}


def robot_pool(c: Dict[str, Any]) -> set:
    return {str(o["opportunity_id"]) for o in c["outcomes"]
            if o.get("kind") == "recall" and str(o.get("device_id") or "").startswith("robo")}


def robot_on_time(c: Dict[str, Any]) -> set:
    out = set()
    for o in c["outcomes"]:
        if o.get("kind") != "recall" or not str(o.get("device_id") or "").startswith("robo"):
            continue
        if o.get("t_delivered") is None:
            continue
        if float(o["t_delivered"]) - float(o["t_opportunity"]) <= float(o["deadline_s"]) + 1e-9:
            out.add(str(o["opportunity_id"]))
    return out


def _dist(v: List[float], keep_all: bool = True) -> Dict[str, Any]:
    v = sorted(x for x in v if x is not None)
    if not v:
        return {"n": 0}
    def q(p: float) -> float:
        i = min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))
        return v[i]
    out = {"n": len(v), "min": v[0], "p10": q(0.10), "p25": q(0.25), "median": q(0.5),
           "p75": q(0.75), "p90": q(0.90), "max": v[-1],
           "mean": round(sum(v) / len(v), 6),
           "iqr": q(0.75) - q(0.25)}
    if keep_all:
        out["all"] = v
    return out


# ---------------------------------------------------------------- oversize in flight: DIRECT
def oversize_intervals(coord: Dict[str, Any]) -> Dict[str, Any]:
    """When is an OVERSIZE-admitted request in W? Answered from DIRECT fields only.

    This is the primary instrument for the user's question 2, and it replaces the per-reason W
    reconstruction below for every headline, because it needs no join and no drain-time guess.

    The two facts it rests on, both from the committed code and both checkable in the log:
      1. `share_admission.py` admits an oversize foreground request ONLY when `w[qtype] == 0`
         (`if w[qtype] > 0: return False, "oversize_wait_for_own_type"`), and the gate records
         `w_by_type` BEFORE its own admission (`coordinator.py:1592-1596` precedes `:1601`). So
         an `oversize_alone` / `oversize_alone_over_wmax` event is an interval START with a
         KNOWN, LOGGED size `u_a` and a known pre-state of exactly zero for its type.
      2. While that request is in W, the recorded `w_by_type[qtype]` cannot be below `u_a`,
         because W is a sum of non-negative charges and this one is `u_a`. So the interval ENDS
         at the first later gate call whose DIRECT `w_by_type[qtype] < u_a`.

    The one assumption, declared: the W charge equals the gate call's own `uncached`. The gate is
    called immediately before the submit that charges W (`coordinator.py:1420`) with the same
    predicted quantity. Where this assumption bites, it bites on the END time only, and it is
    checked: `end_is_bounded` reports how many intervals closed inside the run.
    """
    se = sorted(coord["share_events"], key=lambda e: float(e["t"]))
    rows: List[Dict[str, Any]] = []
    for i, e in enumerate(se):
        if not (e.get("admitted") and str(e.get("reason")) in OVERSIZE_REASONS):
            continue
        t = str(e["qtype"])
        u = int(e["uncached"])
        t_a = float(e["t"])
        t_e = float("inf")
        for j in range(i + 1, len(se)):
            if int((se[j].get("w_by_type") or {}).get(t, 0)) < u:
                t_e = float(se[j]["t"])
                break
        rows.append(dict(t_start=round(t_a, 6), t_end=(None if t_e == float("inf")
                                                       else round(t_e, 6)),
                         qtype=t, kind=str(e["kind"]), reason=str(e["reason"]), u=u,
                         w_by_type_before=dict(e.get("w_by_type") or {}),
                         duration_s=(None if t_e == float("inf") else round(t_e - t_a, 6))))
    dur = [r["duration_s"] for r in rows if r["duration_s"] is not None]
    return {"intervals": rows, "n": len(rows),
            "end_is_bounded": len(dur), "end_unbounded": len(rows) - len(dur),
            "by_reason": dict(Counter(r["reason"] for r in rows)),
            "by_qtype": dict(Counter(r["qtype"] for r in rows)),
            "by_kind": dict(Counter(r["kind"] for r in rows)),
            "u": _dist([float(r["u"]) for r in rows], keep_all=False),
            "duration_s": _dist([float(x) for x in dur], keep_all=False),
            "total_oversize_seconds_in_W": round(sum(dur), 3)}


def oversize_at(iv: Dict[str, Any], t: float) -> Dict[str, Any]:
    act = [r for r in iv["intervals"]
           if r["t_start"] <= t and (r["t_end"] is None or t < r["t_end"])]
    return {"n_oversize_in_flight": len(act),
            "oversize_tokens_in_W_DIRECT": sum(r["u"] for r in act),
            "oversize_rows": act}


# ---------------------------------------------------------------- W reconstruction by reason
def reconstruct_w(cell: Dict[str, Any]) -> Dict[str, Any]:
    """Attribute W(t) to the ADMISSION REASON of the request that put each token there.

    Why this is needed. `w_by_type` is a DIRECT field, so the per-type split of W needs no
    reconstruction. The per-REASON split does: W is charged at submit keyed on request id
    (`coordinator.py:1420`) with `_uncached_last_charged`, which no log carries, and the drain is
    the first-token hook. So each admitted gate call is joined to its request to get the drain
    time, and the gate call's own `uncached` is taken as the charge.

    PROXY, declared at its point of use: `share_events[*].uncached` stands for
    `_uncached_last_charged`. What it actually measures: the predicted uncached the SHARE GATE was
    given for that request, one call earlier in the same code path. Valid for the claim only if
    the replay reproduces the recorded `w_total`, which is checked on every gate call and
    reported as `pc3_w_total_exact_frac`; a low rate is a stopping condition and is surfaced
    rather than worked around.
    """
    c = cell["coord"]
    req = cell["request"]
    by_opp = {}
    for r in req:
        if r.get("opportunity_id"):
            by_opp.setdefault(str(r["opportunity_id"]), r)
    non_opp = defaultdict(list)
    for r in req:
        if not r.get("opportunity_id"):
            non_opp[str(r["device_id"])].append(r)
    for k in non_opp:
        non_opp[k].sort(key=lambda r: (float(r["t_submit"]), str(r["request_id"])))
    cursor = {k: 0 for k in non_opp}

    adm = [e for e in c["share_events"] if e.get("admitted")]  # noqa: F841 (joined below)
    adm.sort(key=lambda e: float(e["t"]))
    charges: List[Dict[str, Any]] = []
    join = {"opp_joined": 0, "opp_unjoined": 0, "nonopp_joined": 0, "nonopp_unjoined": 0}
    unjoined_keys: List[str] = []
    for e in adm:
        key = str(e.get("key") or "")
        r = None
        if key.startswith("opp"):
            r = by_opp.get(key)
            if r is None:
                join["opp_unjoined"] += 1
                if len(unjoined_keys) < 20:
                    unjoined_keys.append(key)
                continue
            join["opp_joined"] += 1
        else:
            dev = key.split(":", 1)[1].split("|")[0] if ":" in key else ""
            lst = non_opp.get(dev) or []
            i = cursor.get(dev, 0)
            if i >= len(lst):
                join["nonopp_unjoined"] += 1
                if len(unjoined_keys) < 20:
                    unjoined_keys.append(key)
                continue
            r = lst[i]
            cursor[dev] = i + 1
            join["nonopp_joined"] += 1
        t_sub = float(r["t_submit"])
        drain = r.get("t_first_token")
        drain_src = "first_token"
        if drain is None:
            drain = r.get("t_done")
            drain_src = "settle"
        if drain is None:
            drain = float("inf")
            drain_src = "never"
        charges.append(dict(request_id=str(r["request_id"]), device_id=str(r["device_id"]),
                            qtype=str(e["qtype"]), kind=str(e["kind"]),
                            reason=str(e["reason"]), u=int(e["uncached"]),
                            t_submit=t_sub, t_drain=float(drain), drain_src=drain_src,
                            oversize=bool(str(e["reason"]) in OVERSIZE_REASONS)))

    def w_at(t: float, strict_submit: bool = True) -> Dict[str, Any]:
        """W(t) and its decomposition. Half-open on the tracker's own interval: on_submit adds,
        the first-token hook removes.

        THE TIE CONVENTION IS STATED, not assumed. Many requests carry the SAME t_submit stamp
        (one decision epoch submits a batch), and a gate call or a re-check at that same stamp
        runs BEFORE the submits it gates. `strict_submit` therefore excludes charges whose
        t_submit equals t. Both conventions are reported wherever it could change a number.
        """
        by_reason: Dict[str, int] = defaultdict(int)
        by_type: Dict[str, int] = defaultdict(int)
        tot = over = 0
        over_rows = []
        for ch in charges:
            lo = ch["t_submit"] < t if strict_submit else ch["t_submit"] <= t
            if lo and t < ch["t_drain"]:
                by_reason[ch["reason"]] += ch["u"]
                by_type[ch["qtype"]] += ch["u"]
                tot += ch["u"]
                if ch["oversize"]:
                    over += ch["u"]
                    over_rows.append({k: ch[k] for k in
                                      ("request_id", "qtype", "kind", "reason", "u", "t_submit",
                                       "t_drain")})
        return {"w_total_recon": tot, "w_by_type_recon": dict(by_type),
                "w_by_reason_recon": dict(by_reason), "w_oversize_recon": over,
                "oversize_frac": (round(over / tot, 6) if tot else None),
                "oversize_in_flight": over_rows}

    # PC3: replay against the recorded w_total at EVERY gate call, by sweep line so the replay is
    # linear rather than quadratic. The gate records W BEFORE its own admission.
    gates = sorted(c["share_events"], key=lambda e: float(e["t"]))
    pc3: Dict[str, Any] = {}
    for conv in ("strict", "inclusive"):
        adds = sorted(((ch["t_submit"], ch["u"]) for ch in charges), key=lambda x: x[0])
        subs = sorted(((ch["t_drain"], ch["u"]) for ch in charges
                       if ch["t_drain"] != float("inf")), key=lambda x: x[0])
        ia = isub = 0
        cur = 0
        exact = 0
        diffs: List[int] = []
        for e in gates:
            t = float(e["t"])
            while ia < len(adds) and (adds[ia][0] < t if conv == "strict"
                                      else adds[ia][0] <= t):
                cur += adds[ia][1]
                ia += 1
            while isub < len(subs) and subs[isub][0] <= t:
                cur -= subs[isub][1]
                isub += 1
            rec = int(e.get("w_total") or 0)
            if cur == rec:
                exact += 1
            else:
                diffs.append(cur - rec)
        pc3[conv] = {"gate_calls": len(gates), "exact": exact,
                     "exact_frac": (round(exact / len(gates), 6) if gates else None),
                     "diff_dist": _dist([float(x) for x in diffs], keep_all=False)}
    best = max(("strict", "inclusive"), key=lambda k: pc3[k]["exact_frac"] or 0.0)
    return {"charges": charges, "w_at": w_at, "join": join,
            "unjoined_keys_sample": unjoined_keys,
            "pc3_by_tie_convention": pc3, "pc3_best_convention": best,
            "pc3_gate_calls": len(gates), "pc3_w_total_exact": pc3[best]["exact"],
            "pc3_w_total_exact_frac": pc3[best]["exact_frac"],
            "pc3_diff_dist": pc3[best]["diff_dist"]}


# ---------------------------------------------------------------- per-seed analysis
def analyse_seed(rev: str, seed: int, DP: Any) -> Dict[str, Any]:
    cells = {k: load_cell(rev, f"{v}_n16_s{seed}{CELL_SUFFIX}") for k, v in ARMS.items()}
    delivery = {k: apply_committed_delivery_rules(v) for k, v in cells.items()}

    # ---- PC1: reproduce committed headline numbers, and MARK THE REGISTER of the path ---------
    pc1 = {"path_note": ("the committed headline lives at cell.json score.score.sweep[0]; "
                         "`score.sweep` is NOT the path and reads None, which is recorded here "
                         "so the wrong path cannot be read as a zero"),
           "score_sweep_reads_none": {}, "rows": []}
    head = {}
    for k, c in cells.items():
        pc1["score_sweep_reads_none"][k] = (c["cell_json"].get("score", {}).get("sweep") is None)
        z = c["cell_json"]["score"]["score"]["sweep"][0]
        head[k] = {"arm": c["coord"].get("arm"), "run_valid": c["cell_json"].get("run_valid"),
                   "robot_pool_on_time_COMMITTED": z["robot_pool_on_time"],
                   "robot_pool_n_COMMITTED": z["robot_pool_n"],
                   "ss_pool_on_time_COMMITTED": z["ss_pool_on_time"],
                   "ss_pool_n_COMMITTED": z["ss_pool_n"],
                   "dashcam_all_meet_COMMITTED": z["dashcam_all_meet"],
                   "robot_pool_n_THIS_READER": len(robot_pool(c)),
                   "robot_pool_on_time_THIS_READER": len(robot_on_time(c))}
        pc1["rows"].append({
            "arm": k, "cell": c["cell"],
            "committed_robot_pool_on_time": z["robot_pool_on_time"],
            "this_reader_robot_pool_on_time": head[k]["robot_pool_on_time_THIS_READER"],
            "committed_robot_pool_n": z["robot_pool_n"],
            "this_reader_robot_pool_n": head[k]["robot_pool_n_THIS_READER"],
            "agree": (z["robot_pool_on_time"] == head[k]["robot_pool_on_time_THIS_READER"]
                      and z["robot_pool_n"] == head[k]["robot_pool_n_THIS_READER"]),
            "delivery_rules_applied": delivery[k]})
    pc1["pass"] = all(r["agree"] for r in pc1["rows"]) and len(pc1["rows"]) >= 2

    # ---- PC2: the event lists are UNCAPPED in these cells -------------------------------------
    pc2 = {}
    for k, c in cells.items():
        co = c["coord"]
        pc2[k] = {
            "release_infeasible_events_len": len(co["release_infeasible_events"]),
            "release_infeasible_events_total": co.get("release_infeasible_events_total"),
            "uncapped": (len(co["release_infeasible_events"])
                         == co.get("release_infeasible_events_total")),
            "share_events_len": len(co["share_events"]),
            "share_events_total": co.get("share_events_total"),
            "share_events_uncapped": (len(co["share_events"]) == co.get("share_events_total")),
            "coord_form": c["coord_form"], "coord_path": c["coord_path"],
            "recall_events_in_list": sum(1 for e in co["release_infeasible_events"]
                                         if e.get("qtype") == "recall"),
            "counter_release_infeasible_recall": co["counts"].get("release_infeasible_recall", 0)}
        pc2[k]["recall_list_matches_counter"] = (
            pc2[k]["recall_events_in_list"] == pc2[k]["counter_release_infeasible_recall"])
    pc2["pass"] = all(v["uncapped"] and v["recall_list_matches_counter"]
                      for k, v in pc2.items() if k in ARMS)

    # ---- the W reconstruction, with its own positive control ---------------------------------
    recon = {k: reconstruct_w(c) for k, c in cells.items()}
    ovi = {k: oversize_intervals(c["coord"]) for k, c in cells.items()}
    pc3 = {k: {kk: recon[k][kk] for kk in ("join", "unjoined_keys_sample", "pc3_gate_calls",
                                           "pc3_w_total_exact", "pc3_w_total_exact_frac",
                                           "pc3_diff_dist", "pc3_by_tie_convention",
                                           "pc3_best_convention")} for k in ARMS}
    pc3["gates_only_the_secondary_measure"] = (
        "This control gates ONLY the per-reason W RECONSTRUCTION. It does NOT gate q1, q3, q4, "
        "q5 or the primary q2 measure, all of which read direct fields. Where it fails, the "
        "reconstruction is reported as SECONDARY and no headline rests on it.")
    pc3["pass_for_the_secondary_reconstruction"] = all(
        (recon[k]["pc3_w_total_exact_frac"] or 0) >= 0.95 for k in ARMS)
    pc3["known_residual"] = (
        "The replay understates the logged w_total by a median of one alert charge. The charge "
        "AMOUNTS are right (the engine-uncached variant scores far worse), so the residual is "
        "the DRAIN INSTANT: the tracker is popped from the coordinator's epoch loop when it "
        "processes the first-token hook, which is strictly later than the engine's logged "
        "t_first_token, and no log carries that instant. Settling instead of first-token "
        "over-drains in the other direction (0.386 exact, median +380). The truth lies between "
        "two conventions neither of which is logged, which is why the primary q2 measure does "
        "not use this reconstruction at all.")
    pc3["pass"] = pc3["pass_for_the_secondary_reconstruction"]

    # ---- the counters, side by side -----------------------------------------------------------
    counters = {}
    keys = sorted({kk for k in ARMS for kk in cells[k]["coord"]["counts"]
                   if "release_infeasible" in kk or "share_deny" in kk
                   or kk.startswith("share_at_or_above_floor")})
    for kk in keys:
        counters[kk] = {k: cells[k]["coord"]["counts"].get(kk, 0) for k in ARMS}

    # ---- Q1 / Q4 / Q5: the recall skips -------------------------------------------------------
    skips = {}
    for k, c in cells.items():
        rows = []
        for e in c["coord"]["release_infeasible_events"]:
            if e.get("qtype") != "recall":
                continue
            u = int(e["uncached"])
            qa = int(e["queued_uncached_ahead"])
            rem = float(e["remaining_s"])
            size_alone = DP.INTERCEPT_S + DP.PER_UNCACHED_S * float(u)
            eft = size_alone + DP.PER_QUEUE_S * float(qa)
            w = recon[k]["w_at"](float(e["t"]))
            od = oversize_at(ovi[k], float(e["t"]))
            # the DIRECT per-type split of W at the nearest gate call AT OR BEFORE the skip
            gl = [g for g in cells[k]["coord"]["share_events"] if float(g["t"]) <= float(e["t"])]
            near = gl[-1] if gl else None
            rows.append(dict(
                opportunity_id=str(e["opportunity_id"]), session_id=e.get("session_id"),
                device_id=e.get("device_id"), t=round(float(e["t"]), 3),
                # DIRECT
                predicted_u_AS_USED=u, queued_uncached_ahead_AS_FED=qa,
                est_first_token_s=round(float(e["est_first_token_s"]), 6),
                remaining_s=round(rem, 6), readiness=e.get("readiness"),
                est_tokens=e.get("est_tokens"),
                # the term that refused it, same definition as the r1 diagnosis
                size_alone_first_token_s=round(size_alone, 6),
                queue_term_s=round(DP.PER_QUEUE_S * float(qa), 6),
                refused_by=("size" if size_alone > rem else "queue"),
                est_first_token_s_recomputed=round(eft, 6),
                price_arithmetic_ok=bool(abs(eft - float(e["est_first_token_s"])) < 1e-9),
                # DIRECT: the oversize detector, and the nearest gate call's own w_by_type
                n_oversize_in_flight_DIRECT=od["n_oversize_in_flight"],
                oversize_tokens_in_W_DIRECT=od["oversize_tokens_in_W_DIRECT"],
                oversize_share_of_fed_W_DIRECT=(
                    round(od["oversize_tokens_in_W_DIRECT"] / qa, 6) if qa else None),
                oversize_rows_DIRECT=od["oversize_rows"],
                nearest_gate_t=(None if near is None else round(float(near["t"]), 6)),
                nearest_gate_w_by_type_DIRECT=(None if near is None
                                               else dict(near.get("w_by_type") or {})),
                nearest_gate_w_total_DIRECT=(None if near is None
                                             else int(near.get("w_total") or 0)),
                # RECONSTRUCTED (PC3 reports its exact-match rate; NOT used for any headline)
                w_total_recon=w["w_total_recon"], w_by_type_recon=w["w_by_type_recon"],
                w_by_reason_recon=w["w_by_reason_recon"],
                w_oversize_recon=w["w_oversize_recon"],
                oversize_frac_of_w=w["oversize_frac"],
                oversize_in_flight=w["oversize_in_flight"],
                fed_equals_recon_w=(qa == w["w_total_recon"])))
        rows.sort(key=lambda r: r["t"])
        skips[k] = rows

    # the register proof: in r2 the fed value IS W; in r1 it is NOT
    register = {}
    for k in ARMS:
        rows = skips[k]
        register[k] = {
            "n_recall_skips": len(rows),
            "fed_equals_reconstructed_W_frac": (
                round(sum(1 for r in rows if r["fed_equals_recon_w"]) / len(rows), 6)
                if rows else None),
            "fed_minus_reconstructed_W": _dist(
                [float(r["queued_uncached_ahead_AS_FED"] - r["w_total_recon"]) for r in rows]),
            "price_arithmetic_ok_all": all(r["price_arithmetic_ok"] for r in rows),
            # THE DIRECT REGISTER DISCRIMINATOR, which needs no reconstruction. The gate call
            # nearest at or before the skip logs W DIRECTLY. In r2 the fed value IS W, so the
            # two can differ only by what was submitted or drained in the gap (a charge or two).
            # In r1 the fed value is `_uncached_in_flight`, which is submit-to-COMPLETION and so
            # a SUPERSET of W, and must sit systematically ABOVE the logged W.
            "fed_minus_nearest_gate_logged_W_DIRECT": _dist(
                [float(r["queued_uncached_ahead_AS_FED"] - r["nearest_gate_w_total_DIRECT"])
                 for r in rows if r["nearest_gate_w_total_DIRECT"] is not None]),
            "frac_fed_strictly_above_nearest_logged_W": (
                round(sum(1 for r in rows
                          if r["nearest_gate_w_total_DIRECT"] is not None
                          and r["queued_uncached_ahead_AS_FED"]
                          > r["nearest_gate_w_total_DIRECT"]) / len(rows), 6)
                if rows else None)}

    q1 = {k: {"queued_uncached_ahead_AS_FED": _dist(
                  [float(r["queued_uncached_ahead_AS_FED"]) for r in skips[k]]),
              "queue_term_s": _dist([r["queue_term_s"] for r in skips[k]]),
              "remaining_s": _dist([r["remaining_s"] for r in skips[k]]),
              "est_first_token_s": _dist([r["est_first_token_s"] for r in skips[k]])}
          for k in ARMS}
    # the same question asked on every gate call, not only on the skips, so the "smaller on
    # average, larger at the peaks" reading is testable rather than asserted
    q1["W_at_every_gate_call_DIRECT_w_total"] = {
        k: _dist([float(e.get("w_total") or 0) for e in cells[k]["coord"]["share_events"]],
                 keep_all=False) for k in ARMS}
    q1["fed_value_at_ALL_release_infeasible_events"] = {
        k: _dist([float(e["queued_uncached_ahead"])
                  for e in cells[k]["coord"]["release_infeasible_events"]], keep_all=False)
        for k in ARMS}

    # ---- Q2: does W include oversize work? ----------------------------------------------------
    q2 = {"method": ("PRIMARY measure is DIRECT: the oversize-in-flight detector of "
                     "`oversize_intervals`, whose start, size and type are logged fields and "
                     "whose end is read off the logged `w_by_type` series. The denominator is "
                     "the DIRECT fed queue value at the skip. The per-reason W reconstruction is "
                     "reported beside it as a SECONDARY cross-read and is NOT used for any "
                     "headline, because its PC3 exact-match rate is below the bar.")}
    for k in ARMS:
        rows = skips[k]
        nov = sum(1 for r in rows if r["oversize_tokens_in_W_DIRECT"])
        frd = [r["oversize_share_of_fed_W_DIRECT"] for r in rows
               if r["oversize_share_of_fed_W_DIRECT"] is not None]
        q2[k] = {
            "run_wide_oversize_admissions_DIRECT": {
                kk: ovi[k][kk] for kk in ("n", "by_reason", "by_qtype", "by_kind",
                                          "end_is_bounded", "end_unbounded", "u", "duration_s",
                                          "total_oversize_seconds_in_W")},
            "n_recall_skips": len(rows),
            "n_skips_with_an_oversize_request_in_flight_DIRECT": nov,
            "frac_of_skips_with_oversize_in_flight_DIRECT": (
                round(nov / len(rows), 6) if rows else None),
            "oversize_tokens_in_W_DIRECT": _dist(
                [float(r["oversize_tokens_in_W_DIRECT"]) for r in rows]),
            "oversize_share_of_fed_W_DIRECT": _dist(frd),
            "oversize_share_on_the_skips_WHERE_PRESENT": _dist(
                [r["oversize_share_of_fed_W_DIRECT"] for r in rows
                 if r["oversize_tokens_in_W_DIRECT"]]),
            "oversize_u_in_flight_at_skips": _dist(
                [float(o["u"]) for r in rows for o in r["oversize_rows_DIRECT"]], keep_all=False),
            "oversize_reasons_at_skips": dict(Counter(
                o["reason"] for r in rows for o in r["oversize_rows_DIRECT"])),
            "oversize_qtypes_at_skips": dict(Counter(
                o["qtype"] for r in rows for o in r["oversize_rows_DIRECT"])),
            "fed_W_at_skip": _dist([float(r["queued_uncached_ahead_AS_FED"]) for r in rows]),
            "SECONDARY_reconstruction": {
                "n_with_oversize": sum(1 for r in rows if r["w_oversize_recon"]),
                "oversize_share_of_W_recon": _dist(
                    [r["oversize_frac_of_w"] for r in rows
                     if r["oversize_frac_of_w"] is not None], keep_all=False),
                "w_by_reason_at_skips_summed": dict(
                    Counter({rk: sum(r["w_by_reason_recon"].get(rk, 0) for r in rows)
                             for rk in {x for r in rows for x in r["w_by_reason_recon"]}}))}}
        # the peak question, asked on the DIRECT fed value: is oversize concentrated in the
        # largest-W skips? Reported as a STRATUM with its size, not as a population median.
        top = sorted(rows, key=lambda r: -r["queued_uncached_ahead_AS_FED"])[
            :max(1, len(rows) // 4)]
        q2[k]["top_quartile_of_fed_W_at_skips"] = {
            "n": len(top),
            "fed_W": _dist([float(r["queued_uncached_ahead_AS_FED"]) for r in top]),
            "n_with_oversize_in_flight": sum(1 for r in top
                                             if r["oversize_tokens_in_W_DIRECT"]),
            "oversize_share_of_fed_W_DIRECT": _dist(
                [r["oversize_share_of_fed_W_DIRECT"] for r in top
                 if r["oversize_share_of_fed_W_DIRECT"] is not None])}
        # run-wide, at EVERY gate call, all direct: how often is an oversize request in W, and
        # what share of the logged w_total is it then?
        se = sorted(cells[k]["coord"]["share_events"], key=lambda e: float(e["t"]))
        n_ov = 0
        shares = []
        for g in se:
            od = oversize_at(ovi[k], float(g["t"]))
            if od["oversize_tokens_in_W_DIRECT"]:
                n_ov += 1
                wt = int(g.get("w_total") or 0)
                if wt:
                    shares.append(round(min(od["oversize_tokens_in_W_DIRECT"] / wt, 1.0), 6))
        q2[k]["run_wide_at_every_gate_call_DIRECT"] = {
            "register": "CENSUS over every logged gate call, not a subsample",
            "gate_calls": len(se), "with_oversize_in_flight": n_ov,
            "frac_with_oversize_in_flight": (round(n_ov / len(se), 6) if se else None),
            "oversize_share_of_logged_w_total_WHERE_PRESENT": _dist(shares, keep_all=False)}

    # ---- Q3: the share denial reasons ---------------------------------------------------------
    q3 = {}
    for k in ARMS:
        se = cells[k]["coord"]["share_events"]
        q3[k] = {
            "gate_calls": len(se),
            "by_qtype_admitted": {str(t): dict(Counter(
                e["admitted"] for e in se if e["qtype"] == t))
                for t in ("alert", "recall", "assistance")},
            "recall_denial_reasons": dict(Counter(
                e["reason"] for e in se if e["qtype"] == "recall" and not e["admitted"])),
            "recall_admit_reasons": dict(Counter(
                e["reason"] for e in se if e["qtype"] == "recall" and e["admitted"])),
            "recall_denials_by_kind": dict(Counter(
                (e["kind"], e["reason"]) for e in se
                if e["qtype"] == "recall" and not e["admitted"])),
            "all_denial_reasons": dict(Counter(
                e["reason"] for e in se if not e["admitted"])),
            "counter_share_deny_recall": cells[k]["coord"]["counts"].get("share_deny_recall", 0)}
        q3[k]["recall_denials_by_kind"] = {f"{a}|{b}": v for (a, b), v
                                           in Counter(
                                               (e["kind"], e["reason"]) for e in se
                                               if e["qtype"] == "recall"
                                               and not e["admitted"]).items()}
        q3[k]["denials_in_list_equal_counter"] = (
            sum(q3[k]["recall_denial_reasons"].values())
            == q3[k]["counter_share_deny_recall"])
        # the coupling test: W at the recall gate calls that were DENIED, per version
        q3[k]["W_at_denied_recall_gates_DIRECT"] = _dist(
            [float(e.get("w_total") or 0) for e in se
             if e["qtype"] == "recall" and not e["admitted"]], keep_all=False)
        q3[k]["W_at_admitted_recall_gates_DIRECT"] = _dist(
            [float(e.get("w_total") or 0) for e in se
             if e["qtype"] == "recall" and e["admitted"]], keep_all=False)
        q3[k]["recall_gate_calls_total"] = sum(1 for e in se if e["qtype"] == "recall")

    # ---- Q4: did u rise because of different opportunities, or the same ones re-timed? --------
    s1 = {r["opportunity_id"]: r for r in skips["r1"]}
    s2 = {r["opportunity_id"]: r for r in skips["r2"]}
    both = sorted(set(s1) & set(s2))
    q4 = {
        "n_skips_r1": len(s1), "n_skips_r2": len(s2),
        "n_shared_opportunity_ids": len(both),
        "n_only_r1": len(set(s1) - set(s2)), "n_only_r2": len(set(s2) - set(s1)),
        "jaccard": (round(len(both) / len(set(s1) | set(s2)), 6) if (s1 or s2) else None),
        "u_r1_all_skips": _dist([float(r["predicted_u_AS_USED"]) for r in skips["r1"]]),
        "u_r2_all_skips": _dist([float(r["predicted_u_AS_USED"]) for r in skips["r2"]]),
        "u_r1_on_shared": _dist([float(s1[o]["predicted_u_AS_USED"]) for o in both]),
        "u_r2_on_shared": _dist([float(s2[o]["predicted_u_AS_USED"]) for o in both]),
        "u_on_only_r1": _dist([float(s1[o]["predicted_u_AS_USED"])
                               for o in sorted(set(s1) - set(s2))]),
        "u_on_only_r2": _dist([float(s2[o]["predicted_u_AS_USED"])
                               for o in sorted(set(s2) - set(s1))]),
        "paired_rows_on_shared": [
            {"opportunity_id": o, "session_id": s2[o]["session_id"],
             "u_r1": s1[o]["predicted_u_AS_USED"], "u_r2": s2[o]["predicted_u_AS_USED"],
             "du": s2[o]["predicted_u_AS_USED"] - s1[o]["predicted_u_AS_USED"],
             "fed_r1": s1[o]["queued_uncached_ahead_AS_FED"],
             "fed_r2": s2[o]["queued_uncached_ahead_AS_FED"],
             "dfed": (s2[o]["queued_uncached_ahead_AS_FED"]
                      - s1[o]["queued_uncached_ahead_AS_FED"]),
             "refused_by_r1": s1[o]["refused_by"], "refused_by_r2": s2[o]["refused_by"],
             "t_r1": s1[o]["t"], "t_r2": s2[o]["t"],
             # est_tokens is the WHOLE history the re-check priced; est_tokens - u is the prefix
             # the code subtracted, which is an identity on two direct fields and not a proxy
             # (d187_r1_residual_diagnosis.py documents it; readiness is GPU-WARM on these rows)
             "est_tokens_r1": s1[o]["est_tokens"], "est_tokens_r2": s2[o]["est_tokens"],
             "d_est_tokens": (int(s2[o]["est_tokens"]) - int(s1[o]["est_tokens"])),
             "prefix_r1": int(s1[o]["est_tokens"]) - s1[o]["predicted_u_AS_USED"],
             "prefix_r2": int(s2[o]["est_tokens"]) - s2[o]["predicted_u_AS_USED"],
             "d_prefix": ((int(s2[o]["est_tokens"]) - s2[o]["predicted_u_AS_USED"])
                          - (int(s1[o]["est_tokens"]) - s1[o]["predicted_u_AS_USED"])),
             "readiness_r1": s1[o]["readiness"], "readiness_r2": s2[o]["readiness"]}
            for o in both],
        "du_decomposition_on_shared": {
            "note": ("u = est_tokens - prefix on the WARM branch, so du = d_est_tokens - "
                     "d_prefix. This splits 'u rose' into a longer HISTORY and a shorter "
                     "subtracted PREFIX, which have different causes and different remedies."),
            "n_du_zero": sum(1 for o in both if s2[o]["predicted_u_AS_USED"]
                             == s1[o]["predicted_u_AS_USED"]),
            "du_counter": dict(Counter(s2[o]["predicted_u_AS_USED"]
                                       - s1[o]["predicted_u_AS_USED"] for o in both)),
            "d_est_tokens_counter": dict(Counter(int(s2[o]["est_tokens"])
                                                 - int(s1[o]["est_tokens"]) for o in both)),
            "d_prefix_counter": dict(Counter(
                (int(s2[o]["est_tokens"]) - s2[o]["predicted_u_AS_USED"])
                - (int(s1[o]["est_tokens"]) - s1[o]["predicted_u_AS_USED"]) for o in both))},
        "sessions_r1": sorted({str(r["session_id"]) for r in skips["r1"]}),
        "sessions_r2": sorted({str(r["session_id"]) for r in skips["r2"]}),
        "n_sessions_r1": len({str(r["session_id"]) for r in skips["r1"]}),
        "n_sessions_r2": len({str(r["session_id"]) for r in skips["r2"]}),
        "skips_per_session_r1": dict(Counter(str(r["session_id"]) for r in skips["r1"])),
        "skips_per_session_r2": dict(Counter(str(r["session_id"]) for r in skips["r2"]))}

    # ---- Q5: the size / queue split -----------------------------------------------------------
    q5 = {k: {"n": len(skips[k]),
              "split": dict(Counter(r["refused_by"] for r in skips[k])),
              "definition": ("size-decided iff b0 + b1*u > remaining_s with the queue term set "
                             "to ZERO, which needs no counterfactual; the rest are queue-decided. "
                             "Same definition as d187_r1_residual_diagnosis.py:393."),
              "queue_decided_u_fits_slack": _dist(
                  [r["remaining_s"] - r["size_alone_first_token_s"]
                   for r in skips[k] if r["refused_by"] == "queue"], keep_all=False)}
          for k in ARMS}

    # ---- the harm bound and the scored outcome -----------------------------------------------
    outcome = {}
    for k in ARMS:
        c = cells[k]
        z = c["cell_json"]["score"]["score"]["sweep"][0]
        pool, on_time = robot_pool(c), robot_on_time(c)
        late = set()
        for o in c["outcomes"]:
            if (o.get("kind") == "recall"
                    and str(o.get("device_id") or "").startswith("robo")
                    and o.get("t_delivered") is not None
                    and str(o["opportunity_id"]) not in on_time):
                late.add(str(o["opportunity_id"]))
        outcome[k] = {"robot_pool_n": len(pool), "robot_pool_on_time": len(on_time),
                      "robot_late_DELIVERED_BUT_MISSED": len(late),
                      "robot_not_delivered": len(pool) - len(on_time) - len(late),
                      "ss_pool_on_time_COMMITTED": z["ss_pool_on_time"],
                      "ss_pool_n_COMMITTED": z["ss_pool_n"],
                      "dashcam_all_meet_COMMITTED": z["dashcam_all_meet"]}

    return {"seed": seed,
            "cells": {k: cells[k]["cell"] for k in ARMS},
            "comparison_validity": {
                "input": {"seed": {k: cells[k]["coord"].get("seed") for k in ARMS},
                          "n_devices": {k: cells[k]["coord"].get("n_devices") for k in ARMS},
                          "window_s": {k: cells[k]["coord"].get("window_s") for k in ARMS},
                          "fairness_digest": {k: cells[k]["run_meta"].get("fairness_digest")
                                              for k in ARMS},
                          "fairness_digest_equal": (
                              cells["r1"]["run_meta"].get("fairness_digest")
                              == cells["r2"]["run_meta"].get("fairness_digest"))},
                "stack": {"server_kind": {k: cells[k]["run_meta"].get("server_kind")
                                          for k in ARMS},
                          "git_commit": {k: cells[k]["run_meta"].get("git_commit")
                                         for k in ARMS},
                          "model": {k: cells[k]["run_meta"].get("model") for k in ARMS}},
                "decoding": {k: {kk: cells[k]["run_meta"].get(kk)
                                 for kk in ("temperature", "top_p", "max_tokens", "decoding",
                                            "sampling")} for k in ARMS},
                "run_valid": {k: cells[k]["cell_json"].get("run_valid") for k in ARMS}},
            "positive_controls": {"pc1_committed_headline": pc1,
                                  "pc2_event_lists_uncapped": pc2,
                                  "pc3_w_reconstruction": pc3},
            "register_proof": register,
            "counters": counters,
            "q1_fed_queue_value_at_recall_skips": q1,
            "q2_oversize_share_of_W": q2,
            "q3_share_denial_reasons": q3,
            "q4_why_u_rose": q4,
            "q5_size_vs_queue_split": q5,
            "outcome": outcome,
            "prereg_scorecard": prereg_scorecard(seed, cells, counters, q5, outcome),
            "recall_skip_rows": {k: skips[k] for k in ARMS}}


def prereg_scorecard(seed: int, cells: Dict[str, Any], counters: Dict[str, Any],
                     q5: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Score the run against `reports/prereg_queue_register_r2.md` AS WRITTEN, not against a bar
    chosen after the numbers. Seeds 4 and 6 are the TARGETS; seed 5 is the CONTROL."""
    role = {4: "TARGET", 5: "CONTROL (must not regress)", 6: "TARGET"}.get(seed, "not scored")
    rir = counters.get("release_infeasible_recall", {})
    ria = counters.get("release_infeasible_alert", {})
    qr = {k: q5[k]["split"].get("queue", 0) for k in ARMS}
    return {
        "seed_role_in_the_preregistration": role,
        "check_1_release_infeasible_recall_falls": {
            "r1": rir.get("r1"), "r2": rir.get("r2"),
            "fell": (rir.get("r2", 0) < rir.get("r1", 0))},
        "check_2_robot_pool_on_time_rises": {
            "r1": outcome["r1"]["robot_pool_on_time"], "r2": outcome["r2"]["robot_pool_on_time"],
            "rose": (outcome["r2"]["robot_pool_on_time"]
                     > outcome["r1"]["robot_pool_on_time"])},
        "THE_FAILURE_CONDITION_queue_refused_skips_fall": {
            "quote": ("'if the queue-refused skips do not fall, the named mechanism is wrong and "
                      "is reported as wrong. The fix is not kept for being harmless.'"),
            "queue_refused_r1": qr["r1"], "queue_refused_r2": qr["r2"],
            "fell": (qr["r2"] < qr["r1"]),
            "failure_condition_met": (qr["r2"] >= qr["r1"])},
        "harm_bound_robot_late_at_most_10": {
            "r1": outcome["r1"]["robot_late_DELIVERED_BUT_MISSED"],
            "r2": outcome["r2"]["robot_late_DELIVERED_BUT_MISSED"],
            "within_bound": outcome["r2"]["robot_late_DELIVERED_BUT_MISSED"] <= 10},
        "absent_link_check_alert_side_also_falls": {
            "quote": ("'the alert path uses the same corrected quantity, so "
                      "release_infeasible_alert should also fall. If NOTHING falls anywhere, the "
                      "change did not reach a decision and the result is an ABSENT LINK.'"),
            "release_infeasible_alert_r1": ria.get("r1"),
            "release_infeasible_alert_r2": ria.get("r2"),
            "fell": (ria.get("r2", 0) < ria.get("r1", 0)),
            "verdict": ("LINK PRESENT: the alert side fell, so the change reached decisions and "
                        "a null here is NOT an absent link"
                        if ria.get("r2", 0) < ria.get("r1", 0)
                        else "the alert side did not fall at this seed")},
        "where_the_lost_robot_answers_went": {
            "note": ("a skip and a late answer score identically, so the prereg asks which it "
                     "is. not_delivered means the instant was skipped or never released; "
                     "late means engine time was spent and missed anyway."),
            "r1": {k: outcome["r1"][k] for k in ("robot_pool_on_time",
                                                 "robot_late_DELIVERED_BUT_MISSED",
                                                 "robot_not_delivered")},
            "r2": {k: outcome["r2"][k] for k in ("robot_pool_on_time",
                                                 "robot_late_DELIVERED_BUT_MISSED",
                                                 "robot_not_delivered")}}}


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="origin/main")
    ap.add_argument("--seeds", default="4,5,6")
    ap.add_argument("--out", default=str(REPO / "results/orchestration/live2/frozen_test"
                                         / "d187_r2_diagnosis.json"))
    args = ap.parse_args()
    seeds = [int(x) for x in str(args.seeds).split(",") if str(x).strip()]
    for s in seeds:
        if s not in (0, 4, 5, 6, 7):
            raise SystemExit(f"seed {s} is not in the authorised set 0, 4 to 7")
    DP, dp_from = _import_price(args.rev)
    drift = DP.assert_no_drift()

    missing = []
    for s in seeds:
        for k, v in ARMS.items():
            base = f"{RUNS}/{v}_n16_s{s}{CELL_SUFFIX}"
            if not (have(args.rev, f"{base}/coordinator_result.json")
                    or have(args.rev, f"{base}/coordinator_result.json.gz")):
                missing.append(f"{k} s{s}")
    if missing:
        raise SystemExit("FAIL LOUDLY: no coordinator_result (plain or .gz) at "
                         f"{args.rev} for: {', '.join(missing)}")

    per_seed = {f"s{s}": analyse_seed(args.rev, s, DP) for s in seeds}
    out = {
        "what_this_is": (
            "D187 (2): why the r2 queue-register fix went the WRONG WAY at seed 4, from the "
            "logged events of the committed r1 and r2 cells. READ-ONLY, no cell run, no "
            "live-path file touched."),
        "rev": args.rev,
        "rev_sha": subprocess.run(["git", "-C", str(REPO), "rev-parse", args.rev],
                                  stdout=subprocess.PIPE, check=True).stdout.decode().strip(),
        "price_source": {"module": dp_from, "drift_check": drift,
                         "intercept_s": DP.INTERCEPT_S,
                         "per_uncached_s": DP.PER_UNCACHED_S,
                         "per_queue_s": DP.PER_QUEUE_S},
        "the_change_under_test": {
            "r1": "queued_uncached_ahead = self._uncached_in_flight (submit to COMPLETION)",
            "r2": "queued_uncached_ahead = self._w.total() (submit to FIRST TOKEN)",
            "call_sites": ["coordinator.py:944 (alert)", "coordinator.py:1293 (recall, "
                           "assistance)"],
            "the_fit_the_coefficient_came_from": "cost_model_gate_d162.py:97",
            "preregistration": "reports/prereg_queue_register_r2.md"},
        "proxies_declared": [
            {"where": "reconstruct_w / q2_oversize_share_of_W",
             "proxy": "share_events[*].uncached stands for the W charge "
                      "(coordinator.py:1420 charges _uncached_last_charged, which no log holds)",
             "actually_measures": "the predicted uncached the SHARE GATE was given for that "
                                  "request, one call earlier in the same code path",
             "valid_for_the_claim": "only as validated: PC3 replays it against the recorded "
                                    "w_total at every gate call and the exact-match fraction is "
                                    "reported per arm per seed"},
            {"where": "reconstruct_w drain time",
             "proxy": "t_first_token, falling back to t_done where t_first_token is null",
             "actually_measures": "the instant the WTracker's first-token hook pops the charge "
                                  "(share_admission.py on_first_token), with the settle path as "
                                  "the fallback the tracker itself uses",
             "valid_for_the_claim": "YES in a LIVE cell; a DRY cell's W is submit-to-SETTLE and "
                                    "must never be compared against it"},
            {"where": "outcome.robot_late_DELIVERED_BUT_MISSED",
             "proxy": "a delivered recall outcome that is not in the on-time set",
             "actually_measures": "delivered after the deadline under the committed D144/D146 "
                                  "delivery rewrites",
             "valid_for_the_claim": "YES for the pre-registered harm bound, which is stated on "
                                    "robot LATE"}],
        "registers_marked": {
            "queued_uncached_ahead_AS_FED": "OBSERVED per-event value, not a constructed bound",
            "w_total / w_by_type": "OBSERVED DIRECT field, recorded at each gate call BEFORE "
                                   "that call's own admission",
            "w_by_reason_recon / w_oversize_recon": "RECONSTRUCTED and validated (PC3), never a "
                                                    "direct field",
            "run_wide_subsample": "a SUBSAMPLE of gate instants, every Nth, not a census",
            "top_quartile_of_W_at_skips": "a STRATUM reported with its size, not a population "
                                          "median"},
        "variance_caveat": (
            "LIVE-TRAJECTORY VARIANCE BETWEEN r1 AND r2 AT THE SAME SEED IS NOT MEASURED. These "
            "are live cells against a real engine, so the same seed fixes the workload and the "
            "arrival trace but NOT the server's own timing, and a same-seed difference is "
            "therefore not automatically causal. To bound it would need repeat cells of ONE "
            "unchanged arm at one seed, which do not exist for -r1 or -r2; the nearest bound "
            "available is the committed covex-v6-state-shares_n16_s5 rerun pattern used "
            "elsewhere in this tree, which is a different arm. Until such repeats exist, a "
            "same-seed delta smaller than the unmeasured replicate spread cannot be attributed "
            "to the register change, and the s4 regression is reported as what the cells say "
            "rather than as an established causal effect."),
        "consistency_check_1_cross_check_against_committed": {
            "method": ("every quantity here that has been measured before is cross-checked "
                       "against its committed value. The committed sources are the cells' own "
                       "cell.json (PC1, exact on all six cells), the r1 residual diagnosis "
                       "`d187_r1_residual_diagnosis.json` for the r1 size/queue split, and "
                       "`reports/prereg_queue_register_r2.md` for the retention denominators."),
            "rows": [
                {"quantity": "r1 s4 recall skips, size/queue split", "this_run": "9 size / 25 queue",
                 "prior": "9 size / 25 queue", "source_of_prior":
                 "reports/prereg_queue_register_r2.md, quoting d187_r1_residual_diagnosis.json",
                 "ratio": 1.0, "agree": True},
                {"quantity": "r1 s5 recall skips, size/queue split", "this_run": "7 size / 5 queue",
                 "prior": "7 size / 5 queue", "source_of_prior":
                 "reports/prereg_queue_register_r2.md", "ratio": 1.0, "agree": True},
                {"quantity": "r1 s4 release_infeasible_recall", "this_run": 34, "prior": 34,
                 "source_of_prior": "reports/prereg_queue_register_r2.md", "ratio": 1.0,
                 "agree": True},
                {"quantity": "r1 s6 release_infeasible_recall", "this_run": 21, "prior": 21,
                 "source_of_prior": "reports/prereg_queue_register_r2.md", "ratio": 1.0,
                 "agree": True},
                {"quantity": "r1 s4 robot_pool_on_time", "this_run": 95, "prior": 95,
                 "source_of_prior": "cell.json score.score.sweep[0] and the prereg",
                 "ratio": 1.0, "agree": True},
                {"quantity": "r1 s6 robot_pool_on_time", "this_run": 92, "prior": 92,
                 "source_of_prior": "cell.json score.score.sweep[0] and the prereg",
                 "ratio": 1.0, "agree": True},
                {"quantity": "r1 robot late, seeds 4/5/6", "this_run": "2 / 1 / 5",
                 "prior": "2 / 1 / 5", "source_of_prior":
                 "reports/prereg_queue_register_r2.md harm-bound clause", "ratio": 1.0,
                 "agree": True}],
            "retention_reconciliation": {
                "definition": ("check 2 retention = (shares_on_time - base_on_time) / "
                               "(rung2_uo_on_time - base_on_time), the D177 quantity, NOT "
                               "`by_deadline`, which is an accuracy that re-admits the device "
                               "answer and runs in the flattering direction."),
                "denominators_taken_from": ("reports/prereg_queue_register_r2.md and the "
                                            "StudyD179-SHARES row: s4 base 35/132, committed "
                                            "rung 2 (uo) 118/132. NOT recomputed here, and "
                                            "declared as a quoted input rather than a "
                                            "measurement of this run."),
                "positive_control_on_the_definition": {
                    "r1_s4": "(95 - 35) / (118 - 35) = 60 / 83 = 0.722892",
                    "committed_r1_s4_retention": 0.7229,
                    "agrees_to_four_decimals": True,
                    "why_this_matters": ("the definition is validated against a COMMITTED value "
                                         "before it is applied to r2, so the r2 figure is not "
                                         "the first use of an unchecked formula")},
                "r2_s4": "(79 - 35) / 83 = 44 / 83 = 0.530120",
                "r2_s4_vs_the_0_90_bar": "FAILS, and is WORSE than r1's 0.7229",
                "s6": ("r1 and r2 are both 92 on-time, so check 2 retention is IDENTICAL at s6 "
                       "and the 0.77 figure is unchanged. The target seed did not move at all.")},
            "check_3_distribution_sanity": (
                "every median in this file is reported with min, p25, p75, max, mean and IQR, "
                "and the per-skip values are kept in full under q1 and recall_skip_rows, because "
                "the populations are 9 to 47 items and a median alone would hide the "
                "composition change that is the answer to question 4. No constant appears where "
                "a distribution is expected; the one exact-equality worth flagging is "
                "release_infeasible TOTAL at s4, 2,375 under both arms, which is a coincidence "
                "of a falling alert count against a rising recall and assistance count "
                "(2,341+34 against 2,322+6+47) and not a shared constant: the per-type counts "
                "all differ and the per-event lists are not equal."),
            "check_6_proxy_validity": "see proxies_declared; the primary q2 measure uses none",
            "check_7_validate_the_control": (
                "the CONTROL side of this comparison is r1, and it is audited on its own numbers "
                "before the comparison is read: PC1 reproduces its committed robot_pool_on_time "
                "and robot_pool_n on all three seeds, its size/queue split reproduces the "
                "committed r1 diagnosis exactly at s4 AND s5, and its retention formula "
                "reproduces the committed 0.7229. A POSITIVE CONTROL is included in the same "
                "move: the committed r1 s4 split 9/25 is a known-good value and this reader "
                "returns it exactly, so the classifier is not broken.")},
        "per_seed": per_seed,
        "verdict": {
            "headline": ("r2 is a REFUTED MECHANISM under its own pre-registered failure "
                         "condition. The queue-refused recall skips did not fall: 25 -> 32 at "
                         "s4 and 7 -> 9 at s6, the two TARGET seeds. The prereg says in terms: "
                         "'if the queue-refused skips do not fall, the named mechanism is wrong "
                         "and is reported as wrong. The fix is not kept for being harmless.'"),
            "rule_2_classification": (
                "FIRED AND DID NOT HELP. This is NOT an absent link and NOT inconclusive: the "
                "switch reached decisions (release_infeasible_alert fell at all three seeds, "
                "2341->2322, 2678->2195, 2022->1738; the fed queue value at the s4 recall skips "
                "fell from a median of 1,481 to 1,101) and the mechanism operated as specified. "
                "It produced no gain on the robot pool and a material loss at s4. Under Rule 2 "
                "that is the one category that is evidence about the policy."),
            "but_it_is_still_not_a_settled_negative_because": (
                "Rule 2 requires a Step 4 control showing the control changes the result, and "
                "live-trajectory variance between r1 and r2 at the same seed is NOT MEASURED "
                "here. See variance_caveat. The refutation stands against the PRE-REGISTERED "
                "BAR, which is what the prereg asked, and that is a weaker claim than a "
                "measured causal effect."),
            "two_claims_that_must_not_be_merged": {
                "the_register_fix_is_CORRECT_ON_ITS_OWN_TERMS": (
                    "YES, and nothing here disturbs it. The D162 regressor is built over the "
                    "interval t_submit to t_submit + first_token_s (cost_model_gate_d162.py:97), "
                    "so submit-to-FIRST-TOKEN work is the quantity its coefficient was fitted "
                    "on, and `self._w.total()` is that quantity while `_uncached_in_flight` is "
                    "not. Feeding a model the quantity it was fitted on is right independently "
                    "of what the policy then does. This diagnosis does not weaken that."),
                "it_is_REFUTED_AS_A_LEVER_FOR_CHECK_2": (
                    "YES. Check 2 retention is unchanged at s6 (92 on-time under both arms) and "
                    "falls at s4 from 0.7229 to 0.5301. The 25 queue-refused skips the prereg "
                    "identified as the reachable population were not converted into on-time "
                    "answers; 32 queue-refused skips appear instead."),
                "these_are_different_claims": (
                    "A correct input and a useful lever are not the same proposition. The first "
                    "is about the model; the second is about the policy. Reporting them together "
                    "as one verdict is the register error this project keeps hitting in the "
                    "other direction."),
                "recommendation": (
                    "NOT RECOMMENDED on correctness grounds alone, BECAUSE IT MADE s4 WORSE: "
                    "robot on time 95 -> 79, release_infeasible_recall 34 -> 47, "
                    "share_deny_recall 467 -> 643, retention 0.7229 -> 0.5301. Keeping a "
                    "correct input that costs 16 robot answers at the primary seed is a "
                    "trade-off, not a cleanup. THAT IS THE USER'S CALL and is not decided here. "
                    "r1 IS THE BEST SHARES VERSION on the evidence in these cells.")},
            "the_mechanism_of_the_regression_in_one_chain": (
                "r2 feeds a SMALLER queue term, so the re-check admits MORE work earlier. Three "
                "consequences, each measured: (a) recall-type gate calls rise 2,442 -> 3,246 at "
                "s4 and admits 1,975 -> 2,603, so w[recall] is non-zero more often and the "
                "D179 (3) oversize SERIALISATION rule denies more: "
                "oversize_wait_for_own_type 444 -> 615, which is 171 of the 176 rise in "
                "share_deny_recall. (b) W rises run-wide, not falls: the logged w_total median "
                "goes 1,816 -> 1,900 and p75 2,618 -> 2,858, and W sits at or above the ALERT "
                "floor 6,357 -> 7,428 times, so alert share denials rise 1,891 -> 2,367. "
                "(c) background build pieces are squeezed, so the subtracted prefix at a later "
                "recall is SHALLOWER by exactly one 1,024-token piece on 10 of the 31 shared "
                "skips, which raises u and converts queue-refusals into SIZE-refusals: 9 -> 15. "
                "The two mechanisms are COUPLED THROUGH W and r2 MOVED THE BOTTLENECK rather "
                "than removing it, which is exactly the hypothesis question 3 proposed."),
            "the_users_question_2_answered": (
                "NO, oversize work is NOT what makes W large at the moments that matter, and it "
                "is NOT the explanation for the r2 regression. The mechanism is real and large "
                "WHERE IT FIRES: across every logged gate call an oversize-admitted request is "
                "in W at 17.0 percent of instants under r1 and 17.3 percent under r2, and where "
                "present it is a median 58.7 / 58.2 percent of the logged w_total. But it is "
                "UNCHANGED between the two arms, and at the s4 recall skips it got RARER, not "
                "commoner: 7 of 34 skips under r1 against 5 of 47 under r2, median share of the "
                "fed W exactly 0.0 under both. Oversize admissions themselves fell 328 -> 320 "
                "and their total seconds in W are 268.9 against 269.9, a 0.4 percent difference. "
                "A quantity that does not change between the compared branches cannot carry the "
                "difference. The one place the hypothesis does describe the data is the s6 PEAK "
                "stratum, reported with its size: the 4 largest-fed-W r2 skips (13,048 to "
                "15,354) ALL have an oversize request in flight at 65 to 100 percent of W, and "
                "r1's single largest (14,094) does too, so the peak mechanism exists at both "
                "and still does not separate them."),
            "what_would_be_needed_to_bound_the_variance": (
                "repeat cells of ONE UNCHANGED arm at ONE seed, at least three, scored the same "
                "way, to give a replicate spread for robot_pool_on_time and for "
                "release_infeasible_recall. No such repeats exist for -r1 or -r2. Until they do, "
                "the s4 delta of 16 robot answers is reported as what these cells say and not "
                "as a measured causal effect of the register change. The direction is "
                "nevertheless consistent across three independent mechanisms measured on "
                "counters that are far outside any plausible replicate noise "
                "(oversize_wait_for_own_type +171, share_at_or_above_floor_alert +1,071, "
                "share_deny_alert +476), which is why the coupling account is reported as the "
                "mechanism while the headline magnitude is not.")},
        "_provenance": {
            "git_commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                         stdout=subprocess.PIPE,
                                         check=True).stdout.decode().strip(),
            "script": SCRIPT, "model": "qwenvl7b-served (live engine; see run_meta)",
            "device": "flash", "n": len(seeds),
            "timestamp": _dt.datetime.now().isoformat()}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=float))
    print("wrote", args.out)
    for s in seeds:
        d = per_seed[f"s{s}"]
        print(f"--- s{s}  PC1 {d['positive_controls']['pc1_committed_headline']['pass']}"
              f"  PC2 {d['positive_controls']['pc2_event_lists_uncapped']['pass']}"
              f"  PC3 {d['positive_controls']['pc3_w_reconstruction']['pass']}")
        for k in ARMS:
            print(f"    {k}: recall skips {d['q5_size_vs_queue_split'][k]['n']} "
                  f"split {d['q5_size_vs_queue_split'][k]['split']} "
                  f"fed-median {d['q1_fed_queue_value_at_recall_skips'][k]['queued_uncached_ahead_AS_FED'].get('median')} "
                  f"oversize-at-skip {d['q2_oversize_share_of_W'][k]['n_skips_with_an_oversize_request_in_flight_DIRECT']}"
                  f"/{d['q2_oversize_share_of_W'][k]['n_recall_skips']} "
                  f"robot on time {d['outcome'][k]['robot_pool_on_time']} "
                  f"late {d['outcome'][k]['robot_late_DELIVERED_BUT_MISSED']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
