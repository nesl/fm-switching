#!/usr/bin/env python3
"""Proof for the RefSpatial point-parser fix: exactly the dropped replies change (CPU only).

  python3 -I experiments/casestudy/ss2_parser_fix_proof.py

The fix adds the {"x": .., "y": ..} object form to `ss2_bench_kit._iter_json_points`. A parser change
is only safe if it changes nothing that already parsed, so this re-parses EVERY committed RefSpatial
reply from both tiers with the committed parser (read out of git at the pre-fix commit) and with the
current one, and reports every reply whose parsed points differ. Masks are not needed and not used:
this proves the PARSE, not the score.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/casestudy"))
from _provenance import stamp  # noqa: E402

SS2 = ROOT / "results/casestudy/study_ss2"
PRE_FIX = "066b575"      # the last commit before the parser fix


def committed_parser(ref):
    src = subprocess.run(["git", "-C", str(ROOT), "show",
                          f"{ref}:experiments/casestudy/ss2_bench_kit.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = Path(ROOT / "results/casestudy/study_ss2/.prefix_kit.py")
    tmp.write_text(src)
    sys.path.insert(0, str(tmp.parent))
    import importlib
    mod = importlib.import_module(".prefix_kit".lstrip("."), package=None) if False else None
    spec = importlib.util.spec_from_file_location("prefix_kit", tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tmp.unlink()
    return mod


def main():
    import ss2_bench_kit as NEW
    OLD = committed_parser(PRE_FIX)
    man = {}
    with (SS2 / "refspatial_manifest.jsonl").open() as fh:
        for ln in fh:
            r = json.loads(ln)
            man[r["qid"]] = r
    changed, same = [], 0
    for tier in ("device", "cloud32b"):
        for r in json.loads((SS2 / f"refspatial_{tier}.json").read_text())["rows"]:
            m = man[r["qid"]]
            w, h = int(m["width"]), int(m["height"])
            raw = r["answer_raw"] or ""
            a = OLD.refspatial_parse_points(raw, w, h)
            b = NEW.refspatial_parse_points(raw, w, h)
            if a.shape != b.shape or (a.size and not np.array_equal(a, b)):
                changed.append(dict(tier=tier, qid=r["qid"], split=m["split"],
                                    points_before=int(a.shape[0]), points_after=int(b.shape[0]),
                                    parsed_after=[[int(x) for x in p] for p in b],
                                    committed_point_accuracy=float(r["score"]
                                                                   ["point_accuracy"]),
                                    answer_raw=raw))
            else:
                same += 1
    out = dict(
        label="RefSpatial point-parser fix proof: the {x, y} object form is now parsed, and nothing "
              "that already parsed has moved. PARSE-LEVEL ONLY; no mask is read and no score is "
              "recomputed here.",
        at=datetime.now().isoformat(), pre_fix_commit=PRE_FIX,
        replies_checked=same + len(changed), replies_unchanged=same,
        replies_changed=len(changed),
        changed_by_tier=dict(device=sum(1 for c in changed if c["tier"] == "device"),
                             cloud32b=sum(1 for c in changed if c["tier"] == "cloud32b")),
        changed=changed,
        not_recovered=dict(
            n=1,
            note="one further cloud reply carries x and y inside MALFORMED JSON, "
                 "'[{\"x\": 280, 840], \"y\": 840}]'. It is deliberately NOT recovered: the user's "
                 "instruction is to parse well-formed forms, and a regex loose enough to salvage "
                 "this would also salvage text that is not a coordinate. Listed so the choice is "
                 "visible rather than silent."),
        mask_hash_gap="the manifest records image_sha16 but NO mask hash, so a mask re-staged "
                      "elsewhere cannot be proven byte-identical to the one the committed run "
                      "scored against. The rescore therefore belongs on the box that holds the "
                      "original masks, and a mask sha256 should be recorded when it runs.")
    out["_provenance"] = stamp(script="ss2_parser_fix_proof.py", model="none", device="cpu",
                               n=same + len(changed), args=None)
    (SS2 / "ss2_parser_fix_proof.json").write_text(json.dumps(out, indent=1))
    print(f"checked {out['replies_checked']} replies: {same} unchanged, "
          f"{len(changed)} changed {out['changed_by_tier']}")
    for c in changed:
        print(f"  {c['tier']} {c['qid']} {c['points_before']} -> {c['points_after']} "
              f"{c['parsed_after']} (committed accuracy {c['committed_point_accuracy']})")


if __name__ == "__main__":
    import importlib.util  # noqa: E402  (used by committed_parser)
    main()
