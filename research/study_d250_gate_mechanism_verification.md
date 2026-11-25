# D250 GATE: THE MEMORY CONDITION IS PROVEN LIVE ON BOTH HALVES, WITH FOUR READINGS AND A POSITIVE CONTROL

**Recorded BEFORE the six D250 baselines run, per CLAUDE.md's requirement that mechanism verification is
completed and recorded before the sweep.**
**Gate cell: `covex-v6-fair-final` n16 s4 `_kv0.5r_h0.5_L3_epg_rq30_preD249`, started 11:38:11.**

## THE FOUR READINGS

| half | reading | source | value |
|---|---|---|---|
| **GPU** | logical pool | launched harness argv, pid 391615 `/proc` cmdline | `--gpu-kv-tokens 31472` present |
| **GPU** | **enforcement** | cell header, read live from the run directory | *** `kv_capacity_enforced: true` *** |
| HOST | argv | server `/proc` argv, last of a duplicated flag | `--kv-offloading-size 13.5` |
| HOST | mmap | server log | offload mmap 14.50 GB |
| HOST | header | cell header | `host_tier_gib 13.5`, `host_tier_tokens 55,315` |

**Arithmetic checked independently: 13.5 * 2^30 / 1e9 = 14.4955 against the logged 14.50 GB, and
110,630 / 2 = 55,315 exactly. Both halves are halved by the SAME factor, so the condition is internally
consistent rather than one-sided: GPU logical pool 62,944 to 31,472 and host 110,630 to 55,315.**

## *** THE PROOF THAT WAS FIRST OFFERED AND WHY IT WAS REJECTED ***

**The GPU half was first evidenced as "ENGINE FLAG LIVE, `--num-gpu-blocks-override 1968
--max-model-len 31472` in the server argv".** *** THOSE ARE THE UNHALVED DEFAULTS: 1968 appears 14 times in
the repo against 985 and 984 three times, and 31472 seventeen times against the halved 15744. THEY ARE
PRESENT IN EVERY CELL, HALVED OR NOT, SO THEY PROVE THE ENGINE STARTED AND NOTHING ELSE. A QUANTITY
IDENTICAL ACROSS THE COMPARED CONDITIONS CANNOT EVIDENCE EITHER OF THEM. ***
**And their being the defaults is CORRECT, not a defect: driver v40 lines 91 to 93 record D151, that
"0.5x / 0.25x GPU pool is the harness's LOGICAL pool with enforcement on (coordinator belief and
enforcement); the engine's real pool is PINNED AND UNCHANGED."**

*** SO THE GPU HALF LIVES IN TWO PLACES AND THE SECOND IS A FLAG THAT DEFAULTS OFF. `cstate.py:474`
declares `kv_capacity_enforced: bool = False`, and the READ is `cstate.py:554`:
`if self.kv_capacity_enforced and int(self.gpu_kv_tokens) > 0:`. WITH THAT FLAG FALSE, `--gpu-kv-tokens
31472` IS A WRITTEN VALUE THAT IS NEVER READ, THE GPU HALF IS **ABSENT**, AND THE CELL WOULD TEST THE HOST
HALF ONLY WHILE EVERY SURFACE SIGN SAID OTHERWISE. *** It reads **true**, so the half is live. The same
field was found FALSE in the dry harness during the D259 work, which correctly refused to make any kv0.5r
claim from it, so the default-off case is not hypothetical.

## WHY THE HEADER IS THE AUTHORITATIVE READ AND NOT THE ARGV

**The launched argv carries `--host-tier-gib 27 ... --host-tier-gib 13.5`, a DUPLICATED flag resolved by
argparse last-wins.** *** SO THE ARGV ALONE IS AMBIGUOUS BY CONSTRUCTION: IF THE ORDER EVER FLIPPED, THE
CONDITION WOULD SILENTLY BECOME UNHALVED AND ONLY THE HEADER WOULD SAY SO. THE HEADER IS THE READ THAT
RESOLVES THE DUPLICATE, WHICH IS WHY IT IS CITED BESIDE THE ARGV AND NOT INSTEAD OF IT. ***

## *** THE POSITIVE CONTROL, AND IT CARRIES MORE THAN THE GATE DOES ***

**The committed `confidence-cascade` kv0.5r s4 header reads the same: enforced true, 31,472.**
*** THAT IS CHECK 7 APPLIED TO THE CONTROL RATHER THAN THE RESULT, AND IT SETTLES SOMETHING LARGER THAN THIS
GATE: HAD A COMMITTED kv0.5r CELL READ `enforced: false`, EVERY COMMITTED kv0.5r RESULT IN THE PROJECT WOULD
HAVE BEEN A HOST-ONLY CONDITION MISLABELLED AS A MEMORY CONDITION. IT READS TRUE, SO THE COMMITTED kv0.5r
CORPUS IS CONFIRMED TO HAVE HAD ENFORCEMENT ON. ***

## DISPOSITION

**No objection to proceeding. When the gate cell ends valid, the six D250 baselines are un-commented and
D257, D244 and D258 are released behind them, in file order.**
**Standing correction adopted by the H100 for all future cells: the GPU proof is the HARNESS argv plus the
HEADER, never the server flags.**
