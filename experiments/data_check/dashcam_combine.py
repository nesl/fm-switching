#!/usr/bin/env python3
"""Combine the StudyD0 outputs into results/data_check/dashcam_data_check.json (expected vs observed, all values).
Run after nexar_check.py, nexar_contact_sheets.py and dota_metadata_check.py:
  ~/.venvs/dashcam/bin/python -I experiments/data_check/dashcam_combine.py
"""
import json
from datetime import datetime
from pathlib import Path

R = Path(__file__).resolve().parents[2] / "results/data_check"


def main():
    n = json.load(open(R / "nexar_check.json"))
    n.pop("rows", None)                                   # per-video rows stay in nexar_check.json
    d = json.load(open(R / "dota_metadata_check.json"))
    cs = json.load(open(R / "nexar_contact_sheets.json"))
    tp = n["timing"]["train/positive"]
    vp = n["video_props"]["train_all"]
    exp_obs = [
        ("nexar rows (all splits)", "2.84k", n["rows_total"]),
        ("nexar train videos", 1500, n["per_split"]["train/positive"]["mp4_files"] + n["per_split"]["train/negative"]["mp4_files"]),
        ("nexar train positive / negative", "750 / 750", f"{n['per_split']['train/positive']['rows']} / {n['per_split']['train/negative']['rows']}"),
        ("nexar collision / near-collision", "400 / 350", n["collision_type_field"]),
        ("nexar resolution", "1280x720", vp["resolution"]),
        ("nexar fps", "~30", vp["avg_fps"]),
        ("nexar duration (train)", "~40 s, bimodal", {k: vp["duration_s"][k] for k in ("min", "p5", "p50", "max")}),
        ("event - alert mean (train pos)", 1.6, round(tp["event_minus_alert"]["mean"], 4)),
        ("event - alert max (train pos)", 4.5, round(tp["event_minus_alert"]["max"], 4)),
        ("frac train pos >= 1 s after event", None, tp["frac_after_event_ge_1s"]),
        ("frac train pos >= 2 s after event", None, tp["frac_after_event_ge_2s"]),
        ("frac train pos >= 3 s before alert", None, tp["frac_before_alert_ge_3s"]),
        ("nexar corrupt / unreadable", 0, n["corrupt_or_unreadable"]["n"]),
        ("dota metadata_train / val", "3275 / 1402", f"{d['n_train']} / {d['n_val']}"),
        ("dota sum num_frames", 477650, d["sum_num_frames"]),
        ("dota frames on disk", "477,650 or 731,932", "UNAVAILABLE (Drive 404)"),
        ("dota ego5 clips", 2261, d["ego5_count"]),
    ]
    out = dict(study="StudyD0-nexar (with DoTA metadata-only)", at=datetime.now().isoformat(),
               expected_vs_observed=[dict(check=a, expected=b, observed=c) for a, b, c in exp_obs],
               nexar=n, dota=d, contact_sheets=cs)
    (R / "dashcam_data_check.json").write_text(json.dumps(out, indent=1, default=str))
    for e in exp_obs:
        print(e)


if __name__ == "__main__":
    main()
