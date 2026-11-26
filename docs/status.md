# Status

Branch: `main`. Last change: 2026-11-26 (Rig v2: orchestration-only 3 levels, R–I–G triad, operational primitives, and universal fronts). The history of the work is in the commit messages.

## What Rig is now

A kit and a guide for building **timeless, domain-agnostic instrumental agents**: a model that operates tools to do a defined job, with a strict three-layer split between **the Idea** (`.rig`, pure-Python engine & gates, `rigkit.py`), **the World** (thin target adapters), and **the Caller** (Agent Skill, stdio & Streamable HTTP MCP, OpenAPI 3.1, localhost approval UI, local plugin).

The pattern comes from a private production agent. Only the concept and the machinery are here; no material of that project.

## What exists

| Part | Where | State |
|---|---|---|
| The guide: method, three levels, build order, patterns, universal fronts, rules | `skills/rig/guide/` | updated for v2 |
| The skill and builder cheatsheet: one entry, a 1-page reference, one file per task | `skills/rig/SKILL.md`, `skills/rig/cheatsheet.md` | updated for v2 |
| The language, version 2 (`"rig": 2`): flow-only `unit <name>` (micro `tool`/`agent` scopes, `example`, `uses`, prefix-less `code` removed); AST-parsed Python/JS data literals (`[list]`, `(tuple)` with arity check, `{key: value}` `dict`, leaf `range` checks, `{group.name.key}` placeholders) and Python/TS types (`list[T]`, `tuple[T1, T2]`, `dict[str, T]`, `{k: T, opt?: T}`, `T?`, `"a" \| "b"`); structured `intent` (`audience`, `style`, `never [-> gate]`); first-class `reason` blocks (`mode careful\|creative`, read-only `tools` + `budget`, `candidates N`); `queue`; `ui` rules; `brief <keys>`; `rollback` alongside `finally`; AST-verified `tested`, inferred `R(...)` reads, gate literal warnings | `skills/rig/spec.md`, `rig.py`, the viewer, the grammars | in step, tested |
| The runner: short run ids (`r1`, `r2`, ...), input schema validation, automatic `intent` injection into `reason` & `model` gates, read-only `arena` tool calls with hard budget, loop-local soft-problem clearing in `until`, transactional `rollback`/`restore`, pluggable `queue` & chunked unattended `next-batch` (lock + circuit breaker + compact summary), `brief` artifacts + safe `artifact` inspection, ground-truth `eval`, two-tier `work` (`openai`, `ollama`, `anthropic`), stdio & Streamable HTTP MCP with Elicitation (`elicitation/create`), OpenAPI 3.1, localhost `/approve/<run>` & rule-control UI (`serve-http`), adapter helpers (`step`, `rpc_call`, `http_json`, `WorkerPool`) | `skills/rig/kit/rigkit.py` | tested |
| Project commands: `new [--level 1\|2\|3] [--template flow\|host]`, `build [--check]`, `doctor [--json]` (3 levels, `never` mapping check, AST gate check), `test [--replay]`, `plugin`, `mcp-config [--http URL] [--provider P]` | `skills/rig/rig_project.py` | tested at all 3 levels for `flow` and `host` templates |
| Agent Skill front (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode) | `rig.py build` | compiled and tested; live runs of v2 form not yet verified |
| Local-model front: LM Studio plugin with warm `serve-stdio` bridge, `waiting.next_action`, `ui_rules`, chat-scoped active run, `work_run` | `skills/rig/kit/templates/plugin/` | type-checked and tested via `try.ts` |
| Universal HTTP / MCP / OpenAPI front (`tool.py mcp`, `tool.py serve-http`, `rig.py mcp-config`) | `skills/rig/kit/rigkit.py`, `skills/rig/rig_project.py` | verified via stdio JSON-RPC, Streamable HTTP MCP, OpenAPI 3.1, and `/approve/<run>` tests; live external MCP/OpenAPI hosts not yet verified |
| The graph viewer: three lanes (`code`, `model`, `person`), `reason` nodes, `rollback`/`finally` boxes, structured `intent`, `ui` rule badges | `viewer/index.html`, `rig.py serve` | updated for v2; v1 checked in browser (2026-11-25) |
| The pattern example, level 3 (`release-tool`, structured `intent`, `never` mappings, `ui` rules) | `examples/release-tool/` | passes `build --check`, `doctor`, and 12 unit tests |
| Second example, level 2 (`band-facts`, `never` mapping) | `examples/band-facts/` | passes `build --check`, `doctor`, and 18 unit tests |
| Real tool, level 3 (`bookmarks`, `never` mappings) | `examples/bookmarks/` | passes `build --check`, `doctor`, and 30 unit tests |

Verification on 2026-11-26 (Rig v2):

- `python3 editors/build.py --check`: passes.
- `python3 -W default -m unittest discover -s tests`: all tests pass with 0 warnings (including `test_docs.py` link, removed-word, and `tool.py` docstring checks).
- `rig.py build --check`, `rig.py doctor`, and `rig.py test` pass on `examples/release-tool`, `examples/band-facts`, and `examples/bookmarks`.
- `rig.py new` at levels 1, 2, and 3 for both `--template flow` and `--template host` all pass their own `rig.py doctor`.

## Tested with real models

The full record of earlier v1 live runs is in [history/notes-2026-11.md](history/notes-2026-11.md) and in the notes of the examples.

- `examples/band-facts` (2026-11-15): Claude Haiku through the compiled skill, and a local Qwen 35B in LM Studio through the plugin.
- `examples/bookmarks` (2026-11-23, 2026-11-25): local Qwen 35B in LM Studio on synthetic and real exports, including `work.ts`.

## Not verified

- Live external MCP/OpenAPI hosts (Claude Desktop, Claude Code, Cursor, LM Studio, Open WebUI, AnythingLLM, Jan) against `tool.py mcp` and `tool.py serve-http`. Verified via automated unit and loopback HTTP tests only.
- Live `tool.py work` calls against real OpenAI-compatible, Ollama, and Anthropic endpoints (including two-tier routing and read-only `reason` arena loops). Verified via mocked HTTP unit tests only.
- Live browser check of the updated v2 viewer (`reason` nodes, `rollback` boxes, structured `intent`, `ui` badges) and `/approve/<run>` visual/diff UI.
- Editor TextMate grammar test (`editors/test-vscode.js`, `syntax_test_rig.rig`; needs `vscode-textmate`).

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
