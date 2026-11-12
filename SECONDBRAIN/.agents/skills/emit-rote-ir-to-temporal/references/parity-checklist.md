# Temporal emission parity checklist

Use this checklist to compare the project-local emission procedure with the
read-only upstream rote adapter. The local skill remains authoritative for
SECONDBRAIN; upstream changes are candidates to review, not code to edit.

## Current behavior to preserve

- Stable workflow type suffix derived from canonical pipeline behavior.
- Topological execution waves and parallel `asyncio.gather` dispatch.
- Exact four-form input-reference grammar.
- Activity timeout parsing for `ms`, `s`, `m`, `h`, and `d`.
- Temporal retries count the initial attempt, so `maximum_attempts` is
  `retry.max + 1`.
- One activity name per executable node ID.
- Mandatory nodes are always scheduled.
- Exit nodes are returned by node ID.
- HITL gates use signals and durable wait conditions.
- Fan-out preserves source-list order.
- Workflow code performs orchestration only; external I/O stays in activities.
- Generated code imports scenario-local `extracted.*`, never `rote` and never a
  missing `expected.extracted.*` package.
- Emission never replaces compiler-owned implementations.

## Features requiring an explicit parity decision

For every occurrence in a pipeline, compare the current upstream implementation
and either implement equivalent local behavior or stop emission:

- `llm_judge.signature_spec`
- legacy Python `signature:`
- `agent_loop`, `termination`, `tools`, and `tool_servers`
- `loop_body`
- `fan_out`
- `hitl_gate`, `signal`, and notification metadata
- MCP-only external calls
- retry category semantics beyond Temporal's generic retry policy
- generated signature helper/runtime dependencies

Never call omission of one of these fields a successful emission.

## Upstream update review

When refreshing `SHARED-SKILLS/rote`, inspect changes only:

```text
src/rote/adapters/temporal.py
src/rote/adapters/_common.py
src/rote/adapters/_py_common.py
src/rote/ir.py
tests/test_temporal_adapter.py
tests/test_temporal_e2e.py
```

Record each behavior change as one of:

- already equivalent locally;
- adopt into this skill/runtime;
- intentionally different, with reason;
- unsupported, blocks affected pipelines.

Do not patch upstream files from this project workflow.

## Known intentional local difference

The upstream Temporal adapter historically generated imports under
`expected.extracted.*`, while SECONDBRAIN stores implementations directly under
`COMPILED/<scenario>/extracted/`. Local emission uses `extracted.*`. The generic
worker also maps legacy `expected.extracted.*` imports so older emitted
scenarios remain runnable during migration.

## Recorded parity decisions

First applied in `datadog-pipeline-stuck-detection` (2026-10-20).

- **No IR `retry` means one attempt (intentionally different).** Upstream emits
  no `RetryPolicy` for these nodes, which gives Temporal's unlimited default.
  Locally they get `RetryPolicy(maximum_attempts=1)`, so deliberate refusals
  fail once instead of looping. Nodes with IR `retry` also mark deterministic
  refusal types (for example `ValueError` and `AuthRequired`) as
  `non_retryable_error_types`.
- **Fan-out payload (equivalent locally).** Each element is sent as
  `{<bound input key>: item}`, matching upstream `fan_out_binding`. The judge
  input schema must have that wrapper key; otherwise emission is blocked until
  the compiled signature is fixed.
- **Conditional HITL auto-pass (adopted).** When a gate's description says it
  is auto-satisfied on a resolved upstream status, wait only in the unresolved
  branch. Use the gate `timeout`, and raise a non-retryable error on timeout.
  An optional `@workflow.query` exposing the gate question is a local addition.
- **Judge without a model key (intentionally different).** Upstream generates a
  signature module that calls the vendor. Locally the compiled signature owns
  dispatch and must return an explicit low-confidence verdict (for example
  `insufficient_evidence`, "LLM judge not run") when the key is unset. It must
  never raise `NotImplementedError` or guess. The judge's dependencies go in
  `WORKER_WITH` (see SKILL.md).
