# Status

Branch: `kit-refocus`. Last change: 2026-11-15. The history of the work is in the commit messages.

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

64 tests pass: `python3 -m unittest discover -s tests`.

## Tested with real models

On `examples/band-facts`: Claude Haiku through the compiled skill, and a local Qwen 35B model in LM Studio through the plugin tools and rules text. Every tool call of both models was valid, and none was refused. The findings and the fixes are in `examples/band-facts/README.md`.

## Not verified

- The plugin was **not** installed and run inside the LM Studio chat window (`lms dev`). So `src/index.ts` has not run: the settings field, and the rules text before the first message. It type-checks.
- Not tested with a real model: a `human` gate at the plugin front, a refusal that the model must not repeat, a paragraph over the word limit, a long batch.
- No agent has built a tool from the guide alone yet. `band-facts` was built by the author of the guide.
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

## Where the old things are

- `examples/older/`: the examples from before the kit. The tests of the snippet scale use them.
- `docs/history/`: the first memos and the research notes.
