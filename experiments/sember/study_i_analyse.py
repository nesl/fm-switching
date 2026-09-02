#!/usr/bin/env python3
"""
Standalone analysis for Study I — S-EMBER tier gap.

Reads results/sember/study_i/study_i_trials.jsonl and produces:
  results/sember/study_i/study_i_results.json   — machine-readable summary
  results/sember/study_i/study_i_summary.md     — human-readable markdown

Can run on partial data: will analyse whichever (model, sampling) combos
have ≥ 10 trials; incomplete configs are flagged but not excluded.

Analyses:
  A — Overall accuracy per config; 8B-4B gap; DENSE-SPARSE gain
  B — Accuracy by category × config; Fisher p-values for category gap
  C — Accuracy vs evidence distance (nearest_dist_s and farthest_dist_s bins)
  D — Latency: median / p90 / p99 / throughput per config
  E — Coverage arithmetic by window size k (farthest_dist_s, ast-based)
  F — DENSE vs SPARSE accuracy delta per model × category
  G — Placement verdict: is the 8B-4B gap large enough to matter?
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TRIALS_PATH = PROJECT_ROOT / "results/sember/study_i/study_i_trials.jsonl"
RESULTS_PATH = PROJECT_ROOT / "results/sember/study_i/study_i_results.json"
SUMMARY_PATH = PROJECT_ROOT / "results/sember/study_i/study_i_summary.md"

CATEGORIES = [
    "time_duration", "visual_detail_recall", "sequential_action", "location_trace",
    "spatial_aware_reasoning", "object_comparison", "temporal_ordering_recognition",
]
MODELS = ["qwen3vl4b", "qwen3vl8b"]
SAMPLINGS = ["SPARSE", "DENSE"]

GAP_THRESHOLD_PP = 5.0   # percentage points — below this the gap is not placement-relevant


# ── helpers ──────────────────────────────────────────────────────────────────

def acc(rows: list[dict]) -> float:
    if not rows:
        return float("nan")
    return sum(1 for r in rows if r.get("correct")) / len(rows)


def pct(v: float) -> str:
    return f"{v*100:.1f}%"


def fisher_p(n11: int, n10: int, n01: int, n00: int) -> float:
    """Fisher's exact test (two-sided) for 2×2 table."""
    from scipy.stats import fisher_exact
    _, p = fisher_exact([[n11, n10], [n01, n00]], alternative="two-sided")
    return p


def confidence_interval_95(n_correct: int, n_total: int) -> tuple[float, float]:
    """Wilson score 95% CI."""
    if n_total == 0:
        return (float("nan"), float("nan"))
    z = 1.96
    p = n_correct / n_total
    denom = 1 + z**2 / n_total
    centre = (p + z**2 / (2 * n_total)) / denom
    margin = z * math.sqrt(p * (1 - p) / n_total + z**2 / (4 * n_total**2)) / denom
    return (max(0, centre - margin), min(1, centre + margin))


def percentile(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    idx = p / 100 * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (idx - lo) * (s[hi] - s[lo])


# ── load ─────────────────────────────────────────────────────────────────────

def load_trials(path: Path = TRIALS_PATH) -> list[dict]:
    if not path.exists():
        sys.exit(f"trials file not found: {path}")
    rows = []
    errors = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if "error" in r:
                    errors += 1
                    continue
                rows.append(r)
            except json.JSONDecodeError:
                errors += 1
    print(f"Loaded {len(rows)} valid trials ({errors} errors skipped)")
    return rows


# ── analyses ─────────────────────────────────────────────────────────────────

def analysis_A(trials: list[dict]) -> dict:
    """Overall accuracy per config; gaps."""
    by = defaultdict(list)
    for r in trials:
        by[(r["model"], r["sampling"])].append(r)

    out: dict = {}
    print("\nA — Overall accuracy")
    print(f"  {'config':<30} {'n':>5} {'acc':>7} {'95% CI':>18}")
    for slug in MODELS:
        for mode in SAMPLINGS:
            rows = by[(slug, mode)]
            if not rows:
                continue
            k = f"{slug}_{mode}"
            a = acc(rows)
            n = len(rows)
            lo, hi = confidence_interval_95(sum(r.get("correct", False) for r in rows), n)
            out[k] = {"n": n, "acc": round(a, 4), "ci95_lo": round(lo, 4), "ci95_hi": round(hi, 4)}
            print(f"  {k:<30} {n:>5} {pct(a):>7}  [{pct(lo)}, {pct(hi)}]")

    # Gaps
    for mode in SAMPLINGS:
        k4, k8 = f"qwen3vl4b_{mode}", f"qwen3vl8b_{mode}"
        if k4 in out and k8 in out:
            gap = out[k8]["acc"] - out[k4]["acc"]
            out[f"gap_8b_4b_{mode}"] = round(gap, 4)
            print(f"  Gap 8B−4B ({mode}): {gap*100:+.1f}pp")

    # DENSE-SPARSE gain
    for slug in MODELS:
        ks, kd = f"{slug}_SPARSE", f"{slug}_DENSE"
        if ks in out and kd in out:
            delta = out[kd]["acc"] - out[ks]["acc"]
            out[f"dense_gain_{slug}"] = round(delta, 4)
            print(f"  DENSE−SPARSE ({slug}): {delta*100:+.1f}pp")

    return out


def analysis_B(trials: list[dict]) -> dict:
    """Accuracy by category with Fisher p-values for the 8B-4B gap (SPARSE)."""
    by = defaultdict(list)
    for r in trials:
        by[(r["model"], r["sampling"])].append(r)

    out: dict = {}
    print("\nB — Accuracy by category (8B−4B gap, SPARSE; p = Fisher exact)")
    print(f"  {'category':<35} {'4B-SP':>6} {'8B-SP':>6} {'gap':>6} {'n4':>4} {'n8':>4} {'p':>8}")
    for cat in CATEGORIES:
        out[cat] = {}
        for slug in MODELS:
            for mode in SAMPLINGS:
                rows = [r for r in by[(slug, mode)] if r.get("category") == cat]
                k = f"{slug}_{mode}"
                a = acc(rows)
                n = len(rows)
                out[cat][k] = {"n": n, "acc": round(a, 4)}

        # Gap and Fisher p for SPARSE
        k4s = out[cat].get("qwen3vl4b_SPARSE", {})
        k8s = out[cat].get("qwen3vl8b_SPARSE", {})
        n4, a4 = k4s.get("n", 0), k4s.get("acc", float("nan"))
        n8, a8 = k8s.get("n", 0), k8s.get("acc", float("nan"))

        if n4 > 0 and n8 > 0 and not math.isnan(a4) and not math.isnan(a8):
            c4 = round(a4 * n4)
            c8 = round(a8 * n8)
            # 2×2: correct/wrong × model
            p = fisher_p(c8, n8 - c8, c4, n4 - c4)
            gap = a8 - a4
            out[cat]["gap_SPARSE"] = round(gap, 4)
            out[cat]["fisher_p_SPARSE"] = round(p, 4)
            star = " *" if p < 0.05 else ("  ~" if p < 0.20 else "")
            print(f"  {cat:<35} {pct(a4):>6} {pct(a8):>6} {gap*100:>+5.1f}pp {n4:>4} {n8:>4} {p:>8.3f}{star}")
        else:
            print(f"  {cat:<35} {'n/a':>6} {'n/a':>6} {'n/a':>6} {n4:>4} {n8:>4} {'n/a':>8}")

    return out


def analysis_C(trials: list[dict]) -> dict:
    """Accuracy vs evidence distance bins (nearest and farthest)."""
    by = defaultdict(list)
    for r in trials:
        by[(r["model"], r["sampling"])].append(r)

    out: dict = {"nearest": {}, "farthest": {}}

    for dist_key, label in [("nearest_dist_s", "nearest (qt−aet)"),
                             ("farthest_dist_s", "farthest (qt−ast)")]:
        bins = [(0, 10), (10, 30), (30, 60), (60, 120), (120, float("inf"))]
        bin_labels = ["[0,10)", "[10,30)", "[30,60)", "[60,120)", "[120,∞)"]
        print(f"\nC — Accuracy vs {label} bins")
        print(f"  {'bin':<12}", end="")
        for slug in MODELS:
            for mode in SAMPLINGS:
                k = f"{slug}_{mode}"[:16]
                print(f"  {k:>16}", end="")
        print()

        section: dict = {}
        for bl, (lo, hi) in zip(bin_labels, bins):
            section[bl] = {}
            row_out = f"  {bl:<12}"
            for slug in MODELS:
                for mode in SAMPLINGS:
                    rows = [r for r in by[(slug, mode)]
                            if lo <= r.get(dist_key, -1) < hi]
                    k = f"{slug}_{mode}"
                    a = acc(rows)
                    n = len(rows)
                    section[bl][k] = {"n": n, "acc": round(a, 4) if not math.isnan(a) else None}
                    val = f"{pct(a)}(n={n})" if not math.isnan(a) else "n/a"
                    row_out += f"  {val:>16}"
            print(row_out)
        out[dist_key] = section

    return out


def analysis_D(trials: list[dict]) -> dict:
    """Latency and token statistics."""
    by = defaultdict(list)
    for r in trials:
        by[(r["model"], r["sampling"])].append(r)

    out: dict = {}
    print("\nD — Latency (ms) and tokens")
    print(f"  {'config':<30} {'lat_med':>8} {'lat_p90':>8} {'lat_p99':>8} {'tok_med':>8} {'tok/ms':>8}")
    for slug in MODELS:
        for mode in SAMPLINGS:
            rows = by[(slug, mode)]
            if not rows:
                continue
            k = f"{slug}_{mode}"
            lats = [r["total_latency_ms"] for r in rows if "total_latency_ms" in r]
            toks = [r["n_input_tokens"] for r in rows if "n_input_tokens" in r]
            if not lats:
                continue
            med_lat = statistics.median(lats)
            p90_lat = percentile(lats, 90)
            p99_lat = percentile(lats, 99)
            med_tok = statistics.median(toks) if toks else float("nan")
            tok_per_ms = med_tok / med_lat if med_lat > 0 else float("nan")
            out[k] = {
                "lat_med_ms": round(med_lat, 1),
                "lat_p90_ms": round(p90_lat, 1),
                "lat_p99_ms": round(p99_lat, 1),
                "tok_med": round(med_tok) if not math.isnan(med_tok) else None,
                "tok_per_ms": round(tok_per_ms, 2) if not math.isnan(tok_per_ms) else None,
            }
            print(f"  {k:<30} {med_lat:>8.0f} {p90_lat:>8.0f} {p99_lat:>8.0f} "
                  f"{med_tok:>8.0f} {tok_per_ms:>8.2f}")

    return out


def analysis_E(trials: list[dict]) -> dict:
    """Coverage by window size k (farthest_dist_s, ast-based)."""
    ref_rows = [r for r in trials
                if r["model"] == "qwen3vl4b" and r["sampling"] == "SPARSE"]
    n = len(ref_rows)
    out: dict = {}
    print(f"\nE — Coverage arithmetic (n={n} ref trials, 4B-SPARSE)")
    print(f"  window k   covered   fraction")
    for k in [3, 10, 30, 60, 120, 300, 600]:
        covered = sum(1 for r in ref_rows
                      if r.get("farthest_dist_s", float("inf")) <= k)
        frac = covered / n if n > 0 else 0
        out[str(k)] = {"covered": covered, "n": n, "frac": round(frac, 4)}
        print(f"  k={k:>5}s   {covered:>7}/{n}   {pct(frac):>8}")
    print(f"  (binding constraint = qt − ast = farthest_dist_s)")
    return out


def analysis_F(trials: list[dict]) -> dict:
    """DENSE vs SPARSE accuracy delta per model × category."""
    by = defaultdict(list)
    for r in trials:
        by[(r["model"], r["sampling"])].append(r)

    out: dict = {}
    print("\nF — DENSE−SPARSE accuracy delta per model × category")
    print(f"  {'category':<35} {'4B Δ':>8} {'8B Δ':>8}")
    for cat in CATEGORIES:
        out[cat] = {}
        row_out = f"  {cat:<35}"
        for slug in MODELS:
            sp_rows = [r for r in by[(slug, "SPARSE")] if r.get("category") == cat]
            de_rows = [r for r in by[(slug, "DENSE")] if r.get("category") == cat]
            a_sp, a_de = acc(sp_rows), acc(de_rows)
            delta = a_de - a_sp if not (math.isnan(a_sp) or math.isnan(a_de)) else float("nan")
            out[cat][slug] = round(delta, 4) if not math.isnan(delta) else None
            val = f"{delta*100:+.1f}pp" if not math.isnan(delta) else "n/a"
            row_out += f"  {val:>8}"
        print(row_out)
    return out


def analysis_G(A: dict, B: dict) -> dict:
    """Placement verdict: is gap large enough to justify two-tier deployment?"""
    gap_sp = A.get("gap_8b_4b_SPARSE", float("nan"))
    gap_de = A.get("gap_8b_4b_DENSE", float("nan"))

    cat_gaps = {cat: B[cat].get("gap_SPARSE", float("nan")) for cat in CATEGORIES}
    valid_gaps = [v for v in cat_gaps.values() if not math.isnan(v)]
    gap_min = min(valid_gaps) if valid_gaps else float("nan")
    gap_max = max(valid_gaps) if valid_gaps else float("nan")
    gap_spread = gap_max - gap_min if not (math.isnan(gap_min) or math.isnan(gap_max)) else float("nan")

    # Verdict thresholds
    def verdict(gap_pp: float) -> str:
        if math.isnan(gap_pp):
            return "UNKNOWN"
        if gap_pp < GAP_THRESHOLD_PP / 100:
            return "NEGLIGIBLE"
        elif gap_pp < 2 * GAP_THRESHOLD_PP / 100:
            return "SMALL"
        else:
            return "MEANINGFUL"

    vsp = verdict(gap_sp)
    vde = verdict(gap_de)

    out = {
        "gap_8b_4b_SPARSE_pp": round(gap_sp * 100, 2) if not math.isnan(gap_sp) else None,
        "gap_8b_4b_DENSE_pp": round(gap_de * 100, 2) if not math.isnan(gap_de) else None,
        "cat_gap_min_pp": round(gap_min * 100, 2) if not math.isnan(gap_min) else None,
        "cat_gap_max_pp": round(gap_max * 100, 2) if not math.isnan(gap_max) else None,
        "cat_gap_spread_pp": round(gap_spread * 100, 2) if not math.isnan(gap_spread) else None,
        "verdict_SPARSE": vsp,
        "verdict_DENSE": vde,
        "threshold_pp": GAP_THRESHOLD_PP,
    }

    print(f"\nG — Placement verdict (threshold: {GAP_THRESHOLD_PP}pp)")
    print(f"  8B−4B SPARSE: {gap_sp*100:+.1f}pp → {vsp}" if not math.isnan(gap_sp) else "  8B−4B SPARSE: n/a")
    print(f"  8B−4B DENSE:  {gap_de*100:+.1f}pp → {vde}" if not math.isnan(gap_de) else "  8B−4B DENSE: n/a")
    print(f"  Category gap range (SPARSE): [{gap_min*100:.1f}pp, {gap_max*100:.1f}pp], spread={gap_spread*100:.1f}pp"
          if not math.isnan(gap_spread) else "  Category gap range: n/a")

    return out


# ── markdown summary ──────────────────────────────────────────────────────────

def write_markdown(trials: list[dict], A: dict, B: dict, C: dict,
                   D: dict, E: dict, F: dict, G: dict) -> None:
    configs_present = sorted({(r["model"], r["sampling"]) for r in trials})
    n_complete = len(configs_present)

    lines = [
        "# Study I — S-EMBER tier gap: analysis summary",
        "",
        f"**Trials:** {len(trials)} valid  |  "
        f"**Configs complete:** {n_complete}/4  |  "
        f"**Generated:** `study_i_analyse.py`",
        "",
        "---",
        "",
        "## A — Overall accuracy",
        "",
        "| config | n | acc | 95% CI |",
        "|--------|---|-----|--------|",
    ]
    for slug in MODELS:
        for mode in SAMPLINGS:
            k = f"{slug}_{mode}"
            d = A.get(k)
            if not d:
                continue
            lo, hi = d.get("ci95_lo", float("nan")), d.get("ci95_hi", float("nan"))
            lines.append(f"| {k} | {d['n']} | {pct(d['acc'])} | [{pct(lo)}, {pct(hi)}] |")

    lines += [""]
    for mode in SAMPLINGS:
        gap = A.get(f"gap_8b_4b_{mode}")
        if gap is not None:
            lines.append(f"- **8B−4B gap ({mode}):** {gap*100:+.1f}pp")
    for slug in MODELS:
        delta = A.get(f"dense_gain_{slug}")
        if delta is not None:
            lines.append(f"- **DENSE−SPARSE ({slug}):** {delta*100:+.1f}pp")

    lines += [
        "",
        "## B — Accuracy by category (SPARSE)",
        "",
        "| category | 4B | 8B | gap | p |",
        "|----------|----|----|-----|---|",
    ]
    for cat in CATEGORIES:
        d = B.get(cat, {})
        a4 = d.get("qwen3vl4b_SPARSE", {}).get("acc", float("nan"))
        a8 = d.get("qwen3vl8b_SPARSE", {}).get("acc", float("nan"))
        n4 = d.get("qwen3vl4b_SPARSE", {}).get("n", 0)
        n8 = d.get("qwen3vl8b_SPARSE", {}).get("n", 0)
        gap = d.get("gap_SPARSE", float("nan"))
        p = d.get("fisher_p_SPARSE", float("nan"))
        a4s = pct(a4) if not math.isnan(a4) else "n/a"
        a8s = pct(a8) if not math.isnan(a8) else "n/a"
        gaps = f"{gap*100:+.1f}pp" if not math.isnan(gap) else "n/a"
        ps = f"{p:.3f}" if not math.isnan(p) else "n/a"
        lines.append(f"| {cat} | {a4s} (n={n4}) | {a8s} (n={n8}) | {gaps} | {ps} |")

    lines += [
        "",
        "## C — Accuracy vs evidence distance",
        "",
        "### nearest_dist_s (qt − aet)",
        "",
        "| bin | 4B-SPARSE | 8B-SPARSE | 4B-DENSE | 8B-DENSE |",
        "|-----|-----------|-----------|----------|----------|",
    ]
    nd = C.get("nearest_dist_s", {})
    for bl in ["[0,10)", "[10,30)", "[30,60)", "[60,120)", "[120,∞)"]:
        row = nd.get(bl, {})
        cells = []
        for slug in MODELS:
            for mode in SAMPLINGS:
                d = row.get(f"{slug}_{mode}", {})
                a = d.get("acc")
                n = d.get("n", 0)
                cells.append(f"{pct(a)}(n={n})" if a is not None else "n/a")
        lines.append(f"| {bl} | {' | '.join(cells)} |")

    lines += [
        "",
        "### farthest_dist_s (qt − ast, coverage-binding)",
        "",
        "| bin | 4B-SPARSE | 8B-SPARSE | 4B-DENSE | 8B-DENSE |",
        "|-----|-----------|-----------|----------|----------|",
    ]
    fd = C.get("farthest_dist_s", {})
    for bl in ["[0,10)", "[10,30)", "[30,60)", "[60,120)", "[120,∞)"]:
        row = fd.get(bl, {})
        cells = []
        for slug in MODELS:
            for mode in SAMPLINGS:
                d = row.get(f"{slug}_{mode}", {})
                a = d.get("acc")
                n = d.get("n", 0)
                cells.append(f"{pct(a)}(n={n})" if a is not None else "n/a")
        lines.append(f"| {bl} | {' | '.join(cells)} |")

    lines += [
        "",
        "## D — Latency",
        "",
        "| config | lat_med | lat_p90 | lat_p99 | tok_med | tok/ms |",
        "|--------|---------|---------|---------|---------|--------|",
    ]
    for slug in MODELS:
        for mode in SAMPLINGS:
            k = f"{slug}_{mode}"
            d = D.get(k)
            if not d:
                continue
            lines.append(
                f"| {k} | {d['lat_med_ms']:.0f}ms | {d['lat_p90_ms']:.0f}ms | "
                f"{d['lat_p99_ms']:.0f}ms | {d['tok_med']} | {d['tok_per_ms']:.2f} |"
            )

    lines += [
        "",
        "## E — Coverage (ast-based, farthest_dist_s)",
        "",
        "| window k | covered | fraction |",
        "|----------|---------|----------|",
    ]
    for k, d in E.items():
        lines.append(f"| {k}s | {d['covered']}/{d['n']} | {pct(d['frac'])} |")

    lines += [
        "",
        "## F — DENSE−SPARSE delta per category",
        "",
        "| category | 4B Δ | 8B Δ |",
        "|----------|------|------|",
    ]
    for cat in CATEGORIES:
        d = F.get(cat, {})
        d4 = d.get("qwen3vl4b")
        d8 = d.get("qwen3vl8b")
        d4s = f"{d4*100:+.1f}pp" if d4 is not None else "n/a"
        d8s = f"{d8*100:+.1f}pp" if d8 is not None else "n/a"
        lines.append(f"| {cat} | {d4s} | {d8s} |")

    lines += [
        "",
        "## G — Placement verdict",
        "",
        f"Threshold: {GAP_THRESHOLD_PP}pp",
        "",
        f"- **SPARSE:** {G.get('gap_8b_4b_SPARSE_pp', 'n/a'):+}pp → {G.get('verdict_SPARSE', 'n/a')}",
        f"- **DENSE:** {G.get('gap_8b_4b_DENSE_pp', 'n/a'):+}pp → {G.get('verdict_DENSE', 'n/a')}",
        f"- Category gap range (SPARSE): [{G.get('cat_gap_min_pp','n/a')}, {G.get('cat_gap_max_pp','n/a')}]pp",
        f"- Spread: {G.get('cat_gap_spread_pp','n/a')}pp",
    ]

    SUMMARY_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nSummary written: {SUMMARY_PATH}")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    trials = load_trials()

    # Report which configs are complete
    by_cfg = defaultdict(list)
    for r in trials:
        by_cfg[(r["model"], r["sampling"])].append(r)
    print("Config counts:")
    for slug in MODELS:
        for mode in SAMPLINGS:
            n = len(by_cfg[(slug, mode)])
            flag = "" if n >= 459 else f"  ← PARTIAL ({n}/459)"
            print(f"  {slug} {mode}: {n}{flag}")

    A = analysis_A(trials)
    B = analysis_B(trials)
    C = analysis_C(trials)
    D = analysis_D(trials)
    E = analysis_E(trials)
    F = analysis_F(trials)
    G = analysis_G(A, B)

    results = {
        "n_trials": len(trials),
        "A_overall": A,
        "B_by_category": B,
        "C_by_evidence_dist": C,
        "D_latency": D,
        "E_coverage": E,
        "F_dense_sparse_delta": F,
        "G_verdict": G,
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nResults JSON: {RESULTS_PATH}")

    write_markdown(trials, A, B, C, D, E, F, G)


if __name__ == "__main__":
    main()
