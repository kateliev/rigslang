# Describe code in Rig; cast and prove snippets (language version 0)

> Kept as a record. Language version 1 removed the snippet scale: `cast`, `probe`, the hashes and the commands `prove`, `probe`, `stamp`, `emit` and `hash` are gone. The links below point to files of version 0.

Part of the skill `rig`. Read [SKILL.md](SKILL.md) first.

This file is for work at the snippet scale: you describe existing code in Rig, or you write code for a unit that is a hole, and a real run proves it. To build a tool or an agent, use the guide ([guide/build-order.md](guide/build-order.md)), where the code lives in normal files and a `code` line binds it.

You, the model, **reason**: you write the code and decide `judge` gates. The **intent** says what the code must do. **Gates** decide in a real runtime if your work is correct.

Before you start, read [spec.md](spec.md) in this folder. It is short, and it is the only definition of the language.

The tool [rig.py](rig.py) is in this folder (Python 3, standard library only). Below, `RIG` means `python <this folder>/rig.py`.

| Command | Use |
|---|---|
| `RIG check FILE` | Validate. Show the status of each unit. Run it after every change. |
| `RIG hash FILE` | Print the current hashes. |
| `RIG prove FILE [UNIT] --stamp` | Run the examples and checks against each `py`, `js` or `ts` cast in its real runtime; stamp it `proved` if all pass. `--lang L` picks one language. |
| `RIG probe FILE [UNIT] --stamp` | Run the probes: live runs against the real world. Stamp `observed` only a cast that has no examples. |
| `RIG stamp FILE UNIT LANG` | Stamp a cast in a language with **no runner**, **only** after you proved it in that language's real runtime. It refuses `py`, `js` and `ts`. |
| `RIG emit FILE LANG DIR` | Write the proved and observed casts in LANG as modules into DIR, each with its catalogue. It refuses the others. |
| `RIG json FILE` | The parsed tree, for other tools. |
| `RIG compile json FILE [UNIT]` | The unit as a catalogue: the JSON rules and flow that a code runner reads. |
| `RIG compile skill FILE [UNIT]` | The unit as a `SKILL.md`. `--rules PATH`: the skill reads the values from that JSON file. |
| `RIG compile tool FILE [UNIT]` | The unit as a tool definition: name, description and the JSON Schema of its inputs. |
| `RIG from-json FILE.json` | A catalogue back to Rig. |
| `RIG serve FILE --json OUT --skill OUT` | The viewer for FILE on 127.0.0.1. Save writes FILE and compiles it again. |

Compile options: `--preset NAME` uses the values of a preset; `-o OUT` writes a file.

## The firm rules

1. **Never imagine what code returns.** A proof comes from a real run. Never type a hash, a `proved` or `observed` stamp or a date by hand. Only `prove --stamp`, `probe --stamp` or `stamp` writes them.
2. **Never falsify an intent.** When you describe existing code, the intent states what the code does, not what it should do. Take the examples from real runs.
3. **Never change a proved cast** unless the human asks or its unit is remelted or stale.
4. **Keep it small.** A snippet needs one intent, one or two examples and one ensure. Do not add ceremony.
5. **Plain language.** Use short sentences, one word for one meaning, and the active voice (ASD-STE100 style).

## A. Code → Rig (describe)

Use this when the human gives you code, a script, a prompt or agent instructions.

1. **Choose the scale.**
   - One function → `unit <name> snippet`.
   - A program with stages → `unit <name> tool`, with `step` and `gate` nodes and `uses` for its functions.
   - An agent, a prompt or a procedure with checkpoints → `unit <name> agent`.
2. **Intent.** Write one sentence that says what the unit does, not how. Describe what the code does (rule 2).
3. **Signature.** Add `in` and `out` lines with types (spec, Section 2: Types). Add a text to each when the unit will be a tool for a model, for example `in query str "the words to search for"`.
4. **Examples.** Take them from existing tests first. Otherwise run the code and record real outputs. Choose 2 to 4 that show the edges (empty input, Unicode, limits).
5. **Ensure.** Add the properties that must always hold. Add a `check py "…"` child when the property can be code.
6. **Cast.** Put the existing code under `cast <lang>`, with no hashes. The cast imports the units that it `uses` from `./<unit>.<ext>` and its rule values from `./<unit>.json` (spec, Section 2: Modules). Then prove it:
   - `py`, `js`, `ts`: `RIG prove FILE UNIT --stamp`.
   - Another language: write a small test in that language from the examples and checks, run it, and only if it passes run `RIG stamp FILE UNIT LANG`.
   - Code that needs the real world (the network, files, a service) often has no examples. Add `probe` lines with `check` children, and run `RIG probe FILE UNIT --stamp`. The result is `observed`, never `proved`.
7. **For agents and procedures:**
   - every number or switch → a `rule` with a `group.name` id (with `min`, `max` and `label`, and a `note` if the value must not change). In the text, write `{group.name}`, never the number;
   - every action → a `step` with `do`, and `by` if code does it;
   - every checkpoint → a `gate`. Use `hard` or `soft` if code can decide it (name the code in `by`). Use `judge` with a `brief` if only judgment can decide it;
   - `by` names a unit (of this file, or in a `uses` line), the unit itself (its own cast), or an `external`. Write `external <name> "what it does"` for code that Rig does not prove. Never write a `by` name that points at nothing: the checker warns, and the gate counts as `none`;
   - every way to stop → an `end`;
   - wire them with `next`, `pass` and `fail`.
   If a checkpoint should be code but no code exists yet, make it `judge` and add `note "candidate for code"`.
8. **Notes.** Add a `note` only when the code looks wrong but is right, or when a value must not change. Do not explain why the unit exists: the intent is enough.
9. Run `RIG check FILE`. Fix every error. Tell the human about each warning that you cannot fix.

## B. Rig → code (cast)

Use this when a unit is a **hole**, **remelted** or **stale**.

1. Run `RIG check FILE` to list the units and their status.
2. For each hole or remelted unit:
   1. Choose the target language. Use the language that the human named, then the language of the project. Use `py` when there is no other preference.
   2. Write the code from the intent, the examples and the ensures. Name the function after the unit (`-` becomes `_`).
   3. Write it under `cast <lang>` with no hashes.
   4. Prove it (step A6). If it fails, fix the code, not the examples. If an example seems wrong, ask the human.
3. For each **stale** unit: prove the current code again. If it passes but the intent no longer describes it, write the intent that describes the code (rule 2). The unit remelts: prove it again.
4. Never touch a proved cast.
5. Run `RIG check FILE`. Report each unit as proved, observed, failed or skipped.

## C. Agent unit → instructions (compile)

For a tool that is a project (a folder with `rig.json`), do not use the single compilers: `RIG build DIR` compiles every front. The steps below are for one `.rig` file with no project.

Use this when the human wants an agent to follow an agent unit. Do not write the instructions by hand: compile them.

1. Run `RIG check FILE`. Fix every error.
2. For an agent that follows instructions (Claude, a chat model): `RIG compile skill FILE UNIT -o SKILL.md`.
3. For a code runner: `RIG compile json FILE UNIT -o UNIT.json`. The runner reads `rules` by `id` and walks `flow` from `start`.
4. When both run the same agent, give the values one place: `RIG compile skill FILE UNIT --rules UNIT.json`. The skill then reads the values from the JSON file.
5. For a model that calls tools: `RIG compile tool FILE UNIT -o UNIT.tool.json` for each tool unit. Do not write tool descriptions or parameter schemas by hand.
6. For a program that imports the code: `RIG emit FILE LANG DIR`. It writes only proved and observed casts.
7. The skill ends with a Report section when the agent decides gates itself. The agent must end its answer with a `Guessed:` line. Do not remove it.
8. To change values later, edit the `.rig` file (or use `RIG serve`) and compile again. Never edit the compiled files.

## D. Intent → agent (build)

This is the short form, for an agent that only follows instructions. For a tool with code, a runner and tests, use [guide/build-order.md](guide/build-order.md).

Use this when the human gives an intent and wants an agent.

1. **Intent and ends.** Write `unit <name> agent`, the `intent`, and one `end` for each way the work can stop.
2. **Steps.** Write the work as `step` nodes in order, each with `do`.
3. **Gates.** At each decision, ask: can code decide this? If yes, use `hard` (a fail blocks) or `soft` (a fail is reported) with `by`. If no, use `judge` with a `brief`. If the decision belongs to a person, use `human` with a `brief` that says what to ask.
4. **Rules.** Make every number and switch a `rule` with a `group.name` id, `label`, and `min`/`max` or `options`. In the text, write `{group.name}`. Add a `preset` for each mode the human names (for example fast and careful).
5. **Wire.** Connect the nodes with `next`, `pass` and `fail`. Every gate needs a `pass`.
6. **Check.** Run `RIG check FILE` until there are no errors. Read the warnings: unused rules, numbers in text, gates without code, `by` names that point at nothing.
7. **Compile.** Section C.
8. **Show.** Tell the human to open the file in the viewer (or `RIG serve FILE`) to inspect the graph.
9. **Harden later.** When code can decide a `judge` gate, write that code as a unit, add `by`, and change the kind to `hard` or `soft`. Coverage counts only proved code: prove the unit, and coverage goes up.

## E. Report

At the end, show the human a short table:

| unit | scale | status | what you did |
|---|---|---|---|

Name each gate that could move from `judge` to code, each gate whose code is not proved (level `code` or `observed`), and each warning that you did not fix.

## Viewing

`viewer/index.html` in the Rig repository shows a `.rig` file in four tabs: **Units** (tables), **Graph** (the flow as a node graph, with the rules as inputs), **Skill** and **JSON** (the compiled forms; the JSON tab also shows the tool definition of a unit that has inputs). Rule values can be edited in the Units and Graph tabs. Open the page in a browser and drop the file on it, or run `RIG serve FILE` to save in place.
