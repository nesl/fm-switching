#!/usr/bin/env python3
"""StudyE8-device-warm analysis: Parts A-D tables, energy, parity, sanity, 6-check."""
import gzip, json, math, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "results/device/study_e8"
E7 = Path("/home/nesl/data/study_e7_d2_frames/e7")
COMMITTED_E7 = ROOT / "results/sember/study_e7/e7_requests_h100nvl.jsonl"
PINNED_HZ = 1300500000

def load_jsonl(p):
    return [json.loads(l) for l in open(p)]

def pct(xs, q):
    xs = sorted(v for v in xs if v is not None)
    if not xs: return None
    if len(xs) == 1: return round(xs[0], 4)
    i = q/100*(len(xs)-1); lo=int(i); hi=min(lo+1,len(xs)-1)
    return round(xs[lo]+(xs[hi]-xs[lo])*(i-lo), 4)

def med(xs):
    xs=[v for v in xs if v is not None]
    return round(st.median(xs),4) if xs else None

# ── tegrastats energy ────────────────────────────────────────────────────────
import bisect
TEG = []
with gzip.open(OUT/"tegrastats.jsonl.gz","rt") as f:
    for l in f:
        try:
            r=json.loads(l)
            if r.get("t") is not None: TEG.append(r)
        except: pass
TEG.sort(key=lambda r:r["t"])
print(f"tegrastats rows: {len(TEG)}")
# cumulative trapezoidal energy (J) at each tegrastats timestamp -> O(log n) range queries
_T=[r["t"] for r in TEG]
_P=[r["tot_mw"] for r in TEG]
_CUM=[0.0]
for i in range(1,len(TEG)):
    dt=_T[i]-_T[i-1]
    _CUM.append(_CUM[-1]+(_P[i]+_P[i-1])/2*dt/1000.0)

def _cum_at(t):
    """Interpolated cumulative energy (J) at wall time t, clamped to the sampled range."""
    if not _T: return 0.0
    if t<=_T[0]: return 0.0
    if t>=_T[-1]: return _CUM[-1]
    i=bisect.bisect_right(_T,t)-1          # _T[i] <= t < _T[i+1]
    dt=_T[i+1]-_T[i]
    if dt<=0: return _CUM[i]
    frac=(t-_T[i])/dt
    # energy from _T[i] to t using trapezoid with interpolated power
    p_t=_P[i]+(_P[i+1]-_P[i])*frac
    seg=(_P[i]+p_t)/2*(t-_T[i])/1000.0
    return _CUM[i]+seg

def energy_j(s, e):
    return round(_cum_at(e)-_cum_at(s),3)

def add_energy(rows):
    for r in rows:
        if r.get("wall_start") and r.get("wall_end"):
            r["energy_j"]=energy_j(r["wall_start"],r["wall_end"])
    return rows

A=add_energy(load_jsonl(OUT/"partA_warm.jsonl"))
B=add_energy(load_jsonl(OUT/"partB_cold.jsonl"))
C=add_energy(load_jsonl(OUT/"partC_keepwarm.jsonl"))
summ=json.load(open(OUT/"study_e8_summary.json"))

appends=[r for r in A if r["kind"]=="append"]
qs=[r for r in A if r["kind"]=="question"]
print(f"Part A: {len(appends)} appends, {len(qs)} warm questions")

res={}

# ── PART A: append cost vs history tokens ────────────────────────────────────
# bin appends by history prompt_tokens
def bin_by(rows, key, edges):
    out=[]
    for lo,hi in zip(edges[:-1],edges[1:]):
        grp=[r for r in rows if r.get(key) is not None and lo<=r[key]<hi]
        if grp:
            out.append({"bin":f"{lo}-{hi}","n":len(grp),
                        "hist_tok_med":med([r["prompt_tokens"] for r in grp]),
                        "evaluated_med":med([r["evaluated"] for r in grp]),
                        "reused_med":med([r["reused"] for r in grp]),
                        "ttft_p50":pct([r["ttft_s"] for r in grp],50),
                        "ttft_p90":pct([r["ttft_s"] for r in grp],90),
                        "total_p50":pct([r["total_latency_s"] for r in grp],50),
                        "energy_p50":pct([r["energy_j"] for r in grp],50)})
    return out
edges=[0,1000,3000,6000,10000,20000,30000,60000]
res["A_append_vs_histtok"]=bin_by(appends,"prompt_tokens",edges)
res["A_question_vs_histtok"]=bin_by(qs,"prompt_tokens",edges)
res["A_append_overall"]={"n":len(appends),"evaluated_med":med([r["evaluated"] for r in appends]),
    "evaluated_max":max(r["evaluated"] for r in appends),
    "ttft_p50":pct([r["ttft_s"] for r in appends],50),"ttft_p90":pct([r["ttft_s"] for r in appends],90),
    "ttft_max":max(r["ttft_s"] for r in appends),
    "reused_frac_med":med([r["reused"]/r["prompt_tokens"] for r in appends if r["prompt_tokens"]])}
res["A_max_prompt_tokens"]=max(r["prompt_tokens"] for r in A)
res["A_nctx_overflow"]=any(r["prompt_tokens"]>=57344 for r in A)
res["A_clock_bad"]=sum(1 for r in A if not r["clock_ok"])
res["A_body_sha_mismatch"]=sum(1 for r in qs if not r.get("body_sha256_match",True))

# ── PART B: cold TTFT fit vs prompt tokens ───────────────────────────────────
bt=[(r["prompt_tokens"],r["ttft_s"]) for r in B]
xs=[x for x,_ in bt]; ys=[y for _,y in bt]
n=len(xs); sx=sum(xs); sy=sum(ys); sxx=sum(x*x for x in xs); sxy=sum(x*y for x,y in bt)
slope=(n*sxy-sx*sy)/(n*sxx-sx*sx); intercept=(sy-slope*sx)/n
ybar=sy/n; ss_tot=sum((y-ybar)**2 for y in ys); ss_res=sum((y-(slope*x+intercept))**2 for x,y in bt)
r2=1-ss_res/ss_tot
res["B_cold_fit"]={"slope_ms_per_tok":round(slope*1000,4),"slope_ms_per_1k":round(slope*1e6,1),
    "intercept_s":round(intercept,4),"r2":round(r2,5),"n":n,
    "tok_range":[min(xs),max(xs)],"ttft_range":[round(min(ys),3),round(max(ys),3)],
    "reused_all_zero":all(r["reused"]==0 for r in B)}
# effective tok/s at several sizes (from prefill_ms)
res["B_prefill_tok_per_s"]=[{"tok":r["prompt_tokens"],"prefill_s":round(r["prefill_ms"]/1000,3),
    "tok_per_s":round(r["prompt_tokens"]/(r["prefill_ms"]/1000),1)} for r in sorted(B,key=lambda r:r["prompt_tokens"])]
# F4 device cold reference (client TTFT): 467->0.497, 1129->1.308, 3085->3.798
F4=[(467,0.497),(1129,1.308),(3085,3.798)]
f4_slope=(F4[-1][1]-F4[0][1])/(F4[-1][0]-F4[0][0])
# predict E8 TTFT at F4 token counts vs F4 actual
cmp=[]
for tok,f4t in F4:
    e8pred=slope*tok+intercept
    cmp.append({"tok":tok,"F4_ttft_s":f4t,"E8_fit_ttft_s":round(e8pred,3),"ratio_E8_over_F4":round(e8pred/f4t,2)})
res["B_vs_F4"]={"F4_slope_ms_per_1k":round(f4_slope*1e6,1),"E8_slope_ms_per_1k":round(slope*1e6,1),
    "slope_ratio":round(slope/f4_slope,2),"per_point":cmp,
    "note":"D2 = many small 352x256 frames (~90 tok each, 7-578 per Q); F4 = few 560x560 (327 tok each, 1/3/9). More frames = more vision-encoder passes + longer contexts (O(n^2) attention), so per-token cold prefill is slower. FORMAT difference, not a stack regression."}

# ── PART C: keep-warm power ──────────────────────────────────────────────────
pc=summ.get("partC",{})
c_app=[r for r in C if r["kind"]=="append"]
res["C"]={"mean_warm_w":pc.get("mean_warm_w"),"mean_idle_w":pc.get("mean_idle_w"),
    "delta_w":pc.get("delta_w"),"energy_per_warm_hour_wh":pc.get("energy_per_warm_hour_wh"),
    "warm_duration_s":pc.get("warm_duration_s"),"n_appends":pc.get("n_appends"),
    "appends_kept_up_flag":pc.get("appends_kept_up"),
    "append_ttft_p50":pct([r["ttft_s"] for r in c_app],50),
    "append_ttft_p90":pct([r["ttft_s"] for r in c_app],90),
    "append_ttft_max":max((r["ttft_s"] for r in c_app),default=None),
    "append_total_max":max((r["total_latency_s"] for r in c_app),default=None),
    "appends_over_2s":sum(1 for r in c_app if r["total_latency_s"]>2.0),
    "append_total_at_start":round(c_app[0]["total_latency_s"],3) if c_app else None,
    "append_total_at_end":round(c_app[-1]["total_latency_s"],3) if c_app else None,
    "hist_tok_end":c_app[-1]["prompt_tokens"] if c_app else None}

# ── PART D: parity ───────────────────────────────────────────────────────────
h100={json.loads(l)["question_id"]:json.loads(l) for l in open(E7/"letters_4b.jsonl")}
# cross-validate letters_4b vs committed e7_requests_h100nvl.jsonl
comm={}
for l in open(COMMITTED_E7):
    d=json.loads(l)
    if d.get("model") in ("4bi","4BI","4b","4B-Instruct",None) or "4b" in str(d.get("model","")).lower():
        comm.setdefault(d.get("question_id"),d)
# just map all committed by qid (model filter below)
comm_all=[json.loads(l) for l in open(COMMITTED_E7)]
comm_by_qid={}
for d in comm_all:
    comm_by_qid.setdefault(d.get("question_id"),[]).append(d)
xval={"checked":0,"match":0,"mismatch":[]}
for qid,h in h100.items():
    cs=comm_by_qid.get(qid,[])
    # find a 4B row
    c4=next((c for c in cs if "4b" in str(c.get("model","")).lower() or c.get("model")=="4bi"),None)
    if c4 and h.get("pred_4b_h100") is not None:
        xval["checked"]+=1
        cp=c4.get("pred") or c4.get("pred_letter")
        if cp==h["pred_4b_h100"]: xval["match"]+=1
        else: xval["mismatch"].append((qid[:12],h["pred_4b_h100"],cp))
res["D_letters4b_vs_committed"]=xval

def agree(dev_rows):
    comp=[]; devonly=[]
    for r in dev_rows:
        qid=r["question_id"]; h=h100.get(qid,{})
        hp=h.get("pred_4b_h100")
        dp=r["pred"]
        if r.get("over_context") or hp is None:
            devonly.append({"qid":qid[:12],"dev":dp,"tok":r["prompt_tokens"]})
        else:
            comp.append((qid,dp,hp))
    n=len(comp); m=sum(1 for _,d,h in comp if d==h)
    return {"n_comparable":n,"agree":m,"agreement":round(m/n,4) if n else None,
            "n_device_only_overctx":len(devonly),"device_only":devonly,
            "disagreements":[(q[:12],d,h) for q,d,h in comp if d!=h]}
res["D_warm_vs_h100"]=agree(qs)
res["D_cold_vs_h100"]=agree(B)
# device warm vs cold (same qids present in both)
coldmap={r["question_id"]:r["pred"] for r in B}
wc=[(r["question_id"],r["pred"],coldmap[r["question_id"]]) for r in qs if r["question_id"] in coldmap]
res["D_warm_vs_cold_device"]={"n":len(wc),"identical":sum(1 for _,w,c in wc if w==c),
    "mismatch":[(q[:12],w,c) for q,w,c in wc if w!=c]}
# device accuracy (warm) vs h100 accuracy on comparable
def acc(rows):
    rr=[r for r in rows if r["pred"] and r["pred"]!="X"]
    return round(sum(1 for r in rows if r.get("correct"))/len(rows),4), len(rows)
# warm vs cold MATCHED (same question, same history): the core question
warmmap={r["question_id"]:r for r in qs}
matched=[]
for cr in B:
    wr=warmmap.get(cr["question_id"])
    if wr:
        matched.append({"qid":cr["question_id"][:12],"tok":cr["prompt_tokens"],
            "cold_ttft":cr["ttft_s"],"warm_ttft":wr["ttft_s"],
            "ttft_speedup":round(cr["ttft_s"]/wr["ttft_s"],1) if wr["ttft_s"] else None,
            "cold_total":cr["total_latency_s"],"warm_total":wr["total_latency_s"],
            "cold_energy_j":cr.get("energy_j"),"warm_energy_j":wr.get("energy_j"),
            "energy_ratio_cold_over_warm":round(cr["energy_j"]/wr["energy_j"],1) if wr.get("energy_j") else None,
            "cold_pred":cr["pred"],"warm_pred":wr["pred"],"letters_match":cr["pred"]==wr["pred"]})
matched.sort(key=lambda m:m["tok"])
res["D_warm_vs_cold_matched"]=matched
res["D_warm_vs_cold_speedup_med"]=med([m["ttft_speedup"] for m in matched])
res["D_warm_vs_cold_energy_ratio_med"]=med([m["energy_ratio_cold_over_warm"] for m in matched])

# Part C: 2s crossover
c_app_sorted=sorted(c_app,key=lambda r:r["n_hist_frames"])
cross=next((r for r in c_app_sorted if r["total_latency_s"]>2.0),None)
res["C_2s_crossover"]={"hist_frames":cross["n_hist_frames"] if cross else None,
    "hist_tok":cross["prompt_tokens"] if cross else None,
    "session_time_s":round(cross["n_hist_frames"]*2,0) if cross else None} if cross else {"note":"never crossed 2s"}

res["D_device_warm_acc"]=acc(qs)
res["D_device_cold_acc"]=acc(B)
h100_comp=[h100[r["question_id"]] for r in qs if not r.get("over_context") and h100.get(r["question_id"],{}).get("pred_4b_h100")]
res["D_h100_acc_on_comparable"]=round(sum(1 for h in h100_comp if h.get("correct"))/len(h100_comp),4) if h100_comp else None

# ── SANITY ───────────────────────────────────────────────────────────────────
res["sanity"]={
    "cold_reused_all_zero":all(r["reused"]==0 for r in B),
    "partA_clock_bad":res["A_clock_bad"],
    "partB_clock_bad":sum(1 for r in B if not r["clock_ok"]),
    "partC_clock_bad":sum(1 for r in C if not r["clock_ok"]),
    "tj_max_overall":max((r["tj"] for r in TEG if r.get("tj")),default=None),
    "throttle_stop":max((r["tj"] for r in TEG if r.get("tj")),default=0)>=90,
    "determinism":summ.get("determinism"),
    "unparsed_warm_X":sum(1 for r in qs if r["pred"]=="X"),
    "unparsed_cold_X":sum(1 for r in B if r["pred"]=="X"),
    "n_questions_warm":len(qs),
    "body_sha_mismatch":res["A_body_sha_mismatch"],
}
res["kv_mem"]=summ["kv_mem"]
res["part0_passed"]=summ["part0"]["passed"]

json.dump(res, open(OUT/"study_e8_analysis.json","w"), indent=2, default=str)
print(json.dumps(res, indent=1, default=str))
