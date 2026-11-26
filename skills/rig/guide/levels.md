# The three levels

A tool has a level. The level says how much the tool needs. A simple tool must not pay for what a production tool needs.

Each level adds to the level before it. A tool can go up a level later: you add files, you do not start again. Plain single-function utilities belong in plain Python (micro-level `tool` units were removed in version 2).

| Level | Name | The tool has | Good for |
|---|---|---|---|
| 1 | checked | Rules, steps, reason blocks, gates in tested code, and the runner. | A checked job with limits and a clear "good or not". |
| 2 | flow | Named ends for every way a run can stop, a regression set that plays the model, a compiled Agent Skill, and the MCP front. | A procedure with stages, used again and again across coding agents and MCP hosts. |
| 3 | production | Permissions (off by default, read by a `hard` gate), rollback/restore, human gates or batch review, queues, and project memory. | Many items, real files or host apps, and the judgment of a person. |

`RIG` in this guide is the path of `skills/rig/rig.py`.

```bash
python3 RIG new DIR NAME --level 1
```

```bash
python3 RIG new DIR NAME --level 3 --template host
```

```bash
python3 RIG doctor DIR [--json]
```

`doctor` checks a tool against the list of its level, and prints each line as `ok` or `MISS` (`--json` prints structured JSON for agents). A tool is at its level when nothing is missing. The level is one number in `rig.json`: to go up, change it and run `doctor`.

## How to choose

Ask these questions in order. Stop at the first "no".

| Question | "no" means |
|---|---|
| Does the job have stages, named ends, or an Agent Skill / regression set? | Level 1 (`checked`) |
| Does it change something hard to undo, work through many items, or need human approval? | Level 2 (`flow`) |
| (both "yes") | Level 3 (`production`) |

When you are not sure, take the lower level.

## Level 1: checked

A flow unit with rules, steps, optional `reason` blocks, and gates. `gates.py` holds the decisions, `steps.py` holds the work, and `tool.py` is the runner.

What the doctor checks:

- The source has no errors.
- Every unit has a flow, an intent, and a type and text for every input.
- The compiled files are current (`rig.py build`).
- No number stands in node prose; `rig.json` names `driver` and `tests`, and the tests pass.
- The tool has at least one gate.
- Every `hard` or `soft` gate names code that exists, and its test file references that function in code (verified via the Python AST).
- Every rule is read by a step, reason block, queue, or gate (`R('group.name')` and `R.get('group.name')` inferred via AST).
- Every `model` gate has a `check`, and every `human` gate has a question.
- Every `step` says who does it (`by <code>` or `by model`), and every `by model` step and `reason` block declares `out <type>`.
- Every `never` clause under `intent` is tracked against `hard`, `model`, or `human` gates (use `never "text" -> <gate-id>` to map explicitly).
- Notes: number rules without a `note`, hardcoded numeric literals in `gates.py`, and gate coverage.

## Level 2: flow

What the doctor adds:

- The flow has an `end` node, every node can be reached, and the flow ends at an `end` line.
- `rig.json` names the compiled Agent Skill (`build.skill`).
- A regression set exists, every case has an expected result (`--baseline`), every `end` node is covered, and the set passes.

```bash
python3 tool.py regress tests/regression-set.json
```

Use `tool.py eval DATASET --baseline PATH` alongside `regress` to measure quality metrics and wall time across rule or model changes.

## Level 3: production

What the doctor adds:

- `README.md`, `notes/project-facts.md`, `notes/failures-log.md`, `bugs-and-fixes.md`, and `reports/` exist.
- At least one rule in the `permissions` group exists, defaults to `off`, and is read by a `hard` gate.
- A `human` gate holds the judgment of the person (or `rig.json` `"human"` says why none is needed).
- A note checks whether a `rollback` block is declared for transactional restore on hard fail, error, or unattended deferral (`next-batch`).

## What a level does not mean

- A level is not a mark of quality. A level 1 tool with strong tested gates is a finished tool.
- Coverage is not a goal by itself. A gate that needs judgment stays a `model` gate; deliberative work belongs in a `reason` block. The goal is that no gate is a guess **by accident**.
