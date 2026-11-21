#!/usr/bin/env python3
"""StudyORIN-REC (D146): re-record the deployed device's ROBOT RECALL answers and latencies on the
Jetson Orin (Qwen3-VL-4B under vLLM), replacing the D87 A6000-proxy substitution.

Mirrors experiments/sember/study_acc2.py:177-183 VERBATIM against the Orin endpoint: the same
committed builders (coordinator.HEADER_TEXT, bodies.RECALL_GEN, bodies.recall_question_text,
bodies.build_body(kind="recall", ...)), the same committed plan (acc2_plan.json) and MCQ source,
the same D2 frame store (sember_d2_q88) staged to the Orin. One request at a time, idle, serial.

Per question recorded (D146): answer letter, correct, TTFT, completion time, output tokens, prompt
tokens, cached tokens (RAW; absent kept absent, not mapped to 0), plus _provenance at the file level.
A question whose history exceeds the server context limit is recorded over_context=true, never
truncated. Resumable on (question_id, rep). No em dashes.

Modes:
  --mode gate   one RECENT part-1 question; prompt_tokens must land in [5476,5682] or STOP.
  --mode part1  the 97 LH-REQ questions, RECENT representation.
  --mode part2  the full S-EMBER suite, RECENT and RICH (=D2) representations.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/sember"))
import study_acc2 as A  # noqa: E402  reuse mcq(), ref(), path_of(); its import sets live2 sys.path

A.STORE = Path("/dev/shm/sember_d2_q88")  # the Orin-staged D2 store; path_of reads A.STORE at call time

import bodies as B  # noqa: E402
import scores as S2  # noqa: E402
from coordinator import HEADER_TEXT  # noqa: E402
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

import httpx  # noqa: E402

OUT = REPO / "results/sember/study_orin_rec"
URL = "http://127.0.0.1:8000/v1/chat/completions"
PLAN = json.loads((REPO / "results/sember/study_acc2/acc2_plan.json").read_text())["plan"]
LH97 = set(json.load(open(REPO / "results/orchestration/live2/lh_req/lh_req_definition.json"))
           ["lh_req_question_ids"])
GATE_LO, GATE_HI = 5476, 5682


def one(client, p, model, tag=None, salt=None):
    vid = p["video_id"]
    frames = [dict(frame_ref=A.ref(vid, t), path=A.path_of(vid, t)) for t in p["frame_times"]]
    M = A._MCQ[p["question_id"]]
    tag = tag or ("orinrec-" + uuid.uuid4().hex[:12])
    body = B.build_body(kind="recall", device_id="acc2", session_id=vid, run_tag=tag,
                        salt=(salt or uuid.uuid4().hex), header=HEADER_TEXT, frames=frames,
                        question=M["question"], options=M["options"],
                        max_tokens=B.RECALL_GEN["max_tokens"], est_tokens=len(frames) * 90)
    wire = dict(B.strip_internal(B.materialize(body, None), strip_hints=True), model=model)
    t0 = time.time()
    first, text, usage, err, over = None, [], {}, None, False
    try:
        with client.stream("POST", URL, json=wire) as r:
            if r.status_code != 200:
                blob = r.read()
                err = f"HTTP {r.status_code}: {blob[:300]!r}"
                low = blob.lower()
                if r.status_code == 400 and (b"context" in low or b"maximum" in low
                                             or b"longer than" in low or b"token" in low):
                    over = True
            else:
                for line in r.iter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    j = json.loads(line[6:])
                    if j.get("usage"):
                        usage = j["usage"]
                    for ch in j.get("choices", []):
                        piece = (ch.get("delta") or {}).get("content")
                        if piece:
                            first = first or time.time()
                            text.append(piece)
    except Exception as e:                                                        # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    letter = S2.recall_letter("".join(text)).get("cloud_letter")
    det = usage.get("prompt_tokens_details") or {}
    gold = M["gold"]
    return dict(question_id=p["question_id"], rep=p["rep"], split=p["split"], category=p["category"],
                video_id=vid, question_time=p["question_time"], n_frames=len(frames),
                frames_missing=p.get("frames_missing"), source=p.get("source"),
                r1_prompt_tokens=p.get("r1_prompt_tokens"),
                letter=letter, gold=gold, correct=(letter == gold),
                ttft_s=(round(first - t0, 4) if first else None),
                completion_s=round(time.time() - t0, 4),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                cached_tokens=det.get("cached_tokens"),
                cached_tokens_present=isinstance(det, dict) and "cached_tokens" in det,
                over_context=over, error=err, text="".join(text)[:300], req=p.get("req"))


def warm_one(client, p, model, cold_letter):
    """WARM best-case (D153/user): one prefill-only request (exactly the 60 RECENT frames + header,
    max_tokens 1, NOT timed, SAME cache_salt) stands in for capture-time prefill, then the real
    question request, TIMED, which must reuse the frame prefix. cached_tokens on the real request
    must cover the frames or this is a STOP. Agreement with the cold part-1 letter is D81 drift."""
    vid = p["video_id"]
    frames = [dict(frame_ref=A.ref(vid, t), path=A.path_of(vid, t)) for t in p["frame_times"]]
    M = A._MCQ[p["question_id"]]
    tag = "orinrec-warm-" + uuid.uuid4().hex[:12]
    salt = uuid.uuid4().hex                                  # one salt shared by prefill + real
    # prefill-only: header + frames, NO question, max_tokens 1, same tag+salt
    pre = B.build_body(kind="recall", device_id="acc2", session_id=vid, run_tag=tag, salt=salt,
                       header=HEADER_TEXT, frames=frames, question=None,
                       max_tokens=B.RECALL_GEN["max_tokens"], est_tokens=len(frames) * 90)
    pre["max_tokens"] = 1                                    # recall gen forces 512; prefill wants 1
    pre_wire = dict(B.strip_internal(B.materialize(pre, None), strip_hints=True), model=model)
    pre_wire = {k: v for k, v in pre_wire.items() if k != "stream_options"}
    pre_wire["stream"] = False                              # non-streamed prefill; drop stream_options
    try:                                                    # NOT timed; just warms the prefix
        r = client.post(URL, json=pre_wire, timeout=600.0)
        pre_err = None if r.status_code == 200 else f"prefill HTTP {r.status_code}: {r.text[:200]!r}"
    except Exception as e:                                                        # noqa: BLE001
        pre_err = f"prefill {type(e).__name__}: {e}"
    # real question request, TIMED, same tag+salt+frames -> frame prefix is warm
    rec = one(client, dict(p, _warm_tag=tag, _warm_salt=salt), model, tag=tag, salt=salt)
    pt = rec.get("prompt_tokens") or 0
    ct = rec.get("cached_tokens")
    frames_tok = pt - 32                                    # frames+header are all but the trailing question block
    rec.update(mode="warm", prefill_error=pre_err, cold_letter=cold_letter,
               agree_with_cold=(rec["letter"] == cold_letter),
               cached_covers_frames=(ct is not None and ct >= min(5000, frames_tok)))
    return rec


def select(mode):
    if mode in ("gate", "part1", "warm"):
        rows = [p for p in PLAN if p["rep"] == "RECENT" and p["question_id"] in LH97]
        rows.sort(key=lambda p: (p["question_id"]))
        return rows[:1] if mode == "gate" else rows
    if mode == "part2":
        rows = [p for p in PLAN if p["rep"] in ("RECENT", "D2")]
        rows.sort(key=lambda p: (p["question_id"], p["rep"]))
        return rows
    raise SystemExit("mode must be gate|part1|part2|warm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=("gate", "part1", "part2", "warm"))
    ap.add_argument("--model", default="qwen3vl4b")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    A._MCQ = A.mcq()
    assert all(k in next(iter(A._MCQ.values())) for k in ("question", "options", "gold")), "MCQ keys"
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"orin_rec_{a.mode}.jsonl"
    done = set()
    if out.exists():
        for l in out.open():
            try:
                r = json.loads(l)
            except json.JSONDecodeError:
                continue
            if not r.get("error"):
                done.add((r["question_id"], r["rep"]))
    rows = [p for p in select(a.mode) if (p["question_id"], p["rep"]) not in done]
    if a.limit:
        rows = rows[:a.limit]
    cold = {}
    if a.mode == "warm":
        for l in (OUT / "orin_rec_part1.jsonl").open():
            if l.strip():
                r = json.loads(l)
                cold[r["question_id"]] = r.get("letter")
    print(f"mode {a.mode}: {len(rows)} requests to run (model {a.model})", flush=True)
    n_err = n_over = n_agree = n_uncov = 0
    started = datetime.now().isoformat()
    with httpx.Client(timeout=httpx.Timeout(600.0)) as c, out.open("a") as fh:
        for i, p in enumerate(rows):
            if a.mode == "warm":
                rec = warm_one(c, p, a.model, cold.get(p["question_id"]))
                n_agree += bool(rec.get("agree_with_cold"))
                if not rec.get("cached_covers_frames"):
                    n_uncov += 1
                    fh.write(json.dumps(rec) + "\n"); fh.flush()
                    print(f"STOP: question {rec['question_id']} cached_tokens={rec.get('cached_tokens')} "
                          f"does NOT cover frames (prompt_tokens={rec.get('prompt_tokens')}). "
                          f"Warm prefill is not reusing the frame prefix.", flush=True)
                    print("WARM_RESULT STOP", flush=True)
                    break
            else:
                rec = one(c, p, a.model)
            n_err += bool(rec["error"] and not rec["over_context"])
            n_over += bool(rec["over_context"])
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if a.mode == "gate":
                pt = rec["prompt_tokens"]
                ok = pt is not None and GATE_LO <= pt <= GATE_HI
                print(f"GATE: prompt_tokens={pt} band=[{GATE_LO},{GATE_HI}] n_frames={rec['n_frames']} "
                      f"letter={rec['letter']} -> {'PASS' if ok else 'STOP'}", flush=True)
                print("GATE_RESULT", "PASS" if ok else "STOP", flush=True)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(rows)} err {n_err} over_context {n_over}", flush=True)
    warm_summary = {}
    if a.mode == "warm":
        import statistics as st
        recs = [json.loads(l) for l in out.open() if l.strip()]
        ok = [r for r in recs if not r.get("error")]
        def pct(xs, q):
            xs = sorted(x for x in xs if x is not None)
            return None if not xs else round(xs[min(len(xs) - 1, int(q * len(xs)))], 4)
        warm_summary = dict(
            label="device BEST-CASE warm latency (exact RECENT frames prefilled)",
            n=len(ok), stopped=(n_uncov > 0),
            cached_covers_frames_all=(n_uncov == 0),
            agree_with_cold=sum(1 for r in ok if r.get("agree_with_cold")),
            ttft_p50=pct([r["ttft_s"] for r in ok], 0.5), ttft_p90=pct([r["ttft_s"] for r in ok], 0.9),
            completion_p50=pct([r["completion_s"] for r in ok], 0.5),
            completion_p90=pct([r["completion_s"] for r in ok], 0.9),
            cached_tokens_min=min((r.get("cached_tokens") or 0) for r in ok) if ok else None)
        print("WARM_RESULT", "STOP" if n_uncov else "PASS",
              "| agree_with_cold", warm_summary["agree_with_cold"], "/", len(ok),
              "| TTFT p50", warm_summary["ttft_p50"], "p90", warm_summary["ttft_p90"],
              "| completion p50", warm_summary["completion_p50"], "p90", warm_summary["completion_p90"],
              flush=True)
    meta = dict(label=f"StudyORIN-REC {a.mode}", mode=a.mode, model=a.model,
                requests=len(rows), errors=n_err, over_context=n_over,
                header_text=HEADER_TEXT, recall_gen=B.RECALL_GEN, store=str(A.STORE),
                warm_summary=warm_summary,
                started=started, finished=datetime.now().isoformat())
    meta["_provenance"] = stamp(script="study_orin_rec.py", model=a.model,
                                device="nvidia_jetson_orin", n=len(rows), args=a)
    (OUT / f"orin_rec_{a.mode}_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {out}\nerrors {n_err} over_context {n_over}", flush=True)


if __name__ == "__main__":
    main()
