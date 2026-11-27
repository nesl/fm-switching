#!/usr/bin/env python3
"""Windowed network scorer (D332). Read-only on cell dirs.
usage: python3 -I netwin.py <outage_cell_dir> <control_cell_dir> <t0> <d> <label> [--json out.json] [--window fixed|def1]
Default window: fixed [R,R+120] (+[R,R+60],[R,R+300]); --window def1 = old B_obs rule window.
Window [R, R+B_obs], R=t0+d. harm = control MINUS outage.
ON-TIME (the committed scorer's, experiments/orchestration/live2/scorer/score.py):
  robot cloud on-time = robot_rows.source_by_deadline=='cloud'  (== _within(o,3.0): t_delivered-t_opportunity<=3.0)
  robot cbd           = robot_rows.standing_correct_by_deadline is True  (headline numerator, D155(3))
  single-shot on-time = assistive_rows.on_time (== source_by_deadline=='cloud'; _within(o,2.0) on t_delivered)
  dashcam within_L    = _within(o,1.0) on t_delivered; checked equal to outcomes.within_L per row.
Outcomes.within_L (emulator pre-guard flag, t_cloud_done based) is reported beside for single-shot.
"""
import json,gzip,os,sys,random,collections
import numpy as np
REPS=2000;SEED=7
def rd(p):
    for q in (p,p+'.gz'):
        if os.path.exists(q):
            op=gzip.open if q.endswith('.gz') else open
            return [json.loads(l) for l in op(q,'rt')]
    return []
def jl(p):
    return json.load(open(p)) if os.path.exists(p) else {}
def ci(v):
    v=sorted(v);return v[int(.025*len(v))],v[int(.975*len(v))-1]
def within(o,L):
    td=o.get('t_delivered');return td is not None and (float(td)-float(o['t_opportunity']))<=L+1e-9
class Cell:
    def __init__(s,d):
        s.d=d.rstrip('/');s.name=os.path.basename(s.d)
        s.sc=jl(s.d+'/cell.json')['score']['score']
        s.meta=jl(s.d+'/run_meta.json');s.hdr=jl(s.d+'/header.json');s.cr=jl(s.d+'/coordinator_result.json')
        s.oc=rd(s.d+'/outcomes.jsonl');s.ocd={o['opportunity_id']:o for o in s.oc}
        s.rq=rd(s.d+'/request.jsonl.gz')
        s.rows={r['opportunity_id']:r for r in s.sc['robot_rows']}
        s.ss={r['opportunity_id']:r for r in s.sc['assistive_rows']}
        s.byrid={x['request_id']:x for x in s.rq}
        s.byopp={x['opportunity_id']:x for x in s.rq if x.get('opportunity_id')}
    def req(s,i):
        o=s.ocd.get(i);cp=o and o.get('cloud_payload')
        return s.byrid.get(cp['request_id']) if cp and cp.get('request_id') else s.byopp.get(i)
    def rob_cbd(s,i): return bool(s.rows[i]['standing_correct_by_deadline'])
    def rob_cloud(s,i): return s.rows[i]['source_by_deadline']=='cloud'
    def classify(s):
        """independent re-derivation (sylib): (stands_on_time, correct) per robot opp. cross-check only."""
        out={}
        for i,rw in s.rows.items():
            o=s.ocd[i];cp=o.get('cloud_payload');r=s.req(i);D=o['deadline_s']
            st=bool(cp and cp.get('cloud_letter') and r is not None and r['http_status']==200 and r['t_done']-o['t_opportunity']<=D and o.get('t_delivered') is not None and o['t_delivered']-o['t_opportunity']<=D and rw['source_by_deadline']=='cloud')
            out[i]=(st,(cp['cloud_letter']==rw['gold']) if st else bool(rw['standing_correct_by_deadline']))
        return out
    def events(s,robot=True):
        return sorted((x['t_submit'],x['prompt_tokens']-(x['cached_tokens'] or 0),x['device_id']) for x in s.rq
            if (x['device_id'].startswith('robo') or not robot) and x['t_submit'] is not None and x['prompt_tokens'])
def rate(e,W,grid):
    t=np.array([a for a,b,c in e]);u=np.array([b for a,b,c in e]);cs=np.concatenate([[0],np.cumsum(u)])
    hi=np.searchsorted(t,grid,side='right');lo=np.searchsorted(t,grid-W,side='right')
    return (cs[hi]-cs[lo])/W
def bobs(C,O,T0,R,W=10,k=1.0,end=1200.0):
    grid=np.arange(0,end+.5,1.0)
    rc,ro=rate(C.events(),W,grid),rate(O.events(),W,grid)
    pre=(grid>=60)&(grid<T0);sd=rc[pre].std();m=rc[pre].mean();thr=rc+k*sd
    idx=[i for i,g in enumerate(grid) if g>=R]
    above=[i for i in idx if ro[i]>thr[i]]
    d1=0.0 if not above else float('nan')
    if above:
        for i in idx:
            if i>=above[0] and ro[i]<=thr[i]: d1=grid[i]-R;break
    ex=[i for i in idx if ro[i]>thr[i]]
    d2=(grid[ex[-1]]+1-R) if ex else 0.0
    first_exc=(grid[above[0]]-R) if above else None
    return dict(W=W,sd=sd,mean=m,def1=d1,def2=d2,first_exceed=first_exc,grid=grid,rc=rc,ro=ro)
def drain_marks(O,T0,R):
    """log-based drain markers from the outage cell itself."""
    vic=set((O.hdr.get('outage') or {}).get('robots',[]))|set(jl(O.d+'/link_events.json').get('outage',{}).get('robots',[]))
    up=O.meta.get('uplink') or {}
    qmax={k:v.get('queue_max') for k,v in up.items() if (not vic or k in vic)}
    qm=max([v for v in qmax.values() if v] or [0])
    late=[o['t_opportunity']+o['uplink_queue_s'] for o in O.oc if o['kind']=='recall' and o['device_id'].startswith('robo') and o['t_opportunity']>=T0 and (o.get('uplink_queue_s') or 0)>1.0 and (not vic or o['device_id'] in vic)]
    dl=[]
    for o in O.oc:
        if o['kind']!='recall' or not o['device_id'].startswith('robo') or (vic and o['device_id'] not in vic): continue
        r=O.req(o['opportunity_id'])
        if r is not None and r.get('t_submit') is not None and r['t_submit']>=R and r['t_submit']-o['t_opportunity']>2.0: dl.append(r['t_submit'])
    dpr=(jl(O.d+'/link_events.json').get('outage') or {}).get('deferred_per_robot') or {}
    dfr=sum(len(v.get('deferred',[])) for v in dpr.values());dtok=sum(b.get('own_tokens',0) for v in dpr.values() for b in v.get('deferred',[]))
    return dict(n_deferred_frames=dfr,deferred_own_tokens=dtok,n_victims=len(vic),uplink_queue_max_max=qm,
                last_backlogged_delivery=(max(late)-R if late else None),n_backlogged=len(late),
                last_delayed_submit=(max(dl)-R if dl else None),n_delayed_after_R=len(dl))
def deficit_recovery(C,O,T0,R,vic,end=1200.0):
    grid=np.arange(T0,end+.5,1.0)
    f=lambda c:np.array([sum(u for t,u,dv in c.events() if t<=g and (not vic or dv in vic)) for g in grid])
    ec=[(t,u) for t,u,dv in C.events() if (not vic or dv in vic)];eo=[(t,u) for t,u,dv in O.events() if (not vic or dv in vic)]
    def cum(e):
        t=np.array([a for a,b in e]);u=np.concatenate([[0],np.cumsum([b for a,b in e])]);return u[np.searchsorted(t,grid,side='right')]
    diff=cum(eo)-cum(ec);ir=int(np.searchsorted(grid,R));mn=diff[ir];rec=[grid[i]-R for i in range(ir,len(grid)) if diff[i]>=0]
    return dict(deficit_at_R_tokens=float(mn),recovered_at=(rec[0] if rec else None),end_diff=float(diff[-1]))
def clus(vals,reps=REPS,seed=SEED):
    by=collections.defaultdict(lambda:[0,0])
    for k,a,b in vals:x=by[k];x[0]+=a;x[1]+=b
    ks=sorted(by);rng=random.Random(seed)
    d=[]
    for _ in range(reps):
        s=[by[ks[rng.randrange(len(ks))]] for _ in ks];d.append(sum(x[0]-x[1] for x in s))
    return (ci(d) if ks else (0,0)),len(ks)
def metrics(C,O,lo,hi,tag,out,rec):
    out.append('%s [%.1f,%.1f)  len %.0f s'%(tag,lo,hi,hi-lo))
    def line(name,vals,unit):
        c=sum(a for k,a,b in vals);o=sum(b for k,a,b in vals);n=len(vals);(l,h),nk=clus(vals)
        out.append('  %-24s n=%4d ctl %4d (%.3f) out %4d (%.3f) harm(ctl-out) %+d CI[%+.0f,%+.0f] clusters=%d (%s)'%(name,n,c,c/max(n,1),o,o/max(n,1),c-o,l,h,nk,unit))
        rec[tag+'|'+name]=dict(n=n,ctl=c,out=o,harm=c-o,ci=[l,h],clusters=nk,units=[(str(k),a,b) for k,a,b in vals])
    ids=sorted(i for i in O.rows if i in C.rows and lo<=O.ocd[i]['t_opportunity']<hi)
    q=lambda i:O.rows[i]['question_id']
    line('robot cbd',[(q(i),int(C.rob_cbd(i)),int(O.rob_cbd(i))) for i in ids],'robot questions')
    line('robot cloud on-time',[(q(i),int(C.rob_cloud(i)),int(O.rob_cloud(i))) for i in ids],'robot questions')
    ids=sorted(i for i in O.ss if i in C.ss and lo<=O.ocd[i]['t_opportunity']<hi)
    line('SS on-time (scorer)',[(O.ss[i]['question_id'],int(C.ss[i]['on_time']),int(O.ss[i]['on_time'])) for i in ids],'SS questions')
    line('SS within_L (outcome)',[(O.ss[i]['question_id'],int(bool(C.ocd[i]['within_L'])),int(bool(O.ocd[i]['within_L']))) for i in ids],'SS questions')
    blk=60 if hi-lo>=120 else 10
    dc={};do={}
    for c,dd in((C,dc),(O,do)):
        for o in c.oc:
            if o['kind']=='monitor' and lo<=o['t_opportunity']<hi:dd[(o['device_id'],o['opportunity_id'])]=(int(o['t_opportunity']//blk),int(within(o,1.0)))
    ks=sorted(set(dc)&set(do))
    line('dashcam within_L',[(dc[k][0],dc[k][1],do[k][1]) for k in ks],'%d s blocks, %d instants; unmatched ctl %d out %d'%(blk,len(ks),len(dc)-len(ks),len(do)-len(ks)))
WINDOW='fixed'
def main():
    global WINDOW
    if '--window' in sys.argv: WINDOW=sys.argv[sys.argv.index('--window')+1]
    import re
    sm=re.search(r'_s(\d+)_',os.path.basename(sys.argv[1].rstrip('/')));SEED_ID=int(sm.group(1)) if sm else None
    od,cd,t0,d,label=sys.argv[1],sys.argv[2],float(sys.argv[3]),float(sys.argv[4]),sys.argv[5]
    js=sys.argv[sys.argv.index('--json')+1] if '--json' in sys.argv else None
    C,O=Cell(cd),Cell(od);T0=t0;R=t0+d;out=[];rec={}
    P=out.append
    P('== netwin %s  outage=%s  control=%s  t0=%.1f d=%.1f R=%.1f'%(label,O.name,C.name,T0,d,R))
    # positive control: control committed values
    cl=C.classify()
    n=len(C.rows);agree=sum(1 for i in C.rows if cl[i][1]==C.rob_cbd(i))
    cbd=sum(C.rob_cbd(i) for i in C.rows)
    P('POSITIVE CONTROL control: robot cbd rows %d, cbd True %d (committed robot_headline %.6f x n %d = %.1f); sylib classifier correct==committed cbd on %d of %d'%(n,cbd,C.sc['robot_headline']['correct_answers_delivered_by_deadline'],C.sc['robot_headline']['n_by_deadline'],C.sc['robot_headline']['correct_answers_delivered_by_deadline']*C.sc['robot_headline']['n_by_deadline'],agree,n))
    P('  control SS: n %d on_time %d (committed %d); within_L(outcomes) %d; dashcam within(1.0) %d vs within_L %d of %d monitors'%(len(C.ss),sum(r['on_time'] for r in C.ss.values()),C.sc['assistive_value']['on_time'],sum(bool(C.ocd[i]['within_L']) for i in C.ss),sum(within(o,1.0) for o in C.oc if o['kind']=='monitor'),sum(bool(o['within_L']) for o in C.oc if o['kind']=='monitor'),sum(1 for o in C.oc if o['kind']=='monitor')))
    clo=O.classify();no=len(O.rows)
    P('POSITIVE CONTROL outage: robot cbd rows %d True %d (headline %.6f x %d); classifier agree %d of %d; SS on_time %d (committed %d) within_L %d; dashcam within(1.0) %d vs within_L %d'%(no,sum(O.rob_cbd(i) for i in O.rows),O.sc['robot_headline']['correct_answers_delivered_by_deadline'],O.sc['robot_headline']['n_by_deadline'],sum(1 for i in O.rows if clo[i][1]==O.rob_cbd(i)),no,sum(r['on_time'] for r in O.ss.values()),O.sc['assistive_value']['on_time'],sum(bool(O.ocd[i]['within_L']) for i in O.ss),sum(within(o,1.0) for o in O.oc if o['kind']=='monitor'),sum(bool(o['within_L']) for o in O.oc if o['kind']=='monitor')))
    P('  same opportunity ids in both cells: robot %d/%d, SS %d/%d'%(len(set(O.rows)&set(C.rows)),len(O.rows),len(set(O.ss)&set(C.ss)),len(O.ss)))
    P('B_obs DEFINITION (fixed before outcomes): rate_W(t)=sum uncached prompt tokens of robot requests with t_submit in (t-W,t] / W, 1 s grid; ctl(t)=control rate at the same absolute time; sd=sd of control rate over [60,t0). DEF1=first t>=R, after outage rate first exceeds ctl+1sd, at which outage<=ctl+1sd. DEF2=last exceedance+1 s. Rule window = DEF1 at W=10; others sensitivity.')
    res={}
    for W in (5,10,20):
        b=bobs(C,O,T0,R,W);res[W]=b
        P('  W=%2d: ctl pre mean %.0f sd %.0f tok/s; first exceed R+%s; B_obs DEF1 %.0f s DEF2 %.0f s'%(W,b['mean'],b['sd'],('%.0f'%b['first_exceed']) if b['first_exceed'] is not None else 'never',b['def1'],b['def2']))
    b=res[10];g=b['grid']
    P('  rate trace W=10 (t-R,ctl,out): '+str([(int(x-R),int(b['rc'][i]),int(b['ro'][i])) for i,x in enumerate(g) if R-20<=x<=R+300 and int(x-R)%10==0]))
    dm=drain_marks(O,T0,R);P('  drain cross-check from outage log: %s'%{k:(round(v,1) if isinstance(v,float) else v) for k,v in dm.items()})
    vic=set((O.hdr.get('outage') or {}).get('robots',[]))
    dr=deficit_recovery(C,O,T0,R,vic);P('  deficit-recovery marker (victim robot uncached tokens, cum out minus ctl from t0): deficit at R %.0f tok; first t>=R with cum out>=ctl: %s; end-of-run diff %+.0f'%(dr['deficit_at_R_tokens'],('R+%.0f s'%dr['recovered_at']) if dr['recovered_at'] is not None else 'never',dr['end_diff']))
    B=b['def1']
    if B!=B: B=1200-R
    flag=''
    if B<30 or abs(res[5]['def1']-res[20]['def1'])>0.5*max(res[10]['def1'],1) : flag='UNSTABLE: DEF1 differs >50% across W or <30 s (bursty); DEF1(W=10) kept as rule'
    P('  DEF1 vs DEF2 vs drain: %.0f / %.0f / %s  %s'%(B,b['def2'],('%.0f'%dm['last_delayed_submit']) if dm['last_delayed_submit'] is not None else 'n/a',flag))
    if WINDOW=='def1':
        metrics(C,O,R,min(R+B,1201),'== PRIMARY windowed [R,R+B_obs DEF1 W=10]',out,rec)
        for W in (5,20):
            if res[W]['def1']==res[W]['def1']:metrics(C,O,R,R+res[W]['def1'],'== sensitivity W=%d DEF1=%.0f'%(W,res[W]['def1']),out,rec)
        metrics(C,O,R,min(R+b['def2'],1201),'== sensitivity DEF2 sustained=%.0f'%b['def2'],out,rec)
        if dm['last_delayed_submit'] and dm['last_delayed_submit']>0:metrics(C,O,R,min(R+dm['last_delayed_submit'],1201),'== sensitivity drain-marker=%.0f'%dm['last_delayed_submit'],out,rec)
        metrics(C,O,R,R+60,'== fixed [R,R+60] (reference)',out,rec)
    else:
        P('RULE WINDOW (user ruling, amends D332 item 8): every arm and seed scored over ONE FIXED [R,R+120]; sensitivity [R,R+60], [R,R+300]. B_obs DEF1/DEF2 above are DESCRIPTIVE per arm only (B_obs depends on the arm).')
        P('  B_obs descriptive (W=10): DEF1 %.0f s, DEF2 %.0f s (outage arm vs control-threshold)'%(B,b['def2']))
        metrics(C,O,R,min(R+120,1201),'== RULE fixed [R,R+120]',out,rec)
        metrics(C,O,R,min(R+60,1201),'== sensitivity fixed [R,R+60]',out,rec)
        metrics(C,O,R,min(R+300,1201),'== sensitivity fixed [R,R+300]',out,rec)
    metrics(C,O,T0,R,'== DURING-OUTAGE [t0,R] (beside)',out,rec)
    metrics(C,O,0,1201,'== WHOLE RUN (beside)',out,rec)
    # catch-up check
    P('CATCH-UP: uncached tokens (robot requests by t_submit)')
    for nm,lo,hi in (('[R,R+300]',R,R+300),('[R,R+B]',R,R+B),('[t0,R]',T0,R),('[R+B,R+300]',R+B,R+300)):
        r={}
        for tag,c in (('ctl',C),('out',O)):
            xs=[x for x in c.events() if lo<=x[0]<hi];r[tag]=(len(xs),sum(x[1] for x in xs))
        vc=set((O.hdr.get('outage') or {}).get('robots',[]))
        P('  %-12s ctl n=%d tok=%d | out n=%d tok=%d | out-ctl tok %+d (%+.1f%%)'%(nm,r['ctl'][0],r['ctl'][1],r['out'][0],r['out'][1],r['out'][1]-r['ctl'][1],100*(r['out'][1]-r['ctl'][1])/max(r['ctl'][1],1)))
    txt='\n'.join(out);print(txt)
    if js:json.dump(dict(seed=SEED_ID,window=WINDOW,label=label,t0=T0,d=d,R=R,B_obs=B,B_def2=b['def2'],rec=rec),open(js,'w'))
main()
