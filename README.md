# RIGS

**RIGS** (version 2) is a language, a kit, and a method for building **rigs** — **timeless, domain-agnostic instrumental agents** where a model operates tools to do a defined job. **RIGS** makes rigs: you describe one rig once in a `.rig` file, and RIGS enforces a strict three-layer split:

```text
  THE CALLER (Fronts — swappable as AI interfaces evolve)
  Agent Skill (SKILL.md) | Stdio & Streamable HTTP MCP | OpenAPI 3.1 | Localhost Approval UI | Local Plugin
                                         │
                                         ▼
  THE IDEA (Core — domain-agnostic, long-lived)
  .rig (intent, rules, queue, steps, reason, gates, ends, rollback, finally) + pure-Python engine & gates + rigkit.py
                                         │
                                         ▼
  THE WORLD (Target Adapters — swappable when apps, APIs, or constraints change)
  Local files | Web APIs | Subprocesses | Host-app JSON-RPC | Databases | Worker pools
```

Every letter of **R–I–G–S** is a runtime-enforced construct:

- **Reason:** first-class `reason` blocks (`mode careful | creative`, read-only `tools` + `budget`, `candidates N`, typed `out`) stay distinct from lightweight single-shot `step ... by model` fill-ins and enable automatic two-tier model routing (`openai`, `ollama`, `anthropic`).
- **Intent:** structured `intent` (`audience`, `style`, `never` invariants) is injected automatically into every `reason` call and `model` gate, and `rig.py doctor` tracks `never` clauses against `hard`, `model`, and `human` gates.
- **Gate:** code decides `hard` and `soft` gates, the model decides `model` gates (marked **guessed**), and a person decides `human` gates (via CLI, MCP Elicitation, or the built-in `/approve/<run>` localhost page).
- **Steps:** deterministic `step ... by <fn>` functions do the work and touch the world through thin adapters, while `step ... by model` handles fast, schema-bound single-shot fill-ins.

## Build a rig

Tell any skill-capable coding agent (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode): *"Build a rig that ..., with the RIGS skill."* By hand:

```bash
python3 skills/rig/rig.py new my-tool my-tool --level 1
```

For a host-application adapter + pure-Python engine project:

```bash
python3 skills/rig/rig.py new my-host-tool my-host-tool --level 3 --template host
```

```bash
python3 skills/rig/rig.py doctor my-tool
```

| Level | Name | For |
|---|---|---|
| 1 | checked | Rules, steps, reason blocks, AST-tested gates in code, and the runner. |
| 2 | flow | Named ends, regression set, compiled Agent Skill, and MCP front. |
| 3 | production | Permissions (`off` by default, read by a `hard` gate), rollback/restore, human gates or batch review, queues, and project memory. |

## See one

[examples/font-names/](examples/font-names/) is a complete level 3 tool and the pattern to copy. It gives the font files of a family short names that fit a delivery standard. Code names the files and decides every gate that code can decide. A `reason` block proposes abbreviations only where the table of code fails, and it tests them with code first. A `model` gate judges whether the names still read well, and a person agrees to the rename. It needs no font: the test cases are empty files with font names. [examples/family-namer/](examples/family-namer/) (level 2) makes such a folder: it names a new family from a story, and its output is the input of font-names. Try font-names:

```bash
cd examples/font-names
python3 tool.py run '{"folder": "tests/cases/display"}' --preset mac
```

To serve Streamable HTTP MCP (`/mcp`), OpenAPI 3.1 (`/openapi.json`), rule controls (`/`), the read-only flow graph (`/viewer?serve=1`), and the localhost approval UI (`/approve/<run>`):

```bash
python3 tool.py serve-http --port 8780
```

To see its flow as a graph:

```bash
python3 ../../skills/rig/rig.py serve font-names.rig --json gen/font-names.json
```

## What is in the repository

| Path | What it is |
|---|---|
| [skills/rig/guide/](skills/rig/guide/) | **The method.** One page of ideas, then the three levels, the build order, production patterns, universal fronts, and rules. |
| [skills/rig/SKILL.md](skills/rig/SKILL.md) | Portable Agent Skill and 1-page [cheatsheet](skills/rig/cheatsheet.md). Copy `skills/rig/` into any coding agent's skills folder. |
| [skills/rig/rig.py](skills/rig/rig.py) | The language tool (stdlib only): `new`, `build`, `doctor`, `test`, `plugin`, `mcp-config`, `check`, `serve`, `compile`. |
| [skills/rig/kit/rigkit.py](skills/rig/kit/rigkit.py) | The runtime (stdlib only): rules, `ui` controls, `reason` arenas, `brief` artifacts, `rollback`/`restore`, `queue` + chunked unattended `next-batch` (lock + circuit breaker), two-tier worker (`openai`, `ollama`, `anthropic`), stdio & Streamable HTTP MCP, OpenAPI 3.1, approval UI, `eval`, and adapter helpers (`step`, `rpc_call`, `http_json`, `WorkerPool`). |
| [skills/rig/kit/templates/](skills/rig/kit/templates/) | Project templates (`flow`, `flow2`, `flow3`, `host`, `plugin`), including external `__NAME__.rig` starters. |
| [skills/rig/resources/](skills/rig/resources/) | Editable stylesheets (`viewer.css`, `http.css`) and viewer client (`viewer.html`, `viewer.js`), copied into `<tool>/resources/` on `new` and `build`. |
| [skills/rig/spec.md](skills/rig/spec.md) | The RIGS v2 language specification. |
| [viewer/index.html](viewer/index.html) | Browser viewer entry point: units, rules (`ui` badges), structured `intent`, and three-lane graph (`code`, `model`, `person`). |
| [examples/font-names/](examples/font-names/) | The pattern example, level 3: short font file names for a delivery standard. Structured `intent` with `never` mappings, `rules` blocks, a tuple rule, presets, a `reason` block with read-only arena tools and `candidates`, a `model` gate, a `human` gate, a permission, an undo log with `rollback`, and a regression set. |
| [examples/family-namer/](examples/family-namer/) | Level 2: a name for a new font family, drawn at random by code from lists of names, chosen by the model with reasons, and chosen by a person; then a folder of placeholder files, which is the input of font-names. A single-shot `step ... by model`, a `reason` block in `mode creative` with `candidates 3`, a seed rule, and a `human` gate with `options` and a `by` function. |
| [editors/](editors/) | VS Code and Sublime Text syntax grammars built from one table. |
| [tests/](tests/) | Unit tests for `rig.py`, `rigkit.py`, project commands, templates, and documentation consistency. |
| [docs/](docs/) | [status.md](docs/status.md), [logic.md](docs/logic.md), [plan-v2-proposal.md](docs/plan-v2-proposal.md), and [history/](docs/history/). |

## The source file

```rig
unit font-names
  intent "give every font file of a family a short file name that fits a delivery standard, stays readable and stays unique"
    never "rename a file without the approval of a person" -> approve
    never "rename a file when permissions.rename is off" -> allowed
    never "give two files the same name" -> unique
  in folder path "the folder of exported font files (.otf, .ttf, .woff, .woff2), named Family-Style"
  code gates gates.py
    test tests/test_gates.py
  code steps steps.py
    test tests/test_steps.py

  rules target
    standard sp_server "Delivery standard"
      options none | sp_online | sp_server | win_path | fs255 | joliet | hfs | iso2 | dos83 | mac533
      ui select
  rules shorten
    abbr_letters (2, 4) 1..6 "Shortest and longest abbreviation that the model may propose, in letters"
  rules arena
    tries 6 1..20 "Most test calls in the abbreviation arena"
  rule permissions.rename off "The tool may rename files"
    ui toggle
  preset mac
    set target.standard hfs

  step plan "Shorten with the table" by steps.plan
  if plan.weak_words
    reason abbreviate "Propose abbreviations"
      do "propose a table of abbreviations for each weak word; test each table with try_names before you answer"
      candidates 2
      tools steps.try_names steps.table
      budget arena.tries
      sees plan.weak_words plan.rows
      out dict[str, str]
    gate abbr-ok hard "Abbreviations are fair" by gates.abbr_ok
      check "each abbreviation starts with the first letter of its word, keeps the order of its letters and has {shorten.abbr_letters} letters"
      retry 1
      fail -> held "no fair abbreviation"
  step final "Final names" by steps.final
  gate fits hard "Every name fits the standard" by gates.fits
    check "every new name fits {target.standard}: its length, its characters and the reserved names"
    fail -> held "a name does not fit"
  gate unique hard "No two files share a name" by gates.unique
    fail -> held "two files would get the same name"
  gate readable model "The names read well"
    if final.abbreviations
    check "pass when the family and the style can still be recognised in each name"
    sees final.table final.abbreviations
    fail -> held "the names do not read well"
  gate approve human "Rename these files?"
    sees final.table
    fail -> declined "the person said no"
  gate allowed hard "The tool may rename" by gates.may_rename
    reads permissions.rename
    fail -> ready "dry run"
  step rename "Rename" by steps.rename
  end done "Renamed"
  end ready "Dry run: the table is ready, nothing renamed"
  end held "Held back: nothing renamed"
  end declined "The person said no: nothing renamed"
  ; the whole file has more gates (files-ok, something, verify) and ends: examples/font-names/font-names.rig

  rollback
    step undo "Put the names back" by steps.undo
```

## Tests

```bash
python3 -m unittest discover -s tests
```

## Status

Language version 2, updated 2026-11-27. [docs/status.md](docs/status.md) says what is verified and what is open.

## License and privacy

- [Apache License 2.0](LICENSE): free to use, change and share, also in commercial work. Keep the copyright notice and [NOTICE](NOTICE).
- [PRIVACY.md](PRIVACY.md): this project collects no personal data.
