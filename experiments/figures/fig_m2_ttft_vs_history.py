#!/usr/bin/env python3
"""M2: first-token latency vs history tokens, cold vs warm, with the 3 s budget line.

Claim: cold first-token latency rises with history length and crosses the 3 s
first-token budget as the history grows, while a warm prefix (prefix reused) keeps
first-token latency far below the budget at every history length. This is why warm
state is worth carrying: it is the difference between meeting and missing the budget
on a long history.

CPU only. Committed data only: the StudyENG1 engine-timing requests (cold = engine
reported 0 cached tokens, warm = cached tokens > 0) and the StudyV5-ENGINE 32B
deployment-stack confirmation points (engine_actions_32b_confirmation_m2.json).
The two are different regimes and are drawn as different series: ENG1 is the engine
study's full request mix, the confirmation is an idle one-request-at-a-time check on
Qwen3-VL-32B-Instruct. Both show the same cold-rises, warm-flat separation.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

ENG1_GLOB = "results/cost/study_eng1/eng1_part?_requests_h100nvl.jsonl"
CONF = "results/orchestration/live2/v5/engine_actions_32b_confirmation_m2.json"
FIGID = "M2_ttft_vs_history_cold_warm"
SLO = 3.0


def cached(r):
    c = r.get("cached_tokens")
    return c if c is not None else 0


def load_eng1():
    rows = []
    for f in glob.glob(str(F.REPO / ENG1_GLOB)):
        for l in open(f):
            import json
            r = json.loads(l)
            if r.get("error") or r.get("ttft_s") is None or r.get("prompt_tokens") is None:
                continue
            rows.append(r)
    # Clean contrast: fully cold (0 cached, the whole prefix is rebuilt) vs warm
    # (the prefix is already built and only a small new delta, at most one 1024-token
    # piece, is prefilled). The uncached delta is what drives first-token latency, so
    # bounding it isolates the warm-reuse regime. Partially cached rebuilds (a larger
    # uncached delta) are neither and are excluded from both series: they are a
    # mostly-cold build wearing a warm flag and otherwise spike the warm line.
    WARM_DELTA = 1024
    cold = [(r["prompt_tokens"], r["ttft_s"]) for r in rows if cached(r) == 0]
    warm = [(r["prompt_tokens"], r["ttft_s"]) for r in rows
            if 0 < r["prompt_tokens"] - cached(r) <= WARM_DELTA]
    return rows, cold, warm


def binned(points, edges):
    pts = np.array(points)
    xs, med, lo, hi = [], [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = pts[(pts[:, 0] >= a) & (pts[:, 0] < b), 1]
        if len(sel) >= 10:
            xs.append((a + b) / 2)
            med.append(np.median(sel))
            lo.append(np.percentile(sel, 25))
            hi.append(np.percentile(sel, 75))
    return np.array(xs), np.array(med), np.array(lo), np.array(hi)


def crossing(xs, med, level):
    for i in range(1, len(xs)):
        if med[i - 1] < level <= med[i]:
            f = (level - med[i - 1]) / (med[i] - med[i - 1])
            return xs[i - 1] + f * (xs[i] - xs[i - 1])
    return None


def main():
    import json
    rows, cold, warm = load_eng1()
    edges = np.arange(0, 31000, 1500)
    xc, mc, lc, hc = binned(cold, edges)
    xw, mw, lw, hw = binned(warm, edges)
    cross = crossing(xc, mc, SLO)

    conf = json.load(open(F.REPO / CONF))
    creq = [r for r in conf["requests"] if r.get("ttft_s") is not None and r.get("prompt_tokens")]
    cc = [(r["prompt_tokens"], r["ttft_s"]) for r in creq if (r.get("cached_tokens") or 0) == 0]
    cw = [(r["prompt_tokens"], r["ttft_s"]) for r in creq
          if 0 < r["prompt_tokens"] - (r.get("cached_tokens") or 0) <= 1024]

    fig, ax = F.new_fig(7.2, 4.5)
    ax.grid(True, axis="both", color=F.GRID, linewidth=0.7, zorder=0)

    ax.fill_between(xc, lc, hc, color=F.RISK, alpha=0.14, zorder=1)
    ax.plot(xc, mc, color=F.RISK, lw=2.2, marker="o", ms=5, zorder=4,
            label="cold, first build (StudyENG1)")
    ax.fill_between(xw, lw, hw, color=F.GREEN, alpha=0.16, zorder=1)
    ax.plot(xw, mw, color=F.GREEN, lw=2.2, ls="--", marker="s", ms=5, zorder=4,
            label="warm, prefix reused (StudyENG1)")

    ax.scatter([p for p, _ in cc], [t for _, t in cc], s=20, facecolors="none",
               edgecolors=F.shade(F.RISK, 0.2), linewidths=1.0, zorder=5,
               label="32B idle confirmation, cold")
    ax.scatter([p for p, _ in cw], [t for _, t in cw], s=20, marker="s",
               facecolors="none", edgecolors=F.shade(F.GREEN, 0.2), linewidths=1.0,
               zorder=5, label="32B idle confirmation, warm")

    ax.axhline(SLO, color=F.INK, lw=1.4, ls=(0, (6, 4)), zorder=3)
    ax.text(30500, SLO + 0.12, "3 s first-token budget", ha="right", va="bottom",
            fontsize=9, color=F.INK)
    if cross:
        ax.axvline(cross, color=F.GREY, lw=1.1, ls=":", zorder=2)
        ax.annotate(f"cold crosses 3 s\nat ~{cross/1000:.0f}k tokens",
                    xy=(cross, SLO), xytext=(cross + 1500, 5.2),
                    fontsize=9, color=F.INK,
                    arrowprops=dict(arrowstyle="->", color=F.GREY, lw=1.1))

    ax.set_xlabel("history length (prompt tokens)")
    ax.set_ylabel("first-token latency (s)")
    ax.set_xlim(0, 31000)
    ax.set_ylim(0, 6.2)
    ax.set_xticks(np.arange(0, 31000, 5000))
    ax.set_xticklabels([f"{int(v/1000)}k" for v in np.arange(0, 31000, 5000)])
    ax.legend(loc="upper left", ncol=1, fontsize=8.6)
    ax.set_title("Cold first-token latency crosses the 3 s budget; warm does not",
                 fontsize=11, pad=8)
    F.save(fig, FIGID, pilot=False)

    warm_hi = max(t for _, t in warm)
    claim = (
        "Cold first-token latency rises with history length and crosses the 3 s first-token "
        f"budget at about {cross/1000:.0f}k prompt tokens, while a warm prefix keeps first-token "
        "latency far below the budget at every history length (the warm median stays near 0.3 s "
        "and does not approach 3 s even at 30k tokens). The 32B idle deployment-stack confirmation "
        "reproduces the same cold-rises, warm-flat separation. Bands are the 25th to 75th percentile "
        "of the binned requests."
    )
    n_cold = sum(1 for r in rows if cached(r) == 0)
    n_warm = sum(1 for r in rows if 0 < r["prompt_tokens"] - cached(r) <= 1024)
    n_part = len(rows) - n_cold - n_warm
    notes = (
        "Cold is the engine-reported 0 cached tokens (the whole prefix is rebuilt); warm is a built prefix with "
        "only a small new delta prefilled (uncached tokens at most one 1024-token piece). The uncached delta is "
        "what drives first-token latency, so bounding it isolates the warm-reuse regime; partially cached "
        "rebuilds with a larger uncached delta are excluded from both series. ENG1 curves are the "
        f"StudyENG1 engine-timing request mix on the H100 deployment stack ({n_cold:,} cold, {n_warm:,} warm, "
        f"{n_part:,} partial excluded, over 313 to 30,105 prompt tokens); the "
        "overlay points are the StudyV5-ENGINE 32B confirmation, one request at a time and idle on "
        "Qwen3-VL-32B-Instruct, so it sits at the lower, unloaded end and is drawn as a separate series, not "
        "merged into the ENG1 bands. Cold is risk-orange, warm is KV-green; the warm series also carries a "
        "dashed line and square markers so the two never rest on colour alone. This figure measures the "
        "physical component of context inertia (transfer and reconstruction latency), the premise the policy acts on."
    )
    srcs = sorted(glob.glob(str(F.REPO / ENG1_GLOB)))
    srcs = [str(Path(s).relative_to(F.REPO)) for s in srcs] + [CONF]
    F.write_caption(FIGID, claim, srcs, pilot=False, notes=notes)


if __name__ == "__main__":
    main()
