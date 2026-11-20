"""CODA-LM judge NEGATIVE CONTROL (Step 4) plus the length natural experiment.

The identity control is the same-salt arm: it proves a 10 CAN be produced. It cannot distinguish a
calibrated judge from a SATURATED one, because a judge that always answers 10 scores 75 of 75
identity pairs at exactly 10.0 with zero variance too. The permutation is the unique-salt arm.

PERMUTATION: judge scene A's reference against scene B's reference, per task. No new data, no
generation, just reindexing.

AND THE LENGTH TEST COMES FREE. Every permuted pair is WRONG BY CONSTRUCTION, so the mismatched set
is a single quality stratum with lengths varying across scenes. If longer predictions score higher
WITHIN that stratum, the judge is rewarding prose despite CODA-LM's explicit instruction not to.
That is the same within-stratum design used on EgoThink, where the same Mistral judge showed
+0.181 on a prompt with NO such instruction.
"""
import json, os, sys, time, statistics, collections, requests
sys.path.insert(0, '/tmp/claude-1001/s3b/experiments/casestudy')
import ss2_codalm_judge as J
import ss2_kit as K

VAL='/home/pragya/codalm_val'; EP='http://127.0.0.1:8001/v1/chat/completions'

def flat_general(d):
    out=[]
    for cat, items in (d or {}).items():
        if isinstance(items, list):
            for it in items: out.append('%s: %s %s' % (cat, it.get('description',''), it.get('explanation','')))
    return '\n'.join(out)
def flat_regional(d):
    return '\n'.join('%s: %s' % (v.get('category_name',''), v.get('description and explanation','')) for v in (d or {}).values())

def call(msgs):
    body=dict(model='mistral7b', temperature=0.0, seed=0, max_tokens=512, stream=False, messages=msgs)
    for att in range(4):
        try:
            r=requests.post(EP, json=body, timeout=180); r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
        except Exception as e:
            last=e; time.sleep(1.5*(att+1))
    raise last

files=sorted(f for f in os.listdir(VAL) if f.endswith('.json'))
refs={}
for fn in files:
    d=json.load(open(os.path.join(VAL,fn)))
    refs[fn]={'general':flat_general(d.get('general_perception')),
              'regional':flat_regional(d.get('region_perception')),
              'suggestion':str(d.get('driving_suggestion') or '')}

rows=[]
for i,fn in enumerate(files):
    other=files[(i+1)%len(files)]              # permute by one position
    for task in ('general','regional','suggestion'):
        ref=refs[fn][task]; pred=refs[other][task]
        if not ref.strip() or not pred.strip(): continue
        txt=call(J.build_messages(task, ref, pred))
        v,reason=K.parse_codalm_rating_detail(txt)
        rows.append(dict(scene=fn, pred_from=other, task=task, rating=v, reason=reason,
                         pred_words=len(pred.split()), raw=txt))
    if (i+1)%5==0: print('  %d/%d' % (i+1,len(files)), flush=True)

print()
print('parse: %d/%d  reasons %s' % (sum(1 for r in rows if r['rating'] is not None), len(rows),
                                    dict(collections.Counter(r['reason'] for r in rows))))
print()
print('NEGATIVE CONTROL (mismatched references, expect LOW):')
for task in ('general','regional','suggestion'):
    v=[r['rating'] for r in rows if r['task']==task and r['rating'] is not None]
    if v: print('  %-11s n=%2d mean %.2f median %.1f min %.1f max %.1f dist %s' % (
      task, len(v), statistics.fmean(v), statistics.median(v), min(v), max(v), dict(sorted(collections.Counter(v).items()))))
allv=[r['rating'] for r in rows if r['rating'] is not None]
print('  ALL         n=%2d mean %.2f' % (len(allv), statistics.fmean(allv)))
print()
print('LENGTH TEST within the mismatched stratum (all wrong by construction):')
ok=[r for r in rows if r['rating'] is not None]
srt=sorted(ok, key=lambda r: r['pred_words']); k=max(1,len(srt)//3)
lo=srt[:k]; hi=srt[-k:]
print('  short tercile n=%d mean words %.1f -> judge %.3f' % (len(lo), statistics.fmean(r['pred_words'] for r in lo), statistics.fmean(r['rating'] for r in lo)))
print('  long  tercile n=%d mean words %.1f -> judge %.3f' % (len(hi), statistics.fmean(r['pred_words'] for r in hi), statistics.fmean(r['rating'] for r in hi)))
print('  DELTA short->long: %+.3f on a 1-10 scale' % (statistics.fmean(r['rating'] for r in hi)-statistics.fmean(r['rating'] for r in lo)))
json.dump(rows, open('/tmp/claude-1001/codalm_negctrl.json','w'), indent=1)
