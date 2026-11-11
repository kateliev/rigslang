# Sidenote: agent configuration as a graph

Started 2026-11-11. Status: discussion and ideas. Not a plan.

Origin: a private production agent that runs a repeated procedure with real thresholds. Its gates and rules were moved into one catalogue file and shown as a node graph, in the style of visual shader programming. This note keeps only the generic ideas. It contains no material from that project.

Add new thoughts at the end (Section 7). Do not delete old ones: mark them as changed or rejected, with the reason.

## 1. The question

A rules page, and a graph even more, start to look like a visual way to program the behavior of an agent. The user connects parts of the graph that stand for logical gates. Together, the parts make the context description that the agent follows.

- How usable is this?
- Can it be more universal, a way to configure other agents too?
- Is it better or worse for the agent, and for what the model is good at?
- The UI makes things more complicated. But it also limits the ways to define gates and logic. Is that limit good?

## 2. Three layers

| Layer | What it is |
|---|---|
| Rules | Typed values with limits (number, range, per variant, switch, choice, text) |
| Gates | A closed list of checkpoints: trigger, action, leads to, on fail, the rules each one reads |
| Verdicts | The code that decides pass or fail |

A graph can show layers 1 and 2. It can edit values. It should not change the wiring. This split is correct.

Why: a shader graph works because every node is executable code with exact types. An agent "gate" is half code and half prose. "The boxes look plausible" or "the part has the wrong shape" is partly a judgment of the model. If a user can rewire prose nodes freely, the graph looks more exact than the agent is.

## 3. Better or worse for the agent

### Better

- The values and the branch points are explicit and typed. A gate has a verdict function or it does not.
- "Gate 13 fails → gate 14" is a fact the model cannot drift from. A paragraph in a guide is easier to read loosely.
- One source for the numbers. In the origin project, an audit found numbers copied into the guide, the skill and a plugin. A single catalogue removes that risk.
- Limits help a model the same way they help a junior engineer: fewer ways to be creatively wrong.

### Worse

- Most of the value of a model is between the gates: choosing an input, seeing that a correction looks wrong, noticing a case the catalogue did not expect.
- A graph cannot hold "prefer the even option, else continue and report" better than a sentence. It only puts the sentence in a box.
- If the graph is the complete specification, the agent becomes one of two things:
  - a slow and expensive script, or
  - an agent that meets a case with no node and has no permitted move.
- The prose guide, the examples, the quality bar and the progress log hold knowledge that the graph cannot hold.

## 4. The proposed shape

- **Graph** for control flow and limits: where the agent can be, what it can do next, which numbers apply.
- **Prose** for judgment: each node carries a short brief for the decision inside it.
- **Code** for verdicts: every gate that can be code is code. The model reports facts; the code decides.

This is the same direction as the robust agent frameworks: a state machine or graph for orchestration, a model inside the nodes.

### Rule for the editor

- Values: free to edit in the graph.
- Topology (new gate, new wire): edit only in the source file, and review it in version control.
- If the graph can rewire one day, every new wire must point to a verdict function that exists. The checker must refuse a wire without one. Otherwise the result is a good-looking diagram that the agent ignores.

## 5. Can it be universal?

Possibly. A generic schema is small:

- Gate: `id, kind, name, trigger, action, leads_to[], on_fail[], rules[]`, plus a reference to the verdict code.
- Rule: `id, group, label, type, value, default, min, max, options, unit, note, evidence`.
- Presets: named sets of rule values.

### Generic parts

1. The node and rule schema, and its validator: every gate has code, every rule is used, every `{rule}` placeholder exists, every link points to a gate or an outcome.
2. The graph view and the table view.
3. A **compile** step: render the graph into the context of the agent: the skill, the guide, the typed fallbacks of each runtime. Without it, these are kept in step by hand.
4. Optional: a trace view. Run the agent and light up the path that one item took through the gates, with the measured values at each gate.

### Domain parts (stay per project)

- The verdict functions.
- The domain types.
- The prose briefs and the quality bar.

### Where it pays off

- Agents that repeat a procedure with real thresholds: a production pipeline, a QA pipeline, a release checklist, a review against a fixed rule set.
- Not open-ended agents ("help me design this"). There, a graph is overhead and forces a structure that is not there.

## 6. Ideas for this repository

- **Graph → context compiler.** One source file, and from it the skill text, the guide sections and typed fallbacks for each runtime.
- **Gate coverage.** Mark each gate as `code`, `model`, or `mixed`. Show the share of the flow that the model decides. Aim to move gates from `model` to `code` over time. (In Rig: `hard` / `soft` against `judge`.)
- **Trace replay.** Log each run as a path through the graph with values. Replay it on the graph. Compare runs before and after a rule change.
- **Rule evidence.** Each rule has an `evidence` link (a note, a test, a report). The graph shows rules without evidence.
- **Presets as diff layers.** Show what a preset changes as a highlighted layer on the graph.
- **Limits as a feature.** A closed list of node kinds (gate, step, end, rule) is easier for a model to read correctly than free prose. Measure this: same task, prose-only context against graph-compiled context.

## 7. Log

- 2026-11-11: gate graph made in the origin project. Wiring read-only, values editable. This note written from the discussion that followed.
- 2026-11-11: the generic part of this note moved to the Rig repository, with all project material removed. The research that followed is in [findings-2026-11-11.md](findings-2026-11-11.md). The language that came out of it is described in [logic.md](logic.md).
