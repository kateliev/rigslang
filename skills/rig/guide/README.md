# The RIGS method

This guide says how to build a **rig** — an **instrumental agent** where a model operates tools to do a defined job. **RIGS** stands for **Reason, Intent, Gate, Steps**; each `.rig` file defines one rig. Read this page first. Then read the page of your task.

| Page | Read it when |
|---|---|
| [../cheatsheet.md](../cheatsheet.md) | You want a 1-page reference of grammar, Python signatures, `rig.json` and commands. |
| [levels.md](levels.md) | You choose how much a tool needs. A simple tool needs little. |
| [build-order.md](build-order.md) | You build a new tool, from the first question to the last check. |
| [patterns.md](patterns.md) | The tool changes real files, works on many items, or needs the judgment of a person. |
| [weak-model.md](weak-model.md) | A local model will run the tool. You design a step or a gate that the model does. |
| [fronts.md](fronts.md) | You connect the tool to Claude, to a local model, to an MCP host, or to all three. |
| [rules.md](rules.md) | Always. One page: the rules that have no exception. |

The pattern example is [examples/font-names](../../../examples/font-names/). When this guide and the example disagree, the example is right, because its tests run.

## 1. The problem

A model that follows a long instruction text does three things wrong:

1. **It reads loosely.** A limit that is only a sentence in a prompt is a suggestion. The model goes over it, and nothing sees that.
2. **It decides what it must not decide.** It reads a number and says "close enough".
3. **It hides its guesses.** The result does not show what code checked and what the model only thought.

More instruction text does not fix this. The fix is to move work out of the text.

## 2. The method: four parts, four owners

| Part | What it is | Who owns it |
|---|---|---|
| **Rules** | Every number, switch and name of the tool. One place (with optional `ui` controls). | The person. A change is a change of one value, with a reason. |
| **Steps & Reason** | Deterministic `step`s (`by steps.fn`), lightweight `step ... by model`, and deliberative `reason` blocks (`mode`, read-only `tools` + `budget`, `candidates`). | Code for deterministic work; two-tier models for fill-in vs. reasoning. |
| **Gates** | The decisions (`hard`, `soft`, `model`, `human`) plus `never` invariants under `intent`. | Code where code can decide. Else the model, marked as a guess. Else a person. |
| **Flow** | The order of the lines, the blocks (`for`, `until`, `if`, `else`, `rollback`, `finally`), `queue`, and where a run can end. | The source file. Code walks it. |

A gate is `hard` or `soft` (code decides), `model` (the model decides; marked as a guess) or `human` (a person decides; the run waits). Full gate rules are in [spec.md](../spec.md).

The model keeps the work it is good at: a judgment that no rule can hold, a step that needs language, a case that the flow did not expect. Everything else is code: also the search, the bookkeeping and the exact texts around that judgment. Design each job of the model for the weakest model that will run it ([weak-model.md](weak-model.md)).

## 3. How a run goes

```
   the front                 the runner                     the code
   (Claude, a plugin,   ──►  walks the flow            ──►  steps.py   does the work
    a person)                of the catalogue               gates.py   decides
        ▲                         │
        │   waiting: a model      │   it stops only where code
        │   gate, a human gate,   │   cannot go on
        └── or a step with ───────┘
            no code
```

1. The front starts a run for one item.
2. The runner walks the flow. It calls the code of each step and each gate.
3. At a node that code cannot do, the runner stops and says what it waits for.
4. The front gives the answer. The runner refuses an answer for another node, and it refuses the model at a human gate.
5. The run ends at an end node. The result has the end, the problems, the gates that were guessed, and the path.

So the code drives, and the model handles the exceptions. An item that needs no judgment needs no model.

## 4. Five things that never change

These hold for the smallest tool and the largest.

1. **One source.** The `.rig` file holds the intent, rules, steps, reason blocks, gates, and flow. The catalogue, Agent Skill, and fronts are compiled from it. Nobody edits a compiled file.
2. **A number lives in a rule.** Not in code, not in a prompt, not in a guide. Code reads it with `R('group.name')`.
3. **A decision that code can make is made by code.** The model reads the verdict. It never reads the numbers and decides.
4. **The model sends data, never code.** The names of the functions are fixed. The arguments are JSON.
5. **A refusal or an error is a result.** It is one JSON line that says what happened. It is not a crash, and the model does not repeat a refused call.

## 5. Every front reads the same pool

A tool has one core (`gates.py`, `steps.py`, `rigkit.py`, and the catalogue) and thin universal fronts: a compiled `skill/SKILL.md` for any skill-capable coding agent (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode), a zero-dependency stdio MCP server (`tool.py mcp`), a Streamable HTTP MCP + OpenAPI 3.1 + localhost approval UI server (`tool.py serve-http`), an LM Studio plugin, and a command line and graph page for a person. See [fronts.md](fronts.md) for every front and CLI command.

No front has a limit of its own, and no front decides a gate. A change of the source reaches all fronts at the next build.

## 6. When to use the method, and when not

Use it for a job that is **a repeated procedure with real limits and a result that can be checked**: a production pipeline, a quality check, a release, a review against fixed rules, a conversion of many files.

Do not use it for open work: "help me design this", a talk, research with no fixed end. There the structure is a cost and gives nothing back.

Between the two: start at level 1 or 2. A tool can grow later without a new start.

## 7. Where the method comes from

The method was taken from a private production agent that runs a long procedure on many items, with a frontier model and a small local model on the same code. That project found each rule of this guide the slow way. Three findings shaped the method most:

- Numbers that were copied into a guide, a skill and a plugin went out of step. One catalogue ended that.
- A local model that got the whole procedure as text left most of its work undone. The same model did the work when code walked the procedure and asked it only for the choices.
- Good work was thrown away because every failed check was a stop. The split into hard and soft gates, and an end for "kept, but doubtful", ended that.

Research that points the same way is in [docs/history/findings-2026-11-11.md](../../../docs/history/findings-2026-11-11.md).
