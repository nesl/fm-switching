#!/usr/bin/env python3
"""Flash tests for the StudyLIVE2-fleet build. CPU only, fake / stub server only.

StudyLIVE2-fleet, part 6, checks (a) to (f). Check (g), the 64-device real-time scale run, is
`test_scale.py` because it takes minutes of wall clock rather than seconds.

NOTHING HERE IS A MEASUREMENT. Every run uses `StubCoordinator`, which holds no model, and the
calibration map is the committed INTERIM map, which D86 allows for flash tests and nothing else.
These checks test the HARNESS: determinism, the fairness invariant, the link arithmetic, the
scorer's arithmetic on hand-built outcomes, session chaining, and the INTERIM-map refusal.

Run:  python3 test_live2_fleet.py
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
FLEET = HERE.parent
LIVE2 = FLEET.parent
ROOT = LIVE2.parents[2]
for p in (str(FLEET), str(LIVE2 / "scorer")):
    if p not in sys.path:
        sys.path.insert(0, p)

import data_sources as DS       # noqa: E402
import emulator as EM           # noqa: E402
import events as EV             # noqa: E402
import links as LK              # noqa: E402
import trace as TR              # noqa: E402
import score as SC              # noqa: E402

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        raise AssertionError(f"{name}: {detail}")


# ---------------------------------------------------------------- (a) determinism
def test_a_determinism(tmp: Path) -> None:
    b1 = TR.generate_trace(1, 6, "50:50", 90.0, "A")
    m1 = TR.write_trace(tmp / "a_s1", b1)
    b1b = TR.generate_trace(1, 6, "50:50", 90.0, "A")
    m1b = TR.write_trace(tmp / "a_s1b", b1b)
    b2 = TR.generate_trace(2, 6, "50:50", 90.0, "A")
    m2 = TR.write_trace(tmp / "a_s2", b2)
    check("a1 same seed -> same trace sha256", m1["trace_sha256"] == m1b["trace_sha256"],
          m1["trace_sha256"][:16])
    check("a2 same seed -> same device_answers sha256",
          m1["device_answers_sha256"] == m1b["device_answers_sha256"])
    check("a3 different seed -> different trace sha256",
          m1["trace_sha256"] != m2["trace_sha256"], m2["trace_sha256"][:16])
    bB = TR.generate_trace(1, 6, "50:50", 90.0, "B")
    mB = TR.write_trace(tmp / "a_s1_modeB", bB)
    check("a4 the trace FILE is mode-independent (D69 identical opportunity streams)",
          mB["trace_sha256"] == m1["trace_sha256"])
    check("a4b the fairness digest is per mode (D96 (2)) and the trace records both",
          m1["fairness_digest"] == m1["fairness_digest_A"]
          and mB["fairness_digest"] == mB["fairness_digest_B"]
          and m1["fairness_digest_A"] != m1["fairness_digest_B"],
          f"A {m1['fairness_digest_A'][:16]} B {m1['fairness_digest_B'][:16]}")
    ids = [r["opportunity_id"] for r in b1["records"]
           if r["kind"] in TR.OPPORTUNITY_KINDS]
    check("a7 every opportunity_id is ASSIGNED by the generator, flat and unique in the run",
          len(ids) == len(set(ids)) and all(i.startswith("opp") for i in ids)
          and not any("opportunity_key" in r for r in b1["records"] + b1["device_answers"]),
          f"{len(ids)} ids, {ids[0]} .. {ids[-1]}")
    check("a8 the same seed assigns the same opportunity_ids",
          ids == [r["opportunity_id"] for r in b1b["records"]
                  if r["kind"] in TR.OPPORTUNITY_KINDS])
    cov = {t[1] for t in (TR._digest_tuple(r, "B") for r in b1["records"]) if t is not None}
    check("a9 the pull-mode digest covers monitor_offer and NOT monitor_frame (D96 (2))",
          "monitor_offer" in cov and "monitor_frame" not in cov, json.dumps(sorted(cov)))
    covA = {t[1] for t in (TR._digest_tuple(r, "A") for r in b1["records"]) if t is not None}
    check("a10 the push-mode digest covers monitor_frame and not monitor_offer, and the two "
          "modes differ ONLY in that label (D96 (2))",
          "monitor_frame" in covA and "monitor_offer" not in covA
          and (covA - {"monitor_frame"}) == (cov - {"monitor_offer"}),
          json.dumps(sorted(covA)))
    # Which non-monitor kinds appear is data-dependent: no session ENDS in a 90-s trace, because
    # the shortest EVAL session is 300 s. So the definition is checked on the mapping itself.
    allowed = {"device_register", "session_start", "session_end", "history_preload",
               "history_append", "recall_question", "monitor_frame", "monitor_offer"}
    check("a11 the digest covers exactly the D96 (2) set plus history_preload (D101), and "
          "nothing else",
          covA <= allowed and cov <= allowed
          and TR._digest_tuple(dict(kind="session_end", device_id="d", session_id="s", t=1.0),
                               "A")[1] == "session_end"
          and TR._digest_tuple(dict(kind="history_preload", device_id="d", session_id="s",
                                    t=0.0, est_tokens=3091), "A")
          == ("d", "history_preload", "0.000000", "s", "3091", "")
          and TR._digest_tuple(dict(kind="monitor_opportunity", device_id="d", t=1.0,
                                    opportunity_id="opp0", deadline_s=1.0), "B")[1]
          == "monitor_offer"
          and TR._digest_tuple(dict(kind="pull_request"), "A") is None,
          json.dumps(sorted(allowed)))
    for r in ("50:50", "75:25", "25:75"):
        n_d, n_r = TR._split_fleet(16, r)
        check(f"a5 ratio {r} splits 16 devices as {n_d}:{n_r}", n_d + n_r == 16)
    try:
        TR.generate_trace(1, 6, "60:40", 90.0, "A")
        check("a6 an unlisted ratio is refused (D67)", False, "no error raised")
    except ValueError:
        check("a6 an unlisted ratio is refused (D67)", True)


# ---------------------------------------------------------------- (b) fairness
def test_b_fairness(tmp: Path) -> None:
    b = TR.generate_trace(3, 8, "50:50", 60.0, "A")
    meta = TR.write_trace(tmp / "b_trace", b)
    arms = [("push_all", "A", dict(capacity_per_s=1e9)),
            ("push_scarce", "A", dict(capacity_per_s=2.0)),
            ("pull_all", "B", dict(capacity_per_s=1e9, pull_all=True)),
            ("pull_none", "B", dict(capacity_per_s=1e9, pull_all=False))]
    for arm, mode, kw in arms:
        em = EM.FleetEmulator(tmp / "b_trace", EM.StubCoordinator(**kw), mode,
                              realtime=False)
        rm = em.run(tmp / f"b_run_{arm}")
        check(f"b {arm}: fairness digest == the trace digest for mode {mode}",
              rm["digests_equal"]
              and rm["fairness_digest"] == meta[f"fairness_digest_{mode}"],
              f"served {rm['n_served']}/{rm['n_opportunities']}")
    served = []
    for arm, _m, _k in arms:
        rm = json.loads((tmp / f"b_run_{arm}" / "run_meta.json").read_text())
        served.append(rm["n_served"])
    check("b arms differ in what they SERVE while presenting the same stream",
          len(set(served)) > 1, f"n_served per arm {served}")
    dall = json.loads((tmp / "b_run_pull_all" / "run_meta.json").read_text())["fairness_digest"]
    dnone = json.loads((tmp / "b_run_pull_none" / "run_meta.json").read_text())["fairness_digest"]
    check("b pull-all and pull-none give the SAME digest, because pulled frames are excluded "
          "in pull mode (D96 (2))", dall == dnone, dall[:16])


# ---------------------------------------------------------------- (c) link math
def test_c_links() -> None:
    v = LK.upload_s(354902)
    check("c1 upload_s(354902) reproduces the committed 0.209 + 0.044 decomposition",
          abs(v - (354902 * 8 / 13.6e6 + 0.022)) < 1e-12 and abs(v - 0.230766) < 1e-5,
          f"{v:.6f} s")
    check("c2 serialise_s is upload_s minus RTT/2",
          abs(LK.serialise_s(100000) - (LK.upload_s(100000) - 0.022)) < 1e-12)
    check("c3 pull_s is RTT/2", abs(LK.pull_s() - 0.022) < 1e-12)
    check("c4 deliver_s(300) = RTT/2 + payload / downlink",
          abs(LK.deliver_s(300) - (0.022 + 300 * 8 / 13.6e6)) < 1e-12,
          f"{LK.deliver_s(300):.6f} s")
    check("c5 a q90 dashcam frame uploads in about 59.6 ms (D75 + E10a median)",
          abs(LK.upload_s(63898) - 0.0595824) < 1e-4, f"{LK.upload_s(63898):.6f} s")
    sens = LK.downlink_sensitivity_s(300)
    spread = max(s for _r, s in sens) - min(s for _r, s in sens)
    check("c6 the ASSUMED downlink rate moves a 300 B answer by under 3 ms over 1-100 Mbit/s",
          spread < 0.003, f"spread {1000 * spread:.3f} ms")
    for bad in (-1,):
        try:
            LK.upload_s(bad)
            check("c7 a negative byte count is refused", False)
        except ValueError:
            check("c7 a negative byte count is refused", True)
    q = LK.UplinkQueue(LK.LinkSpec())
    t1 = q.send("history_batch", "b1", 368_550, 0.0)
    t2 = q.send("monitor_frame", "f1", 63_898, 0.0)
    occ = LK.serialise_s(368_550)
    check("c8 one uplink, shared serially: a frame offered behind a history batch queues",
          abs(t1.queue_s) < 1e-12 and abs(t2.queue_s - occ) < 1e-9,
          f"frame queued {1000 * t2.queue_s:.1f} ms behind a {occ * 1000:.1f} ms batch")
    t3 = q.send("monitor_frame", "f2", 63_898, 10.0)
    check("c9 an idle uplink imposes no queueing", abs(t3.queue_s) < 1e-12)
    st = q.stats()
    check("c10 the queue reports its own occupancy and queueing distribution",
          st["n"] == 3 and st["queue_max"] >= occ - 1e-6, json.dumps(st))


# ---------------------------------------------------------------- (d) scorer on toy outcomes
def _toy(tmp: Path) -> Dict[str, Any]:
    """A trace from the real pools, with HAND-BUILT outcomes whose answers are known."""
    b = TR.generate_trace(11, 8, "25:75", 600.0, "A")
    tdir = tmp / "d_trace"
    TR.write_trace(tdir, b)
    recs = b["records"]
    dash = sorted({r["device_id"] for r in recs if r["kind"] == "monitor_opportunity"})
    served_dev, starved_dev = dash[0], dash[1]
    dev_by_opp = {r["opportunity_id"]: r for r in b["device_answers"]}
    outcomes: List[Dict[str, Any]] = []
    requests: List[Dict[str, Any]] = []
    n_rob = 0
    for r in recs:
        if r["kind"] == "monitor_opportunity":
            opp = r["opportunity_id"]
            on_time = (r["device_id"] == served_dev)
            o = dict(opportunity_id=opp, device_id=r["device_id"], kind="monitor",
                     t_opportunity=r["t"], deadline_s=r["deadline_s"], play_id=r["play_id"],
                     clip=r["clip"], t_local=r["t_local"], presented=True, pulled=None,
                     within_L=on_time)
            if on_time:
                # A cloud score 2 nats above the device's, so the AP must be computable and the
                # served arm's stream must differ from the device-only stream.
                o["t_delivered"] = r["t"] + 0.5
                o["t_cloud_done"] = r["t"] + 0.4
                o["cloud_payload"] = dict(kind="monitor",
                                          cloud_score=dev_by_opp[opp]["device_score"] + 2.0,
                                          cloud_letter=None, cache_path="WARM")
            outcomes.append(o)
        elif r["kind"] == "recall_question":
            opp = r["opportunity_id"]
            n_rob += 1
            on_time = (n_rob % 2 == 1)
            gold = dev_by_opp[opp]["gold_letter"]
            path = "WARM" if n_rob % 4 in (1, 2) else "COLD"
            o = dict(opportunity_id=opp, device_id=r["device_id"], kind="recall",
                     t_opportunity=r["t"], deadline_s=r["deadline_s"],
                     session_id=r["session_id"], question_id=r["question_id"],
                     presented=True, within_L=on_time)
            if on_time:
                o["t_delivered"] = r["t"] + 1.0
                o["t_cloud_done"] = r["t"] + 0.9
                # Cloud right on WARM, wrong on COLD, so the WARM / COLD split is checkable.
                letter = gold if path == "WARM" else ("Z" if gold != "Z" else "Y")
                o["cloud_payload"] = dict(kind="recall", cloud_score=None,
                                          cloud_letter=letter, cache_path=path)
                requests.append(dict(request_id=f"toy-{n_rob:04d}", device_id=r["device_id"],
                                     opportunity_id=opp, cache_path=path,
                                     cached_tokens=(1 if path == "WARM" else 0),
                                     prompt_tokens=1000, t_submit=r["t"], t_done=r["t"] + 0.9))
            outcomes.append(o)
    rdir = tmp / "d_run"
    rdir.mkdir(parents=True, exist_ok=True)
    with open(rdir / "outcomes.jsonl", "w") as fh:
        for o in sorted(outcomes, key=lambda x: x["opportunity_id"]):
            fh.write(json.dumps(o, sort_keys=True) + "\n")
    with open(rdir / "requests.jsonl", "w") as fh:
        for r in requests:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    meta = json.loads((tdir / "trace_meta.json").read_text())
    (rdir / "run_meta.json").write_text(json.dumps(dict(
        server_kind="stub", mode="A", run_s=600.0, n_devices=8, ratio="25:75", seed=11,
        fairness_digest=meta["fairness_digest_A"], run_valid=True,
        cpu_s=0.0, wall_s=0.0, lateness=dict(n=0)), indent=2) + "\n")
    return dict(tdir=tdir, rdir=rdir, served=served_dev, starved=starved_dev,
                n_rob=n_rob, outcomes=outcomes)


def test_d_scorer(tmp: Path) -> None:
    toy = _toy(tmp)
    lo = SC.load(toy["tdir"], toy["rdir"])
    # Known capacity: one dashcam device fully served, one never served.
    a = SC.attainment(lo, min_dash=1, min_rob=1)
    pd = a.dashcam_per_device
    check("d1 the fully served dashcam device attains 1.0",
          abs(pd[toy["served"]]["fraction"] - 1.0) < 1e-12 and pd[toy["served"]]["meets"])
    check("d2 the never served dashcam device attains 0.0 and fails p = 0.25",
          pd[toy["starved"]]["fraction"] == 0.0 and not pd[toy["starved"]]["meets"])
    check("d3 capacity is NOT met when one eligible dashcam device fails",
          (not a.dashcam_all_meet) and (not a.capacity_met))
    exp = round(math.ceil(toy["n_rob"] / 2) / toy["n_rob"], 6)
    check("d4 the robot pool attainment is pooled over devices, not per device",
          a.robot_pool_n == toy["n_rob"] and abs(a.robot_pool_fraction - exp) < 1e-9,
          f"{a.robot_pool_on_time}/{a.robot_pool_n} = {a.robot_pool_fraction}")
    a20 = SC.attainment(lo, min_dash=1, min_rob=20)
    check("d5 a robot pool at or above the 20-question minimum is ELIGIBLE (D82)",
          a20.robot_pool_eligible and toy["n_rob"] >= 20,
          f"pool n = {toy['n_rob']}, min = 20")
    a_big = SC.attainment(lo, min_dash=1, min_rob=10 ** 6)
    check("d5b a robot pool under the minimum is INELIGIBLE and capacity is not met (D82)",
          (not a_big.robot_pool_eligible) and (not a_big.capacity_met))
    a_excl = SC.attainment(lo, min_dash=10 ** 9, min_rob=1)
    check("d6 a dashcam device under the instant minimum is EXCLUDED and reported (D71)",
          len(a_excl.dashcam_excluded) == 2 and not a_excl.dashcam_eligible)
    check("d7 the worst-served robot device is always identified (D82)",
          a.robot_worst_device in a.robot_per_device)

    cal = DS.calibration()
    rv = SC.robot_value(lo)
    wc = rv["warm_cold"]
    check("d8 the WARM / COLD split counts the cloud-standing answers by cache_path (D81)",
          wc["WARM"]["n"] + wc["COLD"]["n"] == rv["n_cloud_standing"] and wc["WARM"]["n"] > 0,
          json.dumps({k: v["n"] for k, v in wc.items()}))
    check("d9 WARM cloud accuracy is 1.0 and COLD is 0.0 in the toy, as built",
          wc["WARM"]["cloud_accuracy"] == 1.0 and wc["COLD"]["cloud_accuracy"] == 0.0)
    dv = SC.dashcam_value(lo, cal)
    check("d10 play-indexed AP is computed over the COMPLETED plays only (D85)",
          dv["ap"] is not None and dv["n_plays"] == dv["n_pos_plays"] + dv["n_neg_plays"],
          f"plays {dv['n_plays']} = {dv['n_pos_plays']} pos + {dv['n_neg_plays']} neg, "
          f"ap {dv['ap']}")
    dvs = {k: v for k, v in dv["ap"].items()}
    check("d11 every AP value is a probability",
          all(0.0 <= v <= 1.0 for v in dvs.values()), json.dumps(dvs))
    do = SC.device_only_value(lo, cal)
    check("d12 the device-only arm is computed from the recordings alone",
          do["dashcam_ap"] is not None and do["robot_n"] == toy["n_rob"])
    check("d13 serving half the fleet moves the AP away from device-only",
          any(abs(dv["ap"][h] - do["dashcam_ap"][h]) > 0 for h in dv["ap"]),
          f"served {dv['ap']} vs device-only {do['dashcam_ap']}")
    # A play's id must survive a repeat of the same clip on another device (D84), and the
    # opportunity id must carry no parsable structure (D96 (1)).
    plays = [r["play_id"] for r in lo.records if r["kind"] == "monitor_opportunity"]
    clips = [p.split("|")[-1] for p in plays]
    check("d14 every play has its own id even when a clip repeats (D84)",
          len(set(plays)) >= len(set(clips)))
    opps = [r["opportunity_id"] for r in lo.records if r["kind"] == "monitor_opportunity"]
    check("d14b the scorer keys on the ASSIGNED opportunity_id, which carries no structure",
          all(o.startswith("opp") and "|" not in o for o in opps)
          and set(opps) <= set(lo.outcomes) and set(opps) <= set(lo.device_answers),
          f"{len(opps)} monitor opportunities, e.g. {opps[0]}")
    cmp_ = SC.compare(SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "toy"),
                      SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "toy2"))
    check("d15 the paired bootstrap of an arm against itself centres on zero with no margin",
          cmp_["dashcam_attainment"]["diff"] == 0.0
          and cmp_["dashcam_attainment"]["ci"] == [0.0, 0.0])


# ---------------------------------------------------------------- (e) session chaining
def test_e_sessions(tmp: Path) -> None:
    b = TR.generate_trace(5, 8, "25:75", 900.0, "A")
    recs = b["records"]
    rob = sorted({r["device_id"] for r in recs if r["kind"] == "session_start"})
    check("e1 robot devices exist at 25:75", len(rob) >= 1, f"{len(rob)} robot devices")
    chained = 0
    for d in rob:
        seq = [r for r in recs if r.get("device_id") == d
               and r["kind"] in ("session_start", "session_end")]
        seq.sort(key=lambda r: (r["t"], 0 if r["kind"] == "session_end" else 1))
        open_sid = None
        for r in seq:
            if r["kind"] == "session_start":
                check(f"e2 {d}: no session starts while another is open",
                      open_sid is None, f"{open_sid} still open at {r['t']}")
                open_sid = r["session_id"]
            else:
                check(f"e3 {d}: session_end matches the open session",
                      open_sid == r["session_id"])
                open_sid = None
                chained += 1
        starts = [r for r in seq if r["kind"] == "session_start"]
        # D101: a robot's first session is JOINED PART-WAY at t = 0; the run-time stagger is the
        # dashcam's (checked in d101).
        check(f"e4 {d}: the first session starts at t = 0 and is joined part-way (D101)",
              abs(starts[0]["t"]) < 1e-9 and starts[0]["joined_part_way"] is True,
              f"start {starts[0]['t']:.3f} s, join offset "
              f"{starts[0]['join_offset_s']:.3f} s")
        for d_sid in {r["session_id"] for r in starts}:
            hb = sorted([r for r in recs if r["kind"] == "history_batch"
                         and r["session_id"] == d_sid], key=lambda r: r["t"])
            pre = [r for r in recs if r["kind"] == "history_preload"
                   and r["session_id"] == d_sid]
            hold = pre + hb
            if not hold:
                continue
            # The session's FIRST HOLDING carries the 31-token D2 header once: the preload for a
            # joined first session (D101), the first batch for a session started from zero (D83).
            check(f"e5 {d_sid[:28]}: history restarts from zero in a new session (D83, D101)",
                  hold[0]["cum_tokens"] == hold[0]["est_tokens"]
                  and hold[0]["est_tokens"] == DS.d2_batch_tokens(
                      len(hold[0]["frame_refs"]), first_batch=True),
                  f"first holding {hold[0]['kind']} {hold[0]['est_tokens']} tok over "
                  f"{len(hold[0]['frame_refs'])} frames")
            check(f"e6 {d_sid[:28]}: holding tokens accumulate monotonically",
                  all(hold[i]["cum_tokens"] > hold[i - 1]["cum_tokens"]
                      for i in range(1, len(hold))))
            if pre:
                check(f"e6b {d_sid[:28]}: a batch after a preload carries NO second header",
                      not hb or hb[0]["est_tokens"] == DS.d2_batch_tokens(
                          len(hb[0]["frame_refs"]), first_batch=False))
    check("e7 at least one session completed and chained into the next", chained >= 1,
          f"{chained} completed sessions")
    sess = [r for r in recs if r["kind"] == "session_start"]
    sids = [r["session_id"] for r in sess]
    check("e8 every session play has its own id (D84)", len(set(sids)) == len(sids))
    check("e9 d2_batch_tokens follows StudyRH4: 90 tok/img plus a 31-tok header once",
          DS.d2_batch_tokens(15, True) == 1381 and DS.d2_batch_tokens(15, False) == 1350)
    check("e10 D2 frames are on a fixed 2-s stride from the session start",
          DS.d2_frames_in(0.0, 30.0) == [2.0 * i for i in range(1, 16)])


# ---------------------------------------------------------------- (d101) the part-way join
class _RecordingStub(EM.StubCoordinator):
    """A stub that keeps every event it was handed, so a test can check the wire form."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.seen: List[Dict[str, Any]] = []

    def on_event(self, event: Dict[str, Any], t: float):
        self.seen.append(dict(event, _t_seen=t))
        return super().on_event(event, t)


def test_d101_join(tmp: Path) -> None:
    seed, n, ratio, run_s = 1, 8, "25:75", 600.0
    b = TR.generate_trace(seed, n, ratio, run_s, "A")
    meta = TR.write_trace(tmp / "d101_trace", b)
    recs, st = b["records"], b["stats"]
    sessions = DS.eval_sessions()
    rob = sorted({r["device_id"] for r in recs if r["kind"] == "session_start"})
    check("d101a robot devices exist in this cell", len(rob) >= 2, f"{len(rob)} robots")

    for d in rob:
        starts = sorted([r for r in recs if r["kind"] == "session_start"
                         and r["device_id"] == d], key=lambda r: r["t"])
        first = starts[0]
        dur0 = sessions[first["source_session"]].duration_s
        off = float(first["join_offset_s"])
        check(f"d101b {d}: the first session starts at t = 0, joined part-way (D101)",
              abs(first["t"]) < 1e-9 and first["joined_part_way"] is True)
        check(f"d101c {d}: the join point is in [0, 0.5 x session duration) (D101)",
              0.0 <= off < 0.5 * dur0 + 1e-9,
              f"{off:.3f} s of a {dur0:.1f} s session = {off / dur0:.3f}")
        check(f"d101d {d}: the draw is recorded per device in trace_meta",
              abs(meta["robot_join"][d]["join_offset_s"] - off) < 1e-6
              and 0.0 <= meta["robot_join"][d]["join_frac"] < TR.JOIN_FRAC_MAX,
              json.dumps(meta["robot_join"][d]))
        check(f"d101e {d}: later sessions in the chain start from zero (D83)",
              all(abs(r["join_offset_s"]) < 1e-12 and r["joined_part_way"] is False
                  for r in starts[1:]), f"{len(starts) - 1} later sessions")
        # Questions before the join point are neither emitted nor counted.
        sid0 = first["session_id"]
        qs = [r for r in recs if r["kind"] == "recall_question" and r["session_id"] == sid0]
        check(f"d101f {d}: no emitted question lies before the join point",
              all(float(r["t_ask_session"]) >= off - 1e-9 for r in qs),
              f"{len(qs)} questions emitted from the joined session")
        want = [q for q in sessions[first["source_session"]].questions
                if off - 1e-9 <= q.t_ask <= dur0 + 1e-9 and q.t_ask - off <= run_s + 1e-9]
        check(f"d101g {d}: exactly the questions at or after the join point are emitted",
              sorted(r["question_id"] for r in qs) == sorted(q.question_id for q in want),
              f"{len(qs)} emitted, {len(want)} expected")
        # The preload holds exactly the pre-join D2 frames, and no frame is held twice.
        pre = [r for r in recs if r["kind"] == "history_preload" and r["session_id"] == sid0]
        hb = [r for r in recs if r["kind"] == "history_batch" and r["session_id"] == sid0]
        want_pre = DS.d2_frames_in(0.0, off)
        if want_pre:
            check(f"d101h {d}: the preload holds exactly the pre-join D2 frames, D2-accounted",
                  len(pre) == 1 and len(pre[0]["frame_refs"]) == len(want_pre)
                  and pre[0]["est_tokens"] == DS.d2_batch_tokens(len(want_pre), True)
                  and pre[0]["t"] == 0.0 and pre[0]["uplink_charged"] is False,
                  f"{len(want_pre)} frames, {pre[0]['est_tokens'] if pre else 0} tok")
        else:
            check(f"d101h {d}: a join inside the first 2-s D2 stride holds nothing, so no "
                  f"preload is emitted", not pre, f"join {off:.3f} s")
        held = [f for r in pre + hb for f in r["frame_refs"]]
        # A batch at run time t covers the session-local window ending at t + off, so the
        # holding after the last batch is exactly the D2 frames up to that point.
        cover_to = off if not hb else max(float(r["t"]) for r in hb) + off
        want_held = {f"{first['source_session']}|f{x:08.2f}"
                     for x in DS.d2_frames_in(0.0, cover_to)}
        check(f"d101i {d}: no frame is held twice and none is dropped between the preload and "
              f"the batches",
              len(held) == len(set(held)) and set(held) == want_held,
              f"{len(held)} frames held up to session time {cover_to:.1f} s")

    check("d101j the skipped questions are counted, not silently dropped",
          st["robot_questions_before_join"] > 0
          and st["robot_questions_total"] == sum(st["robot_questions_per_device"].values()),
          f"{st['robot_questions_before_join']} questions before a join point")
    check("d101k the preload size per device is reported for the eligibility table",
          set(st["robot_preload_tokens"]) == set(rob)
          and st["robot_preload_tokens_min"] <= st["robot_preload_tokens_median"]
          <= st["robot_preload_tokens_max"],
          f"tokens min / median / max = {st['robot_preload_tokens_min']} / "
          f"{st['robot_preload_tokens_median']} / {st['robot_preload_tokens_max']}")
    # Dashcam devices KEEP the run-time stagger and the complete-play rule (D85).
    dash = [r for r in recs if r["kind"] == "device_register" and r["type"] == "dashcam"]
    check("d101l dashcam devices keep the run-time stagger (D101, D85)",
          dash and all(0.0 <= r["start_t"] < TR.DEFAULT_STAGGER_S + 1e-9 for r in dash)
          and any(r["start_t"] > 0.0 for r in dash),
          f"{len(dash)} dashcam devices, offsets in [0, {TR.DEFAULT_STAGGER_S}) s")
    check("d101m robot devices register at t = 0, because the preload is at t = 0",
          all(r["start_t"] == 0.0 for r in recs
              if r["kind"] == "device_register" and r["type"] == "robot"))

    # Determinism, and the k-th robot's draw does not depend on the ratio.
    b2 = TR.generate_trace(seed, n, ratio, run_s, "A")
    b3 = TR.generate_trace(seed + 1, n, ratio, run_s, "A")
    b4 = TR.generate_trace(seed, 16, "50:50", run_s, "A")
    check("d101n the join draw is deterministic in the seed",
          b2["meta"]["robot_join"] == b["meta"]["robot_join"]
          and b3["meta"]["robot_join"] != b["meta"]["robot_join"])
    check("d101o the k-th robot's join FRACTION is the same at every ratio",
          all(abs(b4["meta"]["robot_join"][d]["join_frac"]
                  - b["meta"]["robot_join"][d]["join_frac"]) < 1e-12
              for d in set(b4["meta"]["robot_join"]) & set(b["meta"]["robot_join"])))

    # The digest covers the preload: a different holding at t = 0 is a different experiment.
    tweak = [dict(r) for r in recs]
    for r in tweak:
        if r["kind"] == "history_preload":
            r["est_tokens"] = int(r["est_tokens"]) + 1
            break
    check("d101p the fairness digest covers the preload (D101 coverage = D96 list + preload)",
          TR.fairness_digest(tweak, "A") != TR.fairness_digest(recs, "A"))

    # The emulator charges NO uplink time for a preload.
    co = _RecordingStub(capacity_per_s=1e9)
    em = EM.FleetEmulator(tmp / "d101_trace", co, "A", realtime=False)
    rm = em.run(tmp / "d101_run")
    seen = [e for e in co.seen if e["kind"] == "history_preload"]
    n_pre = sum(1 for r in recs if r["kind"] == "history_preload")
    check("d101q every preload reaches the coordinator, at t = 0, in A's field form",
          len(seen) == n_pre == rm["n_history_preload"]
          and all(e["_t_seen"] == 0.0 and e["t"] == 0.0 for e in seen)
          and all(set(e) - {"kind", "_t_seen"} == set(EV.FIELDS["history_preload"])
                  for e in seen), f"{len(seen)} preloads")
    check("d101r a preload occupies NO uplink slot and queues nothing (D101)",
          all(all(t.kind != "history_preload" for t in q.log) for q in em.queues.values())
          and rm["history_preload_uplink_bytes_charged"] == 0)
    check("d101s the run still reproduces the trace's digest for its mode with preloads in it",
          rm["digests_equal"] and rm["fairness_digest"] == meta["fairness_digest_A"])

    # The SCORER reports the preload and refuses a run whose holding at t = 0 is not the trace's.
    toy = _toy(tmp / "d101_toy")
    s = SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "toy")
    hp = s["history_preload"]
    tmeta = json.loads((toy["tdir"] / "trace_meta.json").read_text())
    check("d101t the scorer reports the preload, its sizes and the join that produced it",
          hp["n_preloads"] >= 1 and hp["all_at_t_zero"] and hp["uplink_charged"] is False
          and hp["n_robots_with_join"] == len(tmeta["robot_join"])
          and hp["est_tokens"]["min"] <= hp["est_tokens"]["median"]
          <= hp["est_tokens"]["max"] and hp["join_frac_max"] == TR.JOIN_FRAC_MAX,
          f"{hp['n_preloads']} preloads, tokens {hp['est_tokens']}")
    check("d101u the preload is NOT an opportunity and is never scored",
          all(o["kind"] in ("monitor", "recall")
              for o in SC.load(toy["tdir"], toy["rdir"]).outcomes.values()))
    rm2 = json.loads((toy["rdir"] / "run_meta.json").read_text())
    rm2["n_history_preload"] = hp["n_preloads"] + 1
    (toy["rdir"] / "run_meta.json").write_text(json.dumps(rm2, indent=2) + "\n")
    check("d101v a run whose preload count differs from its trace is REFUSED (D101)",
          _raises(lambda: SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "toy"),
                  SC.ScoringRefused))


# ---------------------------------------------------------------- (f) INTERIM-map refusal
def _final_map_doc(with_folds: bool, n_folds: int = 5) -> Dict[str, Any]:
    """A PLACEHOLDER map file in the D105 shape. NOT a refit and NOT a measurement.

    The numbers are arbitrary; what the tests use it for is the shape: label FINAL, fit_sample
    dense, and a fold assignment by clip with one map per held-out fold.
    """
    doc: Dict[str, Any] = dict(a=0.1, b=1.0, label="FINAL", fit_sample="dense",
                               fit_split="PLACEHOLDER, not a real refit",
                               compare=dict(h100_32b=dict(a=0.13, b=1.8)))
    if with_folds:
        clips = sorted(DS.nexar_clip_meta())
        doc["folds"] = dict(
            n_folds=n_folds, by="clip",
            assignment={c: i % n_folds for i, c in enumerate(clips)},
            maps={str(k): dict(device_4b_orin=dict(a=0.1 + 0.01 * k, b=1.0),
                               h100_32b=dict(a=0.13 + 0.01 * k, b=1.8))
                  for k in range(n_folds)})
    return doc


def test_d105_folds(tmp: Path) -> None:
    """D105: out-of-fold scoring, and the refusal of a pooled FINAL map."""
    pooled = tmp / "final_pooled.json"
    pooled.write_text(json.dumps(_final_map_doc(with_folds=False)))
    cal_p = DS.calibration(pooled)
    check("d105a a pooled FINAL map is REFUSED: it would score every clip in fold (D105)",
          cal_p["label"] == "FINAL" and cal_p["folds"] is None
          and _raises(lambda: SC.check_calibration(cal_p, dict(server_kind="vllm")),
                      SC.ScoringRefused))
    check("d105b a pooled map is still refused for a stub run, because FINAL is FINAL",
          _raises(lambda: SC.check_calibration(cal_p, dict(server_kind="stub")),
                  SC.ScoringRefused))
    folded = tmp / "final_folded.json"
    folded.write_text(json.dumps(_final_map_doc(with_folds=True)))
    cal = DS.calibration(folded)
    SC.check_calibration(cal, dict(server_kind="vllm"))
    clips = sorted(DS.nexar_clip_meta())
    check("d105c the fold assignment comes from the FILE, 5 folds by clip",
          cal["folds"]["n_folds"] == 5 and cal["folds"]["by"] == "clip"
          and len(cal["folds"]["assignment"]) == len(clips))
    c0, c1 = clips[0], clips[1]
    m0 = SC.map_for(cal, "device_4b_orin", c0)
    m1 = SC.map_for(cal, "device_4b_orin", c1)
    check("d105d each clip is scored with the map of the folds that EXCLUDE it",
          m0 == dict(a=0.1, b=1.0) and m1 == dict(a=0.11, b=1.0)
          and m0 != m1, f"{m0} vs {m1}")
    check("d105e a clip the file places in no fold is REFUSED, never scored pooled",
          _raises(lambda: SC.map_for(cal, "device_4b_orin", "not_a_clip"), SC.ScoringRefused))
    check("d105f a map key missing for a clip's fold is REFUSED",
          _raises(lambda: SC.map_for(cal, "no_such_tier", c0), SC.ScoringRefused))
    check("d105g an INTERIM map has no folds and is applied pooled, which the header says",
          DS.calibration()["folds"] is None
          and "pooled" in SC.calibration_use(DS.calibration())["application"]
          and SC.calibration_use(cal)["fold_fitted"] is True
          and SC.calibration_use(cal)["n_clips_assigned"] == len(clips))
    # The AP path USES the per-clip map: a stub run scored with two different fold maps on the
    # same plays cannot give the same stream.
    toy = _toy(tmp / "d105_toy")
    s = SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "toy")
    check("d105h the AP path runs under the pooled INTERIM map on a stub run (D86)",
          s["dashcam_value"]["n_plays"] > 0
          and s["calibration"]["fold_fitted"] is False)


def test_d103_h_frame_bytes(tmp: Path) -> None:
    """D103 (h): a MEASURED run must charge frame bytes from the Part-2 manifest (D91)."""
    cal_stub = DS.calibration()
    folded = tmp / "d103_final.json"
    folded.write_text(json.dumps(_final_map_doc(with_folds=True)))
    cal_fin = DS.calibration(folded)
    med = dict(frame_bytes_source="E10a committed median q90 (Part 2 not run)")
    man = dict(frame_bytes_source="Part-2 manifest /x/manifest.jsonl")
    SC.check_frame_bytes_source(med, dict(server_kind="stub"), cal_stub)
    check("d103h1 the E10a median is allowed for a flash / stub run", True)
    check("d103h2 a MEASURED run on the E10a median is REFUSED (D103 (h))",
          _raises(lambda: SC.check_frame_bytes_source(med, dict(server_kind="vllm"), cal_fin),
                  SC.ScoringRefused))
    SC.check_frame_bytes_source(man, dict(server_kind="vllm"), cal_fin)
    check("d103h3 a MEASURED run reading the Part-2 manifest is accepted", True)
    check("d103h4 a real server with an INTERIM map is not yet a measurement, so (h) does not "
          "fire there: D86's own refusal does",
          SC.is_measured_run(dict(server_kind="vllm"), cal_stub) is False
          and SC.is_measured_run(dict(server_kind="vllm"), cal_fin) is True
          and SC.is_measured_run(dict(server_kind="stub"), cal_fin) is False)
    toy = _toy(tmp / "d103h_toy")
    s = SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "toy")
    check("d103h5 the frame-bytes source is in every score header",
          s["frame_bytes_source"].startswith("E10a committed median")
          and s["is_measurement"] is False)


def test_d103_f_family(tmp: Path) -> None:
    """D103 (f): the PRIMARY family is fixed in advance; everything else is EXPLORATORY."""
    def sc(arm: str, n: int = 16, ratio: str = "50:50", mode: str = "A",
           memory: Any = "tight") -> Dict[str, Any]:
        return dict(arm=arm, n_devices=n, ratio=ratio, mode=mode, memory=memory)
    pol, base = sc("policy-core"), sc("edf")
    r = SC.classify_family(pol, base, break_sizes=(16, 24))
    check("d103f1 policy vs a round-1 baseline at a break size, tight, 50:50, push-all is "
          "PRIMARY", r["family"] == SC.PRIMARY, r["why"])
    check("d103f2 a size outside the break sizes is EXPLORATORY",
          SC.classify_family(sc("policy-core", n=64), sc("edf", n=64),
                             break_sizes=(16, 24))["family"] == SC.EXPLORATORY)
    check("d103f3 with no break sizes supplied, nothing can be PRIMARY",
          SC.classify_family(pol, base)["family"] == SC.EXPLORATORY)
    for key, bad in (("ratio", "75:25"), ("mode", "B"), ("memory", "roomy")):
        kw = {key: bad}
        check(f"d103f4 {key} = {bad!r} is EXPLORATORY",
              SC.classify_family(sc("policy-core", **kw), sc("edf", **kw),
                                 break_sizes=(16, 24))["family"] == SC.EXPLORATORY)
    check("d103f5 an unrecorded memory setting cannot be claimed as tight",
          SC.classify_family(sc("policy-core", memory=None), sc("edf", memory=None),
                             break_sizes=(16, 24))["family"] == SC.EXPLORATORY
          and "records no memory setting" in
          SC.classify_family(sc("policy-core", memory=None), sc("edf", memory=None),
                             break_sizes=(16, 24))["why"])
    check("d103f6 a comparison between two baselines is EXPLORATORY, not PRIMARY",
          SC.classify_family(sc("edf"), sc("b9"), break_sizes=(16, 24))["family"]
          == SC.EXPLORATORY)
    check("d103f7 an arm outside the round-1 seven is EXPLORATORY",
          SC.classify_family(pol, sc("edf-service-time"),
                             break_sizes=(16, 24))["family"] == SC.EXPLORATORY)
    check("d103f8 the seven baselines of D65 / D90 are the family's baseline set",
          len(SC.GPU_BASELINES) == 7 and SC.POLICY_ARM not in SC.GPU_BASELINES,
          json.dumps(list(SC.GPU_BASELINES)))
    check("d103f9 the AP-difference bootstrap is n = 1,000 (D103 (e))", SC.N_BOOT_AP == 1000)
    # The label travels with every comparison the scorer emits.
    toy = _toy(tmp / "d103f_toy")
    a = SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "policy-core")
    b = SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "edf")
    cmp_ = SC.compare(a, b)
    check("d103f10 every comparison carries its family label and the rule",
          cmp_["family"]["family"] == SC.EXPLORATORY
          and "primary family" in cmp_["family"]["rule"].lower(),
          cmp_["family"]["why"][:80])


def test_f_interim_refusal(tmp: Path) -> None:
    cal = DS.calibration()
    check("f1 the committed orin2_calibration.json is labelled INTERIM (D86)",
          cal["label"] == "INTERIM", cal["sha256"][:16])
    SC.check_calibration(cal, dict(server_kind="stub"))
    check("f2 an INTERIM map MAY score a stub run (flash tests only)", True)
    for kind in ("vllm", "h100", None, "real"):
        try:
            SC.check_calibration(cal, dict(server_kind=kind))
            check(f"f3 an INTERIM map is REFUSED for a non-stub run ({kind!r})", False,
                  "no refusal raised")
        except SC.ScoringRefused:
            check(f"f3 an INTERIM map is REFUSED for a non-stub run ({kind!r})", True)
    fake = tmp / "final_map.json"
    fake.write_text(json.dumps(_final_map_doc(with_folds=True)))
    cal2 = DS.calibration(fake)
    check("f4 a map is FINAL only when it declares label FINAL AND fit_sample dense",
          cal2["label"] == "FINAL")
    SC.check_calibration(cal2, dict(server_kind="vllm"))
    check("f5 a FINAL map that carries its folds may score a non-stub run", True)
    half = tmp / "half_map.json"
    half.write_text(json.dumps(dict(a=0.1, b=1.0, label="FINAL")))
    check("f6 label FINAL without a dense fit_sample is still INTERIM",
          DS.calibration(half)["label"] == "INTERIM")
    toy = _toy(tmp / "f_toy")
    rm = json.loads((toy["rdir"] / "run_meta.json").read_text())
    rm["server_kind"] = "vllm"
    (toy["rdir"] / "run_meta.json").write_text(json.dumps(rm, indent=2) + "\n")
    try:
        SC.score_run(toy["tdir"], toy["rdir"], DS.ORIN_CALIBRATION, "would_be_measured")
        check("f7 score_run refuses a non-stub run with the INTERIM map", False)
    except SC.ScoringRefused as e:
        check("f7 score_run refuses a non-stub run with the INTERIM map", True,
              str(e).splitlines()[0][:90])


# ---------------------------------------------------------------- (g2) D97 measurability
def test_g2_d97(tmp: Path) -> None:
    # A size eligible at seeds 1 and 2 but NOT 3 must be excluded from a comparison that
    # reports all three (D97).
    t = {"50:50": {8: {1: True, 2: True, 3: False},
                   16: {1: True, 2: True, 3: True},
                   24: {1: True, 2: False, 3: True},
                   32: {1: True, 2: True, 3: True}}}
    r = SC.d97_sweep_sizes(t, "50:50")
    check("g2a a size eligible at seeds 1-2 but not 3 is EXCLUDED (D97)",
          r["per_size"][8]["label"] == SC.NOT_MEASURABLE
          and r["per_size"][8]["reason"].endswith("[3]")
          and 8 not in r["included_sizes"], r["per_size"][8]["reason"])
    check("g2b the entry point is the smallest size eligible at EVERY reported seed",
          r["entry_point"] == 16 and r["included_sizes"] == [16, 32], str(r["entry_point"]))
    check("g2c a larger ineligible size is reported as non-monotone, not assumed eligible",
          r["non_monotone_sizes_above_entry"] == [24] and not r["monotone"])
    check("g2d eligibility at a SUBSET of seeds does not include the size by averaging",
          all(not r["per_size"][n]["included"] for n in (8, 24)))
    r2 = SC.d97_sweep_sizes(t, "50:50", seeds=(1, 2))
    check("g2e with only seeds 1-2 reported, the rule applies to THAT set",
          r2["included_sizes"] == [8, 16, 32] and r2["entry_point"] == 8,
          "D79 makes a third seed conditional, so the set is whatever is reported")
    miss = SC.d97_sweep_sizes({"50:50": {8: {1: True, 2: True}}}, "50:50")
    check("g2f a size with no trace for a reported seed is NOT measurable, not assumed",
          not miss["per_size"][8]["included"]
          and miss["per_size"][8]["missing_seeds"] == [3],
          miss["per_size"][8]["reason"])
    pil = SC.d97_pilot_labels({"50:50": {8: {0: False}, 16: {0: True}}}, "50:50")
    check("g2g a PILOT run never yields an entry point (D95 (7), D97)",
          pil["entry_point"] is None and "entry_point" in pil
          and pil["per_size"][8] == "not measurable at seed 0"
          and pil["per_size"][16] == "measurable at seed 0")
    check("g2h the pilot seed may not appear in a reported seed set",
          _raises(lambda: SC.d97_sweep_sizes(t, "50:50", seeds=(0, 1, 2)), SC.ScoringRefused))
    # The table is built from TRACE metadata alone: no run, no server, no GPU (D97).
    b = TR.generate_trace(2, 8, "25:75", 600.0, "A")
    TR.write_trace(tmp / "g2_trace", b)
    tab = SC.eligibility_table([tmp / "g2_trace"])
    nq = b["stats"]["robot_questions_total"]
    check("g2i the eligibility table is read from trace metadata, with no run at all",
          tab["25:75"][8][2] == (nq >= SC.ROB_MIN_QUESTIONS),
          f"{nq} pooled questions vs the minimum of {SC.ROB_MIN_QUESTIONS}")


# ---------------------------------------------------------------- (h) count_only equivalence
def test_h_count_only() -> None:
    for seed, n, ratio, run_s in ((1, 8, "50:50", 600.0), (2, 17, "75:25", 600.0),
                                  (3, 33, "25:75", 300.0), (0, 5, "50:50", 600.0)):
        full = TR.generate_trace(seed, n, ratio, run_s, "A")["stats"]
        cheap = TR.generate_trace(seed, n, ratio, run_s, "A", count_only=True)["stats"]
        check(f"h seed {seed} n {n} {ratio}: count_only stats are IDENTICAL to the full build",
              full == cheap,
              f"{full['robot_questions_total']} robot questions, "
              f"{full['dashcam_meeting_200']} dashcam devices over 200 instants")
    # The rounding rule for odd sizes, stated rather than assumed.
    splits = {n: TR._split_fleet(n, "50:50") for n in (4, 5, 6, 7, 9, 11)}
    check("h2 odd sizes split by round-half-to-even, which does not alternate regularly",
          splits[5] == (2, 3) and splits[7] == (4, 3) and splits[9] == (4, 5)
          and splits[11] == (6, 5), json.dumps({k: list(v) for k, v in splits.items()}))


# ---------------------------------------------------------------- schema
def test_schema() -> None:
    r = EV.check_against_schema()
    check("s1 fleet/events.py field lists are identical to live2/schema.py",
          r.get("schema_present") and r.get("note") == "field lists identical",
          json.dumps(r.get("compared")))
    check("s2 events.make rejects an unknown field",
          _raises(lambda: EV.make("session_start", device_id="d", session_id="s", t=0.0,
                                  extra=1), ValueError))
    check("s3 events.make rejects a missing field",
          _raises(lambda: EV.make("session_start", device_id="d", session_id="s"), ValueError))
    check("s4 opportunity_id_of READS the assigned id (D96 (1)), never constructs one",
          EV.opportunity_id_of(dict(kind="recall_question", session_id="S", question_id="Q",
                                    opportunity_id="opp0000042")) == "opp0000042")
    check("s4b an opportunity event with no opportunity_id is refused (D96 (1))",
          _raises(lambda: EV.opportunity_id_of(
              dict(kind="recall_question", session_id="S", question_id="Q")), ValueError))
    check("s4c schema.py carries opportunity_id on all three opportunity events (D96 (1))",
          not r.get("d96_pending"),
          json.dumps(r.get("pending")) if r.get("d96_pending") else "landed")
    check("s5 the scorer treats both 'stub' and 'fake' as non-measurement servers",
          SC.NON_MEASUREMENT_SERVERS == ("stub", "fake"))


def _raises(fn, exc) -> bool:
    try:
        fn()
        return False
    except exc:
        return True


# ---------------------------------------------------------------- main
def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="live2_fleet_tests_"))
    print(f"scratch: {tmp}\n")
    try:
        test_schema()
        test_a_determinism(tmp)
        test_b_fairness(tmp)
        test_c_links()
        test_d_scorer(tmp)
        test_e_sessions(tmp)
        test_d101_join(tmp)
        test_f_interim_refusal(tmp)
        test_d105_folds(tmp)
        test_d103_h_frame_bytes(tmp)
        test_d103_f_family(tmp)
        test_g2_d97(tmp)
        test_h_count_only()
    finally:
        n_ok = sum(1 for _n, ok, _d in RESULTS if ok)
        print(f"\n{n_ok}/{len(RESULTS)} checks passed")
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if all(ok for _n, ok, _d in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
