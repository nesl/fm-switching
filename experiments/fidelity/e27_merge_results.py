"""
Post-hoc merge: combine LoCoMo-only and EgoSchema-only results into the
final e27_maintenance_qwen7b.json with corrected lifecycle cost.

Run AFTER both --locomo-only and --ego-only runs complete.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT    = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "results" / "fidelity" / "e27_maintenance"

MODES   = ["full_regen", "recursive", "periodic_2", "periodic_5", "periodic_10"]
BUDGETS = ["sum80", "sum200"]

_A6K_L = [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
_A6K_S = [0.165, 0.325, 0.667, 1.369, 3.090, 5.245, 7.805, 14.820, 21.720]


def cold_prefill_s(n_tokens: int) -> float:
    import bisect
    if n_tokens <= _A6K_L[0]:
        return _A6K_S[0]
    if n_tokens >= _A6K_L[-1]:
        slope = (_A6K_S[-1] - _A6K_S[-2]) / (_A6K_L[-1] - _A6K_L[-2])
        return _A6K_S[-1] + slope * (n_tokens - _A6K_L[-1])
    idx = bisect.bisect_right(_A6K_L, n_tokens)
    L0, L1 = _A6K_L[idx-1], _A6K_L[idx]
    t0, t1 = _A6K_S[idx-1], _A6K_S[idx]
    return t0 + (t1 - t0) * (n_tokens - L0) / (L1 - L0)


def load_per_step(prefix: str) -> dict:
    step = {}
    for f in sorted((OUT_DIR / "per_step").glob(f"{prefix}_*.json")):
        key = f.stem[len(prefix)+1:]
        step[key] = json.loads(f.read_text())
    return step


def compute_lifecycle_cost(locomo_step: dict, ego_step: dict) -> dict:
    def _agg(step_data_list):
        agg = defaultdict(lambda: {"input_tokens": [], "latency_s": []})
        for item_data in step_data_list:
            for mode in MODES:
                for budget in BUDGETS:
                    key = f"{mode}_{budget}"
                    for cp in item_data.get("summaries", {}).get(mode, {}).get(budget, []):
                        if cp.get("input_tokens", 0) > 0:
                            agg[key]["input_tokens"].append(cp["input_tokens"])
                            agg[key]["latency_s"].append(cp["latency_s"])
        return agg

    def _summarize(agg):
        out = {}
        for key in agg:
            toks = agg[key]["input_tokens"]
            lats = agg[key]["latency_s"]
            mean_tok = sum(toks) / len(toks) if toks else 0
            mean_lat = sum(lats) / len(lats) if lats else 0
            est_lat = cold_prefill_s(int(mean_tok)) if mean_tok > 0 else 0
            out[key] = {
                "n_refresh_events": len(toks),
                "mean_input_tokens": round(mean_tok, 1),
                "mean_measured_latency_s": round(mean_lat, 4),
                "est_refresh_latency_s": round(est_lat, 4),
            }
        for budget in BUDGETS:
            fr_tok = out.get(f"full_regen_{budget}", {}).get("mean_input_tokens")
            if fr_tok and fr_tok > 0:
                for mode in MODES:
                    k = f"{mode}_{budget}"
                    if k in out:
                        out[k]["token_ratio_vs_full_regen"] = round(
                            out[k]["mean_input_tokens"] / fr_tok, 4)
        return out

    return {
        "locomo":     _summarize(_agg(locomo_step.values())),
        "egoschema":  _summarize(_agg(ego_step.values())),
    }


def classify_outcome(locomo_accuracy: dict, lifecycle: dict) -> str:
    cp_100 = 3
    gaps = []
    for budget in BUDGETS:
        fr = locomo_accuracy.get(cp_100, locomo_accuracy.get(str(cp_100), {})).get(
            f"full_regen_{budget}", {}).get("accuracy")
        rec = locomo_accuracy.get(cp_100, locomo_accuracy.get(str(cp_100), {})).get(
            f"recursive_{budget}", {}).get("accuracy")
        if fr is not None and rec is not None:
            gaps.append(fr - rec)
    if not gaps:
        return "unknown"
    max_gap = max(gaps)
    rec_ratio = lifecycle["locomo"].get("recursive_sum200", {}).get(
        "token_ratio_vs_full_regen", 1.0)
    is_cheap = rec_ratio is not None and rec_ratio < 0.20
    quality_holds = max_gap <= 0.03
    if is_cheap and quality_holds:
        return "A"
    if is_cheap and not quality_holds:
        return "B"
    best_per_ratio = min(
        lifecycle["locomo"].get(f"periodic_{K}_sum200", {}).get(
            "token_ratio_vs_full_regen", 1.0) for K in [2, 5, 10])
    per_gap = max(
        (locomo_accuracy.get(cp_100, locomo_accuracy.get(str(cp_100), {})).get(
            f"full_regen_{budget}", {}).get("accuracy", 0) -
         locomo_accuracy.get(cp_100, locomo_accuracy.get(str(cp_100), {})).get(
            f"periodic_{K}_{budget}", {}).get("accuracy", 0))
        for K in [2, 5, 10] for budget in BUDGETS)
    if best_per_ratio < rec_ratio and per_gap <= 0.03:
        return "C"
    return "B"


def main():
    sidecar_path = OUT_DIR / "e27_locomo_sidecar.json"
    main_path    = OUT_DIR / "e27_maintenance_qwen7b.json"

    if not sidecar_path.exists():
        print("ERROR: sidecar not found — LoCoMo sidecar must be saved first", file=sys.stderr)
        sys.exit(1)

    sidecar = json.loads(sidecar_path.read_text())
    locomo_accuracy = sidecar["locomo_accuracy"]

    current = json.loads(main_path.read_text()) if main_path.exists() else {}
    ego_accuracy = current.get("egoschema_accuracy", {})

    if not ego_accuracy:
        print("WARNING: egoschema_accuracy is empty in main JSON — EgoSchema run may not be done")

    # Load per_step files
    locomo_step = load_per_step("locomo")
    ego_step    = load_per_step("ego")

    print(f"Loaded {len(locomo_step)} LoCoMo convs, {len(ego_step)} EgoSchema clips")

    lifecycle = compute_lifecycle_cost(locomo_step, ego_step)
    outcome   = classify_outcome(locomo_accuracy, lifecycle)

    print("\n=== Lifecycle cost (LoCoMo) ===")
    for k, v in sorted(lifecycle["locomo"].items()):
        print(f"  {k}: tok={v.get('mean_input_tokens'):.0f} "
              f"lat={v.get('mean_measured_latency_s'):.2f}s "
              f"ratio={v.get('token_ratio_vs_full_regen')}")

    print("\n=== LoCoMo accuracy @100% ===")
    cp3 = locomo_accuracy.get(3, locomo_accuracy.get("3", {}))
    for k in sorted(cp3.keys()):
        print(f"  {k}: {cp3[k].get('accuracy')}")

    print(f"\nOutcome: {outcome}")

    # Sanity check from sidecar
    sanity = sidecar.get("sanity_check", {})
    prov   = sidecar.get("_provenance", current.get("_provenance", {}))

    merged = {
        "experiment": "E27",
        "smoke": False,
        "locomo_accuracy": locomo_accuracy,
        "egoschema_accuracy": ego_accuracy,
        "lifecycle_cost": lifecycle,
        "sanity_check": sanity,
        "outcome": outcome,
        "_provenance": prov,
    }

    tmp = main_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, indent=2))
    tmp.replace(main_path)
    print(f"\nSaved merged result to {main_path}")


if __name__ == "__main__":
    main()
