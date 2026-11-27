# RIGS v2 builder cheatsheet

One-page reference for building and maintaining rigs (instrumental agent tools) with RIGS v2. Full language rules: [spec.md](spec.md). Method: [guide/README.md](guide/README.md).

## 1. Canonical `.rig` grammar

```rig
unit my-flow
  intent "one sentence: what the flow must do"
    audience "who reads the output"
    style "concise, plain words"
    never "write without human approval" -> approve
  in item path "the input item"
  out text "the result"
  code gates gates.py
    test tests/test_gates.py
  code steps steps.py
    test tests/test_steps.py

  ; Rules: single `rule`, compact `rules <group>` table, or external `rules "rules.json"` sidecar
  rules limits
    cap     100                 1..1000 "Max items"        ; inline <min>..<max> or open 0.._ / _..100
      ui                                                   ; expose UI control (toggle|select|slider|number|input)
    tiers   {fast: 20, careful: 100} 1.._ "Max per mode"   ; [list], (tuple), {dict}
    bounds  (0.5, 2.0)          0.1..5.0 "Allowed scale"
    mode    careful                      "Strategy"
      options strict | careful | off                       ; choice strings (off/true/none stay strings)
      ui select
  rule batch.size 10 1..100 "Items per chunk"
    ui
  rule permissions.write off "Allow writes"
    ui
  preset careful
    set limits.cap 50

  queue by steps.pending                ; optional external item discovery for queues & next-batch
  step read "Read" by steps.read        ; deterministic code step
    do "read the item"
    reads limits.*                      ; group wildcard expands to all limits.* rules
    brief count summary                 ; save full payload to artifact; show compact keys in sees
    timeout 30s
  gate valid hard "Valid input"         ; hard | soft | model | human
    check "count <= {limits.cap}"
    by gates.valid
    fail -> stop "too many items"
  step classify "Classify" by model     ; lightweight single-shot fill-in (fast worker tier)
    do "pick a label"
    sees read
    out str
  reason plan "Propose options"         ; deliberative/creative cognition (reasoning model tier)
    intent "propose safe options"
      style "short bullets"
    do "explore options using read-only tools"
    mode creative                       ; careful (default) | creative
    tools steps.inspect
    budget 3                            ; hard tool-call budget
    candidates 2                        ; return 2 distinct items of out type
    sees read classify
    out {title: str, summary: str, note?: str}
  gate plan-ok hard "Plan valid" by gates.plan_ok
    retry 2
    fail -> stop "invalid plan"
  until style.pass                      ; multi-gate repair loop (resolved soft problems clear on retry)
    retry 3
    fail -> held
    gate style soft by gates.style
    step fix by model
      if style.failed
      do "fix style problems"
      sees plan
      out text
  gate approve human "Apply changes?"
    sees read plan
    fail -> stop "declined"
  gate allowed hard "May write" by gates.may_write
    fail -> ready "dry run"
  step write by steps.write
  end done "Done"
  end ready "Dry run"
  end held "Held back"
  end stop "Stopped"
  rollback                              ; runs on hard fail, error, unattended deferral, or restore
    step undo by steps.undo
  finally
    step summary by steps.summary
```

- **Types (AST-parsed Python/TS style):** `str`, `text`, `word`, `path`, `int`, `float`, `bool`, `list`, `dict`, `any`, `list[T]`, `tuple[T1, T2]` (or `(T1, T2)`), `dict[str, T]` (or `dict[T]`), `{k1: T1, k2?: T2}`, `T?` (or `T | None`), `"a" | "b"` (or `T1 | T2`).
- **Paths (in `if`, `until`, `for`, `sees`):** dotted keys only (`a.b`), never expressions. Truthy = not missing, `null`, `false`, `""`, `[]`, `{}` (`0` is truthy).
- **Rule reads & overrides:** inferred automatically from `R('group.name')` / `R.get('group.name')` in Python, `{group.name}` / `{group.name.key}` in text, and `retry`/`budget`/`candidates` rules. Override whole rules (`--set k=v`) or single dict keys (`--set group.name.key=v`).

## 2. Exact Python signatures

```python
# Step (steps.py): value is stored at state[<step_id>]; state['_rig'] holds run lifecycle metadata
def read(state, R):
    limit = R('limits.max')
    unattended = state['_rig']['unattended']  # also: run_id, in_rollback, in_finally, rolled_back, end
    return {'count': 1, 'summary': 'ok', 'unattended': unattended, 'full_data': [...]}

# Queue discovery (steps.py): returns list of input dicts
def pending(state, R):
    return [{'item': 'a'}, {'item': 'b'}][:int(R('batch.size'))]

# Read-only reason arena tool (steps.py): receives a deep copy of state.
# The model sees the docstring (waiting.tool_help): say what it does and what JSON it takes.
def inspect(state, R, args):
    '''Show the summary of the file. Takes {"q": "<word>"} to search it.'''
    return {'preview': state['read']['summary'], 'q': args.get('q')}

# Gate (gates.py): pure function; returns bool or verdict dict
def valid(state, R):
    ok = state['read']['count'] <= R('limits.max')
    return {'pass': ok, 'problems': [] if ok else ['too many items']}

# Human gate with options: reads state[<gate_id>]['answer']
def apply(state, R):
    ans = state['pick']['answer']
    return {'pass': ans in ('yes', 'no'), 'choice': ans}
```

## 3. `rig.json` keys and three levels

```json
{
  "rig": 2,
  "name": "my-tool",
  "level": 3,
  "source": "my-tool.rig",
  "unit": "my-tool",
  "driver": "python3 tool.py",
  "build": {"gen": "gen", "skill": "skill/SKILL.md"},
  "kit": "rigkit.py",
  "tests": "python3 -m unittest discover -s tests",
  "regression": "tests/regression-set.json"
}
```

| Level | Name | Doctor checks added at this level |
|---|---|---|
| 1 | checked | Valid v2 source; flow, intent, typed/described inputs; build current; no numbers in prose; driver & tests pass; at least one gate; AST-verified tested code on every `hard`/`soft` gate; every rule read; `out` on every model step / `reason`; `never` boundaries tracked. |
| 2 | flow | Named `end` nodes; all nodes reachable; flow ends at an `end`; Agent Skill compiled (`build.skill`); regression set exists, has baselines, covers every `end`, and passes. |
| 3 | production | `README.md`, `notes/project-facts.md`, `notes/failures-log.md`, `bugs-and-fixes.md`, `reports/`; `permissions.*` defaults to `off` and is read by a `hard` gate; `human` gate (or `"human"` note); `rollback` hook note. |

## 4. Commands

**Project & language (`RIG` = `python3 skills/rig/rig.py`):**

| Command | Use |
|---|---|
| `RIG new DIR NAME [--level 1\|2\|3] [--template flow\|host]` | Create a working project (`host`: host-adapter + pure-Python engine split). |
| `RIG build [DIR] [--check]` | Compile catalogue, Agent Skill, `rigkit.py`, and plugin front. |
| `RIG doctor [DIR] [--no-tests] [--json]` | Check project for its level. |
| `RIG test [DIR] [--replay RUN]` | Run tests, or replay recorded answers of `RUN`. |
| `RIG plugin DIR [--owner NAME]` | Add LM Studio plugin front. |
| `RIG mcp-config DIR [--http URL] [--api-url URL] [--model NAME] [--provider P]` | Print stdio or Streamable HTTP MCP config JSON. |
| `RIG check FILE` / `RIG serve FILE` / `RIG compile json\|skill FILE` | Validate, open graph viewer, or compile one unit. |

**Tool runner (`python3 tool.py ...` — one JSON line per call):**

| Command | Use |
|---|---|
| `run '[JSON]' [--preset P] [--set k=v]` | Start a run (`r1`, `r2`, ...). |
| `batch ITEMS [--report P] [--workers N]` | Run a list/file of inputs. |
| `next-batch [ITEMS] [--size N] [--report P]` | Run one chunk unattended under lock + circuit breaker; roll back & defer waiting items. |
| `queues` | Open `left_for_model`, `waits_for_person`, plus external `pending` items if `queue` declared. |
| `answer RUN JSON [--node ID] [--meta JSON]` | Model answer (`{"pass": ...}` or `{"result": ...}`). |
| `arena RUN TOOL [JSON]` | Invoke a read-only tool in a waiting `reason` block (within `budget`). |
| `work RUN [--api-url URL] [--model NAME] [--provider openai\|ollama\|anthropic] [--reason-api-url URL] [--reason-model NAME]` | Two-tier worker for `step ... by model` and `reason` blocks. |
| `approve RUN [yes\|no\|WORDS]` | Person answer for a `human` gate. |
| `restore RUN` / `artifact RUN NAME [--path K]` | Execute `rollback` block explicitly; inspect a saved `brief` payload read-only. |
| `mcp [...]` / `serve-http [--port 8780]` / `serve-stdio` | Stdio MCP, Streamable HTTP MCP + OpenAPI 3.1 + localhost approval UI, or warm stdio bridge. |
| `drop` / `list` / `prune` / `resume` / `status` / `rerun` / `replay` / `rules` / `flow` / `regress` / `eval` | Run lifecycle, regression tests, and ground-truth dataset scoring (`eval --baseline`). |
