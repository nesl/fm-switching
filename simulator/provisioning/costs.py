"""
Cost model — derived from results/cost/cost_matrix.csv (a6000 rows, Qwen2.5-7B-Instruct).

All times in seconds. All sizes in GB.

Assumptions documented:
- warm_append_s uses linear fit: 0.330 * (L/65536), floored at 0.066s (measured floor at 1K-8K).
- S_ready uses analytical KV formula: 57344 bytes/token (measured from model config).
- transfer_s uses stored-text sizes (not KV); KV transfer over WAN is infeasible.
- prefill_slowdown for non-a6000 nodes applied as multiplier to cold_prefill and restore.
"""

import bisect

# Measured cold prefill (full-restore) on A6000, seconds
_COLD_PREFILL_L  = [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
_COLD_PREFILL_S  = [0.165, 0.325, 0.667, 1.369, 3.090, 5.245, 7.805, 14.820, 21.720]

KV_BYTES_PER_TOK = 57344       # bytes, analytical FP16 for Qwen2.5-7B
WIN_TOKENS       = 2048        # window-10 always ~2k tokens
SUM80_TOKENS     = 80
SUM200_TOKENS    = 200

# Stored text sizes (bytes)
_FULL_TEXT_BYTES_PER_TOK = 4
_WIN_TEXT_BYTES           = 1536   # ~1.5 KB
_SUM80_TEXT_BYTES         = 317
_SUM200_TEXT_BYTES        = 684


class CostModel:
    """All costs are for a6000 baseline (prefill_slowdown=1.0)."""

    def cold_prefill_s(self, L: int, slowdown: float = 1.0) -> float:
        """Cold re-prefill time for L tokens. Linear interp between measured points."""
        L = max(_COLD_PREFILL_L[0], min(_COLD_PREFILL_L[-1], L))
        idx = bisect.bisect_right(_COLD_PREFILL_L, L)
        if idx == 0:
            return _COLD_PREFILL_S[0] * slowdown
        if idx >= len(_COLD_PREFILL_L):
            return _COLD_PREFILL_S[-1] * slowdown
        L0, L1 = _COLD_PREFILL_L[idx - 1], _COLD_PREFILL_L[idx]
        t0, t1 = _COLD_PREFILL_S[idx - 1], _COLD_PREFILL_S[idx]
        t = t0 + (t1 - t0) * (L - L0) / (L1 - L0)
        return t * slowdown

    def warm_append_s(self, L: int, slowdown: float = 1.0) -> float:
        """Warm incremental append (~200-token turn) cost. Linear in L, floored."""
        t = max(0.066, 0.330 * L / 65536)
        return t * slowdown

    def restore_s(self, fidelity: str, L: int, slowdown: float = 1.0) -> float:
        """Time to materialize stored→ready for fidelity f at context length L."""
        if fidelity == "full":
            return self.cold_prefill_s(L, slowdown)
        if fidelity == "win":
            # window is always ~2k tokens regardless of full L
            return self.cold_prefill_s(WIN_TOKENS, slowdown)
        if fidelity == "sum80":
            return 0.027 * slowdown
        if fidelity == "sum200":
            return 0.031 * slowdown
        if fidelity == "blind":
            return 0.0
        raise ValueError(f"Unknown fidelity: {fidelity}")

    def refresh_s(self, fidelity: str, L: int, slowdown: float = 1.0) -> float:
        """Cost to bring a ready object current after staleness (one turn catch-up).
        full/win: warm append; sum80/sum200: must re-read full context (corrected phase-1).
        """
        if fidelity == "full":
            return self.warm_append_s(L, slowdown)
        if fidelity == "win":
            return self.warm_append_s(WIN_TOKENS, slowdown)
        if fidelity in ("sum80", "sum200"):
            # Summaries must regenerate from full context — costs cold_prefill
            return self.cold_prefill_s(L, slowdown)
        if fidelity == "blind":
            return 0.0
        raise ValueError(f"Unknown fidelity: {fidelity}")

    def s_ready_gb(self, fidelity: str, L: int) -> float:
        """GPU memory (GB) consumed when object is KV-resident."""
        if fidelity == "full":
            return KV_BYTES_PER_TOK * L / 1e9
        if fidelity == "win":
            return KV_BYTES_PER_TOK * WIN_TOKENS / 1e9
        if fidelity == "sum80":
            return KV_BYTES_PER_TOK * SUM80_TOKENS / 1e9
        if fidelity == "sum200":
            return KV_BYTES_PER_TOK * SUM200_TOKENS / 1e9
        if fidelity == "blind":
            return 0.0
        raise ValueError(f"Unknown fidelity: {fidelity}")

    def transfer_s(self, fidelity: str, L: int,
                   bw_mbps: float = 10.0, rtt_ms: float = 50.0) -> float:
        """Time (s) to transfer stored-text representation over the network."""
        rtt_s = rtt_ms / 1000.0
        bw_bps = bw_mbps * 1e6
        if fidelity == "full":
            text_bytes = _FULL_TEXT_BYTES_PER_TOK * L
        elif fidelity == "win":
            text_bytes = _WIN_TEXT_BYTES
        elif fidelity == "sum80":
            text_bytes = _SUM80_TEXT_BYTES
        elif fidelity == "sum200":
            text_bytes = _SUM200_TEXT_BYTES
        elif fidelity == "blind":
            return rtt_s
        else:
            raise ValueError(f"Unknown fidelity: {fidelity}")
        return rtt_s + (text_bytes * 8) / bw_bps


COST_MODEL = CostModel()
