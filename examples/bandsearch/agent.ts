// Run the agent without the LM Studio chat window: the loaded model, the
// compiled skill and the two tools, the same parts that the plugin gives.
//   node agent.ts "Pink Floyd"
// LM Studio must run, with a model loaded that can call tools.

import { Chat, LMStudioClient } from "@lmstudio/sdk";
import { skill } from "./src/gen/skill.ts";
import { tools } from "./src/tools.ts";

const band = process.argv[2] ?? "Pink Floyd";
const model = await new LMStudioClient().llm.model();
const chat = Chat.from([{ role: "user", content: `${skill}\n\n## The band\n\n${band}` }]);
await model.act(chat, tools((line) => console.error(line)), {
  onMessage: (m) => {
    if (m.getRole() === "assistant" && m.getText().trim()) console.log(m.getText());
  },
});
