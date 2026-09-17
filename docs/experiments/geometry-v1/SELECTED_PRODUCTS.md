# Selected geometry benchmark: Joriel and Ziven

The owner supplied these two product pages and confirmed “these two” for the new geometry benchmark. D01 and D02 are selected development products. No third commercial product is required. This records product selection, not a completed image freeze or authorization for an unspecified paid campaign. [obs]

## Published identity and scale

| Fixture | Product and source | SKU | Published width × depth × height | Derived metric dimensions |
|---|---|---|---|---|
| D01 | [Joriel Vase — Edward Martin](https://www.edwardmartin.com/products/joriel-vase) | 220121 | 14 × 14 × 14 in | 355.6 × 355.6 × 355.6 mm |
| D02 | [Ziven Bowl in Blue — Edward Martin](https://www.edwardmartin.com/products/ziven-bowl-in-blue) | 220106 | 14 × 14 × 6.25 in | 355.6 × 355.6 × 158.75 mm |

Source: the linked product pages’ Product Details panels, cross-checked with their public `productDetails` dimension records on 2026-09-16 Pacific time. SKU and dimensions are publisher claims, not physical measurements. [docs] Metric values are arithmetic conversions: each inch value × 25.4; these do not add measurement precision. [ESTIMATE]

## References inspected

- **D01 / Joriel:** one gallery image was exposed in the inspected page. The viewed image shows a rounded body, narrow neck, foot, vertical raised bands and repeated relief around the body/neck. [obs] [docs: Joriel product page above]
- **D02 / Ziven:** two gallery images were exposed and viewed: the whole bowl and a detail crop. They show an open interior, uneven rim, foot and projecting folded forms around the outside. The crop supplies detail, not an independent rear viewpoint. [obs] [docs: Ziven product page above]

Source image locators discovered on those pages:

| ID | Image URL | Inspection |
|---|---|---|
| D01-01 | [Joriel whole object](https://d26d755wulekqd.cloudfront.net/products/220121/d9f9c12d-4359-54d3-605f-f958a44808e2_pdp.jpg?f=webp&h=800&w=800) | Viewed on product page |
| D02-01 | [Ziven whole object](https://d26d755wulekqd.cloudfront.net/products/220106/5f65d02b-72ae-ef79-4300-90d925cd524b_pdp.jpg?f=webp&h=800&w=800) | Viewed on product page |
| D02-02 | [Ziven detail](https://d26d755wulekqd.cloudfront.net/products/220106/em_220106_ziven_bl_0001_1335ad35-3c6c-4559-84b7-732781a7fdf1.jpg?f=webp&h=800&w=800) | Viewed enlarged in gallery |

These are live locators, not frozen image bytes or content hashes. The page inspection did not obtain a finished 3D model or open the 3D viewer. No product photographs or native models are included in the public repository. [obs]

## Proposed product-specific geometry review

The following are modeling hypotheses and acceptance-profile requirements to freeze during E0, not measured properties of unseen surfaces. [ESTIMATE]

| Fixture | Protect in geometry | Parameter/editability probe | Failure the review should catch |
|---|---|---|---|
| Joriel | Body/neck/foot proportions; relief bands and transitions; visible rim/opening; relative placement of raised vertical elements | Change overall height independently of width, then adjust relief depth within a declared valid range; preserve identities and restore | Generic smooth vase that resembles only the outer silhouette; relief disappearing under neutral light; over-regularization of visible variation |
| Ziven | Rim profile; interior bowl and wall transition; foot contact; projecting folds, local cavities and attachment transitions | Change bowl height independently of width, then adjust one labeled fold’s projection; preserve neighboring protected geometry and restore | Flat surface decoration substituted for projecting geometry; closed/filled interior; disconnected folds, razor edges or unintended intersections |

Start with global proportions before detail. Represent required relief as geometry; a shader, normal map or color pattern cannot earn geometry credit. Where a handmade irregularity is visible, do not make perfect repetition an automatic quality requirement. Any procedural variation must be reproducible and supported by visible evidence rather than random decoration. [ESTIMATE]

Freeze a whole-object, side/alternate diagnostic, opening/interior and localized relief view set. Reference comparisons must distinguish actual camera correspondence from diagnostic views without photographic ground truth. Use the same neutral material, lighting and view settings across conditions. [ESTIMATE]

## Missing evidence and allowable conclusions

The inspected gallery does not establish exact rear/underside detail, full circumferential feature counts, cavity depth, wall thickness, bottom construction, exact relief dimensions or calibrated camera parameters. These remain unknown; neither a plausible completion nor a published overall dimension proves them. [obs] [ESTIMATE]

During intake, make an explicit known/inferred/unknown table and agree on acceptable hidden-surface approximations. If additional evidence is unavailable, test fidelity only where supported and label unseen construction as an approximation. A provisional asset is permitted if clearly labeled; a required unresolved fidelity criterion remains `needs_evidence`, not `pass`. Do not silently invent an extra reference or use the site’s finished 3D asset as the builder input. [ESTIMATE]

Before measured trials, save the chosen image versions in a separate campaign folder, record URL/retrieval time/format/resolution/SHA-256, freeze dimension tolerances and intended viewing scale, and bind that packet to each trial. Product selection is already complete; request only genuinely missing run/profile decisions together. Image publication rights are not inferred from product selection or the code repository’s MIT license. [ESTIMATE]

## Scope and next-agent entry point

Follow [COMMISSION.md](COMMISSION.md) and [AGENT_PROMPT.md](AGENT_PROMPT.md). E1–E3 develop the process using both selected products. E4 uses two sealed synthetic vessel/bowl geometries. Report commercial-product development acceptance separately from synthetic transfer; there is no unseen-commercial-product test in this two-product campaign. [ESTIMATE]

This intake inspected product pages, dimension data and three displayed reference images. It did not download/freeze reference image files, execute Blender, build geometry, run modeling comparisons, call a paid model provider or obtain human geometry approval. [obs]
