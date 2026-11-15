# Rig

**Rig** is a kit and a method for building **instrumental agents**: a model that operates tools to do a defined job. You describe a tool one time, and Rig gives you the same tool for Claude (a skill), for a local model (an LM Studio plugin) and for a person (a command line and a graph).

The name is the three parts of the work: **R**eason, **I**ntent, **G**ate. The model reasons, and only where judgment is needed. The intent says what the tool must do. Gates decide whether it did: in code where code can decide, by the model where it cannot (marked as a guess), and by a person where the call is theirs.

## The idea in one picture

```
   one source                      one core                         thin fronts
   release.rig              ┌─  gates.py   decisions     ┌─  skill/SKILL.md    Claude
   rules, steps,   build    │   steps.py   the work      │   plugin/           a local model
   gates, ends     ──────►  │   tool.py    the runner  ──┤   tool.py ...       a person
                            └─  gen/*.json catalogue     └─  the graph page    a person
```

- **Rules** hold every number and switch, in one place.
- **Steps** do the work. **Gates** decide. A gate is `hard` or `soft` (code decides), `judge` (the model decides; a guess) or `human` (a person decides; the run waits).
- **A runner walks the flow.** Code does everything it can. The run stops only where it needs the model or a person, and it refuses a call that is out of order. An item that needs no judgment needs no model.
- **The fronts are compiled.** No front has a limit of its own, and no front decides a gate. A change of the source reaches all of them at the next build.

## Build a tool

Tell an agent that has this repository: *"Build a tool that ..., with the Rig skill."* The skill in [skills/rig/](skills/rig/) takes it from your wish to a checked tool. By hand, it goes like this:

```bash
python3 skills/rig/rig.py new my-tool my-tool --level 2
```

```bash
python3 skills/rig/rig.py doctor my-tool
```

The new folder is a small tool that works. You change it into the real one, and `doctor` says what is missing for its level.

| Level | Name | For |
|---|---|---|
| 1 | tools | Simple things: look up, convert, measure. Functions with typed inputs. |
| 2 | checked | A job with limits: rules, and gates in code. |
| 3 | flow | A procedure with stages: named ends, and a regression set that plays the model. |
| 4 | production | Many items, real files, a person who judges: permissions, a human gate, a way back, project memory. |

A simple tool does not pay for what a large one needs, and a tool can go up a level later.

## See one

[examples/release-tool/](examples/release-tool/) is a complete level 4 tool, small enough to read in ten minutes. Try it:

```bash
cd examples/release-tool
```

```bash
python3 tool.py run '{"folder": "tests/cases/good"}'
```

Code walks four nodes, then the run waits for the model at the gate `tone`. Its README goes on from there. To see its flow as a graph:

```bash
python3 ../../skills/rig/rig.py serve release.rig --json gen/release.json
```

## What is in the repository

| Path | What it is |
|---|---|
| [skills/rig/guide/](skills/rig/guide/) | **The method.** One page of ideas, then the levels, the build order, the patterns for production tools, the fronts, and the rules with no exception. |
| [skills/rig/SKILL.md](skills/rig/SKILL.md) | The skill for an AI agent: one entry, and one file for each task. Portable: copy the folder `skills/rig`. |
| [skills/rig/rig.py](skills/rig/rig.py) | The tool, Python standard library only: `new`, `build`, `doctor`, `test`, `plugin` for projects; `check`, `serve`, `compile` for `.rig` files; `prove`, `probe`, `emit` for snippets. |
| [skills/rig/kit/rigkit.py](skills/rig/kit/rigkit.py) | The runtime: rules, verdicts, runs, the command line of a tool. One file; each tool keeps a copy. |
| [skills/rig/kit/templates/](skills/rig/kit/templates/) | What `new` and `plugin` copy. |
| [skills/rig/spec.md](skills/rig/spec.md) | The language of `.rig` files: one page of grammar, a short list of words. |
| [viewer/index.html](viewer/index.html) | The viewer: units as tables, the flow as a node graph, the compiled skill and JSON. Values can be changed. One file, no install. |
| [examples/release-tool/](examples/release-tool/) | The pattern example: a level 4 tool with its tests, its plugin and its notes. |
| [examples/band-facts/](examples/band-facts/) | A second example, level 3: facts about a band from Wikipedia. Code finds and reads; the model writes one paragraph and judges two things. Its README says what the first live runs taught. |
| [examples/bandsearch/](examples/bandsearch/) | An older example, from before the kit: the model walks the flow, and the code is inside the `.rig` files. Kept for the snippet scale. |
| [examples/](examples/) | Single `.rig` files: a snippet, a tool, an agent. |
| [editors/](editors/) | Syntax highlighting for VS Code and Sublime Text, built from one table. |
| [tests/](tests/) | Tests of `rig.py`, the runtime, the project commands and the templates, and a test that the viewer computes the same results as `rig.py`. |
| [docs/](docs/) | [status.md](docs/status.md): the state of the work. [logic.md](docs/logic.md): the ideas of the language. The first memos and the research notes. |

## The source file

A tool is described in one `.rig` file. People read it, the checker checks it, and everything else is compiled from it.

```
unit release agent
  intent "publish a release folder only when its notes, its version and its tests are ready, and a person agrees"
  in folder path "the release folder"
  code gates gates.py
    test tests/test_gates.py

  rule notes.min_words 50
    min 10
    max 500
    label "Shortest release notes"

  gate notes hard "Notes long enough"
    ensure "the notes have at least {notes.min_words} words"
    by gates.notes_ok
    pass -> tone
    fail -> stop "notes too short"
  gate tone judge "Notes speak to users"
    brief "read the notes as a user would; fail if they use internal words"
    pass -> approve
    fail -> stop
  gate approve human "A person agrees"
    brief "show the person the version and the notes; ask: may this release be published?"
    pass -> done
    fail -> stop
  end done "Published"
  end stop "Stopped"
```

- A `{group.name}` in a text names a rule. A number in a text gets a warning.
- `by gates.notes_ok` names a function in `gates.py`. The checker refuses a name with no function, and counts the gate as **tested** only when the test file names it.
- **Coverage** is the share of the gates that checked code decides. The rest are named: this many by the model, this many by a person.

## Snippets: the small end

Rig began as a language for single functions, and that part still works. A unit can hold its code inside the `.rig` file as a **cast**, proved against its examples in a real runtime and pinned by two hashes. If the spec changes, the cast **remelts** and must be proved again.

```bash
python3 skills/rig/rig.py prove examples/slugify.rig
```

It is useful for small pure functions. For a tool, keep the code in normal files and bind it with a `code` line. [docs/logic.md](docs/logic.md) explains the snippet scale; [skills/rig/snippets.md](skills/rig/snippets.md) is the task file for it.

## Tests

```bash
python3 -m unittest discover -s tests
```

The viewer test needs Node.js. The TypeScript runner and the plugin test need Node.js 23.6 or newer.

## Where it comes from

The method was taken from a private production agent, where one procedure runs on a frontier model and on a small local model with the same code, rules and gates. Only the concept and the machinery are here. [skills/rig/guide/README.md](skills/rig/guide/README.md), Section 7, names the findings that shaped it.

## Status

Version 0, in work. The kit, the guide and the example are new (2026-11-15), and the language can still change. [docs/status.md](docs/status.md) says what is done and what is open.

To give the skill to an agent, copy or link `skills/rig/` into the agent's skills folder (for example `.claude/skills/rig/`).

## License and privacy

- [Apache License 2.0](LICENSE): free to use, change and share, also in commercial work. Keep the copyright notice and the [NOTICE](NOTICE) file. The license gives no right to use the name "Rig" for your own product.
- [PRIVACY.md](PRIVACY.md): this project collects no personal data.
