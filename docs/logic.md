# How Rig works, and why

This page explains the ideas of the language. The exact rules are in [the specification](../skills/rig/spec.md).

**Since 2026-11-15 the centre of Rig is the agent scale**: tools and agents whose code lives in normal files, with a runner that walks the flow. The method for that is in [the guide](../skills/rig/guide/README.md). The snippet scale of Section 4 (matrix, cast, remelt) still works and is still tested, but it is now the small end of Rig, not its headline. [status.md](status.md) has the state of the work.

## 1. The problem

When an LLM writes code, three things go wrong:

1. **It forgets.** It solves the same problem again in each session, a little differently each time.
2. **Nobody checks it.** Generated code often looks right and is not.
3. **Nobody knows what was guessed.** Code does not show which parts a model decided by judgment and which parts a test proved.

Agent instructions have the same problems. A paragraph in a prompt is easy to read loosely. Numbers get copied into three files and drift apart.

## 2. The idea: three words

| Word | Question | Who writes it | Who checks it |
|---|---|---|---|
| **reason** | How do we get there? | the model: it writes the code and decides `judge` gates | a gate; until then, it is a **guess** |
| **intent** | What must it do? | the human or the model, in plain controlled language | the examples and checks |
| **gate** | How do we know it did? | the model | **a real runtime** |

Each word has its own actor. The model reasons, the intent states the goal, and the runtime decides. A gate turns the model's guess into a fact, measured against the intent. An intent must never be falsified: when it describes existing code, it states what the code does. Rig keeps the three together in one small file. People read that file, and tools run it.

Rig does not ask *why* a unit exists. The intent says what it must do, and that is enough. When code looks wrong but is right, or a value must not change, write a `note`.

## 3. One syntax, three scales

| Scale | What a unit holds | Example |
|---|---|---|
| **snippet** | a matrix and a cast | [slugify.rig](../examples/older/slugify.rig) |
| **tool** | a matrix, steps, gates, and units that it `uses` | [contacts.rig](../examples/older/contacts.rig) |
| **agent** | rules (parameters), steps and gates | [release-check.rig](../examples/older/release-check.rig) |

The syntax does not change between scales. Only the amount you write changes. A snippet needs one intent and one example. Do not add ceremony that the work does not need.

## 4. The life of a snippet: matrix, proof, cast, remelt

The words come from hot-metal typefounding.

```
   write the matrix           prove in a real runtime          the matrix changes
   (intent, examples,   ──►   (examples + checks pass)   ──►   (hash mismatch)
    ensure)                    → cast, with two hashes          → remelt: a hole again
        ▲                                                              │
        └──────────────────────────────────────────────────────────────┘
```

- The **matrix** is the spec: `in`, `out`, `intent`, `example`, `ensure`.
- A **hole** is a unit with a matrix and no code.
- A **proof** runs every example and every check in a real runtime. The model never imagines a result.
- A **cast** is code that passed the proof. It carries two hashes: one of the matrix and one of the code.
- If the matrix changes, the first hash does not match. The cast **remelts**, and the unit is a hole again.
- If someone edits the code by hand, the second hash does not match. The cast is **stale**: prove it again, and check that the intent still describes it.
- Some code needs the real world: the network, files, a service. Its result changes from day to day, so it has no fixed examples. A **probe** runs it live and checks conditions on the result. A pass is **observed**, not proved: true on that day, against that world. Version control keeps the date.

The two-way check stops drift between the documentation and the code. Neither can change without the other noticing.

## 5. The life of an agent: gates and coverage

An agent unit is a small state machine. **Steps** do work. **Gates** decide. **Ends** stop the flow.

| Gate kind | Who decides | What the result means |
|---|---|---|
| `hard` | code (`by`) | a fact; a fail blocks |
| `soft` | code (`by`) | a fact; a fail is reported |
| `judge` | the model (`brief`) | a **guess**, and labelled so |
| `human` | a person (`brief`) | the flow waits; the model cannot answer |

**Coverage** is the share of gates that **proved or tested** code decides. A `by` line names a unit, an `external`, or a function of a `code` line (code in a normal file, with its test file). The gate takes the level of that code: proved (Rig ran its examples), tested (a test file names the function), observed, code (nothing checks it), or none (the name points at nothing). A gate that names code is not yet a fact: only checked code makes it one.

**A gate in a prompt is a suggestion; a gate in a runner is a fact.** The first compiled skill asked the model to walk the flow and to obey the gates. A test run showed the limit of that: a word limit that was only text was broken, and nothing saw it. So a tool now has a **runner** (`rigkit.py`): code walks the flow, calls the code of the steps and the gates, and stops only at a `judge` gate, a `human` gate, or a step that has no code. It refuses an answer for another node. Over time, move gates from `judge` to `hard` or `soft` when you can write the check, and prove the check. The model stays where it is good: inside the judge gates and inside the steps, for decisions that no rule can hold.

A `judge` result is a guess, and the person must see that. The compiled skill tells the agent to end its answer with a `Guessed:` line that names the gates it decided itself.

**Rules** are the numbers and switches of the agent. They live in one place. The text of a step or gate names a rule as `{group.name}`, never as a number, so the viewer and the checker can see unused rules and missing ones. A **preset** is a named set of rule values, for example a careful mode and a fast mode.

**One source, compiled.** The `.rig` file is the source. It compiles to a JSON catalogue for a code runner, to a skill for an agent that follows instructions, and to a tool definition for a model that calls tools. `emit` writes the proved and observed casts as modules for a program to import. Both come from the same file, so the numbers cannot drift apart between them. The skill can also read its values from the catalogue, so each value has one place at run time too. A person checks the agent in the viewer, as a graph and as tables, and changes values there.

## 6. Documentation and memory

A Rig file is pseudo-code that the agent writes and the human reads. It is also a good format for persistent memory:

- The **intent**, the **notes** and their **evidence** survive between sessions and between models.
- The **status** of each unit (proved, stale, remelted, hole, coverage) shows at a glance what is known and what is guessed.
- Version control keeps every old cast. Nothing is lost when a cast remelts.

## 7. What Rig is not

- It is not a replacement for a programming language. The code of a tool is written in a normal language, in normal files.
- It is not a framework that a tool must live in. A tool keeps one copied file (`rigkit.py`) and its compiled catalogue.
- It is not a prompt format for open-ended work. For "help me design this", plain language is better.
- It is not a way to trust a model. It is a way to *not need to*: the runtime decides.

## 8. Where it came from

- [history/sidenote-agent-configuration.md](history/sidenote-agent-configuration.md): agent configuration as a graph of gates and rules.
- [history/self-writing-language.md](history/self-writing-language.md): intent as data, and the self-writing loop.
- [history/findings-2026-11-11.md](history/findings-2026-11-11.md): research on related work, and what to learn from it.
- [status.md](status.md): the refocus of 2026-11-15, from a language to a kit and a guide.
