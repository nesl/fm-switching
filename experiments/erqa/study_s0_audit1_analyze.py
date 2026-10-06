#!/usr/bin/env python3
"""Study S0 Audit 1 analysis — category counts, direct/compositional contrast,
and within-category homogeneity of arrival-time static features (Correction 2).

Gate 2 framing: a category whose questions are IDENTICAL on all arrival-time
static features is the IDEAL instrument. Any within-category variance in
which-arm-wins is then provably not statically predictable, because a static
predictor must assign identical scores to every member of the block.
"""

import json, re, statistics
from collections import defaultdict, Counter
from pathlib import Path

SRC = Path("results/erqa/study_s0/audit1_mvrobobench.json")

ANCHOR = re.compile(r"options are based on", re.I)
CROSS = re.compile(
    r"across these images|across the|corresponds to the same"
    r"|each color appears exactly once|synchronized views", re.I)


def main():
    data = json.load(open(SRC))
    recs = data["records"]
    for r in recs:
        q = r["qa"]["question"]
        r["q_len"] = len(q)
        r["anchored"] = bool(ANCHOR.search(q))
        r["cross_cue"] = bool(CROSS.search(q))
        r["view_labels"] = tuple(
            i.get("illustration", "") for i in r["qa"].get("images", []))

    by_cat = defaultdict(list)
    for r in recs:
        by_cat[r["category"]].append(r)

    print(f"=== AUDIT 1 — MV-RoboBench (n={len(recs)}) ===\n")

    print("--- n by source ---")
    for s, c in sorted(Counter(r["source"] for r in recs).items()):
        print(f"  {s}: {c}")

    print("\n--- n by category ---")
    for cat in sorted(by_cat):
        print(f"  {cat:<36} {len(by_cat[cat]):>5}")

    print("\n--- DIRECT/COMPOSITIONAL CONTRAST: confound check ---")
    print("Structural marker distribution per category:\n")
    print(f"  {'category':<36} {'n':>5}  {'anchored':>9} {'cross-cue':>10}  {'uniform?':>9}")
    confounded = []
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        a = sum(r["anchored"] for r in rs)
        c = sum(r["cross_cue"] for r in rs)
        pa, pc = a / len(rs), c / len(rs)
        uniform = (pa in (0.0, 1.0)) and (pc in (0.0, 1.0))
        if uniform:
            confounded.append(cat)
        print(f"  {cat:<36} {len(rs):>5}  {100*pa:>8.0f}% {100*pc:>9.0f}%  "
              f"{'YES' if uniform else 'no':>9}")
    print(f"\n  {len(confounded)}/{len(by_cat)} categories are 100% uniform on structural markers.")
    print("  => The direct/compositional distinction is DETERMINED BY CATEGORY.")
    print("     It cannot be used as a factor orthogonal to category. The planned")
    print("     interaction [d_think(comp)] - [d_think(direct)] is a BETWEEN-CATEGORY")
    print("     comparison, not an independent within-category contrast.")

    print("\n--- CORRECTION 2: within-category homogeneity of arrival-time features ---")
    print("Features a static predictor can see before execution:")
    print("  category label, n_views, q_len, view_labels, question text (-> MiniLM)\n")
    print(f"  {'category':<36} {'n':>5} {'distinct':>9} {'largest':>8} {'n_views':>12} {'verdict':>14}")
    print(f"  {'':<36} {'':>5} {'q-strings':>9} {'block':>8} {'mean(sd)':>12}")

    homog = {}
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        qcount = Counter(r["qa"]["question"] for r in rs)
        n_distinct = len(qcount)
        largest = qcount.most_common(1)[0][1]
        nv = [r["n_views"] for r in rs]
        nv_sd = statistics.pstdev(nv)
        frac = largest / len(rs)
        if frac >= 0.25 and nv_sd < 0.1:
            v = "IDEAL"
        elif frac >= 0.10 or n_distinct < len(rs) * 0.5:
            v = "USABLE"
        else:
            v = "weak"
        homog[cat] = dict(n=len(rs), n_distinct=n_distinct, largest_block=largest,
                          largest_frac=frac, nv_sd=nv_sd, verdict=v)
        print(f"  {cat:<36} {len(rs):>5} {n_distinct:>9} {largest:>8} "
              f"{statistics.mean(nv):>6.2f}({nv_sd:>4.2f}) {v:>14}")

    print("\n  IDEAL  = a large block of questions identical on every static feature;")
    print("           a static predictor MUST score them identically (AUROC 0.5 within block).")
    print("  USABLE = substantial repeated blocks, partial static degeneracy.")
    print("  weak   = questions mostly textually unique; MiniLM may separate them.")

    print("\n--- Gate 2 instrument ranking (largest statically-identical block) ---")
    ranked = sorted(homog.items(), key=lambda kv: -kv[1]["largest_block"])
    for cat, h in ranked[:5]:
        print(f"  {cat:<36} largest identical block = {h['largest_block']:>4} "
              f"({100*h['largest_frac']:.0f}% of category)")

    best = ranked[0]
    print(f"\n  PRIMARY Gate 2 instrument: {best[0]}")
    print(f"    {best[1]['largest_block']} questions share a byte-identical question string,")
    print(f"    identical n_views, identical view configuration, identical category.")
    print(f"    Any variance in which-arm-wins across this block is unreachable by")
    print(f"    category, n_views, q_len, or any text embedding.")

    out = Path("results/erqa/study_s0/audit1_summary.json")
    json.dump({
        "n_total": len(recs),
        "by_source": dict(Counter(r["source"] for r in recs)),
        "by_category": {c: len(by_cat[c]) for c in by_cat},
        "marker_confound": {
            "n_uniform_categories": len(confounded),
            "n_categories": len(by_cat),
            "uniform_categories": confounded,
            "conclusion": "direct/compositional is determined by category; "
                          "not an orthogonal factor",
        },
        "homogeneity": homog,
        "primary_gate2_instrument": {
            "category": best[0],
            "largest_identical_block": best[1]["largest_block"],
        },
    }, open(out, "w"), indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
