"""Mandatory flash-attention-2 enforcement for backend-matched re-runs.

Qwen3-VL silently falls back to sdpa when flash-attn is not importable, so
requesting flash_attention_2 is not evidence it was used. Every model load in a
re-run must call assert_fa2() and record the returned value per trial.
"""

REQUIRED = "flash_attention_2"
ASSERTED = None


def assert_fa2(model, where=""):
    """Abort loudly unless the loaded model really is on flash-attention-2."""
    got = {"top": getattr(model.config, "_attn_implementation", None)}
    for sub in ("text_config", "vision_config"):
        cfg = getattr(model.config, sub, None)
        if cfg is not None:
            got[sub] = getattr(cfg, "_attn_implementation", None)
    bad = {k: v for k, v in got.items() if v != REQUIRED}
    if bad:
        raise SystemExit(
            f"FATAL [{where}]: expected {REQUIRED} on every tower, got {got}. "
            "Refusing to run — a silent sdpa fallback would confound the "
            "backend comparison this re-run exists to make.")
    global ASSERTED
    ASSERTED = REQUIRED
    print(f"  attn backend asserted [{where}]: {got}", flush=True)
    return REQUIRED


def record():
    """Value to write into every trial row; None until assert_fa2() has run."""
    return ASSERTED
