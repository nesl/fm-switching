#!/usr/bin/env python3
"""THE ENGINE CONTEXT LIMIT, READ ONCE AT RUN START FROM THE SERVER'S OWN ARGV (D223 (2), D56).

D223 (2), verbatim: "The hard-coded 32,768 context limit in our arms (arms_v6cf.py:86,
arms_v6fair.py:90, hybrid/hybrid_arm.py:157) is replaced by the server's configured max-model-len
read at run start (D56: capacities are inputs), byte-identical at 1x, before any 0.5x policy cell.
Rejected prompts are scored as D175 already rules (device answer stands) and reported per arm by
error kind."

WHY A MODULE AND NOT A CONSTANT. The limit had FIVE spellings in the policy path, three of them
retyped: `hybrid/hybrid_arm.py:157` held the canonical `32768`, `arms_v6cf.py:86` held a FALLBACK
copy behind a bare `except Exception`, and `arms_v6fair.py:90` retyped it again inside
`live2_describe`. `arms_v6cfr3.py:282` read it through `VCF.CONTEXT_LIMIT_TOKENS`, which was a
value bound at IMPORT, so setting the canonical at run start would not have reached it. A value
bound at import cannot be an input. Every read in this file's callers is a CALL, made at decision
time, so there is exactly one place the number can come from.

THE SOURCE IS THE SERVER ARGV, AND THE LAST OCCURRENCE WINS. At 1x the launcher's pinned flag list
carries `--max-model-len 32768` once (index 7 of the committed `server.command`). At the real 0.5x
condition it carries BOTH: the pinned `32768` at index 7 and `--max-model-len 31472` at index 39,
appended by `--server-extra-flags "--num-gpu-blocks-override 1968 --max-model-len 31472"`. vLLM is
an argparse program and argparse keeps the LAST occurrence, so 31,472 is what the engine serves
under. `study_live2_pilot.resolved_server_settings` already records the same semantics for every
flag the pinned list sets twice, under the key `argv_last_wins`; this parse agrees with it by
construction. A first-occurrence parse would read 32,768 at 0.5x and the defect would survive the
fix in silence.

WHAT IS NOT THE SOURCE. `header.json`'s `gpu_kv_tokens` is the HARNESS'S LOGICAL KV POOL, not the
model length. It reads 62,944 at 1x against a max-model-len of 32,768, and 31,472 at 0.5x. It
COINCIDES with the limit at 0.5x and does NOT at 1x, so a check that used it would pass the 0.5x
proof and be wrong in every 1x cell. The engine's reported `kv_cache_tokens` is the same kind of
quantity and is likewise not it.

FAIL LOUD (D223 (2) requirement 1). `parse_max_model_len` RAISES when the flag is absent or its
value is not a positive integer. It does not fall back to 32,768. A fallback that preserves
today's behaviour would make the 1x byte-identity proof pass while leaving the 0.5x path reading
32,768, which is exactly the defect being fixed: the old `arms_v6cf.py` fallback was that shape.

THE ONE REGISTER TO READ CAREFULLY. `MODEL_ARCH_MAX_TOKENS` below is NOT a default for a server
run. It is the Qwen3-VL-32B snapshot's own position limit, and it is used only when NO server is
configured for the run at all: an offline proof script that constructs an arm to exercise the rule,
or a dry cell that sends nothing to any engine and therefore has no engine to be refused by. Every
run that configures a server takes its limit from that server's argv or STOPS. `state()` reports
`source` so a cell's own artefact says which of the two happened; a cell whose source reads
`arch-default-no-server-configured` is not evidence about any engine's limit.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

FLAG = "--max-model-len"

# The model snapshot's own position limit, for runs with no server configured. See the module
# docstring: this is NOT a fallback for a server run, which fails loud instead.
MODEL_ARCH_MAX_TOKENS = 32768

ARCH_SOURCE = "arch-default-no-server-configured"

_limit: Optional[int] = None
_source: Optional[str] = None
_argv_occurrences: Optional[List[Dict[str, Any]]] = None


class ContextLimitUnreadable(RuntimeError):
    """The configured server's max-model-len could not be read. D223 (2): raise, never default."""


def parse_max_model_len(argv: Sequence[Any], where: str = "server argv") -> int:
    """The LAST `--max-model-len` value in `argv`, as an int. Raises if there is not one.

    Last-occurrence, not first: see the module docstring. Both the `--flag value` and the
    `--flag=value` spellings are accepted because argparse accepts both, and a parse that handled
    only the spelling our launcher happens to emit would be a parse of our launcher rather than of
    the engine's command line.
    """
    toks = [str(x) for x in (argv or ())]
    found: List[Dict[str, Any]] = []
    for i, tok in enumerate(toks):
        raw = None
        if tok == FLAG and i + 1 < len(toks):
            raw = toks[i + 1]
        elif tok.startswith(FLAG + "="):
            raw = tok.split("=", 1)[1]
        if raw is None:
            continue
        found.append({"index": i, "raw": raw})
    if not found:
        raise ContextLimitUnreadable(
            "%s carries no %s, so the engine's configured context limit cannot be read at run "
            "start. D223 (2) requires this to STOP rather than assume %d: a run whose limit is "
            "assumed is a run whose over-limit rule is untested. argv=%r"
            % (where, FLAG, MODEL_ARCH_MAX_TOKENS, toks))
    for rec in found:
        try:
            rec["value"] = int(str(rec["raw"]).strip())
        except Exception as exc:                                               # noqa: BLE001
            raise ContextLimitUnreadable(
                "%s carries %s %r, which is not an integer: STOP (D223 (2))"
                % (where, FLAG, rec["raw"])) from exc
        if rec["value"] <= 0:
            raise ContextLimitUnreadable(
                "%s carries %s %d, which is not a positive token count: STOP (D223 (2))"
                % (where, FLAG, rec["value"]))
    return int(found[-1]["value"])


def occurrences(argv: Sequence[Any]) -> List[Dict[str, Any]]:
    """Every `--max-model-len` in `argv`, in order, for the record. Never used to decide."""
    toks = [str(x) for x in (argv or ())]
    out: List[Dict[str, Any]] = []
    for i, tok in enumerate(toks):
        if tok == FLAG and i + 1 < len(toks):
            out.append({"index": i, "value": toks[i + 1]})
        elif tok.startswith(FLAG + "="):
            out.append({"index": i, "value": tok.split("=", 1)[1]})
    return out


def configure_from_server_argv(argv: Sequence[Any], where: str = "server argv") -> Dict[str, Any]:
    """Set the run's limit from a started server's own command line. Raises if unreadable."""
    n = parse_max_model_len(argv, where=where)
    return _set(n, where, occurrences(argv))


def configure_from_extra_flags(flags: Any, where: str = "--server-extra-flags") -> Optional[Dict[str, Any]]:
    """Set the limit from declared extra flags, or return None if they carry no limit.

    This is the path for a run attached to a server THIS PROCESS DID NOT START, where there is no
    argv to read: the extra flags are then the only declared statement of what the engine was
    launched with. It returns None rather than raising when the flags carry no limit, because
    extra flags that set other things are legitimate and the caller decides what to do next.
    """
    if flags is None:
        return None
    toks = flags.split() if isinstance(flags, str) else [str(x) for x in flags]
    if not occurrences(toks):
        return None
    return configure_from_server_argv(toks, where=where)


def configure_from_resolved(n: int, source: str) -> Dict[str, Any]:
    """Install a limit ALREADY read from a server argv by the runner, in another process.

    This is the split-mode hand-off and not a second source: the argv is read ONCE, in the runner,
    and the resolved number travels to the coordinator process in its `cfg`. The source string
    travels with it so the child's own record still names the argv it came from.
    """
    n = int(n)
    if n <= 0:
        raise ContextLimitUnreadable(
            "a resolved context limit of %d is not a positive token count: STOP (D223 (2))" % n)
    return _set(n, source, None)


def configure_from_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """THE COORDINATOR PROCESS'S OWN READ, in split mode. Called by `procsplit._serve`.

    The decisions are made in that process, so the limit the runner read from the server's argv
    has to arrive there; it travels in `cfg` as the already-resolved number. This lives here, and
    not inline in `procsplit.py`, so `d223_context_limit_unit_proofs.py` exercises THE FUNCTION THE
    CHILD CALLS rather than a re-implementation of it that could agree with a broken original.

    A cfg that declares a SERVER and carries no limit STOPS: that is the run with an engine to be
    refused by and the one the ruling is about. A cfg with no server (the harness self-checks,
    `tests/test_live2_harness.py`, a dry cell built by hand) sends nothing to any engine and takes
    the model's own position limit under its own source string. Either way the dead-wiring case is
    caught: if the runner ever stopped putting the key in cfg, every real-server cell would stop
    here rather than quietly plan against 32,768.
    """
    if cfg.get("context_limit_tokens") is not None:
        return configure_from_resolved(
            int(cfg["context_limit_tokens"]),
            str(cfg.get("context_limit_source") or "cfg (source not recorded)"))
    if cfg.get("server_url"):
        raise ContextLimitUnreadable(
            "cfg declares server_url=%r but carries no context_limit_tokens, so this coordinator "
            "process cannot know the engine's configured context limit: STOP (D223 (2))"
            % (cfg.get("server_url"),))
    return configure_arch_default()


def configure_arch_default() -> Dict[str, Any]:
    """For a run with NO server configured. Recorded under its own source string, never silent."""
    return _set(MODEL_ARCH_MAX_TOKENS, ARCH_SOURCE, None)


def _set(n: int, source: str, occ: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    global _limit, _source, _argv_occurrences
    _limit = int(n)
    _source = str(source)
    _argv_occurrences = occ
    return state()


def limit_tokens() -> int:
    """THE ONE READ. Called at decision time by every policy site that enforces the limit.

    Before any run start has configured it, this is the model's own position limit, so an offline
    proof script that constructs an arm behaves as it always has. A cell configures it; `state()`
    says from where.
    """
    return int(MODEL_ARCH_MAX_TOKENS if _limit is None else _limit)


def state() -> Dict[str, Any]:
    """What this run is reading, and from where, for `header.json`."""
    return {
        "context_limit_tokens": limit_tokens(),
        "source": _source or "unset-reading-arch-default",
        "configured": _limit is not None,
        "flag": FLAG,
        "argv_occurrences": _argv_occurrences,
        "rule": "the LAST --max-model-len in the server argv wins, as argparse resolves it",
        "ruling": "D223 (2); capacities are inputs, D56",
        "not_this": ("gpu_kv_tokens and the engine's kv_cache_tokens are the KV POOL, not the "
                     "model length: they coincide with the limit at 0.5x and do not at 1x"),
    }


def reset_for_test() -> None:
    """Unset the run's limit. For unit proofs only; no cell calls this."""
    global _limit, _source, _argv_occurrences
    _limit = _source = _argv_occurrences = None
