# bandsearch: an LM Studio plugin built from Rig

For a band name, the plugin writes one paragraph about the band and lists its albums. The facts come from English Wikipedia. A DuckDuckGo search finds the article.

The `.rig` files are the only source. All code and all definitions in `src/gen/` come from them.

| File | What it is |
|---|---|
| [bandsearch.rig](bandsearch.rig) | The agent: the steps and gates that the model follows. |
| [search.rig](search.rig) | The search tool (observed by a probe) and the snippet `ddg-results` (proved). |
| [wiki.rig](wiki.rig) | The wiki tool (observed by probes) and the snippets `wiki-title` and `album-list` (proved). |
| [build.py](build.py) | Makes `src/gen/` with `rig.py emit` and `rig.py compile`. |
| [src/tools.ts](src/tools.ts) | Connects the emitted code with the compiled tool definitions. |
| [src/index.ts](src/index.ts) | The plugin: the tools, and the agent skill before the first user message. |
| [agent.ts](agent.ts) | A live run of the agent with the loaded model, without the chat window. |

## How the parts connect

| Part | Status | How |
|---|---|---|
| `ddg-results`, `wiki-title`, `album-list` | proved | `rig.py prove --stamp`: the examples run in Node.js |
| `search`, `wiki` | observed | `rig.py probe --stamp`: live runs against DuckDuckGo and Wikipedia |
| tool definitions | compiled | `rig.py compile tool`: the intent, and the JSON Schema of the `in` lines |
| the agent | compiled | `rig.py compile skill`: the flow, the rules, and a Report section |

`rig.py emit` writes only proved and observed casts. If a `.rig` file changes and a cast is not proved or probed again, the build stops.

A plugin cannot set the system prompt. So the plugin puts the skill before the first user message of a chat.

## Use it

You need Node.js 23.6 or newer, Python 3 and LM Studio with a model that can call tools.

```bash
npm install
```

```bash
python3 build.py
```

```bash
lms dev
```

Then open a new chat in LM Studio, turn on the plugin and type a band name.

To change the plugin, change a `.rig` file. Then prove or probe the changed unit again, and build:

```bash
python3 ../../skills/rig/rig.py prove wiki.rig --stamp
```

```bash
python3 ../../skills/rig/rig.py probe wiki.rig --stamp
```

```bash
python3 build.py
```

Other checks:

```bash
python3 ../../skills/rig/rig.py check bandsearch.rig search.rig wiki.rig
```

```bash
node agent.ts "Pink Floyd"
```

```bash
npx tsc --noEmit
```

## Limits

- The DuckDuckGo results page is not a public API. If its markup changes, the proofs still pass, but the probe of `search` fails. Run the probes before a release.
- Some large bands keep only a link to a separate discography article. Then the album list is empty.
- The gates `is-band` and `grounded` are `judge` gates. Their results are guesses, and the answer names them in a `Guessed:` line. In a test run, `grounded` passed a sentence that the summary did not support.
- The word limit of the paragraph is only in the text of the `write` step. No gate checks it, and in a test run the model wrote 142 words for a limit of 120.
