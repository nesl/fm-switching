import sys
from pathlib import Path
p = Path(sys.argv[1])
s = p.read_text()

old = """            belief=(preds.get("belief") or SC.asdict(SC.Belief())),
"""
new = """            belief=(preds.get("belief") or self._belief_prefix_record()),
"""
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new)

old = """    def _log_residency(self, t: float, session_id: str, telemetry=None) -> None:
"""
new = '''    def _belief_prefix_record(self) -> Dict[str, Any]:
        """D213 item 3: the belief's PREDICTED RESIDENT PREFIX per session, in tokens, recorded on
        the decision row at submission so D211 signal (a) is a join on recorded data.

        WHY. D211 signal (a) is `host_tokens = max(0, cached_tokens - believed GPU-resident
        prefix)`. `cached_tokens` is recorded per request; the second input was not recorded for any
        reported arm. `belief.gpu_tokens_by_session` (`schema.py:316`) is logged on every decision
        row and was EMPTY on all 16,840 rows of the committed rung-3 cell, because its only producer
        (`arms_policy.py:1067-1075`) is never entered by the ladder. So the primary input of D211's
        primary signal did not exist and only signal (b) could ever have been validated.

        THE DEFINITION, stated here because the join must not have to guess it. For each open or
        held session with a non-zero history, the value is the prefix the cloud has actually built,
        `min(built_tokens, est_tokens)`, filed under the session's CURRENT BELIEVED TIER
        (`SessionRec.believed_tier()`, the argmax of `belief`). So `gpu_tokens_by_session[sid]` is
        exactly "the number of this session's tokens the policy believes are GPU-resident right
        now", which is what the ruled signal subtracts; a session believed host or cold contributes
        0 there by construction, and its built prefix is filed under its own tier so the join can
        see what the belief thought instead. This is NOT `arms_policy._belief_tokens`'s quantity
        (the whole history size from the rollout's own fleet model) and is not mixed with it:
        `preds["belief"]` still wins wherever an arm supplies one, so nothing that already fills
        this field changes.

        IT IS A RECORDING, AND BOTH HALVES OF THAT ARE PROVED, NOT ASSERTED.
          * It feeds no decision. `_log_decision` is called AFTER the action is chosen and after
            `latency_ms` has been measured by the caller, it writes to `self.logs.decision` and
            returns a decision id, and nothing in live2 reads `DecisionRecord.belief` during a run
            (the only reader in the tree is the offline `d211_signal_a_available.py`).
          * It moves no dry digest. The digested rows ARE the decision records
            (`hybrid/test_hybrid.dry` reads `decision.jsonl` and strips only `arm`,
            `decision_latency_ms` and `decision_id`), so filling `belief` on a dry cell WOULD move
            every arm's dry digest, including rung 4, while a ladder build is in flight. That is a
            methodological change nobody ruled, so the record is LIVE-CELL ONLY and a dry cell keeps
            the committed empty `Belief()` byte for byte. D211 needs it on the first final-ladder
            LIVE cells, which is exactly where it is now written.
        """
        if self.dry_run:
            return SC.asdict(SC.Belief())
        out: Dict[str, Any] = {"gpu_tokens_by_session": {}, "host_tokens_by_session": {},
                               "cold_tokens_by_session": {}}
        field_of = {"gpu": "gpu_tokens_by_session", "host": "host_tokens_by_session",
                    "cold": "cold_tokens_by_session"}
        for sid, s in self.st.sessions.items():
            est = int(getattr(s, "est_tokens", 0) or 0)
            if est <= 0:
                continue
            f = field_of.get(s.believed_tier())
            if f is None:
                continue
            out[f][sid] = min(int(getattr(s, "built_tokens", 0) or 0), est)
        return out

    def _log_residency(self, t: float, session_id: str, telemetry=None) -> None:
'''
assert s.count(old) == 1
s = s.replace(old, new)
p.write_text(s)
print("patched", p)
