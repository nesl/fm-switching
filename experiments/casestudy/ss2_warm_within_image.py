"""Was the repeated-image set served WARM, and on which tier?

The exclusion lists mark questions whose image CONTENT repeats an earlier image in run order. The
cloud's own counters confirm the hits (RefSpatial 186 of 186), so the cloud side is settled. The
DEVICE file instead DECLARES "distinct image+task per request so no warm reuse; cold single-shot",
and a declaration is not an observation. The per-request cache_salt isolates the TEXT prefix cache;
the multimodal encoder cache is keyed by image CONTENT, which no salt touches.

The test holds composition fixed rather than arguing about it: WITHIN each group of questions on one
image, compare the FIRST occurrence in run order against the LATER ones. Same image, so the same
pixel area and nearly the same prompt tokens; the only difference is whether an earlier request had
already encoded that image. A between-subsets comparison cannot do this, because the repeat set and
the clean set differ in image-size composition.
"""
import argparse
import json
import statistics as st
from pathlib import Path


def p(vals, q):
    v = sorted(vals)
    return round(v[min(int(q * len(v)), len(v) - 1)], 4)


def block(rows, qids, key="ttft_s"):
    v = [rows[q][key] for q in qids if rows[q].get(key) is not None]
    if not v:
        return None
    return dict(n=len(v), p50=round(st.median(v), 4), p90=p(v, 0.9),
                mean=round(st.fmean(v), 4), min=round(min(v), 4), max=round(max(v), 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--cloud", required=True)
    ap.add_argument("--shared-images", required=True)
    ap.add_argument("--manifest", required=True, help="run order, which decides first versus later")
    ap.add_argument("--image-dims", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    D = {r["qid"]: r for r in json.loads(Path(a.device).read_text())["rows"] if "error" not in r}
    C = {r["qid"]: r for r in json.loads(Path(a.cloud).read_text())["rows"] if "error" not in r}
    sh = json.loads(Path(a.shared_images).read_text())
    order = [json.loads(l)["qid"] for l in Path(a.manifest).read_text().splitlines() if l.strip()]
    pos = {q: i for i, q in enumerate(order)}
    dims = {}
    for l in Path(a.image_dims).read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            dims[r["qid"]] = int(r["area"])

    first, later = [], []
    for g in sh["groups"]:
        qs = sorted(g, key=lambda q: pos[q])
        first.append(qs[0])
        later.extend(qs[1:])
    on_shared = set(first) | set(later)
    never = [q for q in order if q not in on_shared]

    def comp(qids):
        return dict(n=len(qids),
                    area_p50=int(st.median([dims[q] for q in qids])) if qids else None,
                    device_prompt_tokens_p50=(int(st.median([D[q]["prompt_tokens"] for q in qids]))
                                              if qids else None),
                    device_completion_tokens_p50=(int(st.median([D[q]["completion_tokens"]
                                                                 for q in qids])) if qids else None))

    groups = dict(
        first_occurrence_cold=dict(composition=comp(first),
                                   device_ttft=block(D, first), cloud_ttft=block(C, first)),
        later_occurrence_warm=dict(composition=comp(later),
                                   device_ttft=block(D, later), cloud_ttft=block(C, later)),
        never_on_a_shared_image=dict(composition=comp(never),
                                     device_ttft=block(D, never), cloud_ttft=block(C, never)),
        cold_baseline_first_plus_never=dict(composition=comp(first + never),
                                            device_ttft=block(D, first + never),
                                            cloud_ttft=block(C, first + never)))

    def ratio(tier):
        f = groups["first_occurrence_cold"][tier]["p50"]
        w = groups["later_occurrence_warm"][tier]["p50"]
        return dict(cold_p50=f, warm_p50=w, warm_over_cold=round(w / f, 4),
                    pct_faster_when_warm=round(100.0 * (1 - w / f), 1))

    out = dict(
        study=json.loads(Path(a.device).read_text()).get("study"),
        dataset=json.loads(Path(a.device).read_text()).get("dataset"),
        question=("within one image, is a later request faster than the first? If yes on a tier, "
                  "that tier served the repeat warm, whatever its caching string says."),
        design=("WITHIN-IMAGE. The two compared sets are questions on the SAME images, so pixel "
                "area and prompt tokens are held fixed and the composition block below shows it. "
                "This is the control the between-subsets comparison lacks."),
        n_shared_images=len(sh["groups"]),
        groups=groups,
        device=ratio("device_ttft"),
        cloud=ratio("cloud_ttft"),
        device_declared_caching=json.loads(Path(a.device).read_text()).get("caching"),
        cloud_observed_mm_hits=(((json.loads(Path(a.cloud).read_text()).get("cache_check") or {})
                                 .get("server_counters_parsed") or {}).get("mm_cache_hits")),
        register="OBSERVED, within-image, both tiers. Not a controlled rerun: no cold repeat of the "
                 "same questions was run, so this is an observational inference from run order, "
                 "with composition held fixed rather than adjusted for.",
    )
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print("wrote", a.out)
    for tier in ("device", "cloud"):
        r = out[tier]
        print("  %-7s cold p50 %.4f -> warm p50 %.4f (%.1f%% faster warm)"
              % (tier, r["cold_p50"], r["warm_p50"], r["pct_faster_when_warm"]))


if __name__ == "__main__":
    main()
