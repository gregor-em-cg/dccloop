# Policy history retained in the public snapshot

This is a fresh public source snapshot, not a rewrite of the original project's history. Runtime code, executable policy, schemas and scenario expectations remain byte-preserved; private run archives and original reports remain outside the public repository. [repo verification/SOURCE_PROVENANCE.json:1]

## Public provenance redaction

Two historical policy-document citations contained personal absolute paths. Their public copies replace only those citations with explicitly withheld-source labels. The public synthetic preservation manifest changes those two document hashes, and the public baseline manifest changes the resulting freeze-file hash. Both original manifests remain under `verification/history/`; `PUBLIC_REDACTIONS_v1.json` records every original/public digest and structural comparison. No executable oracle or policy value changes. [repo verification/PUBLIC_REDACTIONS_v1.json:1]

## Durable CLI cancellation

The v1.1.1 repair persists an owner-authorized cancellation independently of whether the worker still exists or can be signalled. Signalling requires a verified identity. Later receipts can be collected and charged once without advancing a cancelled run or launching follow-up work. [repo prototypes/local/controller/store.py:246] [repo prototypes/local/controller/policy.py:203]

The regression fixtures include the actual CLI sequence: review starts, controller interruption, worker completion, cancel, resume. Positive controls require ordinary recovery to keep working. These are retained tests, not merely a policy description. [repo prototypes/local/fixtures/stage1_1_1/cli-cancellation-v1.1.1.json:1]

## P11 contract clarification

An accepted run cancellation remains `cancelled/user_cancelled` even if worker identity/outcome is unresolved. Worker uncertainty remains separately recorded; it never grants permission to signal an unknown process. The older P11 blocked/outcome_unknown oracle is retained, with a separate current-contract case and explicit acceptance mapping. [repo prototypes/local/fixtures/current_contract/CONTRACT_CLARIFICATION_v1.md:3]

## Explicit test preconditions

Completed-input fixtures supply synthetic complete-review starting records for cases whose literal setup was insufficient. They are not a runtime migration or permission to accept bare gate flags. Literal and completed results remain separate. [repo prototypes/local/fixtures/current_contract/CONTRACT_CLARIFICATION_v1.md:7]

## Image reproduction oracle

The retained portability clarification changes PNG comparison from whole-file equality to decoded pixels plus relevant format/color metadata, because incidental file metadata was not the intended image invariant. It preserves the old failure and requires a changed-pixel negative control. The native experiment is not rerun as part of this public release. [repo prototypes/local/fixtures/native-v1/PORTABILITY_CONTRACT_CLARIFICATION_v1.1.md:1]

These corrections constrain future changes: record real specification revisions explicitly, keep earlier evidence, and never weaken an oracle just to make an existing implementation pass. [ESTIMATE]
