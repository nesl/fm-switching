import gzip, json, re, sys
from collections import defaultdict
rows=[json.loads(l) for l in gzip.open(sys.argv[1],"rt")]
rob=[r for r in rows if (r.get("device_id") or "").startswith("robo") and r.get("kind")=="recall"]
ass=[r for r in rows if (r.get("device_id") or "").startswith("asst") and r.get("kind")=="recall"]
print(f"recall outcomes: robot {len(rob)}, single-shot {len(ass)}")
pat=re.compile(r"start_([0-9.]+)_end_([0-9.]+)")
sess=defaultdict(list)
for r in rob:
    sess[r["session_id"]].append(r)
RUN=1200.0
print(f"\n{len(sess)} robot sessions, {len({r['device_id'] for r in rob})} robot devices\n")
print(f"{'session':58s} {'span_s':>8s} {'nq':>3s} {'first_q_t':>9s} {'elig_s':>8s}")
tot_elig=0.0; tot_q=0
for sid,qs in sorted(sess.items()):
    m=pat.search(sid)
    st,en=(float(m.group(1)),float(m.group(2))) if m else (0.0,RUN)
    ts=sorted(q["t_opportunity"] for q in qs)
    # session wall-clock start: first question's t minus its session-local offset is unknown here,
    # so bound the eligible window by the LAST question and the run end, which is conservative.
    first=ts[0]; last=ts[-1]
    # eligible for re-ask: from the first ask to the earlier of (session end in wall clock) and RUN.
    # session end in wall clock is bounded below by the last ask; use span to extend it.
    sess_end_wall=min(RUN, first + (en-st))
    elig=max(0.0, sess_end_wall-first)
    tot_elig+=elig; tot_q+=len(qs)
    print(f"{sid[:58]:58s} {en-st:8.1f} {len(qs):3d} {first:9.1f} {elig:8.1f}")
print(f"\noriginal robot questions: {tot_q}")
print(f"total eligible re-ask window: {tot_elig:.1f} device-seconds")
for mi in (15,30,60,120):
    print(f"  mean interval {mi:3d} s -> expected re-asks {tot_elig/mi:7.1f}, "
          f"total robot questions {tot_q + tot_elig/mi:7.1f}, "
          f"re-ask share {100*(tot_elig/mi)/(tot_q+tot_elig/mi):5.1f}%")
