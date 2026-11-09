#!/usr/bin/env python3
"""StudyB2-h100 shared definitions. Uses experiments/benchmarks/b1_common.py UNCHANGED (its SHA-256 is verified before
every stage and at the start of every B2 GPU step; a different SHA halts the queue).

Models (pinned snapshots in ~/.cache/huggingface/hub, revision = snapshot directory name):
  Instruct: greedy, max_tokens 64, logprobs top 20 (StudyB1).
  Thinking: model-card VL sampling (README "Generation Hyperparameters / VL" of each snapshot, identical for 4B / 8B /
            32B): temperature 1.0, top_p 0.95, top_k 20, repetition_penalty 1.0, presence_penalty 0.0; max_tokens 16384,
            seed 0; whole response saved.
Datasets / parts: "ovo_rtv" = OVO-Bench + RTV-Bench exactly as StudyB1 (b1_common.build_items / fixed_order).
Rows: results/benchmarks/study_b2_<dataset>/b2_rows_<model>[.partK].jsonl.gz, one gzip member per row; a new part is
started before a file would exceed ROTATE_BYTES (90 MB split rule).
Hard stops (halt file logs/dseries_HALT, honoured by the queue): b1_common SHA differs; frame SHA-256 list differs from
the reference arm on a matched request; repeat-control agreement < 99 %.
"""
import hashlib
import json
import zlib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
B1_COMMON = HERE / "b1_common.py"
B1_COMMON_SHA = "50d3d54d39662302997250b80e2fb23bf47da731abec1a80cbb27d49676a8b19"
HALT = REPO_ROOT / "logs/dseries_HALT"
ROTATE_BYTES = 85 * 1024 * 1024

MODELS = {
    "4BI": ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17"),
    "8BI": ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"),
    "32BI": ("Qwen/Qwen3-VL-32B-Instruct", "0cfaf48183f594c314753d30a4c4974bc75f3ccb"),
    "4BT": ("Qwen/Qwen3-VL-4B-Thinking", "1de27d8c51f12e819435303b9e84c4e25ba8401e"),
    "8BT": ("Qwen/Qwen3-VL-8B-Thinking", "92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b"),
    "32BT": ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1"),
}
INSTRUCT_ORDER = ("4BI", "8BI", "32BI")
THINKING_ORDER = ("4BT", "8BT", "32BT")
GEN = {"instruct": dict(temperature=0.0, max_tokens=64, seed=0, logprobs=True, top_logprobs=20),
       "thinking": dict(temperature=1.0, top_p=0.95, top_k=20, repetition_penalty=1.0, presence_penalty=0.0,
                        max_tokens=16384, seed=0)}
GEN_SOURCE = {"instruct": "StudyB1 (greedy, max_tokens 64, logprobs top 20)",
              "thinking": "model card README 'Generation Hyperparameters' VL section of each pinned snapshot "
                          "(4B/8B/32B identical: greedy=false, top_p 0.95, top_k 20, repetition_penalty 1.0, "
                          "presence_penalty 0.0, temperature 1.0); max_tokens 16384 and seed 0 per the B2 spec. "
                          "Note: 32B-Thinking generation_config.json says temperature 0.8; the card VL value 1.0 is used "
                          "and set explicitly in every request."}


def is_thinking(model):
    return model.endswith("T")


def snapshot_dir(model):
    repo, rev = MODELS[model]
    return Path.home() / f".cache/huggingface/hub/models--{repo.replace('/', '--')}/snapshots/{rev}"


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def halt(reason):
    HALT.parent.mkdir(parents=True, exist_ok=True)
    HALT.write_text(f"{datetime.now().isoformat()} {reason}\n")
    raise SystemExit(f"HALT: {reason}")


def check_b1_common():
    got = sha256_file(B1_COMMON)
    if got != B1_COMMON_SHA:
        halt(f"b1_common.py SHA-256 {got} != {B1_COMMON_SHA}")
    return got


# ---------------- rows (gzip members, rotated parts) ----------------
def read_rows_file(path):
    rows = []
    if not path.exists():
        return rows
    data = path.read_bytes()
    while data:  # tolerate a truncated last member after a crash
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            chunk = d.decompress(data)
        except zlib.error:
            break
        for l in chunk.decode(errors="replace").splitlines():
            try:
                rows.append(json.loads(l))
            except json.JSONDecodeError:
                pass
        if not d.eof:
            break
        data = d.unused_data
    return rows


def row_parts(out_dir, stem):
    """All files of one logical rows file: <stem>.jsonl.gz, <stem>.part2.jsonl.gz, ... in order."""
    first = out_dir / f"{stem}.jsonl.gz"
    parts = [first] if first.exists() else []
    k = 2
    while (out_dir / f"{stem}.part{k}.jsonl.gz").exists():
        parts.append(out_dir / f"{stem}.part{k}.jsonl.gz")
        k += 1
    return parts


def read_rows(out_dir, stem):
    rows = []
    for p in row_parts(out_dir, stem):
        rows += read_rows_file(p)
    return rows


def current_part(out_dir, stem):
    parts = row_parts(out_dir, stem)
    if not parts:
        return out_dir / f"{stem}.jsonl.gz"
    last = parts[-1]
    if last.stat().st_size < ROTATE_BYTES:
        return last
    return out_dir / f"{stem}.part{len(parts) + 1}.jsonl.gz"


def latest_ok(rows):
    """(tag, item_id, input) -> the last error-free row (resume writes at most one ok row per key)."""
    out = {}
    for r in rows:
        if not r.get("error"):
            out[(r["tag"], r["item_id"], r["input"])] = r
    return out
