# Editor support

Syntax highlighting for `.rig` files in VS Code and Sublime Text.

Both grammars are made from one table in [build.py](build.py). Do not edit the generated files. Change `build.py`, then run:

```bash
python editors/build.py
```

## What is highlighted

- The head word of each line, by group: what the unit does (`in`, `out`, `intent`, `example`, `check`), the context (`note`, `rule`, `range`, `options`, `preset`, `set`, `uses`, `code`, `test`), the nodes (`step`, `gate`, `end`), the blocks (`for`, `until`, `if`, `else`, `section`, `finally`) and the children of the flow (`by`, `do`, `fail`, `retry`, `timeout`, `tolerate`, `reads`, `sees`).
- `by` and `fail` at the end of a `step` or `gate` line.
- Names: units, rules, steps, gates and ends where they are defined; the item and the path of a `for`; the path of `until` and `if`. Rule names after `reads`, and the end after `->`.
- Strings, rule names in strings (`{group.name}`), `/regex/`, numbers, times (`5m`, `3d`), percents (`20%`), `|` between options, `on`/`off` and `;` comments.
- Gate kinds (`hard`, `soft`, `model`, `human`) and unit scopes (`tool`, `agent`).

The words of language version 0 that version 1 refuses (`next`, `pass`, `judge`, `cast`, …) are not highlighted.

## VS Code

Copy the folder `editors/vscode` into your extensions folder, then restart VS Code:

| System | Extensions folder |
|---|---|
| Windows | `%USERPROFILE%\.vscode\extensions\rig-language` |
| macOS, Linux | `~/.vscode/extensions/rig-language` |

The extension also sets 2-space indentation, `;` comments (Ctrl+/) and folding by indentation for `.rig` files.

## Sublime Text 4

1. Select **Preferences > Browse Packages…**.
2. Copy the folder `editors/sublime` into that folder and name it `Rig`.

The package also sets 2-space indentation, `;` comments (Ctrl+/) and word boundaries that keep `notes.min_words` as one word.

## Tests

[sublime/syntax_test_rig.rig](sublime/syntax_test_rig.rig) is a syntax test in the Sublime Text format. To run it in Sublime Text, open the file and select **Tools > Build**. The package folder must be named `Rig`.

The same file also tests the VS Code grammar:

```bash
cd editors
npm install --no-save vscode-textmate vscode-oniguruma
node test-vscode.js
```

 The generated grammar is checked by `python -m unittest discover tests`: the test fails if `build.py` was changed and the grammars were not built again.
