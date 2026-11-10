#!/usr/bin/env python3
"""StudyE6-intervention PART 0 — E4 upload-consistency fix. OFFLINE ANALYSIS OF EXISTING RESULTS, CPU only.

E4's per-question analysis (its Part 1) charged cloud-held history arms (RICH, U, D2) for every frame
newer than the PREVIOUS QUESTION of the same video, while E4's session analysis charged them for only
the newest frame pending at question time. This script recomputes E4's table 4.1 and its section-5
classification under the session rule and reports both side by side. RECENT arms keep their full
per-question upload under both rules.

ASSUMPTION (stated, not measured): RICH re-samples frames at each question (StudyRH3), so a cloud that
holds all frames at 1 fps can still build the RICH input without a new upload. The newest-frame charge
is therefore the marginal cost of keeping that cloud-side store current.

Everything else (latency curves, UNKNOWN handling, cross-fitting, bootstrap) is E4's, reimplemented so
that the OLD rule reproduces the committed e4_results.json exactly; that reproduction is check 1.
"""
import collections, gzip, json, sys
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

OUT = ROOT / "results/orchestration/study_e6"
E4 = ROOT / "results/orchestration/study_e4"
NB, SEED = 2000, 0
NETS = {"13.6Mbps_44ms": (13.6, 0.044), "88Mbps_22ms": (88.0, 0.022), "5Mbps_142ms": (5.0, 0.142)}
DEADLINES = (1, 2, 5, 10)
FMTS = ("png", "raw")


def jl(p):
    op = gzip.open if str(p).endswith(".gz") else open
    return [json.loads(l) for l in op(p, "rt")]


def qbin(qt):
    return "le120" if qt <= 120 else ("120-480" if qt <= 480 else "gt480")


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
    d11 = jl(ROOT / "results/cost/study_d11/study_d11_requests_h100nvl.jsonl")
    for arm in ("U", "F"):
        put(f"{arm}32", d11, lambda r, a=arm: r["arm"] == a and r["model"] == "32BI")
        put(f"{arm}4", d11, lambda r, a=arm: r["arm"] == a and r["model"] == "4BI")
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

    def at(self, x):
        if x is None or not (self.lo <= x <= self.hi):
            return None, "UNKNOWN" if x is not None else "UNKNOWN"
        return float(np.interp(x, self.cx, self.cy)), "measured/interpolated"


FB = {}


def frame_bytes(hw, fmt):
    k = f"{hw[1]}x{hw[0]}"
    if k not in FB:
        k = f"{hw[0]}x{hw[1]}"
    return FB[k]["png_median"] if fmt == "png" else FB[k]["raw"]


CONFIGS = [  # name, model, location, family, answers, curve, held
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


def main():
    global FB
    OUT.mkdir(parents=True, exist_ok=True)
    FB = json.loads((E4 / "e4_frame_bytes.json").read_text())["sizes"]
    man, d11m, ans, tok, pts = load()
    Q = sorted(man)
    assert len(Q) == 845, len(Q)
    meta = {q: dict(video=man[q]["RECENT"]["video_id"], qt=man[q]["RECENT"]["question_time"],
                    cat=man[q]["RECENT"]["question_category"]) for q in Q}
    curves = {k: Curve(v) for k, v in pts.items()}

    order = collections.defaultdict(list)
    for q in Q:
        order[meta[q]["video"]].append(q)
    prev_qt = {}
    for v, qs in order.items():
        qs.sort(key=lambda q: (meta[q]["qt"], q))
        for i, q in enumerate(qs):
            e = [meta[p]["qt"] for p in qs[:i] if meta[p]["qt"] < meta[q]["qt"]]
            prev_qt[q] = max(e) if e else None

    def frames(arm, q):
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

    def upload_bytes(arm, q, fmt, held, rule):
        """rule='prev_question' = E4's original (every frame newer than the previous question);
           rule='newest_frame'  = E4's session rule (only the newest frame is still pending)."""
        fr = frames(arm, q)
        if not held:
            return sum(frame_bytes(hw, fmt) for _, hw in fr)
        if rule == "newest_frame":
            return frame_bytes(fr[-1][1], fmt) if fr else 0
        if prev_qt[q] is not None:
            fr = [(t, hw) for t, hw in fr if t > prev_qt[q]]
        return sum(frame_bytes(hw, fmt) for _, hw in fr)

    lat, status = {}, {}
    for name, model, loc, fam, key, curve, held in CONFIGS:
        for q in Q:
            if q not in ans[key]:
                lat[(name, q)], status[(name, q)] = None, "INFEASIBLE"
                continue
            lat[(name, q)], status[(name, q)] = curves[curve].at(tok[key].get(q))

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

    def utilities(net, fmt, dl, rule):
        up, rtt = NETS[net]
        U = {}
        for name, model, loc, fam, key, curve, held in CONFIGS:
            for q in Q:
                c = lat[(name, q)]
                if c is None:
                    U[(name, q)] = 0.0
                    continue
                tot = c if loc == "device" else c + upload_bytes(key, q, fmt, held, rule) * 8 / (up * 1e6) + rtt
                U[(name, q)] = float(ans[key][q] and tot <= dl)
        return U

    names = [c[0] for c in CONFIGS]
    attrs = {c[0]: c for c in CONFIGS}

    def analyse(U, qs):
        oracle = {q: max(U[(n, q)] for n in names) for q in qs}
        best_set = {q: [n for n in names if U[(n, q)] == oracle[q] and oracle[q] > 0] for q in qs}
        ins = max(names, key=lambda n: (np.mean([U[(n, q)] for q in qs]), n))
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
        u_or, u_st = {q: oracle[q] for q in qs}, {q: U[(stat_cf[q], q)] for q in qs}
        u_ty = {q: U[(type_cf[q], q)] for q in qs}

        def m(d, sel):
            x = [d[q] for q in sel if q in d]
            return float(np.mean(x)) if x else None
        out = dict(n=len(qs), oracle=m(u_or, qs), static_crossfit=m(u_st, qs), pertype_crossfit=m(u_ty, qs),
                   static_insample_config=ins,
                   headroom_over_static=m(u_or, qs) - m(u_st, qs), headroom_over_pertype=m(u_or, qs) - m(u_ty, qs))
        bs_s = [m(u_or, b) - m(u_st, b) for b in boots]
        bs_t = [m(u_or, b) - m(u_ty, b) for b in boots]
        out["headroom_over_static_ci"] = [float(np.percentile(bs_s, 2.5)), float(np.percentile(bs_s, 97.5))]
        out["headroom_over_pertype_ci"] = [float(np.percentile(bs_t, 2.5)), float(np.percentile(bs_t, 97.5))]
        out["per_config_utility"] = {n: m({q: U[(n, q)] for q in qs}, qs) for n in names}
        cls, cls_excl = collections.Counter(), collections.Counter()
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

    res = dict(label="StudyE6 PART 0: E4 upload-consistency fix. OFFLINE ANALYSIS OF EXISTING RESULTS; CPU only; no inference.",
               at=datetime.now().isoformat(),
               assumption_stated=["cloud-held history arms (RICH/U/D2) pay only the newest pending frame per question, "
                                  "exactly as E4's session analysis; RECENT pays its full per-question upload under both rules",
                                  "RICH re-samples frames at each question (StudyRH3), so a cloud holding all frames at 1 fps "
                                  "can build the RICH input without a fresh upload"],
               tables={}, upload_bytes_example={})
    for rule in ("prev_question", "newest_frame"):
        for net in NETS:
            for fmt in FMTS:
                for dl in DEADLINES:
                    U = utilities(net, fmt, dl, rule)
                    res["tables"][f"{rule}/{net}/{fmt}/{dl}s"] = analyse(U, Q)
    # median per-question upload under each rule, per arm
    for key, held in (("H1", False), ("K3", False), ("H2", True), ("K1", True), ("U32", True), ("D2", True)):
        for rule in ("prev_question", "newest_frame"):
            v = [upload_bytes(key, q, "png", held, rule) for q in Q if q in ans.get(key, {})]
            res["upload_bytes_example"][f"{key}/png/{rule}"] = dict(median=float(np.median(v)), mean=float(np.mean(v)),
                                                                    max=float(np.max(v)), n=len(v))
    res["latency_status_counts"] = {c[0]: dict(collections.Counter(status[(c[0], q)] for q in Q)) for c in CONFIGS}

    # ---- check 1: does the OLD rule reproduce committed E4 table 4.1?
    e4 = json.loads((E4 / "e4_results.json").read_text())
    rep = {}
    for net in NETS:
        for fmt in FMTS:
            for dl in DEADLINES:
                k = f"{net}/{fmt}/{dl}s"
                a = e4["primary"]["tables"][k]["all845"]
                b = res["tables"][f"prev_question/{k}"]
                rep[k] = {m: dict(e4=a[m], here=b[m], diff=abs(a[m] - b[m]))
                          for m in ("oracle", "static_crossfit", "pertype_crossfit", "headroom_over_pertype")}
    res["check_reproduces_e4_old_rule"] = dict(
        max_abs_diff=float(max(v[m]["diff"] for v in rep.values() for m in v)),
        cells=len(rep), detail=rep)
    res["_provenance"] = stamp(script="study_e6_part0_upload_fix.py", model="4BI,32BI (existing results)", device="cpu", n=len(Q))
    (OUT / "e6_part0_upload_fix.json").write_text(json.dumps(res, indent=1, default=float))
    print("max abs diff vs committed E4 (old rule):", res["check_reproduces_e4_old_rule"]["max_abs_diff"])
    for k in ("13.6Mbps_44ms/png/10s", "88Mbps_22ms/png/5s", "88Mbps_22ms/png/10s", "88Mbps_22ms/raw/10s"):
        o, n = res["tables"][f"prev_question/{k}"], res["tables"][f"newest_frame/{k}"]
        print(f"{k:28s} OLD oracle {o['oracle']:.3f} pertype {o['pertype_crossfit']:.3f} hr {o['headroom_over_pertype']:.3f}"
              f"  |  NEW oracle {n['oracle']:.3f} pertype {n['pertype_crossfit']:.3f} hr {n['headroom_over_pertype']:.3f}")


if __name__ == "__main__":
    main()
