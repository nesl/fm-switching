#!/usr/bin/env python3
"""StudyMOT1-dayinlife analysis (CPU only; run after the server is stopped). Amendment 1 runs only (labels A1*).
A 0.5 s bin holds the instants SENT in it (each stream sends one per 2 s); its fraction is missed / sent.

Per repetition, each action run is paired with that repetition's NONE run (same clips, offsets, robot):
  missed instant      submit-to-last-token > 0.916 s, or an error, or no token
  extra missed        missed(action) - missed(NONE), counted over the whole 60 s window
  bins                0.5 s bins of the scheduled send time from the run's t0 (one instant per stream per bin)
  burst length        longest run of consecutive bins in which > 50 % of streams miss (action run)
  burst end           time from the question (t0 + 20 s) to the end of the last bin with any extra miss
                      (bin misses in the action run > bin misses in NONE)
  streams hit         fraction of streams with more misses than in NONE
  robot TTFT          last robot request's first token minus the question time; rebuild time = the same for
                      pieces (the question is answered by the last piece)
Writes results/motivation/mot1/mot1_results.json, mot1_figdata.json and mot1_check.png (PIL).
"""
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

OUT = Path(__file__).resolve().parents[2] / "results/motivation/mot1"
DEADLINE_S, BIN_S, Q_AT_S, WINDOW_S = 0.916, 0.5, 20.0, 60.0
ACTIONS = ("NONE", "ONE-GO", "P2048", "P1024")


def load():
    p = OUT / "mot1_requests.jsonl"
    rows = [json.loads(l) for l in open(p)] if p.exists() else \
        [json.loads(l) for l in __import__("gzip").open(str(p) + ".gz", "rt")]
    runs = defaultdict(list)
    summ = {}
    for r in rows:
        key = (r["label"], r["action"], r["tag"])
        if r.get("kind") == "run_summary":
            summ[key] = r
        else:
            runs[key].append(r)
    return runs, summ


def missed(r):
    return r["error"] is not None or not r.get("t_last") or (r["t_last"] - r["t_submit"]) > DEADLINE_S


def per_run(rows, t0, n):
    mon = [r for r in rows if r["kind"] == "monitor"]
    nb = int(WINDOW_S / BIN_S) + 2
    bins = [[0, 0] for _ in range(nb)]
    per_stream = defaultdict(int)
    for r in mon:
        b = int((r["t_sched"] - t0) // BIN_S)
        bins[b][1] += 1
        if missed(r):
            bins[b][0] += 1
            per_stream[r["stream"]] += 1
    return dict(n_missed=sum(1 for r in mon if missed(r)), n=len(mon), bins=bins, per_stream=dict(per_stream),
                frac_bins=[(m / t if t else 0.0) for m, t in bins])


def analyse(prefix="A1R", actions=ACTIONS):
    runs, summ = load()
    valid = {}
    for key, s in summ.items():
        label, action, tag = key
        if "NSEL" in label or not label.startswith(prefix):    # one design / part only; N-selection runs apart
            continue
        rep = s["rep"]
        # an INVALID control (on-time < 99 %) is superseded by its rerun (label R<r>rerun)
        if action == "NONE" and s["on_time_frac"] < 0.99:
            continue
        valid[(rep, action)] = (key, s)
    reps = sorted({r for r, _ in valid})
    out = dict(per_rep={}, deadline_s=DEADLINE_S, bin_s=BIN_S)
    for rep in reps:
        kN, sN = valid[(rep, "NONE")]
        t0N = sN["t0"]
        base = per_run(runs[kN], t0N, sN["n"])
        row = dict(none=dict(on_time_frac=sN["on_time_frac"], n_missed=base["n_missed"], n=base["n"],
                             frac_bins=base["frac_bins"]))
        for a in actions[1:]:
            if (rep, a) not in valid:
                continue
            k, s = valid[(rep, a)]
            pr = per_run(runs[k], s["t0"], s["n"])
            extra_bins = [max(0, pr["bins"][b][0] - base["bins"][b][0]) for b in range(len(pr["bins"]))]
            longest = cur = 0
            for f in pr["frac_bins"]:
                cur = cur + 1 if f > 0.5 else 0
                longest = max(longest, cur)
            last_extra = max((b for b, e in enumerate(extra_bins) if e > 0), default=None)
            streams = set(range(s["n"]))
            hit = sum(1 for st in streams if pr["per_stream"].get(st, 0) > base["per_stream"].get(st, 0))
            rob = [r for r in runs[k] if r["kind"] == "robot"]
            tq = rob[0]["t_question"] if rob else None
            pieces = [dict(part=r["part_i"], new_frames=r["new_frames"], submit_from_q=round(r["t_submit"] - tq, 4),
                           ttft_s=r["ttft_s"], first_from_q=round(r["t_first"] - tq, 4) if r["t_first"] else None,
                           prompt_tokens=r["prompt_tokens"], cached_tokens=r["cached_tokens"]) for r in rob]
            row[a] = dict(extra_missed=pr["n_missed"] - base["n_missed"], n_missed=pr["n_missed"],
                          burst_bins_gt50=longest, burst_s=longest * BIN_S,
                          burst_end_from_q_s=(round((last_extra + 1) * BIN_S - Q_AT_S, 3) if last_extra is not None else None),
                          frac_streams_hit=round(hit / s["n"], 4),
                          robot_ttft_s=s["robot_ttft_from_q"], robot_first_cached=s["robot_first_cached"],
                          robot_prompt_tokens=(rob[-1]["prompt_tokens"] if rob else None), pieces=pieces,
                          on_time_frac=s["on_time_frac"], frac_bins=pr["frac_bins"], http_errors=s["http_errors"],
                          robot_tier=s.get("robot_tier"), robot_cached_tokens=s.get("robot_cached_tokens"),
                          robot_tier_delta=s.get("robot_tier_delta"))
        out["per_rep"][rep] = row
    summary = {}
    for a in actions[1:]:
        vals = {k: [out["per_rep"][r][a][k] for r in reps if a in out["per_rep"][r]] for k in
                ("extra_missed", "burst_s", "burst_end_from_q_s", "frac_streams_hit", "robot_ttft_s")}
        summary[a] = {k: dict(median=(median([x for x in v if x is not None]) if any(x is not None for x in v) else None),
                              per_rep=v) for k, v in vals.items()}
    out["summary"] = summary
    oneg = [(out["per_rep"][r]["ONE-GO"]["extra_missed"], r) for r in reps if "ONE-GO" in out["per_rep"][r]]
    oneg.sort()
    out["representative_rep"] = oneg[len(oneg) // 2][1] if oneg else None
    return out


def figdata(res, n_sel, N):
    rep = res["representative_rep"]
    pr = res["per_rep"][rep]
    d = dict(label="StudyMOT1-dayinlife figure data (motivation, claim 6)", N=N, n_selection=n_sel,
             deadline_s=DEADLINE_S, bin_s=BIN_S, window_s=WINDOW_S, question_at_s=Q_AT_S, representative_rep=rep,
             representative_rule="the repetition whose ONE-GO extra-miss count is the median of the 5",
             frac_streams_missing_per_bin={a: (pr["none"]["frac_bins"] if a == "NONE" else pr[a]["frac_bins"])
                                           for a in ACTIONS if a == "NONE" or a in pr},
             robot_ttft_s={a: pr[a]["robot_ttft_s"] for a in ACTIONS[1:] if a in pr},
             summary=res["summary"])
    (OUT / "mot1_figdata.json").write_text(json.dumps(d, indent=1) + "\n")
    return d


def plot(fd, name="mot1_check.png"):
    from PIL import Image, ImageDraw
    W, H, m = 1200, 520, 60
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    cols = {"NONE": (120, 120, 120), "ONE-GO": (200, 40, 40), "P2048": (40, 90, 200), "P1024": (30, 150, 60),
            "HOST-WARM": (200, 120, 0)}
    nb = int(WINDOW_S / BIN_S)
    X = lambda b: m + (W - 2 * m) * b / nb
    Y = lambda f: H - m - (H - 2 * m) * f
    dr.rectangle([m, m, W - m, H - m], outline="black")
    qx = X(Q_AT_S / BIN_S)
    dr.line([qx, m, qx, H - m], fill=(0, 0, 0), width=1)
    dr.text((qx + 4, m + 4), "question t=20 s", fill="black")
    for y in (0.0, 0.5, 1.0):
        dr.text((10, Y(y) - 6), f"{y:.1f}", fill="black")
    for i, (a, fr) in enumerate(fd["frac_streams_missing_per_bin"].items()):
        pts = [(X(b), Y(fr[b])) for b in range(min(nb, len(fr)))]
        dr.line(pts, fill=cols[a], width=2)
        dr.text((W - m - 260, m + 8 + 16 * i), f"{a}  robot TTFT {fd['robot_ttft_s'].get(a, '-')}", fill=cols[a])
    dr.text((m, H - m + 20), f"fraction of {fd['N']} dashcam streams missing the 0.916 s deadline per 0.5 s bin "
                             f"(rep {fd['representative_rep']}); x = 0 to 60 s", fill="black")
    im.save(OUT / name)


def main():
    runs_meta = json.loads((OUT / "mot1_runs.json").read_text())
    res = analyse()
    res["n_selection"] = [dict(n=s["n"], on_time_frac=s["on_time_frac"], http_errors=s["http_errors"])
                          for s in runs_meta.get("n_selection", [])]
    res["N"] = runs_meta.get("N")
    res["fill"] = runs_meta.get("fill")
    (OUT / "mot1_results.json").write_text(json.dumps(res, indent=1) + "\n")
    fd = figdata(res, res["n_selection"], res["N"])
    plot(fd)
    for a, v in res["summary"].items():
        print(a, {k: (x["median"], x["per_rep"]) for k, x in v.items()})


ACTIONS5 = ("NONE", "ONE-GO", "P2048", "P1024", "HOST-WARM")


def main_amend2():
    """Amendment 2: Part B (all five actions, roomy host) as amendment 1's analysis; Part A per-run tier and outcome."""
    runs, summ = load()
    meta = json.loads((OUT / "mot1_amend2_runs.json").read_text())
    resB = analyse("A2BR", ACTIONS5)
    a1 = analyse("A1R", ACTIONS)
    ratios = [dict(action=a, measure=k, amend2_B=resB["summary"][a][k]["median"], amend1=a1["summary"][a][k]["median"],
                   ratio=(round(resB["summary"][a][k]["median"] / a1["summary"][a][k]["median"], 4)
                          if resB["summary"][a][k]["median"] and a1["summary"][a][k]["median"] else None))
              for a in ("ONE-GO", "P2048", "P1024") for k in ("extra_missed", "robot_ttft_s", "burst_s")]
    partA = []
    for key, s_ in summ.items():
        if not key[0].startswith("A2AR"):
            continue
        mon = [r for r in runs[key] if r["kind"] == "monitor"]
        nm = sum(1 for r in mon if missed(r))
        partA.append(dict(rep=s_["rep"], predicted_tier="COLD", measured_tier=s_.get("robot_tier"),
                          robot_cached_tokens=s_.get("robot_cached_tokens"), robot_prompt_tokens=s_.get("robot_prompt_tokens"),
                          tier_delta=s_.get("robot_tier_delta"), robot_ttft_s=s_.get("robot_ttft_from_q"), n_missed=nm,
                          on_time_frac=s_["on_time_frac"],
                          extra_missed_vs_amend1_none=(nm - a1["per_rep"][s_["rep"]]["none"]["n_missed"]
                                                       if s_["rep"] in a1["per_rep"] else None),
                          prep=s_.get("prep")))
    partA.sort(key=lambda x: x["rep"])
    hwB = [dict(rep=r, tier=v["HOST-WARM"]["robot_tier"], cached=v["HOST-WARM"]["robot_cached_tokens"],
                delta=v["HOST-WARM"]["robot_tier_delta"]) for r, v in resB["per_rep"].items() if "HOST-WARM" in v]
    out = dict(partB=resB, partA=partA, hostwarm_B_tiers=hwB, amend1_vs_B=ratios,
               fill=dict(A=meta.get("A", {}).get("fill"), B=meta.get("B", {}).get("fill")))
    (OUT / "mot1_amend2_results.json").write_text(json.dumps(out, indent=1) + "\n")
    nonhost = sum(1 for x in hwB if x["tier"] != "HOST")
    if nonhost >= 2:
        print("STOP: Part B HOST-WARM measured non-HOST in", nonhost, "repetitions; no figure data written")
    else:
        rep = resB["representative_rep"]
        pr = resB["per_rep"][rep]
        fd = dict(label="StudyMOT1-dayinlife amendment 2 figure data (Part B, roomy host, all five actions)", N=20,
                  deadline_s=DEADLINE_S, bin_s=BIN_S, window_s=WINDOW_S, question_at_s=Q_AT_S, representative_rep=rep,
                  representative_rule="the Part B repetition whose ONE-GO extra-miss count is the median of the 5",
                  frac_streams_missing_per_bin={a: (pr["none"]["frac_bins"] if a == "NONE" else pr[a]["frac_bins"])
                                                for a in ACTIONS5 if a == "NONE" or a in pr},
                  robot_ttft_s={a: dict(representative=pr[a]["robot_ttft_s"],
                                        per_rep=resB["summary"][a]["robot_ttft_s"]["per_rep"]) for a in ACTIONS5[1:]},
                  summary=resB["summary"], hostwarm_measured_tiers=hwB,
                  partA_tight_host=dict(note="caption block, not a line in the figure: with a 27 GiB host the prepared "
                                             "history's measured tier at the question", runs=[
                      {k: x[k] for k in ("rep", "predicted_tier", "measured_tier", "robot_cached_tokens",
                                         "robot_ttft_s", "n_missed", "extra_missed_vs_amend1_none")} for x in partA]))
        (OUT / "mot1_figdata_amend2.json").write_text(json.dumps(fd, indent=1) + "\n")
        plot(dict(fd, robot_ttft_s={a: v["representative"] for a, v in fd["robot_ttft_s"].items()}),
             "mot1_amend2_check.png")
    for a, v in resB["summary"].items():
        print("B", a, {k: (x["median"], x["per_rep"]) for k, x in v.items()})
    print("A", [(x["rep"], x["measured_tier"], x["robot_cached_tokens"], x["robot_prompt_tokens"], x["robot_ttft_s"],
                 x["n_missed"], x["extra_missed_vs_amend1_none"]) for x in partA])
    print("B host-warm tiers", hwB)
    print("ratios", ratios)


def _mm(v):
    v = [x for x in v if x is not None]
    return dict(median=(median(v) if v else None), min=(min(v) if v else None), max=(max(v) if v else None),
                per_rep=v)


def _cell_from(res, actions, source, measured=True):
    out = {}
    for a in actions:
        reps = [r for r in sorted(res["per_rep"]) if a in res["per_rep"][r]]
        if not reps:
            continue
        rows = [res["per_rep"][r][a] for r in reps]
        out[a] = dict(extra_missed=_mm([x["extra_missed"] for x in rows]),
                      robot_ttft_s=_mm([x["robot_ttft_s"] for x in rows]),
                      measured_tiers=[x.get("robot_tier") for x in rows], reps=reps,
                      source=source, measured_directly=measured)
    return out


def main_amend3():
    """Amendment 3 (light load, N = 8, 27 GiB host, all five actions) and the 2 x 2 grid."""
    runs, summ = load()
    meta = json.loads((OUT / "mot1_amend3_runs.json").read_text())
    r3 = analyse("A3R", ACTIONS5)
    a1 = analyse("A1R", ACTIONS)
    a2 = json.loads((OUT / "mot1_amend2_results.json").read_text())
    resB = a2["partB"]
    # sanity
    a3s = [s for k, s in summ.items() if k[0].startswith("A3R")]
    invalid = [dict(label=s["label"], rep=s["rep"], on_time_frac=s["on_time_frac"]) for s in a3s
               if s["action"] == "NONE" and s["on_time_frac"] < 0.99]
    cold_first = [dict(rep=s["rep"], action=s["action"], first_cached=s.get("robot_first_cached")) for s in a3s
                  if s["action"] in ("ONE-GO", "P2048", "P1024")]
    sanity = dict(none_on_time=[(s["rep"], s["on_time_frac"]) for s in a3s if s["action"] == "NONE"],
                  invalid_controls=invalid, http_errors=sum(s["http_errors"] for s in a3s),
                  cold_first_cached_max=max((x["first_cached"] or 0) for x in cold_first) if cold_first else None,
                  cold_first_cached_le16=all((x["first_cached"] or 0) <= 16 for x in cold_first),
                  n_runs=len(a3s))
    hw = [dict(rep=r, predicted_tier="HOST", measured_tier=v["HOST-WARM"]["robot_tier"],
               cached=v["HOST-WARM"]["robot_cached_tokens"], prompt=v["HOST-WARM"]["robot_prompt_tokens"],
               delta=v["HOST-WARM"]["robot_tier_delta"], robot_ttft_s=v["HOST-WARM"]["robot_ttft_s"],
               extra_missed=v["HOST-WARM"]["extra_missed"])
          for r, v in sorted(r3["per_rep"].items()) if "HOST-WARM" in v]
    preps = [dict(rep=s["rep"], prep=s.get("prep")) for s in a3s if s["action"] == "HOST-WARM"]
    n_host = sum(1 for x in hw if x["measured_tier"] == "HOST")
    cold = ("ONE-GO", "P2048", "P1024")
    ratios = [dict(action=a, measure=k, light=r3["summary"][a][k]["median"], heavy_amend1=a1["summary"][a][k]["median"],
                   ratio=(round(r3["summary"][a][k]["median"] / a1["summary"][a][k]["median"], 4)
                          if r3["summary"][a][k]["median"] and a1["summary"][a][k]["median"] else None))
              for a in cold for k in ("extra_missed", "robot_ttft_s", "burst_s")]
    # the 2 x 2 grid
    light_tight = _cell_from(r3, ACTIONS5[1:], "amendment 3 (N = 8, 27 GiB)")
    heavy_tight = _cell_from(a1, ACTIONS[1:], "amendment 1 (N = 20, 27 GiB), cold actions")
    pa = a2["partA"]
    heavy_tight["HOST-WARM"] = dict(
        extra_missed=_mm([x["extra_missed_vs_amend1_none"] for x in pa]),
        robot_ttft_s=_mm([x["robot_ttft_s"] for x in pa]),
        measured_tiers=[x["measured_tier"] for x in pa], reps=[x["rep"] for x in pa],
        source="amendment 2 Part A (N = 20, 27 GiB), HOST-WARM only; extra misses vs amendment 1's NONE of the "
               "same repetition (another server instance: a cross-run reference, not a paired difference)",
        measured_directly=True)
    heavy_roomy = _cell_from(resB, ACTIONS5[1:], "amendment 2 Part B (N = 20, 256 GiB)")
    light_roomy = {a: dict(v, source="BORROWED from amendment 3's light/tight cold action: host size does not change "
                                     "cold actions (StudyENG1c Part E; amendment 2's 1.01x to 1.17x check)",
                           measured_directly=False)
                   for a, v in _cell_from(r3, cold, "").items()}
    if n_host == len(hw) and hw:
        light_roomy["HOST-WARM"] = dict(light_tight["HOST-WARM"], measured_directly=False,
                                        source="BORROWED from amendment 3's light/tight HOST-WARM, which measured HOST in "
                                               "every repetition: a roomier host can only keep the history at least as "
                                               "warm")
    else:
        light_roomy["HOST-WARM"] = dict(status="not measured", measured_directly=False,
                                        source=f"amendment 3's light/tight HOST-WARM measured HOST in {n_host} of "
                                               f"{len(hw)} repetitions, so it is not borrowed")
    grid = dict(note="rows: load (light N = 8, 4 requests/s; heavy N = 20, 10 requests/s); columns: host tier "
                     "(tight 27 GiB; roomy 256 GiB). Values per action: extra missed dashcam instants vs the paired "
                     "NONE and robot TTFT from the question, median with min and max over 5 repetitions.",
                light_tight=light_tight, heavy_tight=heavy_tight, heavy_roomy=heavy_roomy, light_roomy=light_roomy,
                measured_directly=dict(light_tight="all actions", heavy_tight="all actions (two amendments)",
                                       heavy_roomy="all actions",
                                       light_roomy="none: cold actions borrowed; HOST-WARM borrowed only if light/"
                                                   "tight measured HOST in every repetition"))
    out = dict(amend3=r3, sanity=sanity, hostwarm=hw, hostwarm_preps=preps, light_vs_heavy=ratios,
               fill=meta.get("fill"), checkout=meta.get("checkout"), stop=meta.get("stop"))
    (OUT / "mot1_amend3_results.json").write_text(json.dumps(out, indent=1) + "\n")
    rep = r3["representative_rep"]
    pr = r3["per_rep"][rep]
    fd = dict(label="StudyMOT1-dayinlife amendment 3 figure data (light load, N = 8, 27 GiB host, five actions)",
              N=8, host_gib=27, deadline_s=DEADLINE_S, bin_s=BIN_S, window_s=WINDOW_S, question_at_s=Q_AT_S,
              representative_rep=rep,
              representative_rule="the repetition whose ONE-GO extra-miss count is the median of the 5",
              per_action={a: dict(extra_missed=light_tight[a]["extra_missed"], robot_ttft_s=light_tight[a]["robot_ttft_s"],
                                  measured_tiers=light_tight[a]["measured_tiers"]) for a in light_tight},
              frac_streams_missing_per_bin={a: (pr["none"]["frac_bins"] if a == "NONE" else pr[a]["frac_bins"])
                                            for a in ACTIONS5 if a == "NONE" or a in pr},
              summary=r3["summary"], hostwarm_measured=hw, grid_2x2=grid)
    (OUT / "mot1_figdata_amend3.json").write_text(json.dumps(fd, indent=1) + "\n")
    plot(dict(fd, robot_ttft_s={a: pr[a]["robot_ttft_s"] for a in ACTIONS5[1:] if a in pr}), "mot1_amend3_check.png")
    print("sanity", sanity)
    for a, v in r3["summary"].items():
        print("A3", a, {k: (x["median"], x["per_rep"]) for k, x in v.items()})
    print("hostwarm", hw)
    print("light vs heavy", ratios)


if __name__ == "__main__":
    import sys
    w = sys.argv[1] if len(sys.argv) > 1 else ""
    main_amend2() if w == "amend2" else (main_amend3() if w == "amend3" else main())
