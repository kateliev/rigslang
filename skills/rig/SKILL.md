---
name: rig
description: Read, write and run Rig (.rig) files, a small language that keeps the intent of code and its checks (gates) together. Use it to convert code, scripts, prompts or agent instructions INTO Rig (describe them), to convert Rig INTO code (fill holes, cast and prove them in a real runtime), to check a .rig file, or to turn an agent unit into instructions an agent can follow. Trigger on ".rig", "Rig", "riglang", "describe this code in Rig", "cast the holes", "remelt", "gate coverage".
---

# Rig

Rig stands for **Reason, Intent, Gate**. You, the model, **reason**: you write the code and decide `judge` gates. The human owns the **intent**: what the code must do. **Gates** decide in a real runtime if your work is correct. The model writes Rig, a person reads it.

Before you start, read [spec.md](spec.md) in this folder. It is short, and it is the only definition of the language.

The tool [rig.py](rig.py) is in this folder (Python 3, standard library only). Below, `RIG` means `python <this folder>/rig.py`.

| Command | Use |
|---|---|
| `RIG check FILE` | Validate. Show the status of each unit. Run it after every change. |
| `RIG hash FILE` | Print the current hashes. |
| `RIG prove FILE [UNIT] --stamp` | Run the examples and the `check py` lines against the `py` cast; stamp it if all pass. |
| `RIG stamp FILE UNIT LANG` | Stamp a cast in another language, **only** after you proved it in that language's real runtime. |
| `RIG json FILE` | The parsed tree, for other tools. |

## The firm rules

1. **Never imagine what code returns.** A proof comes from a real run. Never type a hash or a `proved` date by hand. Only `prove --stamp` or `stamp` writes them.
2. **The human owns the intent.** If you write the intent of code that already exists, it is a draft. Show it to the human and ask them to confirm it.
3. **Never change a proved cast** unless the human asks or its unit is remelted or stale.
4. **Keep it small.** A snippet needs one intent, one or two examples and one ensure. Do not add ceremony.
5. **Plain language.** Use short sentences, one word for one meaning, and the active voice (ASD-STE100 style).

## A. Code → Rig (describe)

Use this when the human gives you code, a script, a prompt or agent instructions.

1. **Choose the scale.**
   - One function → `unit <name> snippet`.
   - A program with stages → `unit <name> tool`, with `step` and `gate` nodes and `uses` for its functions.
   - An agent, a prompt or a procedure with checkpoints → `unit <name> agent`.
2. **Intent.** Write one sentence that says what the unit does, not how. It is a draft until the human confirms it (rule 2).
3. **Signature.** Add `in` and `out` lines.
4. **Examples.** Take them from existing tests first. Otherwise run the code and record real outputs. Choose 2 to 4 that show the edges (empty input, Unicode, limits).
5. **Ensure.** Add the properties that must always hold. Add a `check py "…"` child when the property can be code.
6. **Cast.** Put the existing code under `cast <lang>`, with no hashes. Then prove it:
   - Python: `RIG prove FILE UNIT --stamp`.
   - Another language: write a small test in that language from the examples and checks, run it, and only if it passes run `RIG stamp FILE UNIT LANG`.
7. **For agents and procedures:**
   - every number or switch → a `rule` (with `min`, `max` and `label`, and a `note` if the value must not change);
   - every action → a `step` with `do`, and `by` if code does it;
   - every checkpoint → a `gate`. Use `hard` or `soft` if code can decide it (name the function in `by`). Use `judge` with a `brief` if only judgment can decide it;
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
3. For each **stale** unit: prove the current code again. If it passes but the intent no longer describes it, propose a new intent to the human. Do not change the matrix on your own.
4. Never touch a proved cast.
5. Run `RIG check FILE`. Report each unit as proved, failed or skipped.

## C. Agent unit → instructions

Use this when the human wants an agent to follow an agent unit.

1. Write a short skill or prompt from the unit:
   - the intent first;
   - then the flow as numbered checkpoints, by id: `notes (hard): …`, with `pass` and `fail` written as "then go to …";
   - the rule values inline, with their ids;
   - for `judge` gates, the `brief` as the instruction, and the words "label the result as a guess".
2. For `hard` and `soft` gates, tell the agent to **call the `by` code and obey its result**, not to decide by itself.
3. Do not copy rule values into more than one place. If the target runtime can read the `.rig` file (`RIG json`), point it to the file instead.

## D. Report

At the end, show the human a short table:

| unit | scale | status | what you did |
|---|---|---|---|

Name each intent that you drafted and the human did not confirm yet, and each gate that could move from `judge` to code.

## Viewing

`viewer/index.html` in the Rig repository shows any `.rig` file as a table and as a graph. Open it in a browser and drop the file on the page.
