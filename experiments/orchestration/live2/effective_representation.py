"""What representation actually REACHES the charging path, after Policy.__call__ applies defaults?

The arm-level tally sees what decide() emitted. coordinator.py:249 calls `self.arm(obs)`, i.e.
interface.Policy.__call__, which runs apply_defaults BEFORE the coordinator sees the action
(interface.py:380). DEFAULTS["representation"] is "RECENT". So the EFFECTIVE representation may
differ from the emitted one, and the effective one is what cstate.tokens_for_representation reads.
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

SEED, RUN_S, MODE, NDEV = 4, 300.0, 'A', 8
root=Path('/tmp/claude-1001/effrep'); root.mkdir(parents=True, exist_ok=True)
tdir=root/'tr'
if not tdir.exists(): TR.write_trace(tdir, TR.generate_trace(SEED,NDEV,'50:50',RUN_S,MODE))

def run(name):
    d=root/name; d.mkdir(parents=True, exist_ok=True)
    arm=A.make_arm(name); htok=RC.host_tokens(HOST_GIB)
    arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok, targets=CS.TARGETS)
    emitted=collections.Counter()
    raw_decide=arm.decide
    def dshim(obs):
        act=raw_decide(obs)
        for r in act.recall: emitted['%s/%s'%(r.decision,r.representation)]+=1
        return act
    arm.decide=dshim
    logs=Logs(d/'run').open()
    co=Live2Coordinator(arm,None,[],gpu_kv_tokens=GPU_KV,host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok,upload_mode=MODE,window_s=RUN_S,drain_s=10.0,
                        seed=SEED,logs=logs,run_tag=CK.run_tag(SEED,name),dry_run=True)
    # capture the action AFTER Policy.__call__ has applied defaults: this is what the coordinator
    # enacts and what tokens_for_representation reads.
    effective=collections.Counter()
    inner=co.arm
    class _Proxy:
        """Forwards every attribute to the real arm; only __call__ is intercepted, so the
        coordinator's reads of arm.name and the rest are unaffected (PROBE_HAZARDS: a probe that
        replaces an object must keep the object's surface)."""
        def __call__(self, obs):
            act=inner(obs)
            for r in act.recall: effective['%s/%s'%(r.decision,r.representation)]+=1
            return act
        def __getattr__(self, k): return getattr(inner, k)
    co.arm=_Proxy()
    br=EmulatorBridge(co); br.kind='stub'
    EM.FleetEmulator(tdir,br,MODE,realtime=False,drain_s=10.0).run(d/'run')
    logs.close()
    return dict(arm=name, emitted_by_decide=dict(emitted), effective_after_defaults=dict(effective))

out=[]
for n in ('builder-default','simplestream','builder-s7-always-recent','b7-edf-feasibility','edf'):
    try:
        r=run(n); out.append(r)
        print('%-26s emitted=%-22s effective=%s' % (n, r['emitted_by_decide'], r['effective_after_defaults']), flush=True)
    except Exception as e:
        print('skip %s: %r' % (n, e), flush=True)
json.dump(out, open(root/'effective_rep.json','w'), indent=1, default=str)
