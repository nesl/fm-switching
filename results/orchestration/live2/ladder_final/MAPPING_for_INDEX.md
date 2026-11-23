# D208 mapping: committed arm -> final rung (for the user's own `results/INDEX.md` rows)

Given as a table rather than edited into `INDEX.md`, as instructed. Built on origin/main
`62b8a7eb1088656220d08b5b624b564f44ac412c`.

| committed arm | final rung | what the final rung adds over it | the committed arm's cells |
|---|---|---|---|
| `covex-v6-state-uo-c5attr` | **`covex-v6-state-final`** (rung 2) | the D188 (2) id(obs) cache-key fix, turned ON (it was built and left off by default under that same ruling) | KEPT, still comparable; the arm is untouched |
| `covex-v6-fair-c5attr` | **`covex-v6-fair-final`** (rung 3) | rung 2's fix, plus the state planner reading the deficit feed (D206 (2)), plus the alert release re-check | KEPT |
| `covex-v6-fair-c5attr-rr` | **`covex-v6-fair-final`** (rung 3) | this is the arm whose release-re-check mechanism is folded in; the final rung adds the planner limb and the id(obs) fix on top | KEPT; its four per-seed verdicts stand as measurements of their own code (D209 (1)) |
| `covex-v6-cf-c5attr` | **`covex-v6-final`** (rung 4) | rung 3 of the final ladder beneath it, so both counterfactual legs AND the state planner read one deficit source | KEPT |
| `covex-v6-state` | **NOT MAPPED** | nothing: the name keeps its committed meaning | **SIX committed cell directories KEPT and untouched** (s4, s4_rerun, s5, s6, s7, s7_rerun), which is why the final rungs carry the `-final` suffix |
| `covex-v6-fair`, `covex-v6` | **NOT MAPPED** | nothing: both keep their committed registrations | registered, no committed cells |
| `covex-v6-base`, `covex-v6-rules` | **comparators, NOT rungs** | nothing | must stay BYTE-IDENTICAL; proof (a) |

**The suffix is permanent and correct**, and paper labels are mapped at write-up. `arms.ARMS` is a
dict, so a second registration under a committed key replaces rather than adds;
`arms_final_ladder.register()` raises on a clash against a protected-name list rather than relying
on a reading of the code, and `d208_ladder_name_proof.json` records the factory identity of all
nine protected names before and after registration as unchanged.
