"""The runner's backstop for the user ruling of 2026-11-24 (a request whose answer was DELIVERED is
never left rowless or abandoned): `run_live2_real._reconcile_delivered`, then `_request_log_check`.

Controls, each the case it exists for:
  (a) a delivered outcome with NO row (the r10175 shape)  -> a completed_row_reconstructed row ADDED
  (b) a delivered outcome whose row is ABANDONED           -> that row REPLACED, not abandoned
  (c) an abandoned row with NO delivered outcome           -> left abandoned
  (d) BEFORE reconciliation the check reads incomplete; AFTER it, complete.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent, HERE.parent / "fleet", HERE.parent / "scorer"):
    sys.path.insert(0, str(p))

import run_live2_real as RR  # noqa: E402


def _w(p, rows):
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_backstop():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _w(d / "request.jsonl", [
            dict(request_id="r1", http_status=200, prompt_tokens=10, output_tokens=1),
            dict(request_id="r2", http_status=None, abandoned=True, row_source="abandoned"),
            dict(request_id="r3", http_status=None, abandoned=True, row_source="abandoned"),
        ])
        _w(d / "outcomes.jsonl", [
            dict(opportunity_id="o1", t_delivered=1.0, cloud_payload=dict(request_id="r1")),
            dict(opportunity_id="o2", t_delivered=2.0, t_cloud_done=1.9, device_id="asst001",
                 cloud_payload=dict(request_id="r2")),
            dict(opportunity_id="o3", t_delivered=None, cloud_payload=None),
            dict(opportunity_id="o4", t_delivered=4.0, t_cloud_done=3.9, device_id="asst002",
                 cloud_payload=dict(request_id="r4")),
        ])
        before = RR._request_log_check(d, 4)
        assert before["request_log_complete"] is False
        assert before["outcome_request_ids_unresolved"] == 1          # r4
        assert before["delivered_resolving_to_abandoned"] == 1        # r2
        rec = RR._reconcile_delivered(d)
        assert rec["reconstructed_added"] == 1 and rec["abandoned_replaced"] == 1
        rows = {r["request_id"]: r for r in
                (json.loads(l) for l in (d / "request.jsonl").read_text().splitlines())}
        assert rows["r4"]["row_source"] == "completed_row_reconstructed"
        assert rows["r4"]["http_status"] == 200 and rows["r4"]["http_status_inferred"] is True
        assert rows["r4"]["t_first_token"] == 3.9 and rows["r4"]["abandoned"] is False
        assert rows["r2"]["row_source"] == "completed_row_reconstructed"
        assert rows["r2"]["abandoned"] is False
        assert rows["r3"]["abandoned"] is True                         # (c) no delivery
        after = RR._request_log_check(d, 4)
        assert after["request_log_complete"] is True
        assert after["delivered_resolving_to_abandoned"] == 0
        assert after["outcome_request_ids_unresolved"] == 0


if __name__ == "__main__":
    test_backstop()
    print("PASS test_backstop")
