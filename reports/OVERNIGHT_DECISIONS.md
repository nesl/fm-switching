# OVERNIGHT DECISIONS (D187), for the user's morning review

Every entry is PROVISIONAL and carries its evidence. A FINDING entry means something was measured
and NO ACTION was taken, with the reason. A DECISION entry means a new labelled version was built.

---

## 2026-11-22 18:20 FINDING, NO ACTION TAKEN: assistance is oversize because of an image grid that no D-row sets

WHAT WAS MEASURED (read-only, `results/orchestration/live2/frozen_test/image_settings_by_type.json`,
pushed at `c4db4122`). There is exactly ONE image-processor setting, server-wide, for all three
query types: `--mm-processor-kwargs {"size": {"shortest_edge": 4096, "longest_edge": 16777216}}`.
It binds NOTHING: the largest image any type sends is 9.4x below max_pixels and the smallest is 48x
above min_pixels, so no image of any type is rescaled by the processor. Our body builder performs
NO resize, crop or re-encode (`bodies.py:127-147`): it base64s the stored bytes verbatim.

THE DIFFERENCE IS UPSTREAM, IN STORAGE, AND IT IS PER TYPE:
  alert frames       768x432, downsized OFFLINE before storage   338 image tokens
  recall frames      352x256, downsized OFFLINE before storage     90 image tokens
  assistance images  NATIVE dataset resolution, NO pre-resize anywhere
                     p50 1448x938, p90 1448x1536, max 1536x1536  p50 1,307 image tokens

So one assistance image costs 3.9x an alert frame and 14.5x a recall frame.

WHY IT MATTERS TO D179, and it revises my own earlier account. I reported that assistance is
"routinely OVERSIZE against its own share" and used that to explain the W overrun with no recall
present. That is true as far as it goes, but the CAUSE is not the admission rule: as sent, the
median assistance request is 1.63x its own 843.7-token share and therefore takes an oversize
branch; on alert's 768x432 grid the same request would be a CONSTRUCTED 407 tokens, 0.48x its
share, comfortably inside it. Assistance's oversize status turns on an image grid, not on D179 (3).

A SECOND, INDEPENDENT CAUSE compounds it: assistance holds ZERO residency by construction
(`trace.py:567-574`), cached fraction exactly 0.0 on all 1,428 requests, so it pays its whole prompt
every time, while alert's append-only EP-G episode is 89.3 percent cached at p50.

NO D-ROW AUTHORISES THE PER-TYPE EFFECTIVE COST. D67, D70, D91, D111, D136, D143, D148, D153, D156
and D172 were searched. D70 and D91 fix the wire format and inherit the two grids from upstream
studies; D136 and D143 choose the SS datasets and the split only; D172 requires only that the
setting be STATED. The SETTING is uniform and authorised. The effective per-image cost is recorded
nowhere.

WHY NO ACTION WAS TAKEN, and this is the point of the entry. The obvious change, pre-resizing
assistance images to a comparable grid, would make assistance fit inside its share and would very
likely improve the shares arm's numbers. D187 (3) forbids it: "NEVER change targets, deadlines,
metrics, workload, seeds, baselines, pass bars or the margin". The image grid IS the workload. A
change that happens to help the arm under test, made overnight, on a quantity no decision governs,
is exactly the kind of thing the rule exists to prevent, so it is reported and left for the user.

REGISTER: 1,372 and 374 are MEASURED medians; 407 is a CONSTRUCTED bound, not a census.

POSITIVE CONTROLS ON THE READING, both exact before any table was trusted: the EP-G law
`prompt_tokens = 42 + 338 x n_frames` holds on 39,945 of 39,945 alert requests across the four base
cells, deviation histogram {0: 39945}; and `share_capacity.FACTORS` medians recompute from the four
cells that file names as its source at alert 374, recall 7,717, assistance 1,372, ratio 1.000000.

TWO SMALLER ITEMS FROM THE SAME READ:
1. A PROXY THAT FAILS, flagged by the code itself: assistance UPLINK BYTES substitute the S-EMBER D2
   median for every SS2 image (`fleet/data_sources.py:661`), understating them by 2.2x to 24x in
   area. It touches no token count, so nothing above depends on it, but any assistive uplink figure
   resting on it is unvalidated.
2. In the `b7-edf-feasibility` s4 cell, 74 of 8,058 alert requests deviate from the EP-G law, while
   the four base cells are 0 of 39,945. Not diagnosed and not used for any number here; flagged as a
   cheap check for whoever owns b7.

---

## 2026-11-23 02:40Z DECISION, PROVISIONAL: the watchdog's restart condition was wrong in both directions, and its restarts cannot do the work

WHAT HAPPENED. The watchdog installed under D187 (5) restarted on the condition "does the tmux
session `fmsw-overnight` exist". It spawned three sessions in twenty minutes (02:12, 02:20, 02:30)
and would have spent its whole six-per-hour budget. The condition was wrong in BOTH directions at
once:

1. The session actually doing the work was never in tmux. It is attached to the user's client, so
   it cannot move itself there, and to the watchdog it therefore looked DOWN while it was working.
2. Each spawned `claude -c -p` EXITS when its prompt completes, so the tmux session vanishes within
   a minute and the next cron tick spawns another. The restart condition was self-refilling.

THE CORRECTION, applied: a HEARTBEAT gate. A live worker touches `ops/heartbeat`; if it is fresher
than 1,800 s the watchdog does not restart. Tested both ways and logged: fresh gives "OK worker
heartbeat 0s old, not restarting", and an artificially staled heartbeat still fires the restart, so
the gate did not simply disable the watchdog.

THE MORE IMPORTANT FINDING, AND IT IS A PERMISSIONS QUESTION FOR THE USER, NOT SOMETHING TO ROUTE
AROUND. The sessions the watchdog spawns are effectively READ-ONLY. A watchdog-resumed session
reported being refused repo writes, refused even `sed` and `grep` READS under `/tmp/claude-1001/`
where the whole workflow lives, and prompted for `tmux ls`. The H100 independently reproduced the
same thing on its own box. So a faithful restart produces a session that cannot continue the work.
Nothing was changed to work around that, per D187 (5)'s "using only the permission settings already
configured".

WHAT THE SPAWNED SESSION DID WITH THE ONE CHANNEL IT HAD, which is worth recording because it was
correct. It read the handoff, independently found a real defect in the cold-pricing fix (the engine
telemetry was being subtracted on the COLD branch, where it is stale because nothing resets it on
eviction), could not apply the correction, and sent it to the H100 with the exact replacement code
so nobody would have to rediscover it. It also declined to ask the H100 to commit on its behalf and
said so. The H100 verified the defect from the code itself rather than acting on relay, and refused
the proxy write. BOTH behaved correctly.

A CORRECTION TO MY OWN EARLIER REPORT: I told the user that a message the H100 received, which I had
not sent, was "the one event tonight I cannot account for". It is now accounted for. It came from my
own watchdog-spawned session on this box, which is why it arrived with a different session id and
the name "A6000" and described itself as read-only. There was no spoofing and nothing unexplained.

A SECOND CORRECTION, to the fix itself: my first attempt at the COLD guard subtracted `built_tokens`
on the COLD branch whenever it was non-zero, which changed COLD pricing in the UNSAFE direction (an
evicted session's build pieces are evicted with it) and added a second change on top of the
telemetry fix, so an r1-against-shares comparison would have carried two changes rather than one.
The H100 caught it and also noted that my four test cases did not cover COLD with `built_tokens` > 0
- the single case that distinguishes the two forms. The final form leaves COLD exactly as it was and
changes only the warm branch, verified case by case.
