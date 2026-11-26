---
name: band-facts
description: for a band name, write one paragraph about the band and list its albums, with the facts of its English Wikipedia article only
---

# band-facts

for a band name, write one paragraph about the band and list its albums, with the facts of its English Wikipedia article only

Never: state facts outside the Wikipedia summary (gate `grounded`)

## Rules

Read the value of each rule from `../gen/band-facts.json`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.

| Rule | Meaning |
|---|---|
| `answer.max_words` | Longest paragraph, in words; range 40 to 300. Note: an earlier form of this tool had the limit only in the text of a step; the model wrote 142 words for a limit of 120 |
| `answer.rounds` | Most rewrites of the paragraph, for each gate that checks it; range 0 to 5. Note: the regression set has a case that needs one rewrite; no case needed more than two |
| `albums.max` | Most albums in the list; range 1 to 100. Note: longer lists were mostly singles and live albums |
| `search.results` | Search results to look at; range 1 to 20. Note: a live run for a famous band gave a list page as the first result; the step now prefers the title that is the name (README.md) |
| `http.timeout` | Time to wait for each request, in seconds; range 1 to 60. Note: the two services answered in under two seconds; ten leaves room for a slow day |

## How to run

Code walks this flow. Start a run and answer only what waits. Run every command in the folder that holds `rig.json`.

1. Start: `python3 tool.py run '<inputs as JSON>'` (inputs: band=<str>).
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

The runner walks 3 code steps and 5 code gates automatically (`python3 tool.py flow` shows the full map).

| Node | Kind | Action / check | Sees | Out / options |
|---|---|---|---|---|
| `is-band` | model gate | pass if the description and the summary are about a music group with this name; fail if they are about a person, a place, a film or another thing | `band`, `read.title`, `read.description`, `read.summary` |  |
| `write` | model step | write one paragraph about the band, of at most `{answer.max_words}` words, with facts of the summary only; if you see problems, fix them; give the paragraph as the result | `read.summary`, `write` | `text` |
| `grounded` | model gate | compare the paragraph with the summary; fail if the paragraph states a fact that the summary does not have, and name that fact in why | `write`, `read.summary` |  |

Ends: `done` — Answered, `none` — No article, `offline` — The service did not answer, `unfinished` — No good paragraph.

## Report

You decide these gates yourself, not code: `is-band`, `grounded`. Their results are guesses.
End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:

Guessed: is-band, grounded

Do not leave this line out. A person must see which results are guesses. Write it for each run in which you decided a gate, also when the run ended early.
