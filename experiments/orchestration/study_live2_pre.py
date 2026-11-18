#!/usr/bin/env python3
"""StudyLIVE2-pre: round-1 pre-pilot prerequisites 1 and 3 (prerequisite 2, the dense calibration refit, STOPS on
the score-extraction rule; see the report). Pre-registered in research/EXPERIMENTS.md (StudyLIVE2-pre).

part1  (CPU only, no server)  coverage of the source frames against the dense Orin set (42,014 instants), the
       300-clip set and the 164 S-EMBER EVAL sessions; encode once and store (D91); manifests via the UNCHANGED
       live2 build_manifest.py (E10a distributional check, tol 10 %).
part3  (GPU 2, request-harness pattern) the six-step cache-isolation procedure of reports/study_live2_coord.md
       section 3 with the live2 cache-key and body code.

OVERNIGHT DECISION (recorded in the report; affected outputs PROVISIONAL): experiments/orchestration/live2/data/
encode_jpeg.py was written on flash without the data and its two input parsers do not match the frame stores on this
host: (a) Nexar SMALL frames are `<clip>/<pts_ms>.png` (StudyD14 / D14b `d14b_prepare.py`), not `<clip>_t<s>.png`,
so every frame would be UNPARSED; (b) S-EMBER D2 is not an r1_inputs construction (r1_inputs holds only RICH and
RECENT npz); E10a built D2 from `~/.cache/fm-switching/sember_frames` with `study_rh3_inputs.load(path, (352, 256))`
(experiments/cost/study_e10a_sizes.py:84-85). This wrapper applies the SAME recipe through the correct inputs:
  Nexar   frame for instant (clip, t) = the committed D14b N = 1 request's frame (results/dashcam/study_d14b/
          d14b_requests_manifest.jsonl.gz, frame_keys[0], sha256 verified), then
          `Image.open(png).convert("RGB").save(buf, "JPEG", quality=90)` (encode_jpeg.py's / E10a's call);
  S-EMBER D2 frames at the 2-s stride of every EVAL session (`t % 2 == 0`, the RH4 / RH6 D2 selection), loaded with
          E10a's D2 loader and saved with `save(buf, "JPEG", quality=88)`.
Frame refs are the ones fleet/trace.py puts on the wire: `<file_name>|t<tttt.tt>` (Nexar) and `<sid>|f<tttttt.tt>`
(S-EMBER). The store layout (frames/, encode_log.jsonl, encode_meta.json) is what build_manifest.py reads.
Source frames are only read, never modified, moved or deleted.
"""
import argparse
import asyncio
import gzip
import hashlib
import io
import math
import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LIVE2 = HERE / "live2"
sys.path.insert(0, str(LIVE2))
sys.path.insert(0, str(LIVE2 / "data"))
sys.path.insert(0, str(LIVE2 / "fleet"))
sys.path.insert(0, str(REPO / "experiments/sember"))

OUT = REPO / "results/orchestration/live2/pre"
STORE = Path.home() / "data/live2/jpeg"
D14B_REQ = REPO / "results/dashcam/study_d14b/d14b_requests_manifest.jsonl.gz"
D14B_FR = REPO / "results/dashcam/study_d14b/frames_sha256_manifest.jsonl.gz"
NEX_SRC = (Path.home() / "data/dashcam/d14_frames/small", Path.home() / "data/dashcam/d14b_frames/small")
SEM_SRC = Path.home() / ".cache/fm-switching/sember_frames"
D2_STRIDE = 2.0


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(OUT / "live2_pre.log", "a") as f:
        f.write(line + "\n")


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------------------------------------ coverage
def nexar_plan():
    import data_sources as DS
    dense = DS.orin_dense_scores()                                  # (file_name, t) -> row; 42,014
    clips = DS.nexar_clip_meta()                                    # 300-clip set
    req = {}
    for ln in gzip.open(D14B_REQ, "rt"):
        r = json.loads(ln)
        if int(r["n"]) == 1:
            req[(r["file_name"], round(float(r["t"]), 6))] = r
    paths = {}
    for ln in gzip.open(D14B_FR, "rt"):
        r = json.loads(ln)
        paths[(r["file_name"], r["key"])] = (r["path"], r["small_sha256"])
    plan, missing = [], defaultdict(list)
    for (fn, t), _ in sorted(dense.items()):
        q = req.get((fn, t))
        if q is None:
            missing["no_d14b_request"].append([fn, t])
            continue
        key = q["frame_keys"][0]
        p = paths.get((fn, key))
        if p is None or not Path(p[0]).exists():
            missing["frame_file_absent"].append([fn, t, key])
            continue
        plan.append(dict(file_name=fn, t=t, key=key, src=p[0], sha=q["small_sha256"][0],
                         frame_ref=f"{fn}|t{t:07.2f}"))
    dense_clips = {fn for fn, _ in dense}
    cov = dict(dense_rows=len(dense), dense_clips=len(dense_clips), clip_set=len(clips),
               clip_set_not_in_dense=sorted(set(clips) - dense_clips), dense_not_in_clip_set=sorted(dense_clips - set(clips)),
               planned=len(plan), missing={k: dict(n=len(v), first=v[:5]) for k, v in missing.items()},
               source_dirs=[str(p) for p in NEX_SRC],
               n_png_in_source_dirs=sum(1 for d in NEX_SRC for _ in d.rglob("*.png")))
    return plan, cov


def sember_plan():
    import data_sources as DS
    sess = DS.eval_sessions()
    plan, missing = [], defaultdict(list)
    for sid, sm in sorted(sess.items()):
        ix = SEM_SRC / sid / "index.json"
        if not ix.exists():
            missing["no_frame_dir"].append(sid)
            continue
        idx = {float(t): SEM_SRC / sid / f for t, f in json.load(open(ix))["frames"]}
        ts = [t for t in sorted(idx) if t % D2_STRIDE == 0 and t <= sm.duration_s + 1e-9]
        last_q = max(q.t_ask for q in sm.questions)
        if not ts or ts[-1] + D2_STRIDE < last_q:
            missing["frames_do_not_reach_last_question"].append([sid, ts[-1] if ts else None, last_q])
        for t in ts:
            if not idx[t].exists():
                missing["frame_file_absent"].append([sid, t])
                continue
            plan.append(dict(sid=sid, t=t, src=str(idx[t]), frame_ref=f"{sid}|f{t:08.2f}"))
    cov = dict(eval_sessions=len(sess), planned_frames=len(plan), source_dir=str(SEM_SRC),
               missing={k: dict(n=len(v), first=v[:5]) for k, v in missing.items()})
    return plan, cov


# ------------------------------------------------------------------------------------------------ encode workers
def enc_nexar(job):
    from PIL import Image
    png = Path(job["src"]).read_bytes()
    ok = sha(png) == job["sha"]
    im = Image.open(io.BytesIO(png)).convert("RGB")
    size = im.size
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)                         # encode_jpeg.py / E10a Job A call
    rel = f"{job['file_name'].split('.')[0]}/t{job['t']:07.2f}.jpg"
    dst = STORE / "nexar_q90/frames" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue())
    return dict(file=rel, frame_ref=job["frame_ref"], src=job["src"], src_sha_ok=ok, size=list(size))


def enc_sember(job):
    import study_rh3_inputs as B3
    im = B3.load(job["src"], (352, 256))                             # E10a's D2 loader (study_e10a_sizes.py:84-85)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)                         # E10a S-EMBER call
    rel = f"{job['sid']}/f{job['t']:08.2f}.jpg"
    dst = STORE / "sember_d2_q88/frames" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue())
    return dict(file=rel, frame_ref=job["frame_ref"], src=job["src"], size=[im.width, im.height])


def encode(name, plan, fn, quality, dataset, construction, procs):
    import encode_jpeg as EJ
    store = STORE / name
    if (store / "frames").exists() and any((store / "frames").iterdir()):
        raise SystemExit(f"{store}/frames already populated; refusing to overwrite (encode once, D91)")
    (store / "frames").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with ProcessPoolExecutor(procs) as ex:
        rows = list(ex.map(fn, plan, chunksize=64))
    with open(store / "encode_log.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    meta = dict(dataset=dataset, construction=construction, quality=quality, versions=EJ.versions(),
                n_frames=len(rows), sizes=dict(Counter(tuple(r["size"]) for r in rows).most_common()),
                recipe=("Nexar: Image.open(png).convert('RGB').save(JPEG, quality=90)" if dataset == "nexar" else
                        "S-EMBER D2: study_rh3_inputs.load(path, (352, 256)) then save(JPEG, quality=88)"),
                byte_exactness_to_e10a=False, written_by="experiments/orchestration/study_live2_pre.py",
                overnight_decision="input parsing through the committed D14b instant-to-frame manifest (Nexar) and "
                                   "E10a's D2 loader on sember_frames (S-EMBER); same recipe as encode_jpeg.py",
                seconds=round(time.time() - t0, 1))
    if dataset == "nexar":
        meta["source_sha_mismatch"] = sum(1 for r in rows if not r["src_sha_ok"])
    (store / "encode_meta.json").write_text(json.dumps({**meta, "sizes": {str(k): v for k, v in meta["sizes"].items()}},
                                                       indent=2, sort_keys=True) + "\n")
    log(f"encoded {name}: {len(rows)} frames in {meta['seconds']} s; sizes {meta['sizes']}")
    return store, meta


def part1(procs):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifests").mkdir(exist_ok=True)
    nplan, ncov = nexar_plan()
    splan, scov = sember_plan()
    cov = dict(nexar=ncov, sember=scov, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    (OUT / "live2_pre_coverage.json").write_text(json.dumps(cov, indent=1) + "\n")
    log(f"coverage: nexar dense {ncov['dense_rows']} planned {ncov['planned']} missing {ncov['missing']}; "
        f"clip set {ncov['clip_set']} (not in dense {len(ncov['clip_set_not_in_dense'])}); "
        f"sember sessions {scov['eval_sessions']} frames {scov['planned_frames']} missing {scov['missing']}")
    if ncov["missing"] or ncov["clip_set_not_in_dense"] or scov["missing"]:
        raise SystemExit("PART 1 COVERAGE INCOMPLETE: STOP (no substitution)")
    res = {}
    for name, plan, fn, q, ds, con in (("nexar_q90", nplan, enc_nexar, 90, "nexar", None),
                                       ("sember_d2_q88", splan, enc_sember, 88, "sember", "D2")):
        store, meta = encode(name, plan, fn, q, ds, con, procs)
        if ds == "nexar" and meta["source_sha_mismatch"]:
            raise SystemExit(f"{meta['source_sha_mismatch']} Nexar source PNGs differ from the D14b sha256: STOP")
        import subprocess
        p = subprocess.run([sys.executable, str(LIVE2 / "data/build_manifest.py"), "--store", str(store),
                            "--dataset", ds], capture_output=True, text=True)
        mm = json.loads((store / "manifest_meta.json").read_text())
        res[name] = dict(exit=p.returncode, any_flagged=mm["any_flagged"], checks=mm["e10a_checks"], bytes=mm["bytes"],
                         versions=mm["versions"], n_frames=mm["n_frames"])
        with open(store / "manifest.jsonl", "rb") as fi, gzip.open(OUT / "manifests" / f"{name}_manifest.jsonl.gz", "wb") as fo:
            fo.write(fi.read())
        (OUT / "manifests" / f"{name}_manifest_meta.json").write_text((store / "manifest_meta.json").read_text())
        (OUT / "manifests" / f"{name}_encode_meta.json").write_text((store / "encode_meta.json").read_text())
        log(f"manifest {name}: exit {p.returncode}, any_flagged {mm['any_flagged']}, bytes {mm['bytes']}")
    (OUT / "live2_pre_part1.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    if any(v["any_flagged"] or v["exit"] for v in res.values()):
        raise SystemExit("PART 1: a quartile is FLAGGED against E10a: STOP")
    log("PART 1 PASS")


# ------------------------------------------------------------------------------------------------ part 3
ENG1C_META = REPO / "results/cost/study_eng1c/eng1c_run_meta_h100nvl.json"
CAP_TIGHT = 27
GPU_POOL = 62944
N_NEXAR_FR = 16                 # one Nexar clip: its first 16 dense instants (8 s), one request
SEM_H0_S, SEM_APPEND_S = 60.0, 30.0


def start_server27():
    """The round-1 server: StudyENG1c's KV-HOST launch (flags of DE_c38, the most recent ENG1c / ENG1e command)
    with ONLY --kv-offloading-size 38 -> 27 (TIGHT). ENG1 stat-logger plugin loaded as in ENG1c (observe-only);
    no ENG1e add-on."""
    sys.path.insert(0, str(REPO / "experiments/cost"))
    import study_eng1_steptime as M
    X, E, F = M.X, M.E, M.F
    X.META_PATH = OUT / "live2_pre_run_meta_h100nvl.json"
    X.CURRENT = REPO / "logs/live2_pre_current.json"
    M.G.X.META_PATH = X.META_PATH
    E.MON = OUT / "live2_pre_monitor_h100nvl.jsonl"
    snap = E.snapshot("start")
    if snap["ours_outside_job"] or snap["foreign_on_gpu"]:
        raise SystemExit(f"GPU 2 not exclusive at start: {snap['foreign_on_gpu']} {snap['ours_outside_job']}: STOP")
    F.require_idle()
    ref = next(x["flags"] for x in json.loads(ENG1C_META.read_text())["servers"] if x["label"] == "DE_c38")
    flags = M.E.COMMON + ["--kv-offloading-backend", "native", "--kv-offloading-size", f"{CAP_TIGHT:g}"] + \
        M.D.LOGFLAGS + ["--enable-logging-iteration-details"]
    diff = [(a, b) for a, b in zip(ref, flags) if a != b] + ([("len", len(ref), len(flags))] if len(ref) != len(flags)
                                                            else [])
    if diff != [("38", "27")]:
        raise SystemExit(f"flag diff vs ENG1c DE_c38 is {diff}, expected only the host size 38 -> 27: STOP")
    os.environ["PYTHONPATH"] = str(M.PLUGIN_DIR)
    os.environ["ENG1_STATLOG_PATH"] = str(OUT / "live2_pre_statlog.jsonl")
    srv = X.Server("32BI", flags)
    info = srv.start()
    os.environ.pop("PYTHONPATH", None)
    txt = Path(srv.logpath).read_text(errors="replace")
    import re
    import vllm
    mm = re.findall(r"Created mmap file \S+ \(([\d.]+) GB\)", txt)
    ver = re.findall(r"Initializing a V1 LLM engine \((v[\d.]+)\)", txt)
    meta = dict(command=info.get("server_cmd"), flags=flags, flag_diff_vs_eng1c_DE_c38=diff, vllm=vllm.__version__,
                engine_version_line=ver[-1] if ver else None, kv_cache_tokens=info.get("kv_cache_tokens"),
                mmap_gb=float(mm[-1]) if mm else None, plugin_loaded="eng1_statlog" in txt, log=str(srv.logpath),
                git_head=os.popen(f"git -C {REPO} rev-parse HEAD").read().strip(), started=time.strftime("%Y-%m-%dT%H:%M:%S"))
    bad = None
    if info.get("kv_cache_tokens") != GPU_POOL:
        bad = f"GPU pool {info.get('kv_cache_tokens')} != {GPU_POOL}"
    elif not meta["mmap_gb"] or abs(meta["mmap_gb"] - CAP_TIGHT * 2 ** 30 / 1e9) > 0.005 * CAP_TIGHT * 2 ** 30 / 1e9:
        bad = f"host cap not enforced: mmap {meta['mmap_gb']} GB"
    (OUT / "live2_pre_server.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")
    if bad:
        srv.stop()
        raise SystemExit(f"{bad}: STOP")
    log(f"server up: vLLM {meta['vllm']} ({meta['engine_version_line']}), pool {meta['kv_cache_tokens']}, mmap {meta['mmap_gb']} GB, "
        f"flag diff vs DE_c38 {diff}")
    return srv, M, meta


def post(body):
    """One streamed request (request-harness pattern); usage parsed like live2 backend.cached_tokens_of."""
    import httpx
    import bodies as B
    import backend as BE
    payload = B.strip_internal(body, strip_hints=True)
    t0 = time.time()
    usage, first, err = {}, None, None
    try:
        with httpx.stream("POST", "http://127.0.0.1:8031/v1/chat/completions", json=payload, timeout=None) as r:
            if r.status_code != 200:
                err = f"HTTP {r.status_code}: {r.read()[:300]!r}"
            else:
                for line in r.iter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    j = json.loads(line[6:])
                    if j.get("usage"):
                        usage = j["usage"]
                    if first is None and any((c.get("delta") or {}).get("content") for c in j.get("choices", [])):
                        first = time.time()
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    return dict(status="ok" if err is None else "error", error=err, prompt_tokens=BE.prompt_tokens_of(usage),
                cached_tokens=BE.cached_tokens_of(usage), latency_s=round(time.time() - t0, 4),
                ttft_s=round(first - t0, 4) if first else None, cache_salt=payload.get("cache_salt"),
                n_images=sum(1 for c in payload["messages"][0]["content"] if c.get("type") == "image_url"),
                n_bytes_images=sum(1 for c in payload["messages"][0]["content"]
                                   if c.get("type") == "image_url" and c.get("image_url")),
                body_sha=B.body_digest(body))


def part3():
    import bodies as B
    import cachekeys as K
    import coordinator as CO
    nex = [json.loads(l) for l in open(STORE / "nexar_q90/encode_log.jsonl")]
    sem = [json.loads(l) for l in open(STORE / "sember_d2_q88/encode_log.jsonl")]
    clip = "00005.mp4"
    nfr = sorted((r for r in nex if r["frame_ref"].startswith(clip + "|")), key=lambda r: r["frame_ref"])[:N_NEXAR_FR]
    sid = sorted({r["frame_ref"].split("|")[0] for r in sem})[0]
    sfr = sorted((r for r in sem if r["frame_ref"].startswith(sid + "|")), key=lambda r: r["frame_ref"])
    h0 = [r for r in sfr if float(r["frame_ref"].split("|f")[1]) < SEM_H0_S]
    app = [r for r in sfr if SEM_H0_S <= float(r["frame_ref"].split("|f")[1]) < SEM_H0_S + SEM_APPEND_S]
    tag = K.run_tag(0, "live2_pre_isolation")
    salt = {d: K.cache_salt(tag, d) for d in ("A", "B")}

    def frames(rows, root, bytes_for):
        return [dict(frame_ref=r["frame_ref"], path=(root / "frames" / r["file"]) if r["frame_ref"] in bytes_for else None)
                for r in rows]

    def body(dev, session, fr, kind):
        return B.build_body(kind=kind, device_id=dev, session_id=session, run_tag=tag, salt=salt[dev],
                            header=CO.HEADER_TEXT, frames=fr, question=None, options=(), max_tokens=1)

    srv, M, meta = start_server27()
    steps = []
    try:
        nall = {r["frame_ref"] for r in nfr}
        seq = [("2", "A", "nexar first send", body("A", clip, frames(nfr, STORE / "nexar_q90", nall), "monitor")),
               ("3", "B", "nexar same clip, device B first send", body("B", clip, frames(nfr, STORE / "nexar_q90", nall), "monitor")),
               ("4", "A", "nexar device A repeat, unchanged", body("A", clip, frames(nfr, STORE / "nexar_q90", nall), "monitor"))]
        sroot = STORE / "sember_d2_q88"
        allh = {r["frame_ref"] for r in h0 + app}
        newb = {r["frame_ref"] for r in app}
        seq += [("5a", "A", "sember history H0 (60 s), first send", body("A", sid, frames(h0, sroot, {r["frame_ref"] for r in h0}), "append")),
                ("5b", "A", "sember 30 s append: refs for H0 + bytes for new", body("A", sid, frames(h0 + app, sroot, newb), "append")),
                ("5c", "B", "sember same content, device B first send", body("B", sid, frames(h0 + app, sroot, allh), "append")),
                ("5d", "A", "sember device A repeat of its append, unchanged", body("A", sid, frames(h0 + app, sroot, newb), "append"))]
        for step, dev, what, b in seq:
            r = post(b)
            r.update(step=step, device=dev, what=what, mm_uuid_example=b["_live2"]["mm_uuids"][0],
                     n_uuids=len(b["_live2"]["mm_uuids"]))
            steps.append(r)
            log(f"step {step} {dev}: {what}: prompt {r['prompt_tokens']} cached {r['cached_tokens']} "
                f"({r['status']}{'' if not r['error'] else ' ' + r['error']})")
            time.sleep(0.5)
    finally:
        srv.stop()
        snap = M.E.snapshot("end")
    by = {s["step"]: s for s in steps}
    ok = lambda k, cond: by.get(k) is not None and by[k]["status"] == "ok" and by[k]["cached_tokens"] is not None and cond(by[k]["cached_tokens"])
    rule = dict(step3_B_first_zero=ok("3", lambda c: c == 0), step5c_B_first_zero=ok("5c", lambda c: c == 0),
                step4_A_repeat_positive=ok("4", lambda c: c > 0), step5d_A_repeat_positive=ok("5d", lambda c: c > 0))
    verdict = "PASS" if all(rule.values()) else "FAIL"
    out = dict(study="StudyLIVE2-pre Part 3 (D84 cache isolation)", pass_rule=("device B's first send of content device A "
               "already sent reports cached_tokens == 0 (steps 3 and 5) AND device A's repeat reports cached_tokens > 0 "
               "(steps 4 and 5)"), rule=rule, verdict=verdict, steps=steps, run_tag=tag, salts=salt, nexar_clip=clip,
               nexar_frames=len(nfr), sember_session=sid, sember_h0_frames=len(h0), sember_append_frames=len(app),
               header=CO.HEADER_TEXT, server=meta, end_snapshot_foreign=snap.get("foreign_on_gpu"),
               at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    (OUT / "live2_pre_cache_isolation.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    log(f"PART 3 {verdict}: {rule}")


# ------------------------------------------------------------------------------------------------ part 2
# User ruling 2026-11-18: run Part 2 now with the committed StudyD3 body that StudyLIVE2-fix2 copies into the live
# coordinator: experiments/dashcam/d3_infer_vllm.py body() (QUERY lines 43-44, N = 1 header, GEN = temperature 0.0,
# max_tokens 8, seed 0, logprobs True, top_logprobs 20) with ONE change, stream=True; image = the stored q90 JPEG of
# each dense instant; plus a per-request cache_salt (the user's instruction) so no request reuses another's cache.
# Score: d3_infer_vllm.yes_no() on the first token's top-20, then log(p_yes) (ctrl1c_calibrate.py 276-277, 298).
# The calibration file is labelled PENDING-BODY-CHECK until the fix2 body check passes.
P2_CONC = 8
P2_HDR = "The following is 1 dashcam frame."


def p2_body(jpeg: bytes, salt: str):
    sys.path.insert(0, str(REPO / "experiments/dashcam"))
    import d3_infer_vllm as D3
    import base64
    content = [{"type": "text", "text": P2_HDR},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}},
               {"type": "text", "text": D3.QUERY}]
    bd = dict(model="32BI", messages=[{"role": "user", "content": content}], stream=True, **D3.GEN)
    bd["cache_salt"] = salt
    return bd


async def p2_one(c, row, sem, attempt):
    import httpx  # noqa: F401
    sys.path.insert(0, str(REPO / "experiments/dashcam"))
    import d3_infer_vllm as D3
    jpeg = (STORE / "nexar_q90/frames" / row["file"]).read_bytes()
    salt = hashlib.sha256(f"live2pre-p2|{row['frame_ref']}|{attempt}".encode()).hexdigest()[:43]
    b = p2_body(jpeg, salt)
    async with sem:
        t0 = time.time()
        lp, text, err, rid, first = [], "", None, None, None
        try:
            async with c.stream("POST", "http://127.0.0.1:8031/v1/chat/completions", json=b) as r:
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}: {(await r.aread())[:300]!r}"
                else:
                    async for line in r.aiter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        j = json.loads(line[6:])
                        rid = rid or j.get("id")
                        for ch in j.get("choices", []):
                            d = (ch.get("delta") or {}).get("content")
                            if d:
                                text += d
                                first = first or time.time()
                            lp += ((ch.get("logprobs") or {}).get("content") or [])
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        p, y, n = D3.yes_no(lp)
        import math
        return dict(frame_ref=row["frame_ref"], file=row["file"], attempt=attempt, server_id=rid, cache_salt=salt,
                    text=text, first_token=lp[0]["token"] if lp else None, p_yes=p, mass_yes=y, mass_no=n,
                    score=(math.log(p) if p else None), neither=(p is None and err is None), error=err,
                    latency_s=round(time.time() - t0, 4), ttft_s=round(first - t0, 4) if first else None,
                    t_submit=round(t0, 6))


async def p2_requests(rows):
    import httpx
    sem = asyncio.Semaphore(P2_CONC)
    out_p = OUT / "live2_pre_part2_requests.jsonl"
    done = {}
    async with httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=None)) as c:
        for i in range(0, len(rows), 400):
            res = await asyncio.gather(*(p2_one(c, r, sem, 1) for r in rows[i:i + 400]))
            with open(out_p, "a") as f:
                for x in res:
                    f.write(json.dumps(x) + "\n")
                    done[x["frame_ref"]] = x
            if (i // 400) % 10 == 0:
                log(f"part2: {min(i + 400, len(rows))}/{len(rows)} sent; errors so far "
                    f"{sum(1 for v in done.values() if v['error'] or v['p_yes'] is None)}")
        bad = [r for r in rows if done[r["frame_ref"]]["error"] or done[r["frame_ref"]]["p_yes"] is None]
        if bad:
            log(f"part2: retrying {len(bad)} failed / unscored requests once")
            res = await asyncio.gather(*(p2_one(c, r, sem, 2) for r in bad))
            with open(out_p, "a") as f:
                for x in res:
                    f.write(json.dumps(x) + "\n")
                    done[x["frame_ref"]] = x
    return done


def ap_labels():
    """Per-instant labels of the scorer's streaming AP (StudyE9b grid via the fleet scorer's loader): a positive
    clip's instant is positive iff it is the clip's AP target for some horizon in scorer.AP_HORIZONS (grid point
    nearest event - h on E9b's absolute 0.25-s grid, clamped); every instant of a negative clip is negative; any other
    instant of a positive clip has no label under that definition (counted and reported)."""
    import data_sources as DS
    sys.path.insert(0, str(REPO / "experiments/dashcam"))
    sys.path.insert(0, str(LIVE2 / "scorer"))
    import study_e9b_dense as B9
    import score as SC
    clips = DS.nexar_clip_meta()
    lab = {}
    for clip, cm in clips.items():
        G = len([1 for _ in range(int(round((cm.duration_s - B9.T0) / 0.25)) + 1)])
        meta = {clip: dict(event=cm.event_s, G=G)}
        tg = set()
        if cm.label == "positive" and cm.event_s is not None:
            for h in SC.AP_HORIZONS:
                i = B9.target_index(meta, clip, h, 0.25)
                tg.add(round(B9.T0 + 0.25 * i, 6))
        lab[clip] = (cm.label, tg)
    return lab, tuple(SC.AP_HORIZONS)


def part2():
    import numpy as np
    sys.path.insert(0, str(REPO / "experiments/dashcam"))
    import ctrl1c_calibrate as CC
    import data_sources as DS
    enc = [json.loads(l) for l in open(STORE / "nexar_q90/encode_log.jsonl")]
    dense = DS.orin_dense_scores()
    rows = [r for r in enc if (r["frame_ref"].split("|")[0], round(float(r["frame_ref"].split("|t")[1]), 6)) in dense]
    if len(rows) != 42014:
        raise SystemExit(f"part2: {len(rows)} stored frames match the dense set, expected 42,014: STOP")
    rows.sort(key=lambda r: r["frame_ref"])
    srv, M, meta = start_server27()
    try:
        done = asyncio.run(p2_requests(rows))
    finally:
        srv.stop()
    # ---- fit (server down)
    lab, horizons = ap_labels()
    folds = json.loads((REPO / "results/dashcam/ctrl1c/ctrl1c_calibration.json").read_text())
    assign, fold_rule = folds["assignment"], folds["fold_rule"]
    recs = []
    unl = 0
    for r in rows:
        fn, t = r["frame_ref"].split("|")[0], round(float(r["frame_ref"].split("|t")[1]), 6)
        x = done[r["frame_ref"]]
        lb, tg = lab[fn]
        y_ap = (1.0 if t in tg else None) if lb == "positive" else 0.0
        unl += y_ap is None
        recs.append(dict(fn=fn, t=t, fold=assign[fn], s32=x["score"], sorin=dense[(fn, t)]["score"],
                         y_ap=y_ap, y_clip=1.0 if lb == "positive" else 0.0))
    missing = [r for r in recs if r["s32"] is None]
    res = dict(label="PENDING-BODY-CHECK", fit_sample="dense", n_instants=len(recs), n_unscored_32b=len(missing),
               labels=dict(primary="streaming-AP per-instant labels (scorer.AP_HORIZONS %s): positive = a positive "
                                   "clip's AP target instant; negative = every instant of a negative clip; other "
                                   "positive-clip instants unlabelled" % (horizons,),
                           n_unlabelled=unl, n_pos=sum(1 for r in recs if r["y_ap"] == 1.0),
                           n_neg=sum(1 for r in recs if r["y_ap"] == 0.0),
                           secondary="clip-level label on every instant (StudyCTRL1c / ORIN2 convention)"),
               fold_rule=fold_rule, clip_to_fold=assign, request_body=dict(
                   source="experiments/dashcam/d3_infer_vllm.py body() with stream=True; per-request cache_salt",
                   sha256_template=hashlib.sha256(json.dumps(p2_body(b"", "SALT"), sort_keys=True).encode()).hexdigest(),
                   concurrency=P2_CONC),
               jpeg_manifest_sha256=hashlib.sha256((OUT / "manifests/nexar_q90_manifest.jsonl.gz").read_bytes()).hexdigest(),
               server=meta, fits={})
    for lname, key in (("primary_ap_labels", "y_ap"), ("secondary_clip_labels", "y_clip")):
        for tier, sk in (("h100_32b", "s32"), ("orin_4b", "sorin")):
            per, oof = {}, []
            for k in range(5):
                tr = [r for r in recs if r["fold"] != k and r[key] is not None and r[sk] is not None]
                te = [r for r in recs if r["fold"] == k and r[key] is not None and r[sk] is not None]
                f = CC.fit_platt(np.array([r[sk] for r in tr]), np.array([r[key] for r in tr]))
                per[k] = dict(a=f["a"], b=f["b"], n_train=len(tr), n_test=len(te))
                for r in te:
                    z = f["a"] * r[sk] + f["b"]
                    oof.append((1.0 / (1.0 + math.exp(-z)), r[key]))
            pr = np.array([p for p, _ in oof])
            yy = np.array([y for _, y in oof])
            ll = float(-np.mean(yy * np.log(np.clip(pr, 1e-15, 1)) + (1 - yy) * np.log(np.clip(1 - pr, 1e-15, 1))))
            base = float(yy.mean())
            llb = float(-(base * math.log(base) + (1 - base) * math.log(1 - base))) if 0 < base < 1 else None
            bins = np.linspace(0, 1, 11)
            rel = []
            for lo_, hi_ in zip(bins[:-1], bins[1:]):
                m = (pr >= lo_) & (pr < hi_ if hi_ < 1 else pr <= hi_)
                if m.any():
                    rel.append(dict(bin=[round(lo_, 1), round(hi_, 1)], n=int(m.sum()), mean_pred=float(pr[m].mean()),
                                    frac_pos=float(yy[m].mean())))
            a_s = [v["a"] for v in per.values()]
            res["fits"].setdefault(lname, {})[tier] = dict(
                per_fold=per, a_mean=float(np.mean(a_s)), a_spread=[float(min(a_s)), float(max(a_s))],
                b_mean=float(np.mean([v["b"] for v in per.values()])), oof_log_loss=ll, base_rate_log_loss=llb,
                oof_reliability=rel, n=len(oof))
    import math as _m  # noqa: F401
    (REPO / "results/orchestration/live2/calibration").mkdir(parents=True, exist_ok=True)
    outp = REPO / "results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json"
    outp.write_text(json.dumps(res, indent=1, default=float) + "\n")
    log(f"PART 2 written ({res['label']}): unscored {len(missing)}, unlabelled {unl}; "
        + "; ".join(f"{ln} {t} a {v['a_mean']:.4f} [{v['a_spread'][0]:.4f}, {v['a_spread'][1]:.4f}] b {v['b_mean']:.3f} "
                    f"ll {v['oof_log_loss']:.4f}" for ln, d in res["fits"].items() for t, v in d.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=("part1", "part2", "part3"))
    ap.add_argument("--procs", type=int, default=32)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.part == "part1":
        part1(a.procs)
    elif a.part == "part2":
        part2()
    else:
        part3()


if __name__ == "__main__":
    main()
