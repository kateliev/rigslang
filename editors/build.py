'''Build the Rig syntax grammars for VS Code and Sublime Text from one table.

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

# - Regex parts (Oniguruma; both editors read the same patterns)
W = r'[^\s();"][^\s();]*'          # a word that can be a name
E = r'(?=[\s;]|$)'                 # the end of a word
B = r'(?<![^\s(])'                 # the start of an argument
A = r'(?=[\s();]|$)'               # the end of an argument
PH = r'\{[A-Za-z_][\w-]*(?:\.[\w-]+)+\}'  # a rule named in a string: {group.name}

# - Scopes
MATRIX = 'keyword.other.matrix.rig'
CONTEXT = 'keyword.other.context.rig'
FLOW = 'keyword.control.flow.rig'
NODE = 'storage.type.node.rig'
ID = 'entity.name.function.node.rig'

# - Heads: (pattern, scopes of the groups, push the id list after it)
HEADS = [
	(rf'^(unit)\s+({W})(?:\s+(snippet|tool|agent){E})?', ['storage.type.unit.rig', 'entity.name.type.unit.rig', 'storage.modifier.scale.rig'], False),
	(rf'^\s*(in){E}(?:\s+({W}))?(?:\s+({W}))?', [MATRIX, 'variable.parameter.input.rig', 'support.type.rig'], False),
	(rf'^\s*(out){E}(?:\s+({W}))?', [MATRIX, 'support.type.rig'], False),
	(rf'^\s*(intent|example|ensure){E}', [MATRIX], False),
	(rf'^\s*(probe){E}', [CONTEXT], False),
	(rf'^\s*(check){E}(?:\s+({W}))?', [MATRIX, 'storage.type.language.rig'], False),
	(rf'^\s*(evidence){E}(?:\s+({W}))?', [CONTEXT, 'markup.underline.link.rig'], False),
	(rf'^\s*(uses){E}(?:\s+({W}))?', [CONTEXT, 'entity.other.inherited-class.rig'], False),
	(rf'^\s*(external){E}(?:\s+({W}))?', [CONTEXT, 'support.function.rig'], False),
	(rf'^\s*(code|test){E}', [CONTEXT], False),
	(rf'^\s*(rule){E}(?:\s+({W}))?', ['storage.type.rule.rig', 'entity.name.constant.rule.rig'], False),
	(rf'^\s*(preset){E}(?:\s+({W}))?', ['storage.type.rule.rig', 'entity.name.constant.preset.rig'], False),
	(rf'^\s*(set){E}(?:\s+({W}))?', [CONTEXT, 'variable.other.constant.rule.rig'], False),
	(rf'^\s*(note|label|options|min|max|unit){E}', [CONTEXT], False),
	(rf'^\s*(step|end){E}(?:\s+({W}))?', [NODE, ID], False),
	(rf'^\s*(gate){E}(?:\s+({W}))?(?:\s+(hard|soft|judge|human){E})?', [NODE, ID, 'storage.modifier.gate.rig'], False),
	(rf'^\s*(by){E}(?:\s+({W}))?', [FLOW, 'support.function.rig'], False),
	(rf'^\s*(when|do|brief|next|pass|fail){E}', [FLOW], False),
	(rf'^\s*(reads){E}', [FLOW], True),
	(rf'^\s*(sees){E}', [FLOW], False),
]

# - Casts: (rig name, VS Code language id, VS Code scope, Sublime scope)
CASTS = [
	('py', 'python', 'source.python', 'source.python'),
	('js', 'javascript', 'source.js', 'source.js'),
	('ts', 'typescript', 'source.ts', 'source.ts'),
	('sh', 'shellscript', 'source.shell', 'source.shell.bash'),
	('rust', 'rust', 'source.rust', 'source.rust'),
]


def cast_head(lang):
	return (rf'^(\s*)(cast)\s+({lang}){E}(?:\s+(#[^\s;]*))?(?:\s+(#[^\s;]*))?'
	        rf'(?:\s+(proved|observed)(?:\s+(\d{{4}}-\d{{2}}-\d{{2}}))?)?\s*(;.*)?$')


CAST_SCOPES = ['storage.type.cast.rig', 'storage.type.language.rig', 'constant.other.hash.rig',
               'constant.other.hash.rig', 'keyword.other.proved.rig', 'constant.numeric.date.rig',
               'comment.line.semicolon.rig']

# - Arguments, in order of priority
ITEMS = [
	('comment', r';.*$', {0: 'comment.line.semicolon.rig'}),
	('regex', B + r'/(?:\\.|[^/\\])*/(?=[\s)]|$)', {0: 'string.regexp.rig'}),
	('arrow', B + rf'(->)(?:\s+({W}))?', {1: 'keyword.operator.arrow.rig', 2: 'variable.function.target.rig'}),
	('example', B + r'=>' + A, {0: 'keyword.operator.arrow.rig'}),
	('date', B + r'\d{4}-\d{2}-\d{2}' + A, {0: 'constant.numeric.date.rig'}),
	('hash', B + r'#[0-9a-fA-F]+' + A, {0: 'constant.other.hash.rig'}),
	('number', B + r'[-+]?\d+(?:\.\d+)?' + A, {0: 'constant.numeric.rig'}),
	('constant', B + r'(?:on|off|true|false)' + A, {0: 'constant.language.rig'}),
	('unknown', B + r'\?' + A, {0: 'constant.language.unknown.rig'}),
	('paren-open', r'\(', {0: 'punctuation.section.parens.begin.rig'}),
	('paren-close', r'\)', {0: 'punctuation.section.parens.end.rig'}),
]
STRING = 'string.quoted.double.rig'
ESCAPE = 'constant.character.escape.rig'
RULE_REF = 'variable.other.constant.rule.rig'


# - VS Code (TextMate JSON)
def tm_caps(scopes, start=1):
	return {str(i): {'name': s} for i, s in enumerate(scopes, start) if s}


def vscode():
	patterns = [{'include': '#comment'}]
	for lang, _, scope, _ in CASTS:
		patterns.append({
			'begin': cast_head(lang), 'beginCaptures': tm_caps([None] + CAST_SCOPES),
			'while': r'^(?=\1[ \t]+\S|[ \t]*$)',
			'contentName': f'meta.embedded.block.{lang}.rig',
			'patterns': [{'include': scope}],
		})
	patterns.append({
		'begin': cast_head(W), 'beginCaptures': tm_caps([None] + CAST_SCOPES),
		'while': r'^(?=\1[ \t]+\S|[ \t]*$)',
		'contentName': 'markup.raw.block.rig',
	})
	for rx, scopes, ids in HEADS:
		if ids:
			patterns.append({'begin': rx, 'beginCaptures': tm_caps(scopes), 'end': '$',
			                 'patterns': [{'include': '#comment'}, {'match': W, 'name': RULE_REF}]})
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
	       '  main:', '    - include: comment']

	def caps(scopes, start=1, pad='      '):
		lines = [pad + 'captures:']
		lines += [f'{pad}  {i}: {s}' for i, s in enumerate(scopes, start) if s]
		return lines

	escape = r'^(?!\1[ \t]+\S|[ \t]*$)'
	for lang, _, _, scope in CASTS:
		out += [f'    - match: {q(cast_head(lang))}'] + caps(CAST_SCOPES, 2)
		out += [f'      embed: scope:{scope}',
		        f'      embed_scope: meta.embedded.block.{lang}.rig {scope}',
		        f'      escape: {q(escape)}']
	out += [f'    - match: {q(cast_head(W))}'] + caps(CAST_SCOPES, 2)
	out += ['      embed: cast-raw', '      embed_scope: markup.raw.block.rig', f'      escape: {q(escape)}']
	for rx, scopes, ids in HEADS:
		out += [f'    - match: {q(rx)}'] + caps(scopes)
		if ids:
			out += ['      push: rule-refs']
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

	out += ['  string:', "    - match: '\"'", f'      scope: punctuation.definition.string.begin.rig',
	        '      push:', f'        - meta_scope: {STRING}',
	        r"        - match: '\\.'", f'          scope: {ESCAPE}',
	        f'        - match: {q(PH)}', f'          scope: {RULE_REF}',
	        "        - match: '\"'", '          scope: punctuation.definition.string.end.rig', '          pop: true',
	        r"        - match: '$\n?'", '          pop: true', '']
	out += ['  rule-refs:', "    - match: '$\\n?'", '      pop: true', '    - include: comment',
	        f'    - match: {q(W)}', f'      scope: {RULE_REF}', '']
	out += ['  cast-raw:', '    - meta_include_prototype: false', '']
	return '\n'.join(out)


def main():
	check = '--check' in sys.argv[1:]
	stale = []
	for path, text in ((VSCODE, vscode()), (SUBLIME, sublime())):
		old = open(path, encoding='utf-8').read() if os.path.exists(path) else None
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
