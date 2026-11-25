// The worker from a terminal: the jobs of one run go to the loaded model, one by one, without a chat.
//   node --no-warnings work.ts RUN
// LM Studio must run, with a model loaded. Each job is one call in a new context, with the answer
// bound to the "out" type of the step (src/worker.ts). It stops where a person or a judgment is needed.
// The progress goes to stderr; the last result of the tool goes to stdout.

import { LMStudioClient } from "@lmstudio/sdk";
import { work } from "./src/worker.ts";

const run = process.argv[2];
if (!run) { console.log("Give the run id: node --no-warnings work.ts RUN"); process.exit(1); }
const model = await new LMStudioClient().llm.model();
console.log(await work(model, run, undefined, (text) => console.error(text)));
