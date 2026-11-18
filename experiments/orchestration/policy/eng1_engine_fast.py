"""StudyLIVE2-perf: a COPY of `eng1_engine.py` carrying ONE change, for the live policy path.

THE FROZEN FILE IS NEVER EDITED (user ruling, 2026-11-18). `experiments/orchestration/policy/
eng1_engine.py` is one of the twelve files in the StudyT0b freeze
(`results/orchestration/study_t0b/t0b_freeze.json`) and three committed tests assert its md5.
This file is that file, copied, with the single change below; the freeze stays untouched and its
md5 tests stay green.

THE ONE CHANGE, and nothing else. `Eng1Engine.predict` is called about 774,000 times in a
64-device policy cell, and on every call it rebuilt two PROVENANCE strings, each constructing a
`pathlib.Path` purely to take a basename. That is 1.55 M path parses, about 15 % of a profiled
64-device run, for two strings that are constant for a given engine and that no arithmetic
reads. They are now built once per engine and reused (`_basis_step`, `_basis_pol4`).

NOTHING ELSE DIFFERS. `diff eng1_engine.py eng1_engine_fast.py` is this docstring plus the
provenance caching, and `tests/test_eng1_engine_fast.py` asserts that the two classes' `predict`
return IDENTICAL `Prediction`s, field for field including `basis`, over every StudyENG1 /
StudyENG1c Part C FIT trial, every StudyENG1d FIT trial, and every `predict` call the policy
fixtures actually make.

WHICH ONE RUNS WHERE. The live policy path (`live2/arms_policy.py`) loads this copy. Every
replay, fit and scoring path keeps loading the frozen module, so nothing that produced a
committed number changes its import.

--- the frozen file's own docstring follows ---
The MEASURED engine model: StudyENG1's step model, front-end serialization and admission
stall, as the `EngineModel` the policy calls and as a step-level simulator T0 replays traces
through.

THIS MODULE FITS NOTHING. Every coefficient is read from
`results/cost/study_eng1/eng1_step_model.json`, which StudyENG1 fitted on Part A, Part B E0 and
nothing else; Part C and the HOLDOUT never entered it. The structural facts are read from
`reports/study_eng1_steptime.md` and are listed here with their section, so a reader can check
each one against the report:

  section 5   step duration = intercept + piecewise-linear in the step's new prefill tokens
              + per image encoded + per decode request + per prefill request
              + per (token x cached context) + the NEXT step's admission terms.
              Step duration is the BUSY INTERVAL between consecutive output batches, not
              `elapsed_ms`, which section 2.2 rejected as a lower bound.
  sections    the two measured facts about how prefills share a step, BOTH of which the
  5 and 6     simulator needs, because the step model was fitted on steps of both kinds:
              (a) H-step, SUB-LINEAR: Part A A1 measured BATCHES of k simultaneous small
              prefills, k in {1, 2, 4, 8, 16}, and batch time(16) / (16 x time(1)) is 0.510 for
              N=1 and 0.731 for N=3. Those batched steps are part of the step model's own fit
              data, and the model's `per_prefill_req` and `per_encoder_input` terms are per-step
              aggregates over such a batch. So SHORT prefills that fit the step's token budget
              are scheduled TOGETHER.
              (b) H-admit verdict (a), SERIAL BLOCKING: a request arriving while a LONG prefill
              runs waits for essentially all of that request's remaining work (rho 0.97 to 1.00
              at 25 to 75 % of the way through a monolithic 11k prefill). The report's own
              instruction is "the rollout must model the running request's remaining work as a
              queue ahead of a newly arriving request, not as a shared step". So a prefill that
              does NOT fit one step's budget runs ALONE until it is done, which is vLLM's single
              partial-prefill slot.
              Taking only (b) and serializing every prefill would use the step model outside the
              batch compositions it was fitted on. Both rules are therefore implemented.
  section 7   the front end is a SERIAL single server whose service time is
              29.6 ms + 20.2 ms per MB when it was idle and 6.9 ms + 17.7 ms per MB when it was
              already busy. The engine queue after hand-off is microseconds, so all later
              waiting is inside the steps.
  section 8   the admission step: an image-bearing request's multimodal preparation is on the
              engine's critical path and delays whatever is running. It enters through the step
              model's two admission terms, which price the NEXT step's images and encoder
              tokens.
  section 1.2 the servers: vLLM 0.31.0, chunked prefill with 8,192-token steps, fcfs, prefix
              caching ON, KV pool 62,944 tokens. CHUNK_TOKENS and the KV pool size are
              parameters here, not constants, because D56 makes both inputs.
  definition  a D2 frame is 90 prompt tokens (section 11 check 4), which is how a request's
              encoder-token count is derived from its image count. 90 x 91 = 8,190 reproduces
              the 41-plus-image admission stall of 66 ms at the committed 18.1 ms per 1k
              encoder tokens, and that agreement is the only reason the convention is used.

WHAT IS KNOWN TO BE MISSING, stated because T0 exists to measure it rather than to be passed:
there is no sub-linear batching of concurrent prefills, because prefill is serial; the
per-request front-end cost is modelled as the committed two-regime fit and not per request type;
and the step model's admission residual (median 27.9 ms over 1,907 admission steps) is left as
it is. Nothing here is corrected against Part C.

StudyPOL4-engine (2026-11-17) ADDS THREE NAMED TERMS BEHIND A FLAG, and changes nothing when the
flag is off. `EngineSim(step=...)` and `Eng1Engine(step=...)` with `pol4=None` are the model
StudyT0-fidelity froze, bit for bit; `pol4=Pol4Terms.load()` is the revised model. The three
terms are (a) `host_reload_ms`, the host-KV transfer StudyT0 found entirely absent, (b)
`long_prefill_scale`, a correction to the own-block prediction of a prefill that needs more than
one step, and (c) `batch_prefill_gain`, the measured gain when several short prefills share a
step. EVERY COEFFICIENT OF ALL THREE IS READ FROM
`results/orchestration/study_pol4/pol4_terms.json`, fitted by `fit_pol4_terms.py` on StudyENG1
Parts A, B and D and StudyENG1b; nothing is typed here, which a test asserts for the new terms
as it already did for the step model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .engine import Prediction, Request

# StudyENG1 section 1.2: the serving configuration all of Parts A to D ran under.
CHUNK_TOKENS = 8192
KV_POOL_TOKENS_H100NVL = 62_944

# StudyENG1 section 7, front-end service, both regimes.
FE_IDLE_FIXED_MS = 29.6
FE_IDLE_PER_MB_MS = 20.2
FE_BUSY_FIXED_MS = 6.9
FE_BUSY_PER_MB_MS = 17.7

# StudyENG1 section 11, check 4: a D2 frame is 90 prompt tokens.
TOKENS_PER_FRAME = 90

STEP_MODEL_PATH = ("results/cost/study_eng1/eng1_step_model.json")
POL4_TERMS_PATH = ("results/orchestration/study_pol4/pol4_terms.json")

# The selectable engine models. "eng1" is the model StudyT0-fidelity froze and tested on the
# now-spent holdout; "pol4" is that model plus StudyPOL4-engine's three terms at their fitted
# values; "pol4_nobatch" is "pol4" with term (c) at its NEUTRAL value, which is a FLAG SETTING
# and not a refit (the coefficient is still the one in the committed JSON, it is simply switched
# off). D60's bias ablation needs all three, so all three stay reachable and all three are
# tested.
ENGINE_MODELS = ("eng1", "pol4", "pol4_nobatch")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass
class StepModel:
    """StudyENG1's fitted step-time model, read from the committed JSON and never refitted."""

    coef: Dict[str, float]
    knots: Sequence[int]
    path: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Any = None) -> "StepModel":
        p = Path(path) if path is not None else (_repo_root() / STEP_MODEL_PATH)
        raw = json.loads(Path(p).read_text())
        if raw.get("fit_data", "").find("HOLDOUT") < 0:
            raise ValueError("%s does not state its fit data; refusing to use a step model whose "
                             "provenance is unstated" % p)
        return cls(coef=dict(raw["coef"]), knots=tuple(raw["knots"]), path=str(p), raw=raw)

    def step_ms(self, new_tokens: int, images_in_step: int, decode_reqs: int, prefill_reqs: int,
                cached_ctx_tokens: int, next_images: int = 0,
                next_encoder_tokens: int = 0) -> float:
        c = self.coef
        tok = max(int(new_tokens), 0)
        ms = c["intercept_ms"]
        ms += c["per_tok_ms"] * tok
        ms += c["per_tok_above_512_ms"] * max(0, tok - 512)
        ms += c["per_tok_above_2048_ms"] * max(0, tok - 2048)
        ms += c["per_tok_above_4096_ms"] * max(0, tok - 4096)
        ms += c["per_encoder_input_ms"] * max(int(images_in_step), 0)
        ms += c["per_decode_req_ms"] * max(int(decode_reqs), 0)
        ms += c["per_prefill_req_ms"] * max(int(prefill_reqs), 0)
        ms += c["per_tok_x_ctx_per_1e6_ms"] * tok * max(int(cached_ctx_tokens), 0) / 1e6
        ms += c["admission_per_image_ms"] * max(int(next_images), 0)
        ms += c["admission_per_1k_encoder_tokens_ms"] * max(int(next_encoder_tokens), 0) / 1e3
        return max(ms, 0.0)

    def describe(self) -> Dict[str, Any]:
        return dict(path=self.path, n_fit_steps=self.raw.get("n"), r2=self.raw.get("r2"),
                    fit_data=self.raw.get("fit_data"), coef=dict(self.coef),
                    knots=list(self.knots))


POL4_COEF_NAMES = ("host_kv_bytes_per_token", "host_kv_transfer_gb_per_s",
                   "host_kv_lookup_fixed_ms", "long_prefill_scale_intercept",
                   "long_prefill_scale_per_1k_tokens", "batch_prefill_gain_exponent")


@dataclass
class Pol4Terms:
    """StudyPOL4-engine's three terms, read from the committed JSON and never refitted here.

    `for_probe` exists only so the fitting script and the tests can evaluate ONE term at a
    time; it builds a terms object whose other coefficients are NEUTRAL (no transfer, scale
    1.0, exponent 0.0), so a probe can never smuggle a fitted value into this module."""

    coef: Dict[str, float]
    path: str
    raw: Dict[str, Any] = field(default_factory=dict)

    NEUTRAL: Dict[str, float] = None

    @classmethod
    def load(cls, path: Any = None) -> "Pol4Terms":
        p = Path(path) if path is not None else (_repo_root() / POL4_TERMS_PATH)
        raw = json.loads(Path(p).read_text())
        if int(raw.get("holdout_trials_used", -1)) != 0:
            raise ValueError("%s does not state that it used zero HOLDOUT trials; refusing to "
                             "use terms whose fit data is unstated" % p)
        missing = [n for n in POL4_COEF_NAMES if n not in raw.get("coef", {})]
        if missing:
            raise ValueError("%s is missing the coefficients %s" % (p, missing))
        return cls(coef={n: float(raw["coef"][n]) for n in POL4_COEF_NAMES}, path=str(p),
                   raw=raw)

    @classmethod
    def load_for_model(cls, engine_model: str, path: Any = None) -> Optional["Pol4Terms"]:
        if engine_model not in ENGINE_MODELS:
            raise ValueError("engine_model must be one of %s, got %r" % (ENGINE_MODELS,
                                                                         engine_model))
        if engine_model == "eng1":
            return None
        t = cls.load(path)
        if engine_model == "pol4_nobatch":
            coef = dict(t.coef)
            coef["batch_prefill_gain_exponent"] = cls.NEUTRAL["batch_prefill_gain_exponent"]
            return cls(coef=coef, path="%s [term (c) switched off]" % t.path, raw=t.raw)
        return t

    @classmethod
    def for_probe(cls, **overrides: float) -> "Pol4Terms":
        coef = dict(cls.NEUTRAL)
        for k, v in overrides.items():
            if k not in POL4_COEF_NAMES:
                raise KeyError("unknown POL4 coefficient %r" % k)
            coef[k] = float(v)
        return cls(coef=coef, path="(probe: neutral except %s)" % sorted(overrides),
                   raw=dict(probe=True))

    # --- (a) host-KV transfer, StudyENG1 Part D's measured bytes and rate
    def host_reload_ms(self, external_tokens: int) -> float:
        tok = max(int(external_tokens), 0)
        if tok <= 0:
            return 0.0
        by = self.coef["host_kv_bytes_per_token"] * tok
        rate = self.coef["host_kv_transfer_gb_per_s"] * 1e9
        if rate <= 0:
            return 0.0
        return self.coef["host_kv_lookup_fixed_ms"] + 1000.0 * by / rate

    # --- (b) the own-block correction for a prefill that needs more than one step
    def long_prefill_scale(self, total_new_tokens: int, chunk_tokens: int) -> float:
        if int(total_new_tokens) <= int(chunk_tokens):
            return 1.0
        s = (self.coef["long_prefill_scale_intercept"]
             + self.coef["long_prefill_scale_per_1k_tokens"] * total_new_tokens / 1000.0)
        return max(s, 0.0)

    # --- (c) the measured gain when several short prefills share a step
    def batch_prefill_gain(self, n_prefill_reqs: int) -> float:
        m = max(int(n_prefill_reqs), 0)
        if m <= 1:
            return 1.0
        return float(m) ** (-self.coef["batch_prefill_gain_exponent"])

    def describe(self) -> Dict[str, Any]:
        return dict(path=self.path, coef=dict(self.coef),
                    fit_data=self.raw.get("holdout_exclusion"),
                    terms=dict(
                        host_kv_transfer=(self.raw.get("host_kv_transfer") or {}).get("fit_data"),
                        long_cold_prefill=(self.raw.get("long_cold_prefill")
                                           or {}).get("fit_data"),
                        sub_linear_batching=(self.raw.get("sub_linear_batching")
                                             or {}).get("fit_data")))


Pol4Terms.NEUTRAL = dict(host_kv_bytes_per_token=0.0, host_kv_transfer_gb_per_s=1.0,
                         host_kv_lookup_fixed_ms=0.0, long_prefill_scale_intercept=1.0,
                         long_prefill_scale_per_1k_tokens=0.0, batch_prefill_gain_exponent=0.0)


def frontend_service_s(body_mb: float, front_end_was_busy: bool) -> float:
    """StudyENG1 section 7. The busy regime is NOT the idle regime plus a queue: the measured
    busy fit has a smaller fixed term because about 23 ms of the per-request cost overlaps with
    the previous request."""
    mb = max(float(body_mb), 0.0)
    if front_end_was_busy:
        return (FE_BUSY_FIXED_MS + FE_BUSY_PER_MB_MS * mb) / 1000.0
    return (FE_IDLE_FIXED_MS + FE_IDLE_PER_MB_MS * mb) / 1000.0


@dataclass
class SimRequest:
    """One request as the simulator needs it. Every field comes off the recorded row."""

    rid: str
    t_submit: float
    prompt_tokens: int
    cached_tokens: int = 0
    body_mb: float = 0.0
    n_images: int = 0
    out_tokens: int = 1
    tag: str = ""
    # RECORDED INPUT, not a model choice: how many of this request's cached tokens came from
    # the host tier rather than the GPU, as the engine's own
    # `prompt_tokens_by_source|external_kv_transfer` counter reports them. Zero everywhere the
    # record says the hit was local, which is every Part C action except hostreload.
    external_cached_tokens: int = 0

    def external_tokens(self) -> int:
        return min(max(int(self.external_cached_tokens), 0), max(int(self.cached_tokens), 0))

    def new_tokens(self) -> int:
        return max(int(self.prompt_tokens) - max(int(self.cached_tokens), 0), 0)

    def encoder_tokens(self) -> int:
        """Encoder tokens of the request, from its image count at the committed 90 tokens per
        D2 frame, never more than the tokens it actually has to compute."""
        return min(TOKENS_PER_FRAME * max(int(self.n_images), 0), self.new_tokens())


@dataclass
class _Live:
    req: SimRequest
    t_added: float
    remaining_new: int
    images_left: int
    t_first: Optional[float] = None
    out_left: int = 0
    t_end: Optional[float] = None
    step_take: int = 0
    step_images: int = 0
    ext_left: int = 0          # host-KV tokens not yet charged; charged once, on the first step


@dataclass
class EngineSim:
    """A step-level replay of the engine under StudyENG1's measured structure.

    Front end first (serial, two regimes), then the engine in fcfs order of hand-off: short
    prefills that fit one step's token budget are BATCHED into one step (H-step), a prefill too
    big for one step holds the single partial-prefill slot and runs ALONE until it finishes
    (H-admit verdict a), decodes join whatever step is running, and the next step's admission is
    priced in the step before it."""

    step: StepModel
    chunk_tokens: int = CHUNK_TOKENS
    max_steps: int = 2_000_000
    pol4: Optional[Pol4Terms] = None     # None is the model StudyT0-fidelity froze

    def model_name(self) -> str:
        if self.pol4 is None:
            return "eng1"
        if "switched off" in self.pol4.path:
            return "pol4_nobatch"
        return "pol4"

    def run(self, requests: Sequence[SimRequest]) -> Dict[str, Any]:
        reqs = sorted(requests, key=lambda r: (r.t_submit, r.rid))
        # --- front end, StudyENG1 section 7
        fe_free = float("-inf")
        live: List[_Live] = []
        for r in reqs:
            busy = fe_free > r.t_submit + 1e-12
            start = max(r.t_submit, fe_free if busy else r.t_submit)
            svc = frontend_service_s(r.body_mb, busy)
            t_added = start + svc
            fe_free = t_added
            live.append(_Live(req=r, t_added=t_added, remaining_new=r.new_tokens(),
                              images_left=max(int(r.n_images), 0),
                              out_left=max(int(r.out_tokens), 1),
                              ext_left=r.external_tokens()))
        # --- engine, StudyENG1 sections 5, 6 and 8
        waiting = sorted(live, key=lambda x: (x.t_added, x.req.rid))
        idx = 0
        decoding: List[_Live] = []
        partial: Optional[_Live] = None          # the single partial-prefill slot
        t = waiting[0].t_added if waiting else 0.0
        steps = 0
        step_log: List[Dict[str, Any]] = []

        def _schedulable(now: float) -> List[_Live]:
            """fcfs over the requests already handed to the engine, batched up to the step's
            token budget. A request that does not fit the WHOLE budget takes the partial slot
            and runs alone (H-admit); otherwise as many as fit share the step (H-step)."""
            nonlocal idx
            batch: List[_Live] = []
            budget = self.chunk_tokens
            while idx < len(waiting) and waiting[idx].t_added <= now + 1e-12:
                cand = waiting[idx]
                if cand.remaining_new > self.chunk_tokens:
                    if batch:
                        break                     # a long prefill waits for the batch to clear
                    idx += 1
                    return [cand]                 # alone in the partial slot
                if cand.remaining_new > budget:
                    break
                batch.append(cand)
                budget -= cand.remaining_new
                idx += 1
            return batch

        while steps < self.max_steps:
            batch: List[_Live] = []
            if partial is not None:
                batch = [partial]
            else:
                batch = _schedulable(t)
            if not batch and not decoding:
                if idx >= len(waiting):
                    break
                t = waiting[idx].t_added
                continue
            tok = 0
            imgs = 0
            ctx = 0
            for b in batch:
                take = min(b.remaining_new, self.chunk_tokens if len(batch) == 1 else
                           b.remaining_new)
                total_new = max(b.req.new_tokens(), 1)
                bi = (b.images_left if take >= b.remaining_new
                      else int(round(b.req.n_images * take / total_new)))
                bi = min(bi, b.images_left)
                b.step_take = take
                b.step_images = bi
                tok += take
                imgs += bi
                ctx = max(ctx, max(int(b.req.cached_tokens), 0))
            # the admission terms price the batch that will START prefilling in the NEXT step
            will_clear = all(b.step_take >= b.remaining_new for b in batch) if batch else True
            nxt: List[_Live] = []
            if will_clear:
                peek = idx
                budget = self.chunk_tokens
                while peek < len(waiting) and waiting[peek].t_added <= t + 1e-12:
                    c = waiting[peek]
                    if c.remaining_new > budget and nxt:
                        break
                    nxt.append(c)
                    budget -= min(c.remaining_new, budget)
                    peek += 1
                    if c.remaining_new > self.chunk_tokens:
                        break
            nxt_images = sum(c.req.n_images for c in nxt)
            nxt_enc = sum(c.req.encoder_tokens() for c in nxt)
            ms = self.step.step_ms(
                new_tokens=tok, images_in_step=imgs, decode_reqs=len(decoding),
                prefill_reqs=len(batch), cached_ctx_tokens=ctx,
                next_images=nxt_images, next_encoder_tokens=nxt_enc)
            pol4_charge: Dict[str, Any] = {}
            if self.pol4 is not None:
                # The PREFILL cost of this step: the step as scheduled minus the same step with
                # no prefill work in it. Terms (b) and (c) scale this and nothing else, so a
                # decode-only step and the step model's admission terms are untouched.
                base_ms = self.step.step_ms(
                    new_tokens=0, images_in_step=0, decode_reqs=len(decoding), prefill_reqs=0,
                    cached_ctx_tokens=0, next_images=nxt_images, next_encoder_tokens=nxt_enc)
                prefill_ms = max(ms - base_ms, 0.0)
                scale = 1.0
                if len(batch) == 1 and batch[0].req.new_tokens() > self.chunk_tokens:
                    scale = self.pol4.long_prefill_scale(batch[0].req.new_tokens(),
                                                         self.chunk_tokens)
                    pol4_charge["long_prefill_scale"] = scale
                elif len(batch) > 1:
                    scale = self.pol4.batch_prefill_gain(len(batch))
                    pol4_charge["batch_prefill_gain"] = scale
                ms = base_ms + prefill_ms * scale
                reload_ms = 0.0
                for b in batch:
                    if b.ext_left > 0:
                        reload_ms += self.pol4.host_reload_ms(b.ext_left)
                        b.ext_left = 0
                if reload_ms > 0.0:
                    ms += reload_ms
                    pol4_charge["host_reload_ms"] = reload_ms
            dur = max(ms, 0.0) / 1000.0
            t0 = t
            t += dur
            steps += 1
            step_log.append(dict(t_start=t0, t_end=t, duration_s=dur, new_tokens=tok,
                                 images=imgs, decode_reqs=len(decoding),
                                 prefill_reqs=len(batch),
                                 prefilling=[b.req.rid for b in batch],
                                 admitting_next=[c.req.rid for c in nxt],
                                 pol4=pol4_charge))
            done_decode = []
            for d in decoding:
                d.out_left -= 1
                if d.out_left <= 0:
                    d.t_end = t
                    done_decode.append(d)
            for d in done_decode:
                decoding.remove(d)
            partial = None
            for b in batch:
                b.remaining_new -= b.step_take
                b.images_left = max(b.images_left - b.step_images, 0)
                if b.remaining_new <= 0:
                    b.t_first = t
                    b.out_left = max(b.out_left - 1, 0)
                    if b.out_left > 0:
                        decoding.append(b)
                    else:
                        b.t_end = t
                else:
                    partial = b
        out: Dict[str, Any] = {}
        for x in live:
            ttft = (x.t_first - x.req.t_submit) if x.t_first is not None else None
            out[x.req.rid] = dict(t_added=x.t_added, t_first=x.t_first, ttft_s=ttft,
                                  t_end=x.t_end, tag=x.req.tag,
                                  new_tokens=x.req.new_tokens(),
                                  cached_tokens=int(x.req.cached_tokens))
        return dict(per_request=out, n_steps=steps, steps=step_log,
                    engine_model=self.model_name(),
                    unfinished=[x.req.rid for x in live if x.t_first is None])


@dataclass
class Eng1Engine:
    """StudyENG1's measurement behind the policy's `EngineModel` protocol.

    This is the object that replaces `PlaceholderEngine` once T0 says it may be relied on. Every
    prediction carries `in_sample`, which is False exactly where StudyENG1 did not measure:
    outside the measured prefill sizes, and for a summary generation, for which no committed cost
    exists at all."""

    step: StepModel
    gpu_kv_tokens: int = 0
    host_kv_tokens: int = 0
    profiles: Any = None
    chunk_tokens: int = CHUNK_TOKENS
    pol4: Optional[Pol4Terms] = None     # None is the model StudyT0-fidelity froze

    # The one change from the frozen file: these two provenance strings are constant for a given
    # engine, so they are built once instead of on each of ~774,000 `predict` calls.
    _basis_cache: Dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    def _basis_step(self) -> str:
        key = str(self.step.path)
        got = self._basis_cache.get(key)
        if got is None:
            got = ("StudyENG1 step model (%s), serial prefill per section 6, front end per "
                   "section 7" % Path(key).name)
            self._basis_cache[key] = got
        return got

    def _basis_pol4(self) -> str:
        key = "pol4:" + str(self.pol4.path)
        got = self._basis_cache.get(key)
        if got is None:
            got = "StudyPOL4-engine terms from %s" % Path(self.pol4.path).name
            self._basis_cache[key] = got
        return got

    def model_name(self) -> str:
        if self.pol4 is None:
            return "eng1"
        if "switched off" in self.pol4.path:
            return "pol4_nobatch"
        return "pol4"

    @classmethod
    def load(cls, gpu_kv_tokens: int = 0, host_kv_tokens: int = 0, profiles: Any = None,
             path: Any = None, engine_model: str = "eng1",
             pol4_path: Any = None) -> "Eng1Engine":
        if engine_model not in ENGINE_MODELS:
            raise ValueError("engine_model must be one of %s" % (ENGINE_MODELS,))
        return cls(step=StepModel.load(path), gpu_kv_tokens=gpu_kv_tokens,
                   host_kv_tokens=host_kv_tokens, profiles=profiles,
                   pol4=Pol4Terms.load_for_model(engine_model, pol4_path))

    def _solo_prefill_s(self, new_tokens: int, n_images: int, cached_ctx: int,
                        decode_reqs: int, external_tokens: int = 0) -> float:
        left = max(int(new_tokens), 0)
        imgs_left = max(int(n_images), 0)
        total = max(left, 1)
        s = 0.0
        scale = (1.0 if self.pol4 is None
                 else self.pol4.long_prefill_scale(left, self.chunk_tokens))
        while left > 0:
            tok = min(left, self.chunk_tokens)
            imgs = (imgs_left if tok >= left else int(round(n_images * tok / total)))
            imgs = min(imgs, imgs_left)
            ms = self.step.step_ms(tok, imgs, decode_reqs, 1, cached_ctx)
            if self.pol4 is not None:
                base = self.step.step_ms(0, 0, decode_reqs, 0, 0)
                ms = base + max(ms - base, 0.0) * scale
            s += ms / 1000.0
            left -= tok
            imgs_left -= imgs
        if self.pol4 is not None and external_tokens > 0:
            s += self.pol4.host_reload_ms(int(external_tokens)) / 1000.0
        if s == 0.0:
            s = self.step.step_ms(0, 0, decode_reqs, 0, 0) / 1000.0
        return s

    def predict(self, req: Request, concurrent: int, load_pct: int = 25) -> Prediction:
        if concurrent < 0:
            raise ValueError("concurrent must be >= 0")
        in_sample = True
        basis = [self._basis_step()]
        frames = max(int(req.frames), 0)
        if req.kind == "episode_call":
            new_tokens = max(int(req.tokens), 0) or TOKENS_PER_FRAME * max(frames, 1)
            cached = 0
        elif req.kind in ("rc_piece", "state_action", "summary"):
            new_tokens = max(int(req.tokens), 0)
            cached = 0 if req.readiness == "COLD" else max(int(req.meta.get("cached_tokens", 0)),
                                                           0)
            if req.kind == "summary":
                in_sample = False
                basis.append("NOT IN SAMPLE: no committed summary generation cost exists "
                             "(StudyF2 inconclusive); StudyENG1 measured no generation")
        else:
            raise ValueError("unknown request kind %r" % req.kind)
        if new_tokens > 8193:
            in_sample = False
            basis.append("NOT IN SAMPLE: StudyENG1's largest measured single prefill piece was "
                         "8,231 tokens; %d new tokens is an extrapolation" % new_tokens)
        external = (max(int(req.meta.get("external_cached_tokens", 0)), 0)
                    if self.pol4 is not None else 0)
        external = min(external, cached)
        if external > 0:
            basis.append("StudyPOL4-engine term (a): %d cached tokens are charged a host-KV "
                         "reload" % external)
        if self.pol4 is not None:
            basis.append(self._basis_pol4())
        gpu = self._solo_prefill_s(new_tokens, frames, cached, decode_reqs=0,
                                   external_tokens=external)
        # Section 6: a request arriving behind concurrent work waits for that work, it does not
        # share a step. The caller's `concurrent` is other requests in flight, so their remaining
        # work is ahead of this one; without their sizes the only honest statement is that the
        # wait is at least one of this engine's steps per request ahead.
        queue = concurrent * self.step.step_ms(0, 0, concurrent, 0, 0) / 1000.0
        if concurrent > 0:
            basis.append("serial blocking: %d request(s) ahead contribute at least their decode "
                         "steps; the exact wait needs their remaining work, which only the trace "
                         "replay has" % concurrent)
        return Prediction(first_token_s=gpu + queue, service_s=gpu + queue, gpu_s=gpu,
                          in_sample=in_sample, basis="; ".join(basis))

    def capacity_tokens(self) -> Tuple[int, int]:
        return self.gpu_kv_tokens, self.host_kv_tokens

    def describe(self) -> Dict[str, Any]:
        return dict(
            name="Eng1Engine",
            engine_model=self.model_name(),
            replaces="PlaceholderEngine, once T0 says the measurement may be relied on",
            step_model=self.step.describe(),
            pol4_terms=(self.pol4.describe() if self.pol4 is not None else
                        "OFF: this is the model StudyT0-fidelity froze and tested"),
            chunk_tokens=self.chunk_tokens,
            structure=dict(
                prefill="SERIAL at the request level (StudyENG1 section 6, H-admit verdict a)",
                decode="batched into whatever step is running",
                front_end="serial single server, two measured regimes (section 7)",
                admission="the next step's images and encoder tokens (section 8)",
                tokens_per_frame=TOKENS_PER_FRAME,
            ),
            sources=["results/cost/study_eng1/eng1_step_model.json (fitted on Part A and Part B "
                     "E0; Part C and the HOLDOUT never used)",
                     "reports/study_eng1_steptime.md sections 5, 6, 7, 8, 1.2 and 11"],
            not_modelled=["sub-linear batching of concurrent prefills (prefill is serial)",
                          "per-request-type front-end cost beyond the committed two regimes",
                          "the step model's admission residual, median 27.9 ms, left as it is"],
            fitted_here="NOTHING: no coefficient in this module was fitted, and no Part C or "
                        "HOLDOUT datum entered any number it uses")


def make_sim(engine_model: str = "eng1", step_path: Any = None,
             pol4_path: Any = None, **kw: Any) -> EngineSim:
    """The one place a caller chooses between the two models. `eng1` is StudyT0-fidelity's
    frozen model; `pol4` adds StudyPOL4-engine's three terms."""
    if engine_model not in ENGINE_MODELS:
        raise ValueError("engine_model must be one of %s, got %r" % (ENGINE_MODELS,
                                                                     engine_model))
    return EngineSim(step=StepModel.load(step_path),
                     pol4=Pol4Terms.load_for_model(engine_model, pol4_path), **kw)
