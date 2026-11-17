"""StudyPOL4-engine step 5: freeze the revised cost model for StudyT0b.

After this file is written the model may not change for T0b. It records the git state, an md5 of
every model, parameter and source file whose exact bytes decide a prediction, and the FLAG
SETTINGS of the configuration T0b is to score, so that a later run can prove it is scoring the
same model and so that a change is visible in git rather than silent.

The frozen configuration is named explicitly, and the two other selectable configurations are
recorded beside it with the reason each is not the frozen one.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .eng1_engine import ENGINE_MODELS, Pol4Terms, StepModel, make_sim
from .t0_harness import FrozenState

FROZEN_FILES = [
    "results/cost/study_eng1/eng1_step_model.json",
    "results/orchestration/study_pol4/pol4_terms.json",
    "experiments/orchestration/policy/eng1_engine.py",
    "experiments/orchestration/policy/fit_pol4_terms.py",
    "experiments/orchestration/policy/trace_replay.py",
    "experiments/orchestration/policy/kvpool.py",
    "experiments/orchestration/policy/tiers.py",
    "experiments/orchestration/policy/params.py",
    "experiments/orchestration/policy/t0_harness.py",
    "experiments/orchestration/policy/run_t0.py",
    "experiments/orchestration/policy/run_pol4.py",
    "experiments/orchestration/policy/freeze_t0b.py",
]

FROZEN_MODEL = "pol4"
OUT = "results/orchestration/study_t0b/t0b_freeze.json"


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(list(argv) if argv is not None else None)
    root = _root()
    frozen = FrozenState.freeze(root, FROZEN_FILES,
                                note="StudyPOL4-engine: the revised cost model StudyT0b is to "
                                     "score. After this freeze the model may not change for "
                                     "T0b; a change is visible in git.")
    terms = Pol4Terms.load()
    configs = {}
    for m in ENGINE_MODELS:
        sim = make_sim(m)
        configs[m] = dict(
            engine_model_flag=m, model_name=sim.model_name(),
            pol4_terms=("OFF" if sim.pol4 is None else dict(sim.pol4.coef)),
            chunk_tokens=sim.chunk_tokens)
    out = dict(
        study="StudyPOL4-engine (freeze) for StudyT0b-fidelity",
        frozen_model=FROZEN_MODEL,
        flag_settings=dict(
            selector="policy.eng1_engine.make_sim(engine_model=...) and "
                     "Eng1Engine.load(engine_model=...)",
            engine_models=list(ENGINE_MODELS),
            frozen=FROZEN_MODEL,
            configurations=configs,
            why_this_one="pol4 carries all three StudyPOL4 terms at their FITTED values and is "
                         "the only configuration that passes the brief's regression gate on the "
                         "FIT trials: criteria (ii) and (iii) improve and (iv) is unchanged. "
                         "pol4_nobatch scores criterion (i) higher on FIT data but makes "
                         "criterion (ii) WORSE than the old model (0.9500 against 0.9667), "
                         "which is exactly the trade the brief forbids, so it is NOT frozen and "
                         "is kept only as D60's term-(c) ablation. eng1 is the model "
                         "StudyT0-fidelity froze and tested on the now-spent holdout, kept "
                         "reachable for D60's bias ablation."),
        step_model=StepModel.load().describe(),
        pol4_terms=terms.describe(),
        git=frozen.git, files=dict(frozen.files), frozen_at=frozen.frozen_at,
        note=frozen.note,
        binding="StudyT0b must be evaluated on FRESH held-out data only. The 174 StudyENG1 Part "
                "C HOLDOUT triples are SPENT and were not read, predicted or evaluated by "
                "StudyPOL4-engine; the 406 Part C FIT trials are also not a held-out sample for "
                "this model, because they informed which three terms were added.",
        verify_at_freeze=frozen.verify(),
    )
    sys.path.insert(0, str(root / "experiments/lib"))
    from _provenance import stamp
    out["_provenance"] = stamp(script="policy/freeze_t0b.py", model=None, device="cpu",
                               n=len(FROZEN_FILES), args=args)
    p = root / args.out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, default=str))
    print("froze %s as %r" % (p, FROZEN_MODEL))
    print("git head %s  clean=%s" % (frozen.git["head"], frozen.git["clean"]))
    for rel, h in sorted(frozen.files.items()):
        print("  %s  %s" % (h, rel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
