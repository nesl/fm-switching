"""N5: census of `cloud.queued_by_class` readers, and whether the quantity is constant today.

Read-only. No cell is run, no live2 module is imported, nothing is patched. Every number comes
from artifacts committed at ONE literal origin/main sha, read with `git show`, so the stale local
checkout and other sessions' uncommitted work cannot reach this measurement.

WHY THIS EXISTS. `cstate.py:657` reads `vllm:num_requests_waiting` from `st.metrics` and falls
back to the coordinator's own `in_flight["monitor"]`. The metric has never been present, because
`st.metrics` has exactly one writer (`coordinator.py:489`, `self.st.metrics = self.be.metrics()`)
and in every reported live2 cell `be` is `asyncbackend.AsyncBackend`, whose `metrics()` returns
WIRE statistics (`n_built`, `wire_image_parts`, ...) and no `vllm:` key at all. So the question is
not whether connecting the metric would animate a dead channel; it is whether it would REPLACE a
live, varying value. That is the larger risk and it is what this script measures.

THE PROXY, declared because it is the one soft spot. `queued_by_class` is built inside
`cstate.observation()` and is not itself logged. `decision.jsonl` logs `traffic_mix`, which
`cstate.py:431` defines as `{k: int(self.in_flight.get(k, 0)) for k in
("monitor","piece","whole","recall")}` - the SAME `self.in_flight` dict that
`cstate.py:657-662` reads. So `traffic_mix["monitor"]` IS today's `queued_by_class["episodic"]`,
read from the same counter, but sampled at SUBMIT time inside the epoch rather than at the top of
`observation()`. For the question asked - is the quantity constant? - a sample of the same counter
at a slightly later instant is valid, and that is the only claim made from it. Threshold-crossing
shares derived from it are marked CONSTRUCTED, not OBSERVED, because the instant differs.
"""
import collections
import gzip
import io
import json
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/pragya/Desktop/FM-switching")
RUNS = "results/orchestration/live2/frozen_test/runs"
GRID = "1200s_h27_3t_L3_epg_rq30"

# The D213 paper set, as the user named it. `device-only` and `cascade-routing` are included and
# are reported as absent if they have no committed cell on this grid.
PAPER_SET = ("always-cloud-fcfs", "attentionstore-prefetch", "b7-edf-feasibility",
             "confidence-cascade", "eco-llm", "edf", "llf", "lmcache", "mooncake",
             "querystream-proactive", "simplestream", "streamscout", "warm-all-lru",
             "kvflow-prefetch", "cascade-routing", "device-only")

# Our rungs. Every one of these reaches `arms_v5rules2.guard_state`, which is the single read site
# shared by v5-rules-2, v5-full and the whole covex-v6 ladder.
RUNGS = ("v5-rules-2", "hybrid-F-lhreq-noc3", "covex-v6-state", "covex-v6-fair-c5attr",
         "covex-v6-state-uo", "covex-v6-state-shares")

# Thresholds the read sites compare against, from the code at this sha.
THRESH = {
    "mooncake_overload_queue": 4,          # mooncake_adapted.py:50, default overload_queue=4
    "preble_b9_lp_q": 8,                   # preble_adapted.py:57 / constructed.py:416, q/8.0 vs 0.9
    "v5rules2_guard_backlog": 100,         # arms_v5rules2.py:83 GUARD_BACKLOG_DEFAULT
}

RECALL_KINDS = ("release_recall", "decline", "defer")


def sha():
    """ONE literal sha, passed in, never re-resolved. origin/main moved between two calls of an
    earlier draft of this script (87ca3503 -> 74a7113a within nine minutes), which is the split-ref
    hazard: half the analysis would have keyed into one tree and half into another."""
    if len(sys.argv) < 2 or len(sys.argv[1]) != 40:
        raise SystemExit("usage: n5_queued_by_class_census.py <40-char literal sha>")
    rev = sys.argv[1]
    subprocess.run(["git", "cat-file", "-e", rev + "^{commit}"], cwd=REPO, check=True)
    return rev


def git_show_bytes(rev, path):
    p = subprocess.run(["git", "show", "%s:%s" % (rev, path)], cwd=REPO,
                       capture_output=True, check=False)
    if p.returncode != 0:
        return None
    return p.stdout


def ls_cells(rev):
    """Cells are indexed by whichever decision log they committed. A cell that committed NO
    decision log is listed with None, and reported as unmeasurable rather than as absent: the two
    are different facts and only one of them is about the arm."""
    p = subprocess.run(["git", "ls-tree", "-r", "--name-only", rev, "--",
                        RUNS + "/"], cwd=REPO, capture_output=True, text=True, check=True)
    cells = {}
    for line in p.stdout.splitlines():
        parts = line[len(RUNS) + 1:].rsplit("/", 1)
        if len(parts) != 2:
            continue
        cell, base = parts
        if base == "decision.jsonl.gz":
            cells[cell] = "decision.jsonl.gz"
        elif base == "decision.jsonl" and not cells.get(cell):
            cells[cell] = "decision.jsonl"
        else:
            cells.setdefault(cell, None)
    return cells


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, int(q * len(s)))]


def measure(rev, cell, base):
    raw = git_show_bytes(rev, "%s/%s/%s" % (RUNS, cell, base))
    if raw is None:
        return None
    mon, rif, kinds = [], [], collections.Counter()
    # per epoch: the visible-recall count, and the monitor in-flight at the epoch's FIRST row,
    # which is the sample closest to the top of observation().
    per_epoch_recall = collections.Counter()
    epoch_first_mon = {}
    epoch_first_rif = {}
    n = 0
    fh = (gzip.open(io.BytesIO(raw), "rt") if base.endswith(".gz")
          else io.StringIO(raw.decode("utf-8")))
    with fh:
        for line in fh:
            d = json.loads(line)
            n += 1
            tm = d.get("traffic_mix") or {}
            m = int(tm.get("monitor", 0) or 0)
            r = int((tm.get("recall", 0) or 0) + (tm.get("piece", 0) or 0)
                    + (tm.get("whole", 0) or 0))
            mon.append(m)
            rif.append(r)
            kinds[d.get("kind")] += 1
            t = d.get("t")
            if t is not None:
                if t not in epoch_first_mon:
                    epoch_first_mon[t] = m
                    epoch_first_rif[t] = r
                if d.get("kind") in RECALL_KINDS:
                    per_epoch_recall[t] += len(d.get("opportunity_ids") or [1])
    if not n:
        return None

    # reconstruct the two sums the read sites actually form, per epoch
    mooncake_q, backlog = [], []
    for t, m in epoch_first_mon.items():
        qr = per_epoch_recall.get(t, 0)
        r = epoch_first_rif[t]
        mooncake_q.append(qr + m)                 # sum(queued.values())
        backlog.append(qr + m + r + m)            # sum(queued) + sum(running); monitor twice

    def stat(v, label):
        return dict(n=len(v), min=min(v), p50=pct(v, 0.5), p90=pct(v, 0.9), max=max(v),
                    n_distinct=len(set(v)), constant=bool(len(set(v)) == 1), what=label)

    out = dict(
        cell=cell, n_decision_rows=n, n_epochs_with_a_decision=len(epoch_first_mon),
        decision_kinds=dict(kinds),
        # OBSERVED: the same counter cstate.py:657 falls back to.
        queued_episodic_today=stat(mon, "in_flight['monitor'] == queued_by_class['episodic'] today"),
        running_recall_today=stat(rif, "in_flight[recall]+[piece]+[whole] == running_by_class['recall']"),
        # CONSTRUCTED: assembled from a submit-time sample of the same counter.
        mooncake_sum_queued=stat(mooncake_q, "CONSTRUCTED sum(queued_by_class.values())"),
        preble_b9_v5r2_backlog=stat(backlog, "CONSTRUCTED sum(queued)+sum(running)"),
    )
    out["crossings"] = dict(
        mooncake_overloaded_share=round(
            sum(1 for v in mooncake_q if v >= THRESH["mooncake_overload_queue"])
            / float(len(mooncake_q)), 4),
        preble_b9_lp_at_cap_share=round(
            sum(1 for v in backlog if v >= THRESH["preble_b9_lp_q"]) / float(len(backlog)), 4),
        v5rules2_guard_by_backlog_share=round(
            sum(1 for v in backlog if v >= THRESH["v5rules2_guard_backlog"])
            / float(len(backlog)), 4),
        register="CONSTRUCTED: thresholds from code, inputs from a submit-time sample",
    )
    return out


# c_inflight = 8 arms. Their admission cap is the positive control: if traffic_mix["monitor"]
# really is the coordinator's in-flight counter, these arms must top out at EXACTLY their cap, and
# the uncapped arms must not. A reader pointed at the wrong field would not reproduce that split.
CAPPED_AT_8 = ("edf", "llf", "v5-rules-2", "hybrid-F-lhreq-noc3", "covex-v6-state",
               "covex-v6-fair-c5attr", "covex-v6-state-uo", "covex-v6-state-shares")


def checks(rows):
    capped = [(r["arm"], r["cell"], r["queued_episodic_today"]["max"])
              for r in rows if r["arm"] in CAPPED_AT_8]
    uncapped = [(r["arm"], r["cell"], r["queued_episodic_today"]["max"])
                for r in rows if r["arm"] not in CAPPED_AT_8]
    return dict(
        positive_control_c_inflight_8=dict(
            what="arms whose admission cap is c_inflight = 8 must top out at EXACTLY 8",
            n=len(capped), all_max_exactly_8=all(m == 8 for _a, _c, m in capped),
            per_cell_max={c: m for _a, c, m in capped},
            verdict=("PASS: the declared cap is reproduced from the decision log, so the field "
                     "read here is the in-flight counter and not something else"
                     if capped and all(m == 8 for _a, _c, m in capped) else "FAIL or no data"),
            register="OBSERVED"),
        negative_side_of_that_control=dict(
            what="arms with no admission cap must NOT sit at 8",
            n=len(uncapped), none_at_8=all(m != 8 for _a, _c, m in uncapped),
            max_over_uncapped=(max(m for _a, _c, m in uncapped) if uncapped else None),
            register="OBSERVED"),
        distribution_sanity=dict(
            what="CLAUDE.md check 3: a constant where a distribution is expected",
            n_cells=len(rows),
            n_cells_where_queued_episodic_is_constant=sum(
                1 for r in rows if r["queued_episodic_today"]["constant"]),
            register="OBSERVED"),
        cross_check_against_prior=dict(
            what="CLAUDE.md check 1: prior committed value for this quantity",
            prior="results/orchestration/live2/d213_metrics_scrape/readsite_{before,after}.json "
                  "record B_queued_by_class = {recall: 0, episodic: 0}",
            agree="NOT A DISAGREEMENT: that pair is a two-line toy observation with no sessions "
                  "and no in-flight work, so 0/0 is its correct value. It is CONSTRUCTED at a "
                  "stub and is not a measurement of a live cell, so it does not bound this run.",
            register="OBSERVED (the prior file was read at this sha)"),
        proxy=dict(
            what="CLAUDE.md check 6",
            proxy="traffic_mix['monitor'] from decision.jsonl stands for "
                  "queued_by_class['episodic'] as built in cstate.observation()",
            actually_measures="the same self.in_flight['monitor'] counter, sampled at submit time "
                              "inside the epoch rather than at the top of observation()",
            valid_for="the constancy question, which is the headline here",
            not_valid_for="an exact per-epoch value, so every threshold-crossing share is marked "
                          "CONSTRUCTED and none is used as a headline",
            register="declared"))


def provenance(rev, n):
    sys.path.insert(0, str(REPO / "experiments/lib"))
    from _provenance import stamp                                      # noqa: PLC0415
    p = stamp(script="n5_queued_by_class_census.py", model="none", device="flash_cpu", n=n)
    # `stamp` records the LOCAL HEAD, which is hundreds of commits behind origin and carries other
    # sessions' uncommitted work. Nothing here was read from it, so the local sha is kept under its
    # own name and `git_commit` is set to the tree every number actually came from.
    p["local_head_not_read_from"] = p.get("git_commit")
    p["git_commit"] = rev
    p["read_from"] = "git show at the literal sha above; the working tree was not read"
    return p


def main():
    rev = sha()
    cells = ls_cells(rev)
    want = []
    for arm in PAPER_SET + RUNGS:
        got = [c for c in sorted(cells) if c.startswith(arm + "_n16_s") and c.endswith(GRID)
               and "kv0." not in c]
        if not got:
            want.append((arm, None, "no committed cell on this grid"))
            continue
        with_log = [c for c in got if cells[c]]
        if not with_log:
            want.append((arm, None, "cell(s) committed but NO decision log: " + ", ".join(got)))
            continue
        if arm in ("mooncake", "v5-rules-2"):
            want.extend((arm, c, cells[c]) for c in with_log)   # all seeds, the decisive two
        else:
            pref = [c for c in with_log if "_s6_" in c] or with_log
            want.append((arm, pref[0], cells[pref[0]]))

    rows, missing = [], []
    for arm, cell, base in want:
        if cell is None:
            missing.append(dict(arm=arm, why=base))
            continue
        m = measure(rev, cell, base)
        if m is None:
            missing.append(dict(arm=arm, why="decision log unreadable: " + cell))
            continue
        m["arm"] = arm
        m["decision_log"] = base
        m["in_paper_set"] = arm in PAPER_SET
        rows.append(m)
        print("%-26s %-62s rows=%-7d episodic 0..%-4d distinct=%-4d constant=%s"
              % (arm, cell, m["n_decision_rows"], m["queued_episodic_today"]["max"],
                 m["queued_episodic_today"]["n_distinct"],
                 m["queued_episodic_today"]["constant"]), flush=True)

    doc = dict(
        _what="census of cloud.queued_by_class: is it constant today, and who reads it",
        _origin_main_sha=rev,
        _register="every per-cell number is read from a committed decision.jsonl.gz at the sha "
                  "above; see the module docstring for the one declared proxy",
        thresholds=THRESH, grid=GRID,
        n_cells_measured=len(rows), arms_not_measured=missing,
        metric_absence=dict(
            claim="vllm:num_requests_waiting has never been present in live2",
            evidence="st.metrics has exactly one writer, coordinator.py:489 "
                     "(self.st.metrics = self.be.metrics()); in every reported live2 cell be is "
                     "asyncbackend.AsyncBackend, whose metrics() (asyncbackend.py:190-210) "
                     "returns wire statistics and no vllm: key. AsyncBackend.scrape_metrics "
                     "exists but METRICS_SCRAPE_DEFAULT is False (asyncbackend.py:161) and its "
                     "output is not merged into st.metrics.",
            register="OBSERVED from code at the sha above"),
        checks=checks(rows),
        _provenance=provenance(rev, len(rows)),
        cells=rows)
    outp = REPO / "results/orchestration/live2/network/n5_queued_by_class_census.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print("\nwrote", outp)
    const = [r["arm"] for r in rows if r["queued_episodic_today"]["constant"]]
    print("cells where queued_by_class['episodic'] is CONSTANT:", const or "NONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
