---
name: rig
description: Build and maintain instrumental agents with Rig - tools and agents where code does the steps and decides the gates, and a model or a person answers only what code cannot. Use it to build a new tool or agent from a wish ("build me a tool that...", "make an agent for..."), to add a Claude skill or an LM Studio plugin to a tool, to change the rules, gates or flow of a Rig tool, to check a tool (doctor, regression, replay), or to read or write .rig files. Trigger on ".rig", "Rig", "riglang", "rig.json", "rigkit", "gate", "build a tool like", "instrumental agent", "make a skill and a plugin for", "doctor", "gate coverage", "compile the skill".
---

# Rig

Rig is a kit and a method for building **instrumental agents**: a model that operates tools to do a defined job. Its name is the three parts of the work: **R**eason (the model: judgment, and only where it is needed), **I**ntent (what the tool must do, in plain words), **G**ate (who decides whether it did: code, the model, or a person).

One `.rig` file is the source of a tool: its rules, steps, gates and ends. The order of its lines is the order of the flow; a few blocks (`for`, `until`, `if`, `else`, `section`, `finally`) hold loops and choices. The code lives in normal files. A runner walks the flow: code does the steps and decides the gates, and the run stops only where it needs the model or a person. The Claude skill and the local-model plugin of a tool are compiled from the source, and both call the same code.

`RIG` below means `python3 <this folder>/rig.py` (Python 3, standard library only).

## Read the file of your task

| Task | Read |
|---|---|
| Build a new tool or agent | [guide/README.md](guide/README.md) (the method, one page), then [guide/build-order.md](guide/build-order.md) |
| Choose how much a tool needs | [guide/levels.md](guide/levels.md) |
| Change a tool: a value, a gate, the flow, the code | [change.md](change.md) |
| Design a step or a gate that a local model does | [guide/weak-model.md](guide/weak-model.md) |
| Connect a tool to Claude or to a local model | [guide/fronts.md](guide/fronts.md) |
| A tool that changes real files, works on many items, or needs the eye of a person | [guide/patterns.md](guide/patterns.md) |
| A question about a word of the language | [spec.md](spec.md) |

Always read [guide/rules.md](guide/rules.md): one page, the rules that have no exception.

The pattern to copy is the example tool `examples/release-tool` of the Rig repository. When a text and the example disagree, the example is right: its tests run.

## The commands

| Command | Use |
|---|---|
| `RIG new DIR NAME --level N` | Make a project: a working tool of level 1 to 4, to change into the real one. |
| `RIG build DIR` | Compile the source to the catalogue, the skill, the tool definitions and the plugin front. `--check`: fail if a compiled file is not current. |
| `RIG doctor DIR` | Check the project against the list of its level. Each line is `ok` or `MISS`. |
| `RIG test DIR [--replay RUN]` | Run the tests of the project, or play the recorded answers of one run again with the current code. |
| `RIG plugin DIR --owner NAME` | Add the LM Studio plugin: the front for a local model. |
| `RIG check FILE` | Validate a `.rig` file. Show the status and the coverage of each unit. |
| `RIG serve FILE --json OUT` | Show the file as tables and as a graph on 127.0.0.1. Values can be changed there. |
| `python3 tool.py run '<JSON>'` | In a project: start a run. `batch`, `queues`, `answer`, `approve`, `resume`, `status`, `rerun`, `replay`, `rules`, `flow`, `call`, `regress`: see [guide/fronts.md](guide/fronts.md). |
| `RIG compile json\|skill\|tool FILE`, `RIG from-json FILE` | One unit to one form, and a catalogue back to Rig. `build` uses the same compilers. |

## How to work

1. **Ask before you build.** [guide/build-order.md](guide/build-order.md), stage 0, has the questions. Say the level that you chose, and why.
2. **Start from a project that works.** `RIG new`, then change one piece at a time, with `RIG doctor` passing after each piece.
3. **The doctor says when a stage is done**, not your feeling. Read every `MISS` line and every `note` line.
4. **Change the source, then build.** Never edit a compiled file.
5. **Show the person the graph** (`RIG serve`) before you call a flow finished. The wires are theirs to approve.
6. **Report at the end:** the level, the doctor result, the coverage (how many gates code decides, how many the model, how many a person), each `model` gate that could become code, and what you did not check.
