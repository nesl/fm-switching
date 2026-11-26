#!/usr/bin/env python3
"""Pre-registered s4 gate readout (research/study_linksync_s4_gate_prereg.md), items 1 to 5, from the
artefacts of two runs of the SAME trace: our arm and its control. A MECHANISM CHECK, not a
significance test; counts are DESCRIPTIVE. CPU only.

Inputs per run dir: outcomes.jsonl, link_events.json, link_sync_log.json (written when link_events
is on). Scoring uses trace ground truth (when a question was asked) and never feeds a policy.
`--urgent-s` (default 30) is the proposed URGENT-victim definition: the victim's first
post-reconnect question is asked within that many seconds of its reconnect.

PORT-RULE CHECK printed first: a run whose link_ sync counters show no catch-up decision
(`link_sync_releases` == 0) is an ABSENT LINK for the arm that should make them; the control must
show FIFO order (releases in reconnect order).
Item 5 (path) is derived from the controller's question log and delivery times; CORRECTNESS is not
available in a dry run (no cloud letter), so only the path is reported there.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(d):
    d = Path(d)
    out = [json.loads(l) for l in open(d / "outcomes.jsonl")]
    le = json.loads((d / "link_events.json").read_text())
    ls = json.loads((d / "link_sync_log.json").read_text())
    return out, le, ls


def per_victim(d, urgent_s):
    out, le, ls = load(d)
    o = le["outage"]
    victims, t1 = o["robots"], float(o["t_end"])
    arrive = {}
    for e in le["link_log"]:
        if e["ev"] == "arrived":
            arrive[e["device_id"]] = max(arrive.get(e["device_id"], 0.0), float(e["t_arrive"]))
    qlog = {e["query_id"]: e for e in ls["sync_log"] if e["ev"] == "question"}
    rel = [e for e in ls["sync_log"] if e["ev"] == "release"]
    rows = {}
    for v in victims:
        qs = sorted((x for x in out if x["device_id"] == v and x["kind"] == "recall"
                     and x["t_opportunity"] >= t1), key=lambda x: x["t_opportunity"])
        first = qs[0]["t_opportunity"] - t1 if qs else None
        ontime = [x for x in qs if x["within_L"] and x["t_delivered"] is not None]
        item1 = (min(x["t_delivered"] for x in ontime) - t1) if ontime else None
        paths = {}
        for x in qs:
            qid = x["opportunity_id"]
            if not (x["within_L"] and x["t_delivered"] is not None):
                p = "device"
            elif qid in qlog or any(k.endswith(str(x["question_id"])) for k in qlog):
                p = "cloud_question_first"
            elif v in arrive and x["t_opportunity"] >= arrive[v]:
                p = "cloud_full_evidence"
            else:
                p = "cloud_question_first"
            paths[p] = paths.get(p, 0) + 1
        rows[v] = dict(reconnect=t1, drain_s=(None if v not in arrive else round(arrive[v] - t1, 3)),
                       drain_censored=(v not in arrive), first_q_after_reconnect_s=first,
                       urgent=bool(first is not None and first <= urgent_s),
                       first_on_time_cloud_answer_s=item1, item1_censored=(item1 is None),
                       paths=paths, n_questions_after_reconnect=len(qs))
    order = [e["device_id"] for e in rel]
    seen = [e for e in ls["sync_log"] if e["ev"] == "reconnect_seen"]
    est = seen[-1]["next_q_estimates"] if seen else {}
    done = sorted((a, v) for v, a in arrive.items())
    conc = None
    if len(victims) >= 3 and est:
        pairs = agree = 0
        for i in range(len(done)):
            for j in range(i + 1, len(done)):
                a, b = done[i][1], done[j][1]
                if a in est and b in est and est[a] != est[b]:
                    pairs += 1
                    agree += int(est[a] < est[b])
        conc = dict(pairs=pairs, agree=agree, fraction=(agree / pairs if pairs else None))
    win = (t1, max(arrive.values())) if arrive else (t1, t1)
    return dict(victims=victims, rows=rows, release_order=order, completion_order=[v for _a, v in done],
                next_q_estimates=est, concordance=conc, catchup_window=win,
                counters={k: v for k, v in ls["sync_counters"].items() if k.startswith("link_sync") and isinstance(v, int) and v}
                if ls.get("sync_counters") else None)


def loss_in_window(d, victims, win):
    out, _le, _ls = load(d)
    lost = set()
    for x in out:
        if x["device_id"] in victims:
            continue
        if win[0] <= x["t_opportunity"] <= win[1] and not x["within_L"]:
            lost.add(x["opportunity_id"])
    return lost


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ours", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--urgent-s", type=float, default=30.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    o, c = per_victim(a.ours, a.urgent_s), per_victim(a.control, a.urgent_s)
    win = (min(o["catchup_window"][0], c["catchup_window"][0]),
           max(o["catchup_window"][1], c["catchup_window"][1]))
    lo, lc = loss_in_window(a.ours, o["victims"], win), loss_in_window(a.control, c["victims"], win)
    res = dict(port_rule=dict(ours_releases=(o["counters"] or {}).get("link_sync_releases", 0),
                              control_release_order=c["release_order"],
                              control_is_reconnect_fifo=(c["release_order"] == sorted(
                                  c["release_order"], key=lambda x: (c["rows"][x]["reconnect"], x)))),
               ours=o, control=c, item4=dict(window=win, ours_lost=len(lo), control_lost=len(lc),
                                             ours_minus_control=len(lo) - len(lc),
                                             only_ours=sorted(lo - lc), only_control=sorted(lc - lo)))
    print("PORT RULE: ours link_sync_releases", res["port_rule"]["ours_releases"],
          "| control release order", c["release_order"], "FIFO", res["port_rule"]["control_is_reconnect_fifo"])
    for name, r in (("ours", o), ("control", c)):
        print(name, "release order", r["release_order"], "completion", r["completion_order"], "concordance", r["concordance"])
        for v, x in r["rows"].items():
            print("  %s urgent=%s first_q=%s item1=%s (censored %s) drain=%s (censored %s) paths=%s"
                  % (v, x["urgent"], x["first_q_after_reconnect_s"], x["first_on_time_cloud_answer_s"],
                     x["item1_censored"], x["drain_s"], x["drain_censored"], x["paths"]))
    print("item4 non-victim on-time loss in window %s: ours %d control %d diff %d"
          % ([round(x, 2) for x in win], len(lo), len(lc), len(lo) - len(lc)))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
