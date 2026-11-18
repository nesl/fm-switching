#!/usr/bin/env python3
"""StudyENG1e-chain analysis (CPU only; run with no server up). Reads the runner's rows, the ENG1 plugin rows and the
add-on's per-step membership rows (schema in experiments/cost/eng1e_steplog/eng1e_steplog.py and the report).
HOLDOUT pairs are dropped before anything is computed (recorded, not analysed). Modes B and A are never pooled.

Step timing (engine side): end = t0 + el (the moment the step's output was ready); start = max(ts, end of the previous
step), ts = the execute_model dispatch; duration = end - start. (With async scheduling execute_model can block on the CPU
side, e.g. multimodal input preparation and the vision encoder, before the timed wait starts, so el alone understates
such steps.)
Per FIT with-run (engine clock = the add-on's step times; client clock = the harness's time.time(); same host):
  piece k: submit (client), first scheduled step start F_k, last prefill step end L_k, client first token / end;
           front-end window FE_k = F_k - submit_k
  gap k (k < n): [L_k, F_{k+1}); includes piece k+1's client turnaround and front-end window
  chain end C = L_n (last piece's last prefill step end, i.e. its first token)
  bins of a background arrival a (client submit): pre_inj a < job start; pre_fe a < F_1; piece k F_k <= a < L_k;
       gap k L_k <= a < F_{k+1}; post a >= C
  during-chain arrivals: pre_fe, piece k and gap k with k < n
  first service of a background request: its first scheduled step, classified as piece step (a piece is in it),
       gap step (start inside a gap, no piece), after (start >= C) or other (before F_1)
  delta = TTFT(with) - TTFT(without) per background request (matched by index); latency delta likewise
  rho_b_chain = delta / (C - a); rho_b_piece = delta / (L_k - a) for arrivals in piece k
  other-token share of a piece step = tokens of non-piece requests / all tokens in the step
  chain occupancy = sum of piece-step durations / (C - F_1)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from study_eng1d_analyse import jl, cluster_ci, stats, machine_flags  # noqa: E402  (ENG1d helpers, unchanged)

REPO = HERE.parents[1]
OUT = REPO / "results/cost/study_eng1e"
MODES = ("B", "A")
LOADS = ("P25", "P40", "S2", "S4")
ACTIONS = ("mono", "chain2048", "chain1024")
RNG = np.random.default_rng(20261123)
XB = {"P25": (3.6525, 22.7125), "S2": (8.52, 16.6125)}
XA = {"P25": (4.6877, 37.6188), "P40": (24.0905, 89.4948), "S2": (14.2562, 27.8415), "S4": (47.8769, 95.5613)}


def short(eid):
    return eid[len("chatcmpl-"):-9] if eid.startswith("chatcmpl-") else eid


class StepLog:
    """Add-on rows of one server: steps sorted by start; per client rid the list of (step index, phase, tokens)."""

    def __init__(self, path):
        rows = [r for r in jl(path) if "r" in r]
        rows.sort(key=lambda r: r["i"])
        end = np.array([r["t0"] + r["el"] / 1000.0 for r in rows])
        start = np.empty_like(end)
        for k, r in enumerate(rows):
            disp = r.get("ts") if r.get("ts") is not None else r["t0"]
            start[k] = max(disp, end[k - 1]) if k else disp
            start[k] = min(start[k], end[k])
        self.t0 = start                       # step start: max(dispatch, previous step end)
        self.end = end                        # step end: wait start + elapsed (output ready)
        self.el = end - start                 # step duration
        self.rows = rows
        self.by = defaultdict(list)
        for k, r in enumerate(rows):
            for eid, n, ph, c0, ne in r["r"]:
                self.by[short(eid)].append((k, ph, n, ne))

    def window(self, a, b):
        i, j = np.searchsorted(self.t0, a), np.searchsorted(self.t0, b)
        return range(i, j)


def piece_timing(sl, inj):
    out = []
    for r in sorted(inj, key=lambda x: x["part_i"]):
        st = sl.by.get(r["rid"], [])
        pf = [k for k, ph, n, ne in st if ph == "p"]
        if not pf:
            return None
        F = float(sl.t0[pf[0]])
        # engine idle before this request was submitted: time from the end of the last step before its submit to the
        # submit (0 if a step was running); user ruling: report requests starting after idle (>= 0.5 s) separately
        j = int(np.searchsorted(sl.end, r["t_submit"])) - 1
        running = j + 1 < len(sl.t0) and sl.t0[j + 1] <= r["t_submit"]
        idle_before = 0.0 if running or j < 0 else float(r["t_submit"] - sl.end[j])
        L = float(sl.end[pf[-1]])
        out.append(dict(rid=r["rid"], k=r["part_i"], submit=r["t_submit"], F=F, L=L, fe=F - r["t_submit"],
                        steps=pf, n_steps=len(pf), enc=sum(ne for _, _, _, ne in st), new_frames=r.get("new_frames"),
                        tokens=sum(n for _, ph, n, _ in st if ph == "p"), prompt=r["prompt_tokens"],
                        cached=r["cached_tokens"], t_first=r["t_first"], t_end=r["t_end"], ttft=r["ttft_s"],
                        idle_before=idle_before, after_idle=idle_before >= 0.5))
    return out


def binof(a, job_start, pcs):
    if a < job_start:
        return "pre_inj", None
    if a < pcs[0]["F"]:
        return "pre_fe", 0
    for k, p in enumerate(pcs):
        if p["F"] <= a < p["L"]:
            return "piece", k
        if k + 1 < len(pcs) and p["L"] <= a < pcs[k + 1]["F"]:
            return "gap", k
    return "post", None


def analyse_run(w, wo, sl, mach):
    """One FIT pair. Returns (trial row, request rows, gap rows, piece-step rows)."""
    inj = [r for r in w if r.get("kind") == "inject"]
    job = next(r for r in w if r.get("kind") == "job")
    pcs = piece_timing(sl, inj)
    if pcs is None:
        return None
    n = len(pcs)
    C = pcs[-1]["L"]
    piece_steps = set(k for p in pcs for k in p["steps"])
    piece_rids = {p["rid"] for p in pcs}
    gaps = [(pcs[k]["L"], pcs[k + 1]["F"]) for k in range(n - 1)]
    # gap rows
    grows = []
    for k, (g0, g1) in enumerate(gaps):
        idx = [i for i in sl.window(g0 - 0.002, g1) if i not in piece_steps]
        reqs = defaultdict(lambda: [0, 0])
        for i in idx:
            for eid, nt, ph, c0, ne in sl.rows[i]["r"]:
                rid = short(eid)
                if rid not in piece_rids:
                    reqs[rid][0 if ph == "p" else 1] += nt
        grows.append(dict(k=k, dur=g1 - g0, fe_next=pcs[k + 1]["fe"], turnaround=pcs[k + 1]["submit"] - pcs[k]["L"],
                          n_steps=len(idx), n_req=len(reqs), n_req_prefill=sum(1 for v in reqs.values() if v[0]),
                          prefill_tok=sum(v[0] for v in reqs.values()), decode_tok=sum(v[1] for v in reqs.values()),
                          busy=float(sum(sl.el[i] for i in idx))))
    # piece-step composition
    srows = []
    for k in sorted(piece_steps):
        rr = sl.rows[k]["r"]
        tot = sum(x[1] for x in rr)
        oth = sum(x[1] for x in rr if short(x[0]) not in piece_rids)
        oth_p = sum(x[1] for x in rr if short(x[0]) not in piece_rids and x[2] == "p")
        srows.append(dict(tok=tot, other=oth, other_prefill=oth_p, share=oth / tot if tot else 0.0,
                          n_other=sum(1 for x in rr if short(x[0]) not in piece_rids), el=float(sl.el[k])))
    busy = float(sum(sl.el[k] for k in piece_steps))
    # background requests
    ew = {r["idx"]: r for r in w if r.get("kind") == "episodic"}
    eo = {r["idx"]: r for r in wo if r.get("kind") == "episodic"}
    req = []
    for i, r in ew.items():
        o = eo.get(i)
        if not o or r.get("ttft_s") is None or o.get("ttft_s") is None or r.get("error") or o.get("error"):
            continue
        a = r["t_submit"]
        b, k = binof(a, job["t_start"], pcs)
        st = sl.by.get(r["rid"], [])
        first = st[0][0] if st else None
        if first is None:
            fs = None
        elif first in piece_steps:
            fs = "piece"
        elif float(sl.t0[first]) >= C - 0.002:
            fs = "after"
        elif any(g0 - 0.002 <= sl.t0[first] < g1 for g0, g1 in gaps):
            fs = "gap"
        else:
            fs = "other"
        d = r["ttft_s"] - o["ttft_s"]
        dl = r["latency_s"] - o["latency_s"]
        during = b in ("pre_fe", "gap") or (b == "piece" and k < n - 1)
        req.append(dict(idx=i, bin=b, k=k, during=during, delta=d, delta_lat=dl, first=fs,
                        rho_chain=d / (C - a) if C - a > 0.02 and b != "pre_inj" and b != "post" else None,
                        rho_piece=d / (pcs[k]["L"] - a) if b == "piece" and pcs[k]["L"] - a > 0.02 else None))
    t0, t1 = min(x["t_submit"] for x in w if "t_submit" in x), max(x["t_end"] for x in w if "t_end" in x)
    trow = dict(n_pieces=n, chain_span=C - pcs[0]["F"], occupancy=busy / (C - pcs[0]["F"]) if C > pcs[0]["F"] else None,
                fe=[p["fe"] for p in pcs], job_completion=job["job_completion_s"], piece_steps=len(piece_steps),
                imposed_lat=sum(x["delta_lat"] for x in req), imposed_ttft=sum(x["delta"] for x in req),
                enc_ok=all((p["enc"] or 0) >= (p["new_frames"] or 0) for p in pcs),
                first_cold=(pcs[0]["cached"] or 0) <= 16, first_ttft=pcs[0]["ttft"],
                first_idle_before=pcs[0]["idle_before"], n_after_idle=sum(p["after_idle"] for p in pcs),
                later_ttft=[p["ttft"] for p in pcs[1:]], **machine_flags(mach, t0, t1))
    return trow, req, grows, srows


def med_ci_diff(a_by_trial, b_by_trial, n=2000):
    """Difference of pooled medians (a - b), trial-cluster bootstrap within each group."""
    ka, kb = list(a_by_trial), list(b_by_trial)
    if len(ka) < 3 or len(kb) < 3:
        return None, None
    pt = float(np.median([x for k in ka for x in a_by_trial[k]]) - np.median([x for k in kb for x in b_by_trial[k]]))
    bs = []
    for _ in range(n):
        pa = RNG.choice(len(ka), len(ka))
        pb = RNG.choice(len(kb), len(kb))
        va = [x for i in pa for x in a_by_trial[ka[i]]]
        vb = [x for i in pb for x in b_by_trial[kb[i]]]
        if va and vb:
            bs.append(np.median(va) - np.median(vb))
    return round(pt, 4), [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]


def summarise(cells, flag_filter=None):
    out = {}
    for key, c in cells.items():
        T = [(t, tr) for t, tr in c["trials"] if flag_filter is None or flag_filter(tr)]
        keep = {t for t, _ in T}
        R = [(t, x) for t, x in c["req"] if t in keep]
        G = [(t, x) for t, x in c["gaps"] if t in keep]
        S = [(t, x) for t, x in c["steps"] if t in keep]
        dur = [x for _, x in R if x["during"]]
        imp_l = sum(x["delta_lat"] for _, x in R)
        by_bin = {}
        for bname in ("pre_inj", "pre_fe", "piece", "gap", "post"):
            v = [x for _, x in R if x["bin"] == bname]
            by_bin[bname] = dict(n=len(v), lat_sum=round(sum(x["delta_lat"] for x in v), 3),
                                 ttft_sum=round(sum(x["delta"] for x in v), 3),
                                 share_lat=round(sum(x["delta_lat"] for x in v) / imp_l, 4) if imp_l else None,
                                 per_trial_lat=round(sum(x["delta_lat"] for x in v) / max(1, len(T)), 4))
        first = defaultdict(int)
        for x in dur:
            first[x["first"]] += 1
        nd = len(dur)
        o = dict(n_trials=len(T), n_requests=len(R), n_during=nd,
                 total_imposed_lat_s=stats([tr["imposed_lat"] for _, tr in T]),
                 total_imposed_ttft_s=stats([tr["imposed_ttft"] for _, tr in T]),
                 by_bin=by_bin,
                 first_service_of_during=dict(first), frac_first_gap=round(first["gap"] / nd, 4) if nd else None,
                 frac_first_piece=round(first["piece"] / nd, 4) if nd else None,
                 frac_first_after=round(first["after"] / nd, 4) if nd else None,
                 rho_b_chain=dict(stats([x["rho_chain"] for x in dur]),
                                  ci95_cluster=cluster_ci([(t, x["rho_chain"]) for t, x in R if x["during"]])),
                 rho_b_piece=stats([x["rho_piece"] for _, x in R if x["rho_piece"] is not None]),
                 gaps=dict(n=len(G), frac_serving=round(sum(1 for _, g in G if g["n_req"] > 0) / len(G), 4) if G else None,
                           dur_s=stats([g["dur"] for _, g in G]), fe_next_s=stats([g["fe_next"] for _, g in G]),
                           turnaround_s=stats([g["turnaround"] for _, g in G]), n_req=stats([g["n_req"] for _, g in G]),
                           prefill_tok=stats([g["prefill_tok"] for _, g in G]),
                           decode_tok=stats([g["decode_tok"] for _, g in G]), busy_s=stats([g["busy"] for _, g in G])),
                 piece_steps=dict(n=len(S), other_share=stats([s["share"] for _, s in S]),
                                  frac_with_other=round(sum(1 for _, s in S if s["other"] > 0) / len(S), 4) if S else None,
                                  frac_with_other_prefill=round(sum(1 for _, s in S if s["other_prefill"] > 0) / len(S), 4)
                                  if S else None, el_ms=stats([s["el"] * 1000 for _, s in S])),
                 occupancy=stats([tr["occupancy"] for _, tr in T]), chain_span_s=stats([tr["chain_span"] for _, tr in T]),
                 fe_first_s=stats([tr["fe"][0] for _, tr in T]),
                 fe_later_s=stats([f for _, tr in T for f in tr["fe"][1:]]),
                 job_completion_s=stats([tr["job_completion"] for _, tr in T]),
                 first_piece_ttft_s=stats([tr["first_ttft"] for _, tr in T]),
                 first_piece_idle_before_s=stats([tr["first_idle_before"] for _, tr in T]),
                 first_piece_after_idle=sum(tr["first_idle_before"] >= 0.5 for _, tr in T),
                 action_requests_after_idle=sum(tr["n_after_idle"] for _, tr in T),
                 later_piece_ttft_s=stats([x for _, tr in T for x in tr["later_ttft"]]),
                 noise_abs_lat_s=stats([abs(v) for v in c["noise_lat"]]), noise_lat_s=c["noise_lat"],
                 noise_ttft_s=c["noise_ttft"],
                 enc_ok=sum(tr["enc_ok"] for _, tr in T), first_cold=sum(tr["first_cold"] for _, tr in T),
                 flagged_gpu=sum(tr["other_gpu"] for _, tr in T), flagged_cpu=sum(tr["cpu_high"] for _, tr in T),
                 cpu_mean_max=max((tr["cpu_mean"] or 0) for _, tr in T) if T else None)
        o["_S_by_trial"] = defaultdict(list)
        for t, s in S:
            o["_S_by_trial"][t].append(s["share"])
        out[key] = o
    # verdicts
    for key, o in out.items():
        mode, load, act = key.split("|")
        mono = out.get(f"{mode}|{load}|mono")
        if act == "mono" or mono is None:
            o["verdict"] = None
            continue
        g = o["gaps"]
        rc = o["rho_b_chain"].get("median")
        fg, fp = o["frac_first_gap"], o["frac_first_piece"]
        if g["frac_serving"] is not None and g["frac_serving"] >= 0.5 and fg is not None and fg >= 0.30 and \
                rc is not None and rc <= 0.6:
            hg = "SUPPORTED"
        elif fg is not None and fg < 0.10 and rc is not None and rc >= 0.8:
            hg = "REJECTED"
        else:
            hg = "PARTIAL"
        diff, ci = med_ci_diff(o["_S_by_trial"], mono["_S_by_trial"])
        if diff is not None and diff >= 0.10 and ci[0] > 0 and fp is not None and fp >= 0.25:
            hm = "SUPPORTED"
        elif (diff is None or diff < 0.05 or ci[0] <= 0 <= ci[1]) and (fp is None or fp < 0.10):
            hm = "REJECTED"
        else:
            hm = "PARTIAL"
        o["verdict"] = dict(H_gap=hg, H_merge=hm, gap_frac_serving=g["frac_serving"], frac_first_gap=fg,
                            rho_b_chain_median=rc, frac_first_piece=fp, other_share_minus_mono=diff,
                            other_share_diff_ci95=ci, chain_over_mono_imposed_lat=(
                                round(o["total_imposed_lat_s"]["median"] / mono["total_imposed_lat_s"]["median"], 4)
                                if o["total_imposed_lat_s"].get("median") and mono["total_imposed_lat_s"].get("median")
                                else None))
    for o in out.values():
        o.pop("_S_by_trial", None)
    return out


def load_all(pre):
    rows = jl(OUT / f"{pre}_requests_h100nvl.jsonl")
    mach = [m for m in jl(OUT / f"{pre}_machine_h100nvl.jsonl") if "gpus" in m]
    runs = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if "pair" in r and "arm" in r and r.get("kind") not in ("pair_check",):
            runs[r["pair"]][r["arm"]].append(r)
    pcs = [r for r in rows if r.get("kind") == "pair_check"]
    return rows, runs, pcs, mach


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    pre = "eng1e_smoke" if a.smoke else "eng1e"
    rows, runs, pcs, mach = load_all(pre)
    logs = {}
    cells = defaultdict(lambda: dict(trials=[], req=[], gaps=[], steps=[], noise_lat=[], noise_ttft=[]))
    n_hold = defaultdict(int)
    bad = []
    for pc in pcs:
        key = f"{pc['mode']}|{pc['load']}|{pc['action']}"
        if pc["holdout"]:
            n_hold[key] += 1
            continue                                      # HOLDOUT: recorded, not analysed
        rr = runs[pc["pair"]]
        w, wo = rr["with"], rr["without"]
        srv = next(r["server"] for r in w if r.get("kind") == "run_summary")
        if srv not in logs:
            logs[srv] = StepLog(OUT / f"{pre}_steps_{srv}.jsonl.gz")
        res = analyse_run(w, wo, logs[srv], mach)
        if res is None:
            bad.append(pc["pair"])
            continue
        trow, req, grows, srows = res
        t = pc["trial"]
        c = cells[key]
        c["trials"].append((t, trow))
        c["req"] += [(t, x) for x in req]
        c["gaps"] += [(t, x) for x in grows]
        c["steps"] += [(t, x) for x in srows]
        if rr.get("repeat"):
            from study_eng1e_chain import imposed  # noqa: E402  (pure function; no server code runs on import)
            c["noise_lat"].append(round(imposed(rr["repeat"], wo, "latency_s"), 4))
            c["noise_ttft"].append(round(imposed(rr["repeat"], wo), 4))
    res = dict(addon_gate="add-on failed unloaded overhead gate; passed at P40", holdout_recorded=dict(n_hold),
               unanalysable_pairs=bad,
               pair_check=dict(mismatches=sum(p["mismatches"] for p in pcs), compared=sum(p["n"] for p in pcs),
                               enc_check_fail=sum(1 for p in pcs if p.get("enc_check") and not p["enc_check"]["ok"])),
               cells_all=summarise(cells), cells_unflagged=summarise(cells, lambda tr: not tr["other_gpu"]),
               cells_cpu_ok=summarise(cells, lambda tr: not tr["cpu_high"]))
    # mono cross-checks (TTFT sum, FIT)
    xc = {}
    for mode, ref, src in (("B", XB, "ENG1c Part D 38 GiB cold mono FIT (gate)"), ("A", XA, "ENG1d mono11k FIT (gate)")):
        for load in LOADS:
            o = res["cells_all"].get(f"{mode}|{load}|mono")
            if not o:
                continue
            med = o["total_imposed_ttft_s"].get("median")
            row = dict(median_ttft_sum=med, gated=load in ref)
            if load in ref:
                row.update(band=ref[load], passed=ref[load][0] <= med <= ref[load][1], ref=src)
            if mode == "B":
                row["eng1d_band_ungated"] = XA[load]
                row["eng1d_inside"] = XA[load][0] <= med <= XA[load][1]
            xc[f"{mode}|{load}"] = row
    res["mono_crosscheck"] = xc
    (OUT / f"{pre}_results.json").write_text(json.dumps(res, indent=1, default=float))
    for k, o in sorted(res["cells_all"].items()):
        v = o.get("verdict") or {}
        print(k, o["n_trials"], "lat", o["total_imposed_lat_s"].get("median"), "ttft", o["total_imposed_ttft_s"].get("median"),
              "gapserve", o["gaps"]["frac_serving"], "fg", o["frac_first_gap"], "fp", o["frac_first_piece"],
              "rho_c", o["rho_b_chain"].get("median"), "share", o["piece_steps"]["other_share"].get("median"),
              "fe_later", o["fe_later_s"].get("median"), v.get("H_gap"), v.get("H_merge"))


if __name__ == "__main__":
    main()
