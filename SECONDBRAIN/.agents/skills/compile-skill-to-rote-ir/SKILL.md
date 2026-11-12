---
name: compile-skill-to-rote-ir
description: >-
  Compile a SECONDBRAIN agent skill (SKILL.md + optional references/) into a
  runtime-agnostic rote IR (pipeline.yaml) under SECONDBRAIN/COMPILED/, ready
  for later Temporal emission. Two modes: (1) targeted — compile one named
  skill; (2) top-level — scan every skill under
  SECONDBRAIN/.agents/skills/ and recompile only those whose source changed
  since the last compile (or was never compiled). Stops at the IR; it does NOT
  emit runtime code. Trigger phrases: "compile this skill to IR", "compile
  <skill> to rote IR", "recompile skills to IR", "refresh the compiled IR",
  "check which skills need recompiling", "which IR is stale", "build
  pipeline.yaml for <skill>".
---

# Compile SECONDBRAIN Skill → rote IR

Turn a SECONDBRAIN skill into a rote intermediate representation
(`pipeline.yaml`). This is Phases 1–5 of the rote compiler run **inside Zed as
agent work** — no `rote` CLI, no Claude-Code slash command. Emitting runtime
code (Temporal, etc.) is a separate, later step and is explicitly out of scope
here.

**Authoritative compiler reference (read before compiling):**
- `SHARED-SKILLS/rote/skills/rote-compile/SKILL.md` — the seven-phase method.
- `SHARED-SKILLS/rote/skills/rote-compile/references/node-kinds.md` — the five
  node kinds and how to classify each step.
- `SHARED-SKILLS/rote/skills/rote-compile/references/ir-schema.md` — the exact
  `pipeline.yaml` schema (mirrors `SHARED-SKILLS/rote/src/rote/ir.py`).
- `SHARED-SKILLS/rote/skills/rote-compile/references/crystallization-heuristics.md`
  and `.../llm-judge-extraction.md` — for `pure_function`/`external_call`
  extraction and `llm_judge` signature design.

## Conventions

- **Source skills:** `SECONDBRAIN/.agents/skills/<skill>/` (a `SKILL.md`, plus
  optional `references/`).
- **IR output:** `SECONDBRAIN/COMPILED/<skill>/pipeline.yaml`. The IR lives
  outside the skill directory on purpose — it is not part of the skill spec.
- **Implementation workspace:** paths such as
  `impl: extracted/direction.py:derive_consumer_side_endpoints` are executable
  import targets relative to `SECONDBRAIN/COMPILED/<skill>/`, not pointers back
  to prose or to an existing project script. The file and symbol must exist.
- **Provenance:** `SECONDBRAIN/COMPILED/<skill>/provenance.json` records the
  sha256 of every source file the IR was compiled from, including linked local
  scripts/runbooks outside the skill bundle. This is what makes the top-level
  staleness check possible.

## Environment and cleanup lessons

- The canonical compiler references may be a sibling checkout, usually
  `../SHARED-SKILLS/rote/`, not inside `SECONDBRAIN`. Check that path (and
  `git check-ignore`) before reporting the references as unavailable. Do not
  remove the repository's intentional `SHARED-SKILLS` ignore rule merely to
  read a sibling checkout.
- Use the personal/default CA configuration first. Do not force the enterprise
  CA bundle on a personal machine; only investigate or use it after an actual
  TLS/certificate failure. If `uv` needs a writable cache, use a temporary
  cache under `/tmp`, never a project artifact.
- One-off regeneration, inspection, or conversion scripts and intermediate
  data belong under `/tmp`; delete them after use. Do not leave files such as
  `.recompile_ir.py` in `SECONDBRAIN`.
- After loading successfully, perform a semantic pass: every source check must
  remain represented; every node needs an exact `source.section`, valid
  `inputs:` bindings, and deterministic upstream `edges`; declare `entry_nodes`
  and `exit_nodes`; split MCP calls from post-processing and add `mcp:` only
  when the source names a real MCP tool. Resolve every `impl:`/`signature:`
  reference against the compiled directory and verify both the file and symbol
  exist. A schema-valid pipeline can still be semantically incomplete.

## Entry Modes

| Invocation | Do this |
|---|---|
| A specific skill is named ("compile `<skill>` to IR", or a path is given) | **Targeted mode** — compile just that skill. |
| No specific skill named ("recompile skills", "which IR is stale", "refresh compiled IR") | **Top-level mode** — scan all skills, recompile only stale/missing ones. |

---

## Targeted Mode

Compile exactly one skill.

1. Resolve `<skill>` to `SECONDBRAIN/.agents/skills/<skill>/`. Confirm
   `SKILL.md` exists. Read the complete skill bundle and follow every explicit
   project-relative file reference that supplies procedure, executable logic,
   schemas, safety rules, or output contracts (for example `AWS/AGENTS.md`, a
   runbook, or a named collector script). Record these as linked source
   dependencies; a command string alone is not enough to understand or track
   the implementation.
2. Run rote Phases 1–5 against it (Intake → Node Classification → Codification
   Scan → LLM-Judge Extraction → IR Assembly), following the compiler
   references above. Produce `SECONDBRAIN/COMPILED/<skill>/pipeline.yaml` and
   the Phase 5 `eval.yaml` sidecar.
   - Classify every step into exactly one node kind. Prefer the more
     deterministic kind when torn (`pure_function`/`external_call` over
     `agent_loop`).
   - Give every node a `source.section` naming the exact SKILL.md heading it
     came from — this provenance is what lets a future re-compile touch only
     changed sections. Do **not** set `content_hash` (that is rote's to stamp).
   - Phase 3 creates every `extracted/*.py` file named by an `impl:`. The path
     is relative to `SECONDBRAIN/COMPILED/<skill>/`, and the text after `:` is
     the callable symbol the adapter imports. With no verified ground truth,
     emit an honest contract-documented `NotImplementedError` stub; when the
     source already names a checked-in deterministic script or verified API
     contract, create a working wrapper/implementation and offline tests as
     required by rote's `references/implementation.md`. Never emit a dangling
     `impl:` or describe these files as Phase 6 work.
   - Phase 4 creates every Python `signature:` module and eval seed named in the
     IR. Runtime-neutral `signature_spec` remains mandatory for `llm_judge`
     portability.
   - Never silently drop a MANDATORY check. If prose requires a check you can't
     codify, keep it visible (a node with `mandatory: true`, or an open
     question in the report) — never omit it.
3. **Validate the complete Phase 5 workspace.** First load the IR with rote's
   own loader (local, no CLI command):
   ```sh
   # From SECONDBRAIN; use the sibling checkout if it exists.
   env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE -u CURL_CA_BUNDLE \
     UV_CACHE_DIR=/tmp/secondbrain-uv-cache \
     mise exec -- uv run --project ../SHARED-SKILLS/rote \
       --with pydantic --with pyyaml \
       python -c "from rote.ir import load_pipeline; load_pipeline('<abs path to pipeline.yaml>'); print('OK')"
   ```
   Use the enterprise CA only if the personal/default CA actually fails. Fix any
   validation error before continuing. Then resolve every `impl:` and legacy
   `signature:` relative to the compiled directory, import it, and assert the
   named symbol exists. Verify `eval.yaml` exists; when any implementation is
   working rather than a stub, run its deterministic offline tests. Do not run
   `rote emit` or claim the IR is adapter-ready while any reference dangles.
4. **Write provenance.** Recompute source hashes and write
   `SECONDBRAIN/COMPILED/<skill>/provenance.json` (format below).
5. Write `SECONDBRAIN/COMPILED/<skill>/compile-report.md` with the node count by
   kind, HITL gates, the Phase 3 crystallization records (source file and line,
   original rule, implementation target, and stub/working status), linked
   dependencies, and any open questions / judgment calls the human should
   verify. This is the human-readable explanation of what an `impl:` points to.

---

## Top-Level Mode (incremental refresh)

Compile everything that is out of date; skip everything that is current.

1. **List sources:** every directory under `SECONDBRAIN/.agents/skills/` that
   contains a `SKILL.md`.
2. **Classify each skill** as one of:
   - **missing** — no `SECONDBRAIN/COMPILED/<skill>/pipeline.yaml` exists.
   - **stale** — `provenance.json` is absent, any current source or linked
     dependency sha256 differs from the recorded one, a source file was
     added/removed, a recorded dependency disappeared, or a required Phase 3/5
     artifact (`eval.yaml`, `compile-report.md`, or any referenced
     implementation/signature/eval file) is missing.
   - **current** — provenance matches every source and dependency file exactly,
     and all required compiler artifacts resolve.
3. **Compute current hashes** for a skill like this:
   ```sh
   cd SECONDBRAIN/.agents/skills/<skill> && \
     find . -type f \( -name 'SKILL.md' -o -path './references/*' \) | sort | \
     while read -r f; do printf '%s  %s\n' "$f" "$(shasum -a 256 "$f" | awk '{print $1}')"; done
   ```
   Compare against `source_files` in the skill's `provenance.json`, then hash
   and compare every project-relative path in `dependency_files`. Re-scan the
   skill for newly added explicit local dependencies so adding a reference also
   makes the compile stale.
4. **Recompile only missing + stale** skills using **Targeted Mode** (steps
   2–5). Leave current skills untouched.
5. **Report a table**: skill | status (missing/stale/current) | action
   (compiled/skipped) | notes. State explicitly which skills were skipped as
   already-current so the no-op is visible, not silent.

---

## provenance.json format

```json
{
  "schema": "rote-ir-provenance/v1",
  "source_skill": ".agents/skills/<skill>",
  "ir": "pipeline.yaml",
  "ir_schema_ref": "SHARED-SKILLS/rote/skills/rote-compile/references/ir-schema.md",
  "compiled_at": "YYYY-MM-DD",
  "source_files": {
    "SKILL.md": "<sha256>",
    "references/<file>": "<sha256>"
  },
  "dependency_files": {
    "AWS/AGENTS.md": "<sha256>",
    "AWS/scripts/example_collector.py": "<sha256>",
    "RUNBOOK/AWS/example.md": "<sha256>"
  }
}
```

Keys in `source_files` are paths relative to the source skill directory.
`dependency_files` keys are paths relative to `SECONDBRAIN/`. Include only
local files actually read as compiler input, but include all of them. Adding,
removing, or editing any recorded input flips the skill to **stale** on the
next top-level run. If an existing v1 provenance file has no
`dependency_files`, treat it as stale when the skill names linked local inputs.

## Invariants

- **Compiler workspace only.** Emit the runtime-agnostic IR plus its required
  compiler artifacts (`extracted/`, `signatures/`, `evals/`, `eval.yaml`, tests
  when applicable, `compile-report.md`, and provenance). Never emit
  Temporal/Cloudflare/DBOS runtime code from this skill. Handing the completed
  workspace to an adapter is a distinct, later step.
- **The IR is the source of truth.** If a hand-edit and the IR disagree, the IR
  wins.
- **Deterministic over agentic.** When a step could be codified, codify it;
  reserve `agent_loop` for genuinely exploratory work.
- **Validate before declaring done.** A `pipeline.yaml` that does not load via
  `rote.ir.load_pipeline`, or whose `impl:`/`signature:` targets do not resolve
  to real symbols, is not compiled. Schema-valid dangling paths are failures.
- **Provenance is mandatory.** No IR is complete without a matching
  `provenance.json`; the top-level refresh is only correct if provenance is
  always kept in sync with the IR.

## Related

- `SECONDBRAIN/.agents/skills/emit-rote-ir-to-temporal/SKILL.md` — the
  project-local Phase 6 emitter. Use it after this skill completes; it does not
  invoke rote-cli or modify the upstream checkout.
- `SHARED-SKILLS/rote/src/rote/adapters/temporal.py` — read-only upstream
  reference used for parity review, not the SECONDBRAIN emission dependency.
- `SHARED-SKILLS/rote/skills/rote-compile/references/eval-estimates.md` — the
  `eval.yaml` sidecar, if/when you want the before/after cost scorecard.
