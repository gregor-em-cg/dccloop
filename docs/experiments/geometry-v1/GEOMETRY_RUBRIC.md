# Geometry acceptance and measurement v1

**Proposed rubric.** Freeze an asset-specific profile before comparing builders. The thresholds below are starting proposals for calibration, not measured production standards or current test outcomes. Existing controller fixtures/oracles are unchanged. [ESTIMATE]

## Separate four verdicts

Record `technical_validity`, `reference_fidelity`, `scene_usability`, and `human_geometry_approval` separately. Each required criterion is `pass`, `fail`, `needs_evidence`, or `not_applicable` with a reason frozen before candidate review. `needs_evidence` is not a pass. No mean score can erase a failed required criterion. [ESTIMATE]

Human approval identifies the exact candidate/package hash and intended usage. A reviewer model, good render, clean mesh report or valid ZIP cannot substitute for that decision. This is geometry approval only; later material/optical review may still require a scoped geometry revision. [ESTIMATE]

## Evidence bundle

Every bundle binds asset/brief/reference/profile/process/trial/candidate identities, immutable native bytes, inspection script and application versions, dimensions/unit convention, and view settings. Include whole-product orthographic/front-side views where meaningful, one fixed alternate view, close-ups of required geometry, wire/cage evidence and grazing-light detail. Show the intended usage scale as well as close-ups. Freeze the exact view list per fixture. [ESTIMATE]

Use the same capture protocol for all arms. No decorative materials, normal/bump/displacement maps, per-candidate exposure changes, post-render retouching or favorable crops replacing whole-object evidence. Record shading/subdivision modifiers because they affect the evaluated surface and scene cost. [ESTIMATE]

## Mandatory criteria

| ID | Criterion | Independent evidence and failure examples |
|---|---|---|
| G01 | Correct identity and part anatomy | Reference-labeled required parts/counts, relationships and negative spaces; fail missing/extra components or wrong assembly |
| G02 | Dimensions and proportions | Native world-space measurements against sourced values/uncertainty; separate inferred depth; fail undeclared scale adjustment or required tolerance breach |
| G03 | Silhouette and global form | Fixed multi-view comparison and registered measurements where calibration permits; fail a front-view match that breaks other views |
| G04 | Curves, geometric detail and continuity | Required-feature close-up plus intended-scale evidence; fail lost relief, irregular repeats, unintended facets, pinching or discontinuity |
| G05 | Contacts, gaps and intersections | Part relationships and independent cross-section/inspection where justified; fail floating/contact errors or unwanted visible penetration |
| G06 | Topology and surface validity | Normals, finite coordinates, zero-area/duplicate faces and category-specific surface checks; closed-solid rules only on declared closed parts |
| G07 | Editability and stable structure | Declared dimension/part edit, dependency audit, protected-part preservation and restore; fail unresponsive controls, hidden destructive dependencies or broken identities |
| G08 | Scene-use efficiency | Evaluated mesh/object/instance counts plus measured load/memory/update/capture behavior against the pinned scene profile; counts alone are insufficient |
| G09 | Reopen and evidence integrity | Fresh candidate/package reopen and artifact hash/binding checks; fail missing dependencies, stale/mixed candidate views or accidental source-file fallback |

All criteria above are proposed and require applicability/thresholds in the frozen asset profile. A claim of no self-intersections requires an appropriate check; passing manifold/zero-area tests alone cannot establish it. Unsupported inspection should remain unknown. [ESTIMATE]

## Quantitative measurement proposals

For synthetic fixtures, let `D` be the largest known ground-truth bounding-box dimension. Record raw units and normalized error; for example, dimension error is `abs(measured - target) / target`, and landmark error is Euclidean position error divided by `D`. Define alignment once using known scale/orientation. Do not fit nonuniform scale, mirror a candidate or deform it to improve the comparison. [ESTIMATE]

Initial calibration candidates: sourced synthetic dimension error at most 0.1%; annotated landmark error at most 0.5% of `D`; orthographic silhouette overlap at least 0.98 on preregistered known-camera views. These numbers are intentionally provisional. Demonstrate that valid controls pass and meaningful defects fail; revise them before E1 with a recorded rationale if necessary. Keep dimensional, silhouette and localized-detail checks separate. [ESTIMATE]

Optional synthetic surface distance must use a frozen, area-aware sampling/alignment method, with declared sample count and normalization. Report directional/region errors as well as an aggregate so a small missing feature is not hidden by a large correct surface. Do not equate a low average surface error with correct topology or editability. [ESTIMATE]

For real photos, use documented dimensions and approved uncertainty/tolerances. Freeze a shared camera estimate and sensitivity range before comparison. Quantitative image overlap is valid only within those declared calibration limits; otherwise use annotated ordinal judgments and report uncertainty. Do not infer exact hidden geometry from a single attractive image. [ESTIMATE]

## Visual rating anchors

Use blinded human ratings to describe G01/G03/G04/G05 alongside their hard verdicts: [ESTIMATE]

| Rating | Anchor |
|---|---|
| 0 | Wrong/missing structure or unusable result |
| 1 | Major discrepancy apparent in a whole-object view |
| 2 | Recognizable object, but a mandatory proportion/detail/contact still needs correction |
| 3 | Required geometry agrees at the declared use scale and close-ups; no unresolved mandatory defect |
| 4 | Same acceptance as 3, with especially convincing detail continuity and construction evidence |

Proposed acceptance requires every applicable visual criterion at least 3 **and** all its hard requirements satisfied. A 4 in one region cannot compensate for a 2 elsewhere. Calibrate ratings with accepted/rejected anchor examples before trials; record disagreement and obtain human adjudication rather than averaging it away. [ESTIMATE]

## Editability and performance probes

Preregister one meaningful dimension change and one component-level edit per asset. A proposed dimension probe is +10% within the declared valid range. Verify the intended change, unchanged protected parts, stable IDs/assignments and restoration on a disposable copy. Check semantic/evaluated geometry restoration independently; do not assume a resaved native file must be byte-identical despite metadata differences. Preserve the original candidate bytes separately. [ESTIMATE]

For a source-side load test, a proposed baseline is one asset and 25 instances/duplicates under a fixed assembly rule, same hardware/application and same scene settings. Record true instancing versus duplicated meshes. Warm up once, measure three repetitions, and retain the median/range. These are proposed diagnostic settings; studio acceptance limits must be supplied and frozen. Blender measurements do not certify Max performance. [ESTIMATE]

Optimization passes must satisfy the same G01–G09 requirements and preregistered tolerated change. Freeze a minimum meaningful performance improvement during E0 after measuring timing noise; do not declare a tiny fluctuation a win. If the required scene budget or noise bound is missing, mark G08 needs_evidence and report measurements without approval. [ESTIMATE]

## Evaluator checks and custody

Keep evaluator scripts, labels and expected outcomes separate from builder/routing code. Verify valid-positive, wrong-dimension, missing-part, flattened-detail, inapplicable-open-surface and stale-evidence controls. Record what would falsify each check. An evaluator that always approves or always blocks fails calibration. [ESTIMATE]

The final evaluator must not see builder rationale, treatment labels or earlier scores. Within-trial advisory review may guide the allowed correction, but it does not receive hidden target geometry or final validation labels. Record actual context/tool access; a role name is not proof of independence. If validation data is exposed for method tuning, retire it from the holdout set. [ESTIMATE]
