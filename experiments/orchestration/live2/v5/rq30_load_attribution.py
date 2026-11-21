import gzip, json, os
from collections import defaultdict
RUN=1200.0
def kind(r):
    s=r.get("session_id") or ""
    return "robot" if s.startswith("robo") else ("single_shot" if s.startswith("asst") else "dashcam")
print(f"{'cell':14s} {'kind':12s} {'n':>6s} {'unc_tok':>10s} {'tok/s':>8s} {'share':>6s}")
tot={}
for fn in sorted(os.listdir(".")):
    if not fn.endswith(".gz"): continue
    arm = fn.split("_n16")[0]
    rows=[json.loads(l) for l in gzip.open(fn,"rt")]
    agg=defaultdict(lambda:[0,0])
    for r in rows:
        if r.get("t_submit") is None: continue
        u=max(0,(r.get("prompt_tokens") or 0)-(r.get("cached_tokens") or 0))
        k=kind(r); agg[k][0]+=1; agg[k][1]+=u
    T=sum(v[1] for v in agg.values())
    tot[arm]=dict(total_unc=T, by=dict(agg))
    for k in ("dashcam","robot","single_shot"):
        n,u=agg.get(k,[0,0])
        print(f"{arm[:14]:14s} {k:12s} {n:6d} {u:10d} {u/RUN:8.1f} {100*u/max(T,1):5.1f}%")
    print(f"{arm[:14]:14s} {'TOTAL':12s} {sum(v[0] for v in agg.values()):6d} {T:10d} {T/RUN:8.1f}")
    print()
a="v5-rules-2"; b="hybrid-F-lhreq-noc3"
if a in tot and b in tot:
    print("=== v5-rules-2 MINUS noc3, by kind (uncached tok/s):")
    for k in ("dashcam","robot","single_shot"):
        ua=tot[a]["by"].get(k,[0,0])[1]; ub=tot[b]["by"].get(k,[0,0])[1]
        na=tot[a]["by"].get(k,[0,0])[0]; nb=tot[b]["by"].get(k,[0,0])[0]
        print(f"   {k:12s} requests {na-nb:+6d}   tok/s {(ua-ub)/RUN:+9.1f}")
    print(f"   {'TOTAL':12s} {'':15s} tok/s {(tot[a]['total_unc']-tot[b]['total_unc'])/RUN:+9.1f}")
