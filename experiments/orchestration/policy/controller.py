"""Spec 7.7: the device controller, self-normalized, never using absolute confidence.

This is the same mechanism StudyCTRL1-episodes and StudyCTRL1b-crossfit measured, re-expressed as
an online object: the study walked committed traces, this walks a live sample stream. The signal
definitions are identical, including the two readings of "instability" (A2 there) and the
degenerate-window rule (A3 there), so a parameter fitted by the study drops straight in.

The escalation PRICE term is spec 7.7's conditional mechanism: `beta * pi(t)` is added to the
threshold only when `flags.escalation_price` is on, and beta defaults to 0.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional
from collections import deque

FLAT_IQR = 1e-6
FLIP_LEVEL = math.log(0.5)


@dataclass
class ControllerState:
    window: Deque[float] = field(default_factory=deque)
    times: Deque[float] = field(default_factory=deque)
    below_count: int = 0
    open_episode: bool = False
    calls: int = 0
    last_signal: Optional[float] = None
    last_terms: Dict[str, Optional[float]] = field(default_factory=dict)


@dataclass
class DeviceController:
    w_c: float
    delta: float
    n_c: int
    k_c: int
    theta: float
    e_k: int = 10
    cadence_s: float = 0.75
    mode: str = "var"
    beta: float = 0.0
    state: ControllerState = field(default_factory=ControllerState)

    def _trim(self, t: float) -> None:
        while self.state.times and t - self.state.times[0] > self.w_c + 1e-9:
            self.state.times.popleft()
            self.state.window.popleft()

    def signal(self, score: float, t: float) -> Optional[float]:
        """max(z, rise, instability), all three divided by the window IQR. None when the window is
        degenerate or too short, which cannot escalate (A3)."""
        self.state.window.append(float(score))
        self.state.times.append(float(t))
        self._trim(t)
        w = list(self.state.window)
        if len(w) < 2:
            self.state.last_signal = None
            return None
        q75, q25 = _percentile(w, 75), _percentile(w, 25)
        iqr = q75 - q25
        if iqr < FLAT_IQR:
            self.state.last_signal = None
            self.state.last_terms = dict(z=None, rise=None, instability=None, iqr=iqr)
            return None
        med = _percentile(w, 50)
        z = (w[-1] - med) / iqr
        lag = max(int(round(self.delta / self.cadence_s)), 1)
        rise = ((w[-1] - w[-1 - lag]) / iqr) if len(w) > lag else -math.inf
        seg = w[-self.n_c:] if len(w) >= 2 else w
        if self.mode == "var":
            inst = (_std(seg) / iqr) if len(seg) >= 2 else -math.inf
        elif self.mode == "flips":
            if len(seg) >= 2:
                b = [x > FLIP_LEVEL for x in seg]
                inst = sum(1 for i in range(1, len(b)) if b[i] != b[i - 1]) / (len(seg) - 1) / 0.5
            else:
                inst = -math.inf
        else:
            raise ValueError("unknown instability mode %r" % self.mode)
        s = max(z, rise, inst)
        self.state.last_signal = s
        self.state.last_terms = dict(z=z, rise=rise, instability=inst, iqr=iqr)
        return s

    def threshold(self, price: float = 0.0, price_enabled: bool = False) -> float:
        return self.theta + (self.beta * price if price_enabled else 0.0)

    def step(self, score: float, t: float, price: float = 0.0,
             price_enabled: bool = False) -> Dict[str, object]:
        """One device sample. Returns what the device decided and why."""
        s = self.signal(score, t)
        th = self.threshold(price, price_enabled)
        st = self.state
        action = "none"
        if not st.open_episode:
            if s is not None and s > th:
                st.open_episode = True
                st.calls = 1
                st.below_count = 0
                action = "escalate"
        else:
            if s is not None:
                st.below_count = st.below_count + 1 if s <= th else 0
            if st.below_count >= self.k_c or st.calls >= self.e_k:
                st.open_episode = False
                action = "close"
                st.calls = 0
                st.below_count = 0
            else:
                st.calls += 1
                action = "follow_up"
        return dict(action=action, signal=s, threshold=th, terms=dict(st.last_terms),
                    open_episode=st.open_episode, calls=st.calls)

    def cloud_end_episode(self, negative_delta_j: bool, k_e: int) -> bool:
        """Spec 7.7: the CLOUD may end an episode when DeltaJ of continuing is negative for K_e
        consecutive calls."""
        st = self.state
        if not st.open_episode:
            return False
        if negative_delta_j:
            st.below_count = 0
            self._neg = getattr(self, "_neg", 0) + 1
        else:
            self._neg = 0
        if getattr(self, "_neg", 0) >= k_e:
            st.open_episode = False
            st.calls = 0
            self._neg = 0
            return True
        return False


def _percentile(xs: List[float], q: float) -> float:
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = (len(ys) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(ys) - 1)
    frac = pos - lo
    return ys[lo] * (1 - frac) + ys[hi] * frac


def _std(xs: List[float]) -> float:
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
