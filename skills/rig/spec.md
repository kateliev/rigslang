# RIGS language specification, version 2

RIGS stands for **Reason, Intent, Gate, Steps** — the language for making **rigs**. Every letter is a runtime-enforced construct:

- **Reason:** `reason` blocks hold genuine deliberative or creative cognition (`mode careful | creative`, optional read-only `tools` + `budget`, optional `candidates`, typed `out`).
- **Intent:** unit-level and `reason`-level `intent` carries `audience`, `style`, and `never` invariants, injected automatically into every `reason` call and `model` gate.
- **Gate:** code decides `hard` and `soft` gates, the model decides `model` gates (marked **guessed**), and a person decides `human` gates.
- **Steps:** `step ... by <prefix.fn>` runs deterministic code (the only place that touches the world, via thin adapters), while `step ... by model` runs lightweight single-shot schema-bound fill-ins.

RIGS separates **the Idea** (`.rig` + pure-Python engine and gates + `rigkit.py`) from **the World** (thin target adapters) and **the Caller** (Agent Skill, stdio and Streamable HTTP MCP, OpenAPI 3.1, localhost approval UI, local plugin).

One `.rig` file defines a **rig** (one or more orchestrated `unit`s). RIGS files use the extension `.rig`. They are UTF-8 text. This page is the one definition of the language.

Two limits hold:

1. **RIGS is not a general programming language.** It has no variables, no assignments and no expressions. The language says the order of the work and who decides. Code (the `by` functions) computes everything.
2. **The language stays small.** One word has one meaning. No host-application quirk enters `.rig`.

## 1. Syntax

```
node     := head arg* [comment] NEWLINE [children]
children := INDENT node+ DEDENT
arg      := word | number | "string" | /regex/ | [list] | (tuple) | {dict} | type
comment  := ; text            (outside strings and brackets, to the end of the line)
```

- Every line is a **node**: a head word, then arguments.
- Lines indented under a node are its **children**.
- Indent with spaces (2 per level is the convention). A tab in the indentation is an error.
- A **string** is in double quotes. Use `\"` for a quote and `\\` for a backslash.
- A **regex** is between slashes: `/^[a-z]+$/`.
- A **word** is any run of characters without spaces or brackets: `slugify`, `->`, `release.min_words`, `20%`.
- **Data literals** use Python/JS bracket notation, parsed safely with Python's `ast` parser (no expressions):
  - `[a, b]` is a variable-length **list**: `rule dupes.tracking ["utm_", "fbclid"]`.
  - `(a, b)` is a fixed-length **tuple**: `rule scale.bounds (0.5, 2.0)` (a 1-item tuple takes a trailing comma: `(1,)`).
  - `{k: v, ...}` is a key-value **dict** (bare identifier keys or quoted string keys): `rule limits.depth {small: 8, medium: 16, large: 28}`.
- Blank lines and comments are ignored.
- **On the line of its node.** `by <name>` can stand at the end of a `step`, `gate` or `queue` line, and `fail -> <end> ["why"]` at the end of a `gate` line. `step read by steps.read` is the same as a `step read` line with a `by steps.read` line under it.

## 2. Words

A file holds one or more `unit` nodes. Every other word goes inside a unit.

### Container

| Node | Meaning |
|---|---|
| `unit <name>` | An orchestrated flow unit. Every unit in version 2 is a flow (micro scopes `tool` and `agent` were removed in version 2). |

### What the unit does

| Node | Meaning |
|---|---|
| `in <name> [type] ["text"]` | An input. Repeat for each input. The text says what the input is. |
| `out [type] ["text"]` | The output. The text says what the output is. |
| `intent "text"` | What the unit (or a `reason` block) must do, in plain language. |
| ↳ `audience "text"` | Optional child of `intent`: who reads or receives the output. |
| ↳ `style "text"` | Optional child of `intent`: tone, format or length guidance. |
| ↳ `never "text" [-> <gate-id>]` | Optional child of `intent` (repeatable): an invariant boundary. Linking `-> <gate-id>` binds the boundary to an explicit `hard`, `model` or `human` gate (tracked by `rig.py doctor`). |

**Types.** Types use Python/TypeScript bracket notation, parsed via Python's `ast`:

| Type | Values |
|---|---|
| `str`, `text`, `word`, `path` | a string |
| `int` | a whole number |
| `float` | a number |
| `bool` | `true` or `false` |
| `list`, `dict`, `any` | any list, any dict, any value |
| `list[T]` | a list; each item has type `T` |
| `tuple[T1, T2, …]` or `(T1, T2, …)` | a fixed-length list with one item of each type, in order |
| `dict[str, T]` (or `dict[T]`) | a dict with string keys where every value has type `T` |
| `{name1: T1, name2?: T2, …}` | a record with fixed fields (`name?: T` marks an optional field that can be omitted or `null`) |
| `T?` or `T \| None` | a value of type `T`, or `null` (optional on an `in` port or record field) |
| `"v1" \| "v2"` or `T1 \| T2` | one of these literal values (`Literal[...]`), or a union of types |

The checker warns about a type that it does not know. Each `in` port compiles its type to a JSON Schema (`schema`), and the runner validates inputs against those schemas at runtime (`Kit.run`), refusing a mismatch.

### Context

| Node | Meaning |
|---|---|
| `note "text"` | A remark that must stay with its parent. Use it when the code looks wrong but is right, or when a value must not change. |
| `code <prefix> <path>` | The functions of the steps, gates, tools and queue of this unit live in the file at `path` (relative to the `.rig` file). A `by` or `tools` entry names one as `prefix.function`, for example `by gates.notes_ok`. |
| ↳ `test <path>` | Optional child of `code`: the test file of that code. For Python (`.py`) files, the checker parses the AST to confirm the function is defined and referenced in code (not only in comments or docstrings) in the test file; other languages fall back to name matching. Such a function is **tested**. |
| `queue ["name"] by <prefix.function>` | Optional external item discovery step. Returns a list of input records for `queues` and chunked unattended `next-batch` runs. May carry `reads` and `note`. |
| `rule <group.name> <value> [<min>..<max>] ["label"]` | A parameter. The id has a group and a name, joined by a dot. The value is a number, `on`/`off`, a word, a `"string"`, a `/regex/`, a `[list]`, a `(tuple)`, or a `{key: value}` dict. An optional inline range (`50..5000`, `0.._`, `_..100`) sets numeric bounds directly on the line. Put the unit of the value in the label: `rule sort.batch 60 1..500 "Bookmarks in one batch"`. |
| ↳ `range <min> <max>` | Optional child of `rule`: the limits of a number, or of every number in a numeric list, tuple, or dict. Use `_` for an open bound (`range 0 _`, `range _ 100`; at least one bound must be a number). |
| ↳ `options a \| b \| c` | Optional child of `rule`: the string values that a `choice` rule can have (including unquoted words such as `off`, `on`, `true`, `false`, or `none`). |
| ↳ `ui [toggle\|select\|slider\|number\|input]` | Optional child of `rule`: exposes the rule as a control in compiled UI fronts (web dashboard, plugin per-chat settings, viewer), wired to per-run rule overrides. The widget defaults from the rule type. |
| ↳ `note "text"` | Short remark on where the value comes from (kept out of compiled `SKILL.md` prompts; long calibration logs belong in `notes/`). |
| `rules <group>` | Compact rule table block for `<group>` (`^[a-z][a-z0-9_]*$`). Each child line `<name> <value> [<min>..<max>] ["label"]` desugars to `rule <group>.<name> ...` and accepts the same indented children (`range`, `options`, `ui`, `note`). |
| `rules "<path>.json"` | Repeatable external JSON sidecar (resolved relative to the `.rig` file). Accepts `{"rules": [...], "presets": {...}}` or a JSON array `[...]` of rule entries (`id`, `value`, optional `type`, `min`, `max`, `options`, `ui`, `label`, `note`). Validated identically to inline rules; `rig.py serve` updates imported rule values inside `<path>.json`. |
| `preset <name>` | A named set of rule values, for example a fast mode and a careful mode. |
| ↳ `set <rule-id> <value>` | Child of `preset`: one rule and its value in this preset. The same limits (and tuple length) apply. |

```rig
unit sizes
  intent "measure a text and check it against a character limit"
    audience "editors"
    style "short numeric summary"
    never "accept an over-long text" -> fit
  in text str "the text to measure"
  out {words: int, characters: int} "the counts"
  code steps steps.py
    test tests/test_steps.py
  code gates gates.py
    test tests/test_gates.py
  rules size
    limit 1000                        1..100000 "Longest text, in characters"
      ui
      note "longer texts did not come up in the tests"
    tiers {short: 200, standard: 1000} 1.._     "Tier limits, in characters"
    mode  fast                                  "Mode"
      options fast | careful | off
      ui
  preset careful
    set size.mode careful
  step measure by steps.measure
    do "count words and characters"
    reads size.*
  gate fit hard "Within limit"
    check "at most {size.limit} characters (short tier: {size.tiers.short})"
    by gates.fit
    fail -> too-long "over limit"
  end done "Measured"
  end too-long "Too long"
```

**Rule names in text.** In any string of a unit, `{group.name}` names a rule of the unit (and `{group.name.key}` names a key of a `dict` rule). The checker refuses a name or dict key that is not defined. The compilers write the value in its place (Section 6), and `--set group.name.key=value` overrides one key of a `dict` rule for a run. Text in braces without a dot, for example `{word}`, is plain text.

### The flow

**The order of the lines is the order of the flow.** A step or reason block, then the next line. A gate that passes goes on to the next line. A gate that fails goes to an end. The flow never jumps back: the only ways back are the loop blocks (`for`, `until`) and `retry`.

Nodes:

| Node | Meaning |
|---|---|
| `step <id> ["name"]` | Deterministic code (`by <prefix.fn>`) or a single-shot schema-bound model fill-in (`by model`). Its value goes to `state[<id>]`. |
| `reason <id> ["name"]` | Deliberative or creative cognition. Never takes `by` and never mutates the world directly; gates guard the exit. Routes to the reasoning model tier. |
| `gate <id> hard\|soft\|model\|human ["name"]` | A checkpoint. For a `human` gate, the name is the question: `gate approve human "Write the file?"`. |
| `end <id> ["label"]` | An outcome. The run stops here. |

Children of `step`, `reason` and `gate`:

| Node | Of | Meaning |
|---|---|---|
| `do "text"` | step, reason | What the step or reason block does. |
| `by <prefix.function>` | step, gate, queue | The code that does the step, decides the gate, or discovers queue items. More than one `by` runs in order; for a gate, until one fails. |
| `by model` | step | Single-shot structured model call (`sees` -> `out`, no tools, thinking off by default). Requires `out <type>`. Hardening candidate (`by model` -> `by steps.fn`). |
| `intent "text"` | reason | Local intent for this reasoning block (may carry `audience`, `style`, `never`). Combined with unit intent automatically at runtime. |
| `mode careful\|creative` | reason | `careful` (default, thinking-enabled synthesis or diagnosis) or `creative` (divergent exploration). |
| `tools <prefix.fn>*` | reason | Read-only helper functions available inside the reasoning arena. Run on a deep copy of `state` so they can never mutate run state. The docstring of each function is shown to the model as `waiting.tool_help`: it must say what the tool does and which JSON arguments it takes. |
| `budget <n>` | reason | Hard maximum number of read-only tool calls per attempt (`n` >= 1 or a number rule id). |
| `candidates <n>` | reason | Generate `n` distinct options (`n` >= 2 or a number rule id) matching `out`, returned as a list for a `hard` gate to filter and a `model` or `human` gate to pick. |
| `out <type>` | step, reason | The type of what the model step or reason block gives. Required on every `by model` step and `reason` block; enforced at runtime by schema validation. |
| `brief <key>*` | step, reason | Compact summary keys shown to models in `sees`. The runner saves the full payload to `runs/<run>/artifacts/<id>.json` and exposes read-only `artifact` inspection. |
| `check "text"` | gate | What the gate checks, or what the model or the person must decide, in plain words. |
| `reads <rule-id>*` | step, reason, gate, queue | Rules used by this node. Supports `<group>.*` wildcards (expanding to all defined rules in `<group>`). Also inferred automatically from `{group.name}`, `retry`/`budget`/`candidates` (including `until` `retry`), and `R('group.name')` / `R.get('group.name')` in Python AST. |
| `sees <path>*` | step, reason, gate | State paths shown to the model or person. A path is a step/reason id, an input, or a `for` item, then keys: `sees read.summary write`. |
| `options a \| b \| c` | human gate | Answers the person can give. The first is the default. Needs `by`: code that reads `state[<id>]["answer"]`. |
| `retry <n>` | hard gate, model gate | On fail: redo the nearest `step` or `reason` before the gate (only gates may stand between them), at most `n` times (`n` >= 1 or a number rule id). |
| `timeout <time>` | step, reason, model gate, human gate | For example `timeout 5m`, `timeout 3d`: a number and `s`, `m`, `h` or `d`. See Section 5. |
| `if <path>` | step, reason, gate | Runs only when this path of the state is truthy. Else the flow goes on to the next line. |
| `fail -> <end> ["why"]` | gate | Where to go on fail: an end. Repeat for more than one reason (`"when"`). |
| `fail -> continue ["why"]` | gate in a `for` | Leave this item, record it in the report, and go to the next item. |
| `note "text"` | all | A remark. |

```rig
step read "Read the export" by steps.read
  do "read the file"
  brief count summary
gate file-ok hard "A bookmarks export"
  check "the file is a bookmarks file with at least one bookmark"
  by gates.file_ok
  fail -> bad-file "not a bookmarks export"
reason plan "Propose folder options"
  intent "propose clean folder plans"
    style "short paths"
  do "propose two distinct folder plans"
  mode creative
  candidates 2
  sees read
  out list[{id: int, folder: str}]
gate plan-ok hard "Every bookmark once" by gates.plan_ok
  retry 2
  fail -> held "the answer is not good"
gate approve human "Write the new file?"
  sees read plan
  timeout 3d
  fail -> declined
end done "Written"
end bad-file "Not a bookmarks export"
end held "Held back"
end declined "The person said no"
```

### Blocks

The lines indented under a block are its **body**. Write block options (`fail`, `tolerate`, `retry`) before the body.

| Block | Meaning |
|---|---|
| `for <name> in <path>` | Body runs once for each item of a list in state (`state["<name>"]`). Saved after each item. |
| ↳ `tolerate <n>%` | When more than `n`% of items end with `fail -> continue`, the flow takes the block's `fail`. |
| ↳ `fail -> <end> ["why"]` | Where to go when too many items are left. |
| `until <path>` | Body runs, then repeats until `<path>` is truthy. On retry, resolved loop-local `soft` gate problems are cleared cleanly so multi-fixer repair loops keep an accurate problem list. |
| ↳ `retry <n>` | Required: at most `n` extra rounds (`n` >= 1 or a number rule id). |
| ↳ `fail -> <end> ["why"]` | Where to go when `<path>` is still not truthy. |
| `if <path>` | Body runs only when `<path>` is truthy. A path, never an expression. |
| `else` | Follows an `if` at the same indent. |
| `section "name"` | A heading for its body. No runtime effect; the viewer draws it as a box. |
| `rollback` | Top-level block at the end of a unit. Runs automatically on hard fail, error, or unattended deferral in `next-batch`, and explicitly via `tool.py restore RUN`. Soft failures that remain after retries can end at a named outcome without triggering rollback. |
| `finally` | Top-level block at the end of a unit. Runs after the run ends (after `rollback` if rollback ran), also after an error or timeout. The outcome stays the end that came first. |

**A path** is a word with dots: `sort.new_folders`, `page`, `read.summary`. It is never an expression. A path is **truthy** when its value is not missing, not `null`, not `false`, not `""`, not `[]` and not `{}`. The number `0` is truthy.

```rig
for batch in loose.batches
  tolerate 20%
  fail -> held "too many batches are left unsorted"
  step sort by model
    do "sort the batch"
    sees batch
    out list[str]
  gate sort-ok hard by gates.sort_ok
    retry 2
    fail -> continue "no good answer"
if sort.new_folders
  gate new-ok human "Make these folders?"
    options all | none | all-but N
    by steps.accept
else
  step plain by steps.plain
until draft.done
  retry 3
  fail -> held
  gate style soft by gates.style
  step draft by model
    if style.failed
    do "improve the text; say done when it is good"
    out {done: bool, text: str}
section "Output"
  step report by steps.report
end done
end held
rollback
  step undo by steps.undo
finally
  step summary by steps.summary
```

### Gate kinds

| Kind | Who decides | On fail |
|---|---|---|
| `hard` | code (`by`) | Takes `fail` (and triggers `rollback` if declared). |
| `soft` | code (`by`) | Reported; flow goes on. No `fail` line. Loop-local soft problems clear when resolved in an `until` loop. |
| `model` | the model, from `check`, `sees` and `intent` | Takes `fail`. Marked **guessed**. |
| `human` | the person | Waits for the answer. On no, takes `fail`. The model never answers for the person. |

**Gate levels:** `tested` (Python AST confirms definition and code reference in test file), `code` (bound without test reference), `model`, `human`, `none`. **Coverage** = tested gates ÷ all gates.

**Numbers in text and gates.** A number in `do` or `check` prose gets a warning. `rig.py check` also warns about hardcoded numeric literals in Python gate files (ignoring `-1`, `0`, `1`, default parameter values, `range()`, `round()` precision and subscript indices).

## 3. Removed words

Version 2 refuses words removed in version 0 and version 1 (`next`, `pass`, `when`, `ensure`, `judge`, `min`, `max`, `label`, `external`, `cast`, `probe`, `evidence`, `snippet`, `example`, `uses`, `tool`/`agent` scopes, prefix-less `code <path>`, `brief` under `gate`), as well as S-expression lists `(a b)` and S-expression types (`(list ...)`, `(record ...)`, `(tuple ...)`, `(maybe ...)`, `(one-of ...)`). The error names what to write instead.

## 4. Runs

The **runner** is `rigkit.py` (`kit/`). It reads the compiled catalogue (`"rig": 2`) and walks the flow:

- **Short run ids** (`r1`, `r2`, ...), reserved atomically.
- **Read-only run metadata (`state["_rig"]`):** refreshed before every step, gate, arena tool, `rollback`, and `finally` call with `{"run_id", "unattended", "in_rollback", "in_finally", "rolled_back", "end"}`. `unattended` is `True` during `next-batch` execution and `False` during interactive `run`, `answer`, or `rerun`.
- **Runtime input validation** against compiled `in` schemas.
- **Automatic `intent` injection** into `waiting.intent` for every `reason` block and `model` gate.
- **Read-only arena tools** (`tool.py arena RUN TOOL [JSON]`) run on a deep copy of `state` under a hard `budget`. `waiting.tool_help` gives the docstring of each tool. The run keeps every call (the node, the tool, the arguments and the result, cut at 2000 characters) in `arena_log`, and the report of the run shows it as `arena`.
- **Brief artifacts** saved to `runs/<run>/artifacts/<step>.json` and inspected read-only via `tool.py artifact RUN NAME`.
- **Transactional rollback** runs on hard fail, error, unattended deferral (`next-batch`), or explicit `tool.py restore RUN`.
- **Chunked unattended batches (`next-batch`)** discover items from `queue` (or an input list), serialize execution via `runs/.batch.lock`, trip a consecutive-error/timeout circuit breaker, roll back & defer waiting items, write a Markdown report, and return a compact one-line `summary`.
- **Two-tier worker (`work`)** routes `step ... by model` to the fast worker model and `reason` blocks to the reasoning tier (`--reason-api-url`, `--reason-model`, `--reason-provider`), with stdlib backends for `openai`, `ollama`, and `anthropic`.
- **Evaluation (`eval`)** scores a ground-truth dataset (quality metrics + wall time) against an optional saved baseline.

## 5. Timeouts and errors

- **A model step or reason block** past its timeout gives no result; the following gate fails with `timeout`.
- **A model gate or human gate** past its timeout fails with `when: "timeout"`.
- **A code step** past its timeout or raising an error ends at `error`, runs `rollback` (if declared), then runs `finally`.

## 6. Compiled forms & universal fronts

- **Catalogue (`rig.py compile json`):** `"rig": 2`, holding `unit`, `intent`, `intent_spec`, `queue`, `rules` (including `ui`), `presets`, `start`, `rollback`, `finally`, `body`, `flow`, `blocks`, `coverage`.
- **Agent Skill (`rig.py compile skill [--driver CMD]`):** universal `SKILL.md` for Claude Code, Codex, Cursor, Gemini CLI, Antigravity, or OpenCode. Omits historical rule `note`s; when `--driver` is set and a unit has more than 25 rules, lists only `ui` and `permissions.*` rules plus `<driver> rules`.
- **MCP (Stdio + Streamable HTTP) & OpenAPI 3.1 (`tool.py mcp`, `tool.py serve-http`):** zero-dependency JSON-RPC 2.0 MCP over stdio or `POST /mcp`, OpenAPI 3.1 at `/openapi.json`, REST endpoints at `/api/*`, MCP Elicitation (`elicitation/create`) when advertised by the client, rule-bound UI controls at `/`, visual/diff localhost approval page at `/approve/<run>`, and batch report viewer at `/reports`.
- **Local plugin (`rig.py plugin DIR`):** LM Studio plugin reading `front.json` (exposing per-chat controls from `presets` and `ui_rules`, forwarded as `--preset` and `--set` overrides).
- **Viewer (`rig.py serve FILE`):** browser table and three-lane graph on `127.0.0.1`.

## 7. Projects and three levels

A project folder holds `rig.json` (`"rig": 2`) at level 1 (`checked`), 2 (`flow`), or 3 (`production`):

| Command | Use |
|---|---|
| `rig.py new DIR NAME [--level 1\|2\|3] [--template flow\|host]` | Create a project (default CLI flow or host-adapter + pure-Python engine template). |
| `rig.py build [DIR] [--check]` | Compile catalogue, Agent Skill, `rigkit.py`, and plugin front. |
| `rig.py doctor [DIR] [--no-tests] [--json]` | Check the project for its level, including `never` boundary mapping. |
| `rig.py test [DIR] [--replay RUN]` | Run tests or replay a recorded run. |
| `rig.py plugin DIR [--owner NAME]` | Add the LM Studio plugin front. |
| `rig.py mcp-config DIR [--http URL] [--api-url URL] [--model NAME] [--provider P]` | Print stdio or Streamable HTTP MCP config JSON. |

## 8. The rules of the interpreter

1. Never imagine what code returns. A result comes from a run.
2. A `model` gate is decided by the model. Its result is labelled **guessed**, visible in the answer. A `human` gate is decided by a person: stop, ask, and wait. Never answer for the person.
3. Never falsify an intent. Anyone may write or change an intent; a gate decides.
