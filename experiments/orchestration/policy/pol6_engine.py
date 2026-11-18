"""StudyPOL6-chain's engine additions, kept OUT of the frozen engine module and NOT adopted.

WHY THIS FILE EXISTS SEPARATELY. `eng1_engine.py` is named in the StudyT0b freeze
(`results/orchestration/study_t0b/t0b_freeze.json`) with its md5, and
`T0Harness.run_holdout_once` refuses to run if that md5 moves. pol4 stays the frozen and default
model, so everything StudyPOL6 builds lives here behind flags that are OFF by default, exactly as
StudyPOL5's additions live in `pol5_engine.py`.

WHAT PART A FOUND, AND WHAT IT MEANS FOR THIS MODULE. The brief's hypothesis was H-gap: that the
model treats a chained rebuild as contiguous occupancy and so over-charges background requests
for blocking that did not happen between the pieces. Part A measured the gaps on StudyENG1c Part
D FIT and the hypothesis did not survive as an EXPLANATION:

  * the gaps are real. 1,235 of them, median 45.7 ms, and almost all of that is the next piece's
    front-end window (median 42.4 ms); the client's own turnaround is 0.6 ms. Every gap that
    contains a step boundary at all carries other work, so the engine does serve background
    requests in them.
  * but pol4 is not treating the chain as contiguous. pol4 prices a front-end window per request
    from body size, so its simulation ALREADY has inter-piece gaps: 0.284 s per chain against a
    measured 0.513 s for piece1024, and 0.217 s against 0.312 s for piece2048. It also places at
    least as many background requests inside its own gaps as the measurement does.
  * so closing the gap cannot account for the error. Over the 161 chained FIT trials the gap
    position carries 31.3 s of the 303.9 s over-prediction (10 %), while the BUSY position, a
    background request whose first token lands while the engine is actually prefilling a piece,
    carries 270.5 s (89 %).

`piece_gap_scheduling` is implemented here anyway, because the brief asks for it and because it
is the one representation Part A's FIT evidence can price (it reuses StudyPOL5's already-fitted
image-aware front end and introduces no new coefficient). It is OFF by default and recorded as
unable to explain the residual.

WHAT AWAITS StudyENG1e. The leading alternative is H-granularity with H-merge: pol4 gets a
chain's total span right (3.318 s against 3.332 s for piece1024) and its step structure wrong. It
models a piece as ONE step; the engine really spreads a piece over about 1.8 shorter steps
(measured median step 0.157 s against pol4's 0.271 s) and co-batches background prefill into
them (median 3,780 other prefill tokens inside the pieces' own steps, max ctx_req 2). A
background request arriving mid-prefill therefore waits, in pol4, for the end of one long step
instead of the end of one short step.

ERRATUM 2026-11-17. An earlier draft of this docstring ended that sentence with "and can never be
merged into the piece's own step". That clause was WRONG: it was inferred from reading
`_schedulable`, not measured. pol4 does merge, and MORE often than the engine does, sharing
54.98 % of chained piece1024 steps and 69.31 % of piece2048 steps with a background prefill and
admitting up to 6, 8 and 21 prefills into a single step against the engine's observed maximum of
2 (`pol6_partA_merge_addendum.json`; report section 11). The mechanism is therefore H-overmerge,
not a missing merge: pol4 pours too many prefills into one over-long step and charges that step's
duration to all of them. The granularity and step-duration findings are unchanged.

The negative control is mono11k: it exceeds the step budget, runs alone (zero other prefill tokens,
max ctx_req 1), pol4 gets its step count right, and its over-prediction ratio is only 1.13.

That alternative cannot be turned into model parameters from this data, because ENG1c does not
record which requests were in which step; Part A's per-step composition is DERIVED by
subtraction. `AWAITING_ENG1E` names each parameter that StudyENG1e-chain's per-step request
membership would supply. Nothing here is fitted and nothing is frozen.

NO FITTED NUMBER IS TYPED IN THIS FILE. The front-end coefficients are loaded from StudyPOL5's
committed JSON by reference; a test walks this module's AST and asserts that no coefficient value
appears as a numeric literal in it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .eng1_engine import SimRequest, frontend_service_s as pol4_frontend_service_s
from .pol5_engine import Pol5Terms

POL6_TERMS_PATH = "results/orchestration/study_pol6/pol6_terms.json"

INHERITED_COEF_NAMES = ("front_end_fixed_ms", "front_end_per_mb_ms", "front_end_per_image_ms",
                        "front_end_busy_factor")

AWAITING_ENG1E = {
    "step_granularity_tokens_per_step": (
        "How many NEW tokens of a multimodal piece the engine puts in one step. Part A derives "
        "1.75 steps per piece for piece1024 and 1.92 for piece2048 against pol4's 1.0, but a "
        "derivation by subtraction cannot say which tokens went in which step. StudyENG1e's "
        "per-step request membership measures it."),
    "in_step_merge_rule": (
        "Whether, and under what admission condition, a background prefill joins a step a piece "
        "is already prefilling in. Part A shows the engine does co-schedule (median 3,780 and "
        "3,402 other prefill tokens inside the pieces' own steps, max ctx_req 2), but per-step "
        "composition is DERIVED by subtraction, not measured per request. StudyENG1e's per-step "
        "request membership names the requests in each step, which settles the rule."),
    "encoder_budget_per_step": (
        "Whether the extra step per piece is forced by an encoder or multimodal input budget "
        "rather than the token budget. Part A cannot separate the two: it sees 1.75 and 1.92 "
        "steps per piece but not what bounded them. StudyENG1e records each step's membership "
        "alongside its encoder inputs, which separates them."),
}

SCHEDULER_HOOKS = {
    "piece_gap_scheduling": (
        "Represent each piece's front-end window explicitly, so the engine is free of the chain "
        "between consecutive pieces and schedules whatever is queued. IMPLEMENTED here as a "
        "re-timing of the chain's hand-off instants (`apply_piece_gaps`), which needs no change "
        "to the frozen engine module. OFF BY DEFAULT: Part A measured that pol4 already "
        "reproduces 55 % to 70 % of the gap time and already schedules inside its own gaps, and "
        "that the gap position carries only 10 % of the over-prediction."),
    "step_granularity": (
        "Spread a piece's prefill over the number of steps the engine really uses, so a "
        "background request arriving mid-prefill waits for a short step rather than a long one. "
        "NOT IMPLEMENTED: no measured parameter exists yet. See AWAITING_ENG1E."),
    "in_step_merge": (
        "Admit a background prefill into a step a piece is already prefilling in, under the "
        "engine's own admission condition. NOT IMPLEMENTED: no measured parameter exists yet. "
        "See AWAITING_ENG1E."),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Pol6Config:
    """Which of StudyPOL6's representations are active. Every flag is OFF by default, so a
    `Pol6Config()` is pol4's behaviour and nothing in the serving model moves."""

    piece_gap_scheduling: bool = False
    step_granularity: bool = False
    in_step_merge: bool = False
    # REJECTED BY THE REGRESSION GATE (StudyPOL6 Part B). Switching it on replaces pol4's
    # body-size front end for a chained piece with the window StudyENG1e MEASURED, which moves
    # criterion (i) on ENG1e FIT from 0.5944 to 0.8472 on latency and 0.8139 to 0.9083 on TTFT,
    # but moves criterion (iii), the action's own completion, from 0.0209 to 0.1460. pol4 is
    # right about a chain's own span only because two errors cancel in it: its piece step is
    # 1.06 to 1.62x too LONG and its hand-over window is 3 to 13x too SHORT. Correcting one
    # alone breaks the span, and correcting the other means re-fitting the FROZEN step model,
    # which is outside Part B. Kept so the scored comparison is reproducible; OFF by default.
    measured_handover: bool = False

    def any_on(self) -> bool:
        return bool(self.piece_gap_scheduling or self.step_granularity or self.in_step_merge
                    or self.measured_handover)

    def unimplemented_on(self) -> List[str]:
        """Flags that are on but have no measured parameter behind them. Turning one on is a
        request for a number StudyENG1e has not delivered yet, so it raises rather than silently
        running an unparameterised rule."""
        out = []
        if self.step_granularity:
            out.append("step_granularity")
        if self.in_step_merge:
            out.append("in_step_merge")
        return out


@dataclass
class Pol6Terms:
    """StudyPOL6's terms file. It carries NO fitted coefficient of its own: Part A fitted
    nothing, and the only active numbers are StudyPOL5's front-end coefficients, which are read
    from StudyPOL5's committed JSON by reference so there is one source for them."""

    pol5: Pol5Terms
    path: str
    raw: Dict[str, Any] = field(default_factory=dict)
    config: Pol6Config = field(default_factory=Pol6Config)

    @classmethod
    def load(cls, path: Any = None, config: Optional[Pol6Config] = None,
             pol5_path: Any = None) -> "Pol6Terms":
        p = Path(path) if path is not None else (_repo_root() / POL6_TERMS_PATH)
        raw = json.loads(Path(p).read_text())
        if int(raw.get("holdout_trials_used", -1)) != 0:
            raise ValueError("%s does not state that it used zero HOLDOUT trials" % p)
        if raw.get("coef"):
            raise ValueError(
                "%s carries fitted coefficients of its own. Neither Part A nor Part B adopted "
                "one: Part B's hand-over window is recorded under `partB` as a MEASUREMENT that "
                "was REJECTED by the regression gate, not as a live coefficient." % p)
        missing = [n for n in INHERITED_COEF_NAMES
                   if n not in (raw.get("inherits") or {}).get("coefficients", [])]
        if missing:
            raise ValueError("%s does not declare the inherited coefficients %s" % (p, missing))
        pol5 = Pol5Terms.load(pol5_path)
        return cls(pol5=pol5, path=str(p), raw=raw, config=config or Pol6Config())

    def with_config(self, **flags: bool) -> "Pol6Terms":
        return replace(self, config=replace(self.config, **flags))

    def piece_front_end_s(self, body_mb: float, n_images: int, busy: bool = False) -> float:
        """The image-aware front-end window StudyPOL5 fitted, which is what a piece's gap is
        made of: Part A measures a median 42.4 ms front-end window inside a 45.7 ms gap."""
        return self.pol5.frontend_service_s(body_mb, n_images, busy=busy)

    def gap_shift_s(self, body_mb: float, n_images: int, busy: bool = False) -> float:
        """How much longer, or shorter, the image-aware front-end window is than the one pol4
        already charges. This is the whole of what `piece_gap_scheduling` adds, which is why Part
        A can price it without a new coefficient.

        SIGNED ON PURPOSE, and not clamped at zero. A chained piece is a tiny body carrying many
        images (median 0.011 MB and 11 derived images for piece1024, 0.0132 MB and 23 for
        piece2048), which is the corner where the two front-end models disagree most. Part A's
        numbers, per action: pol4 charges 29.8 ms and 29.9 ms, the image-aware term charges
        58.2 ms and 95.4 ms, and the measured median windows are 34.9 ms (piece1024, 825 gaps)
        and 44.1 ms (piece2048, 410 gaps). Both models are wrong in opposite directions,
        pol4 low and the image-aware term high, so this flag is not a calibrated improvement and
        the report says so rather than a clamp hiding it."""
        return (self.piece_front_end_s(body_mb, n_images, busy=busy)
                - pol4_frontend_service_s(body_mb, busy))

    # ---------------------------------------------------------------- Part B, D98-independent
    #
    # THE ONE FITTED TERM pol6 CARRIES. StudyENG1e-chain measures, per injection mode and piece
    # size, the window between a piece completing and the NEXT piece's first engine step
    # (`gaps.fe_next_s`): the client turnaround (7 to 14 ms), the API front end (under 10 ms for
    # uuid references, 50 to 120 ms for bytes) and the wait for dispatch behind whatever the
    # engine runs meanwhile. pol4 charges only its body-size front end, which for a chained
    # piece of uuid references is 29.9 ms against a measured 99 to 231 ms, so pol4 hands the
    # next piece to the engine far too early and the background work the engine would have
    # served in that gap is instead charged the piece's step.
    #
    # The term is a SHIFT on later pieces' submission, computable at decision time from the
    # request itself (its body size and its new tokens) and never from a cell label.
    HANDOVER_IN_SAMPLE_TOKENS = (1024, 2048)
    BYTES_BODY_MB = 0.5          # above this a piece carries image bytes, below it uuid refs

    def handover_shift_s(self, body_mb: float, new_tokens: int) -> float:
        """The measured hand-over window minus what pol4's front end already charges."""
        coef = (((self.raw.get("partB") or {}).get("measured_handover_window") or {})
                .get("piece_handover_s") or {})
        if not coef:
            raise NotImplementedError(
                "pol6's terms file records no measured hand-over window; fit it on StudyENG1e "
                "FIT with fit_pol6_terms.py before switching `measured_handover` on")
        kind = "bytes" if float(body_mb) > self.BYTES_BODY_MB else "refs"
        table = coef[kind]
        toks = sorted(int(k) for k in table)
        n = int(new_tokens)
        lo = max([x for x in toks if x <= n], default=toks[0])
        hi = min([x for x in toks if x >= n], default=toks[-1])
        if lo == hi:
            measured = float(table[str(lo)])
        else:
            f = (n - lo) / float(hi - lo)
            measured = float(table[str(lo)]) * (1 - f) + float(table[str(hi)]) * f
        return measured - pol4_frontend_service_s(body_mb, False)

    def handover_in_sample(self, new_tokens: int) -> bool:
        """StudyENG1e measured two piece sizes. Outside them the shift is interpolated."""
        return int(new_tokens) in self.HANDOVER_IN_SAMPLE_TOKENS

    def awaiting(self) -> Dict[str, str]:
        return dict(AWAITING_ENG1E)

    def adopted(self) -> bool:
        """pol6 is NOT the serving model: it is unwired, unfrozen, and every flag is off by
        default. Part A stopped at the brief's STOP AND ASK because the gap hypothesis was
        contradicted as an explanation."""
        return False

    def describe(self) -> Dict[str, Any]:
        return dict(path=self.path, adopted=self.adopted(), config=vars(self.config),
                    inherits=self.raw.get("inherits"),
                    awaiting_eng1e=self.awaiting(),
                    scheduler_hooks=dict(SCHEDULER_HOOKS),
                    partA_verdict=self.raw.get("partA_verdict"),
                    pol5_terms_path=self.pol5.path)


def apply_piece_gaps(requests: Sequence[SimRequest], terms: Pol6Terms,
                     action_tag: str = "action") -> List[SimRequest]:
    """Re-time a chain's pieces so each one's front-end window is the image-aware one.

    The frozen engine applies its own body-size front end to every request it is given. Shifting
    a piece's submission forward by `gap_shift_s` therefore lengthens the window between the
    previous piece's completion and this piece's hand-off by exactly the difference between the
    two front-end models, which is the gap representation the brief asks for, with no change to
    the frozen module. Background requests are untouched, so what they do in the longer gap is
    the engine's own scheduling rather than anything imposed here.

    The first piece is NOT shifted: its submission is the action's arrival, which the trial fixes.
    With the flag off this is the identity, so nothing can move unless the flag is set."""
    if not (terms.config.piece_gap_scheduling or terms.config.measured_handover):
        return list(requests)
    bad = terms.config.unimplemented_on()
    if bad:
        raise NotImplementedError(
            "flags %s have no measured parameter behind them; StudyENG1e-chain supplies them "
            "(see AWAITING_ENG1E)" % bad)
    acts = [r for r in requests if r.tag == action_tag]
    order = sorted(acts, key=lambda r: (r.t_submit, r.rid))
    shift = 0.0
    shifted: Dict[str, SimRequest] = {}
    for i, r in enumerate(order):
        if i > 0:
            if terms.config.measured_handover:
                shift += terms.handover_shift_s(r.body_mb, r.new_tokens())
            else:
                shift += terms.gap_shift_s(r.body_mb, r.n_images)
            shifted[r.rid] = replace(r, t_submit=r.t_submit + shift)
    return [shifted.get(r.rid, r) for r in requests]


# --------------------------------------------------------------------------- the pol6 model
@dataclass
class Pol6Sim:
    """pol6 = the frozen pol4 engine, with a chain's later pieces handed over at the window
    StudyENG1e MEASURED instead of the one pol4's body-size front end implies.

    It WRAPS the frozen simulator rather than reimplementing it: `eng1_engine.py` is one of the
    twelve files StudyT0b froze, and a Part B that re-derived the scheduler would be scoring a
    different program. With every flag off `run` delegates unchanged, which a test asserts
    output-for-output against `EngineSim` so pol6 cannot drift from pol4 silently.

    What pol6 does NOT change, because StudyENG1e measured pol4 to be right about it:
      * step granularity. Every piece runs in exactly ONE engine step, median and max 1.0 in all
        16 chain cells, which is what pol4 already does. StudyPOL6 Part A's derived 1.75 and 1.92
        steps per piece were an artifact of deriving composition by subtraction on StudyENG1c.
      * the chain's own cost. pol4 predicts a chain's span to within 3 to 13 per cent.
      * in-step merging as a RULE. Forbidding a piece to share its step with background prefill
        was implemented and REJECTED on FIT (it moved the chain ratio from 1.636 to 1.897).
    """

    sim: Any                       # the frozen EngineSim
    terms: Pol6Terms
    action_tag: str = "action"

    def model_name(self) -> str:
        return "pol6" if self.terms.config.any_on() else self.sim.model_name()

    @property
    def step(self) -> Any:
        return self.sim.step

    @property
    def chunk_tokens(self) -> int:
        return self.sim.chunk_tokens

    def run(self, requests: Sequence[SimRequest]) -> Dict[str, Any]:
        reqs = apply_piece_gaps(requests, self.terms, action_tag=self.action_tag)
        out = self.sim.run(reqs)
        out = dict(out)
        out["engine_model"] = self.model_name()
        out["pol6_config"] = vars(self.terms.config)
        return out


def make_pol6_sim(sim: Any, terms_path: Any = None, **flags: bool) -> Pol6Sim:
    """The one place a caller switches pol6 on. Default: every flag off, so pol4 behaviour."""
    terms = Pol6Terms.load(terms_path)
    if flags:
        terms = terms.with_config(**flags)
    return Pol6Sim(sim=sim, terms=terms)
