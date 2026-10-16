"""H100 SDPA vs flash-attn THROUGHPUT recompute (2026-10-16). Analysis only, no inference.
tok/s = n_generated / latency per trial, bucketed by the trial's OWN n_generated (not the other backend's),
plus paired same-trial ratios under three bucketing rules to expose the cross-backend bucketing artifact.
Run from repo root: .venv/bin/python experiments/erqa/h100_fa2_throughput.py"""
import json,statistics as st,collections,sys
import numpy as np
F=[("StudyR","sdpa","results/erqa/study_r/study_r_trials_h100nvl.jsonl"),("StudyR","fa2","results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl"),
("StudyS2","sdpa","results/erqa/study_s2/study_s2_trials_h100nvl.jsonl"),("StudyS2","fa2","results/erqa/study_s2/study_s2_trials_h100nvl_fa2.jsonl"),
("StudyT","sdpa","results/signs/study_t/study_t_trials_h100nvl.jsonl"),("StudyT","fa2","results/signs/study_t/study_t_trials_h100nvl_fa2.jsonl"),
("StudyT","fa2","results/signs/study_t/study_t_longtrace_h100nvl_fa2.jsonl")]
T=[];skipped=collections.Counter();total=collections.Counter()
for study,be,f in F:
    for l in open(f):
        r=json.loads(l)
        if r.get('_hardware')!='h100nvl': skipped['non-H100 (A6000 reused arms A/B)']+=1; continue
        total[(study,be)]+=1
        ng=r.get('n_generated'); lat=r.get('total_latency_ms', r.get('latency_ms'))
        if r.get('latency_ms') is not None and r.get('total_latency_ms') is not None and abs(r['latency_ms']-r['total_latency_ms'])>0.5: skipped['latency fields disagree']+=1
        if ng is None or lat is None or lat<=0: skipped[f'missing ng/lat {study} {be}']+=1; continue
        att=r.get('attn_implementation') or ('sdpa' if be=='sdpa' else None)
        assert (be=='fa2')==(att=='flash_attention_2'),(f,att)
        T.append(dict(study=study,be=be,arm=r['arm'],phase=r.get('phase'),ng=ng,s=lat/1000,tps=ng/(lat/1000),
            think=r['arm'] in('D','T32'),key=(study,r['arm'],r.get('question_id',r.get('path',r.get('sign_id'))),r.get('budget'),r.get('phase'),r.get('forced_min_new_tokens'))))
print("H100 trials per study/backend:",dict(total)); print("excluded/flags:",dict(skipped)); print("usable:",len(T))
def bucket(n): return "<2k" if n<2000 else ("2-8k" if n<=8000 else ">8k")
def cell(rows):
    if not rows: return "—"
    x=np.array([r['tps'] for r in rows]); agg=sum(r['ng'] for r in rows)/sum(r['s'] for r in rows)
    q1,md,q3=np.percentile(x,[25,50,75]); return f"n={len(rows):4d} med {md:5.2f} [IQR {q1:5.2f}-{q3:5.2f}] agg {agg:5.2f} | med gen {int(np.median([r['ng'] for r in rows]))}"
def table(sel,title):
    print(f"\n## {title}")
    for b in ["<2k","2-8k",">8k"]:
        cs={be:[r for r in T if sel(r) and bucket(r['ng'])==b and r['be']==be] for be in('sdpa','fa2')}
        ms={be:np.median([r['tps'] for r in v]) if v else None for be,v in cs.items()}
        ratio=f"{ms['fa2']/ms['sdpa']:.3f}x" if all(ms.values()) else "—"
        print(f"{b:5s} SDPA {cell(cs['sdpa'])}\n      FA2  {cell(cs['fa2'])}\n      fa2/sdpa (median) {ratio}")
table(lambda r:True,"ALL H100 trials, bucketed by own n_generated")
table(lambda r:r['think'],"Thinking arms only (D, T32)")
table(lambda r:not r['think'],"Instruct arms only (A_h100, C, I32)")
for s in ["StudyR","StudyS2","StudyT"]: table(lambda r,s=s:r['study']==s,f"{s} only")
# finer within-bucket: tps vs length
print("\n## fine bins (thinking arms)")
edges=[0,500,1000,2000,4000,8000,12000,16000,30000]
for lo,hi in zip(edges,edges[1:]):
    out=[]
    for be in('sdpa','fa2'):
        v=[r['tps'] for r in T if r['think'] and lo<=r['ng']<hi and r['be']==be]
        out.append(f"{be} n={len(v):3d} med={np.median(v):5.2f}" if v else f"{be} n=  0")
    print(f"{lo:5d}-{hi:5d}: "+" | ".join(out))
# linear fit: seconds = a + ng/b  (prefill + per-token)
print("\n## per-backend fit latency_s = a + c*n_generated (thinking arms, ng>=200)")
for be in('sdpa','fa2'):
    v=[r for r in T if r['think'] and r['be']==be and r['ng']>=200]
    x=np.array([r['ng'] for r in v]);y=np.array([r['s'] for r in v]); c,a=np.polyfit(x,y,1)
    v2=[r for r in v if r['ng']>=8000]; 
    print(f"{be}: a={a:.2f}s  per-token={c*1000:.2f} ms -> {1/c:.2f} tok/s marginal (n={len(v)}); quadratic term:",np.polyfit(x,y,2)[0])
# paired: same trial key both backends
print("\n## paired same trial-key (both backends), ratio fa2/sdpa tok/s, bucketed by SDPA-ng AND by FA2-ng AND by both-in-same-bucket")
idx={be:{r['key']:r for r in T if r['be']==be} for be in('sdpa','fa2')}
common=[k for k in idx['sdpa'] if k in idx['fa2']]
print("paired keys:",len(common))
for mode in ("sdpa-ng","fa2-ng","same-bucket"):
    for b in ["<2k","2-8k",">8k"]:
        rs=[];gs=[];gf=[]
        for k in common:
            s,f=idx['sdpa'][k],idx['fa2'][k]
            bs,bf=bucket(s['ng']),bucket(f['ng'])
            ok={"sdpa-ng":bs==b,"fa2-ng":bf==b,"same-bucket":bs==b and bf==b}[mode]
            if ok: rs.append(f['tps']/s['tps']); gs.append(s['ng']); gf.append(f['ng'])
        if rs: print(f"{mode:11s} {b:5s} n={len(rs):3d} median ratio {np.median(rs):.3f}  med gen sdpa {int(np.median(gs))} fa2 {int(np.median(gf))}  wall-time ratio fa2/sdpa (median of per-pair) {np.median([idx['fa2'][k]['s']/idx['sdpa'][k]['s'] for k in common if ({'sdpa-ng':bucket(idx['sdpa'][k]['ng'])==b,'fa2-ng':bucket(idx['fa2'][k]['ng'])==b,'same-bucket':bucket(idx['sdpa'][k]['ng'])==b==bucket(idx['fa2'][k]['ng'])}[mode])]):.3f}")
