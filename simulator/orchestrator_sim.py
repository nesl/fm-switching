"""
Step 3: Trace-driven orchestrator simulator.

Reads a workload trace (per-cycle VLM latency + initial context) and a
network trace (per-second RTT/connected). At each cycle, the simulator
queries the policy for an action, applies it, advances state.

No GPU, no torch. Pure numpy / dict math.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from cost_model import (FP16, INT4, CLOUD,
                        KV_GROWTH_MB_PER_CYCLE, TOKENS_PER_CYCLE_FULL,
                        QUALITY, EFFECTIVE_TOKENS, SUMMARIZATION_COST_S,
                        llm_latency_ms, migration_cost_s, memory_used_mb,
                        inertia_ms,
                        edge_compute_ms as edge_compute_ms_local,
                        cloud_compute_ms as cloud_compute_ms_local,
                        cloud_serve_outcome)


# ── Action enum (strings for simplicity) ───────────────────────────────
STAY                 = "STAY"
MIGRATE_TO_CLOUD     = "MIGRATE_TO_CLOUD"
MIGRATE_TO_EDGE      = "MIGRATE_TO_EDGE"
SWITCH_TO_FP16       = "SWITCH_TO_FP16"
SWITCH_TO_INT4       = "SWITCH_TO_INT4"
SET_WINDOW_3         = "SET_WINDOW_3"
SET_WINDOW_10        = "SET_WINDOW_10"
SET_FULL_CONTEXT     = "SET_FULL_CONTEXT"
SET_STATELESS        = "SET_STATELESS"
SET_SUMMARY_80       = "SET_SUMMARY_80"
SET_SUMMARY_200      = "SET_SUMMARY_200"
# Latency-hiding: cloud is already prewarmed, switch with zero gap.
# Any small residual cost (buffer-and-replay delta prefill + 1 RTT) is paid
# by the policy and returned through its on_cycle hook.
SWITCH_TO_CLOUD_PREWARMED = "SWITCH_TO_CLOUD_PREWARMED"

ALL_ACTIONS = [
    STAY, MIGRATE_TO_CLOUD, MIGRATE_TO_EDGE,
    SWITCH_TO_FP16, SWITCH_TO_INT4,
    SET_WINDOW_3, SET_WINDOW_10, SET_FULL_CONTEXT, SET_STATELESS,
    SET_SUMMARY_80, SET_SUMMARY_200,
    SWITCH_TO_CLOUD_PREWARMED,
]


@dataclass
class SimState:
    """Snapshot passed to the policy at each cycle."""
    cycle: int
    time_s: float
    context_tokens: int             # actual prompt tokens this cycle (mode-dep)
    accumulated_tokens: int         # if mode were 'full', what would tokens be
    memory_used_mb: float
    memory_cap_mb: float
    network_rtt_ms: float
    network_connected: bool
    llm_location: str               # 'edge' | 'cloud'
    quantization: str               # 'fp16' | 'int4'
    context_mode: str               # 'stateless' | 'window-3' | 'window-10' | 'full'
    current_vlm_latency_s: float
    time_since_last_migration_s: float
    rtt_history_ms: List[float] = field(default_factory=list)
    # Predictive: lookahead handle into traces (read-only, capped to horizon)
    workload_lookahead_vlm_s: List[float] = field(default_factory=list)
    network_lookahead_rtt_ms: List[float] = field(default_factory=list)


@dataclass
class CycleRecord:
    cycle: int
    time_s: float
    config: str           # "edge_fp16/full", etc.
    vlm_latency_s: float
    llm_latency_ms: float
    cycle_total_s: float
    context_tokens: int
    memory_used_mb: float
    quality_score: float
    action: str
    migration_gap_s: float = 0.0
    oom: bool = False


@dataclass
class EpisodeMetrics:
    n_cycles: int
    total_time_s: float
    mean_cycle_latency_s: float
    total_planning_gap_s: float
    num_migrations: int
    peak_memory_mb: float
    oom_events: int
    mean_quality: float
    cycles: List[CycleRecord] = field(default_factory=list)
    # Overlap-window metrics (zero for non-overlap policies)
    peak_memory_mb_overlap: float = 0.0
    overlap_total_s: float = 0.0
    n_overlap_windows: int = 0
    n_lh_aborts: int = 0
    # Continuous-resource metrics (tracked EVERY cycle for ALL policies):
    peak_memory_mb_continuous: float = 0.0
    mean_memory_mb_continuous: float = 0.0
    mean_compute_tokens_per_cycle: float = 0.0   # primary Pareto axis
    mean_compute_seconds_per_cycle: float = 0.0  # secondary Pareto axis
    wasted_compute_tokens: int = 0               # sum across cycles
    # Within-cycle network variation metrics:
    cloud_failure_events: int = 0       # cycles where cloud serving started but failed mid-cycle
    successful_fallbacks: int = 0       # LH variants: cycles where warm replica saved the cycle
    unrecoverable_cycles: int = 0       # non-LH: cycles with cloud failure and no replica
    # Cumulative re-prefill costs (seconds) — breakdown for inertia-binding analysis:
    cloud_failure_reprefill_s: float = 0.0  # edge re-prefill paid on forced cloud→edge returns
    mode_switch_reprefill_s: float = 0.0    # re-prefill paid on rep-mode switches (edge or server)


# ── Trace readers ──────────────────────────────────────────────────────

def read_workload_csv(path: Path):
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            rows.append({"cycle": int(r["cycle"]),
                         "vlm_latency_s": float(r["vlm_latency_s"])})
    return rows


def read_network_csv(path: Path):
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            rows.append({"time_s": float(r["time_s"]),
                         "rtt_ms": float(r["rtt_ms"]),
                         "bandwidth_mbps": float(r["bandwidth_mbps"]),
                         "connected": int(r["connected"]) == 1})
    return rows


def network_at(net: List[dict], t_s: float):
    """Return (rtt_ms, connected) at the given wall time, with simple snap."""
    if not net:
        return 30.0, True
    if t_s <= net[0]["time_s"]:
        return net[0]["rtt_ms"], net[0]["connected"]
    if t_s >= net[-1]["time_s"]:
        return net[-1]["rtt_ms"], net[-1]["connected"]
    idx = min(int(t_s), len(net) - 1)
    return net[idx]["rtt_ms"], net[idx]["connected"]


def network_trajectory(net: List[dict], t_start_s: float, n_subticks: int):
    """Return the trajectory `[(rtt_ms, connected), ...]` of length n_subticks,
    sampling the chain at 1-second sub-ticks starting from floor(t_start_s).
    This exposes within-cycle network variation that `network_at` collapses
    to a single sample."""
    if n_subticks <= 0:
        return []
    out = []
    base = int(max(0, t_start_s))
    for k in range(n_subticks):
        out.append(network_at(net, float(base + k)))
    return out


# ── Effective context-token computation ────────────────────────────────

def effective_tokens(mode: str, accumulated_full_tokens: int) -> int:
    if mode == "full":
        return accumulated_full_tokens
    return EFFECTIVE_TOKENS[mode]


# ── Simulation ─────────────────────────────────────────────────────────

def run_episode(workload, network, policy, *, memory_cap_mb=13_000,
                start_quant="fp16", start_location="edge",
                start_mode="full", lookahead=10, verbose=False,
                quality_override=None):
    """Run one episode of the orchestrator simulator. Returns EpisodeMetrics."""
    if hasattr(policy, "reset"):
        policy.reset()
    _q = quality_override if quality_override is not None else QUALITY
    state_q   = start_quant
    state_loc = start_location
    state_mode = start_mode

    accumulated_full = 161             # would-be full-mode token count
    time_s = 0.0
    last_migration_time = -1e9
    rtt_history = []
    cycles = []
    n_migrations = 0
    oom_count = 0
    peak_mem = 0.0
    total_gap = 0.0

    # Continuous-resource accumulators (tracked every cycle for every policy).
    peak_mem_cont = 0.0
    sum_mem_cont = 0.0
    sum_compute_tokens = 0.0
    sum_compute_seconds = 0.0
    wasted_compute_tokens_sim = 0
    n_cloud_failures = 0
    n_successful_fallbacks = 0
    n_unrecoverable = 0
    cloud_failure_reprefill_s = 0.0
    mode_switch_reprefill_s = 0.0

    n = len(workload)
    prev_accum_full = None
    for i in range(n):
        wl = workload[i]
        rtt_ms, connected = network_at(network, time_s)
        rtt_history.append(rtt_ms)

        ctx_tokens = effective_tokens(state_mode, accumulated_full)
        mem = memory_used_mb(state_q, state_loc, ctx_tokens)
        # OOM check. Normally single-tier: the serving tier's edge memory.
        # ASYMMETRIC RESTORE: a latency-hiding policy that is warming a shadow
        # replica while still serving on the primary tier transiently holds
        # BOTH residencies (edge serving full KV + warming cloud replica). For
        # that warming event ONLY, the policy reports its dual-residency
        # footprint via warming_oom_memory_mb() and the OOM check uses it. This
        # is inert for non-warming cycles and for any policy that does not
        # implement the hook (returns None) — single-tier behaviour is
        # unchanged everywhere else.
        oom_mem = mem
        if hasattr(policy, "warming_oom_memory_mb"):
            warm_mem = policy.warming_oom_memory_mb(
                state_loc=state_loc, state_quant=state_q,
                ctx_tokens=ctx_tokens, accumulated_tokens=accumulated_full,
                base_mem_mb=mem)
            if warm_mem is not None:
                oom_mem = max(oom_mem, float(warm_mem))
        oom = oom_mem > memory_cap_mb
        if oom:
            oom_count += 1
            # Forced fallback: switch to stateless to free KV cache
            state_mode = "stateless"
            ctx_tokens = effective_tokens(state_mode, accumulated_full)
            mem = memory_used_mb(state_q, state_loc, ctx_tokens)

        # Build state for policy (lookahead views)
        wl_la = [w["vlm_latency_s"] for w in workload[i+1:i+1+lookahead]]
        nt_la = []
        for k in range(1, lookahead + 1):
            r, _ = network_at(network, time_s + k * 1.0)
            nt_la.append(r)

        sim_state = SimState(
            cycle=i,
            time_s=time_s,
            context_tokens=ctx_tokens,
            accumulated_tokens=accumulated_full,
            memory_used_mb=mem,
            memory_cap_mb=memory_cap_mb,
            network_rtt_ms=rtt_ms,
            network_connected=connected,
            llm_location=state_loc,
            quantization=state_q,
            context_mode=state_mode,
            current_vlm_latency_s=wl["vlm_latency_s"],
            time_since_last_migration_s=time_s - last_migration_time,
            rtt_history_ms=list(rtt_history[-5:]),
            workload_lookahead_vlm_s=wl_la,
            network_lookahead_rtt_ms=nt_la,
        )

        action = policy.decide(sim_state)
        gap_s = 0.0
        prev_mode = state_mode

        # Apply action
        if action == STAY:
            pass
        elif action == MIGRATE_TO_CLOUD:
            if state_loc != "cloud" and connected:
                gap_s = migration_cost_s("to_cloud", state_q, ctx_tokens, rtt_ms)
                state_loc = "cloud"
                last_migration_time = time_s
                n_migrations += 1
        elif action == MIGRATE_TO_EDGE:
            if state_loc != "edge":
                gap_s = migration_cost_s("to_edge", state_q, ctx_tokens, rtt_ms)
                state_loc = "edge"
                last_migration_time = time_s
                n_migrations += 1
        elif action == SWITCH_TO_FP16:
            if state_q != "fp16":
                # Quant switch on edge means reload weights -> use warm load time
                if state_loc == "edge":
                    gap_s = FP16["llm_load_warm_s"]
                state_q = "fp16"
                last_migration_time = time_s
                n_migrations += 1
        elif action == SWITCH_TO_INT4:
            if state_q != "int4":
                if state_loc == "edge":
                    gap_s = INT4["llm_load_warm_s"]
                state_q = "int4"
                last_migration_time = time_s
                n_migrations += 1
        elif action == SET_WINDOW_3:
            state_mode = "window-3"
        elif action == SET_WINDOW_10:
            state_mode = "window-10"
        elif action == SET_FULL_CONTEXT:
            state_mode = "full"
        elif action == SET_STATELESS:
            state_mode = "stateless"
        elif action == SET_SUMMARY_80:
            state_mode = "summary-80"
        elif action == SET_SUMMARY_200:
            state_mode = "summary-200"
        elif action == SWITCH_TO_CLOUD_PREWARMED:
            if state_loc != "cloud" and connected:
                # Cloud is already warmed by the latency-hiding policy. The
                # policy attaches the buffer-and-replay residual gap (1 RTT +
                # delta prefill) via a small per-switch attribute, queried
                # here. Anything beyond that is hidden by the parallel warm-up.
                residual = float(getattr(policy, "pending_prewarmed_gap_s", 0.0))
                gap_s = max(0.0, residual)
                if hasattr(policy, "pending_prewarmed_gap_s"):
                    policy.pending_prewarmed_gap_s = 0.0
                state_loc = "cloud"
                last_migration_time = time_s
                n_migrations += 1
        else:
            raise ValueError(f"unknown action: {action}")

        # Charge re-prefill gap when representation mode changes.
        # The KV cache must be rebuilt for the new context depth.
        # Summarization modes also pay SUMMARIZATION_COST_S for the summary pass.
        if state_mode != prev_mode:
            _new_ctx = effective_tokens(state_mode, accumulated_full)
            _tier = "edge" if state_loc == "edge" else "server"
            _ms_reprefill_s = inertia_ms(_tier, _new_ctx) / 1000.0
            gap_s += _ms_reprefill_s
            mode_switch_reprefill_s += _ms_reprefill_s
            if state_mode in ("summary-80", "summary-200"):
                gap_s += SUMMARIZATION_COST_S

        # Recompute after action (mode/loc/quant may have changed)
        ctx_tokens = effective_tokens(state_mode, accumulated_full)
        mem = memory_used_mb(state_q, state_loc, ctx_tokens)
        peak_mem = max(peak_mem, mem)

        # ── LLM cost this cycle ─────────────────────────────────────
        # Policy hook for LH variants A/B/C: override the per-cycle compute
        # cost. The hook returns a dict with:
        #   llm_latency_ms          — user-facing wall time for the LLM step
        #   compute_tokens          — total prefill+decode tokens charged
        #                              across BOTH tiers this cycle
        #   compute_seconds         — total compute seconds across tiers
        #   memory_total_mb         — total memory across tiers this cycle
        #   wasted_compute_tokens   — tokens charged but unused for response
        # Standard policies (no hook) use the existing single-tier path.
        new_tokens_per_turn = (accumulated_full - prev_accum_full
                                if prev_accum_full is not None else 0)
        # Within-cycle network trajectory: enough sub-ticks to cover the
        # cloud-serve compute window (ceil seconds). Standard cloud-compute
        # for ctx ~4000 is ~0.65s → 1 sub-tick; long context grows the window.
        cloud_compute_s_estimate = cloud_compute_ms_local(ctx_tokens, 10) / 1000.0
        import math as _math
        traj_len = max(1, _math.ceil(cloud_compute_s_estimate))
        trajectory = network_trajectory(network, time_s, traj_len)
        # Decide cloud outcome from the trajectory (used by both override
        # and standard paths).
        cloud_ok, cloud_mean_rtt, cloud_elapsed_s = cloud_serve_outcome(
            trajectory, ctx_tokens, gen_tokens=10)

        override = None
        if hasattr(policy, "compute_cycle_overrides"):
            override = policy.compute_cycle_overrides(
                sim_state=sim_state,
                state_loc=state_loc, state_quant=state_q,
                ctx_tokens=ctx_tokens, gen_tokens=10,
                rtt_ms=rtt_ms, connected=connected,
                new_tokens_per_turn=new_tokens_per_turn,
                mem_edge_mb=mem,
                trajectory=trajectory,
                cloud_ok=cloud_ok, cloud_mean_rtt=cloud_mean_rtt,
                cloud_elapsed_s=cloud_elapsed_s,
            )
        if override is not None:
            llm_ms = float(override.get("llm_latency_ms", 0.0))
            cycle_compute_tokens = float(override.get("compute_tokens", 0.0))
            cycle_compute_seconds = float(override.get("compute_seconds",
                                                         llm_ms / 1000.0))
            mem_total = float(override.get("memory_total_mb", mem))
            wasted_compute_tokens_sim += int(override.get(
                "wasted_compute_tokens", 0))
            # Variant policies report mid-cycle outcomes via override.
            if override.get("cloud_failed_mid_cycle"):
                n_cloud_failures += 1
            if override.get("successful_fallback"):
                n_successful_fallbacks += 1
        else:
            # Within-cycle cloud failure for standard policies serving cloud:
            # cycle cannot complete on cloud → reactive fallback to edge with
            # the existing planning-gap penalty (warm load + KV re-prefill).
            if state_loc == "cloud" and not cloud_ok:
                n_cloud_failures += 1
                n_unrecoverable += 1
                _reprefill_s = migration_cost_s("to_edge", state_q, ctx_tokens, rtt_ms)
                gap_s += _reprefill_s
                cloud_failure_reprefill_s += _reprefill_s
                state_loc = "edge"
                last_migration_time = time_s
                n_migrations += 1
                # Recompute mem on edge for this cycle
                mem = memory_used_mb(state_q, state_loc, ctx_tokens)
            llm_ms = llm_latency_ms(state_q, state_loc, ctx_tokens,
                                     gen_tokens=10,
                                     network_rtt_ms=(cloud_mean_rtt
                                                       if state_loc == "cloud" else 0))
            # Single-tier compute charge: tokens = prefill+decode tokens served
            # on the active tier (no network in this count). Seconds = same in
            # wall time. This is the baseline; LH variants override.
            cycle_compute_tokens = ctx_tokens + 10
            if state_loc == "edge":
                cycle_compute_seconds = (edge_compute_ms_local(state_q, ctx_tokens, 10)
                                          / 1000.0)
            else:
                cycle_compute_seconds = cloud_compute_ms_local(ctx_tokens, 10) / 1000.0
            mem_total = mem
            # Policies without compute overrides may still hold a shadow tier
            # (e.g. OverlapMigration during warming). Let them surface extra
            # memory via a simple attribute, queried each cycle.
            extra = 0.0
            if hasattr(policy, "shadow_memory_mb"):
                try:
                    extra = float(policy.shadow_memory_mb(
                        state_loc=state_loc, state_quant=state_q,
                        ctx_tokens=ctx_tokens,
                        accumulated_tokens=accumulated_full))
                except Exception:
                    extra = 0.0
            mem_total = mem + max(0.0, extra)

        cycle_total_s = wl["vlm_latency_s"] + (llm_ms / 1000.0) + gap_s
        total_gap += gap_s

        # Continuous resource tallies (every cycle, every policy)
        peak_mem_cont = max(peak_mem_cont, mem_total)
        sum_mem_cont += mem_total
        sum_compute_tokens += cycle_compute_tokens
        sum_compute_seconds += cycle_compute_seconds
        prev_accum_full = accumulated_full

        config_str = f"{state_loc}_{state_q}/{state_mode}"
        cycles.append(CycleRecord(
            cycle=i, time_s=time_s, config=config_str,
            vlm_latency_s=wl["vlm_latency_s"],
            llm_latency_ms=llm_ms,
            cycle_total_s=cycle_total_s,
            context_tokens=ctx_tokens,
            memory_used_mb=mem,
            quality_score=_q[state_mode],
            action=action,
            migration_gap_s=gap_s,
            oom=oom,
        ))

        # Policy hook: latency-hiding (or any policy tracking side-state)
        # may use this to update its phase, accumulate overlap memory, etc.
        if hasattr(policy, "on_cycle_end"):
            policy.on_cycle_end(
                cycle=i, time_s=time_s, cycle_total_s=cycle_total_s,
                state_loc=state_loc, state_quant=state_q,
                accumulated_tokens=accumulated_full,
                ctx_tokens=ctx_tokens, mem_edge_mb=mem,
                memory_cap_mb=memory_cap_mb, rtt_ms=rtt_ms,
                connected=connected,
            )

        time_s += cycle_total_s
        accumulated_full += TOKENS_PER_CYCLE_FULL

        if verbose and (i % 10 == 0 or gap_s > 0):
            print(f"  cyc {i:>3} t={time_s:7.2f}s  cfg={config_str:<22} "
                  f"vlm={wl['vlm_latency_s']:5.2f}s  llm={llm_ms:7.1f}ms "
                  f"mem={mem:6.0f}MB  act={action}{f'  GAP={gap_s:.2f}s' if gap_s else ''}")

    lh_metrics = getattr(policy, "latency_hiding_metrics", None) or {}
    policy_wasted = int(lh_metrics.get("wasted_compute_tokens",
                                         lh_metrics.get("wasted_prefill_tokens", 0)))
    return EpisodeMetrics(
        n_cycles=n,
        total_time_s=time_s,
        mean_cycle_latency_s=sum(c.cycle_total_s for c in cycles) / n,
        total_planning_gap_s=total_gap,
        num_migrations=n_migrations,
        peak_memory_mb=peak_mem,
        oom_events=oom_count,
        mean_quality=sum(c.quality_score for c in cycles) / n,
        cycles=cycles,
        peak_memory_mb_overlap=float(lh_metrics.get("peak_memory_mb_overlap", 0.0)),
        overlap_total_s=float(lh_metrics.get("overlap_total_s", 0.0)),
        n_overlap_windows=int(lh_metrics.get("n_overlap_windows", 0)),
        n_lh_aborts=int(lh_metrics.get("n_aborts", 0)),
        peak_memory_mb_continuous=round(peak_mem_cont, 1),
        mean_memory_mb_continuous=round(sum_mem_cont / n, 1),
        mean_compute_tokens_per_cycle=round(sum_compute_tokens / n, 2),
        mean_compute_seconds_per_cycle=round(sum_compute_seconds / n, 4),
        wasted_compute_tokens=wasted_compute_tokens_sim + policy_wasted,
        cloud_failure_events=n_cloud_failures,
        successful_fallbacks=n_successful_fallbacks,
        unrecoverable_cycles=n_unrecoverable,
        cloud_failure_reprefill_s=round(cloud_failure_reprefill_s, 3),
        mode_switch_reprefill_s=round(mode_switch_reprefill_s, 3),
    )
