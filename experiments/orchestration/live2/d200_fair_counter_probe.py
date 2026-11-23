"""Does `covex-v6-fair`'s committed feed actually move a planner weight off 1.0?

Decides whether D200 1a's premise ("the two are decision-identical") holds for the pre-D177
`arms_v6fair` family, which is REGISTERED (arms.py:725) and whose completion hook calls
`self._cf_engine().counters.observe(...)` (arms_v6fair.py:131).
"""
import json, sys
from pathlib import Path
H = Path(__file__).resolve().parent
for p in (str(H), str(H/"fleet"), str(H/"v5"), str(H/"hybrid"), str(H.parent/"baselines")):
    if p not in sys.path: sys.path.insert(0, p)
sys.argv = ["x", "--arm", "covex-v6-fair", "--seed", "4", "--n", "16",
            "--run-s", "1200", "--cutoff-off"]
import arms as A
import cf_pd_one_cell as C
held = {}
_orig = A.ARMS["covex-v6-fair"]
A.ARMS["covex-v6-fair"] = lambda **kw: held.setdefault("arm", _orig(**kw))
C.main()
arm = held.get("arm")
out = {"arm_built": arm is not None}
if arm is not None:
    cf = arm._cf_engine()
    c = cf.counters
    d = c.as_dict()
    ws = {k: v["weight"] for k, v in d["devices"].items()}
    out.update(n_updates=d["n_updates"], gain=d["gain"], n_devices=len(ws),
               weights=ws, n_weight_not_1=sum(1 for v in ws.values() if abs(v-1.0) > 1e-12),
               max_weight=(max(ws.values()) if ws else None),
               stats_feed={k: v for k, v in dict(arm.stats).items()
                           if "deficit" in k or "fair" in k})
print("PROBE " + json.dumps(out, default=float))
