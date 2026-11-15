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
| `answer.max_words` | Longest paragraph (words); min 40, max 300. Note: an earlier form of this tool had the limit only in the text of a step; the model wrote 142 words for a limit of 120 |
| `answer.rounds` | Most rewrites of the paragraph; min 0, max 5. Note: the regression set has a case that needs one rewrite; no case needed more than two |
| `albums.max` | Most albums in the list; min 1, max 100. Note: longer lists were mostly singles and live albums |
| `search.results` | Search results to look at; min 1, max 20. Note: a live run for a famous band gave a list page as the first result; the step now prefers the title that is the name |
| `http.timeout` | Time to wait for each request (seconds); min 1, max 60. Note: the two services answered in under two seconds; ten leaves room for a slow day |

## How to run

Code walks this flow. You do not walk it yourself: you start a run and answer what waits.
Run every command in the folder of the tool (the folder that holds `rig.json`).

1. Start a run: `python3 tool.py run '<inputs as JSON>'` (inputs: band=<str>).
2. Read the result. It is one JSON object.
   - `outcome`: the run ended at that end node. Report it, with `problems` first. `result` is what the run made (only when a step leads to the end).
   - `waiting`: the run stopped at a node that code cannot do. Read `kind`, `do` and `brief`. `sees` holds the facts of the run that you need for this node: use them, and nothing else.
     - `judge`: decide as `brief` says. Answer: `python3 tool.py answer <run> '{"pass": true}'` (or false, with `"why"`).
     - `step`: do what `do` says. Answer: `python3 tool.py answer <run> '{"result": ...}'`.
     - `human`: show the person what `brief` says, ask, and wait. Then give the decision of the person, never your own: `python3 tool.py approve <run> yes` (or `no`, with a note).
   - `error`: a step failed. Report the error text. Do not answer the node; after the cause is fixed: `python3 tool.py resume <run>`.
   - `refused`: the call was out of order. It is final: do not repeat it. Read `at` and continue from there.
3. Repeat step 2 until the result has `outcome`.

Never decide a hard or soft gate: code decides them. Use only values from a result or from the rules.
`python3 tool.py status <run>` shows a run again; `python3 tool.py rules` shows the rules.

More than one item: `python3 tool.py batch '<a JSON list of inputs>' --report reports/<name>.md`. Code starts a run for each item and gives a summary. Then answer the runs in `left_for_model`, one at a time (`status <run>` shows what each waits for). Give the person the list `waits_for_person` and the path of the report. `python3 tool.py queues` shows what waits, at any time.

## Flow (the map of the run)

### `find` Find the article (step)

- Do: search English Wikipedia for the band name; take the result with the name of the band, else the first result
- Rules: `http.timeout`, `search.results`
- Done by code: `steps.find`. The runner does this.
- Next: go to `article`.

### `article` Article found (hard gate)

- Check: the search answered, and it found an article in at most `{search.results}` results
- Rules: `search.results`
- Decided by code: `gates.article_found`. The runner does this.
- Pass: go to `read`.
- Fail: go to `none` (the search found no article).
- Fail: go to `offline` (the search did not answer).

### `read` Read the article (step)

- Do: read the summary and the Discography section of the article; if the page only lists the meanings of the name, read the article name (band)
- Rules: `http.timeout`
- Done by code: `steps.read`. The runner does this.
- Next: go to `summary`.

### `summary` Summary received (hard gate)

- Check: the article has a summary
- Decided by code: `gates.summary_ok`. The runner does this.
- Pass: go to `title`.
- Fail: go to `none` (the article has no summary).

### `title` The article has the name of the band (hard gate)

- Check: the title of the article is the name of the band, with or without a word in brackets
- Decided by code: `gates.title_matches`. The runner does this.
- Note: a run with a real model: a search for a name that is no band gave the article of a politician; the judge gate saw it, and now code sees it first
- Pass: go to `is-band`.
- Fail: go to `none` (the article has another name).

### `is-band` The article is about the band (judge gate)

- Sees: `band`, `read.title`, `read.description`, `read.summary`
- Judge: pass if the description and the summary are about a music group with this name; fail if they are about a person, a place, a film or another thing. Label the result as a guess.
- Note: candidate for code: the description of the article often has the word band
- Pass: go to `albums`.
- Fail: go to `none` (the article is not about the band).

### `albums` Albums found (soft gate)

- Check: the Discography section lists at least one album
- Decided by code: `gates.albums_found`. The runner does this.
- Pass: go to `write`.
- Fail: go to `write` (the article lists no albums).

### `write` Write the paragraph (step)

- Do: write one paragraph about the band, of at most `{answer.max_words}` words, with facts of the summary only; if you see problems, fix them; give the paragraph as the result
- Rules: `answer.max_words`
- Sees: `read.summary`, `write`
- You do this step when the run waits here.
- Next: go to `short`.

### `short` Short enough (hard gate)

- Check: the paragraph has at most `{answer.max_words}` words, and it is not empty
- Rules: `answer.max_words`
- Decided by code: `gates.short_enough`. The runner does this.
- Pass: go to `grounded`.
- Fail: go to `rounds` (the paragraph is too long or empty).

### `grounded` Only facts of the article (judge gate)

- Sees: `write`, `read.summary`
- Judge: compare the paragraph with the summary; fail if the paragraph states a fact that the summary does not have, and name that fact in why. Label the result as a guess.
- Pass: go to `compose`.
- Fail: go to `rounds` (the paragraph has a fact that is not in the summary).

### `rounds` A rewrite is left (hard gate)

- Check: the paragraph was written at most `{answer.rounds}` times after the first
- Rules: `answer.rounds`
- Decided by code: `gates.rounds_left`. The runner does this.
- Pass: go to `write`.
- Fail: go to `unfinished` (no rewrite left).

### `compose` Compose the answer (step)

- Do: join the paragraph, at most `{albums.max}` albums as title (year), and the URL of the article
- Rules: `albums.max`
- Done by code: `steps.compose`. The runner does this.
- Next: go to `done`.

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
