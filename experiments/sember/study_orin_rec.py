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


def one(client, p, model):
    vid = p["video_id"]
    frames = [dict(frame_ref=A.ref(vid, t), path=A.path_of(vid, t)) for t in p["frame_times"]]
    M = A._MCQ[p["question_id"]]
    tag = "orinrec-" + uuid.uuid4().hex[:12]
    body = B.build_body(kind="recall", device_id="acc2", session_id=vid, run_tag=tag,
                        salt=uuid.uuid4().hex, header=HEADER_TEXT, frames=frames,
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


def select(mode):
    if mode in ("gate", "part1"):
        rows = [p for p in PLAN if p["rep"] == "RECENT" and p["question_id"] in LH97]
        rows.sort(key=lambda p: (p["question_id"]))
        return rows[:1] if mode == "gate" else rows
    if mode == "part2":
        rows = [p for p in PLAN if p["rep"] in ("RECENT", "D2")]
        rows.sort(key=lambda p: (p["question_id"], p["rep"]))
        return rows
    raise SystemExit("mode must be gate|part1|part2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=("gate", "part1", "part2"))
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
    print(f"mode {a.mode}: {len(rows)} requests to run (model {a.model})", flush=True)
    n_err = n_over = 0
    started = datetime.now().isoformat()
    with httpx.Client(timeout=httpx.Timeout(600.0)) as c, out.open("a") as fh:
        for i, p in enumerate(rows):
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
    meta = dict(label=f"StudyORIN-REC {a.mode}", mode=a.mode, model=a.model,
                requests=len(rows), errors=n_err, over_context=n_over,
                header_text=HEADER_TEXT, recall_gen=B.RECALL_GEN, store=str(A.STORE),
                started=started, finished=datetime.now().isoformat())
    meta["_provenance"] = stamp(script="study_orin_rec.py", model=a.model,
                                device="nvidia_jetson_orin", n=len(rows), args=a)
    (OUT / f"orin_rec_{a.mode}_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {out}\nerrors {n_err} over_context {n_over}", flush=True)


if __name__ == "__main__":
    main()
