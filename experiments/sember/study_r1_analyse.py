#!/usr/bin/env python3
"""StudyR1 analysis (original .venv, CPU). Exactly the pre-registered analysis (research/EXPERIMENTS.md, StudyR1).

Pairs the 32B vLLM cells (K1 = 32B-I x RICH, K3 = 32B-I x RECENT, K2 = 32B-T x RICH) with StudyO's committed fa2
trials on question_id. Video-clustered bootstrap, 2,000 resamples, seed 0. Wilson 95% CIs for accuracies.
P4 scores: results/sember/study_r1/study_r1_p4_scores.json (study_r1_p4_scores.py; reproduces StudyO's published (d)).
"""
import json
import sys
from math import sqrt
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402

D = Path("results/sember/study_r1")
DEV = "h100nvl"
STUDYO = Path("results/sember/study_o/study_o_q4_trials_fa2.jsonl")
NBOOT, SEED = 2000, 0
E_GRID = (0.1, 0.2, 0.3)
SNAP_T = (Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Thinking/snapshots/"
          "7edd10ffd1196091948fb245ff63e406ccb2d4d1")


def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [(c - h) / d, (c + h) / d]


def boot(vids, fn):
    rng = np.random.default_rng(SEED)
    uv = np.unique(vids)
    by = {v: np.where(vids == v)[0] for v in uv}
    out = []
    for _ in range(NBOOT):
        idx = np.concatenate([by[v] for v in rng.choice(uv, size=len(uv), replace=True)])
        out.append(fn(idx))
    out = np.array(out, float)
    return [float(np.nanpercentile(out, 2.5)), float(np.nanpercentile(out, 97.5))]


def est(vids, fn):
    obs = fn(np.arange(len(vids)))
    lo, hi = boot(vids, fn)
    return dict(est=obs, ci=[lo, hi], excludes_0=bool(lo > 0 or hi < 0))


def top_e(score, e):
    k = int(round(e * len(score)))
    m = np.zeros(len(score), bool)
    if k:
        m[np.argsort(-score, kind="stable")[:k]] = True
    return m


def acc_oracle(loc, rem, e):
    return top_e((rem.astype(int) - loc.astype(int)).astype(float), e)


def pol(loc, rem, mask):
    return float(np.mean(np.where(mask, rem, loc)))


def main():
    R = [r for r in read_jsonl(D / f"study_r1_requests_{DEV}.jsonl") if r["mode"] == "batched" and not r["error"]]
    cell = {c: {r["question_id"]: r for r in R if r["cell"] == c} for c in ("K1", "K3", "K2")}
    so = {}
    for t in map(json.loads, open(STUDYO)):
        so.setdefault(f"{t['model_arm']}x{t['state_arm']}", {})[t["question_id"]] = t
    man = {(r["question_id"], r["construction"]): r for r in read_jsonl(D / "study_r1_inputs_manifest.jsonl")}
    p4 = json.loads((D / "study_r1_p4_scores.json").read_text())["p_need"]
    out = dict(n_requests=len(R), cells={}, studyo={}, tests={}, escalation={}, parity_all={}, k2={}, latency={})

    # parity over every request (prompt_tokens vs builder's expected ids)
    allr = list(read_jsonl(D / f"study_r1_requests_{DEV}.jsonl"))
    for c in ("K1", "K3", "K2"):
        rr = [r for r in allr if r["cell"] == c and not r["error"]]
        if rr:
            out["parity_all"][c] = dict(n=len(rr), exact=sum(r["prompt_tokens"] == r["expected_prompt_tokens"] for r in rr),
                                        max_abs_rel=max(abs(r["prompt_tokens"] - r["expected_prompt_tokens"])
                                                        / r["expected_prompt_tokens"] for r in rr))
    for c, m in cell.items():
        if m:
            k = sum(r["correct"] for r in m.values())
            out["cells"][c] = dict(n=len(m), acc=k / len(m), wilson95=wilson(k, len(m)),
                                   errors=sum(1 for r in allr if r["cell"] == c and r["mode"] == "batched" and r["error"]))
    for k, m in so.items():
        n = len(m)
        a = sum(t["correct"] for t in m.values())
        out["studyo"][k] = dict(n=n, acc=a / n, wilson95=wilson(a, n))
    out["studyo"]["4B-IxRICH"] = "NOT AVAILABLE (no StudyO run exists)"

    qids = sorted(set(cell["K1"]) & set(so["4B-IxRECENT"]) & set(so["8B-IxRICH"])
                  & (set(cell["K3"]) if cell["K3"] else set(cell["K1"])))
    vids = np.array([so["4B-IxRECENT"][q]["video_id"] for q in qids])
    k1 = np.array([cell["K1"][q]["correct"] for q in qids], float)
    loc = np.array([so["4B-IxRECENT"][q]["correct"] for q in qids], float)
    b8 = np.array([so["8B-IxRICH"][q]["correct"] for q in qids], float)
    t4 = np.array([so["4B-TxRICH"][q]["correct"] for q in qids], float)
    cov = np.array([man[(q, "RECENT")]["evidence_covered"] for q in qids])
    assert all(man[(q, "RECENT")]["evidence_covered"] == so["4B-IxRECENT"][q]["evidence_covered"] for q in qids)
    out["paired_n"] = len(qids)
    out["recent_covers_frac"] = float(cov.mean())

    def did(a, b):
        def f(i):
            m, c_ = ~cov[i], cov[i]
            return float((a[i][m] - b[i][m]).mean() - (a[i][c_] - b[i][c_]).mean())
        return f

    def diff(a, b, mask=None):
        def f(i):
            j = i if mask is None else i[mask[i]]
            return float((a[j] - b[j]).mean())
        return f

    T = out["tests"]
    T["cloud_helps_K1_minus_4BI_RECENT"] = est(vids, diff(k1, loc))
    if cell["K3"]:
        k3 = np.array([cell["K3"][q]["correct"] for q in qids], float)
        T["K1_minus_K3"] = est(vids, diff(k1, k3))
        T["K1_minus_K3_recent_misses"] = est(vids, diff(k1, k3, ~cov))
        T["K1_minus_K3_recent_covers"] = est(vids, diff(k1, k3, cov))
        T["history_gates_DiD"] = est(vids, did(k1, k3))
        T["K3_minus_4BI_RECENT"] = est(vids, diff(k3, loc))
    T["capability_gap_K1_minus_8BI_RICH"] = est(vids, diff(k1, b8))
    T["capability_gap_recent_misses"] = est(vids, diff(k1, b8, ~cov))
    T["capability_gap_recent_covers"] = est(vids, diff(k1, b8, cov))
    T["capability_gap_DiD"] = est(vids, did(k1, b8))
    T["capability_gap_K1_minus_4BI_RICH"] = "NOT AVAILABLE (no 4B-I x RICH run)"
    if cell["K2"]:
        q2 = [q for q in qids if q in cell["K2"]]
        if len(q2) == len(qids):
            k2 = np.array([cell["K2"][q]["correct"] for q in qids], float)
            T["cloud_helps_K2_minus_4BI_RECENT"] = est(vids, diff(k2, loc))
            T["K2_minus_K1"] = est(vids, diff(k2, k1))
            T["K2_minus_4BT_RICH"] = est(vids, diff(k2, t4))

    # escalation policies (local = 4B-I x RECENT; remote = K1, and K2 if complete)
    qt = np.array([so["4B-IxRECENT"][q]["question_time"] for q in qids])
    far = np.array([so["4B-IxRECENT"][q]["farthest"] for q in qids])
    pn = np.array([p4[q] for q in qids])
    remotes = [("K1", k1)] + ([("K2", k2)] if "cloud_helps_K2_minus_4BI_RECENT" in T else [])
    for name, rem in remotes:
        tab = {}
        for e in E_GRID:
            a, b = float(loc.mean()), float(rem.mean())
            tab[str(e)] = dict(never=a, always=b, random=(1 - e) * a + e * b, p4=pol(loc, rem, top_e(pn, e)),
                               question_time=pol(loc, rem, top_e(qt, e)), evidence_oracle=pol(loc, rem, top_e(far, e)),
                               accuracy_oracle=pol(loc, rem, acc_oracle(loc, rem, e)))

        def p4_minus_random(i, rem=rem):
            l_, r_ = loc[i], rem[i]
            return pol(l_, r_, top_e(pn[i], 0.2)) - ((0.8 * l_.mean()) + 0.2 * r_.mean())

        def qt_minus_random(i, rem=rem):
            l_, r_ = loc[i], rem[i]
            return pol(l_, r_, top_e(qt[i], 0.2)) - ((0.8 * l_.mean()) + 0.2 * r_.mean())
        out["escalation"][name] = dict(table=tab, p4_minus_random_e02=est(vids, p4_minus_random),
                                       qt_minus_random_e02=est(vids, qt_minus_random))

    # K2 thinking stats
    if cell["K2"]:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(str(SNAP_T))
        m = list(cell["K2"].values())
        closed = [r for r in m if r["think_closed"]]
        th = [len(tok(r["text"][: r["text"].index("</think>")], add_special_tokens=False)["input_ids"]) for r in closed]
        unc = [r["completion_tokens"] for r in m if not r["think_closed"]]
        out["k2"] = dict(n=len(m), closed=len(closed), unclosed=len(unc), unclosed_completion_tokens=unc,
                         think_tokens_median=float(np.median(th)) if th else None,
                         think_tokens_p90=float(np.percentile(th, 90)) if th else None,
                         completion_tokens_median=float(np.median([r["completion_tokens"] for r in m])),
                         completion_tokens_max=int(max(r["completion_tokens"] for r in m)),
                         acc_closed_only=float(np.mean([r["correct"] for r in closed])) if closed else None)

    # clean single-request latency
    for c in ("K1", "K3"):
        L = [r for r in allr if r["cell"] == c and r["mode"] == "single" and not r["error"]]
        if L:
            def s(k, L=L):
                v = np.array([r[k] for r in L], float)
                return dict(median=float(np.median(v)), p90=float(np.percentile(v, 90)), min=float(v.min()),
                            max=float(v.max()))
            out["latency"][c] = dict(n=len(L), ttft_s=s("ttft_s"), latency_s=s("latency_s"),
                                     prompt_tokens=s("prompt_tokens"), completion_tokens=s("completion_tokens"))
    out["_provenance"] = stamp(script="study_r1_analyse.py", model="qwen3vl-32b", device=DEV, n=len(R))
    (D / f"study_r1_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("cells", "parity_all", "paired_n", "recent_covers_frac")}, indent=1))
    for k, v in T.items():
        print(k, v if isinstance(v, str) else f"{v['est'] * 100:+.2f} pp CI [{v['ci'][0] * 100:+.2f}, {v['ci'][1] * 100:+.2f}]")
    print(json.dumps(out["escalation"], indent=1)[:3000])
    print(json.dumps(out["k2"]), json.dumps(out["latency"]))


if __name__ == "__main__":
    main()
