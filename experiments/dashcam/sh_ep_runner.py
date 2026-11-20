#!/usr/bin/env python3
"""StudySH-EP runner: one OpenAI-compatible vLLM endpoint, one request at a time.

Pre-registered in research/EXPERIMENTS.md (StudySH-EP) and reports/study_sh_ep.md. The SAME
runner runs on the H100 and on the Orin; only --base, --model and --store differ.

  python3 -I experiments/dashcam/sh_ep_runner.py --base http://127.0.0.1:8000 \\
      --model 32BI --store ~/data/live2/jpeg/nexar_q90 --run-tag shep1

WHAT IT SENDS
  The body is the committed SH body with ONE declared shape change: more than one image. Its
  question text and generation parameters are READ out of `experiments/dashcam/d3_infer_vllm.py`
  (QUERY, GEN), never retyped; its header is read out of the frozen request manifest, which is
  where the header rule lives. `live2/bodies.build_body(kind="monitor")` is NOT used: it refuses
  any body with more than one frame, by design, so a multi-frame SH body cannot go through it.

  Exemptions over the committed SH body, all declared, all already in force for live2 round 1:
    * JPEG wire bytes from the D91 store, where StudyD3 and StudyD14b sent PNG (D70, D91);
    * `cache_salt` and a per-image client `uuid` (D84), which post-date both studies;
    * `stream` true, so the first token can be timed (live2's own third declared deviation).

  A frame's BYTES go out once per (clip, condition); every later request that carries the same
  frame sends the uuid-only reference, which is `bodies.image_part`'s delta mode. The uuid carries
  the condition, so one condition's warm state cannot be read by another (D84).

STACK DEVIATIONS THAT MUST BE DECLARED IN THE REPORT
  The committed SH stack (StudyD3 / D14b / D7) runs with PREFIX CACHING OFF,
  --mm-processor-cache-gb 0 and --limit-mm-per-prompt image 9. This study cannot: H3 is a claim
  about warm episodes, so prefix caching and the multimodal processor cache must be ON, and EP-G
  carries up to 21 images. Caching is a methodological parameter (CLAUDE.md), so the runner
  RECORDS the server's own reported configuration and refuses to run if it cannot read it, and the
  report carries the positive control that says what the change did to the scores.
"""
from __future__ import annotations

import argparse
import ast
import base64
import gzip
import hashlib
import json
import math
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/orchestration/live2"))
from _provenance import stamp  # noqa: E402
from cachekeys import mm_uuid  # noqa: E402

MAN = ROOT / "results/dashcam/study_sh_ep"
D3_SCRIPT = ROOT / "experiments/dashcam/d3_infer_vllm.py"
MODELS = {"4BI": "Qwen/Qwen3-VL-4B-Instruct", "32BI": "Qwen/Qwen3-VL-32B-Instruct"}
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout",
             "ConnectTimeout", "PoolTimeout", "WriteTimeout", "CloseError")
ATTEMPTS = 3
HOST = os.uname().nodename   # recorded per RECORD, not only per run: the 4BI set runs on the
                             # H100 and on the Orin, and the cross-stack table joins them by host
N_GREY = 100                 # StudyD3's own grey count
GREY_SIZE = (768, 432)       # StudyD14b SMALL, the pixel grid of every stored frame


def committed(name, consts=()):
    """One function or constant out of the committed StudyD3 script, evaluated not retyped.

    The module is never imported: its body rewrites sys.path, opens httpx and starts a server.
    The extracted source's sha256 goes into the run meta, so an edit to the committed rule cannot
    pass unnoticed.
    """
    tree = ast.parse(D3_SCRIPT.read_text(), filename=str(D3_SCRIPT))
    want, body = set(consts), []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in want for t in node.targets):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == name:
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            body.append(node)
    text = "\n".join(ast.unparse(n) for n in body)
    ns = {"math": math, "__name__": "committed_d3"}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(D3_SCRIPT), "exec"), ns)  # noqa: S102
    return ns[name], hashlib.sha256(text.encode()).hexdigest()


yes_no, YES_NO_SHA = committed("yes_no")
QUERY, QUERY_SHA = committed("QUERY")
GEN, GEN_SHA = committed("GEN")


def store_path(store, clip, key, flat):
    """Resolve a frame in the D91 nexar store, under EITHER layout it is found in.

    `live2/data/encode_jpeg.py` writes one flat file per frame_ref,
    `frames/<clip>.mp4__t<t>.jpg`, and the manifest's `store_files` are built from that rule. The
    H100's actual store is laid out `frames/<clip>/t<t>.jpg`, and StudySH-EP's own 165-frame
    extension wrote flat names beside those clip folders, so the live store MIXES the two. The
    first version of this read the flat name only and died with FileNotFoundError on request one.

    Resolving both here rather than depending on a hand-built symlink view matters for a reason
    beyond convenience: a view is a thing that can be stale or incomplete without the run noticing,
    and a frame silently read from the wrong place is exactly the failure the per-frame sha256
    check below exists to catch. So the runner reads the store as it is, and the checksum still
    has the last word.
    """
    cands = [Path(store) / flat,
             Path(store) / "frames" / clip[:-4] / f"t{flat.rsplit('__t', 1)[-1]}",
             Path(store) / "frames" / clip[:-4] / f"{key}.jpg"]
    for q in cands:
        if q.exists():
            return q
    raise FileNotFoundError(
        f"frame {clip} {key} is in neither store layout; looked at "
        + ", ".join(str(q) for q in cands) + ". Nothing is substituted.")


def grey_jpeg():
    """A grey frame encoded by the D91 nexar recipe, so the control's bytes are the wire form."""
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", GREY_SIZE, (128, 128, 128)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def data_url(b: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(b).decode()


def build_body(row, model, run_tag, store, sent, shuffle_rng=None, grey=None,
               header_key="header"):
    """The request body, plus the bytes actually put on the wire."""
    keys = list(row["frame_keys"])
    files = list(row["store_files"])
    order = list(range(len(keys)))
    if shuffle_rng is not None and len(order) > 1:
        shuffle_rng.shuffle(order)
    clip, cond = row["file_name"], row["condition"]
    salt = "shep-" + hashlib.sha256(
        f"{run_tag}|{clip}|{cond}|{model}".encode()).hexdigest()[:32]
    content = [{"type": "text", "text": row[header_key]}]
    new_bytes, uuids, jpeg_sha = 0, [], {}
    for i in order:
        k = keys[i]
        u = mm_uuid(run_tag, clip, cond, k)
        uuids.append(u)
        if grey is not None:
            content.append({"type": "image_url", "image_url": {"url": data_url(grey)},
                            "uuid": u})
            new_bytes += len(grey)
            continue
        if u in sent:
            content.append({"type": "image_url", "image_url": None, "uuid": u})
            continue
        p = store_path(store, clip, k, files[i])
        b = p.read_bytes()
        got = hashlib.sha256(b).hexdigest()
        content.append({"type": "image_url", "image_url": {"url": data_url(b)}, "uuid": u})
        new_bytes += len(b)
        sent[u] = got
        jpeg_sha[u] = got
    content.append({"type": "text", "text": QUERY})
    body = dict(model=MODELS[model], messages=[dict(role="user", content=content)],
                stream=True, stream_options={"include_usage": True}, cache_salt=salt, **GEN)
    return (body, new_bytes, uuids, salt, [keys[i] for i in order],
            [jpeg_sha.get(u) for u in uuids])


def send(client, body):
    """Stream one request: TTFT, the first token's top-20 logprobs, usage verbatim."""
    t0 = time.perf_counter()
    ttft, lp, usage, text, fin, err = None, None, None, "", None, None
    try:
        with client.stream("POST", "/v1/chat/completions", json=body) as r:
            if r.status_code != 200:
                r.read()
                return dict(error=f"HTTP {r.status_code}: {r.text[:300]}")
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                j = json.loads(payload)
                if j.get("usage"):
                    usage = j["usage"]
                for ch in j.get("choices") or ():
                    d = ch.get("delta") or {}
                    if d.get("content"):
                        if ttft is None:
                            ttft = time.perf_counter() - t0
                        text += d["content"]
                    c = (ch.get("logprobs") or {}).get("content")
                    if c and lp is None:
                        lp = c
                    if ch.get("finish_reason"):
                        fin = ch["finish_reason"]
    except Exception as e:                                                    # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    p, y, n = yes_no(lp)
    u = usage or {}
    det = u.get("prompt_tokens_details")
    return dict(error=err, ttft_s=None if ttft is None else round(ttft, 6),
                wall_s=round(time.perf_counter() - t0, 6), text=text, finish_reason=fin,
                first_token=lp[0]["token"] if lp else None,
                p_yes=p, mass_yes=y, mass_no=n, neither=p is None and err is None,
                score=None if not p else math.log(p),
                prompt_tokens=u.get("prompt_tokens"),
                completion_tokens=u.get("completion_tokens"),
                usage_raw=u,
                # the warm-path read, with PRESENCE separated from zero (CLAUDE.md Step 2): an
                # absent field is an instrument that never reads, a present 0 is a cold prefix
                cached_tokens_present=isinstance(det, dict) and "cached_tokens" in det,
                cached_tokens=(det or {}).get("cached_tokens"))


def server_config(client):
    """Whatever the endpoint will say about its own caching configuration."""
    out = {}
    for path in ("/v1/models", "/version", "/get_server_info"):
        try:
            r = client.get(path, timeout=20.0)
            out[path] = r.json() if r.status_code == 200 else f"HTTP {r.status_code}"
        except Exception as e:                                                # noqa: BLE001
            out[path] = f"{type(e).__name__}: {e}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--model", required=True, choices=sorted(MODELS))
    ap.add_argument("--store", required=True, help="the D91 nexar q90 JPEG store root")
    ap.add_argument("--run-tag", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--conditions", default="C1,C3,C6,EP-B,EP-G")
    ap.add_argument("--sides", default="DEV,EVAL")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--greys", type=int, default=N_GREY)
    ap.add_argument("--shuffle-control", action="store_true",
                    help="re-send C6 and EP-G on the control subset with the context shuffled")
    ap.add_argument("--header-mode", default="constant", choices=("count", "constant"),
                    help="constant (THE RULING, D145, and the default): count-free for every "
                         "multi-frame condition, so the wording cannot confound a context "
                         "comparison and an append-only episode has a real reusable KV prefix; "
                         "C1 keeps StudyD3's committed one-frame literal. count: StudyD3's "
                         "frame-count header, kept as the non-default alternative; under it no "
                         "KV prefix is reusable and H3 is unreachable by construction.")
    ap.add_argument("--timeout", type=float, default=600.0)
    a = ap.parse_args()

    out = Path(a.out) if a.out else MAN / f"sh_ep_requests_{a.model}_{a.run_tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for ln in out.open():
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if not r.get("error"):
                done.add(r["row_id"])
    conds = a.conditions.split(",")
    sides = a.sides.split(",")
    rows = []
    with gzip.open(MAN / "sh_ep_requests_manifest.jsonl.gz", "rt") as fh:
        for ln in fh:
            r = json.loads(ln)
            if r["condition"] in conds and r["side"] in sides:
                rows.append(r)
    # time order WITHIN a (clip, condition), so the append-only conditions warm naturally
    rows.sort(key=lambda r: (r["file_name"], r["condition"], r["t"]))
    if a.limit:
        rows = rows[:a.limit]

    meta_path = MAN / f"sh_ep_run_meta_{a.model}_{a.run_tag}.json"
    hk = "header" if a.header_mode == "count" else "header_constant"
    client = httpx.Client(base_url=a.base.rstrip("/"), timeout=a.timeout)
    cfg = server_config(client)
    sent: dict = {}
    n_err = n_neither = 0
    started = datetime.now().isoformat()
    with out.open("a") as fh:
        for i, row in enumerate(rows):
            rid = f"{row['request_id']}|{a.model}"
            if rid in done:
                continue
            body, nb, uuids, salt, order, jsha = build_body(
                row, a.model, a.run_tag, a.store, sent, header_key=hk)
            rec = send(client, body)
            n_err += bool(rec["error"])
            n_neither += bool(rec["neither"])
            rec.update(row_id=rid, request_id=row["request_id"], model=a.model,
                       file_name=row["file_name"], label=row["label"], side=row["side"],
                       condition=row["condition"], t=row["t"], ref=row["ref"],
                       rel_to_ref=row["rel_to_ref"], lead=row["lead"],
                       n_frames=row["n_frames"], frame_keys_sent_order=order,
                       small_sha256=row["small_sha256"], header=row[hk],
                       header_mode=a.header_mode, jpeg_sha256_sent=jsha, uplink_bytes_new_images=nb,
                       uplink_bytes_body=len(json.dumps(body)),
                       n_new_images=sum(1 for p in body["messages"][0]["content"]
                                        if p.get("type") == "image_url" and p["image_url"]),
                       cache_salt=salt, mm_uuids=uuids, control=None,
                       host=HOST, run_tag=a.run_tag, at=datetime.now().isoformat())
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if (i + 1) % 200 == 0:
                print(f"  {i + 1}/{len(rows)} err {n_err} neither {n_neither}", flush=True)

        # ---- control: grey frames, one per distinct frame count in the run
        grey = grey_jpeg() if a.greys else None
        counts = sorted({r["n_frames"] for r in rows})
        for n in counts:
            proto = next(r for r in rows if r["n_frames"] == n)
            for rep in range(max(1, a.greys // max(1, len(counts)))):
                row = dict(proto, file_name="GREY.mp4",
                           request_id=f"GREY_n{n:02d}_{rep:03d}", condition=proto["condition"])
                body, nb, uuids, salt, order, jsha = build_body(
                    row, a.model, a.run_tag, a.store, {}, grey=grey, header_key=hk)
                rec = send(client, body)
                rec.update(row_id=f"{row['request_id']}|{a.model}", request_id=row["request_id"],
                           model=a.model, file_name=None, label=None, side=None,
                           condition=proto["condition"], t=None, ref=None, rel_to_ref=None,
                           lead=None, n_frames=n, frame_keys_sent_order=[], small_sha256=[],
                           header=row[hk], header_mode=a.header_mode,
                           uplink_bytes_new_images=nb,
                           uplink_bytes_body=len(json.dumps(body)), n_new_images=n,
                           cache_salt=salt, mm_uuids=uuids, control="grey",
                           host=HOST, run_tag=a.run_tag, at=datetime.now().isoformat())
                fh.write(json.dumps(rec) + "\n")
                fh.flush()

        # ---- control: shuffled context order on the pre-registered 50-clip subset
        if a.shuffle_control:
            subset = set(json.loads((MAN / "sh_ep_manifest_meta.json").read_text())
                         ["shuffle_control_clips"])
            rng = random.Random(0)
            for row in rows:
                if row["file_name"] not in subset or row["condition"] not in ("C6", "EP-G"):
                    continue
                if row["n_frames"] < 2:
                    continue
                body, nb, uuids, salt, order, jsha = build_body(
                    row, a.model, a.run_tag + "-shuf", a.store, {}, shuffle_rng=rng,
                    header_key=hk)
                rec = send(client, body)
                rec.update(row_id=f"{row['request_id']}|{a.model}|shuf",
                           request_id=row["request_id"], model=a.model,
                           file_name=row["file_name"], label=row["label"], side=row["side"],
                           condition=row["condition"], t=row["t"], ref=row["ref"],
                           rel_to_ref=row["rel_to_ref"], lead=row["lead"],
                           n_frames=row["n_frames"], frame_keys_sent_order=order,
                           small_sha256=row["small_sha256"], header=row[hk],
                           header_mode=a.header_mode, uplink_bytes_new_images=nb,
                           uplink_bytes_body=len(json.dumps(body)), n_new_images=row["n_frames"],
                           cache_salt=salt, mm_uuids=uuids, control="shuffled",
                           host=HOST, run_tag=a.run_tag, at=datetime.now().isoformat())
                fh.write(json.dumps(rec) + "\n")
                fh.flush()

    meta = dict(label="StudySH-EP inference run", model=a.model, model_id=MODELS[a.model],
                run_tag=a.run_tag, base=a.base, store=str(a.store),
                conditions=conds, sides=sides, header_mode=a.header_mode,
                requests_attempted=len(rows),
                errors=n_err, neither_yes_nor_no=n_neither,
                greys=a.greys, shuffle_control=bool(a.shuffle_control),
                committed_sha256=dict(yes_no=YES_NO_SHA, QUERY=QUERY_SHA, GEN=GEN_SHA),
                question=QUERY, generation=GEN,
                declared_deviations=[
                    "more than one image in the SH body (StudyD3 N = 3 / N = 9 precedent, but "
                    "live2 bodies.build_body(kind='monitor') refuses it)",
                    "frame spacing 0.5 s, not StudyD3's 3 / 8 s: C3 is NOT StudyD3's N = 3",
                    "JPEG wire bytes from the D91 store where D3 / D14b sent PNG (D70, D91)",
                    "cache_salt and per-image client uuid (D84)",
                    "stream true, to time the first token (live2's declared deviation)",
                    "prefix caching and the multimodal processor cache ON, where the committed "
                    "SH stack runs with both OFF; --limit-mm-per-prompt image must be >= 21",
                ],
                server_config=cfg, started=started, finished=datetime.now().isoformat())
    meta["_provenance"] = stamp(script="sh_ep_runner.py", model=a.model,
                                device=os.uname().nodename, n=len(rows), args=a)
    meta_path.write_text(json.dumps(meta, indent=1))
    print(f"wrote {out}\nwrote {meta_path}\nerrors {n_err} neither {n_neither}")


if __name__ == "__main__":
    main()
