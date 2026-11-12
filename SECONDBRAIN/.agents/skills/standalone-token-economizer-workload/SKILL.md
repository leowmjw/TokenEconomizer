---
name: standalone-token-economizer-workload
description: >-
  Read coding-agent session logs from multiple harnesses as a standalone mise
  and uv binary, normalize them into one evidence stream, and apply the study's
  three learned cost controls: corroborated repository facts, evidence-gated
  tool pruning, and failure-loop redirection. Harness configuration and task
  execution are deliberately out of scope.
---

# Standalone TokenEconomizer log workload

Run an offline workload over the coding-agent logs that already exist for one
repository. The binary is a log reader and state fold, not an agent launcher:
it must not start Docker, an agent CLI, a benchmark grader, or a model merely to
replay a session. The same workload can consume logs from Zed, Claude Code,
CommandCode, or another harness through an explicit adapter.

The learned procedure is repository-scoped and conservative:

1. state is isolated by repository and ordered log stream;
2. facts enter a later session only after repeated, non-task-specific evidence;
3. a tool is removed only after it was loaded and repeatedly unused, never when
   it is protected or has ever been used;
4. a failing turn is redirected only when it shows sustained errors and
   repeated failure, while productive progress is left alone;
5. every paid proposer/judge/redirect call already present in the logs is
   included in the same billed-cost ledger;
6. every decision is reversible: facts can retire, tools can be restored, and a
   redirect is advice, never termination.

## Inputs and adapter boundary

The workload input is a JSON object with:

- `repository`: stable repository identity;
- `stream_id`: ordered stream name;
- `harness`: adapter label such as `zed`, `claude_code`, or
  `commandcode`; labels are data, not a hard-coded list;
- `log_sources`: explicit files or directories to read, with no assumed home
  directory, cache, or vendor path;
- `state_dir`: writable state root, outside source checkouts and dependency
  caches;
- `model`: billed model identifier for cache-aware cost weighting;
- optional `seed` and `policy_state` for reproducible replay.

Each harness adapter must produce the normalized event contract in
`references/standalone-contract.md`. An adapter may report unknown fields, but
must never silently reinterpret a missing outcome as success. If a Zed or
CommandCode format is not yet observed, keep its adapter contract-documented
and request a fixture; do not guess from a similarly named product.

The binary must not receive benchmark answers, gold patches, private grader
state, or task-execution configuration. It only reads logs and writes a
machine-readable summary plus an atomically updated policy snapshot.

## Default CLI behavior and transparency

The default command is read-only discovery, not training. It lists the most
recent **10 completed conversations per configured/known harness adapter**,
with harness, conversation ID, repository, timestamp/sequence, source path,
outcome availability, and token-usage availability. The limit is a visible
constant and can be overridden explicitly. Do not silently search guessed home
folders: the user or a project config supplies log roots.

Use explicit commands with these semantics:

- `list`: enumerate recent conversations; never mutate policy state;
- `remembered` or `review`: show the current facts, evidence, active/injected
  status, retired facts, tool exclusions with their evidence, loop-envelope
  statistics, missing-data reasons, and the exact source namespaces that
  produced them;
- `train --conversation <id> ...`: train only from the conversations the user
  selected. If no selection is supplied, present the recent list and wait for
  the user's selection; never treat "last 10" as implicit consent.

Training is therefore a deliberate human-in-the-loop transition. The summary
must distinguish `discovered`, `selected`, `read`, and `learned` conversations
so the user can audit what changed and reject a bad memory. A review command is
also read-only and must work when no policy state exists yet.

## Mise and uv execution contract

The workload is a standalone Python package:

- use `mise tasks`/`mise run <task>` for declared project operations;
- use `mise env` when inspecting the effective environment;
- run Python, tests, and scripts only through `mise exec -- uv run ...`;
- keep `UV_CACHE_DIR` outside the workload output, for example
  `/tmp/secondbrain-uv-cache`;
- do not create a second virtualenv, call `python` directly, or use `uvx` for
  project code;
- keep dependencies in package metadata/lockfile and make the binary entry
  point explicit in the `mise` task definition.

Before replaying logs, inspect the task surface and environment, then run the
narrowest checks:

```sh
mise tasks
mise env
mise run check
mise run run -- --input logs.json --state-dir .state
```

If the project exposes a different task name, use that declared task rather
than inventing a shell command. The run task must print machine-readable JSON
and return non-zero for a malformed manifest, unavailable adapter, unreadable
log, malformed event, or unknown billed model.

## Log replay lifecycle

### 1. Validate, discover, and isolate

Validate the manifest before opening a log. Reject empty repository or stream
identities, path traversal in `state_dir`, duplicate source paths, and an
unknown model. Preserve source order and the recorded session/task order;
never sort events by filesystem mtime or filename as a substitute for an
explicit sequence.

For `list`, ask each configured adapter for conversation metadata and return
at most the latest 10 per adapter by the adapter's explicit sequence/timestamp.
If the adapter cannot establish ordering, mark the order unknown rather than
using filesystem mtime. For `train`, require explicit conversation IDs or a
human selection from that list. A selection gate is skipped only when the user
already supplied IDs.

Create a state namespace from repository identity, harness, and stream ID. Do
not share learned state between unrelated repositories. Baseline and
 economized analyses must use separate state roots unless the caller is
explicitly replaying one historical state transition.

### 2. Read through the named adapter

The adapter is the only harness-specific boundary. It opens the declared
sources and emits events such as session boundaries, prompts, tool catalog
loads, tool calls/results, edits, tests, errors, token usage, and completion
outcomes. It must preserve session IDs and sequence numbers.

Adapters should be small and fixture-tested. Zed, Claude Code, and CommandCode
may have different JSONL, SQLite, or transcript shapes; do not put their
parsers in the generic learning logic. If the source format exposes no
resolved outcome or token breakdown, record `null` and a reason in the event.
A missing field is not evidence that the task resolved or cost zero.

### 3. Normalize and validate events

Normalize every event to the portable schema. Reject malformed required fields
and retain unknown vendor fields under `raw` without allowing them to affect
policy. Normalize tool names only through an adapter mapping; never merge
similarly named tools from different harnesses without evidence.

The normalized trace must remain leakage-safe for learning and optional judges:
use tool names, command shapes, edited basenames, test markers, and normalized
error signatures—not file contents, edit bodies, issue text, answer data, or
secrets.

### 4. Fold repository learning

Update all three mechanisms only after a session is complete:

- **Facts:** consume adapter-provided candidate observations with a claim,
  detector outcome, and context key. A candidate needs three confirmations;
  code facts must be confirmed in distinct edited-file contexts. An ACTIVE fact
  is injectable only after at least four exercised observations and a firing
  rate of at least 40%. A contradiction retires a fact when its recency-weighted
  score falls below zero; a high-stakes fact retires on one clean contradiction.
  Facts are operating guidance, never task solutions or completion claims.
- **Tools:** update the loaded catalog, ever-used set, and consecutive unused
  streaks. Evidence is based on loaded-but-unused sessions, not static adapter
  guesses. The study defaults are ten prompts across at least two sessions, or
  five sessions of any length, before a tool is eligible for removal. Keep the
  protected work surface (shell, read, search, edit/write) and every tool ever
  observed in use. A restored use clears its exclusion.
- **Failure loop:** fold tool actions into a compact state: calls/turns, edits
  per file, distinct edited files, error outputs, test runs, and repeated
  normalized failure signatures. Do not classify a session as stuck merely
  because it is long or has changing failures.

The first session starts with no injected facts and no evidence-based
exclusions. A log-only replay records what the policy would have done; it does
not rewrite the historical transcript or pretend that a redirect was delivered.

### 5. Evaluate intervention policy

Use a free gate before an optional judge. The default gate opens only after
18 tool calls and either one repeated failure or eight error outputs. A strict
fallback requires at least 20 calls, four edits to one file or three edited
files, six error outputs, and repeated failures in at least 20% of failures.

If a judge verdict is present in the source logs, accept `stuck=true` only at
confidence `>= 0.7`. The first accepted stuck verdict would receive one
redirect per turn; record that recommendation as `would_redirect: true`, but
never mutate the historical log or terminate/retry it. If the turn remained
stuck, record a still-stuck notice for the operator. A separate live supervisor
is outside this skill and must not be inferred from offline replay.

### 6. Account for cost and summarize

For each session compute:

`effective execution + logged proposer/judge/redirect overhead`

using the billed model's cache-aware weights. Prefer the token breakdown:
uncached input at 1.0, cache reads at the model's cache-read ratio, cache
writes at the cache-write ratio, and output at the model's output ratio. Fall
back to `tokens_total` only for legacy results and mark that fallback. Unknown
model IDs fail closed. If usage is unavailable, emit `cost_status: unknown`
rather than zero.

Aggregate by exact harness, model, repository, stream, and seed. Never pool
Zed and Claude/CommandCode rows merely because they share a repository; report
the harness dimension and the adapter's missing-data counts.

Write a stable JSON summary containing the source digest, adapter, session/task
order, resolved/unknown counts, effective execution tokens, logged mechanism
overhead, facts injected or eligible, tool exclusions and evidence, loop
recommendations, contract failures, and the next policy state namespace.

## Failure and safety rules

- Fail open for one optional policy/judge field, but fail closed for malformed
  manifests/events, unavailable adapters, unreadable sources, and pricing
  ambiguity.
- Never infer a fact from one task or a tool's irrelevance from a static prior.
- Never claim a redirect happened when replay only computed that it would have.
- Never print secrets or raw credentials from logs.
- Keep state atomic and recoverable; never mutate source logs or repositories.
- Run offline tests with fixtures outside caches and remove temporary fixtures.

## Completion checklist

Before declaring a standalone log workload valid, verify:

1. `mise tasks`, `mise env`, and the declared `mise run check` succeed;
2. one fixture for each enabled harness adapter normalizes successfully;
3. unknown Zed/Claude/CommandCode fields remain explicit rather than guessed;
4. the first session has no learned exclusions or injected facts;
5. facts, tools, and redirect recommendations are observable and reversible;
6. logged mechanism overhead is in the same cache-aware cost basis as execution;
7. malformed logs fail non-zero and no benchmark harness configuration was
   copied into the standalone workload.
