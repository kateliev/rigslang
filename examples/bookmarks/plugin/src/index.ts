// The LM Studio plugin of a Rig tool. The same file for every tool.
//   tools:  from gen/front.json; each call goes to the driver of the tool (bridge.ts); work_run gives
//           the jobs of a run to the loaded model, one by one, without the chat (worker.ts)
//   prompt: the short rules of gen/front.json, before the first user message of a chat

import {
  createConfigSchematics,
  type ChatMessage, type PluginContext, type PromptPreprocessorController, type ToolsProviderController,
} from "@lmstudio/sdk";
import { forModel, front, operatorAnswer } from "./bridge.ts";
import { tools } from "./tools.ts";

const globalConfig = createConfigSchematics()
  .field(
    "toolFolder",
    "string",
    {
      displayName: "Tool folder",
      subtitle: "The folder that holds rig.json. Leave empty when the plugin runs from inside that folder.",
      placeholder: "automatic",
    },
    "",
  )
  .build();

async function provide(ctl: ToolsProviderController) {
  return tools(ctl.getGlobalPluginConfig(globalConfig).get("toolFolder"), undefined, () => ctl.client.llm.model());
}

// A plugin cannot set the system prompt. So the rules go before the first user message, one time.
// A message of the operator that starts with "approve" answers a human gate as the person: the plugin
// runs it before the model sees the message, and the model gets only the result (bridge.ts, operatorAnswer).
async function preprocess(ctl: PromptPreprocessorController, message: ChatMessage) {
  const answer = await operatorAnswer(message.getText(), ctl.getGlobalPluginConfig(globalConfig).get("toolFolder"));
  const text = answer === null ? message.getText() : forModel(message.getText(), answer);
  if (!front.prompt) return answer === null ? message : text;
  const history = await ctl.pullHistory();
  if (history.getMessagesArray().some((m) => m.getRole() === "user")) return answer === null ? message : text;
  return `${front.prompt}\n\n${text}`;
}

export async function main(context: PluginContext) {
  context.withGlobalConfigSchematics(globalConfig);
  context.withToolsProvider(provide);
  context.withPromptPreprocessor(preprocess);
}
