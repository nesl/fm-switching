#!/usr/bin/env python3
"""Emit the StudyR8a tables from the results JSON, so no number is typed by hand."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = sys.argv[1] if len(sys.argv) > 1 else ""
RES = ROOT / f"results/escalation/study_r8a/study_r8a_results{TAG}.json"
OUTP = ROOT / f"results/escalation/study_r8a/study_r8a_tables{TAG}.md"

FAMILIES = ["query_only", "query+prefix_hand", "query+prefix_tfidf", "query+prefix_emb",
            "query+prefix_unc", "query+prefix_handunc", "prefix_unc", "prefix_handunc",
            "prefix_hand", "prefix_tfidf", "prefix_emb", "length_only",
            "CONTROL_shuffled_prefix", "answer_confidence"]


def fam(key):
    for f in sorted(FAMILIES, key=len, reverse=True):
        if key == f or key.startswith(f + "_k"):
            return f
    return key


def main():
    d = json.load(open(RES))
    L = []
    L.append("# StudyR8a — generated tables\n")
    L.append(f"From `{RES.relative_to(ROOT)}`. Every value computed; none typed.\n")

    g = d["gate"]
    L.append("## Gate\n")
    L.append(f"**{g['verdict']}**\n")
    L.append("| workload | best query+prefix router, k <= 100 | rank | k | acc @ e=0.2 | "
             "delta vs query-only | 95% CI | >= 2 pp and CI excludes 0 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for w, b in g["best_per_workload"].items():
        if b is None:
            L.append(f"| {w} | none | | | | | | |")
            continue
        L.append(f"| {w} | `{b['router']}` | {b['rank']} | {b['k']} | {b['acc']:.2f}% | "
                 f"{b['delta']:+.2f} pp | [{b['ci'][0]:+.2f}, {b['ci'][1]:+.2f}] | "
                 f"{'YES' if b['passes'] else 'no'} |")
    L.append("")

    for w, r in d["results"].items():
        L.append(f"\n# {w.upper()}  (n = {r['n']})\n")
        L.append(f"Device {100*r['device_acc']:.2f}% · cloud {100*r['cloud_acc']:.2f}% · "
                 f"gain counts {r['gain_counts']} · {r['n_folds']} folds\n")
        lat = r["decision_latency_s"]
        L.append("## Decision latency (Orin, standalone, uncontended)\n")
        L.append("| k | median s to the k-th reasoning token |")
        L.append("|---|---|")
        for k in [x for x in lat if x != "_n"]:
            L.append(f"| {k} | {lat[k]:.2f} |")
        L.append(f"\nn = {lat['_n']} Orin questions (`tokens_4bt_f16_F16.jsonl.gz`). "
                 "k = 0 is 0 s: decidable before generation starts.\n")

        for tgt in ("device_incorrect", "evidence_outside_window"):
            if tgt not in r["part1"]["query_only"]:
                continue
            L.append(f"## Part 1 — held-out AUROC for `{tgt}`\n")
            L.append("| router | k | latency s | AUROC | 95% CI | delta vs query-only | "
                     "paired 95% CI |")
            L.append("|---|---|---|---|---|---|---|")
            rows = sorted(r["part1"].items(),
                          key=lambda kv: -kv[1][tgt]["auroc"])
            for key, row in rows:
                c = row[tgt]
                L.append(f"| `{key}` | {row['k']} | {row['latency_s']:.1f} | "
                         f"{c['auroc']:.4f} | [{c['ci'][0]:.4f}, {c['ci'][1]:.4f}] | "
                         f"{c['delta_vs_query_only']:+.4f} | "
                         f"[{c['delta_ci'][0]:+.4f}, {c['delta_ci'][1]:+.4f}] |")
            L.append("")

        b = r["part2"]["_baselines"]
        L.append("## Part 2 — escalation utility\n")
        L.append("| e | random | perfect oracle | always-local | always-cloud |")
        L.append("|---|---|---|---|---|")
        for e, v in b.items():
            L.append(f"| {e[1:]} | {v['random']:.2f} | {v['oracle']:.2f} | "
                     f"{v['always_local']:.2f} | {v['always_cloud']:.2f} |")
        L.append("")
        L.append("### At e = 0.2, every router, both rankings\n")
        L.append("| router | k | latency s | rank | acc % | delta vs query-only | 95% CI |")
        L.append("|---|---|---|---|---|---|---|")
        rows = []
        for key, row in r["part2"].items():
            if key == "_baselines":
                continue
            for rank in ("by_gain", "by_failure"):
                c = row[f"e0.2_{rank}"]
                rows.append((c["delta_vs_query_only"], key, row["k"], row["latency_s"],
                             rank, c["acc"], c["ci"]))
        for dd, key, k, lat_, rank, acc, ci in sorted(rows, reverse=True):
            L.append(f"| `{key}` | {k} | {lat_:.1f} | {rank} | {acc:.2f} | {dd:+.2f} | "
                     f"[{ci[0]:+.2f}, {ci[1]:+.2f}] |")
        L.append("")

        L.append("### Best router at each budget e (by_gain)\n")
        L.append("| e | best router | k | acc % | delta vs query-only | 95% CI |")
        L.append("|---|---|---|---|---|---|")
        for e in d["rates"]:
            cand = []
            for key, row in r["part2"].items():
                if key == "_baselines" or key.startswith("CONTROL"):
                    continue
                c = row[f"e{e}_by_gain"]
                cand.append((c["delta_vs_query_only"], key, row["k"], c["acc"], c["ci"]))
            dd, key, k, acc, ci = max(cand)
            L.append(f"| {e} | `{key}` | {k} | {acc:.2f} | {dd:+.2f} | "
                     f"[{ci[0]:+.2f}, {ci[1]:+.2f}] |")
        L.append("")

        if r.get("part3_rescue_matrix"):
            p3 = r["part3_rescue_matrix"]
            L.append("## Part 3 — rescue matrix\n")
            L.append("| category | n |")
            L.append("|---|---|")
            for k, v in p3["counts"].items():
                L.append(f"| {k} | {v} |")
            L.append("")
            L.append("| overlap | n |")
            L.append("|---|---|")
            for k, v in p3["overlaps"].items():
                L.append(f"| {k} | {v} |")
            L.append("")
            a = p3["auroc_capability_vs_history_among_device_failures"]
            L.append(f"AUROC for capability-rescuable vs the rest, among the "
                     f"{a['n']} device failures ({a['n_positive']} positive):\n")
            L.append("| router | AUROC |")
            L.append("|---|---|")
            for k, v in sorted(a["per_router"].items(), key=lambda kv: -kv[1]):
                L.append(f"| `{k}` | {v:.4f} |")
            L.append("")

        L.append("## Mechanism Step 2 — feature audit (CONSTANT entries are stopping flags)\n")
        L.append("| k | features CONSTANT across questions |")
        L.append("|---|---|")
        for k, fa in r["feature_audit"].items():
            const = [n for n, v in fa.items() if v["status"] == "CONSTANT"]
            L.append(f"| {k} | {len(const)}: {', '.join(const) if const else 'none'} |")
        L.append("")

        t = r["mechanism_step3_trace"]
        L.append("## Mechanism Step 3 — one traced unit\n")
        L.append(f"Question `{t['question_id']}` (group `{t['group']}`), device "
                 f"{'correct' if t['device_correct'] else 'WRONG'}, cloud "
                 f"{'correct' if t['cloud_correct'] else 'wrong'}, gain {t['gain']}.\n")
        L.append("| k | prefix tokens | non-zero features | predicted gain | rank | "
                 "escalated at e=0.2 |")
        L.append("|---|---|---|---|---|---|")
        for k, v in t["per_k"].items():
            feats = ", ".join(f"{a}={b:g}" for a, b in list(v["features"].items())[:6])
            L.append(f"| {k} | {v['prefix_tokens']} | {feats or 'none'} | "
                     f"{v['predicted_gain']:+.5f} | {v['rank_of_n']} | "
                     f"{'yes' if v['escalated_at_e02'] else 'no'} |")
        L.append("")

    OUTP.write_text("\n".join(L) + "\n")
    print(f"wrote {OUTP}  ({len(L)} lines)")


if __name__ == "__main__":
    main()
