# Rig language specification, version 1

Rig stands for **Reason, Intent, Gate**. The model reasons: it does the steps that code cannot do, and decides `model` gates. The intent says what the tool must do. Gates decide: code decides `hard` and `soft` gates, the model decides `model` gates, and a person decides `human` gates.

Rig files use the extension `.rig`. They are UTF-8 text. This page is the one definition of the language.

Two limits hold:

1. **Rig is not a general programming language.** It has no variables, no assignments and no expressions. The language says the order of the work and who decides. Code (the `by` functions) computes everything.
2. **The language stays small.** One word has one meaning. A new word comes in only when it removes nodes from real flows.

## 1. Syntax

```
node     := head arg* [comment] NEWLINE [children]
children := INDENT node+ DEDENT
arg      := word | number | "string" | /regex/ | ( arg* )
comment  := ; text            (outside strings, to the end of the line)
```

- Every line is a **node**: a head word, then arguments.
- Lines indented under a node are its **children**.
- Indent with spaces (2 per level is the convention). A tab in the indentation is an error.
- A **string** is in double quotes. Use `\"` for a quote and `\\` for a backslash.
- A **regex** is between slashes: `/^[a-z]+$/`.
- A **word** is any run of characters without spaces: `slugify`, `->`, `=>`, `release.min_words`, `20%`.
- `( ... )` holds a short inline list: `example (1 2 3) => 6`.
- Blank lines and comments are ignored.
- **On the line of its node.** `by <name>` can stand at the end of a `step` or `gate` line, and `fail -> <end> ["why"]` at the end of a `gate` line. `step read by steps.read` is the same as a `step read` line with a `by steps.read` line under it.

## 2. Words

A file holds one or more `unit` nodes. Every other word goes inside a unit.

### Container

| Node | Meaning |
|---|---|
| `unit <name> [tool\|agent]` | A unit of work. The default scope is `tool`. A `tool` unit is one function that a model can call. An `agent` unit has a flow. |

### What the unit does

| Node | Meaning |
|---|---|
| `in <name> [type] ["text"]` | An input. Repeat for each input. The text says what the input is. |
| `out [type] ["text"]` | The output. The text says what the output is. |
| `intent "text"` | What the unit must do, in controlled language. |
| `example <arg>* => <value>` | One input/output pair. |
| `check "text"` | A condition that every result must meet, in plain words. |

**Types.** A type is a word or a short list:

| Type | Values |
|---|---|
| `str`, `text`, `word`, `path` | a string |
| `int` | a whole number |
| `float` | a number |
| `bool` | `true` or `false` |
| `list`, `dict`, `any` | any list, any record, any value |
| `(list T)` | a list; each item has the type T |
| `(tuple T1 T2 …)` | a list with one item of each type, in this order |
| `(record name1 T1 name2 T2 …)` | a record with these fields |
| `(maybe T)` | a value of type T, or no value. In a `record`, the field can be missing. |
| `(one-of v1 v2 …)` | one of these values |

The checker warns about a type that it does not know.

### Context

| Node | Meaning |
|---|---|
| `note "text"` | A remark that must stay with its parent. Use it when the code looks wrong but is right, or when a value must not change. |
| `uses <unit> [file]` | This unit depends on another unit. Give the file when the other unit is in another `.rig` file; the path is relative to this file. |
| `code <path>` | The function of this unit is in the file at `path` (relative to the `.rig` file). The function has the name of the unit (`-` becomes `_`). |
| `code <prefix> <path>` | The functions of the steps and gates of this unit are in the file at `path`. A `by` line names one as `prefix.function`, for example `by gates.notes_ok`. |
| ↳ `test <path>` | Optional child of `code`: the test file of that code. A function that the test file names is **tested**. |
| `rule <group.name> <value> ["label"]` | A parameter. The id has a group and a name, joined by a dot. The value is a number, `on`/`off`, a word, a string, a `/regex/` or a `( list )`. The string after the value is the label that a person reads; put the unit of the value in it: `rule sort.batch 60 "Bookmarks in one batch"`. |
| ↳ `range <min> <max>` | Optional child of `rule`: the limits of a number. |
| ↳ `options a \| b \| c` | Optional child of `rule`: the values that the rule can have. |
| ↳ `note "text"` | Where the value comes from. |
| `preset <name>` | A named set of rule values, for example a fast mode and a careful mode. |
| ↳ `set <rule-id> <value>` | Child of `preset`: one rule and its value in this preset. The same limits apply. |

```rig
unit sizes tool
  intent "count the words and the characters of a text"
  in text str "the text to measure"
  out (record words int characters int) "the counts"
  example "two words" => (2 9)
  check "the counts are not below zero"
  code tools.py
    test tests/test_tools.py
  rule size.max 1000 "Longest text, in characters"
    range 1 100000
    note "longer texts did not come up in the tests"
  rule size.mode fast "Mode"
    options fast | careful
  preset careful
    set size.mode careful
```

**Rule names in text.** In any string of a unit, `{group.name}` names a rule of the unit. The checker refuses a name that is not a rule. The compilers write the value of the rule in its place (Section 6). Text in braces without a dot, for example `{word}`, is plain text.

### The flow (for `agent` units)

**The order of the lines is the order of the flow.** A step, then the next line. A gate that passes goes on to the next line. A gate that fails goes to an end. The flow never jumps back: the only ways back are the loop blocks (`for`, `until`) and `retry`.

Nodes:

| Node | Meaning |
|---|---|
| `step <id> ["name"]` | Something the tool does. Its value goes to the state of the run, under its id. |
| `gate <id> hard\|soft\|model\|human ["name"]` | A checkpoint. For a `human` gate, the name is the question: `gate approve human "Write the file?"`. |
| `end <id> ["label"]` | An outcome. The run stops here. |

Children of `step` and `gate`:

| Node | Of | Meaning |
|---|---|---|
| `do "text"` | step | What the step does. |
| `by <prefix.function>` | step, gate | The code that does the step or decides the gate. The name must be a function of a `code` line, a unit of this file, or a unit in a `uses` line. More than one `by`: they run in order; for a gate, until one fails. |
| `by model` | step | The model does this step. A step with no `by` is done by the model too, with a warning: say it. |
| `out <type>` | step | The type of what the step gives. For a `by model` step, the compilers use it as the schema of the answer, so the model cannot give the wrong form; the runner refuses another form. |
| `check "text"` | gate | What the gate checks, or what the model or the person must decide, in plain words. |
| `reads <rule-id>*` | step, gate | The rules that this node uses. A rule named as `{group.name}` in the text of the node is read too, so `reads` is needed only for rules that the text does not name. |
| `sees <path>*` | step, gate | What the one who does the node gets from the state of the run: for a `model` gate, a `human` gate, or a step that the model does. A path is a step id, an input, or the item of a `for`, then keys: `sees read.summary write`. Without it, the model judges blind. |
| `options a \| b \| c` | human gate | The answers that the person can give. The first is the default: the answer when the person only accepts. A gate with `options` needs `by`: the code that reads the answer. |
| `retry <n>` | hard gate, model gate | On fail: do the nearest step before the gate again (only gates may stand between them), at most `n` times. Then take the `fail` line. `n` is a whole number, or the id of a number rule. |
| `timeout <time>` | step, model gate, human gate | For example `timeout 5m`, `timeout 3d`: a number and `s`, `m`, `h` or `d`. See Section 5. |
| `if <path>` | step, gate | The node runs only when this path of the state is not empty and not false. Else the flow goes on to the next line. |
| `fail -> <end> ["why"]` | gate | Where to go on fail: an end. Repeat for more than one reason; the code of the gate names the reason (`"when"`). |
| `fail -> continue ["why"]` | gate in a `for` | Leave this item, record it in the report, and go to the next item. |
| `note "text"` | all | A remark. |

```rig
step read "Read the export" by steps.read
  do "read the file"
gate file-ok hard "A bookmarks export"
  check "the file is a bookmarks file with at least one bookmark"
  by gates.file_ok
  fail -> bad-file "not a bookmarks export"
step sort "Sort the bookmarks" by model
  do "put each bookmark into the folder where it fits best"
  sees read
  out (list (record id int folder str))
  timeout 10m
gate sort-ok hard "Every bookmark once" by gates.sort_ok
  retry 2
  fail -> held "the answer is not good"
gate approve human "Write the new file?"
  sees read
  timeout 3d
  fail -> declined
end done "Written"
end bad-file "Not a bookmarks export"
end held "Held back"
end declined "The person said no"
```

### Blocks

The lines indented under a block are its **body**. A block can have **options** too (`fail`, `tolerate`, `retry`): write them before the body.

| Block | Meaning |
|---|---|
| `for <name> in <path>` | The body runs once for each item of a list in the state. The current item is `<name>`: a node can `sees <name>`, and code reads it as `state["<name>"]`. The runner saves the run after each item, so a run that stops goes on from the next item. |
| ↳ `tolerate <n>%` | When more than `n` percent of the items end with `fail -> continue`, the flow takes the `fail` of the `for` after the loop. Without `tolerate`, any number of items may be left. |
| ↳ `fail -> <end> ["why"]` | Where to go when too many items are left. |
| `until <path>` | The body runs, then runs again until the path is true. |
| ↳ `retry <n>` | Needed: the body runs again at most `n` times. Then the flow takes the block's `fail`, or goes on when the block has none. |
| ↳ `fail -> <end> ["why"]` | Where to go when the path is still not true. |
| `if <path>` | The body runs only when this path of the state is not empty and not false. A path, never an expression. |
| `else` | Follows an `if` at the same indent. Its body runs when the `if` did not. |
| `section "name"` | A heading for its body. It has no effect on a run. The viewer draws it as a box. |
| `finally` | The last block of a flow. Its body runs after the run ends: after an end, also after an error or a timeout. Use it to write a report. The outcome of the run stays the end that came first. |

**A path** is a word with dots: `sort.new_folders`, `page`, `read.summary`. It is never an expression. A path is **true** when its value is not missing, not `null`, not `false`, not `""`, not `[]` and not `{}`. The number `0` is true.

```rig
for batch in loose.batches
  tolerate 20%
  fail -> held "too many batches are left unsorted"
  step sort by model
    do "sort the batch"
    sees batch
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
  step draft by model
    do "improve the text; say done when it is good"
section "Output"
  step report by steps.report
end done
end held
finally
  step summary by steps.summary
```

### Gate kinds

| Kind | Who decides | On fail |
|---|---|---|
| `hard` | code (`by`) | The flow takes `fail`. |
| `soft` | code (`by`) | The fail is reported. The flow goes on to the next line. A soft gate has no `fail` line. |
| `model` | the model, from `check` and `sees` | The flow takes `fail`. The result is marked **guessed**. |
| `human` | the person | The flow waits for the answer. On no, the flow takes `fail`. The model never answers for the person. |

A `human` gate has two forms:

| Children | Form | Paths |
|---|---|---|
| no `options` | yes or no | yes: the next line. no: `fail`. The gate needs a `fail` line. |
| `options a \| b \| c` and `by` | a choice | The answer goes to the `by` function in `state[<gate id>]["answer"]`. When `by` fails ("not understood"), the gate asks again. The first option is the default: the answer when the person only accepts. When the gate has a `fail` line, the answer no takes it. |

**The level of a gate** says how much is known about the code that decides it:

| Level | When |
|---|---|
| **tested** | `by` names a function of a `code` line, the function exists in the file, and the `test` file of that line names it. |
| **code** | `by` names a function of a `code` line that no test names, or a unit whose own code is not tested. |
| **model** | a `model` gate: the model decides. |
| **human** | a `human` gate: a person decides. |
| **none** | a `hard` or `soft` gate with no `by`, or with a `by` that names nothing (also: a function that is not in its file). |

A gate with more than one `by` has the lowest level of them. A unit in another file counts only when the tool can read that file; else it counts as code. `rig.py check` and `rig.py serve` read the `code` files and their tests.

**Tested** means only that a test file names the function. Run the tests yourself (`rig.py test`, Section 7).

**Coverage** of a flow = tested gates ÷ all gates. The status also shows the count at each level.

**Numbers in the text.** A number in the `do` or `check` text of a step or gate gets a warning. Make it a rule and write `{group.name}`: then the value has one place.

## 3. Words of version 0

Version 1 refuses these words. The error names the replacement.

| Word | Write instead |
|---|---|
| `next -> <id>` | Nothing: the next line is the next node. |
| `pass -> <id>` | Nothing: a gate that passes goes on to the next line. |
| `when "text"` (child of a gate) | `if <path>`. The reason of a fail line stays: `fail -> held "why"`. |
| `brief "text"`, `ensure "text"` | `check "text"`. |
| `gate … judge` | `gate … model`. |
| `min`, `max` (rule) | `range <min> <max>`. |
| `label "text"` (rule) | The string after the value: `rule sort.batch 60 "Bookmarks in one batch"`. |
| `unit` (child of `rule`) | Put the unit in the label. The word `unit` is only the container. |
| `external` | `by` names a function of a `code` file, or a unit. |
| `cast`, `probe`, `evidence`, the scope `snippet` | The code lives in a file (`code <path>`); its test file proves it. Write evidence in the text of a note. |

The commands `prove`, `probe`, `stamp`, `emit` and `hash` are gone. The older examples and the page about them are in `docs/history/`.

## 4. Runs

The **runner** is `rigkit.py` (folder `kit/`). It reads the catalogue (Section 6) and walks the flow:

- Code does the steps and decides the `hard` and `soft` gates.
- At a `model` gate, a `human` gate, or a step that the model does, the run stops and waits for an answer. The runner refuses an answer for another node, an answer of the model at a `human` gate, and an answer for a node that code does.
- A step whose answer does not have the form of its `out` type waits again, with the problems.
- When a run waits, its result carries the values of the `sees` paths of that node, and the problems that failed after the last answer at that node.
- When a run ends at an end that a step leads to, its result carries `result`: the value of that step.

**The run folder.** Each run has a folder: `runs/<run id>/`.

| File | What it holds |
|---|---|
| `run.json` | The run: where it is, its state, its trace, its problems. |
| `flow.json` | **Pin**: a copy of the compiled flow at the start of the run. `resume` and the answers use this copy. When the source changed since, the result says so, and the run goes on with its copy. |
| `rules.json` | The rule values of the run. |
| `answers.json` | **Record**: each answer of the model and of the person, in order. |
| `marks.json` | The state of the run before each line outside a loop. `rerun` starts there. |

**Commands of the runner** (the `driver` of a project, for example `python3 tool.py`):

| Command | What it does |
|---|---|
| `run JSON [--preset N] [--set id=value]` | Start a run. |
| `answer RUN JSON [--node ID]` | The model answers what the run waits for: `{"result": …}` for a step, `{"pass": true\|false, "why": …}` for a gate. |
| `approve RUN [WORDS]` | The person answers a human gate: `yes` or `no`, or the words of the answer at a gate with options. |
| `status RUN`, `resume RUN`, `queues` | Show a run; walk on after a stop of the process; list what waits for the model and for a person. |
| `rerun RUN --from ID [--set id=value]` | **Rerun**: a new run with the state of the old run before the line ID, and changed rules. |
| `replay RUN` | **Replay**: run the whole flow again with the current code and the answers recorded in RUN, with no model. It prints the differences of the end and the path. `rig.py test DIR --replay RUN` does the same. |
| `batch ITEMS [--report PATH]`, `regress FILE [--baseline]`, `rules`, `flow`, `call TOOL JSON` | Many items; the regression set; the rules; the flow; one tool unit. |

## 5. Timeouts and errors

- **A model step** that passes its timeout gives no result. The gate after it then fails, so `retry` and `fail` handle it like a bad answer. A late answer is refused.
- **A model gate or a human gate** that passes its timeout fails with the reason `timeout`. A `fail -> <end> "timeout"` line can send it to its own end. A human gate with a timeout needs a `fail` line.
- **A code step** that passes its timeout, or code that raises an error, ends the run with the built-in outcome `error`. Then `finally` runs. `rerun --from` starts a new run from a line before it.
- Without `timeout`, a node waits with no limit.

The runner checks a timeout when it reads the run: at `status`, `resume`, `queues` and `answer`. It runs no clock of its own.

## 6. Compiled forms

One unit compiles to the forms that agents read. The `.rig` file stays the one source: change it, then compile again. `rig.py build` compiles a project; `rig.py compile` compiles one unit.

| Form | For | Command |
|---|---|---|
| **Catalogue** (JSON) | the runner: it reads the rule values and walks the flow | `rig.py compile json FILE [UNIT]` |
| **Skill** (Markdown) | an agent that follows instructions, for example a `SKILL.md` | `rig.py compile skill FILE [UNIT]` |
| **Tool** (JSON) | a model that calls tools: name, description and JSON Schema of the inputs | `rig.py compile tool FILE [UNIT]` |

- **Catalogue.** `"rig": 1`. The keys: `unit`, `scope`, `intent`, `notes`, `uses`, `code`, `in`, `out`, `examples`, `checks`, `start`, `finally`, `body`, `coverage`, `presets`, `rules`, `flow` and `blocks`. Each rule has `id`, `group`, `label`, `type` (`number`, `switch`, `choice`, `text`, `pattern` or `list`), `value` and `default`, and when they exist `min`, `max`, `options` and `note`. Each node of `flow` has `id`, `kind` (`step`, `hard`, `soft`, `model`, `human` or `end`), `lane` (`code`, `model`, `person` or `end`: who decides), and when they exist `name`, `do`, `check`, `by`, `reads`, `sees`, `out` and `schema`, `options`, `retry` and `back` (the step that `retry` does again), `timeout` (seconds) and `timeout_text`, `if`, `fail` (a list of `{"to", "when", "continue"}`), `next` and `block` (the block that holds it). Each block has `id` (`for:<item>`, `until:<path>`, `if:<path>`, `else:<path>`, `section:<name>`, `finally`), `kind`, `body` (the ids of its lines), `first`, `next`, and its own fields (`item`, `path`, `tolerate`, `retry`, `fail`, `else`, `name`). Every edge is written out, so the runner and the viewer do not read the order of the lines again. `rig.py from-json` turns a catalogue back into Rig with the same meaning.
- **Skill.** The rules as a table, then the lines of the flow in order, with the blocks: what to do, what to check, the code to run and obey, and where to go next. A `model` gate tells the agent to label its result as a guess. A `human` gate tells the agent to stop and ask the person.
- **Skill with a runner.** With `--driver CMD`, the skill does not ask the agent to walk the flow. The runner walks it in code. The agent starts a run with `CMD run`, and answers only the nodes that code cannot do, with `CMD answer`. Use this form whenever the unit has a runner: a gate that lives only in the text of a skill is a suggestion, and a gate in a runner is a fact.
- **Report.** When a flow has gates that the agent decides itself (`model` gates, and `hard` or `soft` gates with no `by`), the skill ends with a Report section. It tells the agent to end its answer with one line, `Guessed:` and the ids of those gates that it decided.
- **Tool.** `name` is the unit name. `description` is the intent, with the rule values written in. `parameters` is a JSON Schema object: one property for each `in`, with the text as its description. An input whose type is `(maybe T)` is not required. `returns` is the JSON Schema of the `out` type.
- **The plugin front.** For each `by model` step with an `out` type, the front of a local model gets one tool, `finish_<step>`, whose `result` has the schema of that type.
- **Values.** By default, the compilers write each value in place of `{group.name}`. With `--rules PATH`, the skill refers to the catalogue at PATH instead. With `--preset NAME`, the values of that preset are used.
- **Serve.** `rig.py serve FILE` shows the file in the viewer. The viewer has no parser: `rig.py` compiles the file and gives the viewer the result (`/bundle`). The viewer draws the blocks as boxes, and each node in the band of who decides it: code, the model or the person. A changed rule value is compiled again (`/compile`); Save writes the `.rig` file. With the runs of the tool (`--runs DIR`; default: the folder `runs` next to FILE), the graph shows the path of one run.

## 7. Projects: a unit with its code, its runner and its fronts

A **project** is a folder with one `rig.json` file. It names the `.rig` source, the level of the tool, and the files that are compiled from the source. The guide (`guide/`, next to this file) explains the levels and the build order.

| Command | What it does |
|---|---|
| `rig.py new DIR NAME [--level N]` | Make a project folder from the templates: the `.rig` source, the code files, the tests, the runner, and the folders for notes and reports. |
| `rig.py build [DIR]` | Compile the source to every front that `rig.json` lists: the catalogue, the skill, the tool definitions, the plugin front. `--check`: write nothing, and fail if a compiled file is not current. |
| `rig.py doctor [DIR]` | Check the project against the list of its level. It prints what is missing. |
| `rig.py test [DIR] [--replay RUN]` | Run the tests of the project (the `tests` command of `rig.json`), or replay one recorded run. |

## 8. The rules of the interpreter

1. Never imagine what code returns. A result comes from a run.
2. A `model` gate is decided by the model. Its result is labelled **guessed**, and the label must be visible in the answer (Section 6, Report). A `human` gate is decided by a person: stop, ask, and wait. Never answer for the person.
3. Never falsify an intent. When you describe existing code, the intent states what the code does, and real runs prove it. Anyone may write or change an intent; a gate decides.
