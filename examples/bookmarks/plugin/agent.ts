// A live run of the front without the LM Studio chat window: the loaded model, the rules
// text and the tools, the same parts that the plugin gives.
//   node --no-warnings agent.ts "the task, as the operator would type it"
//   node --no-warnings agent.ts "the task" --then "approve yes" --then "approve no"
// Each --then is a later message of the operator in the same chat. It goes through the same
// step as in the plugin: a message that starts with "approve" answers a human gate as the person.
// LM Studio must run (lms server start), with a model loaded that can call tools.
// The tool calls and their results go to stderr; the words of the model go to stdout.

import { Chat, LMStudioClient } from "@lmstudio/sdk";
import { forModel, front, operatorAnswer } from "./src/bridge.ts";
import { tools } from "./src/tools.ts";

const turns: string[] = [];
let words: string[] = [];
for (const a of process.argv.slice(2)) {
  if (a === "--then") { turns.push(words.join(" ")); words = []; } else words.push(a);
}
turns.push(words.join(" "));
if (!turns[0]) { console.log('Give the task: node --no-warnings agent.ts "..." [--then "..."]...'); process.exit(1); }

const model = await new LMStudioClient().llm.model();
const chat = Chat.empty();
const log = (line: string) => console.error(line);
for (const [i, turn] of turns.entries()) {
  const answer = await operatorAnswer(turn);
  if (answer !== null) log(`= operator: ${turn}\n< ${answer}`);
  const text = answer === null ? turn : forModel(turn, answer);
  chat.append("user", i === 0 && front.prompt ? `${front.prompt}\n\n${text}` : text);
  if (i > 0) console.log(`\n--- operator: ${turn}\n`);
  await model.act(chat, tools(undefined, log, async () => model), {
    onMessage: (m) => {
      chat.append(m);
      if (m.getRole() === "assistant" && m.getText().trim()) console.log(m.getText());
    },
  });
}
