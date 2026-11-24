#!/usr/bin/env python3
"""Assemble every D209 (2) proof artefact into the one committed result JSON."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# The two (or three) code trees live in a session-unique scratchpad, never in the working
# tree: the local HEAD is over 1,200 commits behind origin and its live2/ tree is stale to
# the point that live2/hybrid/ is absent, so every side of every comparison here is a
# `git archive` of ONE literal origin sha. Set D209_SP to the directory holding the
# `before/`, `after/` and `after_no22/` trees.
SP = Path(os.environ.get("D209_SP", "/tmp/d209"))
BASE = (SP / "BASE_SHA").read_text().strip()


def j(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception as e:                                             # noqa: BLE001
        return {"_missing": str(p), "_error": str(e)}


def main() -> int:
    out = Path(sys.argv[1])
    doc = {
        "study": "D209 (2) placeholder fixes: hits 26, 22 and 6",
        "code_under_test": {
            "base_sha_both_sides": BASE,
            "changed_files": ["experiments/orchestration/live2/touch_policy.py (hit 22)",
                              "experiments/orchestration/live2/engine_actions.py (hit 26)",
                              "experiments/orchestration/live/adapter.py (hit 6)"],
            "trees": {"before": "clean checkout of base_sha",
                      "after": "base_sha + all three fixes",
                      "after_no22": "base_sha + hits 26 and 6 ONLY, for per-hit attribution"}},
        "recipe": ("cf_pd_one_cell.py --cutoff-off, n=16, seed 4, run_s 1200, posted knobs "
                   "40:40:20 / lh_req / ss2 / epg / per-frame / reask 30.0; one dry cell per "
                   "process"),
        "byte_identity_all_three": j(SP / "d209_digests.json"),
        "byte_identity_the_five_matrix_arms_added_later": j(SP / "d209_digests_matrix5.json"),
        "byte_identity_simplestream_rerun": j(SP / "d209_digests_simplestream.json"),
        "byte_identity_confidence_cascade_rerun": j(SP / "d209_digests_cascade.json"),
        "byte_identity_streamscout_and_cascade_routing_rerun": j(SP / "d209_digests_matrix2b.json"),
        "attribution_hits_26_and_6_only": j(SP / "d209_digests_no22.json"),
        "unit_proofs_before": j(SP / "unit_before.json"),
        "unit_proofs_after": j(SP / "unit_after.json"),
        "hit22_price_cell_before": j(SP / "hit22_before.json"),
        "hit22_price_cell_after": j(SP / "hit22_after.json"),
        "step2b_rowdiffs": {p.stem: j(p) for p in sorted(SP.glob("step2b_*.json"))},
        "rung2_variants_concurrency_and_cache_key": {
            "_what": "the six runs of covex-v6-state-uo-c5attr that attribute the digest move",
            "diagkey_before": (SP / "diagkey_before.log").read_text()[-900:]
                              if (SP / "diagkey_before.log").exists() else None,
            "diagkey_after": (SP / "diagkey_after.log").read_text()[-900:]
                             if (SP / "diagkey_after.log").exists() else None,
            "price_semantically_reverted_in_after_tree":
                (SP / "negctl_after_revert.log").read_text()[-900:]
                if (SP / "negctl_after_revert.log").exists() else None},
        "d211_prereg_sha256": (SP / "prereg_sha.txt").read_text().strip()
                              if (SP / "prereg_sha.txt").exists() else None,
        "d211_signal_a_available_form": j(SP / "stage/d211_signal_a_available.json"),
        "_provenance": {
            "git_commit": BASE,
            "script": "d209_digest_driver.py + d209_unit_proofs.py + d209_hit22_prices.py + "
                      "d209_step2b_rowdiff.py",
            "model": "n/a (policy proofs, dry cells, no server)",
            "device": "flash (CPU)",
            "seed": 4,
            "timestamp": datetime.now().isoformat()},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print("wrote", out, out.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
