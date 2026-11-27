#!/usr/bin/env python3
"""Absolute outage-cell comparison A minus B (SECONDARY readout; D332 harm rule stays the verdict).
usage: python3 -I netwin_abs.py --a a1.json [a2.json ...] --b b1.json [...] [--windows 120,60,300,whole] [--out FILE]
Uses `rec` units (cluster, ctl, out) of netwin.py --json: the `out` column is the outage-cell outcome, `ctl` the arm's own control.
Clusters (seed, question) robot/SS, (seed, block) dashcam; paired bootstrap over clusters present in either arm (same trace => same clusters),
seed 7, 2000 reps. Also prints each arm's control level beside."""
import json,sys,random,collections
REPS=2000;SEED=7
def ci(v):
    v=sorted(v);return v[int(.025*len(v))],v[int(.975*len(v))-1]
def grp(a):
    i=a.index('--a')+1
    r=[]
    for x in a[i:]:
        if x.startswith('--'):break
        r.append(x)
    return r
def load(files):
    g=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0]));n=collections.Counter()
    for ix,f in enumerate(files):
        j=json.load(open(f));sd=j.get('seed');sd=ix if sd is None else sd
        for key,r in j['rec'].items():
            for k,c,o in r['units']:
                x=g[key][(sd,k)];x[0]+=c;x[1]+=o;n[key]+=1
    return g,n
WN={'120':'fixed [R,R+120]','60':'fixed [R,R+60]','300':'fixed [R,R+300]','whole':'WHOLE RUN'}
def main():
    A=grp(sys.argv);B=grp(['--a']+sys.argv[sys.argv.index('--b'):]) if False else None
    bi=sys.argv.index('--b')+1;B=[]
    for x in sys.argv[bi:]:
        if x.startswith('--'):break
        B.append(x)
    ws=(sys.argv[sys.argv.index('--windows')+1] if '--windows' in sys.argv else '120,60,300,whole').split(',')
    ga,na=load(A);gb,nb=load(B);out=[]
    out.append('ABSOLUTE outage-cell difference A minus B (SECONDARY, not the D332 verdict). A=%s | B=%s'%(','.join(A),','.join(B)))
    out.append('seeds in A/B: %s / %s'%(sorted({json.load(open(f)).get('seed') for f in A}),sorted({json.load(open(f)).get('seed') for f in B})))
    for w in ws:
        out.append('== window %s'%WN[w])
        for m in ('robot cbd','robot cloud on-time','SS on-time (scorer)','dashcam within_L'):
            ka=[k for k in ga if WN[w] in k and k.endswith('|'+m)]
            if w=='whole': ka=[k for k in ga if 'WHOLE RUN' in k and k.endswith('|'+m)]
            if not ka: continue
            k=ka[0];ca=ga[k];cb=gb[k];ks=sorted(set(ca)|set(cb),key=str)
            sa=sum(v[1] for v in ca.values());sb=sum(v[1] for v in cb.values())
            ra=sum(v[0] for v in ca.values());rb=sum(v[0] for v in cb.values())
            rng=random.Random(SEED);d=[]
            for _ in range(REPS):
                t=0
                for _ in ks:
                    q=ks[rng.randrange(len(ks))];t+=ca.get(q,[0,0])[1]-cb.get(q,[0,0])[1]
                d.append(t)
            l,h=ci(d)
            out.append('  %-20s nA=%d nB=%d | outage A %d B %d | A-B %+d CI[%+.0f,%+.0f] clusters=%d | own control A %d B %d (A-B %+d)'%(m,na[k],nb[k],sa,sb,sa-sb,l,h,len(ks),ra,rb,ra-rb))
    txt='\n'.join(out);print(txt)
    if '--out' in sys.argv:open(sys.argv[sys.argv.index('--out')+1],'w').write(txt+'\n')
main()
