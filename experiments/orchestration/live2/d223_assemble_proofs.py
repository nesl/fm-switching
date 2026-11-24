#!/usr/bin/env python3
"""D223 (2): stamp provenance on the proof outputs and place them under results/.

Same shape as `d213_assemble.py` and `d209_assemble.py`: the proofs write their own JSON to a work
directory, and this collects them, adds `_provenance`, and writes them where `results/INDEX.md`
can point at them.

WHY NOT `_provenance.stamp`. CLAUDE.md's convention is `from _provenance import stamp`, and its
`_git_commit()` runs `git rev-parse HEAD` in the repo root ABOVE the script. These proofs are run
from a private `git archive` of one literal sha, which has no `.git`, so `stamp` would record
`git_commit: "unknown"` for every one of them. The sha is instead passed in explicitly and
recorded as `base_sha`, which is the thing a reader needs: the commit the BEFORE tree was cut
from. `stamp`'s `model` and `device` fields do not apply to a decision-identity proof and are not
invented.

Usage:
  python d223_assemble_proofs.py --work DIR --out-dir DIR --base-sha SHA
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

# work-dir name -> committed name
FILES = {
    "unit_proofs.json": "d223_context_limit_unit_proofs.json",
    "dry_identity.json": "d223_byte_identity_1x.json",
    "realtime_probe.json": "d223_byte_identity_realtime_probe.json",
    "overlimit_counts.json": "d223_overlimit_counts.json",
}
SCRIPT_OF = {
    "d223_context_limit_unit_proofs.json": "d223_context_limit_unit_proofs.py",
    "d223_byte_identity_1x.json": "d223_dry_digest_identity.py",
    # No bespoke script: the probe is three runs of run_live2_real.py with no --server, diffed.
    # See the probe's own `_how_to_reproduce`.
    "d223_byte_identity_realtime_probe.json": "run_live2_real.py (three dry runs, diffed)",
    "d223_overlimit_counts.json": "d223_overlimit_counts.py",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--work", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--base-sha", required=True)
    a = ap.parse_args(argv)
    work, out = Path(a.work), Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat()
    done = []
    for src, dst in FILES.items():
        p = work / src
        if not p.exists():
            print("MISSING, not written: %s" % p)
            continue
        d = json.loads(p.read_text())
        d["_provenance"] = {
            "base_sha": a.base_sha,
            "script": SCRIPT_OF[dst],
            "ruling": "D223 (2), and D56 for the principle that capacities are inputs",
            "host": "flash (A6000 box); these are DRY proofs and no GPU is used",
            "register": "PROOF, not a measurement: no latency or accuracy here is reportable",
            "timestamp": ts,
            "note": ("the BEFORE tree is a private `git archive` of base_sha; the AFTER tree is "
                     "that archive plus this commit's edits. See d223_assemble_proofs.py for why "
                     "_provenance.stamp was not used."),
        }
        (out / dst).write_text(json.dumps(d, indent=1, default=str) + "\n")
        done.append(dst)
        print("wrote %s" % (out / dst))
    print(json.dumps({"written": done, "n": len(done)}, indent=1))
    return 0 if len(done) == len(FILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
