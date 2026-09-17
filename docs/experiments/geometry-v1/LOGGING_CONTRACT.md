# Campaign work, revision and usage log v1

**Required by the owner:** retain all work, revisions, what worked, what did not, why, and token/time consumption so later campaigns can refine the process. The requirements below are the proposed implementation contract for the executing agent. [obs] [ESTIMATE]

## Record as work happens

Use an append-only event ledger, plus a readable [learning log](LEARNING_LOG_TEMPLATE.md). The [event CSV](EVENT_LEDGER_TEMPLATE.csv) supplies columns; `RESULTS_TEMPLATE.csv` is a derived trial summary, and its `active_wall_seconds` means the union of that trial’s active intervals, not summed role time; an equivalent JSONL/transactional implementation is permitted if it preserves the fields and exports this view. Do not rely on an end-of-task recollection. Every attempt, including preparation, failed drafts, native retries, discarded candidates, review, optimization and delivery, belongs in the record. Do not reset it when a run resumes. [ESTIMATE]

Assign a stable `campaign_id`, `event_id`, logical `operation_id`, attempt ID, product/fixture, trial, revision and role. A native technical retry gets a distinct attempt under the same logical operation. A creative correction gets a distinct revision and consumes its creative allowance. Record intent/start before dispatch and the result afterward, with UTC timestamps and elapsed durations from a monotonic clock where available. Persist records before acknowledging completion. [ESTIMATE]

For each revision, preserve:

- Parent/candidate hashes and source recipe/prompt versions, intended change and geometric hypothesis.
- The triggering observation or numbered visual annotation, targeted criteria and protected criteria.
- Native actions actually performed, settings, tool/model versions, artifacts and comparison evidence.
- Before/after verdicts on every affected/protected criterion, regressions and reviewer/human decisions.
- What worked or failed, likely explanation, evidence supporting that explanation and competing explanations.
- A disposition: keep, reject, inconclusive or needs evidence; the next bounded hypothesis; scope in which the lesson applies.

A causal explanation must be labeled observed, source-backed or hypothesis. “The image looks better” does not establish why. If two variables changed, record the confound instead of claiming one caused the improvement. Preserve failed approaches and rejected candidates, not just winners. Version a changed rubric/protocol and explain the independent reason; never overwrite historical expectations to manufacture a pass. [ESTIMATE]

## Tokens and cost: raw receipts first

Record every model call across coordinator, builder, advisory review and final evaluation, including failed/cancelled/retried calls when usage arrives. Bind provider request/receipt IDs to operations; reconcile each receipt once, including late receipts after cancellation, without resuming creative work. Correct prior accounting using an appended correction event referencing the superseded event. Do not count both records. A canonical charge key uses provider, account/project scope and the authoritative billing/request ID. Attempt IDs are attribution metadata: an idempotent retry that returns the same billing identity across attempts is still one charge. If no authoritative identity exists, record the deduplication assumption and uncertainty; never invent a second charge to resolve ambiguity. Provisional, streamed and final usage for that same call are observations of one charge, not separate calls. Mark each observation as cumulative snapshot or additive delta and resolve a deterministic supersession chain; conflicting unresolvable records remain an accounting error. [ESTIMATE]

Retain input tokens, cached-input tokens, cache-write tokens where exposed, output tokens and reasoning tokens where exposed, **with the provider's inclusion semantics**. Cached inputs commonly form a subset of total input; reasoning can be included in output. Never add subsets again. If a provider uses disjoint billing categories, normalize them explicitly and retain the raw receipt and rule used. Leave an unavailable category empty with a reason. [ESTIMATE]

Use per-call usage when present. If only cumulative session counters exist, retain counter/session identity and raw snapshots; compute deltas once within each monotonic counter segment. Record resets, gaps and overlapping scopes. Never add cumulative totals repeatedly or add a parent aggregate to its already-included child calls. Allocating broad session usage to rounds by chronology is an estimate, not measured per-round usage. [ESTIMATE]

Report measured tokens separately from estimated tokens. Report uncached input, cached input and output billing categories separately when supported; document cache-write/reasoning inclusion. `total_tokens = input_tokens + output_tokens` only when those are the provider's complete, nonoverlapping categories. Do not calculate an apparently complete total while dropping unknown usage. [ESTIMATE]

If cost is requested, retain currency, rate source/date/model/tier and the exact billing formula. The ledger’s `accounting_formula_ref` must identify a hashed sidecar containing rate units, category inclusion and arithmetic; `cost_usd` is populated only for USD or a separately documented currency conversion. Separate a verified billed amount from a rate-based API-equivalent estimate. A subscription execution's equivalent token value is not an API invoice. Use `cost_basis` such as `provider_billed`, `api_equivalent_estimate`, `estimated_usage_and_rates`, or `unavailable`. Never substitute zero for unknown. [ESTIMATE]

## Time: distinguish elapsed time from effort

Record each operation's start/end UTC and duration; separately record native process runtime, role-active elapsed time, queue/wait time and human-review time when measured. Keep hardware/application versions for performance comparisons. Emit atomic active-start/active-stop events for pauses/resumes, or retain a hashed `active_intervals_ref` sidecar listing the intervals; aggregate active seconds alone cannot reconstruct overlapping time. Record interrupted intervals and use unavailable fields where a restart loses the timer. [ESTIMATE]

For each revision/trial, report start-to-finish wall time and active elapsed time. For the whole campaign, report start-to-finish wall time, active time as the union of active intervals, and summed role/native seconds as separate compute/work totals. Concurrent agent durations overlap: their sum is not campaign wall time. Do not add native time to active time when native work is already inside that interval. Work spanning idle days must not be reported as continuous active work. [ESTIMATE]

## Final breakdown and reconciliation

Produce machine-readable events and [trial results](RESULTS_TEMPLATE.csv), a usage/time summary by **product → phase → trial → revision → role**, and the human-readable learning report. These are alternative groupings of the same atomic records, not amounts to add together. Provide a separate shared bucket for calibration, orchestration, harness work and reporting. Charge shared costs once to the campaign; any allocation to products must show its rule and remain an estimate. [ESTIMATE]

The final report must include:

1. Every planned, attempted, completed, failed, cancelled, discarded and skipped trial, with reasons and actual native versus simulated work.
2. A revision timeline with linked visual evidence and before/after decisions, including unsuccessful approaches.
3. Product subtotals, shared subtotal and campaign total; measured/estimated/missing usage coverage and partial totals clearly identified.
4. Token categories, wall/active/native time and any cost basis, with reconciliation back to raw receipt/timer sources.
5. What to repeat, avoid or test next, each tied to trial/revision evidence and confidence; no unsupported universal lesson from two products.
6. Model/tool/prompt/profile versions, reproducible commands, source recipes and preserved artifacts needed to repeat a successful method.

Before delivery, independently reconcile unique charged calls/receipts against the event ledger, the ledger against trial totals, and all fixture/product subtotals (including synthetic validation) plus shared work against the campaign total. Include controls that must fail for a duplicated receipt, the same billing request replayed across retry attempts, omitted failed-call usage, a counter reset counted as new consumption, and overlapping agent time reported as wall time. These are required future logging checks, not tests executed by this planning task. Missing evidence must produce an incomplete-accounting verdict, never a synthetic all-clear. [ESTIMATE]

Keep raw prompts, receipts and product artifacts in the private campaign package. Publish only authorized/sanitized summaries; the full local learning record must remain resumable even if public disclosure is restricted. End with an explicit checkpoint listing completed work, unresolved failures, remaining budgets, next authorized step and resume command. Final acceptance and human approval stay separate from the existence of a complete log. [ESTIMATE]

Freeze this logging contract and its templates by hash in the approved campaign record. Version later corrections explicitly; preserve the prior rules and recompute derived summaries transparently from unchanged raw records. [ESTIMATE]
