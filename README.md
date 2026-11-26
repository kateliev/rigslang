# Rig

**Rig** (version 2) is a kit and a method for building **timeless, domain-agnostic instrumental agents**: a model that operates tools to do a defined job. You describe the procedure once in `.rig`, and Rig enforces a strict three-layer split:

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

Every letter of **R–I–G** is a runtime-enforced construct:

- **Reason:** first-class `reason` blocks (`mode careful | creative`, read-only `tools` + `budget`, `candidates N`, typed `out`) stay distinct from lightweight single-shot `step ... by model` fill-ins and enable automatic two-tier model routing (`openai`, `ollama`, `anthropic`).
- **Intent:** structured `intent` (`audience`, `style`, `never` invariants) is injected automatically into every `reason` call and `model` gate, and `rig.py doctor` tracks `never` clauses against `hard`, `model`, and `human` gates.
- **Gate:** code decides `hard` and `soft` gates, the model decides `model` gates (marked **guessed**), and a person decides `human` gates (via CLI, MCP Elicitation, or the built-in `/approve/<run>` localhost page).

## Build a tool

Tell any skill-capable coding agent (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode): *"Build a tool that ..., with the Rig skill."* By hand:

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

[examples/release-tool/](examples/release-tool/) is a complete level 3 tool, small enough to read in ten minutes. Try it:

```bash
cd examples/release-tool
python3 tool.py run '{"folder": "tests/cases/good"}'
```

To serve Streamable HTTP MCP (`/mcp`), OpenAPI 3.1 (`/openapi.json`), rule controls (`/`), and the localhost approval UI (`/approve/<run>`):

```bash
python3 tool.py serve-http --port 8780
```

To see its flow as a graph:

```bash
python3 ../../skills/rig/rig.py serve release.rig --json gen/release.json
```

## What is in the repository

| Path | What it is |
|---|---|
| [skills/rig/guide/](skills/rig/guide/) | **The method.** One page of ideas, then the three levels, the build order, production patterns, universal fronts, and rules. |
| [skills/rig/SKILL.md](skills/rig/SKILL.md) | Portable Agent Skill and 1-page [cheatsheet](skills/rig/cheatsheet.md). Copy `skills/rig/` into any coding agent's skills folder. |
| [skills/rig/rig.py](skills/rig/rig.py) | The language tool (stdlib only): `new`, `build`, `doctor`, `test`, `plugin`, `mcp-config`, `check`, `serve`, `compile`. |
| [skills/rig/kit/rigkit.py](skills/rig/kit/rigkit.py) | The runtime (stdlib only): rules, `ui` controls, `reason` arenas, `brief` artifacts, `rollback`/`restore`, `queue` + chunked unattended `next-batch` (lock + circuit breaker), two-tier worker (`openai`, `ollama`, `anthropic`), stdio & Streamable HTTP MCP, OpenAPI 3.1, approval UI, `eval`, and adapter helpers (`step`, `rpc_call`, `http_json`, `WorkerPool`). |
| [skills/rig/kit/templates/](skills/rig/kit/templates/) | Project templates (`flow`, `flow2`, `flow3`, `host`, `plugin`). |
| [skills/rig/spec.md](skills/rig/spec.md) | The Rig v2 language specification. |
| [viewer/index.html](viewer/index.html) | Browser viewer: units, rules (`ui` badges), structured `intent`, and three-lane graph (`code`, `model`, `person`). |
| [examples/release-tool/](examples/release-tool/) | Level 3 pattern example with structured `intent`, `never` mappings, `ui` rules, tests, and plugin. |
| [examples/band-facts/](examples/band-facts/) | Level 2 example: Wikipedia band facts with `never` boundary mapping and regression set. |
| [examples/bookmarks/](examples/bookmarks/) | Level 3 real tool: browser bookmarks cleanup with `for` loops and human choice gates. |
| [editors/](editors/) | VS Code and Sublime Text syntax grammars built from one table. |
| [tests/](tests/) | Unit tests for `rig.py`, `rigkit.py`, project commands, templates, and documentation consistency. |
| [docs/](docs/) | [status.md](docs/status.md), [logic.md](docs/logic.md), [plan-v2-proposal.md](docs/plan-v2-proposal.md), and [history/](docs/history/). |

## The source file

```rig
unit release
  intent "publish a release folder only when its notes, its version and its tests are ready, and a person agrees"
    audience "end users upgrading the product"
    never "publish without human approval" -> approve
  in folder path "the release folder"
  code gates gates.py
    test tests/test_gates.py
  code steps steps.py

  rule notes.min_words 50 "Shortest release notes, in words"
    range 10 500
    ui

  step collect "Collect" by steps.collect
  gate notes hard "Notes long enough"
    check "the notes have at least {notes.min_words} words"
    by gates.notes_ok
    fail -> stop "notes too short"
  gate tone model "Notes speak to users"
    check "read the notes as a user would; fail if they use internal words"
    sees collect.notes
    fail -> stop
  gate approve human "May this release be published?"
    sees collect.version collect.notes
    fail -> stop
  end done "Published"
  end stop "Stopped"
```

## Tests

```bash
python3 -m unittest discover -s tests
```

## Status

Language version 2, updated 2026-11-26. [docs/status.md](docs/status.md) says what is verified and what is open.

## License and privacy

- [Apache License 2.0](LICENSE): free to use, change and share, also in commercial work. Keep the copyright notice and [NOTICE](NOTICE).
- [PRIVACY.md](PRIVACY.md): this project collects no personal data.
