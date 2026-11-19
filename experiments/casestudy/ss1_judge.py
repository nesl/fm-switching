#!/usr/bin/env python3
"""StudySS1 EgoThink scorer (a): the open-judge pass. Reads an EgoThink run JSON (model answers),
runs EgoThink's own `single-math-v2` judge prompt through an open non-Qwen3-VL model
(Mistral-7B-Instruct-v0.2) served at an OpenAI-compatible endpoint, parses the 0 / 0.5 / 1 rating,
and reports the judge score and its agreement with scorer (b) containment. The judge is a TEXT
model and is NOT shown the image (as EgoThink's protocol stipulates). Greedy. No em dashes.

Usage:
  python3 ss1_judge.py --run results/casestudy/study_ss1/egothink_pilot_device.json \
      --endpoint http://127.0.0.1:8001/v1 --model mistral7b \
      --out results/casestudy/study_ss1/egothink_pilot_device_judge.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ss1_kit as K   # noqa: E402


def judge_call(endpoint, model, prompt, timeout=120, retries=4):
    body = dict(model=model, temperature=0.0, seed=0, max_tokens=512, stream=False,
                messages=[{"role": "system", "content": K.EGOTHINK_JUDGE_SYSTEM},
                          {"role": "user", "content": prompt}])
    last = None
    for att in range(retries + 1):
        try:
            r = requests.post(endpoint.rstrip("/") + "/chat/completions", json=body, timeout=timeout)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last = e
            time.sleep(1.5 * (att + 1))
    raise last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="an EgoThink run JSON from ss1_run.py")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8001/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    run = json.loads(Path(a.run).read_text())
    assert run["dataset"] == "egothink", "the judge pass is EgoThink only"
    rows = [r for r in run["rows"] if "error" not in r]
    out = []
    t0 = time.time()
    n_unparsed = 0
    for i, r in enumerate(rows):
        prompt = K.egothink_judge_prompt(r["question"], r["references"][0], r["answer"])
        text = judge_call(a.endpoint, a.model, prompt)
        rating = K.parse_judge_rating(text)
        if rating is None:
            n_unparsed += 1
        out.append(dict(qid=r["qid"], dimension=r.get("dimension"), area=r.get("area"),
                        question=r["question"], reference=r["references"][0], answer=r["answer"],
                        judge_rating=rating, containment=r["score"].get("containment"),
                        judge_raw=text[:800]))
        if (i + 1) % 25 == 0 or i == len(rows) - 1:
            print("  judge %d/%d unparsed=%d elapsed=%.0fs" %
                  (i + 1, len(rows), n_unparsed, time.time() - t0), flush=True)

    scored = [o for o in out if o["judge_rating"] is not None]
    jvals = [o["judge_rating"] for o in scored]
    # agreement with containment: treat judge>=0.5 as "correct-ish"; containment is 0/1
    agree = sum(1 for o in scored if (o["judge_rating"] >= 0.5) == (o["containment"] >= 0.5))
    res = dict(study="StudySS1", pass_="egothink_judge", judge_model=a.model,
               judge_prompt="EgoThink single-math-v2 (text judge, image withheld), rating 0/0.5/1",
               source_run=a.run, n=len(rows), n_scored=len(scored), n_unparsed=n_unparsed,
               judge_mean=(sum(jvals) / len(jvals) if jvals else None),
               containment_mean=(sum(o["containment"] for o in scored) / len(scored)
                                 if scored else None),
               judge_vs_containment_agreement=(agree / len(scored) if scored else None),
               seconds=time.time() - t0, rows=out)
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    print("wrote", a.out, "judge_mean", res["judge_mean"], "agreement",
          res["judge_vs_containment_agreement"], "unparsed", n_unparsed)


if __name__ == "__main__":
    main()
