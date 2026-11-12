# SECONDBRAIN Agent Guidance

## Standalone TokenEconomizer workload

The workload is an offline log reader and policy-state fold. It does not launch
agents, run benchmark harnesses, modify historical transcripts, or require
Temporal during the current phase.

### Learned methodology

1. Discover completed conversations from explicit, harness-specific log sources.
2. Show recent conversations for review; never treat discovery as training
   consent.
3. Train only from explicitly selected conversation IDs or a human selection.
4. Normalize Zed/Claude/Codex/OpenCode/Pi events into one leakage-safe schema.
5. Learn conservatively:
   - facts need three confirmations; code facts need distinct edited-file
     contexts; injection requires four exercised observations and at least 40%
     firing;
   - tools are removable only after loaded-but-unused evidence; shell/read/
     search/edit/write and every observed tool remain protected;
   - failure-loop redirects require sustained calls, errors, churn/scatter, and
     repeated failures; offline replay records `would_redirect`, not a claimed
     intervention.
6. Account for cache-aware execution cost and logged proposer/judge/redirect
   overhead. Unknown usage stays unknown; unknown model IDs fail closed.
7. Keep state reversible and isolated by repository, harness, and ordered stream.
8. Expose discovered, selected, read, learned, active, retired, excluded, and
   unknown state in the review summary.

## Completed

- Extracted the standalone skill at
  `.agents/skills/standalone-token-economizer-workload/`.
- Compiled the Phase 1–5 IR at
  `COMPILED/standalone-token-economizer-workload/`.
- Added `pipeline.yaml`, `eval.yaml`, provenance, compile report, and developer
  README.
- Implemented and tested deterministic manifest validation, consent/selection,
  event normalization, fact lifecycle, tool evidence, failure-loop detection,
  cache-aware cost accounting, and review summaries.
- Added contract-documented adapter stubs so no vendor log format is guessed.
- Validated the IR, eval sidecar, implementation symbols, AST/provenance, and
  six offline tests.
- Kept Temporal emission, live supervision, and the original study checkout out
  of scope and untouched.

## Remaining work

1. Build real harness adapters using fixtures from each harness. Do not infer
   formats or paths from memory.
2. Add the standalone package/binary entry point and project `mise` tasks for
   `check`, `validate`, `list`, `review`, and `train`.
3. Add fixture-backed adapter tests, malformed-log tests, ordering tests, and
   missing-outcome/usage tests.
4. Persist policy snapshots atomically and expose review/reset behavior.
5. Recompile the IR when adapter contracts or source skill behavior changes.
6. Only after adapters and bounded offline runs are reliable, consider emitting
   Temporal runtime code.

## Adapter priority

Implement adapters in this order:

1. **Zed**
2. **Claude Code**
3. **Codex**
4. **OpenCode**
5. **Pi**

For every adapter, implement the full path before moving to the next:

1. Identify the real log source format from supplied fixtures.
2. Implement conversation discovery with explicit sequence/timestamp ordering.
3. Implement selected-conversation reading.
4. Normalize prompts, tool calls/results, edits, tests, errors, outcomes, and
   token usage.
5. Preserve unknown fields without using raw transcript data as policy evidence.
6. Add valid, malformed, ordering, missing-data, and multi-session tests.
7. Run the common deterministic fold against the adapter output.
8. Document unsupported fields and data-quality limitations.

Do not pool harness state merely because conversations target the same
repository. `commandcode` remains an opaque label unless a fixture establishes
its identity; the current adapter roadmap uses the explicit Codex, OpenCode,
and Pi labels above.
