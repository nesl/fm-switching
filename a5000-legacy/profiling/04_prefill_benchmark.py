"""
04_prefill_benchmark.py — Measure re-prefill cost as a function of context depth

THIS IS THE KEY MEASUREMENT FOR YOUR PROJECT.

It answers: "If a session has accumulated N tokens of context,
how long does it take to re-create that context on a (potentially different) device?"

This cost IS the context inertia. The curve of prefill_time vs context_depth
is what makes migration cost dynamic and time-varying.

Method:
  1. Build a conversation to target depth (accumulate tokens in Python — never sent
     turn-by-turn, so vLLM has no cached prefix to reuse)
  2. Send the FULL conversation as a single streaming request with max_tokens=1
  3. Measure Time to First Token (TTFT) using streaming — timestamp the instant
     the first token chunk arrives from the server. This isolates prefill time
     from decode time and HTTP overhead.
  4. Repeat at multiple context depths

WHY STREAMING FOR TTFT:
  Using requests.post() without streaming wraps the entire HTTP round-trip including
  JSON serialization, 1-token decode, and response deserialization. Streaming lets us
  timestamp the first SSE chunk, which arrives immediately after prefill completes
  (before the response JSON is finalized). This gives true prefill-only timing.

WHY PREFIX CACHING MUST BE OFF:
  Run 01_start_server.py WITHOUT --enable-prefix-caching (the default).
  If prefix caching is on, repeat requests at the same depth hit the KV cache
  and measure near-zero "prefill" time — not the cold re-prefill cost of migration.

Usage:
    python 04_prefill_benchmark.py [--depths 512,1024,2048,4096,8192,16384]
"""

import requests
import time
import csv
import os
import json
import argparse
from datetime import datetime


def detect_model_name(server_url: str) -> str:
    """Query vLLM server to find the loaded model name."""
    try:
        resp = requests.get(f"{server_url}/v1/models", timeout=5)
        if resp.status_code == 200:
            return resp.json()["data"][0]["id"]
    except Exception:
        pass
    return None


def build_conversation_to_depth(target_tokens: int, token_budget: int = None) -> list:
    """Build a synthetic multi-turn conversation reaching approximately target_tokens.

    Uses a mix of long technical prompts and synthetic assistant responses to
    simulate a realistic accumulated context. The conversation is built entirely
    in Python memory — it is never sent turn-by-turn to the server, so vLLM
    cannot reuse any prefix cache across benchmark runs.

    NOTE: Assistant responses are synthetic (repeated text). The token count is
    calibrated correctly, but the KV cache activation pattern will be more uniform
    than a real conversation. This is a known limitation — complement with real
    session traces from 03_workload_generator.py for final paper figures.

    The len//4 estimator undercounts actual BPE tokens by ~5-10%. Pass token_budget
    to hard-cap construction so the real token count never exceeds max_model_len.
    The cap is applied at token_budget / OVERCOUNT_GUARD where OVERCOUNT_GUARD=1.12
    gives a ~12% safety margin against the estimator's undercount.

    Args:
        target_tokens: Approximate total token count to reach.
        token_budget: Hard upper bound on estimated tokens (use max_model_len - 50).
                      If None, no cap is applied.

    Returns:
        List of message dicts in OpenAI chat format.
    """
    OVERCOUNT_GUARD = 1.12  # estimator undercount safety factor
    effective_target = target_tokens
    if token_budget is not None:
        safe_estimate_cap = int(token_budget / OVERCOUNT_GUARD)
        effective_target = min(target_tokens, safe_estimate_cap)
    messages = [
        {"role": "system", "content": "You are a helpful assistant engaged in a detailed technical discussion."}
    ]

    filler_topics = [
        "Explain the architecture of a modern GPU, including the streaming multiprocessors, memory hierarchy, and how thread scheduling works. Be very detailed.",
        "Describe the complete process of training a large language model, from data collection through tokenization, pretraining, fine-tuning, and RLHF. Include specific details about optimizer choices and learning rate schedules.",
        "Walk me through the Linux kernel's memory management subsystem, including virtual memory, page tables, the slab allocator, and how memory-mapped I/O works.",
        "Explain TCP/IP networking from the physical layer up through the application layer, including details about congestion control algorithms and how TLS handshakes work.",
        "Describe the design and implementation of a distributed database system, covering consensus protocols, sharding strategies, replication, and how transactions work across partitions.",
        "Explain how modern compilers work, from lexical analysis through parsing, semantic analysis, optimization passes, and code generation. Include details about SSA form and register allocation.",
        "Describe the mathematics behind transformer attention mechanisms, including scaled dot-product attention, multi-head attention, positional encodings, and why attention is all you need.",
        "Walk me through the design of a real-time operating system, including scheduling algorithms, interrupt handling, priority inversion solutions, and memory protection.",
    ]

    current_tokens = 10  # system prompt
    turn_idx = 0

    while current_tokens < effective_target:
        topic = filler_topics[turn_idx % len(filler_topics)]

        if turn_idx > 0:
            topic = f"Continuing our discussion, elaborate further on the previous point. Also, {topic}"

        messages.append({"role": "user", "content": topic})
        current_tokens += len(topic) // 4

        # Synthetic assistant response simulating accumulated conversation history.
        # This is what would exist in the KV cache from prior turns on the source device.
        assistant_response = f"This is a detailed response to turn {turn_idx + 1}. " * 50

        response_tokens_needed = min(
            (target_tokens - current_tokens) // 2,
            500
        )
        if response_tokens_needed > 0:
            assistant_response = assistant_response[:response_tokens_needed * 4]
            messages.append({"role": "assistant", "content": assistant_response})
            current_tokens += response_tokens_needed

        turn_idx += 1

        if turn_idx > 100:
            break

    return messages


def measure_prefill_time(server_url: str, model_name: str, messages: list,
                         max_new_tokens: int = 1) -> dict:
    """Measure true prefill time (TTFT) using streaming mode.

    Opens a streaming SSE connection and timestamps the instant the first token
    chunk arrives. This is Time to First Token (TTFT), which equals prefill time
    because the server sends the first chunk immediately after the prefill pass
    completes — before decoding the next token.

    Requesting max_tokens=1 means only one decode step occurs, so total time is
    effectively prefill + epsilon. We still measure TTFT rather than total time
    to exclude even that epsilon, plus HTTP response finalization.

    Args:
        server_url: Base URL of vLLM server (e.g. "http://localhost:8000").
        model_name: Model ID as returned by /v1/models.
        messages: Full conversation in OpenAI chat format.
        max_new_tokens: Tokens to generate (keep at 1 to minimize decode time).

    Returns:
        Dict with keys: success, prefill_time_s, total_time_s, prompt_tokens,
        completion_tokens. On failure: success=False, error=str.
    """
    t_start = time.perf_counter()
    t_first_token = None
    t_end = None

    prompt_tokens = -1
    completion_tokens = 0

    try:
        response = requests.post(
            f"{server_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": messages,
                "max_tokens": max_new_tokens,
                "temperature": 0.0,
                "stream": True,
                # Ask vLLM to include token usage in the final streaming chunk.
                # Without this, usage stats are omitted from streaming responses.
                "stream_options": {"include_usage": True},
            },
            stream=True,
            timeout=300,
        )

        if response.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}",
            }

        for raw_line in response.iter_lines():
            if not raw_line:
                continue

            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

            if line == "data: [DONE]":
                break

            if not line.startswith("data: "):
                continue

            # Record TTFT on the FIRST content chunk — this is when prefill finished.
            if t_first_token is None:
                t_first_token = time.perf_counter()

            t_end = time.perf_counter()

            try:
                chunk = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            # Usage arrives in the final chunk (enabled by stream_options above)
            if chunk.get("usage"):
                usage = chunk["usage"]
                prompt_tokens = usage.get("prompt_tokens", -1)
                completion_tokens = usage.get("completion_tokens", 0)

        if t_first_token is None:
            return {"success": False, "error": "No tokens received in stream"}

        return {
            "success": True,
            # TRUE prefill time: from request sent to first token received
            "prefill_time_s": round(t_first_token - t_start, 4),
            # Total time including 1-token decode + response close
            "total_time_s": round(t_end - t_start, 4),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", type=str, default="http://localhost:8000")
    parser.add_argument("--depths", type=str, default="256,512,1024,2048,4096,8192,12288,16000",
                        help="Comma-separated target context depths in tokens")
    parser.add_argument("--max-model-len", type=int, default=16384,
                        help="Server's max_model_len. Used to cap conversation construction "
                             "so requests never exceed context limit. (default: 16384)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="Number of measurements per depth (for statistical robustness)")
    parser.add_argument("--output", type=str, default="logs/prefill_cost_curve.csv")
    parser.add_argument("--warmup", action="store_true", default=True,
                        help="Run a warmup request first")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    depths = [int(d.strip()) for d in args.depths.split(",")]

    model_name = detect_model_name(args.server_url)
    if model_name is None:
        print(f"ERROR: Cannot reach vLLM server at {args.server_url}")
        return
    print(f"Model: {model_name}")
    token_budget = args.max_model_len - 50  # leave room for 1 output token + safety margin
    print(f"Measuring prefill cost at depths: {depths}")
    print(f"Repeats per depth: {args.repeats}")
    print(f"Max model len: {args.max_model_len} (token budget cap: {token_budget})")
    print(f"Timing method: streaming TTFT (time from request to first token chunk)\n")

    # Warmup — loads model weights into GPU L2 cache, stabilizes CUDA context
    if args.warmup:
        print("Warmup request...")
        warmup_msgs = [
            {"role": "system", "content": "Hi"},
            {"role": "user", "content": "Hello"},
        ]
        result = measure_prefill_time(args.server_url, model_name, warmup_msgs)
        if result["success"]:
            print(f"  Warmup TTFT: {result['prefill_time_s']*1000:.1f}ms\n")
        else:
            print(f"  Warmup failed: {result.get('error')} — continuing anyway\n")
        time.sleep(1)

    results = []

    for depth in depths:
        print(f"\n--- Context depth: {depth} tokens ---")

        messages = build_conversation_to_depth(depth, token_budget=token_budget)
        estimated_tokens = sum(len(m["content"]) // 4 for m in messages)
        print(f"  Built conversation: {len(messages)} messages, ~{estimated_tokens} estimated tokens")

        for rep in range(args.repeats):
            time.sleep(0.5)  # let GPU thermal/memory state stabilize

            result = measure_prefill_time(args.server_url, model_name, messages)

            if result["success"]:
                actual_tokens = result["prompt_tokens"]
                prefill_ms = result["prefill_time_s"] * 1000
                total_ms = result["total_time_s"] * 1000
                tokens_per_sec = actual_tokens / result["prefill_time_s"] if result["prefill_time_s"] > 0 else 0
                ms_per_token = prefill_ms / actual_tokens if actual_tokens > 0 else 0

                row = {
                    "timestamp": datetime.now().isoformat(),
                    "target_depth": depth,
                    "actual_prompt_tokens": actual_tokens,
                    "prefill_time_ms": round(prefill_ms, 2),
                    "total_time_ms": round(total_ms, 2),
                    "ms_per_token": round(ms_per_token, 4),
                    "tokens_per_second": round(tokens_per_sec, 1),
                    "repeat": rep + 1,
                    "num_messages": len(messages),
                }
                results.append(row)

                print(f"  Rep {rep+1}: {actual_tokens:5d} tokens → TTFT {prefill_ms:8.1f}ms "
                      f"({ms_per_token:.3f} ms/tok, {tokens_per_sec:.0f} tok/s)")
            else:
                print(f"  Rep {rep+1}: FAILED — {result.get('error', 'unknown')}")

    # Save results
    if results:
        fieldnames = results[0].keys()
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\n\nSaved {len(results)} measurements → {args.output}")

        # Summary table
        print("\n=== CONTEXT INERTIA CURVE (averaged over repeats) ===")
        print(f"{'Depth':>8s} | {'TTFT (ms)':>10s} | {'ms/token':>10s} | {'tok/s':>8s}")
        print("-" * 50)

        from collections import defaultdict
        by_depth = defaultdict(list)
        for r in results:
            by_depth[r["target_depth"]].append(r)

        for depth in sorted(by_depth.keys()):
            rows = by_depth[depth]
            avg_ms = sum(r["prefill_time_ms"] for r in rows) / len(rows)
            avg_ms_tok = sum(r["ms_per_token"] for r in rows) / len(rows)
            avg_tps = sum(r["tokens_per_second"] for r in rows) / len(rows)
            actual = rows[0]["actual_prompt_tokens"]
            print(f"{actual:>8d} | {avg_ms:>10.1f} | {avg_ms_tok:>10.3f} | {avg_tps:>8.0f}")

        print("\nThis curve is your CONTEXT INERTIA characterization.")
        print("It shows how migration cost (cold re-prefill) grows with session depth.")
    else:
        print("\nNo successful measurements. Check server status.")


if __name__ == "__main__":
    main()
