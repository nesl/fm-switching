"""
E35 (E34b) — Corrected WARM catch-up latency and maintenance ordering
======================================================================

Corrects three defects in E34 Parts B and C.

DEFECT 1 — E34 Part B WARM warm-up bug:
  The pre-timing call `llm.generate([cell["current_text"]], sp)` cached
  current_text before any timed rep. All 5 reps then saw a full cache hit on the
  entire current_text — not on the stale prefix only. This produced a flat
  ~25-65 ms line regardless of N or fidelity (cache-hit TTFT on the full context).

  Fix: prime ONLY stale_text before timing. Do NOT touch current_text before the
  timed call. Use a SEPARATE engine load per (fidelity, N, rep) so no
  current_text from a prior N leaks into the KV cache. Engine reload between reps
  is the flush mechanism. Verify: rep1 ≈ rep2 (if rep1 >> rep2, flush is broken).

DEFECT 2 — E34 Part B COLD mislabeled as catch-up:
  build_current() is N-independent; COLD measurements are cold RESTORE cost
  (already in cost_matrix.csv), not catch-up latency. Relabeled here; no
  re-measurement needed.

DEFECT 3 — E34 Part C maintenance ordering error:
  Listed "full COLD re-prefill 3,620ms" as full's maintenance cost. Full's actual
  maintenance cost is warm tail-append (~66ms, E26): the prefix is preserved in
  the KV cache between consecutive turns and never fully evicted. Corrected in
  Part 3 below.

Measurement design:
  Full and win10 (TTFT measurements):
    - Separate engine load per (fidelity, N, rep).
    - Within each engine: prime stale_text ONLY; time generate(current_text,
      max_tokens=1). Expected: stale prefix blocks in cache; delta freshly prefilled.
    - N_REPS=2 engine loads per (fidelity, N). Cross-check: rep1 ≈ rep2.
    - Fidelity separation: full and win10 in separate engines to prevent cross-
      fidelity contamination (win10 is a suffix of full for the same conv; shared
      blocks would give false cache hits).

  sum200 (TTFT + generation):
    - Part 2A (TTFT): 2 engine loads, all N in each (N-independent by construction).
    - Part 2B (recursive generation): 2 engine loads, all N and convs in each.
      Within-engine cross-N contamination negligible: decode (~5.7s) dominates.
    - Part 2C (full regen): 2 engine loads, all convs in each (N-independent).

  Physical validity: every implied tok/s cross-checked vs committed A6000
  cold-prefill rate (5,984 tok/s). Values >2× flagged as cache-hit artifacts.

Engine count: 2 fidelities × 6N × 2reps + 3 sum200 variants × 2reps = 30 loads.
Estimated runtime: ~3 hours on A6000.

Run:
  CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID \\
  VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \\
  PYTHONUNBUFFERED=1 \\
  conda run -n vllm_calib2 python experiments/cost/e34b_catchup.py 2>&1 | tee /tmp/e34b.log
"""

import gc
import json
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
OUT_DIR     = ROOT / "results" / "cost" / "e34b_catchup"

LOCOMO_DATA      = ROOT / "data" / "locomo" / "locomo10.json"
SUM200_CACHE     = ROOT / "results" / "fidelity" / "caches" / "locomo_summaries_200.json"
E34_A_WIN10_JSON = ROOT / "results" / "cost" / "e34_maintenance_semantics" / "part_a_win10.json"

MAX_MODEL_LEN   = 131072
GPU_MEM_FRAC    = 0.90
N_REPS          = 2      # separate engine loads per (fidelity, N) cell

COMMITTED_CP_RATE  = 5984.0   # tok/s — E21/E26 A6000 qwen7b cold prefill
E26_WARM_APPEND_MS = 66.0     # ms — E26 committed, L=8k warm tail-append
E34_SLIDE_FRAC     = 0.657    # from E34 Part C (65.7% of win10 transitions are slides)
E34_SLIDE_COLD_MS  = 975.0    # ms — E34 Part A win10 slide COLD (committed fallback)
E34_GROW_WARM_MS   = 36.0     # ms — E34 Part A win10 grow WARM (committed fallback)
SUM200_UPDATE_MS   = 9565.0   # ms — E27 committed (full-context sum200 update)
SUM200_RESTORE_MS  = 32.0     # ms — cost_matrix.csv (sum200 restore at L=8k)

CROSS_CHECK_THRESH = 2.0
YARN_ROPE_SCALING  = {
    "type": "yarn", "factor": 4.0,
    "original_max_position_embeddings": 32768,
}
YARN_L_THRESHOLD = 32768

N_VALUES   = [1, 5, 10, 20, 50, 100]
FIDELITIES = ["full", "win10"]

SUMMARIZE_PREFIX = "Summarize this conversation in about 200 words:\n\n"

TTFT_BUDGETS = {
    "voice_embodied_s": 0.300,
    "interactive_s":    1.000,
    "background_s":    10.000,
}


# ── Utilities ─────────────────────────────────────────────────────────────────

def _save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)
    print(f"  saved {path.relative_to(ROOT)}", flush=True)


def _tps(tokens, elapsed_s):
    if not tokens or elapsed_s <= 0:
        return None
    return round(tokens / elapsed_s, 1)


def _flag(tps):
    if tps is None:
        return "N/A"
    r = tps / COMMITTED_CP_RATE
    return (f"FLAGGED ({r:.1f}x faster than committed cold-prefill)"
            if r > CROSS_CHECK_THRESH else f"ok ({r:.2f}x)")


def _med(vals):
    return statistics.median(sorted(vals)) if vals else None


def _budget(ms):
    s = ms / 1000.0
    return {k: s <= v for k, v in TTFT_BUDGETS.items()}


# ── LoCoMo helpers ────────────────────────────────────────────────────────────

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


def build_stale(conv, N, fidelity):
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
    else:
        raise ValueError(fidelity)

    return text, delta_turns


def build_current(conv, fidelity):
    if fidelity == "full":
        return sess2text(conv["sessions"], conv["dates"])
    elif fidelity == "win10":
        return sess2text(conv["sessions"][-10:], conv["dates"][-10:])
    raise ValueError(fidelity)


# ── vLLM engine ───────────────────────────────────────────────────────────────

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
    label = "WARM (prefix_caching=True)" if caching else "COLD (prefix_caching=False)"
    print(f"\n  [engine] Starting — {label}, yarn={yarn}", flush=True)
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
    # V1 engine runs in a subprocess; explicit shutdown is needed before del
    # to actually free GPU memory before the next engine loads.
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
    time.sleep(5)


# ── Part 1: Corrected WARM catch-up (full and win10) ─────────────────────────

def _run_catchup_engine(convs, tok, fidelity, N, yarn):
    """
    One engine load: measure WARM catch-up for one (fidelity, N) across 10 convs.

    Procedure (defect-1 fix):
      For each conv:
        1. Prime ONLY stale_text. Do NOT touch current_text before timing.
        2. Time generate(current_text, max_tokens=1).

    Stale-prefix blocks are in cache; delta tokens must be prefilled fresh.
    Returns per-conv rows with elapsed_s and delta_tokens.
    """
    from vllm import SamplingParams
    sp = SamplingParams(max_tokens=1, temperature=0.0)

    llm, _ = make_engine(caching=True, yarn=yarn)
    rows = []
    for conv in convs:
        cid = conv["conv_id"]
        current_text = build_current(conv, fidelity)
        stale_text, delta_turns = build_stale(conv, N, fidelity)

        cur_tok   = ntok(tok, current_text)
        stale_tok = ntok(tok, stale_text)
        delta_tok = sum(ntok(tok, t["text"]) for t in delta_turns) if delta_turns else 0

        if not current_text or not stale_text:
            rows.append({"conv_id": cid, "feasible": False, "error": "empty text"})
            continue

        # Step 1: prime stale ONLY (delta stays uncached)
        llm.generate([stale_text], sp)

        # Step 2: timed call — stale prefix in cache, delta must be freshly prefilled
        t0 = time.perf_counter()
        llm.generate([current_text], sp)
        elapsed = time.perf_counter() - t0

        delta_tps = _tps(delta_tok, elapsed)
        print(f"      {fidelity} N={N} {cid}: "
              f"elapsed={elapsed:.3f}s delta_tok={delta_tok} "
              f"tps={delta_tps} {_flag(delta_tps)}", flush=True)
        rows.append({
            "conv_id":       cid,
            "feasible":      True,
            "fidelity":      fidelity,
            "N":             N,
            "stale_tokens":  stale_tok,
            "current_tokens": cur_tok,
            "delta_tokens":  delta_tok,
            "elapsed_s":     round(elapsed, 4),
            "implied_delta_tps": delta_tps,
            "crosscheck_delta":  _flag(delta_tps),
        })
    drop_engine(llm)
    return rows


def part1_warm_catchup(convs, tok):
    """
    Corrected WARM catch-up for full and win10.
    N_REPS separate engine loads per (fidelity, N). Compare rep1 vs rep2.
    Fidelities measured in separate passes to prevent cross-fidelity contamination.
    """
    all_results = {}

    for fidelity in FIDELITIES:
        yarn = any(
            ntok(tok, build_current(c, fidelity)) >= YARN_L_THRESHOLD
            for c in convs
        )
        print(f"\n{'='*60}", flush=True)
        print(f"Part 1 WARM: fidelity={fidelity} (yarn={yarn})", flush=True)
        print(f"{'='*60}", flush=True)
        fid_results = {}
        for N in N_VALUES:
            reps = []
            for rep in range(1, N_REPS + 1):
                print(f"\n  [{fidelity} N={N} rep {rep}/{N_REPS}]", flush=True)
                rows = _run_catchup_engine(convs, tok, fidelity, N, yarn)
                reps.append(rows)
            fid_results[str(N)] = reps
        all_results[fidelity] = fid_results

    # Aggregate: pair rep1 vs rep2 per (fidelity, N, conv)
    summary = {}
    for fidelity in FIDELITIES:
        summary[fidelity] = {}
        for N in N_VALUES:
            reps = all_results[fidelity][str(N)]
            r1_by = {r["conv_id"]: r for r in reps[0] if r.get("feasible")}
            r2_by = {r["conv_id"]: r for r in reps[1] if r.get("feasible")} if len(reps) > 1 else {}
            paired = []
            for cid, r1 in r1_by.items():
                r2 = r2_by.get(cid)
                ratio = ((r2["elapsed_s"] / max(r1["elapsed_s"], 1e-6))
                         if r2 else None)
                flush_ok = (0.3 <= ratio <= 3.0) if ratio is not None else None
                paired.append({
                    "conv_id":           cid,
                    "delta_tokens":      r1["delta_tokens"],
                    "stale_tokens":      r1["stale_tokens"],
                    "current_tokens":    r1["current_tokens"],
                    "rep1_elapsed_s":    r1["elapsed_s"],
                    "rep2_elapsed_s":    r2["elapsed_s"] if r2 else None,
                    "rep2_vs_rep1":      round(ratio, 3) if ratio else None,
                    "flush_verified":    flush_ok,
                    "implied_delta_tps_rep1": r1["implied_delta_tps"],
                    "crosscheck_rep1":   r1["crosscheck_delta"],
                })

            elap_r1 = [p["rep1_elapsed_s"] for p in paired if p["rep1_elapsed_s"]]
            elap_r2 = [p["rep2_elapsed_s"] for p in paired if p["rep2_elapsed_s"]]
            dtoks   = [p["delta_tokens"] for p in paired]
            all_flush = all(p["flush_verified"] for p in paired if p["flush_verified"] is not None)

            print(f"\n  {fidelity} N={N}: "
                  f"rep1_med={_med(elap_r1):.3f}s "
                  f"rep2_med={_med(elap_r2):.3f}s "
                  f"delta_tok_med={int(_med(dtoks)) if dtoks else 'N/A'} "
                  f"flush_ok={all_flush}", flush=True)

            summary[fidelity][str(N)] = {
                "fidelity":  fidelity,
                "N":         N,
                "flush_method": (
                    "Separate engine load per rep guarantees empty KV cache. "
                    "Flush verified by rep1 ≈ rep2."
                ),
                "flush_verified_all_convs": all_flush,
                "median_elapsed_rep1_s": round(_med(elap_r1), 4) if elap_r1 else None,
                "median_elapsed_rep2_s": round(_med(elap_r2), 4) if elap_r2 else None,
                "delta_tokens_median": int(_med(dtoks)) if dtoks else None,
                "per_conv": paired,
            }

    out = {
        "description": (
            "Corrected WARM catch-up latency for full and win10. "
            "Defect fixed: no current_text warm-up before timing. "
            "Flush: separate engine load per (fidelity, N, rep)."
        ),
        "measurement_procedure": (
            "For each (fidelity, N): N_REPS=2 separate engine loads. "
            "Within each engine, for each conv: prime stale_text ONLY; "
            "time generate(current_text, max_tokens=1). "
            "Stale-prefix blocks in cache; delta prefilled fresh. "
            "Cross-fidelity contamination avoided by separate engines per fidelity "
            "(win10 is suffix of full for same conv; shared blocks give false hits)."
        ),
        "committed_cp_rate_toks": COMMITTED_CP_RATE,
        "summary": summary,
        "raw_reps": all_results,
    }
    _save(OUT_DIR / "part1_warm_catchup.json", out)
    return summary


# ── Part 2: sum200 catch-up ───────────────────────────────────────────────────

def part2_sum200(convs, tok, sum200_cache):
    """
    sum200 catch-up has two distinct components:

    Part 2A — TTFT to serve a query from current sum200 state.
      current_sum is N-independent (~160 tokens). Measured to verify N-invariance.
      Expected: ~37ms regardless of N (confirms cost_matrix.csv entry).

    Part 2B — Recursive update generation:
      (current_sum + N_new_turns) -> new_summary (max_tokens=250).
      With WARM: current_sum in cache; N_new_turns prefilled fresh; then decode.
      Decode (~5.7s) dominates. Within-engine cross-N contamination negligible.
      Two engine loads (one per rep).

    Part 2C — Full regen generation:
      (full_current_conversation) -> new_summary (max_tokens=250).
      N-independent. Each conv's full_text is unique so no cross-conv contamination.
      Two engine loads (one per rep). Expect per-conv variation proportional to
      conversation length (NOT the E32 constant distribution artifact).
    """
    from vllm import SamplingParams
    sp_ttft = SamplingParams(max_tokens=1,   temperature=0.0)
    sp_gen  = SamplingParams(max_tokens=250, temperature=0.0)

    # Build per-conv data once
    conv_data = []
    for conv in convs:
        cid = conv["conv_id"]
        all_turns  = conv["all_turns"]
        cur_sum    = sum200_cache.get(cid, "")
        cur_sum_tok = ntok(tok, cur_sum) if cur_sum else 0
        cur_full   = sess2text(conv["sessions"], conv["dates"])
        cur_full_tok = ntok(tok, cur_full)
        yarn_needed = cur_full_tok >= YARN_L_THRESHOLD

        n_rows = []
        for N in N_VALUES:
            total = len(all_turns)
            eff_N = min(N, total)
            keep  = total - eff_N
            delta_turns = all_turns[keep:]
            delta_text  = "\n".join(t["text"] for t in delta_turns)
            delta_tok   = sum(ntok(tok, t["text"]) for t in delta_turns) if delta_turns else 0
            # Recursive input: current_sum (as stale proxy) + new turns
            rec_input = (SUMMARIZE_PREFIX + cur_sum + "\n\nNew turns:\n" + delta_text
                         if delta_turns else SUMMARIZE_PREFIX + cur_sum)
            rec_tok = ntok(tok, rec_input)
            n_rows.append({
                "N": N,
                "delta_tokens": delta_tok,
                "recursive_input": rec_input,
                "recursive_input_tokens": rec_tok,
            })

        fullregen_input = SUMMARIZE_PREFIX + cur_full
        fullregen_tok   = ntok(tok, fullregen_input)

        conv_data.append({
            "conv_id":            cid,
            "current_sum":        cur_sum,
            "current_sum_tokens": cur_sum_tok,
            "fullregen_input":    fullregen_input,
            "fullregen_tokens":   fullregen_tok,
            "yarn_needed":        yarn_needed,
            "n_rows":             n_rows,
        })

    yarn = any(c["yarn_needed"] for c in conv_data)
    print(f"\n  sum200 yarn={yarn}", flush=True)

    # Part 2A: TTFT
    print("\n=== Part 2A: sum200 TTFT (N-independent; verify invariance) ===", flush=True)
    ttft_reps = []
    for rep in range(1, N_REPS + 1):
        print(f"\n  [TTFT rep {rep}/{N_REPS}]", flush=True)
        llm, _ = make_engine(caching=True, yarn=yarn)
        rep_rows = []
        for cd in conv_data:
            cid     = cd["conv_id"]
            cur_sum = cd["current_sum"]
            if not cur_sum:
                continue
            for nr in cd["n_rows"]:
                N = nr["N"]
                # Prime current_sum (as stale proxy); time TTFT for current_sum
                llm.generate([cur_sum], sp_ttft)
                t0 = time.perf_counter()
                llm.generate([cur_sum], sp_ttft)
                elapsed = time.perf_counter() - t0
                tps = _tps(cd["current_sum_tokens"], elapsed)
                print(f"      TTFT N={N} {cid}: {elapsed:.4f}s tps={tps} {_flag(tps)}", flush=True)
                rep_rows.append({
                    "conv_id": cid, "N": N,
                    "current_sum_tokens": cd["current_sum_tokens"],
                    "elapsed_s": round(elapsed, 4),
                    "implied_tps": tps,
                    "crosscheck": _flag(tps),
                })
        drop_engine(llm)
        ttft_reps.append(rep_rows)

    # Part 2B: recursive generation
    print("\n=== Part 2B: sum200 recursive generation ===", flush=True)
    recursive_reps = []
    for rep in range(1, N_REPS + 1):
        print(f"\n  [recursive rep {rep}/{N_REPS}]", flush=True)
        llm, _ = make_engine(caching=True, yarn=yarn)
        rep_rows = []
        for cd in conv_data:
            cid     = cd["conv_id"]
            cur_sum = cd["current_sum"]
            if not cur_sum:
                continue
            for nr in cd["n_rows"]:
                N = nr["N"]
                # Prime current_sum (stale proxy)
                llm.generate([cur_sum], sp_ttft)
                t0 = time.perf_counter()
                out = llm.generate([nr["recursive_input"]], sp_gen)
                elapsed = time.perf_counter() - t0
                n_out = len(out[0].outputs[0].token_ids) if out else 0
                print(f"      recursive N={N} {cid}: {elapsed:.3f}s n_out={n_out}", flush=True)
                rep_rows.append({
                    "conv_id": cid, "N": N,
                    "recursive_input_tokens": nr["recursive_input_tokens"],
                    "delta_tokens": nr["delta_tokens"],
                    "elapsed_s": round(elapsed, 4),
                    "output_tokens": n_out,
                    "note": "decode-dominated; within-engine cross-N contamination negligible",
                })
        drop_engine(llm)
        recursive_reps.append(rep_rows)

    # Part 2C: full regen
    print("\n=== Part 2C: sum200 full regen (N-independent; check distribution) ===", flush=True)
    fullregen_reps = []
    for rep in range(1, N_REPS + 1):
        print(f"\n  [full_regen rep {rep}/{N_REPS}]", flush=True)
        llm, _ = make_engine(caching=True, yarn=yarn)
        rep_rows = []
        for cd in conv_data:
            cid = cd["conv_id"]
            t0 = time.perf_counter()
            out = llm.generate([cd["fullregen_input"]], sp_gen)
            elapsed = time.perf_counter() - t0
            n_out = len(out[0].outputs[0].token_ids) if out else 0
            print(f"      full_regen {cid}: {elapsed:.3f}s n_out={n_out} "
                  f"fullregen_tok={cd['fullregen_tokens']}", flush=True)
            rep_rows.append({
                "conv_id":           cid,
                "fullregen_tokens":  cd["fullregen_tokens"],
                "elapsed_s":         round(elapsed, 4),
                "output_tokens":     n_out,
                "note": "N-independent (input is always full current conversation)",
            })
        drop_engine(llm)
        fullregen_reps.append(rep_rows)

    # Aggregate
    def _agg_by_N(reps):
        agg = {}
        for N in N_VALUES:
            r1 = [r for r in reps[0] if r.get("N") == N] if reps else []
            r2 = [r for r in reps[1] if r.get("N") == N] if len(reps) > 1 else []
            r1_med = _med([r["elapsed_s"] for r in r1])
            r2_med = _med([r["elapsed_s"] for r in r2])
            dtoks  = _med([r.get("delta_tokens", 0) for r in r1])
            agg[str(N)] = {
                "N": N,
                "delta_tokens_median": round(dtoks) if dtoks else None,
                "median_s_rep1": round(r1_med, 3) if r1_med else None,
                "median_s_rep2": round(r2_med, 3) if r2_med else None,
                "per_conv_rep1": [{"conv_id": r["conv_id"],
                                   "elapsed_s": r["elapsed_s"]} for r in r1],
            }
        return agg

    def _agg_flat(reps):
        r1_med = _med([r["elapsed_s"] for r in reps[0]]) if reps else None
        r2_med = _med([r["elapsed_s"] for r in reps[1]]) if len(reps) > 1 else None
        return {
            "median_s_rep1": round(r1_med, 3) if r1_med else None,
            "median_s_rep2": round(r2_med, 3) if r2_med else None,
            "per_conv_rep1": ([{"conv_id": r["conv_id"],
                                "fullregen_tokens": r.get("fullregen_tokens"),
                                "elapsed_s": r["elapsed_s"]} for r in reps[0]]
                              if reps else []),
            "note": (
                "N-independent. Distribution across convs should reflect "
                "different conversation lengths. Constant distribution = cache artifact."
            ),
        }

    # TTFT summary (should be flat across N)
    ttft_agg = {}
    for N in N_VALUES:
        r1 = [r for r in ttft_reps[0] if r.get("N") == N] if ttft_reps else []
        r2 = [r for r in ttft_reps[1] if r.get("N") == N] if len(ttft_reps) > 1 else []
        ttft_agg[str(N)] = {
            "N": N,
            "median_s_rep1": round(_med([r["elapsed_s"] for r in r1]), 4) if r1 else None,
            "median_s_rep2": round(_med([r["elapsed_s"] for r in r2]), 4) if r2 else None,
        }

    out = {
        "description": (
            "sum200 catch-up: TTFT (N-independent, verify ~37ms), "
            "recursive generation (decode-dominated, varies slightly with N), "
            "full regen (N-independent, per-conv distribution expected — "
            "constant distribution = E32 artifact, not valid)."
        ),
        "ttft_summary_by_N":       ttft_agg,
        "recursive_summary_by_N":  _agg_by_N(recursive_reps),
        "fullregen_summary":       _agg_flat(fullregen_reps),
        "raw_ttft_reps":       ttft_reps,
        "raw_recursive_reps":  recursive_reps,
        "raw_fullregen_reps":  fullregen_reps,
    }
    _save(OUT_DIR / "part2_sum200.json", out)
    return out


# ── Part 3: Corrected maintenance ordering (CPU) ─────────────────────────────

def part3_maintenance(part1_summary, part2_out):
    """
    Corrected maintenance cost ordering.

    Key correction vs E34 Part C:
      Full maintenance cost = warm tail-append (~66ms, E26), NOT cold re-prefill.
      The cold re-prefill cost (3,620ms) only applies when the KV cache is fully
      evicted — not the normal per-turn maintenance path for full fidelity.

    Win10 amortized = slide_frac × slide_cold + grow_frac × grow_warm
      slide_cold from E34 Part A (0.975s median, committed).
      grow_warm from E34 Part A (36ms, committed).
    """
    # Pull win10 costs from E34 Part A json if available; fall back to committed constants
    slide_cold_ms = E34_SLIDE_COLD_MS
    grow_warm_ms  = E34_GROW_WARM_MS
    if E34_A_WIN10_JSON.exists():
        a = json.loads(E34_A_WIN10_JSON.read_text())
        sc_vals, gw_vals = [], []
        for case in a:
            sl = case.get("win10_slide", {}).get("cold", {})
            gr = case.get("win10_growth", {}).get("warm", {})
            if sl.get("feasible") and sl.get("median_s"):
                sc_vals.append(sl["median_s"] * 1000)
            if gr.get("feasible") and gr.get("median_s"):
                gw_vals.append(gr["median_s"] * 1000)
        if sc_vals:
            slide_cold_ms = round(_med(sc_vals), 1)
        if gw_vals:
            grow_warm_ms = round(_med(gw_vals), 1)

    win10_amortized_ms = (E34_SLIDE_FRAC * slide_cold_ms +
                          (1.0 - E34_SLIDE_FRAC) * grow_warm_ms)

    # Full warm catch-up from Part 1 N=1 measurements (the one-turn case)
    full_N1 = part1_summary.get("full", {}).get("1", {})
    full_warmcatchup_ms = (
        round(full_N1["median_elapsed_rep1_s"] * 1000, 1)
        if full_N1.get("median_elapsed_rep1_s") else None
    )

    # sum200 recursive from Part 2 (median across N, rep1)
    rec_vals = []
    rec_summary = part2_out.get("recursive_summary_by_N", {})
    for N_str, v in rec_summary.items():
        if v.get("median_s_rep1"):
            rec_vals.append(v["median_s_rep1"] * 1000)
    sum200_recursive_ms = round(_med(rec_vals), 0) if rec_vals else SUM200_UPDATE_MS

    # Full regen from Part 2C (for reference; this is N-independent)
    fr = part2_out.get("fullregen_summary", {})
    fullregen_ms = (fr.get("median_s_rep1", 0) or 0) * 1000

    maintenance = {
        "description": (
            "Corrected maintenance cost ordering. "
            "Key fix: full maintenance = warm tail-append (E26: 66ms), "
            "not cold re-prefill (E34 COLD: 3,620ms)."
        ),
        "full_warm_append_ms": E26_WARM_APPEND_MS,
        "full_warm_append_budget": _budget(E26_WARM_APPEND_MS),
        "full_warm_catchup_N1_ms": full_warmcatchup_ms,
        "note_full_vs_E34": (
            "E34 Part C listed 'full COLD re-prefill 3,620ms' as full's maintenance cost. "
            "Corrected: full maintenance is warm tail-append (66ms, E26) because "
            "the KV cache prefix is preserved between consecutive turns. "
            "Cold re-prefill applies only on GPU eviction (not the normal maintenance path)."
        ),
        "win10_grow_warm_ms": round(grow_warm_ms, 1),
        "win10_slide_cold_ms": round(slide_cold_ms, 1),
        "win10_slide_frac": E34_SLIDE_FRAC,
        "win10_amortized_ms": round(win10_amortized_ms, 1),
        "win10_amortized_budget": _budget(win10_amortized_ms),
        "sum200_restore_ms": SUM200_RESTORE_MS,
        "sum200_restore_budget": _budget(SUM200_RESTORE_MS),
        "sum200_recursive_ms": sum200_recursive_ms,
        "sum200_recursive_budget": _budget(sum200_recursive_ms),
        "sum200_fullregen_ms": round(fullregen_ms, 0) if fullregen_ms else None,
        "ordering_ascending_cost": [
            f"sum200 restore ({SUM200_RESTORE_MS:.0f} ms) — serves query from stale summary",
            f"full warm-append ({E26_WARM_APPEND_MS:.0f} ms, E26) — normal per-turn cost, voice budget",
            f"win10 amortized ({win10_amortized_ms:.0f} ms) — blended grow+slide, interactive budget",
            f"sum200 recursive (~{sum200_recursive_ms:.0f} ms) — generate new summary, background only",
        ],
        "cost_matrix_restore_reference": "results/cost/cost_matrix.csv (E21/E26, sum200 restore=32ms at L=8k)",
        "e26_warm_append_reference": "reports/phase1_cost_profiling.md (E26, warm-append=66ms at L=8k)",
        "e34_slide_cold_reference": "results/cost/e34_maintenance_semantics/part_a_win10.json (E34 Part A)",
    }

    _save(OUT_DIR / "part3_maintenance.json", maintenance)
    return maintenance


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("E35 (E34b) — Corrected WARM catch-up latency and maintenance ordering", flush=True)
    print(f"Model:  {MODEL_ID}", flush=True)
    print(f"Device: {DEVICE_SLUG} (A6000, GPU 1)", flush=True)
    print(f"N_REPS: {N_REPS} engine loads per (fidelity, N) cell", flush=True)
    print(f"Output: {OUT_DIR.relative_to(ROOT)}", flush=True)
    print("", flush=True)

    tok   = get_tok()
    convs = load_convs()
    print(f"Loaded {len(convs)} conversations", flush=True)

    # Verify win10 token counts match canonical definition (last 10 sessions)
    print("\nWin10 token counts (verify = last 10 sessions):", flush=True)
    for c in convs:
        w_tok = ntok(tok, build_current(c, "win10"))
        f_tok = ntok(tok, build_current(c, "full"))
        print(f"  {c['conv_id']}: sessions={len(c['sessions'])} "
              f"win10_tok={w_tok} full_tok={f_tok}", flush=True)

    # Load sum200 cache
    sum200_cache = {}
    if SUM200_CACHE.exists():
        sum200_cache = json.loads(SUM200_CACHE.read_text())
        print(f"\nLoaded sum200 cache: {len(sum200_cache)} entries", flush=True)
    else:
        print("\nWARNING: sum200 cache not found; sum200 results will be empty", flush=True)

    # Part 1
    print("\n" + "="*60, flush=True)
    print("PART 1: Corrected WARM catch-up (full and win10)", flush=True)
    print("="*60, flush=True)
    part1_summary = part1_warm_catchup(convs, tok)

    # Part 2
    print("\n" + "="*60, flush=True)
    print("PART 2: sum200 catch-up (TTFT + generation)", flush=True)
    print("="*60, flush=True)
    part2_out = part2_sum200(convs, tok, sum200_cache)

    # Part 3
    print("\n" + "="*60, flush=True)
    print("PART 3: Corrected maintenance cost ordering", flush=True)
    print("="*60, flush=True)
    part3_out = part3_maintenance(part1_summary, part2_out)

    print("\n=== E35 DONE ===", flush=True)
    print(f"  {OUT_DIR / 'part1_warm_catchup.json'}", flush=True)
    print(f"  {OUT_DIR / 'part2_sum200.json'}", flush=True)
    print(f"  {OUT_DIR / 'part3_maintenance.json'}", flush=True)

    # Print quick summary
    print("\n--- Part 1 quick summary (median elapsed per N) ---", flush=True)
    for fidelity in FIDELITIES:
        for N in N_VALUES:
            cell = part1_summary.get(fidelity, {}).get(str(N), {})
            r1 = cell.get("median_elapsed_rep1_s")
            r2 = cell.get("median_elapsed_rep2_s")
            dtok = cell.get("delta_tokens_median")
            print(f"  {fidelity} N={N}: rep1={r1}s rep2={r2}s delta_tok={dtok}", flush=True)

    print("\n--- Part 3 maintenance ordering ---", flush=True)
    for line in part3_out.get("ordering_ascending_cost", []):
        print(f"  {line}", flush=True)


if __name__ == "__main__":
    main()
