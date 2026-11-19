<!-- StudyB-baselines (D134 addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# QueryStream (ICLR 2026) — case D, D134 item 6

**Paper.** K. Zhang, Z. Yang, B. Wang, S. Qian, C. Xu, "QueryStream: Advancing Streaming Video
Understanding with Query-Aware Pruning and Proactive Response", **ICLR 2026**
(`https://proceedings.iclr.cc/paper_files/paper/2026/file/0b17d256cf1fe1cc084922a8c6b565b7-Paper-Conference.pdf`).
Its argument: existing streaming methods rely on a **query-agnostic "change-is-important"**
principle, and query-awareness should instead sit in the core of both video processing and
response scheduling. The method is **training-free**.

**Code.** `https://github.com/Zhangkr2003/QueryStreamPlus`, the authors' official repository,
which also covers the follow-up QueryStream++ extending the method to hour-scale multi-turn
streams. **Located but not cloned or opened at the time of writing**; this card and the adapted
policy are written **from the paper**. Licence not yet checked — flagged for the user, the same way
Ekya's and SimpleStream's missing LICENSE files were.

**Files.** `querystream_adapted.py`. **Experiment:** B-recall and A-episodic (it spans both; see
below).

## THE PRE-CHECK SPLIT THIS BASELINE IN HALF, AND THAT IS THE FINDING

D134 requires that before porting an arm we state **what it decides in our setting** and check
that the decision **reaches something live2 enacts** — the same read-path check that found `order`
(never read), `desired_tier` (written twice, never read) and `RecallAction.representation` (written
by arms, read by nothing). Applied to QueryStream, the check does not return yes or no. It returns
**one half each way**, and the two halves are independent mechanisms that can be ported and scored
separately.

| QueryStream mechanism | what it decides in our setting | reaches a live2 decision? |
|---|---|---|
| **Query-Aware Differential Pruning (QDP)** — filter tokens by jointly scoring semantic relevance to the query and temporal novelty | **which evidence to send**: a query-selected subset of the history instead of all of it | **NO, as of this writing.** Carried by `RecallAction.representation`, which nothing in live2 reads, while `_submit_recall` sends and charges `max(int(s.est_tokens), 1)`, the full believed history, regardless. Blocked on Part A. |
| **Proactive Response** — decide *when* to answer rather than answering on every turn | **admit now, or defer**: hold the answer until the stream has supplied enough to answer well | **YES.** Carried by the `RecallAction` decision and `defer_s`, both of which the run loop honours (D90). |

**Consequence for the port.** The Proactive Response half is portable and is ported.
The QDP half is **deferred on the same blocker as SimpleStream** (`cards/simplestream.md`), for
the same reason and with the same remedy: when the representation path is read and enacted, QDP
ports unchanged and is scored at the cost and accuracy of the evidence it actually chose.

**Why this matters rather than being bookkeeping.** Ported whole today, QueryStream's QDP would
emit a pruned-evidence request, receive full-history latency and full-history cost, and be scored
as though its pruning had no benefit and no penalty. That is a null produced by the harness, not by
the method — the failure mode this study has been burned by repeatedly, and the reason D134 asks
for the read-path check *before* the port rather than after.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| proactive response: answer when the evidence suffices, not on a fixed schedule | `RecallAction(decision="DEFER", defer_s=...)` until the admit test passes, then `"CLOUD"` | FAITHFUL in mechanism |
| the sufficiency signal driving that decision | the session's believed readiness and built-token fraction | **ADAPTATION.** The paper's signal is a query-token relevance score computed over the frame stream, which our observation does not expose. We substitute the strongest sufficiency signal live2 does expose. Flagged as the one place a shape had to be chosen. |
| QDP relevance-and-novelty token filter | **not ported** | blocked, see above |
| training | none | FAITHFUL; the method is training-free |

## Limitations, stated

- **The arm scored today is half the method.** Any result must name it as the Proactive Response
  half alone, never as "QueryStream", until QDP is unblocked and ported.
- **The sufficiency proxy is an adaptation**, not the paper's signal, and is the kind of proxy
  consistency check 6 requires be declared. It may not carry a headline conclusion on its own.


## D134 item 6, added 2026-11-19: the Proactive Response half is ported, QDP is not

**Ported:** `querystream_adapted.py::QueryStreamProactiveAdapted`, registered as
`querystream-proactive`. What it decides in our setting: for each robot question, whether the
evidence in hand is already enough to answer, or whether to DEFER and let the stream supply more
first - never deferring past the point where the answer can still land inside its deadline.

**Both required proofs pass** at 8 devices, seed 4, 300 s: **0 illegal actions** across 3,001
epochs, and the fairness digest `00f32b45...` matches the committed `b7-edf-feasibility` control.
The mechanism **fires**: 9 `defer` decisions alongside 9 `release_recall`.

### A first version of the sufficiency proxy was INERT, and it is recorded rather than replaced quietly

The first proxy compared `max(e.tokens for e in q.evidence)` against `readiness_tokens`. **It can
never fire.** `cstate` always offers a `D2` evidence item whose size **is** the whole believed
history, so the ratio is always 1.0 and every query reads as sufficient. The arm produced **zero**
DEFER decisions and was identical to `b7` on decision kinds, while passing legality and the digest
check perfectly.

**The inventory describes what COULD be sent, not what has arrived.** That is the same confusion,
one level down, as the `representation` channel being written by arms and read by nothing: a field
that looks like a measurement and is a declaration.

It was caught by checking the **decision kinds** rather than the pass/fail of the two required
proofs - which both passed. A port can satisfy every stated check and still have its mechanism
never execute.

**The working proxy** uses the quantity that actually moves as the stream runs: the session's
believed history, `readiness_tokens`. The arm waits while the evidence is still growing and answers
once it has settled, or once the deadline forces it. A warm session is sufficient by definition.
Still an **ADAPTATION**, and still not the paper's query-token relevance score, so it may not carry
a headline conclusion on its own.

### QDP remains unported: channel live, signal absent

Part A made `RecallAction.representation` reach execution, so the **channel** is live. The
**signal** is not: QDP prunes on semantic relevance and temporal novelty, and `RecallQuery` exposes
`query_id`, `session_id`, `category`, `arrival_s`, `deadline_s`, `evidence`, `readiness`,
`readiness_tokens` and `device_answer_confidence` - no token- or frame-level relevance anywhere.
The only query-side feature is `category`, which two independent routes have shown is noise and
harmful to act on, so porting QDP onto it would mean implementing a published method on top of a
predictor measured to be destructive.

**This is a distinct class from the dead channels** (`order`, `desired_tier`, `engine_config`),
where the harness cannot carry what the arm decides. Here the harness can carry it and has nothing
to decide with.

**Two-axis label.** This arm leaves `representation` unset, so it is **CHEAP-INJECTED**: comparable
with any RECENT-effective arm, and entitled to **no credit** for the resulting evidence discount,
which it never requested.
