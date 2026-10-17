"""StudyU — break the size/machine confound in the SDPA vs flash-attn throughput result. TIMING ONLY.

A6000 (4B/8B): SDPA tok/s collapses with generated length, flash-attn holds. H100 (32B): both flat, flash 0.79x.
Model size and machine are confounded. This study runs Qwen3-VL-8B-Thinking on the H100 under BOTH backends.

Phases (run in this order by the chain):
  select     pick 40 ERQA questions spanning generated length, from committed traces (4B-T A6000, 32B-T H100
             SDPA + flash-attn): rank by the longest trace any of them produced; take the 20 longest, the 10 around
             the median rank, and 10 evenly spaced over the shorter half. Written to study_u_selection.json.
  natural    8B-T, both backends loaded in ONE process (two model copies), each question run back to back under
             both, order alternating per question (even selection index -> sdpa first). CFG-A sampling,
             max_new_tokens=16384, set_seed(42 + question_id) before each generate (same seed both backends).
  forced8    LABELLED PROBE, not pooled: 8B-T, the 4 longest-ranked questions, min_new_tokens=max_new_tokens=16384.
  forced32   LABELLED PROBE, not pooled: 32B-T, the 2 longest-ranked questions, forced 16384; the two backends are
             loaded sequentially (two 32B copies do not fit), so this arm is cross-load (same process).

Per trial: n_generated, latency, TTFT, and a per-step timestamp series (stopping-criterion hook with a CUDA sync;
HF generate already syncs every step) -> ms/token vs generation position. attn_implementation asserted at load
and recorded per trial. No accuracy is recorded (timing study).

A file `logs/study_u_current.json` names the in-flight trial so the GPU-3 watchdog can record it on a halt.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from transformers import (AutoProcessor, Qwen3VLForConditionalGeneration, StoppingCriteria,
                          StoppingCriteriaList, set_seed)

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r_erqa as R  # noqa: E402
from _provenance import stamp  # noqa: E402

REPO = {
    "8BT":  ("Qwen/Qwen3-VL-8B-Thinking",  "92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b"),
    "32BT": ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1"),
}
BACKENDS = ("sdpa", "flash_attention_2")
DEVICE_SLUG = "h100nvl"
OUT_DIR = Path("results/erqa/study_u")
SEL_PATH = OUT_DIR / "study_u_selection.json"
TRIALS_PATH = OUT_DIR / f"study_u_trials_{DEVICE_SLUG}.jsonl"
STEPS_PATH = OUT_DIR / f"study_u_steps_{DEVICE_SLUG}.jsonl"
META_PATH = OUT_DIR / f"study_u_run_meta_{DEVICE_SLUG}.json"
CURRENT = Path("logs/study_u_current.json")
MAX_NEW = 16384
GEN = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, max_new_tokens=MAX_NEW)
N_FORCED8, N_FORCED32 = 4, 2


# --------------------------------------------------------------------------- selection

def select():
    src = {}
    for f, arm, label in [("results/erqa/study_r/study_r_trials_h100nvl.jsonl", "B", "4BT_a6000"),
                          ("results/erqa/study_r/study_r_trials_h100nvl.jsonl", "D", "32BT_h100_sdpa"),
                          ("results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl", "D", "32BT_h100_fa2")]:
        for r in map(json.loads, open(f)):
            if r["arm"] != arm:
                continue
            n = r.get("n_generated") or (r["n_think_tokens"] + r["n_answer_tokens"])  # B (reused) lacks n_generated
            src.setdefault(r["question_id"], {})[label] = n
    assert len(src) == 400 and all(len(v) == 3 for v in src.values())
    ranked = sorted(src, key=lambda q: (-max(src[q].values()), q))
    longest = ranked[:20]
    mid = ranked[195:205]
    lower = ranked[205:]
    short = [lower[int(round(i))] for i in np.linspace(0, len(lower) - 1, 10)]
    sel = longest + mid + short
    assert len(set(sel)) == 40
    out = dict(rule="rank 400 ERQA qids by max(prior n_generated over 4BT_a6000, 32BT_h100_sdpa, 32BT_h100_fa2); "
                    "20 longest + ranks 195-204 + 10 evenly spaced over ranks 205-399",
               questions=[dict(question_id=q, stratum=("long" if i < 20 else "mid" if i < 30 else "short"),
                               prior_max=max(src[q].values()), prior=src[q]) for i, q in enumerate(sel)],
               forced8=longest[:N_FORCED8], forced32=longest[:N_FORCED32])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SEL_PATH.write_text(json.dumps(out, indent=1))
    print(f"selection written: prior max long {[src[q] for q in longest[:3]]} ...", flush=True)
    return out


# --------------------------------------------------------------------------- model / timing

class StepClock(StoppingCriteria):
    """Records a synchronised timestamp after every generated token. Never stops generation."""
    def __init__(self):
        self.t = []

    def __call__(self, input_ids, scores, **kw):
        torch.cuda.synchronize()
        self.t.append(time.perf_counter())
        return torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)


def load(key, attn):
    from huggingface_hub import snapshot_download
    repo, rev = REPO[key]
    path = snapshot_download(repo, revision=rev, local_files_only=True)
    t0 = time.time()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation=attn).eval()
    got = model.config._attn_implementation
    if got != attn:
        raise SystemExit(f"!!! ATTENTION BACKEND ASSERT FAILED: requested {attn}, model uses {got} — aborting !!!")
    proc = AutoProcessor.from_pretrained(path)
    nbytes = sum(p.numel() * p.element_size() for p in model.parameters())
    info = dict(key=key, repo=repo, revision=rev, attn_implementation=got, load_s=round(time.time() - t0, 1),
                param_bytes_gb=round(nbytes / 1e9, 2),
                allocated_after_load_gb=round(torch.cuda.memory_allocated(0) / 1e9, 2))
    print(f"Loaded {key}/{attn}: {info}", flush=True)
    return model, proc, info


def warmup(model, proc, ds):
    msgs, _ = R.build_messages(ds[0])
    with torch.no_grad():
        model.generate(**R.prepare(proc, msgs), do_sample=False, max_new_tokens=32)
    torch.cuda.synchronize()


def run_trial(model, proc, ds, qid, key, attn, phase, order, forced=False):
    got = model.config._attn_implementation
    assert got == attn, (got, attn)
    msgs, _ = R.build_messages(ds[qid])
    inputs = R.prepare(proc, msgs)
    n_in = int(inputs["input_ids"].shape[1])
    gen = dict(GEN)
    if forced:
        gen["min_new_tokens"] = MAX_NEW
    clock = StepClock()
    wall_start = datetime.now().isoformat()
    CURRENT.write_text(json.dumps(dict(phase=phase, model=key, attn=attn, question_id=qid, wall_start=wall_start,
                                       pid=os.getpid())))
    set_seed(42 + qid)
    torch.cuda.reset_peak_memory_stats(0)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**inputs, **gen, stopping_criteria=StoppingCriteriaList([clock]))
    torch.cuda.synchronize()
    t1 = time.perf_counter()
    wall_end = datetime.now().isoformat()
    gen_ids = out[0][n_in:]
    n_gen = int(gen_ids.shape[0])
    text = proc.decode(gen_ids, skip_special_tokens=True)
    ts = np.array(clock.t)
    if len(ts) != n_gen:
        print(f"WARN step-clock count {len(ts)} != n_generated {n_gen} (q{qid} {attn})", flush=True)
    lat = t1 - t0
    ttft = ts[0] - t0 if len(ts) else None
    steps_ms = np.diff(ts) * 1000 if len(ts) > 1 else np.array([])
    tid = f"{phase}:{key}:{attn}:q{qid}"
    trial = dict(
        trial_id=tid, phase=phase, model=key, revision=REPO[key][1], attn_implementation=got, question_id=qid,
        order=order, forced_min_new_tokens=MAX_NEW if forced else None, seed=42 + qid,
        decoding=("CFG-A temp0.6/top_p0.95/top_k20/min_p0/do_sample" if gen.get("do_sample") else "greedy"),
        max_new_tokens=MAX_NEW,
        n_input_tokens=n_in, n_generated=n_gen, latency_ms=round(lat * 1000, 1),
        ttft_ms=round(ttft * 1000, 1) if ttft is not None else None,
        tok_s=round(n_gen / lat, 3), ms_per_token=round(lat * 1000 / n_gen, 3),
        decode_ms_per_token_median=round(float(np.median(steps_ms)), 3) if len(steps_ms) else None,
        n_step_stamps=len(ts), budget_hit=n_gen >= MAX_NEW, think_closed="</think>" in text,
        peak_alloc_gb=round(torch.cuda.max_memory_allocated(0) / 1e9, 2),
        peak_reserved_gb=round(torch.cuda.max_memory_reserved(0) / 1e9, 2),
        wall_start=wall_start, wall_end=wall_end, _hardware=DEVICE_SLUG,
        _cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"), _pid=os.getpid(),
    )
    with open(TRIALS_PATH, "a") as f:
        f.write(json.dumps(trial) + "\n")
    with open(STEPS_PATH, "a") as f:
        f.write(json.dumps(dict(trial_id=tid, ttft_ms=trial["ttft_ms"],
                                step_ms=[round(float(x), 3) for x in steps_ms])) + "\n")
    CURRENT.write_text(json.dumps(dict(idle_after=tid, at=wall_end)))
    print(f"[{phase}] {key} {attn:17s} q{qid:<3d} in={n_in:5d} gen={n_gen:5d} lat={lat:7.1f}s "
          f"{trial['tok_s']:6.2f} tok/s  step-med {trial['decode_ms_per_token_median']} ms "
          f"closed={trial['think_closed']}", flush=True)
    return trial


def done_ids():
    if not TRIALS_PATH.exists():
        return set()
    return {json.loads(l)["trial_id"] for l in open(TRIALS_PATH)}


def run_natural_and_forced8(ds, sel):
    models = {a: load("8BT", a) for a in BACKENDS}
    for a, (m, p, _) in models.items():
        warmup(m, p, ds)
    done = done_ids()
    qs = [q["question_id"] for q in sel["questions"]]
    for i, qid in enumerate(qs):
        order = BACKENDS if i % 2 == 0 else BACKENDS[::-1]
        for k, a in enumerate(order):
            if f"natural:8BT:{a}:q{qid}" in done:
                continue
            m, p, _ = models[a]
            run_trial(m, p, ds, qid, "8BT", a, "natural", order=k + 1)
    for i, qid in enumerate(sel["forced8"]):
        order = BACKENDS if i % 2 == 0 else BACKENDS[::-1]
        for k, a in enumerate(order):
            if f"forced8:8BT:{a}:q{qid}" in done:
                continue
            m, p, _ = models[a]
            run_trial(m, p, ds, qid, "8BT", a, "forced8", order=k + 1, forced=True)
    return {a: info for a, (_, _, info) in models.items()}


def run_forced32(ds, sel):
    infos = {}
    done = done_ids()
    for a in BACKENDS:
        m, p, info = load("32BT", a)
        infos[a] = info
        warmup(m, p, ds)
        for qid in sel["forced32"]:
            if f"forced32:32BT:{a}:q{qid}" not in done:
                run_trial(m, p, ds, qid, "32BT", a, "forced32", order=1, forced=True)
        del m, p
        torch.cuda.empty_cache()
    return infos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["select", "eight", "forced32"], required=True,
                    help="eight = natural + forced8 (one 8B process)")
    args = ap.parse_args()
    if args.phase == "select":
        select()
        return
    sel = json.loads(SEL_PATH.read_text())
    ds = R.load_erqa()
    started = datetime.now().isoformat()
    infos = run_natural_and_forced8(ds, sel) if args.phase == "eight" else run_forced32(ds, sel)
    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    meta[args.phase] = dict(started=started, finished=datetime.now().isoformat(), models=infos,
                            gen=GEN, gpu=torch.cuda.get_device_name(0), torch=torch.__version__,
                            transformers=__import__("transformers").__version__)
    meta["_provenance"] = stamp(script="study_u_fa2_size.py", model="qwen3vl-8bt/32bt", device=DEVICE_SLUG,
                                n=len(done_ids()), seed=42, args=args)
    META_PATH.write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
