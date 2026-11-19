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
