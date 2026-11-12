# Compile report: standalone-token-economizer-workload

## Scope

This is a Phase 1–5 compile only. The source skill was extracted from the
TokenEconomizer study as a standalone log-reader workload. Harness launchers,
benchmark configuration, Docker, graders, answer keys, and Temporal runtime
files were intentionally excluded. The parent study checkout was not modified.

The pipeline is a log-replay DAG. It models the deliberate training path;
`list` and `remembered`/`review` remain read-only CLI front-end operations and
must not implicitly enter the training path.

## Pipeline inventory

| Node kind | Count | Nodes |
|---|---:|---|
| `pure_function` | 7 | `validate_log_manifest`, `determine_training_selection`, `resolve_training_selection`, `normalize_harness_events`, `fold_repository_learning`, `compute_cache_aware_cost`, `render_review_summary` |
| `external_call` | 2 | `discover_recent_conversations`, `read_selected_harness_logs` |
| `hitl_gate` | 1 | `select_training_conversations` |
| `llm_judge` | 0 | — |
| `agent_loop` | 0 | — |

There is one conditional HITL gate, `training_selection`, entered only when a
`train` request has no explicit conversation IDs. It presents the discovered
catalog and waits for explicit IDs. Discovery alone is never consent.

The pipeline has one entry node, `validate_log_manifest`, and one exit node,
`render_review_summary`. The two adapter calls are intentionally bounded to one
attempt because unavailable or malformed harness data must fail visibly rather
than loop.

## Phase 3 crystallization

| Source rule | Implementation | Status |
|---|---|---|
| Validate explicit repository/stream/harness/source/state/model manifest | `extracted/core.py:validate_log_manifest` | working, stdlib-only |
| List latest ten completed conversations per adapter | `extracted/adapters.py:discover_recent_conversations` | contract-documented stub; no real harness fixtures were supplied |
| Require explicit training selection | `extracted/core.py:determine_training_selection`, `resolve_training_selection` | working, stdlib-only |
| Read selected logs through named adapter | `extracted/adapters.py:read_selected_harness_logs` | contract-documented stub; no real harness fixtures were supplied |
| Validate normalized event contract and ordering | `extracted/core.py:normalize_harness_events` | working, stdlib-only |
| Corroborated facts and lifecycle | `extracted/core.py:fold_repository_learning` | working, stdlib-only |
| Evidence-gated tool pruning | `extracted/core.py:fold_repository_learning` | working, stdlib-only |
| Failure-loop gate and offline `would_redirect` | `extracted/core.py:fold_repository_learning` | working, stdlib-only |
| Cache-aware cost and mechanism overhead | `extracted/core.py:compute_cache_aware_cost` | working, stdlib-only |
| Transparent review summary | `extracted/core.py:render_review_summary` | working, stdlib-only |

The adapter stubs are not dangling references: their symbols exist and their
`NotImplementedError` messages identify the missing fixture/registry contract.
They must be replaced with fixture-backed adapters before any runtime emitter
can call the workflow runnable.

## Deterministic behavior covered by tests

`tests/test_core.py` covers:

- explicit-selection precedence and no-consent-by-default behavior;
- no injected fact on the first session;
- three confirmations, distinct contexts, four exercised observations, and a
  40% firing threshold for later injection;
- protected and ever-used tools never being excluded;
- ten prompts over two sessions qualifying an unused non-protected tool;
- repeated failure redirect recommendations versus changing failures;
- cache-aware usage, logged judge overhead, unknown usage, and unknown model
  failure;
- separation of discovered, selected, read, and learned conversations.

## Linked study dependencies

The IR was informed by the following parent-checkout sources. These are
reference inputs only; no code was copied into the parent repository or
modified there:

- `../README.md`
- `../docs/ARCHITECTURE.md`
- `../experiments/README.md`
- `../experiments/te_bench/facade.py`
- `../experiments/te_bench/runner.py`
- `../experiments/te_bench/mechanism_arms.py`
- `../tokeneconomizer/config.py`
- `../tokeneconomizer/microskills/stage.py`
- `../tokeneconomizer/microskills/distiller.py`
- `../tokeneconomizer/microskills/lifecycle.py`
- `../tokeneconomizer/microskills/observe.py`
- `../tokeneconomizer/toolprune/stage.py`
- `../tokeneconomizer/toolprune/tools.py`
- `../tokeneconomizer/loopguard/rules.py`
- `../tokeneconomizer/loopguard/state.py`
- `../tokeneconomizer/ledger.py`
- `../tokeneconomizer/pricing.py`

## Open questions

1. Real Zed, Claude Code, and CommandCode log fixtures are still needed to
   implement discovery and replay adapters. The compiler deliberately does not
   guess home directories, JSONL shapes, SQLite schemas, or transcript fields.
2. `commandcode` is retained as an opaque adapter label. It is not assumed to
   be Claude Code or any other product.
3. The compiled deterministic fold currently expects adapter-normalized event
   dictionaries. A concrete adapter must document how it establishes explicit
   sequence/order and which outcome/token fields are unavailable.
4. The eventual standalone package still needs its project-level `mise.toml`,
   binary entry point, and adapter registry. This compile workspace records the
   execution contract but does not invent harness configuration.

## Validation status

The Phase 5 workspace has been validated with:

- local `rote.ir.load_pipeline`: passed (`PIPELINE_OK`);
- local `rote.eval.sidecar.load_eval_estimates`: passed (`EVAL_OK`);
- extracted implementation symbol resolution: passed (`IMPLS_OK`);
- AST and provenance JSON parsing: passed (`STATIC_OK`);
- six offline stdlib unit tests: passed.

Temporal emission is intentionally deferred until adapters have real fixtures
and the compiled scenario satisfies the later emitter contract. The two
adapter implementations remain honest runtime-blocking stubs by design.
