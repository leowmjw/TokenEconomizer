# Standalone TokenEconomizer workload

This directory is the compile workspace for the `standalone-token-economizer-workload`
skill. The workload reads coding-agent conversation logs that already exist; it
does **not** launch an agent, run a benchmark, invoke a grader, or modify a
repository checkout.

The learned controls are deliberately conservative:

- promote repository facts only after corroborated observations;
- remove tools only after loaded-but-unused evidence, never protected or used
tools;
- recommend a redirect only for sustained, repeated failure;
- account for logged proposer/judge/redirect usage on the same cache-aware cost
basis as execution;
- expose the remembered state so a developer can accept, reject, or inspect it.

## Current phase

This is the **skill/IR phase**. `pipeline.yaml`, extracted deterministic
functions, tests, and compiler reports are being prepared here. Temporal output
is intentionally out of scope for now. Harness adapters for Zed, Claude Code,
and CommandCode also require real fixtures before they can be implemented
without guessing vendor formats.

## Day-to-day developer workflow

The eventual standalone checkout should expose these `mise` tasks:

```sh
mise tasks
mise env
mise run check
mise run run -- --help
```

All Python execution belongs behind `mise exec -- uv run ...`; do not create a
second virtualenv, call system `python`, or use `uvx` for project code. Keep the
uv cache outside the workload output, for example:

```sh
export UV_CACHE_DIR=/tmp/secondbrain-uv-cache
```

### 1. Configure explicit log sources

Create a manifest that names the repository, ordered stream, harness adapter,
log source, state directory, and exact billed model. Do not rely on guessed
vendor home directories. A source may be JSONL, SQLite, or another format once
its adapter is implemented.

```json
{
  "repository": "~/src/my-repo",
  "stream_id": "daily-coding",
  "harness": "zed",
  "log_sources": [
    {"path": "/explicit/path/session.jsonl", "format": "jsonl"}
  ],
  "state_dir": "/explicit/path/.token-economizer-state",
  "model": "claude-sonnet-4-6",
  "operation": "list"
}
```

Use a stable repository identity rather than an ephemeral worktree path when
possible. Keep state outside source and dependency caches.

### 2. Discover recent conversations first

The default interaction is read-only discovery. It lists at most the latest
ten completed conversations **per configured/known adapter**, including:

- harness and conversation ID;
- repository and sequence/timestamp;
- source path;
- outcome availability;
- token-usage availability.

```sh
mise run run -- --manifest manifest.json list
```

Discovery is not consent to train. The workload must not silently select the
last ten conversations.

### 3. Review what is already remembered

Review is also read-only. Use it before training to understand the current
policy state:

```sh
mise run run -- --manifest manifest.json review
```

Inspect active, candidate, and retired facts; evidence and firing rates; tool
exclusions and why they qualified; loop statistics; cost unknowns; and the
repository/harness/stream state namespace. The summary distinguishes:

- `discovered`: visible in adapter metadata;
- `selected`: explicitly approved by the developer;
- `read`: actually replayed;
- `learned`: conversations that changed policy state.

### 4. Train only from explicit selections

Pass conversation IDs deliberately:

```sh
mise run run -- --manifest manifest.json train \
  --conversation session-2026-11-10 \
  --conversation session-2026-11-11
```

If no IDs are supplied, the CLI should show the recent list and wait for a
human selection. It must not infer that discovery means approval.

A training result is an offline replay. It records `would_redirect`; it never
claims that a redirect was delivered to the historical agent and never rewrites
the source transcript.

### 5. Inspect and validate state changes

Validate a manifest without replaying logs:

```sh
mise run validate -- --manifest manifest.json
```

Run the narrow local checks after changing adapters or policy logic:

```sh
mise run check
```

State updates should be atomic and namespaced by repository, harness, and
ordered stream. Keep baseline and economized analyses in separate state roots
unless intentionally replaying one historical transition.

## Multiple harnesses

Use one explicit adapter label and source set per invocation. For example:

```sh
mise run run -- --manifest zed.json list
mise run run -- --manifest claude-code.json list
mise run run -- --manifest commandcode.json list
```

Do not pool Zed, Claude Code, and CommandCode rows merely because they target
the same repository. Summaries retain the harness and model dimensions. The
label `commandcode` is treated as opaque until a real fixture establishes its
format; it is not assumed to mean Claude Code.

Adapters must normalize into the shared event contract. Missing outcome or
usage remains unknown, not false or zero. Unknown vendor fields may be kept in
`raw`, but raw transcript contents, secrets, file contents, answer data, and
benchmark state must not become learning evidence.

## What the policy learns

### Repository facts

A candidate needs three confirmations. Code facts also need distinct edited-
file contexts. An active fact is eligible for injection only after at least four
exercised observations and a firing rate of at least 40%. Contradictions can
retire facts; high-stakes facts retire on one clean contradiction.

### Tool pruning

The protected work surface includes shell, read, search, edit, and write
families. A tool observed in use is never excluded. Otherwise, removal requires
loaded-but-unused evidence: ten prompts across at least two sessions, or five
sessions of any length. Later use restores the tool's evidence status.

### Failure-loop recommendations

The free gate opens after 18 tool calls plus repeated failure or eight errors.
The strict fallback requires 20 calls, churn/scatter, six errors, and repeated
failures in at least 20% of failures. A logged judge is accepted only at
confidence `>= 0.7`. Offline replay emits a recommendation, not an intervention.

### Cost accounting

Known model IDs use cache-aware weights for uncached input, cache reads, cache
writes, and output. Logged proposer/judge/redirect usage is included as
mechanism overhead. Missing usage produces `cost_status: unknown`; unknown
models fail closed rather than being silently mispriced.

## Adding an adapter

Do not implement a parser from memory. Add a fixture from the real harness,
then document:

1. how conversations are discovered and ordered;
2. how a conversation ID maps to a source;
3. how session boundaries, prompts, tools, edits, tests, failures, outcomes,
   and usage are normalized;
4. which fields remain unavailable and why;
5. offline tests for malformed and valid records.

The adapter is the only harness-specific boundary. The generic learning logic
must consume normalized events and remain unchanged.
