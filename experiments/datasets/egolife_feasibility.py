#!/usr/bin/env python3
"""StudyEGOLIFE-feas: annotation-only feasibility audit of EgoLifeQA for D139.

Reads the EgoLifeQA annotation JSON (fetched separately; NO VIDEO) and the committed S-EMBER
MCQ annotations. Emits gap counts, the D2 token fit at two thresholds, a clip-count disk
estimate, the S-EMBER option-count / chance check, and the D139 usable count.

The D2 token accounting is IMPORTED from live2 (`fleet/data_sources.d2_batch_tokens`), read
only, rather than re-derived here, so the tokens are the same object live2 charges.
"""
import argparse
import collections
import importlib.util
import json
import math
import re
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

SEMBER_MCQ = REPO / "results/sember/study_h/data/sember_mcq.jsonl"
LH_REQ = REPO / "results/orchestration/live2/lh_req/lh_req_definition.json"
LIVE2_DS = REPO / "experiments/orchestration/live2/fleet/data_sources.py"


def _live2():
    """Read-only import of live2's token accounting. Module level is pure constants."""
    spec = importlib.util.spec_from_file_location("live2_data_sources", LIVE2_DS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # the module's @dataclass resolves itself through sys.modules
    spec.loader.exec_module(mod)
    return mod


DS = _live2()
TOKEN_BUDGET = 19_400           # the brief's threshold
BREAKEVEN_D132 = 19_381         # reports/study_covex_hardening.md
CONTEXT_32K = 32_768
CLIP_S = 30.0                   # == DS.HISTORY_BATCH_S
CLIP_MB = 14.5                  # the brief's figure

GAP_BINS = [("le7", 0.0, 420.0), ("7_15", 420.0, 900.0),
            ("15_30", 900.0, 1800.0), ("gt30", 1800.0, math.inf)]


def tod_seconds(t):
    """HHMMSSff -> seconds of day. ff is the sub-second field and is DROPPED, so every gap
    here has 1 s resolution."""
    return int(t[0:2]) * 3600 + int(t[2:4]) * 60 + int(t[4:6])


def day_index(d):
    s = str(d).strip().upper()
    if not s.startswith("DAY") or not s[3:].isdigit():
        return None
    return int(s[3:])


def bin_of(sec):
    for name, lo, hi in GAP_BINS:
        if lo < sec <= hi:
            return name
    return "nonpositive"


def d2_tokens_for_gap(gap_s):
    """live2's own accounting: the D2 frames in (query - gap, query], one first batch."""
    n_frames = len(DS.d2_frames_in(0.0, gap_s))
    return int(DS.d2_batch_tokens(n_frames, first_batch=True)), n_frames


def classify(path, participant):
    """Every row lands in exactly one of: analysis, time_list, cross_day, malformed."""
    buckets = collections.defaultdict(list)
    for r in json.load(open(path)):
        rec = dict(participant=participant, qid=r["ID"], type=r["type"],
                   need_audio=bool(r.get("need_audio")), need_name=bool(r.get("need_name")),
                   last_time=bool(r.get("last_time")),
                   n_choices=sum(1 for k in ("choice_a", "choice_b", "choice_c",
                                             "choice_d", "choice_e") if r.get(k)),
                   answer=r.get("answer"))
        q, tgt = r.get("query_time") or {}, r.get("target_time") or {}
        qd, td = day_index(q.get("date")), day_index(tgt.get("date"))
        rec["_raw"] = dict(query=dict(q), target=dict(tgt))
        rec["date_case_anomaly"] = str(q.get("date", "")) != str(q.get("date", "")).upper() \
            or str(tgt.get("date", "")) != str(tgt.get("date", "")).upper()
        if "time_list" in tgt:
            rec["n_targets"] = len(tgt["time_list"])
            buckets["time_list"].append(rec)
            continue
        qt, tt = q.get("time"), tgt.get("time")
        if qd is None or td is None or not isinstance(qt, str) or not isinstance(tt, str) \
                or len(qt) != 8 or len(tt) != 8 or not qt.isdigit() or not tt.isdigit():
            rec["reason"] = "unparseable date or time field"
            buckets["malformed"].append(rec)
            continue
        rec.update(query_day=qd, target_day=td,
                   query_tod=tod_seconds(qt), target_tod=tod_seconds(tt))
        if qd != td:
            rec["gap_s_wallclock"] = (qd - td) * 86400 + rec["query_tod"] - rec["target_tod"]
            buckets["cross_day"].append(rec)
            continue
        gap = rec["query_tod"] - rec["target_tod"]
        rec["gap_s"] = gap
        if gap <= 0:
            rec["reason"] = f"same-day gap is not positive ({gap} s)"
            buckets["malformed"].append(rec)
            continue
        buckets["analysis"].append(rec)
    return buckets


def flag_split(rows, key):
    """Counts with and without a boolean flag, each with its own denominator."""
    with_, without = [r for r in rows if r[key]], [r for r in rows if not r[key]]
    return dict(denominator=len(rows),
                with_flag=len(with_), without_flag=len(without),
                with_flag_bins=dict(collections.Counter(bin_of(r["gap_s"]) for r in with_)),
                without_flag_bins=dict(collections.Counter(bin_of(r["gap_s"])
                                                           for r in without)))


def sember_block():
    mcq = [json.loads(l) for l in open(SEMBER_MCQ)]
    lh = json.load(open(LH_REQ))
    ids = set(lh["lh_req_question_ids"])
    sub = [r for r in mcq if r["question_id"] in ids]
    opt_lh = collections.Counter(len(r["options"]) for r in sub)
    k = next(iter(opt_lh)) if len(opt_lh) == 1 else None
    n, p = lh["n"], 1.0 / k
    recent, d2 = lh["recent_acc"], lh["d2_acc"]
    nr, nd = round(recent / 100 * n), round(d2 / 100 * n)

    def tail(x):
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x, n + 1))
    letters = collections.Counter(r["correct_letter"] for r in sub)
    return dict(
        mcq_rows=len(mcq),
        option_count_all=dict(collections.Counter(len(r["options"]) for r in mcq)),
        lh_req_n=n, lh_req_resolved=len(sub), lh_req_missing=n - len(sub),
        option_count_lh_req=dict(opt_lh), options_per_question=k,
        chance_pct=100.0 / k, chance_if_four_option_pct=25.0,
        recent_acc_pct=recent, recent_correct=nr,
        d2_acc_pct=d2, d2_correct=nd,
        expected_correct_at_chance=round(n * p, 2),
        recent_minus_chance_pp=round(recent - 100.0 / k, 4),
        p_recent_ge_observed=tail(nr), p_d2_ge_observed=tail(nd),
        correct_letter_dist=dict(letters),
        max_letter_prior_pct=round(100 * max(letters.values()) / len(sub), 2),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", action="append", required=True,
                    help="participant=path/to/EgoLifeQA_<P>.json")
    ap.add_argument("--clip-mb", type=float, default=CLIP_MB)
    ap.add_argument("--hf-meta", help="cached https://huggingface.co/api/datasets/<id> response")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    buckets = collections.defaultdict(list)
    total_read = 0
    for spec in args.qa:
        name, _, path = spec.partition("=")
        b = classify(path, name)
        total_read += sum(len(v) for v in b.values())
        for k, v in b.items():
            buckets[k] += v

    A = buckets["analysis"]
    gaps = [r["gap_s"] for r in A]

    cat_bin = collections.defaultdict(collections.Counter)
    for r in A:
        cat_bin[r["type"]][bin_of(r["gap_s"])] += 1

    # item 3: tokens for every question at 15 min or less, from live2's accounting
    def clips_for(r):
        """The 30 s clips that cover (query - gap, query] on the release's own clip grid."""
        q = r["query_day"] * 86400 + r["query_tod"]
        return {int(k) for k in range(int((q - r["gap_s"]) // CLIP_S),
                                      int(math.ceil(q / CLIP_S)))}

    le15 = [r for r in A if r["gap_s"] <= 900.0]
    tok_rows = []
    for r in le15:
        tok, nfr = d2_tokens_for_gap(r["gap_s"])
        clips = len(clips_for(r))
        tok_rows.append(dict(qid=r["qid"], type=r["type"], gap_s=r["gap_s"],
                             d2_frames=nfr, d2_tokens=tok, clips_30s=clips,
                             need_audio=r["need_audio"], need_name=r["need_name"],
                             fits_19400=tok <= TOKEN_BUDGET,
                             fits_19381=tok <= BREAKEVEN_D132,
                             fits_32768=tok <= CONTEXT_32K))

    # item 4: clip-count disk. Dedup by absolute clip index so overlap is not double counted.
    def clip_set(rows):
        return {(r["participant"], k) for r in rows for k in clips_for(r)}

    # the D139 decision rule
    usable = [t for t in tok_rows
              if t["gap_s"] > 120.0 and t["fits_19400"]
              and not t["need_audio"] and not t["need_name"]]
    usable_rows = [r for r in le15 if r["qid"] in {u["qid"] for u in usable}]

    # Sensitivity: an UPPER BOUND on the usable count if every excluded multi-target row were
    # repaired in the most favourable way (nearest target, same day only). Constructed bound,
    # not an observation: it does not claim those rows are same-day or well formed.
    def best_case_gap(rec):
        raw = rec["_raw"]
        qd, td = day_index(raw["query"].get("date")), day_index(raw["target"].get("date"))
        if qd is None or td is None or qd != td:
            return None
        blob = str(raw["target"].get("time") or "") + "".join(raw["target"].get("time_list") or [])
        stamps = [m for m in re.findall(r"\d{8}", re.sub(r"DAY\d+_", "", blob))]
        if not stamps:
            return None
        qtod = tod_seconds(raw["query"]["time"])
        cands = [qtod - tod_seconds(s) for s in stamps]
        cands = [c for c in cands if c > 120.0]
        return min(cands) if cands else None

    bound_extra = 0
    for rec in buckets["time_list"] + buckets["malformed"]:
        g = best_case_gap(rec)
        if g is None or rec["need_audio"] or rec["need_name"]:
            continue
        if d2_tokens_for_gap(g)[0] <= TOKEN_BUDGET:
            bound_extra += 1

    max_gap_19400 = (TOKEN_BUDGET - DS.D2_HEADER_TOK) / DS.D2_TOK_PER_IMG * DS.D2_STRIDE_S
    max_gap_32768 = (CONTEXT_32K - DS.D2_HEADER_TOK) / DS.D2_TOK_PER_IMG * DS.D2_STRIDE_S

    out = dict(
        coverage=dict(
            note="every row lands in exactly one bucket; the four counts sum to rows_read",
            rows_read=total_read,
            participants_published=sorted({r["participant"] for v in buckets.values()
                                           for r in v}),
            participants_in_benchmark=6,
            questions_in_benchmark_paper=3000,
            analysis_set=len(A),
            excluded_time_list=len(buckets["time_list"]),
            excluded_cross_day=len(buckets["cross_day"]),
            excluded_malformed=len(buckets["malformed"]),
            analysis_set_share_of_rows_read=round(len(A) / total_read, 4),
            malformed_reasons=dict(collections.Counter(r.get("reason")
                                                       for r in buckets["malformed"])),
            malformed_ids=[r["qid"] for r in buckets["malformed"]],
            malformed_examples=[r["_raw"]["target"] for r in buckets["malformed"][:3]],
            time_list_n_targets=dict(collections.Counter(r["n_targets"]
                                                         for r in buckets["time_list"])),
            cross_day_wallclock_gap_median_s=(
                st.median([r["gap_s_wallclock"] for r in buckets["cross_day"]])
                if buckets["cross_day"] else None),
            date_case_anomalies=sum(1 for v in buckets.values() for r in v
                                    if r.get("date_case_anomaly")),
        ),
        gap=dict(
            definition="query_time minus target_time, SAME DAY SINGLE TARGET ONLY; "
                       "HHMMSSff with ff dropped, so 1 s resolution",
            denominator=len(A),
            bins=dict(collections.Counter(bin_of(g) for g in gaps)),
            bin_edges_s={n: [lo, hi] for n, lo, hi in GAP_BINS},
            min_s=min(gaps), p25_s=st.quantiles(gaps, n=4)[0], median_s=st.median(gaps),
            p75_s=st.quantiles(gaps, n=4)[2], max_s=max(gaps),
        ),
        by_type=dict(denominator=len(A),
                     totals=dict(collections.Counter(r["type"] for r in A)),
                     bins={k: dict(v) for k, v in cat_bin.items()}),
        by_flag=dict(need_audio=flag_split(A, "need_audio"),
                     need_name=flag_split(A, "need_name"),
                     joint=dict(denominator=len(A), counts={
                         f"audio={a} name={n}": sum(1 for r in A
                                                    if r["need_audio"] == a
                                                    and r["need_name"] == n)
                         for a in (False, True) for n in (False, True)})),
        tokens=dict(
            source="experiments/orchestration/live2/fleet/data_sources.py d2_batch_tokens",
            d2_tok_per_img=DS.D2_TOK_PER_IMG, d2_stride_s=DS.D2_STRIDE_S,
            d2_header_tok=DS.D2_HEADER_TOK,
            denominator_le15min=len(le15),
            fits_19400=sum(t["fits_19400"] for t in tok_rows),
            fits_19381_breakeven=sum(t["fits_19381"] for t in tok_rows),
            fits_32768=sum(t["fits_32768"] for t in tok_rows),
            max_gap_s_under_19400=max_gap_19400,
            max_gap_s_under_32768=max_gap_32768,
            tokens_min=min(t["d2_tokens"] for t in tok_rows),
            tokens_median=st.median([t["d2_tokens"] for t in tok_rows]),
            tokens_max=max(t["d2_tokens"] for t in tok_rows),
            tokens_at_900s=d2_tokens_for_gap(900.0)[0],
            per_question=tok_rows,
        ),
        disk=dict(
            clip_s=CLIP_S, clip_mb=args.clip_mb,
            basis="the brief's 14.5 MB per 30 s clip; implies "
                  f"{args.clip_mb * 1e6 / CLIP_S / 1e3:.0f} kB/s",
            le15min=dict(denominator=len(le15),
                         clips_sum=sum(t["clips_30s"] for t in tok_rows),
                         clips_dedup=len(clip_set(le15)),
                         gb_sum=sum(t["clips_30s"] for t in tok_rows) * args.clip_mb / 1e3,
                         gb_dedup=len(clip_set(le15)) * args.clip_mb / 1e3),
            usable=dict(denominator=len(usable_rows),
                        clips_sum=sum(u["clips_30s"] for u in usable),
                        clips_dedup=len(clip_set(usable_rows)),
                        gb_sum=sum(u["clips_30s"] for u in usable) * args.clip_mb / 1e3,
                        gb_dedup=len(clip_set(usable_rows)) * args.clip_mb / 1e3),
        ),
        decision_rule=dict(
            rule="gap > 2 min AND d2_tokens <= 19,400 AND need_audio false AND "
                 "need_name false, over the same-day single-target analysis set",
            implied_gap_window_s=[120.0, max_gap_19400],
            denominator_analysis_set=len(A),
            denominator_le15min=len(le15),
            usable_count=len(usable),
            threshold=50,
            verdict=("OFFLINE CORROBORATION ONLY" if len(usable) < 50
                     else "CAN SUPPORT A TRACE-DRIVEN WORKLOAD"),
            attrition=dict(
                analysis_set=len(A),
                after_gap_gt_120s=sum(1 for r in A if r["gap_s"] > 120.0),
                after_tokens_le_19400=sum(1 for t in tok_rows
                                          if t["gap_s"] > 120.0 and t["fits_19400"]),
                after_no_audio=sum(1 for t in tok_rows
                                   if t["gap_s"] > 120.0 and t["fits_19400"]
                                   and not t["need_audio"]),
                after_no_name=len(usable),
            ),
            usable_by_type=dict(collections.Counter(u["type"] for u in usable)),
            usable_ids=[u["qid"] for u in usable],
            counterfactual_under_32768=sum(
                1 for t in tok_rows if t["gap_s"] > 120.0 and t["fits_32768"]
                and not t["need_audio"] and not t["need_name"]),
            upper_bound_if_excluded_rows_repaired=len(usable) + bound_extra,
            upper_bound_extra_from_excluded=bound_extra,
            upper_bound_still_under_threshold=(len(usable) + bound_extra) < 50,
        ),
        sember=sember_block(),
    )
    if args.hf_meta:
        m = json.load(open(args.hf_meta))
        sib = [s["rfilename"] for s in m.get("siblings", [])]
        out["release"] = dict(
            repo=m["id"], sha=m["sha"], last_modified=m["lastModified"],
            gated=m["gated"], private=m["private"], disabled=m["disabled"],
            license_tags=[t for t in m.get("tags", []) if t.startswith("license:")],
            tags=m.get("tags", []), used_storage_bytes=m.get("usedStorage"),
            n_files=len(sib),
            ext_counts=dict(collections.Counter(f.rsplit(".", 1)[-1] for f in sib)),
            egolifeqa_files=[f for f in sib if f.startswith("EgoLifeQA/")],
        )
    for v in buckets.values():
        for r in v:
            r.pop("_raw", None)
    out["_provenance"] = stamp(script="egolife_feasibility.py", model="none",
                               device=None, n=total_read, args=args)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str))
    slim = {k: v for k, v in out.items() if k != "tokens"}
    slim["tokens"] = {k: v for k, v in out["tokens"].items() if k != "per_question"}
    print(json.dumps(slim, indent=1, default=str))


if __name__ == "__main__":
    main()
