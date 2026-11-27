# Project facts: family-namer

What is true about this project. An agent reads this file before it works, on any computer. The memory of an agent is not the same on every computer; this file is.

Keep it short. Newest decision at the bottom of each list, with the date.

## What the tool does

It names a new font family after a figure or a thing that a story asks for, and it makes a folder of empty placeholder font files in `files.out`. It never invents a name, and it never writes into a folder that exists. The output folder is the input of `examples/font-names`.

## The pipeline

1. `lists`: the lists in `names.lists` (name, what the list holds, how many names).
2. `topic` (the model, one fast call): the list that the story asks for, or `none`. `topic-ok` and `has-list` check the answer.
3. `sample` (code): `names.sample` names at random from the list, without repeats. The seed is `names.seed`; with 0, code makes a new seed and records it in the result.
4. `pick` (the model, `mode creative`, `candidates 3`): three drawn names, best first, with a reason for each. `picks-ok` checks them.
5. `names` (code): a family name for each pick (`family_of`: accents folded, Latin letters and digits, a capital for each word). `names-ok` checks them. The model guesses whether they fit the story (`fits`).
6. `choose` (a person): a number, or a name. `steps.choice` reads the answer; an answer it does not understand makes the gate ask again.
7. `free`, `write`, `written`: a new folder `files.out/<Family>` with one empty file for each style and format, then the check. `report` gives the result.

## The lists

| List | Names | Source | Read |
|---|---|---|---|
| `trojan-heroes` | 65: 33 Achaeans, 32 Trojans and allies (with 3 Amazons) | [List of Trojan War characters](https://en.wikipedia.org/wiki/List_of_Trojan_War_characters) | 2026-11-27 |
| `winds` | 13: the 4 chief winds, the 4 lesser winds of the Tower of the Winds, and 5 more winds that the article names | [Anemoi](https://en.wikipedia.org/wiki/Anemoi) | 2026-11-27 |

- The names are facts from the articles, in the common English (Latin) spelling. The notes are our own short words, not sentences of the articles.
- The Trojan list has heroes who fought: no gods, no seers, no servants. A name that is on both sides (Acamas, Antiphus, Amphimachus) is in the list once.
- Every name becomes a valid family name of at most `family.max_name` characters. The longest is `AjaxTheLesser` (13). `test_the_lists_of_the_tool_are_valid` checks this.

## Decisions of the owner

- 2026-11-27: the model chooses, code draws. A name that is not in the draw is refused (`picks-ok`), so the model cannot invent a name.
- 2026-11-27: the tool cannot check whether a name is the name of a font that exists, or a trademark. The human gate says so to the person.
- 2026-11-27: a step that needs the file system returns what it found (`names` lists the existing folders, `write` lists the folder after it wrote); the gates decide from the state and touch no file.

## Words

| Word | Meaning |
|---|---|
| list | one JSON file in `lists/`: a name, what it holds, its source, and its names with notes |
| draw | the names that code takes at random from a list (`sample`) |
| pick | a drawn name that the model chose, with its reason |
| family name | the name of the new family in files: Latin letters and digits, no spaces (`AjaxTheGreat`) |
| placeholder | an empty file named `Family-Style.otf` |
