// The two tools for the model. Everything here comes from the .rig files:
//   the code:        src/gen/search.ts and src/gen/wiki.ts (casts, observed by probes)
//   the definitions: src/gen/*.tool.json (rig.py compile tool)
// This file only connects them.

import { rawFunctionTool, type Tool } from "@lmstudio/sdk";
import searchDef from "./gen/search.tool.json" with { type: "json" };
import wikiDef from "./gen/wiki.tool.json" with { type: "json" };
import { search } from "./gen/search.ts";
import { wiki } from "./gen/wiki.ts";

type Def = { name: string; description: string; parameters: object; returns?: { description?: string } };

function fromDef(def: Def, run: (params: Record<string, unknown>) => Promise<unknown>, log?: (line: string) => void): Tool {
  return rawFunctionTool({
    name: def.name,
    description: def.description + (def.returns?.description ? ". It gives back: " + def.returns.description : ""),
    parametersJsonSchema: def.parameters,
    implementation: async (params) => {
      log?.(`> ${def.name} ${JSON.stringify(params)}`);
      return JSON.stringify(await run(params));
    },
  });
}

export function tools(log?: (line: string) => void): Tool[] {
  return [
    fromDef(searchDef, (p) => search(String(p.query)), log),
    fromDef(wikiDef, (p) => wiki(String(p.url)), log),
  ];
}
