# Handout: Rig language version 1

For the agent that does this work. Read all of it before you change code. Read `AGENTS.md` and `docs/status.md` too.

Status: **approved by the owner, except the items marked (to confirm)**. Ask the owner about those before you start.

## 1. The goal

Version 0 of the flow has only `step`, `gate` and `end`, joined by jumps. Loops, retries and questions to the person are made of extra nodes. The bookmarks example has 35 nodes; about 12 of them are this plumbing.

Version 1 adds a small set of blocks. The order of the lines is the order of the flow. The flow never jumps back.

Two limits stay:

1. **Rig is not a general programming language.** It has no variables, no assignments and no expressions. The language says the order of the work and who decides. Code (`by` functions) computes everything.
2. **The language stays small.** One word has one meaning. A new word comes in only when it removes nodes from real flows. Version 1 has about as many words as version 0 (see Section 9), but it can say more.

## 2. Gates: the kind says who decides

| Kind | Who decides | On fail |
|---|---|---|
| `gate <id> hard` | code (`by`) | The flow takes `fail`. |
| `gate <id> soft` | code (`by`) | The fail is reported. The flow goes on to the next line. |
| `gate <id> model` | the model, from `check` and `sees` | The flow takes `fail`. The result is marked **guessed**. Was `judge`. |
| `gate <id> human` | the person | The flow takes `fail`. The flow waits. The model never answers for the person. |

A `gate human` has two forms:

| Children | Form | Paths |
|---|---|---|
| no `options` | yes or no | yes: the next line. no: `fail ->`. |
| `options a \| b \| c` and `by` | a choice | The answer goes to the `by` function. When `by` does not understand the answer, the gate asks again. The **first option is the default**: the answer when the person only accepts. |

The gate names its question in its name string: `gate approve human "Write the file?"`.

## 3. Words removed

The parser must refuse each of these words, and the error must name the replacement.

| Word | Replacement |
|---|---|
| `next -> <id>` | The next line. |
| `pass -> <id>` | The next line. A gate that passes always goes on. |
| `when "text"` (gate) | `if <path>`. |
| `brief "text"` | `check "text"`. |
| `ensure "text"` | `check "text"` (on a gate and on a unit). |
| `gate … judge` | `gate … model`. |
| `min`, `max` (rule) | `range <min> <max>`. |
| `label "text"` (rule) | The string after the value: `rule sort.batch 60 "Bookmarks in one batch"`, the same as `step <id> "name"`. |
| `unit` (child of `rule`) | Put the unit in the label. The word `unit` keeps one meaning: the container. |
| `external` | `by` names only a function of a `code` file, or a unit (open item 2 of `docs/status.md`). |
| `cast`, `probe`, `check` (child of probe), hashes, `prove`, `stamp`, `emit`, the scope `snippet` | Nothing. The kit does not use them (open item 1). Move `examples/older/` and its tests to `docs/history/`, or delete them. |

`fail -> <id> ["when"]` stays. A gate can still have more than one `fail` line, one for each reason that its code gives.

## 4. Words added

### 4.1 Blocks

The lines indented under a block are its **body**. A block can also have **options** (`fail`, `tolerate`, `retry`). The parser tells them apart by the head word. Write options before the body.

| Block | Meaning |
|---|---|
| `for <name> in <path>` | The body runs once for each item of a list in the state. The current item is `<name>`; a node can `sees <name>`. The runner saves the progress after each item, so a run that stops goes on from the next item. |
| `until <path>` | The body runs, then runs again, until the path is true. The option `retry <n>` limits it: the body runs again at most `n` times. Then the flow takes the block's `fail ->`, or goes on when the block has none. `until` without `retry` is an error. This is the only loop without a list: "until the model says done". |
| `if <path>` | The body runs only when this part of the state is not empty and not false. A path, never an expression. Can also be a child of one node, to guard only that node. |
| `else` | Follows an `if`. Its body runs when the `if` did not. Used only with `if`. |
| `section "name"` | A heading for its body. It has no effect on a run. The viewer can fold it. (to confirm) |
| `finally` | The last block of a flow. Its body always runs, after any `end`, also after a timeout or an error. Use it to write the report. |

### 4.2 Children

| Child | Of | Meaning |
|---|---|---|
| `by model` | `step` | The model does this step. The coverage and the viewer show it. |
| `out <type>` | `step` | The type of what the step gives. The word is the same as the unit's `out`. For a `by model` step, the compilers use this type as the schema of the tool call where the model gives its answer, so the model cannot give the wrong form. |
| `check "text"` | `gate`, `unit` | What the gate checks, or what the model or the person must decide, in plain words. On a unit: a condition on every result. |
| `options a \| b \| c` | `gate human` | The answers that the person can give. The first is the default. The same word as the child of `rule`. |
| `retry <n>` | `gate`, `until` | Do the work again, at most `n` times. On a gate: on fail, do the step before the gate again, then take `fail`. On `until`: run the body again while the path is not true. |
| `timeout <time>` | `step`, `gate human`, `gate model` | For example `timeout 5m`, `timeout 3d`. See Section 5. |
| `fail -> continue` | a `gate` inside `for` | Leave this item, record it in the report, go to the next item. |
| `tolerate <n>%` | `for` | When more than `n` percent of the items end with `continue`, the flow takes the `for`'s `fail ->` after the loop. Without `tolerate`, any number of items may be left. |
| `range <min> <max>` | `rule` | The limits of the value. |

## 5. Timeouts

- **A model step** that passes its timeout gives no result. The gate after it then fails, so `retry` and `fail` handle it like a bad answer.
- **A human gate** that passes its timeout fails with the reason `timeout`. A `fail -> <id> "timeout"` line can send it to its own end.
- **A code step** that passes its timeout, or raises an error, ends the run with the built-in outcome `error`. Then `finally` runs.
- Without `timeout`, a node waits with no limit, as in version 0.

## 6. Changes to the runner (no new words)

| Change | What it does |
|---|---|
| **Pin each run** | At the start of a run, the runner saves a copy of the compiled flow and the rule values in the run folder. `resume` uses that copy. When the source has changed since, `resume` says so and goes on with the copy. |
| **Rerun from a node** | A command `rerun <run> --from <node> [--set rule=value]`. It makes a new run with the state of the old run up to that node. |
| **Record model answers** | The runner saves each answer of the model in the run folder. |
| **Replay in tests** | `rig.py test --replay <run>` runs the whole flow with the recorded model answers, with no model. This is a flow test, next to the function tests. |
| **Progress in loops** | `for` saves after each item (Section 4.1). `until` saves after each round. |

## 7. Changes to the viewer

| Change | What it does |
|---|---|
| **Blocks as boxes** | `for`, `until`, `if`/`else`, `section` and `finally` are drawn as boxes around their nodes, not as nodes. |
| **Lanes** | Three horizontal bands: code, model, person. Each node is in the band of its decider. |
| **One parser** | First do open item 3: the viewer draws the compiled catalogue, so there is one parser. Without this, every change in this handout must be made twice. |

## 8. Example: the bookmarks flow in version 1

```
step read
gate file-ok hard
  check "a bookmarks export in the Netscape HTML form"
  fail -> bad-file
section "Duplicates and similar URLs"
  step dupes
  step group
  for page in group.pages
    gate choose human "Which URLs to keep?"
      options keep-shortest | keep-all | pick N
      by steps.apply
      sees page
section "Sorting"
  step loose
  for batch in loose.batches
    tolerate 20%
    fail -> held
    step sort by model
      out (record moves (list (record id int folder str)) new (list str))
      timeout 5m
    gate sort-ok hard
      retry 2
      fail -> continue
  gate new-ok human "Make these folders?"
    if sort.new_folders
    options all | none | all-but N
    by steps.accept
section "Output"
  step report
  gate share hard              fail -> held
  gate approve human "Write the file?"
    timeout 7d
    fail -> declined
  step build
  gate verify hard             fail -> held
  gate target hard             fail -> exists
  step place
end done
end bad-file
end held
end declined
end exists
finally
  step summary
```

17 steps and gates, plus 5 ends. Version 0 has 30 plus 5.

## 9. The size of the language

| | Version 0 | Version 1 |
|---|---|---|
| Words (heads and children) | 33 | 33 |
| Gate kinds | 4 | 4 |
| Unit scopes | 3 | 2 |
| Nodes in the bookmarks flow | 35 | 22 |
| Words with two meanings | 1 (`unit`) | 0 |

Version 1 words: `unit intent in out example check note uses code test rule range options preset set step gate end do by reads sees fail retry timeout tolerate for until if else section finally continue`.

The `in` of `for <name> in <path>` is part of the line, as `->` is. It is not the head word `in` (an input of a unit).

To cut further later, the candidates are `reads` (the kit could record which rules a function reads during the tests) and `section`.

## 10. Not in this version

- A delay between retries. Add it with the first network step (the link checker).
- Parallel branches. No example needs them yet.
- A block editor in the viewer. The text stays the source.

## 11. The order of the work

Commit after each stage. All tests pass before each commit. Do not push.

1. **One parser** (open item 3). The viewer reads the compiled catalogue. `tests/parity.js` goes or changes.
2. **Remove** the words of Section 3. Move `examples/older/` and the tests of the snippet scale.
3. **Renames**: `judge` → `model`, `brief`/`ensure` → `check`, `min`/`max` → `range`, the rule label as a string.
4. **Order of lines and `for`**, with `fail -> continue`, `tolerate` and saved progress.
5. **`gate human` with `options`** and asking again.
6. **`retry`, `if`/`else`, `timeout`, `finally`, `until`.**
7. **`by model` with `out`**, and the schema in the plugin front.
8. **The runner**: pin, rerun, record, replay (Section 6).
9. **The viewer**: boxes and lanes.
10. **Examples**: rewrite `release-tool`, `band-facts` and `bookmarks`. Each passes its doctor and its tests.
11. **Text**: `skills/rig/spec.md` (version 1), `docs/logic.md` (open item 4), the guide pages, `skills/rig/SKILL.md`, the editor grammars (`editors/build.py`), and `docs/status.md`.

`AGENTS.md` rule 4 asks for the spec, `rig.py`, the viewer, the grammars, the skill and the examples in one commit. For this change, keep each stage in step across these files, and say so in each commit message.

## 12. Done when

- The parser accepts every example of `skills/rig/spec.md` and refuses every word of Section 3, with the replacement in the error.
- Every new word has a test in `tests/`, and the runner has a test for pin, rerun, record and replay.
- The three examples are in version 1 and pass their doctor. The bookmarks flow has at most 22 nodes.
- `rig.py new` makes projects in version 1 at every level, and each passes its doctor.
- The viewer draws the blocks as boxes and the nodes in lanes. Check it in a browser.
- `docs/status.md` says what is verified and what is not. Mark what no real model has run yet: the `out` schema in LM Studio, `options` at the plugin front, timeouts on a real run.

## 13. Rules

- No names or data of the owner's other projects in this repository (`AGENTS.md` rule 1). The examples stay neutral.
- Never write a test result, a level or a stamp that did not come from a real run (`AGENTS.md` rule 2).
- When this handout and the code disagree in a way that the handout does not settle, ask the owner. Do not guess.
