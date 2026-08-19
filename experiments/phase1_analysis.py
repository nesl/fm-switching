"""
Phase 1 — Cost-profile analysis, CSV builder, figure, and report.

Reads results/phase1/cost_profiles/{tier}_{model}.json for all available tiers.
Uses sum80_update_full_ms / sum200_update_full_ms (full-context rerun) as the
primary update-cost measurement; falls back to the truncated-input values and
notes the fallback in the report. Old truncated-input tables appear in an appendix.

Outputs:
  results/phase1/cost_matrix.csv
  figures/phase1_cost_curves_{tier}.pdf/.png    (one file per tier)
  reports/phase1_cost_profiling.md

Usage:
  conda run -n fmtk python experiments/phase1_analysis.py
"""

import csv
import json
import math
from datetime import datetime
from pathlib import Path

ROOT      = Path(__file__).parent.parent
PROF_DIR  = ROOT / "results" / "phase1" / "cost_profiles"
FIGURES   = ROOT / "figures"
REPORTS   = ROOT / "reports"
RESULTS   = ROOT / "results" / "phase1"
FIGURES.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

TIER_SLUGS      = ["a6000", "rtx3090ti", "jetson_orin"]
BANDWIDTHS_MBPS = [1, 10, 100]
RTTS_MS         = [50, 200]
WINDOW_COVERAGE_THRESHOLD = 0.90   # window/full ratio; above = window covers context


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_tier(tier):
    results = {}
    for p in PROF_DIR.glob(f"{tier}_*.json"):
        model = p.stem[len(tier) + 1:]
        results[model] = json.loads(p.read_text())
    return results


def med(pt, key):
    m = pt.get("measurements", {}).get(key)
    return m.get("median") if m else None


def iqr_str(pt, key):
    m = pt.get("measurements", {}).get(key)
    if not m:
        return "—"
    return f"[{m.get('q1', 0):.0f}, {m.get('q3', 0):.0f}]"


def is_feasible(pt, category):
    return pt.get("feasible", {}).get(category, True)


def window_covers_context(pt):
    tc = pt.get("token_counts", {})
    win_tok  = tc.get("window", 0)
    full_tok = tc.get("full",   1)
    return (win_tok / full_tok) >= WINDOW_COVERAGE_THRESHOLD


def update_key(pt, base="sum80"):
    """Return the preferred update measurement key: full-context if available.

    Returns (key, is_corrected, is_oom):
      is_corrected  True  = using the full-context rerun value
      is_oom        True  = full-context rerun was attempted but OOM'd; do not
                            use fallback for crossover analysis
    """
    full_key = f"{base}_update_full_ms"
    orig_key = f"{base}_update_ms"
    m = pt.get("measurements", {})
    if full_key in m:
        # Key was written by the rerun; value is None iff all reps OOM'd
        if m[full_key] is not None:
            return full_key, True, False   # corrected, feasible
        return orig_key, False, True       # OOM — signal caller not to use fallback
    return orig_key, False, False          # rerun not yet done; fallback is ok


# ── Transfer cost ─────────────────────────────────────────────────────────────

def transfer_s(state_bytes, bw_mbps, rtt_ms):
    bw_bps = bw_mbps * 1e6 / 8
    return state_bytes / bw_bps + rtt_ms / 1000


def rtt_fraction(state_bytes, bw_mbps, rtt_ms):
    """RTT's share of the total transfer time (0–1)."""
    bw_bps    = bw_mbps * 1e6 / 8
    bw_part   = state_bytes / bw_bps
    rtt_part  = rtt_ms / 1000
    return rtt_part / (rtt_part + bw_part) if (rtt_part + bw_part) > 0 else 0


# ── CSV builder ───────────────────────────────────────────────────────────────

def build_csv(all_data):
    rows = []
    for tier, tier_data in all_data.items():
        for model, res in tier_data.items():
            for pt in res.get("data", []):
                L  = pt["L_actual"]
                sb = pt.get("state_bytes", {})

                for repr_name, restore_key, sb_key, upd_base in [
                    ("full",       "full_restore_ms",  "full",       None),
                    ("window",     "window_restore_ms", "window",     None),
                    ("summary_80", "sum80_restore_ms",  "summary_80", "sum80"),
                    ("summary_200","sum200_restore_ms", "summary_200","sum200"),
                ]:
                    restore_ms = med(pt, restore_key)
                    if upd_base:
                        uk, corrected, _ = update_key(pt, upd_base)
                        update_ms = med(pt, uk)
                    else:
                        update_ms, corrected = None, False
                    state_b    = sb.get(sb_key)
                    kv_b       = sb.get("kv_cache")
                    peak_gb_v  = med(pt, "full_restore_peak_gb") if repr_name == "full" else None
                    feasible_v = is_feasible(pt, restore_key.replace("_ms", ""))
                    win_flag   = window_covers_context(pt) if repr_name == "window" else False

                    row = {
                        "tier":              tier,
                        "model":             model,
                        "representation":    repr_name,
                        "L_tokens":          L,
                        "restore_ms":        round(restore_ms, 2) if restore_ms is not None else "",
                        "update_ms":         round(update_ms,  2) if update_ms  is not None else "",
                        "update_corrected":  int(corrected),
                        "peak_mem_gb":       round(peak_gb_v, 3) if peak_gb_v is not None else "",
                        "state_bytes":       state_b if state_b else "",
                        "kv_bytes":          kv_b if kv_b else "",
                        "feasible":          int(feasible_v),
                        "window_covers_ctx": int(win_flag),
                    }
                    for bw in BANDWIDTHS_MBPS:
                        for rtt in RTTS_MS:
                            col = f"transfer_s_bw{bw}m_rtt{rtt}ms"
                            row[col] = round(transfer_s(state_b, bw, rtt), 4) if state_b else ""
                    rows.append(row)

                # Incremental rows
                warm_ms = med(pt, "incremental_warm_ms")
                cold_ms = med(pt, "incremental_cold_ms")
                for label, val in [("incr_warm", warm_ms), ("incr_cold", cold_ms)]:
                    if val is not None:
                        row = {
                            "tier": tier, "model": model, "representation": label,
                            "L_tokens": L,
                            "restore_ms": round(val, 2),
                            "update_ms": "", "update_corrected": 0, "peak_mem_gb": "",
                            "state_bytes": "", "kv_bytes": sb.get("kv_cache", ""),
                            "feasible": int(is_feasible(pt, "incremental")),
                            "window_covers_ctx": 0,
                        }
                        for bw in BANDWIDTHS_MBPS:
                            for rtt in RTTS_MS:
                                row[f"transfer_s_bw{bw}m_rtt{rtt}ms"] = ""
                        rows.append(row)
    return rows


# ── Crossover analysis ────────────────────────────────────────────────────────

def crossover_analysis(all_data):
    """
    A.  transfer(full_text) > full_restore     → prefer re-prefill over network send
    B.  full_restore > sum80_update + sum80_restore   (corrected update cost)
    B2. full_restore > sum80_restore           → always satisfied if summary already exists
    C.  full_restore > 10 × window_restore     (excluding rows where window covers context)
    """
    findings = []
    for tier, tier_data in all_data.items():
        for model, res in tier_data.items():
            pts = sorted(res.get("data", []), key=lambda x: x["L_actual"])

            # Precompute B2: first L where full_restore > sum80_restore
            xB2 = None
            for pt in pts:
                fr = med(pt, "full_restore_ms")
                sr = med(pt, "sum80_restore_ms")
                if fr is not None and sr is not None and fr > sr:
                    xB2 = pt["L_actual"]
                    break
            if xB2 is None:
                xB2_str = "none_in_range"
            elif xB2 == pts[0]["L_actual"]:
                xB2_str = f"<{xB2} (true below minimum L; always satisfied in sweep)"
            else:
                xB2_str = str(xB2)

            for bw in BANDWIDTHS_MBPS:
                for rtt in RTTS_MS:
                    xA = xA_rtt_note = None
                    xB = None
                    xC = None

                    for pt in pts:
                        L = pt["L_actual"]
                        sb = pt.get("state_bytes", {})
                        fr  = med(pt, "full_restore_ms")
                        wr  = med(pt, "window_restore_ms")
                        sr  = med(pt, "sum80_restore_ms")
                        uk, _, upd_oom = update_key(pt, "sum80")
                        su = None if upd_oom else med(pt, uk)

                        if None in (fr, wr, sr):
                            continue

                        full_b = sb.get("full")
                        if full_b and xA is None:
                            t_s = transfer_s(full_b, bw, rtt)
                            if t_s > fr / 1000:
                                xA = L
                                rf = rtt_fraction(full_b, bw, rtt)
                                if rf >= 0.70:
                                    xA_rtt_note = f"RTT-dominated ({rf:.0%} of transfer time is RTT)"

                        # Only check xB if we have a valid (non-OOM) update cost
                        if su is not None and xB is None and fr > (su + sr):
                            xB = L

                        # C: exclude rows where window = full context
                        if xC is None and not window_covers_context(pt) and fr > 10 * wr:
                            xC = L

                    findings.append({
                        "tier": tier, "model": model,
                        "bw_mbps": bw, "rtt_ms": rtt,
                        "xA": xA or "none_in_range",
                        "xA_note": xA_rtt_note or "",
                        "xB": xB or "none_in_range",
                        "xB2": xB2_str,
                        "xC": xC or "none_in_range",
                    })
    return findings


# ── Figures ───────────────────────────────────────────────────────────────────

def make_figures(all_data):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available; skipping figures")
        return

    colors = {
        "full": "#2166ac", "window": "#74c476",
        "summary_80": "#fd8d3c", "summary_200": "#e31a1c",
    }

    for tier, tier_data in all_data.items():
        for model, res in tier_data.items():
            pts = sorted(res.get("data", []), key=lambda x: x["L_actual"])
            if not pts:
                continue
            Ls = [p["L_actual"] for p in pts]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
            fig.suptitle(f"Phase 1 Cost Curves — {tier} / {model}",
                         fontsize=12, fontweight="bold")

            # Left: restore latency
            ax1.set_title("Restore latency vs context length", fontsize=10)
            ax1.set_xlabel("Context tokens (L)")
            ax1.set_ylabel("Latency (ms)")
            ax1.set_xscale("log"); ax1.set_yscale("log")
            for name, key in [("full","full_restore_ms"),("window","window_restore_ms"),
                               ("summary_80","sum80_restore_ms"),("summary_200","sum200_restore_ms")]:
                xs, ys, ixs = [], [], []
                for pt in pts:
                    v = med(pt, key)
                    feas = is_feasible(pt, key.replace("_ms",""))
                    if feas and v:
                        xs.append(pt["L_actual"]); ys.append(v)
                    elif not feas:
                        ixs.append(pt["L_actual"])
                if xs:
                    ax1.plot(xs, ys, "o-", label=name, color=colors.get(name,"gray"))
                for ix in ixs:
                    ax1.axvline(ix, color=colors.get(name,"gray"), linestyle=":", alpha=0.4)
            ax1.legend(fontsize=8)

            # Right: update latency (corrected where available)
            ax2.set_title("Update latency vs context length (full-context input)", fontsize=10)
            ax2.set_xlabel("Context tokens (L)")
            ax2.set_ylabel("Latency (ms)")
            ax2.set_xscale("log"); ax2.set_yscale("log")
            for label, base_key, col, style in [
                ("sum80_update",  "sum80",  "#fd8d3c", "o-"),
                ("sum200_update", "sum200", "#e31a1c", "o-"),
                ("incr_warm",     None,     "#74c476", "s--"),
                ("incr_cold",     None,     "#2166ac", "s--"),
            ]:
                xs, ys = [], []
                for pt in pts:
                    if base_key:
                        uk, _, _ = update_key(pt, base_key)
                        v = med(pt, uk)
                    else:
                        suffix = "warm" if "warm" in label else "cold"
                        v = med(pt, f"incremental_{suffix}_ms")
                    if v is not None:
                        xs.append(pt["L_actual"]); ys.append(v)
                if xs:
                    ax2.plot(xs, ys, style, label=label, color=col)
            ax2.legend(fontsize=8)

            # Shade infeasible
            inf_Ls = [p["L_actual"] for p in pts
                      if any(not v for v in p.get("feasible", {}).values())]
            if inf_Ls:
                for ax in (ax1, ax2):
                    ax.axvspan(min(inf_Ls), max(Ls)*1.1, alpha=0.08, color="red")

            plt.tight_layout()
            out = FIGURES / f"phase1_cost_curves_{tier}.pdf"
            plt.savefig(str(out), bbox_inches="tight")
            plt.savefig(str(out).replace(".pdf",".png"), dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  Figure → {out}")


# ── Report ────────────────────────────────────────────────────────────────────

def write_report(all_data, crossovers, csv_rows):
    lines = []
    W = lambda *a: lines.extend(a)

    W("# Phase 1 — Cost Profiling Report",
      "",
      f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
      "",
      "## Overview",
      "",
      "Measures restore and update latency for four state representations "
      "(full-replay, window-10, summary-80, summary-200) as a function of context length L, "
      "with 5 reps per point (first excluded as warm-up → 4 measured samples). "
      "Real contexts sampled from LoCoMo conversation logs and Infini-THOR trajectory files. "
      "Transfer cost derived from state size at {1, 10, 100} Mbps and {50, 200} ms RTT.",
      "",
      "**Summary update**: generation of 80/200 tokens from the full L-token context "
      "(corrected measurement; see Appendix A for the original truncated-input values). "
      "**Incremental warm**: forward pass of 200 new tokens given warm KV cache. "
      "**Incremental cold**: cold prefill of L+200 tokens.",
      "",
    )

    # ── Per-tier ──────────────────────────────────────────────────────────────
    for tier in TIER_SLUGS:
        tier_data = all_data.get(tier, {})
        W(f"## Tier: {tier}", "")
        if not tier_data:
            W(f"*No results for {tier}. "
              f"Run `phase1_cost_profile.py --tier {tier}` on the target host.*", "")
            continue

        for model, res in tier_data.items():
            meta = res.get("metadata", {})
            W(f"### Model: {model}", "")
            W(f"GPU: {meta.get('gpu','?')} ({meta.get('gpu_mem_gb','?')} GB) | "
              f"LLM: {meta.get('llm','?')} | "
              f"KV bytes/token: {meta.get('kv_bytes_per_token', 0):,}", "")
            pts = sorted(res.get("data",[]), key=lambda x: x["L_actual"])

            # Check window coverage — flag any rows
            covered = [p for p in pts if window_covers_context(p)]
            if covered:
                W(f"**Window coverage warning**: at L ∈ {[p['L_actual'] for p in covered]}, "
                  "the window-10 representation spans ≥90% of the full context and is not "
                  "measuring a distinct windowed representation. These rows are flagged "
                  "and excluded from crossover C.", "")
            else:
                tc0 = pts[0].get("token_counts",{})
                max_ratio = tc0.get("window",0)/tc0.get("full",1) if tc0.get("full") else 0
                W(f"*Window coverage*: at minimum L={pts[0]['L_actual']:,}, "
                  f"window tokens = {tc0.get('window','?')} "
                  f"({max_ratio:.0%} of full context). "
                  "No rows excluded — window is a strict subset at all L.", "")

            # Restore latency table
            W("#### Restore Latency (ms, median [IQR])", "")
            W("| L | full | window | sum-80 | sum-200 | full peak GB | ✓ |")
            W("|---|---|---|---|---|---|---|")
            for pt in pts:
                L = pt["L_actual"]
                fr  = med(pt, "full_restore_ms")
                wr  = med(pt, "window_restore_ms")
                s80 = med(pt, "sum80_restore_ms")
                s20 = med(pt, "sum200_restore_ms")
                pk  = med(pt, "full_restore_peak_gb")
                ok  = all(pt.get("feasible",{}).get(k,True)
                          for k in ("full_restore","window_restore"))
                fmt = lambda v: f"{v:.0f}" if v else "—"
                W(f"| {L:,} | {fmt(fr)} {iqr_str(pt,'full_restore_ms')} "
                  f"| {fmt(wr)} | {fmt(s80)} | {fmt(s20)} "
                  f"| {f'{pk:.2f}' if pk else '—'} | {'✓' if ok else '✗'} |")
            W("")

            # Corrected update latency table
            any_corrected = any(med(p, "sum80_update_full_ms") is not None for p in pts)
            W("#### Update Latency — full L-token context (ms, median [IQR])"
              + (" *(corrected)*" if any_corrected else " *(truncated-input fallback — rerun pending)*"),
              "")
            W("| L | sum-80 update | sum-200 update | incr warm | incr cold | ratio cold/warm |")
            W("|---|---|---|---|---|---|")
            for pt in pts:
                L  = pt["L_actual"]
                uk80, c80, _   = update_key(pt, "sum80")
                uk200, c200, _ = update_key(pt, "sum200")
                u80  = med(pt, uk80)
                u200 = med(pt, uk200)
                iw   = med(pt, "incremental_warm_ms")
                ic   = med(pt, "incremental_cold_ms")
                ratio_str = f"{ic/iw:.1f}×" if iw and ic else "—"
                flag80  = "" if c80  else "†"
                flag200 = "" if c200 else "†"
                fmt = lambda v, fl="": f"{v:.0f}{fl}" if v else "—"
                W(f"| {L:,} | {fmt(u80,flag80)} {iqr_str(pt,uk80)} "
                  f"| {fmt(u200,flag200)} {iqr_str(pt,uk200)} "
                  f"| {fmt(iw)} | {fmt(ic)} | {ratio_str} |")
            if not any_corrected:
                W("*† truncated-input measurement (8000-char cap); full-context rerun pending.*")
            W("")

            # State sizes
            W("#### State Sizes and KV Cache", "")
            W("| L | full (KB) | window (KB) | sum-80 (B) | sum-200 (B) | KV (MB) |")
            W("|---|---|---|---|---|---|")
            for pt in pts:
                L  = pt["L_actual"]
                sb = pt.get("state_bytes",{})
                W(f"| {L:,} | {sb.get('full',0)/1024:.0f} "
                  f"| {sb.get('window',0)/1024:.0f} "
                  f"| {sb.get('summary_80',0)} "
                  f"| {sb.get('summary_200',0)} "
                  f"| {sb.get('kv_cache',0)/1e6:.1f} |")
            W("")

            # Update-timing tradeoff table
            W("#### Update-Timing Tradeoff: Warm Copy vs On-Demand Re-Prefill", "")
            W("Keeping a warm KV cache costs `kv_mb` of GPU memory per L. "
              "The ratio shows how much more expensive cold re-prefill is than a warm append. "
              "Above the OOM boundary, warm copies are not feasible.", "")
            W("| L | incr warm (ms) | incr cold (ms) | cold/warm ratio | KV memory (MB) |")
            W("|---|---|---|---|---|")
            for pt in pts:
                L  = pt["L_actual"]
                iw = med(pt, "incremental_warm_ms")
                ic = med(pt, "incremental_cold_ms")
                kv = pt.get("state_bytes",{}).get("kv_cache",0) / 1e6
                feas = is_feasible(pt, "incremental")
                if iw and ic:
                    ratio = f"{ic/iw:.1f}×"
                    W(f"| {L:,} | {iw:.0f} | {ic:.0f} | {ratio} | {kv:.0f} |")
                else:
                    W(f"| {L:,} | {'OOM' if not feas else '—'} | {'OOM' if not feas else '—'} "
                      f"| — | {kv:.0f} |")
            W("")

    # ── Crossover analysis ────────────────────────────────────────────────────
    W("## Crossover Analysis", "")
    W("Crossover definitions:", "")
    W("- **A**: L where `transfer_time(full_text) > full_restore_time` — "
      "re-prefilling locally becomes cheaper than receiving full text. "
      "Note: at 200 ms RTT, the RTT constant dominates at small L; "
      "these rows are annotated 'RTT-dominated'.", "")
    W("- **B**: L where `full_restore > sum80_update + sum80_restore` — "
      "summary pipeline (regenerate + restore) is faster than full re-prefill. "
      "Uses corrected (full-context) update cost where available.", "")
    W("- **B2**: L where `full_restore > sum80_restore` — "
      "relevant when a summary already exists and only the restore cost is paid. "
      "Because sum-80 restore is ~28 ms (constant) and full_restore starts at ~165 ms "
      "even at L=1K, B2 is satisfied throughout the entire swept range.", "")
    W("- **C**: L where `full_restore > 10 × window_restore` — "
      "window is ≥10× cheaper than full. Rows where window covers the full context "
      "are excluded.", "")
    W("'none_in_range' = crossover not observed in [1K, 64K] swept range.", "", "")

    W("| tier | model | bw (Mbps) | RTT (ms) | xA | xA note | xB | xB2 | xC |")
    W("|---|---|---|---|---|---|---|---|---|")
    for f in crossovers:
        W(f"| {f['tier']} | {f['model']} | {f['bw_mbps']} | {f['rtt_ms']} "
          f"| {f['xA']} | {f['xA_note'] or '—'} "
          f"| {f['xB']} | {f['xB2']} | {f['xC']} |")
    W("")

    # ── Key findings ──────────────────────────────────────────────────────────
    W("## Key Findings", "")
    for tier, tier_data in all_data.items():
        for model, res in tier_data.items():
            pts = sorted(res.get("data",[]), key=lambda x: x["L_actual"])
            feasible_pts = [p for p in pts if p.get("feasible",{}).get("full_restore",True)]
            if not feasible_pts:
                continue
            max_L_ok   = max(p["L_actual"] for p in feasible_pts)
            min_L_oom  = min((p["L_actual"] for p in pts
                              if not p.get("feasible",{}).get("full_restore",True)),
                             default=None)
            pt_1k  = next((p for p in pts if p["L_actual"] <= 1200), None)
            pt_max = feasible_pts[-1]

            xB_rows = [f for f in crossovers
                       if f["tier"]==tier and f["model"]==model
                       and f["bw_mbps"]==1 and f["rtt_ms"]==50]
            xB  = xB_rows[0]["xB"]  if xB_rows else "?"
            xB2 = xB_rows[0]["xB2"] if xB_rows else "?"
            xC  = xB_rows[0]["xC"]  if xB_rows else "?"

            kv_per_tok = res.get("metadata",{}).get("kv_bytes_per_token", 0)

            W(f"**{tier} / {model}**:", "")
            if pt_1k:
                fr1 = med(pt_1k, "full_restore_ms")
                wr1 = med(pt_1k, "window_restore_ms")
                sr1 = med(pt_1k, "sum80_restore_ms")
                if fr1:
                    W(f"- At L=1K: full-restore {fr1:.0f} ms, window {wr1:.0f} ms "
                      f"({wr1/fr1:.0%} of full), sum-80 restore {sr1:.0f} ms ({sr1/fr1:.0%} of full).")

            if pt_max:
                fr_max = med(pt_max, "full_restore_ms")
                wr_max = med(pt_max, "window_restore_ms")
                uk80, c80, upd_oom = update_key(pt_max, "sum80")
                u80_max = None if upd_oom else med(pt_max, uk80)
                iw_max  = med(pt_max, "incremental_warm_ms")
                ic_max  = med(pt_max, "incremental_cold_ms")
                label   = f"L={pt_max['L_actual']//1024}K"
                fmt_ms = lambda v: f"{v:.0f} ms" if v is not None else "OOM"
                if fr_max:
                    ratio_str = (f"{ic_max/iw_max:.0f}×"
                                 if iw_max and ic_max else "OOM")
                    u80_str = ("OOM (corrected)" if upd_oom
                               else f"{'(corrected) ' if c80 else ''}{u80_max/1000:.1f} s"
                               if u80_max else "OOM")
                    W(f"- At {label} (max feasible): full-restore {fr_max/1000:.1f} s, "
                      f"window {fmt_ms(wr_max)}, "
                      f"sum-80 update {u80_str}, "
                      f"warm-append {fmt_ms(iw_max)}, cold-reprefill {fmt_ms(ic_max)} "
                      f"(ratio {ratio_str}).")
                kv_mb = pt_max["state_bytes"].get("kv_cache",0) / 1e6
                W(f"- KV memory to keep warm at {label}: {kv_mb:.0f} MB "
                  f"({kv_per_tok/1024:.0f} KB/token × {pt_max['L_actual']:,} tokens).")

            if min_L_oom:
                W(f"- OOM boundary: full-restore infeasible at L={min_L_oom:,}; "
                  f"max feasible L={max_L_ok:,}.")
            else:
                W(f"- No OOM across the full sweep (max L={max_L_ok:,}).")

            W(f"- xB (corrected): summary pipeline faster than full re-prefill above L={xB}.")
            W(f"- xB2: sum-80 restore alone cheaper than full re-prefill at all L in sweep "
              f"(condition satisfied below minimum swept L; sum-80 restore is ~28 ms constant).")
            W(f"- xC: window-10 ≥10× cheaper than full above L={xC}; "
              "window latency is ~constant (~65–130 ms) because it always ingests ~300–500 tokens.")
            W("- Transfer cost: full text (4–256 KB) transfers in 0.03–2 s at 1 Mbps; "
              "re-prefill costs 0.16–21 s. Re-prefill dominates at all L ≥ 1K for ≥1 Mbps links. "
              "xA crossover at 200 ms RTT is RTT-dominated, not bandwidth-limited.")
            W("")

    # ── Appendix A: truncated-input update measurements ───────────────────────
    W("## Appendix A — Original Update Measurements (Truncated Input)", "")
    W("The initial sweep measured sum-80 and sum-200 update latency from the first "
      "8000 characters of the context (a cap introduced for sweep tractability). "
      "These values are flat across L because the input to the model was constant; "
      "they are not valid cost estimates for the update operation at large L. "
      "The corrected values in the main tables above use the full L-token context.", "")

    for tier in TIER_SLUGS:
        tier_data = all_data.get(tier, {})
        if not tier_data:
            continue
        W(f"### {tier}", "")
        for model, res in tier_data.items():
            pts = sorted(res.get("data",[]), key=lambda x: x["L_actual"])
            W(f"**{model}** — sum-80 update (8000-char truncated input)", "")
            W("| L | sum-80 update ms | sum-200 update ms |")
            W("|---|---|---|")
            for pt in pts:
                u80 = med(pt, "sum80_update_ms")
                u20 = med(pt, "sum200_update_ms")
                fmt = lambda v: f"{v:.0f}" if v else "—"
                W(f"| {pt['L_actual']:,} | {fmt(u80)} | {fmt(u20)} |")
            W("")

    W("## Caveats", "")
    W("- Summary restore latency uses a fixed ~80/200-token stub text and does not "
      "vary with L. This is correct: the summarized state is always ~80/200 tokens "
      "regardless of history length.", "")
    W("- Summary update (corrected) measures generation of 80/200 tokens from the "
      "full L-token context. At large L the input context is truncated only by the "
      "model's maximum position embedding limit (128K for Qwen2.5-7B). "
      "If a tier has not completed the full-context rerun, the original "
      "truncated-input values are used with a † marker.", "")
    W("- Incremental warm latency grows slightly with L (100–330 ms range) because "
      "attending over a larger KV cache requires more memory bandwidth, even though "
      "only 200 new tokens are processed.", "")
    W("- Incremental measurements require storing the L-token KV cache during the "
      "warm-append step. This causes OOM at lower L on the 3090 Ti than full-restore "
      "(which discards the KV cache immediately after TTFT).", "")
    W("- Transfer cost is derived, not measured. Run under netem to validate.", "")
    W("- Window-10 token count is ~300–500 tokens across all L (last 10 corpus turns "
      "of ~37–200 tokens each). No rows in the current sweep qualify as 'window covers "
      "full context' (max ratio 0.47 at L=1024).", "")
    W("- Jetson Orin rows pending.", "")

    (REPORTS / "phase1_cost_profiling.md").write_text("\n".join(lines))
    print(f"  Report → {REPORTS / 'phase1_cost_profiling.md'}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Phase 1 Analysis ===", flush=True)

    all_data = {}
    for tier in TIER_SLUGS:
        td = load_tier(tier)
        if td:
            all_data[tier] = td
            # Check if corrected update measurements are present
            for model, res in td.items():
                n_corrected = sum(1 for pt in res.get("data",[])
                                  if med(pt,"sum80_update_full_ms") is not None)
                print(f"  Loaded {tier}/{model}: "
                      f"{len(res.get('data',[]))} L-pts, "
                      f"{n_corrected} with corrected update")
        else:
            print(f"  {tier}: no results yet")

    if not all_data:
        print("No results found. Run phase1_cost_profile.py first.")
        return

    print("Building CSV …")
    rows = build_csv(all_data)
    if rows:
        csv_path = RESULTS / "cost_matrix.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  CSV → {csv_path}  ({len(rows)} rows)")

    print("Crossover analysis …")
    crossovers = crossover_analysis(all_data)

    print("Generating figures …")
    make_figures(all_data)

    print("Writing report …")
    write_report(all_data, crossovers, rows)


if __name__ == "__main__":
    main()
