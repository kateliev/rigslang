---
name: rig
description: Build and maintain rigs (instrumental agents) with RIGS v2 — domain-agnostic orchestrated flows of Reason, Intent, Gate, and Steps where code does deterministic steps and hard/soft gates, reason blocks handle deliberative or creative cognition, and a person decides human gates. Works across Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode, MCP (stdio & HTTP), OpenAPI 3.1, and local models.
---

# RIGS

RIGS is a language, a kit, and a method for building **rigs** — **instrumental agents** where a model operates tools to do a defined job. Its name is the four parts of a unit: **R**eason (`reason` blocks), **I**ntent (structured `intent` with `audience`, `style`, and `never` invariants), **G**ate (`hard`, `soft`, `model`, `human`), and **S**teps (`step ... by <fn>` in code and single-shot `step ... by model`).

RIGS makes rigs: one `.rig` file is the source of one rig — its rules (inline `rule`, compact `rules <group>` tables, or external `rules "rules.json"` sidecars), queue, steps, reason blocks, gates, ends, rollback, and finally. It enforces a three-layer split: **the Idea** (`.rig`, pure-Python engine & gates, `rigkit.py`), **the World** (thin target adapters), and **the Caller** (Agent Skill, stdio & Streamable HTTP MCP, OpenAPI 3.1, localhost approval UI, local plugin).

`RIG` below means `python3 <this folder>/rig.py` (Python 3, standard library only).

## Read the file of your task

| Task | Read |
|---|---|
| Quick reference: grammar, Python signatures, `rig.json`, CLI | [cheatsheet.md](cheatsheet.md) (one page) |
| Build a new tool or agent | [guide/README.md](guide/README.md) (the method, one page), then [guide/build-order.md](guide/build-order.md) |
| Choose how much a tool needs (levels 1–3) | [guide/levels.md](guide/levels.md) |
| Change a tool: a value, a gate, the flow, the code | [change.md](change.md) |
| Design a step or a gate that a local model does | [guide/weak-model.md](guide/weak-model.md) |
| Connect a tool to coding agents, MCP, HTTP/OpenAPI, or a local model | [guide/fronts.md](guide/fronts.md) |
| Production patterns: rollback, queues, `next-batch`, `brief`, `eval` | [guide/patterns.md](guide/patterns.md) |
| A question about a word of the language | [spec.md](spec.md) |

Always read [guide/rules.md](guide/rules.md): one page, the rules that have no exception.

The pattern to copy is `examples/font-names`. When a text and the example disagree, the example is right: its tests run.

## The commands

| Command | Use |
|---|---|
| `RIG new DIR NAME [--level 1\|2\|3] [--template flow\|host]` | Make a working project at level 1 (`checked`), 2 (`flow`), or 3 (`production`). `--template host` creates a host-adapter + pure-Python engine split. |
| `RIG build DIR [--check]` | Compile the source to the catalogue, universal Agent Skill, `rigkit.py`, and plugin front. |
| `RIG doctor DIR [--json]` | Check the project against its level, including AST gate verification and `never` boundary mapping. |
| `RIG test DIR [--replay RUN]` | Run the tests, or replay recorded answers of one run against current code. |
| `RIG plugin DIR --owner NAME` | Add the LM Studio plugin front. |
| `RIG mcp-config DIR [--http URL] [--api-url URL] [--model NAME] [--provider P]` | Print a ready-to-paste stdio or Streamable HTTP MCP config block. |
| `RIG check FILE` | Validate a `.rig` file and show coverage. |
| `RIG serve FILE --json OUT` | Open the local viewer and graph on 127.0.0.1. |
| `python3 tool.py <cmd>` | Run the tool: `run`, `batch`, `next-batch`, `queues`, `answer`, `arena`, `work`, `approve`, `restore`, `artifact`, `resume`, `status`, `drop`, `list`, `prune`, `rerun`, `replay`, `rules`, `flow`, `regress`, `eval`, `serve-stdio`, `serve-http`, `mcp`. |
| `RIG compile json\|skill FILE` | Compile one unit to JSON catalogue or Agent Skill. |

## How to work

1. **Ask before you build.** [guide/build-order.md](guide/build-order.md), stage 0, has the questions. Say the level that you chose, and why.
2. **Start from a project that works.** `RIG new`, then change one piece at a time, with `RIG doctor` passing after each piece.
3. **The doctor says when a stage is done**, not your feeling. Read every `MISS` line and every `note` line.
4. **Change the source, then build.** Never edit a compiled file.
5. **Show the person the graph** (`RIG serve`) before you call a flow finished.
6. **Report at the end:** the level, the doctor result, the coverage (tested code, model, human), `never` boundary mappings, each `model` gate that could become code, and what you did not check.
