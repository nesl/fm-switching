import sys, json
from pathlib import Path
REPO = Path("/tmp/claude-1001/mapwt")
HERE = REPO / "experiments/orchestration/live2"
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(REPO / "experiments/orchestration/live"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import trace as TR

res = TR.generate_trace(seed=4, n_devices=16, ratio="40:40:20", run_s=1200.0, mode="A",
                        count_only=False, robot_question_set="lh_req", ss_question_set="ss2",
                        dashcam_format="epg", robot_upload="per-frame")
recs = res["records"]
# played sessions: session_start records for robot devices
starts = {}
for r in recs:
    if r["kind"] == "session_start" and str(r["device_id"]).startswith("robo"):
        starts[r["session_id"]] = r["t"]
asked = {}
for r in recs:
    if r["kind"] == "recall_question" and str(r["device_id"]).startswith("robo"):
        asked.setdefault(r["session_id"], []).append(r)
print(f"robot sessions STARTED in trace: {len(starts)}")
print(f"robot sessions with >=1 ask:    {len(asked)}")
print(f"robot asks emitted:             {sum(len(v) for v in asked.values())}")

# the session model pool: reach into the generator's own loader the same way it does
sessions = TR.DS.lh_req_sessions() if hasattr(TR.DS, "lh_req_sessions") else None
if sessions is None:
    for name in dir(TR.DS):
        if "session" in name.lower() and callable(getattr(TR.DS, name)):
            print("  candidate loader:", name)
    sys.exit(0)
print(f"session pool: {len(sessions)} sessions, "
      f"{sum(len(s.questions) for s in sessions.values())} questions")
RUN = 1200.0
import re
pat = re.compile(r"start_([0-9.]+)_end_([0-9.]+)")
tot = {"asked":0, "beyond_session":0, "beyond_run":0, "unplayed_session":0}
played_keys = set()
for sid, t0 in starts.items():
    m = pat.search(sid)
    dur = float(m.group(2)) - float(m.group(1)) if m else None
    base = sid.split("|")[-1]
    played_keys.add(base)
    sm = None
    for k, s in sessions.items():
        if str(k) in sid or base.startswith(str(k)):
            sm = s; break
    if sm is None: continue
    for q in sm.questions:
        if q.t_ask > (dur if dur else 0) + 1e-9:
            tot["beyond_session"] += 1
        elif t0 + q.t_ask > RUN + 1e-9:
            tot["beyond_run"] += 1
        else:
            tot["asked"] += 1
print("\nPER-PLAYED-SESSION classification of pool questions:")
for k, v in tot.items(): print(f"  {k:18s} {v}")
