#!/usr/bin/env python3
"""StudyRH3 analysis (original .venv, CPU). Exactly the pre-registered analysis (research/EXPERIMENTS.md, StudyRH3).

Pairs A (R5/RH2 images, 160x128, 1 fps), B (R1's RICH frames as images, 288x224), C (recent 120 s 1 fps at 384x288 +
older 1 per 8 s at 160x128) with R1's K1 (RICH video), K3 (RECENT video) and RH1's H1a / H1b (RICH 50% / 25% video)
on question_id. Same stack (vLLM 0.31.0, H100, FA3), so no cross-stack caveat. Video-clustered bootstrap, 2,000
resamples, seed 0; Wilson 95% CIs. RECENT-miss split from R1's RECENT construction (evidence_covered; 97 / 748).
History tokens = prompt tokens - the same chat with no history (R1's question text only; HF tokenizer, 32B-I template),
i.e. what a device keeps warm. Warm devices per cell = floor(threshold x KV / mean history tokens) for thresholds
0.55x / 0.85x (RH2 footprint rule) and KV 65,280 (bf16) / 129,280 (FP8).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_r1_analyse import est, wilson  # noqa: E402

D = Path("results/sember/study_rh3")
R1 = Path("results/sember/study_r1")
RH1 = Path("results/sember/study_rh1")
DEV = "h100nvl"
SNAP_I = (Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-VL-32B-Instruct/snapshots/"
          "0cfaf48183f594c314753d30a4c4974bc75f3ccb")
KV = {"bf16": 65280, "fp8": 129280}
THRESH = {"clean_0.55x": 0.55, "degraded_0.85x": 0.85}
ORDER = ("K1", "K3", "H1a", "H1b", "A", "B", "C")


def text_only_tokens(rows):
    from transformers import AutoProcessor
    P = AutoProcessor.from_pretrained(str(SNAP_I))
    out = {}
    for r in rows:
        msgs = [{"role": "user", "content": [{"type": "text", "text": r["text"]}]}]
        out[r["question_id"]] = len(P.tokenizer(P.apply_chat_template(msgs, tokenize=False,
                                                                       add_generation_prompt=True))["input_ids"])
    return out


def rich_select(ts_all, cap=256):
    """StudyO's RICH rule: all 1 fps frames up to qt, uniformly capped at 256 (indices round(i(n-1)/(cap-1)))."""
    n = len(ts_all)
    return ts_all if n <= cap else [ts_all[int(round(i * (n - 1) / (cap - 1)))] for i in range(cap)]


def reusable_prefix(man, qids, step_s=10):
    """POST-HOC (not pre-registered): is each representation append-only? For every question, rebuild the cell's
    image list at qt - step_s and at qt with the same rule and count the tokens of the common leading (t, size) run
    (+ header): the most a prefix cache could reuse if the history had been sent step_s earlier (R5/RH2 append
    every 10 s). Image tokens (H/32)(W/32)+2; the header is shared. B rebuilt with StudyO's RICH rule (checked to
    reproduce the manifest's frame list at qt for every question)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import study_rh3_inputs as Bld
    tok = lambda hw: (hw[0] // 32) * (hw[1] // 32) + 2  # noqa: E731
    res, rich_ok = {c: [] for c in "ABC"}, 0
    for q in qids:
        row = man[(q, "B")]
        idx = Bld.frames_index(row["video_id"])
        qt = float(row["question_time"])

        def sel(cell, t_now):
            ts_all = sorted(t for t in idx if t <= t_now + 1e-6)
            if cell == "A":
                return [(t, Bld.SIZE_A) for t in ts_all[-Bld.MAX_IMAGES:]]
            if cell == "B":
                return [(t, Bld.SIZE_B) for t in rich_select(ts_all)]
            old = [(t, Bld.SIZE_C_OLD) for t in ts_all if t < t_now - Bld.RECENT_S and t % Bld.OLD_EVERY_S == 0]
            return old + [(t, Bld.SIZE_C_RECENT) for t in ts_all if t >= t_now - Bld.RECENT_S]
        rich_ok += [float(t) for t, _ in sel("B", qt)] == [float(t) for t in row["frame_t"]]
        if qt - step_s < 0:
            continue
        for c in "ABC":
            now, prev = sel(c, qt), sel(c, qt - step_s)
            k = next((i for i, (x, y) in enumerate(zip(now, prev)) if x != y), min(len(now), len(prev)))
            total = sum(tok(hw) for _, hw in now)
            res[c].append((sum(tok(hw) for _, hw in now[:k]) / total, total - sum(tok(hw) for _, hw in now[:k])))
    out = dict(step_s=step_s, rich_rule_reproduces_manifest=f"{rich_ok}/{len(qids)}")
    for c, v in res.items():
        frac = np.array([x for x, _ in v])
        new = np.array([y for _, y in v])
        out[c] = dict(n=len(v), reusable_frac_mean=float(frac.mean()), reusable_frac_median=float(np.median(frac)),
                      frac_ge_0p9=float((frac >= 0.9).mean()), frac_le_0p1=float((frac <= 0.1).mean()),
                      recomputed_image_tokens_mean=float(new.mean()),
                      recomputed_image_tokens_median=float(np.median(new)))
    return out


def main():
    R = list(read_jsonl(D / f"study_rh3_requests_{DEV}.jsonl"))
    r1 = list(read_jsonl(R1 / f"study_r1_requests_{DEV}.jsonl"))
    rh1 = list(read_jsonl(RH1 / f"study_rh1_requests_{DEV}.jsonl"))
    pick = lambda src, c: {r["question_id"]: r for r in src  # noqa: E731
                           if r["cell"] == c and r["mode"] == "batched" and not r["error"]}
    cell = {c: pick(R, c) for c in ("A", "B", "C")}
    cell.update({c: pick(r1, c) for c in ("K1", "K3")})
    cell.update({c: pick(rh1, c) for c in ("H1a", "H1b")})
    man = {(r["question_id"], r["cell"]): r for r in read_jsonl(D / "study_rh3_inputs_manifest.jsonl")}
    man1 = {(r["question_id"], r["construction"]): r for r in read_jsonl(R1 / "study_r1_inputs_manifest.jsonl")}
    out = dict(parity_all={}, cells={}, tests={}, table=[], warm_devices={}, coverage_split={})

    for c in ("A", "B", "C"):
        rr = [r for r in R if r["cell"] == c and r["mode"] == "batched"]
        ok = [r for r in rr if not r["error"]]
        out["parity_all"][c] = dict(n=len(ok), errors=len(rr) - len(ok),
                                    exact=sum(r["prompt_tokens"] == r["expected_prompt_tokens"] for r in ok),
                                    finish_length=sum(r["finish_reason"] == "length" for r in ok),
                                    unparsed=sum(r["pred"] == "X" for r in ok))
    out["A_capped_640"] = sum(man[(q, "A")]["capped"] for q, _ in [k for k in man if k[1] == "A"])

    qids = sorted(set.intersection(*(set(m) for m in cell.values())))
    out["paired_n"] = len(qids)
    vids = np.array([cell["K1"][q]["video_id"] for q in qids])
    A = {c: np.array([cell[c][q]["correct"] for q in qids], float) for c in cell}
    cov = np.array([man1[(q, "RECENT")]["evidence_covered"] for q in qids])
    out["recent_misses_n"] = int((~cov).sum())
    ntext = text_only_tokens([man1[(q, "RICH")] for q in qids])
    out["text_only_tokens_mean"] = float(np.mean(list(ntext.values())))

    for c in ORDER:
        m = cell[c]
        k = int(sum(m[q]["correct"] for q in qids))
        pt = np.array([m[q]["prompt_tokens"] for q in qids], float)
        hist = pt - np.array([ntext[q] for q in qids], float)
        nimg = np.array([m[q]["n_frames"] for q in qids], float)
        own = [m[q]["evidence_covered"] for q in qids]
        out["cells"][c] = dict(n=len(qids), acc=k / len(qids), wilson95=wilson(k, len(qids)),
                               prompt_tokens_mean=float(pt.mean()), prompt_tokens_median=float(np.median(pt)),
                               prompt_tokens_max=float(pt.max()), history_tokens_mean=float(hist.mean()),
                               frames_mean=float(nimg.mean()), own_evidence_covered=int(sum(own)),
                               acc_recent_misses=float(A[c][~cov].mean()), acc_recent_covers=float(A[c][cov].mean()))
        row = dict(cell=c, **{k_: out["cells"][c][k_] for k_ in ("history_tokens_mean", "prompt_tokens_mean",
                                                                  "frames_mean", "acc", "wilson95",
                                                                  "acc_recent_misses", "acc_recent_covers")})
        out["table"].append(row)
        out["warm_devices"][c] = {f"{th}_{kv}": int(np.floor(tv * kvv / hist.mean()))
                                  for th, tv in THRESH.items() for kv, kvv in KV.items()}

    def diff(a, b, mask=None):
        def f(i):
            j = i if mask is None else i[mask[i]]
            return float((a[j] - b[j]).mean())
        return f

    def did(a, b):
        def f(i):
            m, c_ = ~cov[i], cov[i]
            return float((a[i][m] - b[i][m]).mean() - (a[i][c_] - b[i][c_]).mean())
        return f

    T = out["tests"]
    pairs = [("A", "K1"), ("B", "K1"), ("C", "K1"), ("C", "K3"),          # pre-registered primary
             ("A", "H1a"), ("A", "H1b"), ("B", "A"), ("C", "B"), ("C", "A"), ("A", "K3"), ("B", "K3")]  # secondary
    for x, ref in pairs:
        T[f"{x}_minus_{ref}"] = est(vids, diff(A[x], A[ref]))
        T[f"{x}_minus_{ref}_recent_misses"] = est(vids, diff(A[x], A[ref], ~cov))
        T[f"{x}_minus_{ref}_recent_covers"] = est(vids, diff(A[x], A[ref], cov))
        T[f"{x}_minus_{ref}_DiD"] = est(vids, did(A[x], A[ref]))

    for c in ("A", "B", "C"):
        own = np.array([man[(q, c)]["evidence_covered"] for q in qids])
        out["coverage_split"][c] = dict(n_lost_coverage=int((~own).sum()),
                                        acc_lost=float(A[c][~own].mean()) if (~own).any() else None,
                                        acc_kept=float(A[c][own].mean()))
    agree = {f"{x}_vs_{y}": float(np.mean([cell[x][q]["pred"] == cell[y][q]["pred"] for q in qids]))
             for x, y in (("A", "K1"), ("B", "K1"), ("C", "K1"), ("C", "K3"), ("B", "A"))}
    out["answer_agreement"] = agree
    out["posthoc_reusable_prefix"] = reusable_prefix(man, qids)
    out["_provenance"] = stamp(script="study_rh3_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(qids))
    (D / f"study_rh3_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(paired_n=out["paired_n"], parity=out["parity_all"], capped=out["A_capped_640"],
                          text_only=out["text_only_tokens_mean"], agree=agree), indent=1))
    for r in out["table"]:
        print(f"{r['cell']:4s} hist {r['history_tokens_mean']:7.0f} prompt {r['prompt_tokens_mean']:7.0f} frames "
              f"{r['frames_mean']:6.1f} acc {r['acc'] * 100:5.2f} [{r['wilson95'][0] * 100:.1f}, "
              f"{r['wilson95'][1] * 100:.1f}] miss {r['acc_recent_misses'] * 100:5.1f} cover "
              f"{r['acc_recent_covers'] * 100:5.1f} warm {out['warm_devices'][r['cell']]}")
    for k, v in T.items():
        print(f"{k:28s} {v['est'] * 100:+6.2f} pp CI [{v['ci'][0] * 100:+6.2f}, {v['ci'][1] * 100:+6.2f}]")
    print(json.dumps(out["coverage_split"], indent=1))
    print(json.dumps(out["posthoc_reusable_prefix"], indent=1))


if __name__ == "__main__":
    main()
