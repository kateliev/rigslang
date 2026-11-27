// The tools of the plugin as LM Studio tools. The same file for every tool.
// Used by the plugin (index.ts) and by a live run without the chat window (agent.ts).
// The tool of kind "work" gives the jobs of a run to the model, one by one (worker.ts): it needs the model.

import { rawFunctionTool, type LLM, type Tool } from "@lmstudio/sdk";
import { callTool, front, type RunOverrides } from "./bridge.ts";
import { work } from "./worker.ts";

export function tools(root?: string, log?: (line: string) => void, model?: () => Promise<LLM>, overrides?: RunOverrides): Tool[] {
  return front.tools.filter((t) => t.kind !== "work" || model).map((t) =>
    rawFunctionTool({
      name: t.name,
      description: t.description,
      parametersJsonSchema: t.parameters,
      implementation: async (params, ctx) => {
        log?.(`> ${t.name} ${JSON.stringify(params)}`);
        const p = params as Record<string, unknown>;
        const answer = t.kind === "work" && model
          ? await work(await model(), String(p.run ?? ""), root, (text) => { ctx.status(text); log?.(`  ${text}`); })
          : await callTool(t, p, root, overrides);
        log?.(`< ${answer}`);
        return answer;
      },
    }),
  );
}
