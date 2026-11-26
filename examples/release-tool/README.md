# release: the reference example of the Rig kit

A small tool with every part of a level 4 tool. It checks a release folder and publishes it: it writes `published.json` into the folder.

Read it as the pattern for a new tool. `python3 ../../skills/rig/rig.py new DIR NAME --level 4` makes a folder of the same shape.

| File | What it is |
|---|---|
| [release.rig](release.rig) | The source: 5 rules, 1 preset, 3 steps, 8 gates, 3 ends. The lines run in order. |
| [gates.py](gates.py) | The decisions that code makes. Pure Python. |
| [steps.py](steps.py) | The work: read the folder, write `published.json`. |
| [tool.py](tool.py) | The runner: one command line for every front. |
| [tests/](tests/) | Tests of the gates and the steps; 12 regression cases with the answers of the model played from a file. |
| [gen/release.json](gen/release.json) | Compiled: the catalogue that the runner reads. |
| [skill/SKILL.md](skill/SKILL.md) | Compiled: the instructions for Claude. |
| [notes/](notes/), [bugs-and-fixes.md](bugs-and-fixes.md), [reports/](reports/) | The memory of the project. |

## Who decides what

| Gate | Kind | Who decides |
|---|---|---|
| `notes`, `version`, `tests-required`, `rewritten`, `allowed` | hard | code; a fail goes to an end |
| `tests` | soft | code; a fail is reported, and the run goes on (`tests-required` stops it while `tests.required` is on) |
| `tone` | model | the model; the result is a guess. On fail, `retry notes.rounds` sends the run back to the step `rewrite` |
| `approve` | human | a person; the model cannot answer it |

## Try it

```bash
python3 tool.py run '{"folder": "tests/cases/good"}'
```

Code walks `collect`, `notes`, `version`, `tests-required` and `tests`, then the run waits at `tone` for the model. The step `rewrite` is skipped: its line `if tone.failed` is not true before the first answer of `tone`. Give the answer with the short run id of the result (for example `r1`):

```bash
python3 tool.py answer RUN '{"pass": true}'
```

Now the run waits at `approve` for a person. `answer` is refused here. A person answers:

```bash
python3 tool.py approve RUN yes
```

The run ends at `ready`: a dry run, because `permissions.publish` is off. Other cases: `tests/cases/short-notes`, `bad-version`, `tests-red`.

With `{"pass": false}` at `tone`, the run goes back to `rewrite` (at most `notes.rounds` times): the model rewrites the notes, code checks their length (`rewritten`), and the model decides `tone` again.

Each run has a folder in `runs/`, with a copy of the flow, the rules and every answer. Two commands use it:

```bash
python3 tool.py rerun RUN --from tone --set notes.rounds=0
```

```bash
python3 tool.py replay RUN
```

`rerun` starts a new run with the state of the old one before `tone`. `replay` runs the whole flow again with the recorded answers and the current code, and prints the differences: a flow test with no model.

## Check it

```bash
python3 ../../skills/rig/rig.py doctor .
```

```bash
python3 tool.py regress tests/regression-set.json
```

```bash
python3 ../../skills/rig/rig.py serve release.rig --json gen/release.json
```

The last command shows the flow as a graph. Values can be changed there; the wires are changed in `release.rig`. Each node stands in the lane of who decides it: code, the model or a person. After some runs, choose one in the list **run…** above the graph: the page lights up the path that the run took, and a click on a node shows what happened there.
