# Roadmap and readiness

The goal is a production asset loop that can gain support for additional models, DCC applications, and renderers through explicit adapters. The order below is a proposed validation sequence, not a release promise, execution authorization, or assertion of current compatibility. [ESTIMATE]

## Preserve the working baseline

Retain the local mock controller's pinned-policy, ownership, review-binding, receipt-adoption, and cancellation behavior while extending it. Its SQLite transaction boundary and cancellation code provide concrete source anchors. Proposed documentation must not silently replace existing executable fixtures or erase historical failures. [repo prototypes/local/controller/store.py:66] [repo prototypes/local/controller/store.py:246] [ESTIMATE]

Separate reproducible mock/controller tests from native adapter experiments, visual evaluation, and studio approval. A successful implementation test is not evidence that an asset meets a production brief. [ESTIMATE]

## Proposed stages

| Stage | Bounded work | Evidence needed to finish |
|---|---|---|
| 1. Review and studio profile | Challenge the contracts; inspect one approved and one rejected studio asset; resolve target DCC/renderer, naming, units, material authority and use case | Versioned profile with known unknowns, acceptance criteria and independent expected traces |
| 2. One cross-DCC asset path | Choose one authorized reference set; build geometry; reuse one finish; import into the actual target application; assemble a representative scene | Target-side fidelity, editability, hierarchy, naming, scale, performance, dependencies and human decision on the exact package |
| 3. Controlled material variants | Add one bounded parameter variant and one unique derived finish | Reuse succeeds; shared assets remain unchanged; out-of-range edits and geometry dependencies are caught |
| 4. Unified recovery boundary | Reconcile prototype/native seams; exercise interruption, cancellation, late receipt and uncertain launch cases | Independent expected state traces, actual process fault evidence, positive recovery controls and once-only accounting |
| 5. Model-provider adapter | Connect one explicitly authorized provider under finite budgets; preserve role and policy boundaries | End-to-end held-out quality evaluation, timeout/error handling, complete usage accounting and no self-approval |
| 6. Additional DCC adapter | Implement the same narrow conformance surface in a second application | A versioned capability matrix and target-native evidence for supported operations; explicit unsupported cases |
| 7. Production qualification | Widen asset families, scene scales and failure cases; establish operations/maintenance ownership | Representative held-out assets, measurable quality and performance limits, supported migration, auditability and studio signoff |

All stage entries are proposals. A failed dependency can return work to an earlier stage. Product acceptance should not wait for every future adapter, but the project must not advertise an untested application as supported. [ESTIMATE]

## First concrete experiment

After review and explicit native-execution authorization, use one selected simple asset plus a representative target scene. Freeze input references, expected identities, allowed approximations, target versions, material choice, output scope, and finite budgets before dispatch. Preserve the starting asset and use disposable outputs. [ESTIMATE]

Exercise a valid transfer, a deliberately missing texture, a units mismatch, and a naming collision. Verify that each negative control fails at the intended gate, then restore the valid package and show the positive control succeeds. Obtain a human decision separately from automated pass/fail results. [ESTIMATE]

## Decisions that should remain open

- Which DCC and renderer versions are the first production endpoint?
- Which scene-tree, naming, unit, color and asset-path conventions must be preserved?
- Is the authoritative finish represented by a target-renderer graph, measured sample/maps, or a semantic catalog with multiple realizations?
- What geometry/editability and scene-performance budgets apply to each intended use?
- Who can approve approximations, reopen geometry, promote materials, and publish an asset?
- Which trust boundary is required for generated code and third-party assets?
- How should supported run-state migration work across machines and versions?

These are design questions to resolve through the [studio profile interview](studio-profile-questions.md), not reasons to invent defaults or start a broad redesign. [ESTIMATE]
