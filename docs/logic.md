# How Rig works, and why

This page explains the ideas of the language and of the kit. The exact rules are in [the specification](../skills/rig/spec.md). The method for building a tool is in [the guide](../skills/rig/guide/README.md). [status.md](status.md) has the state of the work.

## 1. The problem

A model that does a job with tools goes wrong in three ways:

1. **It decides what code could decide.** A limit in a prompt is a suggestion. A model wrote 142 words for a limit of 120.
2. **Nobody knows what was guessed.** The answer does not show which parts a test checked and which parts the model decided by judgment.
3. **The numbers drift.** A value is copied into a prompt, a script and a README, and the copies stop agreeing.

## 2. Three words

| Word | Question | Who owns it |
|---|---|---|
| **reason** | What needs judgment? | The model: the steps that need language, and the `model` gates. Its results are marked as guesses. |
| **intent** | What must the tool do? | The person, or the model, in plain words. An intent must never be falsified: when it describes existing code, it says what the code does. |
| **gate** | How do we know it did? | Code where code can decide (`hard`, `soft`). Else the model (`model`, a guess). Else a person (`human`). |

## 3. One source, one core, thin fronts

A tool is one `.rig` file and normal code files. The source says the order of the work and who decides. The code (`steps.py`, `gates.py`) does the work and the decisions. A runner (`rigkit.py`) walks the flow.

The fronts are compiled from the source: a skill for Claude, a plugin for a local model, a command line and a graph page for a person. No front has a limit of its own, and no front decides a gate. A change of the source reaches all fronts at the next build.

## 4. The flow is the order of the lines

In version 1, the lines of the flow run in order. A step, then the next line. A gate that passes goes on to the next line; a gate that fails goes to an end. The flow never jumps back.

Why: a flow with jumps (`next ->`, `pass ->` in version 0) can say anything, but a person must follow arrows to read it. In real flows, about a third of the nodes were plumbing: a step that takes the next page, a gate that asks "is a page left?", a gate that counts the rounds. The order of the lines says the same thing with no extra nodes, and it reads from top to bottom.

What a flow still needs, a few blocks say:

| Block | For |
|---|---|
| `for <item> in <path>` | A list of parts in one run: pages of choices, batches to sort. `fail -> continue` leaves one item; `tolerate` says how many may be left. |
| `until <path>` with `retry <n>` | "Again until the model says done." The only loop without a list. |
| `if <path>`, `else` | Two ways through. `if` on one node skips that node. |
| `section "name"` | A heading. It has no effect on a run. |
| `finally` | The report that must be written, also after an error. |

A correction is `retry <n>` on the gate that checks: on fail, the run goes back to the step before the gate. These are the only ways back, so every loop has a limit that the source states.

**Paths, never expressions.** `if sort.new_folders` tests one value of the state: is it there, and not empty, and not false? Rig has no variables, no assignments and no expressions. When a decision needs a computation, the computation is code, and the source names it with `by`.

## 5. Who decides: the lanes

Every node has a decider: code, the model, or a person. The catalogue writes it as the `lane` of the node, and the graph page draws the nodes in three bands. A person sees at once how much of the flow is code, and where the model or a person acts.

**Coverage** is the share of the gates that tested code decides. It is not a goal by itself: a gate that needs judgment stays a `model` gate. The goal is that no gate is a guess by accident.

A `human` gate is the only place where the person decides, and the model can never answer it. The runner refuses an answer of the model there; the plugin has no tool for it. A gate with `options` takes the words of the person and gives them to code, which asks again when it does not understand them.

## 6. Runs that can be read again

A run has a folder. The runner keeps four things there:

- **A pinned copy of the flow and the rules.** A run that started before a change goes on as it began, and says that the source changed.
- **Every answer** of the model and of the person, in order.
- **The state before each line** outside a loop. `rerun --from <line>` starts a new run there, with changed rules: a fix of code or of a value can be tried on the item where it failed, with no new answers.
- **The progress of a loop.** The run is saved after each item, so a stopped process goes on from the next item.

`replay` plays the recorded answers again with the current code: a flow test with no model. Together with the regression set (written answers) and the tests of the code, it shows what a change does before a model or a person sees it.

## 7. The language stays small

Two limits hold:

1. **Rig is not a general programming language.** It says the order of the work and who decides. Code computes everything.
2. **One word has one meaning, and a word comes in only when it removes nodes from real flows.** Version 1 has about as many words as version 0 (33), but it says more. The words that went out, and what replaces them, are in the spec, Section 3.

## 8. Where Rig came from

Rig began as a language for single functions: a unit held its code inside the `.rig` file as a **cast**, proved against its examples and pinned by hashes. That idea worked for small pure functions, but a tool needs normal code files, tests and a runner. Since the kit (2026-11-15), the code lives in files and the tests prove it. Version 1 (2026-11-25) removed the snippet scale from the language. Its examples and its task file are in [history/](history/).
