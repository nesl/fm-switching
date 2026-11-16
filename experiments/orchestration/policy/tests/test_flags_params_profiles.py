import unittest

from policy import Flags, Params, PROVENANCE
from policy.flags import CONDITIONAL
from policy.profiles import MissingEvidence
from policy.tests._fixtures import PF


class TestFlags(unittest.TestCase):
    def test_every_conditional_defaults_off(self):
        f = Flags()
        for name in CONDITIONAL:
            self.assertFalse(getattr(f, name), "%s must default OFF (spec 7.0, D38)" % name)
        self.assertFalse(f.any_on())

    def test_every_conditional_has_an_enabling_condition_and_a_status(self):
        for name, row in CONDITIONAL.items():
            self.assertIn("enabling_condition", row)
            self.assertTrue(row["status"].startswith(("NOT MET", "NOT COMPUTABLE")),
                            "%s claims a met condition; nothing in the committed evidence "
                            "supports that" % name)

    def test_flags_are_frozen(self):
        f = Flags()
        with self.assertRaises(Exception):
            f.merging = True
        self.assertTrue(f.with_(merging=True).merging)
        self.assertFalse(f.merging)


class TestParams(unittest.TestCase):
    def test_every_field_has_provenance(self):
        p = Params()
        for k in p.as_dict():
            self.assertIn(k, PROVENANCE, "parameter %s has no provenance entry" % k)
            self.assertIn(PROVENANCE[k]["kind"], ("COMMITTED", "DEV-FITTED", "PLACEHOLDER"))

    def test_placeholders_are_listed(self):
        p = Params()
        self.assertIn("H", p.placeholders())
        self.assertIn("feasibility_threshold", p.placeholders())
        self.assertNotIn("piece_sizes_tokens", p.placeholders())

    def test_omega_ss_is_none(self):
        self.assertIsNone(Params().omega["SS"])


class TestProfiles(unittest.TestCase):
    def test_committed_values(self):
        self.assertAlmostEqual(PF.u_sh_device(), 0.4922174586396322, places=12)
        self.assertAlmostEqual(PF.omega("RC"), 0.42463109124188936, places=12)
        self.assertAlmostEqual(PF.rtt_s(), 0.044, places=12)
        self.assertAlmostEqual(PF.uplink_bytes_per_s(), 1_700_000.0, places=6)

    def test_absent_evidence_raises_and_does_not_guess(self):
        for fn in (PF.jitter, PF.bandwidth_percentiles, lambda: PF.omega("SS")):
            with self.assertRaises(MissingEvidence):
                fn()

    def test_conditional_recall_rate_is_not_available(self):
        self.assertFalse(PF.conditional_rate_available())

    def test_nearest_measured_size_only(self):
        self.assertEqual(PF.seconds_per_token("rebuild", 11_500),
                         PF.seconds_per_token("rebuild", 11_000))
        self.assertEqual(PF.seconds_per_token("rebuild", 1_000_000),
                         PF.seconds_per_token("rebuild", 28_000))
