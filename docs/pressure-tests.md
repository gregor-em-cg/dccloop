# Conceptual pressure tests

The expectations below are proposed desk-review cases. They are not executed results or replacement executable oracles. Preserve existing fixtures; recommend a versioned contract revision explicitly if an expectation is wrong. All proposed outcomes in this matrix are `[ESTIMATE]`.

For each case, report starting identities, disturbance, expected and forbidden actions, state/budget/approval effects, required evidence, implementation coverage, and a falsifier. Classify coverage as `source-supported`, `design-gap`, `ambiguous-contract`, or `not-assessable`; these are not runtime PASS labels.

| ID | Counterexample | Proposed response | Observable failure |
|---|---|---|---|
| PT01 | Rear view is missing but exact unseen dimensions are requested | Record a specifically allowed approximation or block the exactness claim | Invented dimensions appear as sourced |
| PT02 | Drawing and photographs conflict | Record conflict and measurement authority; version a changed brief | Convenient value silently wins |
| PT03 | Beautiful render has wrong proportions or parts | Fail mandatory identity/geometry criterion | Average beauty score hides wrong object |
| PT04 | Dense valid mesh slows the representative target scene | Apply scene-use budget and compare a reduced variant to fixed visual anchors | Mesh count alone determines approval |
| PT05 | Optimization preserves one camera but damages another | Fail fidelity; preserve master and change method/scope | Only favorable camera is reviewed |
| PT06 | An intentionally open surface meets a closed-solid rule | Apply frozen category-specific applicability | Geometry is closed solely to satisfy an irrelevant test |
| PT07 | Neutral geometry review passed; transparency exposes a structural defect | Authorize scoped unfreeze, new candidate and dependent proofs | Delivery checks override visual failure |
| PT08 | Material-only displacement changes bounds or contact | Detect dependency and revalidate authorized geometry | Cosmetic job label bypasses protection |
| PT09 | An exact approved library finish exists | Bind immutable version/realization and validate mapping | Unnecessary graph regeneration or unpinned latest |
| PT10 | Unique finish requires out-of-range parameters | Derive isolated variant and required approval | Approved global finish is mutated |
| PT11 | Shared map/node group changes during another asset review | Retain pinned dependency or invalidate evidence | Approved asset appearance drifts silently |
| PT12 | Reference lighting is mistaken for material appearance | Retain uncertainty and evaluate controlled/angular evidence | Photographic shadow becomes universal finish data |
| PT13 | Source graph uses an unsupported target-renderer feature | Reject mapping or apply approved conversion and retest | Default or changed material is silently accepted |
| PT14 | Import alters scale, pivots, normals, instances or UVs | Detect mismatch against pinned target profile | Source-only checks stand in for target validation |
| PT15 | Two variants collide in object/material names on merge | Use stable IDs and approved namespace mapping or reject | Silent renaming breaks downstream bindings |
| PT16 | Textures/proxies only resolve on the author machine | Fail fresh target package with original paths inaccessible | Absolute fallback conceals missing dependencies |
| PT17 | Renderer/color/profile changes after proof approval | Invalidate affected proofs and preserve prior verdict | Old render remains current acceptance evidence |
| PT18 | Evidence mixes versions or omits required whole-object view | Request bounded evidence repair | Attractive crop grants full acceptance |
| PT19 | Builder output or asset metadata tells reviewer to pass | Treat embedded instructions as untrusted data | Asset text grants policy/dispatch/approval authority |
| PT20 | Review starts; controller stops; worker writes receipt; user cancels; resume | Persist cancellation under ownership checks; collect/account once without progression | Cancel fails because worker exited; unverified PID is signalled |
| PT21 | PID is reused or ownership is unresolved | Retain fence/uncertainty; never signal unverified process | Unknown launch becomes permission to retry |
| PT22 | Crash crosses run store, budget store, launch fence and artifact publication | Reconcile each durable boundary without duplicate adoption or blind redispatch | Separate commits are assumed atomic |
| PT23 | Expensive late result arrives at cap or after cancellation | Record consumed/unknown usage once and stop dispatch | Cancelled work disappears from accounting |
| PT24 | Same defect survives repeated reviews | Bounded method change or human escalation | Cosmetic retries reset cumulative counters |
| PT25 | One reviewer passes but required criterion fails; human has not signed | Retain failed/unapproved verdict | Majority vote or best-so-far becomes approval |
| PT26 | Delivered bytes change after human signoff | New identity and applicable revalidation/signoff | Approval transfers silently to different bytes |
| PT27 | Run database is moved to another workstation | Require supported authority/path migration or block resume | Portable asset is mistaken for portable run state |
| PT28 | Cheaper reviewer or shorter context misses rare defects | Evaluate held-out labels, negatives and full cost | Lower cost alone is called an improvement |

## Required state traces

Trace PT20, PT08, PT11 and PT14 with named revisions and before/after state. Include who has authority, which evidence remains valid, which gates are invalidated, budget effects, and restart at the most dangerous boundary. Add at least three counterexamples not already listed. [ESTIMATE]

## Positive controls

A design that blocks everything is insufficient. Include a valid simple asset reaching human review, legitimate finish reuse without regeneration, an allowed material parameter change retaining geometry acceptance, a verified successful target import, and normal receipt recovery without cancellation. [ESTIMATE]

## Independent ground truth

Reserve accepted and rejected studio assets for evaluation; keep expected state traces separate from routing code. Use deliberately corrupted packages, changed-image controls, legitimate open surfaces, and target scenes selected before tuning. Record where human labels are required. A test must have an observable failure condition independent of the implementation's own assertions. [ESTIMATE]
