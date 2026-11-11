// Prints what the viewer computes for each .rig file: unit, matrix hash, body hashes, error lines.
// Used by test_rig.py to compare the viewer with rig.py. Run: node tests/parity.js FILE...
const fs = require("fs"), path = require("path");
const html = fs.readFileSync(path.join(__dirname, "..", "viewer", "index.html"), "utf8");
const js = html.slice(html.indexOf("<script>") + 8, html.indexOf("// - State"));
const out = [];
new Function("out", "files", "fs", js + `
for (const f of files) {
  const root = parse(fs.readFileSync(f, "utf8"));
  for (const u of units(root)) out.push([word(u, 0), h8(matrixText(u)), kids(u, "cast").map(c => h8(bodyText(c.body)))]);
  out.push(["errors", check(root).err.map(e => e[0])]);
}`)(out, process.argv.slice(2), fs);
console.log(JSON.stringify(out));
