# E36e Part B Null: INCONCLUSIVE — Mechanism Absent from Simulation

## All 288 cells produce both_met=1.000. This is a simulation design flaw, not a null result.

---

## Diagnosis

The modeling requirement states "Robot session phases are desynchronized at initialization."
The script desynchronized **turn phase** (random `turn_idx`) but initialized **session age**
at zero (`session_idx=0`) for all robots.

Consequence:
- At initialization: robot context_L is tiny (L_mean=382 tokens, L_max=890 tokens)
- After 30 epochs: session_idx reaches 1–2 at most; L_mean=1,728 tokens
- Device TTFT at these lengths: 344–403ms, well below the 1000ms SLO
- Therefore: all 50 robots pass the TTFT SLO on device regardless of policy
- Edge admission becomes irrelevant — both_met=1.000 for every policy, every cell

The mechanism under test — that device TTFT exceeds the SLO for robots with accumulated
session history, making edge capacity binding — **never activates** in the simulation.

### Steady-state initialization would show:
- With `session_idx = rng.randint(0, n_sess-1)`: L_mean=9,520 tokens
- 20/50 robots have L > 12,000 tokens → device TTFT > 1000ms → they depend on edge
- Edge capacity constraint (N_mem=8 for full, N_mem=23 for win10) would be binding at n=50
- fp_ranked vs maintenance_aware gap would be measurable

### Device TTFT crossover (qwen3b on Jetson, E23 × A1 ratio):

| context_L (tokens) | device TTFT (ms) | 1000ms SLO |
|---|---|---|
| 100–1,000 | 344ms | pass |
| 2,000 | 403ms | pass |
| 5,000 | 613ms | pass |
| 8,192 | 853ms | pass |
| 10,000 | 997ms | pass |
| 12,000 | 1,159ms | **FAIL** |
| 16,384 | 1,524ms | **FAIL** |
| 20,000+ | 1,524ms (clamped) | **FAIL** |

Robots reach L=12,000 only at session_idx≈12 (roughly 12 sessions × 932 tok/session).
With session_idx initialized to 0, robots never reach this threshold in 30 epochs.

---

## Classification (CLAUDE.md Rule 2): INCONCLUSIVE

The mechanism is present (P1–P4 pass in Part A). Part B produces a null because
the mechanism is unexercised — device is always sufficient, so edge competition
never materializes. This is not a settled finding; it is a design failure.

**Structural analogy to prior failures:** E36c's null was traced to `refresh_ms`
returning 0 — a correctly-zero quantity that made the mechanism absent. This Part B
null is traced to `session_idx=0` — also a correctly-zero quantity (robots do start
at session 0) that makes the fleet a transient-startup fleet, not a steady-state fleet.
A quantity that is correctly and consistently zero passes every consistency check.

---

## The fix

In `_make_robots` (experiments/orchestration/e36e_fleet.py), change:

```python
robots[i] = Robot(i, ctx, n_sess, 0, ph_turn)
```

to:

```python
ph_sess = rng.randint(0, n_sess - 1)
robots[i] = Robot(i, ctx, n_sess, ph_sess, ph_turn)
```

This initializes each robot at a uniformly random point in its session lifetime,
producing a steady-state fleet rather than a just-started fleet. The turn phase
remains independently randomized (existing behavior). Both dimensions must be
desynchronized for "phase desynchronized at initialization" to hold.

### Why this is a setup fix, not a methodological change

The claim being tested is about a steady-state fleet. The formulation (FORMULATION.md §5)
models a fleet of robots with accumulated session history. The current initialization
produces a transient-startup fleet that does not correspond to the modeled scenario.
Fixing session_idx to be uniformly random is correcting the implementation to match
the stated model, not changing the model.

### Expected effect on Part B metrics

- both_met will drop from 1.000 to meaningful values (estimated 0.20–0.70 depending on
  n_robots, kv_cap, policy) because 20/50 robots require edge serving to meet the SLO
- fp_ranked vs maintenance_aware gap will become measurable at ti=5s (accel-bound regime)
- S1: best fixed representation is expected to become regime-dependent (full at ti<17s,
  win10 at ti≥17s) matching the Part A analytic prediction

---

## Pending action (requires confirmation before re-run)

1. Apply the session_idx fix to `_make_robots`
2. Re-run Part B (`python e36e_fleet.py --part B`)
3. Re-run S1–S4 analysis
4. Write `reports/e36e_fleet_capacity.md` covering Part A, Part A2, and corrected Part B

The Part A and Part A2 results stand unchanged — they are analytic and unaffected
by the simulation initialization bug.
