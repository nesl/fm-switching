#!/usr/bin/env python3
"""StudyD11 inputs (CPU; ORIGINAL .venv — transformers 5.10.2 + qwen_vl_utils, R1's preprocessing stack).

Arms (all built from R1's committed inputs, ~/.cache/fm-switching/r1_inputs/<RICH|RECENT>/<qid>.npz):
  U  two videos: (1) K1's RICH frames with t < qt - 120 (prefix of K1's frame array, K1's size and stride,
     K1's frames_indices; if the count is odd the last frame is repeated once, as R1 pads), (2) K3's video unchanged.
     qt <= 120 (no older frames): one video = K3 (= K1).
  I  U with video (1) replaced by DONOR frames: same count, same frames_indices (U's timestamps), same size, processed by
     R1's exact pipeline (study_o_q4.cache_video 1 fps JPEG q88 -> qwen_vl_utils.process_vision_info over the full
     K1-length frame list -> processor smart_resize to K1's final size, bicubic, uint8). Donor rule (seed 0,
     random.Random(0), questions in R1 order): candidates = other videos whose cached frame size equals this video's
     (exact native size; every size group has >= 3 videos); prefer a different video_category_broad (S-EMBER has no
     participant or location field; video_category[_broad] is the only scene-like metadata); among the preferred tier,
     those whose duration covers U's latest older timestamp; rng.choice over the sorted list. If no candidate in any
     tier is long enough: TOO-SHORT RULE — the longest same-size candidate, donor time = t * Tmax_donor / t_max (time
     order kept; frames may repeat). Donor frames come from a separate cache (~/.cache/fm-switching/sember_frames_d11)
     so R1's cache is untouched.
  F  qt > 120 only: K3's frames (R1's even-padded array) split into two videos at k = the even index closest to the
     middle (k = 2 * round(T / 4), ties to the lower index), so Qwen3-VL's 2-frame temporal pairs are unchanged.
Checks written to results/cost/study_d11/study_d11_inputs_check.json:
  * reconstruction: R1's pipeline rebuilt here with the question's OWN frames must reproduce K1's stored older frames
    byte-for-byte (30 questions, Random(0)) — proves donor frames get the identical processing;
  * qt <= 120: U = I = K3 = K1 (no older frames); no donor frame shares the question's video_id.
Outputs: ~/.cache/fm-switching/d11_inputs/I/<qid>.npz (donor frames + indices);
results/cost/study_d11/study_d11_inputs_manifest.jsonl (per question: n_old, video hashes, donor, rule tier).
Run: .venv/bin/python experiments/cost/study_d11_inputs.py [--jobs 16]
"""
import argparse
import gzip
import hashlib
import json
import os
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "sember"))
R1M = REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"
MCQ = REPO / "results/sember/study_h/data/sember_mcq.jsonl"
R1IN = Path.home() / ".cache/fm-switching/r1_inputs"
FRAMES = Path.home() / ".cache/fm-switching/sember_frames"
DFRAMES = Path.home() / ".cache/fm-switching/sember_frames_d11"
OUTIN = Path.home() / ".cache/fm-switching/d11_inputs"
OUT = REPO / "results/cost/study_d11"
SNAP_I = Path.home() / (".cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/"
                        "0cfaf48183f594c314753d30a4c4974bc75f3ccb")
W = 120.0
_W = {}


def h(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def older_count(row):
    qt = float(row["question_time"])
    return sum(t < qt - W - 1e-6 for t in row["frame_t"])


def pad_even(fr, idx):
    if len(idx) % 2:
        fr = np.concatenate([fr, fr[-1:]], 0)
        idx = list(idx) + [idx[-1]]
    return fr, list(idx)


def split_k(T):
    """Even index closest to T / 2; ties go to the lower index."""
    return 2 * int(np.ceil(T / 4 - 0.5))


def _init():
    import torch
    torch.set_num_threads(1)                      # workers are spawned; one intra-op thread each
    import study_o_q4 as O
    from transformers import AutoProcessor
    O.VIDEOS = Path.home() / ".cache/fm-switching/sember_videos"
    O.MCQ = MCQ
    _W["O"] = O
    _W["proc"] = AutoProcessor.from_pretrained(str(SNAP_I), min_pixels=O.MIN_PIXELS, max_pixels=O.MAX_PIXELS)
    _W["mcq"] = {r["question_id"]: r for r in map(json.loads, open(MCQ))}


def r1_pipeline(rec, imgs, n_keep):
    """R1's study_r1_inputs.build_video processing for one frame list; returns the first n_keep final uint8 frames."""
    import torch
    from qwen_vl_utils import process_vision_info
    from transformers.image_processing_utils_fast import SizeDict
    from transformers.models.qwen3_vl.video_processing_qwen3_vl import smart_resize
    O, P = _W["O"], _W["proc"]
    msgs = O.build_messages(rec, imgs)
    _, vi, _ = process_vision_info(msgs, return_video_kwargs=True)
    vp = P.video_processor
    T_, _, H_, W_ = vi[0].shape
    rh, rw = smart_resize(num_frames=T_, height=H_, width=W_, temporal_factor=vp.temporal_patch_size,
                          factor=vp.patch_size * vp.merge_size, min_pixels=vp.size["shortest_edge"],
                          max_pixels=vp.size["longest_edge"])
    fin = vp.resize(vi[0], size=SizeDict(height=rh, width=rw), resample=vp.resample)
    return fin.round().clamp(0, 255).to(torch.uint8).numpy()[:n_keep]


def cached(vid, max_t, cache_dir):
    O = _W["O"]
    O.CACHE = cache_dir
    return O.cache_video(vid, max_t)


def nearest(frames, t):
    return min(frames, key=lambda x: (abs(x[0] - t), x[0]))


def work(job):
    """job = (kind, qid, payload). kind 'I' builds donor frames; 'REC' rebuilds own older frames for the check."""
    import PIL.Image
    kind, qid, p = job
    rec = _W["mcq"][qid]
    k1 = p["k1"]
    qt = float(rec["question_time"])
    own = cached(rec["video_id"], qt, FRAMES)
    ts, paths = _W["O"].select("RICH", own, qt)
    assert [round(t, 3) for t in ts] == [round(t, 3) for t in k1["frame_t"]], qid
    n_old = p["n_old"]
    if kind == "REC":
        imgs = [PIL.Image.open(x).convert("RGB") for x in paths]
    else:
        dest = OUTIN / "I" / f"{qid}.npz"
        if dest.exists():                              # resumable
            fr = np.load(dest)["frames"]
            return qid, dict(i_v1_sha256=h(fr), i_v1_frame_sha256=[h(f) for f in fr] if p.get("trace") else None)
        dfr = cached(p["donor"], p["donor_max_t"] + 1.0, DFRAMES)
        dtimes = p["donor_times"]
        imgs = []
        for j, (t, x) in enumerate(zip(ts, paths)):
            src = nearest(dfr, dtimes[j])[1] if j < n_old else x
            imgs.append(PIL.Image.open(src).convert("RGB"))
    fin = r1_pipeline(rec, imgs, n_old)
    for im in imgs:
        im.close()
    z = np.load(R1IN / "RICH" / f"{qid}.npz")
    zf, zi = z["frames"], z["frames_indices"]                         # load once
    if kind == "REC":
        return qid, dict(match=bool(np.array_equal(fin, zf[:n_old])), n_old=n_old,
                         max_abs=int(np.abs(fin.astype(int) - zf[:n_old].astype(int)).max()))
    assert fin.shape[1:] == zf.shape[1:], (qid, fin.shape, zf.shape)
    idx = [int(i) for i in zi[:n_old]]
    fr, idx = pad_even(fin, idx)
    dest = OUTIN / "I" / f"{qid}.npz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest.with_suffix(".tmp.npz"), frames=fr, frames_indices=np.array(idx, np.int32))
    os.replace(dest.with_suffix(".tmp.npz"), dest)
    return qid, dict(i_v1_sha256=h(fr), i_v1_frame_sha256=[h(f) for f in fr] if p.get("trace") else None)


def predecode(job):
    """Decode a donor video once (1 fps JPEG, study_o_q4.cache_video) into the separate D11 cache."""
    vid, max_t = job
    fr = cached(vid, max_t, DFRAMES)
    return vid, len(fr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=16)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {}
    for r in map(json.loads, gzip.open(R1M)):
        rows.setdefault(r["question_id"], {})[r["construction"]] = r
    mcq = {r["question_id"]: r for r in map(json.loads, open(MCQ))}
    order = [q for _, q in sorted((rows[q]["RECENT"]["video_id"], q) for q in rows)]
    # per-video metadata: cached frame size (what R1 processed), category, duration
    import PIL.Image
    vids = sorted({mcq[q]["video_id"] for q in order})
    vmeta = {}
    for v in vids:
        f0 = sorted((FRAMES / v).glob("*.jpg"))[0]
        with PIL.Image.open(f0) as im:
            size = im.size
        m = next(mcq[q] for q in order if mcq[q]["video_id"] == v)
        vmeta[v] = dict(size=list(size), broad=m["video_category_broad"], cat=m["video_category"],
                        duration=float(m["duration"]))
    groups = {}
    for v, m in vmeta.items():
        groups.setdefault(tuple(m["size"]), []).append(v)
    rng = random.Random(0)
    man, jobs = [], []
    trace_q = None
    tiers = dict(different_broad_long_enough=0, same_broad_long_enough=0, too_short_rule=0, none_needed=0)
    for q in order:
        k1, k3 = rows[q]["RICH"], rows[q]["RECENT"]
        qt = float(k3["question_time"])
        f3 = np.load(R1IN / "RECENT" / f"{q}.npz")["frames"]          # load once (npz members decompress per access)
        n_old = older_count(k1)
        rec = dict(question_id=q, video_id=k3["video_id"], question_time=qt, n_old=n_old, k3_sha256=h(f3),
                   k3_n=int(f3.shape[0]), k3_hw=list(f3.shape[2:]), k1_hw=k1["final_hw"])
        if qt > W:
            T = int(f3.shape[0])
            k = split_k(T)
            rec["F_split"] = dict(T_padded=T, k=k, video1=[0, k], video2=[k, T],
                                  pairs_preserved=k % 2 == 0 and 0 < k < T)
        if n_old == 0:
            tiers["none_needed"] += 1
            rec.update(U_videos=1, donor=None, tier="none_needed")
            man.append(rec)
            continue
        z1 = np.load(R1IN / "RICH" / f"{q}.npz")
        u1, uidx = pad_even(z1["frames"][:n_old], [int(i) for i in z1["frames_indices"][:n_old]])
        del z1
        rec.update(U_videos=2, u_v1_sha256=h(u1), u_v1_n=len(uidx), u_v1_idx_first_last=[uidx[0], uidx[-1]])
        t_old = [t for t in k1["frame_t"][:n_old]]
        need = max(t_old)
        own = k3["video_id"]
        cands = sorted(v for v in groups[tuple(vmeta[own]["size"])] if v != own)
        pref = [v for v in cands if vmeta[v]["broad"] != vmeta[own]["broad"]]
        long_pref = [v for v in pref if vmeta[v]["duration"] >= need + 1.0]
        long_all = [v for v in cands if vmeta[v]["duration"] >= need + 1.0]
        if long_pref:
            donor, tier = rng.choice(long_pref), "different_broad_long_enough"
            dt = list(t_old)
        elif long_all:
            donor, tier = rng.choice(long_all), "same_broad_long_enough"
            dt = list(t_old)
        else:
            donor = max(cands, key=lambda v: (vmeta[v]["duration"], v))
            tier = "too_short_rule"
            tmax_d = np.floor(vmeta[donor]["duration"] - 1.0)
            dt = [float(np.floor(t * tmax_d / need)) if need > 0 else 0.0 for t in t_old]
        tiers[tier] += 1
        rec.update(donor=donor, tier=tier, donor_broad=vmeta[donor]["broad"], donor_category=vmeta[donor]["cat"],
                   own_broad=vmeta[own]["broad"], own_category=vmeta[own]["cat"],
                   donor_same_category=vmeta[donor]["cat"] == vmeta[own]["cat"], donor_times=dt,
                   donor_size=vmeta[donor]["size"], own_size=vmeta[own]["size"])
        assert donor != own
        if trace_q is None and qt > 300:
            trace_q = q
        jobs.append(("I", q, dict(k1=k1, n_old=n_old, donor=donor, donor_times=dt, donor_max_t=max(dt),
                                  trace=q == trace_q)))
        man.append(rec)
    rq = random.Random(0).sample([j[1] for j in jobs], 30)
    rec_jobs = [("REC", q, dict(k1=rows[q]["RICH"], n_old=older_count(rows[q]["RICH"]))) for q in rq]
    import multiprocessing as mp
    rc_path = OUT / "study_d11_reconstruction.json"
    with mp.get_context("spawn").Pool(a.jobs, initializer=_init) as pool:
        if rc_path.exists() and sorted(json.loads(rc_path.read_text())) == sorted(rq):
            recon = json.loads(rc_path.read_text())
        else:
            recon = dict(pool.map(work, rec_jobs))
            rc_path.write_text(json.dumps(recon, indent=1))
        if not all(v["match"] for v in recon.values()):
            (OUT / "study_d11_inputs_check.json").write_text(json.dumps(dict(reconstruction=recon), indent=1))
            raise SystemExit("RECONSTRUCTION MISMATCH: R1's pipeline does not reproduce K1's frames — STOP")
        need = {}
        for _, _, p in jobs:
            need[p["donor"]] = max(need.get(p["donor"], 0.0), p["donor_max_t"] + 1.0)
        pool.map(predecode, sorted(need.items()))
        done = dict(pool.map(work, jobs, chunksize=1))
    for rec in man:
        if rec["question_id"] in done:
            d = done[rec["question_id"]]
            rec["i_v1_sha256"] = d["i_v1_sha256"]
            if d["i_v1_frame_sha256"]:
                rec["i_v1_frame_sha256"] = d["i_v1_frame_sha256"]
    with open(OUT / "study_d11_inputs_manifest.jsonl", "w") as f:
        for rec in man:
            f.write(json.dumps(rec) + "\n")
    le = [r for r in man if r["question_time"] <= W]
    chk = dict(n=len(man), tiers=tiers, trace_question=trace_q,
               reconstruction=dict(n=len(recon), all_match=all(v["match"] for v in recon.values()), rows=recon),
               qt_le_120=dict(n=len(le), no_older_frames=sum(r["n_old"] == 0 for r in le)),
               qt_gt_120_without_older=[r["question_id"] for r in man if r["question_time"] > W and r["n_old"] == 0],
               donor_differs_video=all(r["donor"] != r["video_id"] for r in man if r["donor"]),
               donor_same_category=sum(bool(r.get("donor_same_category")) for r in man if r["donor"]),
               donor_different_broad=sum(r.get("donor_broad") != r.get("own_broad") for r in man if r["donor"]),
               n_with_donor=sum(bool(r["donor"]) for r in man),
               metadata_note="S-EMBER has no participant or location field; video_category_broad / video_category "
                             "are the only scene-like metadata (used for the preference)",
               size_groups={f"{k[0]}x{k[1]}": len(v) for k, v in groups.items()},
               f_split_pairs_preserved=all(r["F_split"]["pairs_preserved"] for r in man if "F_split" in r))
    (OUT / "study_d11_inputs_check.json").write_text(json.dumps(chk, indent=1))
    print(json.dumps({k: v for k, v in chk.items() if k != "reconstruction"}, indent=1)[:2500])
    print("reconstruction all match:", chk["reconstruction"]["all_match"])


if __name__ == "__main__":
    main()
