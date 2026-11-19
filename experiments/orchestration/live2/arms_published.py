#!/usr/bin/env python3
"""D130: the StudyB published-system baselines, ported into live2.

StudyB adapted about two dozen published systems in `baselines/*_adapted.py`, each with a CARD in
`baselines/cards/` recording exactly how it was adapted to this setting. Only eight arms existed
in live2. This file ports the adapted classes as live2 arms WITHOUT reinterpreting any card: each
wrapper subclasses `(Live2ArmMixin, <AdaptedClass>)` exactly as `arms.py` does for B8 and B9, and
overrides nothing but `name` and the provenance string.

WHAT A WRAPPER MAY AND MAY NOT DO. It may give the arm its live2 name and record where it came
from. It may NOT change `decide`, re-tune a constructor default, or widen an arm's action space,
because the card is the committed record of the adaptation and the arm's behaviour is the thing
under test.

CARD EXPERIMENT SCOPE, WHICH THE LEADERBOARD MUST RESPECT. live2 is the C-mixed setting
(dashcams and robots together). Several arms named in D130's priority list carry cards scoped to
A-episodic or B-recall ONLY, so running them here puts them outside the regime their card claims.
They are ported anyway because D130 names them, and each one's scope is published in
`live2_describe()["card_experiments"]` and listed in `OUT_OF_CARD_SCOPE` below, so a reader can
see at a glance which rows are inside their card and which are not. **A row for an out-of-scope
arm is not evidence about that published system in its own setting.**

SKIPPED ARMS and the reason for each are in `SKIPPED`, and the reason is also written into the
arm's card, as D130 requires.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_ROOT / "experiments/orchestration/baselines"),
           str(_ROOT / "experiments/orchestration/sim"),
           str(_ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interface import Policy                                            # noqa: E402
from arms import Live2ArmMixin                                          # noqa: E402

import constructed as CONS                                              # noqa: E402
import attentionstore_adapted as _attentionstore                        # noqa: E402
import cascade_adapted as _cascade                                      # noqa: E402
import clockwork_adapted as _clockwork                                  # noqa: E402
import ecollm_adapted as _ecollm                                        # noqa: E402
import ekya_adapted as _ekya                                            # noqa: E402
import hybrid_llm_adapted as _hybrid                                    # noqa: E402
import inarvl_adapted as _inarvl                                        # noqa: E402
import kvflow_adapted as _kvflow                                        # noqa: E402
import lmcache_adapted as _lmcache                                      # noqa: E402
import mooncake_adapted as _mooncake                                    # noqa: E402
import pensieve_adapted as _pensieve                                    # noqa: E402
import perllm_adapted as _perllm                                        # noqa: E402
import preble_adapted as _preble                                        # noqa: E402
import r3streaming_adapted as _r3                                       # noqa: E402
import routellm_adapted as _routellm                                    # noqa: E402
import uniscale_adapted as _uniscale                                    # noqa: E402
import videostorm_adapted as _videostorm                                # noqa: E402


class _PublishedArm(Live2ArmMixin):
    """Shared wrapper behaviour: a live2 name, provenance, and the card's own scope.

    `CARD_EXPERIMENTS` is copied from the adapted class's own `experiments` tuple, which is the
    card's claim, so it cannot drift from the card by being retyped here.
    """

    card: str = ""
    adapted_from: str = ""

    def live2_describe(self) -> Dict[str, Any]:
        d = super().live2_describe()
        d["card"] = self.card
        d["adapted_from"] = self.adapted_from
        d["card_experiments"] = list(getattr(self, "experiments", ()) or ())
        d["in_card_scope_for_live2"] = "C-mixed" in (getattr(self, "experiments", ()) or ())
        return d


def _wrap(cls_name: str, base: type, live2_name: str, card: str, source: str) -> type:
    """Build one wrapper. `decide` is NEVER overridden: the adapted class's own runs."""

    def __init__(self: Any, *a: Any, **kw: Any) -> None:
        base.__init__(self, *a, **kw)
        self.name = live2_name

    return type(cls_name, (_PublishedArm, base), dict(
        __init__=__init__,
        __doc__="D130 port of %s. The adapted class decides; this wrapper only names it." % source,
        live2_source=source + " AS COMMITTED (D130 port, decide() untouched)",
        card="baselines/cards/%s" % card,
        adapted_from=source))


# ---------------------------------------------------------------- 1: constructed B7 and B10
B7EdfFeasibilityArm = _wrap("B7EdfFeasibilityArm", CONS.B7EDFFeasibility,
                            "b7-edf-feasibility", "constructed.md",
                            "baselines/constructed.py::B7EDFFeasibility")
B10BlockingAwareArm = _wrap("B10BlockingAwareArm", CONS.B10BlockingAwareAdmission,
                            "b10-blocking-aware", "constructed.md",
                            "baselines/constructed.py::B10BlockingAwareAdmission")

# ---------------------------------------------------------------- 2
ClockworkArm = _wrap("ClockworkArm", _clockwork.ClockworkAdapted, "clockwork", "clockwork.md",
                     "baselines/clockwork_adapted.py::ClockworkAdapted")
VideoStormArm = _wrap("VideoStormArm", _videostorm.VideoStormAdapted, "videostorm",
                      "videostorm.md", "baselines/videostorm_adapted.py::VideoStormAdapted")
R3StreamingArm = _wrap("R3StreamingArm", _r3.R3StreamingAdapted, "r3-streaming",
                       "r3streaming.md", "baselines/r3streaming_adapted.py::R3StreamingAdapted")

# ---------------------------------------------------------------- 3
HybridLLMArm = _wrap("HybridLLMArm", _hybrid.HybridLLMAdapted, "hybrid-llm", "hybrid_llm.md",
                     "baselines/hybrid_llm_adapted.py::HybridLLMAdapted")
RouteLLMArm = _wrap("RouteLLMArm", _routellm.RouteLLMAdapted, "routellm", "routellm.md",
                    "baselines/routellm_adapted.py::RouteLLMAdapted")
ECOLLMArm = _wrap("ECOLLMArm", _ecollm.ECOLLMAdapted, "eco-llm", "ecollm.md",
                  "baselines/ecollm_adapted.py::ECOLLMAdapted")
CascadeArm = _wrap("CascadeArm", _cascade.CascadeAdapted, "confidence-cascade", "cascade.md",
                   "baselines/cascade_adapted.py::CascadeAdapted")

# ---------------------------------------------------------------- 4
PrebleArm = _wrap("PrebleArm", _preble.PrebleAdapted, "preble", "preble.md",
                  "baselines/preble_adapted.py::PrebleAdapted")
KVFlowArm = _wrap("KVFlowArm", _kvflow.KVFlowAdapted, "kvflow", "kvflow.md",
                  "baselines/kvflow_adapted.py::KVFlowAdapted")
MooncakeArm = _wrap("MooncakeArm", _mooncake.MooncakeAdapted, "mooncake", "mooncake.md",
                    "baselines/mooncake_adapted.py::MooncakeAdapted")
AttentionStoreArm = _wrap("AttentionStoreArm", _attentionstore.AttentionStoreAdapted,
                          "attentionstore", "attentionstore.md",
                          "baselines/attentionstore_adapted.py::AttentionStoreAdapted")
LMCacheArm = _wrap("LMCacheArm", _lmcache.LMCacheAdapted, "lmcache", "lmcache.md",
                   "baselines/lmcache_adapted.py::LMCacheAdapted")
PensieveArm = _wrap("PensieveArm", _pensieve.PensieveAdapted, "pensieve", "pensieve.md",
                    "baselines/pensieve_adapted.py::PensieveAdapted")

# ---------------------------------------------------------------- 5: remaining C-mixed cards
EkyaArm = _wrap("EkyaArm", _ekya.EkyaAdapted, "ekya", "ekya.md",
                "baselines/ekya_adapted.py::EkyaAdapted")
INARVLArm = _wrap("INARVLArm", _inarvl.INARVLAdapted, "inar-vl", "inarvl.md",
                  "baselines/inarvl_adapted.py::INARVLAdapted")
PerLLMArm = _wrap("PerLLMArm", _perllm.PerLLMAdapted, "perllm", "perllm.md",
                  "baselines/perllm_adapted.py::PerLLMAdapted")
UniScaleArm = _wrap("UniScaleArm", _uniscale.UniScaleAdapted, "uniscale", "uniscale.md",
                    "baselines/uniscale_adapted.py::UniScaleAdapted")


PUBLISHED_ARMS: Dict[str, Any] = {
    "b7-edf-feasibility": B7EdfFeasibilityArm,
    "b10-blocking-aware": B10BlockingAwareArm,
    "clockwork": ClockworkArm,
    "videostorm": VideoStormArm,
    "r3-streaming": R3StreamingArm,
    "hybrid-llm": HybridLLMArm,
    "routellm": RouteLLMArm,
    "eco-llm": ECOLLMArm,
    "confidence-cascade": CascadeArm,
    "preble": PrebleArm,
    "kvflow": KVFlowArm,
    "mooncake": MooncakeArm,
    "attentionstore": AttentionStoreArm,
    "lmcache": LMCacheArm,
    "pensieve": PensieveArm,
    "ekya": EkyaArm,
    "inar-vl": INARVLArm,
    "perllm": PerLLMArm,
    "uniscale": UniScaleArm,
}

# Arms whose CARD does not claim C-mixed. Ported because D130 names them, but a leaderboard row
# for one of these is outside the regime its card claims and is not evidence about that published
# system in its own setting.
OUT_OF_CARD_SCOPE: Tuple[str, ...] = (
    "videostorm",            # A-episodic
    "r3-streaming",          # A-episodic, B-recall
    "confidence-cascade",    # A-episodic
    "kvflow",                # B-recall
    "attentionstore",        # B-recall
    "lmcache",               # B-recall
    "pensieve",              # B-recall
)

# name -> why it was not ported. Each reason is also written into the arm's card.
SKIPPED: Dict[str, str] = {}
