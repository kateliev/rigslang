# Project facts: font-names

What is true about this project. An agent reads this file before it works, on any computer. The memory of an agent is not the same on every computer; this file is.

Keep it short. Newest decision at the bottom of each list, with the date.

## What the tool does

It renames the font files of one folder to short names that fit a delivery standard (`target.standard`). It never changes the content of a file.

## The pipeline

1. `read`: the font files of the folder (`.otf`, `.ttf`, `.woff`, `.woff2`). The name is `Family-Style` (the PostScript name); a variable font has its axes in brackets (`Family[wght]`). The formats of one style share one short name.
2. `plan`: the names with the built-in table (`engine.build_rows`).
3. Only when a name needs dropped vowels, initials or a cut: the model proposes abbreviations (`reason abbreviate`), and `abbr-ok` checks them.
4. `final`, the gates `fits`, `unique` and `something`, the person (`approve`), the permission (`allowed`).
5. `rename`: the undo log `undo/<token>.json` first, then two phases (old -> tmp -> new), so that a swap of two names or a change of case also works. `verify` checks the folder after.
6. `rollback` (on a hard fail or an error, or `tool.py restore RUN`): puts the names back from the log.

## Decisions of the owner

- 2026-11-27: the engine is the naming engine of an existing font tool of the owner, cut down to the file names. The name table (IDs 1, 4, 6) and the embedding bits are not in this example: they need a font library.
- 2026-11-27: "fair" is a rule of code, not of the model: an abbreviation is a word of the family, starts with its first letter, keeps the order of its letters, is shorter than the word and has `shorten.abbr_letters` letters; with the table, no name needs a weak step.
- 2026-11-27: `auto` (`shorten.method`) means the method of the standard: 5:3:3 for `mac533`, else abbreviate, drop vowels, cut.

## Words

| Word | Meaning |
|---|---|
| table | the abbreviations of words, after Adobe Tech Note 5088 (`engine.ABBREVIATIONS`), and the words of a run |
| weak step | a step that makes a name a person cannot read: dropped vowels, initials, cut |
| weak word | a word that the table does not know, in a name that needed a weak step |
| fair | an abbreviation table that passes `engine.score` |

## Facts about the file systems

- Windows reserves the names `CON`, `PRN`, `AUX`, `NUL`, `COM0`-`COM9` and `LPT0`-`LPT9`, also with a suffix: `Aux.otf` cannot be a file there. A case folder with such a name breaks a checkout on Windows; the reserved check is in the unit tests only.
- Windows and macOS compare names without case. `unique` does the same.
