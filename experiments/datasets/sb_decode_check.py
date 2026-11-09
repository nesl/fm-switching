#!/usr/bin/env python3
"""StudyB2: render-check every request of a StreamingBench shard on CPU (b1_common.select_frames, no encode) and list
requests whose frames cannot be decoded -> logs/sb_decode_check_shard<k>.json. Run from the repo root."""
import sys, json, traceback
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, "experiments/benchmarks")
import b1_common as B, b2_sb as SB
def job(a):
    it, inp = a
    try:
        tg, _ = B.targets(it["t"], B.INPUTS[inp]); B.select_frames(it["video"], tg, encode=False); return None
    except Exception as e:
        return dict(item=it["item_id"], video=it["video"], t=it["t"], input=inp, err=f"{type(e).__name__}: {e}"[:200])
if __name__ == "__main__":
    shard = int(sys.argv[1])
    items = [it for it in SB.build_items() if it["shard"] == shard]
    jobs = [(it, inp) for it in items for inp in ("RECENT", "HISTORY")]
    with ProcessPoolExecutor(16) as ex:
        bad = [r for r in ex.map(job, jobs, chunksize=4) if r]
    json.dump(bad, open(f"logs/sb_decode_check_shard{shard}.json", "w"), indent=1)
    print(len(jobs), "requests;", len(bad), "fail;", len({b['video'] for b in bad}), "videos")
    for b in bad[:12]: print(b)
