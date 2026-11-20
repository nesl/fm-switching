#!/usr/bin/env python3
"""SS timing for choosing the single-shot deadline (D142 item 4, overnight plan item 1).

32B TTFT for ONE single-shot (SS) request: (a) on an idle engine, (b) injected into a live b7 run of 12 or 16 devices,
dashcam : robot 50:50, push-all (robots LH-REQ if "lh-req ready" is on origin, else MIXED; labelled). 100 requests per
condition, the SAME 100 VizWiz val questions (seed 0 sample, excluding the 70 questions on byte-identical images so
every request is cold for both caches), sent through the StudySS1 kit's own body, prompt and preprocessing
(`ss1_kit`, `ss1_run.call`), one at a time, a unique cache_salt per request (no '/', vLLM 0.31.0).

Modes:
  idle    start the round-1 server; FIRST a prefix-cache POSITIVE CONTROL (separately logged): 3 kit requests each sent
          twice with unique salts (expect cached 0) and once more with a REPEATED salt (expect cached > 0), reading
          per-request usage.prompt_tokens_details.cached_tokens; then the 100 SS requests back to back; stop the server.
  inject  wait for a live run's decision log (the run passed its preflight and is deciding), then send one SS request
          every 5 s from emulator t ~ 60 s to the running server; never starts or stops a server.
Outputs: results/orchestration/live2/ss_timing/<condition>.json. No em dashes.
"""
import json
import random
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "results/orchestration/live2/ss_timing"
sys.path.insert(0, str(REPO / "experiments/casestudy"))
sys.path.insert(0, str(REPO / "experiments/orchestration"))
import ss1_kit as K            # noqa: E402
import ss1_run as R            # noqa: E402

EP = "http://127.0.0.1:8031/v1"
MODEL = "32BI"


def sample(n=100, seed=0):
    rows = R.load_rows(str(REPO / "results/casestudy/study_ss1/vizwiz_val_manifest.jsonl"), "all")
    dup = json.loads((REPO / "results/casestudy/study_ss1/vizwiz_shared_images.json").read_text())
    excl = {q for g in dup["groups"] for q in g}
    rows = [r for r in rows if r["qid"] not in excl]
    return random.Random(seed).sample(rows, n)


def one(row, salt, details=False):
    """One kit request; returns ttft, prompt tokens, output tokens, cached tokens (non-stream re-read if details)."""
    url = K.jpeg_data_url(str(R.image_path(row)))
    text, ttft, total, pt, ct = R.call(EP, MODEL, K.vizwiz_prompt(row["question"]), url, row["gen_max_new_tokens"], salt)
    rec = dict(qid=row["qid"], salt=salt, ttft_s=ttft, total_s=total, prompt_tokens=pt, completion_tokens=ct,
               t_sent_wall=time.time() - (total or 0.0))
    return rec


def cached_tokens(row, salt):
    """Non-streaming kit-identical body to read usage.prompt_tokens_details.cached_tokens per request."""
    body = dict(model=MODEL, temperature=0.0, seed=0, max_tokens=row["gen_max_new_tokens"], stream=False,
                cache_salt=salt, messages=[{"role": "user", "content": [
                    {"type": "text", "text": K.vizwiz_prompt(row["question"])},
                    {"type": "image_url", "image_url": {"url": K.jpeg_data_url(str(R.image_path(row)))}}]}])
    u = requests.post(EP + "/chat/completions", json=body, timeout=180).json().get("usage")
    # RAW, never coerced: absent and zero are different observations (vLLM 0.20.0 left this field null)
    det = (u or {}).get("prompt_tokens_details") if isinstance(u, dict) else None
    present = isinstance(det, dict) and ("cached_tokens" in det)
    raw = det.get("cached_tokens") if present else None
    return dict(usage_present=isinstance(u, dict), details_present=isinstance(det, dict), key_present=present,
                cached_tokens_raw=raw, prompt_tokens=(u or {}).get("prompt_tokens") if isinstance(u, dict) else None)


def summary(recs):
    xs = sorted(r["ttft_s"] for r in recs if r.get("ttft_s") is not None)
    q = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None   # noqa: E731
    return dict(n=len(xs), p50=q(0.50), p90=q(0.90), max=(xs[-1] if xs else None),
                prompt_tokens_p50=sorted(r["prompt_tokens"] or 0 for r in recs)[len(recs) // 2])


def idle():
    import study_live2_pilot as PL
    PL.OUT = OUT
    PL.WORK = Path.home() / "data/ss_timing"
    PL.WORK.mkdir(parents=True, exist_ok=True)
    rows = sample()
    srv, sinfo, _M = PL.start_server(27.0)
    try:
        ctl_rows = sample(3, seed=7)
        ctl = []
        for i, r in enumerate(ctl_rows):
            a = cached_tokens(r, "ctl-uniqA-%d-%d" % (i, time.time_ns()))
            b = cached_tokens(r, "ctl-uniqB-%d-%d" % (i, time.time_ns()))
            same = "ctl-same-%d-%d" % (i, time.time_ns())
            c1 = cached_tokens(r, same)
            c2 = cached_tokens(r, same)
            ctl.append(dict(qid=r["qid"], unique_salt_first=a, unique_salt_second=b, same_salt_first=c1, same_salt_repeat=c2))
        num = lambda v: isinstance(v["cached_tokens_raw"], int)                              # noqa: E731
        instrument_ok = all(num(x[k]) for x in ctl for k in ("unique_salt_first", "unique_salt_second",
                                                              "same_salt_first", "same_salt_repeat"))
        ok = bool(instrument_ok and all(x["unique_salt_second"]["cached_tokens_raw"] == 0 for x in ctl)
                  and all(x["same_salt_repeat"]["cached_tokens_raw"] > 0 for x in ctl))
        diagnosis = ("pass" if ok else "INSTRUMENT NOT REPORTING (cached_tokens absent or null): isolation unmeasured on this route"
                     if not instrument_ok else "FIELD POPULATED BUT THE PATTERN FAILED: a real finding about the prefix cache")
        (OUT / "prefix_cache_positive_control.json").write_text(json.dumps(dict(
            label="POSITIVE CONTROL for the StudySS1-32B prefix-cache isolation claim; run on a fresh server AFTER the "
                  "StudySS1-32B run, separately from it; its hits are the control's, not the run's",
            scope="a separate server start with the identical round-1 command: validates the mechanism and the instrument, "
                  "not the exact StudySS1-32B server process",
            pass_condition="every cached_tokens value present and an integer, AND unique-salt repeat == 0 AND same-salt repeat > 0",
            passed=ok, diagnosis=diagnosis, rows=ctl), indent=1) + "\n")
        recs = [one(r, "ssidle-%d-%d" % (i, time.time_ns())) for i, r in enumerate(rows)]
    finally:
        srv.stop()
    (OUT / "idle.json").write_text(json.dumps(dict(condition="idle", server=sinfo, summary=summary(recs), rows=recs),
                                              indent=1, default=str) + "\n")
    print("idle", summary(recs), "control passed", ok, flush=True)


def inject(label, run_dir, spacing_s=5.0, start_s=60.0):
    rows = sample()
    dl = Path(run_dir) / "decision.jsonl"
    while not (dl.exists() and dl.stat().st_size > 0):
        time.sleep(1.0)
    t0 = time.time()                 # first decision ~ emulator t 0
    recs = []
    for i, r in enumerate(rows):
        target = t0 + start_s + i * spacing_s
        time.sleep(max(target - time.time(), 0.0))
        try:
            rec = one(r, "ss-%s-%d-%d" % (label, i, time.time_ns()))
        except Exception as e:                                                  # noqa: BLE001
            rec = dict(qid=r["qid"], error=repr(e)[:200])
        rec["t_rel_s"] = round(time.time() - t0, 2)
        recs.append(rec)
    ok = [r for r in recs if "error" not in r]
    (OUT / ("%s.json" % label)).write_text(json.dumps(dict(condition=label, background_run=str(run_dir),
                                                           n_errors=len(recs) - len(ok), summary=summary(ok), rows=recs),
                                                      indent=1, default=str) + "\n")
    print(label, summary(ok), "errors", len(recs) - len(ok), flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == "idle":
        idle()
    else:
        inject(sys.argv[2], sys.argv[3])
