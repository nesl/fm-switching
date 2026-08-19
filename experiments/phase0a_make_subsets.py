"""
Phase 0a — Subset generator.
Creates fixed, stratified ID lists for the multi-model regime audit.

Outputs (data/audit_subsets/phase0a/):
  locomo_100.json       — 100 q_uids, stratified by evidence-distance bin
  infinithor_40.json    — 40 qids, stratified by num_evidence
  infinithor_60.json    — 60 qids, stratified by num_evidence (extended gate)
  egoschema_60.json     — 60 q_uids, random seed=42

Run once; commit the resulting JSONs (they define the fixed evaluation surface).
"""
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT   = Path(__file__).parent.parent
OUT    = ROOT / "data" / "audit_subsets" / "phase0a"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 42

# ── LoCoMo 100 ────────────────────────────────────────────────────────────────

def make_locomo_subset():
    scaled = json.loads((ROOT / "results" / "locomo_audit_scaled_qwen7b.json").read_text())
    records = scaled["records"]

    # Partition by distance bin
    by_bin = defaultdict(list)
    for r in records:
        bin_ = r["evidence_distance"].get("distance_bin", "not_found")
        by_bin[bin_].append(r["q_uid"])

    print("LoCoMo distance distribution:")
    for b, ids in sorted(by_bin.items()):
        print(f"  {b}: {len(ids)}")

    # Include ALL non-FAR questions; fill to 100 from FAR, balanced across convs
    selected = []
    for b in ("near", "mid", "not_found"):
        selected.extend(by_bin[b])

    n_far_needed = 100 - len(selected)
    far_ids = by_bin["far"]

    # Spread FAR sample across the 10 conversations
    conv_far = defaultdict(list)
    for uid in far_ids:
        cid = uid.rsplit("_q", 1)[0]
        conv_far[cid].append(uid)

    rng = random.Random(SEED)
    far_selected = []
    # Round-robin across conversations, then shuffle within each
    conv_lists = {c: sorted(ids) for c, ids in conv_far.items()}
    for ids in conv_lists.values():
        rng.shuffle(ids)
    convs = sorted(conv_lists.keys())
    i = 0
    while len(far_selected) < n_far_needed:
        cid = convs[i % len(convs)]
        if conv_lists[cid]:
            far_selected.append(conv_lists[cid].pop(0))
        i += 1

    selected.extend(far_selected)
    rng.shuffle(selected)

    # Verify
    sel_set = set(selected)
    assert len(sel_set) == 100, f"Expected 100, got {len(sel_set)}"

    # Annotate with metadata
    id_to_rec = {r["q_uid"]: r for r in records}
    out = {
        "subset": "locomo_100",
        "seed": SEED,
        "n": 100,
        "stratification": "all non-far bins included; far sample spread evenly across 10 conversations",
        "ids": selected,
        "metadata": {
            uid: {
                "conv_id": id_to_rec[uid]["conv_id"],
                "distance_bin": id_to_rec[uid]["evidence_distance"].get("distance_bin"),
                "turns_from_end": id_to_rec[uid]["evidence_distance"].get("turns_from_end", -1),
            }
            for uid in selected
        },
    }
    (OUT / "locomo_100.json").write_text(json.dumps(out, indent=2))
    print(f"  → locomo_100.json saved (n={len(selected)})")

    # Distance distribution in subset
    sub_bins = defaultdict(int)
    for uid in selected:
        sub_bins[id_to_rec[uid]["evidence_distance"].get("distance_bin", "not_found")] += 1
    print("  Subset distance distribution:", dict(sub_bins))


# ── Infini-THOR 40 ────────────────────────────────────────────────────────────

def make_infinithor_subset():
    mc_csv = ROOT / "data" / "infinithor" / "qa_set_nsieh_multi_clue.csv"
    traj_test = ROOT / "data" / "infinithor" / "traj_test"
    traj_train = ROOT / "data" / "infinithor" / "traj"

    available = set()
    for d in (traj_test, traj_train):
        available |= {p.stem for p in d.glob("*.txt")}

    rows = []
    with open(mc_csv) as f:
        for row in csv.DictReader(f):
            traj_id = row["qid"].rsplit("_q", 1)[0]
            if traj_id in available:
                rows.append(row)

    print(f"Infini-THOR multi-clue rows with available trajectories: {len(rows)}")

    # Stratify by num_evidence (1,2,3,4+)
    by_ne = defaultdict(list)
    for row in rows:
        ne = int(row.get("num_evidence", 1))
        bucket = str(min(ne, 4))
        by_ne[bucket].append(row)

    print("  num_evidence distribution:", {k: len(v) for k, v in sorted(by_ne.items())})

    rng = random.Random(SEED)
    selected = []
    total = len(rows)
    for bucket, bucket_rows in sorted(by_ne.items()):
        frac = len(bucket_rows) / total
        n_take = max(1, round(frac * 40))
        take = rng.sample(bucket_rows, min(n_take, len(bucket_rows)))
        selected.extend(take)

    # Trim or pad to exactly 40
    rng.shuffle(selected)
    if len(selected) > 40:
        selected = selected[:40]
    elif len(selected) < 40:
        remaining = [r for r in rows if r not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[:40 - len(selected)])

    assert len(selected) == 40

    out = {
        "subset": "infinithor_40",
        "seed": SEED,
        "n": 40,
        "stratification": "proportional by num_evidence bucket (1/2/3/4+)",
        "ids": [r["qid"] for r in selected],
        "metadata": {
            r["qid"]: {
                "num_evidence": r.get("num_evidence"),
                "traj_id": r["qid"].rsplit("_q", 1)[0],
                "answer": r.get("answer"),
            }
            for r in selected
        },
    }
    (OUT / "infinithor_40.json").write_text(json.dumps(out, indent=2))
    print(f"  → infinithor_40.json saved (n={len(selected)})")
    sub_ne = defaultdict(int)
    for r in selected:
        sub_ne[r.get("num_evidence", "?")] += 1
    print("  Subset num_evidence distribution:", dict(sub_ne))


# ── Infini-THOR 60 ───────────────────────────────────────────────────────────

def make_infinithor_60_subset():
    mc_csv = ROOT / "data" / "infinithor" / "qa_set_nsieh_multi_clue.csv"
    traj_test = ROOT / "data" / "infinithor" / "traj_test"
    traj_train = ROOT / "data" / "infinithor" / "traj"

    available = set()
    for d in (traj_test, traj_train):
        available |= {p.stem for p in d.glob("*.txt")}

    rows = []
    with open(mc_csv) as f:
        for row in csv.DictReader(f):
            traj_id = row["qid"].rsplit("_q", 1)[0]
            if traj_id in available:
                rows.append(row)

    by_ne = defaultdict(list)
    for row in rows:
        ne = int(row.get("num_evidence", 1))
        bucket = str(min(ne, 4))
        by_ne[bucket].append(row)

    rng = random.Random(SEED + 1)  # different seed from n=40 to get a superset via proportional draw
    selected = []
    total = len(rows)
    for bucket, bucket_rows in sorted(by_ne.items()):
        frac = len(bucket_rows) / total
        n_take = max(1, round(frac * 60))
        take = rng.sample(bucket_rows, min(n_take, len(bucket_rows)))
        selected.extend(take)

    rng.shuffle(selected)
    if len(selected) > 60:
        selected = selected[:60]
    elif len(selected) < 60:
        remaining = [r for r in rows if r not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[:60 - len(selected)])

    assert len(selected) == 60

    out = {
        "subset": "infinithor_60",
        "seed": SEED + 1,
        "n": 60,
        "stratification": "proportional by num_evidence bucket (1/2/3/4+)",
        "ids": [r["qid"] for r in selected],
        "metadata": {
            r["qid"]: {
                "num_evidence": r.get("num_evidence"),
                "traj_id": r["qid"].rsplit("_q", 1)[0],
                "answer": r.get("answer"),
            }
            for r in selected
        },
    }
    (OUT / "infinithor_60.json").write_text(json.dumps(out, indent=2))
    print(f"  → infinithor_60.json saved (n={len(selected)})")
    sub_ne = defaultdict(int)
    for r in selected:
        sub_ne[r.get("num_evidence", "?")] += 1
    print("  Subset num_evidence distribution:", dict(sub_ne))


# ── EgoSchema 60 ──────────────────────────────────────────────────────────────

def make_egoschema_subset():
    ans = json.loads((ROOT / "data" / "egoschema" / "subset_answers.json").read_text())
    all_uids = sorted(ans.keys())
    rng = random.Random(SEED)
    selected = rng.sample(all_uids, 60)

    out = {
        "subset": "egoschema_60",
        "seed": SEED,
        "n": 60,
        "stratification": "random",
        "ids": selected,
    }
    (OUT / "egoschema_60.json").write_text(json.dumps(out, indent=2))
    print(f"  → egoschema_60.json saved (n={len(selected)})")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Phase 0a subset generator ===")
    print("\n[LoCoMo 100]")
    make_locomo_subset()
    print("\n[Infini-THOR 40]")
    make_infinithor_subset()
    print("\n[Infini-THOR 60]")
    make_infinithor_60_subset()
    print("\n[EgoSchema 60]")
    make_egoschema_subset()
    print(f"\nAll subsets written to {OUT}")
    print("Commit these files to fix the evaluation surface.")


if __name__ == "__main__":
    main()
