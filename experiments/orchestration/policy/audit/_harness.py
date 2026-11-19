#!/usr/bin/env python3
"""Shared harness for the StudyCOVEX-harden audits and scenarios.

DEVELOPMENT DATA ONLY (D124): seed 0, the pilot traces, synthetic fixtures. This module refuses
to build a trace on any other seed, so a round-1 seed cannot be touched by accident.
"""
from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any, Dict, List, Optional

AUDIT_DIR = Path(__file__).resolve().parent
POLICY_DIR = AUDIT_DIR.parent
ROOT = POLICY_DIR.parents[2]
LIVE2 = ROOT / "experiments/orchestration/live2"

# D129 widens development data to seeds 0, 4, 5 and 6, so a candidate that wins only on seed 0 is
# visible as such. **Seeds 1, 2 and 3 remain RESERVED FOR ROUND 1 and are refused here**, and the
# refusal names them explicitly so the guardrail cannot be relaxed by accident.
DEV_SEEDS = (0, 4, 5, 6)
RESERVED_ROUND1_SEEDS = (1, 2, 3)


def setup_paths() -> None:
    """`policy/coordinator.py` would shadow `live2/coordinator.py`, so the policy directory and
    this one are kept OFF sys.path and every import below resolves to the live2 tree."""
    drop = {POLICY_DIR.resolve(), AUDIT_DIR.resolve()}
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() not in drop]
    for p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "scorer"), str(LIVE2 / "data"),
              str(ROOT / "experiments/orchestration"),
              str(ROOT / "experiments/orchestration/live"),
              str(ROOT / "experiments/orchestration/baselines"),
              str(ROOT / "experiments/orchestration/sim"),
              str(ROOT / "experiments/lib")):
        if p not in sys.path:
            sys.path.insert(0, p)


def assert_dev_seed(seed: int) -> int:
    """Refuse anything but a development seed, and name a round-1 seed when one is passed."""
    s = int(seed)
    if s in RESERVED_ROUND1_SEEDS:
        raise ValueError(
            "REFUSED: seed %d is RESERVED FOR ROUND 1 (D124, D129). Seeds 1, 2 and 3 must never "
            "be generated, run or inspected by this study." % s)
    if s not in DEV_SEEDS:
        raise ValueError(
            "development data only: seed %r is not in %r." % (seed, DEV_SEEDS))
    return s


def available_switches() -> List[str]:
    """The v1.1 switches that exist on this build, so the harness keeps working as session 1
    lands more of them."""
    setup_paths()
    import arms_policy as AP
    from policy.flags import Flags
    arm_fields = {f.name for f in dc_fields(AP.PolicyCoreArm)}
    flag_fields = {f.name for f in dc_fields(Flags)}
    known = ("honour_job_priority", "deficit_update", "rc_tail", "write_staleness",
             "realistic_competing", "prob_p_finish", "rc_tail_cursor", "rc_tail_zrows",
             "planner_rc", "plan_latest", "replan", "kappa")
    return [s for s in known if s in arm_fields or s in flag_fields]


def _arm_kwargs(switches: Dict[str, bool]) -> Dict[str, Any]:
    setup_paths()
    import arms_policy as AP
    arm_fields = {f.name for f in dc_fields(AP.PolicyCoreArm)}
    out = dict(cost_model="pol4", h_s=0.5, mu_mode="ewma", mu_fixed=None, impl="fast",
               cap_k=None)
    # v1.3 selects the SCARCITY price through the estimator rather than a flag, so `mu_mode` has
    # to be overridable or every v1.3 run would silently be scored with the old EWMA price.
    if "mu_mode" in (switches or {}):
        out["mu_mode"] = str(switches["mu_mode"])
    types = {f.name: f.type for f in dc_fields(AP.PolicyCoreArm)}
    for k, v in (switches or {}).items():
        if k not in arm_fields:
            continue
        # v1.2's `kappa` is a FLOAT, not a flag, so a blanket bool() would turn 1.0 into True and
        # silently change the setting under test.
        if k == "mu_mode":
            continue
        out[k] = float(v) if "float" in str(types.get(k, "")).lower() else bool(v)
    return out


def unsupported_switches(switches: Dict[str, bool]) -> List[str]:
    setup_paths()
    import arms_policy as AP
    arm_fields = {f.name for f in dc_fields(AP.PolicyCoreArm)}
    return sorted(k for k in (switches or {}) if k not in arm_fields)


def build_trace(outdir: Path, n_dev: int, run_s: float, seed: int = 0,
                ratio: str = "50:50", mode: str = "A") -> Path:
    setup_paths()
    import fleet.trace as TR
    assert_dev_seed(seed)
    tdir = Path(outdir) / "trace"
    TR.write_trace(tdir, TR.generate_trace(seed, int(n_dev), ratio, float(run_s), mode))
    return tdir


def trace_questions(n_dev: int, run_s: float, seed: int = 0, ratio: str = "50:50",
                    mode: str = "A") -> Dict[str, Any]:
    setup_paths()
    import fleet.trace as TR
    assert_dev_seed(seed)
    tr = TR.generate_trace(seed, int(n_dev), ratio, float(run_s), mode)
    return dict(questions={r["opportunity_id"]: r for r in tr["records"]
                           if r["kind"] == "recall_question"},
                monitor_opportunities=sum(1 for r in tr["records"]
                                          if r["kind"] == "monitor_opportunity"),
                records=len(tr["records"]))


def run_fleet_cell(outdir: Path, n_dev: int, run_s: float = 600.0, seed: int = 0,
                   arm_name: str = "policy-core", switches: Optional[Dict[str, bool]] = None,
                   host_gib: Optional[float] = None, ratio: str = "50:50",
                   mode: str = "A") -> Dict[str, Any]:
    """One dry run of the real emulator, bridge and coordinator on a fleet trace.

    The same wiring `run_live2_cell` uses, with `dry_run=True` so no server is contacted and no
    GPU is touched. Settings match the pilot: mu EWMA, H = 0.5 s, pol4, tight memory.
    """
    setup_paths()
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import run_live2_cell as RC
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    import fleet.emulator as EM

    assert_dev_seed(seed)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tdir = build_trace(outdir, n_dev, run_s, seed=seed, ratio=ratio, mode=mode)

    import fix_checks as FX
    gib = float(FX.HOST_GIB if host_gib is None else host_gib)
    gpu_kv = int(FX.GPU_KV)
    htok = RC.host_tokens(gib)

    if arm_name == "policy-core":
        arm = A.make_arm("policy-core", **_arm_kwargs(switches or {}))
    elif arm_name.startswith("edf@"):
        # D128 makes C_inflight = 8 edf's default, but the committed code still declares 4, so
        # the variant is constructed explicitly rather than assumed.
        arm = A.Pi0Edf(None, c_inflight=int(arm_name.split("@", 1)[1]))
    elif arm_name.startswith("llf@"):
        arm = A.LlfArm(None, c_inflight=int(arm_name.split("@", 1)[1]))
    else:
        arm = A.make_arm(arm_name)
    arm.live2_configure(gpu_kv_tokens=gpu_kv, host_tier_gib=gib, host_tier_tokens=htok,
                        targets=CS.TARGETS)
    logs = Logs(outdir / "run").open()
    co = Live2Coordinator(arm, None, [], gpu_kv_tokens=gpu_kv, host_tier_gib=gib,
                          host_tier_tokens=htok, upload_mode=mode, window_s=float(run_s),
                          drain_s=10.0, seed=seed, logs=logs,
                          run_tag=CK.run_tag(seed, arm_name), dry_run=True)
    br = EmulatorBridge(co)
    br.kind = "stub"
    try:
        EM.FleetEmulator(tdir, br, mode, realtime=False, drain_s=10.0).run(outdir / "run")
    finally:
        logs.close()
    dec = [json.loads(l) for l in open(outdir / "run" / "decision.jsonl")]
    return dict(arm=arm, coordinator=co, decisions=dec, outdir=outdir,
                arm_stats=dict(getattr(arm, "stats", {}) or {}),
                host_gib=gib, gpu_kv=gpu_kv, n_devices=int(n_dev), seed=seed, run_s=float(run_s))


def released_before_deadline(decisions: List[Dict[str, Any]],
                             questions: Dict[str, Any]) -> Dict[str, Any]:
    """A question counts when a release decision carries its opportunity_id before its own
    deadline. The SAME definition sections E5, F6.3 and V10 use, so the counts are comparable."""
    rel: Dict[str, List[float]] = {}
    for r in decisions:
        if r["kind"] in ("release_recall", "release_whole", "release_piece"):
            for o in (r.get("opportunity_ids") or []):
                rel.setdefault(o, []).append(float(r["t"]))
    on_time, released = 0, 0
    for oid, q in questions.items():
        ts = rel.get(oid)
        if not ts:
            continue
        released += 1
        if min(ts) < float(q["t"]) + float(q["deadline_s"]):
            on_time += 1
    return dict(total=len(questions), released=released, released_before_deadline=on_time)


@contextlib.contextmanager
def capture_delta_j(collect: List[Dict[str, Any]], want_devices: Optional[str] = None):
    """Record every DeltaJ evaluation with its value channels split out.

    Both bindings of `rollout.delta_j` are patched, the one the coordinator imported and the one
    in the rollout module, and `Rollout.run` is wrapped so the two branches' own detail can be
    read. A `release`, `defer` or `dispatch` action carries `item_id` rather than `items`, so the
    item is resolved through the fleet or its device and kind would be invisible.
    """
    setup_paths()
    from policy import coordinator as PCO
    from policy import rollout as PRO

    runs: List[Any] = []
    _run = PRO.Rollout.run

    def run(self, fleet, *a, **k):
        # PASSTHROUGH, not a fixed signature: v1.2's planner calls `rollout.run(fleet,
        # horizon_s=..., rc_rows=True)`, and a wrapper that named the v1.1 arguments raised
        # TypeError on every planner evaluation. Recorded as erratum E5.
        r = _run(self, fleet, *a, **k)
        runs.append(r)
        return r

    _dj = PCO.delta_j

    def dj(ro, fleet, action):
        before = len(runs)
        res = _dj(ro, fleet, action)
        pair = runs[before:]
        collect.append(_decompose(ro, fleet, action, res, pair, want_devices))
        return res

    PRO.Rollout.run = run
    PCO.delta_j = dj
    PRO.delta_j = dj
    try:
        yield collect
    finally:
        PRO.Rollout.run = _run
        PCO.delta_j = _dj
        PRO.delta_j = _dj


def _branch_split(res: Any, omega_sh: float) -> Dict[str, float]:
    """cont, sv and the mu backlog term from one rollout's own detail.

    `terminal = cont + sv + mu_term` (`Rollout._terminal`), so the backlog term is recovered
    exactly by subtraction rather than re-deriving mu and busy.
    """
    det = (getattr(res, "detail", None) or {}).get("terminal") or {}
    cont = sum(float(x.get("value", 0.0)) for x in (det.get("continuation") or []))
    sv = sum(float(x.get("value", 0.0)) for x in (det.get("state_value") or []))
    sh_rows = [o for o in (getattr(res, "opportunities", None) or []) if o.get("task") == "SH"]
    sh_by_dev: Dict[str, float] = {}
    for o in sh_rows:
        gain = omega_sh * (float(o.get("utility") or 0.0) - float(o.get("device_utility") or 0.0))
        sh_by_dev[o["device"]] = sh_by_dev.get(o["device"], 0.0) + gain
    return dict(cont=cont, sv=sv, mu_term=float(res.terminal) - cont - sv,
                u_hat=float(res.u_hat), z_term=float(res.z_term),
                sh_total=sum(sh_by_dev.values()), busy=float(res.engine_busy_s),
                _sh_by_dev=sh_by_dev)


def _decompose(ro: Any, fleet: Any, action: Dict[str, Any], res: Dict[str, Any],
               pair: List[Any], want_devices: Optional[str]) -> Dict[str, Any]:
    omega_sh = float(ro.pf.omega("SH"))
    items = list(action.get("items") or [])
    if not items and action.get("item_id"):
        tgt = action["item_id"]
        for p in list(fleet.pending) + list(fleet.in_flight):
            if p.item_id == tgt:
                items = [p]
                break
    jobs = action.get("jobs") or {}
    devices = sorted({getattr(it, "device", None) for it in items}
                     | {getattr(j, "device", None) for j in jobs.values()} - {None})
    item_kinds = sorted({getattr(it, "kind", None) for it in items} - {None})
    rec: Dict[str, Any] = dict(
        action_kind=action["kind"], item_kinds=item_kinds, devices=devices,
        kind=_kind_label(action, items), delta_j=float(res["delta_j"]),
        u_hat=float(res["terms"]["u_hat"]), z=float(res["terms"]["z"]),
        terminal=float(res["terms"]["terminal"]),
        busy_delta=float(res.get("engine_busy_delta_s") or 0.0),
        mu=float(ro.params.mu), n_items=len(items))
    if len(pair) >= 2:
        a, b = _branch_split(pair[0], omega_sh), _branch_split(pair[1], omega_sh)
        own = set(devices)
        sh_own = (sum(v for d, v in a["_sh_by_dev"].items() if d in own)
                  - sum(v for d, v in b["_sh_by_dev"].items() if d in own))
        sh_harm = (sum(v for d, v in a["_sh_by_dev"].items() if d not in own)
                   - sum(v for d, v in b["_sh_by_dev"].items() if d not in own))
        rec.update(
            cont_delta=a["cont"] - b["cont"], sv_delta=a["sv"] - b["sv"],
            # F-A2 needs the PER-BRANCH sums as well as their difference: a sum that is nonzero
            # per branch and still cancels is a different finding from a sum that is zero.
            sv_branch_a=a["sv"], sv_branch_b=b["sv"],
            backlog_delta=a["mu_term"] - b["mu_term"],
            sh_own_delta=sh_own, sh_harm_delta=sh_harm,
            # whatever u_hat holds that the SH rows do not explain is the RC utility, which
            # `_rc_utility` adds separately from `_opportunity_utility`.
            rc_util_delta=(a["u_hat"] - b["u_hat"]) - (a["sh_total"] - b["sh_total"]),
            busy_action=a["busy"], busy_reference=b["busy"])
    return rec


def _kind_label(action: Dict[str, Any], items: List[Any]) -> str:
    k = action["kind"]
    kinds = {getattr(it, "kind", None) for it in items}
    if k == "admit":
        return "sh_admit" if kinds == {"episode_call"} else "recall_admit"
    if k == "release":
        return "sh_release" if kinds == {"episode_call"} else "piece_release"
    if k == "defer":
        return "sh_hold" if kinds == {"episode_call"} else "piece_defer"
    if k == "dispatch":
        return "sh_dispatch"
    if k == "state":
        ids = [str(getattr(it, "item_id", "")) for it in items]
        if any("PROMOTE_REBUILD" in i for i in ids):
            return "state_promote_rebuild"
        if any("MATERIALIZE" in i for i in ids):
            return "state_materialize"
        return "state_other"
    return k


CHANNELS = ("sh_own_delta", "sh_harm_delta", "rc_util_delta", "z", "cont_delta", "sv_delta",
            "backlog_delta")


def run_synthetic_cell(outdir: Path, n_dev: int, window_s: float = 180.0,
                       switches: Optional[Dict[str, bool]] = None,
                       seed: int = 1) -> Dict[str, Any]:
    """The committed synthetic fixture through `fix_checks._cell`.

    `_cell` builds policy-core itself, so the v1.1 switches are applied by patching `FX._arm`
    from HERE and restoring it afterwards; `fix_checks` is not edited. This fixture is NOT a
    fleet trace, so its seed is the fixture seed `fix_checks.speed` uses (1), not a run seed, and
    it carries no round-1 fleet data.
    """
    setup_paths()
    import fix_checks as FX
    from policy.flags import Flags
    from dataclasses import fields as _f
    flag_names = {x.name for x in _f(Flags)}
    on = {k: bool(v) for k, v in (switches or {}).items() if k in flag_names}
    _arm = FX._arm

    def arm(h=1.0, impl="fast", mu="none", d=None, cap_k=None):
        a = _arm(h=h, impl=impl, mu=mu, d=d, cap_k=cap_k)
        if on:
            a.flags = Flags(**on)
        return a

    FX._arm = arm
    try:
        res = FX._cell(n_dashcam=int(n_dev) // 2, n_robot=int(n_dev) - int(n_dev) // 2,
                       window_s=float(window_s), seed=int(seed), h=1.0, out=Path(outdir))
    finally:
        FX._arm = _arm
    return res


def channel_identity_error(rec: Dict[str, Any]) -> Optional[float]:
    """`delta_j` must equal the seven channels summed, or the decomposition is wrong.

    delta_j = u_hat + z + terminal, u_hat = sh_own + sh_harm + rc_util,
    terminal = cont + sv + backlog.
    """
    if rec.get("cont_delta") is None:
        return None
    s = (rec["sh_own_delta"] + rec["sh_harm_delta"] + rec["rc_util_delta"] + rec["z"]
         + rec["cont_delta"] + rec["sv_delta"] + rec["backlog_delta"])
    return abs(s - rec["delta_j"])
