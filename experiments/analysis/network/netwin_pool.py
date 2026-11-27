#!/usr/bin/env python3
"""Pool netwin --json outputs. Question-clustered bootstrap, seed 7, 2000 reps.
usage: python3 -I netwin_pool.py --a f1.json [f2.json ...] [--b g1.json ...] [--tag SUBSTR] [--out out.txt]
One group (--a): pooled harm (ctl-out) per metric, CI over clusters (seed,unit).
Two groups (--a,--b): harm_A - harm_B per metric (clusters resampled independently per group);
 F0-vs-rung3 rule: A=F0, B=rung3; F0 robot cbd loss below rung3's => CI of (harmA-harmB) < 0 ; SS/dashcam no worse => CI not above 0 (<=0 ... reported).
Cluster = (seed, question) robot/SS, (seed, 60 s block) dashcam; seed from json 'seed' else file index. Cells with different seeds keep distinct clusters.
"""
import json,sys,random,collections
REPS=2000;SEED=7
def ci(v):
    v=sorted(v);return v[int(.025*len(v))],v[int(.975*len(v))-1]
def load(files):
    g=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0]));n=collections.Counter()
    for ix,f in enumerate(files):
        j=json.load(open(f));sd=j.get('seed');sd=ix if sd is None else sd
        for key,r in j['rec'].items():
            for k,a,b in r['units']:
                x=g[key][(sd,k)];x[0]+=a;x[1]+=b;n[key]+=1
    return g,n
def boot(cl,rng):
    ks=sorted(cl,key=str);return sum(cl[ks[rng.randrange(len(ks))]][0]-cl[ks[rng.randrange(len(ks))]][1] for _ in ks) if False else None
def harms(cl,rng):
    ks=sorted(cl,key=str);t=0
    for _ in ks:
        x=cl[ks[rng.randrange(len(ks))]];t+=x[0]-x[1]
    return t
def main():
    A=sys.argv[sys.argv.index('--a')+1:];
    for i,x in enumerate(A):
        if x.startswith('--'):A=A[:i];break
    B=[];
    if '--b' in sys.argv:
        B=sys.argv[sys.argv.index('--b')+1:]
        for i,x in enumerate(B):
            if x.startswith('--'):B=B[:i];break
    tag=sys.argv[sys.argv.index('--tag')+1] if '--tag' in sys.argv else ''
    ga,na=load(A);gb,nb=load(B) if B else (None,None)
    out=[];rng=random.Random(SEED)
    for key in sorted(ga):
        if tag not in key or (gb is not None and key not in gb):continue
        ca=ga[key];ha=sum(a-b for a,b in ca.values());la=sum(a for a,b in ca.values());oa=sum(b for a,b in ca.values())
        if gb is None:
            d=[harms(ca,rng) for _ in range(REPS)];l,h=ci(d)
            out.append('%-70s n=%d ctl %d out %d harm %+d CI[%+.0f,%+.0f] clusters=%d'%(key,na[key],la,oa,ha,l,h,len(ca)))
        else:
            cb=gb[key];hb=sum(a-b for a,b in cb.values())
            d=[harms(ca,rng)-harms(cb,rng) for _ in range(REPS)];l,h=ci(d)
            out.append('%-70s harmA %+d (n=%d,cl=%d) harmB %+d (n=%d,cl=%d) A-B %+d CI[%+.0f,%+.0f]'%(key,ha,na[key],len(ca),hb,nb[key],len(cb),ha-hb,l,h))
    txt='\n'.join(out);print(txt)
    if '--out' in sys.argv:open(sys.argv[sys.argv.index('--out')+1],'w').write(txt+'\n')
main()
