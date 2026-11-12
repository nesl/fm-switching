#!/usr/bin/env python3
"""Run the smoke replay for every baseline in the suite and write the results. CPU only.

No performance claim; no baseline is compared with another. The output records only that each
policy ran, respected the interface and stayed inside the shared budget.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "reconstructed"))

import replay  # noqa: E402

import naive  # noqa: E402
from cascade_adapted import CascadeAdapted  # noqa: E402
from clockwork_adapted import ClockworkAdapted  # noqa: E402
from ekya_adapted import EkyaAdapted  # noqa: E402
from hybrid_llm_adapted import HybridLLMAdapted  # noqa: E402
from inarvl_adapted import INARVLAdapted  # noqa: E402
from lmcache_adapted import LMCacheAdapted  # noqa: E402
from attentionstore_adapted import AttentionStoreAdapted  # noqa: E402
from pensieve_adapted import PensieveAdapted  # noqa: E402
from perllm_adapted import PerLLMAdapted  # noqa: E402
from r3streaming_adapted import R3StreamingAdapted  # noqa: E402
from rh8_adapted import RH8CausalDemand, RH8OracleDemand  # noqa: E402
from routellm_adapted import RouteLLMAdapted  # noqa: E402
from tuned_engine import TunedEngine  # noqa: E402
from videostorm_adapted import VideoStormAdapted  # noqa: E402
from constructed import CONSTRUCTED  # noqa: E402
from covstream_adapted import CoVStreamAdapted  # noqa: E402
from ecollm_adapted import ECOLLMAdapted  # noqa: E402
from kvflow_adapted import KVFlowAdapted  # noqa: E402
from mooncake_adapted import MooncakeAdapted  # noqa: E402
from preble_adapted import PrebleAdapted  # noqa: E402
from simplestream_adapted import SimpleStreamAdapted  # noqa: E402
from streamscout_adapted import StreamScoutAdapted  # noqa: E402
from thinking_qwenvl_adapted import ThinkingQwenVLAdapted  # noqa: E402
from uniscale_adapted import UniScaleAdapted  # noqa: E402


def build():
    return [
        naive.DeviceOnly(),
        naive.AlwaysCloudFCFS(),
        naive.RandomAdmission(budget_fraction=0.5),
        naive.RoundRobin(n_cloud_slots=2),
        naive.StaticPartition(stream_share=0.5),
        naive.EDFServiceTime(),
        naive.HindsightOracle(),
        VideoStormAdapted(objective="maxmin"),
        VideoStormAdapted(objective="maxsum"),
        EkyaAdapted(),
        TunedEngine(),
        ClockworkAdapted(),
        CascadeAdapted(),
        INARVLAdapted(),
        HybridLLMAdapted(),
        RouteLLMAdapted(target_strong_fraction=0.5),
        PerLLMAdapted(),
        AttentionStoreAdapted(),
        LMCacheAdapted(),
        PensieveAdapted(),
        RH8CausalDemand(),
        RH8OracleDemand(high_demand_sessions=["sess-A"]),
        R3StreamingAdapted(),
        # ---- addendum: new paper baselines
        ECOLLMAdapted(),
        StreamScoutAdapted(),
        PrebleAdapted(),
        MooncakeAdapted(),
        KVFlowAdapted(),
        UniScaleAdapted(),
        ThinkingQwenVLAdapted(),
        SimpleStreamAdapted(),
        CoVStreamAdapted(),
        # ---- addendum: constructed baselines
    ] + [cls() for cls in CONSTRUCTED.values()]


def main() -> int:
    out = []
    for p in build():
        label = p.name + (f"/{getattr(p, 'objective', '')}" if getattr(p, "objective", "") else "")
        t0 = time.time()
        try:
            r = replay.run(p)
        except Exception as e:                            # noqa: BLE001
            r = dict(policy=p.name, case=p.case, ran=False, errors=[f"{type(e).__name__}: {e}"],
                     interface_respected=False, budget_respected=False)
        r["label"] = label
        r["wall_s"] = round(time.time() - t0, 2)
        out.append(r)
        ok = r.get("ran") and r.get("interface_respected") and r.get("budget_respected")
        print(f"[{'PASS' if ok else 'FAIL'}] {label:34s} epochs={r.get('epochs','-'):>5} "
              f"gpu-s={r.get('spent_gpu_s','-'):>8} recall={r.get('recall','-')} "
              f"{r.get('wall_s')}s")
        if not ok:
            for e in r.get("errors", [])[:2]:
                print("        ", e)
    dest = HERE.parents[3] / "results/orchestration/study_b_baselines/b_smoke_results.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    n_ok = sum(1 for r in out
               if r.get("ran") and r.get("interface_respected") and r.get("budget_respected"))
    print(f"\n{n_ok}/{len(out)} baselines ran, respected the interface and stayed in budget")
    print(f"wrote {dest}")
    return 0 if n_ok == len(out) else 1


if __name__ == "__main__":
    sys.exit(main())
