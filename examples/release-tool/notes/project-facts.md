# Project facts: release

What is true about this project. An agent reads this file before it works, on any computer.

## What the tool does

It checks a release folder (`NOTES.md`, `VERSION`, `tests.json`) and writes `published.json` into it. It is the reference example of the RIGS kit: small, but with every part of a level 4 tool.

## Decisions of the owner

- 2026-11-15: the tool never publishes by default. The rule `permissions.publish` is off; a run then ends at `ready` and changes nothing.
- 2026-11-15: a person agrees before every publish (gate `approve`). The model cannot answer this gate.
- 2026-11-15: failed tests stop the run only while `tests.required` is on. With the rule off, the failure is reported and the run goes on.

## Words

| Word | Meaning |
|---|---|
| release folder | The folder that the run works on. It is the only place the tool writes. |
| dry run | A run with `permissions.publish` off. |
| rewrite | The notes written again by the model, after the gate `tone` failed. At most `notes.rounds` times. |
