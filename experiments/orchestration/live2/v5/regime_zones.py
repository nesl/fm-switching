import gzip, json, os
W=100.0
def med(v):
    v=sorted(v); return v[len(v)//2] if v else None
allw=[]
for d in ("knee2/req","gate26/req"):
    if not os.path.isdir(d): continue
    for fn in sorted(os.listdir(d)):
        buck={}
        for l in gzip.open(os.path.join(d,fn),"rt"):
            r=json.loads(l); t=r.get("t_submit")
            if t is None: continue
            a=r.get("t_first_token")
            if r.get("http_status")==200 and a is not None:
                buck.setdefault(int(t//W),[]).append(a-t)
        for b,v in buck.items():
            m=med(v)
            if m is not None: allw.append((fn[:-9], b*W, m, len(v)))
print(f"total 100 s windows across {len({x[0] for x in allw})} cells: {len(allw)}")
vals=sorted(x[2] for x in allw)
import bisect
print("window ft_p50 percentiles:")
for p in (50,75,90,95,98,99,100):
    print(f"   p{p:<3d} {vals[min(len(vals)-1,int(p/100*len(vals)))]:9.3f} s")
print()
for lo,hi,name in ((0,2.781,"HEALTHY  (<= 2.781)"),(2.781,31.0,"MIDDLE   (2.781 to 31)"),(31.0,1e9,"COLLAPSED(> 31)")):
    sel=[x for x in allw if lo < x[2] <= hi] if lo>0 else [x for x in allw if x[2] <= hi]
    nreq=sum(x[3] for x in sel)
    print(f"{name:26s} windows {len(sel):5d} ({100*len(sel)/len(allw):5.1f}%)  requests {nreq:7d}  cells {len({x[0] for x in sel}):3d}")
mid=[x for x in allw if 2.781 < x[2] <= 31.0]
print("\nthe MIDDLE windows, all of them:")
for c,t,m,n in sorted(mid,key=lambda z:z[2]):
    print(f"   {m:8.3f} s  n={n:5d}  t={t:6.0f}  {c[:52]}")
