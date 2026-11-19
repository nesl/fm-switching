"""SimpleStream probe, WITH A POSITIVE CONTROL ON THE INSTRUMENT (PROBE_HAZARDS.md).

Every hazard in that file is silent: a probe that looks at the wrong place reports a number rather
than failing. So before any null here is trusted, the instrument is exercised against an arm KNOWN
to emit RECENT on every recall. If the instrument cannot see that, it cannot be trusted to see
SimpleStream either, and the run is void rather than negative.

Two independent routes are kept, per the same file: the emitted-action observable AND the decision
log. The log currently carries no `representation`, so its route is expected to be blind today;
that expectation is recorded so the cross-check is meaningful once the field lands.
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
from interface import validate_action, apply_defaults
from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK

SEED, RUN_S, MODE = 4, 300.0, 'A'
IDENT={'arm','arm_version','decision_latency_ms'}
root=Path('/tmp/claude-1001/sms'); root.mkdir(parents=True, exist_ok=True)

def run(name, ndev):
    tdir=root/('tr_n%d'%ndev)
    if not tdir.exists(): TR.write_trace(tdir, TR.generate_trace(SEED,ndev,'50:50',RUN_S,MODE))
    d=root/('%s_n%d'%(name,ndev)); d.mkdir(parents=True, exist_ok=True)
    arm=A.make_arm(name); htok=RC.host_tokens(HOST_GIB)
    # hazard 4: configure FIRST, then derive the shim, so nothing derived is stale
    arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok, targets=CS.TARGETS)
    reps=collections.Counter(); illegal=[]
    raw=arm.decide                      # instance attribute: resolved at call time, not a module name
    def shim(obs):
        act=raw(obs)
        # TALLY FIRST. apply_defaults MUTATES IN PLACE and DEFAULTS["representation"] == "RECENT",
        # so validating before tallying writes RECENT onto every CLOUD recall and the instrument
        # then reports RECENT for every arm, baseline included. Caught by the probe's own
        # NEGATIVE control: builder-default showed 9 RECENT emissions it never made.
        for r in act.recall: reps['%s/%s' % (r.decision, r.representation)] += 1
        try: validate_action(apply_defaults(act), obs)
        except Exception as e: illegal.append(repr(e))
        return act
    arm.decide=shim
    logs=Logs(d/'run').open()
    co=Live2Coordinator(arm,None,[],gpu_kv_tokens=GPU_KV,host_tier_gib=HOST_GIB,
                        host_tier_tokens=htok,upload_mode=MODE,window_s=RUN_S,drain_s=10.0,
                        seed=SEED,logs=logs,run_tag=CK.run_tag(SEED,name),dry_run=True)
    br=EmulatorBridge(co); br.kind='stub'
    EM.FleetEmulator(tdir,br,MODE,realtime=False,drain_s=10.0).run(d/'run')
    logs.close()
    rows=[json.loads(l) for l in open(d/'run'/'decision.jsonl')]
    canon=[json.dumps({k:v for k,v in r.items() if k not in IDENT},sort_keys=True) for r in rows]
    dg=json.load(open(d/'run'/'run_meta.json')).get('fairness_digest')
    return dict(arm=name, n_dev=ndev, emitted=dict(reps), n_illegal=len(illegal),
                illegal_sample=illegal[:2], digest=dg, canon=canon,
                kinds=dict(collections.Counter(r['kind'] for r in rows)))

NDEV = 8
base = run('builder-default', NDEV)
ctrl = run('builder-s7-always-recent', NDEV)      # POSITIVE CONTROL: must show RECENT
sms  = run('simplestream', NDEV)
b7   = run('b7-edf-feasibility', NDEV)

ctrl_recent = sum(v for k,v in ctrl['emitted'].items() if k.endswith('/RECENT'))
instrument_ok = ctrl_recent > 0
sms_recent = sum(v for k,v in sms['emitted'].items() if k.endswith('/RECENT'))

def diff(a,b):
    return sum(1 for x,y in zip(a['canon'],b['canon']) if x!=y)+abs(len(a['canon'])-len(b['canon']))

res=dict(n_dev=NDEV, seed=SEED,
 positive_control=dict(arm='builder-s7-always-recent', recent_emissions=ctrl_recent,
   instrument_sees_RECENT=instrument_ok,
   verdict=('INSTRUMENT VALIDATED' if instrument_ok else
            'INSTRUMENT BLIND: this run is VOID, not negative')),
 simplestream=dict(emitted=sms['emitted'], recent_emissions=sms_recent,
   n_illegal=sms['n_illegal'], illegal_sample=sms['illegal_sample'],
   digest=sms['digest'], kinds=sms['kinds']),
 baseline=dict(emitted=base['emitted'], digest=base['digest'], kinds=base['kinds']),
 digests_identical=(sms['digest']==base['digest']==b7['digest']==ctrl['digest']),
 route_emitted_action=dict(simplestream_vs_baseline_differs=(sms['emitted']!=base['emitted'])),
 route_decision_log=dict(simplestream_vs_baseline_differing_rows=diff(sms,base),
   control_vs_baseline_differing_rows=diff(ctrl,base),
   expected='0 for the control today, because decision.jsonl carries no representation column '
            '(PROBE_HAZARDS.md hazard 2). A non-zero here once the field lands is the cross-check.'))
print(json.dumps(res, indent=1))
json.dump(res, open(root/'simplestream_probe.json','w'), indent=1)
