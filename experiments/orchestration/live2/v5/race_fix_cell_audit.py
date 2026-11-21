import json, os, subprocess, sys
R = "results/orchestration/live2/frozen_test/runs"
FIX = "2b8714c"   # race fix: split sent from confirmed, 2026-11-20 21:28
def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)
pre, post, unknown = [], [], []
for d in sorted(os.listdir(R)):
    p = os.path.join(R, d)
    if not os.path.isdir(p):
        continue
    if "REFUSED_preflight" in d:
        continue
    gc = None
    for f in ("run_meta.json", "header.json"):
        fp = os.path.join(p, f)
        if os.path.exists(fp):
            try:
                m = json.load(open(fp))
            except Exception:
                continue
            prov = m.get("_provenance") or m
            gc = prov.get("git_commit") or m.get("git_commit") or m.get("head")
            if gc:
                break
    if not gc:
        unknown.append((d, "no git_commit")); continue
    if sh("git", "cat-file", "-e", gc).returncode != 0:
        unknown.append((d, "commit unreachable " + gc[:7])); continue
    anc = sh("git", "merge-base", "--is-ancestor", FIX, gc).returncode == 0
    (post if anc else pre).append((d, gc[:7]))
print(f"RACE FIX = {FIX} (2026-11-20 21:28)\n")
print(f"PRE-FIX cells: {len(pre)}")
for d, g in pre:
    print(f"   {d:62s} {g}")
print(f"\nPOST-FIX cells: {len(post)}")
for d, g in post:
    print(f"   {d:62s} {g}")
print(f"\nUNKNOWN: {len(unknown)}")
for d, w in unknown:
    print(f"   {d:62s} {w}")
