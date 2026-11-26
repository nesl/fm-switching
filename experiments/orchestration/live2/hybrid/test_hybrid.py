#!/usr/bin/env python3
"""Hybrid (D138) proofs on DRY runs (no server):
  1. BASE == b7-edf-feasibility: decision logs byte-identical except the arm name and timing fields,
     on several seeds and sizes.
  2. MOVE PROOF (CLAUDE.md Step 2b): each switch configuration vs the base on one cell: number of differing
     decisions and the first one. A configuration with ZERO differing decisions is an ABSENT LINK.
Usage: python test_hybrid.py identity | moves | pairs | dry   (writes results/orchestration/live2/hybrid/*.json)

The `test_*` functions in this file are collected by pytest and write ONLY to pytest's `tmp_path`:
nothing under results/ is read-modified-written by them, because the committed proof JSONs there were
produced on the H100 and a regeneration from a working tree would silently replace them. The CLI entry
points keep writing to results/ as before, which is the committed workflow."""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
REPO = LIVE2.parents[2]
for p in (HERE, LIVE2, LIVE2 / "fleet", LIVE2 / "tests",
          REPO / "experiments/orchestration", REPO / "experiments/orchestration/baselines",
          REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    sys.path.insert(0, str(p))
OUT = REPO / "results/orchestration/live2/hybrid"
STRIP = ("arm", "decision_latency_ms", "decision_id")


def dry(arm_name, seed, n, run_s=120.0, ratio="50:50", patch=None,
        robot_question_set="eval", ss_question_set="ss1",
        dashcam_format="oneframe", dashcam_min_frames=None,
        robot_upload="batch-30s", robot_reask_mean_s=0.0,
        outage_robots_k=0, outage_duration_s=0.0, outage_seed_offset=0,
        outage_placement="band", outage_semantics="buffered",
        outage_t0_s=None, link_events=False, link_sync=False, keep_dir=None):
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import emulator as EM
    import hybrid  # noqa: F401
    import trace as TR
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # The workload knobs are forwarded so a dry proof can run the SAME workload the live
        # cells run. They default to the committed values, so every existing caller is unchanged:
        # oneframe dashcam, batch-30s upload, no re-asks. Forwarding them matters because D160 (1)
        # is a fix to PER-FRAME upload behaviour, and a dry run left on batch-30s cannot exhibit
        # the problem it fixes (measured: v5-rules issues 827 pieces on batch-30s against about
        # 84,000 per-frame, so a chunking proof run on the default would be measuring nothing).
        _kw = dict(robot_question_set=robot_question_set, ss_question_set=ss_question_set)
        if dashcam_format != "oneframe":
            _kw["dashcam_format"] = dashcam_format
            if dashcam_min_frames is not None:
                _kw["dashcam_min_frames"] = int(dashcam_min_frames)
        if robot_upload != "batch-30s":
            _kw["robot_upload"] = robot_upload
        if float(robot_reask_mean_s) > 0.0:
            _kw["robot_reask_mean_s"] = float(robot_reask_mean_s)
        # D242 A / D266 item 2: passed ONLY when the outage is on, and the placement passed only
        # when it is not the committed default, so a defaulted call is the committed call argument
        # for argument and the off-by-default identity proof is not weakened by this forwarding.
        if int(outage_robots_k) > 0 and float(outage_duration_s) > 0.0:
            _kw["outage_robots_k"] = int(outage_robots_k)
            _kw["outage_duration_s"] = float(outage_duration_s)
            _kw["outage_seed_offset"] = int(outage_seed_offset)
            if outage_placement != "band":
                _kw["outage_placement"] = str(outage_placement)
            if outage_semantics != "buffered":
                _kw["outage_semantics"] = str(outage_semantics)
            if outage_placement == "evidence":
                _kw["outage_t0_s"] = float(outage_t0_s)
            if link_events:
                _kw["outage_link_marks"] = True
        TR.write_trace(d / "t", TR.generate_trace(seed, n, ratio, run_s, "A", **_kw))
        arm = A.make_arm(arm_name)
        if link_sync:
            import link_sync as _LS
            link_sync = bool(_LS.arm_controls_sync(arm))
        if patch is not None:
            patch(arm)
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                            targets=CS.TARGETS)
        logs = Logs(d / "r").open()
        co = Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                              host_tier_tokens=HOST_TOK, upload_mode="A", window_s=run_s, drain_s=5.0,
                              seed=seed, logs=logs, run_tag=CK.run_tag(seed, "x"), dry_run=True,
                              **({} if not link_events else dict(link_events=True)),
                              **({} if not link_sync else dict(link_sync=True)))
        br = EmulatorBridge(co)
        br.kind = "stub"
        em = EM.FleetEmulator(d / "t", br, "A", realtime=False, drain_s=5.0,
                              **({} if not link_events else dict(link_events=True)),
                              **({} if not link_sync else dict(link_sync_hold=True)))
        em.run(d / "r")
        if keep_dir is not None:
            co.write_link_log(d / "r")
            import shutil
            shutil.copytree(d / "r", keep_dir, dirs_exist_ok=True)
        dry.last = dict(arm=arm, co=co, em=em, trace_meta=em.meta)
        logs.close()
        rows = [json.loads(l) for l in open(d / "r" / "decision.jsonl")]
    return [{k: v for k, v in r.items() if k not in STRIP} for r in rows], getattr(arm, "stats", None)


def _differing(a, b):
    """POSITIONAL mismatch. Order-sensitive on purpose for the identity proofs, where byte-identity
    including order is the claim. It is the WRONG register for "did this switch move a decision":
    one early divergence desynchronises the rest of the log, and a pure transposition of two rows
    inside one period counts as 2 while nothing was decided differently. Use _differing_setwise for
    a move proof. (Found by the value-term control: its only non-zero cell, 2 of 16,361, was two
    release_recall rows swapping places at t=527.0 with both items released either way.)"""
    return sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))


def _decision_key(r):
    """What was decided, independent of where it sits in the log: the period, the action kind, the
    opportunities it acts on, and the representation chosen."""
    return (r.get("t"), r.get("kind"), tuple(r.get("opportunity_ids") or ()),
            r.get("representation"), r.get("defer_s"))


def _differing_setwise(a, b):
    """Decisions present in one log and not the other, as a multiset difference over _decision_key.
    A reordering scores 0; an admit that became a defer scores 2 (one gone, one new)."""
    from collections import Counter
    ca, cb = Counter(_decision_key(r) for r in a), Counter(_decision_key(r) for r in b)
    return sum(((ca - cb) + (cb - ca)).values())


def _identity_rows(cells):
    out = []
    for seed, n in cells:
        a, _ = dry("hybrid-base", seed, n)
        b, _ = dry("b7-edf-feasibility", seed, n)
        same = a == b
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
        out.append(dict(seed=seed, n=n, decisions=len(a), b7_decisions=len(b), identical=same, first_diff=first))
        print(out[-1], flush=True)
    return out


def identity(out_dir=OUT):
    out = _identity_rows(((0, 8), (0, 12), (4, 10), (5, 16)))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hybrid_identity.json").write_text(json.dumps(out, indent=1) + "\n")
    if not all(x["identical"] for x in out):
        raise SystemExit("BASE IS NOT byte-identical to b7")


def _moves_rows(seed, n):
    import hybrid
    base, _ = dry("hybrid-base", seed, n)
    out = []
    for name in hybrid.CONFIGS:
        if name == "hybrid-base":
            continue
        rows, stats = dry(name, seed, n)
        diff = _differing(base, rows)
        first = next(((i, base[i], rows[i]) for i, (x, y) in enumerate(zip(base, rows)) if x != y), None)
        out.append(dict(config=name, seed=seed, n=n, base_decisions=len(base), decisions=len(rows),
                        differing=diff, absent_link=(diff == 0), stats=dict(stats or {}),
                        first_diff=(dict(index=first[0], base=first[1], cfg=first[2]) if first else None)))
        print(name, "differing", diff, "stats", dict(stats or {}), flush=True)
    return out


def moves(seed=0, n=12, out_dir=OUT):
    out = _moves_rows(seed, n)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "hybrid_moves.json").write_text(json.dumps(out, indent=1, default=str) + "\n")


PAIRS = [("C1 under the cap", "hybrid-c5", "hybrid-c1c5"),
         ("k_r 1.0 vs 2.0", "hybrid-c1c2k1", "hybrid-c1c2k2"),
         ("C3 (k_r 1.0)", "hybrid-c1c2k1", "hybrid-c1c2k1c3"),
         ("C3 (k_r 2.0)", "hybrid-c1c2k2", "hybrid-c1c2k2c3"),
         ("C2 (vs C1)", "hybrid-c1", "hybrid-c1c2k1")]


def _pairs_rows(seed, n, pairs=None):
    cache, out = {}, []
    for label, a, b in (pairs or PAIRS):
        for x in (a, b):
            if x not in cache:
                cache[x] = dry(x, seed, n)
        ra, rb = cache[a][0], cache[b][0]
        diff = _differing(ra, rb)
        out.append(dict(comparison=label, a=a, b=b, differing=diff, absent_link=(diff == 0),
                        stats_b=dict(cache[b][1] or {})))
        print(label, a, "vs", b, "differing", diff, dict(cache[b][1] or {}), flush=True)
    return out


def pairs(seed=0, n=12, out_dir=OUT):
    """Step 2b on the comparisons the screening actually makes: each component against its neighbour."""
    out = _pairs_rows(seed, n)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "hybrid_pairs.json").write_text(json.dumps(out, indent=1, default=str) + "\n")


# ---- pytest tests ---------------------------------------------------------------------------------
# Small cells, tmp_path writes only, and development seeds 0 and 4 only: 1, 2 and 3 are holdout and
# must never appear here.

SMALL_RUN_S = 60.0


def test_base_identity_matches_b7(tmp_path):
    """The one property whose failure stops the freeze: every switch off must reproduce b7 exactly."""
    rows = _identity_rows(((0, 6), (4, 8)))
    (tmp_path / "hybrid_identity.json").write_text(json.dumps(rows, indent=1) + "\n")
    assert rows and all(r["decisions"] > 0 for r in rows)
    bad = [r for r in rows if not r["identical"]]
    assert not bad, "hybrid-base is NOT byte-identical to b7-edf-feasibility: %r" % (bad,)


def test_ss_absent_identity(tmp_path):
    """With a two-class ratio there are no single-shot devices, so the SS wiring must be inert: no SS
    request is seen, and emptying the SS declared input leaves every decision unchanged."""
    live, stats = dry("hybrid-F", 0, 6, SMALL_RUN_S, ratio="50:50")

    def strip_ss(arm):
        arm._ss_tbl = {}
        arm._ss_types = frozenset()
        arm._ss_values = {}
        arm._ss_placeholder = False

    inert, _ = dry("hybrid-F", 0, 6, SMALL_RUN_S, ratio="50:50", patch=strip_ss)
    (tmp_path / "ss_absent.json").write_text(json.dumps(dict(
        decisions=len(live), differing=_differing(live, inert), stats=dict(stats or {})), indent=1) + "\n")
    assert len(live) > 0
    assert dict(stats or {}).get("ss_seen", 0) == 0
    assert _differing(live, inert) == 0


def test_frozen_configs_registered_and_construct():
    import arms as A
    import hybrid
    for name in ("hybrid-F", "hybrid-F6", "hybrid-F-lhreq", "hybrid-F6-lhreq"):
        assert name in hybrid.CONFIGS
        assert name in A.ARMS
        arm = A.make_arm(name)
        assert arm.name == name
        assert arm.sw["c1"] and arm.sw["c2"] and arm.sw["c3"] and arm.sw["c5"] and not arm.sw["c4"]
        assert arm.defs == "v2" and arm.k_r == 1.5 and arm.throttle_floor == 2 and not arm.c3_always
    assert A.make_arm("hybrid-F6").sw["c6"] and not A.make_arm("hybrid-F").sw["c6"]
    assert A.make_arm("hybrid-F").workload == "mixed"
    assert A.make_arm("hybrid-F-lhreq").workload == "lh_req"


def test_frozen_config_moves_decisions():
    """Step 2b: hybrid-F must reach a decision the base does not, or the switches are an ABSENT LINK."""
    base, _ = dry("hybrid-base", 0, 6, SMALL_RUN_S)
    f, _ = dry("hybrid-F", 0, 6, SMALL_RUN_S)
    assert _differing(base, f) > 0


def test_lh_req_workload_changes_the_value_term():
    import hybrid_arm as HA
    import pytest
    mixed, lh = HA._quality_values("mixed"), HA._quality_values("lh_req")
    assert mixed["recall"] > 0 and lh["recall"] > 0
    assert mixed["recall"] != lh["recall"]
    with pytest.raises(ValueError):
        HA.HybridArm(name="x", workload="not-a-workload")


def test_c6_actually_fires_on_the_lh_req_workload():
    """CLAUDE.md "Citing results": a port's characteristic decision must occur at least once.

    This test exists because it did not. _c6_prepare swallowed every exception into a counter, so an
    incomplete LH-REQ DEV key map raised MissingEvidence on representation N1 at the device tier on
    EVERY period, C6 never reached _c6_one, and hybrid-F6-lhreq was decision-identical to
    hybrid-F-lhreq at all six smoke cells while live2_describe still reported c6=True.
    """
    f, sf = dry("hybrid-F-lhreq", 0, 20, 600.0, ratio="40:40:20",
                robot_question_set="lh_req", ss_question_set="ss2")
    f6, s6 = dry("hybrid-F6-lhreq", 0, 20, 600.0, ratio="40:40:20",
                 robot_question_set="lh_req", ss_question_set="ss2")
    assert (s6 or {}).get("c6_scorer_error", 0) == 0, "the C6 mirror is raising, not deciding"
    assert (s6 or {}).get("c6_calls", 0) > 0, "C6 never reached a candidate set"
    assert _differing(f, f6) > 0, "C6 moved no decision: ABSENT LINK, not a negative"


def test_lh_req_dev_fit_covers_every_condition_the_policy_reads():
    """The escalation path reads five (tier, representation) conditions. The LH-REQ DEV fit measures
    three. Every one of the five must resolve, and every stand-in must be declared."""
    import arms_policy as AP
    from policy.profiles import _RC_TABLE_NAME, load_profiles
    pf = AP._LhReqFittedProfiles(load_profiles())
    for tier, rep in _RC_TABLE_NAME:
        v = pf.rc_accuracy("location_trace", rep, tier)
        assert 0.0 <= v <= 1.0
    declared = set(AP._LhReqFittedProfiles._SUBSTITUTED)
    measured = {("D2", "cloud"), ("RECENT", "cloud")}
    asked = {(rep, tier) for tier, rep in _RC_TABLE_NAME}
    assert asked - measured == declared, "an undeclared substitution: %s" % (asked - measured - declared)


if __name__ == "__main__":
    {"identity": identity, "moves": moves, "pairs": pairs,
     "dry": lambda: print(len(dry(sys.argv[2] if len(sys.argv) > 2 else "hybrid-base",
                                  int(sys.argv[3]) if len(sys.argv) > 3 else 0,
                                  int(sys.argv[4]) if len(sys.argv) > 4 else 8)[0]))}[sys.argv[1]]()
