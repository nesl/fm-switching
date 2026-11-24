# OVERNIGHT HANDOFF, 2026-11-23 evening. Written BEFORE step 1, per the user's plan.

ALL TIMES ARE PST AND STATE THEIR ZONE. Derive idleness from the newest commit's timestamp WITH ITS
OFFSET (`git log --date=iso-strict`), never from a bare clock time: reading PST commit times as UTC
once produced a false "H100 idle eight hours" claim while it had committed one minute earlier.

## READ THIS FIRST, FOR A WATCHDOG RESUME. STATE AS OF 2026-11-23 22:20 PST.

*** THE RESUME PROMPT CONTAINS THREE STALE PREMISES. DO NOT WASTE CALLS ON THEM. ***
- **`ops/watchdog.log` AND `ops/track.log` NOW EXIST ON DISK. CORRECTED 2026-11-23 22:31.** The
  earlier entry said they did not exist anywhere; that was checked with `git cat-file -e`, WHICH ONLY
  TESTS ORIGIN, so it could never have seen a gitignored local file. They are local-only and live:
  `ops/watchdog.log` 299 lines, `ops/track.log` 1,298 lines, newest entry 06:30:01Z. **READ THEM, they
  are informative**, but they are NOT a concurrency check: watchdog.log records session liveness and
  track.log carries prior resumes' own reports. *** WHAT watchdog.log SAYS RIGHT NOW MATTERS: heartbeat
  STALE and `RESTART 3/12: session fmsw-overnight absent` at 06:10, 06:20 and 06:30Z. THE CLAUDE SESSION IS
  RESTARTED EVERY TEN MINUTES, which is why you are reading this. Expect to be resumed again; leave the
  file fit for that.***

*** THE RESTARTS ARE EXPECTED BEHAVIOUR, NOT A CRASH, AND THE OVERNIGHT WORK IS ALIVE. Established by
process census at 22:40, so no resume needs to re-derive it. ***
- The watchdog launches `claude -c --permission-mode auto -p '<the resume prompt>'`, which is a
  ONE-SHOT non-interactive session: it exits when its turn ends. The watchdog then finds no session,
  calls the heartbeat STALE and restarts it. **So "heartbeat STALE" plus "session absent" is what a
  HEALTHY `-p` run looks like to this watchdog.** It is bounded: the log counts `RESTART n/12`, and it
  stood at 4/12 at 22:40. *** CORRECTED 2026-11-24 07:00 PST: "BOUNDED" IS TRUE PER WINDOW
  AND FALSE OVER TIME. THE BUDGET CAN NEVER BE SPENT, SO THIS LOOP IS EFFECTIVELY PERPETUAL. ***
  `ops/watchdog.sh` sets `MAX_RESTARTS=12` and `WINDOW_S=3600`, and line 104 RESETS the counter whenever
  the window elapses (`if [ $((now - first)) -gt $WINDOW_S ]; then first=$now; count=0; fi`). The poll
  fires every TEN MINUTES, so it can only ever reach **6 restarts per hour against a budget of 12**:
  **THE GUARD IS STRUCTURALLY UNREACHABLE.** Measured rather than argued: `BUDGET SPENT` has fired
  **0 times**; the log holds **109 RESTART lines** (re-counted restart 16) spanning 2026-11-23T02:12:39Z to 2026-11-24T15:00:01Z,
  about 37 hours; and the counter histogram shows it reset to `1/12` **18 times**, never exceeding
  `7/12`. So a resume must NOT read `RESTART n/12` as a countdown to a stop. **IT WILL KEEP SPENDING
  ABOUT SIX SESSIONS AN HOUR, INDEFINITELY, UNTIL THE USER STOPS THE `fmsw-overnight` WATCHDOG OR
  ANSWERS THE RULINGS.** **109 sessions have been spent so far** (re-counted restart 9, 07:40 PST; `BUDGET SPENT` still 0). Stopping it is the USER'S call and outside
  what this file authorises, so do not touch it; the correct action is to say so plainly in the reply,
  which is now this file's standing instruction for every further resume. DO NOT read the restarts as evidence that anything broke, and do not go
  hunting for the crash. Each restart does cost a full session, so leave this file accurate.
*** SUPERSEDED 2026-11-24 ~12:00 PST: NOTHING IS RUNNING. THE BOX IS FREE AND A DRY CELL OF YOUR OWN
MAY RUN. *** Verified by census, not assumed: ZERO live2 python under the repo or any scratchpad, loadavg
0.16. E1's sweep and the DEVICE_ANSWERS driver both FINISHED and their sessions STOOD DOWN. The two
bullets below are kept only for the trail.
  [STALE, DO NOT ACT ON:] ~~E1's 52-cell sweep IS RUNNING, pid 304781 ... a dry cell of your own must
  WAIT.~~ ~~The DEVICE_ANSWERS driver was restarted and is writing to scratchpad/cells.~~

*** CORRECTED 2026-11-24 19:2x PST (watchdog restart, this session). THE BLOCK BELOW IS STALE IN FOUR
PLACES AND ONE OF THEM IS DANGEROUS. VERIFIED AGAINST ORIGIN `7ff8e746`, NOT ARGUED. ***

**1. "NOTHING IS RUNNING. THE BOX IS FREE AND A DRY CELL OF YOUR OWN MAY RUN" IS FALSE RIGHT NOW. DO NOT
RUN A DRY CELL.** Census by `/proc/<pid>/cwd` plus interpreter: **pid 629985 `python -I p1_abc.py e5 final
1200`** is alive under `timeout 3000` in `scratchpad/rung4p1_8ab3f7e8`, loadavg 1.17. **It is the rung-4
pass-1 proof sweep and its digests are a D216 ALONE proof bar**, so a dry cell of your own would void it.
The ~12:00 census that wrote "the box is free" was true then and is not now. **A CENSUS IS A TIMESTAMP, NOT
A PROPERTY**, and this file states it as a property - which is how it became a trap rather than a note.

**2. "Step 2 E1: IMPOSSIBLE AS WRITTEN. `scrape_metrics()` has zero callers; no switch reaches a decision"
IS FALSE. E1 IS BUILT, LANDED AND WIRED END TO END.** On origin: `scrape_metrics` defined once and
**called once** (not zero); `published_engine_metrics` present; the runner's `--metrics-scrape` flag
present at **`default=False`**; `procsplit` reads it back into the backend; `metrics_health` written from
the runner at three sites (that is E3, ruling 8). **Measured consequence, from the proof:** over 601 real
live observations the engine metric binds **596** and the belief **5**, with `free_kv` spread over 134
distinct values; with the gauge forced to 0.0 the belief binds **601 of 601**, reproducing the four
committed rung-4 cells' signature exactly. **So ruling 5 and ruling 8 are DONE, not open.**

**3. THE RULINGS LIST IS OUT OF DATE. D228 (2026-11-24, on origin; the log now holds 228 rows) SETTLED
THREE OF THEM.** Ruling **1, the harm form: RULED.** D220 (1)'s gain weighting is **withdrawn as a planner
error**; harm stays in **D177 units** (on-time cloud answers lost by others x per-device `w_d`), the
device-discounted form **stays rejected**, `MARGIN_CF` unchanged at **0.6582**. So the note below that
"device-discounted makes the DEVICE_ANSWERS 1x count 0 and ruling 4 dissolves" **does not apply** - the
count stays 1, the stop fired for real, and **ruling 4 still needs an answer**. Ruling **3, the queue-term
fix, is no longer DO-NOT-BUILD: D228 (1) ruled reading (B)** and it is built - the prediction moves to the
D162 model with the real queued-ahead uncached tokens, away from a model whose own `GATE_STATUS` says it
fails spec v5 section 12, a **247.4582067460825x** unit difference (requests against tokens).

**4. "ALL FIVE OVERNIGHT STEPS ARE CLOSED OR BLOCKED ON THE USER. NOTHING EXPERIMENTAL IS ACTIONABLE" IS
FALSE.** Rung-4 pass 1 is pre-registered on origin as **`StudyD222-PASS1`** (reading B named, both s4 bars
verbatim, `SAFETY_FACTOR 1.76717`) and **two cells are gated on the H100**: `covex-v6-final` **1x s4
`_rerun`** (running since 11:17:45, `never_scraped`) and **kv0.5r s4 `_ms`** (scraped, v36 maps `_ms` to
`--metrics-scrape`). Also landed today and **not** reflected below: the **D225 conformance matrix
verification** (`research/conformance_matrix_verification.md`, 41 confirmed / 11 refuted / 5 not
checkable, freeze gate **16 rows, not 15**); the **31 stub cells marked** with their scores confirmed
intact (31 of 31); **D211 signal (a) computed and FAILED** (`d211_signal_a_validated.json`, ratio 9.89
against a 10 percent bar, classified **fired and did not help**); and both passes of the **D228 (5)
worktree rule**.

**WHAT A RESUME SHOULD ACTUALLY DO NOW: NOTHING EXPERIMENTAL, AND DO NOT START A CELL.** The proof sweep
owns the box. The open work is still the user's rulings, now **five** rather than eight: **2** (rung 4's
supersession), **4** (DEVICE_ANSWERS adopted into `covex-v6-final` or kept separate - note ruling 1 no
longer dissolves it), **6** (which D218 pre-registration is the record), **7** (the r2 queue register), and
the **freeze-gate rulings** the matrix verification added: 10.1, **10.12 the lexicographic objective**
(not built, the code says so about itself, and no D-row anywhere removes it), 10.13, 10.14 and 10.7's exit
hysteresis. **Plus two defects worth fixing whatever the gate decides:** one `GUARD_LAG_S_DEFAULT = 2.0`
serves all three types, so **alerts with a 1.0 s deadline get a 2.0 s guard threshold** and cannot be
protected before their deadline passes; and rung 3/4's `_feed_split` weight is **computed every decision
and read zero times**, because `coordinator.py:1615` returns early with `_share_admission` False on all
five arms.

*** CURRENT POSITION IN ONE BLOCK, SO NO RESUME HAS TO READ 900 LINES TO FIND IT. ***
**ALL FIVE OVERNIGHT STEPS ARE CLOSED OR BLOCKED ON THE USER. NOTHING EXPERIMENTAL IS ACTIONABLE.**
- **THE LADDER IS COMPLETE AND FULLY SCORED** (`8feed0fe`). Rung 3 `covex-v6-fair-final`: **all three
  checks pass at ALL FOUR seeds**, beating its comparator (retention 1.106 / 1.077 / 1.000 against a 0.90
  bar). Rung 4 `covex-v6-final`: **all three pass at ONE seed of four**; check 2 fails at s5/s6/s7 and
  check 1 ALSO fails at s7. **GOVERNING CAVEAT: these four seeds do NOT test the rung-4 DESIGN** - one
  added limb was never reachable and the other fires with a hard-zero queueing term.
- **Step 1 DEVICE_ANSWERS: DONE, and it STOPPED on its pre-registered condition** (1x count is 1).
- **Step 2 E1: IMPOSSIBLE AS WRITTEN.** `scrape_metrics()` has zero callers; no switch reaches a decision.
- **Step 3 item 3: LANDED AND WIRED** (`56a73293`, call site `coordinator.py:2138`, method `:2148`), 24 of
  24 dry arms byte-identical. It also CLOSES the signal-(a) gap for future cells.
- **Step 4 the 0.25x pair: GATED** on step 1's ruling AND on `covex-v6-final-da` not resolving on the
  normal import path (it needs its own byte-identity proof first).
- **Step 5 the doc lines: DONE AND PROVED** (`fbd2f64b`), A = B = `57bed6ace2eb07d1` / 14,509.
- **THE RUN-PATH FREEZE HAS LAPSED, BOTH REASONS.** See the reconciliation further down; the procedure
  that replaces it is: build from ORIGIN's content, census the box, and prove a live-path edit neutral on
  a dry A/B from one literal sha.
**SO THE ONLY OPEN WORK IS THE USER'S RULINGS. THERE ARE EIGHT AND THE FIRST ONE MAY DISSOLVE THE
FOURTH, SO THE ORDER MATTERS:**
  1. *** THE HARM FORM *** - `on-time-cloud` or `device-discounted`. The code says the choice is a user
     ruling and nobody had asked; added 2026-11-24. **TAKE IT FIRST:** under `device-discounted` the
     measured device tables make the harm of displacing an alert or a recall EXACTLY ZERO, so the
     DEVICE_ANSWERS 1x count becomes 0, the stop condition would never have fired, and ruling 4 dissolves
     rather than needing an answer. It also moves rung 4's Rule 2 class at s4 and s7.
  2. Rung 4's supersession, now that it passes check 2 at one seed of four.
  3. The queue-term fix - **DO NOT BUILD** (D187 (2) superseded for it; diagnosed and costed).
  4. DEVICE_ANSWERS adopted into `covex-v6-final` (D209 (1) then supersedes the posted s4 cell) or kept
     as a separate arm. **See ruling 1 first.** The implementation is preserved HELD at
     `experiments/orchestration/live2/held/d218_device_answers/`; do not rebuild it.
  5. Wiring the metrics link. Worth doing but NOT the blocker it once looked like: the belief already
     supplies a varying `free_kv`, so the engine metric mainly matters at 0.25x where capacity binds.
  6. Which of the two agreeing D218 pre-registrations is the record.
  7. **THE r2 QUEUE REGISTER** - keep a CORRECT input that costs 16 robot answers at s4, or keep r1?
     Added 2026-11-24, its own diagnosis defers it. **Does NOT affect the ladder** (rung 4's base is
     `fair_final`, not the shares line).
  8. E3, one line so a cell with failed metrics fetches says so.
**A RESUME THAT FINDS NOTHING ELSE TO DO IS CORRECT: say so and stop, rather than inventing work or
re-deriving this block.** If you have spare capacity, the useful thing is to VERIFY one of this file's own
claims against origin and correct it, which is how every resume since 2026-11-24 09:00 found a real stale
entry - INCLUDING THIS BLOCK, which listed six rulings and omitted the two newest until a resume checked
its own summary against the section it summarises. **A SUMMARY GOES STALE FASTER THAN THE THING IT
SUMMARISES.**

*** VERIFICATION LEDGER, SO SUCCESSIVE RESUMES DO NOT ALL RE-CHECK THE SAME CLAIMS. APPEND TO IT. ***
Each entry: the claim, the verdict, and the restart that checked it. **PICK ONE NOT LISTED HERE.**
- `RESTART n/12` means the loop is bounded -> **FALSE, CORRECTED** (restart 6, 2026-11-24 07:00 PST).
- "NOTHING IS RUNNING, THE BOX IS FREE, A DRY CELL MAY RUN" (~12:00 PST) -> **FALSE BY 19:20**, pid 629985
  is a D216 ALONE proof sweep (this restart, 2026-11-24 19:2x PST). A census is a timestamp, not a property.
- "Step 2 E1 is IMPOSSIBLE AS WRITTEN, `scrape_metrics()` has zero callers" -> **FALSE, E1 IS WIRED END TO
  END** on origin, runner default `False`, E3's `metrics_health` written (this restart).
- "Eight rulings, ruling 1 dissolves ruling 4" -> **FALSE SINCE D228**: ruling 1 is RULED (gain weighting
  withdrawn, harm in D177 units), so ruling 4 does NOT dissolve; rulings 3, 5 and 8 are closed (this restart).
  The budget is unreachable: 12 per 3600 s against a 10-minute poll, with the counter reset at
  `watchdog.sh:104`. `BUDGET SPENT` fired 0 times in 99 restarts over 37 hours. See the corrected
  block above.
- item 3's call site `coordinator.py:2138` -> **TRUE** (restart 7). `belief=` is on that line.
- item 3's method `coordinator.py:2148` -> **TRUE** (restart 7). `def _belief_prefix_record(self)`.
- D187 at `research/policy_design_log.md:208` -> **TRUE** (restart 7).
- the held DEVICE_ANSWERS implementation at `live2/held/d218_device_answers/` -> **TRUE** (restart 7),
  9 files on origin.
- *** THE RULING-1 PREMISE: that the device tables make device-discounted harm EXACTLY ZERO for an
  alert or a recall -> **TRUE AS THE CODE IS WRITTEN, WITH ONE QUALIFICATION THE USER SHOULD SEE**
  (restart 8, 2026-11-24). *** Verified from the code, not from the note that asserts it:
  `p_device_on_time` (`v5/cf_objective.py:393`) returns `1.0 if w <= deadline else 0.0`, and the
  measured inputs are ROBOT 0.2503-0.3108 s over 97 LH-REQ questions against deadlines of 2.5-5 s,
  and DASHCAM 0.2349-0.3169 s over frame positions 1-21 against a 1 s deadline. Both are inside
  their deadlines by a wide margin at every entry, so `p_device_on_time` is 1.0 and the
  `(1 - p_device_on_time)` multiplier is 0. **SO ruling 1 DOES dissolve ruling 4: under
  device-discounted the DEVICE_ANSWERS 1x count becomes 0 and its stop condition would never have
  fired.** Single-shot is the exception the note already gives: it varies, and 45.5 percent of
  refspatial questions give `p_device_on_time` = 0, so the compound could still fire on assistance.
  *** THE QUALIFICATION, AND IT IS A MODELLING CHOICE RATHER THAN A MEASUREMENT: *** the dashcam
  table loaded at `cf_objective.py:167` is `_DS.dashcam_append_ttft_s()`, the APPEND curve ONLY.
  `cf_objective.py:131` records that **THE EPISODE-START CURVE REACHES 1.88 s**, which WOULD exceed
  the 1 s dashcam deadline and give `p_device_on_time` = 0 for that instant. That curve is NOT in
  the lookup, so no decision can ever see it. The zero is therefore exact for the implementation and
  rests on the assumption that a dashcam instant is always priced as an APPEND; if an episode's
  first frame should be priced at its start cost, the discounted harm of displacing THAT alert would
  be non-zero. **Worth knowing before ruling 1, because ruling 1 turns on this zero.**
- *** THE TWO D218 PRE-REGISTRATIONS "AGREE VERBATIM" -> **FALSE AS WORDED, TRUE IN SUBSTANCE, AND
  THIS NARROWS RULING 6 TO A PURELY FORMAL CHOICE** (restart 9, 2026-11-24 07:40 PST). *** Compared
  field by field from origin, BOTH files, not from either one's account of the other. **The strings are
  NOT identical** - a direct equality test on the pass-condition text returns False:
    MINE (`e0811790`, 19:06) splits it into `PASS_CONDITION_.../condition_1` = "pd_request_crossed_bar_
    unexpressible FALLS against covex-v6-final's 27 on the same cell" and `condition_2` =
    "pd_request_device_answers > 0", with the 1x treatment in a SEPARATE key.
    PEER (`77cf269e`, 19:23) is ONE sentence: "on the 0.25x DRY s4 cell: pd_request_crossed_bar_
    unexpressible FALLS AND pd_request_device_answers > 0. The 1x count is REPORTED WHATEVER IT IS."
  **BUT BOTH CARRY THE SAME THREE SUBSTANTIVE POINTS**, including the one that matters most: each says
  the 1x count carries NO PASS OR FAIL and is reported because D209 (1) needs it, and each says a
  non-zero 1x count RAISES the supersession question rather than deciding it. Mine's key is literally
  `the_1x_count_is_REPORTED_WHATEVER_IT_IS`. **SO NO BAR, NO THRESHOLD AND NO NUMBER DIFFERS BETWEEN
  THEM: RULING 6 CANNOT MOVE A RESULT EITHER WAY** and is a provenance and credit question only. Worth
  telling the user, because the way it is phrased makes it sound as though a result could turn on it.
  **AND THE WORD "VERBATIM" WAS MINE** - relayed from the building agent's report without comparing the
  files, and it then entered this ledger as the claim to check. The substance was right and the word was
  not. NOTE line 549 of this file makes the same "VERBATIM" claim; it is corrected by this entry.
- *** `covex-v6-final-da` DOES NOT RESOLVE ON THE NORMAL IMPORT PATH -> **TRUE, AND OVER-SATISFIED, SO
  THE STEP-4 GATE GENUINELY STANDS** (restart 10, 2026-11-24 07:50 PST). *** Verified from origin with an
  untruncated grep whose rc was checked: the name occurs in **12 places, ALL inside
  `live2/held/d218_device_answers/`**, and nowhere else under `experiments/`. The reason it cannot resolve
  is STRONGER than "unregistered": **all 9 files carry a `.patch` or `.held` suffix and there are ZERO
  plain `.py` files under `held/`**, so `arms_v6cf_device.py.held` is not an importable module and cannot
  be caught by a `*.py` glob. **That is D187's "held code defaults OFF" enforced by FILENAME rather than
  a flag** - the one form that cannot be switched on by accident. So step 4 does need its own
  byte-identity proof before the pair runs, exactly as recorded.
  **ONE PRECISION FIX MADE TO THAT README IN THE SAME COMMIT, because it would mislead the next resume
  doing this very check:** its line 5 said the name "occurs in ZERO files under `experiments/` on
  origin". FALSE as literally worded - it occurs in 12, all within `held/` itself - so a resume that
  greps the name finds twelve hits and may distrust the file or conclude the arm IS wired. It now says
  zero files ON THE IMPORT PATH, which is the true and load-bearing claim, with the old wording recorded.
- *** THE r2-QUEUE-REGISTER CLAIM, "a correct input costs 16 robot answers at s4" -> **TRUE, VERIFIED
  FROM THE CELLS THEMSELVES, AND RULING 7 IS SHARPER THAN ITS OWN FRAMING** (restart 11, 2026-11-24
  07:55 PST). *** Read from each arm's OWN committed score block, not from the diagnosis's account of
  itself:
    `covex-v6-state-shares-r1`  robot on time **95** of 132, `by_deadline` **0.5455**
    `covex-v6-state-shares-r2`  robot on time **79** of 132, `by_deadline` **0.5227**
    `covex-v6-state-shares`     robot on time **60** of 132, `by_deadline` **0.5455**
  95 minus 79 is exactly the 16 claimed, so the number is right.
  *** BUT THE WORD "TRADE-OFF" IS NOT: r1 DOMINATES r2 ON BOTH MEASURED AXES. *** r2 is lower on on-time
  (79 against 95) AND lower on correctness-by-deadline (0.5227 against 0.5455). **So nothing measured is
  being traded FOR anything measured** - the only thing r2 has in its favour is that its input is
  correct. Ruling 7 is therefore "keep a correct input that is worse on both measured axes, or keep r1",
  which is a cleaner question than "a trade-off", and the diagnosis's own sentence that "a correct input
  and a useful lever are not the same proposition" is exactly right.
  *** ONE THING THE SAME READ TURNED UP, worth seeing before ruling 7: *** r1 delivers **35 MORE on-time
  robot answers than the unsuffixed `shares` arm (95 against 60) at an IDENTICAL `by_deadline` of
  0.5455.** So on this arm family those 35 extra on-time answers bought ZERO correctness. That is the
  on-time-versus-correct distinction again, and it means the 16 answers r2 "costs" should not be assumed
  to carry 16 answers' worth of value either. Both r1 and r2 do beat the original 60 on on-time.
*** RESTART 16: THE ELEVEN AT-FLOOR BASELINES ARE A GENUINE MEASUREMENT, NOT A DEFECT. VERIFIED
INDEPENDENTLY FROM THE CELLS, AND THE POSITIVE CONTROL IS DECISIVE. THIS CLOSES THE BIGGEST OPEN RISK TO
THE FIGURE DATA. ***
The worry raised earlier was that eleven baselines sit at `by_deadline` = 0.371212 EXACTLY while their
on-time counts VARY from 0 to 6, which the definition seemed not to allow, and that the alternative was
the placeholder failure mode where a cloud answer never reaches the metric. **IT IS THE BENIGN
EXPLANATION, AND IT IS NOW MEASURED PER ARM.** Using `score.robot_rows`'s `source_by_deadline` field,
which records WHICH answer `by_deadline` actually used:
  | arm | cloud-sourced rows | of those device-correct | cloud-correct | ***delta*** |
  | eco-llm | 6 | 2 | 2 | **+0** |
  | kvflow-prefetch | 6 | 2 | 2 | **+0** |
  | always-cloud-fcfs | 5 | 2 | 2 | **+0** |
  | mooncake | 5 | 2 | 2 | **+0** |
  | lmcache | 3 | 0 | 0 | **+0** |
  | warm-all-lru | 3 | 1 | 1 | **+0** |
  | ***`covex-v6-fair-final`*** | ***126*** | 48 | ***82*** | ***+34*** |
**EVERY AT-FLOOR ARM IS EXACTLY +0**: the cloud answers it gets on time are of IDENTICAL correctness to
the device answers they replace, so the metric cannot move and lands on the floor. **AND THE POSITIVE
CONTROL IS THE LOAD-BEARING HALF: `covex-v6-fair-final` is cloud-sourced on 126 of 132 rows and gains
+34 correct answers**, so the channel demonstrably CAN move `by_deadline`. The placeholder hypothesis is
therefore RULED OUT, not merely doubted: `source_by_deadline` shows the cloud answer reaching the metric,
and the gold comparison is live (fair-final's `cloud_letter` spans A:3 B:42 C:16 D:34 E:37 against golds
A:21 B:36 C:25 D:11 E:39, 86 of 132 cloud-correct).
**AND THE CAUSES ARE SEPARATED, WHICH WAS THE POINT:** `cascade-routing` and `r3-streaming` have ZERO
on-time cloud answers, so they reach the floor for a DIFFERENT reason than the nine above. Floor-equality
is not one finding. **SO THE ELEVEN BASELINE ROWS IN THE FIGURE DATA ARE SOUND ON THIS AXIS.** The
remaining open question about them is the H100's own hypothesis, explicitly not a claim: timing-bound
(few on-time answers, neutral) against representation-bound (SimpleStream: full delivery, BELOW the
floor) failure modes. That needs per-arm causes before it is written.

*** EXTENDED AT RESTART 15: ALL THREE OF `READINESS.md`'s STATED GAPS ARE STALE, AND ALL THREE
UNDERSTATE WHAT IS AVAILABLE. CHECKED AGAINST ORIGIN, NOT AGAINST THE FILE. ***
`reports/figdata/READINESS.md` section "Gaps until reruns land" lists three. Every one is now out of date:
  1. **"cascade-routing: no scored cell yet"** -> **FALSE. ALL FOUR SEEDS EXIST, VALID, 0 ERRORS AND
     SCORED**: robot on-time 0 of 132 (s4), 0 of 127 (s5), 0 of 121 (s6), **18 of 105 (s7)**. The 18 at
     s7 are the D176 over-32k set, verified earlier as the identical set and sent as `RECENT`. Its
     `by_deadline` equals the device-only floor at every seed - but BY CONSTRUCTION, because it barely
     sends, NOT because a short representation was delivered fast. If it goes in as "the
     device-only-floor baseline" that distinction must travel with it.
  2. **"confidence-cascade: gap until the D205 rerun lands"** -> **FALSE. ALL FOUR D205 RERUNS HAVE
     LANDED** (`confidence-cascade_n16_s{4,5,6,7}_..._rq30_rerun`).
  3. **"final ladder: not present"** -> **FALSE FOR TWO OF THE THREE ARMS.** `covex-v6-state-final` and
     `covex-v6-fair-final` are ALREADY IN SEVEN TABLES (F1, F2, F3, F4, F13, F14, F1_units; 89
     occurrences each, including 49,012 rows in F3). **ONLY `covex-v6-final` (RUNG 4) IS GENUINELY
     ABSENT** - zero occurrences in every table, with the two present arms' counts exactly symmetric, so
     the exclusion is systematic rather than sporadic. The promised migration ("development rows kept as
     status=superseded-by-final") has therefore PARTLY HAPPENED WITHOUT THE TABLE RECORDING IT: the
     arm-coverage table still names only the DEVELOPMENT arms as the rung rows.
**THE SHAPE OF THIS, AND IT IS THIS FILE'S OWN LESSON POINTING AT SOMEONE ELSE'S FILE: A READINESS NOTE
GOES STALE FASTER THAN THE DATA IT DESCRIBES**, and all three errors run the same way - they say work is
missing when it has landed. A reader trusting the gaps section would hold back three arms that are
available and would not learn that rung 4 is the one real absence.
**RUNG 4's ABSENCE MAY STILL BE THE RIGHT EDITORIAL CALL** - it passes its pre-registered checks at ONE
SEED OF FOUR - but it is nowhere stated as a choice, which is the only part that needs fixing.
**NOT ACTED ON, DELIBERATELY:** `READINESS.md` says "NO FIGURES until the user says plot", the user has
been committing to that directory every few minutes this morning, and D187 forbids touching another
session's work in progress. REPORTED, NOT EDITED.

*** ONE OBSERVATION FOR THE USER, FOUND AT RESTART 14 AND NOT ACTED ON, BECAUSE THE FILES BELONG TO
THE USER'S LIVE FIGURE WORK. RUNG 4 IS ABSENT FROM EVERY FIGURE TABLE. ***
`reports/figdata/` (StudyFIGDATA, D214, pipeline sha `b5264100`, generated 2026-11-23) carries the final
ladder's rung 2 and rung 3 but NOT rung 4. Counted across every CSV on origin:
  | table | `covex-v6-state-final` | `covex-v6-fair-final` | ***`covex-v6-final`*** |
  | F1 | 5 | 5 | **0** |
  | F2 | 12 | 12 | **0** |
  | F3 | 49,012 | 49,012 | **0** |
  | F4 | 64 | 64 | **0** |
  | F13 | 4 | 4 | **0** |
  | F14 | 4 | 4 | **0** |
  | F1_units | 1,914 | 1,914 | **0** |
**THE COUNTS ARE EXACTLY SYMMETRIC FOR THE TWO ARMS THAT ARE PRESENT, AND RUNG 4 IS UNIFORMLY ZERO**, so
this is a systematic exclusion by the pipeline's arm list, not sporadic missing rows.
**WHY IT MAY BE CORRECT AND STILL NEEDS SAYING:** rung 4 passes its pre-registered checks at ONE SEED OF
FOUR, so leaving it out of a headline figure may well be the right editorial call. But it is nowhere
STATED as a choice, and `READINESS.md`'s own arm-coverage table lists NEITHER final arm - it names the
DEVELOPMENT arms (`fair-c5attr`, `state-uo-c5attr`, `base`, `rules`) as the rung rows - **so the table
understates what its own CSVs contain AND is silent on rung 4's absence.** A reader of a ladder figure
built from these tables would see a two-rung ladder and no note explaining it.
**NOT ACTED ON:** `READINESS.md` says "NO FIGURES until the user says plot", the user was committing to
this directory minutes before this check, and D187 forbids touching another session's work in progress.
So this is REPORTED, not edited. The decision is the user's: either exclude rung 4 deliberately and say
so in `READINESS.md`, or regenerate with it included.

*** THE VERIFICATION LEDGER IS NOW COMPLETE. *** Every claim this file listed as unverified has been
checked against origin or against the cells. A resume with spare capacity should NOT invent a new claim:
say the ledger is complete, report the restart cost, and stop.

*** A CORRECTION TO THIS FILE'S OWN HANG-DETECTION LESSON, because I got the discriminator wrong
earlier tonight and a future resume would kill a healthy driver with it. ***
The catalogue below records a driver that sat 59 minutes at `00:00:00` CPU having started nothing. I
treated **zero own CPU** as the hang signal. **THAT IS WRONG AND DANGEROUS: AN ORCHESTRATOR DRIVER
CORRECTLY SHOWS ~0 OWN CPU, BECAUSE ITS CHILDREN DO THE WORK.** pid 304781 has consumed `00:00:00` in
2.5 hours and is perfectly healthy. **THE REAL DISCRIMINATOR IS CHILDREN: `0 CPU` AND `ps --ppid <pid>`
EMPTY is a hang; `0 CPU` WITH a live child burning CPU is a working orchestrator.** Check children, and
check what the child is doing, before calling anything hung.
- **D187 IS NOT IN THIS FILE.** It is `research/policy_design_log.md:208`. Its guardrails, which DO
  apply: every change justified by a MEASURED mechanism and PRE-REGISTERED (commit before its cells);
  each design change a NEW LABELLED version recorded as OVERNIGHT DECISION, PROVISIONAL; never change
  targets, deadlines, metrics, workload, seeds (never 1-3 or HOLDOUT), baselines or pass bars; never
  drop or exclude data; NEVER TUNE A PARAMETER TOWARD PASSING; every result reported whatever its
  direction; held or unproved code defaults OFF; one dry cell per process; D166 commit rules; NO Claude
  attribution lines; no em dashes.
- *** D187 (2)'s "FIX WITHOUT WAITING FOR APPROVAL" IS SUPERSEDED FOR THE RUNG-4 DEFECT. *** The user's
  instruction of 2026-11-23 evening commissioned the diagnosis and required the remedy be "costed, NOT
  built", and the standing rule is STOP AND REPORT, DO NOT DECIDE when a pre-registered condition
  fails. **DO NOT BUILD THE QUEUE-TERM FIX.** It is diagnosed, costed and waiting on the user.

*** THE CONCURRENCY TEST, CORRECTED AGAIN ON 2026-11-24. "DIRTY + DIFFERS" IS TOO COARSE AND IT BLOCKED
REAL WORK ALL NIGHT. *** I read `dirty-vs-HEAD AND differs-from-origin` as "another session is mid-edit"
and declined to touch four files for hours. THREE FACTS KILL THAT READING: nothing was running (no
interpreter under the repo or a scratchpad; loadavg 0.38); the mtimes were **3h42m to 36 HOURS** old
(`INDEX.md` 11-23 20:18, `arms.py` 11-22 22:47, `coordinator.py` 11-22 19:55, `cf_objective.py` 11-22
11:42); and the diffs run the WRONG WAY - the worktree copies are SHORTER than origin's (782 vs 818,
2197 vs 2297, 640 vs 911), so they are OLDER, not newer.
*** THE TEST THAT DECIDES SAFETY: DOES THE WORKING TREE HOLD ANY LINE ORIGIN LACKS? ***
*** THIRD CORRECTION, 2026-11-24: COUNTING WORKTREE-ONLY LINES GIVES FALSE POSITIVES, AND IT GAVE TWO
TODAY. *** The count cannot tell NEW CONTENT from AN OLDER VERSION OF A LINE THAT WAS LATER EDITED,
because an edited line yields one `>` AND one `<`. Measured this morning: `arms.py` showed **6**
worktree-only lines and `research/EXPERIMENTS.md` showed **1**, and BOTH WERE STALE, NOT NEW.
`arms.py`'s worktree copy has `C_INFLIGHT_DEFAULT = 4` where origin has `8` with its D128 note, and it
LACKS origin's D131 piece-serialisation block entirely; its mtime is 2026-11-18 17:11. The
`EXPERIMENTS.md` line was an OLD version of a `StudySH-EP` row, and `StudySH-EP` is on origin in SEVEN
rows across 284 files with all four `sh_ep_*.py` scripts committed, so nothing was at risk.
*** SO USE THREE CHECKS TOGETHER, NOT THE COUNT ALONE: *** (1) is anything RUNNING (an interpreter
under the repo or a scratchpad); (2) MTIME - a copy hours or days old is stale, not mid-edit; (3) READ
THE DIFF AND ASK WHICH SIDE IS NEWER - if the worktree lacks content origin has, or its lines are
superseded versions of origin's, it is OLDER and safe to overwrite. **AND FOR ANY ROW OR SYMBOL THAT
LOOKS LIKE LOST WORK, GREP ORIGIN FOR IT BY NAME BEFORE RESCUING IT**: both of today's candidates were
already committed, and 'rescuing' them would have reverted newer work.
`git show origin/main:<f> > /tmp/o; diff /tmp/o <f> | grep -c '^>'` counts WORKTREE-ONLY lines, the only
content a commit built from origin could destroy. Measured:
  `results/INDEX.md`     worktree-only **0**   -> PURELY STALE-OLDER, NOTHING TO LOSE, SAFE
  `arms.py`              worktree-only **2**   -> unique content, DO NOT TOUCH
  `coordinator.py`       worktree-only **9**   -> unique content, DO NOT TOUCH
  `v5/cf_objective.py`   worktree-only **150** -> unique content, DO NOT TOUCH
**SO THE INDEX ROW "BLOCKED BY CONTENTION" ALL NIGHT WAS NEVER BLOCKED** and is now committed. BUT NOTE
WHAT IS AND IS NOT ESTABLISHED: **unique content means UNSAFE TO OVERWRITE; it does NOT mean a session is
active.** Nothing has written those three files for 25 to 36 hours and nothing is running, so they are
either DELIBERATELY HELD code (the D214 `run_live2_real.py` wiring was exactly that, deliberately not on
origin, and deleting its tree would have destroyed the only copy) or an ABANDONED WIP. **WHICH ONE IS A
USER QUESTION AND IT BLOCKS ITEM 3**, which needs `coordinator.py`. Do not resolve it by guessing.
*** AND A FORMAT TRAP IN `results/INDEX.md` ITSELF: ITS ROWS ARE NOT ALL THE SAME WIDTH. *** Headers
declare 7 columns (8 pipes), but the RECENT rows in the tail use **7 pipes / 6 columns**, dropping the
trailing "old name". My first attempt at this row asserted the wrong width and the assert CAUGHT IT
before anything was written. **Count pipe CHARACTERS (`tr -cd '|' | wc -c`) against THE ADJACENT ROW, not
against a header or a `split()` length** - two counting methods disagreed here and that disagreement was
the real defect.

*** SUPERSEDED BLOCK, KEPT FOR THE TRAIL. DO NOT ACT ON THE TEST IT PRESCRIBES. USE THE
"WORKTREE-ONLY LINES" TEST ABOVE INSTEAD. *** What it gets RIGHT: `git diff --stat origin/main` in a
stale worktree really does report staleness as deletion, and `git diff HEAD` really does detect
uncommitted working-tree edits. **WHAT IT GETS WRONG IS THE INFERENCE IT LICENSES.** It concludes
"anything it prints is an UNCOMMITTED WORKING-TREE EDIT" and then treats that as "another session is
working, so do not touch". MEASURED ON 2026-11-24, THAT INFERENCE IS FALSE THREE WAYS: `git diff HEAD`
flagged `results/INDEX.md`, which held **ZERO** lines origin lacked and was simply stale-older, so the
INDEX row it blocked was never blocked at all; it flagged files last written **25 to 36 hours** earlier
with **no process running**, so "is an edit" does not imply "is active"; and it cannot tell
HELD-DELIBERATELY from ABANDONED, which is the distinction that actually decides what to do.
*** AN UNCOMMITTED EDIT IS A FACT ABOUT THE FILE. ACTIVITY AND SAFETY ARE SEPARATE QUESTIONS AND NEED
THEIR OWN EVIDENCE: mtime, a process census, and the worktree-only line count. ***

*** AND THE "HELD OR ABANDONED?" QUESTION IS NOW CHARACTERISED, 2026-11-24 00:20 PST. ANSWER: NEITHER.
ALL THREE ARE STALE OLDER SNAPSHOTS, AND NO UNIQUE *CODE* IS AT RISK. *** I read the worktree-only lines
instead of leaving the blocker vague:
- `arms.py`, 2 lines: BOTH ARE COMMENTED OUT - `# from arms_v6cf import V6CF_ARMS` and
  `# ARMS.update(V6CF_ARMS)`. Dead text, and a PRE-v6cf-registration state of the file.
- `coordinator.py`, 9 lines: fragments of `_device_answer` referencing
  **`requested_representation`**, which is the **PRE-HIT-7 FORM**; hit 7 (`c511050`) replaced that path
  with `RecallAction.window_s` read in `cstate.tokens_for_representation`. Definitively older.
- `v5/cf_objective.py`, 150 lines: **ZERO symbols origin lacks** - a grep for `def `/`class `/CONST
  among the worktree-only lines returns NOTHING, and every function named in them
  (`attainment_delta`, `attainment_margin`, `device_only_value`, `lex_better`, `option_value`) is
  ALREADY ON ORIGIN. The lines are REWORDED DOCSTRING AND COMMENT PROSE; origin's copy is LONGER (911
  lines against 640).
*** SO ITEM 3 IS NOT BLOCKED BY HELD CODE. *** The three files are superseded snapshots, origin is ahead
of them on every one, and nothing of substance would be lost. **THE LIMIT OF THIS CHECK, STATED:** I
verified that no NEW SYMBOL is defined and that the sampled unique lines are prose or older variants; I
did NOT line-by-line audit all 150. Combined with origin being longer on all three, the pre-hit-7 form in
`coordinator.py`, and nothing having written them for 25 to 36 hours with no process running, the reading
is consistent and strong but it is a CHARACTERISATION, not an exhaustive audit. **A session that wants to
land item 3 should still build from ORIGIN's content (as every commit tonight did) rather than from the
worktree copy, which is the practice that made this question moot for every file I committed.**


*** HOW TO CHECK CONCURRENCY CORRECTLY (the shared worktree lies): ***
`/tmp/claude-1001/mapwt` is HUNDREDS of commits behind origin (1,500 earlier tonight, 670 later), so
`git status` there reports STALENESS AS MODIFICATION and shows committed files as `??` untracked. *** THE TEST THIS FILE PREVIOUSLY PRESCRIBED IS ALSO WRONG, AND FOR THE SAME REASON IT WARNS ABOUT.
`git diff --stat origin/main -- <path>` IN A STALE WORKTREE REPORTS STALENESS AS DELETION: run against
`experiments/` it prints `124 files changed, 238 insertions, 33,648 DELETIONS`, which is 680 commits of
origin's own additions, NOT anyone's edits. A real edit and a missing file are indistinguishable in it.
*** THE TEST THAT ACTUALLY WORKS IS AGAINST THE WORKTREE'S OWN HEAD, NOT ORIGIN: ***
`git -C /tmp/claude-1001/mapwt diff --stat HEAD -- experiments/` plus `git status --porcelain -- <path>`.
Anything it prints is an UNCOMMITTED WORKING-TREE EDIT, because staleness cannot appear in a diff against
one's own HEAD. As of 22:31 that test CONFIRMS the conclusion the broken test had reached by luck:
`M arms.py`, `M coordinator.py` (+483), `M v5/cf_objective.py` (+123), and five more under
`experiments/`, 1,482 insertions in all. **LIVE UNCOMMITTED EDITS TO RUN-PATH FILES. Another session is
mid-work on them.** **A RUN-PATH FREEZE IS ALSO IN FORCE until the ladder completes**,
so TOUCH NO RUN-PATH FILE for either reason.

*** WHAT IS ALREADY SCORED. DO NOT RE-SCORE. ***

*** READ THIS BEFORE SCORING RUNG 4 ANYTHING. THE SCORER IMPLEMENTS RUNG 3's CHECK 1, NOT RUNG 4's, AND
I GOT THIS WRONG FOR FOUR SEEDS BEFORE THE H100 CAUGHT IT BY COMPARING MY OWN STATEMENTS. ***
The FROZEN `results/orchestration/live2/ladder_final/StudyLADDER_FINAL_prereg.json` says, VERBATIM:
  `THE_BARS/covex-v6-fair-final/check_1_alert`: "mean per-episode alert attainment STRICTLY ABOVE
     base's at that seed (s4 > 0.44249, s5 > 0.396211, s6 > 0.465479, s7 > 0.553811)"
  `THE_BARS/covex-v6-final/check_1_alert`:      "mean per-episode alert attainment STRICTLY ABOVE
     **covex-v6-fair-final's** at that seed"
**TWO RUNGS, TWO REFERENCE ARMS.** `d179_rung2_verdict.py` is named for the rung it was written for: its
check 1 is `delta_shares_minus_base` and its own label says "AT LEAST THE BASE'S", which is RUNG 3's
bar. **RUN IT FOR RUNG 4 AND ITS `check_1_alert.pass` IS THE WRONG CHECK.** It also says "at least"
where the prereg says "STRICTLY ABOVE" (immaterial on every cell so far, since rung 3's margins are
+0.216424 and +0.166322, but it would bite at exactly zero delta).
**HOW TO SCORE RUNG 4's CHECK 1 CORRECTLY, from the SAME scorer output, no re-run needed:** read
`per_seed[0].check_1_alert.COMMITTED_RULE_PRIMARY.mean_per_episode_attainment` and compare `shares`
against `rung2_committed` (which IS fair-final when you pass `--rung2-arm covex-v6-fair-final`), strictly
greater. **IGNORE that block's own `pass` field for rung 4.**
*** WHY IT STAYED INVISIBLE, which is the lesson: shares comfortably exceeds BASE at every seed, so the
WRONG BAR PASSED EVERYWHERE. A wrong check that always passes is harder to see than one that always
fails. *** Corrected across the three verdicts at `5a861434`.

*** RUNG 4 IS NOW COMPLETE ON ALL FOUR SEEDS, AND IT PASSES ALL THREE CHECKS AT ONE SEED OF FOUR. ***
| seed | check 1 (vs fair-final, STRICT) | check 2 (retention, bar 0.90) | check 3 | verdict |
|---|---|---|---|---|
| s4 | PASS +0.004066 (qualified) | PASS 0.945 | PASS | ALL PASS |
| s5 | PASS **+0.000294, A HAIR** | **FAIL 0.851064** | PASS | fail |
| s6 | PASS +0.006431 | **FAIL 0.871429** | PASS | fail |
| s7 | **FAIL -0.019534** | **FAIL 0.892307** | PASS | fail, TWO OF THREE |
s7 verdict `0e7ab17d`; check-1 correction `5a861434`. **s7's check-2 threshold was PRE-COMPUTED AND
PUBLISHED AS 78 OF 105 BEFORE THE CELL EXISTED, with 77 failing at 0.8923; the cell came in at 77 and the
scorer returned 0.892307.** Second seed where the pre-computation held exactly (s6's 104 was the first),
which is what makes "the bar did not move toward the result" checkable rather than asserted.
**AND AT s7 THERE IS NO TRADE AT ALL:** at s4 to s6 rung 4 was level or slightly up on alerts while
losing robot answers, so "a trade" was fair. At s7 it is DOWN ON BOTH, alert -0.019534 against the
comparator AND dashcam 265 on-time answers lower AND 7 robot answers lost. **The trade framing holds for
s4 to s6 and MUST NOT be extended to s7.** The H100 found this; it is the sharpest thing about s7.
**SO THE LINE BELOW SAYING "its checks 1 and 3 pass everywhere" IS SUPERSEDED: check 1 FAILS at s7.**

*** CLOSED 2026-11-24 01:55 PST: RUNG 3 AT s7 IS SCORED, THE LADDER IS COMPLETE, AND THE WHOLE
CLAUDE.md CLOSEOUT IS DONE. NOTHING IN THIS SECTION IS OUTSTANDING. DO NOT RE-SCORE AND DO NOT WAIT. ***
  `covex-v6-state-final` s7 landed and was scored: **RUNG 3 PASSES ALL THREE CHECKS AT s7**, check 1
  +0.094501 (0.648312 against base's bar 0.553811), check 2 **RETENTION EXACTLY 1.000000** (84 against
  state-final's 84, base 19), check 3 per-device minimum 0.991667. Positive control PASS 2 of 2 EXACT.
  *** THE CONSTRUCTED BOUND BELOW WAS BORNE OUT AND ITS ESCALATE CONDITION DID NOT FIRE. *** It said
  check 2 cannot fail unless state-final's on-time X exceeded 91, and that X > 91 would mean state-final
  served over-limit questions, contradicting D170, and must be ESCALATED rather than silently rescored.
  **MEASURED X = 84, so 84 <= 91 and no escalation was needed.** Retention came in at 1.000000 against
  the bound's predicted 0.955882 at X = 87, i.e. BETTER than the worst admissible case, as expected
  since retention rises as X falls.
  **CLOSEOUT, ALL FOUR CLAUDE.md AFTER-ANY-TASK STEPS NOW COMPLETE:** the complete-ladder record is
  `frozen_test/d208_LADDER_FINAL_COMPLETE.json` (`8feed0fe`); `research/EXPERIMENTS.md`'s
  StudyLADDER-FINAL row carries the verdict, status, consistency_check and mechanism_verification;
  `results/INDEX.md` line 1122 carries the complete-ladder row; and `research/STATUS.md` now opens with a
  2026-11-24 section (`5cf93024`). **SO THE 'STILL OWED: the results/INDEX.md row' ITEM FURTHER DOWN THIS
  FILE IS STALE - THAT ROW EXISTS.**
  **AND THE RUN-PATH FREEZE'S LADDER REASON HAS LAPSED**, because the ladder is complete.
  *** RECONCILED 2026-11-24: THE OTHER REASON HAS LAPSED TOO, AND THIS FILE'S OWN CORRECTED CONCURRENCY
  SECTION ALREADY CONTAINED THE REFUTATION FOR THESE EXACT FILES. THE "1,482 INSERTIONS" ARE NOT LIVE
  EDITS, THEY ARE A STALE TREE. *** Measured on `/tmp/claude-1001/mapwt`:
    the worktree is **815 COMMITS BEHIND** origin, and ALL 8 dirty tracked files under `experiments/` have
    mtimes of **2026-11-22** (one 11-23 16:12). Nothing running: ZERO live2 python under the repo or any
    scratchpad, loadavg 0.12.
    `v5/cf_objective.py`, the largest diff: **origin 911 lines, worktree 640** - **421 ORIGIN-ONLY** lines
    against 150 worktree-only, so the worktree is **271 LINES SHORTER**. A sample of its "worktree-only"
    lines is explanatory COMMENT PROSE appearing in **0 files** on origin: text origin REWROTE.
    `coordinator.py` 10 worktree-only, `arms.py` 2, and **FIVE OF THE EIGHT have ZERO.**
  *** "INSERTIONS AGAINST ITS OWN HEAD" IS THE WRONG MEASURE, and it is the same coarse test this file
  corrects three times above. *** A tree 815 commits behind differs from its own HEAD for reasons that have
  nothing to do with anyone editing now, and a line count cannot tell NEW CONTENT from AN OLDER VERSION OF
  A LINE SINCE REWRITTEN. The corrected section's own figures already include `640 vs 911` for this file.
  *** WHAT TO DO INSTEAD OF A BLANKET FREEZE, because this is what actually protects: *** (1) BUILD EVERY
  COMMIT FROM ORIGIN'S CONTENT, never from either stale worktree - unchanged, and every commit has;
  (2) CENSUS THE BOX by what processes ARE before any cell; (3) for a live-path file, PROVE DECISION
  NEUTRALITY on a dry A/B from ONE literal sha rather than asserting it, because a COMMENT-ONLY edit here
  was measured to move an arm by 85 decisions. **THAT IS WHAT `fbd2f64b` DID for `cstate.py`'s doc lines:
  A = B = `57bed6ace2eb07d1` / 14,509, which is also the posted committed value.** The blanket wording
  blocked that work for hours and would have blocked it again.
  NOTE THERE ARE **TWO** STALE TREES AT DIFFERENT DISTANCES: `/tmp/claude-1001/mapwt` at 815 commits and
  `/home/pragya/Desktop/FM-switching` at about 1,678. Neither is a source of content and neither is
  evidence of an absence.

*** THE ONLY OUTSTANDING VERDICT IS RUNG 3 AT s7, AND AS OF 23:11 PST IT IS NOT YET SCORABLE. *** [SUPERSEDED, KEPT FOR THE TRAIL]

*** AND IT IS ALREADY DETERMINED FROM COMMITTED DATA. RUNG 3 PASSES ALL THREE CHECKS AT s7 WHATEVER
`covex-v6-state-final` s7 TURNS OUT TO CONTAIN. Derived 23:22 PST; positive control PASS 2 of 2 exact. ***
REGISTER: this is a CONSTRUCTED BOUND, not an observed verdict. The formal scoring still runs when the
cell lands; this tells you WHAT TO EXPECT and makes a surprise detectable.
- **CHECK 1 and CHECK 3 DO NOT DEPEND ON THE MISSING CELL AT ALL** and are read straight off the
  committed rung-4 s7 scorer run, where fair-final is the `rung2_committed` column:
  check 1 per-episode attainment **0.648312 against base's bar 0.553811 -> PASS** (rung 3's bar IS the
  base-referenced one); check 3 per-device minimum **0.991667 against 0.90 -> PASS**.
- **CHECK 2 CANNOT FAIL.** The bar is `base + 0.90 x (state-final's on-time - base)` with base 19 and
  fair-final 84 of a 105 pool, so fair-final passes **iff state-final's on-time X <= 91.2222, i.e.
  X <= 91**. *** THE SERVABLE CEILING AT s7 IS 87 *** (105 minus the 18 D176 over-32k questions, verified
  as the identical set from fair-final's own outcomes), and **87 <= 91**, so no admissible value of X can
  fail the check. Retention at X = 87 is **0.955882**, and retention RISES as X falls.
- **A SECOND, INDEPENDENT ARGUMENT TO THE SAME PLACE:** state-final's robot on-time is BELOW
  fair-final's at every scored seed (119 vs 126 at s4, 112 vs 121 at s5, 106 vs 111 at s6), so X is
  expected at or under 84, far below 91.
- **THE ONE ASSUMPTION, STATED RATHER THAN BURIED:** the 87 ceiling assumes `covex-v6-state-final` also
  declines the 18 over-32k questions as INFEASIBLE per D170, which is what `covex-v6-fair-final` is
  VERIFIED to do. It is one of our arms and carries the same rule, but **I have not observed its s7 cell,
  so this is an inference.** For X to fail the check it would have to reach 92 of 105, meaning it served
  at least 5 over-limit questions AND nearly every other one, while running BELOW fair-final at all
  three other seeds. **IF THE LANDED CELL SHOWS X > 91, DO NOT SILENTLY RESCORE: that would mean
  state-final served over-limit questions, which contradicts D170, and it is an ESCALATE-AND-REPORT.**

*** SO THE LADDER'S CONCLUSION IS ALREADY FIXED, AND THIS IS THE HEADLINE FOR THE USER: ***
**RUNG 3 (`covex-v6-fair-final`) PASSES ALL THREE CHECKS AT ALL FOUR SEEDS**, exceeding its comparator's
gain rather than merely retaining 0.90 of it at s5 (1.1059) and s6 (1.0769). **RUNG 4 (`covex-v6-final`)
PASSES ALL THREE AT ONE SEED OF FOUR**, failing check 2 at s5, s6 and s7 and check 1 at s7 as well. The
entire difference between the rungs is ROBOT RETENTION, and its cause is diagnosed and verified at code
level. **RUNG 3 IS THE ROBUST POLICY AND RUNG 4 REGRESSES IT.**

`covex-v6-state-final` s7 is **0 files on origin**; the other three s7 cells are present (`covex-v6-final`
17, `covex-v6-fair-final` 17, `hybrid-F-lhreq-noc3` 16). It was due about 23:25. **When it lands:**
`d179_rung2_verdict.py --runs <dir> --seeds 7 --shares-arm covex-v6-fair-final --base-arm
hybrid-F-lhreq-noc3 --rung2-arm covex-v6-state-final`, confirm `positive control: PASS` FIRST, and for
RUNG 3 the scorer's `check_1_alert.pass` IS the right check (base-referenced, bar s7 > 0.553811).
Rung 3 so far: ALL THREE PASS at s4, s5 (retention 1.1059) and s6 (1.0769), EXCEEDING its comparator's
gain rather than merely retaining 0.90 of it.

| arm | s4 | s5 | s6 | s7 |
|---|---|---|---|---|
| rung 3 `covex-v6-fair-final` | ALL THREE PASS | **ALL THREE PASS**, retention 1.1059 (`3c644d81`) | **ALL THREE PASS**, retention 1.0769 (`f476ee96`) | **ALL THREE PASS**, retention EXACTLY 1.000000 (`8feed0fe`) |
| rung 4 `covex-v6-final` | ALL THREE PASS | **check 2 FAIL 0.851** (`8e05580e`) | **check 2 FAIL 0.871** (`c7c92285`) | **CHECKS 1 AND 2 BOTH FAIL** (`0e7ab17d`, `5a861434`) |

**RUNG 4 PASSES CHECK 2 AT ONE SEED OF THREE, ON ROBOT RETENTION ALONE**; its checks 1 and 3 pass
everywhere and its alert attainment is slightly ABOVE rung 3's at both failing seeds, so it buys a small
alert gain with a larger robot loss. **RUNG 3 PASSES EVERYTHING EVERYWHERE SCORED.** Rung 2 standing
alone is WORSE THAN BASE on alerts (0.2407 vs 0.3962 at s5) and would fail check 1.
**THE CAUSE IS DIAGNOSED AND VERIFIED AT CODE LEVEL** (`reports/study_rung4_s5_failure.md`, `7ab3b070`):
`arms_v6cfr3.py` calls `CC.predict(cf.model, int(u_request), 0, 0, 0)` while `v5/cf_cost.py:149` is
`predict(model, tokens, cached_tokens=0, overlap_ft=0, overlap_decode=0, link_s=...)` computing
`ft = intercept + per_uncached*unc + per_overlap*overlap_ft`, so **D162's queueing term is IDENTICALLY
ZERO on a gate reached only when other requests are queued.** 14 losses, 0 gains, residual ZERO at s5;
s4 had 2 gains and passed, so **s4's pass is the luckier draw of the same losing trade.**

*** STATE AS OF 2026-11-23 22:55 PST, FROM A PROCESS CENSUS, SO NO RESUME RE-DERIVES IT. ***
- *** E1's 52-CELL SWEEP IS FINISHED AND ITS RESULT IS NOW COMMITTED (this commit). *** It wrote
  `out/digests_e1.json` at 22:46:26 and EXITED; pid 304781 is GONE, which is COMPLETION, not a crash.
  **VERDICT: precheck_passed true, n_arms 24, n_identical 24, n_moved 0, moved_arms [], setwise
  decisions moved 0.** So E1's NON-INTERFERENCE gate PASSES and the ESCALATE-AND-STOP condition did not
  fire. **THE SWEEP'S OWN FILE LABELS WHAT IT CANNOT SHOW, and that label must travel with it:** "how
  many rung-4 decisions the scrape moves: a dry cell builds no backend, so the mechanism is ABSENT and a
  zero here is UNEXERCISED, not a measurement". `covex-v6-final` IS NOT ONE OF THE 24 ARMS; this proves
  only that the scrape disturbs nothing else. CAVEAT RECORDED, NOT BURIED: `n_cells_not_alone = 24`, all
  24 pairs ran with foreign load at loadavg 1.15 to 2.22. A and B agreeing bit-exactly under varying
  load is direct evidence of determinism, and tonight a digest reproduced bit-exactly at loadavg 34.97,
  so the not-alone condition weakens the ALONE claim but not the identity conclusion.
- **THE DEVICE_ANSWERS DRIVER IS WAITING, NOT HUNG, AND THE HANG RULE IN THIS FILE WOULD HAVE
  MISDIAGNOSED IT.** pid 346850 shows `00:00:00` CPU and `ps --ppid` EMPTY after 11 minutes, which this
  file's corrected rule calls a hang. **IT IS NOT: a foreign cell IS running** (`run_live2_real.py
  --arm covex-v6-cf-pd-c5attr`, pid 351013, whose parent chain ends at init, so it is NOT a DA
  descendant), and the DA driver carries `--wait-s 90` and an alone-wait. *** SO THE DISCRIMINATOR NEEDS
  A THIRD STATE, and this is its final form: 0 CPU + no descendants + NOTHING ELSE RUNNING = HANG;
  0 CPU + a live descendant = WORKING ORCHESTRATOR; 0 CPU + no descendants + A FOREIGN CELL RUNNING =
  CORRECTLY WAITING ON THE ALONE RULE. *** Check descendants by walking the parent chain to init, not
  by `ps --ppid` alone, because a cell launched through a shell is not a direct child.
- Ladder at **10 of 12**: `covex-v6-fair-final` s7 IS on origin (17 files); `covex-v6-final` s7 and
  `covex-v6-state-final` s7 are ABSENT. Rung 4 s7 started 22:41:30; state-final s7 due about 23:25.
- Watchdog at **RESTART 5/12**. The budget is finite: 7 restarts left, so do not spend one re-deriving
  what is written above.

*** PRE-COMPUTED FOR s7 SO THE NEXT RESUME READS THE CELL IMMEDIATELY, NOT AFTER AN HOUR OF SETUP: ***
- **RUNG 4's s7 CHECK-2 THRESHOLD IS 78 OF 105, NOT 77.5.** base 19, fair-final 84, gain 65;
  `(shares - 19)/65 >= 0.90` needs `shares >= 77.5`, and answers are integers, so **78 PASSES (0.9077)
  AND 77 FAILS (0.8923)**. Rung 4 may therefore lose AT MOST 6 robot answers against rung 3's 84. **IT
  LOST 14 AT s5 AND 9 AT s6.** That is context, NOT a prediction: s7's mix differs sharply (2,445 robot
  requests against 681 at s6) and base is unusually strong on alerts here at pooled 0.638.
- **THE s7 SERVABLE POOL IS 87, NOT 105, AND THIS IS VERIFIED, NOT PRESUMED.** fair-final s7 has 18
  robot rows with NO `t_delivered`, and those 18 opportunity ids are the IDENTICAL SET to D176's 18
  over-32k questions at seed 7 (intersection 18, zero either way, checked against
  `frozen_test/d170_overlimit.json`). Declining them is D170 behaviour, not a loss. So fair-final is
  **84 of 105 = 0.800 OFFERED but 84 of 87 = 0.966 SERVABLE**. *** REPORT BOTH AND NAME THE DENOMINATOR
  AT THE POINT OF USE; THE PRE-REGISTERED BAR STAYS ON 105, because switching it to 87 would be moving
  a bar after the numbers exist. ***
- `dashcam_all_meet` is PER DEVICE against the 0.25 attainment target (`scorer/score.py:713-719`,
  `meets = eligible and frac >= p_dash - 1e-12`, all-of over ELIGIBLE devices), NOT pooled. So
  state-final s6 reading TRUE at a pooled 0.3161 is CORRECT. "Meets the target" and "is good" are
  different statements. **And the dashcam denominator key is `n_instants`, NOT `n`:** summing `n` gives
  a ZERO denominator and a silent 0.0 fraction.

*** STATE AS OF 2026-11-24 07:00Z = 2026-11-23 23:00 PST. WATCHDOG AT RESTART 6/12, SO SIX LEFT. ***
*** NOTHING IS SCORABLE RIGHT NOW. I CHECKED; DO NOT SPEND A RESTART RE-CHECKING THE SAME THING. ***
s7 on origin: `hybrid-F-lhreq-noc3` 16 files, `covex-v6-fair-final` 17 files, **`covex-v6-final` ZERO,
`covex-v6-state-final` ZERO.** So RUNG 4 s7 cannot be scored because ITS OWN CELL IS ABSENT (not because
of its comparator, which is present), and RUNG 3 s7 cannot be scored because state-final s7 is absent.
Rung 4 s7 started 22:41:30 and state-final s7 was due about 23:25, so both are still in flight. The
run-path freeze still holds: `git diff --stat HEAD -- experiments/` in the stale worktree shows 8 files
and 1,482 insertions uncommitted, including `coordinator.py` and `v5/cf_objective.py`.

*** CORRECTION THAT WOULD OTHERWISE COST A WHOLE RESTART: OVERNIGHT STEP 2 (E1) CANNOT BE DONE AT ALL,
AND THE LIST BELOW STILL TELLS YOU TO DO IT. ***
**THE LANDED E1 SCRAPE IS AN ABSENT LINK: IT IS A SCRAPER THAT NOTHING CALLS.** Verified on origin with
full untruncated output, by two sessions independently:
- `scrape_metrics` has **EXACTLY TWO OCCURRENCES IN THE WHOLE TREE** - its own definition at
  `asyncbackend.py:175` and a PROSE COMMENT at `n5_queued_by_class_census.py:291`. **ZERO CALLERS.**
- `AsyncBackend.metrics()` (`:190-210`) returns wire statistics only and **NO `vllm:` KEY**, and does
  NOT call `scrape_metrics`. `coordinator.py:489` is the only writer of `st.metrics`.
- **NOTHING IN PRODUCTION SETS `metrics_scrape`** (only asyncbackend's own `getattr` defaults at `:178`
  and `:185`); `run_live2_real.py`, `procsplit.py`, `coordinator.py` and `cstate.py` never mention it.
**SO FLIPPING `METRICS_SCRAPE_DEFAULT` WOULD CHANGE NOTHING, AND A STEP 2b DIFF WOULD SHOW IDENTICAL
LOGS - WHICH CLAUDE.md CALLS AN ABSENT LINK, NEVER A NEGATIVE.** Do NOT run that sweep; one session was
authorised to and correctly refused on this ground. **The committed `digests_e1.json` 24-of-24 identical
result is a valid NON-INTERFERENCE result and PROOF OF THE WRONG THING**: `covex-v6-final` is not among
its 24 arms, and the code it compares is unreachable, so an empty commit would produce the same table. It
shows E1 is INERT, not that E1 is safely default-off. Corrections are committed at `77b9f702`,
`20ac7c63` and `dd35ca54`.
**AND THIS CHANGES THE RUNG-4 STORY, so do not repeat the older sentence.** No `vllm:` key means
`gpu_kv_fraction` 0.0 and `pd_kv_bound_by_engine_metric` ABSENT, so THE ENGINE CHANNEL BINDS ZERO
DECISIONS EVERYWHERE. *** THE REST OF THIS CHAIN IS REFUTED AND MUST NOT BE REPEATED. CORRECTED
2026-11-24 FROM THE COMMITTED LADDER CELLS, committed at `c701f83a`; see the OPEN section below for
the per-seed numbers. *** `free_kv` IS **NOT** PINNED AT THE FULL POOL: in all four rung-4 ladder
cells it VARIES (10,115 to 62,944) and `pd_kv_bound_by_belief` EQUALS `pd_decisions`, so THE BELIEF
CHANNEL SETS IT ON 100 PERCENT OF DECISIONS. The `62944`-constant reading came from ONE fake-server
cell of 29 decisions; variation is a property of a cell's ROSTER AND DURATION, not of dry versus
live. AND PROTECT-AND-DEFER IS NOT "NEVER REACHABLE": at s4 and s7 it CROSSED ITS BAR and was
blocked for want of a channel: `pd_harm_over_bar` = 2 and the
`pd_gate_wanted_to_act_but_a_request_has_no_slice_channel` counter = 2. That is Rule 2
**UNEXPRESSIBLE**, not unexercised. s5 and s6 ARE genuinely unexercised (nothing crossed the bar). Three independent
agreements: a live fake-server cell (29 decisions, 0 `PROTECT_AND_DEFER`), the s5 diagnosis (299
decisions, same two gates, 0 `PROTECT_AND_DEFER`), and a dry digest collision
(`covex-v6-cf-pd-c5attr` = `covex-v6-state-uo` at `9a4be873eb3c5fba` / 14,218). **The defensible
sentence, CORRECTED 2026-11-24, is "rung 4 adds one mechanism that FIRED AND HAD NO CHANNEL TO ACT
THROUGH at two seeds of four and was unexercised at the other two, and one that fires and loses", NOT
"one that does not help".** Rule 2 class is UNEXERCISED with a DEFECT as the cause, so the remedy is a
FIX, not a finding, and **"protect-and-defer does not help at 1x" IS NOT SUPPORTED and must not be
written.** Whether rung 4 would beat rung 3 with the metric plumbed is UNKNOWN AND UNTESTED.
**THE WIRING FIX IS A PENDING USER RULING, NOT YOURS**: it changes landed behaviour, D209 makes an
implementation correction a supersede-plus-rerun which would invalidate committed cells, and
`run_live2_real.py` is under the freeze. `d213_patch_asyncbackend.py` on origin now carries a REFUSAL
HEADER because applying it creates a duplicate scrape; do not apply it.

*** THE NEXT STEP, WHICHEVER APPLIES FIRST: ***

*** 0. THE LADDER IS COMPLETE AND FULLY SCORED. THERE IS NOTHING LEFT SCORABLE. STATE AS OF
2026-11-23 23:35 PST. *** All 12 cells on one experiments/ tree. Complete result committed at
`8feed0fe` as `d208_LADDER_FINAL_COMPLETE.json`:
  **RUNG 3 `covex-v6-fair-final`: ALL THREE CHECKS PASS AT ALL FOUR SEEDS. 4 of 4.**
  **RUNG 4 `covex-v6-final`: ALL THREE PASS AT ONE SEED OF FOUR (s4 only).** check 2 fails at s5
  (0.851064), s6 (0.871429) and s7 (0.892307); **check 1 ALSO fails at s7 (-0.019534).**
Rung 3 s7 is now **OBSERVED, not the constructed bound an earlier resume recorded**: check 1 +0.094501
(0.648312 against base's 0.553811), check 2 **retention EXACTLY 1.000000** (state-final 84, fair-final
84, base 19, pool 105), check 3 min 0.991667, positive control 2 of 2 exact.
**THE BOUND'S ONE OPEN ASSUMPTION IS RETIRED:** it assumed state-final would also decline the
over-limit 18 under D170 and needed state-final <= 91; observed is **84, inside the 87 servable
ceiling**, so the assumption held and the escalate-and-report branch did not fire.
*** TWO SCORING CORRECTIONS THAT MUST NOT BE RE-INTRODUCED: ***
  (a) **RUNG 4's CHECK 1 IS "STRICTLY ABOVE covex-v6-fair-final's", NOT ABOVE BASE'S.** Frozen prereg
  `THE_BARS/covex-v6-final/check_1_alert`. `d179_rung2_verdict.py`'s `check_1` is
  `delta_shares_minus_base` and is **RUNG 3's bar**; the scorer is NAMED for the rung it was written
  for. Scoring rung 4 with it passed check 1 at all four seeds, which was WRONG and is withdrawn at
  `5a861434`. Read rung 4's check 1 off the SAME run's `rung2_committed` column instead. A wrong check
  that always passes is harder to see than one that always fails.
  (b) The scorer says "at least" where the prereg says "STRICTLY ABOVE". Immaterial on every cell so
  far (rung 3's margins are +0.216424 and +0.166322) but it would bite at exactly zero delta.
*** AND THE HEADLINE CAVEAT, which belongs with every citation of the above: *** these four seeds do NOT
test the rung-4 DESIGN. **CORRECTED 2026-11-24 (`c701f83a`): protect-and-defer is UNEXPRESSIBLE at
s4 and s7 and UNEXERCISED at s5 and s6, NOT "unreachable in every cell", and `free_kv` is NOT pinned
at the whole pool - it varies 10,115 to 62,944 with the BELIEF channel setting it on every decision.**
What IS true: `metrics()` does not merge `scrape_metrics`, which has ZERO callers, so the ENGINE
channel binds zero decisions; at s4 and s7 the mechanism crossed its bar and had no channel to act
through, and THE GATE'S OWN COUNTER NAMES DEVICE_ANSWERS as the candidate that would apply; and the
deferral predictor is called with the queueing term HARD ZERO. This is evidence about the
rung-4 IMPLEMENTATION AS RUN. **Whether a fixed rung 4 would beat rung 3 is UNKNOWN AND UNTESTED.**

1. ~~`covex-v6-state-final` s6 -> score RUNG 3 at s6~~ **DONE at `f476ee96`: ALL THREE PASS, robot
   retention 1.076923, check 1 +0.166322, positive control 2 of 2 exact.** Rung 3 now passes everything
   at s4, s5 AND s6, and EXCEEDS its comparator's gain at both s5 (1.1059) and s6 (1.0769), not merely
   retaining 0.90 of it. **THE LADDER IS AT 9 OF 12 COMMITTED CELLS; s7 HAS NONE OF THE THREE FINAL
   ARMS** (only `hybrid-F-lhreq-noc3` s7 exists), so as of 22:31 THERE IS NOTHING LEFT TO SCORE.
2. s7 cells land -> score **rung 4 s7 as soon as `fair-final` s7 exists** (rung 4's comparator is
   fair-final, NOT state-final, so it does not wait for state-final s7), and rung 3 s7 once state-final
   s7 exists. Scoring recipe: extract the three cells from origin into a scratch `runs/` dir and run
   `d179_rung2_verdict.py --runs <dir> --seeds <n> --shares-arm <arm> --base-arm hybrid-F-lhreq-noc3
   --rung2-arm <comparator>`. **CONFIRM `positive control: PASS` EVERY TIME before reading a verdict.**
3. Nothing scorable -> do NOT invent work on run-path files. The handoff's five overnight steps below
   are owned by other sessions.

## *** D229 / D230 (8) APPLIED ON FLASH: `ops/STANDDOWN` INSTALLED, AND THE WATCHDOG'S DUPLICATE-SESSION GUARD HAS NEVER BEEN ABLE TO FIRE. ***

**Written by the watchdog-spawned session that D230 (8) rules should not exist.** It was started by
`ops/watchdog.sh` at 19:30:01Z as `RESTART 2/12` (1/12 was 19:20:01Z), carrying the stored prompt "read the
overnight handoff ... continue the next step". **It read D229 and D230 (8) on origin, found that it is the
second session named A6000, did no policy work, stood the watchdog down and reported.** That is what it was
doing, recorded as D230 (8) requires.

**`ops/STANDDOWN` written**, expiry `1795579200` (20:00 local, 2026-11-25T04:00Z), reason citing D229 and
D230 (8). **Verified by re-running the watchdog's own gate arithmetic against the file** rather than
assuming the format: the script reads line 1 with `tr -dc '0-9'`, compares `now < exp`, and would log
"STANDDOWN active for 508 more minutes, not starting Claude". It **self-expires**, so unattended
resilience returns on its own overnight, which is exactly D229's "the user re-enables it for unattended
periods" without needing anyone to remember. `ops/` is **not tracked by git**, so the flag is local and
this handoff entry is its only audit record.

**D229's "while the driver / run restarts stay" has NO flash counterpart, and that is a fact rather than a
liberty taken.** `ops/watchdog.sh` mentions "driver" **zero** times, contains no `python` or `run_live2`
invocation, and has exactly **one** `tmux new-session`. Its entire action is starting a Claude session. So
standing it down disables precisely what D229 names and nothing else; flash has no run driver to preserve,
because the H100 runs the cells.

*** THE FINDING, AND IT EXPLAINS THE WHOLE RESTART HISTORY: THE DUPLICATE-SESSION GUARD AT
`ops/watchdog.sh:95` CANNOT FIRE. *** It reads
`ps -C claude -o args= | grep -v grep | grep -q -- "-c -p"`, and its own comment (lines 88-93) records the
real hazard correctly: "guarding only on the tmux session NAME is not enough ... so the watchdog can start
a SECOND session onto the same repo and the same handoff file. That happened." **But the literal substring
`-c -p` never occurs in any claude command line on this box, including the watchdog's OWN spawn**, whose
argv is `claude -c --permission-mode auto -p '<prompt>'` - the `-c` and the `-p` are **separated by
`--permission-mode auto`**. Measured: `ps -C claude -o args= | grep -c -- "-c -p"` returns **0** against
**six** live claude processes (one watchdog spawn plus five interactive `--continue` / `--resume`).
**So the guard is blind both to interactive sessions, the hazard it was written for, AND to its own
spawns, the thing it was meant to deduplicate. It has always passed.** Only the heartbeat gate and
STANDDOWN have ever restrained this watchdog, which is why 20 restarts and 16 one-shot resumes happened and
why three sessions once started in twenty minutes.
**Same family as every other defect found today: a check that is sound in intent and pointed at the wrong
property**, and one that **advertises safety while providing none**. Note it was also written to avoid
`pgrep -f` self-matching, correctly - the author fixed the hazard they were looking at and introduced a
different one in the pattern. **Fixing it means matching the interpreter and the repo path, or
`--permission-mode`, not an adjacency of two flags.** Not fixed here: this session is standing down, not
editing live-path files, and the flag makes it moot until the user rules.

## *** HOW DEVICE_ANSWERS IS SWITCHED ON: A SEPARATE ARM NOW, FOLDED LATER. (user ruling, 2026-11-24, D231 (1) implementation) ***

**The ruling, and the reason it is the right shape.** `covex-v6-final-da` is created as a **separate arm** =
`covex-v6-final` (pass 1) + DEVICE_ANSWERS on, rule as D218 in D177 units. **This is race-free and that is
the point.** Under the alternative - switching it on inside `covex-v6-final` - cell (a), the pass-1 kv0.5r
s4 `_ms` cell, would be a pass-1 cell **only because its module loads before the commit lands**. A push a
minute earlier would have made (a) a different arm under the pass-1 name, with nothing in the cell's name
to say so. **Two cells differing by ARM cannot be confused by when a commit landed; two cells differing by
a commit's timing can.**
**The guard that makes it checkable rather than trusted:** the H100 asserts `device_answers_enabled` from
the switch state **the arm itself publishes** in each cell - **False for (a), True for (b)** - and **if (a)
reads True it is NOT scored against the pass-1 pre-registration and that is reported.** So the claim is
evidenced per cell, not inferred from a name or a push time.

**Order.** (a) `covex-v6-final` kv0.5r s4 `_ms` runs as planned at about 12:01 with DEVICE_ANSWERS **off**;
(b) `covex-v6-final-da` kv0.5r s4 `_ms` next; then `covex-v6-fair-final-ptg` 1x s4; rung-4 1x s5 to s7 wait
for the user.
**Proofs for (b), minimal:** non-counterfactual arms byte-identical; **`covex-v6-final` UNCHANGED, proved by
reproducing the pass-1 digest** (that is the half that protects (a)'s meaning); `-da` moves decisions. Plus
a one-line pre-registration amendment **before** the cell.

*** AND THE FOLD, WHICH IS THE PART THAT PROTECTS THE RECORD. *** After (b) is scored, and **only when no
rung-4 cell is starting**, DEVICE_ANSWERS is folded into `covex-v6-final` itself, because D221 makes it part
of rung 4 - **and the pass-1 behaviour is kept available as `covex-v6-final-p1`, so the committed pass-1
cells keep a name true to what they ran.** Byte-identity both ways: new `covex-v6-final` == `-da`, and
`covex-v6-final-p1` == the pass-1 digest. Arm-name mapping and the conformance matrix updated with it.
**That is the fix for a hazard this project has hit repeatedly from the other direction: a name whose
meaning changed under already-committed results.** `arm_names_v6.py`'s `V6_LADDER` still names rungs 2 to 4
by superseded names, which an independent verification flagged as a gate row; keeping `-p1` means the
rung-4 cells already on origin do not quietly become cells of a different arm.

**Scoring note for both 0.5x cells, to be recorded in each result:** the comparator
`covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` was **unscored at run time** -
`ScoringRefused` under the D226 guard at `MISSING = 1` (`r10175`), **with no rows at all** - so the 0.5x
verdicts are **final only once the Orin's outcome-keyed rescore lands.** Run the cells regardless; the cells
are the expensive part and the comparison is arithmetic afterwards. **Nobody should later read a missing
comparison as a failed one.**

## *** D231: THE RUNG-4 1x s4 RESULT, AND A BUILD MISS I SHOULD HAVE CAUGHT. (user, 2026-11-24, revisit later) ***

**The result.** `covex-v6-final` `_rerun` 1x s4: robot on time **127/132** against rung 3's 126 and base's
35, so retention **1.011** PASSES the 0.90 bar; single-shot **98.6 percent** PASSES; alert attainment is
still owed by flash. **22 live question deferrals fired**, against 0 in the dry proof, and **none would
miss at either the committed or the new safety factor** - which is what the refit was for: under the old
n=5 factor that column was identically false by an algebraic identity, and it now reports real exposure.

*** THE BUILD MISS, AND WHY IT IS THE PART TO LEARN FROM. DEVICE_ANSWERS WAS NOT BUILT INTO PASS 1, against
D221 and D228 (3), and the cell said so itself: THREE DECISIONS WANTED IT and were refused with the gate
message "not built here". *** The harm and trade code was on origin; **the action wiring was still under
`held/d218_device_answers/`**, so the switch had no reader on the live path. **Every surface sign said pass 1
was complete**: the pre-registration was committed before the cell, all three proofs passed, and the
proofs were run on a tree where DEVICE_ANSWERS *was* present - so the dry proof legitimately showed the
mechanism firing in both directions while the pushed code could not. **The pre-registration itself omitted
the item**, which is how a reader would have discovered it only from the gate string.
**THE RULE THE USER HAS ADDED, AND IT IS THE DURABLE FIX: every pre-registration lists EVERY item of the
prompt it implements, each one marked built or explicitly deferred.** An omission then shows up as a
missing line in a committed row rather than as a counter nobody reads. **This is the same family as the
commit that landed bookkeeping and dropped the mechanism: the paperwork and the capability have to be
checked against each other, in both directions.**

**What follows.** DEVICE_ANSWERS is switched on in `covex-v6-final` from the held implementation
`f097f5d3`, the pre-registration is amended **before** the cell, and the H100 runs
`covex-v6-final` kv0.5r s4 with it on, tagged **`_da_ms`**, as the next policy cell **after** the pass-1
`_ms` cell, which **runs as planned and is not held**. Same 0.5x bar. The per-type guard is built as
`covex-v6-fair-final-ptg` because D230 (2) measured **1.0355 percent** against its own 1 percent rule, and
runs at s4 after both rung-4 cells. **Rung-4 1x s5 to s7 wait for the user.** And flash must determine
whether `robot correct-by-deadline` at **0.628788**, identical across three arms with different on-time
counts, is a genuine tie or a stuck value - because half the 0.5x bar rests on it.

## *** D230 IS THE FREEZE-GATE RULING SET. EVERY ITEM IS MARKED FOR REVISIT. (user, 2026-11-24) ***

Recorded here because a session turnover must not lose it (D229's reason, applied on flash).
**Closed:** 10.1, 10.6 and 10.16 by D221 and D228. **10.11** flexible split set OFF on rungs 3 and 4,
byte-identical. **10.12** the D165 (A) lexicographic objective RULED OUT AS SUPERSEDED - D185's deficit
weights set cross-type priority and D177 makes the within-type accuracy gap constant, so it decides
nothing; spec v6 and `arm_names_v6.py`'s `missing` note are updated as comment/metadata only.
**10.14** counterfactual sync is covered by D226 (1), built OFF before the freeze; **an explicit
host-reload action is RULED OUT because the engine reloads natively and D211 signal (a) FAILED, so host
residency is unobservable per request** - the paper states host reload as native and unobserved.
**Measure-first, not build-first: 10.7.** The per-type guard is not built on argument. The fraction of
100 ms decision periods whose alert first-token lag exceeds 0.8 s is measured from committed rung-3 1x
cells s4 to s7, and **the 1 percent threshold is pre-declared**: at or below it, D178 (3) is amended to the
single 2.0 s guard as built and D166 (3)'s exit hysteresis is ruled out; above it, a labelled rung-3
variant is built and run at s4 first. **This is the right shape for a defect found by reading code: the
code says alerts cannot be protected inside their deadline, and the measurement says whether that ever
happens.**
**10.13 is deliberately undecided**, pending the rung-4 kv0.5r s4 result: if rung 4 beats rung 3 at 0.5x
without keep-ready set and admit-with-protected-victim, both are ruled out as a stated limitation.
**Operations.** The metrics scrape is **ON for every new cell** with `metrics_health` always recorded
(D230 (7)) - which **supersedes my `3b610470` default=False**, correctly: that commit fixed an
*undeclared* deployment default, and this is the user declaring it. The 1x rung-4 cell now running stays
unscraped; **rung-4 seeds 5 to 7 must scrape.** Only flash's main session may instruct the H100. The driver
records each run's unix `t0` (the D211 proxy this removes). The 31 stub cells are marked only and their
scores stand.

## *** NEVER `pkill -f` ON A SHARED BOX. A PATTERN SPECIFIC ENOUGH TO NAME YOUR OWN PROCESS IS SPECIFIC ENOUGH TO NAME A PEER'S, BECAUSE WAITING ON A SHARED FILENAME IS WHAT COORDINATION LOOKS LIKE. ***

Two distinct kills today, both exit **144**, both mine.
**The self-kill**, which the existing note covers: `pgrep -f "p1_abc.py e5 final"` inside a waiter whose own
command line contained that string, so the process-death branch could never fire and a crashed sweep would
have been indistinguishable from a running one.
**The sibling kill, which is new and is the expensive one.** I cleared that waiter with
`pkill -f "until \[ -f .*p1_proofs_report"` and **it also killed a subagent's summariser**, because that
summariser was waiting on the same file. The agent then reported its artefact had "died", inferred the
cause was its own single-background-task design, and re-engineered around a fault that was mine. **A wrong
cause produces the wrong fix**, and the agent's own lesson is the better one: it attributed the failure to
the nearest plausible feature of its own code without evidence distinguishing that from anything else.
**THE RULE: kill by pid, read from `/proc`, after confirming the pid is yours.** Never by name pattern. And
note the shape: the more precisely a pattern describes the thing you want to kill, the more likely a peer is
doing the same thing under the same description - **shared filenames are the coordination mechanism, so they
are also the collision surface.**
**And a waiter must have three distinguishable outcomes**, not two: result appeared / the process died
without writing it / the wait hit its own bound. Silence must never be ambiguous between "still working" and
"dead". That is the same requirement E3's `metrics_health` exists to meet for the scrape, reproduced in our
own tooling - and it was reproduced as a DEFECT in mine before it was reproduced as a rule.

## *** A DEFAULT IS WHAT RUNS, NOT WHAT A CLASS ATTRIBUTE SAYS. ***

E1 part 2 shipped `--metrics-scrape` with `default=True` while `asyncbackend.METRICS_SCRAPE_DEFAULT` was
`False`, and the runner assigned over the class default and passed it into the split cfg. **So every live
cell on the box would have scraped**, and the gated rung-4 1x cell would have run scraped against a rung-3
comparator that never scraped - differing in an input nobody had declared, on the cell the freeze gate turns
on. **I twice told the H100 "the class default is OFF, so nothing scrapes unless a cell asks", describing
the attribute while believing I was describing the system.** The H100 caught it by reading the argparse line
on origin instead of accepting my description. Fixed at `3b610470` (`default=False`), citing D187 and the
committed pre-registration's own words, so the code matches the registration rather than the registration
being quietly rewritten around the code.
**THE RULE: turning a switch on for every cell is a DEPLOYMENT DEFAULT and only the user rules it** (D187:
held or unproved code defaults OFF). **And when you describe a default, read the line that runs** - the
argparse default, the assignment that overrides it, and the consumer - not the class attribute that names it.

## *** A SCRATCH PATH MUST CARRY THE SESSION ID. A TASK-NAMED PATH IS NOT EXCLUSIVE, AND MINE WAS NOT. ***

I briefed a session to claim `scratchpad/matrix_verify_d225`. **Another session was already writing into it**
- files appeared under `matrix_verify_d225/cells/` with a different umask (`rw-rw-r--` against its
`rw-r--r--`) and mtimes 71 seconds before its own writes. It moved to
`matrix_verify_d225_8ab3f7e8`, re-derived every cell read itself, and discarded everything it had not
written. The values agreed where they overlapped, so nothing was contaminated **this time**; earlier today
the same collision on `scratchpad/d223x/a3` had one session delete another's tree under a running 1,200 s
sweep.
**THE RULE: `scratchpad/<task>_<session-id>`, always.** A task name alone collides precisely when two
sessions are given the same task, which is exactly when it is most expensive. Detect a collision by
**umask and mtime, not by content** - agreeing values prove nothing about who wrote them.

## *** A UNIQUE ANCHOR IS NOT THE SAME AS THE INTENDED ANCHOR. ***

A `count == 1` assertion on an edit anchor **passed and put the key in the wrong dict**: the text
`c_inflight=a.c_inflight, kv_capacity_enforced=...` matched once, but in the `cfg` block rather than the
`header` block, because the rewrite had a differently-indented twin. `cfg["metrics_scrape"]` would have
been right and `header.json` **silently empty**, and uniqueness would have certified it.
**THE RULE: assert the anchor's BLOCK, by line number against the block boundaries or by a two-line
anchor, not merely that it occurs once.** Same family as the `&&`-swallowed assert below and as the D191
identity: **a check that is sound and pointed at the wrong property.** That family is this project's most
expensive failure mode and none of its members is an arithmetic error.

## *** EVERY ASSERT IS A HARD STOP. AN ASSERT THAT PRINTS AND CONTINUES IS A DEFECT, NOT A WARNING. (standing rule, D228 addendum item 4, from my own failure) ***

**What happened.** I pushed a commit that landed E1 part 1's bookkeeping and DROPPED the three files that
implement the mechanism. Three patches failed to apply; my file-count check printed `files changed: 6
(expect EXACTLY 9)` and **the push went ahead anyway**. For four minutes origin asserted in
`EXPERIMENTS.md`, `INDEX.md` and `STATUS.md` that the engine-metric scrape was wired and proved, while
`asyncbackend.py` on origin still had `metrics()` not consulting it. **A commit that lands the paperwork
and drops the mechanism is strictly worse than one that fails, because the paperwork is what a later reader
trusts.**

**THE CAUSE, MEASURED RATHER THAN GUESSED. `set -e` IS SUPPRESSED FOR COMMANDS INSIDE `&&` / `||` LISTS,
AND THAT IS WHERE I PUT EVERY ASSERT.** Four one-line experiments, run to settle it:

| shape | result |
|---|---|
| `set -e; for x in a b c; do false && echo yes; done; echo AFTER` | **prints AFTER** - the loop swallows all three failures |
| `set -e; N=6; echo ok && [ "$N" -eq 9 ] && echo A; echo B` | **prints B, rc 0** - this is exactly what I ran |
| `set -e; N=6; [ "$N" -eq 9 ]` as its own statement | rc 1, correctly aborts |
| `set -e; N=6; if [ "$N" -ne 9 ]; then echo STOP; exit 1; fi` | **rc 1, correctly aborts** |

So the same root cause produced BOTH failures in that commit: the `git apply --check && git apply` chain
inside a `for` loop swallowed three patch failures, and the `&& [ "$N" -eq 9 ]` chain swallowed the count
mismatch. **`set -e` plus `&&` is not a check. It reads like one.**

**THE RULE.** Every landing, proof or check script fails hard:
- **Write `if [ "$N" -ne "$EXPECTED" ]; then echo "STOP: ..."; exit 1; fi`.** Never a bare `[ ... ]` and
  never an `&& [ ... ]` relying on errexit.
- **Never chain a check with `&&` onto the thing it is checking**, and never put one in a loop body without
  its own explicit `exit`.
- **Assert the EXACT count both ways, never a bound**, and name what the number should be.
- **After every commit, read the published bytes back FROM ORIGIN** and grep for a string taken **from the
  FILE, not from your commit message**. I made that mistake minutes later and got a clean false absence:
  the grep pattern came from the commit text, the file said it slightly differently, and the result was
  `0`. **A probe searching the wrong string reports an absence indistinguishable from a real one.**
- Prefer the shape the D225 and stub-marking sessions used: copy into a clean `git archive` checkout, stage
  a scoped list, assert added-versus-modified counts separately with explicit `exit 9`, then push.

**There is no single script to fix: the fault was an inline chain, repeated.** The durable fix is this rule
plus the measured reason, because the pattern will otherwise look correct every time it is written.

## *** NEVER EDIT A GATED CELL LIST IN PLACE, NOT EVEN A COMMENT. THIS COST THE H100 ABOUT 45 MINUTES OF POLICY TIME TODAY AND THE FAULT WAS MINE. ***

`RUNG3_KV05R_CELLS` is **hash-gated**: the driver runs a posted list ONLY while its sha256 matches the
`V6_GATE_OK` / `OPERATOR` line in `frozen_grid.log`. I asked for four explanatory header facts to be added
to it; an agent added them **as comments only** and diffed the four runnable lines to prove them
byte-identical - careful about the CONTENT and unaware the FILE was gated. **The hash changed, the list
silently UN-GATED, and the driver fell through to filler**: rung 3 s5 did not start at 10:13 and ran
eco-llm 1x s6 instead, until the H100 found it and re-gated at the new hash.
**THE GATE WAS WORKING CORRECTLY.** To a hash, a comment and an unchecked change are the same event - that
is the entire point of gating, and a gate that let comments through would not be a gate. So the error was
not the hash's strictness, it was editing a gated artefact at all. **AND NOTHING LOOKED WRONG**: the H100
kept busy on filler, no error was raised, and the only visible symptom was a policy cell that quietly did
not start. A session watching for failures would not have seen it.
**THE RULE, adopted at the H100's request: notes about a gated list go in a SEPARATE file**
(`<LIST>.notes.md`) **or in a message to the owner, never into the list.** If a gated list genuinely must
change, the owner changes it and re-gates in one step; re-gating means appending to `frozen_grid.log`,
which the driver appends to concurrently, so it is the owner's move and nobody else's.
**THE GENERALISATION, because this will recur in other forms:** before editing ANY file another process
reads as an input, ask whether something downstream checks its bytes - a hash, a digest, a signature, a
manifest. **A content-preserving edit is not behaviour-preserving when something hashes the content.** My
own byte-identity habit (diff the lines that matter) is exactly the check that passes here while the thing
that actually matters fails.

## *** STATE AS OF 2026-11-24 ~19:00Z. RUNG-4 PASS 1 IS COMMITTED AND ONE CELL IS REQUESTED. READ THIS BEFORE THE OLDER SECTIONS, WHICH IT SUPERSEDES. ***

**PASS 1 IS ON ORIGIN: `8d883208` (code and proofs), pre-registration `StudyD222-PASS1` at `da1593a0`.**
Items 1, 2, 4 and 5 under D228's rulings, plus **E1 part 2**, rebased onto the H100's `5155aad4`.
**Item 3 is NOT built.** D220 (1)'s gain weighting is WITHDRAWN per D228 (2), so the harm form is unchanged
and `MARGIN_CF` stays 0.6582.

*** THE ONE THING OUTSTANDING, RECORDED HERE BECAUSE THE MESSAGE CARRYING IT MAY NOT HAVE ARRIVED. *** I
asked the H100 to post **one** cell and the cross-session route reported delivery UNCONFIRMED and one-way.
So, for whoever reads this next:

```
covex-v6-final 16 4 _L3_epg_rq30_rerun
```

**The `_rerun` tag is a deliberate operator choice, not a spelling accident.**
`covex-v6-final_n16_s4_1200s_h27_3t_L3_epg_rq30` already exists as the superseded cell; never overwrite a
valid one; and under D154 (4) the run tag carries the engine-side cache key, so **a cell priced from the
D162 model must not share a cache entry with one priced from the failing model.** The kv0.5r s4 line follows
once the 1x cell is gated, and it should pass `--metrics-scrape`.

**THE 1x BAR, pre-registered at `da1593a0` so it cannot move afterwards:** against `covex-v6-fair-final` 1x
s4, mean per-episode alert attainment >= rung 3's, robot on-time retention >= 0.90 of rung 3's gain over
base, single-shot >= 90 percent within 2 s. Report beside it: deferral rescues and losses paired by
question, the DEVICE_ANSWERS count, protect-and-defer actions by kind, and `metrics_health`.

*** AND THE REGISTER WARNING THAT WILL OTHERWISE BE MISREAD. The dry s4 proof records ZERO DEFERRALS. THAT
IS NOT A NEGATIVE. *** A dry cell has no engine telemetry and prices every session **COLD**, inflating the
uncached token count roughly tenfold, which inflates predicted service and so inflates
`must_start_now_no_slack` - 52 of its gate hits. `rd_u_cold` is **28 of 28 dry against 1 of 157** in the
committed live s4. Under Rule 2 the dry cell is **UNEXERCISED BY CONSTRUCTION**, and the fail-fast decision
belongs to the LIVE cell. **The direction was written down before the sweep ran, not after its result.**
If the LIVE cell also shows zero deferrals, that is informative.

**TWO FINDINGS WORTH CARRYING.** (1) The D191 column `rd_defer_would_miss_at_measured_worst_bias` was
**identically false by an algebraic identity**: at n = 5 the nearest-rank q90 **is** the sample maximum, so
`bias_max == SAFETY_FACTOR`, `overrun == 0`, and `0 > 0` never fires. Third instance of this shape after
D203 (3) and D206 (1). The estimator and the test were each correct and their composition was vacuous, so
under Rule 2 it is **cancelled by geometry**, and item 4's refit to n = 255 repairs the column as a side
effect. (2) `d222_measured_safety` **RAISES rather than defaulting** when its committed artefact is absent,
and that is how I found that `results/orchestration/live2/d222_pass1/d222_safety_refit.json` had to be
committed with the code: without it every rung-4 arm fails at import. **An import smoke test caught what no
patch check would have.**

**CORRECTIONS TO THE SECTION BELOW, which is now stale.** E1 + E3 part 1 AND part 2 are both on origin
(`b379ef23`, `7fdd0582`, `8d883208`), so the file-hold list no longer applies; the shared worktree `mapwt`
has been archived and classified under D228 (5) (`8f7c1aa1`), and its uncommitted work was **5,509
insertions across 139 files**, not the 632 the section claims - I had counted three files and generalised.

## *** LIVE FILE CLAIMS, 2026-11-24. READ THIS BEFORE YOU EDIT OR BUILD. ***

A peer session asked "who holds E1 + E3?" before starting, which was exactly right, and then RESTARTED
before I could answer, so the answer is written here instead of in a message. **A claim in a message dies
with the session; a claim in the repo does not.** That duplication already cost an hour of compute today
and one session deleted another's proof tree mid-run, so this section exists to stop the third instance.

**HELD BY THE A6000 [6736b0] E1+E3 AGENT, DO NOT EDIT OR BUILD ON THESE:** `live2/asyncbackend.py`,
`live2/run_live2_real.py`, `live2/procsplit.py`, `live/adapter.py`, `live2/cstate.py`,
`live2/metrics_trust.py` (new), `live2/d227_e1_metrics_proofs.py` (new). **E1 + E3 IS ALREADY BUILT AND
PROVED (five parts PASS) AND UNCOMMITTED**, held on the H100's two shas. **PART 2 IS WHAT DISCHARGES THE
ITEM**: until the harness flag and the one `cell.json` line land, `METRICS_SCRAPE_DEFAULT` stays False and
the capability is DORMANT - correct under D187, so `metrics_health` existing with no caller is the
expected intermediate state, NOT a defect to re-fix.
**HELD BY THE H100 FOR ITS TORN-TREE COMMIT:** `live2/run_live2_real.py` and `live2/procsplit.py` until
its sha is read back from origin. Those two are claimed by BOTH, in sequence: H100 first, then the one
`metrics_health` line rebased onto it.

*** `/tmp/claude-1001/mapwt` CARRIES 15 UNCOMMITTED EDITS, 632 LINES, THAT ARE NOT SCRATCH. ***
`coordinator.py` (483), `v5/cf_objective.py` (123) and `arms.py` (33) - the D182 deficit-ordering hook,
belonging to neither the context-limit work nor this session. **DO NOT CLEAN IT UNILATERALLY** and do not
assume it is yours. `research/policy_design_log.md` there IS this session's (the D220-D227 append,
committed) and is dirty-but-equal-to-origin, so it is scratch.
**THE HAZARD, WHICH I HIT TODAY: `git archive` reads the COMMIT and is safe, but `git hash-object` on a
worktree path PICKS UP WHATEVER IS SITTING THERE.** That is how I nearly committed stale `EXPERIMENTS.md`
and `INDEX.md` over other sessions' work; the exact-count assert caught it (expected 3, changed 2). **So
restore every file from `git show <sha>:<path>` IMMEDIATELY BEFORE editing it, and assert the EXACT file
count both ways, never a bound.**

*** AND GIVE EVERY PROOF TREE A PER-SESSION SUFFIX. *** Two sessions both defaulted to
`scratchpad/d223x/a3`; one finished, cleaned up, and deleted the other's tree under a running 1200 s
sweep. The victim's control correctly FAILED and its script refused to report, which is the guard working,
but the compute was gone. A per-session suffix removes the whole class and costs nothing.

## WHERE THE WORK IS

RUNNING NOW (H100): nine final-ladder cells, s5 to s7 for `covex-v6-fair-final`, `covex-v6-final`,
`covex-v6-state-final`, from ~20:11, LADDER COMPLETE ~23:20. Then hit 7 lands on `coordinator.py` and
`cstate.py` with its final-rung identity pass; then SimpleStream reruns as filler; then item 3.
ALL TWELVE LADDER CELLS RUN ON ONE COORDINATOR COMMIT by agreement, so "did the coordinator change
mid-ladder?" never arises. Hit 7 AND item 3 are both `coordinator.py` edits, so BOTH wait for the last
cell. Score each cell as it lands with the committed `d179_rung2_verdict.py`; the s4 verdict is
complete and committed.

## THE FIVE OVERNIGHT STEPS, IN ORDER

1. **DEVICE_ANSWERS (D218 (1))** against the FROZEN pre-registration `77cf269e`, on a NEW VERSION LABEL
   so the posted `covex-v6-final` is untouched. Dry report: per-kind counts at 1x AND 0.25x,
   `pd_request_device_answers`, `pd_request_crossed_bar_unexpressible` BEFORE and AFTER, and THE
   PREDICTED TRADE PER DENIAL (this question's lost weighted P(on time) against on-time answers saved
   BY TYPE, alert / recall / assistance). **THE 1x COUNT DECIDES WHETHER THE POSTED `covex-v6-final` s4
   IS SUPERSEDED: IF NON-ZERO, STOP AND REPORT, DO NOT DECIDE.**
   *** DONE, AND THE STOP CONDITION IS MET. THE 1x COUNT IS 1, NOT 0. *** Committed `4f317e1f`,
   `reports/study_d218_device_answers.md` section 2. The pre-registered pass condition PASSED
   (`pd_request_crossed_bar_unexpressible` 27 -> 0, `pd_request_device_answers` 15 on the dry 0.25x
   cell). **THE SESSION CORRECTLY STOPPED RATHER THAN DECIDING, AND SO DID I.** Two facts point
   opposite ways and only one is the user's question: (a) the POSTED ARM DID NOT MOVE - `covex-v6-final`
   is byte-identical with the candidate off at both settings, 0 differing decisions,
   `57bed6ace2eb07d1` / 14,509 at 1x and `278da529349ff8c2` / 14,306 at 0.25x, **both values
   independently known from committed cells**; (b) but with the switch ON at 1x it gives
   `3cddb4b7c7322a25` / 14,510, **45 differing decisions**, so under D209 (1) the posted s4 cell is
   SUPERSEDED IF the candidate is adopted into `covex-v6-final`. **THE RULING IS WHETHER DEVICE_ANSWERS
   IS A CORRECTION OF AN OMISSION THE SPEC ALREADY CONTAINED (adopt -> supersede -> rerun rung 4) OR A
   SEPARATE ARM `covex-v6-final-da` (posted cell stands).** DO NOT DECIDE IT.
   NOTE ALSO: two sessions built D218 (1) in parallel and produced TWO pre-registrations which AGREE ON
   THE PASS CONDITION VERBATIM, so no bar differs; which is the record is also the user's call. And
   `77cf269e` IS A GIT COMMIT SHA, NOT A DOCUMENT sha256 - I relayed it as a "frozen prereg hash" and
   that conflation would make a pre-registration unverifiable by hash.
2. **E1 - SEE THE CORRECTION ABOVE: THIS STEP IS IMPOSSIBLE AS WRITTEN, THE SCRAPE IS AN
   ABSENT LINK WITH ZERO CALLERS, AND THE WIRING FIX IS A PENDING USER RULING. DO NOT RUN IT.**
   ~~enable the `/metrics` scrape for `covex-v6-final`'s GATE ONLY; prove EVERY other arm
   byte-identical; report HOW MANY RUNG-4 DECISIONS MOVE.~~ MUST LAND BEFORE ANY 0.25x POLICY CELL
   (D216 (2)). `asyncbackend.py` is uncontested, so this can proceed independently of hit 7.
3. **ITEM 3 (D216 (3))**: record the belief's predicted GPU-resident prefix per request so D211 signal
   (a) is computable. Site is `coordinator.py:2126`, so IT WAITS FOR HIT 7.
   *** UPDATED 2026-11-24 09:15 PST: HIT 7 HAS LANDED AND ITEM 3 IS NOT BLOCKED. ITS BYTE-IDENTITY
   SWEEP IS RUNNING RIGHT NOW. DO NOT START A CELL AND DO NOT RE-LAUNCH IT. ***
     *** SUPERSEDED 2026-11-24 later: ITEM 3 HAS LANDED AND NOTHING IS RUNNING. The sweep finished,
     landed as `56a73293` (verified an ANCESTOR of origin/main), 24 of 24 arms BYTE-IDENTICAL with 0
     decisions moved setwise, both committed positive controls matched, and the owning session has
     STOOD DOWN. Verified just now: NO live2 process of any kind under the repo or a scratchpad, and
     loadavg 0.33. **SO THE ALONE RULE DOES NOT BIND ON THIS ACCOUNT AND A DRY CELL MAY RUN** - census
     the box yourself before you do. A stale 'DO NOT START A CELL' is exactly the kind of note this
     file elsewhere complains about for having blocked real work all night, so it is corrected rather
     than left to be re-derived. ***
     pid 378337 = `d213_digest_driver.py --out out/item3_digests.json`, with a LIVE CHILD (pid 381059,
     1:19 CPU) running a `cf_pd_one_cell.py` cell. The orchestrator itself shows `00:00:00` own CPU,
     which per this file's own corrected rule is a HEALTHY ORCHESTRATOR, not a hang: the discriminator
     is CHILDREN, and it has one burning CPU. loadavg 1.25. **THE ALONE RULE THEREFORE BINDS: any dry
     cell of your own MUST WAIT.**
   Hit 7 landed as `c511050` (four files, +59 -3), read back from origin byte-identically rather than
   trusted from the push. **THE SITE MOVED: `coordinator.py:2126` -> `:2138`**, because hit 7 added 15
   `window_s` occurrences to that file. Both of item 3's anchors still occur EXACTLY ONCE, which is why
   its `count == 1` assertions were worth keeping.
   *** AND THE "IT BLOCKS ITEM 3" CLAIM IN THE CONCURRENCY SECTION ABOVE IS STALE. *** That section says
   `coordinator.py`'s 9 worktree-only lines pose a held-code-versus-abandoned-WIP question that BLOCKS
   item 3. **IT DOES NOT: item 3 never needed the shared worktree's copy.** It builds its A and B trees
   from a PRIVATE `git archive` of a re-resolved origin sha, so the dirty shared copy is irrelevant to
   it. The held-versus-abandoned question REMAINS OPEN for anything that would overwrite those three
   files, and it is still a user question, but it is NOT an item-3 blocker and no resume should wait on
   it for that reason.
4. **THE 0.25x PAIR, user-approved FOR THIS PAIR ONLY**, once 1 to 3 pass: `covex-v6-fair-final` and the
   DEVICE_ANSWERS build of `covex-v6-final` at 0.25x s4, REAL ENGINE POOL
   (`--num-gpu-blocks-override 985 --max-model-len 15744`, pool of record 15,760 = 985 x 16), posted
   BEHIND the remaining `FINAL_LADDER_CELLS`. Bar: the frozen D190 (3) rung-4 test at 0.25x, reported
   BESIDE per-type percent correct-by-deadline, single-shot within 2 s, and total on-time cloud answers.
   VALIDATE D211 signals (a) and (b) on these two cells against `host_counters_d211.log` at the frozen
   bar.
5. Rulings applied in this commit: the scorer LABEL fix with its erratum (governing test unchanged), and
   the `arms_v6cf.py` doc line.

## WHAT IS DONE AND MUST NOT BE REDONE

`FINAL_LADDER_CELLS` posted `43ad8be8`; s5 to s7 posted `599e2dbc`. s4 verdict COMPLETE: all three rungs
PASS, rung 3 by +0.1767 on the harder "above base's" bar with retention 1.0833; **rung 4 by +0.004066,
which at 712 episodes is ABOUT 2.9 EPISODES while the fraction meeting the 0.25 target FELL by about 8
EPISODES, so the two alert measures DISAGREE IN SIGN and it must never be quoted as a clean win.** The
better account of rung 4 at 1x is that it sent 675 FEWER robot requests for 121 on time against 126 with
`by_deadline` IDENTICAL. Rung 2 has no bar of its own and rides with rung 3.

## HAZARDS THAT HAVE EACH COST SOMETHING TODAY

### THE ONE PATTERN BEHIND MOST OF TONIGHT'S NEAR-MISSES: AN INSTRUMENT THAT RETURNS A CONFIDENT WRONG
### ANSWER POINTING AT A HARMFUL ACTION. Four distinct instances in one evening, each caught only by
### someone checking WHAT THE INSTRUMENT CLASSIFIED rather than WHAT IT CONCLUDED.
### THE FAMILY, stated once: A BOUND NOBODY STATES, PLUS AN OUTPUT THAT LOOKS LIKE PROGRESS.

| instrument | how it failed | what it looked like | what the wrong action would have been |
|---|---|---|---|
| alone-guards, THREE sessions | bounded by a name pattern, a hardcoded basename list, and a tree snapshot | `alone: true` while the box was busy | a digest recorded as alone that was not |
| a byte-identity check | a raw line-number rule swept two function bodies into "post-run" | PASS on the real tree | shipping wiring whose in-run statements were never checked |
| a hung driver | blocked with 00:00:00 CPU and no children for 59 minutes | indistinguishable from a long cell | waiting out an hour, then reporting a table from nothing |
| a completeness check | "trees already present" looked for ONE file, so minimal stub trees satisfied it and the rebuild was skipped | a proof running against a tree with no coordinator, no fleet and no tests | a failure that reads as a CODE fault rather than a missing tree |
| a liveness watch | `grep -lq ... /proc/*/cmdline` exited non-zero on ERROR, not no-match, so the negation read "gone" | a false terminal state | RELAUNCHING a running sweep, putting two drivers on the box and breaking the alone rule it enforced |

THE OPERATIONAL RULES THAT FALL OUT, AND THEY ARE CHEAP:
- READ WHAT A CHECK CLASSIFIED, NOT ITS VERDICT. An impossible success is as diagnostic as an impossible
  failure, and arithmetic checking cannot see either.
- A CHECK SHOULD CARRY ITS OWN NEGATIVE CONTROL AND RUN IT EVERY TIME. One session now injects four
  decision-changing statements and requires all four to be REJECTED; the real tree passing is the
  positive control.
- SILENCE MUST BE DISTINGUISHABLE FROM PROGRESS. Bound every wait, and make it end on at least three
  conditions named separately: the result appeared, the process died without writing, and the resource
  floor was hit. A watch that reports a false terminal state is WORSE than no watch, because the wrong
  action looks correct.
- COUNT PROCESSES BY WHAT THEY ARE, never by a name. An interpreter plus a path under the repo or a
  scratchpad tree, or enumerate `/proc/<pid>/cwd`. State the census's own blind spot in the record.
- PREFER EVIDENCE OVER A FLAG. Two independent runs agreeing exactly is DIRECT evidence of determinism;
  an alone-flag is only an argument that nothing COULD have disturbed the cell. Record the census and
  the loadavg magnitudes BESIDE any boolean so it can be re-adjudicated later.
- NEVER LET A WAIT HAVE ONLY THE TWO TERMINAL CONDITIONS A READER EXPECTS, and RECORD WHICH ONE FIRED.
  One session's waits now end on a clear guard, a timeout, OR low disk, each written into a
  `wait_terminated_by` field, so "still waiting", "gave up" and "stopped on disk" are three
  DISTINGUISHABLE states in the output rather than one silence. A bounded wait that also ends on
  PROCESS-DISAPPEARANCE would have caught the hung driver with nobody watching.
- A HALTED PROOF MUST NEVER READ AS A CLEAN ONE. The same session's byte-identity proof now writes a
  VERDICT of "NOT RUN: LOW DISK" saying IN WORDS that it is NEITHER A PASS NOR A FAILURE.
- HELD CODE LIVES AS A `.patch`, NOT A `.py`, AND IN GIT RATHER THAN ONLY IN /tmp. The D214 wiring
  existed ONLY inside a scratchpad tree that was about to be deleted for disk; it is now committed at
  `experiments/orchestration/live2/held/` as a patch plus a README, verified to reproduce the held
  md5, with NOTHING importing it and `run_live2_real.py` on origin still at ZERO occurrences of
  `figure_instrumentation`. COMMITTING A PATCH IS NOT LANDING THE WIRING, and storing it as `.patch`
  rather than `.py` is what keeps it out of an import or a glob.
- *** THE LADDER IS COMPOSITION, NOT INHERITANCE, SO AN MRO WALK CANNOT ESTABLISH AN ABSENCE. TOKEN:
  MRO-ABSENCE-INVALID. *** Hit from three directions in one day, which is why it belongs here:
  **(1)** the conformance-matrix build found that a naive `vars()` + MRO diff reports **TWENTY FALSE
  INHERITANCE BREAKS**, because the arms define `__call__` so `callable(_rules)` is true and a walker
  skips it. Caught mid-build.
  **(2)** a session used an MRO walk to conclude that `over_limit_infeasible` is write-only and that
  rung 3 never calls `limit_tokens()`, and nearly sent a user-facing ruling request on a non-problem.
  Its own summary of the fault is the best statement of it: **"my statement was true and my conclusion
  false - no method in rung 3's MRO calls `limit_tokens()`, but the call LEAVES THE MRO THROUGH
  COMPOSITION."** The real chain is `arms_v5rules2.py:107` composing a real `HybridArm`, `:111-112`
  setting the flag on BOTH `self` and `self._base`, `:278` delegating via `self._base.decide(obs)`,
  reached from `arms_v6state.py:379` through `self._rules`, arriving at `hybrid_arm.py:421`.
  **(3)** the SAME unsound method underpinned the E1 licensing warrant for the 0.5x cells. Re-checked
  COMPOSITION-AWARE and the conclusion held: `arms_v5rules2.py`, `hybrid/hybrid_arm.py`,
  `arms_v6state.py`, `arms_v6fair.py`, `arms_final_ladder.py`, `arms_v6fairfeed.py` all carry ZERO
  references to `gpu_kv_fraction` / `kv_cache_usage` / `scrape_metrics`, and `hybrid_arm.py` composes
  nothing further (no `self._base`, no `self._rules`), so the chain TERMINATES there. Verified
  independently here. **The warrant was right and its method was not, which is the case worth fearing:
  a sound conclusion from an unsound method teaches the method.**
  **THE RULE: to claim any mechanism is absent from an arm, WALK `_rules -> _base -> _b7` AND SHOW THE
  PATH WALKED, then show the chain terminates. `d225_switch_diff.py` already does this and prints its
  path; copy it rather than writing a fresh MRO walk.**
- *** AND A READ-BACK CHECK CAN CRY WOLF. *** My own published-bytes check reported MISSING on a commit
  that had landed correctly, because I grepped a prose sentence in the wrong CASE. A verification that
  fails on capitalisation will send someone hunting a phantom revert, and train them to ignore it.
  **Grep a token the writer controls exactly - a sha, a count, a key name, or a planted marker like the
  one on the line above - never a prose sentence.**
- *** TEXT ABOUT A PAST STATE READS AS A PRESENT STATE. THREE INSTANCES TODAY, THREE DIFFERENT
  CARRIERS, AND THE THIRD HAD THE CORRECTION ON THE PRECEDING LINE. *** Collect them, because the
  carrier changes and the error does not:
  **(1) A CODE COMMENT.** `cstate.py:138` says `desired_tier` had "TWO WRITES and NO READ"; the reads
  are twenty lines below at `:527` and `:530`. I seeded two agent briefs with the stale claim.
  **(2) A STATUS STRING.** `v5/cf_cost.py`'s `GATE_STATUS` describes the model as FAILING spec v5
  section 12 - true of that model, while the model that PASSED (D162, per D168) lives in a different
  file under a different key. The string is accurate and the conclusion drawn from it was not.
  **(3) A WITHDRAWN NOTE, WITH ITS OWN WITHDRAWAL DIRECTLY ABOVE IT.** `RUNG3_KV05R_CELLS` carries
  "*** CORRECTION 2026-11-24: NOTES (a) AND (b) BELOW ARE WITHDRAWN. RUNG 3 **DOES** ENFORCE..." at
  line 38, and an agent quoted notes (a) and (b) as current, concluding rung 3 does not enforce the
  context limit and asking for a user ruling on a non-problem. The withdrawal was ONE LINE AWAY.
  **THE RULE: when a file tells you a mechanism is absent, broken or superseded, READ UPWARD AND
  DOWNWARD BEFORE QUOTING IT, AND PREFER THE CODE OVER THE PROSE.** A read site settles a write-only
  claim; a passing gate settles a status string; a withdrawal settles a note. And when you WRITE a
  withdrawal, put it where a quoter cannot miss it: strike the withdrawn text or move it below the
  correction, because "see the correction above" is exactly what a reader skips.
- *** A FIXED DEFECT WHOSE OLD DESCRIPTION SURVIVES IN A CODE COMMENT WILL BE RE-REPORTED FOREVER.
  I DID IT TWICE AND SEEDED TWO AGENT BRIEFS WITH IT. *** `cstate.py:138` says, in the code,
  "`desired_tier` was declared here with TWO WRITES and NO READ anywhere in live2". **THAT COMMENT IS A
  HISTORY, NOT A STATE**: `:468` and `:486` record that `placement_enacted` makes it READ, and `:527`
  and `:530` ARE the reads. A grep that lands on the comment reproduces the stale claim with apparent
  code backing. Same for `_caps`: it is `live2/arms.py:82` and IS read at `arms_published.py:209`, and
  **`baselines/arms.py` DOES NOT EXIST** - a grep against that path returns rc=128, an ERROR, which a
  careless check reads as "no match", so the write-only claim looked confirmed twice over.
  **FOUR STANDING ABSENT-LINK NOTES ARE NOW FIXED AND MUST STOP BEING RE-REPORTED:** `desired_tier` is
  read; `delivered_scores`'s literal-0.0 writers are gone and none of D205's seven readers reads values;
  `telemetry_cached_tokens` is live at three decision sites; `TOUCH_PRICE_MODE` is assigned.
  **THE RULE: to claim a field is write-only, name the READS you searched for and show the search, not
  the comment that says it once had none.** A comment is evidence about the past.
- *** AND THE MISCITATION THAT COMMENT CARRIES HAS PROPAGATED INTO TWO COMMITTED REPORTS. ***
  `cstate.py:138`, `:468` and `:486`, plus `reports/policy_fidelity.md:52` and
  `reports/study_engine_actions.md:129`, cite **"D133 Part A"** for making `desired_tier` enacted. **D133
  is robot capacity over feasible questions and says nothing about placement; the governing row is D134
  (1).** A wrong citation survives every arithmetic check and spreads by copy, so check a cited D-row
  against the log before repeating it.
- *** NEVER ESTABLISH AN ABSENCE BY GREPPING THE SHARED WORKTREE. IT IS ABOUT 1,500 COMMITS BEHIND
  ORIGIN. *** `/home/pragya/Desktop/FM-switching` sat at `17bdf159` while origin was at `7ca9d1e7`:
  1,500 commits. A file committed tonight IS NOT THERE, so `grep -r` over it returns nothing for a file
  that exists. THIS COST ME A WRONG ESCALATION: I told an agent its proof script was uncommitted and
  "one cleanup from destruction" on the strength of `grep -rln ALL_PASS experiments/` returning empty.
  It was committed, and `ALL_PASS` is in THIRTEEN committed files. ALWAYS use `git grep <literal-sha>`
  or `git show <sha>:<path>`, never a filesystem grep of that tree, for any claim about what is or is
  not in the repo. The same staleness is why files committed tonight show as `??` untracked there.
- *** THE STALE-TREE HAZARD, NOW QUANTIFIED, AND IT HAS BITTEN TWO SESSIONS. A FILESYSTEM PROBE OF
  THAT TREE SEES 8.6 PERCENT OF THE DATA AND REPORTS A CONFIDENT ZERO. *** Measured:
  `/home/pragya/Desktop/FM-switching` holds **35** `coordinator_result.json`; origin holds **418**; the
  tree is **1,678 commits behind**. *** THE 408 I FIRST WROTE HERE WAS ITSELF MEASURED AGAINST A TEMPORARILY STALE ORIGIN, WHICH IS THIS HAZARD RECURSING ONE LEVEL UP. *** The H100 reported an availability incident: from about 03:00 to 06:43 on 2026-11-24 its drivers' pushes never landed, because every driver since v28 used a BARE `git pull --rebase`, which fails on that clone with "Cannot rebase onto multiple branches", and a run-watch auto-push had been silently covering it until it expired. I measured the origin-side count at 03:16, INSIDE that window, so origin was missing about ten files at that moment and my denominator was low. The fraction is **8.4 percent**, not 8.6. **THE QUALITATIVE POINT IS UNCHANGED AND SLIGHTLY STRONGER**, and the lesson gains a second edge: a measurement OF a staleness hazard can itself be stale, so date any origin-side count and say when it was taken. A peer's census reported "zero committed cells carry `pd_` stats, 35
  checked" - **and the number 35 made it SOUND LIKE A CENSUS while being 8.6 percent of the
  population.** The counters were there all along, in 408 files. My own instance earlier the same night
  was a `grep -rln` for `ALL_PASS` that returned empty while the string sat in 13 committed files.
  **A SAMPLE SIZE QUOTED BESIDE A NEGATIVE MAKES THE NEGATIVE SOUND MEASURED.** State the tree any
  census walked, and on this repo read git (`git ls-tree`, `git show <sha>:<path>`, `git grep <sha>`)
  rather than the disk. Committing through a temporary index without ever checking out - which is the
  right practice here - guarantees the disk is stale, so the two habits must go together.
- *** A PARTIAL FIX THAT REPRODUCES THE WRONG ANSWER READS AS CONFIRMATION. *** That peer's probe had
  TWO faults: it read the wrong nesting level (`d` instead of `d["arm_stats"]`) AND it walked the stale
  tree. I diagnosed only the first and told it so. **Had it fixed only the nesting, the probe would have
  returned ZERO AGAIN - from the stale tree - and the zero would have looked like confirmation that my
  correction was wrong.** It escaped that only by re-running and noticing the count was still zero, then
  asking why. So when a fix does not change a result, ask whether a SECOND cause is holding it; and when
  you hand someone a diagnosis, say what you checked and what you did not, so a null after their fix is
  readable.
- *** A SUMMARISER THAT PROBES FOR A KEY NAMED AFTER A VALUE PRINTS `None` FOREVER. *** A proof wrote
  `{"verdict": "ALL_PASS", ...}` and a summary line reported `ALL_PASS: None`, which reads as an
  unset aggregate and sent me hunting a swallowed fifth check. There was none: four `P*` keys, all
  PASS, and the aggregate is computed as `all(... for k in out if k.startswith("P"))`, so coverage is
  complete BY CONSTRUCTION and `None` was unreachable from that code. A reader asking for
  `d.get("ALL_PASS")` on a dict whose KEY is `verdict` gets `None` whatever the verdict says. READ THE
  FIELD, THEN ASSERT ITS VALUE IS THE LITERAL EXPECTED STRING; never probe for a key named after the
  value you hope to see, and never read a `None` as a failure before checking the schema.
- *** A RECORD-ONLY COMMIT CAN REPORT SUCCESS AND CHANGE NOTHING. BOUND THE FILE COUNT FROM BELOW,
  NOT ONLY FROM ABOVE, AND READ THE PUBLISHED BYTES BACK. *** A session staged FIVE files from a
  correct scoped list; `diff-tree` reported FOUR. Its working copy of the fifth had been overwritten by
  raw driver output, so the blob it pushed was byte-identical to the one already on origin. **THE PUSH
  SUCCEEDED AND CORRECTED THE ONE FILE THAT MATTERED MOST: NOTHING** - the misleading headline stayed
  published while a commit claiming to fix it landed on top. Its own guard asserted "at most 5 files"
  and PASSED AT 4: **bounded from above, never from below.** So: assert the EXACT expected count, and
  then `git show origin/main:<path>` the file and grep it for the SPECIFIC TEXT the commit exists to
  add. A scoped list guarantees what is STAGED, never that staging CHANGED anything. This is the
  pattern in the RECORDING layer rather than the measurement layer.
- *** "ZERO CPU" IS NOT A HANG SIGNATURE. THE DISCRIMINATOR IS WHETHER IT HAS A WORKING DESCENDANT. ***
  A driver at `00:00:00` CPU after 59 minutes with NO CHILDREN was genuinely hung and had started no
  cell. The same driver later showed `00:00:00` CPU after 20 minutes and was PERFECTLY HEALTHY, because
  it was blocked waiting on a child burning CPU (`346850` 0:00 -> child `357145`, 102 s elapsed, 1:44
  CPU, state `Rl`). A parent blocked on a working child is the NORMAL shape of a driver. So walk the
  tree with `ps -eo pid,ppid,time,stat` and ask whether any DESCENDANT is accumulating CPU; reporting a
  healthy driver as hung would have had someone kill a running cell.
- *** TWO ARMS CAN LAND ON THE SAME NUMBER FOR DIFFERENT REASONS. EQUALITY WITH A FLOOR IS NOT
  EVIDENCE OF A MECHANISM. *** I built a "three-arm convergence" out of `cascade-routing`, `SimpleStream`
  and the D152 `RECENT` measurement, all sitting at or below the device-only floor, and called it one
  mechanism: a short representation cannot answer a long-history question. **THE H100 REFUSED IT AND WAS
  RIGHT.** `cascade-routing` sits on the floor because IT ALMOST NEVER SENDS ANYTHING - its port-rule
  failure - so its `by_deadline` equals the floor BY CONSTRUCTION, not because a short representation was
  delivered fast. **AND I HAD ESTABLISHED THAT MYSELF EARLIER THE SAME NIGHT**, including that its 18
  `RECENT` sends were too few to move its headline, and then used the arm as evidence for the opposite
  reading. The convergence is `SimpleStream` PLUS D152, with `cascade-routing` as a FOOTNOTE for its 18
  sends only. Before grouping arms by an outcome, state each one's CAUSE and confirm they match; this is
  consistency check 3's artefact-spread hazard with the sign reversed - not a spread that cannot mean
  what it says, but an AGREEMENT that does not mean what it looks like.
- *** DO NOT UPGRADE AN OBSERVATION INTO A MECHANISM IN THE WORDING. *** I wrote that SimpleStream's
  below-floor result shows a representation that "ACTIVELY DESTROYS information the device already had".
  **The H100 kept "WORSE than the device-only fallback" instead, because the first is a mechanism claim
  nobody has traced.** The observation is that cloud answers scored below the device's own; the
  explanation is a hypothesis. Both may be true and only one is measured. **A mechanism claim smuggled in
  as an adjective survives every arithmetic check**, which is the register rule applied to prose rather
  than to numbers.
- *** A PROOF'S OWN INSTRUMENT DESERVES THE SAME ABSENCE-CHECKING THE POLICY GETS, AND TWO OF TODAY'S
  WORST FAILURES WERE INSTRUMENTS, NOT POLICIES. *** One proof COMPUTED the D216 (1) alone census and
  loadavg and then DROPPED them before writing its artefact, so the rule it claimed was unevidenced in
  the very file claiming it. Another walked an MRO to rule a mechanism absent, when the call leaves the
  MRO entirely through COMPOSITION, so it reported confidently on a path the decision does not take.
  **Both were instruments reporting about something they could not see, and both were caught only by
  trying to READ THE CLAIM BACK against the thing it described.** So: apply Step 2's own test to your
  harness. Name the read, name the path walked, and read your own artefact back before you believe it.
- *** TWO AGENTS AGREEING VIA THE SAME UNSOUND INSTRUMENT IS ONE OBSERVATION, NOT TWO. *** Two sessions
  independently concluded rung 3 does not enforce the context limit; both had walked the MRO, and the
  agreement read as corroboration. It was one method applied twice. **Before counting an agreement as
  independent, ask whether the two parties used the SAME instrument** - and when they did, say so, because
  an accidental duplicate is not a replication. (The same applies to the eleven-arm digest agreement
  reached by two sessions today: real as a cross-check, but unplanned, and not presented as a planned
  replication.)
- *** WHEN AN INSTRUMENT IS FOUND UNSOUND, RE-ESTABLISH EVERYTHING IT ESTABLISHED. *** The MRO walk that
  produced the false absence had ALSO produced the claim that rung 3 reads no KV telemetry and therefore
  does not wait on E1 - the claim that LICENSES the kv0.5r rung-3 cells. That was re-done on a
  composition-aware walk with a stated terminus: six modules in rung 3's actual chain
  (`arms_v5rules2`, `hybrid/hybrid_arm`, `arms_v6state`, `arms_v6fair`, `arms_final_ladder`,
  `arms_v6fairfeed`), **ZERO references to `gpu_kv_fraction` / `kv_cache_usage` / `scrape_metrics`**, and
  `hybrid_arm.py` composes nothing further (no `self._base` / `self._rules`), so the chain ends there.
  **Conclusion unchanged, foundation replaced** - and verified independently from origin. A sound result
  resting on an unsound method is not yet a result.
- AND FOR RELAYED CLAIMS: a NEGATIVE assertion about a primary artefact is cheap to check and expensive
  to propagate. Three were relayed unverified today (a loadavg precedent that did not exist, a
  touch-price magnitude off by about 26x, and two metric names that did exist). Check a negative against
  the artefact BEFORE passing it on, and send the command and its output with it.


- ALONE GUARDS ARE UNRELIABLE. Three sessions found theirs blind to processes they had no name for, each
  bounded differently (a tree snapshot, a `"one_cell"` pattern, a hardcoded basename list). COUNT LIVE2
  PROCESSES BY WHAT THEY ARE (an interpreter plus a path under the repo or a scratchpad tree, or
  enumerate `/proc/<pid>/cwd`), NEVER by a name pattern, and record the census and loadavg BESIDE the
  boolean. A `/proc` matcher hits your OWN SHELL on a READ-ONLY SCAN, so the hazard is in the MATCHER,
  not the kill; never `pgrep -f`/`pkill -f` on a self-matching pattern (exit 144).
- THE SHARED WORKTREE IS NOT SAFE FOR CELLS. Run every proof cell from a PRIVATE `git archive` of ONE
  LITERAL SHA and cmp-check `arms.py`, `coordinator.py` and `v5/cf_objective.py` inside the archived
  tree first; `arms.py` and `coordinator.py` are in every arm's import graph.
- RE-RESOLVE `origin/main` TO ONE LITERAL SHA IMMEDIATELY BEFORE COMMITTING. Origin moved more than
  thirty times today and a split ref silently reverts another session's files with a CLEAN FAST-FORWARD
  at push time.
- DO NOT ASSERT AN ABSENCE FROM A TRUNCATED VIEW. A `head -40` grep produced a false "the engine emits
  neither key" claim, and I relayed it. Include the exact command and its output with any absence claim.
- A BAR IS ONLY COMPARABLE WITHIN ONE RECIPE, and every bar-table row now carries the commit that
  produced it and the ruled fixes it predates (D217 (4)).

## WHAT IS ACTUALLY LEFT FOR A RESUME, 2026-11-24 01:55 PST

*** EVERY STEP THAT CAN PROCEED WITHOUT A USER RULING IS EITHER DONE OR RUNNING. DO NOT START WORK
LOOKING FOR SOMETHING TO DO; READ THIS LIST FIRST. ***
- **Step 1 DEVICE_ANSWERS: DONE and STOPPED on its pre-registered condition** (1x count is 1). Awaiting
  the user.
- **Step 2 E1: IMPOSSIBLE AS WRITTEN.** The scrape has zero callers; there is no switch whose flip
  reaches a decision. Awaiting the user on the wiring.
- *** STEP 3 item 3: THE SWEEP IS FINISHED AND IT PASSES. 24 of 24 arms IDENTICAL, 0 MOVED, both
  prechecks identical, positive control matched the committed `af8befb9420ad86a`. Driver exited AFTER
  writing its result, which is COMPLETION. Verdict and the raw file are committed at
  `results/orchestration/live2/d213_metrics_scrape/item3_belief_prefix_byte_identity.json` and
  `item3_digests_RAW.json`. *** SUPERSEDED: THE CODE *IS* LANDED. See the correction immediately below. *** ***
  **READ THE VERDICT FILE, NOT THE RAW ONE: the raw result's `fix_in_B`, `B_is` and
  `what_this_cannot_show` ARE STALE E1 METADATA** and say the change under test was `asyncbackend.py`.
  It was not. E1 is already on origin so BOTH trees carry it (`asyncbackend.py` byte-identical in A1 and
  B1), and `diff -rq A1 B1` names EXACTLY ONE differing file: `coordinator.py`, +52 lines, the
  `_belief_prefix_record()` method plus its call site at `:2138`. Verified by diffing the trees.
  **THE REGISTER OF THE 24 OF 24 IS NARROWER THAN IT LOOKS:** the method's first statement is
  `if self.dry_run: return SC.asdict(SC.Belief())`, so the dry VALUE is unchanged BY CONSTRUCTION. What
  the sweep does prove, and it is not a tautology, is that adding 52 lines to `coordinator.py` perturbs
  no dry decision of any of 24 arms THROUGH THE ALLOCATION-ORDER CHANNEL that moved an arm by 85
  decisions on a comment-only edit earlier tonight. **IT DOES NOT PROVE THE LIVE RECORDING IS
  DECISION-NEUTRAL**: no live cell ran, and that rests on a code-reading argument (`_log_decision` runs
  after the action is chosen; the only reader of `DecisionRecord.belief` is the offline
  `d211_signal_a_available.py`). ARGUED, NOT MEASURED.
  *** AND A FINDING BIGGER THAN ITEM 3, FROM THE PATCH'S OWN DOCSTRING: D211 SIGNAL (a) WAS NEVER
  COMPUTABLE ON ANY COMMITTED CELL. *** `belief.gpu_tokens_by_session` is logged on every decision row
  and was **EMPTY ON ALL 16,840 ROWS of the committed rung-3 cell**, because its only producer
  (`arms_policy.py:1067-1075`) is NEVER ENTERED BY THE LADDER. So only signal (b) could ever have been
  validated, and this file's earlier framing that signal (a) merely "lacked a 1x live cell"
  UNDERSTATES it: the field was STRUCTURALLY EMPTY, not just late.
  *** CORRECTED 2026-11-24: ITEM 3 IS LANDED AND WIRED. THIS IS NO LONGER THE NEXT STEP AND NO LONGER
  NEEDS A RULING. DO NOT LAND IT AGAIN AND DO NOT ASK THE USER ABOUT IT. *** Verified on origin, not
  taken on report:
    `coordinator.py:2138`  `belief=(preds.get("belief") or self._belief_prefix_record()),`   <- CALL SITE
    `coordinator.py:2148`  `def _belief_prefix_record(self) -> Dict[str, Any]:`              <- METHOD
    `56a73293` is an ANCESTOR of origin/main, and the verdict file
    `d213_metrics_scrape/item3_belief_prefix_byte_identity.json` is on origin.
  The "worktree's live uncommitted edits" that this entry worried about were STALE, NOT LIVE: the shared
  worktree runs ~1,678 commits behind, and its `coordinator.py` holds ZERO lines origin lacks (mtime
  2026-11-22). That reading is the same coarse concurrency test this file corrects three times above.
  *** AND IT CLOSES THE SIGNAL-(a) GAP THAT THE ENTRY ABOVE CALLS "BIGGER THAN ITEM 3", which is worth
  stating because the two sit side by side and read as unrelated. *** The landed method's own docstring
  names the same defect - `belief.gpu_tokens_by_session` EMPTY on all 16,840 rows of the committed
  rung-3 cell because its only producer `arms_policy.py:1067-1075` is never entered by the ladder - and
  then SUPPLIES the value as a FALLBACK: `min(built_tokens, est_tokens)` filed under the session's
  CURRENT BELIEVED TIER, with `preds["belief"]` still winning wherever an arm supplies one, so nothing
  that already fills the field changes. **SO SIGNAL (a) IS COMPUTABLE FROM NOW ON AND ON NO COMMITTED
  CELL**, since all twelve ladder cells predate it. The remaining limit is unchanged and still ARGUED
  RATHER THAN MEASURED: the record is LIVE-CELL ONLY by design (dry returns `asdict(Belief())`, because
  filling it dry would move every arm's dry digest), so the 24-of-24 dry sweep proves the 52 added lines
  perturb no dry decision through the allocation-order channel, NOT that the live recording is
  decision-neutral. **THAT is the only part a live cell would settle, and it is a much narrower question
  than "should we land it".**

  [SUPERSEDED, KEPT FOR THE TRAIL:]
- **Step 3 item 3: ITS BYTE-IDENTITY SWEEP IS RUNNING. DO NOT RE-LAUNCH AND DO NOT START A DRY CELL.**
  Verified at 01:52 PST: pid 378337 `d213_digest_driver.py --out out/item3_digests.json`, 58 minutes
  elapsed, `00:00:00` OWN CPU, **with a LIVE CHILD** pid 388608 running
  `cf_pd_one_cell.py --arm attentionstore-prefetch --seed 4 --n 16 --run-s 1200 --cutoff-off` at 2:43
  CPU. Per this file's own final discriminator that is a WORKING ORCHESTRATOR, not a hang. loadavg 1.21.
  **THE ALONE RULE THEREFORE BINDS.**
  *** AND YOU DO NOT HAVE TO WAIT FOR `out/item3_digests.json` TO CHECK THE ESCALATE CONDITION. The
  per-cell log `out/item3_digests.log` carries one JSON object per cell with `tag` (A or B), `arm`,
  `digest`, `rows`, `error`, `alone` and `loadavg_start`, so the A-versus-B identity is computable from it
  AT ANY POINT, and the sweep's evidence SURVIVES A DRIVER DEATH even if the result file is never
  written. *** Group the log by `arm`, require `digest` AND `rows` equal between the `A` and `B` rows, and
  escalate on any pair that differs: item 3 is LOGGING ONLY, so every pair MUST match.
  *** THE EXPECTED ARM COUNT IS 24, NOT 20, AND THE LIST IS NOT ALPHABETICAL AT THE END. DO NOT READ AN
  ABSENT RESULT FILE AS A DRIVER DEATH BEFORE ALL 24 ARE PAIRED. *** `d213_digest_driver.py:93` takes its
  set as `list(RUNGS) + list(BASELINES)` when `--arms` is not given: **7 RUNGS** (`covex-v6-base`,
  `covex-v6-rules`, `covex-v6-state-uo`, `covex-v6-state-uo-c5attr`, `covex-v6-fair-c5attr`,
  `covex-v6-cf-c5attr`, `covex-v6-cf-pd-c5attr`) and **17 BASELINES**, whose last four are
  **`kvflow-prefetch`, `cascade-routing`, `device-only`, `v5-rules-2`** - AFTER `warm-all-lru`.
  **THE TRAP, WHICH I NEARLY WALKED INTO AND CHECKED INSTEAD:** the BASELINES list runs alphabetically
  from `always-cloud-fcfs` to `warm-all-lru` and THEN STOPS BEING ALPHABETICAL, so a reader who sees
  `warm-all-lru` logged and 20 arms seen will conclude the sweep is on its LAST arm and that a missing
  `item3_digests.json` means the driver died at the end. **IT DOES NOT: four arms remain, roughly nine
  cells, about 25 minutes.** Count the arms against 24 before diagnosing anything.
  *(`cascade-routing` and `device-only` being in the sweep is correct and not a scoring question: a
  byte-identity sweep tests NON-INTERFERENCE, and `cascade-routing`'s port-rule exclusion governs whether
  it is SCORED, not whether item 3 may perturb it.)*
  **MEASURED AT 02:50 PST: 43 cells, 20 arms seen, 19 fully paired, 0 MOVED, 0 errors, `warm-all-lru`
  half-done.** Still no escalation.
  **MEASURED THIS WAY AT 2026-11-24 02:20 PST, mid-sweep: 14 arms with both sides done, 0 MOVED, 0
  errors, so no escalation up to that point.** `alone` is False on every cell (loadavg_start 0.39 to
  1.56), which is the known and recorded not-alone caveat and weakens the ALONE claim rather than the
  identity conclusion, since A and B agreeing bit-exactly under varying load is direct evidence of
  determinism.
- **Step 4 the 0.25x pair: BLOCKED ON THE USER**, and the DA live pair additionally cannot be posted as
  is, because `covex-v6-final-da` does not resolve on the normal import path.
- **Step 5: DONE.**
- **The CLAUDE.md closeout for StudyLADDER-FINAL is COMPLETE** (EXPERIMENTS row, INDEX row, STATUS
  section). Nothing is owed there.
*** SO IF YOU ARE A RESUME WITH NOTHING ASSIGNED: THE CORRECT ACTION IS TO VERIFY THIS FILE IS STILL
ACCURATE, CHECK WHETHER ITEM 3's SWEEP HAS LANDED ITS RESULT, AND OTHERWISE REPORT AND STOP. DO NOT
INVENT WORK, DO NOT TOUCH A RUN-PATH FILE, AND DO NOT DECIDE ANY OF THE FIVE OPEN RULINGS. ***

## OPEN, NEEDING A USER RULING

*** EXTENDED 2026-11-24 over `results/` and `reports/` as suggested below. NO NEW UNLISTED RULING: the
dozen-odd hits there all REFERENCE rulings already made (dated 2026-11-16, -17 and -22) or are
historical. BUT IT TURNED UP SOMETHING BETTER - A CONSTRAINT ON STEP 4 THAT WAS A FRAMING AND IS NOW A
NAMED READ. ***
`d216_final_kv025/d216_digest_crosscheck_0ce3c2.json` records that **RUNG 3 DOES NOT MOVE WITH MEMORY AT
ALL**: 1x, kv0.25, and kv0.25 with coordinator eviction ENFORCEMENT ON give **ONE digest and one row
count, byte for byte** (`5a03c2807da3681a` / 14,539), and it is scrupulous that *"A RUNG-3 0.25x DRY CELL
MUST NOT BE REPORTED AS A MEMORY RESULT... that flat response is UNEXERCISED, not an equivalence"*, and
consistent with the ruled framing that rungs 2 and 3 adapt to memory **only reactively, through engine
telemetry**, where rung 4 adapts proactively.
*** I TRACED THAT FRAMING TO ITS READ, WHICH IS THE PART THAT WAS MISSING (CLAUDE.md Step 2). ***
  `gpu_kv_fraction` in `arms_v6fair.py`, `arms_v6state.py`, `release_recheck.py`, `hybrid/hybrid_arm.py`,
  `arms.py`, `arms_v6c5.py`: **ZERO in every one.** So rung 3 reads NO KV telemetry anywhere in its
  inheritance chain - the hit-6 census was right that only rung 4 inherits it.
  `latency_estimate_s`: **ONE occurrence, in `hybrid/hybrid_arm.py`**, which rung 3 inherits through
  `V5Rules2Arm`. **THAT IS RUNG 3's ONLY ENGINE-TELEMETRY CHANNEL** - an EWMA of MEASURED TTFTs, not a
  KV gauge.
*** THE CONSEQUENCE FOR STEP 4, AND IT STRENGTHENS ITS DESIGN RATHER THAN UNDERMINING IT: *** step 4
specifies the REAL ENGINE POOL (`--num-gpu-blocks-override 985`), and that requirement is LOAD-BEARING,
not incidental. A dry 0.25x cell cannot move rung 3 at all, because `--kv-scale` changes the LOGICAL
coordinator pool while the dry engine's service times come from a frozen model, so the only channel rung
3 has sees nothing - and `self._caps` (`arms.py:82`) is a write with no read repo-wide, so the arms
cannot see the configured pool either. **ON A REAL ENGINE AT 0.25x THE SERVER ACTUALLY SLOWS UNDER KV
PRESSURE, WHICH IS WHAT `latency_estimate_s` CAN SEE.** So: do NOT substitute a dry cell for step 4's
rung-3 half, and if anyone reports a flat rung 3 from a dry 0.25x cell, that is UNEXERCISED and not a
finding.
**WHAT IS STILL UNTESTED, STATED SO IT IS NOT READ AS MORE THAN IT IS:** that `latency_estimate_s`
ACTUALLY responds enough to move a rung-3 decision at 0.25x is ARGUED FROM THE READ, NOT MEASURED. No
live 0.25x rung-3 cell has ever run. **That is precisely what step 4 would establish**, which is a better
reason to run it than the one originally given.

*** THE SEARCH FOR UNLISTED DECISIONS IS DONE. DO NOT REPEAT IT; EXTEND IT INSTEAD. ***
A resume with spare capacity kept finding that the costly errors were in THIS FILE rather than in the
results, so the method became: grep the code for decisions it DEFERS TO THE USER, then check whether
anyone ever asked. **SIX CANDIDATES EXAMINED, TWO WERE GENUINELY UNLISTED AND ARE NOW ABOVE.**
  `git grep -ihoE "(is|remains) a user ruling|the user's (call|ruling)" origin/main -- experiments/`
  ADDED: **the harm form** (`cf_protect_defer.py`'s `HARM_FORM_NOTE`: "the choice is a user ruling, not
    this module's") and **the r2 queue register** (`d187_r2_queue_register_diagnosis.py:1076`: "THAT IS
    THE USER'S CALL and is not decided here").
  EXAMINED AND DELIBERATELY **NOT** ADDED, with the reason, so the judgement is auditable:
    - `arms_v6fair.py:67`, D170 OFF for rungs 0 to 2. The comment documents the default AND its
      number-neutrality, and that neutrality is a fact INDEPENDENTLY VERIFIED here: all 18 over-limit
      questions are at seed 7 and `covex-v6-fair-final` declined every one (identical set, checked
      against `d170_overlimit.json`). It is about a VERSION LABEL, not a number.
    - `experiments/orchestration/policy/closed_form.py:6`, "Acceptance is the user's call after the H100
      pilot". A REAL open decision but PROPERLY TRACKED - 3 mentions in `research/EXPERIMENTS.md`, 1 in
      `research/policy_design_log.md`, pre-registered in `reports/study_live2_perf.md` section Option B,
      **OFF BY DEFAULT and enabled nowhere** (`Coordinator.sh_cost` defaults to "rollout"), which is
      D187-compliant. It belongs to a different workstream and gating it here would only duplicate it.
    - `hybrid/policy_f_proofs.py:13` and `fleet/data_sources.py:177` reference rulings ALREADY MADE
      (the freeze ruling, and the part-1 D81 to D94 rulings), so they are historical, not open.
**THE LESSON WORTH KEEPING: a decision the code reserves to the user is not thereby ON a list, and two of
six were not.** Both of the two found govern how rung 4 is READ rather than any number, and both were
sitting in a docstring that every reader skips. If a later resume wants more of this, the productive
direction is NOT re-running the same grep: try `NOT APPLIED`, `RECOMMENDED`, `ESCALATE`, `is owed` and
`not decided` over `results/` and `reports/` as well, which this pass did not cover.

- *** THE r2 QUEUE REGISTER: KEEP A CORRECT INPUT THAT COSTS 16 ROBOT ANSWERS, OR KEEP r1? NEW TO THIS
  LIST 2026-11-24. ITS OWN DIAGNOSIS DEFERS IT TO THE USER AND IT APPEARS IN **NO** OPEN LIST. ***
  Found by the same search that surfaced the harm form: code that says "the user's call" and is nowhere
  asked. `d187_r2_queue_register_diagnosis.py:1076`, verbatim: *"Keeping a correct input that costs 16
  robot answers at the primary seed is a trade-off, not a cleanup. **THAT IS THE USER'S CALL and is not
  decided here.** r1 IS THE BEST SHARES VERSION on the evidence in these cells."*
  Mentions: handoff **0**, `policy_design_log.md` **0**, `EXPERIMENTS.md` 1 (StudyD179-SHARES, whose
  verdict opens "No policy result yet" and whose status settles a DIFFERENT question, "c5attr IS RUNG 2").
  **THE MEASURED TRADE**, from the committed diagnosis: r2 is the CORRECTLY computed queue term and it
  made s4 WORSE - robot on time **95 to 79**, retention **0.7229 to 0.5301**,
  `release_infeasible_recall` 34 to 47, `share_deny_recall` 467 to 643. s6 is UNCHANGED (92 on-time under
  both). Its mechanism is traced, not guessed: r2 feeds a SMALLER queue term, so the re-check admits more
  work earlier, recall-type gate calls rise 2,442 to 3,246 at s4, and the D179 (3) oversize SERIALISATION
  rule then denies more (`oversize_wait_for_own_type` 444 to 615, which is 171 of the 176 rise).
  *** THE TENSION THAT MAKES THIS A RULING AND NOT A DEFAULT, AND IT SHOULD BE STATED WHEN IT IS
  DECIDED: *** D187 says **NEVER TUNE A PARAMETER TOWARD PASSING**. Preferring r1 BECAUSE IT SCORES
  BETTER, when r2 is the more correct input, is adjacent to exactly that. It is not literally a parameter
  tune - it is a choice between two implementations - but "keep the less correct input because the
  numbers are kinder" is the shape D187 exists to catch, so it needs an explicit decision on the record
  rather than a silent default. The diagnosis is scrupulous about this and says so in its own words: *"A
  correct input and a useful lever are not the same proposition... Reporting them together as one verdict
  is the register error this project keeps hitting in the other direction."*
  *** SCOPE, VERIFIED, SO THIS IS NOT A CAVEAT ON THE HEADLINE: IT DOES **NOT** TOUCH THE FINAL
  LADDER. *** `arms_final_ladder.py:210` sets `R4_BASE_KEY = "fair_final"`, used at `:222`, so rung 4's
  base is the rung-3 arm and NOT the shares line; `state-shares` appears **ZERO** times in all four
  committed `covex-v6-final` cells; and a reconstructed rung-4 run reports `"base_key": "fair_final"`.
  **So the ladder result (rung 3 4-of-4, rung 4 1-of-4) stands whichever way this is ruled.** It governs
  the SHARES line only, which has no committed policy result yet.

- *** THE HARM FORM. NEW 2026-11-24, AND IT IS LOGICALLY PRIOR TO THE DEVICE_ANSWERS RULING AND TO ANY
  READING OF RUNG 4's COUNTERFACTUAL. THE CODE ITSELF SAYS THIS IS A USER RULING AND IT HAS NEVER BEEN
  PUT TO THE USER. ***
  `cf_protect_defer.py`'s committed `HARM_FORM_NOTE`, verbatim at the end: *"Both are computed and
  reported; the default is the one whose units match the bar, and **THE CHOICE IS A USER RULING, NOT THIS
  MODULE'S**."* It is absent from the open-rulings list until now, and `device_discount` appears **ZERO
  times** in `research/policy_design_log.md`, so it has never been ruled, recorded as open, or numbered.
  **THE TWO READINGS.** `on-time-cloud` is D177's currency and the unit `MARGIN_CF_ON_TIME` is expressed
  in: a displaced request loses `w_j x (p_before - p_after)` on-time CLOUD answers. `device-discounted`
  multiplies each row by `(1 - p_device_on_time_j)`, the literal reading of D165 (B)'s "a question whose
  device answer was already on time loses nothing when the cloud answer is late".
  **WHY THE CHOICE IS NOT COSMETIC, FROM THE MEASURED TABLES** (`v5/cf_objective.py:120-135`, verified):
    robot       0.2503 to 0.3108 s over 97 LH-REQ questions, INSIDE every deadline under test (2.5 to
                5 s), so **`p_device_on_time` is 1.0 on EVERY robot decision**
    dashcam     0.2349 to 0.3169 s over positions 1 to 21, inside a 1 s deadline at every position, so
                1.0 there too (**the EPISODE START curve reaching 1.88 s is the exception worth noting**)
    single_shot **HERE IT VARIES: 45.5 percent of refspatial questions give `p_device_on_time` = 0**
  **SO UNDER `device-discounted` THE HARM OF DISPLACING AN ALERT OR A RECALL IS EXACTLY ZERO, AND THE
  WHOLE PROTECT-AND-DEFER COMPOUND COULD ONLY EVER FIRE ON ASSISTANCE.**
  *** WHAT IT DECIDES, WHICH IS MORE THAN DEVICE_ANSWERS: ***
    (a) **THE DEVICE_ANSWERS 1x COUNT BECOMES 0 AND THE STOP CONDITION WOULD NEVER HAVE FIRED.** The one
        1x denial's traced record reads `harm 5.295616144403798` with `harm_device_discounted: 0.0`
        (independently reproduced, `d39797c0`). So settling this may DISSOLVE the adoption question
        rather than inform it, and it should be settled FIRST.
    (b) **THE s4 AND s7 BAR CROSSINGS BECOME 0 TOO**, so rung 4's Rule 2 class would move from
        UNEXPRESSIBLE at those seeds to UNEXERCISED at all four. The s4 trace reads `harm 1.638113`
        against `bar 1.452307` with `harm_device_discounted: 0.0` (`fbd2f64b`'s A cell).
    (c) It therefore governs how the whole rung-4 counterfactual is reported, not one candidate.
  *** AND A DISTINCTION THE CODE DRAWS THAT ANY WRITE-UP MUST KEEP: *** `cf_objective.py:122-125` says
  `p_device_on_time` is "CONSTANT **BECAUSE THE DEVICE IS FAST**, which is a measured fact, and no longer
  constant because the input was a flat proxy, which was an artefact. **The two look the same in the
  output and are not the same claim.**" So the zeros under `device-discounted` are a REAL PROPERTY OF A
  FAST DEVICE, not an instrumentation defect - which is exactly why this is a ruling and not a bug.
  **NOTHING IS BUILT OR CHANGED PENDING IT.** Both forms are already computed and reported side by side
  on every decision, so whichever way it goes, no code change and no rerun is implied by the ruling
  ITSELF; what may follow is a change in which number is quoted.

- *** THE D209 PROOF-LOAD TWIN FOR THE n20 CELLS IS A DIFFERENT ARM, AND ITS `twin_note` SAYS "THE SAME
  ARM". FOUND 2026-11-24 ON `3b95abd1`. THE CELL IS ALREADY `reportable: False`, SO NOTHING PUBLISHED IS
  AFFECTED - BUT THE TWIN LOGIC WILL BE REUSED FOR MORE n20 CELLS. ***
  `covex-v6-base_n20_s4_1200s_h27_3t_L3_epg_rq30`'s `proof_load_d209` block records
  `twin = hybrid-F-lhreq-noc3_n16_s4_1200s_h27_3t_L3_epg_rq30` with
  `twin_note = "the twin is the committed 16-device 3 s 1x cell of the same arm and seed"`.
  *** THIS ITEM IS RESOLVED, 2026-11-24 02:05 PST, AND IT RESTED ON TWO FALSE CLAIMS, ONE OF THEM MINE.
  IT SHOULD NO LONGER SIT IN THE USER'S OPEN-RULINGS LIST AS WRITTEN. ***
  **FALSE CLAIM 1, THE PREMISE: `covex-v6-base` AND `hybrid-F-lhreq-noc3` ARE NOT DIFFERENT ARMS. THEY
  ARE ONE ARM UNDER TWO NAMES**, so the `twin_note` saying "the same arm" was CORRECT and the objection
  was unfounded. Verified in the registry at `experiments/orchestration/live2/arm_names_v6.py:39-41`:
  `{"rung": 0, "name": "covex-v6-base", "implemented_by": "hybrid-F-lhreq-noc3",
  "committed_as": ["hybrid-F-lhreq-noc3"]}`, with `OLD_TO_RUNG` at `:71` mapping
  `"hybrid-F-lhreq-noc3": "covex-v6-base"`. Independently, `experiments/analysis/figdata/figdata.py:65`
  pairs them in one row: `("base", "hybrid-F-lhreq-noc3", "covex-v6-base", "development", "rung0")`.
  **FALSE CLAIM 2, ITS SUPPORT: the ladder's positive control does NOT treat them as two cells.** Read
  from `d208_final_s7_verdict.json`: `positive_control` is PASS with `n_pass: 2` and its two control arms
  are **`covex-v6-fair-final` and `hybrid-F-lhreq-noc3`** - the arm under test and the base, two genuinely
  different arms. `covex-v6-base` does not appear in it.
  **AND A CORRECTION OF MY OWN OVER-CLAIM, made while arguing the right conclusion from the wrong
  evidence:** I told the H100 that `covex-v6-base` "OCCURS NOWHERE BUT `arm_names_v6.py`". **THAT IS
  WRONG: it occurs in 58 other files under `experiments/`.** They are EXPECTED-DIGEST LOOKUP TABLES keyed
  by the ladder name (`d178_deficit_feed_proofs.py:80`, `d190_rung4_r3_proofs.py:29`,
  `d209_make_tables.py:12`, `d210_kv025_report.py:48` and others, all carrying
  `af8befb9420ad86a` / 12,085) plus the figdata row above, and NONE registers an arm factory - so the
  conclusion survives, but **I reached it from a grep restricted to THREE FILES and generalised to
  "nowhere", which is the same restricted-view absence error this file warns about twice.** The
  conclusion rests on the REGISTRY FIELDS, not on that grep.
  **THE FIX IS ALREADY APPLIED BY THE H100, SO NOTHING IS OWED.** The newest n20 cell,
  `covex-v6-rules_n20_s4_1200s_h27_3t_L3_epg_rq30` (landed 01:57 PST), carries
  `twin = v5-rules-2_n16_s4_1200s_h27_3t_L3_epg_rq30` with
  `twin_note = "the twin is the committed 16-device 3 s 1x cell of the same arm and seed (for
  covex-v6-base / covex-v6-rules it is that arm under its committed name, hybrid-F-lhreq-noc3 /
  v5-rules-2 ...)"`. So the twin logic now NAMES the two-names relationship explicitly, which is exactly
  the remedy recommended below.
  *** WHAT GENUINELY REMAINS, NARROWED FROM THREE CONFLATED CHANGES TO TWO: the ratio still conflates
  FLEET SIZE (16 to 20) AND LOAD, so it still CANNOT be read as a load effect, and
  `decision_p99_up_gt_10pct` is still not evidence of load inflation. The ARM conflation is GONE. ***
  `reportable: False` continues to do the protective work (the new cell is also `reportable: False` at
  `decision_p99_ratio = 2.102`). A same-arm same-FLEET twin would be needed to isolate load, and for
  `covex-v6-base` no such n16 cell exists in this condition; that limitation is unchanged and is a
  property of what was run, not a defect in the note.

  [SUPERSEDED BELOW, KEPT FOR THE TRAIL. DO NOT ACT ON IT.]
  **THOSE ARE DIFFERENT ARMS.** `covex-v6-base` and `hybrid-F-lhreq-noc3` are scored as distinct arms all
  night (the ladder's positive control treats them as two cells).
  **THE SUBSTITUTION WAS NECESSARY, SO THIS IS NOT CARELESSNESS:** there is NO
  `covex-v6-base_n16_s4_1200s_h27_3t_L3_epg_rq30`. Verified by listing all 14 committed `covex-v6-base`
  dirs: the n16 s4 ones are `kv0.25`, `kv0.5` and `L2.5` variants, all different CONDITIONS, and the only
  same-arm same-condition cell at another fleet size is `covex-v6-base_n12_s4...L3_epg_rq30`.
  *** THE CONSEQUENCE, WHICH IS THE PART TO WRITE DOWN: `decision_p99_ratio = 2.145` CONFLATES THREE
  CHANGES AT ONCE - ARM, FLEET SIZE (16 to 20) AND LOAD (`loadavg_1m` 50.89, `other_cpu_cores` 46.257).
  SO IT CANNOT BE READ AS A LOAD EFFECT, AND THE `decision_p99_up_gt_10pct: True` FLAG IT FIRED IS NOT
  EVIDENCE OF LOAD INFLATION. *** No available twin isolates load for this arm, because the same-arm
  same-condition n16 cell does not exist; the n12 cell would at least hold the ARM fixed at the cost of a
  bigger fleet jump. **RECOMMENDED, NOT APPLIED: either name the n12 same-arm cell and say the fleet jump
  is 12 to 20, or keep this twin and change the note to say plainly that the ratio spans an ARM CHANGE
  and is therefore NOT a load measure.** The honest version of that field is more useful than a tighter
  ratio.
  **WHAT IS WORKING AND SHOULD NOT BE CHANGED:** `host_load_peak` carries MAGNITUDES
  (`loadavg_1m: 50.89`, `other_cpu_cores: 46.257`) rather than a boolean, which is the convention
  adopted after the false "loadavg 20.13" claim, and `reportable: False` is doing the real protective
  work here.

- *** A FIGURE'S README MISSTATES WHICH CELLS IT USED. FOUND 2026-11-24 ON THE D192 FIGURE COMMITS
  (`c6ceb5a8`, `9346ba32`, `30f2be8d`). THE DATA IS CORRECT; THE PROSE IS WRONG. NOT FIXED BY ME,
  BECAUSE THE USER WAS COMMITTING IN `reports/figures/` AT THE TIME. ***
  `reports/figures/episodic_scores_README.md` says the build prefers the `_rerun` directory
  "(which supplies always-cloud-fcfs s5, covex-v6-state s4, v5-rules s7)". **THAT PARENTHETICAL IS
  HARDCODED PROSE** in the generator at `experiments/analysis/episodic/build_episodic.py:177-178`, NOT
  derived from the run. The per-row truth IS computed, at `:93` as `"cell_used_rerun": rr`, and the
  committed CSV disagrees with the prose TWO WAYS:
    - it names `covex-v6-state s4` and `v5-rules s7` as rerun-supplied. **MEASURED: `rules` seeds 4-7
      and every `state-*` row are `cell_used_rerun=False`.** Only FIVE rows in the whole CSV are True.
    - **it OMITS the four rows that ARE True: `simplestream` s4, s5, s6 AND s7**, plus
      `always-cloud-fcfs` s5 which it does name correctly.
  *** WHY THIS MATTERS MORE THAN A TYPO: THE SIMPLESTREAM RERUNS ARE A CODE FIX, NOT A RE-RUN OF THE
  SAME CODE. *** They are the hit-7 cells (robot frames per RECALL send 6 -> 1, confirmed live at 132 of
  132), and the fixed-window cells they replace are SUPERSEDED in INDEX. So the README omits exactly the
  substitution a reader most needs to know about, and names two it did not make. By contrast
  `always-cloud-fcfs` s5's rerun is BENIGN and I verified why: the original
  `always-cloud-fcfs_n16_s5_1200s_h27_3t_L3_epg_rq30` has **NO `cell.json` and NO `run_meta.json`**, so
  it is an incomplete cell, and the rerun is not anomalous (that arm carries 37 / 64 / 12 / 33 errors at
  s4-s7, all `run_valid=True`, all `is_measurement=False`).
  *** APPLIED 2026-11-24 02:15 PST at `e248ca1d`. THIS ITEM IS CLOSED; DO NOT RE-FIND IT. *** The
  contention that blocked it has cleared (neither file has uncommitted edits in either worktree, and
  `build_episodic.py` has ZERO importers outside its own directory, so it is not a live-path file). The
  sentence is now DERIVED from `rows`, which `write_readme` already receives, and the committed README
  prose is corrected to the same derived text. **THE DERIVATION WAS VERIFIED BEFORE IT WAS INSTALLED:**
  run against the committed `episodic_scores.csv` it yields "always-cloud-fcfs s5, simplestream s4,
  simplestream s5, simplestream s6, simplestream s7", matching the computed column EXACTLY, and the patch
  script refuses to install it otherwise. Re-measured at the same time: the old prose named **2 pairs that
  are NOT reruns** (`covex-v6-state` s4, `v5-rules` s7) and **omitted 4 that ARE** (`simplestream` s4 to
  s7); 5 of 96 rows are True. **THE CSV IS UNCHANGED and must stay so: the CSV was always right.**
  **THE LIMIT, STATED:** the expression was checked against the committed CSV, where the column is a
  string and is coerced, NOT by regenerating the README, because a full build would write figure outputs
  while item 3's sweep is in flight. In process the column is a real bool, so truthiness behaves
  identically.

  [SUPERSEDED, KEPT FOR THE TRAIL:]
  **RECOMMENDED FIX, NOT APPLIED: derive that sentence from the computed `cell_used_rerun` column rather
  than hardcoding it**, so it cannot drift again. One line in the generator. **DO NOT "fix" the CSV: the
  CSV is right.**
  *(The general shape, for the catalogue: A HARDCODED PROSE CLAIM SITTING BESIDE A COMPUTED COLUMN THAT
  CONTRADICTS IT. The prose is what a reader trusts and the column is what is true, and nothing in the
  pipeline compares them. Same family as a stale docstring, except it is regenerated on every build, so
  it looks freshly verified.)*

- **E3, one line**: `run_live2_real.py` builds `cell.json` from a fixed key list and `metrics_health`
  appears nowhere in it, so a cell with failed metrics fetches does not say so. The fix is
  `out["metrics_health"] = (res.get("backend") or {}).get("metrics_health")`. WAITS FOR A RULING.
- *** DONE 2026-11-24, `fbd2f64b`. NOT A RULING ANY MORE, DO NOT RE-DO IT. *** `cstate.py`'s TWO stale
  state-table doc lines are corrected and PROVED DECISION-NEUTRAL. Hit 7's landing released the file.
  **BOTH LINES WERE WRONG IN BOTH HALVES.** `:16` said the in-flight bookkeeping is "cross-checked
  against `/metrics`" - nothing in any live2 cell is, since `scrape_metrics()` has zero callers. `:17`
  said "the server's `vllm:gpu_cache_usage_perc`" - the committed raw scrape
  `frozen_test/engine_probe_hit26/metrics_scrape_h100.txt` has `vllm:kv_cache_usage_perc` THREE times
  and that key ZERO times, and the field is identically 0.0 in every cell run to date because nothing
  calls the scraper.
  **PROVED, NOT ASSUMED, BECAUSE A COMMENT-ONLY EDIT HERE WAS MEASURED TO MOVE 85 DECISIONS.** A/B from
  one literal sha, differing in exactly one file by `diff -rq` with NO CODE LINES in the diff:
  **A = B = `57bed6ace2eb07d1` / 14,509 = THE POSTED COMMITTED VALUE.** Proof at
  `results/orchestration/live2/frozen_test/d216_cstate_docfix_byte_identity.json`. Zero live2 processes
  on the box, loadavg 0.22 and 0.85, recorded as magnitudes.
  *** TWO BY-PRODUCTS WORTH MORE THAN THE FIX. *** (1) **A IS A POSITIVE CONTROL THAT CONFIRMS HIT 7 AND
  ITEM 3 DECISION-NEUTRAL FOR RUNG 4**, since today's tree with both landed still reproduces the posted
  s4 digest; the A/B design was chosen over the cheaper one-cell check against that digest precisely
  because hit 7 and item 3 landed after it was posted and would otherwise have been conflated. (2) **A
  SUSPECTED SECOND DEFECT IS DISPROVED:** `cstate.py:697` reads `vllm:gpu_cache_usage_perc`, the key the
  engine does NOT emit, which looked like a second fault in series making the metrics-wiring ruling
  insufficient alone. IT IS CORRECT BY DESIGN - `adapter.py:204-205` read EITHER spelling and republish
  under the older `KV_CANONICAL_KEY` "so no reader changes", aliasing counted by `n_kv_key_aliased` - so
  **WIRING THE LINK IS SUFFICIENT ON ITS OWN.**
  *** AND ONE FACT FOR THE DEVICE_ANSWERS RULING THAT THE AGGREGATE COUNTS HID. *** The A cell's traced
  s4 bar crossing reads `harm 1.638113` against `bar 1.452307` AND
  **`harm_device_discounted: 0.0`**. So the crossing exists ONLY under the on-time-cloud harm reading and
  vanishes ENTIRELY under the device-discounted one. **THE HARM-FORM RULING DOES NOT SCALE
  DEVICE_ANSWERS' BENEFIT, IT DECIDES WHETHER THERE IS ANYTHING FOR IT TO DO AT ALL.** The crossing is
  also a genuine capacity event, not a marginal one: the rebuild needed 11,946 tokens against 11,921
  free, so it did not fit, and the gate still refused for want of a channel.
- *** D218 (1) / DEVICE_ANSWERS: THE POSTED-CELL RULING. THE TOP OPEN ITEM. *** The 1x count is 1, so
  the stop condition fired. Adopt into `covex-v6-final` (D209 (1) supersedes the posted s4 cell and rung
  4 is rerun) or keep as a separate arm (posted cell stands)? Also: which of the two parallel
  pre-registrations is the record. See step 1 above.
  *** THE IMPLEMENTATION IS NOW PRESERVED IN GIT, HELD AND NOT APPLIED, AT
  `experiments/orchestration/live2/held/d218_device_answers/` (`f097f5d3`). DO NOT REBUILD IT. *** It had
  NEVER BEEN COMMITTED: its session stood down without committing code, so only the report and the
  pre-registrations were in (`4f317e1f`) and **the implementation existed solely in a scratchpad the
  environment warns a cleanup can clear** - on the night it was written the disk hit 100 percent and a
  7 GB cleanup came within one deletion of destroying another session's only held wiring. Nine files,
  120 KB: three `.patch` files against the committed tree (`arms_v6cf.py` +137 lines,
  `cf_protect_defer.py` +260, `coordinator.py` +2), **each VERIFIED to reproduce the author's working
  tree byte for byte**, and five `.held` files (the DA arm module `arms_v6cf_device.py`, the driver, the
  one-cell runner, the mechanism tests, the author's patch script), plus a README.
  **NOTHING IS ON THE IMPORT PATH AND THE RULING IS NOT PRE-EMPTED:** every file carries a `.patch` or
  `.held` suffix so it cannot be imported or caught by a glob (the D214 precedent), and
  `covex-v6-final-da` still has **ZERO references** in `arms.py` and `arms_v6cf.py` on origin.
  **PRESERVING CODE IS RECORDING; ADOPTING IT IS THE DECISION.**
  Two cautions carried in the README: **DO NOT FORCE A PATCH WHOSE TARGET HAS MOVED** - re-derive it,
  because forcing would silently revert whatever moved it; and the later, larger set from the author's
  WORKING TREE was taken, not the earlier drafts in `scratchpad/d218/`
  (`arms_v6cf_device.py` 10,075 bytes, not the 7,743-byte draft).
  *** AND THE PREREQUISITE THE AGGREGATE COUNTS HID, WHICH SHOULD BE SETTLED BEFORE THE ADOPTION
  QUESTION: *** the traced s4 bar crossing reads `harm 1.638113` against `bar 1.452307` AND
  **`harm_device_discounted: 0.0`** (A-cell trace, `fbd2f64b`'s proof run). The crossing exists ONLY
  under the on-time-cloud harm reading and vanishes ENTIRELY under the device-discounted one, so **THE
  HARM-FORM RULING DECIDES WHETHER THERE IS ANYTHING FOR DEVICE_ANSWERS TO DO AT ALL**, not merely how
  much it gains. It is also a genuine capacity event, not a marginal one: the rebuild needed 11,946
  tokens against 11,921 free, so it did not fit, and the gate still refused for want of a channel.
- *** ANSWERED 2026-11-24 FROM THE COMMITTED LADDER CELLS. THE BELIEF CHANNEL *DOES* VARY LIVE, SO THIS
  GATE IS CLEARED AND NO LIVE CELL IS NEEDED TO CLEAR IT. *** The item below is kept for its reasoning
  but its premise is superseded; do NOT spend a cell re-deriving it.
  The `pd_` counters were IN THE COMMITTED CELLS ALL ALONG, nested inside
  `coordinator_result.json` -> `arm_stats`, NOT at top level. A probe for top-level `pd_` keys found none
  in 35 files and concluded they were uncommitted; they are committed. Read with
  `git show origin/main:results/orchestration/live2/frozen_test/runs/covex-v6-final_n16_s<seed>_1200s_h27_3t_L3_epg_rq30/coordinator_result.json`.
  MEASURED, rung 4 at 1x, ALL FOUR ladder cells:
    seed 4: free_kv 14,993 - 62,944   bound_by_belief 302/302   bound_by_engine ABSENT
    seed 5: free_kv 16,017 - 62,944   bound_by_belief 299/299   bound_by_engine ABSENT
    seed 6: free_kv 21,258 - 62,944   bound_by_belief 293/293   bound_by_engine ABSENT
    seed 7: free_kv 10,115 - 62,944   bound_by_belief 259/259   bound_by_engine ABSENT
  **SO THE BELIEF CHANNEL DETERMINES free_kv ON 100 PERCENT OF DECISIONS AND IS FAR FROM FLAT.** The
  "flat in both live cells examined" reading came from two SHORT, SMALL-ROSTER cells (one fake-server
  cell of 29 decisions). That file's own note that a 300 s dry cell was also constant over 77 decisions
  is the right explanation and it generalises: **VARIATION IS A PROPERTY OF THE CELL'S ROSTER AND
  DURATION, NOT OF DRY-VERSUS-LIVE**, and the full 1,200 s 16-device ladder cells vary in both.
  **CONSEQUENCE: "DEVICE_ANSWERS WILL NOT FIRE LIVE EITHER" IS REFUTED. A null in the live pair would
  be readable, not unreadable.** The engine channel being absent everywhere STANDS and is unaffected.
- *** AND THE SAME COUNTERS UPGRADE PROTECT-AND-DEFER'S RULE 2 CLASS FROM UNEXERCISED TO
  **UNEXPRESSIBLE** AT TWO SEEDS. *** At s4 and s7: `pd_harm_over_bar = 2`, `pd_harm_gt_0p65824 = 2`
  (the MARGIN_CF on-time bar), `pd_gate_wanted_to_act_but_a_request_has_no_slice_channel = 2` and
  `pd_request_crossed_bar_unexpressible = 2`. So the mechanism FIRED, computed a harm ABOVE its bar and
  WANTED TO ACT, and could not, because the only action is to send less and that counter's own name
  says "the latest safe start is already here and a recall query is one prompt, so there is nothing to
  send less of". s5 and s6 are genuinely UNEXERCISED (nothing crossed the bar). **THE GATE THEN NAMES
  ITS OWN REMEDY: "The registered candidate that WOULD apply is DEVICE_ANSWERS."** So DEVICE_ANSWERS is
  the exact channel the existing gate asks for by name and cannot find, and the counts AGREE ACROSS
  HARNESSES: StudyD218-DA's dry report measured that unexpressible count as 2 going to 0 at 1x, and the
  committed s4 cell independently shows 2. Full record at commit `c701f83a`.
- *** BEFORE THE PREPARED LIVE PAIR RUNS: DOES `free_kv` VARY AT ALL LIVE, THROUGH EITHER CHANNEL? ***
  `arms_v6cf.py:322` is `max(pool - max(occ_metric, occ_belief), 0)`, so free_kv has TWO channels. The
  ENGINE channel is absent everywhere (`scrape_metrics` has zero callers). The BELIEF channel was ALSO
  flat in both live cells examined (`occ_belief` summed to 0, free_kv pinned at 62,944) but VARIES in
  the D218 dry cells (8,759 to 62,944 at 1x; 0 to 15,736 at 0.25x, 188 of 260 decisions passing the
  gate). **SO IF THE BELIEF SIDE IS FLAT LIVE TOO, DEVICE_ANSWERS WILL NOT FIRE LIVE EITHER, for the
  same reason protect-and-defer does not, AND A NULL IN THE LIVE PAIR WOULD BE UNREADABLE.** This is
  TESTABLE, not speculative, and is a STRONGER gate than "is the metric scraped". Correction committed
  at `678db118`; my earlier "never reachable in any cell ever run" over-generalised from the live cells
  and is withdrawn to "not reached in any LIVE cell examined, engine channel absent in all cells".
  A detail that cuts both ways: `arms_v6cf.py:291`'s own docstring records free_kv CONSTANT over 77
  decisions on a 300 s DRY cell, so the variation is a property of the CELL'S ROSTER, not of dry vs live.
- *** DONE 2026-11-24, NOT OWED: the `results/INDEX.md` row for the completed ladder EXISTS at line 1122, and `research/STATUS.md` is updated at `5cf93024`. The text below is kept for the trail. *** `INDEX.md` has
  been DIRTY-and-differing (mid-edit by another session) at every check tonight, so appending would
  clobber that work. The row is owed, not forgotten.
- D211 signal (a) will have NO 1x live cell to validate on, because item 3 lands after the last ladder
  cell. Its validation now needs the 0.25x pair or a dedicated later cell.
