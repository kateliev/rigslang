// The LM Studio plugin. It gives the model the two tools and the agent.
//   tools: search (search.rig) and wiki (wiki.rig)
//   agent: the skill compiled from bandsearch.rig

import { type ChatMessage, type PluginContext, type PromptPreprocessorController } from "@lmstudio/sdk";
import { skill } from "./gen/skill.ts";
import { tools } from "./tools.ts";

const MARK = "# bandsearch";

// A preprocessor cannot set the system prompt. So the agent goes before the
// first user message of a chat, one time only.
async function preprocess(ctl: PromptPreprocessorController, message: ChatMessage) {
  const history = await ctl.pullHistory();
  if (history.getMessagesArray().some((m) => m.getText().includes(MARK))) return message;
  return `${skill}\n\n## The band\n\n${message.getText()}`;
}

export async function main(context: PluginContext) {
  context.withToolsProvider(async () => tools());
  context.withPromptPreprocessor(preprocess);
}
