#!/usr/bin/env python3
"""StudyLIVE2-fix: the checks D98, D99, D100 and D102 need, on flash, CPU only.

NOTHING HERE IS A MEASUREMENT. Every cell is a `--dry-run` on a SYNTHETIC trace with the
committed cost curve as the service time; every result file carries `is_measurement: false`.
The quantities that mean anything are the coordinator's OWN (decision latency, CPU, decisions)
and the policy's own arithmetic (admit / decline counts and DeltaJ).

  sh-admission   D98 test (a): SH escalated / admitted / declined and the DeltaJ distribution of
                 admits and declines at H = 0.5 s and H = 1.0 s on the issue-1 fixture
                 (2 dashcams + 1 robot, 60 s, mu = 0).
  equivalence    D99 (2): the optimized policy's decision log is IDENTICAL to the unoptimized
                 post-D98 policy's (`--policy-impl reference`), excluding latency fields, on
                 4 and 8 devices x 3 seeds x 120 s.
  speed          D99 (3): decision time p50 / p99 / max, CPU, epoch overruns and opportunities
                 served at 32, 64 and 128 devices (50 : 50, mode A, tight memory, 180 s).
  parity         D100: the partial-readiness cost check at StudyENG1's 11,184-token history and
                 the two-dashcam starvation check.
"""
import argparse
import json
import statistics as st
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                      # noqa: E402
import cachekeys as CK                                                # noqa: E402
import calib as CALIB                                                 # noqa: E402
import cstate as CS                                                   # noqa: E402
import schema as SC                                                   # noqa: E402
import traces as T                                                    # noqa: E402
from coordinator import DECISION_PERIOD_S, Live2Coordinator, Logs      # noqa: E402

GPU_KV = 62_944          # D76 tight
HOST_GIB = 27.0
HOST_TOK = 48_000
DEFAULT_OUT = ROOT / "results/orchestration/live2/coord/fix"

# The fields a decision log line may legitimately differ in between two implementations of the
# SAME decisions: wall-clock measurements of the decision itself.
LATENCY_FIELDS = ("decision_latency_ms",)


def _arm(h: float = 1.0, impl: str = "fast", mu: str = "none", d: Optional[Path] = None,
         cap_k: Optional[int] = None):
    a = A.make_arm("policy-core", h_s=h, mu_mode=mu, impl=impl, cap_k=cap_k)
    d = d or Path(tempfile.mkdtemp())
    a.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                      targets=CS.TARGETS,
                      calibration_knots_path=CALIB.write_knots(CALIB.load_map(), d / "k.json"))
    return a


def _cell(*, n_dashcam: int, n_robot: int, window_s: float, seed: int = 1, h: float = 1.0,
          impl: str = "fast", mu: str = "none", mode: str = "A", out: Optional[Path] = None,
          cap_k: Optional[int] = None,
          max_wall_s: Optional[float] = None) -> Dict[str, Any]:
    """One dry-run cell. Returns the coordinator's result plus the decision-log path."""
    tr = T.synthetic(n_dashcam=n_dashcam, n_robot=n_robot, duration_s=window_s, seed=seed,
                     upload_mode=mode)
    d = Path(out) if out else Path(tempfile.mkdtemp())
    d.mkdir(parents=True, exist_ok=True)
    a = _arm(h=h, impl=impl, mu=mu, d=d, cap_k=cap_k)
    logs = Logs(d).open()
    co = Live2Coordinator(a, None, tr["events"], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                          host_tier_tokens=HOST_TOK, upload_mode=mode, window_s=window_s,
                          drain_s=15.0, seed=seed, logs=logs,
                          run_tag=CK.run_tag(seed, "policy-core"), dry_run=True,
                          max_wall_s=max_wall_s)
    t0 = time.time()
    res = co.run()
    logs.close()
    res["fairness_digest"] = tr["fairness_digest"]
    res["wall_measured_s"] = round(time.time() - t0, 3)
    res["decision_log"] = str(d / "decision.jsonl")
    res["arm_stats"] = dict(a.stats)
    return res


def _dist(xs: List[float]) -> Dict[str, Any]:
    if not xs:
        return dict(n=0)
    return dict(n=len(xs), min=round(min(xs), 6), p25=round(_q(xs, 0.25), 6),
                median=round(st.median(xs), 6), p75=round(_q(xs, 0.75), 6),
                max=round(max(xs), 6), mean=round(st.fmean(xs), 6))


def _q(xs: List[float], p: float) -> float:
    s = sorted(xs)
    return s[min(int(p * len(s)), len(s) - 1)]


# ---------------------------------------------------------------- D98 test (a)
def sh_admission(out: Path) -> Dict[str, Any]:
    """The issue-1 fixture, which is where the structural zero was measured."""
    rows = []
    # The issue-1 fixture at both H, then a CONGESTED variant: the issue-1 fixture never
    # saturates the modelled engine, so it produces no declines at all, and a table with no
    # declines does not show that the decline side is alive.
    cells = [(0.5, 2, 1, "issue-1 fixture"), (1.0, 2, 1, "issue-1 fixture"),
             (0.5, 8, 2, "congested: 10 devices on one modelled GPU"),
             (1.0, 8, 2, "congested: 10 devices on one modelled GPU")]
    for h, nd, nr, label in cells:
        res = _cell(n_dashcam=nd, n_robot=nr, window_s=60.0, seed=1, h=h,
                    out=out / ("h%.1f_d%d" % (h, nd)))
        s = res["arm_stats"]
        rows.append(dict(
            H=h, fixture=label, n_dashcam=nd, n_robot=nr,
            sh_escalated=s.get("sh_escalated", 0), sh_admitted=s.get("sh_admitted", 0),
            sh_declined=s.get("sh_declined", 0),
            delta_j_admits=_dist(s.get("sh_delta_j_admit", [])),
            delta_j_declines=_dist(s.get("sh_delta_j_decline", [])),
            n_requests=res["n_requests"], n_monitor_answers=res["n_monitor_answers"],
            n_on_time=res["n_on_time"], n_decisions=res["n_decisions"],
            fairness_digest=res["fairness_digest"]))
    return dict(check="d98_sh_admission", is_measurement=False,
                fixture="SYNTHETIC, 60 s, mu = 0, mode A, tight memory, seed 1, dry run. The "
                        "first two rows are the StudyLIVE2-coord open issue 1 fixture "
                        "(2 dashcam + 1 robot); the last two are a congested variant "
                        "(8 dashcam + 2 robot), which is where declines appear at all.",
                decision_period_s=DECISION_PERIOD_S, rows=rows,
                note="Before D98, H = 0.5 s admitted 0 of 240 instants with DeltaJ exactly 0.0 "
                     "on every one, while H = 1.0 s admitted 240 of 240.")


# ---------------------------------------------------------------- D99 (2)
def _strip(path: Path) -> List[str]:
    out = []
    for rec in SC.iter_jsonl(path):
        for f in LATENCY_FIELDS:
            rec.pop(f, None)
        out.append(json.dumps(rec, sort_keys=True))
    return out


def equivalence(out: Path) -> Dict[str, Any]:
    rows = []
    ok = True
    for n in (4, 8):
        for seed in (1, 2, 3):
            paths = {}
            stats = {}
            for impl in ("reference", "fast"):
                d = out / f"n{n}_seed{seed}_{impl}"
                res = _cell(n_dashcam=n // 2, n_robot=n - n // 2, window_s=120.0, seed=seed,
                            h=1.0, impl=impl, out=d)
                paths[impl] = Path(res["decision_log"])
                stats[impl] = dict(n_decisions=res["n_decisions"], n_requests=res["n_requests"],
                                   p50_ms=res["decision_latency_ms"]["p50"],
                                   wall_s=res["wall_measured_s"])
            a, b = _strip(paths["reference"]), _strip(paths["fast"])
            same = a == b
            first_diff = None
            if not same:
                for i, (x, y) in enumerate(zip(a, b)):
                    if x != y:
                        first_diff = dict(line=i, reference=x[:400], fast=y[:400])
                        break
                if first_diff is None:
                    first_diff = dict(line=min(len(a), len(b)), reference_lines=len(a),
                                      fast_lines=len(b))
            ok = ok and same
            rows.append(dict(n_devices=n, seed=seed, n_lines=len(a), identical=same,
                             first_difference=first_diff,
                             speedup=(round(stats["reference"]["wall_s"]
                                            / max(stats["fast"]["wall_s"], 1e-9), 2)),
                             reference=stats["reference"], fast=stats["fast"]))
    return dict(check="d99_equivalence", is_measurement=False, all_identical=ok,
                excluded_fields=list(LATENCY_FIELDS),
                fixture="SYNTHETIC 50 : 50, 120 s, mode A, tight memory, mu = 0, H = 1.0 s, "
                        "dry run", decision_period_s=DECISION_PERIOD_S, rows=rows)


# ---------------------------------------------------------------- D99 (3)
def speed(out: Path, sizes=(32, 64, 128), window_s: float = 180.0,
          max_wall_s: Optional[float] = None, cap_k: Optional[int] = None) -> Dict[str, Any]:
    rows = []
    for n in sizes:
        res = _cell(n_dashcam=n // 2, n_robot=n - n // 2, window_s=window_s, seed=1, h=1.0,
                    out=out / ("n%d" % n), max_wall_s=max_wall_s, cap_k=cap_k)
        rows.append(dict(n_devices=n, n_opportunities=res["n_opportunities"],
                         n_decisions=res["n_decisions"], n_requests=res["n_requests"],
                         n_monitor_answers=res["n_monitor_answers"],
                         n_recall_answers=res["n_recall_answers"],
                         release_cap_k=cap_k,
                         n_cloud_answers=res["n_cloud_answers"],
                         n_on_time=res["n_on_time"],
                         cap_bound=dict(
                             sh_periods=res["arm_stats"].get("sh_cap_bound_periods"),
                             sh_skipped=res["arm_stats"].get("sh_cap_skipped"),
                             release_passes=res["arm_stats"].get("release_cap_bound_passes"),
                             release_skipped=res["arm_stats"].get("release_cap_skipped_items")),
                         scoring_calls=res["arm_stats"].get("scoring_calls"),
                         decision_latency_ms=res["decision_latency_ms"],
                         cpu_s=res["cpu_s"], cpu_percent=res["cpu_percent"],
                         wall_s=res["wall_measured_s"],
                         epoch_overruns=res["epoch_overruns"],
                         virtual_t_reached_s=res["virtual_t_reached_s"],
                         wall_guard_hit=res["wall_guard_hit"],
                         target_p99_under_100ms=bool(
                             res["decision_latency_ms"]["p99"] is not None
                             and res["decision_latency_ms"]["p99"] < 100.0)))
    return dict(check="d99_speed", is_measurement=False,
                fixture="SYNTHETIC 50 : 50, mode A, tight memory (gpu_kv_tokens = %d, "
                        "host_tier_gib = %.0f), %.0f s, mu = 0, H = 1.0 s, dry run with the "
                        "committed cost curve (pol4)" % (GPU_KV, HOST_GIB, window_s),
                decision_period_s=DECISION_PERIOD_S,
                target="p99 decision time under 100 ms at 128 devices (D99 (3))",
                release_cap_k=cap_k,
                host_cpu="13th Gen Intel Core i7-13700KF, 16 cores / 24 threads (flash). The "
                         "H100 host's CPU differs and the pilot re-measures there.",
                rows=rows)


# ---------------------------------------------------------------- D100
def parity(out: Path) -> Dict[str, Any]:
    """(a) a later piece on a warm prefix costs less than a cold rebuild of the same tokens;
    (b) with the per-instant deadline on the wire, pi_0 serves BOTH dashcams."""
    from policy.profiles import load_profiles
    from policy.eng1_engine import Eng1Engine
    from policy.engine import Request
    pf = load_profiles()
    eng = Eng1Engine.load(gpu_kv_tokens=GPU_KV, host_kv_tokens=HOST_TOK, profiles=pf,
                          engine_model="pol4")
    tokens = 11_184                 # StudyENG1's D2 history
    piece = 1024
    built = tokens - piece          # the prefix already built when the LAST piece is costed
    warm = eng.predict(Request(kind="rc_piece", device="d0", tokens=piece, frames=0,
                               readiness="GPU-WARM", job_id="j",
                               meta=dict(cached_tokens=built)), concurrent=0, load_pct=25)
    cold = eng.predict(Request(kind="rc_piece", device="d0", tokens=tokens, frames=0,
                               readiness="COLD", job_id="j"), concurrent=0, load_pct=25)
    a = dict(history_tokens=tokens, piece_tokens=piece, built_prefix_tokens=built,
             cost_model="pol4 (frozen)",
             warm_basis="readiness GPU-WARM with cached_tokens = the built prefix, which is "
                        "exactly what the arm sets on the item (D100 (a))",
             piece_on_warm_prefix_s=round(warm.service_s, 6),
             cold_rebuild_of_the_same_tokens_s=round(cold.service_s, 6),
             piece_is_cheaper=bool(warm.service_s < cold.service_s))
    rows = []
    for arm_name in ("edf", "edf-piece1024", "edf-piece2048"):
        tr = T.synthetic(n_dashcam=2, n_robot=0, duration_s=60.0, seed=1, upload_mode="A")
        arm = A.make_arm(arm_name)
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        d = out / ("starve_" + arm_name)
        logs = Logs(d).open()
        co = Live2Coordinator(arm, None, tr["events"], gpu_kv_tokens=GPU_KV,
                             host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK, upload_mode="A",
                             window_s=60.0, drain_s=15.0, seed=1, logs=logs,
                             run_tag=CK.run_tag(1, arm_name), dry_run=True)
        res = co.run()
        logs.close()
        per_dev: Dict[str, int] = {}
        for ans in co.answers:
            if ans["kind"] == "monitor":
                per_dev[ans["device_id"]] = per_dev.get(ans["device_id"], 0) + 1
        rows.append(dict(arm=arm_name, monitor_answers_by_device=dict(sorted(per_dev.items())),
                         n_devices_served=len(per_dev), n_requests=res["n_requests"],
                         both_devices_served=bool(len(per_dev) == 2)))
    return dict(check="d100_information_parity", is_measurement=False,
                partial_readiness=a, starvation=dict(
                    fixture="SYNTHETIC 2 dashcams, 0 robots, 60 s, mode A, dry run",
                    note="Before D100 pi_0 had no per-instant deadline, every stream tied on "
                         "now + L, and the tie-break by item_id served one dashcam 240 times "
                         "and the other none.",
                    rows=rows),
                decision_period_s=DECISION_PERIOD_S)


# ---------------------------------------------------------------- D99 (4)
def cap(out: Path, ks=(1, 2, 4, 8), at_devices: int = 128, window_s: float = 180.0,
        max_wall_s: Optional[float] = None) -> Dict[str, Any]:
    """D99 (4), run ONLY if (2) misses the target: the smallest K that meets it at `at_devices`,
    how often it binds, and how many decisions it changes on the 8-device fixture."""
    rows = []
    chosen = None
    for k in ks:
        res = _cell(n_dashcam=at_devices // 2, n_robot=at_devices - at_devices // 2,
                    window_s=window_s, seed=1, h=1.0, cap_k=k, out=out / ("k%d" % k),
                    max_wall_s=max_wall_s)
        lat = res["decision_latency_ms"]
        met = bool(lat["p99"] is not None and lat["p99"] < 100.0)
        rows.append(dict(K=k, n_devices=at_devices, decision_latency_ms=lat,
                         cpu_percent=res["cpu_percent"], wall_s=res["wall_measured_s"],
                         epoch_overruns=res["epoch_overruns"],
                         virtual_t_reached_s=res["virtual_t_reached_s"],
                         wall_guard_hit=res["wall_guard_hit"],
                         n_opportunities=res["n_opportunities"],
                         n_requests=res["n_requests"],
                         n_cloud_answers=res["n_cloud_answers"],
                         n_on_time=res["n_on_time"],
                         n_monitor_answers=res["n_monitor_answers"],
                         n_recall_answers=res["n_recall_answers"],
                         cap_bound=dict(
                             sh_periods=res["arm_stats"].get("sh_cap_bound_periods"),
                             sh_skipped=res["arm_stats"].get("sh_cap_skipped"),
                             release_passes=res["arm_stats"].get("release_cap_bound_passes"),
                             release_skipped=res["arm_stats"].get("release_cap_skipped_items")),
                         requests_per_virtual_s=round(
                             res["n_requests"] / max(res["virtual_t_reached_s"], 1e-9), 3),
                         target_p99_under_100ms=met))
        # The sweep does NOT stop at the first K that meets the latency target: a cap can meet
        # it by not deciding at all, and that is exactly what happens at K = 1 on the largest
        # fleet. The whole curve is reported so the choice is not made on latency alone.
        if met and chosen is None:
            chosen = k
    diff = None
    if chosen is not None:
        logs = {}
        for k in (chosen, None):
            d = out / ("diff_k%s" % k)
            r = _cell(n_dashcam=4, n_robot=4, window_s=120.0, seed=1, h=1.0, cap_k=k, out=d)
            logs[k] = (_strip(Path(r["decision_log"])), r)
        a, b = logs[None][0], logs[chosen][0]
        n_diff = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
        # A positional line compare overstates the difference, because one skipped evaluation
        # renumbers every later decision_id. The multiset of (kind, opportunity_ids) is the
        # comparison that says whether the two policies DID different things.
        from collections import Counter
        def _acts(lines):
            c = Counter()
            for x in lines:
                r = json.loads(x)
                c[(r["kind"], tuple(r.get("opportunity_ids") or ()))] += 1
            return c
        ca, cb = _acts(a), _acts(b)
        same = sum((ca & cb).values())
        total = max(sum(ca.values()), 1)
        diff = dict(fixture="SYNTHETIC 8 devices (4 + 4), 120 s, seed 1, mode A, dry run",
                    K=chosen, lines_unlimited=len(a), lines_capped=len(b),
                    lines_differing=n_diff,
                    fraction_differing=(round(n_diff / max(len(a), 1), 4)),
                    note="`lines_differing` is a POSITIONAL compare and overstates the change: "
                         "one skipped evaluation renumbers every later decision_id. "
                         "`actions_in_common_fraction` compares the multiset of "
                         "(kind, opportunity_ids), which is what the two policies actually did.",
                    actions_in_common=same, actions_unlimited=sum(ca.values()),
                    actions_capped=sum(cb.values()),
                    actions_in_common_fraction=round(same / total, 4),
                    cap_bound=dict(
                        sh_periods=logs[chosen][1]["arm_stats"].get("sh_cap_bound_periods"),
                        release_passes=logs[chosen][1]["arm_stats"]
                        .get("release_cap_bound_passes")),
                    n_requests=dict(unlimited=logs[None][1]["n_requests"],
                                    capped=logs[chosen][1]["n_requests"]))
    return dict(check="d99_cap_k", is_measurement=False,
                smallest_K_meeting_the_latency_target=chosen,
                chosen_K=chosen,
                warning="`chosen_K` is the smallest K that meets the LATENCY target and nothing "
                        "else. A cap can meet that target by not deciding: compare each row's "
                        "n_requests and requests_per_virtual_s against the uncapped cell in "
                        "d99_speed.json before using it as a setting.",
                target="p99 decision time under 100 ms at %d devices" % at_devices,
                fixture="SYNTHETIC 50 : 50, mode A, tight memory, %.0f s, mu = 0, H = 1.0 s, "
                        "dry run" % window_s,
                decision_period_s=DECISION_PERIOD_S, rows=rows,
                decisions_changed_on_the_8_device_fixture=diff)


CHECKS = dict(sh_admission=sh_admission, equivalence=equivalence, speed=speed, parity=parity,
              cap=cap)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("check", choices=("sh-admission", "equivalence", "speed", "parity", "cap",
                                      "all"))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--window-s", type=float, default=180.0, help="speed only")
    ap.add_argument("--sizes", default="32,64,128", help="speed only")
    ap.add_argument("--max-wall-s", type=float, default=None, help="speed only")
    ap.add_argument("--cap-k", type=int, default=None, help="speed only: D99 (4) cap")
    ap.add_argument("--ks", default="1,2,4,8", help="cap only: the K values to try, in order")
    a = ap.parse_args(argv)
    out = Path(a.out)
    want = list(CHECKS) if a.check == "all" else [a.check.replace("-", "_")]
    for name in want:
        d = out / name
        if name == "speed":
            res = speed(d, sizes=tuple(int(x) for x in a.sizes.split(",")),
                        window_s=a.window_s, max_wall_s=a.max_wall_s, cap_k=a.cap_k)
        elif name == "cap":
            res = cap(d, ks=tuple(int(x) for x in a.ks.split(",")),
                      at_devices=int(a.sizes.split(",")[-1]), window_s=a.window_s,
                      max_wall_s=a.max_wall_s)
        else:
            res = CHECKS[name](d)
        from _provenance import stamp
        res["_provenance"] = stamp(script="fix_checks.py", model="none", device="flash_cpu",
                                   n=len(res.get("rows", [])), args=a)
        p = out / ("%s.json" % res["check"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
        print(json.dumps({k: v for k, v in res.items() if k != "_provenance"}, indent=1,
                         default=str))
        print("written: %s" % p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
