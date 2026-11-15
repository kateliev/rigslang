# band-facts: a second example, built with the kit

For a band name, the tool writes one paragraph about the band and lists its albums. The facts come from English Wikipedia, through its public API.

It is a level 3 tool (flow), made with `rig.py new` and the build order of the guide. It is the earlier example [bandsearch](../bandsearch/) built again, and the differences show what the kit is for.

| | bandsearch (before) | band-facts (with the kit) |
|---|---|---|
| Who walks the flow | the model, from a skill text | the runner; the model answers three nodes |
| Find and read the article | the model calls two tools | code (`steps.find`, `steps.read`); no model |
| The word limit | a sentence in a step; the model wrote 142 words for a limit of 120 | the gate `short` in code; a long paragraph goes back to the model |
| The list of albums | the model writes it | code (`steps.compose`) |
| What the model sees | everything, all the time | for each node, only the facts that the node names (`sees`) |
| Tests | proofs of three snippets; no test of the flow | gates, steps, and 12 regression cases that play the model, with no network |

## Who decides what

| Node | Kind | Who |
|---|---|---|
| `article`, `summary`, `title`, `short`, `rounds` | hard gate | code |
| `albums` | soft gate | code; no albums is reported, and the run goes on |
| `is-band`, `grounded` | judge gate | the model; a guess |
| `write` | step | the model |
| `find`, `read`, `compose` | step | code |

## Try it

It needs Python 3 and the network.

```bash
python3 tool.py run '{"band": "Pink Floyd"}'
```

The run waits at `is-band`, with the title, the description and the summary of the article in `sees`. Answer with the run id of the result:

```bash
python3 tool.py answer RUN '{"pass": true}'
```

Then the run waits at the step `write`. Give a paragraph:

```bash
python3 tool.py answer RUN '{"result": "Pink Floyd are an English rock band founded in 1965."}'
```

After the gate `grounded`, the run ends at `done`, and `result` holds the answer: the paragraph, the albums and the URL.

Many bands in one call:

```bash
python3 tool.py batch '[{"band": "Pink Floyd"}, {"band": "Motörhead"}]' --report reports/first.md
```

## Check it

```bash
python3 ../../skills/rig/rig.py doctor .
```

```bash
python3 tool.py regress tests/regression-set.json
```

The tests and the regression set use the pages of `tests/fixtures` (a band that does not exist), not the network.

## What the first runs taught

This is stage 8 of the build order, on a small scale.

- **The search page of a web search engine is not an API.** The first form of `find` read such a page, as bandsearch did. The service answered with a check for robots, and the step got no results. The step now uses the search API of Wikipedia. The gate `article` also tells "the service did not answer" from "no article", and each has its own end.
- **The first result is not the article.** A live run for a famous band gave "List of ... band members" first. `parse.pick_title` now prefers the title that is the name of the band, then "name (band)", then the first result. The judge gate `is-band` stays as the check behind it.
- **A model that judges needs the facts.** The first form gave the model only the text of the gate. The language got the word `sees` for this: a node names the parts of the state that go with the question.

## Runs with real models (2026-11-15)

Two models used the tool, each through its own front and with no other help.

| Model | Front | Task | What happened |
|---|---|---|---|
| Claude Haiku | the compiled skill | three bands | 7 commands, none refused. Two bands answered, with the `Guessed:` line. It failed the gate `is-band` for a page of meanings, as it should. |
| Qwen, 35B, local in LM Studio | the plugin tools and rules text (`plugin/agent.ts`) | one band | 4 tool calls, all valid, 43 seconds. |
| the same | the same | four bands, two of them traps | It chose `start_batch` by itself; 14 tool calls, all valid, 82 seconds. It failed `is-band` for both traps. |

No call was refused and no call was wrong. The paragraphs had 63 to 106 words, so the gate `short` did not have to send one back; the tests and the regression set show that it does.

What these runs changed:

- **A name that is no band got the article of a politician.** A full-text search gives a result for any words. The judge gate saw it, but that is a guess doing the work of a fact. The gate `title` in code now ends such a run: the article must have the name of the band.
- **A name with many meanings got the page that lists them.** `steps.read` now goes past such a page to the article "name (band)".
- **A run that a gate ended carried the data of its last step as its "result".** Now only a run whose end follows a step has a result.
- After these changes the local model needed 6 calls for three names, not 14: the two traps ended in code, with no model call.
- The skill text now says "more than one item" where it said "many items", and says to write the `Guessed:` line for a run that ended early too. The first model had asked about both.

## Limits

- Some large bands keep only a link to a separate discography article. Then the album list is empty, and the gate `albums` reports it.
- `is-band` and `grounded` are guesses of the model. The answer names them in its `guessed` list.
- The runs with models were few, and on famous bands. A long batch with a small model is not tested yet.
