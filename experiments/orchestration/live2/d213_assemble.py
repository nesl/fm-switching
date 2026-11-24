#!/usr/bin/env python3
"""D213 items 2 and 3: merge the four proof passes into one committed result file."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True)
    ap.add_argument("--origin-sha", required=True)
    ap.add_argument("--changed", nargs="+", required=True,
                    help="path=sha256 of each file this build changes")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.in_dir)

    def load(name):
        p = d / name
        return json.loads(p.read_text()) if p.exists() else {"_missing": name}

    doc = {
        "study": "StudyD213-METRICS-SCRAPE",
        "rulings": ["D213 item 2 (E1 of StudyPLACEHOLDER-FIX): give live2's AsyncLive2Backend a "
                    "/metrics scrape with D209 (2) hit-6 fail-loud semantics",
                    "D213 item 3 (E6): record the belief's predicted GPU prefix per request so "
                    "D211 signal (a) is computable"],
        "before_tree_is": "git archive of origin/main at one literal sha, unmodified",
        "origin_sha": a.origin_sha,
        "changed_files": dict(x.split("=", 1) for x in a.changed),
        "item2_unit_proofs": {"after": load("unit_after.json"),
                              "before_control": load("unit_before.json")},
        "item2_readsite_step2b": {"after": load("readsite_after.json"),
                                  "before_control": load("readsite_before.json")},
        "item3_proofs": {"after": load("item3_after.json"),
                         "before_control": load("item3_before.json")},
        "dry_digest_byte_identity": load("digests.json"),
    }
    t = doc["dry_digest_byte_identity"].get("arms") or []
    doc["headline"] = {
        "n_arms_paired": len(t),
        "n_identical": sum(1 for r in t if r.get("identical")),
        "n_moved": sum(1 for r in t if not r.get("identical")),
        "moved_arms": [r["arm"] for r in t if not r.get("identical")],
        "dry_decisions_moved_total": sum((r.get("moved_decisions") or {}).get("setwise", 0)
                                         for r in t),
        "positive_controls": {r["arm"]: r["positive_control"] for r in t
                              if r.get("positive_control")},
        "item2_reader_gets_before": (doc["item2_readsite_step2b"]["before_control"]
                                     .get("B_gpu_kv_fraction")),
        "item2_reader_gets_after": (doc["item2_readsite_step2b"]["after"]
                                    .get("B_gpu_kv_fraction")),
        "item2_free_kv_before": (doc["item2_readsite_step2b"]["before_control"]
                                 .get("C_free_kv_tokens")),
        "item2_free_kv_after": (doc["item2_readsite_step2b"]["after"].get("C_free_kv_tokens")),
    }
    Path(a.out).write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps(doc["headline"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
