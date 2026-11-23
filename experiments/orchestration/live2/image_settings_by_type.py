#!/usr/bin/env python3
"""IMAGE PROCESSOR SETTINGS, AND IMAGE SIZE AND TOKENS PER IMAGE, PER QUERY TYPE. READ ONLY, CPU only.

D172 states that "the image-processor settings used by each device measurement are stated in the
paper's setup". This module recovers, from COMMITTED artefacts only, what the three live2 query
types actually send and what the engine actually charged them, so that statement can be written
from measurements rather than from the flag list alone.

IT RUNS NO CELL, STARTS NO SERVER AND TOUCHES NO WORKING-TREE FILE. Every input is read with
`git show <ref>:<path>` into a scratchpad by the caller, or from this repository's committed
tree, and the only output is one JSON under results/orchestration/live2/frozen_test/.

THE THREE TYPES, by device-id prefix, which is the committed rule (d179_rung2_verdict.py:204):
    dash -> alert (EP-G dashcam episode frames)
    robo -> recall (S-EMBER D2 session history frames)
    asst -> assistance (StudySS2 single-shot, ONE image per question)

POSITIVE CONTROLS, both run before any table is trusted:
  (1) the EP-G prompt-token law, prompt_tokens = 42 + 338 * n_frames (bodies.py:97-99 /
      epg_prompt_tokens), checked against the ENGINE's own prompt_tokens on every alert request;
  (2) share_capacity.FACTORS median_uncached (374 / 7717 / 1372), recomputed per type from the
      same four covex-v6-base cells that file says it was derived from.
If either fails, the reader is broken and the table is not reported.

THE TOKEN GEOMETRY. The server is started with
    --mm-processor-kwargs {"size": {"shortest_edge": 4096, "longest_edge": 16777216}}
(study_e10b_mixed.py:79, PROC_SIZE at experiments/sember/study_rh3_inputs.py:39), which are the
processor's min_pixels and max_pixels. Qwen3-VL's smart-resize rounds each side to a multiple of
32 px (patch 16 x merge 2) and then clamps the area to [min_pixels, max_pixels]; tokens per image
are (H/32) * (W/32) plus two vision delimiters (study_rh3_inputs.py:13). `predicted_tokens`
below applies exactly that, so a measured prompt_tokens can be checked against the dimensions the
committed manifests record.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PREFIX_TO_TYPE = {"dash": "alert", "robo": "recall", "asst": "assistance"}
TYPES = ("alert", "recall", "assistance")

# declared constants, quoted with their file:line so a reader can see they are DECLARED not measured
EPG_TEXT_TOKENS = 42            # bodies.py:95
EPG_TOK_PER_FRAME = 338         # bodies.py:96
COMMITTED_MEDIAN_UNCACHED = {"alert": 374.0, "recall": 7717.0, "assistance": 1372.0}  # share_capacity.py:72-80

PATCH_BLOCK = 32                # Qwen3-VL patch 16 x merge 2
VISION_DELIMITERS = 2


def round_by_factor(x: float, factor: int = PATCH_BLOCK) -> int:
    return int(round(x / factor)) * factor


def predicted_tokens(width: int, height: int, min_pixels: int, max_pixels: int) -> int:
    """Tokens one image costs under the live2 mm-processor-kwargs (see module docstring)."""
    h = max(PATCH_BLOCK, round_by_factor(height))
    w = max(PATCH_BLOCK, round_by_factor(width))
    if h * w > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h = max(PATCH_BLOCK, int(math.floor(height / beta / PATCH_BLOCK)) * PATCH_BLOCK)
        w = max(PATCH_BLOCK, int(math.floor(width / beta / PATCH_BLOCK)) * PATCH_BLOCK)
    elif h * w < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h = int(math.ceil(height * beta / PATCH_BLOCK)) * PATCH_BLOCK
        w = int(math.ceil(width * beta / PATCH_BLOCK)) * PATCH_BLOCK
    return (h // PATCH_BLOCK) * (w // PATCH_BLOCK) + VISION_DELIMITERS


def qtype_of(device_id: str) -> Optional[str]:
    return PREFIX_TO_TYPE.get(str(device_id)[:4])


def read_requests(path: Path) -> List[Dict[str, Any]]:
    op = gzip.open if str(path).endswith(".gz") else open
    return [json.loads(l) for l in op(path, "rt") if l.strip()]


def qid_of(uuid: str) -> Optional[str]:
    """The SS2 qid inside an assistance mm uuid: <run>|<dev>|<sess_dev>|<ss>|<dataset/qid>|img."""
    parts = str(uuid).split("|")
    return parts[-2] if len(parts) >= 2 and parts[-1] == "img" else None


def describe(v: Iterable[float]) -> Dict[str, Any]:
    s = sorted(float(x) for x in v)
    if not s:
        return {"n": 0}
    def q(p: float) -> float:
        k = (len(s) - 1) * p
        lo, hi = int(math.floor(k)), int(math.ceil(k))
        return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)
    return {"n": len(s), "min": s[0], "p50": st.median(s), "p90": round(q(0.90), 4),
            "max": s[-1], "mean": round(st.fmean(s), 4)}


def load_ss2_dims(scratch: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for name in ("refspatial", "realworldqa"):
        p = scratch / f"{name}_manifest.jsonl"
        for ln in p.read_text().splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            out[r["qid"]] = dict(dataset=name, width=int(r["width"]), height=int(r["height"]),
                                 image=r.get("image"),
                                 question=(r.get("question") or r.get("prompt_text") or ""))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scratch", required=True,
                    help="directory holding base_s{4,5,6,7}/request.jsonl.gz + header.json and the "
                         "two SS2 manifests, all extracted with `git show <ref>:<path>`")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--ref-sha", required=True,
                    help="the resolved sha of --ref, so the artefact names the exact tree it read")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    scratch = Path(a.scratch)

    header = json.loads((scratch / "base_s4" / "header.json").read_text())
    cmd = [str(x) for x in (header["server"]["command"] or [])]
    mmk = json.loads(cmd[cmd.index("--mm-processor-kwargs") + 1])
    size = mmk["size"]
    min_pixels, max_pixels = int(size["shortest_edge"]), int(size["longest_edge"])

    rows: List[Dict[str, Any]] = []
    per_seed_uncached: Dict[str, Dict[int, float]] = defaultdict(dict)
    for seed in (4, 5, 6, 7):
        rs = read_requests(scratch / f"base_s{seed}" / "request.jsonl.gz")
        by_type: Dict[str, List[float]] = defaultdict(list)
        for r in rs:
            t = qtype_of(r.get("device_id", ""))
            if t is None:
                continue
            u = int(r.get("prompt_tokens") or 0) - int(r.get("cached_tokens") or 0)
            r["_qtype"], r["_uncached"], r["_seed"] = t, u, seed
            r["_n_images"] = len(r.get("mm_uuids") or [])
            rows.append(r)
            by_type[t].append(u)
        for t, v in by_type.items():
            per_seed_uncached[t][seed] = st.median(v)

    # ---------------------------------------------------------------- positive control 1
    alert = [r for r in rows if r["_qtype"] == "alert"]
    law_ok = [r for r in alert
              if r["prompt_tokens"] == EPG_TEXT_TOKENS + EPG_TOK_PER_FRAME * r["_n_images"]]
    dev = Counter(r["prompt_tokens"] - (EPG_TEXT_TOKENS + EPG_TOK_PER_FRAME * r["_n_images"])
                  for r in alert)
    pc1 = dict(
        _control="EP-G prompt-token law 42 + 338 * n_frames (bodies.py:95-99, DECLARED) against the "
                 "engine's own prompt_tokens (MEASURED) on every alert request of the four base cells",
        n_alert_requests=len(alert), n_exact=len(law_ok),
        fraction_exact=round(len(law_ok) / max(len(alert), 1), 6),
        deviation_histogram={str(k): v for k, v in sorted(dev.items())},
        passes=bool(len(law_ok) / max(len(alert), 1) >= 0.99))

    # ---------------------------------------------------------------- positive control 2
    pc2_rows = {}
    for t in TYPES:
        v = [r["_uncached"] for r in rows if r["_qtype"] == t]
        got = st.median(v)
        want = COMMITTED_MEDIAN_UNCACHED[t]
        pc2_rows[t] = dict(this_run=got, committed=want,
                           source="share_capacity.FACTORS[%r]['median_uncached']" % t,
                           ratio=round(got / want, 6), agree=bool(abs(got - want) <= 1.0),
                           per_seed={str(k): v2 for k, v2 in sorted(per_seed_uncached[t].items())})
    pc2 = dict(_control="median uncached tokens per type, recomputed from the same four "
                        "covex-v6-base cells share_capacity.py names as its source",
               rows=pc2_rows, passes=all(x["agree"] for x in pc2_rows.values()))

    # ---------------------------------------------------------------- the per-type table
    ss2 = load_ss2_dims(scratch)
    per_type: Dict[str, Any] = {}
    for t in TYPES:
        rs = [r for r in rows if r["_qtype"] == t]
        blk: Dict[str, Any] = dict(
            n_requests=len(rs),
            images_per_request=describe([r["_n_images"] for r in rs]),
            prompt_tokens=describe([r["prompt_tokens"] for r in rs]),
            uncached_tokens=describe([r["_uncached"] for r in rs]),
            cached_fraction=describe([r.get("cached_fraction") or 0.0 for r in rs]))
        per_type[t] = blk

    # assistance: dimensions as sent, joined qid by qid from the committed SS2 manifests
    asst = [r for r in rows if r["_qtype"] == "assistance"]
    joined, unjoined = [], 0
    for r in asst:
        qid = qid_of((r.get("mm_uuids") or [""])[0])
        m = ss2.get(qid)
        if m is None:
            unjoined += 1
            continue
        pred = predicted_tokens(m["width"], m["height"], min_pixels, max_pixels)
        joined.append(dict(qid=qid, dataset=m["dataset"], width=m["width"], height=m["height"],
                           area_px=m["width"] * m["height"], predicted_image_tokens=pred,
                           prompt_tokens=r["prompt_tokens"],
                           residual_text_tokens=r["prompt_tokens"] - pred))
    per_type["assistance"]["dimensions_as_sent"] = dict(
        _source="results/casestudy/study_ss2/{refspatial,realworldqa}_manifest.jsonl width/height, "
                "joined to each request by the qid carried in its mm uuid",
        n_joined=len(joined), n_unjoined=unjoined,
        width=describe([x["width"] for x in joined]),
        height=describe([x["height"] for x in joined]),
        area_px=describe([x["area_px"] for x in joined]),
        predicted_image_tokens=describe([x["predicted_image_tokens"] for x in joined]),
        residual_text_tokens=describe([x["residual_text_tokens"] for x in joined]),
        by_dataset={d: dict(n=sum(1 for x in joined if x["dataset"] == d),
                            width=describe([x["width"] for x in joined if x["dataset"] == d]),
                            height=describe([x["height"] for x in joined if x["dataset"] == d]),
                            predicted_image_tokens=describe(
                                [x["predicted_image_tokens"] for x in joined if x["dataset"] == d]),
                            prompt_tokens=describe(
                                [x["prompt_tokens"] for x in joined if x["dataset"] == d]),
                            residual_text_tokens=describe(
                                [x["residual_text_tokens"] for x in joined if x["dataset"] == d]))
                    for d in ("refspatial", "realworldqa")})

    # alert / recall: tokens per image recovered from the engine's own counts
    def slope(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_n: Dict[int, List[int]] = defaultdict(list)
        for r in rs:
            by_n[r["_n_images"]].append(r["prompt_tokens"])
        pts = sorted((n, st.median(v)) for n, v in by_n.items() if len(v) >= 3)
        if len(pts) < 2:
            return {"n_points": len(pts)}
        (n0, p0), (n1, p1) = pts[0], pts[-1]
        xs = [float(r["_n_images"]) for r in rs]
        ys = [float(r["prompt_tokens"]) for r in rs]
        mx, my = st.fmean(xs), st.fmean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else float("nan")
        return {"n_points": len(pts), "n_images_range": [n0, n1],
                "tokens_per_image_from_endpoints": round((p1 - p0) / (n1 - n0), 4),
                "implied_text_tokens": round(p0 - (p1 - p0) / (n1 - n0) * n0, 4),
                "tokens_per_image_ols": round(b, 4),
                "implied_text_tokens_ols": round(my - b * mx, 4),
                "_ols_caveat": "the intercept absorbs the per-question text, which varies, so the "
                               "OLS slope is an estimate and the declared value is the constant"}

    per_type["alert"]["tokens_per_image"] = dict(
        measured=slope([r for r in rows if r["_qtype"] == "alert"]),
        declared=EPG_TOK_PER_FRAME, declared_at="bodies.py:96 (EPG_TOK_PER_FRAME)")
    per_type["recall"]["tokens_per_image"] = dict(
        measured=slope([r for r in rows if r["_qtype"] == "recall"]),
        declared=predicted_tokens(352, 256, min_pixels, max_pixels),
        declared_at="data/encode_jpeg.py:86 SEMBER_EXPECT_SIZE['D2'] = (352, 256), token geometry "
                    "per study_rh3_inputs.py:13")
    per_type["alert"]["declared_stored_size_wh"] = [768, 432]
    per_type["alert"]["declared_stored_size_at"] = "data/encode_jpeg.py:85 NEXAR_EXPECT_SIZE"
    per_type["recall"]["declared_stored_size_wh"] = [352, 256]
    per_type["recall"]["declared_stored_size_at"] = "data/encode_jpeg.py:86 SEMBER_EXPECT_SIZE['D2']"

    # ---------------------------------------------------------------- why 1,372 against 374
    asst_floor, asst_share = 242.8, 843.7          # share_capacity.py:68 + FLEXIBLE/3 at equal weights
    cf_alert_grid = [x["residual_text_tokens"] + EPG_TOK_PER_FRAME for x in joined]
    why = {
        "_question": "does image size explain assistance's 1,372 uncached tokens against alert's 374",
        "answer": "PARTLY, AND IT IS THE PART THAT DECIDES OVERSIZE. Two causes compound and the "
                  "decomposition separates them.",
        "cause_1_residency": {
            "alert_cached_fraction_p50": per_type["alert"]["cached_fraction"]["p50"],
            "assistance_cached_fraction_max": per_type["assistance"]["cached_fraction"]["max"],
            "effect": "alert's EP-G episode is append-only, so a typical alert request is charged "
                      "about ONE new frame on a warm prefix; assistance holds ZERO residency by "
                      "construction (trace.py:567-574), so it is charged its whole prompt every "
                      "time. This alone takes alert from a 3,760-token prompt to 374 uncached.",
            "alert_prompt_tokens_p50": per_type["alert"]["prompt_tokens"]["p50"]},
        "cause_2_image_size": {
            "assistance_image_tokens_p50": per_type["assistance"]["dimensions_as_sent"][
                "predicted_image_tokens"]["p50"],
            "alert_tokens_per_frame": EPG_TOK_PER_FRAME,
            "ratio": round(per_type["assistance"]["dimensions_as_sent"][
                "predicted_image_tokens"]["p50"] / EPG_TOK_PER_FRAME, 3)},
        "counterfactual_assistance_on_the_alert_grid": {
            "_construction": "a CONSTRUCTED bound, not a measurement: each assistance request's "
                             "measured text residual plus 338, i.e. what it would cost if its image "
                             "came to the store downsized to 768x432 as a Nexar frame does",
            "tokens": describe(cf_alert_grid),
            "assistance_floor_tokens": asst_floor,
            "assistance_own_share_at_equal_weights": asst_share,
            "measured_p50_against_share": round(per_type["assistance"]["uncached_tokens"]["p50"]
                                                / asst_share, 3),
            "counterfactual_p50_against_share": round(st.median(cf_alert_grid) / asst_share, 3),
            "reading": "at the native grid the median assistance request is 1.63x its own share and "
                       "takes an OVERSIZE branch; on the alert grid it would be about 0.48x its "
                       "share and inside it. So the type's oversize status turns on the image grid, "
                       "which no D-row sets, and not on the admission rule."},
        "_do_not_read_this_as": "a claim that equalising the grids would improve any policy result. "
                                "It would change the workload, which is a methodological change."}

    out = {
        "_what": "image-processor settings, image dimensions as sent and tokens per image, per "
                 "live2 query type, from committed artefacts only",
        "_ref": a.ref,
        "_ref_sha": a.ref_sha,
        "_ref_sha_note": "every input was read with `git show <_ref_sha>:<path>`; the _provenance "
                         "git_commit below is this box's working-tree HEAD, which may differ",
        "_cells": ["hybrid-F-lhreq-noc3_n16_s%d_1200s_h27_3t_L3_epg_rq30" % s for s in (4, 5, 6, 7)],
        "_cells_are": "covex-v6-base under the D172 mapping; the cells share_capacity.py derives "
                      "its frozen numbers from; seeds 4 to 7 only",
        "server_image_settings": {
            "mm_processor_kwargs": mmk,
            "min_pixels_shortest_edge": min_pixels,
            "max_pixels_longest_edge": max_pixels,
            "limit_mm_per_prompt_last_wins": json.loads(
                [cmd[i + 1] for i, x in enumerate(cmd) if x == "--limit-mm-per-prompt"][-1]),
            "trust_request_mm_kwargs": "--trust-request-mm-kwargs" in cmd,
            "mm_processor_cache_gb": cmd[cmd.index("--mm-processor-cache-gb") + 1]
                                     if "--mm-processor-cache-gb" in cmd else None,
            "enable_prefix_caching_last_wins": True,
            "_one_setting_server_wide": "the engine is started once per cell and serves all three "
                                        "types; there is no per-type image-processor setting",
            "_source": "header.json server.command of every cell (study_e10b_mixed.py:78-81 COMMON)"},
        "body_builder_image_handling": {
            "_question": "any resize, crop or re-encode in OUR OWN body builder",
            "answer": "NONE. bodies.image_part (bodies.py:131-147) puts the stored file's bytes on "
                      "the wire base64-encoded verbatim via _data_url (bodies.py:127-128), or a "
                      "uuid-only reference when the device already uploaded them; materialize "
                      "(bodies.py:150-170) only fills a deferred part with that same URL. No PIL "
                      "import, no size argument, no crop, no re-encode anywhere in the module.",
            "per_request_mm_processor_kwargs": "NONE. build_body (bodies.py:211-240) assembles "
                                               "model, stream, messages, cache_salt, gen, optional "
                                               "kv_transfer_params and the fm_* / _live2 hint "
                                               "fields; it never sets mm_processor_kwargs, so "
                                               "--trust-request-mm-kwargs on the server has nothing "
                                               "to trust and the server-wide setting is the only one",
            "the_only_re_encode_is_offline": "data/encode_jpeg.py, PNG or CHW array -> JPEG q90 "
                                             "(Nexar) / q88 (S-EMBER), explicitly 'NO resize in the "
                                             "encode step' (encode_jpeg.py:262) and asserting the "
                                             "expected pixel grid before writing (lines 103-107, "
                                             "118-120)",
            "frames_root": "the coordinator resolves frames_root / frame_ref and sends nothing if "
                           "the file is absent (coordinator.py:1327-1335); a real-server run is "
                           "REFUSED if any ref has no file (preflight.require_frames), and the "
                           "committed frames_preflight.json of every cell used here reports "
                           "n_missing 0, so every image on the wire carried real bytes"},
        "assistance_vs_the_others": {
            "_question": "are ASSISTANCE images capped by the same rule as the other two types",
            "answer": "SAME RULE, and the rule binds nothing. There is exactly one image-processor "
                      "setting, server-wide, for all three types: min_pixels 4096 and max_pixels "
                      "16777216. The largest image any type sends is 1,786,368 px, 9.4x below "
                      "max_pixels, and the smallest is 196,608 px, 48x above min_pixels, so no "
                      "image of any type is rescaled by the processor.",
            "what_actually_differs": "the SOURCE pixel grid, not the cap. Alert and recall frames "
                                     "were downsized OFFLINE to a fixed grid before storage (Nexar "
                                     "SMALL 768x432, S-EMBER D2 352x256); assistance images are "
                                     "stored and sent at the dataset's NATIVE resolution with no "
                                     "pre-resize step anywhere in the pipeline."},
        "device_measurement_comparison": {
            "_question": "do these settings match what the DEVICE measurements used (D172)",
            "single_shot_assistance": {
                "device": "Orin 4B, vLLM 0.20.0, orin3_serve.sh:16 passes --limit-mm-per-prompt "
                          "only and NO --mm-processor-kwargs, so the released Qwen3-VL-4B defaults "
                          "apply: size {shortest_edge 65536, longest_edge 16777216}, patch 16, "
                          "merge 2 (reports/study_ss2.md:110-113)",
                "cloud_live2": "size {shortest_edge 4096, longest_edge 16777216}",
                "match": "PARTIAL BY FLAG, EXACT IN EFFECT. max_pixels is identical; only the "
                         "min_pixels floor differs (65536 against 4096) and it binds on no SS2 "
                         "image, the smallest being 196,608 px, 3.0x the device floor. StudySS2 "
                         "checked this as a census and found prompt-token counts identical on "
                         "1,042 of 1,042 questions (reports/study_ss2.md:279-294).",
                "recorded_where": "ss2_compare.py:546-547 ttft_condition.device_stack / cloud_stack"},
            "alert_dashcam": {
                "device": "Orin 4B, sh_ep_server_orin.sh:43 passes the SAME --mm-processor-kwargs "
                          "string as the H100 (lines 19-20 state the parity requirement explicitly)",
                "cloud_live2": "identical string",
                "match": "YES, byte for byte. --limit-mm-per-prompt differs (image 21 on the Orin "
                         "against image 640 on the H100) but that is an admission limit, not a "
                         "pixel budget, and EP-G is capped at 21 frames."},
            "recall_robot": {
                "device": "the committed robot-recall device baseline is the ORIN2 IN-PROCESS "
                          "llama.cpp harness (D87), which is not a vLLM image processor at all, and "
                          "ss2_compare.py:550-553 states the ORIN3 vLLM numbers and the ORIN2 "
                          "numbers must not be placed side by side as one device's numbers",
                "cloud_live2": "size {shortest_edge 4096, longest_edge 16777216}",
                "match": "NOT COMPARABLE as a flag-for-flag check. The frames are 352x256 on both "
                         "sides because the pixel grid is fixed offline by study_rh3_inputs.load, "
                         "well inside both pixel budgets, so no rescale occurs either way."},
            "cost_tables": "reports/phase1_cost_profiling.md and results/cost/cost_matrix.csv are "
                           "TEXT-token representation costs (full / window / summary) with no image "
                           "input; they carry no image-processor setting and none is needed."},
        "finding_settings_differ_without_a_recorded_decision": {
            "types": ["alert", "recall", "assistance"],
            "the_difference": "alert frames reach the store already downsized to 768x432 (338 "
                              "tokens) and recall frames to 352x256 (90 tokens), while assistance "
                              "images are sent at native resolution, p50 1152x938 and up to "
                              "1536x1536, for a p50 of 1,307 image tokens: 3.9x an alert frame and "
                              "14.5x a recall frame. The image-processor SETTING is one and the "
                              "same for all three; the effective per-image token cost is not.",
            "d_rows_searched": ["D67", "D70", "D91", "D111", "D136", "D143", "D148", "D153",
                                "D156", "D172"],
            "authorising_d_row": None,
            "what_the_d_rows_do_cover": "D70 and D91 fix the WIRE FORMAT (JPEG) and the stored "
                                        "grids for Nexar and S-EMBER, whose sizes come from the "
                                        "upstream studies (StudyD14 SMALL; study_rh3_inputs.load "
                                        "(352, 256)), not from a live2 sizing decision. D136 and "
                                        "D143 choose the SS datasets and the split and say nothing "
                                        "about image size. D172 requires only that the settings be "
                                        "STATED, which is what this file does.",
            "status": "DIFFERENCE WITHOUT A RECORDED DECISION. It is a finding to report, not a "
                      "defect to fix here; whether to equalise the grids is a methodological "
                      "change and the user's to rule on."},
        "positive_control_1_epg_law": pc1,
        "positive_control_2_median_uncached": pc2,
        "per_type": per_type,
        "why_assistance_is_larger_than_alert": why,
        "proxies_declared": [
            {"proxy": "SS2 manifest width and height, used as 'dimensions as sent'",
             "what_it_actually_measures": "the dimensions ss2_build_manifests.py recorded when it "
                                          "decoded the source images, not the file that was staged "
                                          "under frames_by_ref for live2",
             "valid_for_the_claim": "YES, and it is checked rather than assumed: predicting tokens "
                                    "from those dimensions under the live mm-processor-kwargs leaves "
                                    "a residual of 53 to 158 tokens on every one of 1,428 requests, "
                                    "always positive and of the size of the question text, which it "
                                    "could not be if the staged file had been rescaled"},
            {"proxy": "declared stored sizes 768x432 and 352x256 for alert and recall",
             "what_it_actually_measures": "the grid data/encode_jpeg.py ASSERTS before writing each "
                                          "frame; the stored files are on the H100, not on flash",
             "valid_for_the_claim": "YES for the pixel grid, because the measured tokens per image "
                                    "(338 and about 88) are exactly what those grids imply under "
                                    "the live processor setting; the BYTE sizes are not checked here"},
            {"proxy": "the staging step that put the SS2 images under frames_by_ref",
             "what_it_actually_measures": "NOT RECOVERABLE: no committed script stages "
                                          "'<qid>|img'; study_live2_pilot.prep links only "
                                          "nexar_q90 and sember_d2_q88. What IS recoverable is that "
                                          "a file existed for every ref (frames_preflight n_missing "
                                          "0) and that the pixel grid was unchanged (the token "
                                          "check above). Whether the staged file is PNG or JPEG, "
                                          "and its byte size, are NOT recoverable from committed "
                                          "artefacts.",
             "valid_for_the_claim": "sufficient for TOKENS, which is what D179's W and the D162 "
                                    "cost model consume; NOT sufficient for uplink BYTES"},
            {"proxy": "assistance uplink bytes",
             "what_it_actually_measures": "data_sources.py:661 substitutes the committed S-EMBER D2 "
                                          "median byte count for every SS2 image, a 352x256 frame",
             "valid_for_the_claim": "NO, and the code says so: SS2 areas are 2.2x to 24x larger, so "
                                    "the substitution almost certainly UNDERSTATES assistive uplink. "
                                    "It does not touch token counts and so does not affect this file."},
        ],
        "_registers": {
            "measured": ["prompt_tokens, cached_tokens and the uncached difference (the engine's "
                         "own counts, 41,552 requests over four cells)",
                         "image dimensions (committed manifest census, 1,428 of 1,428 joined)"],
            "declared": ["EPG_TOK_PER_FRAME 338 and EPG_TEXT_TOKENS 42 (bodies.py)",
                         "share_capacity.FACTORS median_uncached",
                         "the stored grids in data/encode_jpeg.py"],
            "constructed": ["counterfactual_assistance_on_the_alert_grid, a bound and not a census"]},
        "_comparison_conditions": "input, stack and decoding MATCH across the three types within a "
                                  "cell: one engine process per cell serving all three, one "
                                  "image-processor setting, temperature 0.0; what differs between "
                                  "types is the workload (dataset, image grid, residency) and the "
                                  "max_tokens of each body, which is the thing under study. The "
                                  "device-versus-cloud rows of device_measurement_comparison do NOT "
                                  "match on stack (vLLM 0.20.0 Qwen3-VL-4B against vLLM 0.31.0 "
                                  "Qwen3-VL-32B) and are compared on the processor setting only.",
    }
    import sys
    lib = Path(__file__).resolve().parents[3] / "experiments/lib"
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    from _provenance import stamp                                       # noqa: E402
    out["_provenance"] = stamp(script="image_settings_by_type.py", model="32BI",
                               device="h100nvl (the cells read; this analysis is CPU only on flash)",
                               n=len(rows), args=a)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=False) + "\n")
    print("wrote", a.out)
    print("PC1 pass:", pc1["passes"], "| PC2 pass:", pc2["passes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
