# Current mock contract clarification v1

The owner explicitly adopted section 1 of the next brief. Accepted run cancellation must remain `cancelled/user_cancelled` despite unresolved worker identity. The job remains uncertain until a matching result establishes its outcome; cancellation cannot signal an unverified process, advance gates, or authorize follow-up work. Receipt collection and accounting remain permitted exactly once. [repo inputs/Blender_Build_Test_Refine_Next_Brief.md:13]

The original P11 expected `blocked` and asserted reason `outcome_unknown`. That expectation remains in its original fixture and historical test evidence. Current acceptance checks the actual SQLite cancellation state, worker uncertainty, unrelated-process survival, and late-receipt ineligibility under a separately versioned expectation. [repo tests/run_stage1.py:300] [repo fixtures/current_contract/current-contract-v1.json:1]

The earlier complete-review setup correction is retained in `fixtures/stage1_1/legacy-preconditions-v1.1.json`. It supplies explicit synthetic test starting records only; no runtime or historical database migration is authorized. Literal bare-G3 states are exercised as negative evidence and remain unable to create downstream jobs or signoff without supporting reviews. [repo inputs/Blender_Build_Test_Refine_Next_Brief.md:15] [repo fixtures/current_contract/current-contract-v1.json:1]

Current acceptance is housekeeping for this bounded native milestone. It makes no claim of native execution, visual quality, actual product approval, exhaustive safety, or acceptance of arbitrary historical failures. [repo inputs/Blender_Build_Test_Refine_Next_Brief.md:17]
