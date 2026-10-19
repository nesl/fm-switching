#!/usr/bin/env python3
"""StudyRH3 — accuracy of warmable (separate-image) history representations, plus a one-video prefix-cache check
(vLLM venv). Pre-registered in research/EXPERIMENTS.md (StudyRH3).

PART 0 (--stage part0): R1's server config with prefix caching ON (+ --enable-prompt-tokens-details). For 5 questions
(the first 5 in R1 order whose RICH input is uncapped 1 fps, i.e. n_frames < 256, and has >= 40 frames): R1's RICH
video request truncated to its first n-10 frames (BASE), BASE again (control: an identical request must hit), then
the full n-frame request (EXT = R1's exact K1 request; same text). The frames are R1's final-size uint8 frames for
both, so the pixels of the shared 0..n-10 frames are identical (the most cache-friendly case: in a live system the
processor's total-pixel budget would also rescale every frame as the video grows). max_tokens 1, return_token_ids:
records cached_tokens, prompt_tokens, the common token-id prefix of BASE and EXT, and where the video starts.

PARTS A-C (--stage parity,timing,A,B,C): R1's request settings and code (study_r1_vllm.send / run_cell: 32B-I
@0cfaf481, greedy, max_tokens 512, seed 42, concurrency 8, R1's answer parsing, 845 questions in R1 order) and R1's
server except the multimodal flags: prefix caching OFF, --limit-mm-per-prompt {"image": 640, "video": 0},
--mm-processor-kwargs {"size": PROC_SIZE} (no rescaling of the builder's sizes). Inputs: study_rh3_inputs.py.
  parity  5 questions per cell, max_tokens 1: vLLM prompt_tokens == HF-processor count for the exact images (STOP).
  timing  5 questions per cell sequentially -> estimate (R1's batched speed-up). STOP if > 3 h.
"""
import argparse
import asyncio
import base64
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cost"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r1_vllm as R  # noqa: E402
import study_rh3_inputs as B  # noqa: E402
import study_x_vllm as X  # noqa: E402
from rawio import read_jsonl  # noqa: E402

OUT = Path("results/sember/study_rh3")
GREEDY = dict(temperature=0.0, max_tokens=512)
CELLS = {c: ("32BI", c, GREEDY) for c in ("A", "B", "C")}
IMAGE_FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": B.MAX_IMAGES, "video": 0}),
               "--mm-processor-kwargs", json.dumps({"size": B.PROC_SIZE}), "--host", "127.0.0.1"]
PART0_FLAGS = R.MM_LIMIT + ["--enable-prefix-caching", "--enable-prompt-tokens-details"]
BUDGET_S = 3 * 3600
VISION_START = 151652          # <|vision_start|> (Qwen3-VL tokenizer)

R.OUT = OUT
R.REQ = OUT / f"study_rh3_requests_{X.DEV}.jsonl"
R.META = X.META_PATH = OUT / f"study_rh3_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh3_current.json")
R.CELLS = CELLS


def manifest():
    rows = {}
    for r in read_jsonl(B.MANIFEST):
        rows[(r["question_id"], r["cell"])] = dict(r, construction=r["cell"], n_frames=r["n_images"])
    order = sorted({(r["video_id"], r["question_id"]) for r in rows.values()})
    return rows, [q for _, q in order]


def img_url(path, hw):
    im = B.load(path, hw)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def body(row, cell, model, params, max_tokens=None, stream=True, token_ids=False):
    idx = B.frames_index(row["video_id"])
    sizes = row["hw_per_image"] or [None] * row["n_images"]
    base = {"A": B.SIZE_A, "B": B.SIZE_B}.get(row["cell"])
    content = [{"type": "text", "text": row["header"]}]
    for t, hw in zip(row["frame_t"], sizes):
        # hw_per_image holds the oriented size; B.load re-orients from the portrait base, so pass the portrait form
        if hw is not None:
            hw = tuple(hw) if hw[0] >= hw[1] else (hw[1], hw[0])
        content.append({"type": "image_url", "image_url": {"url": img_url(idx[float(t)], hw or base)}})
    content.append({"type": "text", "text": row["text"]})
    p = dict(params)
    if max_tokens is not None:
        p["max_tokens"] = max_tokens
    b = dict(model=model, stream=stream, seed=R.SEED, messages=[{"role": "user", "content": content}], **p)
    if stream:
        b["stream_options"] = {"include_usage": True}
    if token_ids:
        b["return_token_ids"] = True
    return b, None, row["n_images"]


R.body = body


async def parity(rows, order):
    out = []
    async with httpx.AsyncClient(timeout=None) as c:
        for cell in CELLS:
            for q in order[:5]:
                row = rows[(q, cell)]
                b, _, n = await asyncio.to_thread(body, row, "parity", "32BI", dict(temperature=0.0), 1, False)
                r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
                if "error" in r or "usage" not in r:
                    out.append(dict(question_id=q, cell=cell, error=str(r)[:500]))
                    continue
                pt = r["usage"]["prompt_tokens"]
                out.append(dict(question_id=q, cell=cell, n_images=n, vllm_prompt_tokens=pt,
                                hf_expected_prompt_tokens=row["n_input_instruct"],
                                match=pt == row["n_input_instruct"]))
                X.log(f"parity {cell} {q[:10]} images {n} vllm {pt} hf {row['n_input_instruct']}")
    ok = all(o.get("match") for o in out)
    res = dict(at=datetime.now().isoformat(), gate_passed=ok, n=len(out), rows=out)
    (OUT / f"study_rh3_parity_{X.DEV}.json").write_text(json.dumps(res, indent=1))
    X.log(f"PARITY GATE (A,B,C) {'PASSED' if ok else 'FAILED'}")
    return ok


async def timing(rows, order):
    res = {}
    for cell in CELLS:
        d = await R.run_cell(cell, rows, order, "timing5", limit=5, conc=1)
        recs = [r for r in read_jsonl(R.REQ) if r["cell"] == cell and r["mode"] == "timing5"]
        res[cell] = dict(wall_s=round(d, 1), latency_s=[r["latency_s"] for r in recs],
                         prompt_tokens=[r["prompt_tokens"] for r in recs])
        X.log(f"timing {cell}: {res[cell]}")
    return res


def estimate(timing5):
    """845 x mean sequential latency / R1's measured batched speed-up (as RH1)."""
    r1m = json.loads(Path("results/sember/study_r1/study_r1_run_meta_h100nvl.json").read_text())
    seq = float(np.mean(r1m["timing5"]["K1"]["latency_s"]))
    k1_batched = 34.3 * 60
    speedup = 845 * seq / k1_batched
    per = {c: 845 * float(np.mean(t["latency_s"])) / speedup for c, t in timing5.items()}
    return dict(batched_speedup_from_r1=round(speedup, 2), per_cell_s=per, total_s=sum(per.values()))


# ------------------------------------------------------------------------------------------------ Part 0
def r1_body_frames(row, n_keep, token_ids=True):
    """R1's request for this RICH row, its video cut to the first n_keep frames (n_keep even; R1's own pixels)."""
    z = np.load(R.INP / "RICH" / f"{row['question_id']}.npz")
    fr = z["frames"][:n_keep]
    fidx = [int(i) for i in z["frames_indices"][:n_keep]]
    url = "data:video/jpeg;base64," + ",".join(R.png_b64(f) for f in fr)
    return dict(model="32BI", stream=False, seed=R.SEED, temperature=0.0, max_tokens=1, return_token_ids=token_ids,
                messages=[{"role": "user", "content": [{"type": "video_url", "video_url": {"url": url}},
                                                        {"type": "text", "text": row["text"]}]}],
                media_io_kwargs={"video": dict(num_frames=-1, fps=1.0, frames_indices=fidx, do_sample_frames=False,
                                               total_num_frames=max(1, fidx[-1] + 1))})


async def part0():
    r1 = sorted((r for r in read_jsonl(R.MANIFEST) if r["construction"] == "RICH"),
                key=lambda r: (r["video_id"], r["question_id"]))
    pick = [r for r in r1 if 40 <= r["n_frames"] < 256 and r["n_frames"] % 2 == 0][:5]
    out = []
    async with httpx.AsyncClient(timeout=None) as c:
        async def post(b):
            j = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
            if "usage" not in j:
                return dict(error=str(j)[:400])
            u = j["usage"]
            return dict(prompt_tokens=u["prompt_tokens"],
                        cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                        ids=j.get("prompt_token_ids"))
        for row in pick:
            n = row["n_frames"]
            base, ctrl, ext = (await post(r1_body_frames(row, n - 10)), await post(r1_body_frames(row, n - 10)),
                               await post(r1_body_frames(row, n)))
            ids_b, ids_e = base.pop("ids", None), ext.pop("ids", None)
            ctrl.pop("ids", None)
            common = next((i for i, (x, y) in enumerate(zip(ids_b, ids_e)) if x != y), min(len(ids_b), len(ids_e))) \
                if ids_b and ids_e else None
            vstart = ids_e.index(VISION_START) if ids_e and VISION_START in ids_e else None
            o = dict(question_id=row["question_id"], video_id=row["video_id"], n_frames_base=n - 10, n_frames_ext=n,
                     r1_k1_expected_prompt_tokens=row["n_input_instruct"], base=base, control_repeat=ctrl, ext=ext,
                     common_token_id_prefix=common, tokens_before_video=vstart,
                     ext_cached_frac=(ext.get("cached_tokens") or 0) / ext["prompt_tokens"] if "prompt_tokens" in ext
                     else None)
            out.append(o)
            X.log(f"part0 {row['question_id'][:10]} n {n - 10}->{n}: base {base} ctrl {ctrl} ext {ext} "
                  f"common-id-prefix {common} video-start {vstart}")
    res = dict(at=datetime.now().isoformat(), n=len(out), rows=out,
               ext_cached_tokens=[o["ext"].get("cached_tokens") for o in out],
               control_cached_tokens=[o["control_repeat"].get("cached_tokens") for o in out])
    (OUT / f"study_rh3_part0_{X.DEV}.json").write_text(json.dumps(res, indent=1))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, help="part0 | comma list of parity,timing,A,B,C")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stages = args.stage.split(",")
    srv = X.Server("32BI", PART0_FLAGS if stages == ["part0"] else IMAGE_FLAGS)
    try:
        info = srv.start()
        info["prefix_caching"] = stages == ["part0"]
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(stages=args.stage, started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        X.log(f"KV cache capacity: {info.get('kv_cache_tokens')} tokens")
        if stages == ["part0"]:
            asyncio.run(part0())
        else:
            rows, order = manifest()
            assert len(order) == 845 and len(rows) == 3 * 845, (len(order), len(rows))
            for st in stages:
                if st == "parity":
                    if not asyncio.run(parity(rows, order)):
                        raise SystemExit("RH3 PARITY GATE FAILED — STOP (see study_rh3_parity_h100nvl.json)")
                elif st == "timing":
                    t5 = asyncio.run(timing(rows, order))
                    est = estimate(t5)
                    m = X.meta_load()
                    m["timing5"], m["estimate"] = t5, est
                    X.meta_save(m)
                    X.log(f"RUNTIME ESTIMATE (A+B+C): {est['total_s'] / 3600:.2f} h {est}")
                    if est["total_s"] > BUDGET_S:
                        raise SystemExit(f"RH3 estimate {est['total_s'] / 3600:.2f} h > 3 h — STOP")
                elif st in CELLS:
                    asyncio.run(R.run_cell(st, rows, order, "batched"))
                else:
                    raise SystemExit(f"unknown stage {st}")
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh3_warmable.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
