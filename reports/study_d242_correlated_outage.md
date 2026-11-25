# D242 correlated multi-robot outage screen (rung-3 1x)

**MODEL-BASED SCREEN, NOT A MEASUREMENT.** First-token times are predicted by the committed D162 model; the engine is not run. 1x only. k robots lose the link together; at reconnect their catch-up (reload if the history does not fit the pool, plus backlog) is served in order.

- D162: 0.0678 + 0.000182*uncached + 0.000154*queued_ahead; deadline 3.0 s; GPU pool 62944 tokens minus the non-robot working set (sum of last prompt_tokens of live dashcam/ss sessions at reconnect (estimate from request log)).
- backlog = (D/2)*90; context limit 32768.
- reload: external-KV transfer path exists (external_kv_transfer ~1.8e6 tokens/run) and would be cheaper, but a history that does not fit is charged as full uncached re-prefill (worst case), so reload/evict P(within 3s) is a LOWER bound.
- queued_ahead = uncached catch-up of robots served earlier in the order.
- Orderings: (a) FIFO by reconnect; (b) earliest next question (ORACLE bound); (c) largest deficit first; (d) all histories evicted (baseline).

## Headline

Recovery ORDER adds almost nothing: the (b) oracle ordering beats (a) FIFO by at most 0.006 across every k and D, because all k robots reconnect at the same instant and the binding constraint is the TOTAL catch-up work (queued-ahead accumulates regardless of order), not who goes first. The real lever is keeping histories warm versus evicting them: (a)-(c) run far above (d) at every k and D. P(first token within 3 s) falls steeply as k and D grow (more robots sharing the pool, bigger backlog), and the context limit is exceeded only at D=180 s (~2-3 percent of robot-windows). The counterfactual-ordering room is the (b) minus (a) gap below; it is essentially zero.

## P(first token within 3 s) by k and outage D, pooled over rung-3 1x seeds 4 to 7

| k | D (s) | (a) FIFO | (b) earliest-next (oracle) | (c) largest-deficit | (d) all-evicted | (b)-(a) gap | ctx exceeded | mean device-only Q in window | n robot-windows |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 60 | 1.0 | 1.0 | 1.0 | 0.746835 | 0.0 | 0.0 | 0.863 | 79 |
| 1 | 120 | 1.0 | 1.0 | 1.0 | 0.620253 | 0.0 | 0.0 | 1.663 | 79 |
| 1 | 180 | 1.0 | 1.0 | 1.0 | 0.512821 | 0.0 | 0.025641 | 2.475 | 78 |
| 3 | 60 | 1.0 | 1.0 | 1.0 | 0.404348 | 0.0 | 0.0 | 2.812 | 230 |
| 3 | 120 | 1.0 | 1.0 | 1.0 | 0.283105 | 0.0 | 0.0 | 5.438 | 219 |
| 3 | 180 | 0.747619 | 0.747619 | 0.747619 | 0.204762 | 0.0 | 0.02381 | 8.05 | 210 |
| 5 | 60 | 0.964384 | 0.969863 | 0.969863 | 0.254795 | 0.005479 | 0.0 | 4.412 | 365 |
| 5 | 120 | 0.66087 | 0.66087 | 0.66087 | 0.17971 | 0.0 | 0.0 | 8.9 | 345 |
| 5 | 180 | 0.489231 | 0.489231 | 0.489231 | 0.132308 | 0.0 | 0.027692 | 13.213 | 325 |
| 7 | 60 | 0.78835 | 0.792233 | 0.786408 | 0.180583 | 0.003883 | 0.0 | 6.95 | 515 |
| 7 | 120 | 0.486815 | 0.486815 | 0.486815 | 0.125761 | 0.0 | 0.0 | 13.7 | 493 |
| 7 | 180 | 0.344086 | 0.344086 | 0.344086 | 0.092473 | 0.0 | 0.021505 | 20.363 | 465 |

Full data: results/orchestration/live2/robot_idle/d242_correlated_outage.json
