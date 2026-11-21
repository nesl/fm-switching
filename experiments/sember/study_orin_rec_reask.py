#!/usr/bin/env python3
"""StudyORIN-REC REASK (D161 (3)): measure the 4B device answer at each re-ask time.

For each (question_id, session, re-ask time) in flash's exported lists (seeds 4 to 7,
results/orchestration/live2/reask_lists/), record the device answer on the RECENT
window (60 frames, last 120 s) ending at that re-ask time, same header, prompt and
generation as StudyORIN-REC, default Jetson vLLM config, WARM path as in the WARM
study (prefill the frames untimed, then time the question). Records: answer letter,
logprob confidence on the emitted letter, TTFT, completion, prompt and cached tokens.

CLOCK (resolved against the runner, not assumed): the RECENT window is built over the
D2 frame store, which is indexed on the EPISODE clock (the S-EMBER video timestamp).
The plan's question_time equals the list's ask_time_session, not ask_time (verified:
question_time 164.0 == ask_time_session 164.0, ask_time 156.68). So the window ends at
reask_time_session (episode), and the parity window ends at ask_time_session. flash's
README names reask_time (run wall clock) but defers to the Orin's own frame filter;
this is that filter's clock. The parity control is the empirical check either way.

PARITY CONTROL: at the original ask (window ending at ask_time_session) the answer
must reproduce StudyORIN-REC part 1 / WARM for that question_id. Run once per distinct
question_id. A mismatch beyond the known prefix-cache near-tie drift (D81) is a real
disagreement, not a lookup miss (all 69 pool questions are in the committed warm table).

Reuses the committed builders verbatim via study_orin_rec (A, B, S2, HEADER_TEXT) so
the only changes from part 1 are the window end time, the logprobs flag, and the warm
prefill, exactly as the ruling specifies. One request at a time, idle, serial.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/sember"))
import study_orin_rec as OR  # noqa: E402  sets A.STORE, HEADER_TEXT, URL, OUT, imports A/B/S2
from study_orin_rec import A, B, S2, HEADER_TEXT, URL, OUT  # noqa: E402

import httpx  # noqa: E402

REASK_DIR = REPO / "results/orchestration/live2/reask_lists"
LETTERS = {"A", "B", "C", "D"}


def recent_frames(vid, end_episode):
    """The committed RECENT window ending at end_episode (episode clock): existing D2
    frames in (end_episode - 120, end_episode], same construction as the part-1 plan."""
    full = [t for t in A.d2_times(end_episode) if A.path_of(vid, t).exists()]
    rec = [t for t in full if t > end_episode - A.RECENT_W + 1e-9]
    return rec


def _wire(frames, vid, qid, tag, salt, model, question, max_tokens, logprobs):
    M = A._MCQ[qid]
    body = B.build_body(kind="recall", device_id="acc2", session_id=vid, run_tag=tag,
                        salt=salt, header=HEADER_TEXT, frames=frames,
                        question=(M["question"] if question else None),
                        options=(M["options"] if question else None),
                        max_tokens=max_tokens, est_tokens=len(frames) * 90)
    if not question:
        body["max_tokens"] = 1
    wire = dict(B.strip_internal(B.materialize(body, None), strip_hints=True), model=model)
    if logprobs:
        wire["logprobs"] = True
        wire["top_logprobs"] = 20
    return wire


def letter_confidence(content, letter):
    """Probability mass on the emitted letter at the decision token, from top_logprobs."""
    if not content or not letter:
        return None, None, None
    dec = next((e for e in content if (e.get("token") or "").strip() in LETTERS), content[0])
    top = dec.get("top_logprobs") or []
    mass = sum(math.exp(e["logprob"]) for e in top
               if (e.get("token") or "").strip() == letter)
    chosen = math.exp(dec["logprob"]) if dec.get("logprob") is not None else None
    slim = [{"token": e.get("token"), "logprob": e.get("logprob")} for e in top]
    return (mass or None), chosen, dict(decision_token=dec.get("token"), top=slim)


def run_one(client, vid, qid, frame_times, model, warm=True):
    tag = "reask-" + uuid.uuid4().hex[:12]
    salt = uuid.uuid4().hex
    frames = [dict(frame_ref=A.ref(vid, t), path=A.path_of(vid, t)) for t in frame_times]
    pre_err = None
    if warm:  # untimed prefill of exactly these frames, same tag+salt -> warms the prefix
        pre = _wire(frames, vid, qid, tag, salt, model, question=False,
                    max_tokens=B.RECALL_GEN["max_tokens"], logprobs=False)
        pre = {k: v for k, v in pre.items() if k != "stream_options"}
        pre["stream"] = False
        try:
            r = client.post(URL, json=pre, timeout=600.0)
            pre_err = None if r.status_code == 200 else f"prefill HTTP {r.status_code}: {r.text[:200]!r}"
        except Exception as e:  # noqa: BLE001
            pre_err = f"prefill {type(e).__name__}: {e}"
    wire = _wire(frames, vid, qid, tag, salt, model, question=True,
                 max_tokens=B.RECALL_GEN["max_tokens"], logprobs=True)
    t0 = time.time()
    first, text, usage, err, over, content = None, [], {}, None, False, []
    try:
        with client.stream("POST", URL, json=wire) as r:
            if r.status_code != 200:
                blob = r.read()
                err = f"HTTP {r.status_code}: {blob[:300]!r}"
                low = blob.lower()
                if r.status_code == 400 and any(w in low for w in (b"context", b"maximum", b"longer than", b"token")):
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
                        lp = (ch.get("logprobs") or {}).get("content")
                        if lp:
                            content.extend(lp)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    txt = "".join(text)
    letter = S2.recall_letter(txt).get("cloud_letter")
    mass, chosen, conf = letter_confidence(content, letter)
    det = (usage.get("prompt_tokens_details") or {})
    pt = usage.get("prompt_tokens") or 0
    ct = det.get("cached_tokens")
    return dict(
        letter=letter, gold=A._MCQ[qid]["gold"], correct=(letter == A._MCQ[qid]["gold"]),
        letter_prob=mass, chosen_token_prob=chosen, confidence=conf,
        ttft_s=(round(first - t0, 4) if first else None),
        completion_s=round(time.time() - t0, 4),
        prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
        cached_tokens=ct, cached_tokens_present=("cached_tokens" in det),
        cached_covers_frames=(ct is not None and ct >= min(5000, pt - 32)),
        n_frames=len(frames), prefill_error=pre_err, over_context=over, error=err,
        text=txt[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True, choices=(4, 5, 6, 7))
    ap.add_argument("--model", default="qwen3vl4b")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    A._MCQ = A.mcq()

    rows = [json.loads(l) for l in (REASK_DIR / f"reask_list_seed{a.seed}.jsonl").read_text().splitlines() if l.strip()]
    if a.limit:
        rows = rows[:a.limit]
    # plan video_id per question_id (canonical, matches part 1)
    plan = {p["question_id"]: p for p in json.loads((REPO / "results/sember/study_acc2/acc2_plan.json").read_text())["plan"] if p["rep"] == "RECENT"}
    # part1 + warm letters for the parity control
    part1 = {}
    for l in (OUT / "orin_rec_part1.jsonl").open():
        r = json.loads(l)
        if not r.get("error"):
            part1[r["question_id"]] = r.get("letter")
    warm = {}
    wp = OUT / "orin_rec_warm.jsonl"
    if wp.exists():
        for l in wp.open():
            r = json.loads(l)
            if not r.get("error"):
                warm[r["question_id"]] = r.get("letter")

    out = OUT / f"orin_rec_reask_seed{a.seed}.jsonl"
    done = set()
    if out.exists():
        for l in out.open():
            try:
                r = json.loads(l)
            except json.JSONDecodeError:
                continue
            if not r.get("error") and r.get("kind") == "reask":
                done.add(r["opportunity_id"])

    started = datetime.now().isoformat()
    parity = {}  # question_id -> parity record (run once per distinct qid)
    n_err = n_over = 0
    print(f"REASK seed {a.seed}: {len(rows)} re-asks ({len(set(r['question_id'] for r in rows))} distinct questions)", flush=True)
    with httpx.Client(timeout=httpx.Timeout(600.0)) as c, out.open("a") as fh:
        for i, row in enumerate(rows):
            qid = row["question_id"]
            vid = plan[qid]["video_id"]
            assert vid in row["session_id"], f"video mismatch {vid} vs {row['session_id']}"
            # parity control once per distinct question, at the ORIGINAL ask (episode clock)
            if qid not in parity:
                ft0 = recent_frames(vid, row["ask_time_session"])
                rec0 = run_one(c, vid, qid, ft0, a.model, warm=True)
                pr = dict(kind="parity", seed=a.seed, question_id=qid, video_id=vid,
                          ask_time_session=row["ask_time_session"], ask_time=row["ask_time"],
                          n_frames=rec0["n_frames"], plan_n_frames=len(plan[qid]["frame_times"]),
                          letter=rec0["letter"], part1_letter=part1.get(qid), warm_letter=warm.get(qid),
                          reproduces_part1=(rec0["letter"] == part1.get(qid)),
                          reproduces_warm=(rec0["letter"] == warm.get(qid)),
                          letter_prob=rec0["letter_prob"], ttft_s=rec0["ttft_s"],
                          cached_covers_frames=rec0["cached_covers_frames"], error=rec0["error"])
                parity[qid] = pr
                fh.write(json.dumps(pr) + "\n"); fh.flush()
            if row["opportunity_id"] in done:
                continue
            ft = recent_frames(vid, row["reask_time_session"])
            rec = run_one(c, vid, qid, ft, a.model, warm=True)
            rec.update(kind="reask", seed=a.seed, device_id=row["device_id"],
                       session_id=row["session_id"], question_id=qid, video_id=vid,
                       opportunity_id=row["opportunity_id"], reask_of=row["reask_of"],
                       reask_index=row["reask_index"],
                       reask_time=row["reask_time"], reask_time_session=row["reask_time_session"],
                       history_tokens_cloud=row.get("history_tokens"),
                       device_latency_s_warm_ref=row.get("device_latency_s_warm"))
            n_err += bool(rec["error"] and not rec["over_context"])
            n_over += bool(rec["over_context"])
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(rows)} err {n_err} over {n_over}", flush=True)

    npar = len(parity)
    rep1 = sum(1 for p in parity.values() if p["reproduces_part1"])
    repw = sum(1 for p in parity.values() if p["reproduces_warm"])
    meta = dict(label=f"StudyORIN-REC REASK seed {a.seed}", study="StudyORIN-REC-REASK",
                seed=a.seed, model=a.model, n_reasks=len(rows), n_distinct_questions=npar,
                parity={"n": npar, "reproduces_part1": rep1, "reproduces_warm": repw,
                        "note": "window ends at ask_time_session (episode clock); mismatch beyond prefix-cache near-tie drift (D81) is a real disagreement"},
                clock="episode (reask_time_session / ask_time_session); D2 frame store is episode-indexed, verified question_time==ask_time_session",
                recent_window="committed 60-frame last-120s filter over the D2 frame list, ending at the episode time",
                warm_path="prefill frames untimed (max_tokens 1, same tag+salt), then time the question; logprobs on the timed question",
                errors=n_err, over_context=n_over, started=started, finished=datetime.now().isoformat())
    sys.path.insert(0, str(REPO / "experiments/lib"))
    from _provenance import stamp  # noqa: E402
    meta["_provenance"] = stamp(script="study_orin_rec_reask.py", model=a.model,
                                device="nvidia_jetson_orin", n=len(rows), args=a)
    (OUT / f"orin_rec_reask_seed{a.seed}_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"PARITY seed {a.seed}: {rep1}/{npar} reproduce part1, {repw}/{npar} reproduce warm", flush=True)
    print(f"wrote {out}  errors {n_err} over_context {n_over}", flush=True)


if __name__ == "__main__":
    main()
