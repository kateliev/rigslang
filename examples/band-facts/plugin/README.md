# band-facts: the LM Studio front

The plugin gives a local model the tools of `band-facts`. It has no knowledge of its own: the tools and the rules text come from `src/gen/front.json`, which `rig.py build` compiles from the source of the tool. Each tool call goes to the driver of the tool over a warm `serve-stdio` child process (restarting or falling back to a one-shot call if needed), using the same command line that Claude, MCP hosts and a person use.

Do not edit this README, `src/bridge.ts`, `src/index.ts`, `src/tools.ts`, `src/worker.ts` or `src/gen/`: `rig.py build` writes them. Change the tool, then build.

## Set up

You need Node.js 23.6 or newer, Python 3, and LM Studio with a model that can call tools.

```bash
npm install
```

```bash
lms dev
```

Then open a new chat in LM Studio and turn on the plugin. When the plugin is installed (`lms dev --install`), it no longer runs inside the tool folder: set **Tool folder** in the plugin settings to the folder that holds `rig.json`.

## Try it without LM Studio

```bash
node --no-warnings try.ts
```

```bash
node --no-warnings try.ts start_run '{"band": "The Paper Lanterns"}'
```

A live run with the loaded model, without the chat window. Each `--then` is a later message of the operator in the same chat:

```bash
node --no-warnings agent.ts "the task" --then "approve yes"
```

## The worker

Every `by model` step has an `out` type and is a job for the worker, not for the chat. When a result has `waiting.next_action` with `"call": "work_run"`, the model calls `work_run` one time. The worker gives each job to the loaded model in a new context, passes failure causes and metrics (`--meta`) to the driver, and goes on until the run needs the operator or ends (`src/worker.ts`). The same from a terminal:

```bash
node --no-warnings work.ts RUN
```

Its settings are in `rig.json` of the tool: `"plugin": {"work": {"think": false, "max_tokens": 4000, "max_calls": 50}}`.

## What the model cannot do

- It cannot answer a `human` gate: there is no tool for that, and `waiting.next_action` says `"call": "NONE"`. The operator answers with a chat message that starts with `approve`, as the `say` text of the result gives it: `approve r1 yes`, `approve r1 no`, or, at a gate with options, `approve r1` and the words of the answer (`approve r1 yes` takes the first option). The short form without the run id (`approve yes`) works when one run waits for a person, or when this chat session has an active waiting run; else the plugin refuses it and names the waiting runs. The plugin runs that message before the model sees it, and the model reads only the result. The command in `waiting.command` does the same in a terminal.
- It cannot decide a gate that code decides: the driver refuses.
- It cannot send code: the bridge passes JSON only, and starts the driver without a shell.
