// The LM Studio plugin of a Rig tool. The same file for every tool.
//   tools:  from gen/front.json; each call goes to the driver of the tool (bridge.ts); work_run gives
//           the jobs of a run to the loaded model, one by one, without the chat (worker.ts)
//   prompt: the short rules of gen/front.json, before the first user message of a chat

import {
  createConfigSchematics,
  type ChatMessage, type PluginContext, type PromptPreprocessorController, type ToolsProviderController,
} from "@lmstudio/sdk";
import { forModel, front, operatorAnswer, type RunOverrides, type UiRule } from "./bridge.ts";
import { tools } from "./tools.ts";

export const DEFAULT_PRESET = "__default__";

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

function buildChatConfig() {
  const presets = front.presets ?? [];
  const uiRules = front.ui_rules ?? [];
  if (!presets.length && !uiRules.length) return null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let builder: any = createConfigSchematics();
  if (presets.length) {
    builder = builder.field(
      "preset",
      "select",
      {
        displayName: "Preset",
        options: [
          { value: DEFAULT_PRESET, displayName: "Default" },
          ...presets.filter((p) => p && p !== DEFAULT_PRESET).map((p) => ({ value: p, displayName: p })),
        ],
      },
      DEFAULT_PRESET,
    );
  }
  const byGroup = new Map<string, UiRule[]>();
  for (const r of uiRules) {
    const grp = r.group || r.id.split(".")[0];
    let list = byGroup.get(grp);
    if (!list) {
      list = [];
      byGroup.set(grp, list);
    }
    list.push(r);
  }
  for (const [grp, rules] of byGroup.entries()) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    builder = builder.scope(grp, (sub: any) => {
      for (const r of rules) {
        const shortKey = r.id.startsWith(grp + ".") ? r.id.slice(grp.length + 1) : r.id;
        const subtitle = r.note && r.note.length <= 80 ? r.note : undefined;
        if (r.type === "switch") {
          sub = sub.field(shortKey, "boolean", { displayName: r.label, subtitle }, Boolean(r.default));
        } else if (r.type === "choice" && Array.isArray(r.options) && r.options.length > 0) {
          const opts = r.options.map(String).filter((o) => o.length > 0);
          if (opts.length > 0) {
            const def = String(r.default ?? opts[0]);
            sub = sub.field(shortKey, "select", { displayName: r.label, subtitle, options: opts }, opts.includes(def) ? def : opts[0]);
          }
        } else if (r.type === "number") {
          const defNum = Number(r.default ?? 0);
          const isInt = Number.isInteger(defNum) && (r.min === undefined || Number.isInteger(r.min)) && (r.max === undefined || Number.isInteger(r.max));
          const slider = r.ui === "slider" && r.min !== undefined && r.max !== undefined
            ? { min: r.min, max: r.max, step: isInt ? 1 : (r.max > r.min ? (r.max - r.min) / 100 : 1) }
            : undefined;
          sub = sub.field(shortKey, "numeric", { displayName: r.label, subtitle, min: r.min, max: r.max, int: isInt, slider }, defNum);
        } else if (r.type === "list" || r.type === "tuple" || r.type === "dict") {
          sub = sub.field(shortKey, "string", { displayName: r.label, subtitle }, JSON.stringify(r.default));
        } else {
          sub = sub.field(shortKey, "string", { displayName: r.label, subtitle }, String(r.default ?? ""));
        }
      }
      return sub;
    });
  }
  return builder.build();
}

export const chatConfig = buildChatConfig();

export function extractOverrides(cfg: unknown): RunOverrides | undefined {
  if (!cfg || typeof cfg !== "object") return undefined;
  const getter = (cfg as { get?: (key: string) => unknown }).get;
  if (typeof getter !== "function") return undefined;
  const get = (key: string) => getter.call(cfg, key);
  const out: RunOverrides = {};
  if ((front.presets?.length ?? 0) > 0) {
    const p = String(get("preset") ?? DEFAULT_PRESET);
    if (p && p !== DEFAULT_PRESET) out.preset = p;
  }
  const set: Record<string, string> = {};
  for (const r of front.ui_rules ?? []) {
    const cur = get(r.id);
    if (cur === undefined) continue;
    if (r.type === "switch") {
      if (Boolean(cur) !== Boolean(r.default)) set[r.id] = cur ? "true" : "false";
    } else if (r.type === "number") {
      if (Number(cur) !== Number(r.default ?? 0)) set[r.id] = String(cur);
    } else if (r.type === "list" || r.type === "tuple" || r.type === "dict") {
      const defJson = JSON.stringify(r.default);
      if (String(cur) !== defJson) set[r.id] = String(cur);
    } else {
      if (String(cur) !== String(r.default ?? "")) set[r.id] = String(cur);
    }
  }
  if (Object.keys(set).length > 0) out.set = set;
  return out.preset || out.set ? out : undefined;
}

async function provide(ctl: ToolsProviderController) {
  const overrides = chatConfig ? extractOverrides(ctl.getPluginConfig(chatConfig)) : undefined;
  return tools(ctl.getGlobalPluginConfig(globalConfig).get("toolFolder"), undefined, () => ctl.client.llm.model(), overrides);
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
  if (chatConfig) context.withConfigSchematics(chatConfig);
  context.withToolsProvider(provide);
  context.withPromptPreprocessor(preprocess);
}
