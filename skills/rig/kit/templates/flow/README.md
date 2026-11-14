# __NAME__

A Rig tool, level __LEVEL__ (__LEVEL_NAME__). TODO: say what it does.

| File | What it is |
|---|---|
| `__NAME__.rig` | The source: the rules, the steps, the gates and the ends. Change the flow and the values here. |
| `gates.py` | Every decision that code can make. Pure Python, with tests. |
| `steps.py` | The work. The only code that touches the world. |
| `tool.py` | The runner: one command line that every front calls. |
| `tests/` | The tests of the gates and the steps, and the regression set. |
| `gen/` | Compiled from the source: the catalogue. Do not edit. |
| `skill/SKILL.md` | Compiled from the source: the instructions for Claude. Do not edit. |
| `rigkit.py` | The tool's own copy of the Rig runtime. `rig.py build` keeps it current. |
| `rig.json` | The project file: the level, the source, the compiled files, the tests command. |
| `runs/` | One file for each run: where it is, its state and its path. Not in version control. |

`RIG` is the path of `skills/rig/rig.py` in the Rig repository.

## Run

```bash
python3 tool.py run '{"item": "a longer item"}'
```

The result is one JSON line. `outcome`: the run ended. `waiting`: the run needs the model or a person; answer with `answer` or `approve`.

## Change

Change a value or the flow in `__NAME__.rig`, and the code in `gates.py` and `steps.py`. Then:

```bash
python3 RIG build .
```

```bash
python3 RIG doctor .
```

To see the flow as a graph and change values on a page:

```bash
python3 RIG serve __NAME__.rig --json gen/__NAME__.json
```
