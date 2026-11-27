"""E-engine-hosttier: standalone probe of the vLLM 0.31.0 KV-offload host tier (capacity, eviction order,
refresh-on-hit, store scope). One engine, no coordinator, no fleet. Runs ON THE H100 HOST (GPU 3, driver-idle
block; see research/HOST_H100.md and the runbook). --dry-run uses an in-process FAKE ENGINE that implements the
SOURCE-DERIVED rule (and three rivals) so the logic and the analysis can be tested on CPU.

Parts: A (start-up: connector, num_chunks from the /dev/shm mmap size, GPU blocks), P1 (capacity and order),
P2 (refresh-on-hit at robo003 scale), P3 (store scope), P4 (optional, 7 concurrent chains, --p4).
Prompts are token-id lists sent to /v1/completions, 16n+1 tokens (hit cap n blocks), unique leading random ids
per chain (no cross-chain prefix), one request in flight (except P4), store drain awaited around every request.
Deviation from the design text, flagged: read-back requests in P2 and P4 carry max_offload_tokens 0 so a read
cannot evict what the next read measures (P1 reads keep stores ON as designed: the chain-3 re-store bytes
separate head-first from whole-chain eviction). --reads-store restores the design-literal P2 reads.
"""
import argparse
import glob
import gzip
import json
import math
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "experiments" / "lib"))

BLOCK = 16
CHUNK_B = 4_194_304
FLUSH_TOKENS = 31_361
P1_N = 256
P2_N = 1164
SERVED = "32BI"
MODEL_SLUG = "qwen3vl32b"
HEADER_REF = {
    "h135": "results/orchestration/live2/frozen_test/runs/covex-v6-fair-final-la-er_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30/header.json",
    "h27": "results/orchestration/live2/frozen_test/runs/covex-v6-fair-final-la-er_n16_s4_1200s_h27_3t_L3_epg_rq30/header.json",
}
GPU_BLOCKS_EXPECT = {"h135": 1968}
CHUNKS_EXPECT = {"h135": 3456, "h27": 6912}

COMMITTED_ARGV = {
 'h135': [
  "/home/pragya/.venvs/fm-switching-vllm/bin/vllm",
  "serve",
  "/home/pragya/.cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/0cfaf48183f594c314753d30a4c4974bc75f3ccb",
  "--served-model-name",
  "32BI",
  "--port",
  "8031",
  "--max-model-len",
  "32768",
  "--gpu-memory-utilization",
  "0.9",
  "--tensor-parallel-size",
  "1",
  "--no-enable-prefix-caching",
  "--limit-mm-per-prompt",
  "{\"image\": 16}",
  "--dtype",
  "bfloat16",
  "--seed",
  "0",
  "--limit-mm-per-prompt",
  "{\"image\": 640, \"video\": 1}",
  "--mm-processor-kwargs",
  "{\"size\": {\"shortest_edge\": 4096, \"longest_edge\": 16777216}, \"fps\": 1.0, \"do_sample_frames\": false}",
  "--trust-request-mm-kwargs",
  "--host",
  "127.0.0.1",
  "--enable-prefix-caching",
  "--enable-prompt-tokens-details",
  "--mm-processor-cache-gb",
  "128",
  "--kv-offloading-backend",
  "native",
  "--kv-offloading-size",
  "13.5",
  "--enable-log-requests",
  "--enable-logging-iteration-details",
  "--num-gpu-blocks-override",
  "1968",
  "--max-model-len",
  "31472"
 ],
 'h27': [
  "/home/pragya/.venvs/fm-switching-vllm/bin/vllm",
  "serve",
  "/home/pragya/.cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/0cfaf48183f594c314753d30a4c4974bc75f3ccb",
  "--served-model-name",
  "32BI",
  "--port",
  "8031",
  "--max-model-len",
  "32768",
  "--gpu-memory-utilization",
  "0.9",
  "--tensor-parallel-size",
  "1",
  "--no-enable-prefix-caching",
  "--limit-mm-per-prompt",
  "{\"image\": 16}",
  "--dtype",
  "bfloat16",
  "--seed",
  "0",
  "--limit-mm-per-prompt",
  "{\"image\": 640, \"video\": 1}",
  "--mm-processor-kwargs",
  "{\"size\": {\"shortest_edge\": 4096, \"longest_edge\": 16777216}, \"fps\": 1.0, \"do_sample_frames\": false}",
  "--trust-request-mm-kwargs",
  "--host",
  "127.0.0.1",
  "--enable-prefix-caching",
  "--enable-prompt-tokens-details",
  "--mm-processor-cache-gb",
  "128",
  "--kv-offloading-backend",
  "native",
  "--kv-offloading-size",
  "27",
  "--enable-log-requests",
  "--enable-logging-iteration-details"
 ],
}

# ------------------------------------------------------------------ argv

def build_argv(tag, port, vllm_bin=None):
    argv = list(COMMITTED_ARGV[tag])
    argv[argv.index("--port") + 1] = str(port)
    if vllm_bin:
        argv[0] = vllm_bin
    return argv


def argv_diff(built, header_path):
    ref = json.load(open(header_path))["server"]["command"]
    diff = []
    for i in range(max(len(ref), len(built))):
        a = ref[i] if i < len(ref) else None
        b = built[i] if i < len(built) else None
        if a != b:
            diff.append((i, a, b))
    return diff


def diff_ok(built, diff):
    allowed = {built.index("--port") + 1, 0}
    return all(i in allowed for i, _, _ in diff)


# ------------------------------------------------------------------ prompts

def chain_tokens(chain, ntok, seed=20261126):
    r = random.Random(f"{seed}:{chain}")
    return [r.randrange(1000, 100000) for _ in range(ntok)]


def block_keys(prompt):
    h, keys = 0, []
    for i in range(len(prompt) // BLOCK):
        h = hash((h, tuple(prompt[i * BLOCK:(i + 1) * BLOCK])))
        keys.append(h)
    return keys


# ------------------------------------------------------------------ metrics

_LINE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eE]+|NaN|\+Inf|-Inf)\s*$')


def parse_metrics(text):
    """flat dict: name (trailing _total stripped; {source=X} kept) -> value summed over other labels."""
    out = {}
    for line in text.splitlines():
        if not line or line[0] == "#":
            continue
        m = _LINE.match(line)
        if not m:
            continue
        name, labels, val = m.group(1), m.group(2) or "", float(m.group(3))
        if not name.startswith("vllm:"):
            continue
        if name.endswith("_total"):
            name = name[:-6]
        key = name
        sm = re.search(r'source="([^"]*)"', labels)
        if sm:
            key = f"{name}{{source={sm.group(1)}}}"
        if name == "vllm:cache_config_info":
            nb = re.search(r'num_gpu_blocks="(\d+)"', labels)
            if nb:
                out["num_gpu_blocks"] = float(nb.group(1))
            continue
        out[key] = out.get(key, 0.0) + val
    return out


KEEP = ("vllm:kv_offload_store_bytes", "vllm:kv_offload_load_bytes", "vllm:kv_offload_allocation_failure",
        "vllm:kv_offload_store_size_count", "vllm:kv_offload_load_size_count",
        "vllm:external_prefix_cache_queries", "vllm:external_prefix_cache_hits",
        "vllm:prefix_cache_queries", "vllm:prefix_cache_hits", "vllm:prompt_tokens_cached",
        "vllm:kv_offload_cpu_write_usage_perc", "vllm:kv_offload_cpu_read_usage_perc",
        "vllm:kv_offload_cpu_cache_usage_perc", "vllm:kv_cache_usage_perc", "vllm:prompt_tokens_by_source")
REQUIRED_NAMES = ("vllm:kv_offload_store_bytes", "vllm:kv_offload_load_bytes",
                  "vllm:kv_offload_allocation_failure", "vllm:external_prefix_cache_hits",
                  "vllm:prompt_tokens_by_source{source=external_kv_transfer}",
                  "vllm:prompt_tokens_by_source{source=local_cache_hit}")
DRAIN_KEYS = ("vllm:kv_offload_store_bytes", "vllm:kv_offload_store_size_count",
              "vllm:kv_offload_cpu_write_usage_perc")


def keep(m):
    return {k: v for k, v in m.items() if k.startswith(KEEP) or k == "num_gpu_blocks"}


def delta(m0, m1, k):
    return m1.get(k, 0.0) - m0.get(k, 0.0)


# ------------------------------------------------------------------ fake engine (source-derived rule + rivals)

class FakeEngine:
    """In-process model of the rule READ FROM THE SOURCE (design section 1): per-chunk LRU; rank assigned at
    insert head-to-tail, re-ranked at request finish over every touched key in reversed(head-to-tail) order (head
    ends highest, tail lowest); host hit copies and leaves the host copy; loaded and offered keys are protected
    during the request; a store offer needing more evictions than there are unprotected chunks is dropped whole;
    a request that loaded from host does not re-offer the chunks up to the end of its loaded range, a request
    without a host load re-offers every computed-or-GPU-hit prompt chunk; GPU pool LRU with the tail freed first.
    rule: source | head (no reversal at finish: head evicted first) | whole (evict the owner of the lowest
    chunk wholesale). capacity overridable (cap3200 rival)."""

    def __init__(self, capacity=3456, gpu_blocks=1968, rule="source", gpu_hit_reoffer=True):
        self.cap, self.G, self.rule, self.reoffer = capacity, gpu_blocks, rule, gpu_hit_reoffer
        self.host = {}
        self.gpu = OrderedDict()
        self.rank = 0
        self.c = {"store_bytes": 0, "load_bytes": 0, "alloc_fail": 0, "ext": 0, "local": 0, "compute": 0,
                  "ext_q": 0, "ext_hits": 0, "loc_q": 0, "loc_hits": 0, "cached": 0, "store_size_count": 0}
        self.mmap_bytes = capacity * CHUNK_B
        self.connector = "OffloadingConnector"
        self.names = list(REQUIRED_NAMES)

    def _evict(self, n, protected):
        cand = [(v[0], k) for k, v in self.host.items() if k not in protected]
        if self.rule == "whole":
            cand.sort()
            freed = 0
            owners = []
            for _, k in cand:
                o = self.host[k][1]
                if o not in owners:
                    owners.append(o)
                    freed = sum(1 for kk, vv in self.host.items() if vv[1] in owners and kk not in protected)
                    if freed >= n:
                        break
            if freed < n:
                return False
            for k in [k for k, v in self.host.items() if v[1] in owners and k not in protected]:
                del self.host[k]
            return True
        if len(cand) < n:
            return False
        cand.sort()
        for _, k in cand[:n]:
            del self.host[k]
        return True

    def request(self, prompt, max_tokens=1, max_offload_tokens=None, chain=None):
        L = len(prompt)
        keys = block_keys(prompt)
        nfull = len(keys)
        cap_hit = (L - 1) // BLOCK
        g = 0
        while g < cap_hit and keys[g] in self.gpu:
            g += 1
        h = 0
        while g + h < cap_hit and keys[g + h] in self.host:
            h += 1
        loaded = keys[g:g + h]
        self.c["loc_q"] += L
        self.c["loc_hits"] += g * BLOCK
        self.c["ext_q"] += L - g * BLOCK
        self.c["ext_hits"] += h * BLOCK
        self.c["local"] += g * BLOCK
        self.c["ext"] += h * BLOCK
        self.c["compute"] += L - (g + h) * BLOCK
        self.c["cached"] += (g + h) * BLOCK
        self.c["load_bytes"] += h * CHUNK_B
        touched = list(loaded)
        no_store = max_offload_tokens == 0
        if not no_store:
            start = (g + h) if h > 0 else (0 if self.reoffer else g)
            offered = keys[start:nfull]
            new = [k for k in offered if k not in self.host]
            existing = [k for k in offered if k in self.host]
            protected = set(loaded) | set(offered)
            free = self.cap - len(self.host)
            need = len(new) - free
            ok = True
            if need > 0:
                ok = self._evict(need, protected)
            if not ok:
                self.c["alloc_fail"] += 1
                touched += existing
            else:
                for k in new:
                    self.rank += 1
                    self.host[k] = [self.rank, chain]
                if new:
                    self.c["store_bytes"] += len(new) * CHUNK_B
                    self.c["store_size_count"] += 1
                touched += offered
        pos = {k: i for i, k in enumerate(keys)}
        order = sorted(set(touched), key=pos.__getitem__)
        if self.rule != "head":
            order = list(reversed(order))
        for k in order:
            self.rank += 1
            self.host[k][0] = self.rank
        for k in reversed(keys):
            self.gpu[k] = None
            self.gpu.move_to_end(k)
        while len(self.gpu) > self.G:
            self.gpu.popitem(last=False)
        return {"cached_tokens": (g + h) * BLOCK, "prompt_tokens": L, "completion_tokens": max_tokens}

    def metrics(self):
        c = self.c
        return {"vllm:kv_offload_store_bytes": c["store_bytes"], "vllm:kv_offload_load_bytes": c["load_bytes"],
                "vllm:kv_offload_allocation_failure": c["alloc_fail"],
                "vllm:kv_offload_store_size_count": c["store_size_count"],
                "vllm:external_prefix_cache_queries": c["ext_q"], "vllm:external_prefix_cache_hits": c["ext_hits"],
                "vllm:prefix_cache_queries": c["loc_q"], "vllm:prefix_cache_hits": c["loc_hits"],
                "vllm:prompt_tokens_cached": c["cached"], "vllm:kv_offload_cpu_write_usage_perc": 0.0,
                "vllm:prompt_tokens_by_source{source=external_kv_transfer}": c["ext"],
                "vllm:prompt_tokens_by_source{source=local_cache_hit}": c["local"],
                "vllm:prompt_tokens_by_source{source=local_compute}": c["compute"],
                "num_gpu_blocks": self.G}

    def drain(self, stable_s=2.0):
        return 0.0

    def startup_info(self):
        return {"connector": self.connector, "mmap_bytes": self.mmap_bytes, "mmap_path": "FAKE",
                "gpu_blocks_log": self.G, "gpu_blocks_metric": self.G,
                "metric_names_missing": [], "source": "fake_engine"}


# ------------------------------------------------------------------ real engine

class HttpEngine:
    def __init__(self, port, log_path, shm_before, shm_glob="/dev/shm/vllm_offload_*.mmap"):
        self.url = f"http://127.0.0.1:{port}"
        self.log_path, self.shm_before, self.shm_glob = log_path, shm_before, shm_glob

    def _get(self, path, timeout=30):
        with urllib.request.urlopen(self.url + path, timeout=timeout) as r:
            return r.read().decode()

    def metrics_raw(self):
        return self._get("/metrics")

    def metrics(self):
        return parse_metrics(self.metrics_raw())

    def drain(self, stable_s=2.0, timeout=180.0, poll=0.25):
        t0, last, since = time.time(), None, time.time()
        while time.time() - t0 < timeout:
            m = self.metrics()
            cur = tuple(m.get(k, 0.0) for k in DRAIN_KEYS)
            if cur != last:
                last, since = cur, time.time()
            elif time.time() - since >= stable_s and cur[2] == 0.0:
                return time.time() - t0
            time.sleep(poll)
        raise RuntimeError("store drain did not settle within %.0f s" % timeout)

    def request(self, prompt, max_tokens=1, max_offload_tokens=None, chain=None):
        body = {"model": SERVED, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
        if max_tokens > 1:
            body["ignore_eos"] = True
        if max_offload_tokens is not None:
            body["kv_transfer_params"] = {"max_offload_tokens": int(max_offload_tokens)}
        req = urllib.request.Request(self.url + "/v1/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1800) as r:
            d = json.loads(r.read().decode())
        u = d["usage"]
        det = u.get("prompt_tokens_details") or {}
        return {"cached_tokens": int(det.get("cached_tokens") or 0), "prompt_tokens": u["prompt_tokens"],
                "completion_tokens": u["completion_tokens"]}

    def startup_info(self):
        log = open(self.log_path, errors="replace").read() if os.path.exists(self.log_path) else ""
        conn = re.search(r"Creating v1 connector with name: (\w+)", log)
        gb = re.search(r"GPU KV cache size: ([\d,]+) tokens", log)
        files = sorted(set(glob.glob(self.shm_glob)) - set(self.shm_before), key=os.path.getmtime)
        m = self.metrics()
        names_missing = [n for n in REQUIRED_NAMES if n not in m and n.split("{")[0] not in m]
        created = re.findall(r"Created mmap file (\S+) \(([\d.]+) GB\)", log)
        return {"connector": conn.group(1) if conn else None,
                "mmap_path": files[-1] if files else None,
                "mmap_bytes": os.stat(files[-1]).st_size if files else None,
                "mmap_files_new": files, "mmap_log": created,
                "gpu_blocks_log": int(gb.group(1).replace(",", "")) // BLOCK if gb else None,
                "gpu_kv_tokens_log": int(gb.group(1).replace(",", "")) if gb else None,
                "gpu_blocks_metric": m.get("num_gpu_blocks"),
                "metric_names_missing": names_missing, "source": "http"}


def wait_up(port, proc, timeout=1500):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early rc={proc.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    return time.time() - t0
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("server not up")


# ------------------------------------------------------------------ recorder and steps

class Rec:
    def __init__(self, req_path, met_path):
        self.reqs, self.mets, self.seq = [], [], 0
        self.fr = open(req_path, "w") if req_path else None
        self.fm = open(met_path, "w") if met_path else None

    def metrics(self, step, phase, m):
        row = {"seq": step, "phase": phase, "t": time.time(), "m": keep(m)}
        self.mets.append(row)
        if self.fm:
            self.fm.write(json.dumps(row) + "\n")
            self.fm.flush()

    def req(self, row):
        self.reqs.append(row)
        if self.fr:
            self.fr.write(json.dumps(row) + "\n")
            self.fr.flush()


class Ctx:
    def __init__(self, eng, rec, tag, num_chunks, gpu_blocks, flush_n, seed=20261126, reads_store=False):
        self.eng, self.rec, self.tag = eng, rec, tag
        self.C, self.G, self.flush_n, self.seed, self.reads_store = num_chunks, gpu_blocks, flush_n, seed, reads_store
        self.chain_id = 0

    def new_chain(self):
        self.chain_id += 1
        return self.chain_id

    def step(self, part, trial, label, role, chain, n_blocks=None, ntok=None, max_offload=None, max_tokens=1):
        ntok = ntok if ntok is not None else n_blocks * BLOCK + 1
        self.rec.seq += 1
        sq = self.rec.seq
        prompt = chain_tokens(chain, ntok, self.seed)
        self.eng.drain()
        m0 = self.eng.metrics()
        self.rec.metrics(sq, "before", m0)
        t0 = time.time()
        r = self.eng.request(prompt, max_tokens=max_tokens, max_offload_tokens=max_offload, chain=chain)
        lat = time.time() - t0
        dr = self.eng.drain()
        m1 = self.eng.metrics()
        self.rec.metrics(sq, "after", m1)
        src = "vllm:prompt_tokens_by_source{source=%s}"
        row = {"seq": sq, "part": part, "trial": trial, "label": label, "role": role, "chain": chain,
               "ntok": ntok, "n_blocks": (ntok - 1) // BLOCK, "max_offload_tokens": max_offload,
               "max_tokens": max_tokens, "cached_tokens": r["cached_tokens"], "completion_tokens": r["completion_tokens"],
               "host_hit_tokens": delta(m0, m1, src % "external_kv_transfer"),
               "local_hit_tokens": delta(m0, m1, src % "local_cache_hit"),
               "compute_tokens": delta(m0, m1, src % "local_compute"),
               "store_bytes": delta(m0, m1, "vllm:kv_offload_store_bytes"),
               "load_bytes": delta(m0, m1, "vllm:kv_offload_load_bytes"),
               "alloc_fail": delta(m0, m1, "vllm:kv_offload_allocation_failure"),
               "latency_s": lat, "drain_s": dr}
        self.rec.req(row)
        return row

    def flush(self, part, trial, tag=""):
        for i in range(self.flush_n):
            self.step(part, trial, f"flush{tag}{i}", "flush", self.new_chain(), ntok=FLUSH_TOKENS, max_offload=0)

    def read_off(self):
        return None if self.reads_store else 0


def p1(ctx, trial, n=P1_N):
    K = math.ceil(ctx.C / n) + 2
    chains = []
    for i in range(K):
        c = ctx.new_chain()
        chains.append(c)
        ctx.step("P1", trial, f"fill{i + 1}", "fill", c, n_blocks=n)
    ctx.flush("P1", trial)
    for i in reversed(range(K)):
        ctx.step("P1", trial, f"read{i + 1}", "read", chains[i], n_blocks=n)
    ctx.step("P1", trial, "ctl_fresh", "ctl", ctx.new_chain(), n_blocks=n)
    return chains


def p2(ctx, trial, n=P2_N):
    ro = ctx.read_off()
    # R-host: A, B, flush, re-request A (host hit), C, flush, read A B C
    A, B, C = (ctx.new_chain() for _ in range(3))
    ctx.step("P2", trial, "Rhost.A", "fill", A, n_blocks=n)
    ctx.step("P2", trial, "Rhost.B", "fill", B, n_blocks=n)
    ctx.flush("P2", trial, ".Rhost1")
    ctx.step("P2", trial, "Rhost.A2", "rehit", A, n_blocks=n)
    ctx.step("P2", trial, "Rhost.C", "fill", C, n_blocks=n)
    ctx.flush("P2", trial, ".Rhost2")
    for nm, c in (("A", A), ("B", B), ("C", C)):
        ctx.step("P2", trial, f"Rhost.read{nm}", "read", c, n_blocks=n, max_offload=ro)
    # R-gpu: A, B, re-request A WITHOUT flush (A head still on GPU), C, flush, read
    A, B, C = (ctx.new_chain() for _ in range(3))
    ctx.step("P2", trial, "Rgpu.A", "fill", A, n_blocks=n)
    ctx.step("P2", trial, "Rgpu.B", "fill", B, n_blocks=n)
    ctx.step("P2", trial, "Rgpu.A2", "rehit_gpu", A, n_blocks=n)
    ctx.step("P2", trial, "Rgpu.C", "fill", C, n_blocks=n)
    ctx.flush("P2", trial, ".Rgpu")
    for nm, c in (("A", A), ("B", B), ("C", C)):
        ctx.step("P2", trial, f"Rgpu.read{nm}", "read", c, n_blocks=n, max_offload=ro)
    # R-gone: A B C D (4,656 chunks), flush, re-request A (store on: does a GPU/host hit re-store?), flush, read A
    ch = [ctx.new_chain() for _ in range(4)]
    for nm, c in zip("ABCD", ch):
        ctx.step("P2", trial, f"Rgone.{nm}", "fill", c, n_blocks=n)
    ctx.flush("P2", trial, ".Rgone1")
    ctx.step("P2", trial, "Rgone.A2", "restore", ch[0], n_blocks=n)
    ctx.flush("P2", trial, ".Rgone2")
    ctx.step("P2", trial, "Rgone.readA", "read", ch[0], n_blocks=n, max_offload=ro)


def p3(ctx, trial, n=256):
    c = ctx.new_chain()
    ctx.step("P3", trial, "i.default", "fill", c, n_blocks=n)
    ctx.flush("P3", trial, ".i")
    ctx.step("P3", trial, "i.read", "read", c, n_blocks=n, max_offload=0)
    c = ctx.new_chain()
    ctx.step("P3", trial, "ii.cap0", "fill_cap0", c, n_blocks=n, max_offload=0)
    ctx.step("P3", trial, "ii.gpu_reread", "gpu_reread", c, n_blocks=n, max_offload=0)
    ctx.flush("P3", trial, ".ii")
    ctx.step("P3", trial, "ii.host_read", "read", c, n_blocks=n, max_offload=0)
    c = ctx.new_chain()
    ctx.step("P3", trial, "iii.decode", "fill_decode", c, n_blocks=n, max_tokens=256)


def p4(ctx, trial, n=P2_N, workers=7):
    chains = [ctx.new_chain() for _ in range(workers)]
    eng = ctx.eng
    eng.drain()
    m0 = eng.metrics()
    ctx.rec.seq += 1
    sq = ctx.rec.seq
    ctx.rec.metrics(sq, "before", m0)
    out = {}

    def go(c):
        out[c] = eng.request(chain_tokens(c, n * BLOCK + 1, ctx.seed), 1, None, c)
    if isinstance(eng, FakeEngine):
        for c in chains:
            go(c)
    else:
        th = [threading.Thread(target=go, args=(c,)) for c in chains]
        [t.start() for t in th]
        [t.join() for t in th]
    eng.drain()
    m1 = eng.metrics()
    ctx.rec.metrics(sq, "after", m1)
    ctx.rec.req({"seq": sq, "part": "P4", "trial": trial, "label": "concurrent_fill", "role": "p4fill",
                 "chain": chains, "ntok": n * BLOCK + 1, "n_blocks": n, "max_offload_tokens": None,
                 "cached_tokens": sum(v["cached_tokens"] for v in out.values()),
                 "store_bytes": delta(m0, m1, "vllm:kv_offload_store_bytes"),
                 "alloc_fail": delta(m0, m1, "vllm:kv_offload_allocation_failure"), "concurrent": workers})
    ctx.flush("P4", trial)
    for i, c in enumerate(chains):
        ctx.step("P4", trial, f"read{i + 1}", "read", c, n_blocks=n, max_offload=0)


# ------------------------------------------------------------------ host checks, launch, main

def meminfo_gb(key):
    for ln in open("/proc/meminfo"):
        if ln.startswith(key + ":"):
            return int(ln.split()[1]) / 1e6
    return 0.0


def required_free_gb(host_gib):
    return int(math.ceil((1.25 * host_gib * 1.0737 + 8.0) / 5.0) * 5)


def preflight(args, argv):
    """returns list of abort reasons (empty = go)."""
    bad = []
    q = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    if q.returncode != 0:
        bad.append("nvidia-smi failed")
    else:
        for ln in q.stdout.strip().splitlines():
            i, mem, util = [x.strip() for x in ln.split(",")]
            if int(i) == args.gpu and (float(mem) > 1000 or float(util) > 5):
                bad.append(f"GPU {args.gpu} not idle: {mem} MiB used, {util}% util")
    ap = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory,gpu_uuid", "--format=csv,noheader"],
                        capture_output=True, text=True)
    uuid = subprocess.run(["nvidia-smi", "-i", str(args.gpu), "--query-gpu=uuid", "--format=csv,noheader"],
                          capture_output=True, text=True).stdout.strip()
    if uuid and uuid in ap.stdout:
        bad.append(f"compute process on GPU {args.gpu}: {ap.stdout.strip()}")
    ps = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout.splitlines()
    others = [ln.strip() for ln in ps if "vllm serve" in ln or "vllm.entrypoints" in ln]
    if others and not args.allow_other_vllm:
        bad.append("another vllm server is running (cell start-up possible): " + others[0][:160])
    need = required_free_gb(args.host_gib)
    if meminfo_gb("MemAvailable") < need:
        bad.append(f"MemAvailable {meminfo_gb('MemAvailable'):.1f} GB < {need} GB")
    shm = shutil.disk_usage("/dev/shm")
    if shm.free < args.host_gib * 2**30 * 1.05:
        bad.append(f"/dev/shm free {shm.free / 1e9:.1f} GB < mmap size")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host-gib", type=float, default=13.5, choices=[13.5, 27.0])
    ap.add_argument("--gpu", type=int, default=3)
    ap.add_argument("--port", type=int, default=8131)
    ap.add_argument("--vllm-bin", default=None)
    ap.add_argument("--parts", default="A,P1,P2,P3")
    ap.add_argument("--p4", action="store_true")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--reads-store", action="store_true")
    ap.add_argument("--flush-n", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--header", default=None, help="committed header.json to diff the argv against")
    ap.add_argument("--allow-other-vllm", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fake-rule", default="source", choices=["source", "head", "whole", "cap3200", "nogpureoffer"])
    args = ap.parse_args()

    tag = "h135" if args.host_gib == 13.5 else "h27"
    port = args.port
    argv = build_argv(tag, port, args.vllm_bin)
    header = args.header or str(REPO / HEADER_REF[tag])
    if not os.path.exists(header):
        sys.exit(f"abort: committed header not found: {header} (pass --header)")
    diff = argv_diff(argv, header)
    print("flag diff vs committed header.json (%s):" % os.path.basename(os.path.dirname(header)))
    print("  " + ("EMPTY" if not diff else "\n  ".join(f"argv[{i}]: committed={a!r} probe={b!r}" for i, a, b in diff)))
    if not diff_ok(argv, diff):
        sys.exit("abort: flag diff contains more than the port (and --vllm-bin)")
    parts = args.parts.split(",")
    if tag == "h27" and "P2" in parts:
        parts.remove("P2")
        print("note: P2 skipped at 27 GiB (n=2,316 chains would exceed max-model-len; design runs P1+P3 only)")
    out = Path(args.out_dir) if args.out_dir else (
        Path(__import__("tempfile").mkdtemp(prefix="hosttier_dry_")) if args.dry_run
        else REPO / "results" / "orchestration" / "live2" / "engine_probe")
    out.mkdir(parents=True, exist_ok=True)
    stem = f"hosttier_probe_{tag}_h100nvl" + (f"_dryrun_{args.fake_rule}" if args.dry_run else "")
    rec = Rec(out / f"{stem}_requests.jsonl", out / f"{stem}_metrics.jsonl")

    proc, server_log, shm_before = None, out / f"{stem}_server.log", glob.glob("/dev/shm/vllm_offload_*.mmap")
    startup_s = None
    try:
        if args.dry_run:
            cap = {"cap3200": 3200}.get(args.fake_rule, CHUNKS_EXPECT[tag])
            rule = {"cap3200": "source"}.get(args.fake_rule, args.fake_rule)
            eng = FakeEngine(capacity=cap, gpu_blocks=GPU_BLOCKS_EXPECT.get(tag, 3934), rule=rule)
            eng.mmap_bytes = CHUNKS_EXPECT[tag] * CHUNK_B
            device = "fake_engine_dry_run"
        else:
            bad = preflight(args, argv)
            if bad:
                sys.exit("abort (preflight): " + "; ".join(bad))
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(args.gpu))
            lf = open(server_log, "w")
            proc = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            startup_s = wait_up(port, proc)
            eng = HttpEngine(port, str(server_log), shm_before)
            device = "nvidia_h100_nvl_gpu%d" % args.gpu
        info = eng.startup_info()
        print("PART A:", json.dumps(info))
        nbytes = info.get("mmap_bytes")
        if info["connector"] != "OffloadingConnector":
            sys.exit(f"abort: connector is {info['connector']!r}, not OffloadingConnector (Step 0 invalidator)")
        if not nbytes or nbytes % CHUNK_B:
            sys.exit(f"abort: mmap size {nbytes} is not a whole number of {CHUNK_B}-byte chunks")
        num_chunks = nbytes // CHUNK_B
        gpu_blocks = int(info.get("gpu_blocks_metric") or info.get("gpu_blocks_log") or 0)
        if not gpu_blocks:
            sys.exit("abort: GPU block count not found in the log or in cache_config_info")
        flush_n = args.flush_n or (1 if gpu_blocks <= 1968 else math.ceil(gpu_blocks / 1960))
        part_a = dict(info, num_chunks=num_chunks, expect_num_chunks=CHUNKS_EXPECT[tag],
                      gpu_blocks=gpu_blocks, expect_gpu_blocks=GPU_BLOCKS_EXPECT.get(tag), flush_n=flush_n,
                      startup_s=startup_s, chunk_bytes=CHUNK_B)
        ctx = Ctx(eng, rec, tag, num_chunks, gpu_blocks, flush_n, reads_store=args.reads_store)
        for t in range(1, args.trials + 1):
            if "P1" in parts:
                p1(ctx, t, n=P1_N if tag == "h135" else 250)
        for t in range(1, args.trials + 1):
            if "P2" in parts:
                p2(ctx, t)
        for t in range(1, args.trials + 1):
            if "P3" in parts:
                p3(ctx, t)
        if args.p4:
            p4(ctx, 1)
        result = {"experiment": "E-engine-hosttier", "tag": tag, "host_gib": args.host_gib,
                  "dry_run": args.dry_run, "fake_rule": args.fake_rule if args.dry_run else None,
                  "argv": argv, "flag_diff": diff, "header_ref": header, "parts_run": parts + (["P4"] if args.p4 else []),
                  "trials": args.trials, "reads_store": args.reads_store, "part_a": part_a,
                  "n_requests": len(rec.reqs), "requests_file": f"{stem}_requests.jsonl",
                  "metrics_file": f"{stem}_metrics.jsonl",
                  "prefix_caching_note": "prefix caching ON by committed flags; GPU local hits and host hits are separated "
                                         "via prompt_tokens_by_source; flush requests (max_offload_tokens 0) evict the GPU pool"}
        from _provenance import stamp
        result["_provenance"] = stamp(script="engine_hosttier_probe.py", model=MODEL_SLUG, device=device,
                                      n=len(rec.reqs), seed=20261126, args=args)
        (out / f"{stem}.json").write_text(json.dumps(result, indent=1, default=str))
        print(f"wrote {out / (stem + '.json')} ({len(rec.reqs)} requests)")
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=120)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
            for f in set(glob.glob("/dev/shm/vllm_offload_*.mmap")) - set(shm_before):
                try:
                    os.remove(f)
                    print("removed stale", f)
                except OSError:
                    pass
            if server_log.exists():
                with open(server_log, "rb") as a, gzip.open(str(server_log) + ".gz", "wb") as b:
                    shutil.copyfileobj(a, b)
                server_log.unlink()


if __name__ == "__main__":
    main()
