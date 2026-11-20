#!/usr/bin/env python3
"""StudySS2-32B: run the committed StudySS2 kit (1b8790c, experiments/casestudy/ss2_*, UNCHANGED) with
Qwen3-VL-32B on the H100: RefSpatial-Bench (277) and RealWorldQA (765); CODA-LM skipped by the kit (licence).

This wrapper only manages the server: it starts the round-1 32B server (study_live2_pilot.start_server, 27 GiB host
tier, served as "32BI", port 8031) exactly as StudyACC2 did, records its command and flags, runs the kit's own
`ss2_run.py` (same manifests, prompt templates, image preprocessing, greedy decoding, one request at a time, a
per-question cache_salt so every image is a cold single-shot), and stops the server. No scoring code here: the kit
scores VizWiz VQA accuracy and EgoThink containment; flash runs the EgoThink judge. No em dashes.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/casestudy/study_ss2"
sys.path.insert(0, str(REPO / "experiments/orchestration"))
PY = sys.executable
# vLLM 0.31.0 rejects a cache_salt containing '/', '@', '\\' or NUL (HTTP 400), and the kit passes each question id
# (e.g. "vizwiz_val/VizWiz_val_00000000") as the salt; the Orin's older vLLM accepted it. The salt only partitions the
# prefix cache and never reaches the model, so it cannot change an answer. This shim runs the kit's runner UNCHANGED
# except that the salt has '/' replaced by '_' (still unique per question). Implementation fix, reported.
SHIM = """
import sys
sys.argv = ['ss2_run.py'] + sys.argv[1:]
sys.path.insert(0, '%s')
import ss2_run as R
_call = R.call
def call(endpoint, model, prompt, data_url, max_tokens, salt, timeout=180):
    return _call(endpoint, model, prompt, data_url, max_tokens, str(salt).replace('/', '_'), timeout)
R.call = call
R.main()
""" % str(REPO / "experiments/casestudy")
RUNS = [
    ("refspatial", "refspatial_manifest.jsonl", "refspatial_cloud32b.json"),
    ("realworldqa", "realworldqa_manifest.jsonl", "realworldqa_cloud32b.json"),
]


def main():
    import study_live2_pilot as PL
    PL.OUT = OUT
    PL.WORK = Path.home() / "data/ss2_32b"
    PL.WORK.mkdir(parents=True, exist_ok=True)
    kit_head = subprocess.run(["git", "log", "-1", "--format=%h", "--", "experiments/casestudy/ss2_run.py",
                               "experiments/casestudy/ss2_bench_kit.py"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    srv, sinfo, _M = PL.start_server(27.0)
    meta = dict(study="StudySS2-32B", salt_fix="cache_salt '/' -> '_' (vLLM 0.31.0 rejects '/'); kit files unchanged",
                server=sinfo, served_model="32BI", endpoint="http://127.0.0.1:8031/v1",
                kit_last_commit=kit_head, started=time.strftime("%F %T"), runs=[])
    try:
        for ds, man, out in RUNS:
            t0 = time.time()
            rc = subprocess.run([PY, "-c", SHIM, "--dataset", ds,
                                 "--manifest", str(OUT / man), "--ids", "all", "--tier", "cloud", "--model", "32BI",
                                 "--endpoint", "http://127.0.0.1:8031/v1", "--device", "h100nvl", "--out", str(OUT / out)],
                                cwd=REPO).returncode
            meta["runs"].append(dict(dataset=ds, out=out, rc=rc, seconds=round(time.time() - t0, 1)))
            (OUT / "ss2_cloud32b_run_meta.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")
    finally:
        srv.stop()
        meta["stopped"] = time.strftime("%F %T")
        (OUT / "ss2_cloud32b_run_meta.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")
    print("StudySS2-32B done", json.dumps(meta["runs"]), flush=True)


if __name__ == "__main__":
    main()
