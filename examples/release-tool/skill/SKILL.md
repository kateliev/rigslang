---
name: release
description: publish a release folder only when its notes, its version and its tests are ready, and a person agrees
---

# release

publish a release folder only when its notes, its version and its tests are ready, and a person agrees

Audience: end users upgrading the product
Style: plain language with clear upgrade steps
Never: publish without human approval (gate `approve`)
Never: publish when permissions.publish is off (gate `allowed`)

## Rules

Read the value of each rule from `../gen/release.json`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.

| Rule | Meaning |
|---|---|
| `notes.min_words` | Shortest release notes, in words; range 10 to 500. Note: shorter notes did not answer the usual questions |
| `notes.rounds` | Most rewrites of the notes; range 0 to 5. Note: a third rewrite did not pass where two had failed; the person then writes the notes |
| `version.pattern` | Version format |
| `tests.required` | Tests must pass |
| `permissions.publish` | The tool may publish. Note: off: a dry run. The run ends at ready and changes nothing. |

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

More commands: `python3 tool.py batch '<JSON list>' --report reports/<name>.md`, `python3 tool.py next-batch`, `python3 tool.py queues`, `python3 tool.py status <run>`, `python3 tool.py rules`, `python3 tool.py flow`.

## Flow (summary)

The runner walks 2 code steps and 6 code gates automatically (`python3 tool.py flow` shows the full map).

| Node | Kind | Action / check | Sees | Out / options |
|---|---|---|---|---|
| `rewrite` | model step | rewrite the notes for users: plain words, and the upgrade steps; give the new text as the result | `collect.notes`, `rewrite`, `tone` | `text` |
| `tone` | model gate | read the notes as a user would; fail if they use internal words or miss the upgrade steps | `collect.notes`, `rewrite` |  |
| `approve` | human gate | May this release be published? — show the person the version and the notes | `collect.version`, `collect.notes`, `rewrite` |  |

Ends: `done` — Published, `ready` — Ready, not published, `stop` — Stopped.

## Report

You decide these gates yourself, not code: `tone`. Their results are guesses.
End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:

Guessed: tone

Do not leave this line out. A person must see which results are guesses. Write it for each run in which you decided a gate, also when the run ended early.
