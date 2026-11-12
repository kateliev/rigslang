# Rig

**Rig** is a small language for writing down *what* code must do and *how that is checked*. It works at three scales with one syntax: agents, tools and code snippets.

The name comes from the three parts of the work: **R**eason, **I**ntent, **G**ate. The model reasons: it writes the code and makes the judgment calls. The human or the model states the intent. Gates prove the result in a real runtime.

An LLM is the main writer of Rig files. A person is the main reader. A real runtime, not the model, decides whether code is correct.

```
unit slugify snippet
  intent "lowercase, ASCII only, words joined by hyphens"
  in text str
  out str
  example "Hello World" => "hello-world"
  example "Ça va?" => "ca-va"
  example "  many   spaces  " => "many-spaces"
  ensure "the result has only a-z, 0-9 and -"
    check py "re.fullmatch(r'[a-z0-9-]*', result)"
  ensure "the result does not start or end with -"
    check py "not result.startswith('-') and not result.endswith('-')"
  cast py #1a80d208 #9fe3f5f5 proved 2026-11-11
    import re, unicodedata

    def slugify(text):
        t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "-", t).strip("-")
```

- **intent / in / out / example / ensure** make the *matrix*: the spec of the unit.
- **cast** is code that was proved against the matrix in a real runtime. Two hashes pin it: the first to the matrix, the second to the code.
- If you change the matrix, the hash does not match any more. The cast *remelts*, and the unit becomes a *hole* again.
- In an agent, **gate** nodes are checkpoints. A `hard` or `soft` gate is decided by code; a `judge` gate is decided by the model and is marked as a guess. The answer of the agent names its guesses in a `Guessed:` line.
- **Coverage** counts only gates whose code is proved. A `by` line names a unit or an `external` (code that Rig does not prove).
- A **probe** runs code live, against the network or a service. Its result is **observed**, not proved.
- An agent's numbers and switches are **rules**, named as `{group.name}` in its text. A **preset** is a named set of values.

## Agents: one source, compiled sheets

An agent unit compiles to the forms that agents read:

```bash
python skills/rig/rig.py compile json examples/release-check.rig -o release-check.json
python skills/rig/rig.py compile skill examples/release-check.rig --rules release-check.json -o SKILL.md
```

- The **JSON catalogue** is for a code runner: it reads the rule values and walks the flow.
- The **skill** is for an agent that follows instructions. With `--rules`, it reads the values from the JSON file, so each value has one place.
- The **tool definition** (`compile tool`) is for a model that calls tools: the name, the intent as description, and the JSON Schema of the inputs.
- `emit` writes the proved and observed casts as modules, for a program to import. [examples/bandsearch/](examples/bandsearch/) builds an LM Studio plugin this way.
- Change the `.rig` file, then compile again. `rig.py serve FILE --json OUT --skill OUT` shows the file in the viewer, and Save compiles it again.

## What is in the repository

| Path | What it is |
|---|---|
| [skills/rig/](skills/rig/) | The skill for an AI agent: convert code into Rig and Rig into code. Portable: copy the folder. |
| [skills/rig/spec.md](skills/rig/spec.md) | The language specification (one page of grammar, a short list of words). |
| [skills/rig/rig.py](skills/rig/rig.py) | Reference tool, Python standard library only: `check`, `hash`, `prove` and `probe` (in Python and Node.js), `stamp`, `emit`, `compile` (catalogue, skill, tool definition), `from-json`, `serve`. |
| [viewer/index.html](viewer/index.html) | Viewer for `.rig` files: units as tables, the flow as a node graph, and the compiled skill and JSON. Rule values can be edited. One file, no install. |
| [editors/](editors/) | Syntax highlighting for VS Code and Sublime Text, built from one table. |
| [examples/](examples/) | Example units: a snippet, a tool and an agent. |
| [examples/bandsearch/](examples/bandsearch/) | A larger example: an LM Studio plugin built from Rig units, with TypeScript casts proved in Node. |
| [tests/](tests/) | Tests for `rig.py`, and a test that the viewer computes the same hashes, errors, catalogues and skills. |
| [docs/logic.md](docs/logic.md) | How the language works, and why. |
| [docs/](docs/) | Research notes and the first design memos. |

## Quick start

```bash
python skills/rig/rig.py check examples/slugify.rig
python skills/rig/rig.py prove examples/slugify.rig
```

Open `viewer/index.html` in a browser, then drop a `.rig` file on the page. To load the examples with one click, serve the folder first:

```bash
python -m http.server 8000 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8000/viewer/?src=../examples/release-check.rig`. To edit one file in place, use `python skills/rig/rig.py serve FILE` instead.

Run the tests (the viewer parity test needs Node.js):

```bash
python -m unittest discover tests
```

To give the skill to an agent, copy `skills/rig/` into the agent's skills folder (for example `.claude/skills/rig/`).

## Status

Early design, version 0. The syntax can still change. Read [docs/logic.md](docs/logic.md) first.

## License and privacy

- [Apache License 2.0](LICENSE): free to use, change and share, also in commercial work. Keep the copyright notice and the [NOTICE](NOTICE) file. The license gives no right to use the name "Rig" for your own product.
- [PRIVACY.md](PRIVACY.md): this project collects no personal data.
