# Reconnect cost-model replay (rung-3 1x, robot questions)

**MODEL-BASED SCREEN, NOT A MEASUREMENT.** First-token time is PREDICTED by the committed D162 model; the engine is not run. This is a NETWORK experiment and is **1x only** (D240: kept separate from the memory experiments, never pooled with them).

- D162: first_token = 0.0678 + 0.000182*uncached + 0.000154*queued_ahead; deadline 3.0 s.
- backlog = (D/2) frames * tokens_per_frame, frame stride 2.0 s; tokens/frame measured per seed = {'4': 90.0, '5': 90.0, '6': 90.0, '7': 90.0} (the D2 ~90 law, confirmed).
- queued_ahead is each question's own measured in-flight uncached tokens at its submit.
- Policies: (i) history kept, catch up at question; (ii) history kept, catch up at reconnect; (iii) history evicted.

## Headline

Keeping the history and catching up the backlog AT RECONNECT (policy ii) holds P(first token within 3 s) at about 0.99 regardless of outage length, because the backlog is warm by the time the question arrives. Catching up AT QUESTION time (policy i) degrades as the outage grows (the whole backlog must prefill at the question). Evicting the history (policy iii) is catastrophic even at 60 s. The gap between (ii) and (i)/(iii) is the room an outage-aware recovery policy has: keep the history resident and pre-warm the backlog before the next question.

## P(first token within 3 s), pooled over rung-3 1x seeds 4 to 7

n_questions = 463; tokens/frame median = 90.0.

| outage D | (i) catch-up at question | (ii) catch-up at reconnect | (iii) evicted |
|---|---|---|---|
| 60 s | 0.974082 | 0.989201 | 0.144708 |
| 120 s | 0.937365 | 0.989201 | 0.028078 |
| 300 s | 0.382289 | 0.989201 | 0.0 |

## Per seed

| seed | n questions | tok/frame | D | (i) | (ii) | (iii) |
|---|---|---|---|---|---|---|
| 4 | 132 | 90.0 | 60 s | 0.984848 | 0.992424 | 0.181818 |
| 4 | 132 | 90.0 | 120 s | 0.939394 | 0.992424 | 0.037879 |
| 4 | 132 | 90.0 | 300 s | 0.416667 | 0.992424 | 0.0 |
| 5 | 123 | 90.0 | 60 s | 0.98374 | 0.98374 | 0.113821 |
| 5 | 123 | 90.0 | 120 s | 0.96748 | 0.98374 | 0.02439 |
| 5 | 123 | 90.0 | 300 s | 0.325203 | 0.98374 | 0.0 |
| 6 | 121 | 90.0 | 60 s | 0.950413 | 0.983471 | 0.157025 |
| 6 | 121 | 90.0 | 120 s | 0.884298 | 0.983471 | 0.016529 |
| 6 | 121 | 90.0 | 300 s | 0.31405 | 0.983471 | 0.0 |
| 7 | 87 | 90.0 | 60 s | 0.977011 | 1.0 | 0.114943 |
| 7 | 87 | 90.0 | 120 s | 0.965517 | 1.0 | 0.034483 |
| 7 | 87 | 90.0 | 300 s | 0.505747 | 1.0 | 0.0 |

Full data: results/orchestration/live2/robot_idle/reconnect_replay.json
