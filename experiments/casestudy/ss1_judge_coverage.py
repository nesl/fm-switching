"""Is the judge's unparsed set MISSING AT RANDOM, or enriched in borderline answers?

D142. The parse failure is the JUDGE failing to emit a readable rating, not the answering model
failing. So it plausibly concentrates where the rating is least certain - ambiguous, partial or
strange answers. If so, dropping the unparsed set conditions the comparison on both judgements
having been clean, and if the two columns' unparsed sets differ in SIZE and are DISJOINT, the two
columns were filtered with different strictness on an outcome-correlated variable. That is a bias
rather than noise and its direction is unknown a priori.

The yardstick is CONTAINMENT, because it is computable for every question whether or not the judge
produced a rating. That is what makes the excluded set characterisable rather than merely counted.

Reports, per side and for the pair:
  * unparsed rate;
  * whether the two unparsed sets OVERLAP (same questions failing leaves the paired set intact;
    disjoint failures shrink it twice over);
  * containment mean on the UNPARSED set against the PARSED set, which says whether the exclusion
    sits at the easy or the hard end;
  * judge mean on each side's own parsed set against the paired intersection, which measures what
    the pairing filter does to the reported quantity;
  * the dimension distribution of the unparsed questions.
"""
from __future__ import annotations
import argparse, json, math, statistics
from collections import Counter
from pathlib import Path


def wilson(k, n, z=1.959963985):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - h) / d, 4), round((c + h) / d, 4))


def side(jf):
    j = json.loads(Path(jf).read_text())
    rows = j["rows"]
    parsed = {r["qid"]: r for r in rows if r.get("judge_rating") is not None}
    unparsed = {r["qid"]: r for r in rows if r.get("judge_rating") is None}
    return j, rows, parsed, unparsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device-judge", required=True)
    ap.add_argument("--cloud-judge", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    dj, drows, dpar, dun = side(a.device_judge)
    cj, crows, cpar, cun = side(a.cloud_judge)

    def block(name, rows, par, un):
        cp = [float(r["containment"]) for r in rows if r.get("containment") is not None
              and r["qid"] in par]
        cu = [float(r["containment"]) for r in rows if r.get("containment") is not None
              and r["qid"] in un]
        return dict(
            n=len(rows), n_parsed=len(par), n_unparsed=len(un),
            unparsed_rate=round(len(un) / len(rows), 5),
            unparsed_rate_ci95=wilson(len(un), len(rows)),
            containment_mean_parsed=(round(statistics.fmean(cp), 4) if cp else None),
            containment_mean_unparsed=(round(statistics.fmean(cu), 4) if cu else None),
            containment_gap_unparsed_minus_parsed=(
                round(statistics.fmean(cu) - statistics.fmean(cp), 4) if cp and cu else None),
            judge_mean_own_parsed=(round(statistics.fmean(
                float(r["judge_rating"]) for r in par.values()), 4) if par else None),
            unparsed_by_dimension=dict(Counter(r.get("dimension") for r in un.values())))

    inter = sorted(set(dpar) & set(cpar))
    out = dict(
        study="StudySS1", pass_="judge_coverage_and_missingness",
        device=block("device", drows, dpar, dun),
        cloud=block("cloud", crows, cpar, cun),
        overlap=dict(
            n_unparsed_device=len(dun), n_unparsed_cloud=len(cun),
            n_intersection=len(set(dun) & set(cun)),
            n_union=len(set(dun) | set(cun)),
            disjoint=(len(set(dun) & set(cun)) == 0),
            reading=("same questions failing on both sides leaves the paired set intact; disjoint "
                     "failures remove the union and shrink it twice over.")),
        paired=dict(
            n_paired_parsed=len(inter),
            judge_mean_device_on_pair=(round(statistics.fmean(
                float(dpar[q]["judge_rating"]) for q in inter), 4) if inter else None),
            judge_mean_cloud_on_pair=(round(statistics.fmean(
                float(cpar[q]["judge_rating"]) for q in inter), 4) if inter else None),
            filter_effect_note=("compare each side's judge_mean_own_parsed against its mean on the "
                                "pair. A shift means the pairing filter is not neutral on the "
                                "reported quantity.")),
    )
    dshift = (out["paired"]["judge_mean_device_on_pair"] or 0) - (out["device"]["judge_mean_own_parsed"] or 0)
    cshift = (out["paired"]["judge_mean_cloud_on_pair"] or 0) - (out["cloud"]["judge_mean_own_parsed"] or 0)
    out["paired"]["device_shift_pair_minus_own"] = round(dshift, 4)
    out["paired"]["cloud_shift_pair_minus_own"] = round(cshift, 4)
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: out[k] for k in ("overlap", "paired")}, indent=1))
    for s in ("device", "cloud"):
        b = out[s]
        print("%-7s unparsed %d/%d (%.3f%%)  containment parsed %.4f vs unparsed %s  gap %s" % (
            s, b["n_unparsed"], b["n"], 100 * b["unparsed_rate"],
            b["containment_mean_parsed"], b["containment_mean_unparsed"],
            b["containment_gap_unparsed_minus_parsed"]))


if __name__ == "__main__":
    main()
