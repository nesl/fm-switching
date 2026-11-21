#!/usr/bin/env python3
"""D158 (2) SUBMISSION-RACE FIX: the three proofs the user named, plus the declared cost.

The fault, diagnosed on the H100's own request logs before this file existed: `coordinator`
marked a frame's bytes sent at SUBMISSION, so a later request on the same session sent that frame
as a uuid-only reference before the engine had registered the piece carrying its bytes, and the
engine answered HTTP 400. On CAL1F `warm-all-lru` that was 226 400s, of which ZERO had a previous
request on the same session that had completed 200 before this one was sent.

The fix splits the one set into a SUBMISSION-time set (build progress, unchanged, so no decision
moves) and a CONFIRMATION-time set (reference eligibility, advanced only on a 200).

Subcommands, each writing one JSON under `results/orchestration/live2/racefix/`:

  prescreen <out.json> [pool]          /  prescreen-compare <before> <after> <out.json>
      PROOF 1 as D158 names it: `baseline_prescreen.one` over `arms.ARM_NAMES` (50 arms), one
      side per worktree, then the comparison. NECESSARY AND NOT SUFFICIENT: that cell passes no
      `frames_root`, so no frame carries bytes and the quantity the fix branches on is empty.

  side <out.json> [--confirm200] [--arms a,b]
      PROOFS 1b AND 2 AND THE COST, one side of the before/after pair. A dry cell WITH A REAL
      FRAME STORE, so frames actually carry bytes and `sent_bytes_for` actually grows: without a
      store `_path` returns None for every frame, nothing is ever marked sent, and a proof run
      there cannot exercise the mechanism at all (the same false-proof shape the gate report
      records for proof (a)). Records every decision AND every wire body. `--confirm200` makes
      the dry future report HTTP 200 so confirmation can advance on the dry timeline; without it
      a dry run reports no status, nothing is ever confirmed, and every reference becomes bytes.

  compare <before.json> <after.json> <out.json>
      Diffs two `side` outputs: decisions (proof 1b) and bodies (proof 2).

  replay <run_dir> <out.json>
      PROOF 3. Replays the committed CAL1F `warm-all-lru` request log under both rules and counts
      the references sent for bytes the engine had not acknowledged. No server: this is about
      what the body contains.

REGISTER. `side` and `compare` are a DRY cell: a determinism and wire-form test, never a latency,
quality or capacity result. `replay` is a RECONSTRUCTION from a committed log under the two
rules, not a re-execution of the coordinator, and it is labelled so wherever it is reported.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (HERE, HERE / "hybrid", HERE / "fleet", HERE / "tests", HERE / "scorer", HERE / "data",
           REPO / "experiments/orchestration", REPO / "experiments/orchestration/live",
           REPO / "experiments/orchestration/baselines",
           REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# THE DECLARED CELL for proofs 1b and 2 and for the cost. Fixed here rather than passed, so the
# two sides of the comparison cannot differ in it.
SEED, NDEV, RUN_S, MODE = 10, 12, 600.0, "A"
ARMS = ("warm-all-lru", "edf")
JPEG_DIR = Path(os.path.expanduser("~/data/live2/jpeg/nexar_q90/frames"))

# Fields of a decision row that are wall-clock or environment dependent and so are not part of
# the identity claim. Taken from the committed prescreen's own STRIP list where it has one.
try:
    from test_hybrid import STRIP as _STRIP
    STRIP = set(_STRIP)
except Exception:                                                          # noqa: BLE001
    STRIP = {"latency_ms", "wall_ms", "cpu_ms"}


# ------------------------------------------------------------------ proof 1
PRESCREEN_FIELDS = ["decisions", "digest", "digest_setwise"]


def prescreen_side(out: Path, pool: int = 6) -> dict:
    """One side of PROOF 1: `baseline_prescreen.one` over `arms.ARM_NAMES`, pooled.

    Serial is about six hours and pooled about half an hour, which is the only reason the pool is
    here; it changes nothing about the cell. Run this in a clean worktree at origin/main and again
    in the patched tree, then `prescreen_compare` the two.
    """
    import multiprocessing as mp
    import subprocess
    import time
    import arms as A
    import baseline_prescreen as BP
    import hybrid

    hybrid.register()
    names = sorted(A.ARM_NAMES)
    t0 = time.time()
    got = {}
    with mp.Pool(pool) as pl:
        for arm, rec in pl.imap_unordered(BP.one, names):
            got[arm] = {k: rec.get(k) for k in PRESCREEN_FIELDS + ["error"]}
            print("  %-36s %7s %17s %s" % (arm, rec.get("decisions", "-"),
                                           rec.get("digest", "-"),
                                           "ERROR" if rec.get("error") else ""), flush=True)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    doc = _stamp(dict(repo=str(REPO), git_commit=head, arms_checked=len(names), pool=pool,
                      cell=dict(seed=BP.SEED, n_devices=BP.N, run_s=BP.RUN_S, ratio=BP.RATIO,
                                dry=True, **BP.LH),
                      wall_s=round(time.time() - t0, 1), arms=got), n=len(names), seed=BP.SEED)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=float))
    return doc


def prescreen_compare(before: Path, after: Path, out: Path, prior: Path = None) -> dict:
    """PROOF 1, and the cross-check that validates the BEFORE side rather than only the result."""
    B = json.loads(before.read_text())
    A1 = json.loads(after.read_text())
    arms = sorted(set(B["arms"]) | set(A1["arms"]))
    rows, diff, errs = {}, [], []
    for a in arms:
        b, f = B["arms"].get(a), A1["arms"].get(a)
        if b is None or f is None:
            diff.append(dict(arm=a, why="missing on one side"))
            continue
        if b.get("error") or f.get("error"):
            errs.append(dict(arm=a, before=b.get("error"), after=f.get("error")))
        same = all(b.get(k) == f.get(k) for k in PRESCREEN_FIELDS)
        rows[a] = dict(before={k: b.get(k) for k in PRESCREEN_FIELDS},
                       after={k: f.get(k) for k in PRESCREEN_FIELDS}, identical=same)
        if not same:
            diff.append(dict(arm=a, before=rows[a]["before"], after=rows[a]["after"]))

    xcheck = None
    if prior is not None and prior.exists():
        pb = json.loads(prior.read_text()).get("before", {})
        agree, disagree, missing = [], [], []
        for a, v in B["arms"].items():
            q = pb.get(a)
            if q is None:
                missing.append(a)
            elif all(q.get(k) == v.get(k) for k in PRESCREEN_FIELDS):
                agree.append(a)
            else:
                disagree.append(dict(arm=a, committed={k: q.get(k) for k in PRESCREEN_FIELDS},
                                     this_run={k: v.get(k) for k in PRESCREEN_FIELDS}))
        xcheck = dict(
            _why=("the BEFORE side is an unmodified worktree, so a committed proof's digests are "
                  "the obvious positive control. IT IS NOT ONE HERE: see _reading."),
            _reading=("22 of 50 agree and 28 DISAGREE, because 13 commits touched "
                      "experiments/orchestration/live2/ between that proof's base (e04a7c0) and "
                      "this one, several of which legitimately move decisions (EP-G bodies, "
                      "per-frame upload, measured warm device latency, v5-rules, the "
                      "counterfactual engine). Recorded as a REJECTED control, not a pass: the "
                      "one arm that matched would otherwise stand in for a general agreement "
                      "that does not hold."),
            source=str(prior.relative_to(REPO)) if str(prior).startswith(str(REPO)) else str(prior),
            agree=len(agree), disagree=disagree, not_in_committed_proof=sorted(missing))

    doc = _stamp(dict(
        _what=("D158 (2) proof 1: dry decisions byte-identical before and after on every "
               "committed arm."),
        method=("baseline_prescreen.one over arms.ARM_NAMES (50 arms), multiprocessing.Pool(6), "
                "in a detached worktree at origin/main BEFORE the patch and in the patched tree "
                "AFTER. Same seed, n, run_s, ratio and question sets."),
        _register=("a DRY cell with NO frames_root, so _path returns None for every frame and "
                   "sent_bytes_for never grows. This proves the change cannot move a decision in "
                   "a regime where NO FRAME CARRIES BYTES. It is NECESSARY AND NOT SUFFICIENT; "
                   "the store-backed proof 1b in proof12_confirm200.json is the exercised one."),
        git_commit_before=B.get("git_commit"), git_commit_after=A1.get("git_commit"),
        _commit_note=("the two HEADs are equal because the AFTER side is the same base with the "
                      "patch applied as uncommitted working-tree changes; that is the intended "
                      "comparison, not an error"),
        cell=B.get("cell"), arms_checked=len(rows), fields_compared=PRESCREEN_FIELDS,
        byte_identical=(not diff), differing=diff, errors=errs,
        wall_s_before=B.get("wall_s"), wall_s_after=A1.get("wall_s"),
        cross_check_against_committed_patch1=xcheck, arms=rows), n=len(rows))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=float))
    return doc


# ------------------------------------------------------------------ the store
def _real_frame_store(tdir: Path, root: Path) -> dict:
    """A file per frame_ref the trace needs, backed by REAL committed JPEGs.

    The committed test fixture writes a 1-byte file per frame, which is enough to make `_path`
    resolve but makes every uplink-byte number meaningless. The cost this fix charges is
    re-uploaded image bytes, so the store has to hold real images or the cost cannot be measured.
    Frames are assigned round-robin over the committed nexar_q90 set; the assignment is
    deterministic in the sorted frame_ref order, so both sides of the comparison get identical
    bytes for identical frames.
    """
    pool = sorted(p for p in JPEG_DIR.rglob("*") if p.is_file())
    if not pool:
        raise SystemExit("no committed JPEGs under %s; the cost cannot be measured" % JPEG_DIR)
    refs = set()
    for ln in open(tdir / "trace.jsonl"):
        r = json.loads(ln)
        if r.get("frame_ref"):
            refs.add(r["frame_ref"])
        for x in (r.get("frame_refs") or ()):
            refs.add(x)
    root.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for i, ref in enumerate(sorted(refs)):
        p = root / ref
        p.parent.mkdir(parents=True, exist_ok=True)
        src = pool[i % len(pool)]
        if not p.exists():
            p.write_bytes(src.read_bytes())
        sizes[ref] = p.stat().st_size
    return dict(n_frames=len(refs), pool=len(pool), mean_bytes=round(statistics.mean(
        sizes.values())) if sizes else 0, median_bytes=round(statistics.median(sizes.values()))
        if sizes else 0, total_bytes=sum(sizes.values()))


# ------------------------------------------------------------------ one side
def _body_record(sub, frames):
    """What went on the wire for one request, in a form a diff can read.

    `image_url is None` IS the uuid-only reference form (`bodies.image_part`), so the per-part
    flags below are read off the body that was built and not off the coordinator's intent.
    """
    import bodies as B
    parts = [p for p in sub.body.get("messages", [{}])[0].get("content", ())
             if isinstance(p, dict) and p.get("type") == "image_url"]
    as_ref = [p.get("image_url") is None for p in parts]
    wire = B.strip_internal(sub.body, strip_hints=False)
    blob = json.dumps(wire, sort_keys=True, separators=(",", ":"), default=str)
    return dict(
        request_id=sub.request_id, decision_id=sub.decision_id, kind=sub.kind,
        device_id=sub.device_id, session_id=sub.session_id,
        opportunity_id=sub.opportunity_id, est_tokens=int(sub.est_tokens),
        n_parts=len(parts), n_as_reference=sum(as_ref), n_as_bytes=len(parts) - sum(as_ref),
        frame_refs=[f["frame_ref"] for f in frames],
        bytes_flags=[bool(f.get("path") is not None) for f in frames],
        body_sha256=hashlib.sha256(blob.encode()).hexdigest()[:16],
        wire_bytes=len(blob.encode()),
        mm_uuids=list(sub.mm_uuids))


def side(out: Path, confirm200: bool, arms) -> dict:
    import arms as A
    import cachekeys as CK
    import coordinator as CO
    import cstate as CS
    import emulator as EM
    import hybrid
    import trace as TR
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK

    hybrid.register()
    res = {}
    for arm_name in arms:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = d / "t"
            TR.write_trace(tdir, TR.generate_trace(SEED, NDEV, "50:50", RUN_S, MODE))
            store = _real_frame_store(tdir, d / "frames")
            arm = A.make_arm(arm_name)
            arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
            logs = Logs(d / "r").open()
            co = Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                  host_tier_tokens=HOST_TOK, upload_mode=MODE, window_s=RUN_S,
                                  drain_s=5.0, seed=SEED, logs=logs,
                                  run_tag=CK.run_tag(SEED, arm_name), dry_run=True,
                                  frames_root=d / "frames")
            bodies = []
            real_submit = co._submit

            def spy(**kw):
                rid = real_submit(**kw)
                _fut, sub = co.futures[-1]
                bodies.append(_body_record(sub, kw["frames"]))
                return rid

            co._submit = spy
            # A dry future reports no http_status, so nothing is ever confirmed and every
            # reference goes out as bytes. That is the conservative direction and the honest
            # default, but it is also the MAXIMAL-change condition, so it cannot show that only
            # in-flight references change. `--confirm200` reports 200 on the dry timeline, which
            # is what lets confirmation advance deterministically. BOTH SIDES of the comparison
            # get the same patch, so it cannot favour either.
            real_result = CO._DryFuture.result
            if confirm200:
                def result200(self):
                    r = real_result(self)
                    r["http_status"] = 200
                    return r
                CO._DryFuture.result = result200
            try:
                EM.FleetEmulator(tdir, EmulatorBridge(co), MODE, realtime=False,
                                 drain_s=5.0).run(d / "r")
            finally:
                CO._DryFuture.result = real_result
            logs.close()
            rows = [json.loads(l) for l in open(d / "r" / "decision.jsonl")]
            rows = [{k: v for k, v in r.items() if k not in STRIP} for r in rows]
            sess_sent = {sid: len(s.sent_bytes_for) for sid, s in co.st.sessions.items()}
            sess_conf = {sid: len(getattr(s, "confirmed_bytes_for", ()))
                         for sid, s in co.st.sessions.items()}
            res[arm_name] = dict(
                store=store,
                decisions=len(rows),
                decision_digest=hashlib.sha256(json.dumps(
                    rows, sort_keys=True, separators=(",", ":"),
                    default=float).encode()).hexdigest()[:16],
                rows=rows,
                bodies=bodies,
                n_requests=len(bodies),
                frames_sent_total=sum(sess_sent.values()),
                frames_confirmed_total=sum(sess_conf.values()),
                sessions_with_sent_bytes=sum(1 for v in sess_sent.values() if v),
                wire_bytes_total=sum(b["wire_bytes"] for b in bodies),
                parts_as_bytes_total=sum(b["n_as_bytes"] for b in bodies),
                parts_as_reference_total=sum(b["n_as_reference"] for b in bodies),
                counts={k: v for k, v in sorted(co.counts.items())})
            print("  %-16s decisions %6d requests %5d sent %5d confirmed %5d bytes_parts %6d"
                  % (arm_name, len(rows), len(bodies), sum(sess_sent.values()),
                     sum(sess_conf.values()), res[arm_name]["parts_as_bytes_total"]), flush=True)
    doc = _stamp(dict(_what=__doc__.strip().splitlines()[0],
                      cell=dict(seed=SEED, n_devices=NDEV, run_s=RUN_S, mode=MODE,
                                ratio="50:50", dry=True,
                                frame_store="real nexar_q90 JPEGs", confirm200=confirm200),
                      arms=res), n=len(res))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=float))
    return doc


# ------------------------------------------------------------------ compare
def compare(before: Path, after: Path, out: Path) -> dict:
    A0 = json.loads(before.read_text())
    A1 = json.loads(after.read_text())
    res = {}
    for arm in sorted(set(A0["arms"]) & set(A1["arms"])):
        b, a = A0["arms"][arm], A1["arms"][arm]
        # PROOF 1b: decisions byte-identical, on a cell where frames really carry bytes.
        dec_same = b["rows"] == a["rows"]
        first_dec = next((i for i, (x, y) in enumerate(zip(b["rows"], a["rows"])) if x != y), None)
        # PROOF 2: body-level diff, request by request, matched on request_id.
        bb = {x["request_id"]: x for x in b["bodies"]}
        ab = {x["request_id"]: x for x in a["bodies"]}
        common = sorted(set(bb) & set(ab), key=lambda r: int(r[1:]))
        changed, bad, became_bytes = [], [], 0
        for rid in common:
            x, y = bb[rid], ab[rid]
            if x["body_sha256"] == y["body_sha256"]:
                continue
            # The ONLY admissible change: one or more parts that were uuid-only references are
            # now carrying bytes, with everything else about the request the same. Anything else
            # is a failure of this proof and is recorded as such rather than summarised away.
            same_shape = (x["frame_refs"] == y["frame_refs"] and x["kind"] == y["kind"]
                          and x["est_tokens"] == y["est_tokens"]
                          and x["mm_uuids"] == y["mm_uuids"]
                          and x["n_parts"] == y["n_parts"]
                          and x["session_id"] == y["session_id"]
                          and x["decision_id"] == y["decision_id"])
            flips = [(i, p, q) for i, (p, q) in enumerate(zip(x["bytes_flags"], y["bytes_flags"]))
                     if p != q]
            ref_to_bytes = bool(flips) and all(q and not p for _i, p, q in flips)
            rec = dict(request_id=rid, kind=x["kind"], session_id=x["session_id"],
                       n_parts=x["n_parts"],
                       references_before=x["n_as_reference"], references_after=y["n_as_reference"],
                       bytes_before=x["n_as_bytes"], bytes_after=y["n_as_bytes"],
                       wire_bytes_before=x["wire_bytes"], wire_bytes_after=y["wire_bytes"],
                       n_flipped=len(flips), same_shape=same_shape,
                       reference_became_bytes=ref_to_bytes)
            changed.append(rec)
            became_bytes += len(flips) if ref_to_bytes else 0
            if not (same_shape and ref_to_bytes):
                bad.append(rec)
        # Did any body that had NO bare reference change? That would be the failure the proof
        # is looking for, and it is asked as its own question rather than inferred.
        no_ref_changed = [r["request_id"] for r in changed
                          if bb[r["request_id"]]["n_as_reference"] == 0]
        res[arm] = dict(
            proof1b_decisions_identical=dec_same,
            decisions_before=b["decisions"], decisions_after=a["decisions"],
            decision_digest_before=b["decision_digest"], decision_digest_after=a["decision_digest"],
            first_differing_decision=first_dec,
            mechanism_exercised=dict(
                frames_sent_before=b["frames_sent_total"], frames_sent_after=a["frames_sent_total"],
                frames_confirmed_after=a["frames_confirmed_total"],
                sessions_with_sent_bytes=a["sessions_with_sent_bytes"],
                reference_parts_before=b["parts_as_reference_total"],
                reference_parts_after=a["parts_as_reference_total"]),
            requests_before=len(bb), requests_after=len(ab),
            requests_only_on_one_side=sorted(set(bb) ^ set(ab)),
            bodies_compared=len(common),
            bodies_changed=len(changed),
            bodies_changed_for_another_reason=bad,
            bodies_changed_with_no_bare_reference=no_ref_changed,
            proof2_pass=(not bad and not no_ref_changed
                         and not (set(bb) ^ set(ab))),
            parts_reference_to_bytes=became_bytes,
            cost=dict(
                wire_bytes_before=b["wire_bytes_total"], wire_bytes_after=a["wire_bytes_total"],
                wire_bytes_delta=a["wire_bytes_total"] - b["wire_bytes_total"],
                wire_bytes_ratio=(round(a["wire_bytes_total"] / b["wire_bytes_total"], 4)
                                  if b["wire_bytes_total"] else None),
                image_parts_as_bytes_before=b["parts_as_bytes_total"],
                image_parts_as_bytes_after=a["parts_as_bytes_total"],
                image_parts_resent=a["parts_as_bytes_total"] - b["parts_as_bytes_total"]),
            counts_before=b["counts"], counts_after=a["counts"],
            changed_sample=changed[:10])
        print("  %-16s proof1b %s  proof2 %s  bodies changed %d/%d  wire x%s"
              % (arm, "PASS" if dec_same else "FAIL",
                 "PASS" if res[arm]["proof2_pass"] else "FAIL", len(changed), len(common),
                 res[arm]["cost"]["wire_bytes_ratio"]), flush=True)
    doc = _stamp(dict(_what="D158 (2) proofs 1b and 2 and the declared cost, before vs after.",
                      cell_before=A0["cell"], cell_after=A1["cell"], arms=res,
                      proof1b_pass=all(v["proof1b_decisions_identical"] for v in res.values()),
                      proof2_pass=all(v["proof2_pass"] for v in res.values())), n=len(res))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=float))
    return doc


# ------------------------------------------------------------------ proof 3
def _load_requests(run_dir: Path):
    p = run_dir / "request.jsonl.gz"
    if p.exists():
        return [json.loads(l) for l in gzip.open(p, "rt")]
    return [json.loads(l) for l in open(run_dir / "request.jsonl")]


def _sim(rs, rule: str):
    """One session's log under one rule. Returns per request (references, bytes, dangerous).

    THE TEST IS THE SAME FOR BOTH RULES and it is the engine's side of the contract: a uuid-only
    reference is resolvable only if some earlier request that carried that frame's bytes came
    back 200 before this request was submitted. The two rules differ in WHAT THEY SEND, never in
    how the consequence is judged, which is what makes the two columns comparable.

      old   a frame carries bytes on its FIRST appearance on the session and is a reference ever
            after, because `sent_bytes_for` grew at submission.
      new   a frame carries bytes until the request that carried them RETURNED 200.
    """
    seen = set()
    acked = {}                 # uuid -> earliest t_done of a 200 that CARRIED its bytes
    carried = collections.defaultdict(list)   # uuid -> [(t_done, status)] of carrying requests
    out = []
    for r in rs:
        ts, td, st = r["t_submit"], r.get("t_done"), r.get("http_status")
        u = list(r["mm_uuids"])
        if rule == "old":
            ref = [x for x in u if x in seen]
            byt = [x for x in u if x not in seen]
        else:
            ref = [x for x in u if x in acked and acked[x] <= ts]
            byt = [x for x in u if x not in acked or acked[x] > ts]
        danger = [x for x in ref
                  if not any(s2 == 200 and d2 is not None and d2 <= ts
                             for d2, s2 in carried[x])]
        out.append(dict(request_id=r["request_id"], http_status=st, t_submit=ts,
                        device_id=r["device_id"], n_parts=len(u),
                        references=len(ref), bytes=len(byt), dangerous=len(danger)))
        for x in byt:
            carried[x].append((td, st))
            if st == 200 and td is not None:
                acked[x] = min(acked.get(x, td), td)
        seen.update(u)
    return out


def replay(run_dir: Path, out: Path) -> dict:
    """PROOF 3. The CAL1F `warm-all-lru` sequence under the old rule and under the new one.

    Read from the committed `request.jsonl.gz`, whose `mm_uuids` are the per-frame multimodal
    cache keys the engine itself resolves, so a uuid is the right identity for a proof about what
    the engine can and cannot resolve. Requests are replayed in `t_submit` order within a
    session, which is the order the coordinator put them on the wire.

    A DANGEROUS REFERENCE is a part sent as a uuid-only reference for bytes the engine had not
    acknowledged when the request was submitted. It is what produces the HTTP 400.

    The new rule's count is zero BY CONSTRUCTION, so the number that carries the proof is not
    that zero on its own: it is the old rule's count on the same sequence, and the check that the
    old rule's dangerous requests are the ones that actually failed. Both are reported, and so is
    the reverse check (a 200 that carried a dangerous reference), because a mechanism that also
    fires on the successes would not be the explanation.

    REGISTER: a reconstruction of the two rules over a committed log, not a re-execution of the
    coordinator and not a server round trip.
    """
    rows = _load_requests(run_dir)
    sess = [r for r in rows if r.get("session_id") and r.get("mm_uuids")]
    by_sess = collections.defaultdict(list)
    for r in sorted(sess, key=lambda r: (r["session_id"], r["t_submit"], r["request_id"])):
        by_sess[r["session_id"]].append(r)

    sim = {"old": {}, "new": {}}
    for rule in ("old", "new"):
        for sid, rs in by_sess.items():
            for rec in _sim(rs, rule):
                sim[rule][rec["request_id"]] = rec

    def agg(rule, pred=lambda r: True):
        v = [r for r in sim[rule].values() if pred(r)]
        return dict(requests=len(v),
                    with_a_dangerous_reference=sum(1 for r in v if r["dangerous"]),
                    dangerous_reference_parts=sum(r["dangerous"] for r in v),
                    image_parts_carrying_bytes=sum(r["bytes"] for r in v),
                    image_parts_as_reference=sum(r["references"] for r in v))

    is400 = lambda r: r["http_status"] == 400                              # noqa: E731
    is200 = lambda r: r["http_status"] == 200                              # noqa: E731
    old_all, new_all = agg("old"), agg("new")
    n400 = sum(1 for r in sim["old"].values() if is400(r))
    n200 = sum(1 for r in sim["old"].values() if is200(r))
    doc = dict(
        _what="D158 (2) proof 3: the CAL1F warm-all-lru failing sequence under both rules.",
        _register=("a RECONSTRUCTION of the two rules over the committed request log, not a "
                   "re-execution of the coordinator and not a server round trip"),
        run_dir=(str(run_dir.relative_to(REPO)) if str(run_dir).startswith(str(REPO))
                 else str(run_dir)),
        requests_total=len(rows), session_requests=len(sess), sessions=len(by_sess),
        http_400=n400, http_200=n200,
        old_rule=old_all, new_rule=new_all,
        proof3_pass=(new_all["dangerous_reference_parts"] == 0
                     and old_all["dangerous_reference_parts"] > 0 and n400 > 0),
        on_the_400s=dict(old=agg("old", is400), new=agg("new", is400)),
        control_on_the_200s=dict(
            _why=("the reverse check: if the old rule's dangerous references were as common on "
                  "the requests that SUCCEEDED, the mechanism would not be the explanation"),
            old=agg("old", is200), new=agg("new", is200)),
        cost=dict(image_parts_carrying_bytes_before=old_all["image_parts_carrying_bytes"],
                  image_parts_carrying_bytes_after=new_all["image_parts_carrying_bytes"],
                  image_parts_resent=(new_all["image_parts_carrying_bytes"]
                                      - old_all["image_parts_carrying_bytes"]),
                  ratio=(round(new_all["image_parts_carrying_bytes"]
                               / old_all["image_parts_carrying_bytes"], 4)
                         if old_all["image_parts_carrying_bytes"] else None)),
        sample_400s=[sim["old"][k] | dict(new=sim["new"][k])
                     for k in list(sorted(sim["old"], key=lambda x: int(x[1:])))
                     if is400(sim["old"][k])][:8])
    _stamp(doc, n=len(sess))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=float))
    return doc


def _stamp(doc: dict, n: int, seed: int = SEED) -> dict:
    """CLAUDE.md provenance convention. A dry / replay harness has no model and no accelerator,
    and says so rather than naming one it did not use."""
    try:
        import _provenance
        doc["_provenance"] = _provenance.stamp(script="racefix_proofs.py", model="none-dry",
                                               device="none-cpu", n=n, seed=seed)
    except Exception as e:                                                 # noqa: BLE001
        doc["_provenance"] = {"git_commit": "unstamped", "script": "racefix_proofs.py",
                              "note": "stamp failed: %r" % (e,)}
    return doc


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    OUTDIR = REPO / "results/orchestration/live2/racefix"
    if cmd == "side":
        out = Path(rest[0])
        confirm = "--confirm200" in rest
        arms = ARMS
        for i, a in enumerate(rest):
            if a == "--arms":
                arms = tuple(rest[i + 1].split(","))
        d = side(out, confirm, arms)
        print("wrote", out)
    elif cmd == "compare":
        d = compare(Path(rest[0]), Path(rest[1]), Path(rest[2]))
        print("proof1b", d["proof1b_pass"], "proof2", d["proof2_pass"])
    elif cmd == "prescreen":
        d = prescreen_side(Path(rest[0]), int(rest[1]) if len(rest) > 1 else 6)
        print("wrote", rest[0], "in", d["wall_s"], "s")
    elif cmd == "prescreen-compare":
        d = prescreen_compare(Path(rest[0]), Path(rest[1]), Path(rest[2]),
                              REPO / "results/orchestration/live2/v5/patch1_byte_identity_proof.json")
        print("arms", d["arms_checked"], "byte_identical", d["byte_identical"],
              "differing", len(d["differing"]), "errors", len(d["errors"]))
    elif cmd == "replay":
        d = replay(Path(rest[0]), Path(rest[1]) if len(rest) > 1
                   else OUTDIR / "cal1f_replay.json")
        print(json.dumps({k: v for k, v in d.items()
                          if k in ("http_400", "http_200", "old_rule", "new_rule",
                                   "proof3_pass", "on_the_400s", "control_on_the_200s",
                                   "cost")}, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
