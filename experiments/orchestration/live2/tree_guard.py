#!/usr/bin/env python3
"""TREE INTEGRITY: every file is either git's or one I declared changing. Nothing else.

Why this exists: a tree of mine was found carrying the HELD DEVICE_ANSWERS implementation in
three files I had not declared changing, and the dry sweep running on it was therefore not
evidence of anything. I caught it by comparing against git rather than by trusting the tree. A
proof's own instrument deserves the same absence-checking the policy gets, so the check is now a
script that runs before any proof instead of a habit.
"""
import hashlib, subprocess, sys
from pathlib import Path
TREE = Path(sys.argv[1]).resolve()
SHA  = (TREE/"BASE_SHA").read_text().strip()
REPO = sys.argv[2] if len(sys.argv) > 2 else "/tmp/claude-1001/mapwt"
# E1 part 1 landed on origin at 5155aad4's ancestry, so those files must now MATCH git. Listing
# them as DECLARED would hide a later divergence behind "I meant to change that".
DECLARED = {
 "experiments/orchestration/live2/cf_protect_defer.py",
 "experiments/orchestration/live2/arms_v6cf.py",
 "experiments/orchestration/live2/coordinator.py",
 "experiments/orchestration/live2/arms_v6cf_device.py",
 # rung-4 pass 1 (D222 (1) items 1, 2, 4, 5)
 "experiments/orchestration/live2/v5/cf_cost.py",
 "experiments/orchestration/live2/cf_request_defer.py",
 "experiments/orchestration/live2/arms_v6cf.py",
 "experiments/orchestration/live2/arms_v6cfr3.py",
 "experiments/orchestration/live2/coordinator.py",
 "experiments/orchestration/live2/d222_measured_safety.py",
 "results/orchestration/live2/d222_pass1/d222_safety_refit.json",
 # E1 part 2 (released by the H100 at 5155aad4)
 "experiments/orchestration/live2/run_live2_real.py",
 "experiments/orchestration/live2/procsplit.py",
 # DEVICE_ANSWERS (D218's rule, D221's placement): the three held patches plus the rung-4 wiring
 "experiments/orchestration/live2/cf_protect_defer.py",
 "experiments/orchestration/live2/arms_final_ladder.py",
}
FORBIDDEN = ("DEVICE_ANSWERS_SWITCH_ATTR", "live2_cf_device_answers")

tracked = set(subprocess.run(["git", "ls-tree", "-r", "--name-only", SHA],
                             cwd=REPO, capture_output=True, text=True).stdout.split())
def gitsha(p):
    r = subprocess.run(["git", "rev-parse", "%s:%s" % (SHA, p)], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None
def blobsha(fp):
    b = fp.read_bytes()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(b)); h.update(b)
    return h.hexdigest()

changed, undeclared, untracked_new, forbidden_hits = [], [], [], []
n = 0
for fp in sorted(TREE.rglob("*")):
    if not fp.is_file():
        continue
    rel = str(fp.relative_to(TREE))
    if rel == "BASE_SHA" or "/__pycache__/" in rel or rel.endswith(".pyc"):
        continue
    n += 1
    # The files that legitimately carry the DEVICE_ANSWERS switch name. `arms_final_ladder.py` is
    # DELIBERATELY ABSENT: the ruling forbids touching it until the fold, so a marker there is a
    # FATAL finding and not an expected one.
    EXPECT_MARKER = {"experiments/orchestration/live2/cf_protect_defer.py",
                     "experiments/orchestration/live2/arms_v6cf.py",
                     "experiments/orchestration/live2/arms_v6cf_device.py"}
    if fp.suffix == ".py" and "/held/" not in rel and rel not in EXPECT_MARKER:
        t = fp.read_text(errors="replace")
        for k in FORBIDDEN:
            if k in t:
                forbidden_hits.append("%s :: %s" % (rel, k))
    if rel not in tracked:
        (untracked_new if rel in DECLARED else undeclared).append(rel)
        continue
    if blobsha(fp) != gitsha(rel):
        (changed if rel in DECLARED else undeclared).append(rel)

print("files examined            :", n)
print("base sha                  :", SHA)
print("declared AND changed      :", len(changed))
for r in sorted(changed): print("   M", r)
print("declared AND new          :", len(untracked_new))
for r in sorted(untracked_new): print("   A", r)
print("UNDECLARED differences    :", len(undeclared))
for r in sorted(undeclared)[:40]: print("   !!", r)
print("forbidden held markers    :", len(forbidden_hits))
for r in forbidden_hits[:10]: print("   !!", r)
missing = sorted(DECLARED - set(changed) - set(untracked_new))
print("declared but UNCHANGED    :", len(missing))
for r in missing: print("   ?", r)
# SEVERITY IS SPLIT, because the two findings mean different things and only one is about the
# tree. FATAL: a file differs from git that I did not declare, or a held marker appears in a file
# that should not carry one - the tree is not what I said it is, and no proof on it is evidence.
# ADVISORY: a file I declared turns out to match git, which happens the moment my change LANDS on
# origin and is a stale list, not a dirty tree. Collapsing the two is why this guard printed FAIL
# twice for bookkeeping; a guard whose FAIL is usually harmless is one nobody stops for.
FATAL = bool(undeclared) or bool(forbidden_hits)
ADVISORY = bool(missing)
print("\nFATAL findings   :", "none" if not FATAL else
      "%d undeclared, %d stray marker(s)" % (len(undeclared), len(forbidden_hits)))
print("ADVISORY findings:", "none" if not ADVISORY else
      "%d declared-but-unchanged (my list is stale, the tree is not dirty)" % len(missing))
print("TREE GUARD:", "FAIL" if FATAL else ("PASS" if not ADVISORY else "PASS (advisory only)"))
sys.exit(1 if FATAL else 0)
