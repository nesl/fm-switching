#!/usr/bin/env python3
"""D226 (3): re-derive every committed valid cell's per-type on-time and correct-by-deadline
under the corrected refusal rule, WITHOUT reruns and WITHOUT the frozen-grid traces (absent on
the Orin analysis host).

WHY A RE-DERIVATION, NOT A score.py RE-RUN. The committed scorer (experiments/orchestration/live2/
scorer/score.py) runs at capture time on flash and writes cell.json; it needs trace.jsonl and
device_answers.jsonl, which live under /home/pragya/data on flash and are not on this host. So the
rescore reads each cell's committed cell.json (the already-scored robot_rows / assistive_rows /
sweep / dashcam_value) together with the cell's own outcomes.jsonl(.gz) and request.jsonl(.gz), and
recomputes the numbers the corrected refusal rule changes. The device-prefix partition
(dash*/robo*/asst*) reproduces the committed pool counts exactly (positive control below), so the
re-derivation is anchored to the committed definitions rather than a reimplementation of them.

THE REFUSAL RULE (unified with score.py::refused_request_ids and broadened over canon's http-400
over-32k set). A cloud request is REFUSED when its request-log row has http_status != 200, or no
http_status together with no prompt_tokens and no output_tokens. The outcome record carries no
refusal signal of its own, so a refusal can only be read from the request log. When the request log
DROPPED the row (the 11-21..11-23 writes), a refused request is invisible and would silently stand
as a cloud answer; such an outcome is treated here as UNVERIFIABLE and nulled (device stands,
else no answer), the one direction that cannot credit a possible refusal. score.py itself FAILS
LOUD on this case for future complete-log runs; the historical re-derivation keeps the cell and
reports the correction (request-log-derived quantities for these cells are flagged unreliable).

THREE NUMBERS PER TYPE, so a reader can see what moved and why:
  committed       - read from cell.json (what the tables carry today);
  recomputed_old  - recomputed nulling only refusals whose row is PRESENT (a complete-log scorer);
                    its divergence from committed is a cell the capture-time scorer mis-scored;
  new             - recomputed nulling present refusals AND unverifiable (absent-row) deliveries;
                    its divergence from recomputed_old is the dropped-row effect.

Correct-by-deadline is exact for robot (robot_rows) and single-shot (assistive_rows). For dashcam
the correctness metric is the Nexar streaming AP, recomputed by the mAP pipeline (dsmap/figdata);
here the monitor on-time frame delta is reported and cells whose monitor on-time set changed are
listed as needing an AP refresh.

Output: results/orchestration/live2/d226_rescore/{rescore.csv, rescore.md, rescore.json}, each
stamped with this file's git sha (the canonical scorer id for D226).
"""
from __future__ import annotations
import csv
import glob
import gzip
import io
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RUNS = os.path.join(ROOT, "results/orchestration/live2/frozen_test/runs")
OUT = os.path.join(ROOT, "results/orchestration/live2/d226_rescore")
SS_L_S = 2.0  # single-shot deadline (D142 item 3); assistive_value.deadline_s confirms per cell


def sha_of(path: str) -> str:
    """Canonical scorer id for D226: the content hash (git hash-object) of the two files that make
    up this scorer -- the committed capture-time scorer (score.py) and this re-derivation driver --
    concatenated. A content hash is stable and available before the commit, and names the exact
    scorer code that produced these numbers regardless of which commit it lands in."""
    files = [os.path.join(ROOT, "experiments/orchestration/live2/scorer/score.py"), path]
    try:
        hs = subprocess.check_output(["git", "-C", ROOT, "hash-object"] + files, text=True).split()
        return "score.py:%s+d226_rescore.py:%s" % (hs[0][:12], hs[1][:12])
    except Exception:
        return "uncommitted"


def opn(p):
    return gzip.open(p, "rt") if p.endswith(".gz") else open(p)


def pick(d, base):
    for ext in (".gz", ""):
        p = os.path.join(d, base + ext)
        if os.path.exists(p):
            return p
    return None


def refused_set(by_id):
    """score.py::refused_request_ids, keyed from a {request_id: row} map."""
    out = set()
    for rid, r in by_id.items():
        hs = r.get("http_status")
        if hs is not None:
            try:
                if int(hs) != 200:
                    out.add(rid)
            except (TypeError, ValueError):
                out.add(rid)
            continue
        if not r.get("prompt_tokens") and not r.get("output_tokens"):
            out.add(rid)
    return out


def within(o, L):
    td = o.get("t_delivered")
    return td is not None and (float(td) - float(o["t_opportunity"])) <= L + 1e-9


def kind_of(o):
    if o.get("kind") == "monitor":
        return "dashcam"
    if (o.get("device_id") or "").startswith("asst"):
        return "ss"
    return "robot"


def rescore_cell(d):
    tag = os.path.basename(d)
    cj_path = os.path.join(d, "cell.json")
    of = pick(d, "outcomes.jsonl")
    rf = pick(d, "request.jsonl") or pick(d, "requests.jsonl")
    if not (os.path.exists(cj_path) and of and rf):
        return None
    cj = json.load(open(cj_path))
    sc = (cj.get("score") or {}).get("score") or {}
    sweep = (sc.get("sweep") or [{}])[0]
    if not sweep:
        return None
    L = {"dashcam": float(sweep.get("L_dash", 1.0)),
         "robot": float(sweep.get("L_rob", 3.0)),
         "ss": float((sc.get("assistive_value") or {}).get("deadline_s", SS_L_S))}

    by_id = {}
    done = {}  # opportunity_id -> t_done, for the D146 completion rewrite
    for l in opn(rf):
        try:
            r = json.loads(l)
            by_id[r.get("request_id")] = r
            if r.get("opportunity_id") and r.get("t_done") is not None:
                done[r["opportunity_id"]] = float(r["t_done"])
        except Exception:
            pass
    refused = refused_set(by_id)
    present = set(by_id)

    # D146 completion-delivery rewrite (score.py load(), DELIVERY=="completion"): a recall-kind
    # outcome (robot AND single-shot both carry kind=="recall") is delivered at COMPLETION, not
    # first token. Committed cell.json on-time uses the rewritten stamp, so the re-derivation must
    # apply the SAME rewrite before _within, else robot/ss on-time is overcounted. It is applied
    # ONLY for cells whose committed score recorded delivery_rule=="completion"; older captures
    # (delivery_rule None/first_token) were scored at first token, so rewriting them would
    # introduce a spurious divergence. Load outcomes once, rewrite in place, reuse.
    use_completion = (sc.get("delivery_rule") == "completion")
    outs = []
    for l in opn(of):
        o = json.loads(l)
        if (use_completion and o.get("kind") == "recall" and o.get("t_delivered") is not None
                and o.get("t_cloud_done") is not None and o.get("opportunity_id") in done):
            o["t_delivered"] = done[o["opportunity_id"]] + (float(o["t_delivered"])
                                                            - float(o["t_cloud_done"]))
        outs.append(o)

    # committed per-type on-time (denominator = pool n)
    dash_on_committed = sum(v["on_time"] for v in sweep.get("dashcam_per_device", {}).values())
    dash_n = sum(v["n_instants"] for v in sweep.get("dashcam_per_device", {}).values())
    committed_on = {"dashcam": dash_on_committed,
                    "robot": sweep.get("robot_pool_on_time", 0),
                    "ss": sweep.get("ss_pool_on_time", 0)}
    pool_n = {"dashcam": dash_n, "robot": sweep.get("robot_pool_n", 0),
              "ss": sweep.get("ss_pool_n", 0)}

    # recompute on-time two ways + collect the outcomes to null, per type
    recomp_old = defaultdict(int)
    recomp_new = defaultdict(int)
    recomp_n = defaultdict(int)
    tonull_absent = defaultdict(int)
    tonull_refused = defaultdict(int)
    null_opps = {"absent": defaultdict(list), "refused": defaultdict(list)}
    for o in outs:
        t = kind_of(o)
        recomp_n[t] += 1
        cp = o.get("cloud_payload") or {}
        rid = cp.get("request_id")
        stands = within(o, L[t])
        is_ref = rid in refused
        is_abs = rid is not None and rid not in present
        # recomputed_old: a complete-log scorer nulls present refusals
        if stands and not is_ref:
            recomp_old[t] += 1
        # new: also null unverifiable (absent-row) standing deliveries
        if stands and not is_ref and not is_abs:
            recomp_new[t] += 1
        if stands and is_ref:
            tonull_refused[t] += 1
            null_opps["refused"][t].append(o.get("opportunity_id"))
        elif stands and is_abs:
            tonull_absent[t] += 1
            null_opps["absent"][t].append(o.get("opportunity_id"))

    # --- correct-by-deadline: robot (robot_rows) and ss (assistive_rows), exact override
    # build opportunity -> (refused/absent) for standing cloud, from outcomes
    opp_null = {}
    for o in outs:
        cp = o.get("cloud_payload") or {}
        rid = cp.get("request_id")
        t = kind_of(o)
        if within(o, L[t]) and (rid in refused or (rid is not None and rid not in present)):
            opp_null[o.get("opportunity_id")] = ("refused" if rid in refused else "absent")

    rr = sc.get("robot_rows") or []
    rob_old = sum(1 for r in rr if r.get("standing_correct_by_deadline"))
    rob_n = len(rr)
    rob_new = 0
    rob_flipped = []
    for r in rr:
        v = bool(r.get("standing_correct_by_deadline"))
        if r.get("source_by_deadline") == "cloud" and r.get("opportunity_id") in opp_null:
            # null the cloud: device stands iff device answered within deadline, else no answer
            v = bool(r.get("device_correct")) if r.get("device_on_time") else False
            if v != bool(r.get("standing_correct_by_deadline")):
                rob_flipped.append(r.get("opportunity_id"))
        rob_new += 1 if v else 0

    ar = sc.get("assistive_rows") or []
    def ss_val(r):
        v = r.get("standing_score_by_deadline")
        return float(v) if v is not None else 0.0
    ss_old = sum(ss_val(r) for r in ar)
    ss_n = len(ar)
    ss_new = 0.0
    ss_flipped = []
    for r in ar:
        v = ss_val(r)
        if r.get("source_by_deadline") == "cloud" and r.get("opportunity_id") in opp_null:
            nv = (float(r.get("device_score") or 0.0) if r.get("device_within_deadline") else 0.0)
            if abs(nv - v) > 1e-12:
                ss_flipped.append(r.get("opportunity_id"))
            v = nv
        ss_new += v

    changed = (recomp_new["dashcam"] != committed_on["dashcam"]
               or recomp_new["robot"] != committed_on["robot"]
               or recomp_new["ss"] != committed_on["ss"]
               or rob_new != rob_old or abs(ss_new - ss_old) > 1e-9)
    pc_diverge = {t: recomp_old[t] - committed_on[t] for t in ("dashcam", "robot", "ss")}

    return dict(
        tag=tag, L=L, pool_n=pool_n,
        on_time={t: dict(committed=committed_on[t], recomputed_old=recomp_old[t],
                         new=recomp_new[t], pool_n=recomp_n[t],
                         pc_divergence=pc_diverge[t],
                         null_absent=tonull_absent[t], null_refused=tonull_refused[t])
                 for t in ("dashcam", "robot", "ss")},
        robot_cbd=dict(old_correct=rob_old, new_correct=rob_new, n=rob_n, flipped=rob_flipped),
        ss_cbd=dict(old_score=round(ss_old, 6), new_score=round(ss_new, 6), n=ss_n,
                    flipped=ss_flipped),
        null_opps={k: {t: v for t, v in dv.items() if v} for k, dv in null_opps.items()},
        changed=changed,
        dashcam_ap_refresh=(recomp_new["dashcam"] != recomp_old["dashcam"]
                            or recomp_old["dashcam"] != committed_on["dashcam"]),
    )


def seed_of(tag):
    m = re.search(r"_s(\d+)_", tag)
    return int(m.group(1)) if m else None


def main():
    os.makedirs(OUT, exist_ok=True)
    sha = sha_of(__file__)
    cells = [d for d in sorted(glob.glob(RUNS + "/*")) if os.path.isdir(d)]
    results = []
    skipped = []
    for d in cells:
        tag = os.path.basename(d)
        s = seed_of(tag)
        if s in (1, 2, 3):
            skipped.append((tag, "seed 1-3"))
            continue
        try:
            r = rescore_cell(d)
        except Exception as e:
            skipped.append((tag, "ERR %s: %s" % (type(e).__name__, e)))
            continue
        if r is None:
            skipped.append((tag, "no cell.json / logs / sweep"))
            continue
        results.append(r)

    changed = [r for r in results if r["changed"]]
    pc_bad = [r for r in results if any(r["on_time"][t]["pc_divergence"] for t in r["on_time"])]
    ap_refresh = [r for r in results if r["dashcam_ap_refresh"]]
    rob_flip = [r for r in results if r["robot_cbd"]["flipped"]]
    ss_flip = [r for r in results if r["ss_cbd"]["flipped"]]

    # CSV: one row per (cell, type) for on-time + a robot/ss cbd block
    with open(os.path.join(OUT, "rescore.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scorer_sha", "cell", "seed", "type", "metric", "committed",
                    "recomputed_old", "new", "pool_n", "pc_divergence",
                    "null_absent", "null_refused", "changed"])
        for r in results:
            s = seed_of(r["tag"])
            for t in ("dashcam", "robot", "ss"):
                ot = r["on_time"][t]
                w.writerow([sha, r["tag"], s, t, "on_time", ot["committed"],
                            ot["recomputed_old"], ot["new"], ot["pool_n"],
                            ot["pc_divergence"], ot["null_absent"], ot["null_refused"],
                            int(ot["new"] != ot["committed"] or ot["pc_divergence"] != 0)])
            rc = r["robot_cbd"]
            w.writerow([sha, r["tag"], s, "robot", "correct_by_deadline", rc["old_correct"],
                        rc["old_correct"], rc["new_correct"], rc["n"], 0, "", "",
                        int(rc["new_correct"] != rc["old_correct"])])
            sv = r["ss_cbd"]
            w.writerow([sha, r["tag"], s, "ss", "correct_by_deadline_score", sv["old_score"],
                        sv["old_score"], sv["new_score"], sv["n"], 0, "", "",
                        int(abs(sv["new_score"] - sv["old_score"]) > 1e-9)])

    summary = dict(
        scorer_sha=sha, n_cells=len(results), n_skipped=len(skipped),
        n_changed=len(changed), n_pc_divergent=len(pc_bad),
        n_dashcam_ap_refresh=len(ap_refresh),
        n_robot_cbd_flipped=len(rob_flip), n_ss_cbd_flipped=len(ss_flip),
        changed_cells=[r["tag"] for r in changed],
        robot_cbd_flipped=[(r["tag"], r["robot_cbd"]["old_correct"], r["robot_cbd"]["new_correct"],
                            r["robot_cbd"]["n"], r["robot_cbd"]["flipped"]) for r in rob_flip],
        ss_cbd_flipped=[(r["tag"], r["ss_cbd"]["old_score"], r["ss_cbd"]["new_score"],
                         r["ss_cbd"]["flipped"]) for r in ss_flip],
        pc_divergent=[(r["tag"], {t: r["on_time"][t]["pc_divergence"]
                                  for t in r["on_time"] if r["on_time"][t]["pc_divergence"]})
                      for r in pc_bad],
        dashcam_ap_refresh_cells=[r["tag"] for r in ap_refresh],
        skipped=skipped,
    )
    with open(os.path.join(OUT, "rescore.json"), "w") as f:
        json.dump(dict(summary=summary, cells=results), f, indent=1, sort_keys=True)

    lines = []
    lines.append("# D226 (3) rescore: corrected refusal rule, re-derived from committed cells\n")
    lines.append("Scorer id (content hash of score.py + this driver): `%s`\n" % sha)
    lines.append("Re-derivation (no reruns; frozen-grid traces absent on this host). Refusal rule "
                 "unified with `score.py::refused_request_ids`: http_status != 200, or no status "
                 "with no prompt/output tokens. An outcome whose standing cloud request is absent "
                 "from the request log is UNVERIFIABLE and nulled (device stands, else no answer).\n")
    lines.append("- cells rescored: **%d**  (skipped %d: seeds 1-3 / no logs)" % (len(results), len(skipped)))
    lines.append("- cells whose on-time or correct-by-deadline CHANGES under the rule: **%d**" % len(changed))
    lines.append("- cells where recomputed_old != committed (capture-time scorer mis-scored a "
                 "PRESENT refusal): **%d**" % len(pc_bad))
    lines.append("- robot correct-by-deadline count changed: **%d** cells" % len(rob_flip))
    lines.append("- single-shot correct-by-deadline score changed: **%d** cells" % len(ss_flip))
    lines.append("- dashcam cells needing an AP (mAP) refresh (monitor on-time set moved): **%d**\n" % len(ap_refresh))

    def fmt_rows(rs):
        out = ["| cell | type | committed | recomputed_old | new | pool_n | null_abs | null_ref |",
               "|---|---|---|---|---|---|---|---|"]
        for r in rs:
            for t in ("dashcam", "robot", "ss"):
                ot = r["on_time"][t]
                if ot["new"] != ot["committed"] or ot["pc_divergence"]:
                    out.append("| %s | %s | %d | %d | %d | %d | %d | %d |" % (
                        r["tag"], t, ot["committed"], ot["recomputed_old"], ot["new"],
                        ot["pool_n"], ot["null_absent"], ot["null_refused"]))
        return out

    lines.append("## On-time changes (per type)\n")
    lines += fmt_rows(changed) if changed else ["(none)"]
    lines.append("\n## Robot correct-by-deadline changes\n")
    if rob_flip:
        lines.append("| cell | old_correct | new_correct | n | flipped_opps |")
        lines.append("|---|---|---|---|---|")
        for r in rob_flip:
            rc = r["robot_cbd"]
            lines.append("| %s | %d | %d | %d | %s |" % (r["tag"], rc["old_correct"],
                         rc["new_correct"], rc["n"], ",".join(rc["flipped"])))
    else:
        lines.append("(none - no robot correct-by-deadline count moved)")
    lines.append("\n## Single-shot correct-by-deadline changes\n")
    if ss_flip:
        lines.append("| cell | old_score | new_score | flipped_opps |")
        lines.append("|---|---|---|---|")
        for r in ss_flip:
            sv = r["ss_cbd"]
            lines.append("| %s | %s | %s | %s |" % (r["tag"], sv["old_score"], sv["new_score"],
                         ",".join(sv["flipped"])))
    else:
        lines.append("(none)")
    open(os.path.join(OUT, "rescore.md"), "w").write("\n".join(lines) + "\n")

    print("\n".join(lines[:16]))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
