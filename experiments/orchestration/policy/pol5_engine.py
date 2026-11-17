"""StudyPOL5-engine's additions, kept OUT of the frozen engine module.

WHY THIS FILE EXISTS SEPARATELY. `eng1_engine.py` is named in the StudyT0b freeze
(`results/orchestration/study_t0b/t0b_freeze.json`) with its md5, and `T0Harness.run_holdout_once`
refuses to run if that md5 moves. StudyPOL5 stopped at its regression gate without adopting pol5,
so the frozen module is byte-identical to the committed one and everything StudyPOL5 built lives
here, unwired. Adopting pol5 later means a new row, a new freeze and wiring these two hooks into
the engine; until then nothing in the serving model can change under a frozen test.

WHAT IS HERE AND WHAT IT IS WORTH (reports/study_pol5_engine.md):

  `Pol5Terms`            the fitted coefficients, loaded from the committed JSON, never typed.
  `frontend_service_s`   the image-aware front end: 24.10 ms + 4.16 per MB + 3.099 per image,
                         R^2 0.985 on 58,085 measured windows, busy factor 1.070. StudyPOL4's
                         body-size-only fit prices a 124-image 22.8 MB action at 489 ms against a
                         measured 554 ms. This one stands on its own evidence.
  `host_reload_ms`       the capped-host regime: transfer at the counter's own 44.69 GB/s plus
                         the measured 53.3 ms of non-transfer overhead per reload.
  SCHEDULER HOOKS        described in `SCHEDULER_HOOKS` and NOT implemented here, because both
                         rules they would express were TESTED ON FIT AND REJECTED.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

POL5_TERMS_PATH = "results/orchestration/study_pol5/pol5_terms.json"
POL5_COEF_NAMES = ("front_end_fixed_ms", "front_end_per_mb_ms", "front_end_per_image_ms",
                   "front_end_busy_factor", "host_kv_transfer_gb_per_s_capped",
                   "host_kv_reload_overhead_ms_capped", "async_schedule_lag_steps",
                   "serial_prefill_admission")

SCHEDULER_HOOKS = {
    "async_schedule_lag_steps": (
        "A request handed over during a step may not join it, because the engine prepared that "
        "step while the previous one ran (StudyENG1d section 6). Implemented as a cutoff in "
        "`_schedulable`: eligibility is measured against the PREVIOUS step's start instead of "
        "the current time. TESTED ON FIT AND REJECTED: it raised the piece1024 imposed-delay "
        "ratio on StudyENG1c Part D FIT from 1.74 to 2.42, because it delayed eligibility "
        "without preventing the merge."),
    "serial_prefill_admission": (
        "At most one prefill per step. Implemented as a break after the first candidate in "
        "`_schedulable`. TESTED ON FIT AND REJECTED: 1.74 to 3.25 on the same cut. Its premise "
        "was also unsound: it was inferred from the step-log field `it[1]`, which is not a "
        "prefill count."),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass
class Pol5Terms:
    """StudyPOL5's coefficients, read from the committed JSON. Nothing is typed here, which a
    test asserts by checking that no coefficient's value appears in this file's source."""

    coef: Dict[str, float]
    path: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Any = None) -> "Pol5Terms":
        p = Path(path) if path is not None else (_repo_root() / POL5_TERMS_PATH)
        raw = json.loads(Path(p).read_text())
        if int(raw.get("holdout_trials_used", -1)) != 0:
            raise ValueError("%s does not state that it used zero HOLDOUT trials" % p)
        missing = [n for n in POL5_COEF_NAMES if n not in raw.get("coef", {})]
        if missing:
            raise ValueError("%s is missing the coefficients %s" % (p, missing))
        return cls(coef={n: float(raw["coef"][n]) for n in POL5_COEF_NAMES}, path=str(p), raw=raw)

    def frontend_service_s(self, body_mb: float, n_images: int, busy: bool = False) -> float:
        ms = (self.coef["front_end_fixed_ms"]
              + self.coef["front_end_per_mb_ms"] * max(float(body_mb), 0.0)
              + self.coef["front_end_per_image_ms"] * max(int(n_images), 0))
        if busy:
            ms *= self.coef["front_end_busy_factor"]
        return ms / 1000.0

    def host_reload_ms(self, external_tokens: int, bytes_per_token: float) -> float:
        tok = max(int(external_tokens), 0)
        if tok <= 0:
            return 0.0
        gb = (tok * float(bytes_per_token)) / 1e9
        return ((gb / self.coef["host_kv_transfer_gb_per_s_capped"]) * 1000.0
                + self.coef["host_kv_reload_overhead_ms_capped"])

    def adopted(self) -> bool:
        """Both structural rules are off and this module is not wired into the engine, so pol5
        is NOT the serving model. StudyPOL5 stopped at its regression gate."""
        return False

    def describe(self) -> Dict[str, Any]:
        return dict(path=self.path, coef=dict(self.coef), adopted=self.adopted(),
                    scheduler_hooks=dict(SCHEDULER_HOOKS),
                    front_end=(self.raw.get("front_end") or {}).get("fit_data"),
                    host_kv_transfer=(self.raw.get("host_kv_transfer") or {}).get("applies_to"))
