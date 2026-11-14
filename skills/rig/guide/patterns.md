# Patterns for a production tool

A level 4 tool changes real files, works through many items, and needs the judgment of a person. These patterns come from a production agent. Each one answers a failure that happened.

The doctor cannot check most of them. Check them yourself with the list at the end.

## 1. Work on a copy

**Failure:** a test run changed the real file.

- The default target of the tool is a copy, never the real thing. The real thing needs a word from the person, for that batch.
- A rule of the group `permissions` guards each change that is hard to undo: write, save, send, publish, delete. Its default is the safe value, so a tool that is set up wrong does nothing.
- Put the gate that reads the permission **before** the step, and let the step check the rule again. The flow then has an end for the dry run, and the step is safe when it is called alone.
- Name the copy so that nobody can mix it up with the original (a suffix such as `-TESTCOPY`). Keep copies and run output out of version control.
- A test must leave its test set as it found it (`examples/release-tool/tool.py`, `clean_cases`).

## 2. A way back for every change

**Failure:** an item that failed late was left half done.

- The first step that changes an item keeps the old state: a copy, a backup layer, the old value in the run.
- Every end that is not "done" goes through a restore step, or changes nothing.
- Keep what was thrown away, too. The rejected result goes to a side place (a `.try` copy), not to nothing. The person may want to see why it was rejected, and a result that only failed a soft gate may be the better one.

## 3. Hard, soft and doubtful

**Failure:** good work was thrown away because one small check failed.

- Every verdict is `hard` or `soft`. A hard fail can never be kept. A soft fail can.
- A soft fail first gets a correction round, when a correction exists. The number of rounds is a rule.
- After the rounds, a soft fail ends at **kept, but doubtful**: the result stays, with a mark and the problems in its note. A person looks at the doubtful ones. One rule switches this off (then a soft fail is a restore).
- So a flow has at least these ends: done; doubtful; skipped, with nothing changed.

## 4. Ends that say who must act

**Failure:** "skipped" hid three different things, and nobody knew what to do next.

Sort every item that is not done by **who must act**:

| Queue | Who acts | Example |
|---|---|---|
| left for the model | a model, with a choice to make | The planner found two options and no rule to choose. |
| waits for the person to make something | a person | A part that must be drawn; a missing input file. |
| waits for the person to confirm | a person, with one look | The tool made the thing; one look releases all the items that wait for it. |
| ready to go on | nobody yet: run them again | The thing they waited for now exists. |

- The runner gives two queues from the run files: `left_for_model` and `waits_for_person` (`tool.py queues`). Queues that depend on the job (waits for a part, ready to go on) are ends of the flow, or files that the steps write.
- A queue belongs to one target: keep one runs folder for each. An item of another target is not "ready".
- When the host can show a mark on an item (a colour, a tag), use one mark for each queue. The colours are rules.
- A report for the person lists the queues sorted by how many items wait for each thing. The person then does the work that frees the most items first.

## 5. Code drives the batch

**Failure:** a small model that was asked to work through a long list left most of it undone.

- One call does one item, all steps and gates.
- A batch is a loop in code, not in the model. The model gets one short line for each batch: the counts and the path of the report.
- An item that needs a choice is put back as it was, and goes to the queue "left for the model". The batch goes on.
- At the end, the left items come back to the model as a short list, one time each.
- A batch has a size limit, and it is a rule. The first batch is small.

The runner has this: `tool.py batch` runs a list and writes a report, and `tool.py queues` lists the runs that wait, by who must act. A run that needs the model does not stop the batch: it waits in its file.

## 6. The state survives a restart

**Failure:** the host was restarted, and the tool no longer knew what it had pasted where.

- The runner saves each run as a file after every node. A new process reads it and goes on.
- Anything else that a later step needs (what was changed, how many rounds were done) is in the state of the run, not in the memory of a process.
- When the item changed since the run was saved, the saved run is stale: say so, and do not go on from it.

## 7. Time limits and slow hosts

**Failure:** a host application stopped a call after some seconds, and the item was left broken.

- Know the time limit of the host, and keep each call far under it. One item, one call. A loop over many items watches the clock and goes on in the next call.
- A step that is too slow is an error class of its own. Do not repeat the call. After two in a row, stop the batch and tell the person: the host may need a restart.
- A long result goes to a file. The call returns the verdict and the few fields that the next step needs, and the path of the file.

## 8. Output that the model can read

**Failure:** each step returned a page of numbers; the model lost the thread.

- A result is short JSON. The first keys are the ones to act on: `ok`, the verdict, the next thing to do.
- The verdict says what to do, in words that the instructions use: finish, correct, keep doubtful, restore and skip. The model does not work it out from numbers.
- A problem text names the value, the rule and the value of the rule.
- The whole result goes to a file for the review. The model reads the file only when it needs more.

## 9. The eye of the person

**Failure:** the agent said "looks good" about a result that it had seen at stamp size.

- A visual judgment belongs to the person. Make the gate a `human` gate, or make the end "composed, to be looked at".
- Give the person evidence that is easy to judge: a sheet of many results side by side, with the reference in a second colour, and the problems as text under each.
- Before an agent says anything about a shape, it looks at one item large, not at a sheet of many. Then it reports facts ("the outline lies on the reference"), not a judgment.
- The marks of the person are input. Give the person two or three marks with fixed meanings ("wrong in this way", "wrong in that way"), read them back with a step, and start every review from them.
- The marked items become the test sets: the ones that were good must stay good, and the ones that were marked must change.

## 10. The memory of the project

**Failure:** a later session found the same trap again, and an earlier fix came back as a new bug.

| File | Holds | Rule |
|---|---|---|
| `notes/project-facts.md` | What is true: the pipeline, the decisions of the person, the words, the facts about the host | Read first, on any computer. The memory of an agent differs between computers; this file does not. |
| `notes/failures-log.md` | Methods that failed, and why | Read before a batch. Do not repeat what is here. |
| `bugs-and-fixes.md` | Code bugs: symptom as it was seen, cause, fix, check | A fixed bug gets a regression case. |
| `reports/` | One report for each batch or review | Failures first. |
| the `note` and `evidence` of a rule | Why a value is what it is | A new limit needs one. |

- One word has one meaning. Put the words of the project into `project-facts.md`, and use them the same way in the code, the source and the reports.
- Write for a reader who is tired and not an expert: short sentences, the condition before the instruction.

## 11. A change goes everywhere at once

**Failure:** the code was changed, and the instructions of one model still described the old steps.

- The source is compiled to every front. So a change of a rule, a gate or the flow needs one build.
- What cannot be compiled (a guide in prose, examples for a small model) is listed in the README under "after a change, also update". Keep that list short, and move things out of it into the source when you can.
- The checks after every change are four commands, and all must pass: the doctor, the tests, the regression set, and the type check or build of each front.

## 12. The host bridge

A tool that works inside an application needs code that reaches it: an MCP server, a command line of the application, a script folder.

- Write the bridge one time for each host, and share it between the tools of that host.
- The bridge passes **data**. The front never builds code from the words of the model: the function names are fixed, and the arguments travel as one JSON string.
- The steps run inside the host; the gates do not need it. So the gates and the flow can be tested on any computer, and only the steps need the host.
- A tool that installs alone keeps its own copy of shared code. A check command says when a copy is stale (`rig.py build --check` does this for `rigkit.py`).

## Check list for level 4

- [ ] The default target is a copy. A real target needs a word from the person.
- [ ] Every change that is hard to undo has a `permissions` rule, off by default, and a gate before the step.
- [ ] Every item that fails after the first change is restored, and what was thrown away is kept.
- [ ] Every gate is hard or soft on purpose. A soft fail can end at "doubtful".
- [ ] Every end says who must act. Each queue has a report for the person.
- [ ] A batch is a loop in code. The model gets one item, or one line for each batch.
- [ ] A run goes on after a restart.
- [ ] No call can run into the time limit of the host.
- [ ] No result is longer than the model needs.
- [ ] No agent judges a look. The person has a sheet to judge from, and marks to answer with.
- [ ] The four memory files exist and are read at the start.
- [ ] After a change: doctor, tests, regression, the build of each front.
