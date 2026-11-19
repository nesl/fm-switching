#!/usr/bin/env python3
"""Per-run pilot summary rows (verdicts, robot, D115 decision time, host load, build coverage). CPU only; the pilot
driver calls it between runs, when no server is up. Usage: pilot_summary.py OUT_DIR RAW_DIR SUMMARY_JSON"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_coverage as BC                                                      # noqa: E402


def row(d: Path, raw: Path):
    c = json.loads((d / "cell.json").read_text())
    h = json.loads((d / "header.json").read_text())
    m = json.loads((d / "run_meta.json").read_text()) if (d / "run_meta.json").exists() else {}
    sw = (((c.get("score") or {}).get("score") or {}).get("sweep") or [{}])[0]
    dt, hl = m.get("decision_time") or {}, m.get("host_load") or {}
    valid = bool(c.get("err") is None and c.get("run_valid") and c.get("digests_equal") and (c.get("n_errors") or 0) == 0)
    cov = None
    if valid:
        try:
            src = raw / "runs" / d.name
            t = raw / "work/traces" / f"seed{h['seed']}_n{h['n_devices']}_{int(h['run_s'])}s_A"
            cov = {k: v for k, v in BC.check(src, t).items() if k != "builds"}
        except Exception as e:                                                   # noqa: BLE001
            cov = dict(error=f"{type(e).__name__}: {e}")
    g = lambda x, k: (x or {}).get(k)
    return dict(run=d.name, arm=h.get("arm"), n=h.get("n_devices"), seed=h.get("seed"), host_gib=h.get("host_tier_gib"),
                c_inflight=h.get("c_inflight"), scheduling_policy=h.get("scheduling_policy"),
                git=(h.get("git_commit") or "")[:7], valid=valid, err=c.get("err"),
                n_requests=c.get("n_requests"), n_errors=c.get("n_errors"), lat_p99=g(c.get("lateness"), "p99_ms"),
                dash_all_meet=sw.get("dashcam_all_meet"), robot_measurable=sw.get("robot_pool_eligible"),
                robot_n=sw.get("robot_pool_n"), robot_on_time=sw.get("robot_pool_on_time"),
                robot_frac=sw.get("robot_pool_fraction"),
                passes=(sw.get("dashcam_all_meet") is True and (sw.get("robot_pool_eligible") is not True
                                                               or sw.get("robot_pool_meets") is True)),
                dec_wall_p50=g(dt.get("wall_ms"), "p50"), dec_wall_p99=g(dt.get("wall_ms"), "p99"),
                dec_cpu_p99=g(dt.get("cpu_ms"), "p99"), wall_over_cpu_p99=g(dt.get("wall_over_cpu"), "p99"),
                submit_delay_p99=g(m.get("submit_delay_total_ms"), "p99"),
                host_loadavg_p50=g(hl.get("loadavg_1m"), "p50"), other_cores_p50=g(hl.get("other_cpu_cores"), "p50"),
                other_cores_p99=g(hl.get("other_cpu_cores"), "p99"), build_coverage=cov)


def main():
    out, raw, summ = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    rows = [row(d, raw) for d in sorted(p for p in out.iterdir() if p.is_dir() and (p / "cell.json").exists())]
    summ.write_text(json.dumps(dict(label="StudyLIVE2-pilot overnight baselines (D127-D129). PILOT, NOT A ROUND-1 "
                                          "RESULT. edf = C_inflight 8 (D128); llf and edf-piece* at C_inflight 4",
                                    rows=rows), indent=1) + "\n")
    print(f"summary: {len(rows)} runs -> {summ}")


if __name__ == "__main__":
    main()
