'''Build the RIGS (.rig) syntax grammars for VS Code and Sublime Text from one table.

  python editors/build.py           write both grammar files
  python editors/build.py --check   exit 1 if a grammar file is not current

Edit this file, not the generated grammars. Keep the words in step with skills/rig/spec.md.
'''

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VSCODE = os.path.join(HERE, 'vscode', 'syntaxes', 'rig.tmLanguage.json')
SUBLIME = os.path.join(HERE, 'sublime', 'Rig.sublime-syntax')

# - Regex parts (Oniguruma & Python re; both editors read the same patterns)
W = r'[^\s()\[\]{},:?";][^\s()\[\]{},:?;]*'  # a word that can be a name
E = r'(?=[\s;]|$)'                           # the end of a head word
B = r'(?<![^\s(\[{,:])'                      # the start of an argument or collection item
A = r'(?=[\s()\[\]{},:?;]|$)'                # the end of an argument or collection item
PH = r'\{[A-Za-z_][\w-]*(?:\.[\w-]+)+\}'     # a rule named in a string: {group.name} or {group.name.key}
RULE_ID = r'[A-Za-z_][\w-]*\.[\w.-]+'        # a dotted rule reference (e.g. limits.retries)

# Zero-width boundary that ends a `rules <group>` table when the next unit-level item begins
RULES_BLOCK_END = (
	r'^(?=\s*(?:unit|in|out|intent|code|queue|rule|rules|preset|step|reason|gate|'
	r'for|until|if|else|section|end|rollback|finally)(?:[\s;]|$)| {0,2}[^\s;])'
)

# - Scopes
MATRIX = 'keyword.other.matrix.rig'
CONTEXT = 'keyword.other.context.rig'
FLOW = 'keyword.control.flow.rig'
NODE = 'storage.type.node.rig'
ID = 'entity.name.function.node.rig'
BLOCK = 'keyword.control.block.rig'
STRING = 'string.quoted.double.rig'
ESCAPE = 'constant.character.escape.rig'
RULE_REF = 'variable.other.constant.rule.rig'
PATH_REF = 'variable.other.path.rig'
FN_REF = 'support.function.rig'

# - Heads: (pattern, scopes of the groups, pushed context or None)
# Note: the first (...) group in every entry must be the plain head-word alternation
# (checked against skills/rig/spec.md by tests/test_rig.py).
HEADS = [
	(rf'^(unit)\s+({W})', ['storage.type.unit.rig', 'entity.name.type.unit.rig'], None),
	(rf'^\s*(in){E}(?:\s+({W}))?(?:\s+({W}))?', [MATRIX, 'variable.parameter.input.rig', 'support.type.rig'], None),
	(rf'^\s*(out){E}(?:\s+({W}))?', [MATRIX, 'support.type.rig'], None),
	(rf'^\s*(intent|audience|style|never|check){E}', [MATRIX], None),
	(rf'^\s*(code){E}(?:\s+({W}))?(?:\s+({W}))?', [CONTEXT, 'entity.name.namespace.rig', 'string.unquoted.path.rig'], None),
	(rf'^\s*(test){E}(?:\s+({W}))?', [CONTEXT, 'string.unquoted.path.rig'], None),
	(rf'^\s*(queue){E}', [CONTEXT], None),
	(rf'^\s*(rule){E}(?:\s+({W}))?', ['storage.type.rule.rig', 'entity.name.constant.rule.rig'], None),
	(rf'^\s*(rules)\s+([a-z][a-z0-9_]*){E}', ['storage.type.rule.rig', 'entity.name.constant.rule.rig'], 'rules-block'),
	(rf'^\s*(rules){E}', ['storage.type.rule.rig'], None),
	(rf'^\s*(preset){E}(?:\s+({W}))?', ['storage.type.rule.rig', 'entity.name.constant.preset.rig'], None),
	(rf'^\s*(set){E}(?:\s+({W}))?', [CONTEXT, RULE_REF], None),
	(rf'^\s*(ui){E}(?:\s+(toggle|select|slider|number|input){E})?', [CONTEXT, 'storage.modifier.ui.rig'], None),
	(rf'^\s*(note|options|range){E}', [CONTEXT], None),
	(rf'^\s*(step|reason|end){E}(?:\s+({W}))?', [NODE, ID], None),
	(rf'^\s*(gate){E}(?:\s+({W}))?(?:\s+(hard|soft|model|human){E})?', [NODE, ID, 'storage.modifier.gate.rig'], None),
	(rf'^\s*(for){E}(?:\s+({W}))?(?:\s+(in){E})?(?:\s+({W}))?', [BLOCK, 'variable.other.item.rig', BLOCK, PATH_REF], None),
	(rf'^\s*(until|if){E}(?:\s+({W}))?', [BLOCK, PATH_REF], None),
	(rf'^\s*(else|section|rollback|finally){E}', [BLOCK], None),
	(rf'^\s*(by){E}(?:\s+(model){E})?', [FLOW, 'storage.modifier.lane.rig'], 'fn-refs'),
	(rf'^\s*(tools){E}', [FLOW], 'fn-refs'),
	(rf'^\s*(mode){E}(?:\s+(careful|creative){E})?', [FLOW, 'storage.modifier.mode.rig'], None),
	(rf'^\s*(retry|budget|candidates){E}(?:\s+({RULE_ID}){E})?', [FLOW, RULE_REF], None),
	(rf'^\s*(do|fail|timeout|tolerate){E}', [FLOW], None),
	(rf'^\s*(reads){E}', [FLOW], 'rule-refs'),
	(rf'^\s*(sees|brief){E}', [FLOW], 'path-refs'),
]

LINE_CTXS = {
	'rule-refs': [(W, RULE_REF)],
	'path-refs': [(W, PATH_REF)],
	'fn-refs': [(r'(?<![^\s])model' + E, 'storage.modifier.lane.rig'), (W, FN_REF)],
}

RULES_BLOCK_HEADS = [
	(rf'^\s*(ui){E}(?:\s+(toggle|select|slider|number|input){E})?', [CONTEXT, 'storage.modifier.ui.rig']),
	(rf'^\s*(note|options|range){E}', [CONTEXT]),
	(r'^\s+([a-z][a-z0-9_-]*)(?=\s+[^\s;])', ['entity.name.constant.rule.rig']),
]

# - Arguments, in order of priority
ITEMS = [
	('template-directive', r'(;)(\s*(?:>>>|<<<)\s+level\s+\d+)\s*$', {1: 'comment.line.semicolon.rig', 2: 'keyword.control.directive.rig'}),
	('comment', r';.*$', {0: 'comment.line.semicolon.rig'}),
	('regex', B + r'/(?:\\.|[^/\\])*/(?=[\s)\],}]|$)', {0: 'string.regexp.rig'}),
	('arrow-continue', B + rf'(->)\s+(continue){A}', {1: 'keyword.operator.arrow.rig', 2: FLOW}),
	('arrow', B + rf'(->)(?:\s+({W}))?', {1: 'keyword.operator.arrow.rig', 2: 'variable.function.target.rig'}),
	('inline-by-model', B + r'(by)\s+(model)' + A, {1: FLOW, 2: 'storage.modifier.lane.rig'}),
	('inline-by', B + rf'(by)(?:\s+({W}))?', {1: FLOW, 2: FN_REF}),
	('inline', B + r'fail' + A, {0: FLOW}),
	('field-key', r'(?<=[{,\s])([A-Za-z_][\w-]*)(?=\??:)', {1: 'variable.other.member.rig'}),
	('percent', B + r'\d+(?:\.\d+)?%' + A, {0: 'constant.numeric.rig'}),
	('time', B + r'\d+[smhd]' + A, {0: 'constant.numeric.rig'}),
	('range-open-hi', B + r'([-+]?\d+(?:\.\d+)?)(\.\.)(_)' + A, {1: 'constant.numeric.rig', 2: 'keyword.operator.range.rig', 3: 'constant.language.rig'}),
	('range-open-lo', B + r'(_)(\.\.)([-+]?\d+(?:\.\d+)?)' + A, {1: 'constant.language.rig', 2: 'keyword.operator.range.rig', 3: 'constant.numeric.rig'}),
	('range-span', B + r'([-+]?\d+(?:\.\d+)?)(\.\.)([-+]?\d+(?:\.\d+)?)' + A, {1: 'constant.numeric.rig', 2: 'keyword.operator.range.rig', 3: 'constant.numeric.rig'}),
	('open-bound', B + r'_' + A, {0: 'constant.language.rig'}),
	('bar', r'\|', {0: 'punctuation.separator.rig'}),
	('number', B + r'[-+]?\d+(?:\.\d+)?' + A, {0: 'constant.numeric.rig'}),
	('constant', B + r'(?:on|off|true|false|True|False|null|none|None)' + A, {0: 'constant.language.rig'}),
	('builtin-type', B + r'(?:str|text|word|path|int|float|bool|list|dict|tuple|any|Literal)' + A, {0: 'support.type.rig'}),
	('optional', r'\?', {0: 'keyword.operator.optional.rig'}),
	('colon', r':', {0: 'punctuation.separator.key-value.rig'}),
	('comma', r',', {0: 'punctuation.separator.comma.rig'}),
	('paren-open', r'\(', {0: 'punctuation.section.parens.begin.rig'}),
	('paren-close', r'\)', {0: 'punctuation.section.parens.end.rig'}),
	('bracket-open', r'\[', {0: 'punctuation.section.brackets.begin.rig'}),
	('bracket-close', r'\]', {0: 'punctuation.section.brackets.end.rig'}),
	('brace-open', r'\{', {0: 'punctuation.section.braces.begin.rig'}),
	('brace-close', r'\}', {0: 'punctuation.section.braces.end.rig'}),
]


# - VS Code (TextMate JSON)
def tm_caps(scopes, start=1):
	return {str(i): {'name': s} for i, s in enumerate(scopes, start) if s}


def vscode():
	patterns = [{'include': '#template-directive'}, {'include': '#comment'}]
	for rx, scopes, ctx in HEADS:
		if ctx == 'rules-block':
			rb_patterns = [{'include': '#template-directive'}, {'include': '#comment'}]
			for rrx, rscopes in RULES_BLOCK_HEADS:
				rb_patterns.append({'match': rrx, 'captures': tm_caps(rscopes)})
			rb_patterns.append({'include': '#items'})
			patterns.append({'begin': rx, 'beginCaptures': tm_caps(scopes), 'end': RULES_BLOCK_END, 'patterns': rb_patterns})
		elif ctx in LINE_CTXS:
			line_patterns = [{'include': '#template-directive'}, {'include': '#comment'}]
			for mrx, mscope in LINE_CTXS[ctx]:
				line_patterns.append({'match': mrx, 'name': mscope})
			patterns.append({'begin': rx, 'beginCaptures': tm_caps(scopes), 'end': '$', 'patterns': line_patterns})
		else:
			patterns.append({'match': rx, 'captures': tm_caps(scopes)})
	patterns.append({'include': '#items'})

	repo = {
		'string': {
			'begin': '"', 'end': '"|$', 'name': STRING,
			'patterns': [{'match': r'\\.', 'name': ESCAPE}, {'match': PH, 'name': RULE_REF}],
		},
	}
	items = []
	for name, rx, caps in ITEMS:
		rule = {'match': rx}
		if 0 in caps:
			rule['name'] = caps[0]
		else:
			rule['captures'] = {str(k): {'name': v} for k, v in caps.items()}
		repo[name] = rule
		items.append({'include': '#' + name})
		if name == 'comment':
			items.append({'include': '#string'})
	repo['items'] = {'patterns': items}

	grammar = {
		'$schema': 'https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json',
		'comment': 'Generated by editors/build.py. Do not edit.',
		'name': 'Rig', 'scopeName': 'source.rig', 'fileTypes': ['rig'],
		'patterns': patterns, 'repository': repo,
	}
	return json.dumps(grammar, indent='\t', ensure_ascii=False) + '\n'


# - Sublime Text (sublime-syntax YAML)
def q(s):
	return "'" + s.replace("'", "''") + "'"


def sublime():
	out = ['%YAML 1.2', '---', '# Generated by editors/build.py. Do not edit.',
	       '# https://www.sublimetext.com/docs/syntax.html',
	       'name: Rig', 'scope: source.rig', 'version: 2', 'file_extensions: [rig]', '', 'contexts:',
	       '  main:', '    - include: template-directive', '    - include: comment']

	def caps(scopes, start=1, pad='      '):
		lines = [pad + 'captures:']
		lines += [f'{pad}  {i}: {s}' for i, s in enumerate(scopes, start) if s]
		return lines

	for rx, scopes, ctx in HEADS:
		out += [f'    - match: {q(rx)}'] + caps(scopes)
		if ctx:
			out += [f'      push: {ctx}']
	out += ['    - include: items', '']

	out += ['  items:']
	for name, _, _ in ITEMS:
		out.append(f'    - include: {name}')
		if name == 'comment':
			out.append('    - include: string')
	out.append('')

	for name, rx, cs in ITEMS:
		out += [f'  {name}:', f'    - match: {q(rx)}']
		if 0 in cs:
			out.append(f'      scope: {cs[0]}')
		else:
			out += ['      captures:'] + [f'        {k}: {v}' for k, v in cs.items()]
		out.append('')

	out += ['  string:', "    - match: '\"'", '      scope: punctuation.definition.string.begin.rig',
	        '      push:', f'        - meta_scope: {STRING}',
	        r"        - match: '\\.'", f'          scope: {ESCAPE}',
	        f'        - match: {q(PH)}', f'          scope: {RULE_REF}',
	        "        - match: '\"'", '          scope: punctuation.definition.string.end.rig', '          pop: true',
	        r"        - match: '$\n?'", '          pop: true', '']

	out += ['  rules-block:',
	        f'    - match: {q(RULES_BLOCK_END)}', '      pop: true',
	        '    - include: template-directive', '    - include: comment']
	for rrx, rscopes in RULES_BLOCK_HEADS:
		out += [f'    - match: {q(rrx)}'] + caps(rscopes)
	out += ['    - include: items', '']

	for ctx_name, rules in LINE_CTXS.items():
		out += [f'  {ctx_name}:', "    - match: '$\\n?'", '      pop: true',
		        '    - include: template-directive', '    - include: comment']
		for mrx, mscope in rules:
			out += [f'    - match: {q(mrx)}', f'      scope: {mscope}']
		out.append('')

	return '\n'.join(out)


def main():
	check = '--check' in sys.argv[1:]
	stale = []
	for path, text in ((VSCODE, vscode()), (SUBLIME, sublime())):
		old = None
		if os.path.exists(path):
			with open(path, encoding='utf-8') as f:
				old = f.read()
		if old == text:
			continue
		if check:
			stale.append(os.path.relpath(path, HERE))
		else:
			os.makedirs(os.path.dirname(path), exist_ok=True)
			with open(path, 'w', encoding='utf-8', newline='\n') as f:
				f.write(text)
			print('wrote', os.path.relpath(path, HERE))
	if stale:
		print('not current (run python editors/build.py):', ', '.join(stale))
		return 1
	return 0


if __name__ == '__main__':
	sys.exit(main())
