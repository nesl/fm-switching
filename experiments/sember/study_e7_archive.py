#!/usr/bin/env python3
"""StudyE7-d2-4b Job C — D2 frame archive for the Orin (CPU only; vLLM venv for the RH4 builder imports).

Videos: among videos with >= 2 D2 questions, sort by video length (from the id's end_<s>), split into 4 equal-count
bins by rank, sample 5 per bin with random.Random(0) -> 20 videos.
Per video: every D2 frame from t = 0 to the video's last question time, as the EXACT PNG bytes Job A sent (RH4's
img_url encoding of the 352x256 resize), stored once at e7/frames/<video_id>/t<tttt.t>.png (a later question's
request is the earlier one's image list plus new frames: append-only).
Per question: e7/requests/<question_id>.json = header, ordered image paths, question text, generation parameters,
seed, over_context flag, and body_sha256 — the SHA-256 of the canonical messages JSON; this script rebuilds the
messages FROM THE ARCHIVE FILES and asserts the hash equals Job A's row (so the archive reproduces the request
byte-for-byte). e7/letters_4b.jsonl = Job A's 4B letters (pred, gold, correct, letter mass) for these questions.
e7/sha256_manifest.json = SHA-256 of every file in the tar. Tar -> ~/.cache/fm-switching/e7_orin.tar (not copied).
"""
import base64
import hashlib
import io
import json
import random
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_e7_infer_vllm as A  # noqa: E402

RH, W3, B, R = A.RH, A.W3, A.B, A.R
OUT = Path("results/sember/study_e7")
STAGE = Path.home() / ".cache/fm-switching/e7_orin"
TAR = Path.home() / ".cache/fm-switching/e7_orin.tar"


def length(v):
    return float(v.split("end_")[1])


def main():
    allrows, _ = RH.manifest()
    rows = {q: r for (q, cell), r in allrows.items() if cell == "D2"}
    jobA = {r["question_id"]: r for r in map(json.loads, open(OUT / "e7_requests_h100nvl.jsonl"))
            if not r["grey"] and (not r["error"] or r["infeasible"])}
    assert len(jobA) == 845, len(jobA)
    byv = {}
    for q, r in rows.items():
        byv.setdefault(r["video_id"], []).append(q)
    elig = sorted((v for v, qs in byv.items() if len(qs) >= 2), key=lambda v: (length(v), v))
    k = len(elig) // 4
    bins = [elig[i * k:(i + 1) * k] if i < 3 else elig[3 * k:] for i in range(4)]
    rng = random.Random(0)
    chosen = []
    for i, b in enumerate(bins):
        chosen += [(i, v) for v in sorted(rng.sample(b, 5))]
    import shutil
    if STAGE.exists():
        shutil.rmtree(STAGE)
    root = STAGE / "e7"
    (root / "frames").mkdir(parents=True)
    (root / "requests").mkdir()
    sel_info, letters, nreq, nframes = [], [], 0, 0
    for bi, v in chosen:
        qs = sorted(byv[v], key=lambda q: float(rows[q]["question_time"]))
        tmax = max(float(rows[q]["question_time"]) for q in qs)
        frames = {}
        for t, p, hw in B.select("D2", v, tmax):
            url = W3.img_url(p, hw)
            data = base64.b64decode(url.split(",", 1)[1])
            rel = f"frames/{v}/t{t:07.1f}.png"
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
            frames[t] = rel
        nframes += len(frames)
        for q in qs:
            row = rows[q]
            qt = float(row["question_time"])
            imgs = [frames[t] for t, _, _ in B.select("D2", v, qt)]
            assert len(imgs) == row["n_images"]
            # rebuild the messages from the archive files and check the hash against Job A's request
            content = [{"type": "text", "text": B.HEADERS["D2"]}]
            content += [{"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                                                            base64.b64encode((root / f).read_bytes()).decode()}}
                        for f in imgs]
            content.append({"type": "text", "text": row["text"]})
            sha = A.messages_sha([{"role": "user", "content": content}])
            a = jobA[q]
            assert sha == a["body_sha256"], f"archive does not reproduce Job A's request for {q}"
            req = dict(question_id=q, video_id=v, question_time=qt, question_category=row["question_category"],
                       header=B.HEADERS["D2"], images=imgs, text=row["text"],
                       message_layout="one user turn: [header text] + images in the listed order (PNG, base64 data "
                                      "URLs) + [question text]",
                       generation=dict(temperature=0.0, max_tokens=A.MAX_TOKENS, seed=R.SEED, logprobs=True,
                                       top_logprobs=20),
                       parser="R1: last standalone A-E in the final 300 characters, else X",
                       over_context=row["over_context"], h100_prompt_tokens=a["prompt_tokens"],
                       expected_prompt_tokens=row["n_input_instruct"], body_sha256=sha,
                       body_sha256_definition="sha256(json.dumps(messages, sort_keys=True, separators=(',', ':')))")
            (root / "requests" / f"{q}.json").write_text(json.dumps(req, indent=1))
            letters.append(dict(question_id=q, video_id=v, question_time=qt, pred_4b_h100=a["pred"],
                                correct_letter=a["correct_letter"], correct=a["correct"], infeasible=a["infeasible"],
                                letter_probs=a["letter_probs"], prompt_tokens=a["prompt_tokens"]))
            nreq += 1
        sel_info.append(dict(length_bin=bi, video_id=v, length_s=length(v), n_questions=len(qs), last_qt=tmax,
                             n_frames=len(frames)))
    with open(root / "letters_4b.jsonl", "w") as f:
        for l in letters:
            f.write(json.dumps(l) + "\n")
    (root / "videos.json").write_text(json.dumps(dict(
        rule="videos with >= 2 D2 questions, 4 equal-count length bins by rank, 5 per bin, random.Random(0)",
        eligible=len(elig), bin_edges_s=[[length(b[0]), length(b[-1])] for b in bins], videos=sel_info), indent=1))
    man = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            man[str(p.relative_to(STAGE))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (root / "sha256_manifest.json").write_text(json.dumps(man, indent=0))
    with tarfile.open(TAR, "w") as t:
        t.add(root, arcname="e7")
    size = TAR.stat().st_size
    summary = dict(tar=str(TAR), tar_bytes=size, videos=len(chosen), questions=nreq, frames=nframes,
                   files=len(man) + 1, all_bodies_reproduce_job_a=True, selection=sel_info,
                   bin_edges_s=[[length(b[0]), length(b[-1])] for b in bins], eligible_videos=len(elig))
    from _provenance import stamp
    summary["_provenance"] = stamp(script="study_e7_archive.py", model="4BI", device="cpu", n=nreq)
    (OUT / "e7_archive_summary.json").write_text(json.dumps(summary, indent=1))
    (OUT / "e7_archive_sha256_manifest.json").write_text(json.dumps(man, indent=0))
    shutil.rmtree(STAGE)
    print(json.dumps({k: v for k, v in summary.items() if k != "selection"}, indent=1))


if __name__ == "__main__":
    main()
