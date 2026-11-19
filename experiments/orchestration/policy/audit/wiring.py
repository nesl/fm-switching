#!/usr/bin/env python3
"""StudyCOVEX-harden 1c: the WIRING AND SCALE audit.

Three static checks plus one measured one:
  * fields WRITTEN but never READ;
  * fields READ but never WRITTEN, including those written only inside a function with no
    production caller, which a plain read and write count cannot see;
  * DEAD SWITCHES, flags whose on and off states give byte-identical decisions;
  * every DeltaJ term on a COMMON SCALE, so a term structurally dwarfed by another is visible.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from _harness import LIVE2, POLICY_DIR, ROOT

STATE = POLICY_DIR / "state.py"


def _prod_files() -> List[Path]:
    out = []
    for base in (POLICY_DIR, LIVE2):
        for p in base.rglob("*.py"):
            s = str(p)
            if "test" in s or "__pycache__" in s or "/audit/" in s:
                continue
            out.append(p)
    return out


def field_usage() -> Dict[str, Any]:
    src = STATE.read_text().split("\n")
    fields: Dict[str, List] = {}
    cur = None
    for i, l in enumerate(src, 1):
        m = re.match(r"^class (\w+)", l.strip())
        if m:
            cur = m.group(1)
        m2 = re.match(r"^\s{4}(\w+)\s*:\s*[^=]+(=.*)?$", l)
        if cur and m2 and not m2.group(1).startswith("_"):
            fields.setdefault(cur, []).append((m2.group(1), i, l.strip()))
    text = "\n".join(p.read_text() for p in _prod_files())
    rows = []
    for cls, fs in sorted(fields.items()):
        for f, ln, decl in fs:
            reads = len(re.findall(r"\.%s\b(?!\s*=)" % re.escape(f), text))
            writes = len(re.findall(r"\.%s\s*=(?!=)" % re.escape(f), text))
            writes += len(re.findall(r"\.%s\[[^\]]*\]\s*=(?!=)" % re.escape(f), text))
            ctor = max(len(re.findall(r"(?<![\w.])%s\s*=(?!=)" % re.escape(f), text)) - writes, 0)
            mut = len(re.findall(
                r"\.%s\.(append|extend|update|pop|clear|setdefault|add)\(" % re.escape(f), text))
            rows.append(dict(cls=cls, field=f, line=ln, decl=decl, reads=reads, writes=writes,
                             ctor_kwargs=ctor, mutations=mut))
    read_never_written = [r for r in rows
                          if r["reads"] > 0 and r["writes"] == 0 and r["ctor_kwargs"] == 0
                          and r["mutations"] == 0]
    written_never_read = [r for r in rows
                          if r["reads"] == 0 and (r["writes"] > 0 or r["ctor_kwargs"] > 0
                                                  or r["mutations"] > 0)]
    return dict(rows=rows, read_never_written=read_never_written,
                written_never_read=written_never_read,
                note="a field written ONLY inside a function with no production caller shows "
                     "writes > 0 here and is still dead; those are listed separately by "
                     "`dead_writers`.")


def dead_writers() -> List[Dict[str, Any]]:
    """Functions that write state and have no production caller, so their writes never happen.

    Checked by name across production files, excluding the definition itself and tests.
    """
    text_by_file = {p: p.read_text() for p in _prod_files()}
    out = []
    for fn, writes in (("bump_z", "Device.z"), ("update_deficit", "Device.z via bump_z")):
        callers = []
        for p, t in text_by_file.items():
            # A METHOD call (`dev.bump_z(...)`) must match too. An earlier version of this check
            # used a negative lookbehind on "." and so reported `bump_z` dead while the v1.1
            # deficit update was calling it; that was a false negative of this tool, recorded as
            # erratum E1 in the report.
            for m in re.finditer(r"(?<![\w])%s\s*\(" % re.escape(fn), t):
                line = t[:m.start()].count("\n") + 1
                ctx = t.split("\n")[line - 1]
                if ctx.strip().startswith("def "):
                    continue
                callers.append("%s:%d" % (p.relative_to(ROOT), line))
        out.append(dict(writer=fn, writes=writes, production_callers=sorted(callers),
                        dead=not callers))
    return out


def scale_table(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Every DeltaJ term on one scale, per candidate kind, so dwarfing is visible."""
    import collections
    by_kind = collections.defaultdict(list)
    for r in records:
        by_kind[r["kind"]].append(r)

    def q(xs, f):
        xs = sorted(xs)
        return round(xs[min(int(f * len(xs)), len(xs) - 1)], 6)

    out = {}
    for kind, rs in sorted(by_kind.items()):
        terms = {}
        for c in ("sh_own_delta", "sh_harm_delta", "rc_util_delta", "z", "cont_delta",
                  "sv_delta", "backlog_delta"):
            v = [r[c] for r in rs if r.get(c) is not None]
            if not v:
                continue
            mag = [abs(x) for x in v]
            terms[c] = dict(n=len(v), p50_abs=q(mag, 0.5), p90_abs=q(mag, 0.9),
                            max_abs=round(max(mag), 6), min=round(min(v), 6),
                            max=round(max(v), 6))
        out[kind] = dict(n=len(rs), terms=terms)
    return out
