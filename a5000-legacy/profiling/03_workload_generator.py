"""
03_workload_generator.py — Multi-session workload generator with KV cache tracking

Spawns concurrent "sessions" (multi-turn conversations) against the vLLM server.
Each session accumulates context over time (growing KV cache).
Logs per-session context depth, latency, and token counts.

This simulates what happens in real FM serving: multiple users with
conversations of different lengths running simultaneously.

NOTE ON LATENCY INTERPRETATION:
The latency values logged here reflect INCREMENTAL prefill — vLLM's prefix caching
reuses KV blocks from prior turns, so only newly added tokens are recomputed each turn.
This is NOT the same as cold re-prefill cost (migration cost). To measure migration cost
(context inertia), use 04_prefill_benchmark.py, which submits the full conversation as
a fresh request to a server started with prefix caching disabled.

Usage:
    python 03_workload_generator.py [--sessions 4] [--turns-per-session 20]
"""

import requests
import time
import csv
import os
import json
import argparse
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


# --- Conversation templates to generate diverse sessions ---
# Each session gets a different "persona" that naturally produces varied context growth

SESSION_PROMPTS = [
    {
        "name": "code_review",
        "system": "You are a senior software engineer doing code review.",
        "turns": [
            "Write a Python class for a binary search tree with insert, search, and delete methods.",
            "Now add an in-order traversal method that returns a sorted list.",
            "Add a method to find the kth smallest element.",
            "Write unit tests for all the methods you've implemented.",
            "Now refactor the delete method to handle all three cases more cleanly.",
            "Add a method to check if the tree is balanced.",
            "Implement a serialize and deserialize method for the BST.",
            "Add type hints and docstrings to every method.",
            "Write a performance comparison between your BST and Python's built-in sorted containers.",
            "Summarize all the code you've written in this conversation.",
            "Now extend the BST to support duplicate keys with a count field.",
            "Add a range query method that returns all values between low and high.",
            "Implement a method to find the lowest common ancestor of two nodes.",
            "Write integration tests that combine multiple operations.",
            "Do a final review of all the code and suggest improvements.",
            "Write comprehensive documentation for the entire module.",
            "Create a README with usage examples.",
            "Add error handling for edge cases.",
            "Profile the code and suggest optimizations.",
            "Write a changelog summarizing all changes made in this session.",
        ],
    },
    {
        "name": "research_analysis",
        "system": "You are a research analyst helping with literature review.",
        "turns": [
            "Explain the key differences between transformers and state space models for sequence modeling.",
            "What are the main advantages of Mamba over S4?",
            "How does PagedAttention in vLLM work?",
            "Compare KV cache management strategies across different serving frameworks.",
            "What is the relationship between context length and inference latency?",
            "Explain model parallelism vs pipeline parallelism for LLM serving.",
            "What are the key papers on dynamic model switching for edge inference?",
            "Summarize the EdgeFM approach and its limitations.",
            "How do MPC and RL compare for real-time control problems?",
            "What metrics matter most for evaluating inference serving systems?",
            "Explain the concept of break-even horizon in model migration.",
            "What are the challenges of KV cache migration across devices?",
            "Compare approaches to LLM inference on edge devices.",
            "What is speculative decoding and how does it relate to serving efficiency?",
            "Summarize all the topics we've discussed and identify research gaps.",
            "Draft an abstract for a paper on context-aware model migration.",
            "List the key experiments needed to validate this approach.",
            "What baselines should we compare against?",
            "Suggest a timeline for implementing a prototype.",
            "Write related work section covering these topics.",
        ],
    },
    {
        "name": "data_pipeline",
        "system": "You are a data engineer helping design ETL pipelines.",
        "turns": [
            "Design a real-time data pipeline for processing IoT sensor data at 100Hz.",
            "Add a windowing mechanism that aggregates data over 1-second windows.",
            "How should we handle late-arriving data in this pipeline?",
            "Add anomaly detection to flag unusual sensor readings.",
            "Design the storage schema for the processed data.",
            "Add a monitoring dashboard specification for pipeline health.",
            "How do we scale this to handle 1000 sensors?",
            "Add data quality checks at each stage.",
            "Design a replay mechanism for reprocessing historical data.",
            "Write the Apache Kafka topic configuration for this pipeline.",
            "Add a dead letter queue for failed records.",
            "Design the alerting rules for pipeline failures.",
            "How do we handle schema evolution in the sensor data?",
            "Add data lineage tracking.",
            "Write deployment configuration for Kubernetes.",
            "Design the backup and recovery strategy.",
            "Add performance benchmarks.",
            "Write runbook for common failure scenarios.",
            "Design A/B testing capability for pipeline changes.",
            "Create comprehensive documentation.",
        ],
    },
    {
        "name": "short_qa",
        "system": "You are a helpful assistant. Keep answers brief.",
        "turns": [
            "What is gradient descent?",
            "What's the difference between L1 and L2 regularization?",
            "Explain batch normalization in one paragraph.",
            "What is dropout?",
            "Define overfitting.",
            "What is a learning rate schedule?",
            "Explain cross-entropy loss.",
            "What is an activation function?",
            "Define backpropagation.",
            "What is transfer learning?",
        ],
    },
]


class Session:
    """Represents one multi-turn conversation with the LLM."""

    def __init__(self, session_id: int, config: dict, server_url: str, model_name: str):
        self.session_id = session_id
        self.name = config["name"]
        self.system_prompt = config["system"]
        self.turns = config["turns"]
        self.server_url = server_url
        self.model_name = model_name

        # Conversation history (this is what builds the KV cache)
        self.messages = [{"role": "system", "content": self.system_prompt}]

        # Tracking
        self.context_tokens = 0  # approximate total tokens in conversation
        self.turn_count = 0
        self.log_rows = []

    def estimate_tokens(self, text: str) -> int:
        """Rough token count estimate (1 token ≈ 4 chars for English)."""
        return len(text) // 4

    def run_turn(self, turn_index: int) -> dict:
        """Send one turn of conversation and record metrics.

        NOTE: The latency recorded here is incremental prefill latency (vLLM reuses
        prior KV cache via prefix caching). It is NOT the cold re-prefill cost that
        would be incurred during a migration. See 04_prefill_benchmark.py for that.
        """
        if turn_index >= len(self.turns):
            return None

        user_msg = self.turns[turn_index]
        self.messages.append({"role": "user", "content": user_msg})

        # Count tokens going IN (this is what the KV cache must store)
        prompt_tokens_estimate = sum(self.estimate_tokens(m["content"]) for m in self.messages)

        # Send request to vLLM
        t_start = time.time()
        try:
            response = requests.post(
                f"{self.server_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": self.messages,
                    "max_tokens": 512,
                    "temperature": 0.7,
                },
                timeout=120,
            )
            t_end = time.time()
            latency = t_end - t_start

            if response.status_code == 200:
                data = response.json()
                assistant_msg = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                # vLLM returns actual token counts
                prompt_tokens = usage.get("prompt_tokens", prompt_tokens_estimate)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

                self.messages.append({"role": "assistant", "content": assistant_msg})
                self.context_tokens = total_tokens
                self.turn_count += 1

                row = {
                    "timestamp": datetime.now().isoformat(),
                    "session_id": self.session_id,
                    "session_name": self.name,
                    "turn": self.turn_count,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_context_tokens": total_tokens,
                    # INCREMENTAL latency: vLLM reuses the existing KV cache via prefix
                    # caching, so only the new user turn tokens are recomputed. This
                    # reflects how inference slows as context grows, NOT migration cost.
                    # For cold re-prefill cost (migration penalty), see prefill_cost_curve.csv.
                    "incremental_latency_s": round(latency, 4),
                    "decode_tokens_per_second": round(completion_tokens / latency, 1) if latency > 0 else 0,
                }
                self.log_rows.append(row)
                return row
            else:
                print(f"  [Session {self.session_id}] HTTP {response.status_code}: {response.text[:200]}")
                return None

        except Exception as e:
            print(f"  [Session {self.session_id}] Error: {e}")
            return None


def detect_model_name(server_url: str) -> str:
    """Query vLLM server to find the loaded model name."""
    try:
        resp = requests.get(f"{server_url}/v1/models", timeout=5)
        if resp.status_code == 200:
            models = resp.json()["data"]
            if models:
                return models[0]["id"]
    except Exception:
        pass
    return None


def run_workload(args):
    """Run all sessions with controlled concurrency."""
    os.makedirs("logs", exist_ok=True)

    # Auto-detect model name from server
    model_name = detect_model_name(args.server_url)
    if model_name is None:
        print(f"ERROR: Cannot reach vLLM server at {args.server_url}")
        print("Make sure 01_start_server.py is running first.")
        return
    print(f"Connected to server. Model: {model_name}\n")

    # Create sessions
    num_sessions = min(args.sessions, len(SESSION_PROMPTS))
    sessions = []
    for i in range(num_sessions):
        config = SESSION_PROMPTS[i]
        max_turns = min(args.turns_per_session, len(config["turns"]))
        config = {**config, "turns": config["turns"][:max_turns]}
        sessions.append(Session(i, config, args.server_url, model_name))

    print(f"Running {num_sessions} concurrent sessions, up to {args.turns_per_session} turns each")
    print(f"Inter-turn delay: {args.delay_between_turns}s\n")

    # Run sessions concurrently.
    # Each session runs its turns sequentially (conversation must be in order).
    # Multiple sessions run in parallel (simulating concurrent users).
    all_rows = []

    def run_session(session: Session):
        rows = []
        max_turns = min(args.turns_per_session, len(session.turns))
        for turn_idx in range(max_turns):
            row = session.run_turn(turn_idx)
            if row:
                rows.append(row)
                print(f"  Session {session.session_id} ({session.name}) | "
                      f"Turn {row['turn']:2d} | "
                      f"Context: {row['total_context_tokens']:5d} tok | "
                      f"Incr. latency: {row['incremental_latency_s']:.2f}s | "
                      f"Decode: {row['decode_tokens_per_second']:.0f} tok/s")

            # Delay between turns (simulates user think time)
            time.sleep(args.delay_between_turns)
        return rows

    with ThreadPoolExecutor(max_workers=num_sessions) as executor:
        futures = {executor.submit(run_session, s): s for s in sessions}
        for future in as_completed(futures):
            session = futures[future]
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as e:
                print(f"Session {session.session_id} failed: {e}")

    # Sort by timestamp and save
    all_rows.sort(key=lambda r: r["timestamp"])

    output_path = args.output
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    if all_rows:
        fieldnames = all_rows[0].keys()
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\nSaved {len(all_rows)} records → {output_path}")
    else:
        print("\nNo data collected. Check server connection.")

    # Print summary
    print("\n--- Session Summary ---")
    for s in sessions:
        if s.log_rows:
            final = s.log_rows[-1]
            print(f"  Session {s.session_id} ({s.name}): "
                  f"{s.turn_count} turns, "
                  f"{final['total_context_tokens']} final tokens, "
                  f"avg incremental latency {sum(r['incremental_latency_s'] for r in s.log_rows)/len(s.log_rows):.2f}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", type=str, default="http://localhost:8000",
                        help="vLLM server URL")
    parser.add_argument("--sessions", type=int, default=4,
                        help="Number of concurrent sessions")
    parser.add_argument("--turns-per-session", type=int, default=15,
                        help="Max turns per session")
    parser.add_argument("--delay-between-turns", type=float, default=1.0,
                        help="Seconds between turns within a session (simulates think time)")
    parser.add_argument("--output", type=str, default="logs/session_traces.csv",
                        help="Output CSV path")
    args = parser.parse_args()

    run_workload(args)


if __name__ == "__main__":
    main()
