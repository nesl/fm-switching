#!/usr/bin/env python3
"""StudyE4-counterfactual — OFFLINE ANALYSIS OF EXISTING RESULTS (S-EMBER, 845 questions; Instruct, greedy). CPU only.

When does the best decision change because of capability, evidence, representation or retained state, and how much
headroom is there above (a) the best single static configuration and (b) the best configuration chosen by question
type? Decisions applied as the user answered (2026-11-09):
  - Latency: cold curves from measured single requests (StudyClean H5, StudyD10 images_I, StudyR1 'single' mode for
    32B — prefix caching OFF, verified in study_r1_run_meta); device curve from StudyDevOne N=1 + StudyDevFast N=9/18/37
    (Orin; input tokens are the vLLM counts of the identical payloads). RH4 'timing5' (prefix caching ON) is used ONLY
    as a separately labelled WARM latency for an RH4 D2 configuration. Piecewise-linear interpolation on prompt tokens
    through 100-token bin medians, within the measured range only; outside it the latency is UNKNOWN and that
    configuration is unavailable for that question (counted per configuration). Extrapolation (linear, from the two
    outermost bins) only in a separate EXTRAPOLATED sensitivity table.
  - RH4: D2 only (D1 listed, not a configuration); questions D2 could not run are infeasible for it (utility 0).
  - Device configurations use the H1 / H2 answers (H100 vLLM, identical requests) with device latency; per-question
    agreement with the device-runtime arms C1 / C2 is reported (flag if < 90 %).
Configurations: device 4B (RECENT = H1, RICH = H2); cloud 4B (H1, H2, D11 U); cloud 32B (K3, K1, D11 U, RH4 D2);
secondary set adds cloud 32B RH4 D2 WARM. Controls only: D11 F (noise floor vs K3 / H1), D11 I (not used).
Network (cloud): upload = frames the arm sends x measured bytes per frame at its resolution (raw = W x H x 3; PNG =
median of 200 real S-EMBER frames encoded at that resolution, e4_frame_bytes.json) / uplink + RTT; profiles
13.6 Mbit/s + 44 ms, 88 + 22 ms, 5 + 142 ms. ASSUMPTION: history arms (RICH, U, D2) held at the cloud upload only
frames newer than the previous question of the same video (questions ordered by question_time); RECENT uploads its
frames every time. Deadlines 1, 2, 5, 10 s; utility = correct AND delivered within the deadline.
Per type = category x question-time bin (<= 120, 120-480, > 480 s); per-type and static choices fit on half the videos
and evaluated on the other half (KFold(2) over videos, seed 0), swapped, pooled. Bootstrap by video, 2,000, seed 0.
Writes results/orchestration/study_e4/e4_results.json.
"""
import collections
import gzip
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

OUT = ROOT / "results/orchestration/study_e4"
NB, SEED = 2000, 0
NETS = {"13.6Mbps_44ms": (13.6, 0.044), "88Mbps_22ms": (88.0, 0.022), "5Mbps_142ms": (5.0, 0.142)}
DEADLINES = (1, 2, 5, 10)
FMTS = ("png", "raw")


def jl(p):
    op = gzip.open if str(p).endswith(".gz") else open
    return [json.loads(l) for l in op(p, "rt")]


def qbin(qt):
    return "le120" if qt <= 120 else ("120-480" if qt <= 480 else "gt480")


# ---------------------------------------------------------------- data
def load():
    man = collections.defaultdict(dict)
    for r in jl(ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"):
        man[r["question_id"]][r["construction"]] = r
    d11m = {r["question_id"]: r for r in jl(ROOT / "results/cost/study_d11/study_d11_inputs_manifest.jsonl")}
    ans, tok = {}, {}

    def put(key, rows, f=lambda r: True):
        ans[key], tok[key] = {}, {}
        for r in rows:
            if r.get("error") or not f(r):
                continue
            ans[key][r["question_id"]] = bool(r["correct"])
            tok[key][r["question_id"]] = r.get("prompt_tokens")
    r1 = jl(ROOT / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")
    put("K3", r1, lambda r: r["cell"] == "K3" and r["mode"] == "batched")
    put("K1", r1, lambda r: r["cell"] == "K1" and r["mode"] == "batched")
    cl = jl(ROOT / "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")
    put("H1", cl, lambda r: r["cell"] == "H1" and r["mode"] == "batched")
    put("H2", cl, lambda r: r["cell"] == "H2" and r["mode"] == "batched")
    rh = jl(ROOT / "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz")
    put("D2", rh, lambda r: r["cell"] == "D2" and r["mode"] == "batched")
    put("D1", rh, lambda r: r["cell"] == "D1" and r["mode"] == "batched")
    d11 = jl(ROOT / "results/cost/study_d11/study_d11_requests_h100nvl.jsonl")
    for arm in ("U", "F", "I"):
        put(f"{arm}32", d11, lambda r, a=arm: r["arm"] == a and r["model"] == "32BI")
        put(f"{arm}4", d11, lambda r, a=arm: r["arm"] == a and r["model"] == "4BI")
    for c in ("C1", "C2"):
        ans[c] = {r["question_id"]: bool(r["correct"]) for r in jl(ROOT / f"results/device/accuracy_{c}.jsonl")
                  if r.get("correct") is not None}
    # latency points
    h5 = [r for r in jl(ROOT / "results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz")
          if not r.get("error") and not r.get("warmup")]
    pts = {"cold32": [(r["prompt_tokens"], r["total_s"]) for r in h5 if r["model"] == "32BI"],
           "cold4": [(r["prompt_tokens"], r["total_s"]) for r in h5 if r["model"] == "4BI"]}
    pts["cold32"] += [(r["prompt_tokens"], r["latency_s"]) for r in r1 if r["mode"] == "single" and not r.get("error")]
    pts["cold32"] += [(r["prompt_tokens"], r["total_s"]) for r in jl(ROOT / "results/cost/study_d10/study_d10_requests_h100nvl.jsonl")
                      if r["load"] == "images_I" and not r["warmup"] and not r["error"]]
    dev = []
    for p in ("devfast_4bi_f16_n9.jsonl", "devfast_4bi_f16_n18.jsonl", "devfast_4bi_f16_n37.jsonl", "dev_one_n1.jsonl"):
        dev += [(r["input_tokens"], r["total_latency_s"]) for r in jl(ROOT / "results/device" / p)
                if r.get("total_latency_s") and (r.get("input_tokens") or 0) > 100]
    pts["device4"] = dev
    pts["warm32_D2"] = [(r["prompt_tokens"], r["latency_s"]) for r in rh if r["mode"] == "timing5" and r["cell"] == "D2"
                        and not r.get("error")]
    return man, d11m, ans, tok, pts


class Curve:
    def __init__(self, points, binw=100):
        p = sorted(points)
        bins = collections.defaultdict(list)
        for x, y in p:
            bins[int(x // binw)].append((x, y))
        self.cx = np.array([np.median([a for a, _ in v]) for _, v in sorted(bins.items())])
        self.cy = np.array([np.median([b for _, b in v]) for _, v in sorted(bins.items())])
        self.lo, self.hi, self.n = float(self.cx[0]), float(self.cx[-1]), len(p)

    def at(self, x, extrapolate=False):
        if x is None:
            return None, "UNKNOWN"
        if self.lo <= x <= self.hi:
            return float(np.interp(x, self.cx, self.cy)), "measured/interpolated"
        if not extrapolate or len(self.cx) < 2:
            return None, "UNKNOWN"
        if x > self.hi:
            s = (self.cy[-1] - self.cy[-2]) / (self.cx[-1] - self.cx[-2])
            return float(self.cy[-1] + s * (x - self.cx[-1])), "EXTRAPOLATED"
        s = (self.cy[1] - self.cy[0]) / (self.cx[1] - self.cx[0])
        return float(max(self.cy[0] + s * (x - self.cx[0]), 0.0)), "EXTRAPOLATED"


def hw_key(hw):
    return f"{max(hw)}x{min(hw)}" if f"{max(hw)}x{min(hw)}" in FB else f"{hw[1]}x{hw[0]}"


FB = {}


def frame_bytes(hw, fmt):
    k = f"{hw[1]}x{hw[0]}"
    if k not in FB:
        k = f"{hw[0]}x{hw[1]}"
    return FB[k]["png_median"] if fmt == "png" else FB[k]["raw"]


def main():
    global FB
    OUT.mkdir(parents=True, exist_ok=True)
    FB = json.loads((OUT / "e4_frame_bytes.json").read_text())["sizes"]
    man, d11m, ans, tok, pts = load()
    Q = sorted(man)
    assert len(Q) == 845
    meta = {q: dict(video=man[q]["RECENT"]["video_id"], qt=man[q]["RECENT"]["question_time"],
                    cat=man[q]["RECENT"]["question_category"]) for q in Q}
    res = dict(label="OFFLINE ANALYSIS OF EXISTING RESULTS (S-EMBER; Instruct; greedy); no new inference",
               at=datetime.now().isoformat(), checks={}, latency_curves={})
    # ---- checks: row matching
    res["checks"]["rows_per_arm"] = {k: len(v) for k, v in ans.items()}
    res["checks"]["arms_missing_questions"] = {k: sorted(set(Q) - set(v))[:10] + ([f"... {len(set(Q) - set(v))} total"] if len(set(Q) - set(v)) > 10 else [])
                                               for k, v in ans.items() if k not in ("F32", "F4", "C1", "C2") and set(Q) - set(v)}
    # device agreement
    agr = {}
    for dev, ref in (("C1", "H1"), ("C2", "H2")):
        ks = sorted(set(ans[dev]) & set(ans[ref]))
        agr[f"{dev}vs{ref}"] = dict(n=len(ks), agreement=float(np.mean([ans[dev][k] == ans[ref][k] for k in ks])),
                                    acc_device=float(np.mean([ans[dev][k] for k in ks])), acc_ref=float(np.mean([ans[ref][k] for k in ks])))
    res["checks"]["device_runtime_agreement"] = agr
    curves = {k: Curve(v) for k, v in pts.items()}
    res["latency_curves"] = {k: dict(n_points=c.n, token_range=[c.lo, c.hi], bins=len(c.cx),
                                     sample=[[float(a), float(b)] for a, b in list(zip(c.cx, c.cy))[:: max(1, len(c.cx) // 12)]])
                             for k, c in curves.items()}
    # ---- frames per arm and new-frame sets (history held at the cloud)
    order = collections.defaultdict(list)
    for q in Q:
        order[meta[q]["video"]].append(q)
    prev_qt = {}
    for v, qs in order.items():
        qs.sort(key=lambda q: (meta[q]["qt"], q))
        for i, q in enumerate(qs):
            earlier = [meta[p]["qt"] for p in qs[:i] if meta[p]["qt"] < meta[q]["qt"]]
            prev_qt[q] = max(earlier) if earlier else None

    def frames(arm, q):
        """[(t, hw)] the arm sends for question q."""
        rec, rich = man[q]["RECENT"], man[q]["RICH"]
        if arm in ("H1", "K3"):
            return [(t, rec["final_hw"]) for t in rec["frame_t"]]
        if arm in ("H2", "K1"):
            return [(t, rich["final_hw"]) for t in rich["frame_t"]]
        if arm in ("U4", "U32"):
            t0 = min(rec["frame_t"]) if rec["frame_t"] else meta[q]["qt"]
            return [(t, rich["final_hw"]) for t in rich["frame_t"] if t < t0] + [(t, rec["final_hw"]) for t in rec["frame_t"]]
        if arm == "D2":
            return [(float(t), (256, 352)) for t in range(0, int(meta[q]["qt"]) + 1, 2)]
        raise ValueError(arm)
    u_check = [len([1 for t, _ in frames("U32", q) if t < min(man[q]["RECENT"]["frame_t"])]) - d11m[q]["n_old"] for q in Q if q in d11m]
    res["checks"]["U_old_frame_count_vs_d11_manifest"] = dict(exact=int(sum(x == 0 for x in u_check)), n=len(u_check),
                                                              abs_diff_p50=float(np.median(np.abs(u_check))), abs_diff_max=int(np.max(np.abs(u_check))))

    def upload_bytes(arm, q, fmt, held):
        fr = frames(arm, q)
        if held and prev_qt[q] is not None:
            fr = [(t, hw) for t, hw in fr if t > prev_qt[q]]
        return sum(frame_bytes(hw, fmt) for _, hw in fr)

    CONFIGS = [  # name, model, location, family, answer key, curve, held
        ("dev-4B-RECENT", "4B", "device", "RECENT", "H1", "device4", False),
        ("dev-4B-RICH", "4B", "device", "RICH", "H2", "device4", False),
        ("cl-4B-RECENT", "4B", "cloud", "RECENT", "H1", "cold4", False),
        ("cl-4B-RICH", "4B", "cloud", "RICH", "H2", "cold4", True),
        ("cl-4B-U", "4B", "cloud", "U", "U4", "cold4", True),
        ("cl-32B-RECENT", "32B", "cloud", "RECENT", "K3", "cold32", False),
        ("cl-32B-RICH", "32B", "cloud", "RICH", "K1", "cold32", True),
        ("cl-32B-U", "32B", "cloud", "U", "U32", "cold32", True),
        ("cl-32B-D2", "32B", "cloud", "D2", "D2", "cold32", True),
    ]
    WARM = ("cl-32B-D2-WARM", "32B", "cloud", "D2", "D2", "warm32_D2", True)

    def build(configs, extrapolate):
        lat, status = {}, {}
        for name, model, loc, fam, key, curve, held in configs:
            for q in Q:
                t = tok[key].get(q)
                if q not in ans[key]:                      # arm could not run this question (RH4 over length): infeasible
                    lat[(name, q)], status[(name, q)] = None, "INFEASIBLE"
                    continue
                c, st = curves[curve].at(t, extrapolate)
                lat[(name, q)], status[(name, q)] = c, st
        return lat, status

    def utilities(configs, lat, net, fmt, dl):
        up, rtt = NETS[net]
        U = {}
        for name, model, loc, fam, key, curve, held in configs:
            for q in Q:
                c = lat[(name, q)]
                if c is None:
                    U[(name, q)] = 0.0
                    continue
                total = c if loc == "device" else c + upload_bytes(key, q, fmt, held) * 8 / (up * 1e6) + rtt
                U[(name, q)] = float(ans[key][q] and total <= dl)
        return U

    vids = sorted({meta[q]["video"] for q in Q})
    from sklearn.model_selection import KFold
    vfold = {}
    for fi, (_, te) in enumerate(KFold(2, shuffle=True, random_state=SEED).split(vids)):
        for i in te:
            vfold[vids[i]] = fi
    qfold = {q: vfold[meta[q]["video"]] for q in Q}
    qtype = {q: (meta[q]["cat"], qbin(meta[q]["qt"])) for q in Q}
    by_v = collections.defaultdict(list)
    for q in Q:
        by_v[meta[q]["video"]].append(q)
    rng = np.random.default_rng(SEED)
    boots = [[q for v in rng.choice(vids, len(vids), replace=True) for q in by_v[v]] for _ in range(NB)]

    def analyse(configs, U, qs):
        names = [c[0] for c in configs]
        attrs = {c[0]: c for c in configs}
        oracle = {q: max(U[(n, q)] for n in names) for q in qs}
        best_set = {q: [n for n in names if U[(n, q)] == oracle[q] and oracle[q] > 0] for q in qs}
        insample_static = max(names, key=lambda n: (np.mean([U[(n, q)] for q in qs]), n))
        stat_cf, type_cf = {}, {}
        for fi in (0, 1):
            tr = [q for q in qs if qfold[q] != fi]
            te = [q for q in qs if qfold[q] == fi]
            s = max(names, key=lambda n: (np.mean([U[(n, q)] for q in tr]), n))
            for q in te:
                stat_cf[q] = s
            types = collections.defaultdict(list)
            for q in tr:
                types[qtype[q]].append(q)
            for q in te:
                pool = types.get(qtype[q]) or tr
                type_cf[q] = max(names, key=lambda n: (np.mean([U[(n, x)] for x in pool]), np.mean([U[(n, x)] for x in tr]), n))
        u_or = {q: oracle[q] for q in qs}
        u_st = {q: U[(stat_cf[q], q)] for q in qs}
        u_ty = {q: U[(type_cf[q], q)] for q in qs}
        u_is = {q: U[(insample_static, q)] for q in qs}

        def m(d, sel):
            x = [d[q] for q in sel if q in d]
            return float(np.mean(x)) if x else None
        out = dict(n=len(qs), oracle=m(u_or, qs), static_crossfit=m(u_st, qs), pertype_crossfit=m(u_ty, qs),
                   static_insample=m(u_is, qs), static_insample_config=insample_static,
                   static_crossfit_configs=sorted(set(stat_cf.values())),
                   headroom_over_static=m(u_or, qs) - m(u_st, qs), headroom_over_pertype=m(u_or, qs) - m(u_ty, qs))
        bs_s = [m(u_or, b) - m(u_st, b) for b in boots]
        bs_t = [m(u_or, b) - m(u_ty, b) for b in boots]
        out["headroom_over_static_ci"] = [float(np.percentile(bs_s, 2.5)), float(np.percentile(bs_s, 97.5))]
        out["headroom_over_pertype_ci"] = [float(np.percentile(bs_t, 2.5)), float(np.percentile(bs_t, 97.5))]
        out["per_config_utility"] = {n: m({q: U[(n, q)] for q in qs}, qs) for n in names}
        # classification where the oracle beats the per-type choice
        cls = collections.Counter()
        cls_excl = collections.Counter()
        for q in qs:
            if not (u_or[q] == 1 and u_ty[q] == 0):
                continue
            c0 = attrs[type_cf[q]]
            found = set()
            for b in best_set[q]:
                cb = attrs[b]
                same_m, same_l, same_f = cb[1] == c0[1], cb[2] == c0[2], cb[3] == c0[3]
                if same_m and same_f and not same_l:
                    found.add("location")
                elif same_f and same_l and not same_m:
                    found.add("capability")
                elif same_m and same_l and not same_f:
                    found.add("representation" if {cb[3], c0[3]} == {"RICH", "D2"} else "evidence")
            if not found:
                found = {"interaction"}
            for f in found:
                cls[f] += 1
            for f in ("capability", "evidence", "representation", "interaction", "location"):
                if f in found:
                    cls_excl[f] += 1
                    break
        out["classes_any"] = dict(cls)
        out["classes_exclusive_spec_order"] = dict(cls_excl)
        out["n_oracle_beats_pertype"] = int(sum(1 for q in qs if u_or[q] == 1 and u_ty[q] == 0))
        return out

    def run(configs, extrapolate, label):
        lat, status = build(configs, extrapolate)
        unk = {c[0]: dict(collections.Counter(status[(c[0], q)] for q in Q)) for c in configs}
        tab = {}
        allknown = [q for q in Q if all(lat[(c[0], q)] is not None for c in configs)]
        matched = [q for q in Q if all(q in ans[c[4]] for c in configs)]
        for net in NETS:
            for fmt in FMTS:
                for dl in DEADLINES:
                    U = utilities(configs, lat, net, fmt, dl)
                    tab[f"{net}/{fmt}/{dl}s"] = dict(all845=analyse(configs, U, Q),
                                                     matched_rows=analyse(configs, U, matched),
                                                     all_latency_known=analyse(configs, U, allknown) if len(allknown) > 20 else None)
        return dict(label=label, latency_status_per_config=unk, n_all_latency_known=len(allknown),
                    n_matched_rows=len(matched), tables=tab)

    res["primary"] = run(CONFIGS, False, "PRIMARY: measured / interpolated latency only (cold); UNKNOWN = unavailable")
    res["with_warm_D2"] = run(CONFIGS + [WARM], False, "SECONDARY: adds cl-32B-D2-WARM (RH4 timing5, prefix caching ON) — WARM")
    res["extrapolated"] = run(CONFIGS, True, "SENSITIVITY: EXTRAPOLATED latency beyond the measured range")
    # ---- one-question trace (mechanism Step 3): 88 Mbit/s + 22 ms, PNG, 10 s
    lat_t, st_t = build(CONFIGS, False)
    tq = sorted(Q, key=lambda q: (meta[q]["video"], meta[q]["qt"]))
    tq = next(q for q in tq if meta[q]["qt"] > 120 and all(lat_t[(c[0], q)] is not None for c in CONFIGS))
    up, rtt = NETS["88Mbps_22ms"]
    tr = dict(question_id=tq, video=meta[tq]["video"], qt=meta[tq]["qt"], category=meta[tq]["cat"],
              net="88Mbps_22ms", fmt="png", deadline_s=10, configs={})
    for name, model, loc, fam, key, curve, held in CONFIGS:
        c = lat_t[(name, tq)]
        ub = 0 if loc == "device" else upload_bytes(key, tq, "png", held)
        tx = 0.0 if loc == "device" else ub * 8 / (up * 1e6) + rtt
        tr["configs"][name] = dict(answers=key, prompt_tokens=tok[key].get(tq), curve=curve, compute_s=c, upload_bytes=ub,
                                   network_s=tx, total_s=c + tx, correct=bool(ans[key][tq]),
                                   utility=float(ans[key][tq] and c + tx <= 10))
    res["trace_one_question"] = tr
    # ---- noise floor (correctness level; same latency as the arm it shadows)
    noise = {}
    for f, ref in (("F32", "K3"), ("F4", "H1")):
        ks = sorted(set(ans[f]) & set(ans[ref]))
        a, b = np.array([ans[f][k] for k in ks]), np.array([ans[ref][k] for k in ks])
        noise[f"{f}vs{ref}"] = dict(n=len(ks), disagreement=float(np.mean(a != b)), acc_F=float(a.mean()), acc_ref=float(b.mean()),
                                    oracle_headroom_from_noise=float(np.mean(a | b) - max(a.mean(), b.mean())))
    for x, y in (("K1", "K3"), ("H2", "H1"), ("K3", "H1"), ("K1", "H2"), ("U32", "K3"), ("U4", "H1"), ("D2", "K1")):
        ks = sorted(set(ans[x]) & set(ans[y]))
        a, b = np.array([ans[x][k] for k in ks]), np.array([ans[y][k] for k in ks])
        noise[f"{x}vs{y}"] = dict(n=len(ks), disagreement=float(np.mean(a != b)),
                                  oracle_headroom=float(np.mean(a | b) - max(a.mean(), b.mean())))
    res["noise_and_reversals_correctness"] = noise
    # ---- sessions (part 4): retention policies fixed per session
    sess = {}
    POL = {"32B": {"recent": ("K3", "cold32", "recent"), "stride_D2": ("D2", "cold32", "stream2s"),
                   "full_K1": ("K1", "cold32", "stream1s"), "full_U": ("U32", "cold32", "stream1s")},
           "4B": {"recent": ("H1", "cold4", "recent"), "full_H2": ("H2", "cold4", "stream1s"), "full_U": ("U4", "cold4", "stream1s")}}

    def sess_one(key_out, pnames, vals_v, unknown_counts):
        vs = [v for v in order if len(vals_v[(pnames[0], v)]) > 0]
        w = {v: len(vals_v[(pnames[0], v)]) for v in vs}
        sut = {(pn, v): float(np.mean(vals_v[(pn, v)])) for pn in pnames for v in vs}
        tot = sum(w.values()) or 1

        def agg(smp):
            tw = sum(w[v] for v in smp) or 1
            pu = {pn: sum(sut[(pn, v)] * w[v] for v in smp) / tw for pn in pnames}
            orc = sum(max(sut[(pn, v)] for pn in pnames) * w[v] for v in smp) / tw
            return pu, orc
        pol_util, orc = agg(vs)
        best_single = max(pnames, key=lambda p: pol_util[p])
        best_sets = {v: {pn for pn in pnames if sut[(pn, v)] == max(sut[(p, v)] for p in pnames)} for v in vs}
        stype = {v: collections.Counter(meta[q]["cat"] for q in order[v]).most_common(1)[0][0] for v in vs}
        differs, n_types = [], 0
        for t in set(stype.values()):
            tv = [v for v in vs if stype[v] == t]
            if len(tv) < 2:
                continue
            n_types += 1
            modal = collections.Counter(p for v in tv for p in best_sets[v]).most_common(1)[0][0]
            differs += [modal not in best_sets[v] for v in tv]
        brng = np.random.default_rng(SEED)
        bs = []
        for _ in range(NB):
            smp = list(brng.choice(vs, len(vs), replace=True))
            pu, o = agg(smp)
            bs.append(o - max(pu.values()))
        sess[key_out] = dict(
            sessions=len(vs), sessions_total=len(order), questions=sum(w.values()), unknown_questions_per_policy=unknown_counts,
            policy_utility=pol_util, best_single=best_single, per_session_oracle=orc, headroom=orc - pol_util[best_single],
            headroom_ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
            best_policy_counts=dict(collections.Counter(p for v in vs for p in best_sets[v])),
            sessions_all_policies_tied=sum(len(best_sets[v]) == len(pnames) for v in vs),
            sessions_unique_best=sum(len(best_sets[v]) == 1 for v in vs),
            same_type_sessions_best_differs_from_modal=(float(np.mean(differs)) if differs else None),
            n_same_type_sessions=len(differs), n_session_types_with_2plus=n_types)

    for model, pols in POL.items():
        for net in NETS:
            up, rtt = NETS[net]
            for fmt in FMTS:
                for dl in DEADLINES:
                    su = {}
                    for pn, (key, curve, mode) in pols.items():
                        for v, qs in order.items():
                            vals = []
                            for q in qs:
                                if q not in ans[key]:           # arm could not run it: infeasible (0), as Part 1
                                    vals.append(0.0)
                                    continue
                                c, st = curves[curve].at(tok[key].get(q))
                                if c is None:
                                    vals.append(None)           # UNKNOWN
                                    continue
                                if mode == "recent":
                                    ub = upload_bytes(key, q, fmt, False)
                                else:                       # continuous upload: only the newest frame is pending
                                    fr = frames(key, q)
                                    ub = frame_bytes(fr[-1][1], fmt) if fr else 0
                                vals.append(float(ans[key][q] and c + ub * 8 / (up * 1e6) + rtt <= dl))
                            su[(pn, v)] = vals
                    pnames = list(pols)
                    unk = {pn: sum(x is None for v in order for x in su[(pn, v)]) for pn in pnames}
                    # primary: UNKNOWN = unavailable (0), exactly as Part 1
                    vals_v = {(pn, v): [0.0 if x is None else x for x in su[(pn, v)]] for pn in pnames for v in order}
                    sess_one(f"{model}/{net}/{fmt}/{dl}s/unknown_as_unavailable", pnames, vals_v, unk)
                    # sensitivity: within each session keep only questions where every policy's latency is known
                    vals_v = {}
                    for v in order:
                        keep = [i for i in range(len(order[v])) if all(su[(pn, v)][i] is not None for pn in pnames)]
                        for pn in pnames:
                            vals_v[(pn, v)] = [su[(pn, v)][i] for i in keep]
                    sess_one(f"{model}/{net}/{fmt}/{dl}s/known_questions_only", pnames, vals_v, unk)
                    # sensitivity: drop full_U (mostly UNKNOWN) and keep questions known for the remaining policies
                    p2 = [pn for pn in pnames if pn != "full_U" and pn != "stride_D2"]
                    vals_v = {}
                    for v in order:
                        keep = [i for i in range(len(order[v])) if all(su[(pn, v)][i] is not None for pn in p2)]
                        for pn in p2:
                            vals_v[(pn, v)] = [su[(pn, v)][i] for i in keep]
                    sess_one(f"{model}/{net}/{fmt}/{dl}s/recent_vs_full_known", p2, vals_v, {pn: unk[pn] for pn in p2})
    res["session_definitions"] = dict(
        policies={m: {pn: dict(answers=v[0], latency_curve=v[1], upload=v[2]) for pn, v in pols.items()} for m, pols in POL.items()},
        session="one S-EMBER video; questions ordered by question_time; policy fixed for the whole session",
        session_type="the session's most frequent question category",
        variants=dict(unknown_as_unavailable="PRIMARY: UNKNOWN latency = unavailable (utility 0), as Part 1",
                      known_questions_only="questions where every policy's latency is known",
                      recent_vs_full_known="recent vs full (K1 / H2) only, on questions where both are known"),
        information="a fixed policy uses only frames up to each question time; best-policy choice per session is an ex-post oracle (descriptive)")
    # session noise floor: per-session choice between K3 and F32 (near-identical inputs), correctness only
    fq = [q for q in Q if q in ans["F32"]]
    sv = collections.defaultdict(list)
    for q in fq:
        sv[meta[q]["video"]].append(q)
    k3m = {v: np.mean([ans["K3"][q] for q in qs]) for v, qs in sv.items()}
    fm = {v: np.mean([ans["F32"][q] for q in qs]) for v, qs in sv.items()}
    w = {v: len(qs) for v, qs in sv.items()}
    tot = sum(w.values())
    single = max(sum(k3m[v] * w[v] for v in sv) / tot, sum(fm[v] * w[v] for v in sv) / tot)
    res["session_noise_floor"] = dict(sessions=len(sv), questions=tot,
                                      headroom_K3_vs_F32=float(sum(max(k3m[v], fm[v]) * w[v] for v in sv) / tot - single),
                                      sessions_differ=float(np.mean([k3m[v] != fm[v] for v in sv])))
    res["sessions"] = sess
    res["continuous_upload_MB_per_hour"] = {
        f: dict(stride_D2_2s=1800 * frame_bytes((256, 352), f) / 1e6, full_1fps_RICH_352x256=3600 * frame_bytes((256, 352), f) / 1e6,
                recent=0.0) for f in FMTS}
    res["assumptions"] = ["history arms held at the cloud upload only frames newer than the previous question of the same video",
                          "sessions: continuous-upload policies have only the newest frame pending at question time",
                          "device configurations use H1 / H2 answers (H100 vLLM, identical requests) with Orin latency",
                          "frame bytes: PNG medians measured on 200 S-EMBER frames per resolution; raw = W*H*3"]
    res["_provenance"] = stamp(script="study_e4_counterfactual.py", model="4BI,32BI (existing results)", device="cpu", n=len(Q))
    (OUT / "e4_results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res["checks"], indent=1, default=float)[:3000])
    print(json.dumps(res["latency_curves"], default=float)[:1500])
    print(json.dumps(res["primary"]["latency_status_per_config"], default=float))


if __name__ == "__main__":
    main()
