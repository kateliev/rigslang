# Change a tool

Part of the skill `rig`. Read [SKILL.md](SKILL.md) first, and [guide/rules.md](guide/rules.md).

`RIG` means `python3 <this folder>/rig.py`. `DIR` is the folder of the tool (it holds `rig.json`).

Before any change of a level 3 (production) tool, read its `notes/project-facts.md` (the decisions of the person) and its `notes/failures-log.md` (what was tried already).

## A value

| For | Do |
|---|---|
| One run, to try something | `python3 tool.py run '<JSON>' --set group.name=value` (or `--set group.name.key=value` on a `dict` rule, or `--preset NAME`). The source does not change. |
| To keep | Change the value of the `rule` in the `.rig` file, or on the page of `RIG serve FILE --json gen/NAME.json`. Then `RIG build DIR`. |

Say which rule changed and why, with the evidence, and write the reason into the `note` of the rule. Do not change a limit to make one item pass.

## A new number

Never put it in code. Add a `rule` to the source: `rule group.name <value> "label, with the unit"`, then `range <min> <max>` or `options a | b`, and a `note` that says where the value comes from. Read it in code with `R('group.name')`, and name it in text as `{group.name}`. Then build.

## A gate

| Change | Do |
|---|---|
| The decision of a gate in code | Change the function in `gates.py`, and its test. |
| A new gate in code | Add the function and a test that names it. Add the `gate` line where it belongs in the order, with `by gates.<function>` and a `fail -> <end>` line (a `soft` gate has none). |
| A `model` gate becomes code | Write the function and the test, add `by`, change the kind to `hard` or `soft`. Keep the old `check` if it still says what the gate checks. |
| A gate must wait for the person | Change the kind to `human`, write the question as its name, and a `check`: what to show. For a choice from a list, add `options` and a `by` function that reads the answer. |
| A correction round | Add `retry <n>` (or `retry <rule id>`) to the gate that checks. The run goes back to the nearest step before the gate. |

Never put a decision into a step, a skill or a plugin. A step returns facts; a gate decides.

## The flow

Change the order of the lines in the source: the next line is the next node. A new end needs an `end` line and a regression case that reaches it. A loop is a block: `for <item> in <path>` for a list, `until <path>` with `retry <n>` for "again until done", `retry` on a gate for a correction. A node that runs only sometimes gets `if <path>`. Show the person the graph after a change of the order.

A run that started before the change keeps its own copy of the flow (`runs/RUN/flow.json`), so it goes on as it began. To try the new flow on an old run: `python3 tool.py rerun RUN --from <line>`, or `python3 RIG test DIR --replay RUN`.

## The code of a step

Change `steps.py` and its test. A step that changes something keeps a way back ([guide/patterns.md](guide/patterns.md), sections 1 and 2).

## After every change

All must pass:

```bash
python3 RIG build DIR
```

```bash
python3 RIG doctor DIR
```

```bash
python3 tool.py regress tests/regression-set.json
```

- `doctor` runs the tests and the regression set too; run `regress` alone to read the differences.
- A regression case that changes its result **and the change is wanted**: look at the new path, then `python3 tool.py regress tests/regression-set.json --baseline`, and name the changed cases in the commit message.
- A case that changes and the change is **not** wanted: stop and report.
- The plugin, when the tool has one: `node --no-warnings try.ts` in `plugin/` shows the tools and the rules text that the model gets. Read them after a change of an `intent`, a `check` or a `do`.
- A front that is not compiled (extra skill files, a guide in prose): the README of the tool lists them under "after a change, also update".

Then write down what you learned: [guide/rules.md](guide/rules.md), rule 18.

## Raise the level

Change `"level"` in `rig.json`, run `RIG doctor DIR`, and add what it lists as `MISS`. For level 3, also go through the check list at the end of [guide/patterns.md](guide/patterns.md).
