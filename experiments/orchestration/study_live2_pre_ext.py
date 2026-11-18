#!/usr/bin/env python3
"""StudyLIVE2-pre Part 1 EXTENSION (user request 2026-11-18): extend the S-EMBER D2 JPEG store to the END of every EVAL
session, not only to its last question. CPU only, no server.

Why an extraction is needed: the committed 1 fps source frames (`~/.cache/fm-switching/sember_frames`, written by
`experiments/sember/study_o_q4.py::cache_video`) stop one frame after each session's last question (`max_qt` + 1 s).
This script runs THE COMMITTED `cache_video` (extracted from the file by AST and executed unchanged; PyAV 1 fps decode,
PIL JPEG q88) with `max_qt` = the session's duration into a NEW directory `~/.cache/fm-switching/sember_frames_full/`,
so the existing source frames are never modified, and checks that every frame it shares with the existing directory is
BYTE-IDENTICAL (sha256). Then, with the same D2 recipe as Part 1 (`study_rh3_inputs.load(path, (352, 256))`, then
JPEG q88), it encodes ONLY the 2-s-stride instants the store does not yet hold (D91: stored JPEGs are encoded once and
never re-encoded), appends them to the store's encode log, and the UNCHANGED `build_manifest.py` rebuilds the manifest
with the E10a distributional check.
"""
import ast
import hashlib
import io
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "live2" / "fleet"))
sys.path.insert(0, str(REPO / "experiments/sember"))
SRC_OLD = Path.home() / ".cache/fm-switching/sember_frames"
SRC_FULL = Path.home() / ".cache/fm-switching/sember_frames_full"
VIDEOS = Path.home() / ".cache/fm-switching/sember_videos"
STORE = Path.home() / "data/live2/jpeg/sember_d2_q88"
OUT = REPO / "results/orchestration/live2/pre"


def _cache_video():
    import av
    src = (REPO / "experiments/sember/study_o_q4.py").read_text()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "cache_video")
    ns = dict(av=av, json=json, Path=Path, CACHE=SRC_FULL, VIDEOS=VIDEOS)
    exec(compile(ast.Module([fn], []), "study_o_q4.py", "exec"), ns)
    return ns["cache_video"]


def extract(job):
    vid, dur = job
    fr = _cache_video()(vid, float(dur))
    old = SRC_OLD / vid
    shared = same = 0
    for t, p in fr:
        q = old / p.name
        if q.exists():
            shared += 1
            same += hashlib.sha256(p.read_bytes()).hexdigest() == hashlib.sha256(q.read_bytes()).hexdigest()
    return dict(vid=vid, duration=dur, n_full=len(fr), last_t=fr[-1][0] if fr else None, shared=shared, identical=same)


def enc(job):
    import study_rh3_inputs as B3
    sid, t, src = job
    im = B3.load(src, (352, 256))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    rel = f"{sid}/f{t:08.2f}.jpg"
    dst = STORE / "frames" / rel
    if dst.exists():
        raise SystemExit(f"{dst} exists: refusing to overwrite (encode once, D91)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue())
    return dict(file=rel, frame_ref=f"{sid}|f{t:08.2f}", src=str(src), size=[im.width, im.height], extension=True)


def main():
    import data_sources as DS
    t0 = time.time()
    sess = DS.eval_sessions()
    jobs = [(sid, sm.duration_s) for sid, sm in sorted(sess.items())]
    with ProcessPoolExecutor(32) as ex:
        ext = list(ex.map(extract, jobs))
    bad = [e for e in ext if e["shared"] != e["identical"]]
    print(f"extracted {len(ext)} sessions in {time.time() - t0:.0f} s; frames {sum(e['n_full'] for e in ext)}; shared "
          f"{sum(e['shared'] for e in ext)}, identical {sum(e['identical'] for e in ext)}; mismatching sessions {len(bad)}")
    if bad:
        raise SystemExit(f"re-extracted frames differ from the existing source frames in {len(bad)} sessions: STOP")
    have = {json.loads(l)["frame_ref"] for l in open(STORE / "encode_log.jsonl")}
    todo = []
    for e in ext:
        idx = {float(t): SRC_FULL / e["vid"] / f for t, f in json.load(open(SRC_FULL / e["vid"] / "index.json"))["frames"]}
        for t in sorted(idx):
            if t % 2.0 == 0 and t <= e["duration"] + 1e-9 and f"{e['vid']}|f{t:08.2f}" not in have:
                todo.append((e["vid"], t, str(idx[t])))
    with ProcessPoolExecutor(32) as ex:
        rows = list(ex.map(enc, todo, chunksize=64))
    with open(STORE / "encode_log.jsonl", "a") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    meta = json.loads((STORE / "encode_meta.json").read_text())
    meta.setdefault("extensions", []).append(dict(
        at=time.strftime("%Y-%m-%dT%H:%M:%S"), added=len(rows), source=str(SRC_FULL),
        reason="extend every EVAL session to its END (user request 2026-11-18), not only to its last question",
        source_extractor="experiments/sember/study_o_q4.py::cache_video run unchanged (AST) with max_qt = duration; "
                         "frames shared with the existing source directory byte-identical"))
    meta["n_frames"] = meta.get("n_frames", 0) + len(rows)
    (STORE / "encode_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    p = subprocess.run([sys.executable, str(HERE / "live2/data/build_manifest.py"), "--store", str(STORE),
                        "--dataset", "sember"], capture_output=True, text=True)
    mm = json.loads((STORE / "manifest_meta.json").read_text())
    res = dict(sessions=len(ext), extracted_frames=sum(e["n_full"] for e in ext), shared=sum(e["shared"] for e in ext),
               identical=sum(e["identical"] for e in ext), added_d2_frames=len(rows), store_frames=mm["n_frames"],
               build_manifest_exit=p.returncode, any_flagged=mm["any_flagged"], bytes=mm["bytes"],
               checks=mm["e10a_checks"], per_session=ext)
    (OUT / "live2_pre_part1_extension.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_session", "checks")}))
    if p.returncode or mm["any_flagged"]:
        raise SystemExit("E10a check FLAGGED after the extension: STOP")


if __name__ == "__main__":
    main()
