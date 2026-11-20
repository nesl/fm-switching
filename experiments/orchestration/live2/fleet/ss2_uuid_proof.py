"""D84 for single-shot: two SS devices drawing the same image must not share a cache entry.

Why this needs proving rather than assuming. StudySS2 measured that a repeated image is served WARM
by the multimodal encoder cache on BOTH tiers (within-image, 27.5 percent faster on the device and
33.4 percent on the cloud with prompt tokens held fixed), and that `cache_salt` does NOT prevent it
because the salt isolates the TEXT prefix cache while the multimodal cache is keyed by image
CONTENT. RefSpatial repeats a lot: 61 images carry 247 of its 277 questions. So an SS pool drawn
from it will put the same pixels in front of the engine many times in one run, and without a
per-request multimodal uuid the SS timing column would be measuring cache state.

The mechanism already exists: `cachekeys.mm_uuid(run_tag, device_id, session_id, frame_ref)`
REPLACES the engine's computed multimodal hash (vLLM 0.31.0, see cachekeys.py's references), and
the SS trace gives every opportunity its own `session_id` of the form "<device>|ss<cursor>". So the
uuid is unique per (device, opportunity) by construction. This script checks that it IS, on a real
trace, on the cases that would break it:

  (a) the SAME qid drawn by two different devices;
  (b) the SAME qid drawn twice by ONE device at different opportunities;
  (c) DIFFERENT qids whose IMAGE CONTENT is identical, which is the case a content-keyed cache
      would hit and an identifier-keyed check would miss entirely. StudySS1 taught this directly:
      by image id VizWiz val is 4,319 unique on 4,319 and passes clean, while 34 groups of
      byte-identical photos sat under different filenames.

A pass here is a statement about the REQUEST BODIES the harness will build, not about the server.
The server-side confirmation (mm_cache_queries > 0 AND mm_cache_hits == 0) is the H100's and is a
separate gate.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import trace as TR          # noqa: E402
import data_sources as DS    # noqa: E402
import cachekeys as CK       # noqa: E402


def proof(seed=0, n_devices=16, ratio="40:40:20", run_s=1200.0, arm="hybrid-F"):
    tag = CK.run_tag(seed, arm)
    b = TR.generate_trace(seed=seed, n_devices=n_devices, ratio=ratio, run_s=run_s, mode="A",
                          robot_question_set="lh_req", ss_question_set="ss2")
    recs = b["records"]
    # the SS image reaches the engine through the single history_batch of each SS session
    ss_batches = [r for r in recs if r["kind"] == "history_batch"
                  and r["device_id"].startswith("ass")]
    rows = []
    for r in ss_batches:
        for fref in r["frame_refs"]:
            rows.append(dict(device_id=r["device_id"], session_id=r["session_id"],
                             frame_ref=fref, qid=fref.rsplit("|", 1)[0],
                             uuid=CK.mm_uuid(tag, r["device_id"], r["session_id"], fref)))

    pool = {q["qid"]: q for q in DS.ss_questions("ss2", "eval")}
    by_sha = defaultdict(set)
    for q in pool.values():
        by_sha[q["image_sha16"]].add(q["qid"])

    # (a) same qid, different devices
    dev_by_qid = defaultdict(set)
    for r in rows:
        dev_by_qid[r["qid"]].add(r["device_id"])
    case_a = sorted(q for q, d in dev_by_qid.items() if len(d) > 1)
    a_rows = [r for r in rows if r["qid"] in set(case_a)]
    a_shared = sorted({u for u, n in _count(r["uuid"] for r in a_rows).items() if n > 1})

    # (b) same qid, same device, twice
    pairs = _count((r["device_id"], r["qid"]) for r in rows)
    case_b = sorted(k for k, n in pairs.items() if n > 1)
    b_rows = [r for r in rows if (r["device_id"], r["qid"]) in set(case_b)]
    b_shared = sorted({u for u, n in _count(r["uuid"] for r in b_rows).items() if n > 1})

    # (c) different qids, identical image content
    drawn = {r["qid"] for r in rows}
    content_groups = {sha: sorted(q for q in qs if q in drawn)
                      for sha, qs in by_sha.items() if len(qs) > 1}
    content_groups = {k: v for k, v in content_groups.items() if len(v) > 1}
    c_rows = [r for r in rows if any(r["qid"] in v for v in content_groups.values())]
    c_shared = sorted({u for u, n in _count(r["uuid"] for r in c_rows).items() if n > 1})

    all_shared = sorted({u for u, n in _count(r["uuid"] for r in rows).items() if n > 1})
    return dict(
        cell=dict(seed=seed, n_devices=n_devices, ratio=ratio, run_s=run_s, arm=arm,
                  run_tag=tag, ss_question_set="ss2", robot_question_set="lh_req"),
        n_ss_image_submissions=len(rows),
        n_distinct_uuids=len(set(r["uuid"] for r in rows)),
        n_distinct_qids_drawn=len(drawn),
        uuid_collisions_overall=all_shared,
        case_a_same_qid_two_devices=dict(
            n_qids=len(case_a), n_submissions=len(a_rows), colliding_uuids=a_shared,
            pass_=not a_shared,
            note="the case the ruling names. A collision here would mean two devices share a "
                 "multimodal cache entry."),
        case_b_same_qid_same_device_twice=dict(
            n_pairs=len(case_b), n_submissions=len(b_rows), colliding_uuids=b_shared,
            pass_=not b_shared,
            note="a repeat by one device at a LATER opportunity. For single-shot the intended "
                 "condition is cold per image, so these must also differ; that is the one place "
                 "where SS deliberately forgoes the within-device reuse D84 otherwise preserves."),
        case_c_identical_image_content_different_qids=dict(
            n_content_groups=len(content_groups), n_submissions=len(c_rows),
            colliding_uuids=c_shared, pass_=not c_shared,
            groups_sample={k: v for k, v in list(content_groups.items())[:5]},
            note="the case a content-keyed cache WOULD hit and an identifier check would miss. "
                 "StudySS1: by image id VizWiz val is 4,319 unique on 4,319 and passes clean, "
                 "while 34 groups of byte-identical photos sat under different filenames."),
        negative_control=_negative_control(rows, tag),
        register="request bodies, not server behaviour. The server-side gate "
                 "(mm_cache_queries > 0 AND mm_cache_hits == 0) is the H100's and is separate.")


def _negative_control(rows, tag):
    """A check that cannot fail is worthless, so show the check CAN fail.

    Recompute the uuids with the device and session dropped from the key, which is what a
    content-or-identifier-keyed scheme would do, and confirm collisions DO appear. If this control
    reports no collisions, the trace holds no repeated image and the main result is vacuous.
    """
    naive = _count(r["frame_ref"] for r in rows)
    collisions = sorted(k for k, n in naive.items() if n > 1)
    return dict(
        scheme="frame_ref alone, device and session dropped from the key",
        n_colliding_keys=len(collisions),
        max_submissions_on_one_key=max(naive.values()) if naive else 0,
        control_can_fail=bool(collisions),
        note="collisions MUST appear here. They do not appear in the real scheme, so the real "
             "scheme is doing the work rather than the trace happening to hold no repeats.")


def _count(it):
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def main():
    out = {}
    for n in (16, 20, 32):
        out["n%d" % n] = proof(n_devices=n)
    p = DS.ROOT / "results/orchestration/live2/lh_req/ss2_uuid_proof.json"
    p.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", p)
    for k, v in out.items():
        print("%-5s submissions %-5d distinct uuids %-5d qids %-4d | a %s  b %s  c %s | control can fail %s (max %d on one naive key)"
              % (k, v["n_ss_image_submissions"], v["n_distinct_uuids"], v["n_distinct_qids_drawn"],
                 v["case_a_same_qid_two_devices"]["pass_"],
                 v["case_b_same_qid_same_device_twice"]["pass_"],
                 v["case_c_identical_image_content_different_qids"]["pass_"],
                 v["negative_control"]["control_can_fail"],
                 v["negative_control"]["max_submissions_on_one_key"]))


if __name__ == "__main__":
    main()
