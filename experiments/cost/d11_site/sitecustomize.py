"""Loaded at interpreter start for the StudyD11 vLLM server processes only (PYTHONPATH set by study_d11_vllm.py).
Runs the system sitecustomize first, then registers the 'npz_frames' video loader when D11_NPZ_LOADER=1."""
import os
import runpy
if os.path.exists("/usr/lib/python3.10/sitecustomize.py"):
    try:
        runpy.run_path("/usr/lib/python3.10/sitecustomize.py")
    except Exception:  # noqa: BLE001
        pass
if os.environ.get("D11_NPZ_LOADER") == "1":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import d11_npz_video_loader  # noqa: F401
