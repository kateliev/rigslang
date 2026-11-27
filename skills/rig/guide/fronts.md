# Fronts: one tool, several models

A tool has one core and several fronts. The core is the code and the catalogue. A front is the thin part that one kind of user talks to. All fronts call the same command line, so they all read the same knowledge.

```text
   Coding agents     a local model      MCP & HTTP/OpenAPI     a person
   (Claude, Codex,   (LM Studio         (tool.py mcp,          (CLI, /approve UI,
    Cursor, Gemini,   plugin)            tool.py serve-http)    graph viewer)
    Antigravity...)      │                       │                    │
      │                  │                       │                    │
   skill/SKILL.md    plugin/            JSON-RPC 2.0 / REST    /approve/<run>
      │                  │                       │                    │
      └──────────────────┴───────────────────────┼────────────────────┘
                                                 ▼
                                        python3 tool.py ...      one JSON line per call
                                                 │
                                     rigkit.py: walks the flow, keeps the run, refuses a wrong call
                                                 │
                                      gates.py  steps.py  gen/<name>.json
```

`RIG` is the path of `skills/rig/rig.py`. `python3 RIG build DIR` compiles every front.

## 1. The command line (the driver)

Every tool has `tool.py`. It is the only door to the tool. Runs get short sequential ids (`r1`, `r2`, ...).

| Call | What it does |
|---|---|
| `tool.py run '<inputs as JSON>'` | Start a run. Code walks the flow as far as it can. Options: `--preset NAME`, `--set group.name=value` (for this run only). Inputs are validated against their port schemas. |
| `tool.py batch '<JSON list>' [--report PATH] [--workers N]` | Start a run for each item of a list (or of a file). `--workers N` (default `1`) runs items in parallel threads while preserving `errors_stop`. |
| `tool.py next-batch [ITEMS] [--size N] [--report PATH]` | Run one chunk unattended (from `ITEMS` or the unit's `queue` step) under `runs/.batch.lock` and a consecutive-error/timeout circuit breaker. Rolls back and defers waiting items and prints one compact `summary` line. |
| `tool.py queues` | Open runs split into `left_for_model` and `waits_for_person` (via `runs/.waiting.json`), plus external `pending` items when `queue` is declared. |
| `tool.py answer RUN '<JSON>' [--node ID] [--meta '<JSON>']` | The model answers the node that the run waits at: `{"pass": true, "why": "..."}` for a gate, `{"result": ...}` for a step or reason block. `--node` refuses a stale call; `--meta` records metrics (`model`, `seconds`, `tokens`, `error`). |
| `tool.py arena RUN TOOL [JSON]` | Call a read-only tool declared on a waiting `reason` block, running on a deep copy of `state` under its hard `budget`. |
| `tool.py approve RUN [WORDS]` | A person answers a human gate: `yes` or `no`, or at a gate with `options`, the words of the answer (`yes` or nothing: the first option). |
| `tool.py restore RUN` | Run the unit's `rollback` block explicitly to restore state for `RUN`. |
| `tool.py artifact RUN NAME [--path KEY] [--offset N] [--limit N]` | Read-only inspection of a full payload saved by a step or reason block that declares `brief`. |
| `tool.py work RUN [--api-url URL] [--model NAME] [--provider openai\|ollama\|anthropic]` | Two-tier Python worker (stdlib only): routes `step ... by model` to the worker model and `reason` blocks to the reasoning tier (`--reason-api-url`, `--reason-model`, `--reason-api-key`, `--reason-provider`; env `RIG_*` / `RIG_REASON_*`). Supports `openai`, `ollama`, and `anthropic` APIs. |
| `tool.py mcp [--api-url URL] [--model NAME] [--approve-url URL]` | Zero-dependency JSON-RPC 2.0 stdio MCP server (with MCP Elicitation when advertised by the client). |
| `tool.py serve-http [--host 127.0.0.1] [--port 8780] [--reports DIR]` | Stdlib HTTP server exposing Streamable HTTP MCP (`POST /mcp`), OpenAPI 3.1 (`/openapi.json`), REST endpoints (`/api/*`), rule-bound UI controls (`/`), the flow graph (`/viewer?serve=1`), visual/diff human approval pages (`/approve/<run>`), and reports (`/reports`). |
| `tool.py serve-stdio` | Warm JSON-lines loop over stdin/stdout keeping Python and loaded modules warm (used by the plugin bridge). |
| `tool.py drop RUN [REASON]` | Mark a waiting run ended with outcome `dropped` so abandoned runs leave `queues`. |
| `tool.py list [--limit N]` | List runs, newest first (default 50). |
| `tool.py prune [--keep N]` | Delete old finished run folders beyond the newest `N` (default 20). Never deletes waiting runs. |
| `tool.py resume RUN` | Walk on after the process stopped (for example in the middle of a loop: it goes on from the next item). |
| `tool.py status RUN` | Show a run again. It also applies a timeout that ran out. |
| `tool.py rerun RUN --from ID [--set group.name=value]` | A new run with the state of the old run before the line ID (from `marks/<node>.json`), and changed rules. |
| `tool.py replay RUN` | Run the flow again with the answers recorded in RUN and the current code; print the differences of the end and the path. No model. `rig.py test DIR --replay RUN` does the same. |
| `tool.py rules` / `tool.py flow` | The values of the rules; the nodes of the flow. |
| `tool.py regress FILE [--baseline]` | Play the regression set. |
| `tool.py eval DATASET [--baseline PATH] [--save-baseline]` | Score a ground-truth dataset (quality metrics + wall time) and compare against a saved baseline. |

Each call prints one JSON line (except `serve-stdio` and `mcp`, which loop over stdio). The keys to read:

| Key | Meaning |
|---|---|
| `outcome` | The run ended: `end` is the id of the end node (or `error`, or `dropped`). |
| `waiting` | The run needs an answer: `node`, `kind` (`model`, `step`, `human`), the text of the node (`name`, `do`, `check`), and `sees`: the facts of the run that the node names. In a `for` block, `item` says which item. A step with an `out` type has `schema`; a human gate has `say`: the exact messages that answer it, for the model to show as they are (a human gate with options also has `options` and `default`); a node with a timeout has `timeout` and `since`. `waiting.problems`: what failed after the last answer at this node, so that the next answer can fix it. Plugin and MCP fronts replace CLI-only `waiting.answer` with a front-specific `waiting.next_action`. |
| `result` | With `outcome`: what the run made (the value of the step that leads to the end). A run that a gate ended has none. |
| `error` | Code failed: `node` and the error text. The run ended with the outcome `error`, and `finally` ran. |
| `refused` | The call is not allowed now. It is final. |
| `problems` | Every failed gate so far, as text. |
| `left` | The items of a `for` block that a gate left with `fail -> continue`, with the reason. |
| `note` | The flow changed since the run started. The run goes on with its own copy of the flow (`runs/RUN/flow.json`). |
| `guessed` | The gates that the model decided. |
| `path` | The nodes that the run went through. |

Two settings of the runner can be rules of the source: `run.errors_stop` (a batch stops after this many errors in a row; default 2) and `run.sees_max` (the longest text in `sees`; default 6000 characters).

Each run has a folder, `runs/<run id>/`, with a pinned copy of the flow and the rules, every answer, and per-node checkpoints in `marks/<node>.json` ([spec.md](../spec.md), section 4).

## 2. The Agent Skill front (any skill-capable coding agent)

`rig.json` names the skill file (`"build": {"skill": "skill/SKILL.md"}`). `rig.py build` compiles it with `--driver`, producing a lean ~50–65 line skill that works in Claude Code, Codex, Cursor, Gemini CLI, Antigravity, and OpenCode: the driver loop, a compact table of model, reason, and human nodes, a one-line summary of code stages, and the `Guessed:` rule.

Copy or link `skill/` into the agent's skills directory under the tool name. Any agent can also run `tool.py work RUN` with `--provider openai|ollama|anthropic` and optional `--reason-*` two-tier routing.

A large tool needs more than the compiled file: how to set up the host, how to review a batch, how to change a rule. Write these as extra files next to the compiled skill, **one file for each task**, and name them in the README of the tool. Keep the compiled `SKILL.md` as the entry, and never edit it.

## 3. The front for a local model: an LM Studio plugin

```bash
python3 RIG plugin DIR --owner NAME
```

This adds the folder `plugin/`: an LM Studio plugin. Its code is the same for every tool. `rig.py build` keeps the code and the README current; do not edit them. Everything about the tool comes from `plugin/src/gen/front.json`, which the build compiles:

- **The tools.** `start_run` (with the inputs of the unit), `answer_gate` (only when the flow has a gate for the model), `work_run` (when the flow has a `by model` step or `reason` block), `run_status`, `start_batch`, and `queues`. Presets and rules marked with `ui` are exported in `presets` and `ui_rules` and registered as per-chat plugin settings (`context.withConfigSchematics`), forwarding `--preset` and `--set` overrides on `start_run` and `start_batch`.
- **The rules text.** Short numbered lines injected before the first message of a chat.
- **The warm stdio driver.** `src/bridge.ts` keeps one persistent `tool.py serve-stdio` child process per session (with queued requests, timeouts, auto-restart, and fallback to one-shot spawn), avoiding Python startup cost on every tool call.
- **Self-directing `waiting.next_action`.** The bridge strips CLI-only `waiting.answer` and adds `waiting.next_action` so the model sees the exact next tool call (`work_run`, `answer_gate`, or `NONE` with `show_verbatim` at a human gate).
- **Chat-scoped active run.** The bridge tracks the last waiting run returned in the session, so `approve yes` resolves cleanly even when older waiting runs exist.

There is no tool for a human gate. The model can only show the operator what to decide. The operator answers with a chat message that starts with `approve`:

| Message | What it does |
|---|---|
| `approve r1 yes` | Answers run `r1`: yes. (Legacy `YYYYMMDD-HHMMSS-NN` ids are still accepted.) |
| `approve r1 no` | The same, no. |
| `approve r1 yes WORDS` | Yes, with words that the tool reads (for example the choices of a page). |
| `approve r1 WORDS` | At a gate with `options`: the answer. `approve r1 yes` takes the first option. |
| `approve yes`, `approve WORDS` | The short form, without the run id. Works when one run waits for a person, or when this session has an active waiting run. Otherwise the plugin refuses it and names the waiting runs. |

The `say` text of a result that waits gives the long form, with the short run id (`approve r1 <words>`). The model shows it as it is, so the operator can copy it.

The plugin runs such a message before the model sees it (`operatorAnswer` in `src/bridge.ts`), and the model gets only the result. The model cannot do this: it is not a tool, and only a message of the operator goes through this step. A result that waits for a person also has `waiting.command`: the same answer as a command for a terminal, with the tool folder.

### The worker: jobs out of the chat

Every `by model` step has an `out` type and is a **job**: a small task with an answer of one form, often once for each item of a `for` block. The chat model does not do jobs. It calls `work_run` one time, and the worker (`src/worker.ts` in the plugin, or `tool.py work RUN` from the CLI/MCP) does them:

1. It reads what the run waits for (`status`).
2. It gives the job to the model in a **new, empty context**: a short fixed rules text, the `do` text, the `sees` values, and the `problems` of the last answer.
3. If the model hits `max_tokens` or outputs invalid JSON, the worker passes the actual error cause (`meta.error`) and timing/token metrics (`--meta '{"model": ..., "seconds": ..., "tokens": ...}'`) to `tool.py answer RUN ... --node ID`, so the retry prompt explains what went wrong and `answers.json` records the metrics.
4. It goes on until the run waits for a person, for a judgment of a `model` gate, or ends. It also stops after `max_calls` jobs, and when the same job fails five times in a row.

The chat stays short, and no job sees the history of another. Plugin worker settings live in `rig.json` under `"plugin": {"work": {...}}`:

| Setting | Default | Meaning |
|---|---|---|
| `think` | `false` | `true`: the model thinks first, then writes the JSON; the worker reads the JSON after the thinking. `false`: the answer is bound to the schema from its first token, so the model cannot think. |
| `max_tokens` | 4000 | The most tokens of one job, thinking included. A job that reaches it records the cap error in `problems`, and the worker asks again. |
| `max_calls` | 50 | The most jobs in one `work_run`. |

Choose `think` with a test on real items ([weak-model.md](weak-model.md), section 4): without thinking a small model is fast, but it often takes the easy answer.

From a terminal: `node --no-warnings work.ts RUN` uses the loaded LM Studio model, or `python3 tool.py work RUN --api-url http://127.0.0.1:1234/v1 --model <name>` uses any OpenAI-compatible server with standard-library Python only.

Try the plugin without LM Studio:

```bash
node --no-warnings try.ts
```

```bash
node --no-warnings try.ts start_run '{"item": "a longer item"}'
```

`try.ts` uses the same bridge as the plugin, with you in place of the model. Use it to read the exact JSON that the model will see. `node --no-warnings try.ts say "approve yes"` sends a message of the operator.

A live run with the loaded model, without the chat window. Each `--then` is a later message of the operator in the same chat:

```bash
node --no-warnings agent.ts "the task" --then "approve yes"
```

### What a small model needs

A small local model is not a small frontier model. It follows a short list well, and a long text badly. [weak-model.md](weak-model.md) says how to design the jobs of the model for it; this list is about the front.

- **Few tools.** Each tool is one more thing to choose wrongly. The flow tools above are six at most, and a flow gets only the ones that it needs. Do not give the model a tool for each step: the runner does the steps.
- **A short rules text.** One line for each kind of result. The text of each decision arrives with the result (`check`, `do`), when the model needs it and not before.
- **The result says what to do next.** The model reads `waiting.next_action` and acts. It does not plan the flow.
- **Simple words.** Short sentences, one meaning for one word, the condition before the instruction. Write the `intent`, `check` and `do` texts of the source for the small model; the large model reads them just as well.
- **No tool where the model has no job.** At a human gate, `waiting.next_action` is `NONE`: call no tool, show `say` word for word, stop.
- **"Refused" is final.** Say it in the rules text. A small model repeats a failed call until it is told not to.
- **Do not invent.** Say that names and numbers come only from results.
- **One item at a time.** For many items, a loop in code runs them and gives the model a summary ([patterns.md](patterns.md), section 5).
- **Limits on the inputs.** A type and a range in the tool definition stop a wild value before it reaches the code.

Test with the model that will do the work. A text that a large model reads right can still fail with a small one.

## 4. Universal MCP (Stdio + Streamable HTTP) & OpenAPI 3.1

Any MCP host (Claude Desktop, Claude Code, Cursor, LM Studio, Windsurf) or HTTP/OpenAPI client (Open WebUI, AnythingLLM, Jan, workflow engines) can run any Rig tool with zero extra dependencies:

```bash
python3 RIG mcp-config DIR [--api-url URL] [--model NAME] [--provider openai|ollama|anthropic]
```

```bash
python3 RIG mcp-config DIR --http http://127.0.0.1:8780
```

```bash
python3 tool.py serve-http --port 8780
```

- **Stdio MCP (`tool.py mcp`) and Streamable HTTP MCP (`POST /mcp`):** expose `start_run`, `answer_gate`, `work_run` / `answer_step`, `arena_call` (when `reason` tools exist), `run_status`, `start_batch`, `next_batch`, `queues`, `drop_run`, `restore_run` (when `rollback` exists), and `read_artifact` (when `brief` steps exist).
- **OpenAPI 3.1 (`/openapi.json`) & REST (`/api/*`):** standard JSON endpoints wired to the unit's compiled input schema.
- **Universal human gates & visual review UI:** human gates are never exposed as model tools. When a client advertises MCP Elicitation (`capabilities.elicitation`), waiting responses attach `waiting.elicitation` (`elicitation/create`). When served over HTTP (or `--approve-url` is set), waiting responses also attach `waiting.approve_url` pointing to `/approve/<run>`, which renders the question, `sees` values, image galleries and before/after diffs, and one-click Approve/Reject/option buttons. The root `/` dashboard exposes `rule ... ui` controls wired to per-run overrides, and `/reports` serves batch reports.

## 5. The front for a person

- The command line (`approve`, `restore`, `next-batch`, `eval`) or the built-in localhost web UI (`tool.py serve-http`).
- The graph viewer: `python3 RIG serve NAME.rig --json gen/NAME.json` (or `/viewer?serve=1` on `tool.py serve-http`) shows the source as tables and as a three-lane graph (`code`, `model`, `person`), with `reason` nodes, `rollback`/`finally` blocks, structured `intent`, and `ui` rule badges.
- Editable stylesheets in `resources/`: `rig.py new` and `rig.py build` copy `viewer.html` and `viewer.js` (managed by the build) plus `viewer.css` and `http.css` into `<tool>/resources/`. Edit `resources/viewer.css` (colors, typography, `--graph-col`, `--graph-gap`, `--graph-lane-pad`) or `resources/http.css` freely per project; `rig.py build` keeps your changes, `rig.py build DIR --reset-css` restores the defaults, and both `rig.py serve` and `tool.py serve-http` serve your local CSS live.

## 6. A tool inside a host application

Use the built-in host template to split **the Idea** from **the World**:

```bash
python3 RIG new DIR NAME --level 3 --template host
```

- **`engine.py` & `gates.py`** stay pure Python with zero host imports; unit tests run anywhere.
- **`adapter.py`** holds all host quirks (JSON-RPC via `rigkit.rpc_call`, HTTP via `rigkit.http_json`, `@rigkit.step`, or `rigkit.WorkerPool`).
- **`rollback`** restores the host snapshot automatically on hard fail, error, or unattended deferral in `next-batch`, and explicitly via `tool.py restore RUN`.

## 7. What no front may do

- Hold a limit or a default of its own.
- Decide a gate, or change a verdict.
- Build code from the words of the model.
- Answer a human gate.
- Be edited by hand where it is compiled.
