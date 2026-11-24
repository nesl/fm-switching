# DEVICE_ANSWERS (StudyD218-DA): HELD AND NOT APPLIED. DO NOT WIRE THIS.

*** NOTHING HERE IS ON THE IMPORT PATH, AND NOTHING MUST BE PUT ON IT WITHOUT A USER RULING. ***
Every file carries a `.patch` or `.held` suffix precisely so it cannot be imported or picked up by a
glob. `covex-v6-final-da` occurs in ZERO files under `experiments/` on origin, and that is the correct
state until the ruling below is made.

## WHY THIS DIRECTORY EXISTS

The DEVICE_ANSWERS implementation was built, proved dry and reported, and its owning session STOOD DOWN
WITHOUT COMMITTING ANY CODE (correctly: it read CLAUDE.md's git rules as reserving that to the user).
Only the report and the pre-registrations were committed, at `4f317e1f`. **SO THE IMPLEMENTATION ITSELF
EXISTED ONLY IN A SCRATCHPAD**, which the environment warns a reboot or routine cleanup can clear, and on
the night it was written the disk hit 100 percent and a 7 GB scratchpad cleanup came within one deletion
of destroying another session's only copy of held wiring. This directory removes that risk and CHANGES
NOTHING ELSE. Preserving code is RECORDING; adopting it is the user's DECISION.

## THE PENDING RULING THIS DOES NOT PRE-EMPT

The dry 1x count is **1**, not 0, so the pre-registered stop condition fired and the session stopped
rather than deciding. **Adopt DEVICE_ANSWERS into `covex-v6-final` (D209 (1) then supersedes the posted
s4 cell and rung 4 is rerun), or keep it as a separate arm `covex-v6-final-da` (the posted cell stands)?**
Also open: which of two parallel pre-registrations, which AGREE ON THE PASS CONDITION VERBATIM, is the
record.
*** AND ONE PREREQUISITE THAT THE AGGREGATE COUNTS HID: *** the traced s4 bar crossing has
`harm 1.638113` against `bar 1.452307` AND **`harm_device_discounted: 0.0`**. So the crossing exists ONLY
under the on-time-cloud harm reading and vanishes ENTIRELY under the device-discounted one. **THE
HARM-FORM RULING DECIDES WHETHER THERE IS ANYTHING FOR DEVICE_ANSWERS TO DO AT ALL**, not merely how much
it gains.

## CONTENTS, AND HOW TO RECONSTRUCT

Patches are `diff -u` against the files as committed on `4e1d0ff5`, and **EACH WAS VERIFIED TO REPRODUCE
THE AUTHOR'S WORKING TREE BYTE FOR BYTE** before being stored:
| file | what | reproduces |
|---|---|---|
| `arms_v6cf.py.patch` | +137 lines on the live arm module | md5 `e6ea16cc193d` |
| `cf_protect_defer.py.patch` | +260 lines, the protect-and-defer branch | md5 `539e7538b1c4` |
| `coordinator.py.patch` | +2 lines | md5 `81136b045755` |
| `arms_v6cf_device.py.held` | the DEVICE_ANSWERS arm module, a NEW file | 10,075 bytes |
| `d218_da_driver.py.held` | the sweep driver | 18,436 bytes |
| `d218_da_one_cell.py.held` | the one-cell runner | 5,837 bytes |
| `d218_da_mechanism_tests.py.held` | the mechanism tests | 10,316 bytes |
| `patch_pd.py.held` | the author's own patch script | 18,106 bytes |

**DO NOT FORCE A PATCH THAT NO LONGER APPLIES.** If any target has moved on origin, re-derive the change
rather than forcing it: forcing would silently revert whatever moved it. The authoritative account of what
this code does and what was proved is `reports/study_d218_device_answers.md`, and the frozen
pre-registrations are in `results/orchestration/live2/d218_device_answers/`.

## WHAT WAS PROVED, AND WHAT WAS NOT

PROVED DRY: the pre-registered pass condition (`pd_request_crossed_bar_unexpressible` 27 to 0 with 15
denials at 0.25x), nine byte-identity pairs at 0 differing, the off-switch identity at both settings, and
both Step 4 controls collapsing to base exactly. NOT PROVED: anything live. `covex-v6-final-da` has never
run a live cell, and the live pair is PREPARED but deliberately NOT POSTED.
