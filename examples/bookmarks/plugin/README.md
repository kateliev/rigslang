# bookmarks: the LM Studio front

The plugin gives a local model the tools of `bookmarks`. It has no knowledge of its own: the tools and the rules text come from `src/gen/front.json`, which `rig.py build` compiles from the source of the tool. Each tool call goes to the driver of the tool, the same command line that Claude and a person use.

Do not edit `src/bridge.ts`, `src/index.ts` or `src/gen/`. Change the tool, then build.

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
node --no-warnings try.ts start_run '{"item": "a longer item"}'
```

A live run with the loaded model, without the chat window. Each `--then` is a later message of the operator in the same chat:

```bash
node --no-warnings agent.ts "the task" --then "approve yes"
```

## What the model cannot do

- It cannot answer a `human` gate: there is no tool for that. The operator answers with a chat message that starts with `approve`: `approve yes`, `approve no`, or `approve RUN yes WORDS` when more than one run waits. The plugin runs that message before the model sees it, and the model reads only the result. The command in `waiting.command` does the same in a terminal.
- It cannot decide a gate that code decides: the driver refuses.
- It cannot send code: the bridge passes JSON only, and starts the driver without a shell.
