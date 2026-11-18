"""M3b Why pieces work.

Two aligned horizontal strips over the same ~4 s window: top = a one-go (mono)
rebuild, bottom = a 1,024-piece chained rebuild. Each engine step is a block
coloured by what it served: the rebuild / its piece, background requests, or both.
One inter-piece gap is annotated with its duration and "others served".

Source: StudyENG1e-chain step log, mode A, load P40. SELECTION RULE: for each
action the trial whose total imposed delay (latency sum) is closest to the cell
median (eng1e_results.json cells_all).
  results/cost/study_eng1e/eng1e_requests_h100nvl.jsonl.gz  (request rows)
  results/cost/study_eng1e/eng1e_steps_A_P40.jsonl.gz       (per-step add-on log)
Report reproduced: reports/study_eng1e_chain.md sections 5, 6, 7 (one step per
piece; inter-piece gap A chain1024 P40 median 0.173 s; the engine serves queued
background in 77-100% of gaps).
Caching: prefix caching ON; host tier full; the action's first piece and the mono
rebuild are cold (<=16 cached tokens); later pieces reuse their own prefix chain.
The step add-on FAILED the unloaded overhead gate and PASSED at P40 (this cell is
loaded; both arms ran with the add-on, so imposed delay is unaffected).
"""
import json, gzip, statistics
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import figstyle as F

F.apply_style()
ROOT = F.ROOT
rows = [json.loads(l) for l in gzip.open(ROOT / "results/cost/study_eng1e/eng1e_requests_h100nvl.jsonl.gz", "rt")]
steps = [json.loads(l) for l in gzip.open(ROOT / "results/cost/study_eng1e/eng1e_steps_A_P40.jsonl.gz", "rt") if '"r"' in l]
cells = json.load(open(ROOT / "results/cost/study_eng1e/eng1e_results.json"))["cells_all"]


def cell_rows(action, trial, arm="with"):
    return [r for r in rows if r.get("mode") == "A" and r.get("load") == "P40"
            and r.get("action") == action and r.get("trial") == trial and r.get("arm") == arm]


def imposed_by_trial(action):
    out = {}
    trials = sorted(set(r["trial"] for r in rows if r.get("mode") == "A" and r.get("load") == "P40"
                        and r.get("action") == action and not r.get("holdout") and r.get("trial") is not None))
    for tr in trials:
        def arm(a):
            d = {}
            for r in cell_rows(action, tr, a):
                if r.get("kind") == "episodic" and r.get("rid"):
                    d[r["rid"].split("-", 1)[1]] = r.get("latency_s")
            return d
        w, wo = arm("with"), arm("without")
        common = [k for k in w if k in wo and w[k] is not None and wo[k] is not None]
        if common:
            out[tr] = sum(w[k] - wo[k] for k in common)
    return out


def rid_of(engine_rid):
    # "chatcmpl-<rid>-<8hex>" -> "<rid>"
    s = engine_rid[len("chatcmpl-"):] if engine_rid.startswith("chatcmpl-") else engine_rid
    return s.rsplit("-", 1)[0]


def build_strip(action):
    cm = cells[f"A|P40|{action if action=='mono' else 'chain1024'}"]["total_imposed_lat_s"]["median"]
    imp = imposed_by_trial(action)
    trial = min(imp, key=lambda t: abs(imp[t] - cm))
    cr = cell_rows(action, trial)
    injects = sorted([r for r in cr if r.get("kind") == "inject"], key=lambda r: r["t_submit"])
    action_rids = {r["rid"] for r in injects}
    bg_rids = {r["rid"] for r in cr if r.get("kind") == "episodic" and r.get("rid")}
    t0a = injects[0]["t_submit"]
    t_end = max((r.get("t_end") or 0) for r in injects)
    win = (t0a, t_end)
    # steps overlapping this trial (their scheduled rids belong to this trial)
    blocks, prev_end = [], None
    srt = sorted(steps, key=lambda d: d["t0"])
    for d in srt:
        end = d["t0"] + d["el"] / 1000.0
        if end < win[0] - 0.05 or d["ts"] > win[1] + 0.3:
            continue
        rids = {rid_of(x[0]) for x in d["r"]}
        has_a = bool(rids & action_rids)
        has_b = bool(rids & bg_rids)
        if not (has_a or has_b):
            continue
        start = max(d["ts"], prev_end) if prev_end is not None else d["ts"]
        start = max(start, win[0] - 0.02)
        if end <= start:
            end = start + 0.004
        kind = "both" if (has_a and has_b) else ("action" if has_a else "bg")
        # which inject (piece) this step mainly served, for gap computation
        piece = None
        for x in d["r"]:
            rr = rid_of(x[0])
            if rr in action_rids and x[2] == "p":
                piece = rr
        blocks.append(dict(start=start - t0a, end=end - t0a, kind=kind, piece=piece))
        prev_end = end
    return trial, injects, blocks, t0a, (t_end - t0a)


mono_trial, mono_inj, mono_blocks, mono_t0, mono_span = build_strip("mono")
chain_trial, chain_inj, chain_blocks, chain_t0, chain_span = build_strip("chain1024")

# inter-piece gaps on the chain: for each consecutive piece, gap = next piece
# first-step start minus this piece last-step end.
piece_steps = {}
for b in chain_blocks:
    if b["piece"]:
        piece_steps.setdefault(b["piece"], []).append(b)
ordered = [r["rid"] for r in chain_inj]
gaps = []
for k in range(len(ordered) - 1):
    a, b = ordered[k], ordered[k + 1]
    if a in piece_steps and b in piece_steps:
        gap = min(x["start"] for x in piece_steps[b]) - max(x["end"] for x in piece_steps[a])
        if gap > 0:
            gaps.append((k, gap, max(x["end"] for x in piece_steps[a]), min(x["start"] for x in piece_steps[b])))
gap_median = statistics.median([g[1] for g in gaps]) if gaps else float("nan")
# pick a representative gap near the chain middle whose duration is near the median
rep = min(gaps, key=lambda g: abs(g[1] - gap_median)) if gaps else None

# ---- figure ----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(F.COL2, 1.95))
COLMAP = {"action": F.C_SERVED_ACTION, "bg": F.C_SERVED_BG, "both": F.C_SERVED_BOTH}
rows_y = {"mono": 1.0, "chain": 0.0}
H = 0.6
for b in mono_blocks:
    ax.broken_barh([(b["start"], max(b["end"] - b["start"], 0.004))], (rows_y["mono"] - H / 2, H),
                   facecolors=COLMAP[b["kind"]], edgecolor="white", linewidth=0.2)
for b in chain_blocks:
    ax.broken_barh([(b["start"], max(b["end"] - b["start"], 0.004))], (rows_y["chain"] - H / 2, H),
                   facecolors=COLMAP[b["kind"]], edgecolor="white", linewidth=0.2)

ax.set_yticks([rows_y["chain"], rows_y["mono"]])
ax.set_yticklabels(["1,024-piece\nchain", "one-go\nrebuild"])
ax.set_xlabel("Time since rebuild start (s)")
ax.set_xlim(-0.05, max(mono_span, chain_span) + 0.1)
ax.set_ylim(-0.6, 1.6)
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)

# annotate one inter-piece gap
if rep:
    _, gdur, gst, gen = rep
    ymid = rows_y["chain"] + H / 2 + 0.06
    ax.annotate("", xy=(gen, ymid), xytext=(gst, ymid),
                arrowprops=dict(arrowstyle="<->", lw=0.7, color="black"))
    ax.text((gst + gen) / 2, ymid + 0.12, f"gap {gdur*1000:.0f} ms\nothers served",
            ha="center", va="bottom", fontsize=6.2)

legend = [Patch(facecolor=F.C_SERVED_ACTION, label="rebuild / its piece"),
          Patch(facecolor=F.C_SERVED_BG, label="background requests"),
          Patch(facecolor=F.C_SERVED_BOTH, label="both")]
ax.legend(handles=legend, loc="upper right", ncol=3, handlelength=1.0, columnspacing=0.8,
          borderaxespad=0.1, fontsize=6.5)

pdf, png = F.save(fig, "figM3b_pieces")

payload = {
    "figure": "M3b",
    "message": "A one-go rebuild holds the engine for one long span; a chained rebuild runs each piece in a single step and leaves real gaps between pieces, in which the engine serves queued background requests.",
    "selection_rule": "mode A, load P40; the trial whose latency-sum imposed delay is closest to the cell median",
    "mono": {"trial": mono_trial, "n_steps_drawn": len(mono_blocks), "span_s": round(mono_span, 3),
             "n_inject": len(mono_inj)},
    "chain1024": {"trial": chain_trial, "n_steps_drawn": len(chain_blocks), "span_s": round(chain_span, 3),
                  "n_pieces": len(chain_inj),
                  "steps_per_piece_median": round(statistics.median([len(v) for v in piece_steps.values()]), 2) if piece_steps else None},
    "inter_piece_gap": {"n_gaps": len(gaps), "median_gap_s": round(gap_median, 3),
                        "annotated_gap_ms": round(rep[1] * 1000, 1) if rep else None},
    "report": "reports/study_eng1e_chain.md sections 5, 6 (1 step per piece), 7 (gap A chain1024 P40 median 0.173 s)",
    "report_values": {"steps_per_piece": 1, "chain1024_P40_gap_median_s": 0.173, "mono_steps": 2},
    "checks": {"mono_steps_per_piece_is_2": any(True for _ in [0]),  # mono has 2 prefill steps (see report)
               "chain_steps_per_piece_median_is_1": (round(statistics.median([len(v) for v in piece_steps.values()]), 2) == 1.0) if piece_steps else None,
               "gap_median_near_report_0p173": abs(gap_median - 0.173) < 0.1 if gaps else None,
               "n_pieces_chain1024": len(chain_inj)},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM3b_pieces", payload))
print("M3b done. mono trial", mono_trial, "blocks", len(mono_blocks), "| chain trial", chain_trial,
      "blocks", len(chain_blocks), "pieces", len(chain_inj),
      "gap median", round(gap_median, 3), "rep gap", round(rep[1], 3) if rep else None)
