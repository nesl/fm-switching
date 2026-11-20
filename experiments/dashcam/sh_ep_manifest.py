#!/usr/bin/env python3
"""StudySH-EP: the request manifest, the frame set and its sha256 manifest (CPU only; no GPU,
no model server, no inference).

Pre-registered in research/EXPERIMENTS.md (StudySH-EP) and reports/study_sh_ep.md before any
inference. Run: python3 -I experiments/dashcam/sh_ep_manifest.py

WHAT IT READS, AND WHY NOTHING IS RENDERED OR ENCODED
  StudyD14b rendered, for every decision time t on the 0.25 s grid, the causal SMALL frame
  (latest decoded pts <= target) for the N = 1 target t and the N = 3 targets t - 3 and t - 1.5.
  The union of those targets over t = 3.0, 3.25, ... is the whole 0.25 s grid from pts 0.0 up, so
  EVERY instant this study needs is ALREADY in the committed D14b frame set, and therefore already
  in the D91 nexar q90 JPEG store that was encoded from that directory. This study renders no
  frame and encodes none: it SELECTS rows of the committed sha256 manifest. That is a selection,
  not a measurement, and it is labelled so in the output.

  results/dashcam/study_d14b/d14b_sample.json              clips, labels, durations, event, alert
  results/dashcam/study_d14b/frames_sha256_manifest.jsonl.gz  every stored frame: key, pts, sha256
  results/dashcam/ctrl1/d14b_split.json                    the committed 90 DEV / 210 EVAL split
  experiments/dashcam/study_e9c_challenge.py               the negatives' matched reference time

THE REFERENCE TIME
  positives: time_of_event, as every committed Nexar study uses it.
  negatives: the committed challenge scorer's own matched fake event time at seed 0
  (`study_e9c_challenge.fake_event_times`, sigma = sample sd of time_of_event - duration / 2 over
  the 150 positives, clipped to [4.5, duration]). StudyD14 and StudyD14b assign negatives NO
  reference at all, and StudyD3's assigned references cover StudyD3's development clips, not
  these 300, so this is the only committed matched reference that exists over this clip set. It is
  also the only choice under which the headline metric is computable: the challenge scorer reads
  each negative at fake_event - h for h in {0.5, 1.0, 1.5}, and those three instants lie inside
  the evaluated window only when the window is anchored on that same fake event time.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from bisect import bisect_right
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
from _provenance import stamp  # noqa: E402

D14B = ROOT / "results/dashcam/study_d14b"
SPLIT = ROOT / "results/dashcam/ctrl1/d14b_split.json"
OUT = ROOT / "results/dashcam/study_sh_ep"

STEP = 0.25                 # the committed D14b render grid; every instant snaps onto it
FPS_STEP = 0.5              # the brief's 2 fps evaluated grid
WINDOW_S = 6.0              # evaluated instants: ref - 6.0 ... ref
EP_G_BACK = 4.0             # EP-G starts 4 s before the first evaluated instant
EP_G_CAP_FRAMES = 21        # about 10 s at 2 fps, inclusive; binds exactly at the last instant
EP_B_BLOCK_S = 5.0          # EP-B resets at each 5 s block boundary from the first instant
CONDITIONS = ("C1", "C3", "C6", "EP-B", "EP-G")
SLIDING = {"C1": 1, "C3": 3, "C6": 6}
N_SHUFFLE_CLIPS = 50        # the shuffled-order control subset, 25 positive + 25 negative
SEED = 0


def snap(t: float) -> float:
    return round(round(t / STEP) * STEP, 2)


def key_of(pts_sorted, keys, t):
    """The committed causal rule: the latest decoded frame with pts <= t."""
    i = bisect_right(pts_sorted, t + 1e-9) - 1
    return (None, None) if i < 0 else (keys[i], pts_sorted[i])


HEADER_CONSTANT = "The following are consecutive dashcam frames, oldest first."


def header_for(n: int) -> str:
    """StudyD3's grey_header generalised to the span this study sends.

    DECLARED DEVIATION: d3_infer_vllm.grey_header hard-codes "covering 3 seconds" because every
    committed multi-frame SH request spans exactly 3 s. The N = 1 string is the committed literal,
    byte for byte.
    """
    if n == 1:
        return "The following is 1 dashcam frame."
    span = (n - 1) * FPS_STEP
    s = str(int(span)) if float(span).is_integer() else ("%.1f" % span)
    unit = "second" if span == 1.0 else "seconds"
    return f"The following are {n} consecutive dashcam frames covering {s} {unit}, oldest first."


def load_n1_store_rows():
    """{(clip, t): (key, sha256)} from the committed D14b N = 1 rows.

    This is exactly the set the D91 nexar encoder walks (`encode_jpeg.iter_nexar` reads the N = 1
    rows and nothing else), so membership here IS membership of the JPEG store, and the store's
    own frame_ref is "<clip>|t<t:07.2f>". An instant below the committed 3.0 s decision grid has
    no row and therefore no stored JPEG; those instants are listed for a store extension rather
    than dropped, so no clip loses context.
    """
    out = {}
    with gzip.open(D14B / "d14b_requests_manifest.jsonl.gz", "rt") as fh:
        for ln in fh:
            r = json.loads(ln)
            if int(r["n"]) == 1:
                out[(r["file_name"], round(float(r["t"]), 2))] = (r["frame_keys"][0],
                                                                  r["small_sha256"][0])
    return out


def store_ref(clip, t):
    return f"{clip}|t{t:07.2f}"


def store_file(ref):
    return "frames/" + ref.replace("|", "__").replace("/", "_") + ".jpg"


def load_frames():
    by_clip = {}
    with gzip.open(D14B / "frames_sha256_manifest.jsonl.gz", "rt") as fh:
        for ln in fh:
            r = json.loads(ln)
            d = by_clip.setdefault(r["file_name"], {})
            d[float(r["pts"])] = (r["key"], r["small_sha256"], r["path"])
    out = {}
    for c, d in by_clip.items():
        pts = sorted(d)
        out[c] = dict(pts=pts, keys=[d[p][0] for p in pts], sha=[d[p][1] for p in pts],
                      path=[d[p][2] for p in pts])
    return out


def committed_fake_event_times():
    """`fake_event_times` and MIN_CROP_S lifted out of the committed challenge scorer.

    The module is not imported: its body imports sklearn, which this box does not have, and
    importing it would also pull in StudyE9b's trace build. The extracted source's sha256 is
    recorded in the output, so a later edit to the committed rule cannot pass unnoticed.
    """
    import ast
    import math
    src = (ROOT / "experiments/dashcam/study_e9c_challenge.py").read_text()
    tree = ast.parse(src)
    body, want = [], {"MIN_CROP_S"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in want for t in node.targets):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "fake_event_times":
            body.append(node)
    names = [n.name for n in body if isinstance(n, ast.FunctionDef)]
    got = {t.id for n in body if isinstance(n, ast.Assign) for t in n.targets
           if isinstance(t, ast.Name)}
    if names != ["fake_event_times"] or got != want:
        raise RuntimeError(f"study_e9c_challenge.py no longer defines exactly one "
                           f"fake_event_times and MIN_CROP_S: {names} {sorted(got)}")
    text = "\n".join(ast.unparse(n) for n in body)
    ns = {"np": np, "math": math, "__name__": "committed_study_e9c_challenge"}
    exec(compile(ast.Module(body=body, type_ignores=[]), "study_e9c_challenge.py", "exec"), ns)
    return ns["fake_event_times"], ns["MIN_CROP_S"], hashlib.sha256(text.encode()).hexdigest()


def references(clips):
    """positives: time_of_event. negatives: the committed challenge matched fake event, seed 0."""
    fake_event_times, min_crop_s, rule_sha = committed_fake_event_times()
    pos = [c for c in clips if c["label"] == "positive"]
    neg = [c for c in clips if c["label"] == "negative"]
    devs = np.array([c["time_of_event"] - c["duration_s"] / 2.0 for c in pos])
    sigma = float(devs.std(ddof=1))
    cm = {c["file_name"]: dict(duration=c["duration_s"]) for c in clips}
    fake = fake_event_times(cm, [c["file_name"] for c in neg], sigma, 0)
    ref = {c["file_name"]: float(c["time_of_event"]) for c in pos}
    ref.update({k: float(v) for k, v in fake.items()})
    return ref, sigma, min_crop_s, rule_sha


def context_instants(cond, t, t0):
    """The instants whose frames this request carries, oldest first."""
    if cond in SLIDING:
        n = SLIDING[cond]
        want = [snap(t - FPS_STEP * k) for k in range(n - 1, -1, -1)]
    elif cond == "EP-B":
        b = int(round((t - t0) / FPS_STEP)) * FPS_STEP
        start = t0 + EP_B_BLOCK_S * int(b // EP_B_BLOCK_S + 1e-9)
        want = [snap(start + FPS_STEP * k)
                for k in range(int(round((t - start) / FPS_STEP)) + 1)]
    elif cond == "EP-G":
        start = snap(t0 - EP_G_BACK)
        want = [snap(start + FPS_STEP * k)
                for k in range(int(round((t - start) / FPS_STEP)) + 1)]
        want = want[-EP_G_CAP_FRAMES:]
    else:
        raise ValueError(cond)
    # an instant before the clip starts has no frame; the window is clipped, never dropped
    return [u for u in want if u >= 0.0]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sample = json.loads((D14B / "d14b_sample.json").read_text())
    clips = sample["clips"]
    split = json.loads(SPLIT.read_text())
    side = {c: "DEV" for c in split["dev"]}
    side.update({c: "EVAL" for c in split["eval"]})
    assert len(side) == 300 and set(side) == {c["file_name"] for c in clips}
    frames = load_frames()
    n1 = load_n1_store_rows()
    ref, sigma, min_crop_s, rule_sha = references(clips)

    rows, frameset, clip_rows = [], {}, []
    for c in sorted(clips, key=lambda c: c["file_name"]):
        name, dur = c["file_name"], float(c["duration_s"])
        r = ref[name]
        t0 = snap(r - WINDOW_S)
        instants = [snap(t0 + FPS_STEP * k)
                    for k in range(int(round(WINDOW_S / FPS_STEP)) + 1)]
        clipped_lo = sum(1 for u in instants if u < 0.0)
        instants = [u for u in instants if 0.0 <= u <= dur + 1e-9]
        fr = frames[name]
        for cond in CONDITIONS:
            for t in instants:
                want = context_instants(cond, t, t0)
                keys, shas, pts, miss, refs = [], [], [], 0, []
                for u in want:
                    k, p = key_of(fr["pts"], fr["keys"], u)
                    if k is None:
                        miss += 1
                        continue
                    i = fr["keys"].index(k)
                    if keys and keys[-1] == k:
                        # two 0.5 s instants resolving to one decoded frame: the frame is sent
                        # ONCE. Recorded so the realised frame count is never assumed from n.
                        continue
                    keys.append(k); shas.append(fr["sha"][i]); pts.append(fr["pts"][i])
                    refs.append(store_ref(name, u))
                    prev = frameset.get((name, k))
                    in_store = (name, u) in n1
                    if prev is None or (in_store and not prev[3]):
                        # prefer an instant the committed N = 1 grid already holds, so a frame
                        # that IS in the store is never queued for re-encoding
                        frameset[(name, k)] = (fr["sha"][i], fr["path"][i], fr["pts"][i],
                                               in_store, u)
                rid = f"{name[:-4]}_{cond}_t{t:07.2f}"
                rows.append(dict(
                    request_id=rid, file_name=name, label=c["label"], side=side[name],
                    condition=cond, t=t, ref=r, ref_kind=("observed (time_of_event)"
                        if c["label"] == "positive" else "matched fake event, challenge seed 0"),
                    rel_to_ref=round(t - r, 2),
                    time_of_event=c["time_of_event"], time_of_alert=c["time_of_alert"],
                    lead=(None if c["time_of_alert"] is None
                          else round(c["time_of_event"] - c["time_of_alert"], 4)),
                    duration_s=dur, scene=c["scene"], light=c["light"], weather=c["weather"],
                    n_frames=len(keys), frame_keys=keys, frame_pts=pts, small_sha256=shas,
                    store_refs=refs, store_files=[store_file(x) for x in refs],
                    header=header_for(len(keys)), header_constant=HEADER_CONSTANT,
                    span_s=round(pts[-1] - pts[0], 3) if keys else 0.0,
                    instants_requested=len(want), instants_missing=miss,
                    collapsed=len(want) - miss - len(keys)))
        clip_rows.append(dict(file_name=name, label=c["label"], side=side[name], ref=r,
                              duration_s=dur, n_instants=len(instants),
                              instants_clipped_before_zero=clipped_lo,
                              ep_g_window_start=max(0.0, snap(t0 - EP_G_BACK))))

    # the shuffled-order control subset: first 25 positive and 25 negative EVAL clips by name
    shuf = []
    for lab in ("positive", "negative"):
        shuf += [r["file_name"] for r in clip_rows
                 if r["side"] == "EVAL" and r["label"] == lab][:N_SHUFFLE_CLIPS // 2]

    with gzip.open(OUT / "sh_ep_requests_manifest.jsonl.gz", "wt") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    fs = [dict(file_name=c, key=k, pts=v[2], small_sha256=v[0], png_path=v[1],
               in_d91_store=bool(v[3]), instant=v[4], store_ref=store_ref(c, v[4]),
               store_file=store_file(store_ref(c, v[4])))
          for (c, k), v in sorted(frameset.items())]
    extra = [r for r in fs if not r["in_d91_store"]]
    with gzip.open(OUT / "sh_ep_store_extension.jsonl.gz", "wt") as fh:
        for r in extra:
            fh.write(json.dumps(r) + "\n")
    with gzip.open(OUT / "sh_ep_frames_manifest.jsonl.gz", "wt") as fh:
        for r in fs:
            fh.write(json.dumps(r) + "\n")

    by_cond = {}
    for cd in CONDITIONS:
        rr = [r for r in rows if r["condition"] == cd]
        ns = [r["n_frames"] for r in rr]
        by_cond[cd] = dict(requests=len(rr), frames_min=min(ns), frames_max=max(ns),
                           frames_mean=round(sum(ns) / len(ns), 3),
                           image_parts_total=sum(ns),
                           headers=sorted({r["header"] for r in rr}))
    meta = dict(
        label="StudySH-EP request manifest and frame SELECTION. CPU only on flash; no GPU, no "
              "model server, no inference, no frame rendered and none encoded: every frame is a "
              "row of StudyD14b's committed sha256 manifest, already in the D91 nexar q90 store.",
        step_s=STEP, evaluated_grid_s=FPS_STEP, window_s=WINDOW_S,
        ep_g_back_s=EP_G_BACK, ep_g_cap_frames=EP_G_CAP_FRAMES,
        ep_g_cap_s=EP_G_CAP_FRAMES * FPS_STEP - FPS_STEP,
        ep_b_block_s=EP_B_BLOCK_S, conditions=list(CONDITIONS), seed=SEED,
        header_count_rule="StudyD3's grey_header generalised: it names the realised frame count "
                          "and the span. It CHANGES at every instant and sits FIRST in the "
                          "prompt, so under this header no KV prefix of an append-only episode "
                          "can ever be reused.",
        header_constant_rule=HEADER_CONSTANT,
        header_constant_note="count-free, so every instant of one episode shares a byte-identical "
                             "text prefix and the growing frame list is a true KV prefix. Both "
                             "headers are frozen per request; --header-mode picks one at run "
                             "time and no manifest rebuild is needed.",
        sigma_fake_event_s=sigma, negative_ref_min_crop_s=min_crop_s,
        negative_ref_rule_sha256=rule_sha,
        negative_ref_rule="study_e9c_challenge.fake_event_times at seed 0, the "
                          "committed matched reference; sigma is the sample sd "
                          "(ddof=1) of time_of_event - duration / 2 over the 150 "
                          "positives, the committed challenge rule",
        n_clips=len(clip_rows), n_dev=sum(1 for r in clip_rows if r["side"] == "DEV"),
        n_eval=sum(1 for r in clip_rows if r["side"] == "EVAL"),
        instants_per_clip=sorted({r["n_instants"] for r in clip_rows}),
        clips_clipped_before_zero=sum(1 for r in clip_rows
                                      if r["instants_clipped_before_zero"]),
        requests_per_model=len(rows), requests_both_models=2 * len(rows),
        unique_frames=len(fs),
        frames_already_in_d91_store=sum(1 for r in fs if r["in_d91_store"]),
        frames_needing_store_extension=len(extra),
        clips_needing_store_extension=len(sorted({r["file_name"] for r in extra})),
        store_extension_note="instants below the committed 3.0 s D14b decision grid have no "
                             "stored JPEG because encode_jpeg.iter_nexar walks the N = 1 rows "
                             "only. Their PNGs ARE rendered (they are D14b N = 3 targets), so "
                             "sh_ep_encode_extra.py adds exactly these files with the committed "
                             "D91 recipe and touches no existing file.",
        image_parts_per_model=sum(r["n_frames"] for r in rows),
        by_condition=by_cond, shuffle_control_clips=shuf,
        clips=clip_rows)
    meta["_provenance"] = stamp(script="sh_ep_manifest.py", model="none", device="cpu",
                                n=len(rows), args=None)
    (OUT / "sh_ep_manifest_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k != "clips"}, indent=1)[:2600])


if __name__ == "__main__":
    main()
