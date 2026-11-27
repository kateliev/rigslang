# Editor support

Syntax highlighting for Rig v2 `.rig` files in VS Code and Sublime Text.

Both grammars are built from one table in [build.py](build.py). Do not edit the generated grammar files directly. Change `build.py`, then run:

```bash
python3 editors/build.py
```

## What is highlighted

- **Head words by group:**
  - Unit signature and intent: `unit`, `in`, `out`, `intent`, `audience`, `style`, `never`, `check`.
  - Context and rules: `code` (prefix + file path), `test`, `queue`, `rule`, `rules` (`rules <group>` compact tables and `rules "<path>.json"` sidecars), `preset`, `set`, `ui` (`toggle`, `select`, `slider`, `number`, `input`), `note`, `options`, `range`.
  - Flow nodes: `step`, `reason`, `gate` (`hard`, `soft`, `model`, `human`), `end`.
  - Blocks: `for ... in ...`, `until`, `if`, `else`, `section`, `rollback`, `finally`.
  - Node modifiers and wiring: `by` (`by model` and `by <prefix.fn>`, standalone or inline), `tools` (`<prefix.fn>*`), `mode` (`careful`, `creative`), `do`, `fail` (`-> <end>` and `-> continue`), `retry`, `budget`, `candidates` (numbers or dotted rule ids), `timeout`, `tolerate`, `reads` (including `<group>.*` wildcards), `sees`, `brief`.
- **Types and data literals:** built-in types (`str`, `text`, `word`, `path`, `int`, `float`, `bool`, `list`, `dict`, `tuple`, `any`, `Literal`), optional `?`, union/choice `|`, `[list]`, `(tuple)`, `{key: value}` dicts and `{field: T, opt?: T}` records (with field/member keys highlighted).
- **Values and bounds:** strings with escapes and `{group.name}` / `{group.name.key}` rule placeholders, `/regex/`, inline bounds (`1..1000`, `0.._`, `_..100`) and open `_` bounds, times (`5m`, `3d`), percents (`20%`), booleans/nulls (`on`, `off`, `true`, `false`, `none`, `null`), `;` comments, and `; >>> level N` template directives.

Words removed from earlier versions (`next`, `pass`, `judge`, `cast`, `ensure`, `snippet`, …) stay unhighlighted.

## VS Code

Copy `editors/vscode` into your extensions folder, then reload VS Code:

| System | Extensions folder |
|---|---|
| Windows | `%USERPROFILE%\.vscode\extensions\rig-language` |
| macOS, Linux | `~/.vscode/extensions/rig-language` |

The extension sets 2-space indentation, bracket pairs (`()`, `[]`, `{}`), `;` line comments (`Ctrl+/`), and indentation folding for `.rig` files.

## Sublime Text 4

1. Select **Preferences > Browse Packages…**.
2. Copy `editors/sublime` into that folder and name it `Rig`.

The package sets 2-space indentation, `;` line comments (`Ctrl+/`), block indentation rules, and word separators that keep dotted and hyphenated Rig names (`notes.min_words`, `long-enough`) as one word.

## Tests

[sublime/syntax_test_rig.rig](sublime/syntax_test_rig.rig) is a column-level scope test in Sublime Text's syntax test format:

- **Python unit tests (zero extra packages):** `python3 -m unittest discover -s tests` checks that the generated grammars are current, every head word matches [spec.md](../skills/rig/spec.md), and every scope assertion in `syntax_test_rig.rig` passes.
- **Sublime Text:** open `syntax_test_rig.rig` and select **Tools > Build** (with the package named `Rig`).
- **VS Code TextMate engine (optional):**
  ```bash
  cd editors
  npm install --no-save vscode-textmate vscode-oniguruma
  node test-vscode.js
  ```
