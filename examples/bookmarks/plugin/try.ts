// Call a tool of the plugin without LM Studio: the same bridge, with you in place of the model.
//   node --no-warnings try.ts                       list the tools and print the rules that the model gets
//   node --no-warnings try.ts TOOL '{"key": ...}'   one call; prints the JSON that the model would read
//   node --no-warnings try.ts say "approve yes"     a message of the operator: an approval answers a human gate
// Needs Node.js 23.6 or newer. Run it in the plugin folder.

import { callTool, closeDriver, front, operatorAnswer } from "./src/bridge.ts";

const [name, json] = process.argv.slice(2);
try {
  if (!name) {
    console.log(front.prompt + "\n");
    for (const t of front.tools) console.log(`${t.name}(${Object.keys(t.parameters.properties).join(", ")}): ${t.description}`);
  } else if (name === "say") {
    console.log((await operatorAnswer(json ?? "")) ?? "not an approval: the model gets this message as it is");
  } else {
    const tool = front.tools.find((t) => t.name === name);
    if (!tool) { console.log(`No tool ${name}. Tools: ${front.tools.map((t) => t.name).join(", ")}`); process.exit(1); }
    console.log(await callTool(tool, json ? JSON.parse(json) : {}));
  }
} finally {
  closeDriver();
}
