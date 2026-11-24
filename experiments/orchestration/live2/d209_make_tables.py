#!/usr/bin/env python3
"""Render the byte-identity and committed-cross-check tables from the sweep JSONs."""
import json
import pathlib
import sys
from pathlib import Path

SP = Path("/tmp/claude-1001/-home-pragya-Desktop-FM-switching/"
          "8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad")

COMMITTED = {
    "covex-v6-base": ("af8befb9420ad86a", 12085, "EXPERIMENTS.md StudyFROZEN-test; c5attr_digest_proofs.json P1"),
    "covex-v6-state-uo": ("9a4be873eb3c5fba", 14218, "c5attr_digest_proofs.json P1"),
    "covex-v6-state-uo-c5attr": ("9a4be873eb3c5fba", 14218, "EXPERIMENTS.md StudyFROZEN-test (ALONE; 639cd15ed38c9da0 / 14,207 under concurrency, d190_rung4_r3_proofs.py:192-197)"),
    "covex-v6-fair-c5attr": ("12e4f73ce0ebd865", 13812, "EXPERIMENTS.md StudyFROZEN-test; D208 (1) rung-3 bar"),
    "v5-rules-2": ("18067c4c66bb44b8", 11955, "c5attr_digest_proofs.json P1"),
    "b7-edf-feasibility": ("b9aadd1c3a2b26d5", 12265, "c5attr_digest_proofs.json P1"),
    "covex-v6-cf-c5attr": ("f5b627392839527c", 14470,
                           "EXPERIMENTS.md StudyFROZEN-test, the post-D206 rung-4 bar"),
}
RUNG = {"covex-v6-base": "rung 0 (base)", "covex-v6-rules": "rung 1 (rules)",
        "covex-v6-state-uo": "rung 2 family", "covex-v6-state-uo-c5attr": "RUNG 2",
        "covex-v6-fair-c5attr": "RUNG 3", "covex-v6-cf-c5attr": "rung 4 family",
        "covex-v6-cf-pd-c5attr": "RUNG 4"}
KV_READER = {"preble", "b9", "uniscale", "covex-v6-cf-c5attr", "covex-v6-cf-pd-c5attr"}
# the committed BASELINE_MATRIX ACTIVE set plus the three restored arms, per the 2026-11-23 ruling
# that the matrix governs. preble, b9 and uniscale are NOT in it, so they are not reportable arms
# and are labelled as such rather than quietly dropped: the hit-6 defect in them is still on record.
MATRIX = {"always-cloud-fcfs", "attentionstore-prefetch", "b7-edf-feasibility",
          "confidence-cascade", "eco-llm", "edf", "llf", "lmcache", "mooncake",
          "querystream-proactive", "simplestream", "streamscout", "warm-all-lru",
          "kvflow-prefetch", "cascade-routing", "device-only"}
NOT_REPORTABLE = {"preble", "b9", "uniscale"}


def table(doc, title):
    out = [f"**{title}**", "",
           "| arm | role | before | rows | after | rows | identical? |",
           "|---|---|---|---|---|---|---|"]
    moved = []
    err = []
    for r in doc["arms"]:
        a = r["arm"]
        if a in RUNG:
            role = RUNG[a]
        elif a in MATRIX:
            role = "BASELINE_MATRIX active"
        elif a in NOT_REPORTABLE:
            role = "**NOT a reported arm** (not in BASELINE_MATRIX; run before the ruling, kept as a noted gap)"
        else:
            role = "reported baseline"
        if a in KV_READER:
            role += ", reads `gpu_kv_fraction`"
        if r.get("before_error") or r.get("after_error"):
            err.append((a, r.get("before_error"), r.get("after_error")))
            continue
        ok = "**YES**" if r["identical"] else "**NO**"
        if not r["identical"]:
            moved.append(a)
        out.append("| `%s` | %s | `%s` | %s | `%s` | %s | %s |"
                   % (a, role, r["before_digest"], f'{r["before_rows"]:,}',
                      r["after_digest"], f'{r["after_rows"]:,}', ok))
    out += ["", "Arms whose digest MOVED: %s" % (", ".join("`%s`" % m for m in moved) or "none"),
            "", "Distinct before-side digests over %d arms: %d, so the digest discriminates arms "
            "and an identity is not a degenerate hash."
            % (doc["n_arms"], doc["n_distinct_before_digests"])]
    if err:
        out += ["", "Cells that did not produce a digest (reported, not dropped):"]
        for a, b, f in err:
            out.append("- `%s`: before %r, after %r" % (a, (b or "")[:160], (f or "")[:160]))
    return "\n".join(out)


def check1(doc):
    out = ["| quantity | this run (before side) | prior committed | source of prior | ratio | agree? |",
           "|---|---|---|---|---|---|"]
    for r in doc["arms"]:
        a = r["arm"]
        if a not in COMMITTED or r.get("before_error"):
            continue
        dg, nr, src = COMMITTED[a]
        agree = "AGREE" if (r["before_digest"] == dg and r["before_rows"] == nr) else "**DISAGREE**"
        out.append("| `%s` digest / rows | `%s` / %s | `%s` / %s | %s | %s | %s |"
                   % (a, r["before_digest"], f'{r["before_rows"]:,}', dg, f"{nr:,}", src,
                      "1.000" if r["before_rows"] == nr
                      else "%.4f" % (r["before_rows"] / nr), agree))
    return "\n".join(out)



def consolidated(out_lines):
    """ONE verdict per arm across every pass, with a later rerun superseding an earlier pair that
    errored on a missing checkout file. This is the gate; the per-pass tables above are the audit
    trail behind it."""
    import glob
    import os
    seen = {}
    for f in sorted(glob.glob(str(SP / "d209_digests*.json"))):
        if f.endswith("d209_digests_no22.json"):
            continue                      # the attribution pass, not the gate
        d = json.loads(pathlib.Path(f).read_text())
        for r in d["arms"]:
            err = r.get("before_error") or r.get("after_error")
            prev = seen.get(r["arm"])
            if prev is not None and prev["err"] is None and err:
                continue                  # never let a failed rerun overwrite a good verdict
            seen[r["arm"]] = {"r": r, "err": err, "pass": os.path.basename(f)}
    rows, moved, errs = [], [], []
    for a in sorted(seen):
        v = seen[a]; r = v["r"]
        if a in RUNG:
            role = RUNG[a]
        elif a in MATRIX:
            role = "BASELINE_MATRIX active"
        elif a in NOT_REPORTABLE:
            role = "**NOT a reported arm**"
        else:
            role = "reported baseline"
        if v["err"]:
            errs.append((a, v["err"][:140])); continue
        verdict = "**IDENTICAL**" if r["identical"] else "**MOVED**"
        if not r["identical"]:
            moved.append(a)
        rows.append("| `%s` | %s | `%s` | %s | `%s` | %s | %s |"
                    % (a, role, r["before_digest"], f'{r["before_rows"]:,}',
                       r["after_digest"], f'{r["after_rows"]:,}', verdict))
    out_lines += ["", "### CONSOLIDATED GATE: one verdict per arm, across every pass", "",
                  "| arm | role | before | rows | after | rows | verdict |",
                  "|---|---|---|---|---|---|---|"] + rows
    out_lines += ["", "**Arms with a verdict: %d. MOVED: %s.**"
                  % (len(rows), ", ".join("`%s`" % m for m in moved) or "NONE")]
    if errs:
        out_lines += ["", "Arms with no verdict (reported, not dropped):"]
        out_lines += ["- `%s`: %s" % (a, e) for a, e in errs]
    return out_lines

def main():
    main_doc = json.loads((SP / "d209_digests.json").read_text())
    out = [table(main_doc, "All three fixes: `before` against `after`, 46 dry s4 cells, one cell "
                           "per process, committed recipe"), ""]
    for extra, title in ((SP / "d209_digests_matrix2b.json",
                          "`streamscout` and `cascade-routing`, rerun after their missing committed "
                          "inputs were supplied"),
                         (SP / "d209_digests_cascade.json",
                          "`confidence-cascade`, rerun after its missing committed input was "
                          "supplied (its first pair errored IDENTICALLY on both sides)"),
                         (SP / "d209_digests_simplestream.json",
                          "`simplestream`, rerun after its missing committed input was supplied "
                          "(its first pair errored IDENTICALLY on both sides, on a data file absent "
                          "from the checkout, not on the code)"),):
        if extra.exists():
            out += [table(json.loads(extra.read_text()), title), ""]
    p5 = SP / "d209_digests_matrix5.json"
    if p5.exists():
        out += [table(json.loads(p5.read_text()),
                      "The five BASELINE_MATRIX arms added after the set was fixed: `before` "
                      "against `after`"), ""]
    p2 = SP / "d209_digests_no22.json"
    if p2.exists():
        out += [table(json.loads(p2.read_text()),
                      "ATTRIBUTION: `before` against `after_no22` (hits 26 and 6 ONLY, "
                      "`touch_policy.py` byte-identical)"), ""]
    out = consolidated(out)
    Path(sys.argv[1]).write_text("\n".join(out) + "\n")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(check1(main_doc) + "\n")
    print("\n".join(out[-24:]))


if __name__ == "__main__":
    main()
