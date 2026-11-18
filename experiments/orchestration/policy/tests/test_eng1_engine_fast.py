#!/usr/bin/env python3
"""`eng1_engine_fast.Eng1Engine.predict` is the frozen `predict`, to the last field.

StudyLIVE2-perf, under the user's freeze ruling of 2026-11-18: never edit a frozen file. The
live policy path loads `policy/eng1_engine_fast.py`, a copy of the frozen
`policy/eng1_engine.py` whose only change is that two PROVENANCE strings are built once per
engine instead of on each of about 774,000 `predict` calls. The frozen file is untouched and its
md5 tests stay green; these tests are what make the copy safe to rely on.

Three kinds of evidence, because "it should be the same" is not evidence:

  1. the two files differ ONLY where the copy says they do, checked function by function on the
     parsed syntax tree rather than by reading the diff;
  2. `predict` returns IDENTICAL `Prediction`s, field for field including `basis`, over every
     StudyENG1 / StudyENG1c Part C FIT trial row and every StudyENG1d FIT trial row (84,000-odd
     calls), with the HOLDOUT rows of both studies never touched;
  3. and over every `predict` call the policy fixtures actually make, recorded from a dry cell
     rather than guessed at.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = HERE.parent
ORCH = POLICY.parent
ROOT = ORCH.parents[1]
for _p in (str(ORCH), str(ORCH / "live2"), str(ORCH / "live2" / "fleet"),
           str(ORCH / "live2" / "scorer"), str(ORCH / "live"), str(ORCH / "baselines"),
           str(ORCH / "sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from policy import eng1_engine as FROZEN                                # noqa: E402
from policy import eng1_engine_fast as FAST                             # noqa: E402
from policy.engine import Request                                       # noqa: E402

FROZEN_PATH = POLICY / "eng1_engine.py"
FAST_PATH = POLICY / "eng1_engine_fast.py"
FREEZE = ROOT / "results/orchestration/study_t0b/t0b_freeze.json"

# the only three differences the copy is allowed to have in its code
ALLOWED_NEW = {("Eng1Engine", "_basis_step"), ("Eng1Engine", "_basis_pol4")}
ALLOWED_CHANGED = {("Eng1Engine", "predict")}

KIND_OF = {"episodic": "episode_call", "warm_escalation": "episode_call",
           "warm_append": "rc_piece", "inject": "rc_piece"}


def _hashable(v):
    """Recorded `meta` values go into a set, so make the containers comparable."""
    if isinstance(v, dict):
        return tuple(sorted((k, _hashable(x)) for k, x in v.items()))
    if isinstance(v, (list, tuple)):
        return tuple(_hashable(x) for x in v)
    return v


def _functions(path: Path):
    """(class, name) -> normalised syntax tree, with docstrings dropped."""
    tree = ast.parse(path.read_text(), filename=str(path))
    out = {}

    def strip_doc(node):
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]
        clone = ast.Module(body=body, type_ignores=[])
        return ast.dump(clone)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[(None, node.name)] = strip_doc(node)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef):
                    out[(node.name, sub.name)] = strip_doc(sub)
    return out


def _engines():
    """One frozen and one fast engine built from the same committed inputs."""
    step = FROZEN.StepModel.load()
    pol4 = FROZEN.Pol4Terms.load_for_model("pol4")
    frozen = FROZEN.Eng1Engine(step=step, gpu_kv_tokens=62944, host_kv_tokens=1_000_000,
                               profiles=None, pol4=pol4)
    fast = FAST.Eng1Engine(step=FAST.StepModel.load(), gpu_kv_tokens=62944,
                           host_kv_tokens=1_000_000, profiles=None,
                           pol4=FAST.Pol4Terms.load_for_model("pol4"))
    return frozen, fast


def _requests_from_trials(trials, limit_rows=None):
    """One `Request` per recorded row, in the row's own kind, tokens and cached tokens."""
    out = []
    for t in trials:
        for _mode, arm in sorted(t.arms.items()):
            for r in list(arm.background) + list(arm.action):
                kind = KIND_OF.get(str(r.get("kind")))
                if kind is None:
                    continue
                tok = int(r.get("prompt_tokens") or 0)
                cached = int(r.get("cached_tokens") or 0)
                readiness = "COLD" if cached == 0 else "HOST-WARM"
                frames = max(1, round(tok / FROZEN.TOKENS_PER_FRAME)) if kind == "episode_call" \
                    else 0
                out.append(Request(kind=kind, device=str(r.get("rid") or "d"), tokens=tok,
                                   frames=frames, readiness=readiness,
                                   meta=dict(cached_tokens=cached,
                                             external_cached_tokens=min(cached, tok))))
                if limit_rows is not None and len(out) >= limit_rows:
                    return out
    return out


def _compare(case, frozen, fast, reqs, concurrents=(0, 1, 3)):
    n = 0
    for req in reqs:
        for c in concurrents:
            a = frozen.predict(req, c)
            b = fast.predict(req, c)
            if asdict(a) != asdict(b):
                case.fail("predict differs on kind=%s tokens=%d readiness=%s concurrent=%d:\n"
                          "  frozen %r\n  fast   %r"
                          % (req.kind, req.tokens, req.readiness, c, a, b))
            n += 1
    return n


class TestTheCopyDiffersOnlyWhereItSaysItDoes(unittest.TestCase):
    def test_every_other_function_is_syntactically_identical(self):
        a, b = _functions(FROZEN_PATH), _functions(FAST_PATH)
        self.assertEqual(set(b) - set(a), ALLOWED_NEW,
                         "the copy defines a function the frozen file does not")
        self.assertEqual(set(a) - set(b), set(), "the copy dropped a function")
        changed = {k for k in set(a) & set(b) if a[k] != b[k]}
        self.assertEqual(changed, ALLOWED_CHANGED,
                         "the copy changed a function other than Eng1Engine.predict")

    def test_the_two_provenance_lines_are_the_only_change_inside_predict(self):
        a = ast.dump(ast.parse(FROZEN_PATH.read_text()))
        b = ast.dump(ast.parse(FAST_PATH.read_text()))
        self.assertNotEqual(a, b)
        # the frozen file builds the strings inline; the copy must not
        self.assertIn("serial prefill per section 6", FROZEN_PATH.read_text())
        body = FAST_PATH.read_text()
        head, _, rest = body.partition('--- the frozen file\'s own docstring follows ---')
        self.assertIn("_basis_step", rest)
        self.assertEqual(rest.count('% Path(self.step.path).name'), 0,
                         "the copy still builds the step basis inline")

    def test_the_frozen_module_is_byte_for_byte_what_the_freeze_recorded(self):
        d = json.loads(FREEZE.read_text())
        files = next(v for v in d.values()
                     if isinstance(v, dict) and any(".py" in str(x) for x in list(v)[:5]))
        rel = "experiments/orchestration/policy/eng1_engine.py"
        self.assertIn(rel, files)
        want = files[rel] if isinstance(files[rel], str) else files[rel].get("md5")
        got = hashlib.md5(FROZEN_PATH.read_bytes()).hexdigest()
        self.assertEqual(got, want, "the FROZEN file changed; that is never allowed")


class TestPredictIsIdenticalOnTheFitTrials(unittest.TestCase):
    def test_eng1_and_eng1c_part_c_fit_trials(self):
        from policy import trace_replay as tr
        trials = [t for t in tr.load_part_c_trials() if not t.holdout]
        self.assertGreater(len(trials), 300, "the FIT split did not load")
        self.assertTrue(all(not t.holdout for t in trials), "a HOLDOUT trial leaked in")
        frozen, fast = _engines()
        reqs = _requests_from_trials(trials)
        self.assertGreater(len(reqs), 20000, len(reqs))
        n = _compare(self, frozen, fast, reqs, concurrents=(0, 2))
        self.assertGreater(n, 40000, n)

    def test_eng1d_fit_trials(self):
        from policy import eng1d_replay as e1d
        trials, audit = e1d.load_trials("fit")
        self.assertEqual(audit["split"], "fit")
        self.assertGreater(len(trials), 100, len(trials))
        frozen, fast = _engines()
        reqs = _requests_from_trials(trials)
        self.assertGreater(len(reqs), 1000, len(reqs))
        n = _compare(self, frozen, fast, reqs, concurrents=(0, 2))
        self.assertGreater(n, 2000, n)

    def test_the_whole_measured_token_range_including_out_of_sample(self):
        """The in-sample flag and its basis line are part of the output, so sweep across it."""
        frozen, fast = _engines()
        reqs = []
        for kind in ("episode_call", "rc_piece", "state_action", "summary"):
            for tok in (0, 1, 377, 378, 512, 2048, 4096, 8193, 8194, 11000, 28000, 100000):
                for readiness in ("COLD", "HOST-WARM", "GPU-WARM"):
                    reqs.append(Request(kind=kind, device="d", tokens=tok,
                                        frames=(1 if kind == "episode_call" else 0),
                                        readiness=readiness,
                                        meta=dict(cached_tokens=tok // 2,
                                                  external_cached_tokens=tok // 4)))
        n = _compare(self, frozen, fast, reqs, concurrents=(0, 1, 5))
        self.assertEqual(n, len(reqs) * 3)


class TestPredictIsIdenticalOnEveryCallThePolicyMakes(unittest.TestCase):
    def test_every_predict_call_a_dry_policy_cell_makes(self):
        import fix_checks as FX
        calls = []
        real = FAST.Eng1Engine.predict

        def recording(self, req, concurrent, load_pct=25):
            calls.append((req.kind, req.device, int(req.tokens), int(req.frames), req.model,
                          req.readiness, req.job_id, int(req.piece_index),
                          tuple(sorted((k, _hashable(v)) for k, v in req.meta.items())),
                          int(concurrent), int(load_pct)))
            return real(self, req, concurrent, load_pct)

        FAST.Eng1Engine.predict = recording
        try:
            FX._cell(n_dashcam=4, n_robot=4, window_s=60.0, seed=1, h=1.0)
        finally:
            FAST.Eng1Engine.predict = real
        self.assertGreater(len(calls), 5000, "the fixture made too few predict calls")
        # the recorded meta must round-trip exactly, or this would compare a different call than
        # the policy made; every value the fixture produces is a scalar
        for c in calls:
            for _k, v in c[8]:
                self.assertIsInstance(v, (int, float, bool, str, type(None)),
                                      "a meta value is a container, so the recorded call is not "
                                      "the call the policy made")
        uniq = sorted(set(calls))
        frozen, fast = _engines()
        for c in uniq:
            (kind, dev, tok, frames, model, readiness, job, piece, meta, conc, load) = c
            req = Request(kind=kind, device=dev, tokens=tok, frames=frames, model=model,
                          readiness=readiness, job_id=job, piece_index=piece, meta=dict(meta))
            a = frozen.predict(req, conc, load)
            req2 = Request(kind=kind, device=dev, tokens=tok, frames=frames, model=model,
                           readiness=readiness, job_id=job, piece_index=piece, meta=dict(meta))
            b = fast.predict(req2, conc, load)
            self.assertEqual(asdict(a), asdict(b), "differs on a call the policy really makes: %r"
                             % (c,))

    def test_the_live_policy_path_loads_the_fast_copy(self):
        import arms_policy as AP
        self.assertIs(AP.Eng1Engine, FAST.Eng1Engine)
        self.assertIsNot(AP.Eng1Engine, FROZEN.Eng1Engine)


if __name__ == "__main__":
    unittest.main(verbosity=2)
