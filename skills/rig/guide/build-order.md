# Build order: from a wish to a working tool

For the agent that builds a tool, and for the person who asks for it. Do the stages in order. Each stage has a **done when** line: do not start the next stage before it is true.

`RIG` is the path of `skills/rig/rig.py`. The pattern example is `examples/release-tool`.

| Stage | What | Level |
|---|---|---|
| 0 | Ask | all |
| 1 | Do the job by hand | 2 and up |
| 2 | Make the project | all |
| 3 | Write the steps | all |
| 4 | Move every number into a rule | 2 and up |
| 5 | Move every decision into a gate | 2 and up |
| 6 | Wire the flow and name the ends | 2 and up |
| 7 | Build the fronts | all |
| 8 | Run, look, and learn | 3 and up |
| 9 | Harden | 3 and up |

A level 1 tool uses stages 0, 2, 3 and 7. It is done in one session.

## Stage 0. Ask

Ask the person before you write anything. Use these questions, and write the answers into `notes/project-facts.md` (level 4) or the README.

1. **The job.** What goes in, and what must come out? Give one real example.
2. **The item.** What is one unit of work (a file, a record, a glyph, a page)? How many are there?
3. **The host.** Where does the work happen: files, a web service, an application? How does code reach it (a library, a command line, an MCP server)?
4. **Good or not.** How do you know that a result is good? Which part of that can be measured, and which part must be seen?
5. **Harm.** What can the tool change that is hard to undo? What must it never touch?
6. **The person.** Which decisions stay with you? What do you want to see before something is kept?
7. **The models.** Who will run the tool: Claude, a local model, both? How small is the local model?
8. **The end.** In which ways can one item end? (Done; skipped, with a reason; waits for a person; ...)

Then choose the level with [levels.md](levels.md) and say it to the person.

**Done when:** the answers are written down, and the person agreed to the level.

## Stage 1. Do the job by hand

Do 10 to 20 real items yourself, with the person watching the results. Use the host directly. Keep a log: for each item what you did, what you measured, where you decided something, and what went wrong.

Do not write the tool yet. This stage finds the real steps and the real decisions. A flow that is designed before any item was done is a guess about the job.

The log is the raw material for the next stages:

- A thing you did the same way each time is a **step**.
- A number you used is a **rule**.
- A place where you looked at a value and chose is a **gate**.
- A place where the person corrected you is a `human` gate, or a missing gate.
- A way an item ended is an **end**.

**Done when:** the person accepts most of the results, and the log names the steps, the numbers, the decisions and the ends.

## Stage 2. Make the project

```bash
python3 RIG new DIR NAME --level N
```

The new folder is a working tool with one example step and one example gate. Run its doctor once to see everything pass. Then replace the example with the real tool, one piece at a time, with the doctor passing after each piece.

**Done when:** the folder exists, and `python3 RIG doctor DIR` reports nothing missing.

## Stage 3. Write the steps

A step is a function in `steps.py`: `def name(state, R)`. It reads the state of the run and the rules, does its work, and returns a value. The value goes to `state[<step id>]`.

- A step does one thing, and returns the facts that a gate needs. It does not decide.
- Only steps touch the world. Gates never do.
- A step that changes something has a way back: it keeps the old thing, or it works on a copy ([patterns.md](patterns.md)).
- A step that fails raises an error with a clear text. The runner turns it into a result, and the run can resume after the cause is fixed.
- When the code runs inside a host application, keep each call short and return one JSON line (`rigkit.step`).

Write a test for each step that can run without the host. For a step that needs the host, test it in the host on a copy, and say so in the test file.

**Done when:** each step of the log is a function, and you ran each one on real items.

## Stage 4. Move every number into a rule

Search the code and your log for numbers, switches and names (a file name, a font name, a server). Each one becomes a `rule` in the source:

```
rule notes.min_words 50
  min 10
  max 500
  label "Shortest release notes"
  unit "words"
  note "shorter notes did not answer the usual questions"
```

- The id is `group.name`. Groups make the table readable: `limits`, `permissions`, `files`, and the stages of the job.
- Give `min` and `max`, or `options`. They stop a wrong value before a run starts.
- The `note` says where the value comes from. A value with no reason is a value that nobody dares to change.
- Do not set a limit from one item. Say in the note how many items it was checked on.
- A mode of the tool (fast and careful, old method and new method) is a `preset`: a named set of values.

**Done when:** no number is left in the code or in the text of a node, and the doctor line "no number in the text" is ok.

## Stage 5. Move every decision into a gate

For each decision of the log, ask: **can code decide this?**

| Answer | Kind | What to write |
|---|---|---|
| Yes, and a fail must stop the item | `hard` | a function in `gates.py`, and a test |
| Yes, but the item can go on with a mark | `soft` | a function in `gates.py`, and a test |
| No: it needs judgment, and the model has what it needs to judge | `judge` | a `brief`: what to judge, and what makes a pass |
| No: it is the person's call (taste, risk, anything visual) | `human` | a `brief`: what to show, and what to ask |

A gate is a pure function: `def name(state, R)`. No files, no network, no host. It returns:

```python
{'pass': False, 'when': 'tests failed; reported', 'problems': ['the last test run failed'], 'failed': 3}
```

- `problems` is text for a person: the value, the rule and its value. "the notes have 12 words (notes.min_words 50)".
- `when` names the fail line to follow, when the gate has more than one.
- Other keys are facts. They go into the trace of the run.

Each gate gets a test with the rule defaults, and a test with a changed rule. The checker counts a gate as tested only when the test file names its function.

Two questions catch most missing gates:

- **"What did the person correct in stage 1?"** Each correction is a gate that was missing.
- **"What does the model assume here?"** An assumption that code can check is a gate.

**Done when:** `python3 RIG doctor DIR` shows the lines "every hard or soft gate names code that exists" and "a test names the code of every gate" as ok.

## Stage 6. Wire the flow and name the ends

Connect the nodes in the source with `next`, `pass` and `fail`. Then name every way a run can end.

- An end says **who must act next**: nobody (done), the person (waits for a part, waits for a look), the model (left for a choice). "Stopped" alone is too little: see queues in [patterns.md](patterns.md).
- A gate that only reports leads on to the same node on fail. A gate that blocks leads to an end, or to a correction step.
- A correction is a loop. Every loop needs a gate that counts the rounds, with the limit as a rule.
- Keep the wires in the source file. The graph page shows them, and it changes values only.

Look at the flow as a graph with the person. A person sees a missing path in a graph much faster than in a text:

```bash
python3 RIG serve NAME.rig --json gen/NAME.json
```

Then write the regression set: one case for each end, and one for each fail line that matters. Write the baseline after you looked at the paths.

**Done when:** the person looked at the graph and agreed, and the doctor lines of level 3 are ok.

## Stage 7. Build the fronts

```bash
python3 RIG build DIR
```

This compiles the catalogue, the skill and the tool definitions. See [fronts.md](fronts.md) for the plugin of a local model and for how to install the skill.

Test each front the way it will be used: give the model one item and watch the calls. The first run with a model always finds a text that the model reads in another way than you meant. Fix the text in the source (an `intent`, a `brief`, a `do`), not in the compiled file.

**Done when:** each front did one whole item, and you read the trace of that run.

## Stage 8. Run, look, and learn

Now the loop that makes the tool good. One round:

1. Run a batch. Start small: 5 items, then 20, then all.
2. Write a report: failures first, with the reason. Then the counts.
3. The person looks at the results and marks what is wrong, in the host or in a list.
4. Start from the marks. For each one ask: which gate should have seen this? Either a gate is missing, or a limit is wrong, or a step is wrong.
5. Change the tool. Add the marked items to the regression set, with the result that is right.
6. Write what you learned: a failed method into `notes/failures-log.md`, a code bug into `bugs-and-fixes.md`, a decision of the person into `notes/project-facts.md`.

Rules for this loop:

- **The judgment of a result belongs to the person.** You may say "the check passes". You do not say "it looks good".
- **Say what was not checked.** A report that hides a gap is worse than a gap.
- **Do not change a limit to make one item pass.** Find what is different about the item.
- **A regression case that changes its result is a stop.** Report it. The person decides whether the new result is the right one.

**Done when:** this stage does not end. A round is done when its marks are in the regression set and the set passes.

## Stage 9. Harden

After some rounds, look at the `judge` gates and at the steps that the model does.

- A `judge` gate that the model always answers the same way from the same facts can be code. Write the function and its test, add `by`, and change the kind. Coverage goes up.
- A step that the model does the same way each time can be code.
- A `judge` gate that the model gets wrong, and that code cannot decide, becomes a `human` gate, or gets a better brief.
- An item that a small model cannot do goes to an end "left for a larger model or a person", not to a guess.

Do not harden early. A gate written before the job is understood fixes the wrong thing in place.

**Done when:** the coverage note of the doctor stopped moving for a few rounds, and every remaining `judge` gate is one on purpose.
