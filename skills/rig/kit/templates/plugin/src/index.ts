// The LM Studio plugin of a Rig tool. The same file for every tool.
//   tools:  from gen/front.json; each call goes to the driver of the tool (bridge.ts)
//   prompt: the short rules of gen/front.json, before the first user message of a chat

import {
  createConfigSchematics,
  type ChatMessage, type PluginContext, type PromptPreprocessorController, type ToolsProviderController,
} from "@lmstudio/sdk";
import { front } from "./bridge.ts";
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
  return tools(ctl.getGlobalPluginConfig(globalConfig).get("toolFolder"));
}

// A plugin cannot set the system prompt. So the rules go before the first user message, one time.
async function preprocess(ctl: PromptPreprocessorController, message: ChatMessage) {
  if (!front.prompt) return message;
  const history = await ctl.pullHistory();
  if (history.getMessagesArray().some((m) => m.getRole() === "user")) return message;
  return `${front.prompt}\n\n${message.getText()}`;
}

export async function main(context: PluginContext) {
  context.withGlobalConfigSchematics(globalConfig);
  context.withToolsProvider(provide);
  context.withPromptPreprocessor(preprocess);
}
