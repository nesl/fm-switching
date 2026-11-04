"""StudyD11 vLLM video loader 'npz_frames' (registered into vLLM's VIDEO_LOADER_REGISTRY).

Why: R1's transport (`data:video/jpeg;base64,<png>,<png>,...` + per-REQUEST media_io_kwargs frames_indices) cannot give
two videos in one request their own timestamps — vLLM 0.31's jpeg-sequence path takes ONE frames_indices list per
request and requires its length to equal each video's frame count (vllm/multimodal/media/video.py: load_base64).
This loader receives each video as `data:video/x-npz;base64,<npz>` carrying its own uint8 frames [T, H, W, 3] and its
own frames_indices / fps / total_num_frames, and returns exactly what the jpeg-sequence path returns (an HWC uint8
frame stack + the same metadata keys), so the processor sees identical pixels and per-video timing.
Selected per request with media_io_kwargs {"video": {"video_backend": "npz_frames"}}.
"""
import io

import numpy as np
from vllm.multimodal.video import VIDEO_LOADER_REGISTRY, VideoLoader


@VIDEO_LOADER_REGISTRY.register("npz_frames")
class NpzFramesLoader(VideoLoader):
    @classmethod
    def load_bytes(cls, data: bytes, **kwargs):
        z = np.load(io.BytesIO(data), allow_pickle=False)
        frames = np.ascontiguousarray(z["frames"])
        assert frames.ndim == 4 and frames.shape[-1] == 3 and frames.dtype == np.uint8, frames.shape
        idx = [int(i) for i in z["frames_indices"]]
        assert len(idx) == frames.shape[0]
        fps = float(z["fps"])
        total = int(z["total_num_frames"])
        assert total >= len(idx)
        meta = {"total_num_frames": total, "fps": fps, "duration": total / fps if fps > 0 else 0.0,
                "video_backend": "jpeg_sequence", "frames_indices": idx, "do_sample_frames": False}
        return frames, meta
