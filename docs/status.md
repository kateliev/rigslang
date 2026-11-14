# Status of the refocus

Branch: `kit-refocus`. Started 2026-11-15. Newest entry at the bottom of the log.

## The goal

Rig changes from "a language" into **a kit and a guide for building instrumental agents**: a model that operates tools to do a defined job. One day the owner says "build tool X, look at this repository", and an agent builds it by the guide.

The pattern comes from a private production agent. Only the concept and the machinery are here; no material of that project.

## The design, in short

- The `.rig` file stays the one source: rules, presets, steps, gates, ends.
- The code of a tool lives in normal files. A `code` line binds a `by` name to a function, and a `test` line names its test file.
- Gates have four kinds: `hard`, `soft` (code decides), `judge` (the model decides, a guess), `human` (a person decides, the flow waits).
- A runner (`skills/rig/kit/rigkit.py`) walks the flow. Code drives; the model answers only what code cannot do; the runner refuses a call out of order.
- The fronts are compiled: the catalogue (JSON), the skill for Claude, the tool definitions and the plugin for a local model. Both fronts call the same code.
- A tool has a level, 1 to 4. A simple tool does not pay for what a production tool needs.

## Plan

| # | Part | State |
|---|---|---|
| 1 | Language: `human` gates, `code` and `test` lines, the level `tested`, coverage; viewer, spec and grammars in step | done |
| 2 | Runtime kit `rigkit.py`: rules, verdicts, runs, guard, command line, regression; tests | done |
| 3 | Project commands in `rig.py`: `new`, `build`, `doctor`, `test`; templates | done |
| 4 | One complete example tool, built with the kit (`examples/release-tool`) | done |
| 5 | The guide `skills/rig/guide/`: method, levels, build order, patterns, fronts, rules | done |
| 6 | The skill, split by task; README and docs refocused | done |
| 7 | LM Studio plugin front (template and bridge) | done, but not yet run inside LM Studio |
| 8 | `bandsearch` brought up to the kit (enforced gates, a runner, a regression set) | open |
| 9 | Trace view in the viewer: light up the path of one run | done |
| 10 | Batches, queues and batch reports in the runner | done |

## Log

- 2026-11-15, part 1. `rig.py`: gate kind `human`; `code [prefix] path` with a `test` child; `by prefix.function`; level `tested`; coverage counts proved and tested gates; `compile skill --driver CMD` for a skill that starts runs and does not walk the flow; `serve` gives the levels of bound code to the viewer at `/levels`. Viewer, spec (new Section 7) and editor grammars updated. All 37 tests pass.
- 2026-11-15, parts 2 to 4. `skills/rig/kit/rigkit.py`: `Rules`, `Kit` (bind code, verdicts, runs saved as files, refusals, `resume` after an error, a loop limit), the command line (`run`, `answer`, `approve`, `resume`, `status`, `rules`, `flow`, `call`, `regress`), and the `step` wrapper for code inside a host. `skills/rig/rig_project.py`: `rig.py new | build | doctor | test`, with the project file `rig.json` and the templates in `kit/templates/`. `examples/release-tool`: a level 4 tool with all four gate kinds, 12 regression cases, its notes and its compiled skill. The doctor found a real gap while the example was built (an end node that no regression case reached). 58 tests pass.
- 2026-11-15, parts 5 to 7. The guide: `README.md` (the method), `levels.md`, `build-order.md` (stages 0 to 9, each with a "done when"), `patterns.md` (12 patterns for production tools and a check list), `fronts.md`, `rules.md`. The skill is one entry (`SKILL.md`) and one file for each task (`change.md`, `snippets.md`, the guide pages). `rig.py plugin DIR` adds an LM Studio plugin whose code is the same for every tool: it reads its tools and its rules text from `plugin/src/gen/front.json` (compiled) and calls the driver without a shell. README, `docs/logic.md` and `AGENTS.md` refocused. 59 tests pass.
- 2026-11-15, parts 9 and 10. `rigkit.py`: `batch` (code runs a list; a run that needs the model waits and does not stop the batch; a report with the failures first; a stop after errors in a row) and `queues` (the runs that wait, by who must act). Both are in the compiled skill and in the plugin front. Viewer: the graph tab has a list of runs and shows the path of one run, with what happened at each node. Checked in a browser on the example. A bug found there and fixed: `serve` could hang at start, in a host name lookup of Python's `HTTPServer`. `build` now keeps the plugin code of a tool current. 62 tests pass.

## Not verified

- The plugin was tested through its bridge with `try.ts` (start a run, answer a gate, the refusal at a human gate). `src/index.ts` was **not** type-checked and **not** run inside LM Studio: `@lmstudio/sdk` is not installed here. It follows the SDK calls of the older `bandsearch` example.
- No model has used a compiled skill or a plugin of the kit yet. The first real run will find texts to fix.
- The level `tested` means only that a test file names the function. `rig.py doctor` runs the tests, so a failing test is seen, but a test that names a function and checks nothing is not.
