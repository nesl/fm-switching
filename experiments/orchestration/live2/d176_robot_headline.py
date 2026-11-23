#!/usr/bin/env python3
"""D176 (3): the D176-COMPLIANT ROBOT HEADLINE COLUMN, BESIDE the as-committed one.

WHAT THIS IS AND WHAT IT IS NOT. This is a REPORTING script. It does not re-score anything, it
does not touch the committed scorer `d179_rung2_verdict.py`, and it never writes a verdict JSON
under a committed label. It reads committed cell outputs and emits TWO columns per arm and seed:

  robot_on_time_of_pool_as_committed   the figure today's committed cells and plots carry, which
                                       INCLUDES the 18 over-limit questions as misses
  robot_on_time_of_pool_d176           the same numerator over the D176 denominator, which
                                       EXCLUDES those 18 for every arm identically

Neither is ever emitted alone. The excluded count and the excluded questions' identities travel
with every row, because a bare 0.9655 next to a remembered 0.8000 is the whole failure this
column exists to prevent.

WHY THE ARM-VERSUS-ARM COMPARISON IS UNCHANGED, and why the column still matters. The 18 are the
SAME 18 for every arm: the robot pool is trace-determined, the pool id SET is identical across
every committed cell at a seed (checked here, set equality and not merely count equality), and
the exclusion is applied identically. Retentions, gains and every arm-versus-arm verdict are
therefore unchanged to the digit. What changes is the ABSOLUTE figure a reader quotes: at seed 7
`covex-v6-fair-c5attr-rr` is 84 of 105 = 0.8000 as committed and 84 of 87 = 0.9655 under D176,
a difference of 0.1655. The Orin's plots must quote the D176 column.

------------------------------------------------------------------------------------------------
THE REGISTER, MARKED ON EVERY FIGURE. Two different quantities wear the name "on time" and they
differ by a few counts per cell. Both are reported for both columns, never mixed:

  DELIVERY (primary)   the committed scorer's rule, `score._within`, which is what
                       `score.score.sweep[0].robot_pool_on_time` holds:
                           t_delivered - t_opportunity <= L + 1e-9
                       with t_delivered first put through the two committed passes transcribed in
                       `_committed_delivery` below (D144 (2) / D175 (1) nulls a refused request's
                       delivery; D146 re-bases a `recall` delivery onto the request's t_done plus
                       the same per-row forward delay). L_rob = 3.0 s.
  FIRST TOKEN (beside) `cloud_payload.on_time`, the COORDINATOR's own online flag, taken at the
                       first token. It is systematically the more generous reading, because
                       `t_delivered` adds the forward delay on top of completion.

A reader who compares one register's count against the other register's bound is making exactly
the mistake this project has already made once (the d179 docstring records 2,209 against 2,349 on
one cell's alert instants). So every number below carries `register` in its own name.

NOT REPORTED HERE, deliberately: `robot_headline.correct_answers_delivered_by_deadline` is an
ACCURACY that admits the DEVICE answer, not an on-time rate (d179_rung2_verdict.py's
ROBOT_ACCURACY_REGISTER). Correcting its denominator is a separate ruling and is out of scope.

------------------------------------------------------------------------------------------------
WHERE THE 18 COME FROM, stated exactly, because "establish them from the data" has a sharp edge
here. NO FILE UNDER runs/ RECORDS A QUESTION'S HISTORY TOKEN COUNT WHEN THE REQUEST WAS NOT SENT.
`outcomes.jsonl.gz` carries `cloud_payload.tokens_charged` only for a request that went, and
`request.jsonl.gz` carries `prompt_tokens` only for one the engine answered; neither has a
`history_tokens` field, and no cell output contains the string 32768. So the MEMBERSHIP CRITERION
(trace `history_tokens` > 32,768) is read from the committed, arm-independent record that the
harness's own D170 pass wrote:

    results/orchestration/live2/frozen_test/d170_overlimit.json
      -> offered_by_seed["<seed>"]["opportunity_ids"]        (the field used)

built by `d170_overlimit.py` from `trace.generate_trace(...)` record field `history_tokens`,
which is deterministic in the seed and identical for every arm by construction.

THAT SET IS THEN CORROBORATED FROM THE CELL OUTPUTS THEMSELVES, five ways, each a stopping
condition if it fails (see `_establish_exclusions`):

  (a) every excluded id is a `robo` recall opportunity in every cell's own pool;
  (b) all of them share ONE device_id and ONE session_id per seed, read from the outcome rows;
  (c) they are EXACTLY that session's recall opportunities (18 of robo004's 21 at seed 7; the
      other 3 are session s001, which the cells show sent at 7,237 / 7,417 / 9,217 prompt tokens,
      comfortably under the limit, as a session that starts from zero must be);
  (d) the only DIRECT in-cell over-limit evidence that exists - an outcome whose
      `tokens_charged` or a request whose `prompt_tokens` exceeds 32,768 - is a SUBSET of the
      set. At seed 7 that evidence is `always-cloud-fcfs` sending opp0006097 and opp0008403 at
      38,821 and 48,811 tokens charged, both inside the 18. An over-limit send OUTSIDE the set
      would be a definition clash and stops the run;
  (e) seeds 4 to 6 have an EMPTY set and no cell shows any over-limit send or prompt there, so
      their two columns must come out EQUAL. That equality is check 1.

------------------------------------------------------------------------------------------------
READ-ONLY, AND ON WHICH TREE. Cell outputs are read either from a runs directory on disk
(`--runs`) or, when this box's checkout does not hold them, straight out of git objects
(`--git-ref <sha>`), which is the same committed bytes without spending disk on a tree export.

USAGE

  python d176_robot_headline.py --git-ref <sha> \
      --out results/orchestration/live2/d176_headline/d176_robot_headline.json \
      --report reports/study_d176_headline.md
  python d176_robot_headline.py --runs <runs dir> --out <json> [--report <md>]
      [--seeds 4,5,6,7] [--tag _L3_epg_rq30]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

LIMIT_TOKENS = 32768
L_ROB = 3.0
EPS = 1e-9
ROBOT_PREFIX = "robo"
DEFAULT_SEEDS = (4, 5, 6, 7)
DEFAULT_TAG = "_L3_epg_rq30"
CELL_SUFFIX = "_n16_s%d_1200s_h27_3t%s"

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
RUNS_REL = "results/orchestration/live2/frozen_test/runs"
OVERLIMIT_REL = "results/orchestration/live2/frozen_test/d170_overlimit.json"

# The covex-v6 ladder. Each entry is (reported name, the committed cell's arm slug, role). Two of
# the ladder's names are not the slug the cells carry and the identity is cited, not assumed:
#   covex-v6-base  == hybrid-F-lhreq-noc3   (d181_share_floors.json `source` states it, and the
#                                            d179_rung2_verdict.py docstring repeats it)
#   covex-v6-rules == v5-rules-2            (design log D-row: "covex-v6-rules (+ chunked JIT
#                                            warming + saturation guard; was v5-rules-2)")
LADDER: Tuple[Tuple[str, str, str], ...] = (
    ("covex-v6-base", "hybrid-F-lhreq-noc3", "ladder rung 0 (base)"),
    ("covex-v6-rules", "v5-rules-2", "ladder rung 1 (rules)"),
    ("covex-v6-state-uo", "covex-v6-state-uo", "ladder rung 2, plain"),
    ("covex-v6-state-uo-c5attr", "covex-v6-state-uo-c5attr", "ladder rung 2, c5attr"),
    ("covex-v6-fair-c5attr", "covex-v6-fair-c5attr", "ladder rung 3"),
    ("covex-v6-fair-c5attr-rr", "covex-v6-fair-c5attr-rr", "ladder rung 3 + rr"),
    ("covex-v6-cf-c5attr", "covex-v6-cf-c5attr", "ladder rung 4 (counterfactual)"),
)
# Rung 4's cells were not committed when this was written and its slug is not yet fixed on disk,
# so the resolver tries the plausible spellings and reports MISSING with the list it tried rather
# than silently dropping the rung.
RUNG4_CANDIDATES = ("covex-v6-cf-c5attr", "covex-v6-cfpd-c5attr", "covex-v6-cf-pd-c5attr",
                    "covex-v6-cfpd", "covex-v6-cf")

# D205 (1): these arms' committed cells are SUPERSEDED (every reader of a literal 0.0 score
# escalated on every instant). Their rows are still emitted - the correction applies to whatever
# is reported - but the label travels with them so no one quotes one as a current figure.
SUPERSEDED_D205 = ("r3-streaming", "thinking-qwenvl", "uniscale", "b4", "inar-vl", "hybrid-llm",
                   "confidence-cascade")
# Arms that are ablations or earlier rungs rather than the reported baseline set.
ABLATION = ("covex-v6-state-shares", "covex-v6-state-shares-r1", "covex-v6-state-shares-r2",
            "covex-v6-fair-c5attr-gain0", "covex-v6-state", "v5-rules")

COLUMN_NAMES = ("robot_on_time_of_pool_as_committed", "robot_on_time_of_pool_d176")


# ------------------------------------------------------------------------------------------------
# sources


class Source:
    """Committed cell outputs, from a runs directory or straight out of git objects."""

    def __init__(self, runs: Optional[str], git_ref: Optional[str]) -> None:
        self.runs = runs
        self.git_ref = git_ref
        if (runs is None) == (git_ref is None):
            raise SystemExit("give exactly one of --runs and --git-ref")
        self.kind = "filesystem" if runs else "git"

    def _git(self, rel: str) -> Optional[bytes]:
        r = subprocess.run(["git", "-C", REPO, "show", "%s:%s" % (self.git_ref, rel)],
                           capture_output=True)
        return None if r.returncode else r.stdout

    def raw(self, rel: str) -> Optional[bytes]:
        if self.kind == "git":
            return self._git(rel)
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as fh:
            return fh.read()

    def cell_raw(self, cell: str, name: str) -> Optional[bytes]:
        if self.kind == "filesystem":
            path = os.path.join(self.runs, cell, name)
            if not os.path.exists(path):
                return None
            with open(path, "rb") as fh:
                return fh.read()
        return self._git("%s/%s/%s" % (RUNS_REL, cell, name))

    def cell_json(self, cell: str, name: str) -> Optional[Dict[str, Any]]:
        raw = self.cell_raw(cell, name)
        return None if raw is None else json.loads(raw.decode())

    def cell_jsonl(self, cell: str, name: str) -> Optional[List[Dict[str, Any]]]:
        raw = self.cell_raw(cell, name + ".gz")
        if raw is not None:
            raw = gzip.decompress(raw)
        else:
            raw = self.cell_raw(cell, name)
        if raw is None:
            return None
        return [json.loads(l) for l in raw.decode().splitlines() if l.strip()]

    def cells(self) -> List[str]:
        if self.kind == "filesystem":
            return sorted(d for d in os.listdir(self.runs)
                          if os.path.isdir(os.path.join(self.runs, d)))
        out = subprocess.run(["git", "-C", REPO, "ls-tree", "-r", "--name-only", self.git_ref,
                              "--", RUNS_REL + "/"], capture_output=True, check=True).stdout
        names: Set[str] = set()
        for line in out.decode().splitlines():
            rest = line[len(RUNS_REL) + 1:]
            if "/" in rest:
                names.add(rest.split("/")[0])
        return sorted(names)


# ------------------------------------------------------------------------------------------------
# the committed delivery rule, transcribed


def _committed_delivery(outcomes: List[Dict[str, Any]],
                        reqs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The committed scorer's two delivery passes, keyed by opportunity_id.

    Transcribed from scorer/score.py (the same transcription d179_rung2_verdict.py carries and
    proves) rather than imported, because `score.load` needs the trace tree and this script must
    run on a box that holds only committed run outputs. The transcription is not asserted: the
    positive control re-derives each cell's own `sweep[0].robot_pool_on_time` and demands exact
    equality, and a mismatch means THIS SCRIPT IS WRONG, NOT THE COMMITTED NUMBER.
    """
    out = {o["opportunity_id"]: dict(o) for o in outcomes}
    failed: Set[Any] = set()
    for r in reqs:
        hs = r.get("http_status")
        if hs is not None:
            try:
                if int(hs) != 200:
                    failed.add(r.get("request_id"))
            except (TypeError, ValueError):
                failed.add(r.get("request_id"))
            continue
        if not r.get("prompt_tokens") and not r.get("output_tokens"):
            failed.add(r.get("request_id"))
    for o in out.values():
        cp = o.get("cloud_payload") or {}
        if cp.get("request_id") in failed:
            o["t_delivered"] = None
            o["cloud_payload"] = None
            o["d144_failed_request"] = True
    done = {r["opportunity_id"]: float(r["t_done"]) for r in reqs
            if r.get("opportunity_id") and r.get("t_done") is not None}
    for oid, o in out.items():
        if o.get("kind") != "recall" or o.get("t_delivered") is None:
            continue
        if o.get("t_cloud_done") is None or oid not in done:
            continue
        o["t_delivered_first_token"] = o["t_delivered"]
        o["t_delivered"] = done[oid] + (float(o["t_delivered"]) - float(o["t_cloud_done"]))
    return out


def _within(o: Dict[str, Any], L: float) -> bool:
    td = o.get("t_delivered")
    return td is not None and (float(td) - float(o["t_opportunity"])) <= L + EPS


def _flag_on_time(o: Dict[str, Any]) -> bool:
    return bool((o.get("cloud_payload") or {}).get("on_time"))


def _frac(k: int, n: int) -> Optional[float]:
    return round(k / n, 6) if n else None


# ------------------------------------------------------------------------------------------------
# cell reading


def read_cell(src: Source, cell: str) -> Dict[str, Any]:
    """One cell: its committed score block, its robot pool, and both registers on both columns."""
    cj = src.cell_json(cell, "cell.json")
    outcomes = src.cell_jsonl(cell, "outcomes.jsonl")
    reqs = src.cell_jsonl(cell, "request.jsonl")
    if cj is None or outcomes is None or reqs is None:
        missing = [n for n, v in (("cell.json", cj), ("outcomes.jsonl.gz", outcomes),
                                  ("request.jsonl.gz", reqs)) if v is None]
        return {"cell": cell, "usable": False, "missing_files": missing,
                "_why": "an incomplete cell directory is reported, never silently skipped"}

    delivered = _committed_delivery(outcomes, reqs)
    pool = [o for o in delivered.values()
            if str(o.get("device_id") or "").startswith(ROBOT_PREFIX)]
    pool_ids = {o["opportunity_id"] for o in pool}

    score = ((cj.get("score") or {}).get("score") or {})
    sweep = (score.get("sweep") or [{}])[0]
    required = ("robot_pool_n", "robot_pool_on_time", "robot_pool_fraction")
    missing_keys = [k for k in required if k not in sweep]

    prompt_tokens = {r["opportunity_id"]: int(r["prompt_tokens"] or 0) for r in reqs
                     if r.get("opportunity_id") and r.get("prompt_tokens")}
    # READ FROM THE RAW OUTCOME ROWS, not from `delivered`. The D144/D175 pass sets
    # `cloud_payload = None` on a refused request, and the only over-limit sends that exist in the
    # committed set ARE refusals (always-cloud-fcfs at seed 7, 38,821 and 48,811 tokens charged),
    # so reading tokens_charged after the pass emptied this corroboration to nothing while every
    # other number stayed right. A corroboration that silently becomes vacuous is worse than one
    # that fails, so the raw rows are used and the count is asserted non-zero in the summary.
    charged = {o["opportunity_id"]: int(((o.get("cloud_payload") or {}).get("tokens_charged"))
                                        or 0)
               for o in outcomes if o.get("opportunity_id") in pool_ids}
    sent_over = sorted({oid for oid, tc in charged.items() if tc > LIMIT_TOKENS}
                       | {oid for oid, pt in prompt_tokens.items()
                          if oid in pool_ids and pt > LIMIT_TOKENS})

    return {
        "cell": cell,
        "usable": True,
        "arm_slug_in_cell": cj.get("arm"),
        "seed": cj.get("seed"),
        "n_devices": cj.get("n_devices"),
        "run_valid": cj.get("run_valid"),
        "digests_equal": cj.get("digests_equal"),
        "committed_score_block": {
            "_path": "cell.json -> score -> score -> sweep[0]",
            "_required_keys_missing_FLAG": missing_keys,
            "robot_pool_n": sweep.get("robot_pool_n"),
            "robot_pool_on_time": sweep.get("robot_pool_on_time"),
            "robot_pool_fraction": sweep.get("robot_pool_fraction"),
            "L_rob": sweep.get("L_rob"),
            "p_rob": sweep.get("p_rob"),
            "delivery_rule": score.get("delivery_rule"),
            "on_time_rule": score.get("on_time_rule"),
        },
        "_pool_rows": pool,
        "_pool_ids": pool_ids,
        "_robot_rows": score.get("robot_rows") or [],
        "in_cell_over_limit_sends": {
            "_test": ("cloud_payload.tokens_charged > 32768, or the request log's prompt_tokens "
                      "> 32768, on a robo recall opportunity. This is the ONLY direct over-limit "
                      "evidence any cell output carries"),
            "opportunity_ids": sent_over,
            "n": len(sent_over),
            "tokens_charged": {oid: charged[oid] for oid in sent_over if oid in charged},
        },
        "max_prompt_tokens_on_robot_pool": max([0] + [pt for oid, pt in prompt_tokens.items()
                                                      if oid in pool_ids]),
    }


def columns(cell: Dict[str, Any], excluded: Set[str]) -> Dict[str, Any]:
    """BOTH columns, in BOTH registers, with numerators, denominators and the excluded identities.

    The two columns share a numerator whenever every excluded question is a miss, which is the
    case here; the code does not assume it. It counts the numerator over each denominator
    separately, and reports the excluded questions' own outcomes so a reader can see that they
    were misses rather than take it on trust.
    """
    pool = cell["_pool_rows"]
    ex_rows = [o for o in pool if o["opportunity_id"] in excluded]
    keep = [o for o in pool if o["opportunity_id"] not in excluded]

    def col(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        k_del = sum(1 for o in rows if _within(o, L_ROB))
        k_tok = sum(1 for o in rows if _flag_on_time(o))
        return {
            "register_DELIVERY_PRIMARY": {
                "_register": ("the committed scorer's delivery rule, t_delivered - "
                              "t_opportunity <= 3.0 s + 1e-9, after the D144/D175 refusal pass "
                              "and the D146 completion re-base; this is what "
                              "sweep[0].robot_pool_on_time holds"),
                "on_time": k_del, "n": len(rows), "fraction": _frac(k_del, len(rows)),
            },
            "register_FIRST_TOKEN_BESIDE": {
                "_register": ("cloud_payload.on_time, the coordinator's own online flag at the "
                              "FIRST TOKEN; systematically more generous than the delivery rule "
                              "because t_delivered adds the forward delay. Never compared "
                              "against a delivery-rule bound"),
                "on_time": k_tok, "n": len(rows), "fraction": _frac(k_tok, len(rows)),
            },
        }

    return {
        COLUMN_NAMES[0]: col(pool),
        COLUMN_NAMES[1]: col(keep),
        "_both_columns_are_always_emitted": True,
        "excluded_n": len(ex_rows),
        "excluded_opportunity_ids": sorted(o["opportunity_id"] for o in ex_rows),
        "excluded_identity": [
            {"opportunity_id": o["opportunity_id"], "device_id": o.get("device_id"),
             "session_id": o.get("session_id"),
             "t_opportunity_s": round(float(o["t_opportunity"]), 3),
             "on_time_DELIVERY": _within(o, L_ROB),
             "on_time_FIRST_TOKEN": _flag_on_time(o),
             "tokens_charged": ((o.get("cloud_payload") or {}).get("tokens_charged"))}
            for o in sorted(ex_rows, key=lambda o: o["opportunity_id"])],
        "excluded_all_were_misses_in_both_registers": (
            all(not _within(o, L_ROB) and not _flag_on_time(o) for o in ex_rows)
            if ex_rows else None),
        "delta_fraction_d176_minus_as_committed_DELIVERY": (
            None if not pool or not keep else
            round(_frac(sum(1 for o in keep if _within(o, L_ROB)), len(keep))
                  - _frac(sum(1 for o in pool if _within(o, L_ROB)), len(pool)), 6)),
    }


# ------------------------------------------------------------------------------------------------
# the exclusion set and its corroboration


def _establish_exclusions(src: Source, cells_by_seed: Dict[int, List[Dict[str, Any]]],
                          seeds: Sequence[int]) -> Dict[str, Any]:
    """The over-limit set per seed, with its provenance and five stopping-condition checks."""
    raw = src.raw(OVERLIMIT_REL)
    if raw is None:
        raise SystemExit("cannot read %s; the membership criterion has no committed source"
                         % OVERLIMIT_REL)
    d170 = json.loads(raw.decode())
    offered = d170.get("offered_by_seed") or {}

    res: Dict[str, Any] = {
        "_membership_criterion": ("the trace's recall record field `history_tokens` exceeds the "
                                 "32,768-token server context limit"),
        "_field_used": "%s -> offered_by_seed[<seed>].opportunity_ids" % OVERLIMIT_REL,
        "_why_not_from_runs": ("no file under runs/ records a question's history token count when "
                              "the request was not sent: outcomes.jsonl.gz has tokens_charged "
                              "only for a sent request, request.jsonl.gz has prompt_tokens only "
                              "for an answered one, neither has history_tokens, and no cell "
                              "output contains the string 32768. The criterion is therefore read "
                              "from the committed arm-independent D170 record and CORROBORATED "
                              "from the cells, five ways, each a stopping condition"),
        "_limit_tokens": LIMIT_TOKENS,
        "by_seed": {},
        "checks": {},
        "stop": [],
    }
    sets: Dict[int, Set[str]] = {}
    for s in seeds:
        ids = set((offered.get(str(s)) or {}).get("opportunity_ids") or [])
        sets[s] = ids
        res["by_seed"][str(s)] = {
            "n": len(ids),
            "opportunity_ids": sorted(ids),
            "max_history_tokens_d170": (offered.get(str(s)) or {}).get("max_history_tokens"),
        }

    # (a) present in every cell's own pool; (b) one device and one session; (c) exactly that
    # session's recall opportunities.
    ident: Dict[str, Any] = {}
    for s in seeds:
        usable = [c for c in cells_by_seed.get(s, []) if c["usable"]]
        if not usable:
            continue
        not_in_pool = {c["cell"]: sorted(sets[s] - c["_pool_ids"]) for c in usable
                       if sets[s] - c["_pool_ids"]}
        if not_in_pool:
            res["stop"].append("excluded ids absent from a cell's robot pool at seed %d: %s"
                               % (s, not_in_pool))
        ref = usable[0]
        rows = [o for o in ref["_pool_rows"] if o["opportunity_id"] in sets[s]]
        devices = sorted({str(o.get("device_id")) for o in rows})
        sessions = sorted({str(o.get("session_id")) for o in rows})
        qids = [o.get("question_id") for o in rows]
        first_ask: Dict[Any, str] = {}
        for o in sorted((o for o in ref["_pool_rows"]
                         if str(o.get("device_id")) in devices),
                        key=lambda o: float(o["t_opportunity"])):
            first_ask.setdefault(o.get("question_id"), o["opportunity_id"])
        reasks = [o["opportunity_id"] for o in rows
                  if first_ask.get(o.get("question_id")) != o["opportunity_id"]]
        same_session_pool = sorted(o["opportunity_id"] for o in ref["_pool_rows"]
                                   if str(o.get("session_id")) in sessions)
        ident[str(s)] = {
            "n": len(rows),
            "device_ids": devices,
            "session_ids": sessions,
            "one_device_and_one_session": len(devices) == 1 and len(sessions) == 1,
            "t_opportunity_s_min": (round(min(float(o["t_opportunity"]) for o in rows), 3)
                                    if rows else None),
            "t_opportunity_s_max": (round(max(float(o["t_opportunity"]) for o in rows), 3)
                                    if rows else None),
            "distinct_question_ids": len(set(qids)),
            "re_asks": len(reasks),
            "original_asks": len(rows) - len(reasks),
            "equals_that_session_whole_recall_pool": same_session_pool == sorted(sets[s]),
            "session_pool_n": len(same_session_pool),
            "identity_read_from": "%s outcomes.jsonl.gz rows" % ref["cell"],
        }
        if rows and not ident[str(s)]["one_device_and_one_session"]:
            res["stop"].append("the excluded set at seed %d spans %d devices and %d sessions"
                               % (s, len(devices), len(sessions)))
    res["checks"]["identity_from_cell_outputs"] = ident

    # (d) direct in-cell over-limit evidence must be a SUBSET of the set.
    direct: Dict[str, Any] = {"cells_with_evidence": [], "all_inside_the_set": True}
    for s in seeds:
        for c in cells_by_seed.get(s, []):
            if not c["usable"]:
                continue
            got = set(c["in_cell_over_limit_sends"]["opportunity_ids"])
            if not got:
                continue
            outside = sorted(got - sets[s])
            direct["cells_with_evidence"].append({
                "cell": c["cell"], "seed": s, "opportunity_ids": sorted(got),
                "tokens_charged": c["in_cell_over_limit_sends"]["tokens_charged"],
                "outside_the_set": outside})
            if outside:
                direct["all_inside_the_set"] = False
                res["stop"].append("cell %s sent an over-limit request for %s, which is NOT in "
                                   "the D170 set: definition clash" % (c["cell"], outside))
    direct["n_cells_with_evidence"] = len(direct["cells_with_evidence"])
    direct["_if_this_is_empty"] = (
        "no cell output shows a single over-limit send anywhere, so corroboration (d) is VACUOUS "
        "rather than passed and must be reported as such, not as a pass. It is non-empty on the "
        "committed set: always-cloud-fcfs at seed 7")
    res["checks"]["direct_in_cell_over_limit_evidence"] = direct

    # (e) seeds with an empty set must show no over-limit prompt anywhere.
    empty = {str(s): {
        "n_excluded": len(sets[s]),
        "max_prompt_tokens_on_robot_pool_over_cells": max(
            [0] + [c["max_prompt_tokens_on_robot_pool"] for c in cells_by_seed.get(s, [])
                   if c["usable"]]),
    } for s in seeds if not sets[s]}
    for s, blk in empty.items():
        if blk["max_prompt_tokens_on_robot_pool_over_cells"] > LIMIT_TOKENS:
            res["stop"].append("seed %s has an empty exclusion set but a cell shows a robot "
                               "prompt of %d tokens" % (s, blk["max_prompt_tokens_on_robot_pool_over_cells"]))
    res["checks"]["seeds_with_no_exclusions"] = empty

    res["_sets"] = sets
    return res


def _arm_invariance(cells_by_seed: Dict[int, List[Dict[str, Any]]],
                    sets: Dict[int, Set[str]]) -> Dict[str, Any]:
    """SET equality, not count equality, per seed: the pool and the exclusion.

    An arm-dependent exclusion would change the arm-versus-arm comparison, which is the one thing
    this correction must not do, so this is a stopping condition and not a note.
    """
    out: Dict[str, Any] = {
        "_what": ("per seed: the robot pool's opportunity-id SET and the applied exclusion SET, "
                  "compared across every usable cell. Counts are reported too, but set equality "
                  "is the test; equal counts over different ids would pass a count check and "
                  "change the comparison"),
        "by_seed": {}, "stop": [],
    }
    for s, cells in sorted(cells_by_seed.items()):
        usable = [c for c in cells if c["usable"]]
        if not usable:
            out["by_seed"][str(s)] = {"n_cells": 0, "verdict": "NO USABLE CELL"}
            continue
        pool_sets = {c["cell"]: frozenset(c["_pool_ids"]) for c in usable}
        applied = {c["cell"]: frozenset(sets[s] & c["_pool_ids"]) for c in usable}
        pool_equal = len(set(pool_sets.values())) == 1
        excl_equal = len(set(applied.values())) == 1
        ref_pool = next(iter(pool_sets.values()))
        out["by_seed"][str(s)] = {
            "n_cells": len(usable),
            "robot_pool_n_by_cell": {c: len(v) for c, v in pool_sets.items()},
            "robot_pool_id_SET_equal_across_arms": pool_equal,
            "robot_pool_n": len(ref_pool),
            "exclusion_id_SET_equal_across_arms": excl_equal,
            "exclusion_n": len(next(iter(applied.values()))),
            "d176_denominator": len(ref_pool) - len(next(iter(applied.values()))),
            "verdict": "ARM-INVARIANT" if pool_equal and excl_equal else "NOT ARM-INVARIANT",
            "symmetric_differences": ({} if pool_equal and excl_equal else {
                c: {"pool_only_here": sorted(frozenset(pool_sets[c]) - ref_pool),
                    "pool_missing_here": sorted(ref_pool - frozenset(pool_sets[c]))}
                for c in pool_sets}),
        }
        if not (pool_equal and excl_equal):
            out["stop"].append("seed %d: exclusion or pool is NOT arm-invariant" % s)
    return out


# ------------------------------------------------------------------------------------------------
# checks


def positive_control(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The as-committed column must reproduce each cell's own committed figure EXACTLY.

    Consistency check 7. The control is the side of this comparison that is never otherwise
    audited: the D176 column has no committed counterpart to check against, so the only thing that
    can show this script reads the cells correctly is that its UNCORRECTED column lands on the
    committed number to the digit, on cells it did not derive anything from. A failure here means
    THE SCRIPT IS WRONG, NOT THE COMMITTED NUMBER.
    """
    per = []
    for r in rows:
        cm = r["committed_score_block"]
        mine = r["columns"][COLUMN_NAMES[0]]["register_DELIVERY_PRIMARY"]
        checks = [("robot_pool_on_time", cm["robot_pool_on_time"], mine["on_time"]),
                  ("robot_pool_n", cm["robot_pool_n"], mine["n"]),
                  ("robot_pool_fraction", cm["robot_pool_fraction"], mine["fraction"])]
        row = {
            "cell": r["cell"], "arm": r["arm_reported_name"], "seed": r["seed"],
            "checks": [{"quantity": q, "committed": w, "recomputed": g, "agree": w == g}
                       for q, w, g in checks],
            "pass": all(w == g for _, w, g in checks),
        }
        if not row["pass"]:
            row["diagnosis"] = _pc_diagnosis(r)
            row["explained_pre_d175"] = bool(row["diagnosis"]["every_difference_is_a_refusal"])
        per.append(row)
    strict = [p for p in per if p["pass"]]
    explained = [p for p in per if not p["pass"] and p.get("explained_pre_d175")]
    unexplained = [p for p in per if not p["pass"] and not p.get("explained_pre_d175")]
    return {
        "_what": ("the as-committed column, re-derived here from outcomes.jsonl.gz plus "
                  "request.jsonl.gz, against each cell's own score.sweep[0] block"),
        "tolerance": "EXACT, 0 counts",
        "cells": per,
        "n_cells": len(per),
        "n_pass_exact": len(strict),
        "n_explained_pre_d175": len(explained),
        "n_unexplained": len(unexplained),
        "verdict": ("PASS" if per and not unexplained and not explained else
                    ("PASS WITH EXPLAINED PRE-D175 CELLS" if per and not unexplained else "FAIL")),
        "_explained_means": (
            "the cell was scored BEFORE the D175 (1) guard, so its committed numerator counts a "
            "REFUSED request as a delivery. The difference is itemised per opportunity and every "
            "differing one is shown to be a refusal (no http_status, no prompt_tokens, no "
            "output_tokens). D175 (1) was amended on 2026-11-23 to say the guard is NOT a no-op "
            "and no cell may be scored assuming it is; such a cell is listed, with its arm, and "
            "its own committed figure is the one that is stale"),
        "_if_it_fails_unexplained": ("THE SCRIPT IS WRONG, NOT THE COMMITTED NUMBER. Report the "
                                     "script failure, not the comparison."),
    }


def _pc_diagnosis(r: Dict[str, Any]) -> Dict[str, Any]:
    """Itemise a positive-control difference per opportunity, and say what each one is.

    A count that is one short is not a diagnosis. The only readings that make a mismatch
    EXPLAINED rather than a script bug are per-question ones, so this lists every opportunity the
    cell's own pre-guard `within_L` flag counts and this script's rule does not, and tests each
    against the D144/D175 refusal condition.
    """
    # THE PER-QUESTION COMPARATOR IS `score.robot_rows[].source_by_deadline == "cloud"`, which is
    # the committed scorer's own per-question record of "the cloud answer arrived inside the 3 s
    # deadline" and sums to `sweep[0].robot_pool_on_time`. It is NOT the outcome row's `within_L`
    # flag: that is the harness's online flag, it is set on opportunities the committed numerator
    # does not count, and diffing against it produced two differences on a cell whose count is one
    # short, which diagnoses nothing. The sum identity is checked below rather than assumed.
    own_on_time = {str(x.get("opportunity_id")) for x in (r.get("_robot_rows") or [])
                   if x.get("source_by_deadline") == "cloud"}
    diffs = []
    for o in r["_pool_rows"]:
        own = o["opportunity_id"] in own_on_time
        mine = _within(o, L_ROB)
        if own == mine:
            continue
        diffs.append({
            "opportunity_id": o["opportunity_id"],
            "device_id": o.get("device_id"),
            "committed_scorer_source_by_deadline_is_cloud": own,
            "this_script_delivery_rule": mine,
            "d144_failed_request": bool(o.get("d144_failed_request")),
            "t_opportunity_s": round(float(o["t_opportunity"]), 4),
            "t_cloud_done_s": (round(float(o["t_cloud_done"]), 4)
                               if o.get("t_cloud_done") is not None else None),
        })
    cm = r["committed_score_block"]["robot_pool_on_time"]
    return {
        "_what": ("every opportunity where the committed scorer's own per-question flag "
                  "(robot_rows[].source_by_deadline == 'cloud') and this script's committed-rule "
                  "reading disagree"),
        "committed_per_question_sum": len(own_on_time),
        "committed_sweep_robot_pool_on_time": cm,
        "per_question_sum_equals_sweep": len(own_on_time) == cm,
        "n_differences": len(diffs),
        "differences": diffs,
        "every_difference_is_a_refusal": bool(diffs) and all(
            d["d144_failed_request"] and d["committed_scorer_source_by_deadline_is_cloud"]
            and not d["this_script_delivery_rule"] for d in diffs),
    }


def equality_check(rows: List[Dict[str, Any]], seeds: Sequence[int],
                   sets: Dict[int, Set[str]]) -> Dict[str, Any]:
    """Seeds with no over-limit question must give two IDENTICAL columns."""
    per = []
    for r in rows:
        s = r["seed"]
        if sets.get(s):
            continue
        a = r["columns"][COLUMN_NAMES[0]]
        b = r["columns"][COLUMN_NAMES[1]]
        ok = all(a[k] == b[k] for k in ("register_DELIVERY_PRIMARY", "register_FIRST_TOKEN_BESIDE"))
        per.append({"cell": r["cell"], "arm": r["arm_reported_name"], "seed": s,
                    "columns_identical": ok,
                    "as_committed_fraction": a["register_DELIVERY_PRIMARY"]["fraction"],
                    "d176_fraction": b["register_DELIVERY_PRIMARY"]["fraction"]})
    return {
        "_what": ("seeds %s have an EMPTY exclusion set, so the two columns must come out EQUAL; "
                  "an inequality means the exclusion leaked into a seed it does not apply to"
                  % sorted(s for s in seeds if not sets.get(s))),
        "n_rows": len(per), "n_identical": sum(1 for p in per if p["columns_identical"]),
        "verdict": ("PASS" if per and all(p["columns_identical"] for p in per)
                    else ("FAIL" if per else "NO ROWS")),
        "rows": per,
    }


def anchor_check(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The named anchor: covex-v6-fair-c5attr-rr at seed 7 is 84 of 105 and 84 of 87."""
    want = {"arm": "covex-v6-fair-c5attr-rr", "seed": 7,
            "as_committed": (84, 105), "d176": (84, 87)}
    hit = next((r for r in rows if r["arm_reported_name"] == want["arm"]
                and r["seed"] == want["seed"]), None)
    if hit is None:
        return {"_what": want, "verdict": "MISSING CELL", "found": None}
    a = hit["columns"][COLUMN_NAMES[0]]["register_DELIVERY_PRIMARY"]
    b = hit["columns"][COLUMN_NAMES[1]]["register_DELIVERY_PRIMARY"]
    got = {"as_committed": (a["on_time"], a["n"]), "d176": (b["on_time"], b["n"])}
    return {
        "_what": ("the anchor stated in the ruling: 84 of 105 = 0.8000 as committed and 84 of 87 "
                  "= 0.9655 under D176, a 0.1655 difference in the ABSOLUTE number"),
        "expected": {k: list(v) for k, v in want.items() if isinstance(v, tuple)},
        "found": {k: list(v) for k, v in got.items()},
        "as_committed_fraction": a["fraction"], "d176_fraction": b["fraction"],
        "difference": (round(b["fraction"] - a["fraction"], 6)
                       if a["fraction"] is not None and b["fraction"] is not None else None),
        "verdict": ("PASS" if got["as_committed"] == want["as_committed"]
                    and got["d176"] == want["d176"] else "FAIL"),
    }


# ------------------------------------------------------------------------------------------------
# main


def _what_each_arm_did(rows: List[Dict[str, Any]], sets: Dict[int, Set[str]]) -> Dict[str, Any]:
    """D176 asks for "what each arm did with them", and it is not a formality.

    The ruling describes the 18 as misses for every arm, and for most arms they are. They are NOT
    for all of them: some arms deliver an on-time answer to some of the 18 (measured here, and
    the arms are named in `arms_whose_d176_column_falls` rather than written into this text), so
    for those arms the D176 column is LOWER than the as-committed one, not higher. The reason is
    in D170: an outcome
    row carrying a request_id is not an over-limit send, and `simplestream` answers these
    questions with `tokens_charged` 467 - a short representation of a long history. An arm that
    answers an over-limit question inside 3 s did not attend over the limit; it sent less. So the
    direction of the correction is ARM-DEPENDENT while the excluded SET is not, and a reader who
    expects every D176 figure to rise would misread exactly these four.
    """
    per = []
    for r in rows:
        s = int(r["seed"])
        if not sets.get(s):
            continue
        ex = r["columns"]["excluded_identity"]
        a = r["columns"][COLUMN_NAMES[0]]["register_DELIVERY_PRIMARY"]
        b = r["columns"][COLUMN_NAMES[1]]["register_DELIVERY_PRIMARY"]
        k_del = sum(1 for e in ex if e["on_time_DELIVERY"])
        k_tok = sum(1 for e in ex if e["on_time_FIRST_TOKEN"])
        per.append({
            "arm": r["arm_reported_name"], "seed": s, "role": r["role"],
            "excluded_n": len(ex),
            "of_the_excluded_on_time_DELIVERY": k_del,
            "of_the_excluded_on_time_FIRST_TOKEN": k_tok,
            "sent_a_representation_over_the_limit": r["in_cell_over_limit_sends"]["n"],
            "d176_column_direction": ("higher" if (b["fraction"] or 0) > (a["fraction"] or 0)
                                      else ("lower" if (b["fraction"] or 0) < (a["fraction"] or 0)
                                            else "unchanged")),
            "as_committed_fraction": a["fraction"], "d176_fraction": b["fraction"],
        })
    return {
        "_what": ("per arm and affected seed: how many of the excluded questions that arm "
                  "delivered on time, and which way the D176 column therefore moves"),
        "_direction_is_arm_dependent": (
            "the excluded SET is arm-invariant, so the comparison is unchanged, but the SIGN of "
            "the change to an arm's own absolute figure is not: an arm that answered some of the "
            "excluded questions on time loses those from its numerator as well as its "
            "denominator and its D176 figure FALLS"),
        "_an_on_time_answer_here_is_not_an_over_limit_send": (
            "D170's test: tokens_charged above the limit, not the presence of a request_id. "
            "`simplestream` carries a request_id on all 18 with tokens_charged 467, which is a "
            "short representation of a long history"),
        "arms_whose_d176_column_falls": sorted({p["arm"] for p in per
                                                if p["d176_column_direction"] == "lower"}),
        "rows": per,
    }


def _role(slug: str) -> str:
    for name, s, role in LADDER:
        if s == slug:
            return role
    if slug in SUPERSEDED_D205:
        return "SUPERSEDED by D205 (1); reported with the label, never as a current figure"
    if slug in ABLATION:
        return "ablation or earlier rung, not the reported baseline set"
    return "baseline, reported set"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", help="a runs directory on disk")
    ap.add_argument("--git-ref", help="read committed cell outputs out of git objects at this sha")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--seeds", default=",".join(str(s) for s in DEFAULT_SEEDS))
    ap.add_argument("--tag", default=DEFAULT_TAG)
    a = ap.parse_args(argv)
    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
    for s in seeds:
        if s not in (4, 5, 6, 7):
            raise SystemExit("seeds 1 to 3 and HOLDOUT are never reported; got %d" % s)

    src = Source(a.runs, a.git_ref)
    present = set(src.cells())

    # resolve every reported arm to a cell name per seed, and say what is missing
    arms: List[Tuple[str, str, str]] = []
    rung4 = next((c for c in RUNG4_CANDIDATES
                  if any(n.startswith(c + "_n16_s") for n in present)), None)
    for name, slug, role in LADDER:
        if slug == "covex-v6-cf-c5attr":
            if rung4 is None:
                arms.append((name, "__ABSENT__", role))
                continue
            slug = rung4
        arms.append((name, slug, role))
    ladder_slugs = {s for _, s, _ in arms}
    # Discovery matches the EXACT cell suffix for one of the reported seeds, never merely the tag
    # at the end of the name. `covex-v6-base_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30` ends in the
    # tag and is a DIFFERENT condition (0.5x KV); admitting it invented a `covex-v6-base` arm
    # whose exact-tag cells then read as missing while the real base rows were already present
    # under their own slug.
    suffixes = [CELL_SUFFIX % (s, a.tag) for s in seeds]
    others = sorted({n[:-len(suf)] for n in present for suf in suffixes
                     if n.endswith(suf)} - ladder_slugs)
    for slug in others:
        arms.append((slug, slug, _role(slug)))

    rows: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for name, slug, role in arms:
        for s in seeds:
            if slug == "__ABSENT__":
                missing.append({"arm_reported_name": name, "seed": s, "role": role,
                                "why": "no committed cell under any of %s"
                                       % list(RUNG4_CANDIDATES)})
                continue
            cell = slug + (CELL_SUFFIX % (s, a.tag))
            if cell not in present:
                missing.append({"arm_reported_name": name, "seed": s, "role": role,
                                "cell_looked_for": cell, "why": "no such committed cell"})
                continue
            r = read_cell(src, cell)
            source_note = "first attempt"
            # THE FIRST ATTEMPT IS THE CELL (frozen_headline.py's rule), and a rerun never
            # displaces a first attempt that produced a scored cell.json. But three directories
            # here hold ONLY preflight files - the attempt aborted before any outcome was written,
            # and two of them are named in runs/SKIPPED - while the `_rerun` beside them holds the
            # scored run. Treating an aborted attempt as "the cell" would drop a committed arm and
            # seed from the table and read as if that arm had no figure, so the fallback is taken
            # and LABELLED, and it is taken only when the first attempt carries no cell.json.
            if not r["usable"] and (cell + "_rerun") in present:
                r2 = read_cell(src, cell + "_rerun")
                if r2["usable"]:
                    r, source_note = r2, ("rerun; the first attempt %s aborted with no cell.json "
                                          "(missing %s)" % (cell, r["missing_files"]))
            r["arm_reported_name"] = name
            r["arm_cell_slug"] = slug
            r["role"] = role
            r["cell_source"] = source_note
            if not r["usable"]:
                missing.append({"arm_reported_name": name, "seed": s, "role": role,
                                "cell_looked_for": cell,
                                "why": "incomplete cell directory, missing %s%s"
                                       % (r["missing_files"],
                                          "" if (cell + "_rerun") not in present
                                          else "; the _rerun directory is incomplete too")})
                continue
            r["seed"] = r["seed"] if r["seed"] is not None else s
            rows.append(r)

    cells_by_seed: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        cells_by_seed[int(r["seed"])].append(r)

    excl = _establish_exclusions(src, cells_by_seed, seeds)
    sets: Dict[int, Set[str]] = excl.pop("_sets")
    inv = _arm_invariance(cells_by_seed, sets)

    for r in rows:
        r["columns"] = columns(r, sets.get(int(r["seed"]), set()))

    pc = positive_control(rows)
    eq = equality_check(rows, seeds, sets)
    anc = anchor_check(rows)

    for r in rows:
        r.pop("_pool_rows", None)
        r.pop("_pool_ids", None)
        r.pop("_robot_rows", None)

    try:
        sha = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True,
                             check=True).stdout.decode().strip()
    except subprocess.CalledProcessError:
        sha = "unknown"

    res: Dict[str, Any] = {
        "_what": ("D176 (3): a D176-compliant robot headline column BESIDE the as-committed one, "
                  "for every arm and seed. A REPORTING correction, not a re-scoring: the "
                  "committed scorer is untouched and no committed verdict JSON is regenerated"),
        "_the_two_columns": {
            COLUMN_NAMES[0]: ("every robo00x opportunity in the cell, which is what the committed "
                              "cells and today's plots carry; the 18 over-limit questions are IN "
                              "it, and for most arms they are in it as misses - but NOT for all, "
                              "see what_each_arm_did_with_the_excluded"),
            COLUMN_NAMES[1]: ("the same pool with the over-limit questions excluded for EVERY ARM "
                              "IDENTICALLY, per D176; this is the column the Orin's plots must "
                              "quote"),
            "_never_emitted_alone": ("both columns, with numerators, denominators, the excluded "
                                     "count and the excluded identities, travel together in every "
                                     "row"),
        },
        "_the_comparison_is_unchanged": (
            "the exclusion is the same id set for every arm at a seed (arm_invariance below, set "
            "equality and not count equality), so every arm-versus-arm difference, gain and "
            "retention is unchanged. What changes is the ABSOLUTE figure a reader quotes"),
        "_registers": {
            "DELIVERY_PRIMARY": ("the committed scorer's delivery rule; this is "
                                 "sweep[0].robot_pool_on_time"),
            "FIRST_TOKEN_BESIDE": ("cloud_payload.on_time, the coordinator's online flag at the "
                                   "first token. The two differ by a few counts per cell because "
                                   "t_delivered adds the forward delay; a count from one register "
                                   "is never compared against a bound from the other"),
        },
        "_source": {"kind": src.kind, "runs_dir": a.runs, "git_ref": a.git_ref,
                    "runs_rel": RUNS_REL, "tag": a.tag, "seeds": seeds,
                    "read_only": True,
                    "_seeds_never_reported": "seeds 1 to 3 and HOLDOUT are out of the reported set"},
        "exclusion_set": excl,
        "arm_invariance": inv,
        "what_each_arm_did_with_the_excluded": _what_each_arm_did(rows, sets),
        "checks": {
            "1_seeds_without_exclusions_give_equal_columns": eq,
            "2_anchor_s7_fair_c5attr_rr": anc,
            "3_exclusion_set_arm_invariant": {"verdict": (
                "PASS" if not inv["stop"] else "FAIL"), "stop": inv["stop"]},
            "4_exclusion_set_established_and_corroborated": {
                "verdict": "PASS" if not excl["stop"] else "FAIL", "stop": excl["stop"]},
            "5_positive_control_as_committed_column": pc,
        },
        "rows": rows,
        "missing_cells": missing,
        "n_rows": len(rows),
        "_provenance": {
            "git_commit": a.git_ref or sha,
            "local_head_at_run_time": sha,
            "cell_outputs_read_from": ("git objects at %s" % a.git_ref if a.git_ref
                                       else "runs directory %s" % a.runs),
            "script": "d176_robot_headline.py",
            "model": "n/a (read-only reporting over committed cell outputs)",
            "device": "n/a (CPU)",
            "n": len(rows),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print("wrote", a.out)
    if a.report:
        os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
        with open(a.report, "w") as fh:
            fh.write(_md(res))
        print("wrote", a.report)

    print("positive control: %s (%d/%d cells exact, %d explained pre-D175, %d unexplained)" % (
        pc["verdict"], pc["n_pass_exact"], pc["n_cells"], pc["n_explained_pre_d175"],
        pc["n_unexplained"]))
    print("equal-columns check: %s; anchor: %s; arm-invariance: %s" % (
        eq["verdict"], anc["verdict"], res["checks"]["3_exclusion_set_arm_invariant"]["verdict"]))
    for r in rows:
        a0 = r["columns"][COLUMN_NAMES[0]]["register_DELIVERY_PRIMARY"]
        b0 = r["columns"][COLUMN_NAMES[1]]["register_DELIVERY_PRIMARY"]
        print("%-28s s%d  as-committed %3d/%3d = %-8s   d176 %3d/%3d = %-8s  excluded %2d" % (
            r["arm_reported_name"][:28], r["seed"], a0["on_time"], a0["n"],
            a0["fraction"], b0["on_time"], b0["n"], b0["fraction"],
            r["columns"]["excluded_n"]))
    bad = (pc["verdict"] == "FAIL" or eq["verdict"] == "FAIL" or anc["verdict"] == "FAIL"
           or excl["stop"] or inv["stop"])
    return 1 if bad else 0


def _md(res: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("# StudyD176-HEADLINE: the D176-compliant robot headline column\n")
    L.append(res["_what"] + ".\n")
    anc = res["checks"]["2_anchor_s7_fair_c5attr_rr"]
    L.append("**Headline.** At seed 7 `covex-v6-fair-c5attr-rr` is %s as committed and %s under "
             "D176, a difference of %s in the ABSOLUTE number. The plots must quote the D176 "
             "column; `0.80` is the as-committed figure and carries 18 over-limit questions as "
             "misses. Seeds 4, 5 and 6 have no over-limit question, so their two columns are "
             "equal. Every arm-versus-arm verdict is unchanged, because the excluded set is the "
             "same for every arm.\n" % (anc["as_committed_fraction"], anc["d176_fraction"],
                                        anc["difference"]))
    L.append("## The two columns\n")
    L.append("| arm | role | seed | as-committed (delivery) | D176 (delivery) | excluded | "
             "as-committed (first token) | D176 (first token) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(res["rows"], key=lambda r: (r["role"], r["arm_reported_name"], r["seed"])):
        c = r["columns"]
        a0 = c[COLUMN_NAMES[0]]["register_DELIVERY_PRIMARY"]
        b0 = c[COLUMN_NAMES[1]]["register_DELIVERY_PRIMARY"]
        a1 = c[COLUMN_NAMES[0]]["register_FIRST_TOKEN_BESIDE"]
        b1 = c[COLUMN_NAMES[1]]["register_FIRST_TOKEN_BESIDE"]
        L.append("| `%s` | %s | %d | %d/%d = %s | %d/%d = %s | %d | %d/%d = %s | %d/%d = %s |" % (
            r["arm_reported_name"], r["role"], r["seed"], a0["on_time"], a0["n"], a0["fraction"],
            b0["on_time"], b0["n"], b0["fraction"], c["excluded_n"],
            a1["on_time"], a1["n"], a1["fraction"], b1["on_time"], b1["n"], b1["fraction"]))
    L.append("")
    L.append("Register: the DELIVERY columns are the committed scorer's rule and are what "
             "`sweep[0].robot_pool_on_time` holds; the FIRST TOKEN columns are "
             "`cloud_payload.on_time`, the coordinator's online flag. The two are different "
             "quantities and a count from one is never read against a bound from the other.\n")
    L.append("## The excluded questions\n")
    for s, blk in sorted((res["exclusion_set"]["checks"]["identity_from_cell_outputs"]).items()):
        if not blk["n"]:
            L.append("- seed %s: NO over-limit question, so nothing is excluded and the two "
                     "columns are equal by construction" % s)
            continue
        L.append("- seed %s: n = %s, device %s, session %s, t %s to %s s, %s distinct "
                 "question ids, %s re-asks and %s original asks; the excluded set equals that "
                 "session's WHOLE recall pool: %s" % (
                     s, blk["n"], ", ".join(blk["device_ids"]), ", ".join(blk["session_ids"]),
                     blk["t_opportunity_s_min"], blk["t_opportunity_s_max"],
                     blk["distinct_question_ids"], blk["re_asks"], blk["original_asks"],
                     blk["equals_that_session_whole_recall_pool"]))
    L.append("")
    L.append("Membership criterion and the field used: %s" % res["exclusion_set"]["_field_used"])
    L.append("")
    L.append(res["exclusion_set"]["_why_not_from_runs"] + ".\n")
    dr = res["exclusion_set"]["checks"]["direct_in_cell_over_limit_evidence"]
    L.append("Direct in-cell corroboration (the only over-limit evidence any cell output "
             "carries): %d cell(s). %s. All inside the set: %s.\n" % (
                 dr["n_cells_with_evidence"],
                 "; ".join("`%s` seed %d sent %s with tokens charged %s" % (
                     c["cell"], c["seed"], ", ".join(c["opportunity_ids"]),
                     ", ".join(str(v) for v in c["tokens_charged"].values()))
                     for c in dr["cells_with_evidence"]) or "none, so this corroboration is "
                 "VACUOUS and is reported as such, not as a pass",
                 dr["all_inside_the_set"]))
    nx = res["exclusion_set"]["checks"]["seeds_with_no_exclusions"]
    L.append("Seeds with no exclusion, with the largest robot prompt any cell shows there, "
             "against the 32,768 limit: %s.\n" % ", ".join(
                 "seed %s %d tokens" % (k, v["max_prompt_tokens_on_robot_pool_over_cells"])
                 for k, v in sorted(nx.items())))
    reruns = [r for r in res["rows"] if r.get("cell_source", "").startswith("rerun")]
    if reruns:
        L.append("Cells taken from a `_rerun` directory because the first attempt aborted with "
                 "no `cell.json` (the first attempt is otherwise always the cell): %s.\n"
                 % ", ".join("`%s` seed %s" % (r["arm_reported_name"], r["seed"])
                             for r in reruns))
    L.append("## What each arm did with the excluded questions\n")
    w = res["what_each_arm_did_with_the_excluded"]
    L.append(w["_direction_is_arm_dependent"].capitalize() + ".\n")
    L.append("Arms whose D176 column FALLS: %s.\n" % (
        ", ".join("`%s`" % x for x in w["arms_whose_d176_column_falls"]) or "none"))
    L.append("| arm | seed | excluded | of those on time (delivery) | of those on time (first token) | "
             "over-limit sends | as-committed | D176 | direction |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for p_ in sorted(w["rows"], key=lambda x: (x["role"], x["arm"], x["seed"])):
        L.append("| `%s` | %d | %d | %d | %d | %d | %s | %s | %s |" % (
            p_["arm"], p_["seed"], p_["excluded_n"], p_["of_the_excluded_on_time_DELIVERY"],
            p_["of_the_excluded_on_time_FIRST_TOKEN"],
            p_["sent_a_representation_over_the_limit"], p_["as_committed_fraction"],
            p_["d176_fraction"], p_["d176_column_direction"]))
    L.append("")
    L.append("## Checks\n")
    for k, v in res["checks"].items():
        L.append("- **%s**: %s" % (k, v.get("verdict")))
    L.append("")
    pc = res["checks"]["5_positive_control_as_committed_column"]
    L.append("Positive control: %d of %d cells reproduce their own committed "
             "`sweep[0].robot_pool_on_time`, `robot_pool_n` and `robot_pool_fraction` EXACTLY; "
             "%d explained, %d unexplained. A failure here would mean the "
             "SCRIPT is wrong, not the committed number.\n" % (
                 pc["n_pass_exact"], pc["n_cells"], pc["n_explained_pre_d175"],
                 pc["n_unexplained"]))
    for c in pc["cells"]:
        if c["pass"]:
            continue
        d = c["diagnosis"]
        L.append("- `%s` seed %s: committed %s, recomputed %s. %d differing opportunity: %s. "
                 "Every difference is a D144/D175 refusal: %s. The cell was scored before the "
                 "D175 (1) guard, so its own committed numerator counts a refused request as a "
                 "delivery; this is a SECOND non-zero case of the guard beyond the "
                 "kvflow-prefetch s4 one D175 records, and it is the CELL's figure that is "
                 "stale, not this column." % (
                     c["cell"], c["seed"], c["checks"][0]["committed"],
                     c["checks"][0]["recomputed"], d["n_differences"],
                     ", ".join(x["opportunity_id"] for x in d["differences"]),
                     d["every_difference_is_a_refusal"]))
    L.append("")
    if res["missing_cells"]:
        L.append("## Cells not found\n")
        for m in res["missing_cells"]:
            L.append("- `%s` seed %s: %s" % (m["arm_reported_name"], m["seed"], m["why"]))
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
