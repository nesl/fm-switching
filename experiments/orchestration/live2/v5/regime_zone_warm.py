import gzip, json, os
W=100.0; HEALTHY=2.781; COLLAPSED=31.0
def med(v):
    v=sorted(v); return v[len(v)//2] if v else None
tot={"healthy":[0,0],"middle":[0,0],"collapsed":[0,0]}
cells_h=set()
for d in ("knee2/req","gate26/req"):
    if not os.path.isdir(d): continue
    for fn in sorted(os.listdir(d)):
        rows=[json.loads(l) for l in gzip.open(os.path.join(d,fn),"rt")]
        buck={}
        for r in rows:
            t=r.get("t_submit")
            if t is None: continue
            a=r.get("t_first_token")
            if r.get("http_status")==200 and a is not None:
                buck.setdefault(int(t//W),[]).append(a-t)
        lab={}
        for b,v in buck.items():
            m=med(v)
            if m is None: continue
            lab[b]= "healthy" if m<=HEALTHY else ("middle" if m<=COLLAPSED else "collapsed")
        for r in rows:
            t=r.get("t_submit")
            if t is None: continue
            z=lab.get(int(t//W))
            if z is None: continue
            tot[z][0]+=1
            if (r.get("cached_tokens") or 0)>0: tot[z][1]+=1
            if z=="healthy": cells_h.add(fn[:-9])
print(f"{'zone':11s} {'requests':>9s} {'warm':>8s} {'warm %':>7s}")
for z,(n,w) in tot.items():
    print(f"{z:11s} {n:9d} {w:8d} {100*w/max(n,1):7.2f}")
print(f"\ncells contributing HEALTHY windows: {len(cells_h)}")
print(f"HEALTHY warm requests: {tot['healthy'][1]} -> a held-out split drawn from healthy "
      f"windows CAN contain warm rows")
