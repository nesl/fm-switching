#!/usr/bin/env python3
"""H100 wrapper for flash's 32B engine-action confirmation (24c5492), user priority item (1), one break at a run boundary.

Starts the PINNED round-1 32B server with study_live2_pilot.start_server(27.0) (the same call every frozen-grid cell
makes: DE_c38 flag check, GPU-2 exclusivity preflight, KV pool check), runs the unchanged script with no flags against
it, then stops the server. The script's output JSON is the record; the server's launch info is written beside it.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "experiments/orchestration"))
import study_live2_pilot as P                                              # noqa: E402

OUT = REPO / "results/orchestration/live2/v5"
srv, sinfo, _M = P.start_server(27.0)
t0 = time.time()
try:
    rc = subprocess.call([sys.executable, str(REPO / "experiments/orchestration/live2/confirm_engine_actions_32b.py")],
                         cwd=str(REPO))
finally:
    srv.stop()
(OUT / "engine_actions_32b_confirmation_server.json").write_text(json.dumps(
    dict(server=sinfo, script_rc=rc, wall_s=round(time.time() - t0, 1),
         note="round-1 server via study_live2_pilot.start_server(27.0); script 24c5492 run unchanged with no flags"),
    indent=1, default=str) + "\n")
print("rc", rc)
sys.exit(rc)
