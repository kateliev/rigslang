---
name: family-namer
description: name a new font family after a figure or a thing that the story asks for: a name drawn at random from a list of the tool, chosen with reasons, and valid as a family name
---

# family-namer

name a new font family after a figure or a thing that the story asks for: a name drawn at random from a list of the tool, chosen with reasons, and valid as a family name

Audience: type designers who name a new family
Style: three names, one sentence of reason for each, no invented names
Never: propose a name that is not in a list of the tool (gate `picks-ok`)
Never: write files without the choice of a person (gate `choose`)
Never: write into a folder that exists (gate `free`)

## Rules

Read the value of each rule from `../gen/family-namer.json`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.

| Rule | Meaning |
|---|---|
| `names.lists` | Folder of the name lists, one JSON file for each list |
| `names.sample` | Names that code draws at random from the list; range 3 to 30 |
| `names.seed` | Seed of the draw; 0 makes a new draw for each run; range 0 to … |
| `family.styles` | Styles of the placeholder family |
| `family.formats` | File formats of the placeholders |
| `family.max_name` | Longest family name, in characters; range 3 to 63 |
| `files.out` | Folder for the new families, relative to the tool folder |

## How to run

Code walks this flow. Start a run and answer only what waits. Run every command in the folder that holds `rig.json`.

1. Start: `python3 tool.py run '<inputs as JSON>'` (inputs: story=<text>).
2. Read the JSON result:
   - `outcome`: the run ended. Report it, with `problems` first (and `result` if present). `error` means code failed.
   - `waiting` (`kind: model`): decide `check` from `sees` (respecting `intent`). Run `python3 tool.py answer <run> '{"pass": true, "why": "..."}'` (or `false`).
   - `waiting` (`kind: step`): do `do` from `sees`. Run `python3 tool.py answer <run> '{"result": ...}'` matching `schema` if present.
   - `waiting` (`kind: reason`): deliberate (`mode`: `careful` or `creative`) respecting `intent`, `never` boundaries, and any `candidates` count; use `python3 tool.py arena <run> <tool>` for read-only tools up to `budget`. Run `python3 tool.py answer <run> '{"result": ...}'`.
   - `waiting` (`kind: human`): show the person `name`, `check`, `sees`, and `say` word for word; wait, then run `python3 tool.py approve <run> yes` (or `no` / their words). Never answer for a person.
   - `waiting.problems`: fix those problems in the new answer. `refused`: final — run `python3 tool.py status <run>`.
3. Repeat step 2 until `outcome`. Never decide a hard or soft gate yourself.

More commands: `python3 tool.py batch '<JSON list>' --report reports/<name>.md`, `python3 tool.py next-batch`, `python3 tool.py queues`, `python3 tool.py status <run>`, `python3 tool.py rules`, `python3 tool.py flow`.

## Flow (summary)

The runner walks 5 code steps and 6 code gates automatically (`python3 tool.py flow` shows the full map).

| Node | Kind | Action / check | Sees | Out / options |
|---|---|---|---|---|
| `topic` | model step | read the story and pick the one list whose names the story asks for. Give its name exactly as in lists, or none when no list fits | `story`, `lists` | `{list: str, why: str}` |
| `pick` | reason (creative) | from the drawn names, choose the three that fit the story best, best first. Give each name exactly as drawn, and one sentence why it fits | `story`, `topic`, `sample` | `{name: str, why: str}` × 3 |
| `fits` | model gate | pass when each name fits what the story asks for; fail when a name ignores it | `story`, `pick` |  |
| `choose` | human gate | Which name for the family? — show the person the three names with their reasons. A name can be the name of a font that exists, or a trademark: the tool cannot check that | `names` | `1` / `2` / `3` |

Ends: `done` — Named: run font-names on the new folder, `no-list` — No list fits the story, `held` — Held back: nothing written, `declined` — The person chose none: nothing written.

## Report

You decide these gates yourself, not code: `fits`. Their results are guesses.
End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:

Guessed: fits

Do not leave this line out. A person must see which results are guesses. Write it for each run in which you decided a gate, also when the run ended early.
