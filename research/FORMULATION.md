# Problem Formulation: Fidelity-Aware State Provisioning for Mobile FM Sessions

Status: v2 (2026-08-19). Owner: Pragya. Supersedes v1 (representation-aware
warm-state orchestration). This file is the spec for the trace-driven
simulator (E24) and the anchor for the decisive phase-diagram experiment.
Measured values in brackets cite results/fidelity/ and results/cost/.

Changes from v1, after external review: (1) two-level state abstraction
separating semantic fidelity from materialization level, fixing a resource
accounting bug; (2) "fidelity" replaces "representation" throughout —
representation reads as an encoding choice and collides with KV-compression
work, fidelity says application capability changes; (3) cache-value baseline
and semantic ablation added; (4) phase diagram replaces bar-chart ablation as
the decisive experiment; (5) continuous replication (RoutedSync) stated as the
boundary condition the paper starts beyond; (6) Context Inertia demoted to an
explanatory phrase.

---

## Motivating scenario

A personal assistant agent starts on-device (Jetson-class) as its user leaves
home. Its session history is short; everything fits locally. As the user
moves, edge server E1 comes into range. The runtime's regime estimate says the
session's queries are gist-compressible, so it provisions a 200-token summary
at E1: cheap to transfer, cheap to keep current, sufficient for the SLO. The
user starts asking questions that reach deep into the session history:
specific earlier events, exact ordering. The regime estimate shifts toward
dense-incompressible. A summary can no longer meet the quality SLO, and
materializing the full history at handoff would take tens of seconds [a6000:
21.7 s prefill at 64k tokens; jetson: slower]. The runtime begins materializing
full-fidelity state at E1 in the background while the device still serves.
E1's execution-ready capacity is finite, and holding this session's
materialized full state [~57 KB/token KV, 3.8 GB at 64k] forces demoting
another session's materialized window to stored form; that session will pay a
materialization delay on its next handoff. Later the user moves again: E1
drops out of range, E2 appears, and the same question repeats with less
certainty: what capability did we provision at E2?

The decisions in that story — what fidelity of state to provision, at what
materialization level, where, and when to refresh it — are the paper. Edge
capacity determines not merely whether a session is present at a node, but
what future questions that node is prepared to answer without expensive
reconstruction. State fidelity is a resource dimension: reducing it changes
future application capability, not just reconstruction latency, and the
cheapest sufficient fidelity depends on a query regime the runtime does not
observe.

We call the growth of reconstruction cost with accumulated session history
context inertia; it is the cost mechanism, not the contribution.

---

## Setting

A set of long-lived sessions S = {1..n} runs over a tiered compute graph.
Nodes are device d, edge servers e1, e2, ..., cloud c. A mobility trace M(t)
determines, at each time t, which nodes are reachable from session i's
endpoint and at what effective bandwidth B_ij(t) and RTT. The feasible compute
graph G_i(t) changes as the endpoint moves: an edge server near the endpoint
at time t may be unreachable at t+1. Mobility is structural, not scenery: it
creates transient preparation windows (E2 reachable cheaply now, handoff in
~20 s), candidate nodes that appear and disappear, and edge capacity far below
datacenter tiering assumptions.

The session, not a pipeline stage, is the managed entity.

## State objects: fidelity × materialization

Each session i has accumulated history of length L_i(t) tokens, growing at
rate lambda_i. A state object is a replica of session i's state at node j,
described by two independent axes:

**Semantic fidelity** f in F = {sum80, sum200, win, full}: what subset of
future queries the object can answer at quality. Fidelities are not byte
encodings of equivalent state; a 200-token summary and the full history answer
different sets of future questions [measured Q: LoCoMo full 0.34–0.40 vs
summary 0.10–0.13, window 0.22–0.26; EgoSchema sum200 ≈ full; Infini-THOR
reader-dependent].

**Materialization level** m in {stored, ready}:
- stored: the object exists at the node as text. Footprint S_store(f, L)
  [full text ~4 B/token → ~256 KB at 64k; summaries ~0.3–0.8 KB; window ~8 KB].
  Storage is effectively non-binding; DRAM/disk absorb it.
- ready: the object is execution-ready (KV-resident) and can serve without
  prefill. Footprint S_ready(f, L) [~57 KB/token of materialized content:
  full at 64k ≈ 3.8 GB; win (~2k tok) ≈ 115 MB; summaries ≈ 5–12 MB].
  GPU memory after model residency is the binding capacity.

**Costs per object (i, j, f, m):**
- transfer(f, L, B): move stored form to node j [text sizes above; negligible
  vs materialization at ≥1 Mbps for summaries/window, small for full text]
- materialize(f, L, j): stored → ready, i.e., prefill at node j [measured
  a6000: full 165 ms at 1k → 21.7 s at 64k, near-linear; window 65–130 ms
  flat; summary ~30 ms flat; jetson: pending E23, ~6x slower at 4k under
  sdpa; infeasible regions recorded as such — rtx3090ti OOM above 32k]
- refresh(f, L): bring the object current after new turns. For ready-full:
  warm incremental append [~330 ms/turn at 64k vs 22.5 s cold, ~68x]. For
  summaries: regeneration requires prefill of L — summary freshness costs
  like full materialization [corrected phase-1 measurement], so cheap-to-hold
  is not cheap-to-maintain. Stale objects pay catch-up before serving.
- Q(f, w): expected task quality of fidelity f under workload regime w.

**Resource accounting rule (fixes v1 bug):** the capacity constraint binds on
S_ready only. A stored full transcript at E1 does not consume meaningful
capacity; it consumes future materialization latency. v1 conflated
stored-at-node with execution-ready and could manufacture scarcity by charging
full-fidelity objects KV-sized footprints while summaries were charged text
sizes. The two-level abstraction makes "store full text everywhere,
materialize selectively" a legitimate policy the optimizer can discover.

KV is therefore not a competing representation but the materialized form of
any fidelity. Cross-architecture KV portability and per-tier model
heterogeneity remain scoped out (see Scoping).

## Regime uncertainty

The regime w_i of session i's future queries is not observed. The runtime
holds an estimate ŵ_i from an online probe or history; the oracle w_i is an
evaluation upper bound. Q is also reader-model dependent [0a: Mistral cannot
exploit summaries Qwen can], fixed per deployment (see Scoping). The policy's
advantage must not derive from oracle knowledge of w_i: headline results use
the implementable estimator, with oracle reported as the ceiling and a
prediction-error sweep between them.

## Decisions

At each control epoch, for each session i and node j in G_i(t):
- z_ijfm in {0,1}: provision fidelity f at materialization m for session i at
  node j
- p_i: the node currently serving session i
- u_ijf: refresh policy for the object (every turn, periodic, on-demand)

## Constraints

1. **Ready-capacity**: sum over i,f of z_ijf,ready · S_ready(f, L_i) <= C_j
   per node j. C_j is GPU memory after model residency [24 GB edge GPU minus
   15 GB model ≈ 9 GB usable: two ready-full 64k sessions do not fit].
2. **Serving feasibility**: p_i must hold an object fresh enough to serve
   within the latency SLO, or pay materialization + catch-up first.
3. **Reachability**: transfers only along edges of G_i(t) at B(t).
4. **Infeasibility**: (j, f, ready, L) combinations beyond node memory or
   timeout are excluded [rtx3090ti above 32k; jetson ceiling lower, E23].

## Objective

Maximize the fraction of requests satisfying both the latency SLO and the
quality SLO Q(served fidelity, w_i) >= q_min, over the trace. Latency, bytes
transferred, ready-capacity occupancy, refresh compute, wasted prefetch, and
cold-materialization frequency are reported as explanatory metrics, not
folded into a weighted objective. Handoff latency on a mobility event is the
binding term: materialize-from-stored at the target if provisioned, transfer
+ materialize if not.

## Boundary condition: where this problem exists

With sufficient bandwidth and capacity, continuous replication of ready state
(RoutedSync, March simulator result) keeps every candidate synchronized and
no provisioning decision is needed. That result defines the boundary: this
paper operates where replication stops scaling — ready-capacity C_j too small
to hold all sessions at full fidelity across candidates, bandwidth too
variable to stream KV diffs continuously, candidate sets changing with
mobility. Assumptions 4–6 below are irreducible; remove any one and the
optimization collapses to a known problem:
1. Sessions accumulate information needed by future requests [LoCoMo full >>
   blind].
2. Cold materialization threatens the latency SLO at realistic L [21.7 s at
   64k].
3. Fidelities differ materially in cost and capability [phase-0a Q table;
   S_ready spread].
4. Full fidelity cannot be ready at every plausible target [capacity
   arithmetic above].
5. Future serving location is uncertain [mobility trace].
6. Future fidelity requirement is uncertain or heterogeneous [regime mix +
   estimator].

## The coupling claim (falsifiable)

Claim: fidelity choice and provisioning location do not decompose, because
ready-capacity has semantic capability, not just byte occupancy — one GB of
ready state is not interchangeable across fidelities, since a provisioned
node's value depends on the distribution of future information requirements,
not only reuse probability.

Decomposed policies that must fail for the claim to hold:
- **Fidelity-first**: pick minimal f with Q(f, ŵ) >= q_min, then place
  cheaply. Fails by spending fidelity on unlikely destinations.
- **Placement-first**: pick nodes by mobility prediction, then fit fidelities
  to capacity. Fails by putting semantically inadequate state at likely
  destinations.
- **Cache-value**: rank objects by P(future use) × saved latency / bytes —
  strong stochastic-caching baseline. Fails iff fidelity-dependent capability
  matters beyond byte-value; if it matches joint, the abstraction is
  cosmetic and the paper's central objection ("this is ordinary cache
  placement") stands.

**Decisive experiment: the phase diagram.** X: ready capacity normalized by
the requirement to hold every candidate at full fidelity (0, 10, 25, 50, 75,
100%). Y: mobility uncertainty (static → low predictability, parameterized
from trace families by handoff entropy). Sweeps: session length, session
count, bandwidth, regime mix. Expected shape, committed in advance: all
policies converge at high capacity (replication wins or ties); everyone
struggles near zero capacity; static mobility → fidelity-first suffices;
single-regime population → placement-first suffices; the joint win region is
mid-capacity × mixed regimes × moderate uncertainty. Reporting the
convergence boundaries is deliberate — the claim's credibility rests on the
advantage disappearing where the coupling is removed.

**Semantic ablation (kill test):** replace fidelities with byte-equivalent
abstract objects (same sizes and costs, no Q differences). If the joint
advantage persists, the semantic story is doing nothing and the framing must
be abandoned.

**Stop conditions** (any of these kills or radically changes the framing):
fidelity-first within ~5% of joint almost everywhere; placement-first
likewise; joint wins only on synthetic adversarial traces; ready-full fits
everywhere on realistic hardware; cache-value matches joint; advantage
requires oracle w_i.

## Policies for E24 (first gate)

joint · fidelity-first · placement-first · reactive (no pre-provisioning) ·
always-full · always-compact · cache-value · oracle (true w_i, known M).
Added in hardening (weeks 5–7): continuous replication (RoutedSync),
mobility-only prefetch (provisions likely nodes, fidelity-blind).

## Ablations

oracle vs implemented vs no fidelity predictor; oracle vs implemented vs no
mobility predictor; no pre-staging; fixed fidelity; unlimited capacity;
semantic ablation (above).

---

## Scoping

**Single model per deployment.** Every node runs the same model; Q(f, w) does
not vary by node. Real deployments are heterogeneous (3B on device, 70B in
cloud), adding Q(f, w, m_j) and making state partially non-portable across
tiers even as text: phase-0a cross-summarizer results show summaries written
by one model read by another transfer nontrivially [Mistral reading Qwen's
summaries gains nothing over its own]. Scoped to discussion with those
measurements as evidence.

**KV portability.** Materialized state is architecture-bound; cross-model KV
transfer is out of scope. KV appears only as the ready materialization of a
fidelity, with measured sizes.

**Runtime constant.** Prefill numbers are HF transformers + flash-attn
(flash) / sdpa (jetson). A vLLM calibration run on a6000 at selected L will
report the constant-factor gap; the cost structure (near-linear growth,
warm/cold ratio, ready-capacity binding) is the load-bearing input, not the
absolute constant. [pending]

## Open parameters (set at E24 build)

Control epoch; edge node count; session count n and regime mix; lambda_i from
LoCoMo/Infini-THOR turn statistics; q_min and latency SLO per session class;
mobility trace source and handoff-entropy parameterization; ŵ estimator
(cheap summary-vs-full agreement probe vs history-based fidelity risk);
epsilon for the decomposition test; workload C construction (mobile/embodied
sessions from Infini-THOR trajectories inside the mobility harness —
observations and topology from the same world; no new dataset,
GRAVEYARD.md governs).