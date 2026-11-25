---
name: band-facts
description: for a band name, write one paragraph about the band and list its albums, with the facts of its English Wikipedia article only
---

# band-facts

for a band name, write one paragraph about the band and list its albums, with the facts of its English Wikipedia article only

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

Code walks this flow. You do not walk it yourself: you start a run and answer what waits.
Run every command in the folder of the tool (the folder that holds `rig.json`).

1. Start a run: `python3 tool.py run '<inputs as JSON>'` (inputs: band=<str>).
2. Read the result. It is one JSON object.
   - `outcome`: the run ended at that end. Report it, with `problems` first. `result` is what the run made (only when a step leads to the end).
   - `waiting`: the run stopped at a node that code cannot do. Read `kind`, `do` and `check`. `sees` holds the facts of the run that you need for this node: use them, and nothing else.
     - `model` (a gate): decide what `check` says. Answer: `python3 tool.py answer <run> '{"pass": true}'` (or false, with `"why"`).
     - `step`: do what `do` says. Answer: `python3 tool.py answer <run> '{"result": ...}'`. When `waiting` has `schema`, the result must have that form.
     - `human`: show the person the question (`name` and `check`), `sees`, and the text of `say` as it is (it names the answers; the first option is the default). Then wait. Give the answer of the person, never your own: `python3 tool.py approve <run> yes` (or `no`), or `python3 tool.py approve <run> <the words of the person>`.
   - `problems` in `waiting`: your last answer at this node failed. Fix these problems in the new answer.
   - `refused`: the call was out of order. It is final: do not repeat it. Read `at` and continue from there.
3. Repeat step 2 until the result has `outcome`. The outcome `error` means that code failed: report the error text. Do not answer for code.

Never decide a hard or soft gate: code decides them. Use only values from a result or from the rules.
`python3 tool.py status <run>` shows a run again; `python3 tool.py rules` shows the rules.

More than one item: `python3 tool.py batch '<a JSON list of inputs>' --report reports/<name>.md`. Code starts a run for each item and gives a summary. Then answer the runs in `left_for_model`, one at a time (`status <run>` shows what each waits for). Give the person the list `waits_for_person` and the path of the report. `python3 tool.py queues` shows what waits, at any time.

## Flow (the map of the run)

The lines run in order. A gate that passes goes on to the next line.

### `find` Find the article (step)

- Do: search English Wikipedia for the band name; take the result with the name of the band, else the first result
- Rules: `http.timeout`, `search.results`
- Done by code: `steps.find`. The runner does this.

### `article` Article found (hard gate)

- Check: the search answered, and it found an article in at most `{search.results}` results
- Rules: `search.results`
- Decided by code: `gates.article_found`. The runner does this.
- Fail: go to `none` (the search found no article).
- Fail: go to `offline` (the search did not answer).

### `read` Read the article (step)

- Do: read the summary and the Discography section of the article; if the page only lists the meanings of the name, read the article name (band)
- Rules: `http.timeout`
- Done by code: `steps.read`. The runner does this.

### `summary` Summary received (hard gate)

- Check: the article has a summary
- Decided by code: `gates.summary_ok`. The runner does this.
- Fail: go to `none` (the article has no summary).

### `title` The article has the name of the band (hard gate)

- Check: the title of the article is the name of the band, with or without a word in brackets
- Decided by code: `gates.title_matches`. The runner does this.
- Note: a run with a real model: a search for a name that is no band gave the article of a politician; the model gate saw it, and now code sees it first
- Fail: go to `none` (the article has another name).

### `is-band` The article is about the band (model gate)

- Check: pass if the description and the summary are about a music group with this name; fail if they are about a person, a place, a film or another thing
- Sees: `band`, `read.title`, `read.description`, `read.summary`
- You decide this gate. Label the result as a guess.
- Note: candidate for code: the description of the article often has the word band
- Fail: go to `none` (the article is not about the band).

### `albums` Albums found (soft gate)

- Check: the Discography section lists at least one album; a fail is reported
- Decided by code: `gates.albums_found`. The runner does this.

### `write` Write the paragraph (step)

- Do: write one paragraph about the band, of at most `{answer.max_words}` words, with facts of the summary only; if you see problems, fix them; give the paragraph as the result
- Rules: `answer.max_words`
- Sees: `read.summary`, `write`
- The answer has the type `text`.
- You do this step when the run waits here.

### `short` Short enough (hard gate)

- Check: the paragraph has at most `{answer.max_words}` words, and it is not empty
- Rules: `answer.max_words`, `answer.rounds`
- Decided by code: `gates.short_enough`. The runner does this.
- On fail: do `write` again, at most answer.rounds times. Then take the fail line.
- Fail: go to `unfinished` (the paragraph is too long or empty).

### `grounded` Only facts of the article (model gate)

- Check: compare the paragraph with the summary; fail if the paragraph states a fact that the summary does not have, and name that fact in why
- Rules: `answer.rounds`
- Sees: `write`, `read.summary`
- You decide this gate. Label the result as a guess.
- On fail: do `write` again, at most answer.rounds times. Then take the fail line.
- Fail: go to `unfinished` (the paragraph has a fact that is not in the summary).

### `compose` Compose the answer (step)

- Do: join the paragraph, at most `{albums.max}` albums as title (year), and the URL of the article
- Rules: `albums.max`
- Done by code: `steps.compose`. The runner does this.

### `done` Answered (end)

- Stop here.

### `none` No article (end)

- Stop here.

### `offline` The service did not answer (end)

- Stop here.

### `unfinished` No good paragraph (end)

- Stop here.

## Report

You decide these gates yourself, not code: `is-band`, `grounded`. Their results are guesses.
End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:

Guessed: is-band, grounded

Do not leave this line out. A person must see which results are guesses. Write it for each run in which you decided a gate, also when the run ended early.
