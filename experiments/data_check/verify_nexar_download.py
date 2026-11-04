"""Exit 0 only if every file in the remote HF dataset repo exists locally with the same size."""
import os, sys
from huggingface_hub import HfApi
local = sys.argv[1]
api = HfApi(token=os.environ.get("HF_TOKEN"))
files = [f for f in api.list_repo_tree("nexar-ai/nexar_collision_prediction", repo_type="dataset", recursive=True)
         if getattr(f, "size", None) is not None]
bad = [f.path for f in files if not os.path.isfile(os.path.join(local, f.path))
       or os.path.getsize(os.path.join(local, f.path)) != f.size]
tot = sum(f.size for f in files)
print(f"remote files {len(files)} bytes {tot} missing_or_size_mismatch {len(bad)}")
for b in bad[:20]: print("  BAD", b)
sys.exit(1 if bad or not files else 0)
