#!/usr/bin/env python3
"""StudySS1-32B (D142 item 3): run the committed StudySS1 kit (8492e02, experiments/casestudy/ss1_*, UNCHANGED) with
Qwen3-VL-32B on the H100: full VizWiz val (4,319) and EgoThink (700).

This wrapper only manages the server: it starts the round-1 32B server (study_live2_pilot.start_server, 27 GiB host
tier, served as "32BI", port 8031) exactly as StudyACC2 did, records its command and flags, runs the kit's own
`ss1_run.py` (same manifests, prompt templates, image preprocessing, greedy decoding, one request at a time, a
per-question cache_salt so every image is a cold single-shot), and stops the server. No scoring code here: the kit
scores VizWiz VQA accuracy and EgoThink containment; flash runs the EgoThink judge. No em dashes.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/casestudy/study_ss1"
sys.path.insert(0, str(REPO / "experiments/orchestration"))
PY = sys.executable
RUNS = [
    ("vizwiz", "vizwiz_val_manifest.jsonl", "vizwiz_val_cloud32b.json"),
    ("egothink", "egothink_manifest.jsonl", "egothink_cloud32b.json"),
]


def main():
    import study_live2_pilot as PL
    PL.OUT = OUT
    PL.WORK = Path.home() / "data/ss1_32b"
    PL.WORK.mkdir(parents=True, exist_ok=True)
    kit_head = subprocess.run(["git", "log", "-1", "--format=%h", "--", "experiments/casestudy/ss1_run.py",
                               "experiments/casestudy/ss1_kit.py"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    srv, sinfo, _M = PL.start_server(27.0)
    meta = dict(study="StudySS1-32B", server=sinfo, served_model="32BI", endpoint="http://127.0.0.1:8031/v1",
                kit_last_commit=kit_head, started=time.strftime("%F %T"), runs=[])
    try:
        for ds, man, out in RUNS:
            t0 = time.time()
            rc = subprocess.run([PY, str(REPO / "experiments/casestudy/ss1_run.py"), "--dataset", ds,
                                 "--manifest", str(OUT / man), "--ids", "all", "--tier", "cloud", "--model", "32BI",
                                 "--endpoint", "http://127.0.0.1:8031/v1", "--out", str(OUT / out)],
                                cwd=REPO).returncode
            meta["runs"].append(dict(dataset=ds, out=out, rc=rc, seconds=round(time.time() - t0, 1)))
            (OUT / "ss1_cloud32b_run_meta.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")
    finally:
        srv.stop()
        meta["stopped"] = time.strftime("%F %T")
        (OUT / "ss1_cloud32b_run_meta.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")
    print("StudySS1-32B done", json.dumps(meta["runs"]), flush=True)


if __name__ == "__main__":
    main()
