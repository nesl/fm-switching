#!/usr/bin/env python3
"""StudyF2-summary analysis (CPU; dashcam venv). Accuracy per model and stratum; paired vs K3/H1 (recent), K1/H2
(rich) and D11 U (U32/U4), video bootstrap 2,000 seed 0; tokens per question; caption build cost; negative control;
10-chunk caption sample (seed 0). Writes results/sember/study_f2/f2_results.json."""
import collections
import gzip
import json
import random
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
sys.path.insert(0, str(REPO / "experiments/sember"))
from study_f1_analyse import boot, by_video, stratum, strata, STRATA, NB, SEED  # noqa: E402

OUT = REPO / "results/sember/study_f2"
R1 = "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"
CL = "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz"
D11 = "results/cost/study_d11/study_d11_requests_h100nvl.jsonl"
REFS = {"32BI": {"recent_K3": (R1, "K3"), "rich_K1": (R1, "K1"), "U32": (D11, "U32")},
        "4BI": {"recent_H1": (CL, "H1"), "rich_H2": (CL, "H2"), "U4": (D11, "U4")}}


def load_ref(p, cell):
    op = gzip.open if p.endswith(".gz") else open
    out = {}
    for l in op(REPO / p, "rt"):
        r = json.loads(l)
        if r.get("cell") == cell and r.get("mode", "batched") == "batched" and not r["error"]:
            out[r["question_id"]] = r          # last good row wins (D11 retries are appended)
    return out


def main():
    rng = np.random.default_rng(SEED)
    M = strata()
    rows = [json.loads(l) for l in open(OUT / "f2_requests_h100nvl.jsonl")]
    ok = {(r["model"], r["question_id"]): r for r in rows if not r["error"]}
    caps = [json.loads(l) for l in open(OUT / "f2_captions_h100nvl.jsonl")]
    capok = {c["chunk_id"]: c for c in caps if not c["error"]}
    meta = json.loads((OUT / "f2_run_meta_h100nvl.json").read_text())
    qs = sorted({q for _, q in ok})
    any_r = {q: next(ok[(m, q)] for m in ("32BI", "4BI") if (m, q) in ok) for q in qs}
    vid = {q: any_r[q]["video_id"] for q in qs}
    st = {q: stratum(M[q], float(any_r[q]["question_time"])) for q in qs}
    res = dict(label="StudyF2-summary: generic 30-s chunk captions (32B, question-blind) for history older than "
               "qt - 120 s + K3's RECENT video; H100 GPU 1 vLLM stack; accuracy only",
               strata_counts=dict(collections.Counter(st.values())), checks={}, accuracy={}, paired={}, tokens={},
               caption_cost={}, negative_control=meta.get("negative_control"))
    for mdl in ("32BI", "4BI"):
        mine = [ok[(mdl, q)] for q in qs if (mdl, q) in ok]
        res["checks"][mdl] = dict(rows_ok=len(mine), missing=845 - len(mine),
                                  error_rows_retried=sum(1 for r in rows if r["model"] == mdl and r["error"]),
                                  unparsed_X=sum(r["pred"] == "X" for r in mine),
                                  finish_length=sum(r["finish_reason"] == "length" for r in mine),
                                  cached_tokens_nonzero=sum(bool(r["cached_tokens"]) for r in mine))
        refs = {k: load_ref(*v) for k, v in REFS[mdl].items()}
        for s in ("ALL",) + STRATA:
            sel = [q for q in qs if (s == "ALL" or st[q] == s) and (mdl, q) in ok]
            res["accuracy"][f"{mdl}/F2/{s}"] = boot(by_video((vid[q], float(ok[(mdl, q)]["correct"])) for q in sel), rng)
            for k, ref in refs.items():
                sel2 = [q for q in sel if q in ref]
                res["accuracy"][f"{mdl}/{k}/{s}"] = boot(by_video((vid[q], float(ref[q]["correct"])) for q in sel2), rng)
                res["paired"][f"{mdl}/F2-{k}/{s}"] = dict(
                    boot(by_video((vid[q], float(ok[(mdl, q)]["correct"]) - float(ref[q]["correct"])) for q in sel2), rng),
                    agreement=float(np.mean([ok[(mdl, q)]["pred"] == ref[q]["pred"] for q in sel2])),
                    ref_prompt_tokens_median=float(np.median([ref[q]["prompt_tokens"] for q in sel2])))
            pt = [ok[(mdl, q)]["prompt_tokens"] for q in sel]
            sm = [ok[(mdl, q)]["summary_tokens_est"] or 0 for q in sel]
            res["tokens"][f"{mdl}/{s}"] = dict(prompt_median=float(np.median(pt)), prompt_max=int(max(pt)),
                                               summary_tokens_median=float(np.median(sm)), summary_tokens_max=int(max(sm)),
                                               chunks_median=float(np.median([ok[(mdl, q)]["n_chunks"] for q in sel])),
                                               extra_over_K3_median=float(np.median([ok[(mdl, q)]["prompt_tokens"] -
                                                                                      ok[(mdl, q)]["k3_expected_prompt_tokens"] for q in sel])))
    # caption cost
    seg = meta.get("caption_batched_segments", [])
    n_batched = sum(s["chunks"] for s in seg)
    wall = sum(s["wall_s"] for s in seg)
    ser = [json.loads(l) for l in open(OUT / "f2_caption_serial_h100nvl.jsonl")] if (OUT / "f2_caption_serial_h100nvl.jsonl").exists() else []
    ser = [r for r in ser if not r["discarded"]]
    ctok = [c["caption_tokens"] for c in capok.values()]
    res["caption_cost"] = dict(
        chunks=len(capok), videos=len({c["video_id"] for c in capok.values()}),
        chunks_per_video_hour=3600 / 30,
        batched=dict(chunks=n_batched, wall_s=wall, concurrency=8,
                     gpu_s_per_chunk_amortised=(wall / n_batched) if n_batched else None,
                     gpu_s_per_video_hour_amortised=(wall / n_batched * 120) if n_batched else None),
        serial=dict(n=len(ser), total_s_median=float(np.median([r["total_s"] for r in ser])) if ser else None,
                    total_s_p90=float(np.percentile([r["total_s"] for r in ser], 90)) if ser else None,
                    gpu_s_per_video_hour_serial=float(np.median([r["total_s"] for r in ser]) * 120) if ser else None,
                    cached_nonzero=sum(bool(r["cached_tokens"]) for r in ser)),
        caption_tokens=dict(median=float(np.median(ctok)), p90=float(np.percentile(ctok, 90)), max=int(max(ctok)),
                            hit_128_cap=sum(c["finish_reason"] == "length" for c in capok.values())),
        caption_prompt_tokens_median=float(np.median([c["prompt_tokens"] for c in capok.values()])))
    sample = random.Random(0).sample(sorted(capok), 10)
    res["caption_sample"] = [dict(chunk_id=k, range=f"{capok[k]['start_s']}-{capok[k]['end_s']} s",
                                  caption=capok[k]["caption"], tokens=capok[k]["caption_tokens"]) for k in sample]
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_f2_analyse.py", model="4BI,32BI", device="cpu", n=len(qs))
    (OUT / "f2_results.json").write_text(json.dumps(res, indent=1, default=float))
    for k, v in res["paired"].items():
        print(k, round(v["est"], 4), [round(x, 4) for x in v["ci"]])


if __name__ == "__main__":
    main()
