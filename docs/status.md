# Status

Branch: `main`. Last change: 2026-11-25 (language version 1). The history of the work is in the commit messages.

## What Rig is now

A kit and a guide for building **instrumental agents**: a model that operates tools to do a defined job. The goal: the owner says "build tool X, look at this repository", and an agent builds it by the guide.

The pattern comes from a private production agent. Only the concept and the machinery are here; no material of that project.

## What exists

| Part | Where | State |
|---|---|---|
| The guide: method, levels, build order, patterns, fronts, rules | `skills/rig/guide/` | written |
| The skill: one entry, one file for each task | `skills/rig/SKILL.md` | written |
| The language, version 1: the order of the lines is the order of the flow; blocks `for`, `until`, `if`/`else`, `section`, `finally`; gates `hard`, `soft`, `model`, `human` (with `options`); `retry`, `timeout`, `fail -> continue`, `tolerate`, `by model`, `out`, `range` | `skills/rig/spec.md`, `rig.py`, the viewer, the grammars | in step, tested |
| The runner: runs in their own folders (pin, record, marks), rerun, replay, refusals, batches, queues, reports, regression | `skills/rig/kit/rigkit.py` | tested |
| Project commands: `new`, `build`, `doctor`, `test`, `plugin` | `skills/rig/rig_project.py` | tested at all four levels |
| The front for Claude: a compiled skill | `rig.py build` | used by a real model |
| The front for a local model: an LM Studio plugin, the same code for every tool | `skills/rig/kit/templates/plugin/` | used by a real model through `agent.ts` (2026-11-23), and in the LM Studio chat window on the bookmarks tool (2026-11-25) |
| The graph page: three lanes (code, model, person), the blocks as boxes, the path of one run; it has no parser, it draws what `rig.py` compiles | `viewer/index.html`, `rig.py serve` | checked in a browser (release and bookmarks, 2026-11-25) |
| The pattern example, level 4 | `examples/release-tool/` | passes its doctor |
| A second example, level 3, with what its runs taught | `examples/band-facts/` | passes its doctor; ran with two models |
| A real tool, level 4: clean up an Edge bookmarks export | `examples/bookmarks/` | passes its doctor; 22 nodes in version 1 (35 in version 0). Version 0 of it ran end to end with a local Qwen 35B through the plugin code. Version 1 ran with the same model on a real export of the owner (below), not yet end to end |

101 tests pass: `python3 -m unittest discover -s tests` (2026-11-25). Five of them (`tests/test_docs.py`) guard the texts: every relative link resolves, no text uses a word of version 0, and the docstring of each `tool.py` names the commands of `Kit.cli`. Each example has its own tests too (`rig.py test DIR`), and each passes its doctor.

## Tested with real models

The full record of each run is in [history/notes-2026-11.md](history/notes-2026-11.md) and in the notes of the examples.

- `examples/band-facts` (2026-11-15): Claude Haiku through the compiled skill, and a local Qwen 35B in LM Studio through the plugin tools and rules text (`agent.ts`). Every tool call was valid, and none was refused. The findings are in `examples/band-facts/README.md`.
- `examples/bookmarks`, version 0 (2026-11-23): the local Qwen 35B through the plugin code (`agent.ts`), on synthetic files. `approve` messages at three `human` gates, six sort batches, a fix from `waiting.problems`, and a new chat that went on from `queues`. The numbers are in `examples/bookmarks/notes/project-facts.md`.
- `examples/bookmarks`, version 1 (2026-11-25): the plugin in the LM Studio chat window, with the local Qwen 35B, on a real export of the owner. Then the sorting through the worker (`work.ts`), on 8 batches of 30. These runs gave the worker, `say`, the choices from code, and the page [guide/weak-model.md](../skills/rig/guide/weak-model.md).

## Not verified

- `work_run` called by the model in the LM Studio chat window. Only `work.ts` in a terminal ran it.
- The `say` text with the run id, and the `forModel` text for a refused operator message: they came after the chats in the window, and no model has seen them.
- The worker on release-tool and band-facts; timeouts in a real run; the skill texts of version 1 with Claude.
- The release-tool and band-facts plugins in the LM Studio chat window. band-facts ran only through `agent.ts`, which runs the same bridge code.
- A whole bookmarks run, from the export to the written file, with version 1. A file of thousands of bookmarks with a model.
- With a real model: a refusal that the model must not repeat, a paragraph over the word limit.
- A local model sometimes tells the operator to answer `yes` where the plugin needs `approve yes`.
- The editor syntax test (`editors/test-vscode.js`, `syntax_test_rig.rig`). It needs `vscode-textmate` from npm, which is not installed here. The grammars are built, and their table is tested.
- The viewer was checked in one browser (the pane of the Claude desktop app), on release-tool and bookmarks, with one run. Not checked: dragging nodes with boxes, a flow with `until` or `else`, a phone-size screen.
- The plugin code type-checks (`tsc --noEmit` in `examples/bookmarks/plugin` and `examples/band-facts/plugin`, 2026-11-25), and the tests run `try.ts` with an approval.
- `examples/bookmarks` was built by an agent from the guide, the skill and the two examples. It is not a guide-only build test: the agent could read the kit code.
- The level `tested` means only that a test file names the function. The doctor runs the tests, but it cannot see a test that checks nothing.

## Open

| # | What | Note |
|---|---|---|
| 1 | The doctor runs the `example` lines | Left from removing casts: let the doctor run the `example` lines of a unit against its bound function. |
| 2 | A template for a tool whose steps run inside a host application | The guide describes the shape (`fronts.md`, section 5). `rig.py new` makes command-line tools only. |
| 3 | A guide-only build test | A fresh agent builds a small tool from the skill and the guide, with no other help. |
| 4 | The origin project on the kit | Optional. Its fronts are kept in step by hand today. |
| 5 | Bookmarks: `work_run` in the LM Studio chat window, then a whole run on a real export | The sorting ran with the worker (`work.ts`). Check the first values of `similar.max_group`, `sort.host_elsewhere` and `safety.max_removed` with the dry-run report. |
| 6 | Bookmarks: the link checker | The hook is `steps.dead_links` (called by the step `report`) and `dead.json` in the work folder; dead links go to `links.folder`, never deleted. A delay between retries comes with the first network step. |
| 7 | The model copies the long run id | The `say` text of a human gate gives `approve <run id> …`. A short id, or an `approve` without id for the run of this chat, would take that job away. |
| 8 | A plain `yes` from the operator | The plugin could take a bare `yes` or `no` as an approval when exactly one run waits for a person. Not done: a bare `yes` may answer a question of the model. |
| 9 | Not in version 1 | A delay between retries; parallel branches; a block editor in the viewer. |
| 10 | Cut the language further | Candidates: `reads` (the kit could record which rules a function reads during the tests) and `section`; the unit words `check` (a second meaning of the word) and `example` (it never runs); `finish_step`, if every `by model` step must have `out`. |
| 11 | Questions 2 to 4 of the review of the texts | The doctor line about `permissions`; the unused `node` field in `bridge.ts`; the `?` value of the editor grammars ([history/review-docs-2026-11.md](history/review-docs-2026-11.md), Section 3). |

## Where the old things are

- [history/](history/): the first memos, the research notes, the work orders of version 1 and of the review of the texts, and the dated notes of 2026-11 ([history/notes-2026-11.md](history/notes-2026-11.md)).
- The examples of language version 0 and the task file of the snippet scale are only in git: `git show 5337e26:docs/history/older-examples/`.
