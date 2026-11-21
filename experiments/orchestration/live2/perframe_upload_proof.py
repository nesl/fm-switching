#!/usr/bin/env python3
"""D154 (4) / D150 SYNC (1): the per-frame robot upload contract, proved on the CPU.

NO GPU, NO server, NO model, NO measurement. Everything here is the wire form of the trace and
the event stream the coordinator receives from the emulator, on one declared cell.

What it proves, in the order the report records it:

  (0) INVARIANTS of the per-frame contract: one frame per upload record, the record offered at
      the frame's own capture time, the D2 token accounting of `data_sources.d2_batch_tokens`
      reproduced to the token, and the batch-30s frame stream a PREFIX of the per-frame one.
  (1) THE CROSS-ARM DIGEST (the proof the user named): the upload stream, arm by arm, as the
      COORDINATOR RECEIVED IT through the emulator, not merely as the trace file holds it.
      Taken over the UPLOAD records and not over whole decision logs, because decision logs
      legitimately differ by arm.
  (2) STEP 2b: the switch reaches a decision. The upload records of the two modes on one cell,
      the count of differences and the first one.
  (3) THE COST CHANGE: requests per run, tokens per request, total tokens, uplink bytes, and the
      uplink queueing the extra requests cause, before and after.
  (4) THE NEGATIVE CONTROL: with the switch at its default the trace is BYTE-IDENTICAL to the
      one `origin/main`'s own generator produces, checked against a file read out of git.

Usage: python3 perframe_upload_proof.py --out results/orchestration/live2/perframe
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(REPO / "experiments/orchestration/live"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                        # noqa: E402
import cachekeys as CK                                                  # noqa: E402
import cstate as CS                                                     # noqa: E402
import data_sources as DS                                               # noqa: E402
import emulator as EM                                                   # noqa: E402
import hybrid                                                           # noqa: E402,F401
import preflight as PF                                                  # noqa: E402
import trace as TR                                                      # noqa: E402
from bridge import EmulatorBridge                                       # noqa: E402
from coordinator import Live2Coordinator, Logs                          # noqa: E402

# THE DECLARED PROOF CELL, the same one StudyEPG-bodies used, so the two rows are comparable.
CELL = dict(seed=0, n_devices=8, ratio="50:50", run_s=300.0, mode="A")
ARMS = ("always-cloud-fcfs", "edf", "eco-llm", "warm-all-lru", "llf", "mooncake")
MODES = ("batch-30s", "per-frame")


def _canon(r: Dict[str, Any]) -> str:
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


def _upload_row(e: Dict[str, Any]) -> List[str]:
    """The canonical row of ONE upload, as the coordinator received it.

    Everything the upload carries and nothing else: who sent it, which session it belongs to,
    the upload's own id, WHEN IT ARRIVED, the ordered frames it carried, and the cumulative
    history tokens it declares. No decision, no arm state and no body: an arm that schedules
    differently must still see exactly these rows.
    """
    return [str(e["device_id"]), str(e["session_id"]), str(e["batch_id"]),
            "%.6f" % float(e["t_arrive"]), ",".join(str(f) for f in e["frame_refs"]),
            str(int(e["est_tokens"]))]


def _digest(rows: List[List[str]]) -> str:
    h = hashlib.sha256()
    for r in rows:                      # ORDER AS RECEIVED; an arm must not reorder the wire
        h.update(("|".join(r) + "\n").encode())
    return h.hexdigest()


def _trace(work: Path, robot_upload: str) -> Path:
    name = (f"seed{CELL['seed']}_n{CELL['n_devices']}_{int(CELL['run_s'])}s_{CELL['mode']}"
            + ("" if robot_upload == "batch-30s" else "_perframe"))
    tdir = work / "traces" / name
    if not (tdir / "trace.jsonl").exists():
        TR.write_trace(tdir, TR.generate_trace(
            CELL["seed"], CELL["n_devices"], CELL["ratio"], CELL["run_s"], CELL["mode"],
            **({} if robot_upload == "batch-30s" else dict(robot_upload=robot_upload))))
    return tdir


def _frame_store(tdir: Path, root: Path) -> Dict[str, Any]:
    """LESSON 1 OF StudyEPG-bodies, applied. A proof run with no resolvable frame store silently
    turns every frame into a uuid-only reference and proves nothing about bytes. The store holds
    PLACEHOLDER bytes, which is valid for a wire-form proof and for nothing else."""
    root.mkdir(parents=True, exist_ok=True)
    import harness_fixture as HF
    refs = HF.refs_in_trace(tdir)
    n_made = 0
    for ref in sorted(refs):
        p = root / ref
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(b"\xff\xd8\xff\xe0PLACEHOLDER-NOT-A-JPEG")
            n_made += 1
    rep = PF.require_frames(tdir, root, "device-only-no-server")
    return dict(n_refs=len(refs), n_written=n_made,
                n_unresolved=int(rep.get("n_missing") or 0),
                n_empty=int(rep.get("n_empty") or 0), ok=bool(rep.get("ok")),
                preflight={k: v for k, v in rep.items()
                           if k not in ("missing", "empty")})


def _run_arm(tdir: Path, rdir: Path, arm_name: str, frames_root: Path,
             robot_upload: str) -> Dict[str, Any]:
    """One arm over one trace, no server. Returns the uploads the COORDINATOR received."""
    rdir.mkdir(parents=True, exist_ok=True)
    arm = A.make_arm(arm_name)
    arm.live2_configure(gpu_kv_tokens=62944, host_tier_gib=27.0,
                        host_tier_tokens=1_000_000, targets=CS.TARGETS)
    logs = Logs(rdir).open()
    co = Live2Coordinator(arm, None, [], gpu_kv_tokens=62944, host_tier_gib=27.0,
                          host_tier_tokens=1_000_000, upload_mode=CELL["mode"],
                          window_s=CELL["run_s"], drain_s=5.0, decision_period_s=0.1,
                          seed=CELL["seed"], logs=logs,
                          run_tag=CK.run_tag(CELL["seed"], arm_name,
                                             label=("live2" if robot_upload == "batch-30s"
                                                    else "live2perframe")),
                          frames_root=frames_root, defer_images=True, dry_run=True,
                          targets=CS.TARGETS)
    # OUTPUT-ONLY instrumentation. The coordinator is not modified: its own `history_append` is
    # called exactly as before and its return value is passed straight back.
    seen: List[Dict[str, Any]] = []
    real = co.st.history_append

    def wrapped(ev):
        seen.append(dict(ev))
        return real(ev)
    co.st.history_append = wrapped
    br = EmulatorBridge(co)
    br.kind = "stub-no-server"
    em = EM.FleetEmulator(tdir, br, CELL["mode"], realtime=False, drain_s=5.0)
    rm = em.run(rdir)
    logs.close()
    n_lines = {f: sum(1 for _ in open(rdir / f))
               for f in ("request.jsonl", "decision.jsonl") if (rdir / f).exists()}
    kinds: Dict[str, int] = collections.Counter()
    if (rdir / "decision.jsonl").exists():
        for ln in open(rdir / "decision.jsonl"):
            kinds[str(json.loads(ln).get("kind"))] += 1
    return dict(arm=arm_name, uploads=seen, run_meta=rm, counts=dict(co.counts),
                n_requests=n_lines.get("request.jsonl"),
                n_decisions=n_lines.get("decision.jsonl"),
                decision_kinds=dict(sorted(kinds.items())))


def _trace_uploads(tdir: Path) -> List[Dict[str, Any]]:
    out = []
    for ln in open(tdir / "trace.jsonl"):
        r = json.loads(ln)
        if r["kind"] == "history_batch" and r["device_id"].startswith("robo"):
            out.append(r)
    return out


def invariants(tdir_b: Path, tdir_p: Path) -> Dict[str, Any]:
    ub, up = _trace_uploads(tdir_b), _trace_uploads(tdir_p)
    meta_p = json.loads((tdir_p / "trace_meta.json").read_text())
    one_frame = all(len(r["frame_refs"]) == 1 for r in up)
    bytes_per = {r["frame_bytes"] for r in up}
    # the record's offer time IS the frame's capture time, on the session's own clock
    t0 = {}
    for ln in open(tdir_p / "trace.jsonl"):
        r = json.loads(ln)
        if r["kind"] == "session_start":
            t0[r["session_id"]] = float(r["t"]) - float(r["join_offset_s"])
    at_capture = 0
    for r in up:
        x = float(r["frame_refs"][0].rsplit("|f", 1)[1])
        if abs(float(r["t"]) - (t0[r["session_id"]] + x)) < 1e-6:
            at_capture += 1
    # token accounting, reproduced from data_sources rather than asserted
    tok_ok, cum_ok = 0, 0
    per_sess_first: Dict[str, bool] = {}
    for ln in open(tdir_p / "trace.jsonl"):
        r = json.loads(ln)
        if r["kind"] in ("history_preload", "history_batch"):
            first = r["session_id"] not in per_sess_first
            per_sess_first[r["session_id"]] = True
            if int(r["est_tokens"]) == DS.d2_batch_tokens(len(r["frame_refs"]), first):
                tok_ok += 1
    runs: Dict[str, int] = collections.defaultdict(int)
    for ln in open(tdir_p / "trace.jsonl"):
        r = json.loads(ln)
        if r["kind"] in ("history_preload", "history_batch"):
            runs[r["session_id"]] += int(r["est_tokens"])
            cum_ok += int(r["cum_tokens"]) == runs[r["session_id"]]
    # the batch-30s frame stream is a PREFIX of the per-frame one, per session
    def by_sess(tdir):
        d = collections.defaultdict(list)
        for ln in open(tdir / "trace.jsonl"):
            r = json.loads(ln)
            if r["kind"] in ("history_batch", "history_preload"):
                d[r["session_id"]] += list(r["frame_refs"])
        return d
    fb, fp = by_sess(tdir_b), by_sess(tdir_p)
    prefix = {s: fp.get(s, [])[:len(fb[s])] == fb[s] for s in fb}
    extra = {s: len(fp.get(s, [])) - len(fb.get(s, []))
             for s in set(fb) | set(fp) if len(fp.get(s, [])) != len(fb.get(s, []))}
    return dict(
        n_uploads_batch=len(ub), n_uploads_perframe=len(up),
        every_record_one_frame=one_frame,
        frame_bytes_values=sorted(bytes_per),
        records_offered_at_capture_time=at_capture, records_total=len(up),
        d2_token_law_ok=tok_ok, cum_tokens_running_total_ok=cum_ok,
        batch_stream_is_a_prefix=all(prefix.values()),
        sessions_with_extra_frames=extra,
        extra_frames_total=sum(extra.values()),
        sessions_only_in_perframe=sorted(set(fp) - set(fb)),
        robot_upload_meta=meta_p.get("robot_upload"),
        history_batch_s_meta=meta_p.get("history_batch_s"))


def holding(tdir: Path) -> Dict[str, Any]:
    """TWO quantities the contract moves, measured off the trace alone (arm-independent).

    (1) DELIVERY DELAY per frame: capture time to the record's offer time. Under batch-30s a
        frame waits for its window to close, up to the 30-s period; under per-frame it does not
        wait at all.
    (2) THE HOLDING GAP at a question: `recall_question.history_tokens` is what the trace says
        the cloud holds at the ask (every D2 frame up to `t_ask`), while the coordinator's belief
        is the `cum_tokens` of the last upload it has received. Under batch-30s the two can
        disagree by up to a whole window; per-frame closes that gap to the uplink's own latency.
    """
    t0, last, delays, gaps = {}, {}, [], []
    recs = [json.loads(l) for l in open(tdir / "trace.jsonl")]
    for r in recs:
        if r["kind"] == "session_start":
            t0[r["session_id"]] = float(r["t"]) - float(r["join_offset_s"])
    for r in sorted(recs, key=lambda r: float(r.get("t", 0.0))):
        if r["kind"] == "history_preload":
            last[r["session_id"]] = int(r["cum_tokens"])
        elif r["kind"] == "history_batch" and r["device_id"].startswith("robo"):
            last[r["session_id"]] = int(r["cum_tokens"])
            for f in r["frame_refs"]:
                x = float(f.rsplit("|f", 1)[1])
                delays.append(round(float(r["t"]) - (t0[r["session_id"]] + x), 6))
        elif r["kind"] == "recall_question" and r["device_id"].startswith("robo"):
            gaps.append(int(r["history_tokens"]) - int(last.get(r["session_id"], 0)))
    def dist(v):
        if not v:
            return None
        v = sorted(v)
        return dict(n=len(v), min=v[0], p50=v[len(v) // 2], max=v[-1],
                    mean=round(sum(v) / len(v), 6))
    return dict(frame_delivery_delay_s=dist(delays), holding_gap_tokens_at_question=dist(gaps),
                n_questions_with_gap=sum(1 for g in gaps if g > 0))


def step2b(tdir_b: Path, tdir_p: Path) -> Dict[str, Any]:
    rb = [_upload_row(dict(r, t_arrive=r["t"])) for r in _trace_uploads(tdir_b)]
    rp = [_upload_row(dict(r, t_arrive=r["t"])) for r in _trace_uploads(tdir_p)]
    n = max(len(rb), len(rp))
    diffs, first = 0, None
    for i in range(n):
        a = rb[i] if i < len(rb) else None
        c = rp[i] if i < len(rp) else None
        if a != c:
            diffs += 1
            if first is None:
                first = dict(index=i, batch_30s=a, per_frame=c)
    return dict(n_batch=len(rb), n_perframe=len(rp), n_differing=diffs,
                first_difference=first,
                digest_batch=_digest(rb), digest_perframe=_digest(rp))


def _tamper(rows: List[List[str]]) -> Dict[str, Any]:
    """Positive control for the digest: change ONE token of ONE row and it must be detected."""
    if not rows:
        return dict(ok=None, note="no upload rows")
    bad = [list(r) for r in rows]
    bad[len(bad) // 2][5] = str(int(bad[len(bad) // 2][5]) + 1)
    return dict(row_perturbed=len(bad) // 2, field="est_tokens", delta_tokens=1,
                digest_changed=_digest(bad) != _digest(rows),
                n_differing_detected=sum(1 for i in range(len(rows))
                                         if rows[i] != bad[i]))


def _arrival(uploads: List[Dict[str, Any]], tdir: Path) -> Dict[str, Any]:
    """Capture time to the time the COORDINATOR received the upload, over the uplink."""
    t0 = {}
    for ln in open(tdir / "trace.jsonl"):
        r = json.loads(ln)
        if r["kind"] == "session_start":
            t0[r["session_id"]] = float(r["t"]) - float(r["join_offset_s"])
    v = []
    for e in uploads:
        for f in e["frame_refs"]:
            x = float(str(f).rsplit("|f", 1)[1])
            v.append(round(float(e["t_arrive"]) - (t0[e["session_id"]] + x), 6))
    v.sort()
    return dict(n=len(v), min=v[0], p50=v[len(v) // 2], max=v[-1],
                mean=round(sum(v) / len(v), 6)) if v else None


def cost_table(res: Dict[str, Dict[str, Any]], tdir: Dict[str, Path]) -> Dict[str, Any]:
    out = {}
    for m in MODES:
        ups = _trace_uploads(tdir[m])
        toks = [int(r["est_tokens"]) for r in ups]
        nby = [int(r["frame_bytes"]) for r in ups]
        nfr = [len(r["frame_refs"]) for r in ups]
        rm = res[m][ARMS[0]]["run_meta"]
        up = rm.get("uplink") or {}
        qp99 = [v.get("queue_p99") for v in up.values() if isinstance(v, dict)
                and v.get("queue_p99") is not None]
        qmax = [v.get("queue_max") for v in up.values() if isinstance(v, dict)
                and v.get("queue_max") is not None]
        out[m] = dict(
            upload_requests=len(ups),
            frames_total=sum(nfr),
            frames_per_request_min=min(nfr) if nfr else None,
            frames_per_request_max=max(nfr) if nfr else None,
            tokens_per_request_min=min(toks) if toks else None,
            tokens_per_request_max=max(toks) if toks else None,
            tokens_per_request_mean=round(sum(toks) / len(toks), 3) if toks else None,
            tokens_total=sum(toks),
            uplink_bytes_total=sum(nby),
            uplink_bytes_per_request_min=min(nby) if nby else None,
            uplink_bytes_per_request_max=max(nby) if nby else None,
            uplink_queue_p99_s_median=rm.get("uplink_queue_p99_s_median"),
            uplink_queue_p99_s_max=max(qp99) if qp99 else None,
            uplink_queue_max_s=max(qmax) if qmax else None,
            robot_questions=json.loads((tdir[m] / "trace_meta.json").read_text())
            .get("stats", {}).get("robot_questions_total"),
            engine_requests_by_arm={arm: res[m][arm]["n_requests"] for arm in ARMS},
            engine_decision_kinds_by_arm={arm: res[m][arm]["decision_kinds"]
                                          for arm in ARMS})
    return out


def negative_control(work: Path) -> Dict[str, Any]:
    """With the switch at its default, is the trace the one origin/main's generator writes?

    The committed generator is read OUT OF GIT, not out of the working tree, so this cannot be
    satisfied by my own copy of the file.
    """
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "origin/main"],
                          capture_output=True, text=True).stdout.strip()
    src = subprocess.run(
        ["git", "-C", str(REPO), "show",
         f"{head}:experiments/orchestration/live2/fleet/trace.py"],
        capture_output=True, text=True)
    if src.returncode != 0:
        return dict(ok=None, note="origin/main's fleet/trace.py not readable", stderr=src.stderr)
    with tempfile.TemporaryDirectory() as d:
        old = Path(d) / "fleet"
        old.mkdir()
        (old / "trace.py").write_text(src.stdout)
        sys.path.insert(0, str(old))
        for k in ("trace",):
            sys.modules.pop(k, None)
        import importlib
        old_tr = importlib.import_module("trace")
        assert Path(old_tr.__file__).parent == old, old_tr.__file__
        b_old = old_tr.generate_trace(CELL["seed"], CELL["n_devices"], CELL["ratio"],
                                      CELL["run_s"], CELL["mode"])
        sys.path.remove(str(old))
        sys.modules.pop("trace", None)
        import trace as new_tr                                            # noqa: F811
        importlib.reload(new_tr)
        b_new = new_tr.generate_trace(CELL["seed"], CELL["n_devices"], CELL["ratio"],
                                      CELL["run_s"], CELL["mode"])
    lines_old = [_canon(r) for r in b_old["records"]]
    lines_new = [_canon(r) for r in b_new["records"]]
    ans_old = [_canon(r) for r in b_old["device_answers"]]
    ans_new = [_canon(r) for r in b_new["device_answers"]]
    return dict(
        origin_main=head,
        records_byte_identical=lines_old == lines_new,
        device_answers_byte_identical=ans_old == ans_new,
        n_records=len(lines_new),
        digest_old=_digest([[x] for x in lines_old]),
        digest_new=_digest([[x] for x in lines_new]),
        fairness_digest_old=old_tr.fairness_digest(b_old["records"], CELL["mode"]),
        fairness_digest_new=new_tr.fairness_digest(b_new["records"], CELL["mode"]),
        stats_keys_added=sorted(set(b_new["stats"]) - set(b_old["stats"])),
        meta_keys_added=sorted(set(b_new["meta"]) - set(b_old["meta"])),
        per_frame_counters_zero_under_default=dict(
            robot_history_uploads=b_new["stats"]["robot_history_uploads"],
            robot_history_frames=b_new["stats"]["robot_history_frames"],
            robot_upload=b_new["stats"]["robot_upload"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "results/orchestration/live2/perframe"))
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(a.work) if a.work else (out / "work")
    work.mkdir(parents=True, exist_ok=True)

    tdir = {m: _trace(work, m) for m in MODES}
    store = {m: _frame_store(tdir[m], work / f"frames_{m}") for m in MODES}

    res: Dict[str, Dict[str, Any]] = {m: {} for m in MODES}
    for m in MODES:
        for arm in ARMS:
            res[m][arm] = _run_arm(tdir[m], work / f"run_{m}_{arm}", arm,
                                   work / f"frames_{m}", m)

    # (1) THE CROSS-ARM UPLOAD DIGEST, as the coordinator received it.
    cross: Dict[str, Any] = {}
    for m in MODES:
        rows = {arm: [_upload_row(e) for e in res[m][arm]["uploads"]] for arm in ARMS}
        dig = {arm: _digest(rows[arm]) for arm in ARMS}
        base = ARMS[0]
        pairs = {}
        for arm in ARMS[1:]:
            n_diff = sum(1 for i in range(max(len(rows[base]), len(rows[arm])))
                         if (rows[base][i] if i < len(rows[base]) else None)
                         != (rows[arm][i] if i < len(rows[arm]) else None))
            pairs[f"{base} vs {arm}"] = dict(n_differing=n_diff,
                                             equal=dig[arm] == dig[base])
        cross[m] = dict(
            arms=list(ARMS), n_uploads_per_arm={arm: len(rows[arm]) for arm in ARMS},
            digest_by_arm=dig, all_equal=len(set(dig.values())) == 1,
            pairwise_vs_first=pairs,
            trace_file_digest=_digest([_upload_row(dict(r, t_arrive=r["t"]))
                                       for r in _trace_uploads(tdir[m])]),
            decisions_by_arm={arm: res[m][arm]["n_decisions"] for arm in ARMS},
            requests_by_arm={arm: res[m][arm]["n_requests"] for arm in ARMS},
            decision_kinds_by_arm={arm: res[m][arm]["decision_kinds"] for arm in ARMS},
            decision_counts_differ_by_arm=len({json.dumps(res[m][arm]["decision_kinds"],
                                                          sort_keys=True)
                                               for arm in ARMS}) > 1,
            # CHECK 7, THE POSITIVE CONTROL. A digest comparison that cannot fail proves
            # nothing, so one row of one arm's stream is perturbed by a single token and the
            # comparison must report a difference. An impossible success is as diagnostic as an
            # impossible failure.
            tamper_control=_tamper(rows[base]),
            # ... and the arms must have DONE something different, or the equality above would
            # be the equality of six identical runs. The decision kinds are the witness.
            arrival_delay_s=_arrival(res[m][base]["uploads"], tdir[m]),
            fairness_digest_by_arm={arm: res[m][arm]["run_meta"]["fairness_digest"]
                                    for arm in ARMS},
            digests_equal_by_arm={arm: res[m][arm]["run_meta"]["digests_equal"]
                                  for arm in ARMS})

    report = dict(
        cell=CELL, arms=list(ARMS),
        what_this_is="NOT A MEASUREMENT: wire forms and event streams on the CPU, no GPU, no "
                     "server, no model, no frame encoded",
        trace_dirs={m: str(tdir[m]) for m in MODES},
        trace_sha256={m: json.loads((tdir[m] / "trace_meta.json").read_text())["trace_sha256"]
                      for m in MODES},
        fairness_digest_trace={
            m: json.loads((tdir[m] / "trace_meta.json").read_text())[
                f"fairness_digest_{CELL['mode']}"] for m in MODES},
        frame_store=store,
        invariants=invariants(tdir["batch-30s"], tdir["per-frame"]),
        cross_arm_upload_digest=cross,
        step2b=step2b(tdir["batch-30s"], tdir["per-frame"]),
        holding={m: holding(tdir[m]) for m in MODES},
        recall_prompt_tokens={
            m: sum(int(json.loads(l)["history_tokens"])
                   for l in open(tdir[m] / "trace.jsonl")
                   if json.loads(l)["kind"] == "recall_question"
                   and json.loads(l)["device_id"].startswith("robo")) for m in MODES},
        cost=cost_table(res, tdir),
        negative_control=negative_control(work),
        robot_upload_note=TR.ROBOT_UPLOAD_NOTE,
        d2_accounting=dict(tok_per_img=DS.D2_TOK_PER_IMG, header_tok=DS.D2_HEADER_TOK,
                           stride_s=DS.D2_STRIDE_S,
                           hist_frame_bytes=int(round(DS.E10A_SEMBER_Q88_D2_MEDIAN_B)),
                           history_batch_s=DS.HISTORY_BATCH_S),
    )
    try:
        from _provenance import stamp
        report["_provenance"] = stamp(script="perframe_upload_proof.py", model="none",
                                      device="cpu",
                                      n=report["cost"]["per-frame"]["upload_requests"],
                                      seed=CELL["seed"], args=a)
    except Exception as e:                                             # noqa: BLE001
        report["_provenance"] = dict(git_commit="unstamped", error=str(e))
    (out / "perframe_proofs.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k in ("invariants", "step2b", "cost", "holding",
                               "recall_prompt_tokens", "negative_control")},
                     indent=1, default=str)[:4000])
    for m in MODES:
        c = report["cross_arm_upload_digest"][m]
        print(m, "uploads/arm", c["n_uploads_per_arm"], "all_equal", c["all_equal"])
    print("wrote", out / "perframe_proofs.json")


if __name__ == "__main__":
    main()
