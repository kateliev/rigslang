// The tools of the plugin as LM Studio tools. The same file for every tool.
// Used by the plugin (index.ts) and by a live run without the chat window (agent.ts).

import { rawFunctionTool, type Tool } from "@lmstudio/sdk";
import { callTool, front } from "./bridge.ts";

export function tools(root?: string, log?: (line: string) => void): Tool[] {
  return front.tools.map((t) =>
    rawFunctionTool({
      name: t.name,
      description: t.description,
      parametersJsonSchema: t.parameters,
      implementation: async (params) => {
        log?.(`> ${t.name} ${JSON.stringify(params)}`);
        const answer = await callTool(t, params as Record<string, unknown>, root);
        log?.(`< ${answer}`);
        return answer;
      },
    }),
  );
}
