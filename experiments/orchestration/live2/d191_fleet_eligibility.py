"""D97 eligibility from the TRACE ONLY, outcome-independent, no GPU, count_only."""
import sys, json
HERE = "/tmp/claude-1001/mapwt/experiments/orchestration/live2"
for p in (HERE, HERE+"/fleet", HERE+"/v5", HERE+"/hybrid", HERE+"/../baselines"):
    sys.path.insert(0, p)
import trace as TR
MODE = sys.argv[2]
out=[]
for n in (12, 16, 20):
    for seed in (4, 5):
        t = TR.generate_trace(seed, n, "40:40:20", 1200.0, MODE,
                              robot_question_set="lh_req", ss_question_set="ss2",
                              dashcam_format="epg", dashcam_min_frames=3,
                              robot_upload="per-frame", robot_reask_mean_s=30.0)
        st = t.get("stats", {}) or {}
        recs = t.get("records", []) or []
        rq = [r for r in recs if (r.get("kind") if isinstance(r, dict) else None) == "recall_question"]
        devs = sorted({r.get("device_id") for r in rq if r.get("device_id")})
        row = {"n_devices": n, "seed": seed, "robot_questions": len(rq),
               "robot_devices": len(devs), "eligible_ge20": len(rq) >= 20,
               "n_records": len(recs)}
        out.append(row); print(json.dumps(row))
json.dump({"_what": "D97 robot-pool eligibility at 12 / 16 / 20 devices, 40:40:20, lh_req, rq30, 1200 s, from the TRACE only",
           "_rule": "D82 / D95 (2): a fleet size enters a comparison only if its robot pool reaches 20 pooled questions, at EVERY seed used",
           "mode": MODE, "rows": out,
           "verdict_12": all(r["eligible_ge20"] for r in out if r["n_devices"]==12),
           "verdict_20": all(r["eligible_ge20"] for r in out if r["n_devices"]==20)},
          open(sys.argv[1], "w"), indent=1)
