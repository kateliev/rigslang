# The four levels

A tool has a level. The level says how much the tool needs. A simple tool must not pay for what a production tool needs.

Each level adds to the level before it. A tool can go up a level later: you add files, you do not start again.

| Level | Name | The tool has | Good for |
|---|---|---|---|
| 1 | tools | Functions with typed inputs. The tool definitions come from the source. | Look up, convert, measure, rename, fetch. |
| 2 | checked | Rules, and gates in code that return a verdict. A flow that the runner walks. | A job with limits and a clear "good or not". |
| 3 | flow | Named ends for every way a run can stop. A regression set that plays the answers of the model. A compiled skill. | A procedure with stages, used again and again. |
| 4 | production | Permissions, a human gate, a way back for every change, and the memory files of the project. | Many items, real files, the judgment of a person. |

`RIG` in this guide is the path of `skills/rig/rig.py`.

```bash
python3 RIG new DIR NAME --level 2
```

```bash
python3 RIG doctor DIR
```

`doctor` checks a tool against the list of its level, and prints each line as `ok` or `MISS`. A tool is at its level when nothing is missing. The level is one number in `rig.json`: to go up, change it and run `doctor`.

## How to choose

Ask these questions in order. Stop at the first "no".

| Question | "no" means |
|---|---|
| Does the job have a limit or a "good or not" that code can check? | Level 1 |
| Does the job have stages, or more than one way to end? Will it be used again and again? | Level 2 |
| Does it change something that is hard to undo? Does it work through many items? Must a person judge the result? | Level 3 |
| (all three "yes") | Level 4 |

When you are not sure, take the lower level.

## Level 1: tools

A tool unit in the source, and one function in a code file.

```
unit word-count tool
  intent "count the words and the characters of a text"
  in text str "the text to measure"
  out (record words int characters int) "the counts"
  code tools.py
    test tests/test_tools.py
```

What the doctor checks:

- The source has no errors.
- Every unit has code, an intent, and a type and a text for every input. The model reads the intent and the texts as the description of the tool, so they are part of the tool.
- The compiled files are current.
- No number stands in the text of a node.
- The tests pass.

## Level 2: checked

An agent unit with rules, steps and gates. `gates.py` holds the decisions, `steps.py` holds the work, and `tool.py` is the runner.

What the doctor adds:

- The tool has at least one gate.
- Every `hard` or `soft` gate names code that exists, and a test names that code.
- Every rule is read by a step or a gate.
- Every `model` gate has a `check`, and every `human` gate a question.
- Every step says who does it: `by <code>` or `by model`.
- A note: number rules with no note that says where the value comes from.
- A note: the coverage. It is the share of the gates that tested code decides.

At this level the tool already runs without a model up to its first `model` gate. That is the point: you can test everything before any model sees it.

## Level 3: flow

What the doctor adds:

- The flow has an end node, every node can be reached, and the flow ends at an end line, not past its last line. (The checker already refuses a `hard`, `model` or yes/no `human` gate with no `fail` line.)
- `rig.json` names the driver (the runner command) and the compiled skill.
- A regression set exists, every case has an expected result, and the set passes.
- Every end node is the end of a regression case. A note: every gate is on the path of a case.

A regression case holds the inputs and the answers that the model and the person give. So the whole flow runs in a test, with no model:

```json
{"name": "one rewrite", "inputs": {"folder": "tests/cases/good"},
 "answers": {"tone": [{"pass": false}, {"pass": true}], "rewrite": {"result": "..."}, "approve": {"person": true, "pass": true}}}
```

```bash
python3 tool.py regress tests/regression-set.json
```

Write the expected results with `--baseline` after you looked at them. Run the set after every change of the steps, the gates, the rules or the flow. A result that changes on purpose gets a new baseline, and the commit message names the cases.

A run of a real model is a second kind of flow test. Its folder keeps every answer, so `python3 RIG test DIR --replay RUN` plays the same run again with the current code, and prints where the end or the path changed.

## Level 4: production

What the doctor adds:

- `README.md`, `notes/project-facts.md`, `notes/failures-log.md`, `bugs-and-fixes.md` and `reports/` exist.
- A rule of the group `permissions` guards every change that cannot be undone. Its default is the safe value.
- A `human` gate holds the judgment of the person. If the tool needs none, `rig.json` says why in `"human"`.

The doctor cannot check the rest of level 4. It is in [patterns.md](patterns.md): work on a copy, a way back, state that survives a restart, queues by who must act, and the review that starts from the marks of the person.

## What a level does not mean

- A level is not a mark of quality. A level 1 tool with good texts is a finished tool.
- A level does not say how good the gates are. That comes from runs and from the person: see [build-order.md](build-order.md), stage 8.
- Coverage is not a goal by itself. A gate that needs judgment stays a `model` gate. The goal is that no gate is a guess **by accident**.
