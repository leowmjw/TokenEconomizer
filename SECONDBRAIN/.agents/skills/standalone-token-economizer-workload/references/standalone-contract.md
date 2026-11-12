# Standalone log-adapter contract

This reference belongs to `standalone-token-economizer-workload`. It defines a
portable offline boundary, not a benchmark harness configuration.

## Project tasks

The standalone project must declare these logical operations in `mise.toml`:

- `check`: parse/type/lint/test the package without network services;
- `run`: invoke the binary with forwarded arguments;
- `validate`: validate one log manifest and print a JSON summary.

Operators use `mise tasks`, `mise env`, `mise run check`,
`mise run validate -- ...`, and `mise run run -- ...`. Python dependencies and
scripts run through `mise exec -- uv run`; no direct system Python or project
virtualenv is assumed.

## Manifest

The binary reads one JSON manifest from stdin or a file passed by the run task:

```json
{
  "repository": "stable repository identity",
  "stream_id": "ordered-stream-name",
  "harness": "zed",
  "log_sources": [
    {"path": "/explicit/path/to/session-log.jsonl", "format": "jsonl"}
  ],
  "state_dir": "/explicit/writable/state-root",
  "model": "billed-model-id",
  "seed": 0,
  "policy_state": {}
}
```

`harness` is an adapter registry key. The generic package must not assume a
fixed Zed, Claude Code, or CommandCode home directory. Paths are explicit and
must not point into the state/cache output. A manifest with an unknown adapter,
missing source, duplicate source, path traversal, or unknown model is invalid.

## Conversation discovery and selection

Adapters expose conversation metadata separately from event replay. Each
metadata record contains at least:

```json
{
  "conversation_id": "session-1",
  "harness": "zed",
  "repository": "stable repository identity",
  "sequence": 42,
  "timestamp": "2026-01-02T03:04:05Z",
  "source_path": "/explicit/path/to/session-log.jsonl",
  "completed": true,
  "outcome_available": false,
  "usage_available": true,
  "outcome": null
}
```

`sequence` is preferred for ordering; an adapter may provide a timestamp when
sequence is unavailable. If neither is reliable, it must set an explicit
`ordering: "unknown"` marker rather than substituting filesystem mtime.
`source_path` is descriptive metadata and must remain within the declared log
sources. Unknown outcome or usage is represented by `null`/`false`, never by a
successful or zero-valued default.

The `list` operation returns at most the latest 10 completed conversations for
each configured or known adapter and never mutates policy state. `remembered`
or `review` is also read-only and reports the active, candidate, and retired
policy state plus evidence and missing-data reasons. The `train` operation
requires explicit `conversation_id` values. If none are provided, it must
present the discovery list and wait for an explicit human selection; discovery
alone is never consent to train. Summaries distinguish conversations that were
discovered, selected, read, and learned.

## Adapter output

Each adapter returns an ordered list of dictionaries. Required fields are:

```json
{
  "harness": "zed",
  "session_id": "session-1",
  "sequence": 12,
  "kind": "tool_result",
  "timestamp": null,
  "tool": "Read",
  "ok": true,
  "args": {"path": "src/example.py"},
  "error_signature": null,
  "edited_files": [],
  "test_run": false,
  "tools_loaded": [],
  "tools_used": [],
  "usage": null,
  "resolved": null,
  "fact_candidates": [],
  "raw": {}
}
```

`kind` is one of `session_start`, `prompt`, `tool_call`, `tool_result`, or
`session_end`. Fields not applicable to a kind are empty or `null`. Adapters
must preserve `session_id` and monotonic `sequence`; if the source lacks one,
they must assign a local sequence and record `sequence_source: "adapter"`.
`resolved: null` means unknown, never false. `usage: null` means unavailable,
not zero. `raw` may retain vendor fields but is never passed to a judge or used
as policy evidence.

A `fact_candidates` entry has:

```json
{
  "id": "canonical-check-command",
  "claim": "Use mise run check for repository validation.",
  "context_key": "tests-src",
  "exercised": true,
  "fired": true,
  "verdict": "confirm",
  "high_stakes": false
}
```

The adapter must not manufacture a candidate merely because a command appeared
once. It may emit candidates only when the source format itself provides the
necessary observation, or leave the list empty for the generic fold.

## Policy and result

The fold receives the prior policy state and returns a next state with facts,
tool evidence, loop signals, and `would_redirect` recommendations. It never
rewrites the input logs.

The binary writes exactly one JSON summary to stdout. At minimum:

```json
{
  "repository": "stable repository identity",
  "stream_id": "ordered-stream-name",
  "harness": "zed",
  "model": "billed-model-id",
  "source_digest": "sha256...",
  "sessions": 1,
  "resolved": 0,
  "unknown_outcomes": 1,
  "effective_execution_tokens": null,
  "mechanism_overhead_tokens": 0,
  "cost_status": "unknown",
  "would_redirect": 0,
  "contract_failures": [],
  "next_state_namespace": "..."
}
```

A summary is invalid if it silently changes source order, treats missing
resolution/usage as a successful zero, or merges different harness/model
bases. State writes are atomic and use a separate namespace for each
repository/harness/stream combination.
