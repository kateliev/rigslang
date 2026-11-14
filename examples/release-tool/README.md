# release: the reference example of the Rig kit

A small tool with every part of a level 4 tool. It checks a release folder and publishes it: it writes `published.json` into the folder.

Read it as the pattern for a new tool. `python3 ../../skills/rig/rig.py new DIR NAME --level 4` makes a folder of the same shape.

| File | What it is |
|---|---|
| [release.rig](release.rig) | The source: 5 rules, 1 preset, 3 steps, 7 gates, 3 ends. |
| [gates.py](gates.py) | The five decisions that code makes. Pure Python. |
| [steps.py](steps.py) | The work: read the folder, write `published.json`. |
| [tool.py](tool.py) | The runner: one command line for every front. |
| [tests/](tests/) | Tests of the gates and the steps; 11 regression cases with the answers of the model played from a file. |
| [gen/release.json](gen/release.json) | Compiled: the catalogue that the runner reads. |
| [skill/SKILL.md](skill/SKILL.md) | Compiled: the instructions for Claude. |
| [notes/](notes/), [bugs-and-fixes.md](bugs-and-fixes.md), [reports/](reports/) | The memory of the project. |

## Who decides what

| Gate | Kind | Who decides |
|---|---|---|
| `notes`, `version`, `rounds`, `allowed` | hard | code; a fail blocks |
| `tests` | soft | code; a fail is reported, and it stops the run only while `tests.required` is on |
| `tone` | judge | the model; the result is a guess |
| `approve` | human | a person; the model cannot answer it |

## Try it

```bash
python3 tool.py run '{"folder": "tests/cases/good"}'
```

Code walks `collect`, `notes`, `version` and `tests`, then the run waits at `tone` for the model. Give the answer with the run id of the result:

```bash
python3 tool.py answer RUN '{"pass": true}'
```

Now the run waits at `approve` for a person. `answer` is refused here. A person answers:

```bash
python3 tool.py approve RUN yes
```

The run ends at `ready`: a dry run, because `permissions.publish` is off. Other cases: `tests/cases/short-notes`, `bad-version`, `tests-red`.

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

The last command shows the flow as a graph. Values can be changed there; the wires are changed in `release.rig`.
