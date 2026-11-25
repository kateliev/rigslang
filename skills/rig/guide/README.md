# The Rig method

This guide says how to build an **instrumental agent**: a model that operates tools to do a defined job. Read this page first. Then read the page of your task.

| Page | Read it when |
|---|---|
| [levels.md](levels.md) | You choose how much a tool needs. A simple tool needs little. |
| [build-order.md](build-order.md) | You build a new tool, from the first question to the last check. |
| [patterns.md](patterns.md) | The tool changes real files, works on many items, or needs the judgment of a person. |
| [weak-model.md](weak-model.md) | A local model will run the tool. You design a step or a gate that the model does. |
| [fronts.md](fronts.md) | You connect the tool to Claude, to a local model, or to both. |
| [rules.md](rules.md) | Always. One page: the rules that have no exception. |

The pattern example is [examples/release-tool](../../../examples/release-tool/). When this guide and the example disagree, the example is right, because its tests run.

## 1. The problem

A model that follows a long instruction text does three things wrong:

1. **It reads loosely.** A limit that is only a sentence in a prompt is a suggestion. The model goes over it, and nothing sees that.
2. **It decides what it must not decide.** It reads a number and says "close enough".
3. **It hides its guesses.** The result does not show what code checked and what the model only thought.

More instruction text does not fix this. The fix is to move work out of the text.

## 2. The method: four parts, four owners

| Part | What it is | Who owns it |
|---|---|---|
| **Rules** | Every number, switch and name of the tool. One place. | The person. A change is a change of one value, with a reason. |
| **Steps** | The work. The only code that touches the world. | Code. |
| **Gates** | The decisions. | Code where code can decide. Else the model, marked as a guess. Else a person. |
| **Flow** | The order of the lines, the blocks (`for`, `until`, `if`, `finally`), and where a run can end. | The source file. Code walks it. |

A gate has one of four kinds:

| Kind | Who decides | What it means |
|---|---|---|
| `hard` | code | A fact. A fail goes to an end. |
| `soft` | code | A fact. A fail is reported, and the run goes on. |
| `model` | the model | A guess. The result says so. |
| `human` | a person | The run waits. The model cannot answer. |

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

1. **One source.** The `.rig` file holds the names, the numbers and the flow. The catalogue, the skill and the tool definitions are compiled from it. Nobody edits a compiled file.
2. **A number lives in a rule.** Not in code, not in a prompt, not in a guide. Code reads it with `R('group.name')`.
3. **A decision that code can make is made by code.** The model reads the verdict. It never reads the numbers and decides.
4. **The model sends data, never code.** The names of the functions are fixed. The arguments are JSON.
5. **A refusal or an error is a result.** It is one JSON line that says what happened. It is not a crash, and the model does not repeat a refused call.

## 5. Every front reads the same pool

A tool has one core and several fronts.

| | What it is | Where the knowledge is |
|---|---|---|
| Core | `gates.py`, `steps.py`, the runner | In code and in the catalogue |
| Front for Claude | `skill/SKILL.md` | Compiled from the source |
| Front for a local model | A plugin with tool definitions and a short text | Compiled from the source |
| Front for a person | The command line; the graph and table pages | The same catalogue |

The fronts are thin. A front starts runs and passes answers. No front has a limit of its own, and no front decides a gate. A change of the source changes every front at the next build.

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
