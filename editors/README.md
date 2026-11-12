# Editor support

Syntax highlighting for `.rig` files in VS Code and Sublime Text.

Both grammars are made from one table in [build.py](build.py). Do not edit the generated files. Change `build.py`, then run:

```bash
python editors/build.py
```

## What is highlighted

- The head word of each line, by group: the matrix (`in`, `out`, `intent`, `example`, `ensure`, `check`), the context (`note`, `evidence`, `rule`, `preset`, `set`, `uses`, `external`, `probe`, …) and the flow (`step`, `gate`, `end`, `next`, `pass`, `fail`, …).
- Names: units, rules, steps, gates and ends where they are defined. Rule names after `reads`, and node names after `->`.
- Strings, rule names in strings (`{group.name}`), `/regex/`, numbers, `on`/`off`, hashes, dates, `?` (an unknown value) and `;` comments.
- **Cast bodies use the highlighting of their language** for `py`, `js`, `ts`, `sh` and `rust`. Other languages show as raw text. A cast body ends at the first line that is not indented more than `cast`.
- Gate kinds (`hard`, `soft`, `judge`) and unit scales (`snippet`, `tool`, `agent`).

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
