"""Analysis of E-engine-hosttier (CPU only). Reads hosttier_probe_<tag>_h100nvl[...].json plus its _requests.jsonl and
prints, per part, the inferred capacity, eviction order, refresh-on-hit result, store scope, a PASS / MISMATCH line
per source-derived prediction, the rival-outcome table (replay of the same request sequence through the source-rule
model and three rivals), and the shadow parameters the measurement would replace. NO fitted constant: every
reported number is a count read from the engine or a closed form of the sizes the probe sent."""
import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_hosttier_probe as P  # noqa: E402

CB, BL = P.CHUNK_B, P.BLOCK
FAILS = []


def line(name, ok, obs, pred, note=""):
    tag = "PASS" if ok else "MISMATCH"
    if not ok:
        FAILS.append(name)
    print(f"  [{tag}] {name}: observed {obs} | predicted {pred}" + (f" | {note}" if note else ""))


def load(prefix):
    res = json.load(open(prefix + ".json"))
    rows = [json.loads(x) for x in open(os.path.join(os.path.dirname(prefix), res["requests_file"]))]
    return res, rows


def blocks(r):
    return int(round(r["cached_tokens"] / BL))


def closed_p1(K, n, C):
    over = max(0, K * n - C)
    lost_full, part = divmod(over, n)
    pred = []
    for i in range(1, K + 1):
        if i <= lost_full:
            pred.append(0)
        elif i == lost_full + 1 and part:
            pred.append(n - part)
        else:
            pred.append(n)
    return pred, part


def rule_replay(res, rows, rule, cap=None):
    pa = res["part_a"]
    eng = P.FakeEngine(capacity=cap or pa["num_chunks"], gpu_blocks=pa["gpu_blocks"], rule=rule)
    out = {}
    for r in rows:
        if r["part"] == "P4" and r["role"] == "p4fill":
            for c in r["chain"]:
                eng.request(P.chain_tokens(c, r["ntok"]), 1, None, c)
            continue
        before = dict(eng.c)
        a = eng.request(P.chain_tokens(r["chain"], r["ntok"]), r.get("max_tokens", 1), r["max_offload_tokens"], r["chain"])
        out[r["seq"]] = {"cached": a["cached_tokens"], "store": eng.c["store_bytes"] - before["store_bytes"]}
    return out


def analyse(res, rows):
    pa, tag = res["part_a"], res["tag"]
    C = pa["num_chunks"]
    print(f"== {res['tag']}  dry_run={res['dry_run']} rule={res.get('fake_rule')}  requests={len(rows)}  trials={res['trials']}")
    print("PART A (start-up; settles capacity formula)")
    line("A1 connector class", pa["connector"] == "OffloadingConnector", pa["connector"], "OffloadingConnector")
    line("A2 num_chunks = mmap bytes / 4,194,304", C == pa["expect_num_chunks"], C, pa["expect_num_chunks"],
         f"mmap_bytes={pa['mmap_bytes']}; shadow has {3457 if tag == 'h135' else 6914}")
    if pa.get("expect_gpu_blocks"):
        line("A3 GPU blocks", pa["gpu_blocks"] == pa["expect_gpu_blocks"], pa["gpu_blocks"], pa["expect_gpu_blocks"])
    else:
        print(f"  [INFO] A3 GPU blocks (no override at 1x): {pa['gpu_blocks']}")
    line("A4 required metric names present", not pa.get("metric_names_missing"), pa.get("metric_names_missing") or "all", "none missing")

    by = defaultdict(list)
    for r in rows:
        by[(r["part"], r["trial"])].append(r)

    p1cap, p1order, p1sum = [], [], []
    for (part, t), rs in sorted(by.items()):
        if part != "P1":
            continue
        fills = [r for r in rs if r["role"] == "fill"]
        reads = [r for r in rs if r["role"] == "read"]
        K, n = len(fills), fills[0]["n_blocks"]
        obs = [blocks(r) for r in reversed(reads)]
        pred, part_lost = closed_p1(K, n, C)
        ctl = [r for r in rs if r["role"] == "ctl"][0]
        S = sum(obs)
        p1sum.append(S)
        print(f"PART P1 trial {t} (K={K} chains of n={n}; fill {K * n} chunks vs capacity {C}; read newest to oldest)")
        print(f"  per-chain hit blocks, oldest to newest: {obs}")
        line("P1 negative control (never-sent chain reads 0)", blocks(ctl) == 0, blocks(ctl), 0)
        line("P1 positive control (newest chain complete)", obs[-1] == n, obs[-1], n)
        line("P1 sum of hit blocks = num_chunks (independent capacity)", S == C, S, C,
             f"inferred capacity {S} blocks = {S * BL} tokens")
        line("P1 per-chain pattern (tail-first per-chunk LRU)", obs == pred, "see list", pred)
        pidx = next((i for i, v in enumerate(pred) if 0 < v < n), None)
        if pidx is not None:
            pr = reads[K - 1 - pidx]
            lost = n - pred[pidx]
            line("P1 partial chain re-store bytes = missing tail only", pr["store_bytes"] == lost * CB,
                 int(pr["store_bytes"] // CB), lost, "chunks")
        p1cap.append(S)
        # diagnosis: capacity is read first (same order, other size), then head-first versus whole-chain
        predS, _ = closed_p1(K, n, S)
        if obs == pred:
            dg = "per-chunk LRU, tail evicted first within a chain (source rule)"
        elif S != C and obs == predS:
            dg = (f"P1 pattern equals per-chunk tail-first LRU at capacity {S} (num_chunks {C}); head-first or whole-chain "
                  f"eviction at {C} give the same hit counts: decided by the re-store bytes and the replay table below")
        else:
            pobs = obs[pidx] if pidx is not None else None
            if pidx is not None and pobs == 0:
                st = int(reads[K - 1 - pidx]["store_bytes"] // CB)
                if st == n:
                    dg = f"whole-chain eviction (partial chain read 0 and re-stored all {n} chunks)"
                elif st == part_lost or st == n - part_lost:
                    dg = f"head-first eviction (partial chain read 0 but only {st} chunks re-stored: the rest were still present)"
                else:
                    dg = f"partial chain read 0, re-store {st} chunks: unclassified (head-first or whole-chain)"
            else:
                dg = f"unexplained pattern (sum {S} versus num_chunks {C}): see per-chain list"
        print(f"  DIAGNOSIS trial {t}: {dg}")
        p1order.append(dg)

    p2 = [(t, rs) for (pt, t), rs in sorted(by.items()) if pt == "P2"]
    refresh = []
    for t, rs in p2:
        g = {r["label"]: r for r in rs}
        n = g["Rhost.A"]["n_blocks"]
        ov = max(0, 3 * n - C)
        print(f"PART P2 trial {t} (n={n}; 3 chains = {3 * n} chunks vs capacity {C}; overflow {ov})")
        ha, hb, hc = (blocks(g[f"Rhost.read{x}"]) for x in "ABC")
        line("P2 R-host A whole, B loses the overflow (refresh at finish on a host hit)", (ha, hb, hc) == (n, n - ov, n),
             (ha, hb, hc), (n, n - ov, n))
        if (ha, hb, hc) == (n, n - ov, n):
            refresh.append("host-hit refresh at request finish: YES (A kept whole, B lost its tail)")
        elif (ha, hb, hc) == (n - ov, n, n):
            refresh.append("host-hit refresh: NO (A not refreshed, A lost its tail)")
        else:
            refresh.append(f"host-hit refresh: unclear, reads A,B,C = {(ha, hb, hc)}")
        ga, gb, gc = (blocks(g[f"Rgpu.read{x}"]) for x in "ABC")
        print(f"  [INFO] R-gpu reads A,B,C = {(ga, gb, gc)} (GPU head hit {int(g['Rgpu.A2']['local_hit_tokens'] // BL)} blocks at the re-request); "
              f"A = {n} means the GPU hit refreshed the host copy; A < {n} means the GPU-resident head was not refreshed")
        restore = int(g["Rgone.A2"]["store_bytes"] // CB)
        print(f"  [INFO] R-gone: re-request of an evicted chain stored {restore} chunks; read-back after = {blocks(g['Rgone.readA'])} blocks "
              f"({'re-stores evicted chunks on a request' if restore > 0 else 'does NOT re-store'})")

    p3 = [(t, rs) for (pt, t), rs in sorted(by.items()) if pt == "P3"]
    for t, rs in p3:
        g = {r["label"]: r for r in rs}
        n = g["i.default"]["n_blocks"]
        print(f"PART P3 trial {t} (n={n})")
        line("P3(i) default store = n x 4,194,304 B", g["i.default"]["store_bytes"] == n * CB, int(g["i.default"]["store_bytes"]), n * CB)
        line("P3(i) host hit after flush = n blocks (non-GPU part reads back)", blocks(g["i.read"]) == n, blocks(g["i.read"]), n)
        line("P3(ii) max_offload_tokens 0: store 0", g["ii.cap0"]["store_bytes"] == 0, int(g["ii.cap0"]["store_bytes"]), 0)
        line("P3(ii) GPU hit before flush > 0", g["ii.gpu_reread"]["local_hit_tokens"] > 0, int(g["ii.gpu_reread"]["local_hit_tokens"]), ">0")
        line("P3(ii) host hit after flush 0", g["ii.host_read"]["host_hit_tokens"] == 0, int(g["ii.host_read"]["host_hit_tokens"]), 0)
        line("P3(iii) decode blocks not stored (store = prompt chunks only)", g["iii.decode"]["store_bytes"] == n * CB,
             int(g["iii.decode"]["store_bytes"]), n * CB)

    p4 = [r for r in rows if r["part"] == "P4"]
    if p4:
        f = [r for r in p4 if r["role"] == "p4fill"][0]
        rd = [blocks(r) for r in p4 if r["role"] == "read"]
        print("PART P4 (informational, concurrent; not a pure sequential read)")
        print(f"  allocation_failure delta {f['alloc_fail']}, sum read hits {sum(rd)} blocks (sequential prediction: capacity {C}), per chain {rd}")

    print("RIVAL OUTCOMES: replay of the same request sequence (cached tokens and store bytes per step)")
    replay_rows = [r for r in rows]
    tab = []
    Sset = sorted(set(p1sum))
    extra = [(f"rival capacity = inferred P1 sum {Sset[0]} (source order)", "source", Sset[0])] if len(Sset) == 1 and Sset[0] != C and Sset[0] != 3200 else []
    for nm, rule, cap in (("source rule (tail-first per chunk, refresh at finish)", "source", None),
                          ("rival head-first eviction", "head", None),
                          ("rival whole-chain eviction", "whole", None),
                          ("rival capacity 3,200", "source", 3200)) if not extra else (
            ("source rule (tail-first per chunk, refresh at finish)", "source", None), extra[0],
            ("rival head-first eviction", "head", None), ("rival whole-chain eviction", "whole", None),
            ("rival capacity 3,200", "source", 3200)):
        rp = rule_replay(res, replay_rows, rule, cap)
        ev = [r for r in rows if r["seq"] in rp]
        mc = sum(1 for r in ev if r["cached_tokens"] == rp[r["seq"]]["cached"])
        ms = sum(1 for r in ev if int(r["store_bytes"]) == rp[r["seq"]]["store"])
        tab.append((nm, mc, ms, len(ev)))
        first = next((r["label"] for r in ev if r["cached_tokens"] != rp[r["seq"]]["cached"]), None)
        print(f"  {nm:55s} cached match {mc}/{len(ev)}  store match {ms}/{len(ev)}  first cached mismatch: {first}")
    best = max(tab, key=lambda x: (x[1], x[2]))
    print(f"  OVERALL DIAGNOSIS (best-matching model on cached tokens, then store bytes): {best[0]} "
          f"[{best[1]}/{best[3]} cached, {best[2]}/{best[3]} store]")
    line("replay: observed sequence equals the source-rule model on every step",
         tab[0][1] == tab[0][3] and tab[0][2] == tab[0][3], f"{tab[0][1]}/{tab[0][3]} cached, {tab[0][2]}/{tab[0][3]} store",
         "all steps", f"best model: {best[0]}")

    print("SHADOW PARAMETERS THIS MEASUREMENT REPLACES (read counts, no fitted constant)")
    cap_obs = sorted(set(p1cap))
    print(f"  host capacity (blocks): P1 sum of hit blocks {cap_obs} (a capacity reading only under per-chunk tail-first order), "
          f"mmap num_chunks {C}, shadow {3457 if tag == 'h135' else 6914}")
    print(f"  LRU / eviction order: {sorted(set(p1order))}")
    print(f"  refresh rule: {sorted(set(refresh)) or 'P2 not run'}")
    print("  store scope: P3 lines above (default full prompt write-through, max_offload_tokens 0, prompt-only)")
    print(f"SUMMARY: {len(FAILS)} MISMATCH" + (": " + "; ".join(sorted(set(FAILS))) if FAILS else ", all predictions PASS"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix", help="path without .json, e.g. results/.../hosttier_probe_h135_h100nvl")
    a = ap.parse_args()
    res, rows = load(a.prefix)
    analyse(res, rows)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
