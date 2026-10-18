"""StudyX2a — does natural non-termination exist at the recommended sampling settings? (vLLM venv)

Qwen3-VL-32B-Thinking @7edd10ff, the StudyX server unchanged (vLLM 0.31.0, FA3, gmu 0.90, max_model_len 32768, prefix
caching off, PyTorch-native sampler). NO forcing: no min_tokens, no ignore_eos. Every sampling parameter is sent
explicitly, so vLLM's generation_config defaults never apply.

Arms (run in this order; T1.0 is the decision arm):
  T1.0  model card "Generation Hyperparameters / VL": temperature 1.0, top_p 0.95, top_k 20, repetition_penalty 1.0,
        presence_penalty 0.0
  T0.8  shipped generation_config.json: temperature 0.8, top_p 0.95, top_k 20, repetition_penalty 1.0 (no
        presence_penalty key -> 0.0)
  T0.6  StudyX CFG-A (continuity): temperature 0.6, top_p 0.95, top_k 20, min_p 0.0
Workload: the 23-sign StudyX normal pool x 5 seeds (42 + 1000 s, s = 0..4: the StudyX normal-stream seeds) per arm,
max_tokens 24,576, closed loop at concurrency 12, seed-major order. Full text stored.

Runtime guard (pre-registered): after each arm, if elapsed + (arms left x longest arm so far) > 3 h, stop before the
next arm and report.
"""
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_x_vllm as X  # noqa: E402

OUT = Path("results/cost/study_x2a")
X.REQ_PATH = OUT / f"study_x2a_requests_{X.DEV}.jsonl"
X.MET_PATH = OUT / f"study_x2a_metrics_{X.DEV}.jsonl"
X.STAMP_PATH = OUT / f"study_x2a_stamps_{X.DEV}.jsonl"
X.META_PATH = OUT / f"study_x2a_run_meta_{X.DEV}.json"

BASE_P = dict(top_p=0.95, top_k=20, min_p=0.0, repetition_penalty=1.0, presence_penalty=0.0,
              frequency_penalty=0.0, max_tokens=X.SIGN_CAP)
ARMS = [("T1.0", dict(BASE_P, temperature=1.0)),
        ("T0.8", dict(BASE_P, temperature=0.8)),
        ("T0.6", dict(BASE_P, temperature=0.6))]
SEEDS = [42 + 1000 * s for s in range(5)]
CONCURRENCY = 12
GUARD_S = 3 * 3600


class TextRun(X.Run):
    async def request(self, entry, params, role, seed, keep_text=True):
        return await super().request(entry, params, role, seed, keep_text=True)


async def stage():
    P = X.pack()
    signs = X.normal_signs()
    assert len(signs) == 23, signs
    t_start, longest = time.time(), 0.0
    for i, (arm, params) in enumerate(ARMS):
        tag = f"X2a_{arm}"
        if X.is_done(tag):
            continue
        items = [(P[f"sign:{s}"], params, "natural", seed) for seed in SEEDS for s in signs]
        run = TextRun(tag, "32BT")
        t0 = time.time()
        await X.closed_loop(run, items[:CONCURRENCY], items[CONCURRENCY:], total=len(items),
                            concurrency=CONCURRENCY)
        await run.close()
        dur = time.time() - t0
        longest = max(longest, dur)
        recs = run.records
        cap = sum((r["completion_tokens"] or 0) >= X.SIGN_CAP and not r["think_closed"] for r in recs)
        X.log(f"{tag}: {len(recs)} requests in {dur / 60:.1f} min; cap-hit (never closed) {cap}/{len(recs)}; "
              f"errors {sum(bool(r['error']) for r in recs)}")
        X.mark_done(tag, arm=arm, params=params, seeds=SEEDS, signs=signs, concurrency=CONCURRENCY,
                    duration_s=round(dur, 1), n=len(recs), cap_hits=cap)
        await X.wait_idle("32BT")
        left = len(ARMS) - i - 1
        proj = time.time() - t_start + left * longest
        if left and proj > GUARD_S:
            X.log(f"RUNTIME GUARD: projected total {proj / 3600:.2f} h > 3 h — stopping before {ARMS[i + 1][0]}")
            m = X.meta_load()
            m["guard_stop"] = dict(at=datetime.now().isoformat(), projected_h=round(proj / 3600, 2),
                                   next_arm=ARMS[i + 1][0])
            X.meta_save(m)
            return


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srv = X.Server("32BT")
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(stage="X2a", started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        m["arms"] = {a: p for a, p in ARMS}
        X.meta_save(m)
        asyncio.run(stage())
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m["_provenance"] = stamp(script="study_x2a_natural.py", model="qwen3vl-32b-thinking", device=X.DEV,
                             n=3 * 23 * len(SEEDS))
    X.meta_save(m)


if __name__ == "__main__":
    main()
