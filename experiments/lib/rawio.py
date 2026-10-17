"""Raw per-event result files (token stamps, per-step times, metric timelines).

Repo convention (2026-10-16): per-event raw files are committed ONLY as gzip (`<name>.jsonl.gz`); token-stamp
records are additionally delta-encoded (`t0_ms` + integer `dt_ms` list), which is lossless at the 1 ms precision they
are recorded with. Harnesses may append to the plain `<name>.jsonl` during a run; `compact()` converts it after the
run (verifying the round trip before deleting the plain file). Readers use `read_jsonl()`, which reads the plain
and/or gzipped file and decodes stamps transparently.

  python experiments/lib/rawio.py <file.jsonl> [...]     # compact in place -> file.jsonl.gz
"""
import gzip
import json
import sys
from pathlib import Path


def _encode(rec):
    if "stamps" not in rec:
        return rec
    rec = dict(rec)
    ms = [round(x * 1000) for x in rec.pop("stamps")]
    rec["t0_ms"] = ms[0] if ms else None
    rec["dt_ms"] = [b - a for a, b in zip(ms, ms[1:])]
    return rec


def _decode(rec):
    if "dt_ms" not in rec:
        return rec
    rec = dict(rec)
    out, c = [], rec.pop("t0_ms")
    dts = rec.pop("dt_ms")
    if c is not None:
        out.append(c / 1000)
        for d in dts:
            c += d
            out.append(c / 1000)
    rec["stamps"] = out
    return rec


def read_jsonl(path):
    """Yield records from `path` (plain .jsonl) and/or `path`.gz, decoding delta-encoded stamps."""
    path = Path(str(path).removesuffix(".gz"))
    gz = Path(str(path) + ".gz")
    if gz.exists():
        with gzip.open(gz, "rt") as f:
            for line in f:
                if line.strip():
                    yield _decode(json.loads(line))
    if path.exists():
        for line in open(path):
            if line.strip():
                yield _decode(json.loads(line))


def compact(path):
    """Append plain `path` into `path`.gz (stamps delta-encoded), verify losslessly, then delete the plain file."""
    path = Path(path)
    gz = Path(str(path) + ".gz")
    old = []
    if gz.exists():   # read ONLY the gz here (read_jsonl() would also pick up the plain file being compacted)
        with gzip.open(gz, "rt") as f:
            old = [_decode(json.loads(l)) for l in f if l.strip()]
    new = [json.loads(l) for l in open(path) if l.strip()]
    tmp = Path(str(gz) + ".tmp")
    with gzip.open(tmp, "wt", compresslevel=9) as f:
        for r in old + new:
            f.write(json.dumps(_encode(r), separators=(",", ":")) + "\n")
    with gzip.open(tmp, "rt") as f:
        back = [_decode(json.loads(l)) for l in f if l.strip()]
    for a, b in zip(back, old + new):
        if "stamps" in b:
            assert [round(x * 1000) for x in a["stamps"]] == [round(x * 1000) for x in b["stamps"]], "stamp mismatch"
            assert all(abs(x - y) < 1e-9 for x, y in zip(a["stamps"], b["stamps"])), "stamp precision loss"
        else:
            assert a == b, "record mismatch"
    assert len(back) == len(old) + len(new)
    tmp.replace(gz)
    path.unlink()
    print(f"compacted {path} -> {gz} ({len(new)} new + {len(old)} existing records, {gz.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        compact(p)
