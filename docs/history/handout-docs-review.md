# Handout: make the texts true to the project

For the agent that does this work. Read all of it before you change a file. Read `AGENTS.md` and `docs/status.md` too.

## 1. The goal

The code changed fast on 2026-11-25: language version 1, the run folders, `rerun` and `replay`, the `say` line of a human gate, the worker of the plugin (`work_run`), the candidate folders of the bookmarks tool. Some texts did not follow. A reader (a person, or an agent that builds a new tool from the guide) now meets statements that are no longer true.

Find every statement in the texts that the code or a real run does not support, and make it true. **The code is the reality. The text follows the code.**

This is a review of texts, not of code. Do not change what a tool does.

## 2. What to check

| Group | Files |
|---|---|
| The skill | `skills/rig/SKILL.md`, `skills/rig/change.md` |
| The guide | every page of `skills/rig/guide/` (`README.md`, `build-order.md`, `levels.md`, `patterns.md`, `fronts.md`, `rules.md`, `weak-model.md`) |
| The language | `skills/rig/spec.md` |
| The project docs | `README.md`, `docs/logic.md`, `docs/status.md`, `AGENTS.md`, `PRIVACY.md`, `editors/README.md` |
| The templates | every text file under `skills/rig/kit/templates/` (READMEs, docstrings of `tool.py`, `steps.py`, `gates.py`, the comments at the top of the plugin files) |
| The examples | `README.md`, `plugin/README.md`, the docstring of `tool.py`, `reports/README.md` of `examples/release-tool`, `examples/band-facts`, `examples/bookmarks` |
| Docstrings that act as docs | the module docstrings of `skills/rig/rig.py`, `skills/rig/rig_project.py`, `skills/rig/kit/rigkit.py`, and the comments at the top of `viewer/index.html` |

**Do not check, and do not change:**

- `.claude/worktrees/` (an old copy of the repository) and every `node_modules/` folder.
- `docs/history/` and `docs/handout-*.md`: they are records of their time.
- The dated entries of `notes/project-facts.md`, `notes/failures-log.md` and `bugs-and-fixes.md` of the examples: they say what was true on that day. You may add a short dated line that says a fact changed. Do not rewrite the old line.
- The compiled files (`gen/`, `skill/SKILL.md` of an example, `plugin/src/gen/`, the copies of `rigkit.py` and of the plugin sources in the examples). Build them; never edit them.

## 3. Where the truth is

Read these before you judge a text. When a text and one of these disagree, the text is wrong, unless the code looks wrong too (Section 6).

| Topic | The source of truth |
|---|---|
| The words of the language, the gate kinds, the errors and their replacements | `rig.py`: `CHILDREN`, `NODE_KIDS`, `BLOCKS`, `GATE_KINDS`, `REMOVED`, `check()` |
| The catalogue and its keys | `rig.py`: `catalog()`, `node_info()`, `block_info()`; a real file in `examples/*/gen/` |
| The commands of `rig.py` | its module docstring and `main()`; `rig_project.main()` |
| The commands of a tool, and the keys of a result (`waiting`, `say`, `left`, `note`, …) | `rigkit.py`: `Kit.cli` (its docstring), `waiting()`, `report()` |
| The run folder | `rigkit.py`: `run()`, `put()`, `walk()`; a real run folder under `examples/*/runs/` |
| What the doctor checks at each level | `rig_project.doctor()`: the text of each `add(...)` line |
| What `rig.py new` makes | `rig_project.rig_source()` and `skills/rig/kit/templates/`; make a project of each level in your scratch folder and look |
| The plugin: its tools, its rules text, the worker, the `approve` messages | `rig_project.front()`; `templates/plugin/src/bridge.ts`, `tools.ts`, `worker.ts`, `index.ts`; a compiled `plugin/src/gen/front.json` |
| The rules of an example, their values and their notes | its `.rig` file |
| What was verified with a real model | `docs/status.md` and the dated notes of the examples; never your own idea of what probably works |

## 4. How to check

Go through the files of Section 2, one at a time. For each **statement that can be checked**, find its source in Section 3 and compare. A statement can be checked when it names:

- a command, a flag, or an argument;
- a word of the language, a key of JSON, a file, a folder, or a function;
- a number: a count of tests, nodes, gates, rules, cases, batches; a value of a rule; a time;
- a behaviour: "a fail goes to …", "the run waits at …", "the model gets …";
- the result of a run, or what was or was not verified.

**Run it when you can.** Many statements can be checked with a real run. Run only commands that need no network and no model, and that write only into ignored folders (`runs/`, `work/`, `out/`, `tests/.tmp/`) or into your scratch folder. Examples:

```bash
python3 -m unittest discover -s tests
```

```bash
python3 skills/rig/rig.py doctor examples/release-tool
```

```bash
python3 skills/rig/rig.py new <scratch>/demo demo-tool --level 4
```

```bash
cd examples/release-tool && python3 tool.py run '{"folder": "tests/cases/good"}'
```

**Mechanical checks first.** They find most of the drift in minutes. Do them with a short script in your scratch folder, not by eye:

1. **Links.** Every relative link in a Markdown file of Section 2 points to a file or folder that exists.
2. **Removed words.** No text of Section 2 uses a word of `rig.REMOVED`, the gate kind `judge`, the scope `snippet`, or the commands `prove`, `probe`, `stamp`, `emit`, `hash`, except where it says that the word is gone. Careful: `check`, `pass` and `judge` are also plain English words. Look at each hit.
3. **Paths in code blocks.** Each file or folder that a code block names exists, for example `src/worker.ts` or `tests/regression-set.json`.
4. **Numbers.** Each count in a text matches a count that you take from the code or from a run on the same day.

**Known drift.** These were seen and are probably still wrong. Check each one, and fix it when the code confirms it:

- **`finish_<step>` tools.** The plugin no longer has them. The worker took their place: the tool `work_run`, `src/worker.ts`, `work.ts`, and the setting `"plugin": {"work": {...}}` in `rig.json`. Look in `spec.md` (Section 6, "The plugin front"), `guide/fronts.md`, `docs/status.md`, the READMEs and the plugin READMEs.
- **`approve` messages without the run id.** `say` now gives `approve <run> <words>`, and a message without the run id is refused when more than one run waits. Look at the tables of answers in `guide/fronts.md`, `examples/bookmarks/README.md` and the plugin READMEs. Say clearly when the short form works (exactly one run waits) and when it does not.
- **The bookmarks tool.**
  - The model writes a short topic and picks a number from the choices (`{"id", "topic", "pick"}`); it does not get the folder list.
  - `sort.batch` is 30, `sort.choices` is 5, `similar.page_size` is 8.
  - The flow has 22 nodes.
  - Check every number and every example answer in its README against `bookmarks.rig`, `bm.py` and `gen/bookmarks.json`.
- **`guide/weak-model.md`** is new. Check that `guide/README.md`, `SKILL.md` and `build-order.md` link to it where a reader needs it, and that the other pages do not say the opposite (for example a page that gives the model a long list to search).
- **Counts in `docs/status.md`** (tests, nodes, cases). Take them from a run on the day you write them.
- **The docstrings of the `tool.py` files.** Each must list the commands that `Kit.cli` has now.
- **`levels.md`.** Its doctor lines must match the `add(...)` lines of `rig_project.doctor()`, level by level.

## 5. How to fix

- Change the smallest part of the text that makes it true. Keep the plan and the voice of the page.
- Write in the style of `AGENTS.md` rule 7: short sentences, one word for one meaning, the condition before the instruction. Use the words of the language as the spec uses them: a **gate** is not a "check", a **step** is not a "task", an **end** is not a "result".
- One fact has one place. When two pages say the same thing, keep the full text on one page and link to it from the other.
- A text that names a thing that is gone says what replaced it. It does not keep the old name "for the record": that is what `docs/history/` is for.
- Never write a number, a result or a "verified" that you did not get from the code or from a real run today (`AGENTS.md` rule 2). When you cannot verify a statement, mark it in your report as not verified. Do not guess.
- No names or data of the owner's other projects (`AGENTS.md` rule 1).
- After a change to a template, build the examples (`python3 skills/rig/rig.py build examples/<name>`) so that their copies stay current.

## 6. When the code may be wrong

Sometimes the text is right and the code is wrong: a guide rule that the code breaks, a doctor line that checks less than `levels.md` says, a refusal text that sends the reader to the wrong place. **Do not change the code in this work.** Write the case in your report (file, line, what the text says, what the code does), and ask the owner. Change the text only when the owner says that the code is right.

## 7. A guard against new drift

Add tests to `tests/` that keep the mechanical checks true from now on. Make each check its own test, so that a fail names the problem:

1. Every relative link in the Markdown files of Section 2 resolves.
2. No text of Section 2 uses a word of `rig.REMOVED` as a word of the language. Exclude `docs/history/` and the handouts; allow a sentence that says the word is gone.
3. The commands in the docstring of the `tool.py` of each example and template are the commands of `Kit.cli`.

All tests must pass before a commit (`AGENTS.md` rule 6).

## 8. Report and commit

Write a short report in `docs/review-docs-2026-11.md`:

- A table of every change: the file, what it said, what it says now, the source in the code.
- The statements that you could not verify, and why.
- The cases of Section 6, with the question for the owner.

Commit when all tests pass, with a message that names the groups of files you changed. Do not push.

## 9. Done when

- Each file of Section 2 was read, and each statement that can be checked was checked.
- The mechanical checks of Section 4 find nothing, and the tests of Section 7 pass.
- The known drift of Section 4 is fixed, or the report says why not.
- `docs/status.md` is true: what exists, what is not verified, what is open.
- The report is written, and the owner has the questions of Section 6.
