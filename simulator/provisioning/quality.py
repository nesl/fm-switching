"""
Q(fidelity, regime) table — measured accuracy from phase-0a multimodel audit.

Sources (Qwen2.5-7B-Instruct, n as noted):
  compressible   → EgoSchema (n=500, E05)
  mixed_sensitive→ Infini-THOR (n=60 NsiEH, E11)
  dense          → LoCoMo cat=1 scaled (n=282, E13)

win under mixed_sensitive is ESTIMATED (0.460) — not directly measured in E11.
All other values are measured.
"""

# Q[regime][fidelity] = fraction of requests meeting quality at that fidelity
Q_TABLE = {
    "compressible": {
        "full":   0.502,
        "win":    0.506,
        "sum200": 0.498,
        "sum80":  0.470,
        "blind":  0.268,
    },
    "mixed_sensitive": {
        "full":   0.580,
        "win":    0.460,  # ESTIMATED: not directly measured in E11
        "sum200": 0.550,
        "sum80":  0.550,
        "blind":  0.360,
    },
    "dense": {
        "full":   0.340,
        "win":    0.220,
        "sum200": 0.099,
        "sum80":  0.099,
        "blind":  0.000,
    },
}

REGIMES = list(Q_TABLE.keys())
FIDELITIES = ["full", "win", "sum200", "sum80", "blind"]

# Ordering by quality cost (cheapest to most expensive in bytes; used by fidelity_only)
# For each regime, the minimal-sufficient fidelity at q_min=0.30:
#   dense:          full  (only 0.340 >= 0.30)
#   mixed_sensitive:sum80 (0.550 >= 0.30; cheaper than win/full)
#   compressible:   sum80 (0.470 >= 0.30; cheapest passing)
CHEAPEST_SUFFICIENT = {
    "compressible":   "sum80",
    "mixed_sensitive":"sum80",
    "dense":          "full",
}


def quality(fidelity: str, regime: str) -> float:
    """Return Q(fidelity, regime). Raises KeyError for unknown keys."""
    return Q_TABLE[regime][fidelity]


def meets_slo(fidelity: str, regime: str, q_min: float) -> bool:
    return quality(fidelity, regime) >= q_min
