"""Spec 10.2 and section 4: the DEV tables the policy reads, loaded from StudyPROF1-dev.

Nothing is invented here. A quantity the profile marks ASSUMPTION or PROPOSAL stays marked, and
`Profiles.provenance_of` answers for any key the policy uses. A quantity that does not exist
raises `MissingEvidence` rather than returning a plausible number.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "results/orchestration/prof1/profiles_dev.json"


def _nearest(tokens: int, tab: Dict[int, Any]) -> int:
    return min(tab, key=lambda s: abs(s - tokens))


class MissingEvidence(KeyError):
    """Raised when the policy asks for a quantity no committed study provides."""


@dataclass
class Profiles:
    raw: Dict[str, Any]
    path: str

    # ---- spec 4.1
    def u_sh_device(self, mapping: str = "identity") -> float:
        d = self.raw["u_SH"]["u_device"]
        return float(d["u_identity"] if mapping == "identity" else d["u_affine_proposal"])

    def u_sh_grid(self, m: int, cadence_s: float = 0.5,
                  mapping: str = "identity") -> List[Tuple[float, float]]:
        key = "u_identity" if mapping == "identity" else "u_affine_proposal"
        pts = []
        for k, v in self.raw["u_SH"]["cloud"].items():
            if v["m_frames"] != m or abs(v["cadence_s"] - cadence_s) > 1e-9:
                continue
            pts.append((float(v["delay_s"]), float(v[key])))
        if not pts:
            raise MissingEvidence("no u_SH curve for m=%d at cadence %.2f s" % (m, cadence_s))
        return sorted(pts)

    def frames_warning(self) -> str:
        return self.raw["u_SH"]["note_on_frames"]

    # ---- spec 4.3 and 6
    def rc_accuracy(self, qtype: str, rep: str, tier: str = "cloud") -> float:
        name = {("cloud", "RICH"): "32B-RICH", ("cloud", "RECENT"): "32B-RECENT",
                ("cloud", "D2"): "32B-D2", ("device", "D2"): "4B-D2",
                ("device", "N1"): "device-N1-orin"}.get((tier, rep))
        if name is None:
            raise MissingEvidence("no committed RC table for tier %r representation %r"
                                  % (tier, rep))
        tab = self.raw["RC"]["tables"][name]["by_category"]
        if qtype not in tab:
            raise MissingEvidence("question type %r is not in the %s table" % (qtype, name))
        return float(tab[qtype]["accuracy"])

    def representation_for(self, qtype: str) -> str:
        m = self.raw["RC"]["question_type_to_representation"]
        if qtype not in m:
            raise MissingEvidence("question type %r has no representation mapping" % qtype)
        return m[qtype]["representation"]

    def question_types(self) -> List[str]:
        return sorted(self.raw["RC"]["question_type_to_representation"])

    # ---- spec 3.2
    def omega(self, k: str) -> float:
        v = self.raw["class_weights_omega"]["omega"].get(k)
        if v is None:
            raise MissingEvidence("omega_%s is not calibrated (no committed accuracy pair)" % k)
        return float(v)

    # ---- spec 4.3, 6.2 durations
    def duration(self, name: str) -> Dict[str, Any]:
        d = self.raw["durations"]
        if name not in d:
            raise MissingEvidence("no committed duration family %r" % name)
        return d[name]

    def seconds_per_token(self, kind: str, tokens: int = 11000) -> float:
        """The committed per-token rate at the NEAREST measured history size.

        StudyRH5 measured 11k and 28k only. Spec 4.3 needs a rate at arbitrary sizes, so the
        interpolation rule the profile itself states is applied and nothing is extrapolated
        outside the two measured sizes (see spec_map.AMBIGUITIES A6)."""
        fam = {"rebuild": "cold_rebuild_per_token", "reload": "host_reload_per_token"}[kind]
        tab = {int(k): float(v) for k, v in self.duration(fam)["seconds_per_token"].items()}
        return tab[_nearest(tokens, tab)]

    def catchup_per_frame_s(self, model: str = "32BI") -> float:
        v = self.duration("catchup_per_frame")["seconds_per_frame"]
        if model not in v:
            raise MissingEvidence("no catch-up rule for model %r" % model)
        return float(v[model])

    def recall_ttft_s(self, readiness: str, tokens: int = 11000) -> float:
        """Committed recall TTFT. `readiness` is COLD, GPU-WARM or HOST-WARM (spec 6 tiers)."""
        v = self.duration("recall_ttft_by_readiness")["values_s"]
        sizes = sorted({int(k.split("|")[0]) for k in v})
        key = "%d|%s" % (_nearest(tokens, {s: s for s in sizes}), readiness.upper())
        if key not in v:
            raise MissingEvidence("no committed recall TTFT for %r" % key)
        return float(v[key])

    def episodic_ttft_s(self, model: str, n: int, load_pct: int) -> float:
        v = self.duration("episodic_ttft_by_n")["values_s"]
        key = "%s_N%d_load%d" % (model, n, load_pct)
        if key not in v:
            raise MissingEvidence("no committed episodic TTFT for %r" % key)
        return float(v[key])

    def device_answer_latency_s(self) -> float:
        return float(self.duration("device_answer_latency")["seconds"])

    # ---- spec 4, 7.5, 7.11
    def link(self) -> Dict[str, Any]:
        return self.raw["link_model"]

    def uplink_bytes_per_s(self) -> float:
        return float(self.link()["bandwidth"]["uplink_bytes_per_s"])

    def rtt_s(self) -> float:
        return float(self.link()["rtt"]["seconds"])

    def jitter(self) -> None:
        raise MissingEvidence(
            "jitter is declared ABSENT by StudyPROF1-dev: no committed trace carries it. "
            "Spec 13 pins it (P6). The policy must not assume a value.")

    def bandwidth_percentiles(self) -> None:
        raise MissingEvidence(
            "bandwidth percentiles do not exist in committed data: the traces carry a "
            "connectivity bit per second, not a bandwidth series. Bandwidth is the committed "
            "13.6 Mbit/s constant, labelled ASSUMPTION.")

    # ---- spec 6.4
    def lambda_rc_default(self) -> float:
        return float(self.raw["demand"]["lambda_rc_default_per_s"])

    def conditional_rate_available(self) -> bool:
        t = self.raw["demand"]["conditional_rate_test_6_4"]
        return bool(t.get("computable", False))

    def provenance_of(self, dotted: str) -> str:
        node: Any = self.raw
        for part in dotted.split("."):
            node = node[part]
        if isinstance(node, dict):
            for k in ("provenance", "dev_rule", "rule"):
                if k in node:
                    return str(node[k])
        return "see the profile JSON; this key carries no provenance field of its own"


def load_profiles(path: Optional[Path] = None) -> Profiles:
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        raise MissingEvidence("the DEV profile %s does not exist; run StudyPROF1-dev first" % p)
    return Profiles(raw=json.loads(p.read_text()), path=str(p))
