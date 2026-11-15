// A live run of the front without the LM Studio chat window: the loaded model, the rules
// text and the tools, the same parts that the plugin gives.
//   node --no-warnings agent.ts "the task, as the operator would type it"
// LM Studio must run (lms server start), with a model loaded that can call tools.
// The tool calls and their results go to stderr; the words of the model go to stdout.

import { Chat, LMStudioClient } from "@lmstudio/sdk";
import { front } from "./src/bridge.ts";
import { tools } from "./src/tools.ts";

const task = process.argv.slice(2).join(" ");
if (!task) { console.log('Give the task: node --no-warnings agent.ts "..."'); process.exit(1); }
const model = await new LMStudioClient().llm.model();
const chat = Chat.from([{ role: "user", content: front.prompt ? `${front.prompt}\n\n${task}` : task }]);
await model.act(chat, tools(undefined, (line) => console.error(line)), {
  onMessage: (m) => {
    if (m.getRole() === "assistant" && m.getText().trim()) console.log(m.getText());
  },
});
