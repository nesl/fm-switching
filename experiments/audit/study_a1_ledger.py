"""
StudyA1 - comparability ledger.

Builds a machine-readable record of every result cell we cite, so each pairwise
comparison can be classified as identical-input, reallocated-budget, or otherwise.
Recorded facts only: any field not present in a committed file is UNKNOWN, with a
recovery note. Runs no inference and edits nothing under results/ except its own output.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "results" / "audit" / "comparability_ledger.json"
OUT_MD = REPO / "reports" / "comparability_ledger.md"

UNK = "UNKNOWN"


def _rows(fp: Path):
    if not fp.exists():
        return []
    op = gzip.open if fp.suffix == ".gz" else open
    out = []
    with op(fp, "rt") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _j(fp: Path):
    return json.load(open(fp)) if fp.exists() else {}


def qhash(qids):
    """Stable hash of the question set (order-independent)."""
    u = sorted(set(qids))
    return hashlib.sha256("\n".join(u).encode()).hexdigest()[:16] + f"/n={len(u)}"


def thash(texts):
    u = sorted(set(texts))
    return hashlib.sha256("\n".join(u).encode()).hexdigest()[:16] + f"/n_distinct={len(u)}"


def span(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return UNK
    return {"median": st.median(vals), "min": min(vals), "max": max(vals)}


# ----------------------------------------------------------------- status

STATUS_VOCAB = ("canonical", "complete", "INVALID", "CONFOUNDED", "pending",
                "not run", "dropped", "NOT PERFORMED")


def registry_status():
    """Copy each study's status out of research/EXPERIMENTS.md (not inferred)."""
    out = {}
    for line in open(REPO / "research" / "EXPERIMENTS.md"):
        if not line.startswith("| ") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 4:
            continue
        eid_cell = cells[1]
        eid = eid_cell.split()[0] if eid_cell else ""
        if not eid or eid in ("E-id",):
            continue
        flag = "none (no audit flag on this row)"
        if "**[" in eid_cell:
            flag = eid_cell[eid_cell.index("**["):].strip()
        # the status column is not at a fixed index across rows; take the last cell
        # whose text starts with a known status word
        status = UNK
        for c in cells[2:]:
            if any(c.startswith(v) for v in STATUS_VOCAB):
                status = c
        if status == UNK and len(cells) > 9:
            status = ("no distinct status column in this row; verdict cell reads: "
                      + cells[9][:160])
        out[eid] = {"registry_status": status, "registry_flag": flag,
                    "registry_hosts": cells[7] if len(cells) > 7 else UNK,
                    "eid_cell_raw": eid_cell[:300]}
    return out


# ------------------------------------------------------- common extractors

def sember_cell(cell, reqs, manifest_by_q, meta, *, mode="batched", **over):
    r = [x for x in reqs if x.get("cell") == cell and x.get("mode") == mode]
    if not r:
        return None
    qids = [x["question_id"] for x in r]
    mans = [manifest_by_q.get(q) for q in qids]
    mans = [m for m in mans if m]
    hw = Counter()
    vis = []
    hdr = []
    for m in mans:
        if "final_hw" in m:
            hw[tuple(m["final_hw"])] += 1
        elif "hw" in m and m["hw"]:
            for h in m["hw"]:
                hw[tuple(h)] += 1
        if "image_tokens" in m:
            vis.append(m["image_tokens"])
        if "header" in m:
            hdr.append(m["header"])
    d = {
        "n": len(r),
        "question_set_hash": qhash(qids),
        "frame_count": span([x.get("n_frames") for x in r]),
        "prompt_tokens": span([x.get("prompt_tokens") for x in r]),
        "vision_tokens": span(vis) if vis else UNK,
        "final_resolution": ({f"{a}x{b}": c for (a, b), c in hw.most_common(6)} if hw else UNK),
        "frame_timestamps_source": ("inputs manifest `frame_t` (per question)" if mans
                                    else UNK),
        "input_frame_hashes": UNK,
        "header_or_template_hash": (thash(hdr) if hdr else UNK),
        "question_text_hash": thash([m.get("text", "") for m in mans]) if mans else UNK,
        "decoding": r[0].get("params", UNK),
        "max_tokens": (r[0].get("params") or {}).get("max_tokens", UNK),
        "seed": r[0].get("seed", UNK),
        "batching_mode": mode,
        "correctness": "exact match of parsed letter vs correct_letter (`correct` field)",
        "accuracy_pct": round(100 * sum(bool(x.get("correct")) for x in r) / len(r), 4),
    }
    d.update(over)
    return d


def server_facts(meta, want_stage=None, want_key=None):
    for s in meta.get("servers", []):
        if want_stage and want_stage not in (s.get("stages") or ""):
            continue
        if want_key and s.get("key") != want_key:
            continue
        stack = meta.get("stack", {})
        return {
            "model": s.get("repo", UNK),
            "snapshot": s.get("revision", UNK),
            "runtime": f"vLLM {stack.get('vllm', UNK)}",
            "torch": stack.get("torch", UNK),
            "cuda": stack.get("cuda", UNK),
            "attention_backend": f"FlashAttention {s.get('flash_attention_version', UNK)}",
            "prefix_cache": s.get("prefix_caching", UNK),
            "max_model_len": s.get("max_model_len", UNK),
            "quantization_dtype": UNK,
            "concurrency": UNK,
        }
    return {}


# ------------------------------------------------------------------ build

def build():
    L = {}
    reg = registry_status()

    # ---------------- S-EMBER: StudyR1 (K1, K2, K3)
    r1_meta = _j(REPO / "results/sember/study_r1/study_r1_run_meta_h100nvl.json")
    r1_req = _rows(REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")
    r1_man = {m["question_id"] + "|" + m["construction"]: m
              for m in _rows(REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz")}
    for cell, constr in (("K1", "RICH"), ("K2", "RICH"), ("K3", "RECENT")):
        by_q = {q.split("|")[0]: m for q, m in r1_man.items() if q.endswith("|" + constr)}
        d = sember_cell(cell, r1_req, by_q, r1_meta)
        if not d:
            continue
        d.update(server_facts(r1_meta, want_key="32BI") or {})
        d.update({
            "experiment": "StudyR1", "cell": cell, "workload": "S-EMBER",
            "construction": constr,
            "input_format": "video (121-256 frames as one video input)",
            "host_gpu": "h100nvl GPU 3",
            "timing_boundary": "batched mode - NOT VALID AS LATENCY (concurrent requests); "
                               "timing5/single modes carry the latency numbers",
            "result_file": "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz",
            **reg.get("StudyR1", {}),
        })
        L[f"R1.{cell}"] = d

    # K2 is a second RICH cell; record which model served it
    if "R1.K2" in L:
        L["R1.K2"]["note"] = ("second RICH cell in StudyR1; model/stage mapping to the "
                              "32BI vs 32BT server is " + UNK + " from run_meta alone")

    # ---------------- S-EMBER: StudyRH4 (D1, D2)
    rh4_meta = _j(REPO / "results/sember/study_rh4/study_rh4_run_meta_h100nvl.json")
    rh4_req = _rows(REPO / "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz")
    rh4_man = defaultdict(dict)
    for m in _rows(REPO / "results/sember/study_rh4/study_rh4_inputs_manifest.jsonl.gz"):
        rh4_man[m.get("cell")][m["question_id"]] = m
    for cell in ("D1", "D2"):
        d = sember_cell(cell, rh4_req, rh4_man.get(cell, {}), rh4_meta)
        if not d:
            continue
        d.update(server_facts(rh4_meta, want_key="32BI") or {})
        d.update({
            "experiment": "StudyRH4", "cell": cell, "workload": "S-EMBER",
            "construction": f"RH4 {cell} (fixed stride, separate images)",
            "input_format": "separate images (append-only, fixed 2 s stride)",
            "host_gpu": "h100nvl GPU 3",
            "timing_boundary": "batched - NOT VALID AS LATENCY",
            "result_file": "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz",
            **reg.get("StudyRH4", {}),
        })
        d["WARNING_prefix_cache"] = (
            "run_meta records prefix_caching=True for this server, unlike StudyR1 and "
            "StudyClean (both False). Accuracy under greedy decoding is unaffected, but "
            "no RH4 latency number is a cold prefill.")
        L[f"RH4.{cell}"] = d

    # ---------------- S-EMBER: StudyClean (SAN, H1, H2, H3)
    cl_meta = _j(REPO / "results/cost/study_clean/study_clean_run_meta_h100nvl.json")
    cl_req = _rows(REPO / "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")
    srv = {"SAN": "32BI", "H1": "4BI", "H2": "4BI", "H3": "32BI"}
    fmt = {"SAN": "video (K3's own requests)", "H1": "video (K3's own requests)",
           "H2": "video (K1's own requests)",
           "H3": "separate images (RH4 D2 frames with t >= qt-120, D2 header kept)"}
    for cell in ("SAN", "H1", "H2", "H3"):
        d = sember_cell(cell, cl_req, {}, cl_meta)
        if not d:
            continue
        d.update(server_facts(cl_meta, want_stage=cell, want_key=srv[cell]) or {})
        d.update({
            "experiment": "StudyClean", "cell": cell, "workload": "S-EMBER",
            "input_format": fmt[cell],
            "host_gpu": "h100nvl GPU 1",
            "timing_boundary": "batched - NOT VALID AS LATENCY",
            "frame_timestamps_source": (
                "inherited from StudyR1 K3/K1 request construction" if cell in ("SAN", "H1", "H2")
                else "RH4 D2 frames filtered to t >= qt-120"),
            "vision_tokens": UNK,
            "final_resolution": UNK,
            "header_or_template_hash": UNK,
            "question_text_hash": UNK,
            "result_file": "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz",
            **reg.get("StudyClean", {}),
        })
        if cell == "SAN":
            d["sanity"] = cl_meta.get("sanity", UNK)
        L[f"Clean.{cell}"] = d

    # ---------------- S-EMBER device cells C1-C4
    for cell in ("C1", "C2", "C3", "C4"):
        meta = _j(REPO / f"results/device/accuracy_{cell}_meta.json")
        rows = _rows(REPO / f"results/device/accuracy_{cell}.jsonl")
        if not rows:
            continue
        qids = [r["question_id"] for r in rows]
        L[f"device.{cell}"] = {
            "experiment": "StudyDevAcc-llamacpp", "cell": cell, "workload": "S-EMBER",
            "construction": meta.get("construction", UNK),
            "n": len(rows),
            "question_set_hash": qhash(qids),
            "frame_timestamps_source": "recorded per request (`frame_timestamps`)",
            "input_frame_hashes": UNK,
            "frame_count": span([r.get("n_frames") for r in rows]),
            "final_resolution": UNK,
            "vision_tokens": UNK,
            "prompt_tokens": span([r.get("n_input_tokens") for r in rows]),
            "input_format": "separate images (llama.cpp multimodal)",
            "header_or_template_hash": UNK,
            "model": meta.get("model", UNK),
            "snapshot": meta.get("gguf_lm", UNK) + " sha256 " + str(meta.get("gguf_lm_sha256", UNK))[:16],
            "quantization_dtype": "F16 GGUF",
            "runtime": "llama.cpp " + str(meta.get("llamacpp_commit", UNK))[:12],
            "attention_backend": "llama.cpp -fa on (flash attention)",
            "host_gpu": "a6000 (GPU 1) - per the StudyDevAcc-llamacpp registry row",
            "batching_mode": "serial, one request at a time",
            "concurrency": 1,
            "decoding": meta.get("gen", UNK),
            "max_tokens": (meta.get("gen") or {}).get("max_tokens", UNK),
            "seed": meta.get("seed", UNK),
            "prefix_cache": UNK,
            "timing_boundary": "NOT VALID AS LATENCY (contended; no per-request timing recorded)",
            "correctness": "exact match of parsed letter (`correct`), parse_status recorded",
            "accuracy_pct": round(100 * sum(bool(r.get("correct")) for r in rows) / len(rows), 4),
            "result_file": f"results/device/accuracy_{cell}.jsonl",
            **reg.get("StudyDevAcc-llamacpp", {}),
        }
        if cell in ("C3", "C4"):
            L[f"device.{cell}"]["registry_flag"] = (
                "CONFOUNDED (Thinking arm; sampled temperature 1.0 vs greedy Instruct "
                "comparators) - audit 2026-11-03")

    # ---------------- MV-RoboBench: StudyS2 arm C, StudyClean H4, StudyR4
    s2_meta = _j(REPO / "results/erqa/study_s2/study_s2_run_meta_h100nvl.json")
    s2 = _rows(REPO / "results/erqa/study_s2/study_s2_trials_h100nvl.jsonl")
    for arm in sorted({r.get("arm") for r in s2 if r.get("arm")}):
        rows = [r for r in s2 if r.get("arm") == arm]
        L[f"S2.{arm}"] = {
            "experiment": "StudyS2", "cell": f"arm {arm}", "workload": "MV-RoboBench",
            "n": len(rows),
            "question_set_hash": qhash([r.get("path", "") for r in rows]),
            "frame_timestamps_source": "n/a (multi-view still images)",
            "input_frame_hashes": UNK,
            "frame_count": span([r.get("n_views") for r in rows]),
            "final_resolution": UNK, "vision_tokens": UNK,
            "prompt_tokens": span([r.get("n_input_tokens") for r in rows]),
            "input_format": "separate images (multi-view)",
            "header_or_template_hash": thash([r.get("prompt", "")[:200] for r in rows]),
            "model": (rows[0].get("model_snapshot") or UNK).split("@")[0],
            "snapshot": (rows[0].get("model_snapshot") or "@" + UNK).split("@")[-1],
            "quantization_dtype": rows[0].get("quant", UNK),
            "runtime": "HF transformers (see run_meta)",
            "attention_backend": "sdpa (asserted in report)",
            "host_gpu": "h100nvl GPU 3",
            "batching_mode": "batch 1", "concurrency": 1,
            "decoding": "greedy", "max_tokens": 512, "seed": UNK,
            "prefix_cache": "n/a (HF, no prefix cache)",
            "timing_boundary": "total_latency_ms recorded; contended - not a clean latency",
            "correctness": "answer_text letter vs ground truth",
            "result_file": "results/erqa/study_s2/study_s2_trials_h100nvl.jsonl",
            **reg.get("StudyS2", {}),
        }
    h4 = _rows(REPO / "results/cost/study_clean/study_clean_h4_trials_h100nvl.jsonl.gz")
    if h4:
        L["Clean.H4"] = {
            "experiment": "StudyClean", "cell": "H4", "workload": "MV-RoboBench",
            "n": len(h4),
            "question_set_hash": qhash([r.get("path", "") for r in h4]),
            "frame_timestamps_source": "n/a (multi-view still images)",
            "input_frame_hashes": UNK,
            "frame_count": span([r.get("n_views") for r in h4]),
            "final_resolution": UNK, "vision_tokens": UNK,
            "prompt_tokens": span([r.get("n_input_tokens") for r in h4]),
            "input_format": "separate images (StudyS2 prompt and manifest, unchanged)",
            "header_or_template_hash": thash([r.get("prompt", "")[:200] for r in h4]),
            "model": "Qwen/Qwen3-VL-4B-Instruct",
            "snapshot": "ebb281ec70b05090aa6165b016eac8ec08e71b17",
            "quantization_dtype": "bf16",
            "runtime": "HF transformers 5.10.2 / torch 2.8.0+cu128",
            "attention_backend": "sdpa", "host_gpu": "h100nvl GPU 1",
            "batching_mode": "batch 1", "concurrency": 1,
            "decoding": "greedy", "max_tokens": 512, "seed": UNK,
            "prefix_cache": "n/a (HF)",
            "timing_boundary": "NOT VALID AS LATENCY (accuracy cell)",
            "correctness": "parsed letter vs ground truth; all 401 parsed 'direct'",
            "result_file": "results/cost/study_clean/study_clean_h4_trials_h100nvl.jsonl.gz",
            **reg.get("StudyClean", {}),
        }

    # ---------------- ERQA: StudyR arms
    r_meta = _j(REPO / "results/erqa/study_r/study_r_run_meta_h100nvl.json")
    r_arms = r_meta.get("arms", {})
    r_rows = _rows(REPO / "results/erqa/study_r/study_r_trials_h100nvl.jsonl")
    for arm in sorted({r.get("arm") for r in r_rows if r.get("arm")}):
        rows = [r for r in r_rows if r.get("arm") == arm]
        am = r_arms.get(arm, {})
        reused = rows[0].get("_reused_from")
        thinking = "Thinking" in str(am.get("repo", ""))
        L[f"R.{arm}"] = {
            "experiment": "StudyR", "cell": f"arm {arm}", "workload": "ERQA",
            "n": len(rows),
            "question_set_hash": qhash([str(r.get("index", i)) for i, r in enumerate(rows)]),
            "frame_timestamps_source": "n/a (ERQA still images)",
            "input_frame_hashes": UNK,
            "frame_count": span([r.get("n_images") for r in rows]),
            "final_resolution": UNK, "vision_tokens": UNK,
            "prompt_tokens": span([r.get("n_input_tokens") for r in rows]),
            "input_format": "separate images",
            "header_or_template_hash": UNK,
            "model": am.get("repo") or (rows[0].get("_reused_snapshot") or UNK).split("@")[0],
            "snapshot": am.get("revision") or (
                (rows[0].get("_reused_snapshot") or "@" + UNK).split("@")[-1]),
            "quantization_dtype": am.get("quant", r_meta.get("quant_32b", UNK)),
            "runtime": f"HF transformers {r_meta.get('transformers', UNK)} / torch "
                       f"{r_meta.get('torch', UNK)}",
            "attention_backend": am.get("attn_implementation", UNK),
            "host_gpu": (rows[0].get("_hardware") if reused else r_meta.get("gpu", UNK)),
            "batching_mode": "batch 1", "concurrency": 1,
            "decoding": (r_meta.get("thinking_gen") if thinking
                         else r_meta.get("instruct_gen", UNK)),
            "max_tokens": ((r_meta.get("thinking_gen") or {}).get("max_new_tokens") if thinking
                           else (r_meta.get("instruct_gen") or {}).get("max_new_tokens", UNK)),
            "seed": rows[0].get("seed", UNK),
            "prefix_cache": "n/a (HF)",
            "timing_boundary": "NOT VALID AS LATENCY",
            "correctness": "parsed letter vs ground truth",
            "result_file": "results/erqa/study_r/study_r_trials_h100nvl.jsonl",
            **reg.get("StudyR", {}),
        }
        if reused:
            L[f"R.{arm}"]["WARNING_reused_arm"] = (
                f"NOT an H100 run: rows carry `_reused_from` = {reused!r} and `_hardware` = "
                f"{rows[0].get('_hardware')!r}. Decoding note: "
                f"{rows[0].get('_reused_decoding')!r}. A contrast against arm C using THIS "
                "arm is CROSS-HOST; the audit's same-host ERQA comparison correctly uses "
                "arm A_h100 instead.")
        if thinking:
            L[f"R.{arm}"]["registry_flag"] = (
                "CONFOUNDED (Thinking arm; sampled temperature 0.6 vs greedy Instruct "
                "comparators) - audit 2026-11-03")

    # ---------------- Latency: StudyDevFast / StudyDevOne / StudyClean H5
    for n in (37, 18, 9):
        rows = _rows(REPO / f"results/device/devfast_4bi_f16_n{n}.jsonl")
        if not rows:
            continue
        warm = [r for r in rows if (r.get("n_input_tokens") or r.get("input_tokens")) == 1]
        cold = [r for r in rows if r not in warm]
        L[f"DevFast.N{n}"] = {
            "experiment": "StudyDevFast", "cell": f"4B-I F16 N={n}", "workload": "S-EMBER frames",
            "n": len(cold), "n_excluded_warm_rows": len(warm),
            "question_set_hash": qhash([str(r.get("question_id", i)) for i, r in enumerate(cold)]),
            "frame_timestamps_source": "recorded per request where present; else " + UNK,
            "input_frame_hashes": "sha256 recorded in results/device/identical_input_manifest.json "
                                  "(StudyDevOne Part 1, 120 q x N in {37,18,9,1})",
            "frame_count": span([r.get("n_frames") for r in cold]),
            "final_resolution": "560x560 PNG (per StudyDevOne manifest)",
            "vision_tokens": UNK,
            "prompt_tokens": span([r.get("n_input_tokens") or r.get("input_tokens") for r in cold]),
            "input_format": "separate images (llama.cpp)",
            "header_or_template_hash": UNK,
            "model": "Qwen3VL-4B-Instruct-F16.gguf", "snapshot": "llama.cpp c0fd7862",
            "quantization_dtype": "F16 GGUF",
            "runtime": "llama.cpp (llama-server)", "attention_backend": "-fa on",
            "host_gpu": "jetson_orin (MAXN)",
            "batching_mode": "serial", "concurrency": 1,
            "decoding": "greedy", "max_tokens": UNK, "seed": UNK,
            "prefix_cache": "cache_prompt default ON - the first row of every cell is warm "
                            "(input_tokens=1) and is EXCLUDED",
            "timing_boundary": "TTFT, device-local, uncontended; medians exclude the warm row",
            "correctness": "n/a (latency cell)",
            "result_file": f"results/device/devfast_4bi_f16_n{n}.jsonl",
            **reg.get("StudyDevFast", {}),
        }
    d1 = _rows(REPO / "results/device/dev_one_n1.jsonl")
    if d1:
        L["DevOne.N1"] = {
            "experiment": "StudyDevOne", "cell": "4B-I F16 N=1 (cold)",
            "workload": "StudyDevOne identical-payload manifest",
            "n": len(d1),
            "question_set_hash": qhash([r["question_id"] for r in d1]),
            "frame_timestamps_source": "results/device/identical_input_manifest.json",
            "input_frame_hashes": "sha256 per PNG recorded in identical_input_manifest.json",
            "frame_count": span([r.get("n_frames") for r in d1]),
            "final_resolution": "560x560 PNG",
            "vision_tokens": UNK,
            "prompt_tokens": span([r.get("input_tokens") for r in d1]),
            "input_format": "separate images (llama.cpp)",
            "header_or_template_hash": UNK,
            "model": "Qwen3VL-4B-Instruct-F16.gguf", "snapshot": "llama.cpp c0fd7862",
            "quantization_dtype": "F16 GGUF",
            "runtime": "llama.cpp (llama-server)", "attention_backend": "-fa on",
            "host_gpu": "jetson_orin (MAXN, GPU pinned 1.3005 GHz on all requests)",
            "batching_mode": "serial", "concurrency": 1,
            "decoding": "greedy", "max_tokens": UNK, "seed": UNK,
            "prefix_cache": "OFF (cache_prompt=false); cached_n = 0 on every request",
            "timing_boundary": "TTFT, device-local, COLD, clock-pinned, uncontended",
            "correctness": "parsed letter vs correct_letter; accuracy 12.5 % (below chance)",
            "ttft_s": span([r.get("ttft_s") for r in d1]),
            "result_file": "results/device/dev_one_n1.jsonl",
            **reg.get("StudyDevOne", {}),
        }

    h5 = _rows(REPO / "results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz")
    for model in sorted({r.get("model") for r in h5 if r.get("model")}):
        for N in sorted({r.get("N") for r in h5 if r.get("N")}, reverse=True):
            for ps in (1, 2):
                rows = [r for r in h5 if r.get("model") == model and r.get("N") == N
                        and r.get("pass") == ps and not r.get("warmup")]
                if not rows:
                    continue
                L[f"Clean.H5.{model}_N{N}_p{ps}"] = {
                    "experiment": "StudyClean", "cell": f"H5 {model} N={N} pass {ps}",
                    "workload": "StudyDevOne identical-payload manifest",
                    "n": len(rows),
                    "question_set_hash": qhash([r.get("question_id", "") for r in rows]),
                    "frame_timestamps_source": "StudyDevOne manifest ([t=Xs] markers verified)",
                    "input_frame_hashes": "VERIFIED: 4380/4380 frame sha256 match the Orin manifest",
                    "frame_count": span([r.get("n_frames") for r in rows]),
                    "final_resolution": "560x560 PNG (byte-identical to the Orin payloads)",
                    "vision_tokens": UNK,
                    "prompt_tokens": span([r.get("prompt_tokens") for r in rows]),
                    "input_format": "separate images",
                    "header_or_template_hash": "question text verified identical to the Orin manifest",
                    "model": ("Qwen/Qwen3-VL-32B-Instruct" if model == "32BI"
                              else "Qwen/Qwen3-VL-4B-Instruct"),
                    "snapshot": ("0cfaf48183f594c314753d30a4c4974bc75f3ccb" if model == "32BI"
                                 else "ebb281ec70b05090aa6165b016eac8ec08e71b17"),
                    "quantization_dtype": UNK,
                    "runtime": "vLLM 0.31.0", "attention_backend": "FlashAttention 3",
                    "host_gpu": "h100nvl GPU 1 (shared host, localhost, no network)",
                    "batching_mode": "serial, one request at a time", "concurrency": 1,
                    "decoding": "greedy", "max_tokens": 512, "seed": UNK,
                    "prefix_cache": "OFF; cached_tokens 0 on every request and cache-hit "
                                    "counters never grew",
                    "timing_boundary": "TTFT from immediately before sending a pre-serialized "
                                       "body to the first content token; localhost, shared host",
                    "correctness": "indicative only, n=120",
                    "ttft_s": span([r.get("ttft_s") for r in rows]),
                    "cached_tokens_max": max([r.get("cached_tokens") or 0 for r in rows]),
                    "result_file": "results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz",
                    **reg.get("StudyClean", {}),
                }
    return L, reg




# ------------------------------------------------------------ sanity checks

def accuracy_by_q(rows, key="question_id"):
    return {r[key]: bool(r.get("correct")) for r in rows if key in r}


def paired_delta(a, b):
    """A - B in percentage points over the questions both arms answered."""
    common = sorted(set(a) & set(b))
    if not common:
        return None
    da = 100 * sum(a[q] for q in common) / len(common)
    db = 100 * sum(b[q] for q in common) / len(common)
    return {"n_paired": len(common), "A_pct": round(da, 4), "B_pct": round(db, 4),
            "delta_pp": round(da - db, 4)}


def sanity_checks():
    r1 = _rows(REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")
    cl = _rows(REPO / "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")
    rh4 = _rows(REPO / "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz")

    rh3 = _rows(REPO / "results/sember/study_rh3/study_rh3_requests_h100nvl.jsonl.gz")

    def cell(rows, name, mode="batched"):
        return accuracy_by_q([r for r in rows if r.get("cell") == name
                              and r.get("mode") == mode and not r.get("error")])

    K1, K3 = cell(r1, "K1"), cell(r1, "K3")
    H1, H2, H3 = cell(cl, "H1"), cell(cl, "H2"), cell(cl, "H3")
    D1, D2 = cell(rh4, "D1"), cell(rh4, "D2")
    A, B = cell(rh3, "A"), cell(rh3, "B")
    # the "RH4 paired set": answered without error in K1, K3, A, B, D1 and D2
    # (study_clean_analyse.py:122, which asserts n == 839)
    rh4_paired = set.intersection(*(set(m) for m in (K1, K3, A, B, D1, D2)))
    D2p = {q: v for q, v in D2.items() if q in rh4_paired}
    H3p = {q: v for q, v in H3.items() if q in rh4_paired}

    expected = {"H1 - K3": -5.80, "H2 - K1": -9.35, "D2 - H3 (RH4 paired set)": 1.79,
                "K1 - K3": 1.18, "H2 - H1": -2.37}
    got = {"H1 - K3": paired_delta(H1, K3), "H2 - K1": paired_delta(H2, K1),
           "D2 - H3 (RH4 paired set)": paired_delta(D2p, H3p),
           "K1 - K3": paired_delta(K1, K3), "H2 - H1": paired_delta(H2, H1)}
    out_extra = {"rh4_paired_set_n": len(rh4_paired)}
    out = {}
    for k, exp in expected.items():
        g = got[k]
        diff = None if g is None else round(abs(g["delta_pp"] - exp), 4)
        out[k] = {"expected_pp": exp, "recomputed": g, "abs_diff_pp": diff,
                  "within_0.01pp": (diff is not None and diff <= 0.01)}
    out["_rh4_paired_set_n"] = out_extra["rh4_paired_set_n"]
    return out


# -------------------------------------------------------- pairwise comparisons

COMPARISONS = [
    dict(id="H1-K3", a="Clean.H1", b="R1.K3",
         cited="study_clean_comparisons.md -5.80 pp",
         labels=["IDENTICAL_INPUT"],
         identifies="model capability at fixed input (4B-I vs 32B-I)",
         cannot="say anything about the device tier: both arms ran on the H100, "
                "and H1 is 4B on cloud hardware, not a device measurement",
         evidence="StudyClean input_identity: prompt tokens 845/845 exact, H1 replays "
                  "K3's own requests; same vLLM 0.31.0 FA3, both greedy 512"),
    dict(id="H2-K1", a="Clean.H2", b="R1.K1",
         cited="study_clean_comparisons.md -9.35 pp",
         labels=["IDENTICAL_INPUT"],
         identifies="model capability at fixed input on the RICH construction",
         cannot="separate capability from host: K1 ran on GPU 3 and H2 on GPU 1. "
                "The SAN cell (30/30 letters) is the evidence that the card does not "
                "move greedy letters, so this is a near-identical, not an identical, host",
         evidence="prompt tokens 845/845 exact; same stack and decoding"),
    dict(id="D2-H3", a="RH4.D2", b="Clean.H3",
         cited="study_clean_comparisons.md +1.79 pp overall, +21.28 OLDER, -3.15 INSIDE",
         labels=["STRICT_ADDITION", "STACK_DIFFERENT"],
         identifies="the value of history at a fixed model, stride, frame size and format: "
                    "H3 is exactly D2's frames filtered to t >= qt-120, so D2 strictly "
                    "contains H3's frames",
         cannot="separate history from the header (H3 keeps D2's 'from the session start' "
                "header, which is false for H3 when qt > 120); and it cannot be read as a "
                "clean cold-latency contrast, because RH4's server ran with "
                "prefix_caching=True while StudyClean's ran with it OFF",
         evidence="tokens INSIDE 5,622 vs 12,710; OLDER 5,603 vs 14,857; qt<=120 3,505 = "
                  "3,505 (identical input, built-in null)"),
    dict(id="K1-K3", a="R1.K1", b="R1.K3",
         cited="audit (a) +1.18 pp; +17.53 OLDER, +10.18 OVERLAP, -5.80 INSIDE",
         labels=["REALLOCATED_BUDGET"],
         identifies="nothing on its own as a single factor: RICH vs RECENT moves the "
                    "window, the frame count and the resolution together under one token "
                    "budget",
         cannot="attribute the sign flip to history length alone; the audit already "
                "records that window, frame count and resolution move together",
         evidence="same model, stack, host, greedy t=0.0; audit comparability table"),
    dict(id="H2-H1", a="Clean.H2", b="Clean.H1",
         cited="study_clean_comparisons.md -2.37 pp",
         labels=["REALLOCATED_BUDGET"],
         identifies="the same RICH-vs-RECENT reallocation as K1-K3, but read by 4B-I",
         cannot="be used as a capability claim; both arms are the same model",
         evidence="same server, same stack, same decoding, same 845 questions"),
    dict(id="C2-C1", a="device.C2", b="device.C1",
         cited="audit (b) -0.47 pp; +19.59 OLDER, -5.56 INSIDE",
         labels=["REALLOCATED_BUDGET"],
         identifies="the RICH-vs-RECENT reallocation on the device runtime (llama.cpp F16)",
         cannot="be compared directly against K1-K3 as a device-vs-cloud statement; "
                "it only shows the sign pattern replicates",
         evidence="same GGUF, same server flags, same greedy decoding, same 845 questions"),
    dict(id="K1/K3-vs-4B-I(StudyO)", a="R1.K1", b="(StudyO 4B-I fa2 arms)",
         cited="audit (c) +8.99 / +5.56 pp",
         labels=["STACK_DIFFERENT", "FORMAT_DIFFERENT"],
         identifies="nothing cleanly",
         cannot="support any capability claim: model size, serving stack (vLLM vs HF "
                "flash_attention_2) and kernel all move at once. The audit labels it "
                "CROSS-STACK",
         evidence="audit (c); median frame counts matched (231/231, 121/121)"),
    dict(id="ERQA C-A_h100", a="R.C", b="R.A_h100",
         cited="audit (d) +6.00 pp",
         labels=["IDENTICAL_INPUT"],
         identifies="model capability (32B-I vs 4B-I) on identical questions, same host, "
                    "same sdpa kernel, same greedy decoding",
         cannot="say anything about a device: both arms are cloud-hardware runs; "
                "A_h100 is the 4B model on the H100",
         evidence="audit (d), n=400, same trials file"),
    dict(id="MVRobo C-H4", a="S2.C", b="Clean.H4",
         cited="study_clean_comparisons.md +10.22 pp",
         labels=["IDENTICAL_INPUT", "STACK_DIFFERENT"],
         identifies="model capability on an identical prompt set and an identical HF stack",
         cannot="be called same-host: arm C ran on h100nvl GPU 3 and H4 on GPU 1. "
                "Input tokens are 401/401 equal",
         evidence="StudyS2 prompt and manifest reused unchanged; HF 5.10.2, torch "
                  "2.8.0+cu128, sdpa, batch 1, bf16, greedy 512"),
    dict(id="MVRobo C-R4", a="S2.C", b="(StudyR4 4B-I, RTX 3090 Ti)",
         cited="audit (e) +10.97 pp",
         labels=["IDENTICAL_INPUT", "STACK_DIFFERENT"],
         identifies="model capability on identical questions, but across hosts",
         cannot="be used as a same-host capability number; the audit labels it CROSS-HOST "
                "(H100 NVL vs RTX 3090 Ti). StudyClean H4 supersedes it with an "
                "identical-stack +10.22",
         evidence="audit (e), n=401"),
    dict(id="H5 Orin-H100", a="DevFast.N37 / DevOne.N1", b="Clean.H5.*",
         cited="study_clean_comparisons.md 15.8-16.7x (4B), 7.1x at N=1",
         labels=["IDENTICAL_INPUT"],
         identifies="the hardware and stack gap in TTFT at a fixed payload: the payload "
                    "bytes are sha256-identical (4,380/4,380 frames) and the prompt "
                    "token counts match on both stacks",
         cannot="be read as an end-to-end device-vs-cloud latency: the H100 side is "
                "localhost with NO NETWORK, and it is a shared host. The runtimes also "
                "differ (llama.cpp vs vLLM 0.31.0), so hardware and stack are not separated",
         evidence="h5_input_identity 4,380 frames matched; cached_tokens 0 on every "
                  "request; Orin warm rows (input_tokens=1) excluded"),
]

EXCLUSIONS = [
    ("E24, E24b, E24c", "INVALID (audit 2026-11-03). E24/E24b compare disjoint "
     "single-point rules; E24c's policies share one value function and allocator and "
     "joint's candidate set strictly contains the decomposed policies', so the defect is "
     "the value function, not the action space. Excluded by instruction."),
    ("StudyI2 SPATIAL and TEMPORAL arms; StudyI3 TEMPORAL and its reanalysis",
     "INVALID (audit 2026-11-03): these arms sample the FIRST N seconds, not the N "
     "seconds before the question. SPARSE is unaffected."),
    ("StudyD and StudyD2 (the Thinking studies)",
     "INVALID (audit 2026-11-03): Thinking decoded greedily; all 240 and 420 repetition "
     "groups byte-identical. NOT the same object as RH4's D2 arm, which is canonical and "
     "IS in this ledger as RH4.D2."),
    ("StudyJ as a gate", "INVALID (audit 2026-11-03): temp 0.6, 2048 budget, no stored scores."),
]


CHANGED = [
 ("The audit's \"the replay has not happened\" is now out of date",
  "`reports/audit_2026_11_03.md` §Comparability states that StudyDevOne built the "
  "identical-input manifest *so that* the H100 could replay byte-identical payloads, and "
  "that **\"that replay has not happened\"**. It has: StudyClean H5 ran later the same day "
  "and replayed all 120 questions at N in {37,18,9,1} with **4,380/4,380 frame sha256 "
  "matching the manifest**. So the record now does contain an identical-input "
  "device-vs-cloud comparison - but a **latency** one only. The audit's stronger sentence, "
  "that no device-vs-cloud *accuracy* comparison uses identical input, still holds: H5's "
  "accuracy column is n=120 and labelled indicative."),
 ("MV-RoboBench 32B vs 4B: cross-host +10.97 superseded by identical-stack +10.22",
  "Audit (e) reports +10.97 pp for arm C minus StudyR4's 4B-I, labelled CROSS-HOST "
  "(H100 NVL vs RTX 3090 Ti). StudyClean H4 re-ran the 4B arm on StudyS2's own prompt and "
  "manifest with an identical HF stack, giving **+10.22 pp**. The cross-host number should "
  "no longer be the cited one. Note H4 and arm C still differ by GPU (GPU 1 vs GPU 3), so "
  "even +10.22 is IDENTICAL_INPUT + STACK_DIFFERENT, not a same-host result."),
 ("ERQA arm A is an a6000 run reused from StudyK, not an H100 run",
  "`study_r_trials_h100nvl.jsonl` rows for arm A carry `_reused_from = "
  "'study_q_arm_E (=study_k INSTRUCT)'` and `_hardware = 'a6000'`. The file name says "
  "h100nvl, so arm A is easy to misread as an H100 cell. Any 32B-vs-4B ERQA contrast built "
  "on arm **A** is CROSS-HOST. The audit's (d) comparison is correct because it uses "
  "**A_h100**, which the run meta confirms on `NVIDIA H100 NVL` with `sdpa`."),
 ("StudyRH4 served with prefix caching ON; StudyR1 and StudyClean served with it OFF",
  "`study_rh4_run_meta_h100nvl.json` records `prefix_caching: True`, while "
  "`study_r1_run_meta` and `study_clean_run_meta` both record `False`. Under greedy "
  "decoding this does not affect accuracy, so **D2 - H3 as an accuracy contrast is "
  "unaffected**. But it means no StudyRH4 timing number is a cold prefill, and a D2-vs-H3 "
  "latency reading would be comparing a prefix-cached server against a cold one. "
  "CLAUDE.md treats cache state as a methodological parameter, so this is recorded here "
  "rather than left implicit."),
 ("K1 - K3 is REALLOCATED_BUDGET, not a history-length contrast",
  "The audit already notes that window, frame count and resolution move together between "
  "RICH and RECENT. The ledger makes that a label: K1-K3 and H2-H1 identify **no single "
  "factor**. The clean history contrast in the record is D2 - H3, where the model, stride, "
  "frame size and format are fixed and D2's frames strictly contain H3's."),
]


# ------------------------------------------------------------------ report

LEDGER_FIELDS = [
    ("experiment", "experiment"), ("cell", "cell"),
    ("registry_status", "status (registry)"), ("registry_flag", "status flag"),
    ("workload", "workload"), ("n", "n"),
    ("question_set_hash", "question-set hash"),
    ("frame_timestamps_source", "frame timestamps source"),
    ("input_frame_hashes", "input frame hashes"),
    ("frame_count", "frame count"),
    ("final_resolution", "final processed resolution"),
    ("vision_tokens", "vision tokens"),
    ("prompt_tokens", "total prompt tokens"),
    ("input_format", "input format"),
    ("header_or_template_hash", "header / template hash"),
    ("model", "model"), ("snapshot", "snapshot"),
    ("quantization_dtype", "quantization / dtype"),
    ("runtime", "runtime + version"),
    ("attention_backend", "attention backend"),
    ("host_gpu", "host and GPU"),
    ("batching_mode", "batching mode"), ("concurrency", "concurrency"),
    ("decoding", "decoding"), ("max_tokens", "max tokens"),
    ("prefix_cache", "prefix-cache state"),
    ("timing_boundary", "timing boundary"),
    ("correctness", "correctness definition"),
    ("result_file", "result file"),
]

RECOVERY = {
    "vision_tokens": "recoverable for StudyR1/StudyRH4 from the inputs manifest "
                     "(`grid_thw`, `image_tokens`); for StudyClean and the device cells it "
                     "would need a re-tokenisation of the stored prompts (CPU only, no inference).",
    "final_resolution": "recoverable from the inputs manifest (`final_hw` / `hw`) for "
                        "StudyR1 and StudyRH4; for the device and StudyClean cells it would "
                        "need the frame cache or a re-run of the image preprocessor.",
    "input_frame_hashes": "only StudyDevOne recorded per-PNG sha256 "
                          "(`results/device/identical_input_manifest.json`). For the other "
                          "cells the frames were rendered on the fly and not hashed; they "
                          "could be regenerated deterministically from the video ids and "
                          "`frame_t`, then hashed, without any inference.",
    "quantization_dtype": "recoverable from the server command line in the run log "
                          "(`logs/study_x_server_*.log`) or from the HF config dtype.",
    "concurrency": "recoverable from the batched-mode request scheduler in the study script "
                   "and from the `at` timestamps in the request records.",
    "seed": "recorded per request for the S-EMBER cells; absent for the HF ERQA/MV-RoboBench "
            "cells, where decoding is greedy and the seed is irrelevant to the output.",
    "header_or_template_hash": "recoverable by hashing the stored prompt text in the trials "
                               "files; StudyRH4 records the header string explicitly.",
}


def fmt(v):
    if isinstance(v, dict):
        if set(v) == {"median", "min", "max"}:
            return f"median {v['median']}, range [{v['min']}, {v['max']}]"
        if all(isinstance(x, int) for x in v.values()) and any("x" in str(k) for k in v):
            return ", ".join(f"{k} ({v[k]} images)" for k in list(v)[:6])
        return ", ".join(f"{k}={v[k]}" for k in list(v)[:6])
    return str(v)


def write_report(ledger, sanity, reg):
    L = []
    w = L.append
    w("# StudyA1 — comparability ledger\n")
    w("**Date:** 2026-11-04 · **Host:** flash, CPU only · **E-id:** StudyA1 "
      "(`research/EXPERIMENTS.md`) · **No inference was run.**\n")
    w("Every cell we cite, with the facts actually recorded in committed files. A field "
      "that is not recorded reads `UNKNOWN` — nothing here is inferred. "
      "Machine-readable copy: `results/audit/comparability_ledger.json`.\n")

    w("\n## 1. Counts\n")
    cnt = Counter()
    for c in COMPARISONS:
        for lab in c["labels"]:
            cnt[lab] += 1
    w("| classification | comparisons |")
    w("|---|---|")
    for k, v in cnt.most_common():
        w(f"| {k} | {v} |")
    w(f"\n{len(ledger)} cells ledgered across "
      f"{len({d['experiment'] for d in ledger.values()})} experiments; "
      f"{len(COMPARISONS)} comparisons classified (labels are not exclusive).\n")

    w("\n## 2. Sanity checks (recomputed from the raw request files)\n")
    w("| check | expected | recomputed | n paired | abs diff | within 0.01 pp |")
    w("|---|---|---|---|---|---|")
    for k, v in sanity.items():
        if not isinstance(v, dict):
            continue
        r = v["recomputed"]
        got = "—" if r is None else f"{r['delta_pp']:+.4f} ({r['A_pct']:.2f} vs {r['B_pct']:.2f})"
        npair = "—" if r is None else r["n_paired"]
        w(f"| {k} | {v['expected_pp']:+.2f} | {got} | {npair} | "
          f"{v['abs_diff_pp']} | {'YES' if v['within_0.01pp'] else '**NO**'} |")

    w("\n## 3. Pairwise comparisons\n")
    for c in COMPARISONS:
        w(f"### {c['id']}  ·  {' + '.join(c['labels'])}\n")
        w(f"- **Arms:** `{c['a']}` vs `{c['b']}`")
        w(f"- **Cited as:** {c['cited']}")
        w(f"- **Can identify:** {c['identifies']}")
        w(f"- **Cannot be used to claim:** {c['cannot']}")
        w(f"- **Evidence:** {c['evidence']}\n")

    w("\n## 3b. Comparisons that changed from how they were previously described\n")
    for t, body in CHANGED:
        w(f"**{t}**\n")
        w(body + "\n")

    w("\n## 4. Exclusions\n")
    w("| excluded | reason |")
    w("|---|---|")
    for name, why in EXCLUSIONS:
        w(f"| {name} | {why} |")

    w("\n## 5. UNKNOWN fields that matter, and how to recover them\n")
    unk = defaultdict(list)
    for cid, d in ledger.items():
        for f, _ in LEDGER_FIELDS:
            if str(d.get(f, UNK)) == UNK:
                unk[f].append(cid)
    w("| field | cells with UNKNOWN | how it could be recovered |")
    w("|---|---|---|")
    for f, cells in sorted(unk.items(), key=lambda kv: -len(kv[1])):
        w(f"| `{f}` | {len(cells)} | {RECOVERY.get(f, 'not recorded anywhere; would need a re-run.')} |")

    w("\n## 6. The ledger\n")
    for cid in sorted(ledger):
        d = ledger[cid]
        w(f"### `{cid}`\n")
        w("| field | value |")
        w("|---|---|")
        for f, label in LEDGER_FIELDS:
            if f in d:
                w(f"| {label} | {fmt(d[f])} |")
        for extra in ("WARNING_prefix_cache", "note", "sanity", "ttft_s",
                      "accuracy_pct", "cached_tokens_max", "n_excluded_warm_rows",
                      "registry_hosts", "question_text_hash"):
            if extra in d:
                w(f"| {extra} | {fmt(d[extra])} |")
        w("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ledger, reg = build()
    sanity = sanity_checks()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"cells": ledger, "comparisons": COMPARISONS, "sanity_checks": sanity,
               "exclusions": [{"excluded": a, "reason": b} for a, b in EXCLUSIONS]},
              open(OUT_JSON, "w"), indent=1, default=str)
    OUT_MD.write_text(write_report(ledger, sanity, reg))
    print(f"{len(ledger)} cells, {len(COMPARISONS)} comparisons -> {OUT_JSON}")
    print(f"-> {OUT_MD}")
    print("\nSANITY:")
    for k, v in sanity.items():
        if not isinstance(v, dict):
            print(f"  {k} = {v}")
            continue
        r = v["recomputed"]
        got = "none" if r is None else f"{r['delta_pp']:+.4f} (n={r['n_paired']})"
        flag = "ok" if v["within_0.01pp"] else "** DIFFERS **"
        print(f"  {k:28s} expected {v['expected_pp']:+.2f}  got {got}  {flag}")
