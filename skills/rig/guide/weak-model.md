# Design for the weaker model

A Rig tool has two kinds of driver. Claude builds the tool: it runs it first, finds where it breaks, and makes the path smooth. Then a local model drives the tool through the plugin, many times. The two fronts read the same source and stay in step. **Design every job of the model for the weaker of the two.** What a small local model does well, Claude does well too. The other way round is not true.

## 1. Who does what

| Code does | The model does |
|---|---|
| Search: find the few candidates in a long list | Judge: pick one of the few candidates |
| Bookkeeping: batches, ids, the order of the work, the state of the run | Knowledge: what a page is about, what a name means |
| Every text that must be exact: ids, commands, the messages for the person | Language: a short text, a summary, a name |
| Every check: the form of the answer, the ids, the limits | Nothing that code can check |

The model is for what code cannot do: a judgment that needs knowledge of the world or of language. "Gumroad is a shop for digital goods" is such a judgment; no rule in Python knows it. Everything around that judgment is code, also when the model could do it.

## 2. The shape of a job

A step of the model is a **job**. Give each job this shape:

1. **Small.** One item, or one batch of short items (the bookmarks tool: 30 bookmarks).
2. **Closed.** The model chooses among candidates that code found: "pick 1 to 5", not "find the best of 227". Code builds the candidates before the loop, one time for all items (a "prefetch").
3. **Without history.** A new, empty context for each job. The worker of the plugin does this ([fronts.md](fronts.md), section 3). A long chat makes each answer slower and less sure.
4. **Bound to a form.** The step has an `out` type. The answer must have that form, and the runner refuses another.
5. **Checked.** A hard gate after the step checks every answer, with `retry` and then `fail -> continue`. A bad answer costs one retry, not the run.
6. **Limited.** A cap on the tokens of one job. A model that repeats itself stops at the cap, and the gate retries.

## 3. What a small model does wrong

These come from real runs of the bookmarks tool with a local 35B model with about 3B active parameters (2026-11-25):

| Do not ask the model to | What happened |
|---|---|
| Search a long list | With 227 folders it read the list line by line for each bookmark, then repeated the same lines: about 57,000 characters of thinking, and no answer. |
| Copy a long exact string | With thinking off, it copied the run id `20261125-120008-01` as `20261125-1125-1125-…` without end. |
| Carry a long chat | Each batch made the chat about 10,000 tokens longer, and each answer slower: about 1.5 minutes for a batch of 30. |
| Choose when one answer is safe | The present folder was choice 1. Without thinking, the model picked 1 for every bookmark of four batches. |
| Reason in a field of the answer | A `why` or `topic` field before the pick did not help: the model copied the title into it. |

The fixes were all in code: candidates from code, the present folder at its place by score (no safe first place), the jobs out of the chat, and the answer bound to a schema.

## 4. Thinking: measure, do not assume

A model that thinks first is slower. Do not assume that it is better: measure it on real items.

The bookmarks tool, the same 8 batches of 30, on a real export:

| Mode | Time for all batches | Agreement |
|---|---|---|
| Chat, thinking on | about 13 minutes | (the reference) |
| Worker, thinking off, answer bound to the schema | 137 seconds; each batch passed the gate at the first answer | 92 of 120 decisions as in the reference |
| Worker, thinking on, new context | 2.5 to 3 minutes for each batch | 41 of 60 decisions as in the reference |

Two runs with thinking agreed less with each other than the fast run agreed with the first one. For this job, many items are close calls, and thinking bought time, not certainty. So the tool uses the fast mode, and the person checks the result in the dry-run report.

Measure your own job the same way: the same items, two modes, the number of decisions that agree, and the time. A job where thinking really changes the result keeps it (`"think": true` in `rig.json`), with a cap on the tokens.

## 5. Caution

- **Expect little.** Give the model the smallest decision that only it can make. When code can do a part, code does it.
- **No safe default in a list.** Do not put the "keep it" answer first, and do not mark it as better than the others.
- **No long strings to copy.** Code writes ids and commands into the texts that the person reads.
- **A judgment that matters goes to the person.** The model proposes; a `human` gate or a report lets the person see and refuse it.
- **An item that the model cannot do** goes to an end "left for a larger model or a person", not to a guess ([build-order.md](build-order.md), stage 9).

## 6. Check list for a job of the model

- [ ] The model chooses among candidates that code found. It does not search.
- [ ] Code made the candidates before the loop, one time.
- [ ] No answer is a safe default at the first place.
- [ ] The step has an `out` type, and a hard gate checks each answer, with `retry` and `fail -> continue`.
- [ ] The job runs in the worker (a new context each time), not in the chat.
- [ ] The model copies no long id or command.
- [ ] Thinking on or off was chosen with a measurement on real items, and the numbers are in `notes/project-facts.md`.
