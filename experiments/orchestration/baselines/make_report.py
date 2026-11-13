#!/usr/bin/env python3
"""Generate reports/study_b_baselines.md from the registry and the smoke results.

StudyB-baselines. Every row is read from registry.yaml, smoke/smoke_results.json or
smoke/originals_smoke.json; nothing about what was built is hand-typed here.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
B = Path(__file__).resolve().parent
REG = B / "registry.yaml"
RES = ROOT / "results/orchestration/study_b_baselines"
SM = json.loads((RES / "b_smoke_results.json").read_text())
ORIG = json.loads((RES / "b_originals_smoke.json").read_text())
L = []


def w(s=""):
    L.append(s)


def parse_registry():
    """Minimal reader so the report does not depend on pyyaml being installed."""
    rows, cur, key = [], None, None
    for ln in REG.read_text().splitlines():
        if ln.startswith("  - name:"):
            cur = dict(name=json.loads(ln.split("name:", 1)[1].strip()))
            rows.append(cur)
            key = None
        elif cur is not None and ln.startswith("    ") and ":" in ln and not ln.strip().startswith("-"):
            k, _, v = ln.strip().partition(":")
            v = v.strip()
            key = k
            if v == "":
                cur[k] = []
            elif v == "[]":
                cur[k] = []
            elif v == "null":
                cur[k] = None
            else:
                try:
                    cur[k] = json.loads(v)
                except Exception:
                    cur[k] = v
        elif cur is not None and ln.strip().startswith("- ") and key:
            cur.setdefault(key, [])
            if isinstance(cur[key], list):
                try:
                    cur[key].append(json.loads(ln.strip()[2:]))
                except Exception:
                    cur[key].append(ln.strip()[2:])
    return rows


ROWS = parse_registry()
BY = {r["name"]: r for r in ROWS}

# ---- related-work-only entries: verified id, and the one-line reason they are not baselines.
RELATED = [
    ("Chameleon", "SIGCOMM 2018", "verified (OpenAlex)",
     "picks video-analytics configurations by exploiting temporal correlation across cameras; it "
     "tunes a pipeline's knobs, not the device/cloud placement of a standing query."),
    ("Reducto", "SIGCOMM 2020", "verified (OpenAlex)",
     "on-camera frame filtering decides WHICH frames to send; our cadence and frame-count knobs "
     "already cover that axis and it makes no serving decision."),
    ("DDS (Server-Driven Video Streaming)", "SIGCOMM 2020", "verified (OpenAlex)",
     "a server-driven two-pass video codec loop for DNN inference; it optimises the encode, not "
     "scheduling or admission."),
    ("Nexus", "SOSP 2019", "verified (OpenAlex)",
     "GPU cluster scheduling for batched DNN video analysis; no stateful sessions and no "
     "device tier, so it cannot express our recall decisions."),
    ("Shepherd", "NSDI 2023", "verified (USENIX page: Zhang, Tang, Khandelwal, Stoica)",
     "serving-layer preemption and batching over request streams; its planning layer aggregates "
     "streams for predictability rather than choosing a tier."),
    ("VTC (Fairness in Serving LLMs)", "OSDI 2024 (arXiv 2023 record verified)",
     "partly verified - OpenAlex found the preprint, not the OSDI record",
     "a fairness scheduler among tenants; our evaluation has one tenant, so its objective is "
     "undefined here."),
    ("Sarathi-Serve", "OSDI 2024 (arXiv 2024 record verified)",
     "partly verified - preprint only", "chunked-prefill scheduling INSIDE one engine; it is an "
     "engine lever, already covered by the tuned-engine baseline's E2 configuration."),
    ("DistServe", "OSDI 2024 (arXiv 2024 record verified)", "partly verified - preprint only",
     "prefill/decode disaggregation across GPUs; we have one replica and our costs are "
     "prefill-dominated, so there is nothing to disaggregate."),
    ("Splitwise", "ISCA 2024", "verified (OpenAlex, DOI 10.1109/ISCA59077.2024.00019)",
     "phase splitting across machine pools; a cluster-provisioning decision, not a per-request "
     "placement one."),
    ("EPD disaggregation", "arXiv:2501.05460 (2024-12-25)", "verified (arXiv API)",
     "encode/prefill/decode disaggregation for multimodal serving; same reason as DistServe, and "
     "StudyE10d showed the LM prefill is the unsplittable unit on our hardware."),
    ("Llumnix", "OSDI 2024 (arXiv 2024 record verified)", "partly verified - preprint only",
     "live migration of requests between instances for load balancing; one replica here."),
    ("Symphony", "arXiv 2023", "verified (OpenAlex)",
     "deferred batch scheduling for DNN serving; a batching policy, and our action space has no "
     "batch dimension."),
    ("CoSense-LLM", "arXiv 2025", "verified (OpenAlex)",
     "semantic edge-cloud compression for sensing; it decides what semantics to send, which our "
     "representation set already fixes to measured options."),
    ("EdgeCoInfer", "arXiv 2026", "verified (OpenAlex)",
     "hierarchical collaborative inference by model partitioning; FORMULATION scopes out "
     "splitting one model across tiers."),
    ("StreamScout", "arXiv 2026", "verified (OpenAlex)",
     "learns when to look deeper in a stream; closest to R3-Streaming's Reason stage, which is "
     "already a built baseline."),
    ("VLMCache", "MobiSys 2026", "verified (OpenAlex)",
     "on-device VLM caching; a device-side mechanism, not a placement or admission policy."),
    ("Pallas", "arXiv:2608.16477 (2026-08-17)", "verified (arXiv API)",
     "proactive KV cache MIGRATION between serving nodes; one replica here, so migration has no "
     "destination."),
    ("ctHO", "arXiv:2603.28018 (2026-03-30)", "verified (arXiv API)",
     "edge LLM handover with joint KV transfer; a mobility/handover mechanism, and StudyE6b "
     "already covers our mobility question."),
    ("llm-d", "software, not a paper (user decision 2026-11-12)",
     "cited as software - `github.com/llm-d/llm-d`",
     "a Kubernetes-native distributed inference stack; infrastructure rather than a published "
     "policy we can reconstruct, and cited as software per the user's instruction."),
    ("CacheRoute", "DROPPED (no identifier)", "dropped - user decision 2026-11-12",
     "a cache-aware router; no identifier could be found, so it is dropped rather than cited."),
    ("MSAO", "arXiv:2604.02945 (2026-04)", "verified (arXiv API, id supplied by the user)",
     "multi-server adaptive offloading; a multi-server provisioning/offloading problem, while we "
     "have one cloud replica and a fixed device."),
    ("AceSpec", "arXiv:2609.02514 (2026-09)", "verified (arXiv API, id supplied by the user)",
     "speculative decoding; a decode-time accelerator, orthogonal to placement, and our costs "
     "are prefill-dominated (StudyE10d)."),
    ("Splitwise-DRL", "arXiv:2512.23310 (2025-12)", "verified (arXiv API, id supplied by the "
     "user) - NOTE: a DIFFERENT Splitwise from ISCA'24 (its title is \"Splitwise: Collaborative "
     "Edge-Cloud Inference for LLMs via Lya...\")",
     "collaborative edge-cloud inference chosen by a learned controller; the closest related "
     "work in this list, and the reason B9 exists - but it decides a split point inside the "
     "model, which FORMULATION scopes out, so it cannot be expressed in our action space."),
    ("SpotVLM / edgeVLM", "arXiv:2508.12638 (2025-08)",
     "verified (arXiv API, id supplied by the user)",
     "on-device VLM execution; a device-side runtime, not a placement or admission policy."),
    ("SAIL", "MobiSys 2026, DOI 10.1145/3745756.3809224",
     "verified (Crossref, DOI supplied by the user)",
     "an on-device VLM system rather than a scheduler; same reason as VLMCache, which is from the "
     "same venue and already listed above."),
    ("HERMES", "ACL 2026, anthology `2026.acl-long.381` (pp. 8411-8430)",
     "verified (ACL Anthology, id supplied by the user)",
     "\"KV Cache as Hierarchical Memory for Efficient Streaming Video Understanding\" - it "
     "restructures the KV cache INSIDE one model, which our action space cannot express (the "
     "R3-Streaming limitation, `cards/r3streaming.md` A1)."),
    ("QueryStream", "ICLR 2026 poster, OpenReview `738HjJEbml`",
     "verified (ICLR virtual site, id resolved from the poster page) - **VERIFIED, NOT BUILT**",
     "requested as a P1 component baseline. Verified, but its gating component (RTAR) is named "
     "and neither defined nor released, so building it would mean inventing the trigger - see "
     "section 9.1 for the missing component."),
    ("Route2Look", "DROPPED (does not appear to exist)",
     "**NOT FOUND** (OpenAlex; title, venue, id and authors all unresolvable) - dropped per the "
     "user's instruction 2026-11-12", "nothing was built; nothing else was done."),
    ("Fairway", "DROPPED (does not appear to exist)",
     "**NOT FOUND** (OpenAlex; title, venue, id and authors all unresolvable) - dropped per the "
     "user's instruction 2026-11-12", "nothing was built; nothing else was done."),
]

NAIVE = [r for r in ROWS if r["case"] == "naive"]
SHORT = [r for r in ROWS if r["case"] in ("A", "B", "C", "D", "own")]
BORDER = [r for r in ROWS if "NOT built" in str(r.get("case")) or "related-work only" in str(r.get("case"))]

w("# StudyB-baselines: the baseline suite for the scheduler evaluation")
w()
w("E-id: StudyB-baselines (`research/EXPERIMENTS.md`). **This is an engineering and literature "
  "task. It runs no experiment and makes no performance claim, and no two baselines are compared "
  "anywhere in it.** CPU only on the flash host: no GPU, no model server, no inference. The "
  "network was used only to search for papers, clone public repositories and pip-install into a "
  "throwaway venv; third-party code lives **outside this repository** in `~/baselines_src/` and "
  "is never vendored into it.")
w()
w("## 0. Three things to read before the tables")
w()
w("**(a) The tuned engine: DECIDED 2026-11-12 - it is StudyE10e's P1.** This baseline was specified as \"the best engine configuration from StudyE10c / "
  "E10e\". When the suite was first built **StudyE10e did not exist**, so it was flagged as "
  "under-specified. StudyE10e has since run and tested exactly the missing lever - the "
  "long-prefill threshold - and its pre-registered verdict is **\"no config removes the "
  "interference\"**: P1 (threshold 1024), P2 (512) and P3 (1024 + priority) each hold C0 capacity "
  "at the 40 % ladder top with no loss, exactly like the default, and each collapses to **< 10 %** "
  "under cold recall (C1) and under KV-host-plus-cold-recall (C4) - five ladder levels below "
  "their own C0. **And under recall they are strictly worse than the default**: the caps do cut "
  "episodic p99 at C1 (2.646 s -> 1.978 s at P2, about -25 %) but never approach the 0.45 s "
  "budget, while charging cold-recall TTFT p99 +12-13 % at C1 and +14-21 % at C4, and degrading "
  "warm recall at C4 (P2 appends / escalations +37 % / +30 %; P3 escalation x2.1, because "
  "priority demotes warm recall). StudyE10e also records that the two partial-prefill counters "
  "originally requested do not exist in vLLM 0.31.0. So `tuned_engine.py` now exposes all SEVEN "
  "measured configurations - E10c's E0 / E1 / E2 / E4 and E10e's P1 / P2 / P3 - keeps "
  "`BEST_MEASURED = E0` with a measurement rather than an absence behind it, and still raises on "
  "any unmeasured name. **The user set `TUNED = P1`** (`--long-prefill-token-threshold 1024`, "
  "default step budget, FCFS) on that evidence, and the choice is well founded: P1 cuts episodic "
  "p99 by 19-25 % at C1 and 18-30 % at C4 at **no C0 capacity cost**, and **alone among the three "
  "it spares warm recall** - at C4 its warm append p50 rises x1.02 and its escalation x1.01, "
  "against P2's x1.37 / x1.30 and P3's x1.53 / x2.09. Its cost is confined to cold recall (TTFT "
  "p99 x1.12 at C1, x1.14 at C4). `TUNED = P1` and `BEST_MEASURED = E0` are kept as two separate "
  "recorded senses - the tuned choice, and the best under E10c / E10e's capacity rule - so they "
  "are never conflated, and **it does not restore capacity**: E10e's verdict stands and is quoted "
  "in `cards/tuned_engine.md`. One caveat is carried from E10e: its verdict covers its own "
  "controls plus E10c's, not two documented 0.31.0 combinations it did not try (a 2,048-token "
  "step budget together with the 512-token cap, and `--no-async-scheduling`).")
w()
w("One consequence of the switch, stated so no one reads more into it than it says: the 10-minute "
  "replay smoke test was re-run under `TUNED = P1` and **every recorded field of all 38 "
  "configurations then in the suite is unchanged** (only wall-clock times differ). That is expected and is not "
  "evidence for P1 - the replay harness charges no engine-configuration cost, so `engine_config` "
  "is a field the policy emits and the harness validates but does not price. P1's benefit and its "
  "cold-recall cost live in StudyE10e's measured latency curves, not in this replay; any study "
  "that wants to see them must charge them.")
w()
w("**(b) Ekya's repository has no licence.** `github.com/edge-video-services/ekya` is Microsoft "
  "Research's own release, but it contains **no LICENSE or COPYING file anywhere** and the README "
  "names none, so no right to use or modify is granted. Applied consequence: the clone is used "
  "for citation and commit pinning only, **no file in it was opened, run or copied**, its own "
  "CPU-runnable toy simulator was deliberately left unrun, and the adapted baseline was written "
  "from the paper. **RESOLVED 2026-11-12: the user approved citation-only use** (section 9 "
  "item 2); the clone and the pin stay, and nothing in it is opened.")
w()
w("**(c) StudyRH8's winning policy reads labels - the resolution below was approved "
  "2026-11-12 (section 9 item 3).** RH8's MIX-DEMAND keeps warm \"exactly the "
  "high-demand devices\" - in the code, the same `random.Random(0).sample(...)` draw that "
  "*assigned* the synthetic demand. RH8's own 2026-11-03 audit says this \"does not show that "
  "demand can be *predicted*\". Our interface forbids a policy from reading labels, so rather "
  "than invent a hybrid, **both readings ship and are labelled**: `RH8OracleDemand` (an upper "
  "bound, excluded from the causality check, reported like the hindsight oracle) and "
  "`RH8CausalDemand` (deployable, but **not** what StudyRH8 measured).")
w()

w("## 1. The policy interface")
w()
w("Defined first, in `experiments/orchestration/baselines/interface.py`, before any baseline. It "
  "is enforced, not merely documented:")
w()
w("- **Causal observations only.** `Observation` is frozen and the fields that could leak the "
  "future are absent; `scrub()` additionally asserts that no field or dict key named in "
  "`FORBIDDEN_FIELDS` (17 of them: labels, correctness, `time_of_event`, future arrivals, oracle "
  "values, ...) reached the policy. It runs on **every** epoch via `Policy.__call__`.")
w("- **Two actions added by the 2026-11-12 amendment**, both validated like the rest: "
  "`MATERIALIZE(session, target_tokens, slice_tokens)` - the explicit act of BUILDING a session's "
  "cloud-side state, as against `KEEP_GPU_WARM`, which only holds state that exists - and "
  "per-stream `SUSPEND_UNTIL(t)`, which issues no cloud call until *t* while the application reads "
  "the device's own scores. `slice_tokens = None` means one monolithic prefill. See section 13.")
w("- **One action space.** `validate_action` rejects a cadence outside {0.25, 0.5, 1.0} s, a "
  "frame count outside {1, 3}, an unknown representation or session action, a negative defer, or "
  "an action naming an entity the observation did not contain - which is how a policy would "
  "smuggle in knowledge of the future.")
w("- **One set of defaults.** A baseline that decides only part of the space leaves the rest "
  "`None` and `apply_defaults` fills it from `DEFAULTS`, *identically for every baseline*: cloud "
  "N = 1 at c = 0.5 s, recall on cloud with RECENT, LRU host offload, FCFS order, default "
  "engine. Each card lists which defaults its baseline relies on.")
w("- **One budget.** `Budget` is checked by the harness, not the policy, so no baseline can award "
  "itself more cloud work than our scheduler gets.")
w()
w("Supporting modules, all reading committed measurements and nothing else: `costs.py` (StudyD4 / "
  "D7 / D7b / D8 / RH5 / E10b / E10d constants, re-exported from `study_e9_episodes.py` so there "
  "is one copy per constant in the repo), `profiles.py` (the resource-quality profile from "
  "StudyE9b / E9c), `devsplit.py` (**StudyD3's development clips** - the only place a "
  "hyperparameter may be fitted; StudyD14 / D14b are the validation clips and are never fitted "
  "on).")
w()
w(f"One interpolation rule is stated rather than measured: `costs.recall_ttft_s` interpolates "
  f"linearly in tokens between StudyRH5's 11k and 28k points for the warm states and uses the "
  f"measured cold prefill rate for COLD. Every card that relies on it says so.")
w()

w("## 2. The four cases, as decided")
w()
w("\"Code exists\" means an official or author-endorsed public repository. A third-party "
  "reimplementation counts only if the paper's authors link it; otherwise it is treated as no "
  "code and the search is recorded.")
w()
w("| case | meaning | count |")
w("|---|---|---|")
for c, m in (("A", "code exists and runs in our setting; wrapped, decision logic untouched"),
             ("B", "code exists but needs adaptation; ORIGINAL (pinned) + ADAPTED both kept"),
             ("C", "no code; faithful reconstruction, usable unchanged"),
             ("D", "no code and needs adaptation; reconstruction + adapted both kept")):
    n = sum(1 for r in ROWS if r["case"] == c)
    w(f"| **{c}** | {m} | {n} |")
w(f"| naive | implemented directly behind the interface | {len(NAIVE)} |")
w(f"| own | our own measured configuration, not an external paper | "
  f"{sum(1 for r in ROWS if r['case'] == 'own')} |")
w()
w("No candidate came out as case C: every paper without code also needed adaptation, because our "
  "action space (two tiers, three representations, a standing video query plus a stateful recall "
  "session) differs from every paper's.")
w()

w("## 3. Naive baselines")
w()
w("| name | what it decides | file |")
w("|---|---|---|")
for r in NAIVE:
    w(f"| `{r['name']}` | {r.get('decides','-')} | `{r['files'][0]}` |")
w()
w("`hindsight-oracle` is an **upper bound, not a policy**: the interface forbids future "
  "information in the observation, so the harness injects the realised trace through the "
  "constructor, the class declares `reads_future = True`, and the causality check excludes it. "
  "The same mechanism carries `RH8OracleDemand`.")
w()

w("## 4. Shortlist: case decision, evidence, versions built")
w()
w("| baseline | paper (verified) | code | case | versions | card |")
w("|---|---|---|---|---|---|")
for r in SHORT:
    code = r.get("code_url") or "-"
    if code and code.startswith("http"):
        code = f"`{code.split(' ; ')[0]}`" + (" +1" if " ; " in str(r.get("code_url")) else "")
    pc = r.get("pinned_commit")
    code = code + (f"<br>@`{str(pc)[:12]}`" if pc else "")
    w(f"| `{r['name']}` | {r.get('paper') or '-'}<br>*{r.get('verified') or 'n/a'}* | {code} | "
      f"**{r['case']}** | {', '.join(r.get('versions') or []) or '-'} | "
      f"{('`' + r['card'] + '`') if r.get('card') else '-'} |")
w()
w("### Searches that found no code")
w()
w("For every case-D baseline the search was: the arXiv abstract page and its \"Code, Data and "
  "Media\" section; the authors' institutional and personal pages; a GitHub search by paper "
  "title and by author; and, where one exists, the publisher's project page (Microsoft Research "
  "for VideoStorm and Hybrid LLM, the USENIX page for CachedAttention, the EuroSys record for "
  "Pensieve). None links an official or author-endorsed repository. VideoStorm additionally has "
  "no third-party reimplementation that the authors link.")
w()
w("### Reconstruction toy tests")
w()
w("Each case-D reconstruction runs in **the paper's own abstract setting** and each check names "
  "the qualitative behaviour it reproduces.")
w()
w("| reconstruction | behaviours reproduced | named from the paper |")
w("|---|---|---|")
TOY = {
 "videostorm": "Eq. (2) lag accumulation; S6.1/Fig. 6 one-sided lag penalty; S6.2.2/S8.2.1 "
               "MaxMin beats an equal split on the minimum; Eq. (3) vs Eq. (4) each wins on its "
               "own objective; Eq. (3)'s capacity constraint; S6.3 score range",
 "hybrid_llm": "S3 quality gap; S3.1 vs S3.2 y^det has higher variance than y^prob; S3.3/Eq. (3) "
               "the transformation spreads labels; S3 p_w tracks Pr[H >= 0]; S4 the threshold is "
               "the cost knob; Eq. (1)/(2)/(4) BCE",
 "perllm": "S3.2 f(y) >= 0 iff feasible; Eq. (4) violations penalised and energy costs; CS-UCB "
           "optimism and bonus decay; Algorithm 1 accept-first-feasible and regret update; CMAB "
           "learning",
 "attentionstore": "S4.1/Fig. 6c load hidden behind compute; S4.1/Fig. 7a->7b a larger buffer "
                   "reduces exposed load; S4.1 async save; S4.2 fetch follows the scheduler "
                   "queue; **S4.2 eviction differs from LRU**; S4.3 decoupling survives a prefix "
                   "shift",
 "pensieve": "S4 value grows with recompute cost and with the reuse horizon; eviction fits the "
             "tier; token granularity gives partial residency; dropping costs more than swapping; "
             "AOT pipelined swap",
 "inarvl": "S3 stage (3) the 10-dimensional descriptor; stage (4) stronger model predicts more "
           "quality and dominated candidates are pruned; stage (5) easy stays on the edge, hard "
           "offloads, and the same input stays local when latency is priced high",
 "r3streaming": "S4.2/Fig. 2 nearby 1.0 vs historical 0.01 and the 95-96 % token reduction; the "
                "asymmetric schedule beats its inverse on nearby tokens; S4(ii) defers on weak "
                "evidence; S4(iii) escalates only the hardest within budget and nothing at budget "
                "0; Respond gates Reason",
}
for n, txt in TOY.items():
    r = BY.get(n.replace("_", "-")) or BY.get(n) or {}
    w(f"| `reconstructed/{n}.py` | **{r.get('toy_test','-')}** | {txt} |")
w()

w("## 5. Smoke tests")
w()
w("### 5.1 Every adapted baseline: the 10-minute replay")
w()
w("4 episodic streams (StudyD14b traces, cloud latency from StudyE9b setting (ii) at 25 % load, "
  "device at its 0.75 s saturated cadence with 0.567 s latency) and 2 recall sessions (StudyRH4 / "
  "RH5 D2 sizes 11,050 and 28,114 tokens, costs from StudyRH5 / StudyE10b), 600 s at a 0.25-s "
  "grid = 2,401 decision epochs, one shared budget of 120 GPU-seconds, one connectivity change "
  "at t = 300 s. It checks only that the policy **runs**, **respects the interface**, **stays in "
  "budget** and **never sees a forbidden field or future data**. "
  "**No performance claim; no comparison between baselines.** The GPU-seconds and recall columns "
  "are descriptive only - they show the policy did something, not that it did well, and a lower "
  "or higher number is neither better nor worse here.")
w()
w("| baseline | epochs | ran | interface | budget | GPU-s spent (of 120) | recall cloud/device/deferred | reads future |")
w("|---|---|---|---|---|---|---|---|")
for r in SM:
    rc = r.get("recall", {})
    w(f"| `{r.get('label', r['policy'])}` | {r.get('epochs','-')} | "
      f"{'PASS' if r.get('ran') else 'FAIL'} | "
      f"{'PASS' if r.get('interface_respected') else 'FAIL'} | "
      f"{'PASS' if r.get('budget_respected') else 'FAIL'} | {r.get('spent_gpu_s','-')} | "
      f"{rc.get('cloud','-')}/{rc.get('device','-')}/{rc.get('deferred','-')} | "
      f"{'YES (upper bound)' if r.get('reads_future') else 'no'} |")
w()
n_ok = sum(1 for r in SM if r.get("ran") and r.get("interface_respected")
           and r.get("budget_respected"))
w(f"**{n_ok} of {len(SM)} configurations ran, respected the interface and stayed inside the "
  f"shared budget.** Two of them (`hindsight-oracle`, `rh8-demand-aware-ORACLE`) are upper "
  f"bounds that read information the interface forbids, by construction and by declaration.")
w()
w("### 5.2 Case-B originals: what ran on CPU and what did not")
w()
w("| original | pinned commit | licence | smoke result |")
w("|---|---|---|---|")
for k, v in ORIG.items():
    res = ("**PASS** - " + v.get("what", "") if v.get("ran") else "not run - " + v.get("what", ""))
    w(f"| `{k}` | `{str(v.get('pinned_commit'))[:12]}` | {v.get('license','?')} | {res}. "
      f"{v.get('detail','')} |")
w()
w("Only FrugalGPT produced a positive CPU smoke (its own committed cascade summary parses). The "
  "rest are blocked by a GPU dependency, a build toolchain, missing data the repository does not "
  "ship, or credentials this task must not handle - each recorded with the exact blocker in "
  "`results/orchestration/study_b_baselines/b_originals_smoke.json`, and Ekya additionally by its missing licence.")
w()

w("## 6. Borderline candidates: decided, mostly not built")
w()
w("| candidate | id (verified) | case | decision and reason |")
w("|---|---|---|---|")
for r in BORDER:
    w(f"| `{r['name']}` | {r.get('paper','-')}<br>*{r.get('verified','-')}* | {r['case']} | "
      f"{r.get('notes','-')} |")
w()
w("**CoVStream is the one genuine interface conflict in this suite**, and it is reported rather "
  "than hybridised: its edge tier produces compact features *and captions* and its cloud tier "
  "maintains an *entity graph*. Our evidence inventory holds only representations we have "
  "measured ({RECENT, RICH, D2}); expressing CoVStream would mean inventing a caption/graph "
  "representation that no study of ours has built or costed. That changes what it fundamentally "
  "decides, so it is listed as related work.")
w()

w("## 7. Related work only: verified, with the one-line reason each is not a baseline")
w()
w("| work | venue / id | verification | why not a baseline |")
w("|---|---|---|---|")
for nm, vid, ver, why in RELATED:
    w(f"| {nm} | {vid} | {ver} | {why} |")
w()
unver = [nm for nm, _v, ver, _w in RELATED if "UNVERIFIED" in ver]
assert not unver, f"unexpected UNVERIFIED related-work rows: {unver}"
w("### Citations: RESOLVED 2026-11-12 - nothing in this table is unverified")
w()
w("The eight citations this section previously flagged were resolved by the user's §9 answers "
  "and then checked independently here; **none is left unverified.** What changed:")
w()
w("| work | previously | now | checked against |")
w("|---|---|---|---|")
w("| SpotVLM / edgeVLM | unverified | arXiv:2508.12638 | arXiv API |")
w("| MSAO | unverified | arXiv:2604.02945 | arXiv API |")
w("| AceSpec | unverified | arXiv:2609.02514 | arXiv API |")
w("| Splitwise-DRL | unverified | arXiv:2512.23310 | arXiv API |")
w("| SAIL | unverified (MobiSys 2026 claimed) | DOI 10.1145/3745756.3809224, MobiSys 2026 | "
  "Crossref |")
w("| HERMES | unverified (ACL 2026 claimed) | `2026.acl-long.381`, ACL 2026 pp. 8411-8430 | "
  "ACL Anthology |")
w("| QueryStream | no identifier | ICLR 2026 poster, OpenReview `738HjJEbml` | the ICLR virtual "
  "site; **verified, not built** (§9.1) |")
w("| llm-d | unverified | cited **as software**, `github.com/llm-d/llm-d` | user decision - it "
  "is a project, not a paper |")
w("| CacheRoute | unverified | **dropped** | no identifier exists; user decision |")
w("| Route2Look, Fairway | requested as candidates | **dropped, nothing built** | OpenAlex: "
  "title, venue, id and authors all unresolvable (§11) |")
w()
w("**One correction worth recording.** arXiv:2512.23310 is a *different* Splitwise from the "
  "ISCA'24 paper already in this table - its title is \"Splitwise: Collaborative Edge-Cloud "
  "Inference for LLMs via Lya...\". The two are listed as separate rows and must not be "
  "conflated: the ISCA'24 one splits prefill from decode across machine pools, the 2025 one "
  "splits one model across edge and cloud.")
w()
w("Two further partial verifications, stated plainly: OpenAlex returned the **preprint** record "
  "but not the proceedings record for VTC, Sarathi-Serve, DistServe and Llumnix. Their OSDI 2024 "
  "venues are from the publisher pages and my own reading, not from an index query in this "
  "session, so they are marked *partly verified*.")
w()

w("## 8. What a reviewer should check, and what is weakest")
w()
w("Per-baseline detail is in the cards; these are the five places where this suite is furthest "
  "from the originals, all of them consequences of our action space rather than of the papers:")
w()
w("1. **Sub-session KV granularity is not expressible.** AttentionStore manages KV *layer-wise* "
  "across three tiers and Pensieve at *token/chunk* granularity; our `session_action` is "
  "whole-session over two tiers. Both mechanisms are reconstructed and toy-tested, but the "
  "policies cannot use them. See `cards/attentionstore.md` A1 and `cards/pensieve.md` A1.")
w("2. **Hybrid LLM's three routers collapse toward one on our data.** StudyD3 has one response "
  "per (clip, offset, arm), so Eq. (2)'s 10-sample expectation is unavailable and `r_prob` / "
  "`r_trans` receive single-sample labels. See `cards/hybrid_llm.md` A6.")
w("3. **VideoStorm's profiler is not exercised.** Section 5's greedy configuration exploration "
  "needs inference; we substitute measured profiles, so only the scheduler is tested. See "
  "`cards/videostorm.md` A2.")
w("4. **INAR-VL's image signals are substituted.** We do not re-read pixels, so blur / exposure / "
  "artifact / detail become device-trajectory statistics. This baseline is \"INAR-VL's router "
  "structure on our signals\", not INAR-VL. See `cards/inarvl.md` A1.")
w("5. **Clockwork loses batching.** Our action space has no batch dimension, so §5.3's batch-size "
  "strategies and speculative growth are dropped. See `cards/clockwork.md` A4.")
w()
w("6. **The device arm is a validated-to-first-order stand-in, and StudyD15 now bounds it.** "
  "Every episodic baseline's \"device\" is StudyD14b's H100-served `4BI_N1` score, not the Orin "
  "running llama.cpp. StudyD15 Part A tested exactly that proxy and **REJECTED** it as an "
  "adequate *exact* numerical stand-in under its strict pre-registered bar (every AP-diff CI must "
  "contain 0 **and** both StudyE9 decision-rule outcomes unchanged). It is a strong first-order "
  "match - Pearson and Spearman **0.943**, trigger same-side 89.9-96.7 %, **4 of 5** streaming-AP "
  "horizons with a paired-bootstrap CI containing 0 - and where it differs (h = 0.5 s, +0.017) "
  "the **real device is slightly better, not worse**; what fails the bar is that StudyE9's "
  "decision rule 2 outcome changes. For this suite: fairness rule 1 is unaffected because every "
  "baseline uses the same arm, but **no exact device-side number may be read off these "
  "baselines**. StudyD15 Part B separately confirms that the device's held-history cost is "
  "client-side request handling of resent frames (~9.7 ms per held frame; 88 ms server "
  "prompt-eval at 480 frames with the history KV-cached), not model compute - which leaves "
  "`costs.DEV_LAT_S` (StudyD8 arm A's single-frame N = 1 total p50, 0.567 s) untouched, since "
  "that path sends one frame.")
w()
w("Two reconstruction gaps where a paper did not print something needed, each marked in its card "
  "and its module: Hybrid LLM's label-transformation closed form (§3.3 gives the objective and "
  "says `t` is grid-searched, not the function) and PerLLM's `P(t)` term (it appears in the "
  "CS-UCB figure undefined; set to zero).")
w()

w("## 9. Decisions - ALL ANSWERED 2026-11-12")
w()
w("Every question this section opened has been answered by the user. Recorded here, in the "
  "registry and in the affected cards.")
w()
w("| # | question | decision |")
w("|---|---|---|")
w("| 1 | the tuned engine | **= StudyE10e's P1** (`--long-prefill-token-threshold 1024`, default "
  "step budget, FCFS). It does not restore capacity, but it cuts episodic p99 19-25 % at C1 and "
  "18-30 % at C4 at no C0 capacity cost and alone among P1/P2/P3 spares warm recall; cold-recall "
  "p99 +12-14 % is the accepted cost. `cards/tuned_engine.md` records StudyE10c, E10d and E10e's "
  "verdicts and every measured cost, and **the guard that raises on unmeasured configurations is "
  "kept**. |")
w("| 2 | Ekya's missing licence | **citation-only use approved.** The clone stays for citation and "
  "commit pinning; nothing in it was opened, run or copied; the adapted baseline stays written "
  "from the paper. |")
w("| 3 | StudyRH8's oracle labels | **approved as proposed.** `rh8-demand-aware-ORACLE` is "
  "reported as an upper bound alongside the hindsight oracle and excluded from every deployable "
  "comparison; `RH8CausalDemand` is a separate deployable policy, labelled as **not** what "
  "StudyRH8 measured. |")
w("| 4 | the unverifiable citations | **identifiers supplied and verified** (§7). Route2Look and "
  "Fairway **dropped**; CacheRoute **dropped** (no identifier); llm-d cited **as software, not a "
  "paper**; QueryStream **verified but not built** (§9.1). |")
w("| 5 | FlashBack and TMO | **not built for now.** Both stay verified and recorded; TMO's clone "
  "and pin stand. |")
w()
w("### 9.1 QueryStream: verified, NOT built - and exactly what is missing")
w()
w("The user's rule was to build it if the mechanism is fully specified and otherwise to mark it "
  "\"verified, not built\" with the missing component. **Verified:** *QueryStream: Advancing "
  "Streaming Video Understanding with Query-Aware Pruning and Proactive Response*, Zhang, Yang, "
  "Wang, Qian and Xu, **ICLR 2026 poster**, OpenReview id **`738HjJEbml`**, with author-linked "
  "code at `github.com/Zhangkr2003/QueryStream` (**Apache-2.0**, cloned and pinned at "
  "`b793153403f7`).")
w()
w("**Not built, and the missing component is specific.** The paper has two parts: **QDP** "
  "(Query-aware Differential Pruning - filtering visual tokens by query relevance and temporal "
  "novelty) and **RTAR** (Relevance-Triggered Active Response - deciding when to respond). The "
  "addendum asked for the **gating / response logic**, i.e. RTAR. RTAR is **named** in the "
  "repository's README but neither **defined** there nor **implemented** in the release: the "
  "README's own \"At a glance\" table gives the released inference as \"Single-query QDP\", and "
  "the released `querystream/` tree contains only `demo/infer.py` plus a patched Qwen2.5-VL - a "
  "search for `rtar`, `proactive`, `trigger` and `should_respond` across the repository finds "
  "only README prose. The OpenReview PDF would not fetch and the OpenReview API returns 403, so "
  "**the relevance statistic and the firing condition could not be read**. Building it would mean "
  "inventing the trigger, which is what the rule forbids.")
w()
w("Separately, QDP prunes visual tokens *inside* the model, which our action space cannot express "
  "in any case (the same limitation as R3-Streaming's compression ratio, `cards/r3streaming.md` "
  "A1). **To build this baseline we need RTAR's statistic and firing condition** - from the paper "
  "PDF, or from an RTAR implementation.")
w()

w("## 10. Files")
w()
w("| path | what |")
w("|---|---|")
for p, d in [
    ("`experiments/orchestration/baselines/interface.py`", "the policy interface, enforced"),
    ("`.../costs.py`", "measured cost curves, one copy per constant"),
    ("`.../profiles.py`", "resource-quality profiles from StudyE9b / E9c"),
    ("`.../devsplit.py`", "StudyD3 development split - the only fitting set"),
    ("`.../naive.py`", "the seven naive baselines"),
    ("`.../<name>_adapted.py`", "one module per adapted baseline (14 modules)"),
    ("`.../reconstructed/`", "7 faithful reconstructions + 7 toy tests"),
    ("`.../cards/<name>.md`", "14 cards, one per case A / B / D baseline and per flagged own baseline"),
    ("`.../registry.yaml`", "24 entries: name, paper, verification, code, pinned commit, licence, case, versions, files"),
    ("`.../smoke/replay.py`, `run_all.py`", "the 10-minute replay harness and its runner"),
    ("`results/orchestration/study_b_baselines/b_smoke_results.json`", "the adapted-baseline smoke results"),
    ("`results/orchestration/study_b_baselines/b_originals_smoke.json`", "what each cloned original could and could not do on CPU"),
    ("`.../make_report.py`", "this report"),
    ("`~/baselines_src/<name>`", "7 third-party clones at pinned commits, OUTSIDE this repository"),
]:
    w(f"| {p} | {d} |")
w()

# ============================================================ addendum
import sys as _sys
_sys.path.insert(0, str(B)); _sys.path.insert(0, str(B / "reconstructed"))
import interface as _I  # noqa: E402

ADD = [r for r in ROWS if r["name"] in (
    "eco-llm", "streamscout", "preble", "mooncake", "kvflow", "uniscale",
    "thinking-qwenvl-atdm", "simplestream", "covstream")]
CONSTR = [r for r in ROWS if r["case"] == "constructed"]
UNVER = [r for r in ROWS if "UNVERIFIED" in str(r.get("case"))]

w("---")
w()
w("# ADDENDUM (2026-11-12): new candidates, constructed baselines, fairness rules, "
  "experiment grouping")
w()
w("Everything above still holds. This part records what the addendum added.")
w()
w("## 11. Verification first: Route2Look, Fairway, QueryStream")
w()
w("The addendum requires Route2Look and Fairway to be **verified before anything is built**, and "
  "that if a paper cannot be found it is marked \"unverified, not built\" and nothing else is "
  "done. Applied, and extended to a third candidate. **All three were re-checked on 2026-11-12 "
  "after the user's §9 answers, and they did not come out the same way:**")
w()
w("| candidate | outcome 2026-11-12 | basis |")
w("|---|---|---|")
w("| `route2look` | **DROPPED, unverified** | OpenAlex returns no record under this title; no "
  "venue, id or author list could be established. Nothing built, nothing else done. |")
w("| `fairway` | **DROPPED, unverified** | as above. |")
w("| `querystream` | **VERIFIED - NOT BUILT** | the user supplied the ICLR 2026 poster page; the "
  "paper and an Apache-2.0 author-linked repository both exist (OpenReview `738HjJEbml`, code "
  "pinned at `b793153403f7`). It is not built because its **RTAR** trigger is unspecified in "
  "every source reachable from here - see §9.1. |")
w()
RESOLVED3 = [r for r in ROWS if r["name"] in ("route2look", "fairway", "querystream")]
assert len(RESOLVED3) == 3, [r["name"] for r in RESOLVED3]
w("The registry entries, which are what the suite loader reads:")
w()
w("| candidate | requested as | verification | registry case | note |")
w("|---|---|---|---|---|")
for r in RESOLVED3:
    w(f"| `{r['name']}` | {r.get('priority','-')} | {r.get('verified','-')} | "
      f"**{r['case']}** | {r.get('notes','')} |")
w()
w("**QueryStream is no longer in this position.** It was requested as a P1 component baseline "
  "and at first could not be found under that name; the user's §9 answer supplied the poster "
  "page, and it verified. It is still not built, but for a different and narrower reason than "
  "Route2Look and Fairway: the paper exists and the missing piece is one named component (RTAR's "
  "relevance statistic and firing condition), recorded in §9.1. Route2Look and Fairway remain "
  "unfound and are dropped.")
w()
w("## 12. The six fairness rules, enforced")
w()
w("The addendum's rules are enforced in `interface.py` and the harness, not merely documented, "
  "and every card restates them:")
w()
w("| rule | how it is enforced |")
w("|---|---|")
for k in sorted(_I.FAIRNESS_RULES):
    w(f"| **{k}** | {_I.FAIRNESS_RULES[k]} |")
w()
w("`interface.check_fairness(policy)` runs before every smoke replay and raises on a policy that "
  "names a model outside {4BI, 32BI}, restricts the action space without a stated reason, or "
  "claims an unknown experiment. The harness additionally charges a session's **first** promotion "
  "to GPU-warm at the measured cold-prefill cost (rule 3: no policy gets free history), charges "
  "uplink bytes on every episodic cloud call, and asserts the demand trace's SHA-256 digest is "
  "identical for every policy (rule 6).")
w()
w("Two policies declare `reads_future = True` and are excluded from every deployable comparison: "
  "`hindsight-oracle` and `rh8-demand-aware-ORACLE`. One declares "
  "`restricts_action_space`: `thinking-qwenvl-atdm`, because being a readiness-only component IS "
  "the property under test (rule 4). Two declare `multi_instance_adapted`: `preble` and "
  "`mooncake`, because both are multi-replica systems adapted to our single replica (rule 2).")
w()
w("## 13. New candidates")
w()
w("| baseline | priority | paper (verification) | code | case | versions | card |")
w("|---|---|---|---|---|---|---|")
for r in ADD:
    code = r.get("code_url") or "-"
    if str(code).startswith("http"):
        code = f"`{code}`"
    if r.get("pinned_commit"):
        code += f"<br>@`{str(r['pinned_commit'])[:12]}`"
    if r.get("license"):
        code += f"<br>{r['license']}"
    w(f"| `{r['name']}` | {r.get('priority','-')} | {r.get('paper','-')}<br>*{r.get('verified','-')}* "
      f"| {code} | **{r['case']}** | {', '.join(r.get('versions') or []) or '-'} | "
      f"`{r.get('card','-')}` |")
w()
w("### Reconstruction toy tests (addendum)")
w()
w("| reconstruction | behaviours | named from the paper |")
w("|---|---|---|")
TOY2 = {
 "ecollm": "joint exploration over model AND pipeline knobs; **joint selection beats model "
           "selection alone under a cost SLO** (the paper's central claim); highest quality among "
           "feasible; least-violating when nothing is feasible; ties break to lower cost",
 "streamscout": "three views recent -> uniform -> query-relevant; answers at the first sufficient "
                "stage; the deepest view always answers; **thresholds distilled on a TRAINING set "
                "reproduce the earliest adequate stage**; harder examples escalate further",
 "kvflow": "steps-to-execution read off the workflow order; **eviction keeps the node about to "
           "run and drops the far one, where LRU would do the opposite**; evicts until the tier "
           "fits; prefetch nearest-first; fully overlapped prefetch",
 "uniscale": "arms are (model, compute) PAIRS so the optimisation is joint; LinUCB optimism and "
             "shrinking confidence width; concentration on the rewarding arm; **the efficiency "
             "reward makes the strongest arm lose when compute is priced**; played-arm-only update",
 "thinking_qwenvl": "waits on low progress; waits on low confidence; answers when both clear; "
                    r"**t\* is the first sufficient-evidence timestamp**; every decision carries a "
                    r"reason (the transparency claim); raising thresholds delays t\*",
 "covstream": "bandwidth far below raw upload; the edge encodes every frame regardless of "
              "queries; **the construction compute is CHARGED and non-zero with no query**; "
              "answering uploads nothing; richer features cost more bandwidth",
}
for n, txt in TOY2.items():
    r = next((x for x in ROWS if x["name"] == n.replace("_", "-")
              or x["name"] == n or x["name"].startswith(n.split("_")[0])), {})
    w(f"| `reconstructed/{n}.py` | **{r.get('toy_test','-')}** | {txt} |")
w()
w("## 14. Constructed baselines, and B9's component choices")
w()
w("| id | what it is | experiments |")
w("|---|---|---|")
for r in CONSTR:
    w(f"| `{r['name']}` | see `cards/constructed.md` | {', '.join(r.get('experiments') or [])} |")
w()
w("**B9 is the primary competitor and is built to be as strong as this suite allows.** Its four "
  "mechanisms, and why each choice was made over the alternative the addendum offered:")
w()
w("| component | choice | why over the alternative |")
w("|---|---|---|")
w("| (i) model / evidence routing | **ECO-LLM-style** joint (tier, representation, cadence, N) "
  "selection under SLOs | the addendum offered ECO-LLM-style *or* the calibrated query-type "
  "router; the former optimises over the joint space rather than a per-type rule, so it is "
  "strictly more informed |")
w("| (ii) streaming readiness + rate | **VideoStorm MaxMin** (Eq. 4) rate allocation, gated by an "
  "**R3-Streaming-style readiness** test | both were asked for; MaxMin over MaxSum because it "
  "protects the worst stream, and StudyE9b / E9c show rate allocation — not escalation — is the "
  "episodic lever |")
w("| (iii) SLO-aware cloud scheduling | **utility-per-GPU-second** admission with **EDF** order "
  "among the admitted | the addendum offered EDF *or* utility-per-cost; using the ratio for "
  "admission and EDF for ordering is stronger than either alone |")
w("| (iv) KV management | **host offload** + **Preble-style cache affinity** under load + "
  "**KVFlow-style reuse-aware eviction** on the causal inter-arrival estimate | the three modern "
  "mechanisms this suite holds, composed; the reuse signal is causal because rule 5 forbids "
  "KVFlow's workflow lookahead |")
w()
w("The four run **independently**: each optimises its own objective from the shared observation "
  "and none sees another's choice. Where two would touch the same field, a fixed precedence "
  "resolves it — (ii) sets the episodic rate and (i) may only *downgrade* it; (i) chooses the "
  "recall representation, (iii) may refuse on budget and (iv) on cache affinity; (iv) alone "
  "places sessions; (iii) alone orders. **That precedence is exactly what a jointly-optimising "
  "scheduler is meant to beat**, so it is stated rather than tuned away: any advantage our "
  "scheduler shows over B9 must come from coordinating the four decisions, not from better "
  "components.")
w()
w("## 15. The suite grouped by experiment")
w()
w("Metrics are the addendum's: **A** uses challenge mAP (StudyE9c's definition) as the headline "
  "with streaming AP (StudyE9b) beside it, on StudyD14b under the StudyE9b delivery model, plus "
  "false alarms and GPU-seconds; **B** uses S-EMBER accuracy on **PNG** inputs (StudyE10a-full "
  "did not validate JPEG), deadline success, memory, communication and maintenance compute; "
  "**C** reports per-class outcomes and flags any policy that starves a class.")
w()
for exp, lbl in (("A-episodic", "A — episodic"), ("B-recall", "B — recall"),
                 ("C-mixed", "C — mixed")):
    rows = [r for r in ROWS if exp in (r.get("experiments") or [])]
    w(f"### Experiment {lbl} — {len(rows)} baselines")
    w()
    w("| baseline | case | priority |")
    w("|---|---|---|")
    for r in sorted(rows, key=lambda x: (str(x["case"]), x["name"])):
        w(f"| `{r['name']}` | {r['case']} | {r.get('priority','-')} |")
    w()
w("**Our scheduler is not in these lists**; it is added later and compared against them.")
w()

# ============================================================ amendment 2026-11-12 (part 2)
import json as _json  # noqa: E402
_SM = {r["policy"]: r for r in _json.loads(
    (ROOT / "results/orchestration/study_b_baselines/b_smoke_results.json").read_text())}
_RA = _json.loads(
    (ROOT / "results/orchestration/study_b_baselines/b_recall_accuracy.json").read_text())
_E9D = _json.loads((ROOT / "results/dashcam/study_e9d/e9d_results.json").read_text())

w("---")
w()
w("# AMENDMENT (2026-11-12, later 2): two new actions, the recall and delay profiles, B10 and B11")
w()
w("Everything above still holds, and **no baseline number, cost constant or case decision from it "
  "changes**. This part records what the amendment added. It was pre-registered in the "
  "`StudyB-baselines` row of `research/EXPERIMENTS.md` before any of it was written.")
w()
w("## 13. The interface: MATERIALIZE and SUSPEND_UNTIL")
w()
w("| action | signature | what it means | validation |")
w("|---|---|---|---|")
w("| `MATERIALIZE` | `SessionAction(session, \"MATERIALIZE\", target_tokens, slice_tokens)` | "
  "**build** a session's cloud-side state up to `target_tokens`. `slice_tokens = None` means one "
  "monolithic prefill; an integer means chain slices of that size | `target_tokens` must be a "
  "positive int; `slice_tokens` must be `None` or a positive int; both fields are rejected on any "
  "other session action |")
w("| `SUSPEND_UNTIL` | `StreamAction(stream, \"suspend\", suspend_until_s=t)` | issue **no** "
  "cloud call for this stream until *t*; the application uses the device's own scores meanwhile | "
  "*t* must be in the future; a suspended stream may not carry a cadence or a frame count, and "
  "`suspend_until_s` is rejected on a non-suspended stream |")
w()
w("**`slice_tokens = None` is the property under test, not a defect of the baselines.** Every "
  "baseline written before the amendment can express only the monolithic form, and `interface."
  "FAIRNESS_RULES[4]` now says so explicitly. B11 is the slicing ablation and B10 its "
  "no-slicing counterpart (section 15).")
w()
w("**Five baselines whose own papers prefetch or eagerly warm are wired to `MATERIALIZE`**, with "
  "`slice_tokens = None` because each of those papers moves whole prefixes:")
w()
w("| baseline | what in the paper is a BUILD | card |")
w("|---|---|---|")
w("| `kvflow` | the prefetch that pulls a KV node in ahead of its predicted next execution | "
  "`cards/kvflow.md` |")
w("| `attentionstore` | the scheduler-aware fetch that promotes a session from DRAM into HBM | "
  "`cards/attentionstore.md` |")
w("| `pensieve` | moving a chunk into the GPU tier that is not already there | "
  "`cards/pensieve.md` |")
w("| `lmcache` | the loader that builds a GPU-resident KV copy | `cards/lmcache.md` |")
w("| `rh8-demand-aware` (both arms) | StudyRH8's EAGER warm-up pass, whose cost its own "
  "2026-11-03 audit records as EXCLUDED from RH8's in-window metrics (240 warm-up records moving "
  "4,289 MB, present only in the EAGER cells) | `cards/rh8.md` |")
w()
w("**What changed is what those baselines DECLARE, not what they are charged.** The harness "
  "already billed a session's first promotion to GPU-warm at the measured cold-prefill cost "
  "(fairness rule 3) and bills `MATERIALIZE` on the same path. The re-run smoke record is "
  "identical field for field to the pre-amendment one apart from the new counters, which is the "
  "check that this is true.")
w()
w("| baseline | MATERIALIZE calls | monolithic | sliced | slice sizes |")
w("|---|---|---|---|---|")
for _nm, _r in sorted(_SM.items()):
    if _r.get("materialize_calls"):
        w(f"| `{_nm}` | {_r['materialize_calls']} | {_r['materialize_monolithic']} | "
          f"{_r['materialize_sliced']} | {_r['slice_token_sizes'] or '—'} |")
w()
w("Two of the five never warm anything in this particular replay and so never call it: "
  "`pensieve`'s eviction leaves the GPU tier empty, and `rh8-demand-aware-causal`'s eager count "
  "is `round(0.25 x 2) = 0` with only two sessions. Both are properties of a two-session, "
  "10-minute replay and neither is changed by the amendment.")
w()
w("**No baseline uses `SUSPEND_UNTIL` yet** (0 suspended steps across all 40). It exists because "
  "StudyE9d measured what suspending costs, and because a policy that cannot express \"stop "
  "calling the cloud for the next second\" cannot be compared against one that can.")
w()
w("## 14. The profiles the amendment added")
w()
w("### 14.1 Recall accuracy per category x question-time bin x configuration")
w()
w("`recall_profiles.py` -> `results/orchestration/study_b_baselines/b_recall_accuracy.json` and "
  "`.csv`. **Every cell is a count of committed per-question `correct` flags.** Nothing is "
  "estimated, fitted or interpolated, and the loaders are StudyE6b's own so there is one "
  "definition of each configuration in the repository. Question-time bins are StudyE6b's "
  f"(`le120`, `120-480`, `gt480`); CIs are video-clustered bootstraps, "
  f"{_RA['n_bootstrap']} resamples, seed {_RA['seed']}.")
w()
w("| configuration | tier | source | n | accuracy | CI | le120 | 120-480 | gt480 |")
w("|---|---|---|---|---|---|---|---|---|")
for _nm, _c in _RA["configs"].items():
    _b = _c["by_bin"]
    def _bb(k):
        v = _b[k]
        if v["accuracy"] is None:
            return "—"
        return (f"{v['accuracy']:.3f} (n={v['n']})"
                + (" **UNRELIABLE**" if v["unreliable"] else ""))
    w(f"| `{_nm}` | {_c['tier']} | {_c['source']} | {_c['n']} | **{_c['accuracy']:.4f}** | "
      f"[{_c['ci'][0]:.3f}, {_c['ci'][1]:.3f}] | {_bb('le120')} | {_bb('120-480')} | "
      f"{_bb('gt480')} |")
w()
w("Per-category and per-(category x bin) cells are in the JSON and the CSV; a cell with "
  f"fewer than {_RA['small_n_flag']} questions is flagged `UNRELIABLE` rather than quoted, and "
  "there are many of those at the category x bin level.")
w()
w("**`4B-D2` is the DEVICE PROXY and is labelled as such everywhere.** Its letters are the "
  "H100 4B's for StudyE7's D2 input. StudyE8 Part D measured device-vs-H100 agreement at 68/68 "
  "warm and 27/27 cold on byte-identical inputs and StudyF4 measured per-question agreement "
  "0.972-0.981 with no cell below 90 %; but **StudyD15 Part A rejected the H100-for-Orin proxy as "
  "an EXACT numerical stand-in**, so these tables are valid for ordering and first-order value "
  "and never as exact device numbers.")
w()
w("### 14.2 The StudyE9d delay curves")
w()
w("`profiles.delay_curve`, `profiles.value_at_delay`, `profiles.d_star_s` and "
  "`profiles.blocking_loss` read StudyE9d directly. The four facts a policy can now consult:")
w()
w("| quantity | what it is | value |")
w("|---|---|---|")
_k = "always-cloud 32BI_N1@0.5"
_k3 = "always-cloud 32BI_N3@0.5"
w(f"| V(d) | challenge mAP against added delivery delay, 0 to 3 s in 0.25-s steps | 32B N = 1 at "
  f"cadence 0.5 s: {_E9D['vd'][_k + '|d0.0']['challenge_mAP']['value']:.4f} at d = 0 falling to "
  f"{_E9D['vd'][_k + '|d3.0']['challenge_mAP']['value']:.4f} at d = 3 s |")
w(f"| d\* | the added delay at which a cloud arm falls to the device's value | 32B N = 1 "
  f"**{_E9D['dstar'][_k]['challenge_mAP']['d_star_s']:.2f} s** (challenge mAP), "
  f"{_E9D['dstar'][_k]['streaming_h0.0']['d_star_s']:.2f} s (streaming AP at h = 0); 32B N = 3 "
  f"{_E9D['dstar'][_k3]['challenge_mAP']['d_star_s']:.2f} s and "
  f"{_E9D['dstar'][_k3]['streaming_h0.0']['d_star_s']:.2f} s |")
w(f"| blocking loss | value lost to a cloud-path outage of w seconds | at w = 2 s, QUEUE "
  f"{_E9D['blocking'][_k + '|QUEUE|w2.0']['mAP_loss']['mean']:+.4f} mAP against SUSPEND "
  f"{_E9D['blocking'][_k + '|SUSPEND|w2.0']['mAP_loss']['mean']:+.4f} |")
w("| interpolation | value BETWEEN StudyE9d's 0.25-s grid points | linear, held flat beyond "
  "3.0 s - **a RULE, not a measurement**, stated in `profiles.PROVENANCE` and in the B10 card |")
w()
w("**Two warnings are carried from StudyE9d into every card that uses it**: d\* has a wide CI "
  "and is not a threshold (the curve is the usable object), and a loss below about 0.001 challenge "
  "mAP is inside the noise floor and should be read as zero.")
w()
w("## 15. B10 and B11")
w()
w("| id | what it is | why it exists |")
w("|---|---|---|")
w("| **B10** blocking-aware admission, **no slicing** | defers a recall whose predicted "
  "non-preemptive engine time would hold an episodic stream past StudyE9d's d\*, unless its "
  "deadline slack is exhausted; EDF otherwise; recall served at whatever readiness the session "
  "actually has; KV management is B9's component (iv) verbatim | it is the strongest policy that "
  "uses the blocking mechanism StudyE10c / E10d / E10e located **without** slicing |")
w("| **B11** naive slicing | every materialization chained in fixed 2,048-token slices, FCFS, no "
  "awareness of episodic timing; everything else as tuned-engine always-cloud (StudyE10e's P1) | "
  "it is slicing **without** scheduling - the ablation that separates the two mechanisms |")
w()
w("B10's rule, verbatim from `constructed.py`:")
w()
w("```")
w("T        = costs.recall_ttft_s(readiness_tokens, readiness)   # predicted non-preemptive time")
w("affected = connected streams with a call due inside T (cadence <= T)")
w("d*       = profiles.d_star_s(arm, cadence)                    # StudyE9d")
w("if slack <= T:        ADMIT     # a deadline is never sacrificed to a stream")
w("elif T >= min(d*):    DEFER by min(0.25 s, slack - T)")
w("else:                 ADMIT")
w("```")
w()
w("Every component choice is tabulated in `cards/constructed.md`, including the three that are "
  "rules rather than measurements: the TTFT interpolation between StudyRH5's 11k and 28k points, "
  "reading \"no crossing inside the 3-s grid\" as 3.0 s, and the 0.25-s defer quantum.")
w()
w("**B11's per-slice overhead is NOT measured.** StudySIM1 sweeps it over "
  "{0.02, 0.05, 0.1, 0.2, 0.47} s and **every B11 result is labelled parametric** until "
  "StudySLICE1 measures it. It is the one free parameter in the suite and it is exposed here "
  "rather than buried in a constructor.")
w()
w("### What the smoke replay exercises, and what it does not")
w()
_b10 = _SM.get("B10-blocking-aware-admission", {})
w(f"**All 40 configurations ran, respected the interface and stayed in budget** (was 38; B10 and "
  f"B11 are the two new ones). But B10's deferral rule **never fires in this replay**: both of its "
  f"sessions stay HOST-WARM, so T = 0.46-1.00 s against d\* = 2.54 s, and the record shows "
  f"{_b10.get('recall', {}).get('cloud', '?')} admitted, "
  f"{_b10.get('recall', {}).get('deferred', '?')} deferred and "
  f"{_b10.get('materialize_calls', '?')} materializations. **That is exactly the "
  "silently-unexercised mechanism CLAUDE.md's protocol exists to catch**, so it is stated here "
  "rather than left for a reader to infer from a PASS.")
w()
w("The rule is instead exercised explicitly in "
  "`reconstructed/test_constructed_amendment_toy.py`, which asserts **24 named behaviours, all "
  "reproduced**: that d\* is read from StudyE9d and not guessed (2.537 s); that a COLD 28k "
  "recall's predicted hold exceeds it (7.40 s) and a HOST-WARM 11k recall's does not (0.46 s); "
  "that B10 therefore DEFERS the first while it has slack and ADMITS it once the slack is "
  "exhausted; that admitting a COLD query materializes the session monolithically; that B11 "
  "slices at 2,048 tokens, is FCFS and runs engine P1; and that the interface REJECTS each of the "
  "eight malformed uses of the two new actions.")
w()

out = ROOT / "reports/study_b_baselines.md"
out.write_text("\n".join(L) + "\n")
bad = 0
for i, x in enumerate(L):
    if x.startswith("|---"):
        n = x.count("|")
        if L[i - 1].count("|") != n:
            bad += 1
        j = i + 1
        while j < len(L) and L[j].startswith("|"):
            if L[j].count("|") != n:
                bad += 1
            j += 1
print(f"wrote {out} lines={len(L)} tables={sum(1 for x in L if x.startswith('|---'))} "
      f"malformed={bad}")
