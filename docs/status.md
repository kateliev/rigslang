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
| Plugin front | A `by model` step with `out` is a job for the worker (`src/worker.ts`, tool `work_run`, `work.ts` in a terminal): each job goes to the loaded model in a new context, and the answer goes to the driver. Mode `think` off (the answer bound to the schema) or on, set in `rig.json`. An operator message `approve [RUN] WORDS` passes the words of an answer. |
| Examples | All three in version 1; each passes its doctor and its tests. The regression cases of release-tool and band-facts end where they ended in version 0 (new baselines for the paths). |
| Text | The spec, `docs/logic.md` (open item 4), the guide pages, the skill, the editor grammars and the READMEs. |

**Decisions in this work that the handout did not settle.** The owner answered four questions first (keep `section`; a `fail` on the gate line; a fail goes only to an end or `continue`; keep the single compilers and `from-json` and update them), and accepted the decisions below on 2026-11-25:

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

## First run of version 1 with a model (2026-11-25)

The bookmarks plugin, installed in LM Studio, with a local Qwen 35B (`qwen3.6-35b-a3b`) on a real Edge export of the owner. Code read the file and made 7 pages of similar URLs; the run waited at the human gate `choose`. Then the chat stalled:

- The model showed page 1, but cut the list at group 9 of 20, and made up its own numbered menu instead of the `approve` messages.
- The owner answered "1". That is no `approve` message, so it went to the model. The model has no tool for a human gate; it took `finish_sort` (the tool of another step) for one, doubted it, and repeated its thinking for about 30,000 characters with no call.
- An earlier message: the refusal "set Tool folder in the plugin settings" made the model send the owner to the settings of Edge.

Fixes: a waiting human gate now carries `say`, the exact messages that answer it (`rigkit.waiting`); the rules text of the plugin says to call no tool at a human gate, to show `say` word for word, and that a message that does not start with `approve` is no answer; the rule for steps says "(only then)"; `status` composes the waiting text again, so a run that waits gets fixed texts; the refusal names LM Studio; `similar.page_size` is 8, not 20.

Second chat: the model showed the page and the `say` line well. The operator wrote `approve yes rest`, and the plugin refused it, because the run of the first chat waited for a person too, and a message without a run id is ambiguous. The model took the refusal as its own error, called `run_status` and showed the page again, so the chat went in a circle. Fixes: `say` names the run id in each message (`approve 20261125-111637-01 yes`); a refused message of the operator reaches the model as "tell the operator this, word for word, and do not call a tool" (`forModel` in `bridge.ts`). Not yet verified with the model. Open: a run that nobody will answer any more has no way to end; a command to drop it would keep `queues` clean.

Third chat (batch 1 of 5 to sort): the model got 60 bookmarks and the whole list of 227 folders, and read the list line by line for each bookmark. It wrote about 57,000 characters of thinking, repeated itself, and gave no answer. Fix in `examples/bookmarks` (no kit change): code finds the candidate folders of each bookmark once (`bm.candidates`, in `steps.loose`). The model sees only `prepare.batch`, `prepare.of`, `prepare.bookmarks` (each with at most `sort.choices` numbered choices) and `prepare.new_so_far`, and answers `{"id", "pick"}`. A site of `similar.skip_hosts` no longer makes a bookmark misfiled. `sort.batch` is 30, not 60. Tested on the fixture.

The worker (same day). The chat took about 13 minutes for the 8 batches. Fix in the kit: the plugin gives a step of the model with `out` to a worker, one job in a new context each time (`work_run`, `src/worker.ts`). Real runs on the same 8 batches: thinking off, answer bound to the schema: 137 seconds, each batch passed `sort-ok` at the first answer, 92 of 120 decisions as in the chat run. Thinking on in a new context: 2.5 to 3 minutes for each batch, and only 41 of 60 decisions as in the chat run, so it was stopped after 2 batches. The bookmarks tool uses thinking off. Found on the way: without thinking the model picks a safe first choice (now the present folder takes its place by score), and a `why` field does not make it reason. The method is in the new guide page `skills/rig/guide/weak-model.md`, and in rule 5 of `guide/rules.md`.

## Not verified

Language version 1 (2026-11-25):

- Version 1 ran with a real model on the bookmarks tool (see above): the worker with `out` and `retry`, `approve` messages at a gate with options. Not run: `work_run` called by the model inside the LM Studio chat window (only `work.ts` in a terminal ran), the worker on the release and band examples, timeouts in a real run, the new skill texts with Claude.
- Open: the `say` text of a human gate still asks the model to copy the long run id. A short id, or an `approve` without id for the run of this chat, would take that job away.
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
| 8 | Bookmarks: run in the LM Studio chat window, then on a real export | Started 2026-11-25: the sorting runs with the worker (`work.ts`), not yet through `work_run` in the chat window. The owner installs the plugin (`lms dev`), and runs it on a copy of a real export. Check the first values of `similar.max_group`, `sort.host_elsewhere` and `safety.max_removed` with the dry-run report. |
| 9 | Bookmarks: the link checker | The hook is `steps.dead_links` (called by the step `report`) and `dead.json` in the work folder; dead links go to `links.folder`, never deleted. Handout, Section 10: a delay between retries comes with the first network step. |
| 10 | A plain `yes` from the operator | The plugin could take a bare `yes` or `no` as an approval when exactly one run waits for a person. Not done: a bare `yes` may answer a question of the model. |
| 11 | Not in version 1 (handout, Section 10) | A delay between retries; parallel branches; a block editor in the viewer. |
| 12 | Cut the language further | The handout names the candidates: `reads` (the kit could record which rules a function reads during the tests) and `section`. |

## Where the old things are

- `docs/history/older-examples/`: the examples from before the kit, in language version 0. `rig.py` refuses them now.
- `docs/history/snippets-v0.md`: the task file of the snippet scale.
- `docs/history/`: the first memos and the research notes.
- `docs/handout-language-v1.md`: the work order of language version 1.
