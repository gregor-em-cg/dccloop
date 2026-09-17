# Contributing to DCCLoop

Help turn a small, inspectable prototype into a reliable cross-tool asset loop. Production readiness and multiple provider/DCC implementations are goals, not current claims. [ESTIMATE]

## Start with evidence

Open an issue that identifies the intended workflow, exact tool/version, failure trigger, expected outcome and evidence needed to decide. A new adapter proposal should state the capabilities it supports and rejects, its process ownership/cancellation model and its target-side acceptance test.

For a pull request:

1. Keep the change bounded and explain the resulting behavior.
2. Write independent positive and negative expectations before changing routing code.
3. Preserve existing failed results and immutable versions. If a specification is wrong, propose a versioned correction; do not silently change an oracle to fit the implementation.
4. Run applicable checks from [testing](docs/testing.md), and state what was actually executed, simulated, skipped or unverified.
5. Document any change to authority, receipt adoption, gate freshness, budget accounting or recovery.

The current prototype's frozen source and fixture manifests deliberately detect changes. Runtime evolution needs a versioned baseline and migration explanation; merely regenerating hashes is not acceptance. [repo prototypes/local/tests/run_current_contract.py:49]

## Protect the public boundary

Do not commit credentials, personal paths, session logs, run databases, commercial photographs, private customer assets or unlicensed materials. Use small synthetic inputs for regressions. The MIT license covers contributed project code/documentation; contributors must have permission to share their work.

Geometry/material development must use disposable copies, bounded native jobs and explicit permission for the chosen product/reference set. A proposed issue, review comment or image annotation does not authorize new paid/provider/native work by itself. [ESTIMATE]

## Useful early contributions

- A small public-domain or contributor-owned synthetic fixture with known dimensional and visual expectations.
- An explicit provider adapter contract with cost/error/cancellation receipts.
- A target-DCC import proof that validates hierarchy, units, pivots, material assignments and dependencies.
- A versioned material entry and controlled-variant test.
- Independent recovery counterexamples, including positive controls that still allow valid work to finish.

These are suggested contributions, not implemented features. [ESTIMATE]
