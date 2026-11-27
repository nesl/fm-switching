#!/usr/bin/env python3
"""Unit tests for the uplink question-priority switch (links.UplinkQueue). CPU only.
Run: python -I test_uplink_question_priority.py
"""
import sys
import unittest
from pathlib import Path

L = Path(__file__).resolve().parents[1]
for p in (L, L / "fleet"):
    sys.path.insert(0, str(p))

import links as LK  # noqa: E402

RATE = 2.219
FRAME_B = 24570
Q_B = 1200
FRAME_S = LK.serialise_s(FRAME_B, RATE)
Q_S = LK.serialise_s(Q_B, RATE)


def _queue(prio, retimed=None):
    spec = LK.LinkSpec(uplink_mbps=RATE)
    if not prio:
        return LK.UplinkQueue(spec)
    cb = (lambda tr, old: retimed.append((tr.ref, old, tr.t_arrive))) if retimed is not None else None
    return LK.UplinkQueue(spec, True, cb)


def _backlog(q, n=94, t=100.0):
    return [q.send("history_batch", "b%d" % i, FRAME_B, t) for i in range(n)]


class QuestionPriority(unittest.TestCase):
    def test_off_is_fifo(self):
        q = _queue(False)
        fr = _backlog(q)
        qs = q.send("recall_question", "q1", Q_B, 103.0)
        self.assertEqual(qs.t_start, fr[-1].t_start + FRAME_S)
        self.assertTrue(all(t.cls == 1 for t in q.log[:-1]))

    def test_on_question_waits_at_most_one_frame(self):
        q = _queue(True)
        fr = _backlog(q)
        before = [(t.t_start, t.t_arrive) for t in fr]
        qs = q.send("recall_question", "q1", Q_B, 103.0)
        self.assertLessEqual(qs.t_start - 103.0, FRAME_S + 1e-12)
        self.assertLess(qs.t_start - 103.0, 0.0886 + 1e-4)
        on_wire = [t for t in fr if t.t_start < 103.0 < t.t_start + FRAME_S][0]
        self.assertAlmostEqual(qs.t_start, on_wire.t_start + FRAME_S, places=9)
        started = [t for t in fr if t.t_start <= on_wire.t_start]
        self.assertEqual([(t.t_start, t.t_arrive) for t in started], before[:len(started)])

    def test_frames_stay_fifo_and_shift_by_question_only(self):
        q = _queue(True)
        fr = _backlog(q)
        before = [t.t_arrive for t in fr]
        q.send("recall_question", "q1", Q_B, 103.0)
        order = [t.ref for t in q.log if t.cls == 1]
        self.assertEqual(order, ["b%d" % i for i in range(94)])
        for a, b in zip(q.log, q.log[1:]):
            self.assertGreaterEqual(b.t_start, a.t_start + LK.serialise_s(a.nbytes, RATE) - 1e-12)
        self.assertAlmostEqual(fr[-1].t_arrive - before[-1], Q_S, places=9)
        self.assertLess(Q_S, 0.01)

    def test_questions_fifo_within_class_and_ahead_of_frames(self):
        q = _queue(True)
        fr = _backlog(q)
        a = q.send("recall_question", "qa", Q_B, 103.0)
        b = q.send("recall_question", "qb", Q_B, 103.5)
        self.assertLess(a.t_start, b.t_start)
        self.assertLess(b.t_start, [t for t in fr if t.t_start > b.t_start][0].t_start)

    def test_tie_class_zero_first(self):
        q = _queue(True)
        f = q.send("monitor_frame", "m1", FRAME_B, 50.0)
        qs = q.send("recall_question", "q1", Q_B, 50.0)
        self.assertEqual(qs.t_start, 50.0)
        self.assertAlmostEqual(f.t_start, 50.0 + Q_S, places=9)

    def test_idle_wire_and_gap_absorption(self):
        q = _queue(True)
        f = q.send("monitor_frame", "m1", FRAME_B, 10.0)
        qs = q.send("recall_question", "q1", Q_B, 20.0)
        self.assertEqual((qs.t_start, f.t_start), (20.0, 10.0))
        retimed = []
        q2 = _queue(True, retimed)
        q2.send("monitor_frame", "m1", FRAME_B, 10.0)
        g = q2.send("monitor_frame", "m2", FRAME_B, 30.0)
        q2.send("recall_question", "q1", Q_B, 10.01)
        self.assertEqual(g.t_start, 30.0)
        self.assertEqual(retimed, [])

    def test_retime_callback_and_free_at(self):
        retimed = []
        q = _queue(True, retimed)
        _backlog(q)
        end_before = q.free_at
        q.send("recall_question", "q1", Q_B, 103.0)
        self.assertGreater(len(retimed), 0)
        self.assertAlmostEqual(q.free_at - end_before, Q_S, places=9)

    def test_frame_after_question_offers_follow_free_at(self):
        q = _queue(True)
        _backlog(q, 5)
        q.send("recall_question", "q1", Q_B, 100.01)
        late = q.send("monitor_frame", "m", FRAME_B, 100.02)
        self.assertAlmostEqual(late.t_start, q.log[-2].t_start + FRAME_S, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=1)
