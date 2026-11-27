# __NAME__

A RIGS v2 host-adapter rig, level __LEVEL__ (__LEVEL_NAME__). TODO: say what it does.

| File | What it is |
|---|---|
| `__NAME__.rig` | The Idea: rules, steps, gates, ends, queue, and rollback. Domain-agnostic and host-free. |
| `engine.py` | Pure-Python domain logic. Zero host imports; unit-tested directly. |
| `adapter.py` | The World: thin host-app RPC / I/O adapter (`rigkit.rpc_call`, `rigkit.step`). |
| `steps.py` | Wires `adapter.py` and `engine.py` to the flow. |
| `gates.py` | Pure-Python decisions. |
| `tool.py` | The runner and universal fronts (`run`, `next-batch`, `restore`, `mcp`, `serve-http`). |
| `tests/` | Unit tests for engine, gates, steps, and (from level 2) the regression set. |
| `gen/` | Compiled catalogue. Do not edit. |
| `rigkit.py` | The tool's own copy of the RIGS runtime. `rig.py build` keeps it current. |
| `rig.json` | Project manifest. |

## Run

```bash
python3 tool.py run '{"item": "a longer item"}'
python3 tool.py next-batch --size 10
python3 tool.py serve-http --port 8780
```
