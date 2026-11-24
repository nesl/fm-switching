"""Negative controls for the torn-tree guard (live2/source_agreement.py), agreed with flash 2026-11-24.

Each control is the case it exists to catch, with the expected outcome stated, so an impossible
pass and an impossible failure are equally visible:
  (i)   a file BOTH runner and child loaded differs                  -> TornTree (case 1)
  (ii)  a RUNNER-ONLY file differs                                    -> NO raise: the measured gap,
        closed instead by the runner's pre-flight refusal
  (iii-a) a module the child loaded at START is edited mid-run       -> WARNING moved_after_import
  (iii-b) a module first loaded LATE was edited before its import    -> INVALID torn_lazy_import
  (iv)  nothing moved                                                 -> OK
plus one real-tree check that the full hash is deterministic and covers this file.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import source_agreement as SA  # noqa: E402

A, B, C = "experiments/orchestration/live2/procsplit.py", "experiments/orchestration/live2/run_live2_real.py", \
    "experiments/orchestration/live2/arms_lazy.py"


def test_i_overlap_mismatch_raises():
    runner = {A: "h1", B: "hr"}
    child = {A: "h2"}
    try:
        SA.check_start(runner, child)
    except SA.TornTree as e:
        assert "runner_child_mismatch" in str(e)
        return
    raise AssertionError("an overlapping file that differs must raise TornTree")


def test_ii_runner_only_change_is_not_caught():
    runner = {A: "h1", B: "h_runner_old"}          # B is runner-only
    child = {A: "h1"}
    rec = SA.check_start(runner, child)
    assert rec["runner_only_n"] == 1 and rec["overlap_n"] == 1 and rec["runner_child_mismatch"] == []


def test_iii_a_moved_after_import_warns_and_keeps():
    start_all = {A: "h1", C: "c1"}
    child_start = {A: "h1"}
    end_all = {A: "h1_edited", C: "c1"}
    rec = SA.check_end(start_all, child_start, {A: "h1_edited"}, end_all)
    assert rec["verdict"] == "WARNING moved_after_import" and rec["moved_after_import"] == [A]
    assert rec["torn_lazy_import"] == []


def test_iii_b_lazy_import_after_change_is_invalid():
    start_all = {A: "h1", C: "c1"}
    child_start = {A: "h1"}                         # C not loaded yet at start
    end_all = {A: "h1", C: "c1_edited"}
    rec = SA.check_end(start_all, child_start, {A: "h1", C: "c1_edited"}, end_all)
    assert rec["verdict"] == "INVALID torn_lazy_import" and rec["torn_lazy_import"] == [C]


def test_iv_nothing_moved_is_ok():
    m = {A: "h1", C: "c1"}
    rec = SA.check_end(m, {A: "h1"}, m, dict(m))
    assert rec["verdict"] == "OK" and rec["tree_files_changed_during_cell_n"] == 0


def test_real_tree_hash_is_deterministic_and_covers_this_file():
    x, y = SA.all_repo_py(), SA.all_repo_py()
    assert x["files"] == y["files"] and len(x["files"]) > 100
    assert "experiments/orchestration/live2/source_agreement.py" in x["files"]
    loaded = SA.loaded_repo_files()
    assert "experiments/orchestration/live2/source_agreement.py" in loaded
    assert loaded["experiments/orchestration/live2/source_agreement.py"] == \
        x["files"]["experiments/orchestration/live2/source_agreement.py"]


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_") and callable(f):
            f()
            n += 1
            print("PASS", k)
    print(f"{n} passed")
