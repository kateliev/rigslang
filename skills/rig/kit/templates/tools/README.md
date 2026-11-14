# __NAME__

A Rig tool, level __LEVEL__ (__LEVEL_NAME__). TODO: say what it does.

| File | What it is |
|---|---|
| `__NAME__.rig` | The source: the intent, the inputs and the output of each tool. Change it here. |
| `tools.py` | The code: one function for each tool unit. |
| `tool.py` | The command line that every front calls. |
| `tests/` | The tests. |
| `gen/` | Compiled from the source: the catalogue and the tool definition. Do not edit. |
| `rigkit.py` | The tool's own copy of the Rig runtime. `rig.py build` keeps it current. |
| `rig.json` | The project file: the level, the source, the compiled files, the tests command. |

`RIG` is the path of `skills/rig/rig.py` in the Rig repository.

```bash
python3 tool.py call __NAME__ '{"text": "some words"}'
```

After a change of the source or the code:

```bash
python3 RIG build .
```

```bash
python3 RIG doctor .
```
