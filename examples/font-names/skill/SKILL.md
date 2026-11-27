---
name: font-names
description: give every font file of a family a short file name that fits a delivery standard, stays readable and stays unique
---

# font-names

give every font file of a family a short file name that fits a delivery standard, stays readable and stays unique

Audience: type designers and font distributors
Style: names a type designer can read: table abbreviations, no dropped vowels, no cut words
Never: rename a file without the approval of a person (gate `approve`)
Never: rename a file when permissions.rename is off (gate `allowed`)
Never: give two files the same name (gate `unique`)

## Rules

Read the value of each rule from `../gen/font-names.json`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.

| Rule | Meaning |
|---|---|
| `target.standard` | Delivery standard; one of: none, sp_online, sp_server, win_path, fs255, joliet, hfs, iso2, dos83, mac533 |
| `target.folder` | Destination folder or URL; its length counts against the path limit |
| `shorten.method` | Shortening method (auto: the method of the standard); one of: auto, abbr, vowels, m533, cut |
| `shorten.consistent` | Shorten every style of the family to the same level |
| `shorten.ask_model` | Ask the model for abbreviations when the table is not enough |
| `shorten.abbr_letters` | Shortest and longest abbreviation that the model may propose, in letters; range 1 to 6 |
| `arena.tries` | Most test calls in the abbreviation arena; range 1 to 20 |
| `files.undo` | Folder of the undo logs, relative to the tool folder |
| `permissions.rename` | The tool may rename files |

## How to run

Code walks this flow. Start a run and answer only what waits. Run every command in the folder that holds `rig.json`.

1. Start: `python3 tool.py run '<inputs as JSON>'` (inputs: folder=<path>).
2. Read the JSON result:
   - `outcome`: the run ended. Report it, with `problems` first (and `result` if present). `error` means code failed.
   - `waiting` (`kind: model`): decide `check` from `sees` (respecting `intent`). Run `python3 tool.py answer <run> '{"pass": true, "why": "..."}'` (or `false`).
   - `waiting` (`kind: step`): do `do` from `sees`. Run `python3 tool.py answer <run> '{"result": ...}'` matching `schema` if present.
   - `waiting` (`kind: reason`): deliberate (`mode`: `careful` or `creative`) respecting `intent`, `never` boundaries, and any `candidates` count; use `python3 tool.py arena <run> <tool>` for read-only tools up to `budget`. Run `python3 tool.py answer <run> '{"result": ...}'`.
   - `waiting` (`kind: human`): show the person `name`, `check`, `sees`, and `say` word for word; wait, then run `python3 tool.py approve <run> yes` (or `no` / their words). Never answer for a person.
   - `waiting.problems`: fix those problems in the new answer. `refused`: final — run `python3 tool.py status <run>`.
3. Repeat step 2 until `outcome`. Never decide a hard or soft gate yourself.

More commands: `python3 tool.py batch '<JSON list>' --report reports/<name>.md`, `python3 tool.py next-batch`, `python3 tool.py queues`, `python3 tool.py status <run>`, `python3 tool.py rules`, `python3 tool.py flow`, `python3 tool.py restore <run>`.

## Flow (summary)

The runner walks 5 code steps and 7 code gates automatically (`python3 tool.py flow` shows the full map).

| Node | Kind | Action / check | Sees | Out / options |
|---|---|---|---|---|
| `abbreviate` | reason (careful) | propose a table of abbreviations, one for each weak word, as type designers write them (Grotesque: Grt): the first letter of the word, then letters of the word in their order, `{shorten.abbr_letters}` letters (shortest, longest). Test each table with try_names before you answer; table shows the built-in words | `plan.weak_words`, `plan.rows` | `dict[str, str]` × 2 |
| `readable` | model gate | read the new names as a type designer would: pass when the family and the style can still be recognised in each name | `final.table`, `final.abbreviations` |  |
| `approve` | human gate | Rename these files? — show the person the table of old and new names | `final.table`, `final.abbreviations` |  |

Ends: `done` — Renamed, `ready` — Dry run: the table is ready, nothing renamed, `same` — Nothing to rename, `held` — Held back: nothing renamed, `declined` — The person said no: nothing renamed, `empty` — No font files.

## Report

You decide these gates yourself, not code: `readable`. Their results are guesses.
End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:

Guessed: readable

Do not leave this line out. A person must see which results are guesses. Write it for each run in which you decided a gate, also when the run ended early.
