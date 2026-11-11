# Rig language specification, version 0

Rig stands for **Reason, Intent, Gate**. The model reasons: it writes code and decides `judge` gates. The human states the intent. Gates prove the result in a real runtime.

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
| `in <name> [type]` | An input. Repeat for each input. |
| `out [type]` | The output. |
| `intent "text"` | What the unit must do, in controlled language. |
| `example <arg>* => <value>` | One input/output pair. |
| `ensure "condition"` | A condition that every result must meet, in plain words. |
| ↳ `check <lang> "expression"` | Optional child of `ensure`: the condition as code. The expression sees the inputs by name and `result`. |

### Context (not hashed)

| Node | Meaning |
|---|---|
| `note "text"` | A remark that must stay with its parent. Use it when the code looks wrong but is right, or when a value must not change. |
| ↳ `evidence <path or url>` | Optional child: a test or report that supports the note. |
| `uses <unit>` | This unit depends on another unit. |
| `rule <id> <value>` | A parameter. The value is a number, `on`/`off`, a word or a string. |
| ↳ `min`, `max`, `options`, `unit`, `label`, `note` | Optional children of `rule`. |

### Cast (verified code)

```
cast <lang> #<matrix-hash> #<body-hash> [proved <YYYY-MM-DD>]
  <raw code>
```

- `lang` is a short language name: `py`, `js`, `ts`, `rust`, `sh`, and so on.
- A unit can have one cast per language.
- The hashes are defined in Section 4. Only a tool writes them, after a real proof.

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
| `reads <rule-id>*` | The rules that this node uses. |
| `ensure "condition"` | (gate) The condition, in plain words. |
| `by <code-ref>` | The code that does the step or decides the gate, for example `checks.notes_ok`. |
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

**Coverage** of a flow = (hard and soft gates that have `by`) ÷ (all gates).

## 3. Status of a unit

| Status | When |
|---|---|
| **proved** | A cast exists and both hashes match. |
| **remelted** | The matrix hash does not match: the spec changed. The unit is a hole again. |
| **stale** | The body hash does not match: someone changed the code by hand. Prove it again, and check that the intent still describes the code. |
| **hole** | A matrix exists, but no cast. |
| **flow** | The unit has steps or gates. Its status is its coverage. |

## 4. Hashes

**Matrix hash.**

1. Take the unit's direct children with the heads `in`, `out`, `intent`, `example` and `ensure`, with all their descendants, in file order.
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
6. A `judge` gate is decided by the model. Its result is labelled **guessed**.
7. The human owns the intent. An intent that the model drafts from existing code is a proposal until the human confirms it.
