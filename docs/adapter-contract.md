# Adapter contract proposal

This document proposes a capability boundary for future DCC and model adapters. It is not a published runtime API or a claim that any interchange format preserves arbitrary scenes. A new adapter should earn a narrow supported scope through tests. [ESTIMATE]

## Distinct responsibilities

| Boundary | Proposed responsibility | Must not own |
|---|---|---|
| Controller | Policy, budgets, ownership, revisions, dispatch authority, approval state | Unrecorded native edits |
| Model role adapter | Typed build proposals or evidence-bound review judgments | Process launch, policy changes, self-approval |
| DCC adapter | Declared native operations and machine-readable inspection | Unbounded creative continuation |
| Renderer adapter | Render declared views under a pinned profile | Silent camera, exposure, material, or geometry changes |
| Delivery adapter | Export/import mapping, dependency packaging, target-side checks | Assuming source-side validation proves target compatibility |

All table entries are proposed boundaries. Adapters can share an implementation where that keeps the system smaller; separate interfaces do not require separate services or permanent agents. [ESTIMATE]

## Capability declaration

A proposed declaration should identify application/version, adapter version, platform, renderer/plugins, supported operations and parameter limits, input/output formats, editable features preserved, process ownership mechanism, timeout/cancellation behavior, and known unsupported features. Unknown capability is distinct from supported capability. [ESTIMATE]

Start with typed operations such as inspect, build a declared fixture, edit an exposed parameter, render a fixed view set, export, import, and package. Expand only with acceptance examples and negative controls. Supporting trusted local scripts does not establish a secure sandbox for arbitrary generated code. [ESTIMATE]

## Job and receipt identities

The proposed production contract retains these logical fields; exact schema names and migration rules remain design work. [ESTIMATE]

| Record | Required meaning |
|---|---|
| Intent | Run/job/attempt identity; owner epoch; immutable inputs; operation; allowed changes; pinned adapter/profile; budget reservation; expected current candidate |
| Launch evidence | Verified process identity or provider job handle; dispatch state; fence/lease identity; start time; uncertainty when confirmation is missing |
| Receipt | Intent hash; attempt and launch identity; output/evidence hashes; actual or explicitly unknown consumption; execution outcome; provenance |
| Review | Candidate and evidence identities; criterion applicability; per-criterion judgment; localized defect; proposed correction scope; reviewer provenance |
| Delivery | Semantic asset/version; exact package identity; source-to-target mapping; dependencies; target validation; approval binding |

The existing mock store verifies receipt intent, attempt, epoch, ownership transfer, and artifact hashes. It rejects conflicting receipts for one attempt and records usage plus completion in a transaction. Treat that as a source anchor, not proof of end-to-end exactly-once native execution. [repo prototypes/local/controller/store.py:206]

At the external execution boundary, prefer a reconciled attempt with at-most-once result adoption and honest uncertainty over an unsupported exactly-once execution claim. A retry needs durable evidence that it is allowed and a new bounded attempt where appropriate. [ESTIMATE]

## Process and cancellation rules

The mock cancellation path records the run cancellation independently of whether the worker is alive or safe to terminate. The routing policy prevents reconciliation from revoking that cancellation. [repo prototypes/local/controller/store.py:246] [repo prototypes/local/controller/policy.py:26]

Every future adapter must define how to verify ownership before signalling a native process or cancelling a provider job. Unknown identity must preserve cancellation intent while leaving process termination unresolved. Late receipts should reconcile once, remain available for audit, and never advance gates or create follow-up jobs after cancellation. [ESTIMATE]

## Target-DCC contract

Freeze target versions and test actual import. Validate units, orientation, transforms, pivot/origin, part identity, normals, UV channels, instances, materials, dependency paths, and required editability. Check both a fresh single-asset import and insertion into a representative assembly scene. Unsupported features must be explicit failures or approved conversions. [ESTIMATE]

Keep stable semantic part IDs separate from display names. A studio profile supplies root/container structure, groups/layers, helpers, naming templates, namespace rules, and collision policy. Preserve a reversible source-to-target map and reject unexpected importer renaming when it breaks bindings. No example naming template is a universal studio convention. [ESTIMATE]

An interchange file, converted native package, and rendering proof are different artifacts. Validate package dependencies with source locations inaccessible. Copying a run database to another host is not an ownership migration protocol; portable assets and portable controller state require separate evidence. [ESTIMATE]

## Minimum conformance experiment

For a new adapter, freeze expectations before execution: a valid simple asset; unsupported operation; stale input; missing dependency; duplicate/conflicting receipt; interrupted launch; late completion after cancellation; naming collision; and a target-side units/material mismatch. Include a valid resume/import control so a permanently blocked adapter cannot pass. Report actual native execution separately from mocks and simulations. [ESTIMATE]
