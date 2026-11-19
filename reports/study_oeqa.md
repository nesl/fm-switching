# StudyOEQA — OpenEQA feasibility gates

> **UPDATE, 2026-11-19, after the ruling to proceed: THE SANCTIONED ROUTE IS DEAD.**
> The HM3D Option 1 tarball **no longer exists**, verified directly. Every documented route to
> OpenEQA's episode frames is now closed, and the one surviving mirror **cannot be verified against
> the published md5 by construction**. Details in "The download attempt" below. **Nothing was
> computed; the ruling's own precondition — record *and verify* the md5 — is unsatisfiable.**

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


---

## The download attempt, 2026-11-19

The ruling was to proceed with HM3D Option 1, recording the source URL and md5 and labelling every
result "HM3D via third-party mirror". I checked headroom (51 GB free, unchanged), fetched the exact
URL from the repository, and downloaded.

**Source URL, as published:**
`https://www.dropbox.com/scl/fi/t79gsjqlan8dneg7o63sw/open-eqa-hm3d-frames-v0.tgz?rlkey=1iuukwy2g3f5t06q4a3mxqobm`
**Published md5:** `286aa5d2fda99f4ed1567ae212998370`

### What arrived was not the tarball

`curl` exited **0**. It wrote a file with the **correct name**. Nothing in the command's own signals
indicated a problem. The file was **230 KB**, and:

- `file` reports **HTML document**, not gzip.
- md5 of what arrived: **`2e5a0bdac63a966fa5b808ad91c993ba`** against the published
  **`286aa5d2fda99f4ed1567ae212998370`**.
- Its `<title>` is **"Dropbox - Link Expired"**.

**The md5 check did exactly the job it was required to do**, and it is worth being precise about
what it caught: a **success signal that was not one**. Exit code 0, right filename, no error. Only
the hash and the size revealed it. Recording the hash without verifying it would have left a 230 KB
HTML file named `.tgz` to be discovered at extraction, or later, as a result.

### Confirmed dead, not a redirect artefact

Three variants, none returning the archive:

| variant | result |
|---|---|
| `...&dl=1` | HTTP 200, `content-type: text/html` |
| `...&dl=0` | HTTP 200, `content-type: text/html` |
| `dl.dropboxusercontent.com/...` | **HTTP 403**, content-length 0 |

Independently corroborated: open issues on third-party repositories report the same expiry for both
the frames archive (filed ~209 days ago) and the states archive, and the request to re-upload the
states archive is **still open**.

### All three documented routes are now closed

| route | status |
|---|---|
| ScanNet | **blocked** — unsigned Terms of Use, and 62 GB extraction against 51 GB free |
| HM3D Option 2 (render from Habitat) | **blocked** — the trajectory-states archive is also expired |
| HM3D Option 1 (frames tarball) | **DEAD** — link expired, verified above |

### The surviving mirror cannot satisfy the ruling's own condition

A Hugging Face mirror (`AIGeeksGroup/OpenEQA`, MIT, ungated) carries HM3D RGB frames **as 63
per-scene `.tar` files**, reported elsewhere as 12,563,097,600 bytes. Two problems, and the first is
disqualifying on its own terms:

1. **Byte identity to the original is unverifiable by construction.** The published md5 covers a
   **single `.tgz`** that no longer exists in that form. Sixty-three separate tars cannot be hashed
   against one archive's checksum. A third party that pinned this mirror states plainly that the
   original Dropbox byte identity is **unverified**. So the one integrity link to the benchmark's
   actual frames is gone, and the ruling's instruction to *verify* the md5 cannot be followed.
2. **Size.** The dataset page reports a total of **87 GB**, well beyond 51 GB free, though a
   HM3D-only subset might fit.

### The accurate reproducibility claim, strengthened again

The earlier framing was "not independently reproducible from source". That is now too weak. The
accurate statement is:

> **OpenEQA's episode frames are not obtainable by any documented route, and the only surviving
> mirror cannot be verified against the published checksum.**

The annotations remain available and MIT-licensed; the **frames** are the problem. This is not a
scientific limitation of the benchmark, it is an availability one, and it would have become visible
only at extraction had the hash not been checked first.

### Decision requested

Proceeding would mean computing on frames **we cannot show are the benchmark's frames**. Given that
every downstream number would inherit that, I have stopped. Options:

1. **Accept the unverifiable mirror**, labelled "HM3D via unverifiable third-party mirror, byte
   identity to the original NOT established", and fetch only the HM3D subset if it fits.
2. **Sign the ScanNet Terms of Use and free ~70 GB**, making the larger and *verifiable* subset
   available.
3. **Close OpenEQA in `research/GRAVEYARD.md`** as unobtainable, with this report as the record.

Option 3 is a real candidate. The GRAVEYARD already closes eight datasets, and "the data cannot be
obtained or verified" is a cleaner closure reason than most of them.
