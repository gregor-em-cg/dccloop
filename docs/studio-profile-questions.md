# Studio profile interview

Use this after the initial design review to replace assumptions with a versioned delivery profile. The questions are prompts, not imposed studio rules. Begin with actual accepted and rejected examples that the studio has permission to share. [ESTIMATE]

## Decisions for the first experiment

1. Which target DCC, version, operating system, renderer, plugins, and render-farm environment do artists use? Are preview and production renderers different?
2. What does the studio call the material-development stage, and what inputs, outputs, and approval responsibilities does that term include?
3. Can you provide a permitted copy of one accepted asset, its materials, and a representative assembly scene? Is there a rejected example with documented reasons?
4. What exact root/container, layers/groups, part hierarchy, pivots, helper exclusions, and object/material/map/file names are required? Provide a scene-tree listing and two naming examples.
5. Which asset categories, output sizes, and closest viewing distances matter? Which features must be editable geometry, and which may be approximated, baked, hidden, or omitted?
6. What scene size, instance count, load time, viewport response, memory, and render-time limits define usable performance? Which machine and scene are the benchmark?
7. Where is the approved finish library today, who owns it, and what constitutes its authority: renderer graphs, measured samples, textures, or a combination?
8. Who approves geometry, materials, and final delivery? Who can authorize reopening protected geometry or accepting an approximation?

## Operational details

9. Is one editable asset expected, or a source master plus optimized scene variant? Which controls, instances, and modifiers must survive transfer?
10. Which transfer formats/conversion scripts already work, and where do they fail? Is a target-native package required?
11. What are the unit, orientation, origin/pivot, transform, normals, and smoothing conventions? Which post-import changes count as defects?
12. What UV-channel, real-world mapping, texel-density, texture resolution, color, and channel-meaning rules apply? Which depend on material family or renderer?
13. How are textures, proxies, caches, and plugins packaged and resolved on another workstation or farm? Which assets cannot be redistributed?
14. Which material parameters may vary without new approval? When does a derived finish become a separately approved library entry?
15. Which review evidence is mandatory: whole-object views, neutral shading, topology, close-ups, turntables, lighting sweeps, target-scene renders, or live manipulation?
16. How are multiple instances and variants inserted without identity, name, material, or namespace collisions? Are object names currently used as pipeline IDs?
17. How are corrections recorded, routed, and signed off? Which accepted components remain protected during a revision?
18. What are recurring per-asset time/cost and intervention limits? Separate pipeline development from modeling, materials, validation, and delivery.

## Reply template

- Target application / renderer / plugins / machines:
- Material-stage terminology and responsibility:
- Accepted/rejected examples and representative scene:
- Hierarchy and naming examples:
- Asset categories and viewing distances:
- Geometry / editability / performance criteria:
- Library authority and allowed variation:
- Transfer format / dependencies / units / color:
- Approval owners and escalation:
- Budgets and stop conditions:
- Unknown or requires testing:

Answers should refine the studio profile and first experiment. Supplying a profile is not itself authorization to launch a native build or publish an asset. [ESTIMATE]
