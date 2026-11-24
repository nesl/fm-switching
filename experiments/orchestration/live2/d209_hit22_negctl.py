#!/usr/bin/env python3
"""HIT 22's decisive negative control: the AFTER tree, with the corrected price SEMANTICALLY
reverted and the file's text left exactly as committed.

WHY THIS AND NOT THE `before` TREE. The before/after pair differs by three files' TEXT as well as
by one price, and `arms_v6state.V6StateArm._queued_behind` caches its pending-work rows under
`id(obs)`, a MEMORY ADDRESS (the defect `cf_pd_one_cell.py --diag-epoch-cache-key` exists to test),
so a rung-2 arm's decisions can depend on allocation history and therefore on a docstring's length.
A before/after digest difference is consistent BOTH with the price change and with that artifact.
This control separates them: same tree, same bytes, same allocation, ONE value changed.

If the digest returns to the before tree's value, the price moved the decisions.
If it stays at the after tree's value, the difference was never the price.

The runner, the recipe, the posted knobs and the digest are `cf_pd_one_cell.py`'s own; this file
only installs the revert and calls its `main()`.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_pd_one_cell as C                                                     # noqa: E402
import touch_policy as TP                                                      # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "revert"
argv = [a for a in sys.argv[1:] if a.startswith("-") or not a in ("revert", "keep")]

if MODE == "revert":
    TP.price_for_touch = TP.touch_price_gpu_s          # the pre-D209 reload proxy, by value only
    TP.TOUCH_PRICE_MODE = "reload-proxy"

sys.argv = [sys.argv[0]] + argv
raise SystemExit(C.main())
