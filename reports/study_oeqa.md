# StudyOEQA — OpenEQA feasibility gates

**Status: STOPPED AT THE GATES, BEFORE ANY DOWNLOAD.** Nothing has been fetched. One of the two
corpora is blocked on a licence we have not signed, and the same corpus independently exceeds the
free disk. The other clears both gates. This report is the decision request.

---

## Gate 1 — licences

| component | terms | status |
|---|---|---|
| OpenEQA code and Q&A pairs | **MIT** | **clear.** The question-answer pairs ship as a JSON file in the repo. |
| **ScanNet episode histories** | **ScanNet Terms of Use** | **BLOCKED.** |
| HM3D frames, Option 1 (RGB tarball) | no agreement stated | clear, with a provenance caveat below |
| HM3D frames, Option 2 (render from Habitat) | HM3D dataset access | **BLOCKED** |

**ScanNet, verbatim from its repository:** *"If you would like to download the ScanNet data, fill
out an agreement to the ScanNet Terms of Use ... using your institutional email addresses, and send
it to us at scannet@googlegroups.com."* The repository further states *"The data is released under
the ScanNet Terms of Use, and the code is released under the MIT license."* Turnaround is stated as
up to a week.

**We have not signed this.** Per the directive, I have stopped rather than proceeded. What is
needed is a filled-out ScanNet Terms of Use agreement sent from an institutional address, and a
reply before anything can be downloaded.

**HM3D Option 2** requires HM3D dataset access and an API token id and secret passed to
`habitat_sim.utils.datasets_download`. That is an access request we have not made.

**HM3D Option 1** needs no agreement: it is a pre-rendered RGB frame tarball
(`open-eqa-hm3d-frames-v0.tgz`, md5 `286aa5d2fda99f4ed1567ae212998370`). **Caveat, flagged rather
than buried:** OpenEQA's own documentation notes it is *"hosted by a third party repo (not by
Meta)"*. It is therefore a convenience mirror, not a first-party release, and the md5 is the only
integrity guarantee. That is a provenance limitation to record on any result derived from it.

---

## Gate 2 — disk

**Free space now: 51 GB, filesystem 99 % full.** (Down from 63 GB earlier today. I cleared 341 MB
of my own run outputs; the remaining pressure is other sessions' worktrees, which I have not
touched.)

| route | extraction output | peak need | verdict against 51 GB |
|---|---|---|---|
| ScanNet, RGB-only | **62 GB**, ~8 hrs | 62 GB **plus** the raw `.sens` corpus, which must be present first | **INFEASIBLE.** The output alone exceeds free space. |
| ScanNet, RGB-D + pose | 70 GB, ~10 hrs | worse | **INFEASIBLE** |
| **HM3D Option 1, RGB frames** | **~12 GB** | ~24 GB peak (tarball + extracted), ~12 GB resident after deleting the archive | **FEASIBLE**, ~27 GB margin |
| HM3D Option 2, RGB-D + pose | 16 GB, ~1.5 hrs | plus habitat-sim and the HM3D validation data | tight, and blocked on access regardless |

**ScanNet fails both gates independently.** Even with a signed agreement it does not fit, so the
licence and the disk would both have to be resolved.

---

## What this leaves, and what it costs the science

**Only the HM3D subset is reachable: 557 questions across 63 scenes**, against ScanNet's 1,079
questions across 89 scenes. So a run today would cover roughly a third of OpenEQA's ~1,600
questions, and the HM3D third only.

**One further caveat on HM3D, found while checking the above.** A third-party paper reports that
the HM3D episode trajectory *states* needed to render frames from the benchmark's exact camera
viewpoints are no longer publicly available, and that it therefore evaluated on the ScanNet subset
only. That blocks **Option 2**; it does not block **Option 1**, which ships frames already
rendered. The consequence is that the third-party tarball is not merely the convenient HM3D route,
it is currently the **only** one — which raises the weight resting on that single mirror.

---

## Decision requested

1. **Proceed on HM3D Option 1 alone?** It clears both gates. The kit and the gate analysis below
   would run on 557 questions.
2. **Or start the ScanNet Terms of Use process now** (institutional email, up to a week) **and
   separately resolve ~70 GB of disk**, so the larger subset becomes available later?

I have not downloaded anything and will not until this is answered.

---

## The kit, designed but not run

Shared with the H100 in the StudySS1 style. Written now because it costs nothing and because the
gate below is the point of the exercise, not a precondition to get past it.

- **Manifests**, one per representation, listing question id, episode id and frame paths.
- **One prompt template**, one image path: D2-style frames, **JPEG q88, 352x256**, matching the
  committed encoder. If OpenEQA's source frames differ in aspect ratio this will be stated rather
  than silently re-cropped.
- **Representations: FULL / RECENT (matching live2's window) / FINAL frame only.**
- **Two scorers**, with their agreement reported as a result in its own right:
  1. OpenEQA's **LLM-Match** prompt, run by **Mistral-7B-Instruct-v0.2**. **Deviation stated
     explicitly: the paper uses GPT-4.** A 7B judge is not a drop-in for GPT-4 and the agreement
     figure is the evidence for how far it is from one.
  2. A **normalised match** scorer.
- **Device run:** Qwen3-VL-4B-Instruct on the A6000 as the device proxy per D87, all three
  representations, pilot 300 questions, full set only if under ~4 hours. Accuracy with CIs, TTFT
  and tokens.

### The gate, run as a first-class question

`research/GRAVEYARD.md` closes **eight** datasets and its "Recurring failure modes" section names
the exact hazard here: *"captioning-pipeline datasets (FindingDory, EgoLife) require a working
perception layer. If the captioner degrades at reduced frame budgets, the compression signal is
confounded."* FindingDory failed precisely this way — full = summary = blind.

So the gate is measured, not assumed:

1. **Anchor recoverability** — is the answer recoverable from the episode at all, checked against
   the annotation or the frames containing the object or event.
2. **Success with full history.**
3. **FULL vs RECENT vs FINAL gap.**
4. **The fraction of questions that genuinely need earlier frames** — the number that decides
   whether OpenEQA is a usable testbed, and the direct counterpart to S-EMBER's **88.5 %**
   recent-covers fraction. If OpenEQA's fraction is also small, that is evidence about the **task
   class** rather than about one workload, which is a much stronger statement than either dataset
   supports alone.

### Positive and negative controls on the gate itself

Twice this week a check of mine passed for the wrong reason, and both the scorer-agreement figure
and the anchor-recoverability check are places where a plausible number is easy to produce and hard
to question. So before the gate is trusted on the rest:

- **a question whose anchor is obviously PRESENT** must be sorted as recoverable, and
- **a question whose anchor is obviously ABSENT** must be sorted as not recoverable.

If the gate does not sort those two correctly, its verdict on the remaining questions means
nothing and the run is void rather than negative.
