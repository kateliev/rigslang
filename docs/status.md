# Status

Branch: `main`. Last change: 2026-11-26 (language version 1, kit and front improvements). The history of the work is in the commit messages.

## What Rig is now

A kit and a guide for building **instrumental agents**: a model that operates tools to do a defined job. The goal: the owner says "build tool X, look at this repository", and an agent builds it by the guide.

The pattern comes from a private production agent. Only the concept and the machinery are here; no material of that project.

## What exists

| Part | Where | State |
|---|---|---|
| The guide: method, levels, build order, patterns, fronts, rules | `skills/rig/guide/` | written, consolidated |
| The skill and builder cheatsheet: one entry, a 1-page reference, one file per task | `skills/rig/SKILL.md`, `skills/rig/cheatsheet.md` | written |
| The language, version 1: lines in flow order; blocks `for`, `until`, `if`/`else`, `section`, `finally`; gates `hard`, `soft`, `model`, `human` (`options`); `retry`, `timeout`, `fail -> continue`, `tolerate`, `by model`, required `out`, `range`, `gate.failed`; AST-verified `tested`, inferred `R(...)` rule reads, gate literal warnings | `skills/rig/spec.md`, `rig.py`, the viewer, the grammars | in step, tested |
| The runner: short run ids (`r1`, `r2`, ...), runtime input schema validation, per-node `marks/<node>.json`, `.waiting.json` queue index, `drop`, `list`, `prune`, parallel `batch --workers`, `answer --meta`, `serve-stdio`, Python worker (`work`), stdio MCP server (`mcp`), rerun, replay, refusals, reports, regression | `skills/rig/kit/rigkit.py` | tested |
| Project commands: `new`, `build`, `doctor [--json]` (L1 `example` execution, L2 AST checks & `out` check, L4 `permissions.*` default `off` + `hard` gate read), `test`, `plugin`, `mcp-config` | `skills/rig/rig_project.py` | tested at all four levels |
| The front for Claude: a lean compiled skill (~50–65 lines with `--driver`) | `rig.py build` | compiled and tested; live run of lean form not yet verified |
| The front for a local model: an LM Studio plugin with warm `serve-stdio` bridge, `waiting.next_action`, chat-scoped active run, and `work_run` with failure feedback and `--meta` metrics | `skills/rig/kit/templates/plugin/` | earlier plugin used with a real model (`agent.ts` 2026-11-23, chat window 2026-11-25); warm bridge & `next_action` type-checked and tested via `try.ts` |
| The front for any MCP host: zero-dependency JSON-RPC 2.0 stdio MCP server (`tool.py mcp`, `rig.py mcp-config DIR`) | `skills/rig/kit/rigkit.py`, `skills/rig/rig_project.py` | tested via stdio unit tests; live host not yet verified |
| The graph page: three lanes (code, model, person), the blocks as boxes, the path of one run; it has no parser, it draws what `rig.py` compiles | `viewer/index.html`, `rig.py serve` | checked in a browser (release and bookmarks, 2026-11-25) |
| The pattern example, level 4 (`if tone.failed`) | `examples/release-tool/` | passes `build --check`, `doctor`, and 12 unit tests |
| A second example, level 3, with what its runs taught | `examples/band-facts/` | passes `build --check`, `doctor`, and 18 unit tests; ran with two models |
| A real tool, level 4: clean up an Edge bookmarks export | `examples/bookmarks/` | passes `build --check`, `doctor`, and 30 unit tests; 23 nodes in version 1 (19 steps/gates including pure `step keep`, 4 ends; 35 in version 0) |

Verification on 2026-11-26:

- `python3 -W default -m unittest discover -s tests`: all 125 tests pass with 0 warnings. Five of those tests (`tests/test_docs.py`) guard the texts: every relative link resolves, no text uses a word of version 0, no `finish_<step>` tool name remains, and each `tool.py` docstring matches `Kit.cli`.
- `python3 editors/build.py --check`: passes.
- `rig.py build --check`, `rig.py doctor`, and `rig.py test` pass on `examples/release-tool` (12 tests), `examples/band-facts` (18 tests), and `examples/bookmarks` (30 tests).
- `rig.py new` at levels 1, 2, 3, and 4 all pass their own `rig.py doctor`.
- `tsc --noEmit` passes in `examples/bookmarks/plugin` and `examples/band-facts/plugin`.

## Tested with real models

The full record of each run is in [history/notes-2026-11.md](history/notes-2026-11.md) and in the notes of the examples.

- `examples/band-facts` (2026-11-15): Claude Haiku through the compiled skill, and a local Qwen 35B in LM Studio through the plugin tools and rules text (`agent.ts`). Every tool call was valid, and none was refused. The findings are in `examples/band-facts/README.md`.
- `examples/bookmarks`, version 0 (2026-11-23): the local Qwen 35B through the plugin code (`agent.ts`), on synthetic files. `approve` messages at three `human` gates, six sort batches, a fix from `waiting.problems`, and a new chat that went on from `queues`. The numbers are in `examples/bookmarks/notes/project-facts.md`.
- `examples/bookmarks`, version 1 (2026-11-25): the plugin in the LM Studio chat window, with the local Qwen 35B, on a real export of the owner. Then the sorting through the worker (`work.ts`), on 8 batches of 30. These runs gave the worker, `say`, the choices from code, and the page [guide/weak-model.md](../skills/rig/guide/weak-model.md).

## Not verified

- `tool.py mcp` inside a live MCP host (Claude Desktop, Claude Code, Cursor, LM Studio, or Windsurf). Verified via stdio JSON-RPC unit tests only.
- `tool.py work` against a real OpenAI-compatible server. Verified via mocked HTTP unit tests only.
- Warm `serve-stdio` bridge, `waiting.next_action`, chat-scoped active run, and `work_run` called by a model inside the live LM Studio chat window. Verified via `tsc --noEmit` and Node `try.ts` tests only.
- The lean compiled `SKILL.md` (~50–65 lines) with Claude in a live session.
- The `say` text with the short run id (`r1`), and the `forModel` text for a refused operator message: no live model has seen them yet.
- The worker on release-tool and band-facts; timeouts in a real run.
- The release-tool and band-facts plugins in the LM Studio chat window. band-facts ran only through `agent.ts`, which runs the same bridge code.
- A whole bookmarks run, from the export to the written file, with version 1. A file of thousands of bookmarks with a model.
- With a real model: a refusal that the model must not repeat, a paragraph over the word limit.
- A local model sometimes tells the operator to answer `yes` where the plugin needs `approve yes`.
- The editor syntax test (`editors/test-vscode.js`, `syntax_test_rig.rig`). It needs `vscode-textmate` from npm, which is not installed here. The grammars are built, and their table is tested.
- The viewer was checked in one browser (the pane of the Claude desktop app), on release-tool and bookmarks, with one run. Not checked: dragging nodes with boxes, a flow with `until` or `else`, a phone-size screen.
- `examples/bookmarks` was built by an agent from the guide, the skill and the two examples. It is not a guide-only build test: the agent could read the kit code.
- The level `tested` confirms via Python AST that a test file references the gate function in code (not only in comments or docstrings), and the doctor runs the tests, but it cannot see a test that checks nothing.

## Open

| # | What | Note |
|---|---|---|
| 1 | A template for a tool whose steps run inside a host application | The guide describes the shape (`fronts.md`, section 6). `rig.py new` makes command-line tools only. |
| 2 | A guide-only build test | A fresh agent builds a small tool from the skill, cheatsheet and guide, with no other help. |
| 3 | The origin project on the kit | Optional. Its fronts are kept in step by hand today. |
| 4 | Bookmarks: `work_run` in the LM Studio chat window, then a whole run on a real export | Check the first values of `similar.max_group`, `sort.host_elsewhere` and `safety.max_removed` with the dry-run report. |
| 5 | Bookmarks: the link checker | The hook is `steps.dead_links` (called by the step `report`) and `dead.json` in the work folder; dead links go to `links.folder`, never deleted. A delay between retries comes with the first network step. |
| 6 | Live host tests for new fronts | Verify `tool.py mcp` in Claude Desktop / Cursor / LM Studio, `tool.py work` against a real OpenAI-compatible server, warm `serve-stdio` in the LM Studio UI, and lean `SKILL.md` with Claude. |
| 7 | A plain `yes` from the operator | The plugin could take a bare `yes` or `no` as an approval when one run waits for a person. Not done: a bare `yes` may answer a question of the model. |
| 8 | Not in version 1 | A delay between retries; parallel flow branches; a block editor in the viewer. |

## Where the old things are

- [history/](history/): the first memos, the research notes, the work orders of version 1 and of the review of the texts, and the dated notes of 2026-11 ([history/notes-2026-11.md](history/notes-2026-11.md)).
- The examples of language version 0 and the task file of the snippet scale are only in git: `git show 5337e26:docs/history/older-examples/`.
