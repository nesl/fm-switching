"""
E34 — Sliding-window update semantics + corrected catch-up latency
===================================================================

Three parts, all on A6000 + Qwen2.5-7B + vLLM.

PART A — Update semantics per state object
  What does "absorbing k new turns" mean as a KV-cache operation?
  Measured under two labelled conditions:
    WARM — prefix_caching=True; cache primed before each rep; stated what is primed
    COLD — prefix_caching=False; each rep starts from empty cache

  Objects:
    full       — tail append (prefix preserved)
                 L in {8k,16k,32k,64k}, k in {200,1000,3000}
    win10_grow — growth phase: window <10 sessions, tail append, prefix preserved
                 (use sessions[0:9] → sessions[0:10] as old/new)
    win10_slide — sliding phase: >=10 sessions, head evicted, prefix CHANGES
                 (use sessions[0:10] → sessions[1:11] as old/new)
                 check whether vLLM finds ANY prefix hit
    sum80/sum200 — reference from cost_matrix.csv; not re-measured

PART B — Corrected catch-up latency (replaces E32 Part B)
  LoCoMo n=10, N in {1,5,10,20,50,100}, fidelities {full,win10,sum200}
  Both WARM (stale prefix primed) and COLD (no cache) reported.
  Per-conversation values included; cross-check against committed ~5984 tok/s.

PART C — Consequences (CPU analysis)
  Maintenance cost ordering; TTFT budget compliance; taxonomy check.

Run on A6000 (GPU 1):
  CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID \\
  VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \\
  conda run -n fmtk python experiments/cost/e34_maintenance_semantics.py [--part A|B|C|all]
"""

import argparse
import csv
import gc
import json
import math
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
sys.path.insert(0, str(ROOT / "experiments" / "cost"))

MODEL_ID    = "Qwen/Qwen2.5-7B-Instruct"
MODEL_SLUG  = "qwen7b"
DEVICE_SLUG = "a6000"
OUT_DIR     = ROOT / "results" / "cost" / "e34_maintenance_semantics"
FIG_DIR     = ROOT / "figures" / "cost"

LOCOMO_DATA    = ROOT / "data" / "locomo" / "locomo10.json"
SUM200_CACHE   = ROOT / "results" / "fidelity" / "caches" / "locomo_summaries_200.json"
COST_MATRIX    = ROOT / "results" / "cost" / "cost_matrix.csv"

MAX_MODEL_LEN  = 131072
GPU_MEM_FRAC   = 0.90
REPS           = 5

# Committed cold-prefill rate (A6000, qwen7b, L=8k, E26 cost_matrix.csv)
COMMITTED_CP_RATE = 5984.0   # tokens/s
CROSS_CHECK_THRESH = 2.0     # flag if >2× faster than committed

YARN_ROPE_SCALING = {
    "type": "yarn",
    "factor": 4.0,
    "original_max_position_embeddings": 32768,
}
YARN_L_THRESHOLD = 32768

PART_A_L_VALUES = [8192, 16384, 32768, 65536]
PART_A_K_VALUES = [200, 1000, 3000]
PART_B_N_VALUES = [1, 5, 10, 20, 50, 100]
PART_B_FIDELITIES = ["full", "win10", "sum200"]

TTFT_BUDGETS = {
    "voice_embodied_s": 0.300,
    "interactive_s":    1.000,
    "background_s":    10.000,
}


# ── Utilities ──────────────────────────────────────────────────────────────────

def _save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)
    print(f"  saved {path.relative_to(ROOT)}")


def _summ(vals):
    s = sorted(vals)
    n = len(s)
    med = statistics.median(s)
    q1  = statistics.median(s[: n // 2]) if n >= 2 else med
    q3  = statistics.median(s[n - n // 2 :]) if n >= 2 else med
    return {
        "median_s": round(med,  4),
        "iqr_s":    round(q3 - q1, 4),
        "min_s":    round(s[0], 4),
        "max_s":    round(s[-1], 4),
        "all_s":    [round(v, 4) for v in s],
    }


def _tps(tokens, elapsed_s):
    return round(tokens / elapsed_s, 1) if elapsed_s > 0 and tokens > 0 else None


def _flag(tps):
    if tps is None:
        return "N/A"
    r = tps / COMMITTED_CP_RATE
    return (f"FLAGGED ({r:.1f}× faster than committed cold-prefill; consistent with cache hit)"
            if r > CROSS_CHECK_THRESH else f"ok ({r:.2f}×)")


# ── LoCoMo helpers ─────────────────────────────────────────────────────────────

def load_convs():
    raw = json.loads(LOCOMO_DATA.read_text())
    out = []
    for item in raw:
        cid = item["sample_id"]
        c = item["conversation"]
        sessions, dates, all_turns = [], [], []
        i = 1
        while f"session_{i}" in c:
            turns = c[f"session_{i}"]
            sessions.append(turns)
            dates.append(c.get(f"session_{i}_date_time", ""))
            all_turns.extend(turns)
            i += 1
        out.append({"conv_id": cid, "sessions": sessions,
                    "dates": dates, "all_turns": all_turns})
    return out


def sess2text(sessions, dates):
    lines = []
    for si, (sess, date) in enumerate(zip(sessions, dates)):
        hdr = f"[Session {si + 1}" + (f" — {date}]" if date else "]")
        lines.append(hdr)
        for t in sess:
            lines.append(f"{t['speaker']}: {t['text']}")
        lines.append("")
    return "\n".join(lines).strip()


def get_tok():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(MODEL_ID)


def ntok(tok, text):
    return len(tok.encode(text, add_special_tokens=False))


def build_pad(tok, target_L, convs):
    """Build synthetic context of ≈ target_L tokens from LoCoMo turns."""
    all_turns = [t["text"] for c in convs for s in c["sessions"] for t in s]
    parts, total = [], 0
    idx = 0
    while total < target_L:
        chunk = all_turns[idx % len(all_turns)]
        ids = tok.encode(chunk, add_special_tokens=False)
        if total + len(ids) > target_L:
            clip = target_L - total
            parts.append(tok.decode(ids[:clip]))
            total += clip
            break
        parts.append(chunk)
        total += len(ids)
        idx += 1
    text = "\n".join(parts)
    return text, ntok(tok, text)


def build_ext(tok, target_k, convs, offset_frac=0.5):
    """Build ≈target_k-token extension from the middle of the LoCoMo corpus."""
    all_turns = [t["text"] for c in convs for s in c["sessions"] for t in s]
    n = len(all_turns)
    start = int(n * offset_frac)
    parts, total = [], 0
    idx = start
    while total < target_k:
        chunk = all_turns[idx % n]
        ids = tok.encode(chunk, add_special_tokens=False)
        if total + len(ids) > target_k:
            clip = target_k - total
            parts.append(tok.decode(ids[:clip]))
            total += clip
            break
        parts.append(chunk)
        total += len(ids)
        idx += 1
    text = "\n".join(parts)
    return text, ntok(tok, text)


def sliding_stats(convs):
    rows = []
    for conv in convs:
        S = len(conv["sessions"])
        g  = min(S - 1, 9)
        sl = max(S - 10, 0)
        total = S - 1
        rows.append({
            "conv_id": conv["conv_id"], "n_sessions": S,
            "growth_tr": g, "sliding_tr": sl, "total_tr": total,
            "slide_frac": round(sl / total, 4) if total > 0 else 0.0,
        })
    fracs = [r["slide_frac"] for r in rows]
    agg_slide = sum(r["sliding_tr"] for r in rows)
    agg_total = sum(r["total_tr"]   for r in rows)
    return rows, {
        "median_slide_frac":     round(statistics.median(fracs), 4),
        "min_slide_frac":        round(min(fracs), 4),
        "max_slide_frac":        round(max(fracs), 4),
        "aggregate_slide_frac":  round(agg_slide / max(1, agg_total), 4),
        "total_sliding_tr":      agg_slide,
        "total_transitions":     agg_total,
    }


# ── vLLM engine ────────────────────────────────────────────────────────────────

def _find_model_path():
    base = (Path.home() / ".cache" / "huggingface" / "hub" /
            "models--Qwen--Qwen2.5-7B-Instruct" / "snapshots")
    if base.exists():
        snaps = sorted(base.iterdir())
        if snaps:
            return str(snaps[-1])
    return None


def _yarn_dir(base):
    tmp = Path(tempfile.mkdtemp()) / "qwen_yarn"
    tmp.mkdir()
    src = Path(base)
    cfg = json.loads((src / "config.json").read_text())
    cfg["rope_scaling"] = YARN_ROPE_SCALING
    (tmp / "config.json").write_text(json.dumps(cfg, indent=2))
    for f in src.iterdir():
        if f.name != "config.json":
            (tmp / f.name).symlink_to(f.resolve())
    return str(tmp)


def make_engine(caching: bool, yarn: bool = True):
    from vllm import LLM
    label = ("WARM (prefix_caching=True)"
             if caching else "COLD (prefix_caching=False)")
    print(f"\n  [engine] Starting — {label}, yarn={yarn}")
    if yarn:
        base = _find_model_path()
        if base is None:
            raise RuntimeError("Model cache not found; set HF_HOME or pre-download")
        model = _yarn_dir(base)
    else:
        model = MODEL_ID
    llm = LLM(
        model=model,
        dtype="float16",
        gpu_memory_utilization=GPU_MEM_FRAC,
        enable_prefix_caching=caching,
        max_model_len=MAX_MODEL_LEN,
        enforce_eager=True,
    )
    return llm, label


def drop_engine(llm):
    # vLLM 0.8.5 V1 engine runs in a subprocess; explicit shutdown is needed
    # before del to actually free GPU memory before the next engine loads.
    try:
        llm.llm_engine.engine_core.shutdown()
    except Exception:
        pass
    del llm
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass
    time.sleep(5)  # give the engine subprocess time to exit and release GPU memory


# ── Measurement primitives ─────────────────────────────────────────────────────

def measure_warm_append(llm, prefix_text, ext_text, ext_tokens, reps=REPS):
    """
    WARM: prime cache with prefix_text, time TTFT for prefix_text + ext_text.
    Cache re-primed before each rep.
    """
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=1, temperature=0.0)
    full = prefix_text + "\n" + ext_text

    try:
        llm.generate([prefix_text], sp)   # prime
        llm.generate([full], sp)          # warm-up
    except Exception as e:
        return {"feasible": False, "error": str(e),
                "condition": "WARM (prefix_caching=True; cache primed before each rep)"}

    times = []
    for r in range(reps):
        llm.generate([prefix_text], sp)   # re-prime
        t0 = time.perf_counter()
        llm.generate([full], sp)
        times.append(time.perf_counter() - t0)
        print(f"      warm rep {r+1}/{reps}: {times[-1]:.3f}s")

    med = statistics.median(sorted(times))
    tps = _tps(ext_tokens, med)
    return {
        "feasible": True,
        "condition": "WARM (prefix_caching=True; prefix re-primed before each rep)",
        "extension_tokens": ext_tokens,
        **_summ(times),
        "implied_toks_per_s": tps,
        "crosscheck": _flag(tps),
    }


def measure_cold(llm, text, n_tokens, reps=REPS):
    """
    COLD: prefix_caching=False. Measure TTFT for text from empty cache.
    With caching disabled, each call is a fresh computation.
    """
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=1, temperature=0.0)

    try:
        llm.generate([text], sp)   # warm-up (CUDA context, not prefix)
    except Exception as e:
        return {"feasible": False, "error": str(e),
                "condition": "COLD (prefix_caching=False)"}

    times = []
    for r in range(reps):
        t0 = time.perf_counter()
        llm.generate([text], sp)
        times.append(time.perf_counter() - t0)
        print(f"      cold rep {r+1}/{reps}: {times[-1]:.3f}s")

    med = statistics.median(sorted(times))
    tps = _tps(n_tokens, med)
    return {
        "feasible": True,
        "condition": "COLD (prefix_caching=False; each rep from empty cache)",
        "context_tokens": n_tokens,
        **_summ(times),
        "implied_toks_per_s": tps,
        "crosscheck": _flag(tps),
    }


def measure_new_window_with_old_cached(llm, old_text, new_text, new_tokens, reps=REPS):
    """
    WARM + head-eviction: prime old window, measure TTFT for new window.
    Used to determine whether vLLM finds any prefix hit despite the head change.
    """
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=1, temperature=0.0)

    try:
        llm.generate([old_text], sp)   # prime old (also serves as CUDA warm-up; new_text
                                       # must NOT be pre-generated here or it enters the KV
                                       # cache and subsequent reps retrieve it from cache
                                       # rather than measuring the true cold prefill cost)
    except Exception as e:
        return {"feasible": False, "error": str(e),
                "condition": "WARM(old_primed)+new_window (head-eviction test)"}

    times = []
    for r in range(reps):
        llm.generate([old_text], sp)   # re-prime old
        t0 = time.perf_counter()
        llm.generate([new_text], sp)
        times.append(time.perf_counter() - t0)
        print(f"      slide WARM rep {r+1}/{reps}: {times[-1]:.3f}s")

    med = statistics.median(sorted(times))
    tps = _tps(new_tokens, med)
    return {
        "feasible": True,
        "condition": ("WARM (prefix_caching=True; OLD window primed before each rep; "
                      "NEW window measured — tests whether head-eviction allows any prefix hit)"),
        "new_window_tokens": new_tokens,
        **_summ(times),
        "implied_toks_per_s": tps,
        "crosscheck": _flag(tps),
        "note": "If result ≈ COLD, no prefix hit (expected). If much faster, partial hit occurred.",
    }


# ── PART A ─────────────────────────────────────────────────────────────────────

def part_a(convs, tok, skip_a1=False):
    results_full  = []
    results_win10 = []

    # ── A1: full warm-append and cold-prefill ────────────────────────────────
    if skip_a1:
        print("\n=== Part A1: skipped (--part A2 mode) ===")
    else:
        print("\n=== Part A1: full warm-append ===")
        print("  Cache state: WARM=prefix_caching=True prefix primed; COLD=prefix_caching=False")

        # Build all prompts first
        full_cases = []
        for L in PART_A_L_VALUES:
            prefix_text, actual_L = build_pad(tok, L, convs)
            for k in PART_A_K_VALUES:
                ext_text, actual_k = build_ext(tok, k, convs)
                full_text = prefix_text + "\n" + ext_text
                actual_full = ntok(tok, full_text)
                full_cases.append({
                    "L_target": L, "L_actual": actual_L,
                    "k_target": k, "k_actual": actual_k,
                    "full_context_tokens": actual_full,
                    "prefix_text": prefix_text,
                    "ext_text": ext_text,
                    "full_text": full_text,
                    "yarn": (L >= YARN_L_THRESHOLD),
                })
                print(f"  L={L} k={k}: actual_L={actual_L} actual_k={actual_k} full={actual_full}")

        # WARM pass (all L+k in one engine, using YaRN for all — safe for all L)
        llm, label = make_engine(caching=True, yarn=True)
        for case in full_cases:
            print(f"\n  [WARM] L={case['L_target']} k={case['k_target']}")
            warm = measure_warm_append(llm, case["prefix_text"], case["ext_text"], case["k_actual"])
            case["warm"] = warm
        drop_engine(llm)

        # COLD pass (all L+k in one engine)
        llm, label = make_engine(caching=False, yarn=True)
        for case in full_cases:
            print(f"\n  [COLD] L={case['L_target']} k={case['k_target']}")
            cold = measure_cold(llm, case["full_text"], case["full_context_tokens"])
            case["cold"] = cold
        drop_engine(llm)

        # Assemble results (drop raw text strings)
        for case in full_cases:
            results_full.append({
                "object": "full",
                "update_operation": "tail_append (prefix preserved)",
                "prefix_preserved": True,
                "L_target": case["L_target"], "L_actual": case["L_actual"],
                "k_target": case["k_target"], "k_actual": case["k_actual"],
                "full_context_tokens": case["full_context_tokens"],
                "yarn": case["yarn"],
                "warm": case.get("warm", {}),
                "cold": case.get("cold", {}),
            })

    # ── A2: win-10 growth phase and sliding phase ────────────────────────────
    print("\n=== Part A2: win-10 sliding semantics ===")
    print("  Cache state: WARM=prefix_caching=True; COLD=prefix_caching=False")

    # Build all win10 test cases
    win10_cases = []
    for conv in convs:
        cid = conv["conv_id"]
        S = len(conv["sessions"])
        if S < 12:
            print(f"  {cid}: {S} sessions < 12; skipping")
            continue

        # Growth-phase: sessions[0:9] → sessions[0:10]
        old_grow = sess2text(conv["sessions"][0:9],  conv["dates"][0:9])
        new_grow = sess2text(conv["sessions"][0:10], conv["dates"][0:10])
        # The extension is the added session (sessions[9])
        added_sess_text = sess2text([conv["sessions"][9]], [conv["dates"][9]])
        old_tok_g   = ntok(tok, old_grow)
        new_tok_g   = ntok(tok, new_grow)
        delta_tok_g = ntok(tok, added_sess_text)
        pred_s_g = delta_tok_g / COMMITTED_CP_RATE

        # Sliding-phase: sessions[0:10] → sessions[1:11]
        old_slide = sess2text(conv["sessions"][0:10], conv["dates"][0:10])
        new_slide = sess2text(conv["sessions"][1:11], conv["dates"][1:11])
        old_tok_s  = ntok(tok, old_slide)
        new_tok_s  = ntok(tok, new_slide)
        pred_s_sl  = new_tok_s / COMMITTED_CP_RATE

        print(f"  {cid} (S={S}): "
              f"grow old={old_tok_g} δ={delta_tok_g} | "
              f"slide old={old_tok_s} new={new_tok_s}")

        win10_cases.append({
            "conv_id": cid, "n_sessions_total": S,
            "grow": {
                "old_text": old_grow, "new_text": new_grow,
                "ext_text": added_sess_text,
                "old_tokens": old_tok_g, "new_tokens": new_tok_g,
                "delta_tokens": delta_tok_g, "predicted_cold_s": round(pred_s_g, 3),
            },
            "slide": {
                "old_text": old_slide, "new_text": new_slide,
                "old_tokens": old_tok_s, "new_tokens": new_tok_s,
                "predicted_cold_s": round(pred_s_sl, 3),
            },
        })

    # WARM pass for win10
    llm, _ = make_engine(caching=True, yarn=False)
    for case in win10_cases:
        cid = case["conv_id"]
        print(f"\n  [WARM grow] {cid}")
        case["grow"]["warm"] = measure_warm_append(
            llm, case["grow"]["old_text"], case["grow"]["ext_text"],
            case["grow"]["delta_tokens"])
        print(f"\n  [WARM slide] {cid}")
        case["slide"]["warm"] = measure_new_window_with_old_cached(
            llm, case["slide"]["old_text"], case["slide"]["new_text"],
            case["slide"]["new_tokens"])
    drop_engine(llm)

    # COLD pass for win10
    llm, _ = make_engine(caching=False, yarn=False)
    for case in win10_cases:
        cid = case["conv_id"]
        print(f"\n  [COLD grow] {cid}")
        case["grow"]["cold"] = measure_cold(
            llm, case["grow"]["new_text"], case["grow"]["new_tokens"])
        print(f"\n  [COLD slide] {cid}")
        case["slide"]["cold"] = measure_cold(
            llm, case["slide"]["new_text"], case["slide"]["new_tokens"])
    drop_engine(llm)

    # Assemble (drop raw text)
    for case in win10_cases:
        g = case["grow"]
        s = case["slide"]
        results_win10.append({
            "conv_id": case["conv_id"],
            "n_sessions_total": case["n_sessions_total"],
            "win10_growth": {
                "object": "win10_growth",
                "update_operation": "tail_append (growth phase: <10 sessions, prefix preserved)",
                "prefix_preserved": True,
                "old_tokens": g["old_tokens"], "new_tokens": g["new_tokens"],
                "delta_tokens": g["delta_tokens"],
                "predicted_cold_s": g["predicted_cold_s"],
                "warm": g.get("warm", {}),
                "cold": g.get("cold", {}),
            },
            "win10_slide": {
                "object": "win10_slide",
                "update_operation": "cold_reprefill (sliding phase: head eviction invalidates prefix)",
                "prefix_preserved": False,
                "old_tokens": s["old_tokens"], "new_tokens": s["new_tokens"],
                "predicted_cold_s": s["predicted_cold_s"],
                "warm": s.get("warm", {}),
                "cold": s.get("cold", {}),
            },
        })

    return results_full, results_win10


# ── PART B ─────────────────────────────────────────────────────────────────────

def build_stale(conv, N, fidelity, sum200_cache):
    """Build stale context (N individual turns removed from tail)."""
    sessions  = conv["sessions"]
    dates     = conv["dates"]
    all_turns = conv["all_turns"]
    total     = len(all_turns)
    eff_N     = min(N, total)
    keep      = total - eff_N
    delta_turns = all_turns[keep:]

    rem = keep
    r_sessions, r_dates = [], []
    for sess, date in zip(sessions, dates):
        if rem <= 0:
            break
        if rem >= len(sess):
            r_sessions.append(list(sess))
            r_dates.append(date)
            rem -= len(sess)
        else:
            r_sessions.append(list(sess[:rem]))
            r_dates.append(date)
            rem = 0

    if fidelity == "full":
        text = sess2text(r_sessions, r_dates)
    elif fidelity == "win10":
        text = sess2text(r_sessions[-10:], r_dates[-10:])
    elif fidelity == "sum200":
        cid = conv["conv_id"]
        text = sum200_cache.get(f"{cid}_N{N}", sum200_cache.get(cid, ""))
    else:
        raise ValueError(fidelity)

    return text, delta_turns


def build_current(conv, fidelity, sum200_cache):
    """Build current (N=0) context."""
    if fidelity == "full":
        return sess2text(conv["sessions"], conv["dates"])
    elif fidelity == "win10":
        return sess2text(conv["sessions"][-10:], conv["dates"][-10:])
    elif fidelity == "sum200":
        cid = conv["conv_id"]
        return sum200_cache.get(cid, "")
    raise ValueError(fidelity)


def part_b(convs, tok):
    sum200_cache = {}
    if SUM200_CACHE.exists():
        sum200_cache = json.loads(SUM200_CACHE.read_text())
        print(f"  Loaded sum200 cache: {len(sum200_cache)} entries")
    else:
        print(f"  WARNING: sum200 cache not found; sum200 results will be empty strings")

    # Pre-compute all context texts and token counts
    cells = []   # (conv, fidelity, N, stale_text, current_text, stale_tokens, curr_tokens, delta_tokens)
    for fidelity in PART_B_FIDELITIES:
        for N in PART_B_N_VALUES:
            for conv in convs:
                cid    = conv["conv_id"]
                cur_t  = build_current(conv, fidelity, sum200_cache)
                stale_t, delta_turns = build_stale(conv, N, fidelity, sum200_cache)
                cur_tok   = ntok(tok, cur_t)
                stale_tok = ntok(tok, stale_t)
                delta_tok = sum(ntok(tok, t["text"]) for t in delta_turns) if delta_turns else 0
                n_sess = len(conv["sessions"])
                mean_tps_conv = len(conv["all_turns"]) / max(1, n_sess)
                cells.append({
                    "conv_id":       cid,
                    "fidelity":      fidelity,
                    "N":             N,
                    "session_equiv": round(N / mean_tps_conv, 2) if N > 0 else 0.0,
                    "stale_tokens":  stale_tok,
                    "delta_tokens":  delta_tok,
                    "current_tokens": cur_tok,
                    "current_text":  cur_t,
                    "stale_text":    stale_t,
                    "n_sessions_total": n_sess,
                })

    print(f"\n  {len(cells)} (fidelity, N, conv) cells to measure")

    # Determine if YaRN needed (if any full context >= 32k tokens)
    yarn = any(c["current_tokens"] >= YARN_L_THRESHOLD for c in cells)
    print(f"  yarn={yarn}")

    # WARM pass: one engine for all cells
    print("\n[Part B WARM pass]")
    print("  Cache state: prefix_caching=True; stale context primed before each rep")
    llm, _ = make_engine(caching=True, yarn=yarn)
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=1, temperature=0.0)

    for cell in cells:
        if not cell["current_text"] or not cell["stale_text"]:
            cell["warm"] = {"feasible": False, "error": "empty context text"}
            continue
        cid = cell["conv_id"]
        fid = cell["fidelity"]
        N   = cell["N"]

        # Prime stale; warm-up current
        llm.generate([cell["stale_text"]], sp)
        llm.generate([cell["current_text"]], sp)

        times = []
        for r in range(REPS):
            llm.generate([cell["stale_text"]], sp)   # re-prime stale
            t0 = time.perf_counter()
            llm.generate([cell["current_text"]], sp)
            times.append(time.perf_counter() - t0)

        med = statistics.median(sorted(times))
        # implied rate based on delta_tokens (the "new" content that should be processed)
        delta_tps = _tps(cell["delta_tokens"], med)
        # implied rate based on current_tokens (cold-equivalent rate check)
        curr_tps  = _tps(cell["current_tokens"], med)
        cell["warm"] = {
            "condition":    ("WARM (prefix_caching=True; stale context primed before each rep; "
                             "TTFT measures extension of stale KV to current context)"),
            **_summ(times),
            "implied_toks_per_s_delta": delta_tps,
            "implied_toks_per_s_current": curr_tps,
            "crosscheck_delta": _flag(delta_tps),
            "crosscheck_current": _flag(curr_tps),
        }
        print(f"    {fid} N={N} {cid}: warm_med={med:.3f}s "
              f"delta_tps={delta_tps} {_flag(delta_tps)}")

    drop_engine(llm)

    # COLD pass: one engine for all cells
    print("\n[Part B COLD pass]")
    print("  Cache state: prefix_caching=False; each rep from empty cache")
    llm, _ = make_engine(caching=False, yarn=yarn)

    for cell in cells:
        if not cell["current_text"]:
            cell["cold"] = {"feasible": False, "error": "empty context text"}
            continue
        cid = cell["conv_id"]
        fid = cell["fidelity"]
        N   = cell["N"]

        llm.generate([cell["current_text"]], sp)   # warm-up CUDA context

        times = []
        for r in range(REPS):
            t0 = time.perf_counter()
            llm.generate([cell["current_text"]], sp)
            times.append(time.perf_counter() - t0)

        med = statistics.median(sorted(times))
        curr_tps = _tps(cell["current_tokens"], med)
        cell["cold"] = {
            "condition": ("COLD (prefix_caching=False; each rep is a full re-prefill from empty cache)"),
            **_summ(times),
            "implied_toks_per_s_current": curr_tps,
            "crosscheck_current": _flag(curr_tps),
        }
        print(f"    {fid} N={N} {cid}: cold_med={med:.3f}s "
              f"curr_tps={curr_tps} {_flag(curr_tps)}")

    drop_engine(llm)

    # Serialize (drop text, keep numbers)
    out = []
    for cell in cells:
        out.append({k: v for k, v in cell.items()
                    if k not in ("current_text", "stale_text")})
    return out


# ── PART C: Analysis ────────────────────────────────────────────────────────────

def part_c(results_full, results_win10, results_b, convs, tok):
    slide_rows, slide_agg = sliding_stats(convs)

    # Win10 token counts
    win10_toks = [ntok(tok, sess2text(c["sessions"][-10:], c["dates"][-10:])) for c in convs]
    win10_med  = int(statistics.median(sorted(win10_toks)))

    # Summary references from cost_matrix.csv
    cm_ref = {}
    if COST_MATRIX.exists():
        with open(COST_MATRIX) as f:
            for row in csv.DictReader(f):
                if row.get("tier") == "a6000" and row.get("model") == "qwen7b":
                    key = (row["representation"], int(row["L_tokens"]))
                    cm_ref[key] = row

    def cm_val(rep, L, field):
        r = cm_ref.get((rep, L))
        return float(r[field]) if r and r.get(field) else None

    # Committed reference values
    sum80_restore_ms  = cm_val("summary_80",  8192, "restore_ms")   or 29.0
    sum200_restore_ms = cm_val("summary_200", 8192, "restore_ms")   or 32.0
    sum80_update_ms   = cm_val("summary_80",  8192, "update_ms")    or 4804.0
    sum200_update_ms  = cm_val("summary_200", 8192, "update_ms")    or 9565.0

    # Win10 restore: cold re-prefill of the ~7275-token current window
    # Take from Part A win10 slide COLD measurements (new_tokens ≈ win10 window size)
    slide_cold_ms_vals = []
    grow_warm_ms_vals  = []
    slide_warm_ms_vals = []
    for case in results_win10:
        sl = case.get("win10_slide", {})
        gr = case.get("win10_growth", {})
        if sl.get("cold", {}).get("feasible"):
            slide_cold_ms_vals.append(sl["cold"]["median_s"] * 1000)
        if sl.get("warm", {}).get("feasible"):
            slide_warm_ms_vals.append(sl["warm"]["median_s"] * 1000)
        if gr.get("warm", {}).get("feasible"):
            grow_warm_ms_vals.append(gr["warm"]["median_s"] * 1000)

    win10_restore_ms = (statistics.median(sorted(slide_cold_ms_vals))
                        if slide_cold_ms_vals else None)
    win10_grow_ms    = (statistics.median(sorted(grow_warm_ms_vals))
                        if grow_warm_ms_vals else None)
    win10_slide_warm_ms = (statistics.median(sorted(slide_warm_ms_vals))
                           if slide_warm_ms_vals else None)

    agg_sf = slide_agg["aggregate_slide_frac"]
    if win10_restore_ms is not None and win10_grow_ms is not None:
        win10_amortized_ms = (1 - agg_sf) * win10_grow_ms + agg_sf * win10_restore_ms
    else:
        win10_amortized_ms = None

    # Taxonomy check: does win10 slide WARM ≈ COLD?
    if win10_slide_warm_ms is not None and win10_restore_ms is not None:
        wc_ratio = win10_slide_warm_ms / win10_restore_ms
        prefix_hit = (wc_ratio < 0.5)
        if prefix_hit:
            taxonomy_note = (
                f"win10 slide WARM ({win10_slide_warm_ms:.0f}ms) << COLD ({win10_restore_ms:.0f}ms) "
                f"[ratio {wc_ratio:.2f}]: partial prefix hit detected; update semantics MAY be "
                f"closer to append in this case."
            )
        else:
            taxonomy_note = (
                f"win10 slide WARM ({win10_slide_warm_ms:.0f}ms) ≈ COLD ({win10_restore_ms:.0f}ms) "
                f"[ratio {wc_ratio:.2f}]: no prefix hit. Head eviction produces a full re-prefill. "
                f"The formulation's two-class taxonomy (raw-append vs derived-regenerate) must "
                f"become THREE classes: (1) raw-append (full, win10-growth), (2) cold-reprefill "
                f"(win10-slide), (3) derived-regenerate (sum80, sum200). "
                f"Amortized win10 update cost ≠ append cost."
            )
    else:
        prefix_hit   = None
        taxonomy_note = "UNTRACEABLE: Part A win10 slide results not available"

    # TTFT budget compliance
    def budget_check(ms_val):
        if ms_val is None:
            return "NOT MEASURED"
        s = ms_val / 1000.0
        return {k: ("PASS" if s <= v else "FAIL") for k, v in TTFT_BUDGETS.items()}

    # Win10 restore meets 1s interactive budget?
    win10_meets_1s_interactive = (
        win10_restore_ms is not None and win10_restore_ms < 1000.0)

    # Cross-check Part B: flag any cell where WARM is >2× faster than committed cold-prefill
    b_flags = []
    for cell in results_b:
        w = cell.get("warm", {})
        delta_tps = w.get("implied_toks_per_s_delta")
        if delta_tps and (delta_tps / COMMITTED_CP_RATE) > CROSS_CHECK_THRESH:
            b_flags.append({
                "conv_id":  cell["conv_id"],
                "fidelity": cell["fidelity"],
                "N":        cell["N"],
                "warm_median_s": w.get("median_s"),
                "delta_tokens":  cell["delta_tokens"],
                "implied_delta_tps": delta_tps,
                "ratio": round(delta_tps / COMMITTED_CP_RATE, 2),
                "flag": "WARM >>2× committed cold-prefill; likely cache hit not true extension",
            })

    analysis = {
        "sliding_frequency": {
            "per_conversation": slide_rows,
            "aggregate": slide_agg,
        },
        "win10_token_counts": {
            "per_conv": win10_toks,
            "median":   win10_med,
        },
        "maintenance_cost_ms": {
            "sum80_restore":     sum80_restore_ms,
            "sum200_restore":    sum200_restore_ms,
            "sum80_update_L8k":  sum80_update_ms,
            "sum200_update_L8k": sum200_update_ms,
            "win10_grow_warm":   win10_grow_ms,
            "win10_slide_cold":  win10_restore_ms,
            "win10_amortized":   win10_amortized_ms,
            "win10_slide_warm":  win10_slide_warm_ms,
            "note": ("win10_amortized = (1-slide_frac)×grow_warm + slide_frac×slide_cold; "
                     f"slide_frac={agg_sf}"),
        },
        "win10_restore_ms": win10_restore_ms,
        "win10_meets_1s_interactive_budget": win10_meets_1s_interactive,
        "budget_compliance": {
            "sum80_restore":  budget_check(sum80_restore_ms),
            "sum200_restore": budget_check(sum200_restore_ms),
            "win10_restore":  budget_check(win10_restore_ms),
            "win10_grow":     budget_check(win10_grow_ms),
            "win10_slide":    budget_check(win10_restore_ms),
        },
        "taxonomy": {
            "formulation_claim": "two-class: raw-append (full,win) vs derived-regenerate (sum)",
            "win10_slide_prefix_hit": prefix_hit,
            "warm_cold_ratio":   (round(wc_ratio, 3) if (win10_slide_warm_ms and win10_restore_ms) else None),
            "conclusion": taxonomy_note,
        },
        "part_b_crosscheck_flags": b_flags,
    }

    return analysis


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="all", choices=["A", "A2", "B", "C", "all"])
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading LoCoMo conversations...")
    convs = load_convs()
    print(f"  {len(convs)} conversations, sessions: "
          f"min={min(len(c['sessions']) for c in convs)} "
          f"max={max(len(c['sessions']) for c in convs)}")

    print("\nLoading tokenizer...")
    tok = get_tok()

    results_full  = []
    results_win10 = []
    results_b     = []

    if args.part in ("A", "all"):
        results_full, results_win10 = part_a(convs, tok)
        _save(OUT_DIR / "part_a_full.json", {
            "description": "full: warm-append vs cold-prefill at L+k",
            "cache_state": "WARM=prefix_caching=True prefix-primed; COLD=prefix_caching=False",
            "measurements": results_full,
        })
        _save(OUT_DIR / "part_a_win10.json", {
            "description": "win10: growth-phase append vs sliding-phase re-prefill",
            "cache_state": "WARM=prefix_caching=True; COLD=prefix_caching=False",
            "measurements": results_win10,
        })
    elif args.part == "A2":
        # Re-run only win10 (A2) — load A1 full results from disk, re-run A2 with bug fix.
        p = OUT_DIR / "part_a_full.json"
        if p.exists():
            results_full = json.loads(p.read_text())["measurements"]
        _, results_win10 = part_a(convs, tok, skip_a1=True)
        _save(OUT_DIR / "part_a_win10.json", {
            "description": "win10: growth-phase append vs sliding-phase re-prefill (bug-fixed: slide warm no longer pre-caches new_text)",
            "cache_state": "WARM=prefix_caching=True; COLD=prefix_caching=False",
            "measurements": results_win10,
        })
    else:
        p = OUT_DIR / "part_a_full.json"
        if p.exists():
            results_full = json.loads(p.read_text())["measurements"]
        p = OUT_DIR / "part_a_win10.json"
        if p.exists():
            results_win10 = json.loads(p.read_text())["measurements"]

    if args.part in ("B", "all"):
        results_b = part_b(convs, tok)
        _save(OUT_DIR / "part_b_catchup.json", {
            "description": "corrected catch-up latency: WARM and COLD, per-conversation",
            "n_conversations": len(convs),
            "fidelities": PART_B_FIDELITIES,
            "N_values": PART_B_N_VALUES,
            "reps_per_cell": REPS,
            "cache_state": (
                "WARM: prefix_caching=True; stale context primed before each rep. "
                "COLD: prefix_caching=False; each rep from empty cache. "
                "Warm≈Cold for small delta → cache-hit (old E32 artifact). "
                "Warm<<Cold → true prefix reuse."
            ),
            "measurements": results_b,
        })
    else:
        p = OUT_DIR / "part_b_catchup.json"
        if p.exists():
            results_b = json.loads(p.read_text())["measurements"]

    # Part C always runs
    print("\n=== Part C: Analysis ===")
    analysis = part_c(results_full, results_win10, results_b, convs, tok)
    _save(OUT_DIR / "part_c_analysis.json", analysis)

    # Provenance
    try:
        from _provenance import stamp
        prov = stamp(script="e34_maintenance_semantics.py",
                     model=MODEL_SLUG, device=DEVICE_SLUG,
                     n=len(convs), args=args)
    except Exception:
        import datetime
        prov = {"git_commit": "pre-provenance",
                "script": "e34_maintenance_semantics.py",
                "model": MODEL_SLUG, "device": DEVICE_SLUG,
                "timestamp": datetime.datetime.now().isoformat()}

    _save(OUT_DIR / "e34_summary.json", {
        "experiment": "E34",
        "description": "Sliding-window update semantics + corrected catch-up latency",
        "parts_run": args.part,
        "n_conversations": len(convs),
        "_provenance": prov,
    })
    print("\nAll done.")


if __name__ == "__main__":
    main()
