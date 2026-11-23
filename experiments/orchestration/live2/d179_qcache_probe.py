#!/usr/bin/env python3
"""ONE DRY CELL PER PROCESS, for the arms_v6state.py:236 `_queued_behind` cache-key defect.

    key = (int(obs.epoch) if isinstance(obs.epoch, int) else id(obs))      arms_v6state.py:236
    def observation(self, now: float, epoch: str, ...)                     cstate.py:579

`obs.epoch` is always a str, so the key is always a memory address, and CPython reuses addresses.
This runner is the measurement half of `d179_qcache_key_defect.py`, which reads its outputs.

ONE CELL PER PROCESS IS NOT OPTIONAL HERE: a dry cell does not reproduce across runs inside one
process, and that non-reproduction is the defect under test.

NOTHING IN THE LIVE PATH IS EDITED. The probe wraps `V6StateArm._queued_behind` in this process
only; the `fixed` key mode rebuilds the cache once per decision period by clearing
`_q_cache_key` whenever `obs.now_s` changes, which is the proposed fix applied through a wrapper
rather than committed to the arm.

A STALE HIT CHANGES A VALUE; A STALE MISS COSTS ONLY A RECOMPUTE, so the two are counted
separately, and a stale hit whose cached list is EMPTY (or empty after the own-session filter) is
counted apart from one that is not, because only the latter can reach `harm_warm`.

Environment: QC_TREE (the checked-out tree to import from), QC_OUT (where to write), optional
QC_AUDIT_OPEN (record every results/ file the run reads, so the inputs can be audited).
Usage: QC_TREE=... QC_OUT=... python -I d179_qcache_probe.py probe <arm> <seed> <current|fixed> <run_s>
"""
import hashlib
import json
import os
import sys

# AUDIT: every file opened under the tree, so the inputs can be verified against origin/main
_OPENED = set()
if os.environ.get("QC_AUDIT_OPEN"):
    import builtins as _b
    _ro = _b.open
    def _o(file, *a, **k):
        try:
            _OPENED.add(str(file))
        except Exception:
            pass
        return _ro(file, *a, **k)
    _b.open = _o
    import pathlib as _pl
    _rp = _pl.Path.open
    def _po(self, *a, **k):
        _OPENED.add(str(self))
        return _rp(self, *a, **k)
    _pl.Path.open = _po

TREE = os.environ["QC_TREE"]
HERE = TREE + "/experiments/orchestration/live2"
for p in (HERE, HERE + "/fleet", HERE + "/hybrid", HERE + "/tests", HERE + "/v5",
          TREE + "/experiments/orchestration",
          TREE + "/experiments/orchestration/baselines",
          TREE + "/experiments/orchestration/sim"):
    sys.path.insert(0, p)

import arms as A                                                        # noqa: E402
import arms_v6state as VS                                               # noqa: E402
import test_hybrid as TH                                                # noqa: E402

mode, arm_name, seed, keymode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
run_s = float(sys.argv[5]) if len(sys.argv) > 5 else 1200.0

STATS = {"calls": 0, "hits": 0, "misses": 0, "stale_hits": 0, "fresh_hits": 0,
         "distinct_addrs": 0, "periods_seen": 0, "addr_reuse_events": 0,
         # a stale hit whose cached list is NON-EMPTY is a wrong harm_warm input: every entry's
         # slack_s was computed from the PREVIOUS period's now_s
         "stale_hits_cache_nonempty": 0, "stale_hits_cache_empty": 0,
         # the recall set itself changed between the write and the stale read
         "stale_hits_recall_set_changed": 0,
         # the stale read returned a non-empty list to _harm_warm (after the own-session filter)
         "stale_hits_returned_nonempty": 0}
_addr_now = {}          # addr -> (now_s, recall_signature, len(cache)) at the owning write
_addrs = set()
_nows = set()
_ORIG = VS.V6StateArm._queued_behind


def _sig(obs):
    out = []
    for qy in (getattr(obs, "recall", None) or ()):
        out.append((str(qy.query_id), int(getattr(qy, "readiness_tokens", 0) or 0),
                    str(qy.session_id), float(qy.deadline_s)))
    return tuple(out)


def _wrapped(self, obs, session_id):
    STATS["calls"] += 1
    now = float(getattr(obs, "now_s", -1.0))
    if now not in _nows:
        _nows.add(now)
        STATS["periods_seen"] = len(_nows)
    addr = id(obs)
    if addr not in _addrs:
        _addrs.add(addr)
        STATS["distinct_addrs"] = len(_addrs)
    if keymode == "fixed":
        # the proposed fix, applied WITHOUT editing the live path: rebuild once per period
        if getattr(self, "_qc_last_now", None) != now:
            self._q_cache_key = None
            self._qc_last_now = now
    pre = getattr(self, "_q_cache_key", None)
    hit = (pre == addr)
    if hit:
        STATS["hits"] += 1
        owner = _addr_now.get(addr)
        if owner is not None and owner[0] != now:
            STATS["stale_hits"] += 1
            cached = list(getattr(self, "_q_cache", None) or ())
            if cached:
                STATS["stale_hits_cache_nonempty"] += 1
            else:
                STATS["stale_hits_cache_empty"] += 1
            if owner[1] != _sig(obs):
                STATS["stale_hits_recall_set_changed"] += 1
            if [r for r in cached if r["session_id"] != session_id]:
                STATS["stale_hits_returned_nonempty"] += 1
        else:
            STATS["fresh_hits"] += 1
    else:
        STATS["misses"] += 1
        if addr in _addr_now and _addr_now[addr][0] != now:
            STATS["addr_reuse_events"] += 1
    out = _ORIG(self, obs, session_id)
    _addr_now[id(obs)] = (now, _sig(obs), len(getattr(self, "_q_cache", None) or ()))
    return out


if mode == "probe" or keymode == "fixed":
    VS.V6StateArm._queued_behind = _wrapped

CELL = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
            dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)
rows, st = TH.dry(arm_name, seed, 16, run_s=run_s, **CELL)
rows = list(rows or [])
rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
digest = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                   default=float).encode()).hexdigest()[:16]
st = dict(st or {})
out = {"mode": mode, "arm": arm_name, "seed": seed, "keymode": keymode, "run_s": run_s,
       "digest": digest, "rows": len(rows), "pid": os.getpid(),
       "state_decisions": st.get("state_decisions"),
       "state_chosen_HOLD_BACK": st.get("state_chosen_HOLD_BACK"),
       "state_chosen_TOUCH": st.get("state_chosen_TOUCH"),
       "state_chosen_WARM": st.get("state_chosen_WARM"),
       "state_chosen_KEEP": st.get("state_chosen_KEEP"),
       "harm_warm_priced": st.get("harm_warm_priced"),
       "harm_warm_nonzero": st.get("harm_warm_nonzero"),
       "harm_warm_milli_sum": st.get("harm_warm_milli_sum"),
       "state_touch_emitted": st.get("state_touch_emitted"),
       "state_hold_back_enacted": st.get("state_hold_back_enacted")}
if mode == "probe" or keymode == "fixed":
    out["qcache"] = dict(STATS)
out["opened_under_tree"] = sorted(x for x in _OPENED if "/tree/results/" in x or "/tree/research/" in x or "/tree/reports/" in x)
dest = os.environ.get("QC_OUT")
if dest:
    with open(dest, "w") as f:
        json.dump({"result": out, "rows_sample": rr[:3]}, f)
    # the full row list, for the setwise and positional diff
    with open(dest + ".rows.json", "w") as f:
        json.dump(rr, f, separators=(",", ":"), default=float)
print(json.dumps(out))
