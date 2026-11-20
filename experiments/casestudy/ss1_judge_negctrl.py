"""EgoThink judge NEGATIVE CONTROL: the arm the +0.0623 has never faced.

Method carried over from the CODA-LM control: keep question A and its gold, but substitute the
ANSWER from question B. A judge reading content should score that near 0 on the 0/0.5/1 scale.

This bears on a number already committed: the EgoThink judge paired difference of +0.0623
[+0.0338, +0.0901]. If mismatched pairs score near the top as CODA-LM's did, that difference is
between two numbers that do not track correctness and the column should be WITHDRAWN rather than
caveated. If they score near 0, it is the only judge figure in either study with both arms of its
control.
"""
import json, sys, time, statistics, collections, requests
sys.path.insert(0, '/tmp/claude-1001/s3b/experiments/casestudy')
import ss1_kit as K

SRC='/tmp/claude-1001/s3b/results/casestudy/study_ss1/egothink_device_judge.json'
EP='http://127.0.0.1:8001/v1/chat/completions'
N=150

rows=[r for r in json.load(open(SRC))['rows'] if r.get('judge_rating') is not None]
print('available parsed rows:', len(rows))
sample=rows[:N]

def call(prompt):
    body=dict(model='mistral7b', temperature=0.0, seed=0, max_tokens=512, stream=False,
              messages=[{"role":"system","content":K.EGOTHINK_JUDGE_SYSTEM},
                        {"role":"user","content":prompt}])
    for att in range(4):
        try:
            r=requests.post(EP, json=body, timeout=180); r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
        except Exception as e:
            last=e; time.sleep(1.5*(att+1))
    raise last

out=[]
for i,r in enumerate(sample):
    other=sample[(i+1)%len(sample)]
    prompt=K.egothink_judge_prompt(r['question'], r['reference'], other['answer'])  # MISMATCHED answer
    txt=call(prompt)
    v=K.parse_judge_rating(txt)
    out.append(dict(qid=r['qid'], dimension=r.get('dimension'), answer_from=other['qid'],
                    rating=v, orig_rating=r['judge_rating'], raw=txt))
    if (i+1)%25==0: print('  %d/%d' % (i+1,len(sample)), flush=True)

ok=[o for o in out if o['rating'] is not None]
print()
print('parse: %d/%d' % (len(ok), len(out)))
v=[o['rating'] for o in ok]
print('MISMATCHED (expect near 0 on the 0/0.5/1 scale):')
print('  n=%d mean %.4f median %.1f  distribution %s' % (
  len(v), statistics.fmean(v), statistics.median(v), dict(sorted(collections.Counter(v).items()))))
orig=[o['orig_rating'] for o in ok]
print('  the SAME questions on their OWN answers: mean %.4f' % statistics.fmean(orig))
print('  gap (own minus mismatched): %+.4f' % (statistics.fmean(orig)-statistics.fmean(v)))
print('  fraction of mismatched scoring >= 0.5 (the binarisation used for agreement): %.1f%%' % (
  100*sum(1 for x in v if x>=0.5)/len(v)))
json.dump(out, open('/tmp/claude-1001/ego_negctrl.json','w'), indent=1)
