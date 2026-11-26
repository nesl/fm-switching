#!/usr/bin/env python3
"""E2 dose tooling, window rule A (link_ line). CPU only, no cell.

For each seed choose t0 on a 0.5 s grid in the band [LO, HI] (default [270, 810]) that MAXIMISES the
number of DISTINCT robot questions, over the FULL k=5 prefix of the seed's victim permutation,
that (i) are asked at or after t0 and (ii) have an annotated evidence interval
[answer_start_time, answer_end_time] overlapping the window [t0, t0 + D). One t0 per seed, the same
for every k. Ties are broken to the EARLIEST t0 (the plateau start is reported with its width).

WHAT THE RULE READS. It reads the trace's FUTURE questions and the annotated evidence times. That
is legal for SCENARIO DESIGN (the policy never sees it) and it SELECTS the window that maximises
dose, so the dose is BY CONSTRUCTION and is not an effect size.

Questions do not depend on the outage (the outage moves only history offers and `t_offer`), so
the questions are read once per seed from a trace built with the permutation's k=5 prefix; the
permutation is the 'outage-perm' stream shared with the centre rule, so victims are identical to
the centre rule's.
Usage: link_e2_window_rule_a.py --repo DIR --out FILE [--seed 4 --seed 5]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d262_dose_readings as DR                                             # noqa: E402


def questions(repo, seed, ratio, n, run_s, d):
    DS, TR = DR.load(repo)
    ev = DR.evidence(repo)
    DS.ROBOT_DEADLINE_S = 3.0
    b = TR.generate_trace(seed, n, ratio, run_s, "A", outage_robots_k=5, outage_duration_s=d,
                          outage_placement="evidence", outage_t0_s=0.5 * (run_s - d),
                          **DR.WORKLOAD)
    om = b["meta"]["outage"]
    perm = list(om["victim_permutation"])
    qs = []
    unjoined = 0
    for r in b["records"]:
        if r.get("kind") != "recall_question" or not str(r["device_id"]).startswith("robo"):
            continue
        e = ev.get(str(r.get("question_id") or "").casefold())
        tas = r.get("t_ask_session")
        if e is None or tas is None:
            unjoined += 1
            continue
        sess0 = float(r["t"]) - float(tas)
        qs.append(dict(device=str(r["device_id"]), qid=str(r["question_id"]).casefold(),
                       t=float(r["t"]), a=sess0 + e[0], z=sess0 + e[1]))
    return perm, qs, unjoined, om


def count(qs, devs, t0, t1):
    s = set()
    for q in qs:
        if q["device"] in devs and q["t"] >= t0 and q["a"] < t1 and q["z"] > t0:
            s.add((q["device"], q["qid"]))
    return len(s)


def pair_doses(perm, qs, t0, d):
    t1 = t0 + d
    p13 = set(perm[1:3]); p35 = set(perm[3:5]); p01 = set(perm[0:1])
    return dict(k1=count(qs, p01, t0, t1), k1_to_3=count(qs, p13, t0, t1),
                k3_to_5=count(qs, p35, t0, t1), k5_prefix=count(qs, set(perm[:5]), t0, t1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, action="append", default=None)
    ap.add_argument("--ratio", default="3:11:2")
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--d", type=float, default=120.0)
    ap.add_argument("--lo", type=float, default=270.0)
    ap.add_argument("--hi", type=float, default=810.0)
    ap.add_argument("--step", type=float, default=0.5)
    a = ap.parse_args(argv)
    out = {"_rule": ("A: argmax over t0 on a %.1f s grid in [%g, %g] of the distinct robot "
                     "questions of the full k=5 permutation prefix, asked at or after t0, whose "
                     "evidence interval overlaps [t0, t0+%g); earliest t0 on ties; same t0 for all k"
                     % (a.step, a.lo, a.hi, a.d)),
           "_caveat": ("reads the trace's future questions (legal for scenario design, the policy "
                       "never sees it) and picks the window that maximises dose: the dose is by "
                       "construction and is not an effect size"),
           "seeds": {}}
    for s in sorted(a.seed or [4, 5]):
        perm, qs, unj, om = questions(Path(a.repo), s, a.ratio, a.n, a.run_s, a.d)
        grid = [a.lo + i * a.step for i in range(int(round((a.hi - a.lo) / a.step)) + 1)]
        tot = [(count(qs, set(perm[:5]), t, t + a.d), t) for t in grid]
        best = max(c for c, _t in tot)
        plateau = [t for c, t in tot if c == best]
        t0 = plateau[0]
        centre = 0.5 * (a.run_s - a.d)
        out["seeds"][str(s)] = dict(
            victim_permutation=perm, n_questions_joined=len(qs), n_unjoined=unj,
            t0=t0, k5_prefix_distinct=best, plateau_start=plateau[0], plateau_end=plateau[-1],
            plateau_contiguous=bool(all(abs((plateau[i + 1] - plateau[i]) - a.step) < 1e-9
                                        for i in range(len(plateau) - 1))),
            n_grid=len(grid), n_grid_with_nonzero_at_both_pairs=sum(
                1 for t in grid if (lambda p: p["k1_to_3"] > 0 and p["k3_to_5"] > 0)(
                    pair_doses(perm, qs, t, a.d))),
            doses_at_t0=pair_doses(perm, qs, t0, a.d),
            centre_t0=centre, doses_at_centre=pair_doses(perm, qs, centre, a.d))
        r = out["seeds"][str(s)]
        print("s%d t0 %.1f k5 %d  pairs 1-3 %d 3-5 %d | centre %.1f: 1-3 %d 3-5 %d"
              % (s, t0, best, r["doses_at_t0"]["k1_to_3"], r["doses_at_t0"]["k3_to_5"], centre,
                 r["doses_at_centre"]["k1_to_3"], r["doses_at_centre"]["k3_to_5"]))
    out["matched_total_ruleA"] = sum(v["doses_at_t0"]["k1_to_3"] + v["doses_at_t0"]["k3_to_5"]
                                     for v in out["seeds"].values())
    out["matched_total_centre"] = sum(v["doses_at_centre"]["k1_to_3"] + v["doses_at_centre"]["k3_to_5"]
                                      for v in out["seeds"].values())
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print("matched total rule A", out["matched_total_ruleA"], "centre", out["matched_total_centre"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
