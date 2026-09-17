# Reusable material design

The proposed material stage selects an approved reusable finish where possible, derives a controlled variant when necessary, and validates the resulting appearance in the intended renderer. A reusable semantic finish and an application's node graph are related but distinct records. This is a library design proposal, not an implemented catalog. [ESTIMATE]

## Entry and binding

| Proposed field | Purpose |
|---|---|
| Material ID and immutable version | Stable catalog identity and reproducible asset binding |
| Family, finish, provenance and approval | Discovery, intended use, source traceability and ownership |
| Appearance anchors | Approved reference evidence, sample conditions and known uncertainty |
| Physical scale and mappings | Units, UV requirements, texture scale and displacement assumptions |
| Textures and dependencies | Content hashes, channel meanings, color spaces, licenses and distribution constraints |
| Exposed parameters | Allowed values/ranges and which changes require approval |
| Renderer realization | Application/renderer versions, graph or recipe, supported features and validation evidence |
| Parent and change record | Derivation lineage without mutating an approved shared entry |

These are proposed semantic fields, not frozen schemas. An asset binding pins the material version and renderer realization; resolving an unpinned “latest” at delivery would undermine reproducibility. [ESTIMATE]

## Selection and controlled variation

1. Reuse an exact approved finish, checking mapping, scale and supported renderer profile.
2. If needed, create a permitted parameter variant and record its values.
3. For changes outside approved bounds, derive an isolated graph/material version with its parent and change scope recorded.
4. Review the asset-specific result; promote it into the shared catalog only through a separate library decision.

This is a proposed lookup order. Do not rebuild an existing finish simply because an agent can generate nodes. Do not edit approved shared graphs or maps in place to satisfy one asset. Pin transitive dependencies such as nested node groups and procedural assets as well as top-level material IDs. [ESTIMATE]

## Geometry dependencies

Geometry can be provisionally approved before final materials. Material proofs must still detect geometry-sensitive defects in transparent, reflective, displaced, woven, or thin surfaces. A graph edit that changes bounds, silhouette, contacts, required UVs, or evaluated geometry requests the appropriate geometry revalidation. Keep the old candidate and invalidate only evidence whose dependencies changed, with a recorded reason. [ESTIMATE]

Reference photography is not a direct material measurement. Record uncertain lighting, exposure, coating, scale, and viewing conditions. Validate angular response and controlled views where needed, rather than treating a single attractive match as universal physical truth. Proposed thresholds require calibration against accepted examples. [ESTIMATE]

## Cross-DCC alternatives to test

| Approach | What to investigate | Failure to expose |
|---|---|---|
| Author in source DCC, translate or bake | Graph-feature coverage, scale/color fidelity, editability and maintenance | Unsupported nodes silently become an approximation or default material |
| Select semantic finish, realize in target renderer | Authoritative studio library, diagnostic source representation and parameter mapping | Source preview is mistaken for target appearance proof |
| Maintain approved realizations in both | Version coupling, shared anchors and regression cost | One realization drifts while the other stays approved |

These alternatives are proposals, not compatibility assertions. Select the smallest approach that passes the actual studio workflow. Consult official version-specific documentation and native tests before asserting transfer support. [ESTIMATE]

## Material approval evidence

Require exact dependency identities, assigned part IDs, representative full/detail views, declared lighting/color/render settings, protected-part checks, and target-side appearance validation. Keep material reuse, asset appearance approval, and catalog publication as separate decisions. A permitted roughness change should have a positive control that retains geometry acceptance; silhouette-changing displacement should have a negative control that reopens it. [ESTIMATE]
