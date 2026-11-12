---
name: emit-rote-ir-to-temporal
description: >-
  Emit and validate a runnable Temporal workflow from a completed
  SECONDBRAIN/COMPILED/<scenario>/pipeline.yaml without invoking rote-cli or
  importing rote at runtime. Use after compile-skill-to-rote-ir has produced a
  validated IR, real extracted implementations, tests, eval.yaml, report, and
  provenance. Also use to refresh Temporal output after pipeline changes,
  compare the local emitter procedure with the read-only upstream rote adapter,
  or run a scenario through the local Overmind Temporal stack.
---

# Emit rote IR to Temporal independently

Perform Phase 6 locally from a completed compiled scenario. The upstream rote
checkout is reference material only. Never modify it and never require it to
emit, start, or run the resulting workflow.

## Independence boundary

Do not run any of these commands:

```text
rote emit
rote compile
uvx --from rote-cli ...
python -m rote...
```

The generated runtime may depend on `temporalio`, but must not import `rote`.
Use `mise exec --` for project commands and `uv` for every Python environment or
script. The local Temporal CLI is `~/go/bin/temporal`.

The optional upstream checkout is read-only reference material:

- `SHARED-SKILLS/rote/src/rote/adapters/temporal.py`
- `SHARED-SKILLS/rote/src/rote/adapters/_common.py`
- `SHARED-SKILLS/rote/src/rote/adapters/_py_common.py`
- `SHARED-SKILLS/rote/src/rote/ir.py`
- `SHARED-SKILLS/rote/tests/test_temporal_adapter.py`

Read `references/parity-checklist.md` before emission. If upstream behavior has
changed, report the delta and update this skill or project-local runtime code;
do not patch the upstream checkout.

## Lessons learned / environment and packaging checklist

- Run dependency commands through `mise exec --`; `mise.toml` supplies the
  enterprise CA bundle via `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, and
  `CURL_CA_BUNDLE`. If the bundle is missing or stale, run
  `mise run refresh-local-tls-ca-bundle` before retrying PyPI access.
- In the sandbox or on a machine with a protected default uv cache, set
  `UV_CACHE_DIR` to a writable temporary directory such as
  `/tmp/secondbrain-uv-cache`. Never put that cache in the scenario output.
- A scenario-local `extracted/` directory must contain `__init__.py`; the
  worker dynamically installs that package even when the implementation module
  itself is present.
- Treat generated files as stale when they describe a different node set or
  reference nonexistent modules, even if an old manifest exists. Replace them
  only when their hashes match the manifest; otherwise stop for human review.
- If Overmind cannot start or bind localhost in the execution environment,
  fall back to the installed `~/go/bin/temporal` CLI directly, start the
  server with the Procfile's arguments, launch the worker separately, run one
  bounded workflow, and stop both processes in cleanup.
- `scripts/temporal_run.py --summary` has scenario-specific summary fields and
  may discard meaningful output for other scenarios. For generic validation,
  run without `--summary` and inspect the full JSON result.
- Fan-out activities receive `{<bound input key>: item}` (for example
  `inputs: {drill: run_drill.output}` gives `{"drill": item}`). A judge
  `signature_spec.input_schema` must have that wrapper key; with
  `extra="forbid"` a flat schema fails at runtime. Fix it in the compiled
  artifacts (signature, `signature_spec`, evals, tests), not in the emitter.
- Temporal's default activity retry policy is unlimited. Upstream rote emits no
  `RetryPolicy` when IR `retry` is absent, so a deliberate refusal (org not
  established, auth required) would loop forever. Emit
  `RetryPolicy(maximum_attempts=1)` for nodes without IR `retry`, and list it
  as a parity difference.
- A `hitl_gate` whose description says it is auto-satisfied (for example when
  an upstream status is `resolved`) waits only in the unresolved branch and
  passes `{}` otherwise. Bound the wait with the gate `timeout`, and raise a
  non-retryable error on timeout.

## Runtime locations (resolve per checkout; never assume)

Two paths can differ between machines and checkouts. Resolve both before
Step 4 and state the values in the report.

| Variable | Meaning | Resolution order |
|---|---|---|
| `SECONDBRAIN_ROOT` | The checkout whose `COMPILED/<scenario>/` you emitted into. The worker loads the scenario from here. | 1. The current project's `SECONDBRAIN/` root, if it holds `COMPILED/<scenario>/pipeline.yaml`. 2. The value the user gives. |
| `TEMPORAL_RUNTIME_DIR` | The checkout holding `scripts/temporal_worker.py`, `scripts/temporal_run.py` and `Procfile`. | 1. `$SECONDBRAIN_ROOT` if it has `scripts/temporal_worker.py`. 2. A sibling checkout the user named earlier (known: `$HOME/GOMOD/go-agent-context/SECONDBRAIN`). 3. Otherwise **ask**; do not guess. |

The two may be different checkouts. The worker only needs `SECONDBRAIN_ROOT`
to contain `COMPILED/`. Pass absolute paths. In tool environments that limit
the working directory to the project, call the runtime scripts by absolute path
from the project root. If file-reading tools can't reach the runtime checkout,
use `cat` in the terminal.

### Worker dependencies (`WORKER_WITH`)

The worker script declares only `temporalio`. Build the extra `--with` list
from what the emitted activities import at runtime:

- `--with pydantic` when any `signatures/*.py` or `extracted/*.py` imports
  pydantic;
- `--with anthropic` (or `openai`) only when a judge calls the model and its
  key is set (check presence only, never print it);
- any other third-party import found in `extracted/` (AST scan).

Run the worker as `uv run <WORKER_WITH> --script "$TEMPORAL_RUNTIME_DIR/scripts/temporal_worker.py"`.
The runtime Procfile's `worker:` line runs plain
`uv run --script scripts/temporal_worker.py` and cannot take extra `--with`.
When `WORKER_WITH` is non-empty, start the server and worker directly (see
Step 5) instead of using Overmind. Do not edit the runtime checkout's Procfile
unless the user asks.

## Inputs and outputs

Input:

```text
SECONDBRAIN/COMPILED/<scenario>/pipeline.yaml
```

Required neighboring compiler artifacts:

```text
extracted/__init__.py
extracted/*.py
eval.yaml
compile-report.md
provenance.json
tests/
```

Emit into the same scenario directory:

```text
activities.py
workflow.py
__init__.py
.secondbrain-temporal-manifest.json
```

Never overwrite `pipeline.yaml`, `extracted/`, tests, evals, reports, or
provenance during Phase 6.

## Step 1: Resolve one scenario

Resolve a named scenario to `SECONDBRAIN/COMPILED/<scenario>/`. Refuse path
traversal, absolute scenario names, or a directory without `pipeline.yaml`.
Confirm every required compiler artifact exists.

Read the entire pipeline. Record its name, version, node kinds, entry/exit
nodes, edges, input bindings, retries, timeouts, fan-out, loop bodies, MCP
bindings, signatures, and HITL signals.

## Step 2: Pre-emission validation

Before writing runtime files:

1. Parse YAML using a `mise exec -- uv run ...` Python environment with PyYAML.
2. Ensure node IDs are unique and every edge, entry, exit, and loop-body ID
   resolves.
3. Topologically sort the top-level DAG. Fail on cycles or forward input
   references.
4. For every `pure_function` and `external_call`, resolve `impl:` relative to
   the scenario directory. Parse the module with `ast`, confirm the callable
   exists, and confirm its keyword parameters can receive all `inputs:` keys.
5. Reject missing or `NotImplementedError` implementations. This emitter is for
   graduated pipelines, not stubs.
6. Confirm the four supported binding forms only:
   `pipeline.input`, `pipeline.input.<field>`, `<node>.output`, and
   `<node>.output.<field>`.
7. Confirm `eval.yaml`, `compile-report.md`, and provenance exist and the
   scenario tests pass.
8. Fail closed on a node kind or feature the local emitter cannot faithfully
   represent. Never silently drop retries, fan-out, HITL, signatures, agent
   loops, MCP bindings, mandatory nodes, or output fields.

A schema-valid IR with a dangling implementation is not emit-ready.

## Step 3: Deterministic emission rules

Emission is template expansion only. Do not reinterpret source-skill prose in
Phase 6; change the IR or extracted implementation first if behavior is wrong.

### Activities

Generate one Temporal activity for every executable top-level or loop-body
node.

For `pure_function` and direct-API `external_call` nodes:

- import the exact `impl:` symbol from `extracted.<module>`;
- call it with `**payload`;
- await an awaitable result, while allowing a synchronous deterministic
  function;
- recursively serialize Pydantic models, dataclasses, tuples, lists, and dicts;
- preserve the node ID as `@activity.defn(name="<node_id>")`.

Never generate `expected.extracted.*` imports. The implementation already lives
beside the emitted files under the scenario's `extracted/` package.

For other node kinds, follow the parity checklist and emit only when the full
contract is represented. If parity is incomplete, stop with the exact node ID
and unsupported feature rather than generating partial code.

### Workflow

Generate a workflow class whose registered Temporal type contains a stable
8-character hash of canonical behavior. Exclude source/provenance annotations
from the hash; include behavior-affecting fields.

The workflow must:

- execute topologically sorted waves;
- run independent nodes in one wave with `asyncio.gather`;
- construct each activity payload from `inputs:` bindings exactly;
- map IR timeout strings (`ms`, `s`, `m`, `h`, `d`) to Temporal durations;
- map `retry.max` to `maximum_attempts = max + 1`;
- return every exit node under its node ID;
- keep all nondeterministic I/O inside activities;
- implement HITL as Temporal signals plus durable `wait_condition`, never local
  polling or sleeps inside workflow code.

### Safe replacement

Hash each generated file. If an existing generated file differs from the hash
recorded in `.secondbrain-temporal-manifest.json`, treat it as user-edited and
stop. Do not overwrite it or create ambiguous `.new` files. Regeneration may
replace only files proven to be prior emitter output.

Write files atomically and update the manifest only after every output succeeds.

## Step 4: Static and import validation

Run all commands through `mise exec --`.

1. Parse generated Python with `ast` or `py_compile` without leaving
   `__pycache__` artifacts.
2. Verify generated code has no `rote` import.
3. Verify `activities.py` imports only real `extracted/` modules.
4. Load the scenario through:

```sh
UV_CACHE_DIR=/tmp/secondbrain-uv-cache mise exec -- env \
  SECONDBRAIN_ROOT="<SECONDBRAIN_ROOT>" \
  uv run <WORKER_WITH> --script "<TEMPORAL_RUNTIME_DIR>/scripts/temporal_worker.py" \
  --scenario <scenario> --validate-only
```

Validate-only imports the workflow and activity modules but not lazily
imported judge dependencies. A missing `WORKER_WITH` entry shows up only in
Step 5, so always run a bounded execution that reaches the judge.

Expected result: exactly one workflow and the pipeline's executable activity
count.

## Step 5: Local Temporal validation

**Option A: Overmind.** Use only when `WORKER_WITH` is empty. Run from
`<TEMPORAL_RUNTIME_DIR>`:

```sh
mise exec -- env \
  SECONDBRAIN_ROOT="<SECONDBRAIN_ROOT>" \
  ROTE_SCENARIO=<scenario> \
  overmind start
```

The Procfile starts `~/go/bin/temporal server start-dev` without
`--db-filename`, so persistence is in-memory, and starts the Python worker with
`uv`.

**Option B: direct.** Use when `WORKER_WITH` is non-empty or Overmind can't
start. Background both processes and write logs to `/tmp`:

```sh
~/go/bin/temporal server start-dev --headless --log-level warn > /tmp/temporal-emit/server.log 2>&1 &
UV_CACHE_DIR=/tmp/secondbrain-uv-cache SECONDBRAIN_ROOT="<SECONDBRAIN_ROOT>" \
  mise exec -- uv run <WORKER_WITH> --script "<TEMPORAL_RUNTIME_DIR>/scripts/temporal_worker.py" \
  --scenario <scenario> > /tmp/temporal-emit/worker.log 2>&1 &
```

Invoke a scenario with:

```sh
UV_CACHE_DIR=/tmp/secondbrain-uv-cache mise exec -- env \
  SECONDBRAIN_ROOT="<SECONDBRAIN_ROOT>" \
  uv run --script "<TEMPORAL_RUNTIME_DIR>/scripts/temporal_run.py" \
  --scenario <scenario> --input '<json>'
```

For HITL gates, start with `~/go/bin/temporal workflow start --type <WorkflowType> --task-queue <scenario> --workflow-id <id> --input '<json>'`.
Confirm it parks, read any emitted query, then use `temporal workflow signal`
and `temporal workflow result`. Also test one invalid gate answer: it must fail
once without retrying.

Always stop Overmind, or the direct server and worker processes, after a
bounded test. Remove any `__pycache__` the worker left in the scenario
directory.

### External-service safety

Offline tests must use temporary fixtures outside real cache directories and
must delete them. Never use fake future timestamps in a real project cache.

Before a live AWS scenario:

1. Read `AWS/AGENTS.md`.
2. Confirm the exact profiles and SSO instances from `AWS/AWS-config`.
3. Check session expiry with the approved `aws-sso ... list` command.
4. Login only to the required instance when expired.
5. Pass an explicit narrow `profiles` input. Do not rely on a broad default for
   a validation run.
6. Keep the checked-in allowlisted collector as the only AWS execution path.
7. Verify the resulting cache timestamp, region, account IDs, profile list, and
   errors before reporting success.

## Step 6: Report

Report:

- scenario and pipeline version;
- files emitted or preserved;
- workflow type/hash, activity count, waves, and task queue;
- resolved `SECONDBRAIN_ROOT`, `TEMPORAL_RUNTIME_DIR`, and `WORKER_WITH`;
- static/import/test results;
- whether validation was offline or live;
- exact live external-service scope, if any;
- upstream parity differences and whether this skill needs an update.

Do not call the workflow runnable until both scenario import validation and a
bounded local Temporal execution pass.
