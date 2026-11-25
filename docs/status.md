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
| The front for a local model: an LM Studio plugin, the same code for every tool | `skills/rig/kit/templates/plugin/` | used by a real model through `agent.ts` |
| The graph page: three lanes (code, model, person), the blocks as boxes, the path of one run; it has no parser, it draws what `rig.py` compiles | `viewer/index.html`, `rig.py serve` | checked in a browser (release and bookmarks, 2026-11-25) |
| The pattern example, level 4 | `examples/release-tool/` | passes its doctor |
| A second example, level 3, with what its runs taught | `examples/band-facts/` | passes its doctor; ran with two models |
| A real tool, level 4: clean up an Edge bookmarks export | `examples/bookmarks/` | passes its doctor; 22 nodes in version 1 (35 in version 0). Version 0 of it ran end to end with a local Qwen 35B through the plugin code; version 1 has not run with a model |

94 tests pass: `python3 -m unittest discover -s tests` (2026-11-25). Each example has its own tests too (`rig.py test DIR`), and each passes its doctor.

## Language version 1 (2026-11-25)

Made by the handout `docs/handout-language-v1.md`. What changed:

| Part | Change |
|---|---|
| One parser | The viewer has no parser. `rig.py serve` gives it a bundle (`/bundle`, `/compile`). `tests/parity.js` is gone. |
| Words removed | `next`, `pass`, `when` (gate child), `brief`, `ensure`, `judge`, `min`, `max`, `label`, `unit` (rule child), `external`, `cast`, `probe`, `evidence`, the scope `snippet`; the commands `prove`, `probe`, `stamp`, `emit`, `hash`. The checker refuses each word and names the replacement. `examples/older/` and `snippets.md` moved to `docs/history/`. |
| Words added | `for … in`, `until`, `if`, `else`, `section`, `finally`, `by model`, `out` (step), `check`, `options` (human gate, with `by`), `retry`, `timeout`, `fail -> continue`, `tolerate`, `range`. A `by` or a `fail` can stand on the line of its node. |
| Catalogue | `"rig": 1`. Every edge is written out: `next`, `fail`, `back` (retry), `block`, `lane`; and `blocks` and `body`. |
| Runner | Blocks, retry, `if`, options asked again, the `out` form checked, timeouts, `finally`, the outcome `error`. A run folder: `run.json`, `flow.json` and `rules.json` (pin), `answers.json` (record), `marks.json` (for `rerun`). Commands `rerun`, `replay`; `rig.py test DIR --replay RUN`. The visit limit (`run.max_visits`) and `"route": true` are gone: every loop is a block or a retry with a limit. |
| Plugin front | One tool `finish_<step>` for each `by model` step with `out`: its `result` has the schema of the type. An operator message `approve [RUN] WORDS` passes the words of an answer. |
| Examples | All three in version 1; each passes its doctor and its tests. The regression cases of release-tool and band-facts end where they ended in version 0 (new baselines for the paths). |
| Text | The spec, `docs/logic.md` (open item 4), the guide pages, the skill, the editor grammars and the READMEs. |

**Decisions in this work that the owner did not see before** (the owner answered four questions first: keep `section`; a `fail` on the gate line; a fail goes only to an end or `continue`; keep the single compilers and `from-json` and update them):

- `by` on the line of a step or gate too (the example of the handout writes `step sort by model`).
- `retry <rule id>` as well as `retry <n>`, so that a preset can change it (release-tool `notes.rounds`, bookmarks `sort.rounds`).
- `retry` goes back to the nearest step before the gate in the same block, past gates (release-tool: `rewrite`, `rewritten`, `tone`).
- `evidence` is removed (it is not in the word list of the handout); write evidence in the text of the note.
- A path is true when it is not missing, `null`, `false`, `""`, `[]` or `{}`. The number `0` is true.
- A timeout is checked when a run is read (`status`, `resume`, `queues`, `answer`); the runner has no clock. A code step that passes its timeout ends the run with `error`; its thread is left to finish in the background.
- band-facts: each of the two gates that check the paragraph has its own retries, so the model may rewrite more often in all than in version 0 when both gates fail in turn.
- bookmarks, to reach 22 nodes: one step `similar` with two `by` lines (duplicates, then groups); `sort-ok` has two `by` lines (`gates.sort_ok`, then `steps.keep`, which saves the batch); the dead-link hook is in `report`; the end `exists` became `held` with the reason "the output file exists". `tolerate 20%` (from the handout) holds back a run where more than 20% of the batches stay unsorted: the regression case with 1 of 2 batches unsorted now ends at `held`, and a new case reaches `declined`.
- `AGENTS.md` rule 2 named the removed commands (`hash`, `prove`); it now names tests, levels, regression results and recorded answers, with the same meaning.

## Tested with real models

On `examples/band-facts`: Claude Haiku through the compiled skill, and a local Qwen 35B model in LM Studio through the plugin tools and rules text. Every tool call of both models was valid, and none was refused. The findings and the fixes are in `examples/band-facts/README.md`.

On `examples/bookmarks` (2026-11-23): the local Qwen 35B through the plugin code (`agent.ts`, which now plays later operator messages with `--then`). Three runs on synthetic files: three `human` gates answered by `approve` messages of the operator, a long run of six sort batches (313 bookmarks, 300 of 300 moves right), one answer refused by a gate and fixed by the model from `waiting.problems`, and a new chat that went on with a run from `queues`. The numbers are in `examples/bookmarks/notes/project-facts.md`.

## Kit changes from the bookmarks tool (2026-11-23)

| What was wrong | Fix | Where |
|---|---|---|
| A gate that ends a loop ("no page is left") added a line to the problems of the run at every loop end. | A gate in code can return `"route": true` with its fail: a turn of the flow, kept in the trace, not a problem. | `rigkit.py` (`verdict`, `after_gate`), `guide/build-order.md` |
| A waiting node showed only the problems of the whole run, old ones too. In batch 2 the model saw the failure of batch 1. | `waiting.problems`: what failed after the last answer at this node. The plugin rules text names it. | `rigkit.py` (`waiting`, `answer`), `rig_project.front`, `spec.md` section 7, `guide/fronts.md` |
| At the plugin front, a human gate told the operator a command but not the folder; and in a chat the operator answers in the chat, which the model must not pass on. | The bridge adds `waiting.command` (with the tool folder). The plugin reads an operator message that starts with `approve` as the answer of the person, before the model sees it (`operatorAnswer`). Not a tool: the model cannot call it. | `templates/plugin/src/bridge.ts`, `src/index.ts`, `agent.ts`, `try.ts`, README, `guide/fronts.md` |
| `answer_gate` was a tool even for a flow with no gate for the model. | The tool and its rule line only when a gate is `judge` or has no code. | `rig_project.front` |
| No guide text for one large item with parts (a file of thousands of records). | A pattern: one run, a loop over parts saved as files, a `route` gate at the end. | `guide/patterns.md`, section 5 |

## Not verified

Language version 1 (2026-11-25):

- **No real model has run version 1.** Not run: the `out` schema as a tool of the plugin in LM Studio (`finish_sort`), `options` at the plugin front (an `approve` message with words), timeouts in a real run, `retry` with a real model, the new skill texts with Claude.
- The editor grammars are built and their table is tested, but the syntax test (`editors/test-vscode.js`, `syntax_test_rig.rig`) was not run: it needs `vscode-textmate` from npm, which is not installed here.
- The viewer was checked in one browser (the pane of the Claude desktop app), on the release and bookmarks examples, with one run. Not checked: dragging nodes with boxes, a flow with `until` or `else`, a phone-size screen.
- The plugin code type-checks (`tsc`) and `try.ts` ran an approval; it was not run in the LM Studio chat window.

From before:

- The plugin was **not** installed and run inside the LM Studio chat window (`lms dev`). So `src/index.ts` has not run: the settings field, the rules text before the first message, and the new `approve` message step in the preprocessor. It type-checks, and `agent.ts` runs the same bridge code.
- Not tested with a real model: a refusal that the model must not repeat, a paragraph over the word limit.
- The bookmarks tool has not seen a real Edge export, nor a file of thousands of bookmarks with a model.
- A local model sometimes tells the operator to answer `yes` where the plugin needs `approve yes`.
- `examples/bookmarks` was built by an agent from the guide, the skill and the two examples, with one question to the owner (where the tool lives). It is not a guide-only build test: the agent could read the kit code.
- The level `tested` means only that a test file names the function. The doctor runs the tests, but it cannot see a test that checks nothing.

## Open

| # | What | Note |
|---|---|---|
| 1 | Remove casts and hashes from the language | Done (version 1). Still open from the proposal: let the doctor run the `example` lines against the bound function. |
| 2 | Remove what the kit replaced | `external` is gone (version 1). The owner chose to keep the single compilers and `from-json`; they are updated for blocks. |
| 3 | One parser | Done (version 1). The viewer draws what `rig.py serve` compiles (`/bundle`). Without the server it opens a compiled catalogue, read only. |
| 4 | Rewrite `docs/logic.md` for the kit | Done (version 1). |
| 5 | A template for a tool whose steps run inside a host application | The guide describes the shape (`fronts.md`, section 5). `rig.py new` makes command-line tools only. |
| 6 | A guide-only build test | A fresh agent builds a small tool from the skill and the guide, with no other help. |
| 7 | The origin project on the kit | Optional. Its fronts are kept in step by hand today. |
| 8 | Bookmarks: run in the LM Studio chat window, then on a real export | Now also the first run of language version 1 with a model (`finish_sort`, `approve` words at the options gates). The owner installs the plugin (`lms dev`), and runs it on a copy of a real export. Check the first values of `similar.max_group`, `sort.host_elsewhere` and `safety.max_removed` with the dry-run report. |
| 9 | Bookmarks: the link checker | The hook is `steps.dead_links` (called by the step `report`) and `dead.json` in the work folder; dead links go to `links.folder`, never deleted. Handout, Section 10: a delay between retries comes with the first network step. |
| 10 | A plain `yes` from the operator | The plugin could take a bare `yes` or `no` as an approval when exactly one run waits for a person. Not done: a bare `yes` may answer a question of the model. |
| 11 | Not in version 1 (handout, Section 10) | A delay between retries; parallel branches; a block editor in the viewer. |
| 12 | Cut the language further | The handout names the candidates: `reads` (the kit could record which rules a function reads during the tests) and `section`. |

## Where the old things are

- `docs/history/older-examples/`: the examples from before the kit, in language version 0. `rig.py` refuses them now.
- `docs/history/snippets-v0.md`: the task file of the snippet scale.
- `docs/history/`: the first memos and the research notes.
- `docs/handout-language-v1.md`: the work order of language version 1.
