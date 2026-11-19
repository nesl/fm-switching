"""Requirement 2 for the S7 EVIDENCE slot, whose effect decision.jsonl does not record.

The standard move proof diffs decision.jsonl rows. That log carries no `representation` field, so
an arm that changes ONLY which evidence it asks for is invisible to it: builder-s7-always-recent
emits RECENT on every recall and still shows 0 differing rows. The observable here is therefore the
EMITTED ACTION, captured from the arm itself, not the logged decision.
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
root=Path('/tmp/claude-1001/s7'); root.mkdir(parents=True, exist_ok=True)

def run(name, ndev):
    tdir=root/('tr_n%d'%ndev)
    if not tdir.exists(): TR.write_trace(tdir, TR.generate_trace(SEED,ndev,'50:50',RUN_S,MODE))
    d=root/('%s_n%d'%(name,ndev)); d.mkdir(parents=True, exist_ok=True)
    arm=A.make_arm(name); htok=RC.host_tokens(HOST_GIB)
    arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok, targets=CS.TARGETS)
    reps=collections.Counter()
    raw=arm.decide
    def shim(obs):
        act=raw(obs)
        for r in act.recall:
            reps['%s/%s' % (r.decision, r.representation)] += 1
        return act
    arm.decide=shim
    logs=Logs(d/'run').open()
    co=Live2Coordinator(arm,None,[],gpu_kv_tokens=GPU_KV,host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok,upload_mode=MODE,window_s=RUN_S,drain_s=10.0,
                        seed=SEED,logs=logs,run_tag=CK.run_tag(SEED,name),dry_run=True)
    br=EmulatorBridge(co); br.kind='stub'
    EM.FleetEmulator(tdir,br,MODE,realtime=False,drain_s=10.0).run(d/'run')
    logs.close()
    st=dict(getattr(arm,'stats',{}) or {})
    return dict(arm=name, n_dev=ndev, emitted=dict(reps),
                s7_recent=st.get('s7_recent',0), s7_degraded=st.get('s7_degraded',0),
                s7_infeasible=st.get('s7_degrade_still_infeasible',0))

out=[]
for ndev in (8,12,16,32):
    base=run('builder-default',ndev)
    for n in ('builder-s7-always-recent','builder-s7-degrade'):
        r=run(n,ndev); r['base_emitted']=base['emitted']
        moved = r['emitted']!=base['emitted']
        r['moves_an_emitted_action']=moved
        out.append(r)
        print('n=%-3d %-28s emitted=%s moved=%s (recent=%d degraded=%d infeas=%d)' % (
            ndev, n, r['emitted'], moved, r['s7_recent'], r['s7_degraded'], r['s7_infeasible']), flush=True)
json.dump(out, open(root/'s7_moves.json','w'), indent=1, default=str)
