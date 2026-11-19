#!/usr/bin/env python3
"""D119: the decision-preserving CPU speed-ups, each behind its own switch, DEFAULT OFF.

The rule for every D119 item is that the OFF path runs exactly the code it ran before, so the
pilot on the H100 is unaffected, and the ON path returns the same values.

`memo_u_sh_grid` is the first item: `Profiles.u_sh_grid` was 2.41 % of sampled decision time at
64 devices because it rebuilt and re-sorted its list of curve points on every call over a profile
that is loaded once and never mutated.
"""
from __future__ import annotations

import unittest

from policy.profiles import MissingEvidence, load_profiles

CASES = ((1, 0.5), (1, 1.0), (1, 0.25))
MAPPINGS = ("identity", "affine")


class TestMemoUShGridIsOffByDefault(unittest.TestCase):
    def test_the_switch_defaults_to_off(self):
        self.assertFalse(load_profiles().memo_u_sh_grid,
                         "D119 requires every switch to default OFF while the pilot runs")

    def test_off_means_nothing_is_cached(self):
        pf = load_profiles()
        pf.u_sh_grid(1, 0.5)
        self.assertFalse([k for k in pf._memo if k and k[0] == "u_sh_grid"],
                         "with the switch off no u_sh_grid entry may be cached")


class TestMemoUShGridReturnsTheSameValues(unittest.TestCase):
    def test_both_paths_agree_on_every_available_case(self):
        plain, memo = load_profiles(), load_profiles()
        memo.memo_u_sh_grid = True
        checked = 0
        for m, cad in CASES:
            for mapping in MAPPINGS:
                try:
                    want = plain.u_sh_grid(m, cad, mapping)
                except (MissingEvidence, KeyError):
                    continue
                got = memo.u_sh_grid(m, cad, mapping)
                self.assertEqual(want, got, "(m=%d, cadence=%s, %s)" % (m, cad, mapping))
                # and again, now from the cache
                self.assertEqual(want, memo.u_sh_grid(m, cad, mapping))
                checked += 1
        self.assertGreater(checked, 0, "no u_sh curve was available to compare")

    def test_a_second_call_returns_the_cached_object(self):
        pf = load_profiles()
        pf.memo_u_sh_grid = True
        a = pf.u_sh_grid(1, 0.5)
        self.assertIs(a, pf.u_sh_grid(1, 0.5))

    def test_the_cache_is_per_instance(self):
        a, b = load_profiles(), load_profiles()
        a.memo_u_sh_grid = True
        a.u_sh_grid(1, 0.5)
        self.assertFalse([k for k in b._memo if k and k[0] == "u_sh_grid"],
                         "one profile's cache must not reach another instance")

    def test_the_key_separates_the_arguments(self):
        """A cache keyed too loosely would return one cadence's curve for another."""
        pf = load_profiles()
        pf.memo_u_sh_grid = True
        got = {}
        for m, cad in CASES:
            try:
                got[(m, cad)] = pf.u_sh_grid(m, cad)
            except (MissingEvidence, KeyError):
                continue
        keys = [k for k in pf._memo if k and k[0] == "u_sh_grid"]
        self.assertEqual(len(keys), len(got),
                         "one cache entry per distinct argument tuple, got %r" % (keys,))

    def test_negative_control_a_broken_cache_is_caught(self):
        """The equality test above must actually be able to fail."""
        pf = load_profiles()
        pf.memo_u_sh_grid = True
        want = pf.u_sh_grid(1, 0.5)
        pf._memo[("u_sh_grid", 1, 0.5, "identity")] = [(0.0, -1.0)]
        self.assertNotEqual(want, pf.u_sh_grid(1, 0.5),
                            "a deliberately poisoned cache entry was NOT caught, so the "
                            "equality test proves nothing")

    def test_the_uncached_helper_is_what_the_off_path_runs(self):
        pf = load_profiles()
        self.assertEqual(pf.u_sh_grid(1, 0.5), pf._u_sh_grid_uncached(1, 0.5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
