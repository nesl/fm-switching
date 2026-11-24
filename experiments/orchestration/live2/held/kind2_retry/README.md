# Kind-2 fix, PREPARED NOT APPLIED (user ruling 2026-11-24)

Apply to ALL arms before the held-out seeds 1 to 3 (which run fresh); never mid-evaluation.

What it is: `asyncbackend.py.patch` (base 8ea68467) adds a switch `AsyncLive2Backend.kind2_retry`
(class default `KIND2_RETRY_DEFAULT = False`). When ON, a request whose client raised `httpx.ReadError`
BEFORE ANY RESPONSE BYTE (no HTTP status and no first line: the kind-2 signature, 109 of 109 on reused
pooled connections on 2026-11-24) is retried ONCE on a separate no-keep-alive client, so the retry always
opens a NEW connection. The latency keeps the original submit time. Every other request, and every request
when the switch is OFF, takes the unchanged path. The result dict gains `kind2_retried` and `kind2_first`
(the first attempt's exception); the backend counts `n_kind2_retries` and `n_kind2_retry_ok`.

Why this and not a fresh connection per request: a fresh connection on EVERY request adds connection
set-up to every request of every arm, changing timing everywhere, so it cannot be shown not to change
decisions. The retry touches only requests that currently fail.

Proof (`k2_proof.py`, real `_post` through `httpx.MockTransport`, CPU only; results in
results/orchestration/live2/kind2_retry/k2_proof_results.jsonl): OFF is identical to the base on all
three cases (normal, pre-byte ReadError, mid-stream ReadError); ON leaves the normal and the mid-stream
cases unchanged (1 transport call, no retry) and turns the pre-byte ReadError into a success on the
second call (2 calls, retried, first attempt recorded). The proof caught a defect in the first draft
(`httpx` is imported lazily in this module, so the ON path raised NameError); fixed with the same
lazy import.

Register: decisions on requests that do NOT hit the kind-2 failure cannot change (identical code path).
On a request that does, the outcome changes BY DESIGN (a miss becomes, at best, a late or on-time
answer); that is the fix, which is why it is applied to all arms at once and before fresh seeds only.
A dry decision-identity proof cannot exercise this file (dry cells do not use AsyncLive2Backend).
