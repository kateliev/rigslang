# Status

Branch: `main`. Last change: 2026-11-27 (RIGS v2.1: system and language named RIGS — Reason, Intent, Gate, Steps — where RIGS builds rigs defined in `.rig` files; updated VS Code & Sublime Text syntax grammars + automated `syntax_test_rig.rig` scope checks, externalized viewer & HTTP resources in `skills/rig/resources/`, external `__NAME__.rig` templates, rule ergonomics, JSON rules sidecar, `state["_rig"]` metadata, lean `SKILL.md`, per-chat LM Studio plugin settings, and nested `until` / `choice` fixes). The history of the work is in the commit messages.

## What RIGS is now

A language, a kit, and a guide for building **rigs** — **timeless, domain-agnostic instrumental agents** where a model operates tools to do a defined job, with a strict three-layer split between **the Idea** (`.rig`, pure-Python engine & gates, `rigkit.py`), **the World** (thin target adapters), and **the Caller** (Agent Skill, stdio & Streamable HTTP MCP, OpenAPI 3.1, localhost approval UI, local plugin).

The pattern comes from a private production agent. Only the concept and the machinery are here; no material of that project.

## What exists

| Part | Where | State |
|---|---|---|
| The guide: method, three levels, build order, patterns, universal fronts, rules | `skills/rig/guide/` | updated for v2 |
| The skill and builder cheatsheet: one entry, a 1-page reference, one file per task | `skills/rig/SKILL.md`, `skills/rig/cheatsheet.md` | updated for v2 |
| The language, version 2 (`"rig": 2`): flow-only `unit <name>`; compact `rules <group>` tables, inline `<min>..<max>` / open `0.._` bounds (`range 0 _`), external `rules "<path>.json"` sidecars, `reads <group>.*` wildcards, unquoted reserved words in `choice` rules (`off`, `true`, `none`); AST-parsed Python/JS data literals (`[list]`, `(tuple)`, `{key: value}` `dict`, leaf `range` checks, `{group.name.key}` placeholders) and Python/TS types (`list[T]`, `tuple[T1, T2]`, `dict[str, T]`, `{k: T, opt?: T}`, `T?`, `"a" \| "b"`); structured `intent` (`audience`, `style`, `never [-> gate]`); first-class `reason` blocks (`mode careful\|creative`, read-only `tools` + `budget`, `candidates N`); `queue`; `ui` rules; `brief <keys>`; `rollback` alongside `finally`; AST-verified `tested`, inferred `R(...)` and `until` `retry` reads, gate literal warnings | `skills/rig/spec.md`, `rig.py`, the viewer, the grammars | in step, tested |
| The runner: short run ids (`r1`, `r2`, ...), read-only `state["_rig"]` lifecycle metadata (`run_id`, `unattended`, `in_rollback`, `in_finally`, `rolled_back`, `end`), input schema validation, automatic `intent` injection into `reason` & `model` gates, read-only `arena` tool calls with hard budget, single- and nested-loop soft-problem clearing in `until`, transactional `rollback`/`restore`, pluggable `queue` & chunked unattended `next-batch` (lock + circuit breaker + compact summary), `brief` artifacts + safe `artifact` inspection, ground-truth `eval`, two-tier `work` (`openai`, `ollama`, `anthropic`), stdio & Streamable HTTP MCP with Elicitation (`elicitation/create`), OpenAPI 3.1, localhost `/approve/<run>` & rule-control UI (`serve-http`), adapter helpers (`step`, `rpc_call`, `http_json`, `WorkerPool`) | `skills/rig/kit/rigkit.py` | tested |
| Project commands: `new [--level 1\|2\|3] [--template flow\|host]` (external `__NAME__.rig` templates with `; >>> level N` blocks), `build [--check] [--reset-css]`, `doctor [--json]` (3 levels, `never` mapping check, AST gate check, editable stylesheet presence check, relaxed number-rule `note` check when `notes/` or `rules.json` exists), `test [--replay]`, `plugin`, `mcp-config [--http URL] [--provider P]` | `skills/rig/rig_project.py`, `skills/rig/kit/templates/` | tested at all 3 levels for `flow` and `host` templates |
| Agent Skill front (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode; rule `note`s omitted and >25-rule tables capped to `ui`/`permissions` + `<driver> rules`) | `rig.py build` | compiled and tested; live runs of v2 form not yet verified |
| Local-model front: LM Studio plugin with warm `serve-stdio` bridge, `waiting.next_action`, per-chat `presets` + scoped `ui_rules` schematics (`--preset` / `--set`), chat-scoped active run, `work_run` | `skills/rig/kit/templates/plugin/` | type-checked (`tsc --noEmit`) and tested via `try.ts` & `@lmstudio/sdk` |
| Universal HTTP / MCP / OpenAPI front (`tool.py mcp`, `tool.py serve-http`, `rig.py mcp-config`) | `skills/rig/kit/rigkit.py`, `skills/rig/rig_project.py` | verified via stdio JSON-RPC, Streamable HTTP MCP, OpenAPI 3.1, `/viewer`, `/http.css`, and `/approve/<run>` tests; live external MCP/OpenAPI hosts not yet verified |
| The graph viewer & external resources: three lanes (`code`, `model`, `person`), `reason` nodes, `rollback`/`finally` boxes, structured `intent`, `ui` rule badges; external `viewer.html`, `viewer.js`, and user-editable `viewer.css` (`--graph-col`, `--graph-gap`, `--graph-lane-pad`) & `http.css` copied into `<tool>/resources/` | `skills/rig/resources/`, `viewer/index.html`, `rig.py serve` | updated for v2; v1 checked in browser (2026-11-25) |
| The pattern example, level 3 (`release-tool`, structured `intent`, `never` mappings, `ui` rules) | `examples/release-tool/` | passes `build --check`, `doctor`, and 12 unit tests |
| Second example, level 2 (`band-facts`, `never` mapping) | `examples/band-facts/` | passes `build --check`, `doctor`, and 18 unit tests |
| Real tool, level 3 (`bookmarks`, `never` mappings) | `examples/bookmarks/` | passes `build --check`, `doctor`, and 30 unit tests |

Verification on 2026-11-27 (RIGS v2.1):

- `python3 editors/build.py --check`: passes (both `rig.tmLanguage.json` and `Rig.sublime-syntax`, with column-level scope assertions in `editors/sublime/syntax_test_rig.rig` verified in `unittest`).
- `python3 -W default -m unittest discover -s tests`: all 141 tests pass with 0 warnings (including `test_docs.py` link, removed-word, and `tool.py` docstring checks, `syntax_test_rig.rig` grammar scope checks, external viewer/HTTP resource preservation tests, `@lmstudio/sdk` config schematics, and loopback HTTP `serve` / `serve-http` tests).
- `rig.py build --check`, `rig.py doctor`, `rig.py test`, and `tsc --noEmit` pass on `examples/release-tool`, `examples/band-facts`, and `examples/bookmarks`.
- `rig.py new` at levels 1, 2, and 3 for both `--template flow` and `--template host` all pass their own `rig.py doctor`.

## Tested with real models

The full record of earlier v1 live runs is in [history/notes-2026-11.md](history/notes-2026-11.md) and in the notes of the examples.

- `examples/band-facts` (2026-11-15): Claude Haiku through the compiled skill, and a local Qwen 35B in LM Studio through the plugin.
- `examples/bookmarks` (2026-11-23, 2026-11-25): local Qwen 35B in LM Studio on synthetic and real exports, including `work.ts`.

## Not verified

- Live external MCP/OpenAPI hosts (Claude Desktop, Claude Code, Cursor, LM Studio, Open WebUI, AnythingLLM, Jan) against `tool.py mcp` and `tool.py serve-http`. Verified via automated unit and loopback HTTP tests only.
- Live `tool.py work` calls against real OpenAI-compatible, Ollama, and Anthropic endpoints (including two-tier routing and read-only `reason` arena loops). Verified via mocked HTTP unit tests only.
- Live browser check of the updated v2 viewer (`reason` nodes, `rollback` boxes, structured `intent`, `ui` badges) and `/approve/<run>` visual/diff UI.
- Native Sublime Text / `vscode-textmate` runner on `editors/sublime/syntax_test_rig.rig` (column assertions are verified by the pure-Python TextMate tokenizer in `tests/test_rig.py`; `editors/test-vscode.js` needs `vscode-textmate`).

## Open

| # | What | Note |
|---|---|---|
| 1 | Live host tests for v2 fronts | Verify `tool.py serve-http` (Streamable HTTP MCP, OpenAPI 3.1, `/approve/<run>`), `tool.py mcp` with Elicitation, and two-tier `tool.py work` (`openai`, `ollama`, `anthropic`) against live clients and models. |
| 2 | A guide-only build test | A fresh agent builds a small v2 tool from the skill, cheatsheet and guide, with no other help. |
| 3 | Bookmarks: full live run and link checker hook | Run `bookmarks` end-to-end on a real export and wire `steps.dead_links`. |
| 4 | Not in version 2 | Delay between retries; parallel flow branches; visual block editor in the viewer. |

## Where the old things are

- [history/](history/): the first memos, research notes, work orders of version 1 and the dated notes of 2026-11 ([history/notes-2026-11.md](history/notes-2026-11.md)).
- [plan-v2-proposal.md](plan-v2-proposal.md): the Rig v2 proposal (implemented).
