"""CODA-LM judge POSITIVE CONTROL: score the reference answer against ITSELF.

CLAUDE.md check 7: a known-good input must pass the check being applied, and if it fails the CHECK
is broken rather than the arm. The reference IS the gold standard by construction, so an identity
pair (prediction == reference) should sit at the top of the 1-10 scale. This also validates the new
parser on LIVE judge output rather than test vectors, and exercises the reason codes.

The paper cannot supply this anchor: its Table 2 numbers had HUMAN VERIFICATION of the GPT-4
evaluations (sec 4.2), so its published Text-Scores cannot calibrate our unverified pipeline.
"""
import json, os, sys, time, requests
sys.path.insert(0, '/tmp/claude-1001/s3b/experiments/casestudy')
import ss2_codalm_judge as J
import ss2_kit as K

VAL='/home/pragya/codalm_val'
EP='http://127.0.0.1:8001/v1/chat/completions'

def flatten_general(d):
    out=[]
    for cat, items in (d or {}).items():
        if isinstance(items, list):
            for it in items:
                out.append('%s: %s %s' % (cat, it.get('description',''), it.get('explanation','')))
    return '\n'.join(out)

def flatten_regional(d):
    return '\n'.join('%s: %s' % (v.get('category_name',''), v.get('description and explanation',''))
                     for v in (d or {}).values())

def call(msgs):
    body=dict(model='mistral7b', temperature=0.0, seed=0, max_tokens=512, stream=False, messages=msgs)
    for att in range(4):
        try:
            r=requests.post(EP, json=body, timeout=180); r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
        except Exception as e:
            last=e; time.sleep(1.5*(att+1))
    raise last

rows=[]
files=sorted(f for f in os.listdir(VAL) if f.endswith('.json'))
for i,fn in enumerate(files):
    d=json.load(open(os.path.join(VAL,fn)))
    for task, ref in (('general', flatten_general(d.get('general_perception'))),
                      ('regional', flatten_regional(d.get('region_perception'))),
                      ('suggestion', str(d.get('driving_suggestion') or ''))):
        if not ref.strip(): continue
        txt=call(J.build_messages(task, ref, ref))     # IDENTITY: prediction == reference
        v,reason=K.parse_codalm_rating_detail(txt)
        rows.append(dict(scene=fn, task=task, rating=v, reason=reason, raw=txt[:300]))
    if (i+1)%5==0: print('  %d/%d scenes' % (i+1,len(files)), flush=True)

import statistics, collections
print()
gate=K.parser_gate([r['raw'] for r in rows])
print('PARSER GATE on live output:', {k:gate[k] for k in ('n','n_parsed','parse_rate','reason_breakdown','out_of_range_n','gate')})
print()
print('IDENTITY POSITIVE CONTROL (prediction == reference, expect top of scale):')
for task in ('general','regional','suggestion'):
    v=[r['rating'] for r in rows if r['task']==task and r['rating'] is not None]
    if v:
        print('  %-11s n=%2d  mean %.2f  median %.1f  min %.1f  max %.1f  dist %s' % (
          task, len(v), statistics.fmean(v), statistics.median(v), min(v), max(v),
          dict(sorted(collections.Counter(v).items()))))
allv=[r['rating'] for r in rows if r['rating'] is not None]
print('  ALL         n=%2d  mean %.2f' % (len(allv), statistics.fmean(allv)))
json.dump(dict(rows=rows, gate=gate), open('/tmp/claude-1001/codalm_control.json','w'), indent=1)
