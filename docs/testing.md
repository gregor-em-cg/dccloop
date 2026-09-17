# Testing and evidence boundaries

The public snapshot preserves runtime code and executable expectations. Two historical document citations and their preservation hashes receive the documented public redaction in `verification/PUBLIC_REDACTIONS_v1.json`; no runtime/scenario change is involved. The checks separate genuine local-process execution from simulations and geometry predicates, without launching a native application or provider. [repo tools/run_checks.py:1] [repo verification/PUBLIC_REDACTIONS_v1.json:1]

## Complete local check

From the repository root:

```sh
python3 -B tools/run_checks.py
```

This wrapper invokes the existing harnesses from `prototypes/local`, leaves their detailed outputs in ignored local directories, and writes a compact summary to `verification/local-test-results.json`. It returns nonzero on an unexplained failure. [repo tools/run_checks.py:1]

Individual commands, from `prototypes/local`:

```sh
python3 -B -m tests.run_current_contract --run-suites
python3 -B -m tests.test_native_integrity
python3 -B -m unittest tests.test_fluted_candidate_v4 -v
```

## Why some retained rows fail

The frozen current-contract acceptance expects the original literal-input suite to report 120/125 and the completed-input suite 124/125. Four literal cases lack explicit complete-review starting records. P11's original blocked/outcome_unknown expectation conflicts with the later explicit durable-cancellation contract. These historical failures remain visible; they are not converted into individual passes. [repo prototypes/local/fixtures/current_contract/current-contract-v1.json:1]

The acceptance harness checks the exact failing IDs, assertions and persisted states; rejects any extra failure; requires Stage 1.1 and CLI regression cases to pass; and runs a separate CURRENT-P11 positive control. It also checks preservation of 44 baseline files. A different failure, missing control or changed frozen input must fail acceptance. [repo prototypes/local/tests/run_current_contract.py:95] [repo prototypes/local/tests/run_current_contract.py:163]

## What the checks establish

| Check | Execution scope | What would fail it |
|---|---|---|
| Current mock contract | Real local mock Python workers, controller interruption/cancel/resume and synthetic policy inputs | Wrong state, extra job, duplicate receipt/accounting, bad ownership behavior, changed expectation or unmapped failure. [repo prototypes/local/tests/run_current_contract.py:1] |
| Native integrity guards | Deliberately simulated host/receipt inputs plus an actual Python CLI ownership check; native dispatch blocked by a spy | Attempted dispatch, wrong rejection, unexpected signal, altered run state or changed budget. [repo prototypes/local/tests/test_native_integrity.py:1] |
| Geometry unit tests | Python mesh generation and independent geometric predicates | Missing/reversed/degenerate faces, wrong envelope, broken lanes, invalid-input acceptance or nondeterminism. [repo prototypes/local/tests/test_fluted_candidate_v4.py:1] |
| Frozen-input checker | File hashes against preserved manifests | Missing or changed declared input. This is preservation evidence, not functional or visual evidence. [repo tools/check_frozen.py:1] |

## Environments and exclusions

The initial public verification summary records the actual local platform and Python version used. The lightweight CI job checks frozen inputs and geometry predicates only; passing it does not establish portable controller recovery. [repo verification/local-test-results.json:1] [repo .github/workflows/checks.yml:1]

Not verified by this release: Windows operation, Blender execution in a fresh public clone, other DCC import/render behavior, real model-provider reliability/cost enforcement, host power loss, arbitrary-code isolation, independent-reviewer authentication or production visual quality. The native boundary's fixed Blender application path and process/filesystem assumptions need explicit adapter/platform work. [repo prototypes/local/native_adapter/core.py:12] [repo prototypes/local/native_adapter/job_host.py:1]

Product-contract, product-delivery and C4-scope tests depend on excluded historical product evidence and are not part of the public runnable suite. Historical local Blender results are context for the design, not fresh public-release execution. [repo prototypes/local/native_adapter/product_contract.py:34]
