# Rig

**Rig** is a small language for writing down *why* code exists, *what* it must do, and *how that is checked*. It works at three scales with one syntax: agents, tools and code snippets.

The name comes from its three main words: **R**eason, **I**ntent, **G**ate.

An LLM is the main writer of Rig files. A person is the main reader. A real runtime, not the model, decides whether code is correct.

```
unit slugify snippet
  reason "URLs must be stable and readable"
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

- **reason / intent / in / out / example / ensure** make the *matrix*: the spec of the unit.
- **cast** is code that was proved against the matrix in a real runtime. Two hashes pin it: the first to the matrix, the second to the code.
- If you change the matrix, the hash does not match any more. The cast *remelts*, and the unit becomes a *hole* again.
- In an agent, **gate** nodes are checkpoints. A `hard` or `soft` gate is decided by code; a `judge` gate is decided by the model and is marked as a guess.

## What is in the repository

| Path | What it is |
|---|---|
| [skills/rig/](skills/rig/) | The skill for an AI agent: convert code into Rig and Rig into code. Portable: copy the folder. |
| [skills/rig/spec.md](skills/rig/spec.md) | The language specification (one page of grammar, a short list of words). |
| [skills/rig/rig.py](skills/rig/rig.py) | Reference tool, Python standard library only: `check`, `hash`, `prove`, `json`. |
| [viewer/index.html](viewer/index.html) | Viewer for `.rig` files: a table tab and a graph tab. One file, no install. |
| [examples/](examples/) | Example units: a snippet, a tool and an agent. |
| [tests/](tests/) | Tests for `rig.py`, and a test that the viewer computes the same hashes and errors. |
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

Then open `http://127.0.0.1:8000/viewer/?src=../examples/release-check.rig`.

Run the tests (the viewer parity test needs Node.js):

```bash
python -m unittest discover tests
```

To give the skill to an agent, copy `skills/rig/` into the agent's skills folder (for example `.claude/skills/rig/`).

## Status

Early design, version 0. The syntax can still change. Read [docs/logic.md](docs/logic.md) first.

## License and privacy

- [PolyForm Noncommercial 1.0.0](LICENSE.md): free for personal use, research, education and non-profit organizations. Commercial use needs a separate license from the author.
- [PRIVACY.md](PRIVACY.md): this project collects no personal data.
