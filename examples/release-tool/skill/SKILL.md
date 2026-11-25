---
name: release
description: publish a release folder only when its notes, its version and its tests are ready, and a person agrees
---

# release

publish a release folder only when its notes, its version and its tests are ready, and a person agrees

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

Code walks this flow. You do not walk it yourself: you start a run and answer what waits.
Run every command in the folder of the tool (the folder that holds `rig.json`).

1. Start a run: `python3 tool.py run '<inputs as JSON>'` (inputs: folder=<path>).
2. Read the result. It is one JSON object.
   - `outcome`: the run ended at that end. Report it, with `problems` first. `result` is what the run made (only when a step leads to the end).
   - `waiting`: the run stopped at a node that code cannot do. Read `kind`, `do` and `check`. `sees` holds the facts of the run that you need for this node: use them, and nothing else.
     - `model` (a gate): decide what `check` says. Answer: `python3 tool.py answer <run> '{"pass": true}'` (or false, with `"why"`).
     - `step`: do what `do` says. Answer: `python3 tool.py answer <run> '{"result": ...}'`. When `waiting` has `schema`, the result must have that form.
     - `human`: show the person the question (`name` and `check`) and `sees`, and wait. When `waiting` has `options`, show them: the first is the default. Then give the answer of the person, never your own: `python3 tool.py approve <run> yes` (or `no`), or `python3 tool.py approve <run> <the words of the person>`.
   - `problems` in `waiting`: your last answer at this node failed. Fix these problems in the new answer.
   - `refused`: the call was out of order. It is final: do not repeat it. Read `at` and continue from there.
3. Repeat step 2 until the result has `outcome`. The outcome `error` means that code failed: report the error text. Do not answer for code.

Never decide a hard or soft gate: code decides them. Use only values from a result or from the rules.
`python3 tool.py status <run>` shows a run again; `python3 tool.py rules` shows the rules.

More than one item: `python3 tool.py batch '<a JSON list of inputs>' --report reports/<name>.md`. Code starts a run for each item and gives a summary. Then answer the runs in `left_for_model`, one at a time (`status <run>` shows what each waits for). Give the person the list `waits_for_person` and the path of the report. `python3 tool.py queues` shows what waits, at any time.

## Flow (the map of the run)

The lines run in order. A gate that passes goes on to the next line.

### `collect` Collect (step)

- Do: read NOTES.md, VERSION and tests.json of the folder
- Done by code: `steps.collect`. The runner does this.

### `notes` Notes long enough (hard gate)

- Check: the notes have at least `{notes.min_words}` words
- Rules: `notes.min_words`
- Decided by code: `gates.notes_ok`. The runner does this.
- Fail: go to `stop` (notes too short).

### `version` Version format (hard gate)

- Check: the version matches `{version.pattern}`
- Rules: `version.pattern`
- Decided by code: `gates.version_ok`. The runner does this.
- Fail: go to `stop` (bad version).

### `tests-required` Tests green when they are required (hard gate)

- Check: the last test run passed, or the rule tests.required is off
- Rules: `tests.required`
- Decided by code: `gates.tests_required`. The runner does this.
- Fail: go to `stop` (tests failed and tests are required).

### `tests` Tests green (soft gate)

- Check: the last test run passed; a fail is reported
- Decided by code: `gates.tests_green`. The runner does this.

### `rewrite` Rewrite the notes (step)

- Only when `tone` is not empty and not false. Else go on to the next line.
- Do: rewrite the notes for users: plain words, and the upgrade steps; give the new text as the result
- Sees: `collect.notes`, `rewrite`, `tone`
- The answer has the type `text`.
- You do this step when the run waits here.

### `rewritten` The rewrite is long enough (hard gate)

- Only when `rewrite` is not empty and not false. Else go on to the next line.
- Check: the rewritten notes have at least `{notes.min_words}` words
- Rules: `notes.min_words`
- Decided by code: `gates.notes_ok`. The runner does this.
- Fail: go to `stop` (the rewrite is too short).

### `tone` Notes speak to users (model gate)

- Check: read the notes as a user would; fail if they use internal words or miss the upgrade steps
- Rules: `notes.rounds`
- Sees: `collect.notes`, `rewrite`
- You decide this gate. Label the result as a guess.
- On fail: do `rewrite` again, at most notes.rounds times. Then take the fail line.
- Fail: go to `stop` (the notes do not speak to users).

### `approve` May this release be published? (human gate)

- Check: show the person the version and the notes
- Sees: `collect.version`, `collect.notes`, `rewrite`
- A person decides. Stop and ask the person. Do not decide this gate yourself.
- Fail: go to `stop` (the person said no).

### `allowed` The tool may publish (hard gate)

- Check: the rule permissions.publish is on
- Rules: `permissions.publish`
- Decided by code: `gates.may_publish`. The runner does this.
- Fail: go to `ready` (dry run).

### `publish` Publish (step)

- Do: write published.json into the folder
- Done by code: `steps.publish`. The runner does this.

### `done` Published (end)

- Stop here.

### `ready` Ready, not published (end)

- Stop here.

### `stop` Stopped (end)

- Stop here.

## Report

You decide these gates yourself, not code: `tone`. Their results are guesses.
End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:

Guessed: tone

Do not leave this line out. A person must see which results are guesses. Write it for each run in which you decided a gate, also when the run ended early.
