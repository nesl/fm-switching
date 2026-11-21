"""Proofs for full v5 component 1 (per-type host-offload controls). Dry, no GPU.

Deliberately NOT proved here: that the engine honours the field. That is offload_verify.py on the
H100. These proofs establish only that the policy DECIDES per type and that the decision reaches
the wire body with its declared type and value, and that no other arm's body moves.
"""
import json, sys, time
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

import bodies as B           # noqa: E402
import offload_policy as OP  # noqa: E402

OUT = R / "results/orchestration/live2/frozen_test/offload_proofs.json"


def _body(dev_type, kind="monitor", enabled=True, n_frames=1, fmt="oneframe"):
    frames = [{"frame_ref": f"f{i}", "path": None} for i in range(n_frames)]
    return B.build_body(kind=kind, device_id="d0", session_id=("s0" if kind != "monitor" else None),
                        run_tag="rt", salt="salt0", header="H", frames=frames,
                        question=("q?" if kind == "recall" else None),
                        est_tokens=100, dashcam_format=fmt,
                        kv_transfer_params=OP.params_for(dev_type, enabled))


def main():
    res, t0 = {}, time.time()

    # P1 the rule itself: the declared per-type decision, read back from the module
    res["P1_rule"] = {t: OP.params_for(t, True) for t in ("dashcam", "robot", "assistive", "unknown")}
    p1 = (res["P1_rule"]["assistive"] == {"max_offload_tokens": 0, "max_load_tokens": 0}
          and res["P1_rule"]["dashcam"] == {"max_offload_tokens": 0}
          and res["P1_rule"]["robot"] is None and res["P1_rule"]["unknown"] is None)

    # P2 STEP 2b: the switch must reach the wire body, and differ per type
    on = {t: _body(t, "monitor" if t == "dashcam" else "recall", True) for t in ("dashcam", "robot", "assistive")}
    off = {t: _body(t, "monitor" if t == "dashcam" else "recall", False) for t in ("dashcam", "robot", "assistive")}
    res["P2_step2b"] = {t: dict(on=on[t].get("kv_transfer_params"),
                                off=off[t].get("kv_transfer_params"),
                                digest_on=B.body_digest(on[t]), digest_off=B.body_digest(off[t]),
                                body_moved=B.body_digest(on[t]) != B.body_digest(off[t]))
                        for t in on}
    # the two deviating types must MOVE the body; robot must not, because its rule is the default
    p2 = (res["P2_step2b"]["dashcam"]["body_moved"] and res["P2_step2b"]["assistive"]["body_moved"]
          and not res["P2_step2b"]["robot"]["body_moved"])

    # P3 declared type and value: int 0, never bool. A bool is a different type at the engine.
    vals = []
    for t in ("dashcam", "assistive"):
        for k, v in (on[t].get("kv_transfer_params") or {}).items():
            vals.append(dict(type=t, key=k, value=v, py_type=type(v).__name__,
                             is_int_not_bool=(isinstance(v, int) and not isinstance(v, bool))))
    res["P3_declared_type"] = vals
    p3 = bool(vals) and all(v["is_int_not_bool"] and v["value"] == 0 for v in vals)

    # P4 the field SURVIVES to the wire: strip_internal must not drop it (it is a real vLLM field)
    w = B.strip_internal(on["dashcam"], strip_hints=True)
    res["P4_survives_strip"] = dict(on_wire=("kv_transfer_params" in w),
                                    value=w.get("kv_transfer_params"),
                                    internal_gone=("_live2" not in w and not any(
                                        k.startswith("fm_") for k in w)))
    p4 = res["P4_survives_strip"]["on_wire"] and res["P4_survives_strip"]["internal_gone"]

    # P5 NEGATIVE CONTROL: with the switch off, every body is byte-identical to the committed one
    #    (committed = built with no kv_transfer_params argument at all)
    base = {t: _body(t, "monitor" if t == "dashcam" else "recall", False) for t in ("dashcam", "robot", "assistive")}
    plain = {}
    for t in ("dashcam", "robot", "assistive"):
        frames = [{"frame_ref": "f0", "path": None}]
        kind = "monitor" if t == "dashcam" else "recall"
        plain[t] = B.build_body(kind=kind, device_id="d0", session_id=(None if kind == "monitor" else "s0"),
                                run_tag="rt", salt="salt0", header="H", frames=frames,
                                question=("q?" if kind == "recall" else None), est_tokens=100)
    res["P5_negative_control"] = {t: dict(switch_off=B.body_digest(base[t]),
                                          committed=B.body_digest(plain[t]),
                                          identical=B.body_digest(base[t]) == B.body_digest(plain[t]))
                                  for t in plain}
    p5 = all(v["identical"] for v in res["P5_negative_control"].values())

    # P6 PORT RULE / characteristic decision: the arm that declares the capability must be the only
    #    one that does, and it must actually emit on a type that deviates
    import arms_v5full as V5F
    import arms as A
    import hybrid  # noqa: F401  registers the hybrid configs
    others = {}
    for n in ("edf", "llf", "b7-edf-feasibility", "always-cloud-fcfs", "mooncake",
              "attentionstore-prefetch", "warm-all-lru", "v5-rules", "v5-rules-2"):
        try:
            others[n] = OP.arm_enables(A.make_arm(n))
        except Exception as e:
            others[n] = f"ERR {type(e).__name__}"
    res["P6_port_rule"] = dict(v5full_declares=OP.arm_enables(V5F.V5FullArm(dry=True)),
                               other_arms_declare=others,
                               emissions={t: OP.params_for(t, True) is not None
                                          for t in OP.KNOWN_TYPES})
    p6 = (res["P6_port_rule"]["v5full_declares"] is True
          and all(v is False for v in others.values() if isinstance(v, bool))
          and sum(res["P6_port_rule"]["emissions"].values()) == 2)

    checks = dict(P1_rule=p1, P2_step2b=p2, P3_declared_type=p3, P4_survives_strip=p4,
                  P5_negative_control=p5, P6_port_rule=p6)
    res["checks"] = checks
    res["ALL_PASS"] = all(checks.values())
    res["_elapsed_s"] = round(time.time() - t0, 2)
    res["_not_established_here"] = ("whether the ENGINE honours kv_transfer_params. These proofs "
                                    "show the policy decides per type and the value reaches the "
                                    "wire with its declared type. offload_verify.py on the H100 "
                                    "answers the engine question; until it runs, component 1 may "
                                    "not be described as working.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))
    for k, v in checks.items():
        print(f"  {k:22s} {'PASS' if v else 'FAIL'}")
    print(f"\nALL_PASS: {res['ALL_PASS']}")
    print(f"rule: dashcam {res['P1_rule']['dashcam']}  robot {res['P1_rule']['robot']}  "
          f"assistive {res['P1_rule']['assistive']}")
    print(f"wrote {OUT}")
    return 0 if res["ALL_PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
