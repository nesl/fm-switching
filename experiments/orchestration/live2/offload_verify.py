"""Live verification of vLLM 0.31.0 per-request host-offload controls (full v5 component 1).

Answers three questions the policy's per-type state rule depends on, each with its own control:

  Q1 does SKIP RETENTION take effect     kv_transfer_params {"max_offload_tokens": 0}
  Q2 does HOST RELOAD take effect        no kv_transfer_params at all  (this is also the POSITIVE CONTROL)
  Q3 does FORBID RELOAD take effect      {"max_load_tokens": 0} and {"kv_load_tiers": []}

Why /metrics and not cached_tokens: the per-request GPU-vs-host split is not in the API, because
cached_tokens = GPU-local + host-loaded (study_rh5_host_offload.py:12). The discriminator below is
RH5's own pre-registered one, reused verbatim so these numbers cross-check against its committed
rows: GPU-WARM is prefix_cache_hits >= need with external <= 64; HOST-WARM is external >= need with
kv_offload_load_bytes > 0 and local <= 64; COLD is cached_tokens <= 64.

Every probe forces GPU eviction between the store and the read, because a GPU prefix hit would mask
a host load and make a "yes" meaningless. Q3 carries the control that matters most: after the
forbid-reload read it reads the SAME prefix again with no controls, which must come back HOST-WARM.
Without that step a COLD result cannot tell "forbid-reload worked" from "it was never on host".

Text prefixes, not frames: the controls act on KV blocks, so the cheapest prefix that fills the pool
is the right one. Each probe gets its own cache_salt, so no probe can be served from another's KV.

Read-only on the H100 beyond starting and stopping its own server: it builds nothing, writes only
its own result file, and starts the round-1 server through study_live2_pilot.start_server(27).
"""
import argparse, asyncio, json, os, random, re, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "experiments/orchestration"))
sys.path.insert(0, str(REPO / "experiments/cost"))

HARD_CAP_S = 15 * 60
METRIC_PAT = re.compile(r"^(vllm:(?:[a-z_]*prefix_cache[a-z_]*|kv_offload[a-z_]*|num_preemptions[a-z_]*|"
                        r"[a-z_]*external[a-z_]*))(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$")
FILL_FACTOR = 1.5
PREFIX_WORDS = 6000          # ~8k tokens, comfortably above the 64-token noise floor
FILLER_WORDS = 6000
WORDS = ("corridor shelf pallet ladder conveyor crate bracket spindle gasket flange rotor caliper "
         "hopper gantry trolley bearing coupling manifold nozzle bulkhead").split()


def text(seed, n):
    r = random.Random(seed)
    return " ".join(r.choice(WORDS) for _ in range(n))


def scrape(txt):
    row = {}
    for line in txt.splitlines():
        m = METRIC_PAT.match(line)
        if m:
            row[m.group(1)] = row.get(m.group(1), 0.0) + float(m.group(2))
    return row


def delta(a, b):
    return {k: round(b.get(k, 0.0) - a.get(k, 0.0), 3)
            for k in set(a) | set(b) if abs(b.get(k, 0.0) - a.get(k, 0.0)) > 1e-9}


def g(d, *names):
    return sum(v for k, v in d.items() if any(k.split(":", 1)[-1].startswith(n) for n in names))


# NOTE ON kv_offload_load_bytes, from the 2026-11-21 run: the delta came back FRACTIONAL
# (3913421399.102), so it is a histogram sum and not a byte counter. The classification below only
# ever asks whether it is > 0, which a histogram sum still answers, and the external-hit count
# carries the verdict either way. It is recorded so nobody later cites this number AS BYTES.


def classify(d, cached_tokens, prompt_tokens):
    """RH5's pre-registered discriminator, unchanged."""
    local, ext = g(d, "prefix_cache_hits"), g(d, "external_prefix_cache_hits")
    load = g(d, "kv_offload_load_bytes")
    need = 0.9 * (prompt_tokens - 300)
    if local >= need and ext <= 64:
        state = "GPU-WARM"
    elif ext >= need and load > 0 and local <= 64:
        state = "HOST-WARM"
    elif (cached_tokens or 0) <= 64:
        state = "COLD"
    else:
        state = "MIXED-OR-UNCLEAR"
    return state, dict(local_hits=local, external_hits=ext, load_bytes=load, need=round(need, 1))


class Cell:
    def __init__(self, base, model):
        import httpx
        self.base, self.model = base, model
        self.c = httpx.AsyncClient(timeout=600.0)

    async def metrics(self):
        return scrape((await self.c.get(f"{self.base}/metrics")).text)

    async def post(self, prompt, salt, kvtp=None, label=""):
        body = dict(model=self.model, temperature=0.0, max_tokens=1, cache_salt=salt,
                    messages=[{"role": "user", "content": prompt}])
        if kvtp is not None:
            body["kv_transfer_params"] = kvtp
        m0 = await self.metrics()
        t0 = time.time()
        r = await self.c.post(f"{self.base}/v1/chat/completions", json=body)
        el = time.time() - t0
        ok = r.status_code == 200
        js = r.json() if ok else None
        usage = (js or {}).get("usage") or {}
        m1 = await self.metrics()
        d = delta(m0, m1)
        pt = usage.get("prompt_tokens") or 0
        ct = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
        state, ev = classify(d, ct, pt)
        return dict(label=label, http=r.status_code, ok=ok,
                    error=(None if ok else r.text[:400]),
                    kv_transfer_params=kvtp, latency_s=round(el, 3),
                    prompt_tokens=pt, cached_tokens=ct, state=state, evidence=ev, metric_delta=d)

    async def evict(self, kv, tag):
        """Push other prefixes through the cache until >= FILL_FACTOR x the GPU pool."""
        filled, i = 0, 0
        while filled < FILL_FACTOR * kv:
            i += 1
            r = await self.post(text(f"fill|{tag}|{i}", FILLER_WORDS), f"fill|{tag}|{i}", label=f"filler{i}")
            if not r["ok"]:
                return dict(filled_tokens=filled, requests=i, failed=r)
            filled += r["prompt_tokens"]
        return dict(filled_tokens=filled, requests=i, failed=None)


async def run(base, model, kv, out):
    cell = Cell(base, model)
    res = {"_meta": dict(base=base, model=model, gpu_kv_tokens=kv, fill_factor=FILL_FACTOR,
                         started=time.strftime("%Y-%m-%dT%H:%M:%S"))}
    probes = []

    async def probe(name, store_kvtp, read_kvtp, question):
        salt = f"offverify|{name}"
        p = text(salt, PREFIX_WORDS)
        store = await cell.post(p, salt, kvtp=store_kvtp, label="store")
        ev = await cell.evict(kv, name)
        read = await cell.post(p, salt, kvtp=read_kvtp, label="read")
        row = dict(probe=name, question=question, store=store, eviction=ev, read=read)
        probes.append(row)
        print(f"  {name}: store {store['state']} ({store['prompt_tokens']} tok) -> evict "
              f"{ev['filled_tokens']} tok -> read {read['state']} "
              f"local {read['evidence']['local_hits']:.0f} ext {read['evidence']['external_hits']:.0f} "
              f"load {read['evidence']['load_bytes']:.0f} http {read['http']}", flush=True)
        return row

    # Q2 FIRST, because it is the positive control: if a plain re-read is not served from host,
    # no "no" from Q1 or Q3 can be interpreted at all.
    pc = await probe("Q2_positive_control_plain_reload", None, None,
                     "does host reload take effect with no kv_transfer_params")
    pc_ok = pc["read"]["state"] == "HOST-WARM"

    await probe("Q1_skip_retention", {"max_offload_tokens": 0}, None,
                "does max_offload_tokens=0 stop the prefix being retained on host")
    await probe("Q3a_forbid_reload_max_load_tokens", None, {"max_load_tokens": 0},
                "does max_load_tokens=0 stop a host-resident prefix being reloaded")
    # The control for Q3, with the fix the first run proved necessary. On 2026-11-21 this control
    # came back GPU-WARM, because the FORBIDDEN read had itself recomputed the prefix cold and left
    # it GPU-resident, and nothing evicted it in between, so the control hit that recompute and
    # never consulted the host. It could then not distinguish "forbid-reload worked" from "never on
    # host", which is why the verdict was INCONCLUSIVE. Evicting first forces the control to answer
    # the question it exists to answer.
    salt3 = "offverify|Q3a_forbid_reload_max_load_tokens"
    ev3 = await cell.evict(kv, "Q3a_control")
    ctl = await cell.post(text(salt3, PREFIX_WORDS), salt3, kvtp=None, label="Q3a_control_replain")
    ctl["eviction_before_control"] = ev3
    probes.append(dict(probe="Q3a_control_was_it_on_host", question=
                       "after the forbidden read, is the same prefix still reachable on host",
                       read=ctl))
    print(f"  Q3a_control: {ctl['state']} ext {ctl['evidence']['external_hits']:.0f} "
          f"load {ctl['evidence']['load_bytes']:.0f}", flush=True)
    await probe("Q3b_forbid_reload_empty_tiers", None, {"kv_load_tiers": []},
                "does kv_load_tiers=[] stop a host-resident prefix being reloaded")

    res["probes"] = probes
    res["verdicts"] = verdicts(probes, pc_ok)
    res["_meta"]["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=2))
    await cell.c.aclose()
    return res


def verdicts(probes, pc_ok):
    by = {p["probe"]: p for p in probes}

    def read_state(n):
        return (by.get(n, {}).get("read") or {}).get("state")

    def http(n):
        return (by.get(n, {}).get("read") or {}).get("http")
    v = {}
    v["positive_control"] = ("PASS: a plain re-read after eviction was served from host"
                             if pc_ok else
                             f"FAIL: plain re-read came back {read_state('Q2_positive_control_plain_reload')}, "
                             "so no negative result below is interpretable")
    v["Q2_host_reload"] = "YES" if pc_ok else "NO-OR-UNINTERPRETABLE"
    if not pc_ok:
        v["Q1_skip_retention"] = v["Q3_forbid_reload"] = "UNINTERPRETABLE: positive control failed"
        return v
    s1 = read_state("Q1_skip_retention")
    v["Q1_skip_retention"] = ("YES: nothing was retained on host" if s1 == "COLD" else
                              f"NO: read came back {s1}, so the prefix was retained despite "
                              f"max_offload_tokens=0 (http {http('Q1_skip_retention')})")
    ctl = read_state("Q3a_control_was_it_on_host")
    for key, name in (("Q3a_max_load_tokens", "Q3a_forbid_reload_max_load_tokens"),
                      ("Q3b_kv_load_tiers", "Q3b_forbid_reload_empty_tiers")):
        s = read_state(name)
        if s == "COLD" and ctl == "HOST-WARM":
            v[key] = "YES: recomputed although the control proved it was still on host"
        elif s == "COLD":
            v[key] = (f"INCONCLUSIVE: read was COLD but the control came back {ctl}, so it may never "
                      "have been on host (absence, not a working control)")
        else:
            v[key] = f"NO: read came back {s} despite the control (http {http(name)})"
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/orchestration/live2/offload_verify/offload_verify_h100.json")
    ap.add_argument("--base", default="http://127.0.0.1:8031")
    ap.add_argument("--model", default="32BI")
    ap.add_argument("--host-gib", type=float, default=27)
    ap.add_argument("--no-server", action="store_true", help="attach to a server already up (local debug only)")
    a = ap.parse_args()
    t0 = time.time()
    srv = meta = None
    if not a.no_server:
        import study_live2_pilot as P
        srv, meta, _M = P.start_server(a.host_gib)
        print(f"server up in {meta.get('startup_s')}s, host tier {a.host_gib} GiB", flush=True)
    kv = 62944
    try:
        res = asyncio.run(asyncio.wait_for(run(a.base, a.model, kv, a.out), timeout=HARD_CAP_S - 60))
    finally:
        if srv is not None:
            srv.stop()
            print("server stopped", flush=True)
    if meta:
        res["_meta"]["server"] = meta
        Path(a.out).write_text(json.dumps(res, indent=2))
    print("\n================ VERDICTS ================")
    for k, val in res["verdicts"].items():
        print(f"{k:22s} {val}")
    print(f"\nelapsed {time.time() - t0:.0f}s   wrote {a.out}")


if __name__ == "__main__":
    main()
