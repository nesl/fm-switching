"""Proofs for full v5 component 2 (TOUCH as a real request). Dry, no GPU."""
import collections, json, sys, time
from pathlib import Path

H = Path(__file__).resolve().parent
R = H.parents[2]
for p in (str(H), str(H / "fleet"), str(H / "scorer"), str(H / "hybrid"), str(H / "v5"),
          str(R / "experiments/orchestration/live"), str(R / "experiments/orchestration/baselines"),
          str(R / "experiments/orchestration/baselines/reconstructed"),
          str(R / "experiments/orchestration/sim"), str(R / "experiments/lib"),
          str(R / "experiments/orchestration")):
    if p not in sys.path:
        sys.path.insert(0, p)

import costs as C            # noqa: E402
import touch_policy as TP    # noqa: E402

OUT = R / "results/orchestration/live2/frozen_test/touch_proofs.json"


def main():
    res, t0 = {}, time.time()

    # P1 PRICED BY PREDICTED CACHE STATE, and the price must VARY with the state. A constant here
    # would mean the price carries no information about survival, which is the whole point (D160).
    pure = {"gpu": {"gpu": 1.0}, "host": {"host": 1.0}, "cold": {"cold": 1.0}}
    prices = {k: TP.touch_price_gpu_s(11000, b, C) for k, b in pure.items()}
    res["P1_price_by_state"] = dict(prices_11k=prices,
                                    distinct=len({round(v, 6) for v in prices.values()}),
                                    cold_over_gpu=(prices["cold"] / prices["gpu"]
                                                   if prices["gpu"] else None))
    p1 = len({round(v, 6) for v in prices.values()}) == 3 and prices["cold"] > prices["gpu"]

    # P2 M6 GUARD. A mixed touch LOSES host-warmth, so it must be refused, and StudyRES1 R3 makes
    # a near-boundary belief count as mixed.
    cases = {
        "wholly_gpu": {"gpu": 1.0},
        "wholly_host": {"host": 1.0},
        "near_boundary_host": {"host": 0.80, "gpu": 0.20},
        "mixed_half": {"host": 0.5, "gpu": 0.5},
        "cold": {"cold": 1.0},
    }
    g = {k: dict(zip(("allowed", "reason"), TP.mixed_touch_guard(v))) for k, v in cases.items()}
    res["P2_m6_guard"] = g
    p2 = (g["wholly_gpu"]["allowed"] and g["wholly_host"]["allowed"]
          and not g["near_boundary_host"]["allowed"] and not g["mixed_half"]["allowed"]
          and not g["cold"]["allowed"])

    # P3 and P4. WHY NOT A DRY CELL, stated because my first attempt WAS one and it produced a
    # clean-looking zero. `coordinator._promote_confirmed`'s own docstring: "A DRY RUN HAS NO
    # ENGINE AND NO `http_status`, so nothing is ever promoted and every reference goes out as
    # bytes", and `_DryFuture.result()` returns http_status=None. So `confirmed_bytes_for` is
    # ALWAYS EMPTY in a dry run, and a touch correctly refuses to re-send bytes, so a dry cell can
    # never issue one. That zero is a dry-run artefact, not an absent mechanism, and reporting it
    # as a result would have been exactly the unexercised-null this protocol exists to catch.
    # The mechanism is therefore proved on a CONSTRUCTED coordinator where a prefix is confirmed.
    import cachekeys as CK
    import cstate as CS2
    from coordinator import Live2Coordinator, Logs
    import tempfile
    import arms as A2

    def harness(touch_on):
        d = Path(tempfile.mkdtemp())
        arm = A2.make_arm("b7-edf-feasibility")
        setattr(arm, "live2_touch_requests", bool(touch_on))
        arm.live2_configure(gpu_kv_tokens=62944, host_tier_gib=27, host_tier_tokens=48000,
                            targets=CS2.TARGETS)
        co = Live2Coordinator(arm, None, [], gpu_kv_tokens=62944, host_tier_gib=27,
                              host_tier_tokens=48000, upload_mode="A", window_s=600.0,
                              drain_s=5.0, seed=4, logs=Logs(d / "r").open(),
                              run_tag=CK.run_tag(4, "touch"), dry_run=True)
        co.st.register(dict(kind="device_register", device_id="robo000", type="robot",
                            uplink_mbps=13.6, rtt_ms=44.0, start_t=0.0), "salt0")
        co.st.session_start(dict(kind="session_start", device_id="robo000", session_id="s0",
                                 t=0.0))
        s = co.st.sessions["s0"]
        s.frames = [f"f{i}" for i in range(8)]
        s.sent_bytes_for = set(s.frames)
        s.confirmed_bytes_for = set(s.frames)        # what a live 200 would have promoted
        s.built_tokens = 11000
        s.belief = {"gpu": 1.0, "host": 0.0, "cold": 0.0}
        return co, s

    co_on, s_on = harness(True)
    rid = co_on._submit_touch(s_on, 10.0, 1.0, {}, co_on.st.traffic_mix())
    body = next((sub.body for _f, sub in co_on.futures if sub.kind == "touch"), None)
    imgs_on = [c for c in (body or {}).get("messages", [{}])[0].get("content", [])
               if c.get("type") != "text"] if body else []
    res["P3_reaches_a_request"] = dict(
        request_id=rid, touch_considered=co_on.counts.get("touch_considered", 0),
        touch_issued=co_on.counts.get("touch_issued", 0),
        touch_issued_gpu=co_on.counts.get("touch_issued_gpu", 0),
        submitted_body_present=body is not None,
        body_max_tokens=(body or {}).get("max_tokens"),
        body_images=len(imgs_on),
        body_any_inline_bytes=any("data:" in json.dumps(c) for c in imgs_on),
        why_not_dry=("confirmed_bytes_for is always empty in a dry cell "
                     "(_DryFuture http_status=None), so a dry cell cannot issue a touch"))
    p3 = (rid is not None and co_on.counts.get("touch_issued", 0) == 1 and body is not None
          and (body or {}).get("max_tokens") == 1
          and not res["P3_reaches_a_request"]["body_any_inline_bytes"])

    co_off, s_off = harness(False)
    co_off._enact(type("A", (), {"streams": [], "sessions": [
        type("SA", (), {"session_id": "s0", "action": "KEEP_GPU_WARM",
                        "target_tokens": None, "slice_tokens": None})()],
        "recall": [], "notes": {}})(), 10.0, 1.0)
    # and the M6 guard as a NEGATIVE CONTROL: same harness, straddling belief, must refuse
    co_mix, s_mix = harness(True)
    s_mix.belief = {"gpu": 0.6, "host": 0.4, "cold": 0.0}
    rid_mix = co_mix._submit_touch(s_mix, 10.0, 1.0, {}, co_mix.st.traffic_mix())
    res["P4_step2b"] = dict(
        switch_off_touch_issued=co_off.counts.get("touch_issued", 0),
        switch_off_keep_gpu_warm_seen=co_off.counts.get("session_KEEP_GPU_WARM", 0),
        guard_refused_request_id=rid_mix,
        guard_refused_count=co_mix.counts.get("touch_refused_guard", 0),
        decisions_moved=(co_on.counts.get("touch_issued", 0)
                         != co_off.counts.get("touch_issued", 0)))
    p4 = (co_off.counts.get("touch_issued", 0) == 0
          and co_off.counts.get("session_KEEP_GPU_WARM", 0) >= 1
          and rid_mix is None and co_mix.counts.get("touch_refused_guard", 0) == 1)

    # P5 a touch carries NO bytes and asks for one token: re-sending bytes would make it a
    # rebuild, not a touch.
    import bodies as B
    tb = B.build_body(kind="touch", device_id="d0", session_id="s0", run_tag="rt", salt="s",
                      header="H", frames=[dict(frame_ref="f0", path=None),
                                          dict(frame_ref="f1", path=None)],
                      max_tokens=TP.TOUCH_MAX_TOKENS, est_tokens=11000)
    parts = tb["messages"][0]["content"]
    imgs = [c for c in parts if c.get("type") != "text"]
    res["P5_body"] = dict(max_tokens=tb.get("max_tokens"), n_images=len(imgs),
                          any_inline_bytes=any("data:" in json.dumps(c) for c in imgs),
                          n_new_frames=tb["_live2"]["n_new_frames"])
    p5 = (tb.get("max_tokens") == 1 and not res["P5_body"]["any_inline_bytes"]
          and tb["_live2"]["n_new_frames"] == 0)

    # P6 HONEST STATUS IN v5-FULL: declared, wired, and currently UNEXERCISED there.
    import arms_v5full as V5F
    a = V5F.V5FullArm(dry=True)
    res["P6_v5full_status"] = dict(
        declares_switch=TP.arm_enables(a),
        emits_keep_gpu_warm_today=False,
        status="UNEXERCISED in v5-full until plan_state is wired (component 6); the mechanism is "
               "proved live through lmcache, which does emit KEEP_GPU_WARM",
        evidence="arms_v5rules.py:18 states the v5-rules base has no KEEP_GPU_WARM")
    p6 = TP.arm_enables(a) is True

    checks = dict(P1_price_by_state=p1, P2_m6_guard=p2, P3_reaches_a_request=p3,
                  P4_step2b=p4, P5_body=p5, P6_declared=p6)
    res["checks"] = checks
    res["ALL_PASS"] = all(checks.values())
    res["_elapsed_s"] = round(time.time() - t0, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, default=str))
    for k, v in checks.items():
        print(f"  {k:24s} {'PASS' if v else 'FAIL'}")
    print(f"\nALL_PASS: {res['ALL_PASS']}")
    print(f"price 11k by state: {prices}")
    print(f"touch issued: switch on {res['P3_reaches_a_request']['touch_issued']}, "
          f"switch off {res['P4_step2b']['switch_off_touch_issued']}, "
          f"M6 guard refusals {res['P4_step2b']['guard_refused_count']}")
    print(f"wrote {OUT}")
    return 0 if res["ALL_PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
