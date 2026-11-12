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
    ("llm-d / CacheRoute", "NOT VERIFIED", "**UNVERIFIED** - no index record found",
     "a Kubernetes-native distributed inference stack / cache-aware router; infrastructure "
     "rather than a published policy we can reconstruct."),
    ("MSAO", "NOT VERIFIED", "**UNVERIFIED** - no index record found",
     "multi-server adaptive offloading; could not confirm the paper exists under this name."),
    ("AceSpec", "NOT VERIFIED", "**UNVERIFIED** - no index record found",
     "speculative decoding; a decode-time accelerator, orthogonal to placement."),
    ("Splitwise-DRL", "NOT VERIFIED", "**UNVERIFIED** - no index record found",
     "a reinforcement-learning variant of Splitwise; same cluster-provisioning scope."),
    ("SpotVLM / edgeVLM", "NOT VERIFIED", "**UNVERIFIED** - no index record found",
     "on-device VLM execution; a device-side runtime, not a scheduler."),
    ("SAIL", "MobiSys 2026 (claimed)", "**UNVERIFIED** - no index record found",
     "could not confirm; if it exists it is an on-device VLM system rather than a scheduler."),
    ("HERMES", "ACL 2026 (claimed)", "**UNVERIFIED** - no index record found",
     "could not confirm under this name."),
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
w("**(a) StudyE10e does not exist.** The tuned-engine baseline was specified as \"the best "
  "engine configuration from StudyE10c / E10e (priority + step budget + long-prefill "
  "threshold)\". There is no `reports/study_e10e*.md` and no StudyE10e row in the registry (only "
  "E10a, E10b, E10c, E10d). Worse for the specification: **StudyE10c's verdict is that no engine "
  "setting helps** - E0 (default), E1 (priority), E2 (2,048-token step budget) and E4 (both) "
  "were \"identical to E0 in 12 / 12 comparable ladders\" - and **the long-prefill threshold was "
  "never run** (StudyE10d lists it as an untested lever). So the best *measured* configuration is "
  "the default. `tuned_engine.py` therefore exposes only the four configurations a committed "
  "study measured, defaults to E0 with the reason attached, and **raises** if asked for any other "
  "name, so no table downstream can contain a number no measurement supports. **This needs your "
  "decision** (see §7).")
w()
w("**(b) Ekya's repository has no licence.** `github.com/edge-video-services/ekya` is Microsoft "
  "Research's own release, but it contains **no LICENSE or COPYING file anywhere** and the README "
  "names none, so no right to use or modify is granted. Applied consequence: the clone is used "
  "for citation and commit pinning only, **no file in it was opened, run or copied**, its own "
  "CPU-runnable toy simulator was deliberately left unrun, and the adapted baseline was written "
  "from the paper. Flagged rather than resolved.")
w()
w("**(c) StudyRH8's winning policy reads labels.** RH8's MIX-DEMAND keeps warm \"exactly the "
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
w(f"### Citations I could not verify ({len(unver)})")
w()
w("Searched OpenAlex by title, the arXiv API by identifier where one was given, and the web; no "
  "index record was found for:")
w()
for nm in unver:
    w(f"- **{nm}**")
w()
w("These are flagged rather than cited. Four of them (llm-d / CacheRoute, SAIL, VLMCache, "
  "HERMES) were given with a venue or product name but no identifier, and the remaining ones "
  "(MSAO, AceSpec, Splitwise-DRL, SpotVLM / edgeVLM) may be internal shorthands rather than "
  "paper titles. **If any of these is meant to be in the related-work section, it needs an "
  "identifier.** Note that VLMCache (MobiSys 2026) *did* verify and is listed above; SAIL, also "
  "given as MobiSys 2026, did not.")
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
w("Two reconstruction gaps where a paper did not print something needed, each marked in its card "
  "and its module: Hybrid LLM's label-transformation closed form (§3.3 gives the objective and "
  "says `t` is grid-searched, not the function) and PerLLM's `P(t)` term (it appears in the "
  "CS-UCB figure undefined; set to zero).")
w()

w("## 9. Open questions for you")
w()
w("1. **The tuned engine (§0a).** Either StudyE10e is planned and this baseline should wait for "
  "it, or the intended baseline is \"E10c's best measured configuration\", which is the **default "
  "engine** - in which case `tuned-engine` and `naive.always-cloud-fcfs` differ only in name. "
  "Needs a decision; I will not guess a tuned combination.")
w("2. **Ekya's licence (§0b).** Confirm that citation-only use is what you want, or ask the "
  "authors for a licence if the original needs to run.")
w("3. **RH8 (§0c).** Confirm that the oracle arm is to be reported as an upper bound and the "
  "causal arm as a separate, clearly-labelled policy that StudyRH8 never measured.")
w("4. **The 8 unverifiable citations (§7).** Identifiers needed, or drop them.")
w("5. **FlashBack and TMO** are decided but not built (§6). Both are under the half-day bar; say "
  "the word and they go in.")
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
  "done. Applied, and extended to a third candidate that turned out the same way:")
w()
w("| candidate | requested as | verification attempted | outcome |")
w("|---|---|---|---|")
for r in UNVER:
    w(f"| `{r['name']}` | {r.get('priority','-')} | {r.get('verified','-')} | "
      f"**{r['case']}** — {r.get('notes','')} |")
w()
w("**QueryStream was requested as a P1 component baseline**, but no index record exists for it "
  "under that name (the addendum gives no identifier, only \"ICLR 2026\"). Building it would "
  "mean inventing its gating and response logic, so it is treated exactly like Route2Look and "
  "Fairway. **All three need an identifier before they can enter the suite.**")
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
