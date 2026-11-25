# Review of the texts, 2026-11-25

The work order is [handout-docs-review.md](handout-docs-review.md). The code is the reality, and the text follows the code. No code behaviour changed. Two docstrings and one comment changed (`rig_project.py`, the `tool.py` files, `viewer/index.html`).

The runs of this review (2026-11-25):

- `python3 -m unittest discover -s tests`: 99 tests pass (94 before, plus 5 new in `tests/test_docs.py`).
- `rig.py build` and `rig.py doctor` for the three examples: all compiled files are current, nothing is missing.
- `rig.py new` at levels 1 to 4 in a scratch folder: each new project passes its own doctor.
- The tests of each example pass. `editors/build.py --check` passes.
- `tsc --noEmit` passes in `examples/bookmarks/plugin` and `examples/band-facts/plugin`.
- The "Try it" steps of `examples/release-tool/README.md` ran as the README says: 5 nodes, `tone`, `answer` refused at `approve`, the end `ready`, `replay` with no differences.

## 1. The changes

| File | What it said | What it says now | Source in the code |
|---|---|---|---|
| `skills/rig/spec.md`, Section 6 | The plugin front gets one tool `finish_<step>` for each `by model` step with `out`. | A step with `out` is a job for the worker (`work_run`). A model step with no `out` gets `finish_step`. A gate for the model gets `answer_gate`. No tool answers a human gate. | `rig_project.front()` |
| `skills/rig/spec.md`, Section 6 | The catalogue keys did not name `preset`, the node key `notes`, or `block` of a block. | It names them. | `rig.catalog()`, `node_info()`, `block_info()`; `examples/*/gen/*.json` |
| `skills/rig/spec.md`, Section 7 | No `rig.py plugin` in the table of project commands. | A row for `rig.py plugin DIR [--owner NAME]`. | `rig.py` docstring, `rig_project.main()` |
| `skills/rig/guide/fronts.md`, section 3 | `approve yes` "answers the one run that waits"; `approve RUN yes` only "when more than one run waits". | The long form `approve RUN …` first, as `say` gives it. The short form works only when exactly one run waits; else the plugin refuses it and names the runs. | `rigkit.waiting()` (`say`), `bridge.ts` (`operatorAnswer`) |
| `skills/rig/guide/fronts.md`, the worker | A job that reaches `max_tokens` "fails, and the gate retries it". The worker stops at a person, a model gate or the end. | The job gives no result: the step waits again with the problems, and the worker asks again. The worker also stops after `max_calls` jobs, and after five fails of the same job in a row. | `worker.ts` (`work`); `rigkit.schema_problems(None, …)` gives a problem |
| `skills/rig/guide/fronts.md`, small model | "The flow tools above are six at most." | Seven at most, and a flow gets only the ones it needs. | `rig_project.front()`: `start_run`, `answer_gate`, `work_run`, `finish_step`, `run_status`, `start_batch`, `queues` |
| `skills/rig/guide/levels.md` | Level 1: "every unit has code"; the line about the tests command was missing. Level 3: "a unit has a flow" was missing. Level 4: the `permissions` rule "guards every change", "its default is the safe value". | Code or a flow; `rig.json` names the tests command. A unit has a flow. The doctor checks only that a `permissions` rule exists. | `rig_project.doctor()`, the `add(...)` lines |
| `skills/rig/guide/rules.md`, rule 1 | The compiled files did not name the plugin. | Also `plugin/src/gen/` and the plugin's copies of the template code. | `rig_project.outputs()` |
| `skills/rig/guide/rules.md`, rule 7 | "Read `pass`, `problems` and the next node from the result." | Read `outcome`, `waiting` and `problems`. A run result has no `pass`. | `rigkit.report()` |
| `skills/rig/guide/patterns.md`, section 6 | The runner saves each run "after every node". | When the run waits, when it ends, after each `for` item and each `until` round. | `rigkit.walk()`, `control()` |
| `skills/rig/guide/weak-model.md`, section 2 | At the token cap "the gate retries". | The job gives no result, the step waits again, and the worker asks again. | `worker.ts`, `rigkit.answer()` |
| `skills/rig/guide/build-order.md`, stage 5 | No link to `weak-model.md` where the jobs of the model are designed. | One sentence and the link. | Handout, Section 4 |
| `skills/rig/SKILL.md` | The tool commands left out `batch`, `queues`, `call`. | All commands of `Kit.cli`. | `rigkit.Kit.cli` |
| `examples/*/tool.py`, `templates/flow/tool.py` (docstrings) | Each listed only some of the commands. | Each lists the 13 commands of `Kit.cli`. | `rigkit.Kit.cli` |
| `templates/flow/README.md` | `runs/`: "one file for each run". `tests/`: "and the regression set" (also at level 2). | One folder for each run, with what it holds. The regression set from level 3. | `rigkit.put()`; `rig_project.new()` |
| `templates/plugin/README.md`, the three `examples/*/plugin/README.md` | `approve yes`, `approve no`; `approve RUN …` "when more than one run waits". | The long form as `say` gives it; the short form only when exactly one run waits. | `rigkit.waiting()`, `bridge.ts` |
| `examples/*/plugin/README.md` | `try.ts start_run '{"item": …}'`: the input of the template. | The real input of each tool (`folder`, `band`, `file`). | `gen/*.json`, `"in"` |
| `examples/bookmarks/README.md` | The plugin tool `finish_sort` has the schema of the `sort` answer. | The worker gives each batch to the model (`work_run`), with the answer bound to the schema. | `plugin/src/gen/front.json` |
| `examples/bookmarks/README.md` | The choices: "its present folder, then the folders that share the most words". The model answers `{"id": 12, "pick": 2}`. | The present folder at the place of its own score. The model also gets a map of the top folders, and answers `{"id", "topic", "pick"}`, with `folder` and `new` when no choice fits. | `bm.candidates()`, `steps.prepare()`, `bookmarks.rig` (`out` of `sort`) |
| `examples/bookmarks/README.md` | The hand example `answer RUN '{"result": [{"id": 4, "folder": "…"}]}'`: the runner refuses it (no `topic`, no `pick`). | `{"id": 4, "topic": "cooking", "pick": 2}`. | the schema in `gen/bookmarks.json` |
| `examples/bookmarks/README.md` | "If more than one run waits, write the run id." | When the short form works, when it does not, and that `say` gives the long form. | `bridge.ts` (`operatorAnswer`) |
| `PRIVACY.md` | "The `prove` command runs the code in a `.rig` file." The viewer "makes no network requests". | `prove` is gone: `doctor` and `test` run the tests of a project, and a tool runs its code. The viewer sends requests only to `rig.py serve` on 127.0.0.1. | `rig.py` (`REMOVED`, `serve`), `viewer/index.html` (`fetch`) |
| `viewer/index.html` (head comment) | No requests "except the bundle of `rig.py serve`". | The requests to its own server: `/bundle`, `/compile`, `/runs`, `/file`. | `viewer/index.html`, `rig.py serve` (`do_GET`, `do_POST`) |
| `README.md`, Status | "Version 0, in work … new (2026-11-15)." | Language version 1 (2026-11-25); the kit came on 2026-11-15. | `rig.VERSION` |
| `skills/rig/rig_project.py` (module docstring) | "new, build, doctor, test"; no `"work"` in the `rig.json` sample. | Also `plugin`; the `"work"` setting of the worker. | `rig_project.main()`, `front()` |
| `docs/status.md` | The plugin row: used only through `agent.ts`. The bookmarks row: "version 1 has not run with a model". "Not verified": the plugin never ran in the chat window. | In step with the dated section "First run of version 1 with a model" of the same page: the bookmarks plugin ran in the chat window; `work_run` from the chat window did not. | `docs/status.md` (its own dated section), the commit `9027799` |
| `docs/status.md`, 2026-11-23 table | `"route": true` as the fix; "a gate is `judge`"; `spec.md` section 7; a `route` gate in `patterns.md`. | What replaced each: a `for` block; `model`; Section 4; a `for` block. | `rig.REMOVED`, `rigkit.control()`, `spec.md` |
| `docs/status.md`, first run of version 1 | `finish_sort`; the model answers `{"id", "pick"}`. | `finish_sort` was the tool of that time, and the worker took its place. Later the same day the answer got `topic`, and the batch got `prepare.map`. | `bookmarks.rig`, commit `9027799` |
| `docs/status.md` | 94 tests; `tsc` named with no run. | 99 tests, and what `tests/test_docs.py` guards; `tsc --noEmit` with the two folders where it ran today. | this review's runs |
| `tests/test_docs.py` (new) | — | 5 tests: the links resolve; no text uses a word of version 0; no `finish_<step>` tool; the docstring of each flow `tool.py` names the commands of `Kit.cli`; the level 1 `tool.py` names only commands of `Kit.cli`. Each test fails on the texts as they were before this review. | Handout, Section 7 |

The mechanical checks of Section 4 find nothing now. All links resolve. The hits for removed words are lines that say the word is gone. The paths in code blocks exist, or they are files that a run makes (`run.json`, `out/`), or things that `status.md` says are gone or moved.

Checked and found true, with no change: `guide/README.md`, `change.md`, `docs/logic.md` (the count of 33 words includes `continue`, as `docs/handout-language-v1.md` counts it), `AGENTS.md`, `editors/README.md` (against `editors/build.py`), `examples/release-tool/README.md`, `examples/band-facts/README.md` (11 steps and gates, 4 ends, 12 regression cases), the reports READMEs, the level 4 templates, and the module docstrings of `rig.py` and `rigkit.py`. The bookmarks numbers of the handout are true: `sort.batch` 30, `sort.choices` 5, `similar.page_size` 8, 22 nodes (18 steps and gates, 4 ends).

## 2. Not verified

- **The runs with real models.** The numbers in `guide/weak-model.md`, `docs/status.md` and the notes of the examples (137 seconds, 92 of 120, 41 of 60, the chats of 2026-11-25) come from the dated notes. They agree with each other. This review did not run a model.
- **The plugin in the LM Studio chat window.** `docs/status.md` now says that the bookmarks plugin ran there on 2026-11-25. This comes from the dated section of the same page ("installed in LM Studio", "Second chat"). It was not seen in this review.
- **`examples/band-facts/README.md`, "Try it".** It needs the network. Not run.
- **`tool.py resume RUN` after a stop of the process in the middle of a walk.** Not run. `patterns.md`, section 6 now names it from the code.
- **The type check of `examples/release-tool/plugin`.** It has no `node_modules`, so `tsc` was not run there.
- **The viewer** was not opened in a browser in this review. Only its head comment changed.
- **The editor syntax test** (`editors/test-vscode.js`) still needs `vscode-textmate`. Not run.

## 3. Questions for the owner (the code may be wrong)

In each case the text now says what the code does. The code did not change.

1. **A `rerun` can write over the old run.** `rigkit.py` line 322, `new_id()`: the id is the time to the second, plus a counter that starts at 1 in each process. A `rerun` in a new process in the same second as the old run gets the same id. In this review, `tool.py rerun RUN --from tone` wrote over the run folder of RUN, and its `from` named itself. `spec.md`, Section 4 says that `rerun` makes "a new run". It can also happen with two `run` calls in one second. **Answer (2026-11-25):** fix it. `new_id` now takes the first counter whose run does not exist, and reserves its folder with `os.mkdir`. The test `test_a_new_process_does_not_take_the_id_of_a_run` covers it, and the same `rerun` in the same second now gets `-02`.
2. **The doctor line about `permissions` says more than it checks.** `rig_project.py` line 355: the text says that a `permissions` rule "guards every change that cannot be undone", but the check only finds one rule of the group. `levels.md` now says this. **Question:** change the doctor text to "a rule of the group permissions exists", or make the check stronger (for example: the rule is off by default, and a gate reads it)?
3. **A dead field in the plugin bridge.** `templates/plugin/src/bridge.ts` lines 17 and 40: a `finish_step` tool may carry `node` ("the one step that this tool answers"), and `--node` goes to the driver. `rig_project.front()` never sets `node`, so the comment describes the old `finish_<step>` tools. **Question:** remove the field, or set `node` when the flow has exactly one model step with no `out`?
4. **The grammars colour a value that the spec does not have.** `editors/build.py` line 67 colours `?` as "an unknown value", and `editors/README.md` says so. `spec.md` has no `?` value, and `rig.py` reads `?` as a plain word. **Question:** remove the pattern from the grammar, or add the value to the spec?
