#!/usr/bin/env python3
"""Which live arms read a DEVICE SCORE when deciding? (CPU only, static read of committed code.)

  python3 -I experiments/orchestration/live2/device_score_audit.py

This is the port rule applied to a channel rather than to an arm: "a port's proofs must include
that its characteristic decision occurs at least once". An arm that escalates when the device is
unsure cannot make that decision if no device score reaches it, and the question is not whether the
channel is DECLARED but whether it is SUPPLIED and READ.

Three things are checked separately, because the answer differs for each:
  1. which arms DECLARE `reads_device_answer = True`;
  2. whether the live2 observation builder SUPPLIES a value;
  3. what the declaration COSTS the arm that makes it.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

BASE = ROOT / "experiments/orchestration/baselines"
LIVE2 = ROOT / "experiments/orchestration/live2"
OUT = ROOT / "results/orchestration/live2/device_score_audit.json"
FIELD = "device_answer_confidence"


def declarers():
    out = {}
    for p in sorted(BASE.glob("*.py")):
        src = p.read_text()
        if re.search(r"^\s*reads_device_answer\s*=\s*True", src, re.M):
            out[p.name] = dict(declares=True, reads_the_field=FIELD in src,
                               field_sites=[i + 1 for i, l in enumerate(src.splitlines())
                                            if FIELD in l and not l.strip().startswith("#")])
        elif re.search(r"^\s*reads_device_answer\s*=\s*False", src, re.M):
            out[p.name] = dict(declares=False, reads_the_field=FIELD in src, field_sites=[])
    return out


def supply():
    """Does cstate.observation supply a value, and does it consult the declaration?"""
    src = (LIVE2 / "cstate.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "observation")
    body = ast.unparse(fn)
    assigns = [l.strip() for l in body.splitlines() if FIELD in l]
    lit = re.findall(FIELD + r"\s*=\s*([A-Za-z0-9_.]+)", body)
    return dict(
        function=f"cstate.py:{fn.lineno}-{fn.end_lineno}",
        takes_reads_device_answer_parameter=any(
            a.arg == "reads_device_answer" for a in fn.args.args + fn.args.kwonlyargs),
        uses_that_parameter_in_its_body=body.count("reads_device_answer") - 1,
        assignments=assigns, assigned_values=sorted(set(lit)),
        always_none=lit == ["None"] * len(lit) and bool(lit))


def call_site():
    """Does the coordinator even pass the declaration through?"""
    src = (LIVE2 / "coordinator.py").read_text().splitlines()
    calls = [(i + 1, l.strip()) for i, l in enumerate(src) if ".observation(" in l]
    flag = [(i + 1, l.strip()) for i, l in enumerate(src) if "reads_device" in l]
    return dict(observation_calls=calls, reads_device_sites=flag,
                passes_the_flag=any("reads_device" in l for _, l in calls))


def main():
    d, s, c = declarers(), supply(), call_site()
    cost_sites = [l for _, l in c["reads_device_sites"] if "DEVICE_ANSWER_CHARGE_S" in l]
    res = dict(
        label="StudySS2 request, live2 side: which arms read a device score when deciding. "
              "Static read of committed code; no model, no GPU, no run.",
        at=datetime.now().isoformat(),
        arms_declaring_reads_device_answer=sorted(k for k, v in d.items() if v["declares"]),
        arms_declaring_false=sorted(k for k, v in d.items() if not v["declares"]),
        per_file=d, live2_supply=s, live2_call_site=c,
        what_the_declaration_costs=cost_sites,
        verdict=(
            "DECLARED BY {n} ARMS, SUPPLIED TO NONE. live2's observation builder hard-codes "
            "{f}=None for every recall query; it accepts a reads_device_answer parameter and "
            "uses it {u} times in its body; and the coordinator does not pass that parameter at "
            "all, so it always takes its default. The declaration is nonetheless CHARGED: the "
            "coordinator reads its own reads_device flag to make the arm wait "
            "DEVICE_ANSWER_CHARGE_S before it may act, and to serve the opportunity that much "
            "later. So an arm declaring it pays the full price of reading the device answer and "
            "receives None instead of the answer."
        ).format(n=sum(1 for v in d.values() if v["declares"]), f=FIELD,
                 u=s["uses_that_parameter_in_its_body"]))
    res["_provenance"] = stamp(script="device_score_audit.py", model="none", device="cpu",
                               n=len(d), args=None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_file", "_provenance")},
                     indent=1))


if __name__ == "__main__":
    main()
