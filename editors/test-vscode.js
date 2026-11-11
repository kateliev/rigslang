// Run the Sublime-format syntax test against the VS Code grammar.
// Setup, once: cd editors && npm install --no-save vscode-textmate vscode-oniguruma
// Run: node editors/test-vscode.js
// Embedded languages are stubs: the test checks only the Rig scopes.
const fs = require('fs'), path = require('path');
const vsctm = require('vscode-textmate'), onig = require('vscode-oniguruma');
const grammarPath = path.join(__dirname, 'vscode/syntaxes/rig.tmLanguage.json');
const testPath = path.join(__dirname, 'sublime/syntax_test_rig.rig');
const wasm = fs.readFileSync(require.resolve('vscode-oniguruma/release/onig.wasm')).buffer;
const lib = onig.loadWASM(wasm).then(() => ({ createOnigScanner: p => new onig.OnigScanner(p), createOnigString: s => new onig.OnigString(s) }));
const stub = s => ({ scopeName: s, patterns: [{ match: '(def|return|function)', name: 'keyword.stub' }] });
const reg = new vsctm.Registry({ onigLib: lib, loadGrammar: async s =>
  s === 'source.rig' ? vsctm.parseRawGrammar(fs.readFileSync(grammarPath, 'utf8'), grammarPath) : stub(s) });
const has = (scopes, sel) => scopes.some(sc => sc === sel || sc.startsWith(sel + '.'));
reg.loadGrammar('source.rig').then(g => {
  const lines = fs.readFileSync(testPath, 'utf8').split('\n');
  let stack = vsctm.INITIAL, last = null, fails = 0, checks = 0;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const r = g.tokenizeLine(line, stack); stack = r.ruleStack;
    const m = /^;( *)(<-|\^+) (- )?(\S+)/.exec(line);
    if (i > 0 && m) {
      const col = m[2] === '<-' ? 0 : m[1].length + 1, len = m[2] === '<-' ? 1 : m[2].length;
      for (let c = col; c < col + len; c++) {
        const t = last.tokens.find(t => t.startIndex <= c && c < t.endIndex);
        const ok = t && (m[3] ? !has(t.scopes, m[4]) : has(t.scopes, m[4]));
        checks++;
        if (!ok) { fails++; console.log(`line ${last.n + 1} col ${c}: want ${m[3] || ''}${m[4]} got ${t ? t.scopes.join(' ') : 'none'}\n  ${last.text}`); break; }
      }
    } else last = { n: i, text: line, tokens: r.tokens };
  }
  console.log(`${checks} column checks, ${fails} failed assertions`);
  process.exit(fails ? 1 : 0);
});
