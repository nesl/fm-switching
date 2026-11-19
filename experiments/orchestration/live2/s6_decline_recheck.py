"""s6-decline re-check: decision.jsonl cannot tell DEVICE from REJECT (coordinator.py:446-455
logs both as kind "decline"), so the earlier decision-row null is UNINFORMATIVE. outcomes.jsonl
DOES record `decision`, so this settles it now without waiting for the logging change.
"""
import json, sys, collections
from pathlib import Path
WT = Path('/tmp/claude-1001/s3b')
L2 = WT/'experiments/orchestration/live2'; RT = WT/'experiments/orchestration'
for p in (str(L2), str(L2/'fleet'), str(L2/'scorer'), str(L2/'data'), str(L2/'tests'),
          str(RT), str(RT/'live'), str(RT/'baselines'), str(RT/'sim'), str(WT/'experiments/lib')):
    if p not in sys.path: sys.path.insert(0, p)
import arms as A, cstate as CS, run_live2_cell as RC, cachekeys as CK
import fleet.trace as TR, fleet.emulator as EM
from coordinator import Live2Coordinator, Logs
from bridge import EmulatorBridge
from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK

SEED, RUN_S, MODE = 4, 300.0, 'A'
root=Path('/tmp/claude-1001/s6'); root.mkdir(parents=True, exist_ok=True)

def run(name, ndev):
    tdir=root/('tr_n%d'%ndev)
    if not tdir.exists(): TR.write_trace(tdir, TR.generate_trace(SEED,ndev,'50:50',RUN_S,MODE))
    d=root/('%s_n%d'%(name,ndev)); d.mkdir(parents=True, exist_ok=True)
    arm=A.make_arm(name); htok=RC.host_tokens(HOST_GIB)
    arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok, targets=CS.TARGETS)
    emitted=collections.Counter()
    raw=arm.decide
    def shim(obs):
        act=raw(obs)
        for r in act.recall: emitted[r.decision]+=1
        return act
    arm.decide=shim
    logs=Logs(d/'run').open()
    co=Live2Coordinator(arm,None,[],gpu_kv_tokens=GPU_KV,host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok,upload_mode=MODE,window_s=RUN_S,drain_s=10.0,
                        seed=SEED,logs=logs,run_tag=CK.run_tag(SEED,name),dry_run=True)
    br=EmulatorBridge(co); br.kind='stub'
    EM.FleetEmulator(tdir,br,MODE,realtime=False,drain_s=10.0).run(d/'run')
    logs.close()
    outs=[json.loads(l) for l in open(d/'run'/'outcomes.jsonl')]
    dec=collections.Counter(str(o.get('decision')) for o in outs if o.get('kind')=='recall')
    served=collections.Counter(str(o.get('served_by')) for o in outs if o.get('kind')=='recall')
    rows=[json.loads(l) for l in open(d/'run'/'decision.jsonl')]
    return dict(arm=name, n_dev=ndev, emitted_by_arm=dict(emitted),
                outcome_decision=dict(dec), outcome_served_by=dict(served),
                decision_kinds=dict(collections.Counter(r['kind'] for r in rows)))

out=[]
for ndev in (16,32):
    for n in ('builder-default','builder-s6-decline'):
        r=run(n,ndev); out.append(r)
        print('n=%-3d %-24s emitted=%s | outcome.decision=%s | kinds=%s' % (
            ndev, n, r['emitted_by_arm'], r['outcome_decision'], r['decision_kinds']), flush=True)
json.dump(out, open(root/'s6_recheck.json','w'), indent=1, default=str)
