#!/usr/bin/env python3
"""D223 (2) UNIT PROOFS FOR THE ONE CONTEXT-LIMIT READ. Positive observation, not argument.

WHAT EACH PROOF IS FOR.

  (1) THE 0.5x VALUE, OBSERVED. The committed real-0.5x cell's own `header.json` argv is fed to
      the parse and the result is printed. The ruling's number is 31,472 and this is where it is
      SEEN rather than argued. The argv carries `--max-model-len` TWICE, so this is also the
      last-occurrence proof: a first-occurrence parse would return 32,768 here and the defect
      would survive the fix in silence.

  (2) THE 1x VALUE, OBSERVED. The committed 1x cell's argv, which carries the flag ONCE, returns
      32,768. This is the POSITIVE CONTROL on the parse (CLAUDE.md check 7): if the parse were
      broken, this known-good committed arm would fail it, and the check would be the thing at
      fault rather than the arm.

  (3) THE NEGATIVE CONTROL. An argv with no `--max-model-len` must RAISE. A silent default is the
      defect being fixed: with one, the 1x byte-identity proof passes and the 0.5x fix is dead.

  (4) THE TRAP, STATED AS A MEASUREMENT. `gpu_kv_tokens` is the harness's logical KV pool, not the
      model length. This prints both, at both conditions, and shows that it COINCIDES with the
      limit at 0.5x and does NOT at 1x. A check that used it would have passed proof (1) and been
      wrong in every 1x cell.

  (5) THE READ SITES ARE LIVE, NOT WRITE-ONLY (CLAUDE.md Step 2). For each policy read site, the
      limit is set to two different values and the site's own expression is evaluated, showing it
      FOLLOWS. A quantity that is written and never read is ABSENT, and the module attribute
      `CONTEXT_LIMIT_TOKENS` is the exact shape that fails this way: it used to be a value bound
      at import, so a run-start read could not reach `arms_v6cfr3.py`'s `VCF.CONTEXT_LIMIT_TOKENS`.

  (6) NO RETYPED COPY IS LEFT IN THE POLICY PATH. The live2 tree is scanned for the literal and
      every hit is listed with a verdict, so the absence claim is made with its census beside it
      rather than from a truncated view.

Usage: python d223_context_limit_unit_proofs.py --repo-results DIR --out FILE
  --repo-results is a directory holding the two committed `header.json` files, extracted from the
  commit under test; the files are never read from a shared working tree.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import context_limit as CL                                                     # noqa: E402

ONE_X = "header_1x.json"
HALF_X = "header_kv05r.json"

# The policy read sites this ruling replaced, each as the expression that is evaluated there.
READ_SITES = (
    ("hybrid/hybrid_arm.py", "CL.limit_tokens() (was CONTEXT_LIMIT_TOKENS = 32768)",
     lambda: __import__("hybrid.hybrid_arm", fromlist=["x"]).CONTEXT_LIMIT_TOKENS),
    ("arms_v6cf.py", "CL.limit_tokens() (was a retyped 32768 fallback)",
     lambda: __import__("arms_v6cf").CONTEXT_LIMIT_TOKENS),
)


def _argv(d: Path, name: str) -> List[str]:
    h = json.loads((d / name).read_text())
    return [str(x) for x in ((h.get("server") or {}).get("command") or [])]


def _hdr(d: Path, name: str) -> Dict[str, Any]:
    return json.loads((d / name).read_text())


def proof_values(d: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for tag, name, expect in (("kv0.5r_real_engine", HALF_X, 31472), ("one_x", ONE_X, 32768)):
        argv = _argv(d, name)
        occ = CL.occurrences(argv)
        got = CL.parse_max_model_len(argv, where=name)
        first = int(occ[0]["value"]) if occ else None
        out[tag] = {
            "header": name,
            "n_occurrences": len(occ), "occurrences": occ,
            "parsed_LAST_occurrence": got, "expected": expect, "PASS": got == expect,
            "what_a_FIRST_occurrence_parse_would_have_returned": first,
            "first_differs_from_last": first != got,
        }
    out["_what"] = ("OBSERVED. (1) the real-0.5x argv parses to 31,472 and carries the flag twice, "
                    "so last-occurrence is load-bearing here. (2) the 1x argv parses to 32,768 and "
                    "is the POSITIVE CONTROL on the parse.")
    out["PASS"] = all(v["PASS"] for k, v in out.items() if isinstance(v, dict) and "PASS" in v)
    return out


def proof_negative_control() -> Dict[str, Any]:
    cases = []
    for why, argv in (
        ("no --max-model-len at all", ["vllm", "serve", "/m", "--port", "8031", "--seed", "0"]),
        ("the flag present but trailing, with no value", ["vllm", "serve", "/m", "--max-model-len"]),
        ("a non-integer value", ["vllm", "serve", "--max-model-len", "thirty-two-k"]),
        ("a non-positive value", ["vllm", "serve", "--max-model-len", "0"]),
        ("an empty argv", []),
    ):
        try:
            got = CL.parse_max_model_len(argv, where="negative control")
            cases.append({"why": why, "RAISED": False, "returned": got,
                          "VERDICT": "FAIL: it returned a value where it must have raised"})
        except CL.ContextLimitUnreadable as e:
            cases.append({"why": why, "RAISED": True, "error": str(e)[:160],
                          "VERDICT": "PASS"})
    ok = all(c["RAISED"] for c in cases)
    return {"_what": ("THE NEGATIVE CONTROL. Five argvs from which the limit cannot be read; the "
                      "parse must RAISE for every one and must never fall back to 32,768."),
            "n_cases": len(cases), "cases": cases, "PASS": ok,
            "VERDICT": ("PASS: every unreadable argv raised, so no run can silently assume its "
                        "limit." if ok else
                        "FAIL: at least one unreadable argv returned a value. The fix is DEAD: a "
                        "0.5x cell could plan against 32,768 while its engine serves 31,472.")}


def proof_kv_pool_is_not_the_limit(d: Path) -> Dict[str, Any]:
    rows = []
    for tag, name in (("one_x", ONE_X), ("kv0.5r_real_engine", HALF_X)):
        h = _hdr(d, name)
        lim = CL.parse_max_model_len(_argv(d, name), where=name)
        pool = h.get("gpu_kv_tokens")
        rows.append({"condition": tag, "max_model_len_from_argv": lim,
                     "gpu_kv_tokens": pool, "coincides": pool == lim})
    mis = [r for r in rows if not r["coincides"]]
    return {"_what": ("THE TRAP, MEASURED. `gpu_kv_tokens` is the harness's logical KV pool. If it "
                      "had been used as the limit it would have passed the 0.5x proof and been "
                      "wrong at 1x, which is why it is not the source."),
            "rows": rows,
            "PASS": bool(mis),
            "VERDICT": ("PASS: gpu_kv_tokens coincides with the limit at 0.5x and DIFFERS at 1x "
                        "(%s), so it is demonstrably a different quantity and using it would have "
                        "been wrong in every 1x cell."
                        % ", ".join("%s: pool %s vs limit %s" % (r["condition"], r["gpu_kv_tokens"],
                                                                 r["max_model_len_from_argv"])
                                    for r in mis)
                        if mis else
                        "INCONCLUSIVE: the pool equalled the limit at every condition here, so "
                        "this run cannot distinguish them. Do not read it as agreement.")}


def proof_read_sites_follow() -> Dict[str, Any]:
    """STEP 2: each read site is evaluated under two different limits and must FOLLOW both."""
    rows = []
    for path, expr, read in READ_SITES:
        got = {}
        err = None
        try:
            for probe in (31472, 12345):
                CL.configure_from_resolved(probe, "unit proof probe")
                got[probe] = int(read())
        except Exception as e:                                                 # noqa: BLE001
            err = "%s: %s" % (type(e).__name__, e)
        follows = (err is None and all(int(k) == v for k, v in got.items()))
        rows.append({"site": path, "expression": expr,
                     "observed": {str(k): v for k, v in got.items()},
                     "error": err,
                     "FOLLOWS_THE_RUN_LIMIT": follows,
                     "verdict": ("LIVE READ" if follows else
                                 "ABSENT OR STALE: this site does not follow the run's limit, so "
                                 "it implements no causal link and is a stopping condition")})
    CL.reset_for_test()
    ok = bool(rows) and all(r["FOLLOWS_THE_RUN_LIMIT"] for r in rows)
    return {"_what": ("OBSERVED, per read site. The limit is set to two different values and each "
                      "site's own expression is evaluated. A site that does not follow is a "
                      "write-only field: non-zero, varying, instrumentable and causally absent."),
            "rows": rows, "PASS": ok}


def proof_split_mode_handoff() -> Dict[str, Any]:
    """THE CHILD PROCESS'S READ, on the exact function `procsplit._serve` calls.

    In split mode, which is the DEFAULT, the coordinator, the arm and every decision live in a
    separate process fed only by `cfg`. A limit configured in the runner alone would be a write
    with no read there, so this exercises `configure_from_cfg` directly, in all three of its
    branches, and asserts that `procsplit.py` actually calls it rather than re-implementing it.
    """
    cases = []
    CL.reset_for_test()
    r = CL.configure_from_cfg({"context_limit_tokens": 31472,
                               "context_limit_source": "argv", "server_url": "http://x"})
    cases.append({"branch": "a real-server cfg carrying the resolved limit",
                  "limit": r["context_limit_tokens"], "source": r["source"],
                  "expected": 31472, "PASS": r["context_limit_tokens"] == 31472})
    CL.reset_for_test()
    try:
        CL.configure_from_cfg({"server_url": "http://x"})
        cases.append({"branch": "a cfg DECLARING A SERVER with no limit", "RAISED": False,
                      "PASS": False,
                      "note": "it must STOP: this is the run the ruling is about"})
    except CL.ContextLimitUnreadable as e:
        cases.append({"branch": "a cfg DECLARING A SERVER with no limit", "RAISED": True,
                      "error": str(e)[:140], "PASS": True})
    CL.reset_for_test()
    r = CL.configure_from_cfg({})
    cases.append({"branch": "a cfg with NO server (dry cell, harness self-checks, tests)",
                  "limit": r["context_limit_tokens"], "source": r["source"],
                  "expected": CL.MODEL_ARCH_MAX_TOKENS,
                  "PASS": (r["context_limit_tokens"] == CL.MODEL_ARCH_MAX_TOKENS
                           and r["source"] == CL.ARCH_SOURCE)})
    CL.reset_for_test()
    # THE CALL SITE, read from the file: a proof of a function nobody calls proves nothing.
    ps = (HERE / "procsplit.py").read_text()
    called = "CL.configure_from_cfg(cfg)" in ps
    reimplemented = "context_limit_tokens" in ps and "configure_from_resolved" in ps
    ok = all(c["PASS"] for c in cases) and called and not reimplemented
    return {"_what": ("OBSERVED. The split-mode hand-off, on the function procsplit._serve calls, "
                      "in all three branches, plus a check that procsplit CALLS it."),
            "cases": cases,
            "procsplit_calls_configure_from_cfg": called,
            "procsplit_reimplements_the_branching": reimplemented,
            "PASS": ok,
            "VERDICT": ("PASS: the child's read is live, it STOPS on a server cfg with no limit, "
                        "and procsplit calls this function rather than a copy of it." if ok else
                        "FAIL: the split-mode hand-off is not proved; in split mode, which is the "
                        "default, that is where the whole fix would be dead.")}


def proof_no_retyped_copy(live2: Path) -> Dict[str, Any]:
    """The census beside the absence claim, never a truncated view.

    IT COUNTS NUMBER TOKENS, NOT LINES THAT CONTAIN THE DIGITS. A line-based grep classifies this
    file's own docstring as code, because a docstring line does not start with `#`, and then the
    check fails on prose while a real retyped literal somewhere else is lost in the noise. The
    tokenizer is what distinguishes a VALUE from a mention of one, which is the only distinction
    the proof is about.
    """
    import io
    import tokenize
    # Offline analysis of the COMMITTED 1x cells, where 32,768 IS the right number. Left alone
    # deliberately: changing them would silently alter committed analysis of 1x cells, and a 0.5x
    # analysis limit is a separate ruling.
    offline = {"d170_overlimit.py", "d176_robot_headline.py", "confirm_engine_actions_32b.py",
               # the 1x REFERENCE threshold of the 0.5x count, the same register as the three
               # above: an analysis constant, read by no decision.
               "d223_overlimit_counts.py"}
    hits: List[Dict[str, Any]] = []
    for p in sorted(live2.rglob("*.py")):
        rel = str(p.relative_to(live2))
        text = p.read_text(errors="replace")
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
        except Exception as e:                                                 # noqa: BLE001
            hits.append({"file": rel, "line": 0, "text": "", "kind": "UNPARSED",
                         "verdict": "COULD NOT TOKENISE (%s): review by hand" % type(e).__name__})
            continue
        lines = text.splitlines()
        for t in toks:
            if t.type != tokenize.NUMBER:
                continue
            try:
                val = int(t.string.replace("_", ""))
            except Exception:                                                  # noqa: BLE001
                continue
            if val != 32768:
                continue
            ln = t.start[0]
            if p.name == Path(__file__).name:
                v = ("THIS CHECK'S OWN CONSTANT: the value the 1x argv is asserted to parse to, "
                     "and the comparand of this census. Not read by any decision.")
            elif p.name == "context_limit.py":
                v = ("THE ONE DECLARED DEFINITION: the model snapshot's own position limit, used "
                     "only when no server is configured, and reported under its own source string")
            elif p.name in offline:
                v = "OFFLINE ANALYSIS OF THE 1x CELLS, left alone by ruling"
            else:
                v = "A LITERAL VALUE IN THE POLICY TREE: must be reviewed"
            hits.append({"file": rel, "line": ln, "kind": "NUMBER token",
                         "text": (lines[ln - 1].strip()[:150] if ln <= len(lines) else ""),
                         "verdict": v})
    live_code = [h for h in hits if h["verdict"].startswith("A LITERAL VALUE")
                 or h["verdict"].startswith("COULD NOT TOKENISE")]
    return {"_what": ("THE CENSUS. Every 32768 NUMBER TOKEN in the live2 tree, each with a "
                      "verdict. Prose and comments are excluded by the tokenizer, not by a "
                      "pattern. The absence claim is the EMPTY `unreviewed_code_hits` list beside "
                      "this full census, not a grep read to its first page."),
            "n_hits": len(hits), "hits": hits,
            "unreviewed_code_hits": live_code,
            "PASS": not live_code}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-results", required=True,
                    help="dir holding header_1x.json and header_kv05r.json from the commit")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    d = Path(a.repo_results)

    out: Dict[str, Any] = {
        "_what": "D223 (2) unit proofs for the one context-limit read",
        "_ruling": ("D223 (2): the hard-coded 32,768 is replaced by the server's configured "
                    "max-model-len read at run start (D56: capacities are inputs)"),
        "values_observed": proof_values(d),
        "negative_control": proof_negative_control(),
        "kv_pool_is_not_the_limit": proof_kv_pool_is_not_the_limit(d),
        "read_sites_follow": proof_read_sites_follow(),
        "split_mode_handoff": proof_split_mode_handoff(),
        "no_retyped_copy": proof_no_retyped_copy(HERE),
    }
    keys = ("values_observed", "negative_control", "kv_pool_is_not_the_limit",
            "read_sites_follow", "split_mode_handoff", "no_retyped_copy")
    out["ALL_PASS"] = all(bool(out[k].get("PASS")) for k in keys)
    out["per_proof"] = {k: bool(out[k].get("PASS")) for k in keys}
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"ALL_PASS": out["ALL_PASS"], "per_proof": out["per_proof"],
                      "limit_at_kv05r": out["values_observed"]["kv0.5r_real_engine"]["parsed_LAST_occurrence"],
                      "limit_at_1x": out["values_observed"]["one_x"]["parsed_LAST_occurrence"]},
                     indent=1))
    return 0 if out["ALL_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
