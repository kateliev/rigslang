# Rig language specification, version 0

Rig stands for **Reason, Intent, Gate**. The model reasons: it writes code and decides `judge` gates. The human or the model states the intent. Gates prove the result in a real runtime.

Rig files use the extension `.rig`. They are UTF-8 text. This page is the one definition of the language.

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
- A **word** is any run of characters without spaces: `slugify`, `->`, `=>`, `release.min_words`, `#3f0c9e21`.
- `( ... )` holds a short inline list: `example (1 2 3) => 6`.
- Blank lines and comments are ignored.
- **Exception:** the children of a `cast` node are raw text, not nodes. They are kept as written.

## 2. Words

A file holds one or more `unit` nodes. Every other word goes inside a unit.

### Container

| Node | Meaning |
|---|---|
| `unit <name> [snippet\|tool\|agent]` | A unit of work. The default scope is `snippet`. |

### The matrix (the spec of a unit; it is hashed)

| Node | Meaning |
|---|---|
| `in <name> [type] ["text"]` | An input. Repeat for each input. The text says what the input is. |
| `out [type] ["text"]` | The output. The text says what the output is. |
| `intent "text"` | What the unit must do, in controlled language. |
| `example <arg>* => <value>` | One input/output pair. |
| `ensure "condition"` | A condition that every result must meet, in plain words. |
| ↳ `check <lang> "expression"` | Optional child of `ensure`: the condition as code. The expression sees the inputs by name and `result`. |

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

The checker warns about a type that it does not know. A proof checks each result against the `out` type.

### Context (not hashed)

| Node | Meaning |
|---|---|
| `note "text"` | A remark that must stay with its parent. Use it when the code looks wrong but is right, or when a value must not change. |
| ↳ `evidence <path or url>` | Optional child: a test or report that supports the note. |
| `uses <unit> [file]` | This unit depends on another unit. Give the file when the other unit is in another `.rig` file; the path is relative to this file. |
| `external <name> ["text"]` | Code that Rig does not prove: a library function, a service, or code outside the `.rig` files. A `by` line can name it. |
| `probe <arg>*` | A live run: the code runs with these inputs against the real world (the network, files, services). Its result is **observed**, never proved. |
| ↳ `check <lang> "expression"` | Child of `probe`: a condition on this one result. |
| `rule <group.name> <value>` | A parameter. The id has a group and a name, joined by a dot. The value is a number, `on`/`off`, a word, a string, a `/regex/` or a `( list )`. |
| ↳ `min`, `max`, `options`, `unit`, `label`, `note` | Optional children of `rule`. The value must be inside `min` and `max`, and one of `options`. |
| `preset <name>` | A named set of rule values, for example a fast mode and a careful mode. |
| ↳ `set <rule-id> <value>` | Child of `preset`: one rule and its value in this preset. The same limits apply. |

**Rule names in text.** In any string of a unit, `{group.name}` names a rule of the unit. The checker refuses a name that is not a rule. The compilers write the value of the rule in its place (Section 6). Text in braces without a dot, for example `{word}`, is plain text.

### Cast (verified code)

```
cast <lang> #<matrix-hash> #<body-hash> [proved|observed <YYYY-MM-DD>]
  <raw code>
```

- `lang` is a short language name: `py`, `js`, `ts`, `rust`, `sh`, and so on.
- A unit can have one cast per language.
- The hashes are defined in Section 4. Only a tool writes them, after a real run: `proved` after the examples pass, `observed` after the probes pass.
- The cast defines one function, named after the unit (`-` becomes `_`). The function can be `async`.
- **Modules.** A runner and `emit` write each cast as a module named after its unit: `<unit>.ts`, `<unit>.js`, or `<unit_name>.py` (`-` becomes `_`). Next to it they write the catalogue of the unit, `<unit>.json` (Section 6). A cast imports the units that it `uses` and its own catalogue from these files, for example `import { wiki_title } from "./wiki-title.ts"`.

### Flow (for `agent` units, and `tool` units that have stages)

| Node | Meaning |
|---|---|
| `step <id> ["name"]` | Something the agent does. |
| `gate <id> hard\|soft\|judge ["name"]` | A checkpoint. |
| `end <id> ["label"]` | An outcome. The flow stops here. |

Children of `step` and `gate`:

| Node | Meaning |
|---|---|
| `when "text"` | (gate) What triggers the check. |
| `do "text"` | (step) What the step does. |
| `reads <rule-id>*` | The rules that this node uses. A rule named as `{group.name}` in the text of the node is read too, so `reads` is needed only for rules that the text does not name. |
| `ensure "condition"` | (gate) The condition, in plain words. |
| `by <name>` | The code that does the step or decides the gate. The name must be a unit of this file, a unit in a `uses` line, or an `external` of this unit. A unit can name itself: then its own cast decides. The checker warns about any other name. |
| `brief "text"` | (judge gate) What the model must judge, and how. |
| `next -> <id>` | (step) The next node. |
| `pass -> <id>` | (gate) Where to go on pass. |
| `fail -> <id> ["when"]` | (gate) Where to go on fail. Repeat for more than one case. |

The flow starts at the first `step` or `gate` of the unit.

### Gate kinds

| Kind | Who decides | On fail |
|---|---|---|
| `hard` | code (`by`) | the flow follows `fail`; the work does not continue as if it passed |
| `soft` | code (`by`) | the result is reported; `fail` may lead on to the same next node |
| `judge` | the model, using `brief` | the result is labelled **guessed** |

**The level of a gate** says how much is known about the code that decides it:

| Level | When |
|---|---|
| **proved** | `by` names a unit that is proved (Section 3). |
| **observed** | `by` names a unit that is observed. |
| **code** | `by` names an `external`, or a unit that is neither proved nor observed. |
| **judge** | a `judge` gate: the model decides. |
| **none** | a `hard` or `soft` gate with no `by`, or with a `by` that names nothing. |

A gate with more than one `by` has the lowest level of them. A unit is **proved** when its cast is proved, or when it has no stamped cast and all of its gates are proved. It is **observed** in the same way, with observed or proved in place of proved. A unit in another file counts only when the tool can read that file; else it counts as code.

**Coverage** of a flow = (proved gates) ÷ (all gates). The status also shows the count at each level.

**Numbers in the text.** A number in the `when`, `do`, `ensure` or `brief` text of a step or gate gets a warning. Make it a rule and write `{group.name}`: then the value has one place.

## 3. Status of a unit

| Status | When |
|---|---|
| **proved** | A cast is stamped `proved` and both hashes match. |
| **observed** | A cast is stamped `observed` and both hashes match: its probes passed, but no examples prove it. |
| **unproved** | A cast has no hashes yet. |
| **remelted** | The matrix hash does not match: the spec changed. The unit is a hole again. |
| **stale** | The body hash does not match: someone changed the code by hand. Prove it again, and check that the intent still describes the code. |
| **hole** | A matrix exists, but no cast. |
| **flow** | The unit has steps or gates. Its status is its coverage and the count at each level. |

## 3a. Runs: prove, probe, stamp

A **runner** runs a cast in its real runtime. `rig.py` has runners for `py` (Python 3), `js` and `ts` (Node.js; `ts` needs Node.js 23.6 or newer). The runner writes the cast, the casts of the units that it `uses` (in the same language) and their catalogues as modules into an empty folder (Section 2, Modules). Then it calls the function.

- **prove** calls the function with the inputs of each `example`. A result must equal the example value, match the `out` type and pass every `check`. A `check` in the language of the cast runs in that runtime. A `check py` runs in Python on the result as JSON. A cast without examples cannot be proved.
- **probe** calls the function with the inputs of each `probe`. A result must match the `out` type, pass every `check` of the unit's `ensure` lines and every `check` of the probe. Probes need the real world, so a pass is **observed**, not proved.
- **stamp.** `prove --stamp` writes `proved` and the date. `probe --stamp` writes `observed` and the date, but only for a cast that has no examples: a unit with examples must be proved. For a language that has a runner, `rig.py stamp` refuses: use `prove --stamp`. For other languages, `stamp` is the only way, and you must run the tests in that language first.
- **emit** writes the modules of all proved and observed casts in one language into a folder, for a program to import. It refuses a cast that is not stamped, or whose hashes do not match.

## 4. Hashes

**Matrix hash.**

1. Take the unit's direct children with the heads `in`, `out`, `intent`, `example` and `ensure`, with all their descendants, in file order. A `probe` is not part of the matrix: it tests the world, not the spec.
2. Write each node as one canonical line: two spaces for each level below the unit's direct children, then the tokens as written in the source, joined by one space. An inline list is written `(a b c)`. Comments are not included.
3. Join the lines with `\n`. Encode as UTF-8. Take SHA-256. Keep the first 8 hex characters.

**Body hash.** Take the raw lines of the cast. Remove the indentation that all non-blank lines share. Remove spaces at the end of each line. Remove blank lines at the start and the end. Join with `\n`, then SHA-256, first 8 hex characters.

Both hashes are written with a `#` prefix. `rig.py hash` prints them.

## 5. The rules of the interpreter

1. A cast whose status is **proved**: run it. Do not write it again.
2. A **hole**: choose a language, write the code, run every `example` and every `check` **in a real runtime**. Write the cast only if all pass.
3. **Remelted**: go to rule 2. The old cast stays only in version control.
4. **Stale**: prove the code again. If the intent no longer describes it, propose a new intent to the human.
5. Never imagine what code returns. A proof comes from a run.
6. A `judge` gate is decided by the model. Its result is labelled **guessed**, and the label must be visible in the answer (Section 6, Report).
7. Never falsify an intent. When you describe existing code, the intent states what the code does, and real runs prove it. Anyone may write or change an intent; a gate decides.
8. A probe never proves. Its result is **observed**: true on that day, against that world.

## 6. Compiled forms

One unit compiles to the forms that agents read. The `.rig` file stays the one source: change it, then compile again. `rig.py compile` does this, and the viewer shows the same output.

| Form | For | Command |
|---|---|---|
| **Catalogue** (JSON) | a code runner: it reads the rule values and walks the flow | `rig.py compile json FILE [UNIT]` |
| **Skill** (Markdown) | an agent that follows instructions, for example a `SKILL.md` | `rig.py compile skill FILE [UNIT]` |
| **Tool** (JSON) | a model that calls tools: name, description and JSON Schema of the inputs | `rig.py compile tool FILE [UNIT]` |

- **Catalogue.** The keys are the words of Rig: `intent`, `in`, `out`, `uses`, `external`, `notes`, `presets`, `rules` and `flow`. Each input has `name`, `type` and `text`; `out` has `type` and `text`. Each `uses` entry has `unit`, and `file` when it is given. Each external has `name` and `text`. `coverage` has the count of `gates` and the count at each level: `proved`, `observed`, `code`, `judge` and `none`. Each rule has `id`, `group`, `label`, `type` (`number`, `switch`, `choice`, `text`, `pattern` or `list`), `value` and `default`, and when they exist `min`, `max`, `options`, `unit`, `note` and `evidence`. Each flow node has `id`, `kind` (`step`, `hard`, `soft`, `judge` or `end`), `name`, its texts, `by`, `reads`, and `next`, `pass` and `fail` as lists of `{"to", "when"}`. `rig.py from-json` turns a catalogue back into Rig with the same meaning.
- **Skill.** The rules as a table, then each node of the flow in order: what to do, what to check, the code to run and obey, and where to go next. A `judge` gate tells the agent to label its result as a guess.
- **Report.** When a flow has gates that the agent decides itself (`judge` gates, and `hard` or `soft` gates with no `by`), the skill ends with a Report section. It tells the agent to end its answer with one line, `Guessed:` and the ids of those gates that it decided. A person must see which results are guesses.
- **Tool.** `name` is the unit name. `description` is the intent, with the rule values written in. `parameters` is a JSON Schema object: one property for each `in`, with the text as its description. An input whose type is `(maybe T)` is not required. `returns` is the JSON Schema of the `out` type.
- **Values.** By default, the compilers write each value in place of `{group.name}`. With `--rules PATH`, the skill refers to the catalogue at PATH instead, so the values have one place at run time too. With `--preset NAME`, the values of that preset are used.
- **Serve.** `rig.py serve FILE --json OUT --skill OUT` shows the file in the viewer. Save writes the `.rig` file and compiles it again.
