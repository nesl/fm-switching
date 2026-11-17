#!/usr/bin/env python3
"""StudyENG1d-loadedblock analysis (CPU only; run only when no server is up). Reads results/cost/study_eng1d/eng1d[_smoke]_*
and writes eng1d[_smoke]_results.json. With --replicate-eng1 also analyses StudyENG1 Part C FIT pairs (HOLDOUT rows
are dropped before anything is computed) and writes eng1d_eng1_replication.json.

Action timing (engine): the action's last prefill step = the last step row with t <= the action's client first-token
time; its row time is the action's prefill end; its first scheduled time = that client first-token time - the plugin's
prefill time (scheduled -> first token). Action steps = step rows ('it') with t in (scheduled, last row].
Step composition (DERIVED): per action step, other-request prefill tokens = the step row's first-output computed tokens
('pts'[0]) minus the action's computed tokens on its last step; action tokens = step context tokens - other.
Conservation: sum of derived action tokens vs action computed tokens (prompt - cached), tolerance 64 (also 512).
Per background request (with-arm, FIT): delta = TTFT(with) - TTFT(without) matched by index; arrival = client submit;
offset = (arrival - scheduled) / (prefill end - scheduled); bins pre_inj (before the action's submission),
pre_fe (between submission and scheduling: the action's front-end work), 0-25, 25-50, 50-75, 75-100, post (>= 1).
rho_pol4 (StudyPOL4-engine Part 1b section 2A.6) = delta / (action first token - arrival) for arrivals between the
action's submission and first token; reported for reconciliation only. Verdict CIs: bootstrap over trials.
rho_b (PRIMARY) = delta / (prefill end - arrival); rho_a (SECONDARY) = delta / (remaining action tokens at arrival x
unloaded per-token time), remaining = derived action tokens of later steps plus the in-progress step prorated by the
time left in it.
Queue at arrival: client in-flight requests of the same run (submitted, no first token yet; the action included) and
the plugin's waiting count at the next step boundary after the arrival; excess = delta - R_b. Steps waited = step rows in (submit, first token].
Verdict per load x action: rho_b over offsets 25 to 75 %: median >= 0.8 H1; median <= 0.6 and >= 50 % of action steps
carry other work (other prefill tokens or decodes) H2; else PARTIAL.
Flags: a trial (with-arm setup to end) is flagged if any GPU other than GPU 2 had utilization > 5 % in a machine
sample in its window, or the mean host CPU utilization in its window exceeded 80 %.
"""
import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/cost/study_eng1d"
ENG1 = REPO / "results/cost/study_eng1"
LOADS = ("P25", "P40", "S2", "S4")
ACTIONS = ("mono11k", "piece2048", "piece1024")
BINS = ("pre_inj", "pre_fe", "0-25", "25-50", "50-75", "75-100", "post")
QBINS = ((0, 0, "0"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 10, "6-10"), (11, 10 ** 6, ">10"))
TOL, TOL2 = 64, 512
ENG1_C_FIT = {("P25", "piece1024"): 0.10, ("P25", "piece2048"): 0.49, ("P25", "mono11k"): 16.2,
              ("P40", "piece1024"): 0.39, ("P40", "piece2048"): 0.91, ("P40", "mono11k"): 32.9,
              ("S2", "piece1024"): 0.08, ("S2", "piece2048"): 0.62, ("S2", "mono11k"): 19.0,
              ("S4", "piece1024"): 0.40, ("S4", "piece2048"): 2.57, ("S4", "mono11k"): 71.2}
RNG = np.random.default_rng(20261117)


def jl(p):
    if not Path(p).exists():
        return []
    op = gzip.open if str(p).endswith(".gz") else open
    with op(p, "rt") as f:
        return [json.loads(l) for l in f if l.strip()]


def cluster_ci(pairs, n=2000):
    """pairs: [(trial, value)]; bootstrap over TRIALS (arrivals within a trial are not independent)."""
    by = defaultdict(list)
    for t, x in pairs:
        if x is not None and np.isfinite(x):
            by[t].append(x)
    keys = list(by)
    if len(keys) < 5:
        return None
    meds = []
    for _ in range(n):
        pick = RNG.choice(len(keys), size=len(keys), replace=True)
        meds.append(np.median([x for i in pick for x in by[keys[i]]]))
    return [round(float(np.percentile(meds, 2.5)), 4), round(float(np.percentile(meds, 97.5)), 4)]


def ols(x, y):
    x, y = np.array(x, float), np.array(y, float)
    if len(x) < 5 or np.ptp(x) == 0:
        return None
    A = np.vstack([np.ones_like(x), x]).T
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ c
    r2 = 1 - (res ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return dict(intercept_s=round(float(c[0]), 4), slope_s_per_req=round(float(c[1]), 5), r2=round(float(r2), 3), n=len(x))


def stats(v):
    v = [x for x in v if x is not None and np.isfinite(x)]
    if not v:
        return dict(n=0)
    a = np.array(v)
    out = dict(n=len(v), median=round(float(np.median(a)), 4), p10=round(float(np.percentile(a, 10)), 4),
               p90=round(float(np.percentile(a, 90)), 4), min=round(float(a.min()), 4), max=round(float(a.max()), 4))
    if len(v) >= 5:
        bs = np.median(RNG.choice(a, size=(2000, len(a)), replace=True), axis=1)
        out["ci95"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
    return out


class Steps:
    def __init__(self, path):
        rows = jl(path)
        self.rows = [r for r in rows if "it" in r]
        self.all = rows
        self.t = np.array([r["t"] for r in self.rows])
        self.allt = np.array([r["t"] for r in rows])
        self.fin = {}
        for r in rows:
            for f in r.get("fin", []):
                self.fin[f["id"]] = f

    def window(self, t0, t1):
        i0, i1 = np.searchsorted(self.t, t0, "right"), np.searchsorted(self.t, t1, "right")
        return list(range(i0, i1))

    def last_le(self, t):
        return int(np.searchsorted(self.t, t, "right")) - 1

    def wait_next(self, t):
        """Engine waiting count at the first output batch after t (rows exist only at step ends, so the row before
        an arrival inside a long step is stale; this is the queue seen at the next step boundary)."""
        i = int(np.searchsorted(self.allt, t, "right"))
        return self.all[i].get("wait") if i < len(self.all) else None

    def dur(self, i):
        return round(float(self.t[i] - self.t[i - 1]), 5) if i > 0 else None


def action_timing(st, inj):
    """Engine timing and DERIVED step composition of one injected action."""
    f = st.fin.get("chatcmpl-" + inj["rid"])
    if f is None or inj.get("t_first") is None:
        return None
    comp = (inj["prompt_tokens"] or 0) - (inj["cached_tokens"] or 0)
    last = st.last_le(inj["t_first"] + 0.002)
    t_end = float(st.t[last])
    t_sched = inj["t_first"] - f["pf"]
    idx = [i for i in st.window(t_sched, t_end)]
    steps = []
    for i in idx:
        r = st.rows[i]
        it = r["it"]
        first_out = (r.get("pts") or [0])[0]
        other = first_out - (comp if i == last else 0)
        d = st.dur(i)
        if i == idx[0] and d is not None:        # an idle engine before the action: the step starts at scheduling
            d = round(min(d, r["t"] - t_sched), 5)
        steps.append(dict(i=i, t=r["t"], dur_s=d, ctx_req=it[1], ctx_tok=it[2], dec_req=it[3],
                          other_prefill=other, action_tok=it[2] - other, images=it[6], wait=r.get("wait")))
    tot = sum(s["action_tok"] for s in steps)
    return dict(t_sched=t_sched, t_end=t_end, pf=f["pf"], q=f["q"], comp=comp, steps=steps, n_steps=len(steps),
                derived_total=tot, cons_err=tot - comp, cons_ok=abs(tot - comp) <= TOL, cons_ok512=abs(tot - comp) <= TOL2)


def rem_tokens(steps, a):
    """Action prefill tokens remaining at time a: later steps in full, the in-progress step prorated by the time left
    in it (step k spans (t_k - dur_k, t_k])."""
    rem = 0.0
    for s_ in steps:
        if s_["t"] <= a:
            continue
        d = s_["dur_s"] or 0.0
        start = s_["t"] - d
        frac = 1.0 if a <= start or d <= 0 else (s_["t"] - a) / d
        rem += frac * s_["action_tok"]
    return rem


def binof(off, a=None, t_inj=None):
    if off < 0:
        return "pre_inj" if t_inj is not None and a < t_inj else "pre_fe"
    if off >= 1:
        return "post"
    return BINS[2 + min(3, int(off * 4))]


def qbin(n):
    return next(lbl for lo, hi, lbl in QBINS if lo <= n <= hi)


def machine_flags(mach, t0, t1):
    s = [m for m in mach if t0 <= m["t"] <= t1 and "gpus" in m]
    if not s:                                   # nearest sample
        near = min((m for m in mach if "gpus" in m), key=lambda m: abs(m["t"] - (t0 + t1) / 2), default=None)
        s = [near] if near else []
    gpu = any(g["util"] > 5 for m in s for g in m["gpus"] if g["index"] != 2)
    cpu = [m["cpu_total"] for m in s if m.get("cpu_total") is not None]
    cpu_m = float(np.mean(cpu)) if cpu else None
    return dict(other_gpu=gpu, cpu_mean=round(cpu_m, 1) if cpu_m is not None else None,
                cpu_high=bool(cpu_m is not None and cpu_m > 80.0))


def analyse_pairs(rows, steps_of, per_tok, mach=None):
    """rows: partC rows (FIT only); steps_of(server label or load) -> Steps. Returns per-request and per-trial rows."""
    runs = defaultdict(dict)
    for r in rows:
        if r.get("kind") in ("episodic", "inject", "run_summary") and r.get("action") in ACTIONS:
            runs[(r["load"], r["action"], r["trial"], r["pair"])].setdefault(r["mode"], []).append(r)
    req, trials = [], []
    for (load, act, trial, pair), m in sorted(runs.items()):
        if "with" not in m or "without" not in m:
            continue
        w, o = m["with"], m["without"]
        inj = next((r for r in w if r["kind"] == "inject"), None)
        summ = next((r for r in w if r["kind"] == "run_summary"), {})
        st = steps_of(inj.get("server") or load) if inj else None
        at = action_timing(st, inj) if inj and st else None
        bo = {r["idx"]: r for r in o if r["kind"] == "episodic"}
        rp = {r["idx"]: r for r in m.get("repeat", []) if r["kind"] == "episodic"}
        bw = [r for r in w if r["kind"] == "episodic"]
        flags = machine_flags(mach, summ.get("t_setup", summ.get("t0_trace", 0)) - 1,
                              summ.get("t_end", summ.get("t0_trace", 0) + 15) + 1) if mach else None
        tot, totp, n_pre, pre_tot = 0.0, None, 0, 0.0
        if rp:
            totp = sum(rp[i]["ttft_s"] - bo[i]["ttft_s"] for i in rp if i in bo and rp[i]["ttft_s"] is not None
                       and bo[i]["ttft_s"] is not None)
        inflight_src = [(r["t_submit"], r["t_first"] or r["t_end"]) for r in w if r["kind"] in ("episodic", "inject")]
        for r in bw:
            b = bo.get(r["idx"])
            if b is None or r["ttft_s"] is None or b["ttft_s"] is None:
                continue
            d = r["ttft_s"] - b["ttft_s"]
            tot += d
            a = r["t_submit"]
            rec = dict(load=load, action=act, trial=trial, idx=r["idx"], delta_s=round(d, 5), ttft_with=r["ttft_s"],
                       ttft_without=b["ttft_s"], flagged=bool(flags and (flags["other_gpu"] or flags["cpu_high"])),
                       cpu_high=bool(flags and flags["cpu_high"]))
            if at:
                span = at["t_end"] - at["t_sched"]
                off = (a - at["t_sched"]) / span if span > 0 else None
                rec["offset"] = round(off, 4)
                rec["bin"] = binof(off, a, inj["t_submit"])
                # POL4 Part 1b definition (section 2A.6): window from the action's submission to its first token
                if inj["t_submit"] <= a < inj["t_first"]:
                    rec["rho_pol4"] = round(d / (inj["t_first"] - a), 5)
                rec["inflight"] = sum(1 for s, e in inflight_src if s < a < e)
                rec["plugin_wait_next"] = st.wait_next(a)
                rec["steps_waited"] = len(st.window(a, r["t_first"]))
                if rec["bin"] not in ("pre_inj", "pre_fe", "post"):
                    rem_t = at["t_end"] - a
                    rec["R_b_s"] = round(rem_t, 5)
                    rec["rho_b"] = round(d / rem_t, 5) if rem_t > 0 else None
                    rec["excess_s"] = round(d - rem_t, 5)
                    rem_tok = round(rem_tokens(at["steps"], a), 1)
                    rec["rem_tok"] = rem_tok
                    pt = per_tok.get(act)
                    rec["R_a_s"] = round(rem_tok * pt, 5) if pt else None
                    rec["rho_a"] = round(d / (rem_tok * pt), 5) if pt and rem_tok > 0 else None
                if rec["bin"] == "pre_fe":
                    n_pre += 1
                    pre_tot += d
            req.append(rec)
        tr = dict(load=load, action=act, trial=trial, total_imposed_s=round(tot, 4),
                  repeat_noise_s=round(totp, 4) if totp is not None else None, n_bg=len(bw), pre_n=n_pre,
                  pre_imposed_s=round(pre_tot, 4), machine=flags,
                  flagged=bool(flags and (flags["other_gpu"] or flags["cpu_high"])))
        if at:
            ss = at["steps"]
            tr.update(action_pf_s=round(at["pf"], 4), action_span_s=round(at["t_end"] - at["t_sched"], 4),
                      action_comp_tok=at["comp"], derived_tok=at["derived_total"], cons_err=at["cons_err"],
                      cons_ok=at["cons_ok"], cons_ok512=at["cons_ok512"], n_action_steps=len(ss),
                      steps_with_other_prefill=sum(1 for s in ss if s["other_prefill"] > 0),
                      steps_with_decodes=sum(1 for s in ss if s["dec_req"] > 0),
                      steps_with_other_work=sum(1 for s in ss if s["other_prefill"] > 0 or s["dec_req"] > 0),
                      action_tok_share=round(sum(s["action_tok"] for s in ss) / max(1, sum(s["ctx_tok"] for s in ss)), 4),
                      other_prefill_tok=sum(s["other_prefill"] for s in ss),
                      decodes_in_action_steps=sum(s["dec_req"] for s in ss), steps=ss)
        else:
            tr["timing_missing"] = True
        trials.append(tr)
    return req, trials


def summarise(req, trials, flag_filter=None):
    def keep(x):
        return flag_filter is None or not x.get(flag_filter)
    R = [r for r in req if keep(r)]
    T = [t for t in trials if keep(t)]
    out = {}
    for ld in LOADS:
        for a in ACTIONS:
            rr = [r for r in R if r["load"] == ld and r["action"] == a]
            tt = [t for t in T if t["load"] == ld and t["action"] == a]
            if not tt:
                continue
            cell = dict(n_trials=len(tt), n_requests=len(rr))
            cell["by_bin"] = {b: dict(rho_b=stats([r.get("rho_b") for r in rr if r.get("bin") == b]),
                                      rho_a=stats([r.get("rho_a") for r in rr if r.get("bin") == b]),
                                      delta_s=stats([r["delta_s"] for r in rr if r.get("bin") == b]),
                                      excess_s=stats([r.get("excess_s") for r in rr if r.get("bin") == b]))
                              for b in BINS}
            cell["by_queue"] = {q: dict(rho_b=stats([r.get("rho_b") for r in rr if r.get("inflight") is not None and
                                                     qbin(r["inflight"]) == q and r.get("rho_b") is not None]))
                                for _, _, q in QBINS}
            mid = [r["rho_b"] for r in rr if r.get("rho_b") is not None and 0.25 <= r["offset"] < 0.75]
            mid_ci = cluster_ci([(r["trial"], r["rho_b"]) for r in rr if r.get("rho_b") is not None
                                 and 0.25 <= r["offset"] < 0.75])
            inside = [r for r in rr if r.get("excess_s") is not None and r.get("inflight") is not None]
            cell["excess_vs_inflight"] = ols([r["inflight"] for r in inside], [r["excess_s"] for r in inside])
            cell["rho_pol4"] = stats([r.get("rho_pol4") for r in rr])
            mid_a = [r["rho_a"] for r in rr if r.get("rho_a") is not None and 0.25 <= r["offset"] < 0.75]
            ow = sum(t.get("steps_with_other_work", 0) for t in tt)
            ns = sum(t.get("n_action_steps", 0) for t in tt)
            frac_other = ow / ns if ns else None
            med = float(np.median(mid)) if mid else None
            if med is None:
                verdict = "NO DATA"
            elif med >= 0.8:
                verdict = "H1"
            elif med <= 0.6 and frac_other is not None and frac_other >= 0.5:
                verdict = "H2"
            else:
                verdict = "PARTIAL"
            cell["verdict"] = dict(rho_b_25_75=stats(mid), rho_b_25_75_trial_ci95=mid_ci, rho_a_25_75=stats(mid_a), frac_action_steps_other_work=
                                   round(frac_other, 4) if frac_other is not None else None, verdict=verdict)
            cell["total_imposed_s"] = stats([t["total_imposed_s"] for t in tt])
            cell["repeat_noise_abs_s"] = stats([abs(t["repeat_noise_s"]) for t in tt if t.get("repeat_noise_s") is not None])
            cell["eng1_c_fit_median_s"] = ENG1_C_FIT.get((ld, a))
            cell["pre_fe_bin"] = dict(n_requests=sum(t["pre_n"] for t in tt),
                                      imposed_per_trial_s=stats([t["pre_imposed_s"] for t in tt]),
                                      delta_s=stats([r["delta_s"] for r in rr if r.get("bin") == "pre_fe"]))
            cell["imposed_by_bin_per_trial_s"] = {b: stats([sum(r["delta_s"] for r in rr if r["trial"] == t["trial"]
                                                                and r.get("bin") == b) for t in tt]) for b in BINS}
            cs = [t for t in tt if "cons_ok" in t]
            cell["conservation"] = dict(n=len(cs), pass64=sum(t["cons_ok"] for t in cs),
                                        pass512=sum(t["cons_ok512"] for t in cs),
                                        err=stats([t["cons_err"] for t in cs]))
            cell["step_composition"] = dict(
                n_action_steps=stats([t.get("n_action_steps") for t in cs]),
                action_tok_share=stats([t.get("action_tok_share") for t in cs]),
                other_prefill_tok=stats([t.get("other_prefill_tok") for t in cs]),
                decodes_in_action_steps=stats([t.get("decodes_in_action_steps") for t in cs]),
                frac_steps_other_prefill=round(sum(t.get("steps_with_other_prefill", 0) for t in cs) / max(1, ns), 4),
                frac_steps_decodes=round(sum(t.get("steps_with_decodes", 0) for t in cs) / max(1, ns), 4),
                action_span_s=stats([t.get("action_span_s") for t in cs]))
            out[f"{ld}|{a}"] = cell
    return out


# ------------------------------------------------------------------------------------------------ control
def control(pre, per_tok_out):
    rows = jl(OUT / f"{pre}_partB_requests_h100nvl.jsonl")
    if not rows:
        return None
    lab = rows[0]["server"]
    st = Steps(OUT / f"{pre}_steps" / f"{lab}.jsonl.gz")
    solo_ep = float(np.median([r["ttft_s"] for r in rows if r.get("sub") == "solo_ep" and r["ttft_s"]]))
    for L in ("mono11k", "piece2048"):
        v = []
        for r in rows:
            if r.get("sub") == "solo_long" and r.get("long") == L:
                f = st.fin.get("chatcmpl-" + r["rid"])
                comp = (r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0)
                if f and comp:
                    v.append(f["pf"] / comp)
        if v:
            per_tok_out[L] = float(np.median(v))
    inj = [r for r in rows if r.get("sub") == "inject"]
    pairs = defaultdict(dict)
    for r in inj:
        pairs[(r["long"], r["offset"], r["rep"], r["t_sched"] if r["kind"] != "episodic" else None)]
    longs = [r for r in inj if r["kind"] != "episodic"]
    eps = [r for r in inj if r["kind"] == "episodic"]
    cells = defaultdict(lambda: dict(rho_eng1b=[], rho_b=[], rho_a=[]))
    for e in eps:
        Lr = min((l for l in longs if l["long"] == e["long"] and l["offset"] == e["offset"] and l["rep"] == e["rep"]),
                 key=lambda l: abs(l["t_submit"] - (e["t_submit"] - e["offset"] * e["D_L"])), default=None)
        if Lr is None or e["ttft_s"] is None:
            continue
        wait = e["ttft_s"] - solo_ep
        c = cells[(e["long"], e["offset"])]
        c["rho_eng1b"].append(wait / (e["D_L"] * (1 - e["offset"])))
        at = action_timing(st, Lr)
        if at:
            rem = at["t_end"] - e["t_submit"]
            if rem > 0:
                c["rho_b"].append(wait / rem)
            rt = rem_tokens(at["steps"], e["t_submit"])
            if rt and e["long"] in per_tok_out:
                c["rho_a"].append(wait / (rt * per_tok_out[e["long"]]))
            c.setdefault("cons_err", []).append(at["cons_err"])
    return dict(solo_ep=solo_ep, per_token_s=per_tok_out,
                cells={f"{L}_off{int(o * 100)}": {k: stats(v) for k, v in c.items()} for (L, o), c in sorted(cells.items())})


def eng1_piece1024_per_tok():
    """Unloaded per-token prefill time of a 1,024-token piece (not in this study's control): ENG1 Part B E0 solo
    pieces (engine prefill time / computed tokens)."""
    rows = [r for r in jl(ENG1 / "eng1_partB_requests_h100nvl.jsonl") if r.get("sub") == "solo_long"
            and r.get("engine") == "E0" and r.get("long") == "piece1024"]
    st = Steps(ENG1 / "eng1_steps" / "B_E0.jsonl.gz")
    v = []
    for r in rows:
        f = st.fin.get("chatcmpl-" + r["rid"])
        comp = (r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0)
        if f and comp:
            v.append(f["pf"] / comp)
    return float(np.median(v)) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--replicate-eng1", action="store_true")
    a = ap.parse_args()
    pre = "eng1d_smoke" if a.smoke else "eng1d"
    split = json.loads((OUT / "eng1d_holdout_split.json").read_text())
    per_tok = {}
    res = dict(control=control(pre, per_tok))
    per_tok["piece1024"] = eng1_piece1024_per_tok()
    res["per_token_s"] = per_tok
    rows = jl(OUT / f"{pre}_partC_requests_h100nvl.jsonl")
    hold_rows = [r for r in rows if r.get("holdout")]
    fit = [r for r in rows if not r.get("holdout")]
    for r in fit:                                # guard: the split decides, not only the row flag
        if r.get("trial") is not None and r.get("load") in LOADS and r.get("action") in ACTIONS:
            assert r["trial"] not in split["holdout"][f"{r['load']}|{r['action']}"]
    res["holdout_recorded"] = dict(rows=len(hold_rows), pairs=len({r["pair"] for r in hold_rows if r.get("pair")}),
                                   note="recorded, NOT analysed")
    mach = jl(OUT / f"{pre}_machine_h100nvl.jsonl")
    cache = {}

    def steps_of(label):
        if label not in cache:
            cache[label] = Steps(OUT / f"{pre}_steps" / f"{label}.jsonl.gz")
        return cache[label]
    req, trials = analyse_pairs(fit, steps_of, per_tok, mach)
    pc = [r for r in rows if r.get("kind") == "pair_check"]
    res["pair_check"] = dict(pairs=len(pc), mismatches=sum(r["mismatches"] for r in pc), compared=sum(r["n"] for r in pc))
    res["cells_all"] = summarise(req, trials)
    res["rho_pol4_by_action"] = {a: dict(stats=stats([r.get("rho_pol4") for r in req if r["action"] == a]),
                                         trial_ci95=cluster_ci([((r["load"], r["trial"]), r.get("rho_pol4"))
                                                                for r in req if r["action"] == a]))
                                 for a in ACTIONS}
    res["cells_unflagged"] = summarise(req, trials, "flagged")
    res["cells_cpu_ok"] = summarise(req, trials, "cpu_high")
    res["flags"] = dict(trials=len(trials), flagged=sum(t["flagged"] for t in trials),
                        other_gpu=sum(bool(t["machine"] and t["machine"]["other_gpu"]) for t in trials),
                        cpu_high=sum(bool(t["machine"] and t["machine"]["cpu_high"]) for t in trials),
                        cpu_mean=stats([t["machine"]["cpu_mean"] for t in trials if t["machine"]]))
    res["conservation_overall"] = dict(n=sum(1 for t in trials if "cons_ok" in t),
                                       pass64=sum(t.get("cons_ok", False) for t in trials),
                                       pass512=sum(t.get("cons_ok512", False) for t in trials),
                                       missing_timing=sum(1 for t in trials if t.get("timing_missing")))
    ms = [m for m in mach if "gpus" in m]
    res["machine"] = dict(samples=len(ms), mem_avail_min_gib=min((m["mem_gib"]["MemAvailable"] for m in ms), default=None),
                          cpu_total=stats([m.get("cpu_total") for m in ms]),
                          load1=stats([m["load"][0] for m in ms]),
                          other_gpu_active_frac={g: round(np.mean([any(x["index"] == g and x["util"] > 5 for x in m["gpus"])
                                                                   for m in ms]), 4) if ms else None for g in (0, 1, 3)})
    with open(OUT / f"{pre}_requests_derived.jsonl", "w") as f:
        for r in req:
            f.write(json.dumps(r) + "\n")
    with open(OUT / f"{pre}_trials_derived.jsonl", "w") as f:
        for t in trials:
            f.write(json.dumps(t) + "\n")
    (OUT / f"{pre}_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(dict(control=res["control"], pair_check=res["pair_check"], flags=res["flags"],
                          conservation=res["conservation_overall"],
                          verdicts={k: v["verdict"] | dict(total=v["total_imposed_s"].get("median"))
                                    for k, v in res["cells_all"].items()}), indent=1))
    if a.replicate_eng1:
        e1 = [r for r in jl(ENG1 / "eng1_partC_requests_h100nvl.jsonl") if not r.get("holdout")]
        e1 = [r for r in e1 if r.get("action") in ACTIONS and r.get("load") in LOADS]
        e1split = json.loads((ENG1 / "eng1_holdout_split.json").read_text())
        e1 = [r for r in e1 if r.get("trial") is None or r["trial"] not in e1split["holdout"][f"{r['load']}|{r['action']}"]]
        c1 = {}

        def steps1(load):
            if load not in c1:
                c1[load] = Steps(ENG1 / "eng1_steps" / f"C_{load}_E0.jsonl.gz")
            return c1[load]
        for r in e1:
            r["server"] = None                   # ENG1 rows carry no server label: steps by load
        req1, tr1 = analyse_pairs(e1, steps1, per_tok)
        rep = dict(label="ENG1 Part C FIT pairs only (HOLDOUT rows dropped before analysis)",
                   cells=summarise(req1, tr1),
                   rho_pol4_by_action={a: dict(stats=stats([r.get("rho_pol4") for r in req1 if r["action"] == a]),
                                               trial_ci95=cluster_ci([((r["load"], r["trial"]), r.get("rho_pol4"))
                                                                      for r in req1 if r["action"] == a]))
                                       for a in ACTIONS},
                   conservation=dict(n=sum(1 for t in tr1 if "cons_ok" in t), pass64=sum(t.get("cons_ok", False) for t in tr1),
                                     pass512=sum(t.get("cons_ok512", False) for t in tr1)))
        (OUT / "eng1d_eng1_replication.json").write_text(json.dumps(rep, indent=1))
        print(json.dumps({k: v["verdict"] | dict(total=v["total_imposed_s"].get("median"))
                          for k, v in rep["cells"].items()}, indent=1))


if __name__ == "__main__":
    main()
