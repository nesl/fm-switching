"""
StudyM smoke test — Reasoning gate on SenTSR-Bench.

Arms:
  T-OFF  Qwen3-8B  enable_thinking=False  temp=0.7 top_p=0.8  top_k=20 min_p=0
  T-ON   Qwen3-8B  enable_thinking=True   temp=0.6 top_p=0.95 top_k=20 min_p=0

30 of 110 SenTSR-Bench series (seed=42), 3 stages each = 90 items.
3 seeds per item per arm = 540 trials total.

Pre-registered in research/EXPERIMENTS.md row StudyM.
Writes: results/ts/study_m_smoke/study_m_smoke_trials.jsonl
"""
import sys, json, os, time, re, argparse
import numpy as np
import torch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from _provenance import stamp
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH   = "/mnt/ssd/hf_models/models--Qwen--Qwen3-8B"
MODEL_SNAP   = "b968826d9c46dd6066d109eabc6255188de91218"
HF_CACHE     = "/mnt/ssd/hf_models"
DEVICE       = "cuda:1"
TRIALS_PATH  = "results/ts/study_m_smoke/study_m_smoke_trials.jsonl"

SEEDS         = [42, 123, 456]
SERIES_INDICES = [7,8,12,17,18,36,37,43,45,47,48,49,50,54,59,
                  61,63,68,71,73,75,82,83,84,86,88,89,94,96,105]

# Decoding from Qwen3-8B model card verbatim
GEN_T_OFF = dict(do_sample=True, temperature=0.7, top_p=0.8,  top_k=20, min_p=0.0, max_new_tokens=1024)
GEN_T_ON  = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, max_new_tokens=16384)

RUNTIME_STOP_HOURS = 12.0

PROMPT_TEMPLATE = """\
You are a sensor time series analysis expert for industrial warehouse monitoring.

The following multivariate time series records sensor readings over time:

{series_text}

Question: {question}

Options:
A. {opt_a}
B. {opt_b}
C. {opt_c}
D. {opt_d}

Answer with a single letter (A, B, C, or D) on its own line.\
"""


def serialize_series(timeseries, cols):
    lines = []
    for ch_idx, ch_name in enumerate(cols):
        vals = ", ".join(f"{v:.4f}" for v in timeseries[ch_idx])
        lines.append(f"{ch_name}: {vals}")
    return "\n".join(lines)


def build_prompt(entry):
    series_text = serialize_series(entry["timeseries"], entry["cols"])
    opts = entry["options"]
    return PROMPT_TEMPLATE.format(
        series_text=series_text,
        question=entry["question"],
        opt_a=opts[0], opt_b=opts[1], opt_c=opts[2], opt_d=opts[3],
    )


def parse_answer(text):
    """Extract A/B/C/D from model output."""
    clean = text.strip()
    m = re.search(r'\b([A-D])\b', clean)
    if m:
        return m.group(1), "ok"
    return None, "parse_failed"


def count_tokens(tokenizer, text):
    return len(tokenizer.encode(text, add_special_tokens=False))


def already_done(path):
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    t = json.loads(line)
                    done.add((t["series_idx"], t["entry_idx"], t["arm"], t["seed"]))
                except Exception:
                    pass
    return done


def run_arm(model, tokenizer, prompt_text, gen_kwargs, seed, enable_thinking):
    torch.manual_seed(seed)
    # Apply chat template — enable_thinking controls <think> injection
    messages = [{"role": "user", "content": prompt_text}]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    input_ids = tokenizer([text], return_tensors="pt").input_ids.to(DEVICE)
    n_input = input_ids.shape[1]

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(input_ids, **gen_kwargs)
    lat_ms = (time.time() - t0) * 1000

    generated = output_ids[0][n_input:]
    full_output = tokenizer.decode(generated, skip_special_tokens=False)

    budget_hit = (len(generated) >= gen_kwargs["max_new_tokens"])

    if "</think>" in full_output:
        think_part, answer_part = full_output.split("</think>", 1)
        think_content = think_part.replace("<think>", "").strip()
        answer_text   = answer_part.strip()
        think_closed  = True
    elif "<think>" in full_output:
        # thinking started but never closed (budget hit mid-think)
        think_content = full_output.replace("<think>", "").strip()
        answer_text   = ""
        think_closed  = False
    else:
        # no think block at all — T-OFF mode; full output is the answer
        think_content = ""
        answer_text   = full_output.strip()
        think_closed  = False

    # strip EOS/pad special tokens that the tokenizer appends at sequence end
    for _tok in ("<|im_end|>", "<|im_start|>", "<|endoftext|>"):
        answer_text   = answer_text.replace(_tok, "")
        think_content = think_content.replace(_tok, "")
    answer_text   = answer_text.strip()
    think_content = think_content.strip()

    n_think  = count_tokens(tokenizer, think_content) if think_content else 0
    n_answer = count_tokens(tokenizer, answer_text)   if answer_text   else 0

    parsed_answer, parse_status = parse_answer(answer_text)

    return {
        "n_input_tokens":  n_input,
        "n_think_tokens":  n_think,
        "n_answer_tokens": n_answer,
        "n_generated_tokens": len(generated),
        "think_closed":    think_closed,
        "budget_hit":      budget_hit,
        "parsed_answer":   parsed_answer,
        "parse_status":    parse_status,
        "total_latency_ms": lat_ms,
        "raw_output":      full_output,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--arm", choices=["T-OFF", "T-ON"], default=None,
                        help="Run only one arm (default: both)")
    args = parser.parse_args()

    # Verify series selection
    rng = np.random.default_rng(seed=42)
    check = sorted(rng.choice(110, size=30, replace=False).tolist())
    assert check == SERIES_INDICES, f"Series index mismatch: {check}"

    ds = load_dataset("ZLHe0/SenTSR-Bench", split="test", cache_dir=HF_CACHE)
    assert len(ds) == 330, f"Expected 330 entries, got {len(ds)}"

    arms_to_run = ["T-OFF", "T-ON"] if args.arm is None else [args.arm]

    # Build planned runs
    runs = []
    for series_idx in SERIES_INDICES:
        for stage_offset, stage_name in enumerate(["what_happened", "how_happened", "suggested_fix"]):
            entry_idx = series_idx * 3 + stage_offset
            entry     = ds[entry_idx]
            assert entry["question_type"] == stage_name, (
                f"stage mismatch at entry {entry_idx}: expected {stage_name}, got {entry['question_type']}")
            for arm in arms_to_run:
                for seed in SEEDS:
                    runs.append({
                        "series_idx": series_idx,
                        "entry_idx":  entry_idx,
                        "stage":      stage_name,
                        "arm":        arm,
                        "seed":       seed,
                        "entry":      entry,
                    })

    print(f"Planned: {len(runs)} trials  (series={len(SERIES_INDICES)}, arms={arms_to_run}, seeds={SEEDS})")

    if args.dry_run:
        print("--dry-run: exiting.")
        return

    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)
    done = already_done(TRIALS_PATH)
    pending = [r for r in runs if (r["series_idx"], r["entry_idx"], r["arm"], r["seed"]) not in done]
    print(f"Already done: {len(done)}  Pending: {len(pending)}")

    if not pending:
        print("All trials complete.")
        return

    # Runtime projection before loading model
    # T-ON budget is 16384 tokens; rough estimate 3–12h for 540 trials
    # (checked against plan §9 stop condition)

    print(f"Loading model from {MODEL_PATH} ...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model     = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    print("Model loaded.", flush=True)

    lat_history = []
    trial_idx   = 0
    t_wall_start = time.time()

    with open(TRIALS_PATH, "a") as out_f:
        for run in pending:
            key = (run["series_idx"], run["entry_idx"], run["arm"], run["seed"])
            if key in done:
                continue

            enable_thinking = (run["arm"] == "T-ON")
            gen_kwargs = GEN_T_ON if enable_thinking else GEN_T_OFF
            prompt_text = build_prompt(run["entry"])
            correct_letter = chr(ord("A") + run["entry"]["correct_index"])

            try:
                result = run_arm(model, tokenizer, prompt_text, gen_kwargs,
                                 run["seed"], enable_thinking)
                correct = (result["parsed_answer"] == correct_letter)

                trial = {
                    "series_idx":      run["series_idx"],
                    "entry_idx":       run["entry_idx"],
                    "stage":           run["stage"],
                    "arm":             run["arm"],
                    "seed":            run["seed"],
                    "correct_letter":  correct_letter,
                    "n_input_tokens":  result["n_input_tokens"],
                    "n_think_tokens":  result["n_think_tokens"],
                    "n_answer_tokens": result["n_answer_tokens"],
                    "n_generated_tokens": result["n_generated_tokens"],
                    "think_closed":    result["think_closed"],
                    "budget_hit":      result["budget_hit"],
                    "parsed_answer":   result["parsed_answer"],
                    "parse_status":    result["parse_status"],
                    "correct":         correct,
                    "total_latency_ms": result["total_latency_ms"],
                    "raw_output":      result["raw_output"],
                    "model_snapshot":  MODEL_SNAP,
                }
                out_f.write(json.dumps(trial) + "\n")
                out_f.flush()
                done.add(key)
                lat_history.append(result["total_latency_ms"])
                trial_idx += 1

                think_info = (f"think={result['n_think_tokens']}tok"
                              if enable_thinking else "no-think")
                print(
                    f"[{trial_idx:4d}] s{run['series_idx']:3d} {run['stage'][:12]:12s} "
                    f"{run['arm']} seed={run['seed']}  "
                    f"{'OK' if result['parse_status']=='ok' else 'FAIL'}  "
                    f"{'✓' if correct else '✗'}  {think_info}  "
                    f"bgt={'Y' if result['budget_hit'] else 'N'}  "
                    f"lat={result['total_latency_ms']/1000:.1f}s",
                    flush=True,
                )

                # Runtime projection after 10 trials
                if len(lat_history) == 10:
                    mean_ms   = sum(lat_history) / len(lat_history)
                    remaining = len(pending) - trial_idx
                    proj_h    = (mean_ms * remaining) / 3_600_000
                    print(f"\n=== RUNTIME PROJECTION (after 10 trials) ===")
                    print(f"Mean lat: {mean_ms/1000:.1f}s  Remaining: {remaining}  Projected: {proj_h:.1f}h")
                    if proj_h > RUNTIME_STOP_HOURS:
                        print(f"STOP: projection {proj_h:.1f}h > {RUNTIME_STOP_HOURS}h threshold.")
                        print("Halting as required by study_m_plan.md §10.")
                        break
                    else:
                        print(f"Within {RUNTIME_STOP_HOURS}h. Continuing.")
                    print("=============================================\n", flush=True)

            except Exception as e:
                trial = {
                    "series_idx": run["series_idx"],
                    "entry_idx":  run["entry_idx"],
                    "stage":      run["stage"],
                    "arm":        run["arm"],
                    "seed":       run["seed"],
                    "error":      str(e),
                    "model_snapshot": MODEL_SNAP,
                }
                out_f.write(json.dumps(trial) + "\n")
                out_f.flush()
                print(f"[{trial_idx:4d}] ERROR s{run['series_idx']} {run['arm']} seed={run['seed']}: {e}", flush=True)

    wall_h = (time.time() - t_wall_start) / 3600
    total  = sum(1 for _ in open(TRIALS_PATH))
    print(f"\nDone. {total} trials in {TRIALS_PATH}  wall={wall_h:.2f}h")

    # Write provenance into a sidecar file
    prov = stamp(script="study_m_smoke.py", model="qwen3-8b",
                 device="a6000", n=total, args=args)
    prov_path = TRIALS_PATH.replace(".jsonl", "_provenance.json")
    with open(prov_path, "w") as f:
        json.dump(prov, f, indent=2)
    print(f"Provenance: {prov_path}")


if __name__ == "__main__":
    main()
