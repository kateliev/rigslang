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
| 5 | The guide: method, levels, build order, patterns, fronts | in work |
| 6 | The skill, split by task; README and docs refocused | open |
| 7 | LM Studio plugin front (template and bridge) | open |
| 8 | `bandsearch` brought up to the kit (enforced gates, a runner, a regression set) | open |
| 9 | Trace view in the viewer: light up the path of one run | open |

## Log

- 2026-11-15, part 1. `rig.py`: gate kind `human`; `code [prefix] path` with a `test` child; `by prefix.function`; level `tested`; coverage counts proved and tested gates; `compile skill --driver CMD` for a skill that starts runs and does not walk the flow; `serve` gives the levels of bound code to the viewer at `/levels`. Viewer, spec (new Section 7) and editor grammars updated. All 37 tests pass.
- 2026-11-15, parts 2 to 4. `skills/rig/kit/rigkit.py`: `Rules`, `Kit` (bind code, verdicts, runs saved as files, refusals, `resume` after an error, a loop limit), the command line (`run`, `answer`, `approve`, `resume`, `status`, `rules`, `flow`, `call`, `regress`), and the `step` wrapper for code inside a host. `skills/rig/rig_project.py`: `rig.py new | build | doctor | test`, with the project file `rig.json` and the templates in `kit/templates/`. `examples/release-tool`: a level 4 tool with all four gate kinds, 12 regression cases, its notes and its compiled skill. The doctor found a real gap while the example was built (an end node that no regression case reached). 58 tests pass.
