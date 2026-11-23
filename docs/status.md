# Status

Branch: `claude/edge-bookmarks-0b3a10`. Last change: 2026-11-23. The history of the work is in the commit messages.

## What Rig is now

A kit and a guide for building **instrumental agents**: a model that operates tools to do a defined job. The goal: the owner says "build tool X, look at this repository", and an agent builds it by the guide.

The pattern comes from a private production agent. Only the concept and the machinery are here; no material of that project.

## What exists

| Part | Where | State |
|---|---|---|
| The guide: method, levels, build order, patterns, fronts, rules | `skills/rig/guide/` | written |
| The skill: one entry, one file for each task | `skills/rig/SKILL.md` | written |
| The language: rules, steps, gates (`hard`, `soft`, `judge`, `human`), `code` and `test` lines, `sees` | `skills/rig/spec.md`, `rig.py`, the viewer, the grammars | in step, tested |
| The runner: runs, refusals, batches, queues, reports, regression | `skills/rig/kit/rigkit.py` | tested |
| Project commands: `new`, `build`, `doctor`, `test`, `plugin` | `skills/rig/rig_project.py` | tested at all four levels |
| The front for Claude: a compiled skill | `rig.py build` | used by a real model |
| The front for a local model: an LM Studio plugin, the same code for every tool | `skills/rig/kit/templates/plugin/` | used by a real model through `agent.ts` |
| The graph page, with the path of one run | `viewer/index.html`, `rig.py serve` | checked in a browser |
| The pattern example, level 4 | `examples/release-tool/` | passes its doctor |
| A second example, level 3, with what its runs taught | `examples/band-facts/` | passes its doctor; ran with two models |
| A real tool, level 4: clean up an Edge bookmarks export | `examples/bookmarks/` | passes its doctor; ran end to end with a local Qwen 35B through the plugin code |

67 tests pass: `python3 -m unittest discover -s tests`. Each example has its own tests too (`rig.py test DIR`).

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

- The plugin was **not** installed and run inside the LM Studio chat window (`lms dev`). So `src/index.ts` has not run: the settings field, the rules text before the first message, and the new `approve` message step in the preprocessor. It type-checks, and `agent.ts` runs the same bridge code.
- Not tested with a real model: a refusal that the model must not repeat, a paragraph over the word limit.
- The bookmarks tool has not seen a real Edge export, nor a file of thousands of bookmarks with a model.
- A local model sometimes tells the operator to answer `yes` where the plugin needs `approve yes`.
- `examples/bookmarks` was built by an agent from the guide, the skill and the two examples, with one question to the owner (where the tool lives). It is not a guide-only build test: the agent could read the kit code.
- The level `tested` means only that a test file names the function. The doctor runs the tests, but it cannot see a test that checks nothing.

## Open

| # | What | Note |
|---|---|---|
| 1 | Remove casts and hashes from the language | The snippet scale (`cast`, `prove`, `probe`, `stamp`, `emit`, hashes) is still in `rig.py`, the viewer and the spec. The kit does not use it. Proposed: remove it, keep `example` lines, and let the doctor run them against the bound function. `examples/older/` and some tests of `tests/test_rig.py` depend on it. |
| 2 | Remove what the kit replaced | The single compilers (`compile json`, `skill`, `tool`, `from-json`), the skill form where the model walks the flow, and the word `external`. |
| 3 | One parser | The viewer has its own parser and compilers in JavaScript, held in step by a test. It could draw the compiled catalogue. Then a raw `.rig` file can no longer be dropped on the page. |
| 4 | Rewrite `docs/logic.md` for the kit | It still explains mostly the snippet scale. |
| 5 | A template for a tool whose steps run inside a host application | The guide describes the shape (`fronts.md`, section 5). `rig.py new` makes command-line tools only. |
| 6 | A guide-only build test | A fresh agent builds a small tool from the skill and the guide, with no other help. |
| 7 | The origin project on the kit | Optional. Its fronts are kept in step by hand today. |
| 8 | Bookmarks: run in the LM Studio chat window, then on a real export | The owner installs the plugin (`lms dev`), and runs it on a copy of a real export. Check the first values of `similar.max_group`, `sort.host_elsewhere` and `safety.max_removed` with the dry-run report. |
| 9 | Bookmarks: the link checker | The hook is the step `links` and `dead.json` in the work folder; dead links go to `links.folder`, never deleted. |
| 10 | A plain `yes` from the operator | The plugin could take a bare `yes` or `no` as an approval when exactly one run waits for a person. Not done: a bare `yes` may answer a question of the model. |

## Where the old things are

- `examples/older/`: the examples from before the kit. The tests of the snippet scale use them.
- `docs/history/`: the first memos and the research notes.
