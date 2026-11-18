#!/usr/bin/env python3
"""D111 (user ruling 2026-11-18): store a substitute for every S-EMBER D2 frame a planned trace asks for at a session's
end that the 1 fps frame store does not hold. CPU only, no server.

Boundary convention found by StudyMOT2 seed 9's preflight: the TRACE's 2-s history grid is END-INCLUSIVE (it asks for
t = 2 * floor(duration / 2) <= duration), while the FRAME STORE, decoded at 1 fps by `study_o_q4.py::cache_video`, ends
at its last decodable 1 s frame, which can lie up to about 1 s before the end; so a trace can ask for one instant past
the store.

  enumerate   build every planned trace in memory (the runner's exact `generate_trace` call, with the combined
              manifest), run the preflight's every-ref check on it, and record the missing refs, which traces use
              them, and each trace's (trace_sha256, device_answers_sha256, fairness_digest_A, fairness_digest_B).
  fill        for each missing ref: (a) PREFERRED the source video's last native-rate frame at or before the
              requested time and within 0.1 s of it, through the extractor's own steps (PyAV decode,
              `frame.to_image()` saved as JPEG q88, as `cache_video` does), then the D2 recipe
              (`study_rh3_inputs.load(path, (352, 256))`, JPEG q88); (b) FALLBACK only where (a) finds nothing within
              0.1 s, the session's last stored frame. Marked in the encode log (substitute_of, method, offset_s,
              sha256); the manifest is rebuilt by build_manifest.py, which carries those fields for substitute rows.
  verify      re-enumerate: 0 missing refs, and every trace's four hashes identical to the enumeration's.

Existing JPEGs are never touched (D91): a substitute is written only where no file exists.
"""
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE / "live2", HERE / "live2" / "fleet", REPO / "experiments/sember"):
    sys.path.insert(0, str(p))
STORE = Path.home() / "data/live2/jpeg/sember_d2_q88"
JPEG = Path.home() / "data/live2/jpeg"
COMBINED = JPEG / "combined_manifest.jsonl"
FRAMES_BY_REF = Path.home() / "data/live2/frames_by_ref"
VIDEOS = Path.home() / ".cache/fm-switching/sember_videos"
OUT = REPO / "results/orchestration/live2/pre"
SCRATCH = Path(os.environ.get("D111_SCRATCH", tempfile.gettempdir()))
NATIVE_TOL_S = 0.1
MAX_FRAC = 0.01


def specs():
    """Every trace a planned run uses (D111 step 1.1)."""
    s = [("MOT2", 9, 12, "50:50", 600.0), ("MOT2", 10, 12, "50:50", 600.0),
         ("pilot-step1", 0, 8, "50:50", 120.0)]
    s += [("pilot-ladder", 0, n, "50:50", 600.0) for n in (4, 8, 16, 32, 64, 128, 256, 512)]
    s += [("round1", seed, n, ratio, 600.0) for seed in (1, 2, 3) for ratio in ("50:50", "75:25", "25:75")
          for n in range(4, 129)]
    return s


def one(spec):
    import preflight as PF
    import trace as TR
    use, seed, n, ratio, run_s = spec
    b = TR.generate_trace(seed, n, ratio, run_s, "A", frame_manifest=COMBINED)
    with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
        tdir = Path(d) / "t"
        TR.write_trace(tdir, b)
        meta = json.loads((tdir / "trace_meta.json").read_text())
        rep = PF.check(tdir, FRAMES_BY_REF)
        refs = PF.trace_frame_refs(tdir)
    missing = [r for r in refs if not (FRAMES_BY_REF / r).exists() or (FRAMES_BY_REF / r).stat().st_size == 0]
    return dict(use=use, seed=seed, n=n, ratio=ratio, run_s=run_s, n_refs=len(refs), n_missing=len(missing),
                missing=missing, preflight_ok=rep["ok"],
                hashes={k: meta[k] for k in ("trace_sha256", "device_answers_sha256",
                                             "fairness_digest_A", "fairness_digest_B")})


def enumerate_all(tag):
    t0 = time.time()
    with ProcessPoolExecutor(32) as ex:
        res = list(ex.map(one, specs(), chunksize=4))
    by_ref = {}
    for r in res:
        for m in r["missing"]:
            by_ref.setdefault(m, []).append(f"{r['use']} seed{r['seed']} n{r['n']} {r['ratio']} {int(r['run_s'])}s")
    out = dict(tag=tag, at=time.strftime("%Y-%m-%dT%H:%M:%S"), n_traces=len(res), wall_s=round(time.time() - t0, 1),
               n_missing_refs=len(by_ref), max_missing_frac=max((r["n_missing"] / r["n_refs"] for r in res if r["n_refs"]),
                                                               default=0.0),
               missing_by_ref={k: dict(n_traces=len(v), traces=v[:20]) for k, v in sorted(by_ref.items())},
               traces=[{k: v for k, v in r.items() if k != "missing"} for r in res])
    return out


def last_stored(sid, t):
    d = STORE / "frames" / sid
    ts = sorted(float(p.stem[1:]) for p in d.glob("f*.jpg"))
    prior = [x for x in ts if x < t - 1e-9]
    return prior[-1] if prior else None


def _d2(src_image_path):
    import study_rh3_inputs as B3
    im = B3.load(str(src_image_path), (352, 256))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), [im.width, im.height]


def substitute(ref):
    import av
    sid, ft = ref.split("|")
    t = float(ft[1:])
    dst = STORE / "frames" / sid / f"f{t:08.2f}.jpg"
    if dst.exists():
        return dict(frame_ref=ref, error="exists")
    # (a) native-rate last frame at or before t, within 0.1 s
    best = None
    c = av.open(str(VIDEOS / f"{sid}.mp4"))
    st = c.streams.video[0]
    tb = float(st.time_base)
    fps = float(st.average_rate) if st.average_rate else None
    for fr in c.decode(st):
        if fr.pts is None:
            continue
        ts = fr.pts * tb
        if ts > t + 1e-6:
            break
        best = (ts, fr.to_image())
    c.close()
    with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
        if best is not None and t - best[0] <= NATIVE_TOL_S + 1e-9:
            src = Path(d) / "native.jpg"
            best[1].save(src, quality=88)                     # the extractor's own source-frame step
            data, size = _d2(src)
            row = dict(method="native_last_frame", substitute_of=f"{sid}.mp4@pts{best[0]:.6f}",
                       offset_s=round(t - best[0], 6), video_fps=fps)
        else:
            prev = last_stored(sid, t)
            if prev is None:
                return dict(frame_ref=ref, error="no native frame within 0.1 s and no stored frame before it")
            data = (STORE / "frames" / sid / f"f{prev:08.2f}.jpg").read_bytes()
            size = None
            row = dict(method="prev_stored_frame", substitute_of=f"{sid}|f{prev:08.2f}",
                       offset_s=round(t - prev, 6), native_last_before_s=(round(best[0], 6) if best else None))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    rel = f"{sid}/f{t:08.2f}.jpg"
    return dict(file=rel, frame_ref=ref, size=size, sha256=hashlib.sha256(data).hexdigest(), substitute=True,
                d111=True, **row)


def fill(enum):
    refs = sorted(enum["missing_by_ref"])
    bad_frac = [t for t in enum["traces"] if t["n_refs"] and t["n_missing"] / t["n_refs"] > MAX_FRAC]
    if bad_frac:
        raise SystemExit(f"STOP: {len(bad_frac)} traces need substitutes for > 1 % of their refs: {bad_frac[:3]}")
    if any("|f" not in r for r in refs):
        raise SystemExit(f"STOP: a missing ref is not an S-EMBER D2 ref: {[r for r in refs if '|f' not in r][:3]}")
    with ProcessPoolExecutor(16) as ex:
        rows = list(ex.map(substitute, refs))
    errs = [r for r in rows if r.get("error")]
    if errs:
        raise SystemExit(f"STOP: {len(errs)} refs could not be filled by (a) or (b): {errs[:3]}")
    with open(STORE / "encode_log.jsonl", "a") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    meta = json.loads((STORE / "encode_meta.json").read_text())
    meta.setdefault("extensions", []).append(dict(
        at=time.strftime("%Y-%m-%dT%H:%M:%S"), added=len(rows), decision="D111",
        reason="end-of-session instants a planned trace asks for past the 1 fps store's last frame (trace end "
               "inclusive, frame store exclusive)",
        methods={m: sum(1 for r in rows if r["method"] == m) for m in ("native_last_frame", "prev_stored_frame")}))
    meta["n_frames"] = meta.get("n_frames", 0) + len(rows)
    (STORE / "encode_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    p = subprocess.run([sys.executable, str(HERE / "live2/data/build_manifest.py"), "--store", str(STORE),
                        "--dataset", "sember"], capture_output=True, text=True)
    mm = json.loads((STORE / "manifest_meta.json").read_text())
    # the pilot's inputs: combined manifest and frame-ref symlinks
    n_link = 0
    with open(COMBINED, "w") as man:
        for name in ("nexar_q90", "sember_d2_q88"):
            for ln in open(JPEG / name / "manifest.jsonl"):
                x = json.loads(ln)
                man.write(json.dumps(dict(frame_ref=x["frame_ref"], bytes=x["bytes"], sha256=x["sha256"])) + "\n")
                link = FRAMES_BY_REF / x["frame_ref"]
                if not link.exists():
                    link.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(x["path"], link)
                    n_link += 1
    return dict(rows=rows, build_manifest_exit=p.returncode, build_manifest_stderr=p.stderr[-2000:],
                any_flagged=mm["any_flagged"], e10a_checks=mm["e10a_checks"], store_frames=mm["n_frames"],
                new_symlinks=n_link)


def main():
    what = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    if what == "enumerate":
        e = enumerate_all("before")
        (OUT / "d111_enumeration_before.json").write_text(json.dumps(e, indent=1) + "\n")
        print(json.dumps({k: e[k] for k in ("n_traces", "wall_s", "n_missing_refs", "max_missing_frac")}))
    elif what == "fill":
        e = json.loads((OUT / "d111_enumeration_before.json").read_text())
        f = fill(e)
        (OUT / "d111_fill.json").write_text(json.dumps(f, indent=1) + "\n")
        print(json.dumps({k: v for k, v in f.items() if k not in ("rows", "e10a_checks")}))
    elif what == "verify":
        before = json.loads((OUT / "d111_enumeration_before.json").read_text())
        after = enumerate_all("after")
        hb = {(t["use"], t["seed"], t["n"], t["ratio"], t["run_s"]): t["hashes"] for t in before["traces"]}
        changed = [dict(key=list(k), before=hb[k], after=t["hashes"]) for t in after["traces"]
                   for k in [(t["use"], t["seed"], t["n"], t["ratio"], t["run_s"])] if hb.get(k) != t["hashes"]]
        v = dict(n_traces=after["n_traces"], n_missing_refs_after=after["n_missing_refs"],
                 all_preflight_ok=all(t["preflight_ok"] for t in after["traces"]), n_traces_changed=len(changed),
                 changed=changed[:20])
        (OUT / "d111_enumeration_after.json").write_text(json.dumps(after, indent=1) + "\n")
        (OUT / "d111_verify.json").write_text(json.dumps(v, indent=1) + "\n")
        print(json.dumps({k: x for k, x in v.items() if k != "changed"}))
        if v["n_missing_refs_after"] or v["n_traces_changed"]:
            raise SystemExit("STOP: missing refs remain or a trace / digest changed")


if __name__ == "__main__":
    main()
