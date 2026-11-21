"""Per-type host-tier state as per-request offload controls (full v5 component 1, D56 and D150).

D56 makes where each history lives a core decision, and D150 records that vLLM cannot be commanded
to pin KV. What vLLM 0.31.0 does expose is per-request offload control, so the policy expresses the
per-type rule the user set:

    assistive (single-shot)  no host retention, no reload     nothing to come back to: one view, one answer
    dashcam                  no host retention                a dead episode ages out of GPU and never flushes host
    robot history            retention on, reload allowed     the one history worth paying to keep

D164: these are POLICY actions. Baselines run vLLM defaults, so the controls are emitted only for an
arm that declares `live2_offload_controls = True`; every other arm's body is byte-identical to its
committed one.

The robot branch deliberately emits NO field, because retention-on and reload-allowed IS the engine
default, and a no-op field would be a write that claims a decision it does not make. Only the two
deviating types carry a control.

WHAT IS ESTABLISHED. This module decides and emits, and offload_verify.py has now confirmed on the
H100 that the engine HONOURS both spellings used here (see the block below). The rule is therefore
actuatable, not merely emitted. The one residual gap is the register of the forbid-reload evidence:
it rests on a between-probe comparison with the identically constructed positive control, because
that probe's own within-probe control was contaminated by its predecessor's recompute.
"""
from typing import Any, Dict, Optional

# int 0, never False: a bool would be a different declared type arriving at the engine, and the
# coerced-field failure (a field declared int read as bool, turning 2 into 1) is a committed
# precedent in this repo's protocol.
# VERIFIED ON THE H100, 2026-11-21 (results/orchestration/live2/offload_verify/
# offload_verify_h100.json, run on a fresh round-1 server). Do NOT change these spellings:
#   max_offload_tokens: 0   HONOURED. Store with it, evict, re-read: COLD (cached 0, external 0),
#                           against the positive control's HOST-WARM (external 8,080) on an
#                           otherwise identical probe. This is what the dashcam and assistive
#                           no-retention rule rides on.
#   max_load_tokens: 0      HONOURED. Read came back COLD at 1.387 s, matching the 1.411 s cold
#                           read, where the identically constructed positive control was
#                           HOST-WARM at 0.123 s.
#   kv_load_tiers: []       NOT HONOURED. The same probe came back HOST-WARM (external 8,080,
#                           0.120 s), so the empty tier filter is ignored on this build. It is
#                           recorded here because it is the obvious-looking way to express
#                           "forbid reload" and it silently does nothing.
NO_RETENTION: Dict[str, Any] = {"max_offload_tokens": 0}
NO_RETENTION_NO_RELOAD: Dict[str, Any] = {"max_offload_tokens": 0, "max_load_tokens": 0}

RULE: Dict[str, Optional[Dict[str, Any]]] = {
    "assistive": NO_RETENTION_NO_RELOAD,
    "dashcam": NO_RETENTION,
    "robot": None,
}

KNOWN_TYPES = tuple(RULE)


def params_for(device_type: Optional[str], enabled: bool) -> Optional[Dict[str, Any]]:
    """The controls this device's requests carry, or None for the engine default.

    An unknown device type returns None rather than guessing: a type we have not ruled on gets the
    engine default, which is the committed behaviour, instead of a silently invented policy.
    """
    if not enabled or not device_type:
        return None
    r = RULE.get(str(device_type))
    return dict(r) if r else None


def arm_enables(arm: Any) -> bool:
    """D164: only an arm that declares the capability emits controls."""
    return bool(getattr(arm, "live2_offload_controls", False))
