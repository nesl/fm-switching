"""
Relative-quality sufficiency for E24b.

Fidelity f is sufficient for regime w at tau iff Q(f,w) >= tau * Q("full", w).
This replaces the absolute q_min=0.30 threshold used in E24.

Verified at build time: blind is never sufficient at tau in {0.80, 0.90, 0.95}.
"""

from .quality import Q_TABLE, FIDELITIES

# Ordered cheapest→most expensive by S_ready footprint
_FIDELITY_SIZE_ORDER = ["sum80", "sum200", "win", "full"]


def sufficient(f: str, w: str, tau: float) -> bool:
    return Q_TABLE[w][f] >= tau * Q_TABLE[w]["full"]


def cheapest_sufficient_tau(w: str, tau: float) -> str:
    for f in _FIDELITY_SIZE_ORDER:
        if sufficient(f, w, tau):
            return f
    return "full"


def verify_blind_never_sufficient(taus=(0.80, 0.90, 0.95)):
    for tau in taus:
        for regime in Q_TABLE:
            if sufficient("blind", regime, tau):
                raise ValueError(
                    f"Q mapping error: blind sufficient at tau={tau} regime={regime}")


def sufficiency_table(taus=(0.80, 0.90, 0.95)):
    rows = []
    for tau in taus:
        for regime in sorted(Q_TABLE.keys()):
            row = {"tau": tau, "regime": regime}
            for f in FIDELITIES:
                row[f] = sufficient(f, regime, tau)
            row["cheapest_sufficient"] = cheapest_sufficient_tau(regime, tau)
            rows.append(row)
    return rows


def has_graded_ladder(w: str, tau: float) -> bool:
    """True if both blind and sum80 fail, and sum200 or win is sufficient."""
    return (not sufficient("blind", w, tau)
            and not sufficient("sum80", w, tau)
            and (sufficient("sum200", w, tau) or sufficient("win", w, tau)))
