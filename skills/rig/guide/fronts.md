# Fronts: one tool, several models

A tool has one core and several fronts. The core is the code and the catalogue. A front is the thin part that one kind of user talks to. All fronts call the same command line, so they all read the same knowledge.

```
   Claude            a local model           a person
     │                    │                      │
  skill/SKILL.md     plugin (LM Studio)     the command line,
  (compiled)         (compiled front.json)  the graph page
     │                    │                      │
     └────────────────────┼──────────────────────┘
                          ▼
                 python3 tool.py ...        one JSON line for each call
                          │
              rigkit.py: walks the flow, keeps the run, refuses a wrong call
                          │
               gates.py  steps.py  gen/<name>.json
```

`RIG` is the path of `skills/rig/rig.py`. `python3 RIG build DIR` compiles every front.

## 1. The command line (the driver)

Every tool has `tool.py`. It is the only door to the tool.

| Call | What it does |
|---|---|
| `tool.py run '<inputs as JSON>'` | Start a run. Code walks the flow as far as it can. Options: `--preset NAME`, `--set group.name=value` (for this run only). |
| `tool.py batch '<JSON list>' --report PATH` | Start a run for each item of a list (or of a file). Code runs the list and gives a summary; the report has the failures first. A batch stops after two errors in a row. |
| `tool.py queues` | The runs that did not end, by who must act: `left_for_model`, `waits_for_person`, `errors`. |
| `tool.py answer RUN '<JSON>'` | The model answers the node that the run waits at: `{"pass": true, "why": "..."}` for a gate, `{"result": ...}` for a step. |
| `tool.py approve RUN yes\|no [NOTE]` | A person answers a human gate. |
| `tool.py resume RUN` | Walk on after an error was fixed. |
| `tool.py status RUN` | Show a run again. |
| `tool.py rules` / `tool.py flow` | The values of the rules; the nodes of the flow. |
| `tool.py call TOOL '<JSON>'` | Call a tool unit (level 1). |
| `tool.py regress FILE [--baseline]` | Play the regression set. |

Each call prints one JSON line. The keys to read:

| Key | Meaning |
|---|---|
| `outcome` | The run ended: `end` is the id of the end node. |
| `waiting` | The run needs an answer: `node`, `kind` (`judge`, `step`, `human`), the text of the node, and `sees`: the facts of the run that the node names. `waiting.problems`: what failed after the last answer at this node, so that the next answer can fix it. It is not there at the first visit of a node. |
| `result` | With `outcome`: what the run made (the value of the step that leads to the end). A run that a gate ended has none. |
| `error` | A step failed: `node` and the error text. The run stays at that node. |
| `refused` | The call is not allowed now. It is final. |
| `problems` | Every failed gate so far, as text. A gate in code that ends a loop marks its fail with `"route": true`: that fail is a turn of the flow, and it is not a problem. |
| `guessed` | The gates that the model decided. |
| `path` | The nodes that the run went through. |

Two settings of the runner can be rules of the source: `run.max_visits` (a run that enters one node more often stops: a loop; default 10) and `run.errors_stop` (a batch stops after this many errors in a row; default 2).

## 2. The front for Claude: a skill

`rig.json` names the skill file (`"build": {"skill": "skill/SKILL.md"}`). The build compiles it with the driver, so the skill does not ask Claude to walk the flow. It says: start a run, read the result, answer what waits. Then it shows the rules and the flow as a map.

To use it, put the folder `skill/` where Claude Code looks for skills, under the name of the tool: a link or a copy at `.claude/skills/<name>/` of the project, or of the home folder. The skill says to run the commands in the folder of the tool, so tell Claude where that folder is, or add the path to the project's `CLAUDE.md`.

A large tool needs more than the compiled file: how to set up the host, how to review a batch, how to change a rule. Write these as extra files next to the compiled skill, **one file for each task**, and name them in the README of the tool. An agent that reads six files before it starts has read five too many. Keep the compiled `SKILL.md` as the entry, and never edit it.

## 3. The front for a local model: a plugin

```bash
python3 RIG plugin DIR --owner NAME
```

This adds the folder `plugin/`: an LM Studio plugin. Its code is the same for every tool. Everything about the tool comes from `plugin/src/gen/front.json`, which the build compiles:

- **The tools.** `start_run` (with the inputs of the unit), `answer_gate` (only when the flow has a gate for the model), `finish_step` (only when the flow has a step for the model), `run_status`, `start_batch`, `queues`, and one tool for each tool unit.
- **The rules text.** About ten short numbered lines. The plugin puts it before the first message of a chat.
- **The driver.** The plugin starts it for each call, without a shell.

There is no tool for a human gate. The model can only show the operator what to decide. The operator answers with a chat message that starts with `approve`:

| Message | What it does |
|---|---|
| `approve yes` | Answers the one run that waits for a person: yes. |
| `approve no` | The same, no. |
| `approve yes WORDS` | Yes, with words that the tool reads (for example the choices of a page). |
| `approve RUN yes` | When more than one run waits: names the run. |

The plugin runs such a message before the model sees it (`operatorAnswer` in `src/bridge.ts`), and the model gets only the result. The model cannot do this: it is not a tool, and only a message of the operator goes through this step. A result that waits for a person also has `waiting.command`: the same answer as a command for a terminal, with the tool folder.

Try the plugin without LM Studio:

```bash
node --no-warnings try.ts
```

```bash
node --no-warnings try.ts start_run '{"item": "a longer item"}'
```

`try.ts` uses the same bridge as the plugin, with you in place of the model. Use it to read the exact JSON that the model will see. `node --no-warnings try.ts say "approve yes"` sends a message of the operator.

A live run with the loaded model, without the chat window. Each `--then` is a later message of the operator in the same chat:

```bash
node --no-warnings agent.ts "the task" --then "approve yes"
```

### What a small model needs

A small local model is not a small frontier model. It follows a short list well, and a long text badly.

- **Few tools.** Each tool is one more thing to choose wrongly. The flow tools above are six at most. Do not give the model a tool for each step: the runner does the steps.
- **A short rules text.** One line for each kind of result. The text of each decision arrives with the result (`brief`, `do`), when the model needs it and not before.
- **The result says what to do next.** The model reads `waiting` and acts. It does not plan the flow.
- **Simple words.** Short sentences, one meaning for one word, the condition before the instruction. Write the `intent`, `brief` and `do` texts of the source for the small model; the large model reads them just as well.
- **"Refused" is final.** Say it in the rules text. A small model repeats a failed call until it is told not to.
- **Do not invent.** Say that names and numbers come only from results.
- **One item at a time.** For many items, a loop in code runs them and gives the model a summary ([patterns.md](patterns.md), section 5).
- **Limits on the inputs.** A type and a range in the tool definition stop a wild value before it reaches the code.

Test with the model that will do the work. A text that a large model reads right can still fail with a small one.

## 4. The front for a person

- The command line, as above. A person answers human gates with `approve`.
- The pages: `python3 RIG serve NAME.rig --json gen/NAME.json` shows the source as tables and as a graph. Values can be changed on the page, and Save builds the catalogue again. The wires are read-only: change the flow in the source file, and review it in version control.
- **The path of a run.** The graph page has a list of the runs of the tool (the folder `runs/` next to the source; `--runs DIR` for another). Choose one: the graph lights up the path that the run took. A number on a node is the order of the visit, a red frame is a gate that failed, and a dashed frame is where the run waits. Click a node to read what happened there: pass or fail, the problems, the facts, and who decided.
- The reports and the queues of a production tool ([patterns.md](patterns.md)).

## 5. A tool inside a host application

Some tools must run inside an application (a font editor, a design tool). Then the steps cannot be a plain command line: they run in the application, and the agent reaches them through a bridge of the host, for example an MCP server with a "run this code" call.

Keep the same shape:

- The **gates** stay pure Python. They run anywhere, and their tests need no host.
- The **steps** run in the host. Wrap each one with `rigkit.step`: it prints one JSON line with `ok`, `step` and `result`, and turns an error into a result.
- The **runner** runs where the steps run, or the front walks the flow with one call for each step. In both cases a step returns the verdict of its gates, and the front only reads it.
- The front passes data only. The function names are fixed in the front; the arguments travel as one JSON string.
- Write the host bridge one time, and share it between the tools of that host.

This is the shape of the production agent that the method comes from. It is not yet in the templates: `rig.py new` makes command-line tools. See [docs/status.md](../../../docs/status.md).

## 6. What no front may do

- Hold a limit or a default of its own.
- Decide a gate, or change a verdict.
- Build code from the words of the model.
- Answer a human gate.
- Be edited by hand where it is compiled.
