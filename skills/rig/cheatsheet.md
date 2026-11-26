# Rig builder cheatsheet

One-page reference for building and maintaining Rig tools. Full language rules: [spec.md](spec.md). Method: [guide/README.md](guide/README.md).

## 1. Canonical `.rig` grammar

```rig
unit my-tool tool                       ; scope: tool (default) or agent
  intent "one sentence: what the unit does"
  in text str "input description"
  out (record words int) "output description"
  example "two words" => (2)            ; executed by doctor on tool units
  code tools.py
    test tests/test_tools.py

unit my-agent agent
  intent "one sentence: what the agent does"
  in item path "the input item"
  out text "the result"
  uses helper-tool other.rig            ; optional dependency
  code gates gates.py
    test tests/test_gates.py
  code steps steps.py
    test tests/test_steps.py

  rule limits.max 100 "Max items"       ; types: number, on/off, choice, text, /regex/, (list)
    range 1 1000                        ; for number rules
    note "where the value comes from"
  rule mode.kind fast "Run mode"
    options fast | careful
  rule permissions.write off "Allow writes"
  preset careful
    set mode.kind careful

  step read "Read" by steps.read        ; inline "by" allowed on step and gate
    do "read the item"
    timeout 30s                         ; s, m, h, or d
  gate valid hard "Valid input"         ; kinds: hard | soft | model | human
    check "count <= {limits.max}"       ; {group.name} substitutes the rule value
    by gates.valid
    fail -> stop "too many items"       ; inline "fail -> end" also allowed
  step draft "Draft" by model
    if tone.failed                      ; gate state has .pass and .failed
    do "write a short draft"
    sees read draft tone                ; state paths shown to model/person
    out text                            ; required on every "by model" step
  gate tone model "Tone check"
    check "pass if plain and clear"
    sees read draft
    retry 2                             ; retries nearest preceding step (or a number rule id)
    fail -> stop "tone failed"
  for part in read.parts                ; blocks: for, until, if, else, section, finally
    tolerate 20%
    fail -> held "too many left"
    step work by steps.work
    gate part-ok hard by gates.part_ok
      fail -> continue "skip this part" ; only inside a "for" block
  if read.extra
    gate pick human "Choose items?"
      options yes | no                  ; human choice gate needs "by"
      sees read.extra
      by steps.apply
  else
    step plain by steps.plain
  until draft.done
    retry 3
    fail -> held
    step refine by model
      do "refine"
      sees draft
      out (record done bool text str)
  section "Finish"
    gate allowed hard "May write" by gates.may_write
      fail -> ready "dry run"
    step write by steps.write
  end done "Done"
  end ready "Dry run"
  end held "Held back"
  end stop "Stopped"
  finally
    step summary by steps.summary
```

- **Types:** `str`, `text`, `word`, `path`, `int`, `float`, `bool`, `list`, `dict`, `any`, `(list T)`, `(tuple T1 T2 ...)`, `(record k1 T1 k2 T2 ...)`, `(maybe T)`, `(one-of v1 v2 ...)`.
- **Paths (in `if`, `until`, `for`, `sees`):** dotted keys only (`a.b`), never expressions. Truthy = not missing, `null`, `false`, `""`, `[]`, `{}` (`0` is true).
- **Rule reads:** inferred automatically from `R('group.name')` / `R.get('group.name')` in Python, `{group.name}` in text, and `retry <rule>`. Write `reads group.name` only for non-Python code or indirect reads.

## 2. Exact Python signatures

```python
# Tool unit (tools.py): function name is unit name with "-" -> "_"
def my_tool(text):
    return {'words': len(text.split())}

# Step (steps.py): value is stored at state[<step_id>]
def read(state, R):
    limit = R('limits.max')
    return {'items': [...], 'limit': limit}

# Gate (gates.py): pure function; returns bool or verdict dict
def valid(state, R):
    n = len(state['read']['items'])
    if n <= R('limits.max'):
        return True
    return {
        'pass': False,
        'when': 'too many items',                       # matches fail -> end "when"
        'problems': [f'{n} items (limits.max {R("limits.max")})'],
        'count': n,                                     # extra keys go to trace facts
    }

# Human gate with options (steps.py or gates.py): reads state[<gate_id>]['answer']
def apply(state, R):
    ans = state['pick']['answer']
    if ans in ('yes', 'no'):
        return {'pass': True, 'choice': ans}            # extra keys merge into state['pick']
    return {'pass': False, 'problems': [f'unknown answer: {ans}']}  # gate asks again
```

## 3. `rig.json` keys and levels

```json
{
  "rig": 1,
  "name": "my-tool",
  "level": 4,
  "source": "my-tool.rig",
  "unit": "my-tool",
  "driver": "python3 tool.py",
  "build": {"gen": "gen", "skill": "skill/SKILL.md"},
  "kit": "rigkit.py",
  "tests": "python3 -m unittest discover -s tests",
  "regression": "tests/regression-set.json",
  "plugin": {"folder": "plugin", "owner": "local", "timeout_s": 120,
             "work": {"think": false, "max_tokens": 4000, "max_calls": 50}}
}
```

Optional: `"human": "reason"` (level 4 when no `human` gate is needed).

| Level | Name | Doctor checks added at this level |
|---|---|---|
| 1 | tools | Valid source; units have code/flow + intent + typed/described inputs; build current; no numbers in node text; tests pass; tool `example` lines pass. |
| 2 | checked | At least one gate; every `hard`/`soft` gate binds to an existing function referenced in code by its test file (AST); every rule is read; every `model`/`human` gate has check/question; every step has `by`; every `by model` step has `out`. |
| 3 | flow | Flow with `end` nodes; all nodes reachable; flow ends at an `end`; `driver` and compiled `skill` set; regression set exists, has baselines, covers every `end`, and passes. |
| 4 | production | `README.md`, `notes/project-facts.md`, `notes/failures-log.md`, `bugs-and-fixes.md`, `reports/`; `permissions.*` rule defaults to `off` and is read by a `hard` gate; `human` gate (or `"human"` note). |

## 4. Commands

**Project & language (`RIG` = `python3 skills/rig/rig.py`):**

| Command | Use |
|---|---|
| `RIG new DIR NAME --level 1\|2\|3\|4` | Create a working project at the given level. |
| `RIG build [DIR] [--check]` | Compile catalogue, lean skill, tool JSONs, `rigkit.py`, and plugin front. |
| `RIG doctor [DIR] [--no-tests] [--json]` | Check the project for its level (`--json` for structured output). |
| `RIG test [DIR] [--replay RUN]` | Run project tests, or replay recorded answers of `RUN` against current code. |
| `RIG plugin DIR [--owner NAME]` | Add the LM Studio plugin front. |
| `RIG mcp-config DIR [--api-url URL] [--model NAME]` | Print a JSON MCP server config block for the tool. |
| `RIG check FILE` | Validate `.rig`, AST-check bindings/tests, show coverage and gate literal warnings. |
| `RIG serve FILE [--json OUT] [--runs DIR]` | Open the local viewer/graph on `127.0.0.1`. |
| `RIG compile json\|skill\|tool FILE [UNIT]` | Compile one unit (`--preset`, `--driver`, `--rules`, `-o`). |

**Tool runner (`python3 tool.py ...` — one JSON line per call):**

| Command | Use |
|---|---|
| `run '[JSON]' [--preset P] [--set k=v]` | Start a run (`r1`, `r2`, ...). |
| `batch ITEMS [--report P] [--workers N]` | Run a list/file of inputs (optionally parallel). |
| `queues` | Waiting runs split into `left_for_model` and `waits_for_person`. |
| `answer RUN JSON [--node ID] [--meta JSON]` | Model answer (`{"pass": ...}` or `{"result": ...}`). |
| `approve RUN [yes\|no\|WORDS]` | Person answer for a `human` gate. |
| `work RUN [--api-url URL] [--model NAME]` | Run `by model` steps in fresh contexts (`--api-key`, `--think`, `--max-tokens`, `--max-calls`). |
| `mcp [--api-url URL] [--model NAME]` | Run the zero-dependency JSON-RPC 2.0 stdio MCP server. |
| `serve-stdio` | Warm JSON-lines driver loop (used by the plugin bridge). |
| `drop RUN [REASON]` / `list [--limit N]` / `prune [--keep N]` | Drop a waiting run; list runs; remove old finished runs. |
| `resume RUN` / `status RUN` | Continue an interrupted run; inspect status and apply timeouts. |
| `rerun RUN --from ID [--set k=v]` / `replay RUN` | Branch from a checkpoint (`marks/<node>.json`); replay recorded answers. |
| `rules` / `flow` / `call TOOL [JSON]` / `regress FILE [--baseline]` | Inspect rules/flow; call level-1 tool; run or update regression baselines. |
