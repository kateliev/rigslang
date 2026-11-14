# __NAME__: the LM Studio front

The plugin gives a local model the tools of `__NAME__`. It has no knowledge of its own: the tools and the rules text come from `src/gen/front.json`, which `rig.py build` compiles from the source of the tool. Each tool call goes to the driver of the tool, the same command line that Claude and a person use.

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

## What the model cannot do

- It cannot answer a `human` gate: there is no tool for that. The operator answers on the command line of the tool (`approve RUN yes|no`).
- It cannot decide a gate that code decides: the driver refuses.
- It cannot send code: the bridge passes JSON only, and starts the driver without a shell.
