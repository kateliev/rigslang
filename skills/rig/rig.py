#!/usr/bin/env python3
"""rig.py: the tool of Rig, language version 2. Standard library only.

    python rig.py check FILE...               validate; show the status of every unit
    python rig.py json FILE                   the parsed tree as JSON
    python rig.py compile json FILE [UNIT]    the unit as a catalogue: rules, presets and flow,
                                              the JSON that the runner reads
    python rig.py compile skill FILE [UNIT]   the unit as a SKILL.md for an agent that follows
                                              instructions; --rules PATH: refer to the values
                                              in that JSON file instead of writing them in
        compile options: --preset NAME (use the values of a preset), -o OUT (write a file),
                                              --driver CMD (skill: a runner walks the flow)
    python rig.py serve FILE [UNIT]           the viewer for FILE on 127.0.0.1; Save writes FILE
        [--port 8765] [--json OUT] [--skill OUT] [--rules-ref] [--runs DIR]
                                              and compiles it again to OUT; --rules-ref makes
                                              the skill read its values from the JSON

    python rig.py new DIR NAME [--level N] [--template host]
                                              make a project: a tool with its source, code, tests
                                              and runner (levels 1 to 3: guide/levels.md)
    python rig.py build [DIR] [--check]       compile the source of a project to its fronts: the
                                              catalogue, the skill, the plugin front
    python rig.py doctor [DIR] [--no-tests] [--json]
                                              check a project against the list of its level
    python rig.py test [DIR] [--replay RUN]   run the tests of a project; --replay: run the flow
                                              again with the answers recorded in a run
    python rig.py plugin DIR [--owner NAME]   add the front for a local model: an LM Studio plugin
                                              that reads its tools and its rules from the build
    python rig.py mcp-config DIR [--api-url URL] [--model NAME] [--http URL]
                                              print an MCP server JSON config for the project

The language is defined in spec.md (same folder).
"""
import ast
import json
import os
import re
import sys

VERSION = 2
FLOW = ('step', 'reason', 'gate', 'end')                          # the nodes of a flow
BLOCKS = ('for', 'until', 'if', 'else', 'section', 'rollback', 'finally')  # the blocks: their body is the lines under them
ITEMS = FLOW + BLOCKS
GATE_KINDS = ('hard', 'soft', 'model', 'human')
REASON_MODES = ('careful', 'creative')
UI_CONTROLS = ('toggle', 'select', 'slider', 'number', 'input')
LEVELS = ('none', 'code', 'tested')  # low to high; "model" and "human" are apart
MATRIX = ('in', 'out', 'intent')
BASE_TYPES = ('str', 'text', 'word', 'path', 'int', 'float', 'bool', 'list', 'dict', 'any')
PAIRS = {'(': ')', '[': ']', '{': '}'}
CLOSERS = {')': '(', ']': '[', '}': '{'}
LEGACY_TYPES = {
	'list': 'write list[T] instead of (list T)',
	'tuple': 'write tuple[T1, T2] or (T1, T2) instead of (tuple ...)',
	'record': 'write {field: type, ...} instead of (record ...)',
	'maybe': 'write T? or T | None instead of (maybe T)',
	'one-of': 'write "a" | "b" instead of (one-of ...)',
}
NODE_KIDS = {
	'step': {'do', 'by', 'reads', 'sees', 'out', 'brief', 'timeout', 'if', 'note'},
	'reason': {'intent', 'do', 'mode', 'reads', 'sees', 'tools', 'budget', 'candidates', 'out', 'brief', 'timeout', 'if', 'note'},
	'gate': {'check', 'by', 'reads', 'sees', 'options', 'retry', 'timeout', 'if', 'fail', 'note'},
	'end': {'note'},
}
BLOCK_OPTIONS = {'for': {'tolerate', 'fail'}, 'until': {'retry', 'fail'}}
CHILDREN = {
	'unit': {'in', 'out', 'intent', 'note', 'code', 'rule', 'rules', 'preset', 'queue'} | set(ITEMS),
	'intent': {'audience', 'style', 'never', 'note'},
	'queue': {'by', 'reads', 'note'},
	'code': {'test', 'note'},
	'preset': {'set'},
	'rule': {'range', 'options', 'ui', 'note'},
	'rules': set(),
}
CHILDREN.update(NODE_KIDS)
for _b in BLOCKS:
	CHILDREN[_b] = set(ITEMS) | BLOCK_OPTIONS.get(_b, set()) | {'note'}
INLINE = {'step': ('by',), 'gate': ('by', 'fail'), 'queue': ('by',)}  # children that can stand on the line of their node
RESERVED = ('continue', 'error')  # "fail -> continue" and the built-in outcome "error": not ids
# Words removed in version 1 and version 2, with what to write instead.
REMOVED = {
	'next': 'remove it: the next line is the next node',
	'pass': 'remove it: a gate that passes goes on to the next line',
	'when': 'write "if <path>" as a child of the node',
	'ensure': 'write check "text"',
	'min': 'write range <min> <max>',
	'max': 'write range <min> <max>',
	'label': 'write the label as the string after the value: rule <id> <value> "label"',
	'external': '"by" names a function of a "code" file',
	'cast': 'the code lives in a file: write code <prefix> <path>',
	'probe': 'test the code in its test file',
	'evidence': 'write the evidence in the text of the note',
	'example': 'removed in version 2: write unit tests in your test file',
	'uses': 'removed in version 2: import helper modules in Python code',
}
NUMBER = re.compile(r'^-?\d+(\.\d+)?([eE][+-]?\d+)?$')
INLINE_RANGE = re.compile(r'^(_|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\.\.(_|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)$')
GROUP_ID = re.compile(r'^[a-z][a-z0-9_]*$')
RULE_ID = re.compile(r'^[A-Za-z_][\w-]*(\.[\w-]+)+$')
PATH = re.compile(r'^[A-Za-z_][\w-]*(\.[\w-]+)*$')
PLACE = re.compile(r'\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}')
PROSE_NUMBER = re.compile(r'(?<![\w.#{-])\d+(?:\.\d+)?(?![\w}])')
PROSE = ('do', 'check')
TIME = re.compile(r'^(\d+)(s|m|h|d)$')
SECONDS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


class RigError(Exception):
	def __init__(self, line, text):
		Exception.__init__(self, 'line {}: {}'.format(line, text))
		self.line = line


class Node(object):
	def __init__(self, head, args, line, indent):
		self.head, self.args, self.line, self.indent = head, args, line, indent
		self.children = []
		self.spans = []
		self.parent = None

	def word(self, i, default=None):
		return self.args[i][1] if len(self.args) > i else default

	def kids(self, head):
		return [c for c in self.children if c.head == head]


# - Parsing ------------------------------------------
def _scan_balanced(s, i, line):
	'''Scan balanced (...), [...], or {...} starting at i (where s[i] in PAIRS), skipping quoted strings.'''
	n = len(s)
	stack = [s[i]]
	j = i + 1
	while j < n and stack:
		ch = s[j]
		if ch in ('"', "'"):
			q = ch
			j += 1
			while j < n and s[j] != q:
				j += 2 if s[j] == '\\' else 1
			if j >= n:
				raise RigError(line, 'the string is not closed')
			j += 1
			continue
		if ch in PAIRS:
			stack.append(ch)
		elif ch in CLOSERS:
			if stack[-1] != CLOSERS[ch]:
				raise RigError(line, '"{}" does not match "{}"'.format(ch, stack[-1]))
			stack.pop()
		j += 1
	if stack:
		raise RigError(line, 'a "{}" is not closed'.format(stack[-1]))
	if j < n and s[j] == '?':
		j += 1
	return j


def tokenize(s, line, spans=None):
	'''One line (without its indentation) -> a list of args: (kind, text).
	spans: a list that gets (start, end) of each top-level arg in s.'''
	out, i, n = [], 0, len(s)
	start = 0
	while i < n:
		if spans is not None and len(spans) < len(out):
			spans.append((start, i))
		if s[i] not in ' \t':
			start = i
		c = s[i]
		if c in ' \t':
			i += 1
			continue
		if c == ';':
			break
		if c in CLOSERS:
			raise RigError(line, 'a "{}" without "{}"'.format(c, CLOSERS[c]))
		if c == '"':
			j = i + 1
			while j < n and s[j] != '"':
				j += 2 if s[j] == '\\' else 1
			if j >= n:
				raise RigError(line, 'the string is not closed')
			out.append(('str', s[i:j + 1]))
			i = j + 1
			continue
		if c in PAIRS:
			j = _scan_balanced(s, i, line)
			out.append(('expr', s[i:j]))
			i = j
			continue
		if c == '/':
			j = i + 1
			while j < n and s[j] != '/':
				j += 2 if s[j] == '\\' else 1
			if j < n and (j + 1 == n or s[j + 1] in ' \t)]};'):
				out.append(('re', s[i:j + 1]))
				i = j + 1
				continue
		j = i
		while j < n and s[j] not in ' \t;([{}])':
			j += 1
		if j < n and s[j] == '[':
			j = _scan_balanced(s, j, line)
			out.append(('expr', s[i:j]))
			i = j
			continue
		w = s[i:j]
		if w.endswith('?') and len(w) > 1:
			out.append(('expr', w))
		else:
			out.append(('num' if NUMBER.match(w) else 'word', w))
		i = j
	if spans is not None and len(spans) < len(out):
		spans.append((start, i))
	return out


def ser(arg):
	if isinstance(arg, str):
		return arg
	kind, v = arg
	return '(' + ' '.join(ser(a) for a in v) + ')' if kind == 'list' else v


def _split_inline_range(r):
	'''Desugar optional inline "<lo>..<hi>" after <value> on a rule node into a "range" child.'''
	if len(r.args) >= 3 and r.args[2][0] == 'word':
		m = INLINE_RANGE.match(r.args[2][1])
		if m:
			del r.args[2]
			if len(r.spans) > 2:
				del r.spans[2]
			lo_tok = ('word', '_') if m.group(1) == '_' else ('num', m.group(1))
			hi_tok = ('word', '_') if m.group(2) == '_' else ('num', m.group(2))
			g = Node('range', [lo_tok, hi_tok], r.line, r.indent + 2)
			g.parent = r
			r.children.insert(0, g)


def parse(text):
	'''Text -> the root node (head "file"). Raises RigError.'''
	lines = text.replace('\r\n', '\n').split('\n')
	root = Node('file', [], 0, -1)
	stack = [root]
	for i, raw in enumerate(lines):
		line = i + 1
		body = raw.lstrip(' \t')
		if not body.strip() or body.startswith(';'):
			continue
		lead = raw[:len(raw) - len(body)]
		if '\t' in lead:
			raise RigError(line, 'a tab in the indentation: indent with spaces')
		indent = len(lead)
		while stack[-1].indent >= indent:
			stack.pop()
		sp = []
		toks = tokenize(body, line, sp)
		if not toks:
			continue
		if toks[0][0] != 'word':
			raise RigError(line, 'a line must start with a word')
		node = Node(toks[0][1], toks[1:], line, indent)
		node.spans = [(indent + a, indent + b) for a, b in sp[1:]]  # the columns of each argument, for the viewer
		node.parent = stack[-1]
		if node.head in INLINE:  # "step <id> by model", "gate <id> <kind> fail -> <end>", "queue by steps.pending"
			min_k = 2 if node.head == 'gate' else (0 if node.head == 'queue' else 1)
			cuts = [k for k, a in enumerate(node.args) if k >= min_k and a[0] == 'word' and a[1] in INLINE[node.head]]
			for k, at in enumerate(cuts):
				stop = cuts[k + 1] if k + 1 < len(cuts) else len(node.args)
				f = Node(node.args[at][1], node.args[at + 1:stop], line, indent + 1)
				f.parent, f.spans = node, node.spans[at + 1:stop]
				node.children.append(f)
			if cuts:
				node.args, node.spans = node.args[:cuts[0]], node.spans[:cuts[0]]
		stack[-1].children.append(node)
		stack.append(node)
	for u in root.children:
		u.root = root  # a unit knows its file: "by" can name the other units in it
		if u.head != 'unit':
			continue
		norm = []
		for c in u.children:
			if c.head == 'rule':
				_split_inline_range(c)
				norm.append(c)
			elif c.head == 'rules' and len(c.args) == 1 and c.args[0][0] == 'word' and GROUP_ID.match(c.args[0][1]):
				grp = c.args[0][1]
				if not c.children:
					norm.append(c)
					continue
				for rc in c.children:
					if rc.head == 'rule':
						rc._bad_compact = 'inside "rules {}", write "<name> <value>", without "rule"'.format(grp)
						rc.parent = u
						norm.append(rc)
						continue
					rid = '{}.{}'.format(grp, rc.head)
					rnode = Node('rule', [('word', rid)] + list(rc.args), rc.line, rc.indent)
					rnode.spans = [(rc.indent, rc.indent + len(rc.head))] + list(rc.spans)
					rnode.parent = u
					rnode.children = list(rc.children)
					for kc in rnode.children:
						kc.parent = rnode
					_split_inline_range(rnode)
					norm.append(rnode)
			else:
				norm.append(c)
		u.children = norm
	return root


# - Values and types (parsed via Python AST) ---------
KEY_IDENT = re.compile(r'[A-Za-z_][\w-]*')


class _ParseProblem(Exception):
	pass


def _prep_python_expr(raw, allow_opt=False):
	'''Normalize JS-style bare object keys ({Light: 20, a?: str}) and postfix T? into valid Python AST syntax.'''
	out, stack, i, n = [], [], 0, len(raw)
	expect_key = False
	while i < n:
		ch = raw[i]
		if ch in ('"', "'"):
			q = ch
			j = i + 1
			while j < n and raw[j] != q:
				j += 2 if raw[j] == '\\' else 1
			if j >= n:
				raise _ParseProblem('the string is not closed')
			lit = raw[i:j + 1]
			i = j + 1
			if allow_opt and stack and stack[-1] == '{' and expect_key:
				k = i
				while k < n and raw[k] in ' \t':
					k += 1
				if raw[k:k + 2] == '?:':
					key_val = ast.literal_eval(lit)
					out.append(repr('__opt__' + str(key_val)) + ':')
					i = k + 2
					expect_key = False
					continue
			out.append(lit)
			if stack and stack[-1] == '{' and expect_key:
				k = i
				while k < n and raw[k] in ' \t':
					k += 1
				if raw[k:k + 1] == ':':
					expect_key = False
			continue
		if ch in PAIRS:
			stack.append(ch)
			expect_key = (ch == '{')
			out.append(ch)
			i += 1
			continue
		if ch in CLOSERS:
			if stack:
				stack.pop()
			expect_key = False
			out.append(ch)
			i += 1
			continue
		if ch == ',':
			if stack and stack[-1] == '{':
				expect_key = True
			out.append(ch)
			i += 1
			continue
		if stack and stack[-1] == '{' and expect_key and (ch.isalpha() or ch == '_'):
			m = KEY_IDENT.match(raw, i)
			if m:
				k = m.end()
				while k < n and raw[k] in ' \t':
					k += 1
				if allow_opt and raw[k:k + 2] == '?:':
					out.append(repr('__opt__' + m.group(0)) + ':')
					i = k + 2
					expect_key = False
					continue
				if raw[k:k + 1] == ':':
					out.append(repr(m.group(0)) + ':')
					i = k + 1
					expect_key = False
					continue
		if allow_opt and ch == '?':
			out.append(' | None')
			i += 1
			continue
		out.append(ch)
		i += 1
	return ''.join(out)


def _eval_ast_val(node):
	if isinstance(node, ast.Constant):
		if isinstance(node.value, (str, int, float, bool)) or node.value is None:
			return node.value
		raise _ParseProblem('unsupported literal value')
	if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant):
		v = node.operand.value
		if isinstance(v, (int, float)) and not isinstance(v, bool):
			return -v if isinstance(node.op, ast.USub) else +v
	if isinstance(node, ast.Name):
		return {'true': True, 'True': True, 'false': False, 'False': False, 'null': None, 'none': None, 'None': None}.get(node.id, node.id)
	if isinstance(node, ast.List):
		return [_eval_ast_val(x) for x in node.elts]
	if isinstance(node, ast.Tuple):
		return [_eval_ast_val(x) for x in node.elts]
	if isinstance(node, ast.Dict):
		d = {}
		for k_node, v_node in zip(node.keys, node.values):
			if k_node is None:
				raise _ParseProblem('dict unpacking is not allowed in a literal')
			if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str):
				k = k_node.value
			elif isinstance(k_node, ast.Name):
				k = k_node.id
			else:
				raise _ParseProblem('dict keys must be strings or names')
			if k in d:
				raise _ParseProblem('duplicate key "{}" in dict'.format(k))
			d[k] = _eval_ast_val(v_node)
		return d
	raise _ParseProblem('expressions are not allowed: write a static literal ([list], (tuple), or {key: value})')


def parse_literal(arg):
	'''Parse a value token -> (kind_name, python_value, error_or_None).
	kind_name is one of: str, number, pattern, switch, list, tuple, dict, word.'''
	if arg is None:
		return None, None, 'no value'
	kind, v = arg
	if kind == 'str':
		out, i = [], 1
		while i < len(v) - 1:
			if v[i] == '\\' and i + 1 < len(v) - 1:
				nxt = v[i + 1]
				out.append({'n': '\n', 't': '\t'}.get(nxt, nxt))
				i += 2
			else:
				out.append(v[i])
				i += 1
		return 'str', ''.join(out), None
	if kind == 'num':
		return 'number', (float(v) if ('.' in v or 'e' in v or 'E' in v) else int(v)), None
	if kind == 're':
		return 'pattern', v[1:-1], None
	if kind == 'list':  # synthetic compatibility if constructed directly
		return 'list', [value(a) for a in v], None
	if kind == 'expr':
		raw = v.strip()
		if not raw or raw[0] not in '([{':
			return 'word', raw, 'write a value: number, "string", on/off, [list], (tuple), or {key: value}'
		try:
			norm = _prep_python_expr(raw, allow_opt=False)
			body = ast.parse(norm, mode='eval').body
		except (_ParseProblem, SyntaxError):
			if raw.startswith('(') and ',' not in raw:
				return 'tuple', None, 'use [a, b] for a list, or (a, b) with commas for a tuple'
			return {'[': 'list', '(': 'tuple', '{': 'dict'}[raw[0]], None, 'invalid {} literal: write valid Python/JS syntax (for example [1, 2], (0.5, 2.0), or {{Light: 20, Heavy: 48}})'.format({'[': 'list', '(': 'tuple', '{': 'dict'}[raw[0]])
		if raw.startswith('(') and not isinstance(body, ast.Tuple):
			return 'tuple', None, 'a single-item tuple needs a trailing comma: write (x,), or [x] for a list'
		try:
			val = _eval_ast_val(body)
		except _ParseProblem as e:
			return {'[': 'list', '(': 'tuple', '{': 'dict'}[raw[0]], None, str(e)
		if isinstance(body, ast.List):
			return 'list', val, None
		if isinstance(body, ast.Tuple):
			return 'tuple', val, None
		if isinstance(body, ast.Dict):
			return 'dict', val, None
		return 'word', val, 'invalid literal value'
	mapped = {'true': True, 'false': False, 'on': True, 'off': False, 'none': None}
	if v in ('on', 'off'):
		return 'switch', v == 'on', None
	return 'word', mapped.get(v, v), None


def value(arg):
	_, val, err = parse_literal(arg)
	if err is not None:
		return arg[1] if isinstance(arg, tuple) else arg
	return val


def _flatten_bitor(node):
	if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
		return _flatten_bitor(node.left) + _flatten_bitor(node.right)
	return [node]


def _lit_const(node):
	if isinstance(node, ast.Constant):
		if isinstance(node.value, (str, int, float, bool)) or node.value is None:
			return node.value
	if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant):
		v = node.operand.value
		if isinstance(v, (int, float)) and not isinstance(v, bool):
			return -v if isinstance(node.op, ast.USub) else +v
	if isinstance(node, ast.Name):
		if node.id in ('true', 'True'):
			return True
		if node.id in ('false', 'False'):
			return False
		if node.id in ('null', 'none', 'None'):
			return None
	raise _ParseProblem('not a literal')


def _subscript_args(node, src):
	if not isinstance(node.slice, ast.Tuple):
		return [node.slice]
	seg = ast.get_source_segment(src, node) if src else None
	if seg and '[' in seg and seg.endswith(']'):
		inner = seg[seg.index('[') + 1:-1].strip()
		if inner.startswith('(') and _scan_balanced(inner, 0, 0) == len(inner):
			return [node.slice]
	return list(node.slice.elts)


def _ast_to_type_ir(node, src=''):
	if isinstance(node, ast.Name):
		if node.id in BASE_TYPES:
			return ('base', node.id)
		if node.id in ('None', 'null', 'none'):
			return ('null',)
		raise _ParseProblem('type "{}" is not known: use {}, list[T], tuple[T1, T2], dict[str, T], {{field: T}}, T?, or "a" | "b"'.format(node.id, ', '.join(BASE_TYPES)))
	if isinstance(node, ast.Constant) or (isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd))):
		v = _lit_const(node)
		return ('null',) if v is None else ('lit', v)
	if isinstance(node, ast.Subscript):
		if not isinstance(node.value, ast.Name):
			raise _ParseProblem('a generic type starts with list, tuple, dict, or Literal')
		head = node.value.id
		elts = _subscript_args(node, src)
		if head == 'list':
			if len(elts) != 1:
				raise _ParseProblem('list[T] takes one type')
			return ('list', _ast_to_type_ir(elts[0], src))
		if head == 'tuple':
			if not elts:
				raise _ParseProblem('tuple[T1, T2, ...] needs types')
			return ('tuple', [_ast_to_type_ir(e, src) for e in elts])
		if head == 'dict':
			if len(elts) == 1:
				return ('dict_of', _ast_to_type_ir(elts[0], src))
			if len(elts) == 2:
				kt = _ast_to_type_ir(elts[0], src)
				if kt[0] != 'base' or kt[1] not in ('str', 'text', 'word', 'path', 'any'):
					raise _ParseProblem('dict[K, V] key type must be str (JSON object keys are strings)')
				return ('dict_of', _ast_to_type_ir(elts[1], src))
			raise _ParseProblem('write dict[str, T]')
		if head == 'Literal':
			if not elts:
				raise _ParseProblem('Literal[...] needs values')
			vals = []
			for e in elts:
				vals.append(e.id if isinstance(e, ast.Name) and e.id not in ('true', 'True', 'false', 'False', 'null', 'none', 'None') else _lit_const(e))
			return ('enum', vals)
		raise _ParseProblem('type "{}[...]" is not known: use list[T], tuple[T1, T2], dict[str, T], or Literal[...]'.format(head))
	if isinstance(node, ast.Tuple):
		if not node.elts:
			raise _ParseProblem('tuple type needs at least one type')
		return ('tuple', [_ast_to_type_ir(e, src) for e in node.elts])
	if isinstance(node, ast.Dict):
		if not node.keys:
			raise _ParseProblem('record type {} needs at least one field (use dict for any object)')
		fields, seen = [], set()
		for k_node, v_node in zip(node.keys, node.values):
			if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
				raise _ParseProblem('a record field name must be a word or string')
			raw_k = k_node.value
			opt = raw_k.startswith('__opt__')
			fname = raw_k[7:] if opt else raw_k
			if not fname:
				raise _ParseProblem('empty record field name')
			if fname in seen:
				raise _ParseProblem('duplicate field "{}" in record type'.format(fname))
			seen.add(fname)
			ft = _ast_to_type_ir(v_node, src)
			if opt and not _ir_nullable(ft):
				ft = ('nullable', ft)
			elif _ir_nullable(ft):
				opt = True
			fields.append((fname, ft, opt))
		return ('record', fields)
	if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
		parts = [_ast_to_type_ir(x, src) for x in _flatten_bitor(node)]
		has_null = any(p[0] == 'null' for p in parts)
		non_null = [p for p in parts if p[0] != 'null']
		if not non_null:
			return ('null',)
		if all(p[0] in ('lit', 'enum') for p in non_null):
			vals = []
			for p in non_null:
				for x in ([p[1]] if p[0] == 'lit' else p[1]):
					if x not in vals:
						vals.append(x)
			enum_ir = ('enum', vals)
			return ('nullable', enum_ir) if has_null else enum_ir
		if len(non_null) == 1 and has_null:
			return ('nullable', non_null[0])
		branches = list(non_null) + ([('null',)] if has_null else [])
		return ('union', branches)
	raise _ParseProblem('invalid type syntax: use {}, list[T], tuple[T1, T2], dict[str, T], {{field: T}}, T?, or "a" | "b"'.format(', '.join(BASE_TYPES)))


def _ir_nullable(ir):
	if ir is None:
		return False
	if ir[0] in ('null', 'nullable'):
		return True
	if ir[0] == 'union':
		return any(_ir_nullable(b) for b in ir[1])
	return False


def parse_type(t):
	'''Parse a type string or token -> (ir, error_or_None).'''
	if t is None:
		return None, None
	raw = (ser(t) if isinstance(t, tuple) else str(t)).strip()
	if not raw:
		return None, 'empty type'
	m_leg = re.match(r'^\(\s*(list|tuple|record|maybe|one-of)\b', raw)
	if m_leg:
		return None, LEGACY_TYPES[m_leg.group(1)]
	if raw.startswith('(') and ',' not in raw:
		return None, 'write tuple[T1, T2] or (T1, T2) with commas for a tuple type'
	try:
		norm = _prep_python_expr(raw, allow_opt=True)
		body = ast.parse(norm, mode='eval').body
		return _ast_to_type_ir(body, norm), None
	except _ParseProblem as e:
		return None, str(e)
	except SyntaxError:
		return None, 'invalid type "{}": use {}, list[T], tuple[T1, T2], dict[str, T], {{field: T}}, T?, or "a" | "b"'.format(raw, ', '.join(BASE_TYPES))


def is_optional(t):
	ir, err = parse_type(t)
	return False if err or ir is None else _ir_nullable(ir)


is_maybe = is_optional


def type_problem(t):
	'''-> None, or a short text that says what is wrong with the type.'''
	_, err = parse_type(t)
	return err


def _val_eq(a, b):
	if isinstance(a, bool) or isinstance(b, bool):
		return type(a) is type(b) and a == b
	if isinstance(a, (int, float)) and isinstance(b, (int, float)):
		return a == b
	return type(a) is type(b) and a == b


def _ir_ok(v, ir):
	kind = ir[0]
	if kind == 'base':
		w = ir[1]
		if w in ('str', 'text', 'word', 'path'):
			return isinstance(v, str)
		if w == 'int':
			return isinstance(v, int) and not isinstance(v, bool)
		if w == 'float':
			return isinstance(v, (int, float)) and not isinstance(v, bool)
		if w == 'bool':
			return isinstance(v, bool)
		if w == 'list':
			return isinstance(v, list)
		if w == 'dict':
			return isinstance(v, dict)
		return True
	if kind == 'null':
		return v is None
	if kind == 'lit':
		return _val_eq(v, ir[1])
	if kind == 'enum':
		return any(_val_eq(v, x) for x in ir[1])
	if kind == 'nullable':
		return v is None or _ir_ok(v, ir[1])
	if kind == 'list':
		return isinstance(v, list) and all(_ir_ok(x, ir[1]) for x in v)
	if kind == 'tuple':
		return isinstance(v, (list, tuple)) and len(v) == len(ir[1]) and all(_ir_ok(x, tt) for x, tt in zip(v, ir[1]))
	if kind == 'dict_of':
		return isinstance(v, dict) and all(isinstance(k, str) and _ir_ok(val, ir[1]) for k, val in v.items())
	if kind == 'record':
		if not isinstance(v, dict):
			return False
		known = set(fname for fname, _, _ in ir[1])
		if any(k not in known for k in v):
			return False
		for fname, ft, opt in ir[1]:
			if fname not in v:
				if not opt:
					return False
			elif not _ir_ok(v[fname], ft):
				return False
		return True
	if kind == 'union':
		return any(_ir_ok(v, b) for b in ir[1])
	return True


def type_ok(v, t):
	'''Does the value v (as JSON gives it) match the type t?'''
	if t is None:
		return True
	ir, err = parse_type(t)
	return True if (err or ir is None) else _ir_ok(v, ir)


def _ir_schema(ir):
	kind = ir[0]
	if kind == 'base':
		return {'str': {'type': 'string'}, 'text': {'type': 'string'}, 'word': {'type': 'string'}, 'path': {'type': 'string'},
			'int': {'type': 'integer'}, 'float': {'type': 'number'}, 'bool': {'type': 'boolean'},
			'list': {'type': 'array'}, 'dict': {'type': 'object'}}.get(ir[1], {})
	if kind == 'null':
		return {'type': 'null'}
	if kind == 'lit':
		return {'enum': [ir[1]]}
	if kind == 'enum':
		return {'enum': list(ir[1])}
	if kind == 'nullable':
		return {'anyOf': [_ir_schema(ir[1]), {'type': 'null'}]}
	if kind == 'list':
		return {'type': 'array', 'items': _ir_schema(ir[1])}
	if kind == 'tuple':
		return {'type': 'array', 'prefixItems': [_ir_schema(x) for x in ir[1]], 'minItems': len(ir[1]), 'maxItems': len(ir[1])}
	if kind == 'dict_of':
		return {'type': 'object', 'additionalProperties': _ir_schema(ir[1])}
	if kind == 'record':
		props, req = {}, []
		for fname, ft, opt in ir[1]:
			props[fname] = _ir_schema(ft)
			if not opt:
				req.append(fname)
		return {'type': 'object', 'properties': props, 'required': req, 'additionalProperties': False}
	if kind == 'union':
		return {'anyOf': [_ir_schema(b) for b in ir[1]]}
	return {}


def type_schema(t):
	'''A type string or token -> JSON Schema.'''
	if t is None:
		return {}
	ir, err = parse_type(t)
	return {} if (err or ir is None) else _ir_schema(ir)


def out_type_str(n):
	'''Type string from a step/reason "out" child node.'''
	return ' '.join(ser(a) for a in n.args).strip() if n.args else None


def in_parts(n):
	'''An "in" or "out" node -> (name, type string or None, text). An "out" node: the name is None.'''
	name = n.word(0) if n.head == 'in' else None
	rest = n.args[1:] if n.head == 'in' else n.args
	if not rest:
		return name, None, ''
	if len(rest) == 1 and rest[0][0] == 'str':
		return name, None, value(rest[0])
	if len(rest) >= 2 and rest[-1][0] == 'str' and rest[-2] != ('word', '|'):
		t_args, text = rest[:-1], value(rest[-1])
	else:
		t_args, text = rest, ''
	t_str = ' '.join(ser(a) for a in t_args).strip() or None
	return name, t_str, text


def seconds(word):
	'''"5m" -> 300; None for a word that is not a time.'''
	m = TIME.match(word or '')
	return int(m.group(1)) * SECONDS[m.group(2)] if m else None


def choice_val(tok):
	'''A choice option or value token as a string (keeping unquoted words like off/true/none as strings).'''
	if tok is None:
		return None
	return value(tok) if tok[0] == 'str' else ser(tok)


def options_of(n):
	'''The values of an "options" line: "a | b | c", or "a b c" for one-word values.'''
	toks = [choice_val(a) for a in n.args]
	if '|' in toks:
		out, cur = [], []
		for t in toks + ['|']:
			if t == '|':
				out.append(' '.join(cur))
				cur = []
			else:
				cur.append(t)
		return out
	return toks


# - The flow: nodes and blocks ------------------------
def units(root):
	return [u for u in root.children if u.head == 'unit']


def items(n):
	'''The flow items of a unit or a block: its steps, reasons, gates, ends and blocks, in order.'''
	return [c for c in n.children if c.head in ITEMS and not (c.head == 'if' and n.head in ('step', 'reason', 'gate'))]


def walk_items(n):
	'''Every flow item under n, in file order.'''
	out = []
	for c in items(n):
		out.append(c)
		out.extend(walk_items(c))
	return out


def flow_nodes(u):
	return [c for c in walk_items(u) if c.head in FLOW]


def has_flow(u):
	return bool(items(u))


def block_ids(u):
	'''A readable id for each block: "for:page", "until:sort.done", "if:sort.new", "section:Output", "finally".'''
	out, used = {}, set()
	for b in walk_items(u):
		if b.head not in BLOCKS:
			continue
		if b.head == 'for':
			base = 'for:' + (b.word(0) or '?')
		elif b.head == 'section':
			base = 'section:' + ((value(b.args[0]) if b.args and b.args[0][0] == 'str' else b.word(0)) or '?')
		elif b.head in ('finally', 'rollback'):
			base = b.head
		elif b.head == 'else':  # named after its "if": the line before it
			sib = items(b.parent)
			k = next(i for i, x in enumerate(sib) if x is b)
			base = 'else:' + (sib[k - 1].word(0) if k and sib[k - 1].head == 'if' and sib[k - 1].word(0) else '?')
		else:
			base = b.head + ':' + (b.word(0) or '?')
		bid, k = base, 2
		while bid in used:
			bid, k = '{}~{}'.format(base, k), k + 1
		used.add(bid)
		out[id(b)] = bid
	return out


def item_id(n, bids):
	return bids[id(n)] if n.head in BLOCKS else n.word(0)


# - Code outside the .rig file: "code [prefix] path", with an optional "test path" child ---
class Ctx(object):
	'''The units that "by" can reach: the units of the file, and of the files in "uses" lines.'''

	def __init__(self, root, path=None):
		self.units, self.files, self.base = {}, set(), {}
		self._texts, self._asts = {}, {}
		self.add(root, path)

	def read_text(self, path):
		p = os.path.normpath(os.path.abspath(path))
		if p not in self._texts:
			self._texts[p] = read_text(p)
		return self._texts[p]

	def parse_py(self, path):
		p = os.path.normpath(os.path.abspath(path))
		if p not in self._asts:
			text = self.read_text(p)
			if text is None:
				self._asts[p] = None
			else:
				try:
					self._asts[p] = ast.parse(text, filename=p)
				except SyntaxError:
					self._asts[p] = False
		return self._asts[p]

	def add(self, root, path):
		base = os.path.dirname(os.path.abspath(path)) if path else None
		if path:
			expand_external_rules(root, path)
		for u in units(root):
			if u.word(0) not in self.units:
				self.units[u.word(0)] = u
				self.base[u.word(0)] = base
			for sf in getattr(u, '_sidecar_files', ()):
				self.files.add(sf)


def _py_expr_str(val, as_tuple=False):
	if isinstance(val, bool):
		return 'True' if val else 'False'
	if val is None:
		return 'None'
	if isinstance(val, (int, float)):
		return repr(val)
	if isinstance(val, str):
		return json.dumps(val, ensure_ascii=False)
	if isinstance(val, (list, tuple)):
		inner = ', '.join(_py_expr_str(x) for x in val)
		if as_tuple:
			return '({},)'.format(inner) if len(val) == 1 else '({})'.format(inner)
		return '[{}]'.format(inner)
	if isinstance(val, dict):
		return '{' + ', '.join('{}: {}'.format(json.dumps(str(k), ensure_ascii=False), _py_expr_str(v)) for k, v in val.items()) + '}'
	return json.dumps(str(val), ensure_ascii=False)


def _json_val_to_tok(val, explicit_type=None, has_options=False):
	'''Convert a Python/JSON rule value into a rig.py token (kind, text).'''
	if has_options or explicit_type == 'choice':
		if isinstance(val, bool):
			return ('word', 'true' if val else 'false')
		if val is None:
			return ('word', 'none')
		if isinstance(val, str):
			return ('str', json.dumps(val, ensure_ascii=False)) if (' ' in val or not val or val in ('|',)) else ('word', val)
		return ('word', str(val))
	if explicit_type == 'switch' or (explicit_type is None and isinstance(val, bool)):
		if isinstance(val, bool):
			return ('word', 'on' if val else 'off')
		return ('str', json.dumps(str(val), ensure_ascii=False))
	if explicit_type in ('tuple', 'range'):
		if isinstance(val, (list, tuple)):
			return ('expr', _py_expr_str(val, as_tuple=True))
		return ('str', json.dumps(str(val), ensure_ascii=False))
	if explicit_type in ('dict', 'per_master') or (explicit_type is None and isinstance(val, dict)):
		if isinstance(val, dict):
			return ('expr', _py_expr_str(val, as_tuple=False))
		return ('str', json.dumps(str(val), ensure_ascii=False))
	if explicit_type == 'list' or (explicit_type is None and isinstance(val, list)):
		if isinstance(val, list):
			return ('expr', _py_expr_str(val, as_tuple=False))
		return ('str', json.dumps(str(val), ensure_ascii=False))
	if explicit_type == 'number' or (explicit_type is None and isinstance(val, (int, float)) and not isinstance(val, bool)):
		if isinstance(val, (int, float)) and not isinstance(val, bool):
			return ('num', repr(val) if isinstance(val, float) else str(val))
		return ('str', json.dumps(str(val), ensure_ascii=False))
	if explicit_type == 'pattern':
		if isinstance(val, str):
			return ('re', '/' + val + '/')
		return ('str', json.dumps(str(val), ensure_ascii=False))
	if val is None:
		return ('str', '""')
	return ('str', json.dumps(str(val), ensure_ascii=False))


def expand_external_rules(root, path=None, sidecars=None):
	'''Load any external `rules "<path>.json"` declarations on units of root relative to path.'''
	base = os.path.dirname(os.path.abspath(path)) if path else getattr(root, 'base', None)
	if not base:
		return root
	norm_base = os.path.normpath(base)
	if sidecars is None and getattr(root, '_expanded_base', None) == norm_base:
		return root
	key = (norm_base, json.dumps(sidecars, sort_keys=True) if sidecars else None)
	if getattr(root, '_expanded_key', None) == key:
		return root
	root.base = base
	root._expanded_base = norm_base
	root._expanded_key = key
	known_types = {'switch': 'switch', 'choice': 'choice', 'number': 'number', 'tuple': 'tuple', 'range': 'tuple',
		'list': 'list', 'dict': 'dict', 'per_master': 'dict', 'pattern': 'pattern', 'text': 'text'}
	for u in units(root):
		u.base = base
		u.children = [c for c in u.children if not getattr(c, 'from_json', None)]
		u._sidecar_errors = []
		u._sidecar_files = []
		new_children = []
		for c in u.children:
			new_children.append(c)
			if c.head != 'rules' or len(c.args) != 1 or c.args[0][0] != 'str':
				continue
			rel = value(c.args[0])
			jpath = os.path.normpath(os.path.join(base, rel))
			u._sidecar_files.append(jpath)
			if not os.path.exists(jpath):
				u._sidecar_errors.append((c.line, 'the rules file "{}" does not exist'.format(rel)))
				continue
			raw = read_text(jpath)
			if raw is None:
				u._sidecar_errors.append((c.line, 'could not read rules file "{}"'.format(rel)))
				continue
			try:
				data = json.loads(raw)
			except ValueError as e:
				u._sidecar_errors.append((c.line, 'rules file "{}": invalid JSON ({})'.format(rel, e)))
				continue
			if isinstance(data, list):
				raw_rules, raw_presets = data, {}
			elif isinstance(data, dict):
				raw_rules = data.get('rules', [])
				raw_presets = data.get('presets', {})
				if not isinstance(raw_rules, list) or not isinstance(raw_presets, dict):
					u._sidecar_errors.append((c.line, 'rules file "{}": expected "rules" list and optional "presets" object'.format(rel)))
					continue
			else:
				u._sidecar_errors.append((c.line, 'rules file "{}": expected a JSON object or array'.format(rel)))
				continue
			sc_map = (sidecars or {}).get(rel) or {}
			inline_by_id = dict((r.word(0), r) for r in u.children if r.head == 'rule' and r.word(0))
			loaded_by_id = {}
			for idx, entry in enumerate(raw_rules):
				if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
					u._sidecar_errors.append((c.line, 'rules file "{}" item {}: expected object with string "id"'.format(rel, idx)))
					continue
				rid = entry['id']
				raw_type = entry.get('type')
				if raw_type is not None and raw_type not in known_types:
					u._sidecar_errors.append((c.line, 'rules file "{}" rule "{}": unknown type "{}"'.format(rel, rid, raw_type)))
					continue
				norm_type = known_types.get(raw_type)
				has_opts = isinstance(entry.get('options'), list) and len(entry['options']) > 0
				val = entry['value'] if 'value' in entry else entry.get('default')
				if raw_type == 'range' and (not isinstance(val, list) or len(val) != 2):
					u._sidecar_errors.append((c.line, 'rules file "{}" rule "{}": type "range" needs a 2-item [min, max] list'.format(rel, rid)))
					continue
				if rid in sc_map:
					try:
						ov_toks = tokenize(str(sc_map[rid]).strip(), c.line)
						val_tok = ov_toks[0] if len(ov_toks) == 1 else ('str', json.dumps(str(sc_map[rid]), ensure_ascii=False))
					except RigError as e:
						u._sidecar_errors.append((c.line, 'rule "{}": {}'.format(rid, str(e).split(': ', 1)[-1])))
						continue
				else:
					val_tok = _json_val_to_tok(val, explicit_type=raw_type, has_options=has_opts)
				rargs = [('word', rid), val_tok]
				if isinstance(entry.get('label'), str) and entry['label']:
					rargs.append(('str', json.dumps(entry['label'], ensure_ascii=False)))
				rnode = Node('rule', rargs, c.line, c.indent)
				rnode.parent = u
				rnode.from_json = rel
				rnode.json_path = jpath
				if norm_type and not has_opts:
					rnode.explicit_type = norm_type
				has_lo = 'min' in entry and entry['min'] is not None
				has_hi = 'max' in entry and entry['max'] is not None
				if has_lo or has_hi:
					lo_tok = _json_val_to_tok(entry['min'], 'number') if has_lo else ('word', '_')
					hi_tok = _json_val_to_tok(entry['max'], 'number') if has_hi else ('word', '_')
					g = Node('range', [lo_tok, hi_tok], c.line, c.indent + 2)
					g.parent = rnode
					rnode.children.append(g)
				if 'options' in entry:
					if not isinstance(entry['options'], list) or not entry['options']:
						u._sidecar_errors.append((c.line, 'rules file "{}" rule "{}": "options" must be a non-empty list'.format(rel, rid)))
					else:
						opt_args = []
						for oi, ov in enumerate(entry['options']):
							if oi:
								opt_args.append(('word', '|'))
							opt_args.append(('str', json.dumps(str(ov), ensure_ascii=False)))
						onode = Node('options', opt_args, c.line, c.indent + 2)
						onode.parent = rnode
						rnode.children.append(onode)
				if entry.get('ui'):
					ui_val = entry['ui']
					uargs = [('word', ui_val)] if isinstance(ui_val, str) and ui_val not in ('true', '') else []
					uinode = Node('ui', uargs, c.line, c.indent + 2)
					uinode.parent = rnode
					rnode.children.append(uinode)
				if isinstance(entry.get('note'), str) and entry['note'].strip():
					nnode = Node('note', [('str', json.dumps(entry['note'], ensure_ascii=False))], c.line, c.indent + 2)
					nnode.parent = rnode
					rnode.children.append(nnode)
				new_children.append(rnode)
				loaded_by_id[rid] = rnode
			for pname, pmap in raw_presets.items():
				if not isinstance(pmap, dict):
					u._sidecar_errors.append((c.line, 'rules file "{}" preset "{}": expected an object of rule overrides'.format(rel, pname)))
					continue
				pnode = Node('preset', [('word', str(pname))], c.line, c.indent)
				pnode.parent = u
				pnode.from_json = rel
				pnode.json_path = jpath
				for prid, pval in pmap.items():
					ref_r = loaded_by_id.get(prid) or inline_by_id.get(prid)
					rt = rule_type(ref_r) if ref_r is not None else None
					ptok = _json_val_to_tok(pval, explicit_type=rt, has_options=(rt == 'choice'))
					snode = Node('set', [('word', str(prid)), ptok], c.line, c.indent + 2)
					snode.parent = pnode
					pnode.children.append(snode)
				new_children.append(pnode)
		u.children = new_children
	return root


def ctx_of(u, ctx=None):
	return ctx or Ctx(getattr(u, 'root', None) or Node('file', [], 0, -1))


def lowest(levels):
	return min(levels, key=LEVELS.index) if levels else 'none'


DEFINES = r'(?:\bdef|\bfunction|\bconst|\blet|\bvar)\s+{}\b'


def code_lines(u):
	'''The "code" lines of a unit -> list of {"prefix" (None: the unit's own function), "file", "test", "line"}.'''
	out = []
	for c in u.kids('code'):
		own = len(c.args) < 2
		t = c.kids('test')
		out.append({'prefix': None if own else c.word(0), 'file': c.word(0 if own else 1), 'test': t[0].word(0) if t else None, 'line': c.line})
	return out


def code_for(b, u):
	'''The "code" line that holds the name b -> (line, function name), or None.
	b is "prefix.function", or the name of the unit (its own function).'''
	for c in code_lines(u):
		if c['prefix'] is None and b == u.word(0):
			return c, b.replace('-', '_')
		if c['prefix'] and b.startswith(c['prefix'] + '.') and len(b) > len(c['prefix']) + 1:
			return c, b[len(c['prefix']) + 1:].replace('-', '_')
	return None


def read_text(path):
	try:
		with open(path, encoding='utf-8') as f:
			return f.read()
	except (OSError, UnicodeDecodeError):
		return None


def py_defines(tree, fn):
	'''Does the Python AST define a function named fn?'''
	return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn for n in ast.walk(tree))


def py_references(tree, fn):
	'''Does the Python AST reference fn as code (Name or Attribute), not only in comments or strings?'''
	return any((isinstance(n, ast.Name) and n.id == fn) or (isinstance(n, ast.Attribute) and n.attr == fn) for n in ast.walk(tree))


def py_func_node(tree, fn):
	'''The FunctionDef or AsyncFunctionDef named fn in a Python AST (top-level first).'''
	for n in tree.body:
		if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn:
			return n
	for n in ast.walk(tree):
		if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn:
			return n
	return None


def py_func_reads(tree, fn):
	'''Rule ids passed as string constants to R(...) or R.get(...) inside fn (and same-module helpers it calls).'''
	funcs = dict((n.name, n) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
	start = funcs.get(fn) or py_func_node(tree, fn)
	if start is None:
		return []
	out, visited = [], set()

	def walk(node):
		if isinstance(node, ast.Call):
			rid = None
			if isinstance(node.func, ast.Name) and node.func.id == 'R' and node.args:
				a0 = node.args[0]
				if isinstance(a0, ast.Constant) and isinstance(a0.value, str) and RULE_ID.match(a0.value):
					rid = a0.value
			elif isinstance(node.func, ast.Attribute) and node.func.attr == 'get' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'R' and node.args:
				a0 = node.args[0]
				if isinstance(a0, ast.Constant) and isinstance(a0.value, str) and RULE_ID.match(a0.value):
					rid = a0.value
			if rid and rid not in out:
				out.append(rid)
			if isinstance(node.func, ast.Name) and node.func.id in funcs and node.func.id not in visited:
				visited.add(node.func.id)
				walk(funcs[node.func.id])
		for child in ast.iter_child_nodes(node):
			walk(child)

	visited.add(fn)
	walk(start)
	return out


def py_hardcoded_numbers(tree, fn):
	'''Hardcoded numeric literals inside a gate function, excluding -1/0/1, defaults, subscripts, range(), and round() precision.'''
	node = py_func_node(tree, fn) if isinstance(tree, ast.Module) else None
	if node is None:
		return []
	out = []

	def record(v):
		if v not in (-1, 0, 1) and v not in out:
			out.append(v)

	def walk(n):
		if isinstance(n, ast.Subscript):
			walk(n.value)
			return
		if isinstance(n, ast.Call):
			if isinstance(n.func, ast.Name) and n.func.id == 'range':
				return
			if isinstance(n.func, ast.Name) and n.func.id == 'round':
				if n.args:
					walk(n.args[0])
				return
			walk(n.func)
			for a in n.args:
				walk(a)
			for kw in n.keywords:
				walk(kw.value)
			return
		if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub) and isinstance(n.operand, ast.Constant) and isinstance(n.operand.value, (int, float)) and not isinstance(n.operand.value, bool):
			record(-n.operand.value)
			return
		if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
			record(n.value)
			return
		if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
			for d in n.decorator_list:
				walk(d)
			for s in n.body:
				walk(s)
			return
		if isinstance(n, ast.Lambda):
			walk(n.body)
			return
		for child in ast.iter_child_nodes(n):
			walk(child)

	walk(node)
	return out


def bound_level(b, u, ctx):
	'''The level of a name that a "code" line holds: none (the file or the function is missing),
	code (the function exists), tested (a test file names it). Without the folder of the file: code.'''
	c, fn = code_for(b, u)
	base = ctx.base.get(u.word(0)) if ctx else None
	if not base:
		return 'code'
	if not c['file']:
		return 'none'
	code_path = os.path.join(base, c['file'])
	if c['file'].endswith('.py'):
		tree = ctx.parse_py(code_path)
		if tree is None:
			return 'none'
		if isinstance(tree, ast.Module):
			if not py_defines(tree, fn):
				return 'none'
		else:
			text = ctx.read_text(code_path)
			if text is None or not re.search(DEFINES.format(re.escape(fn)), text):
				return 'none'
	else:
		text = ctx.read_text(code_path)
		if text is None or not re.search(DEFINES.format(re.escape(fn)), text):
			return 'none'
	if not c['test']:
		return 'code'
	test_path = os.path.join(base, c['test'])
	if c['test'].endswith('.py'):
		test_tree = ctx.parse_py(test_path)
		if test_tree is None:
			return 'code'
		if isinstance(test_tree, ast.Module):
			return 'tested' if py_references(test_tree, fn) else 'code'
		test = ctx.read_text(test_path)
		return 'tested' if test and re.search(r'\b{}\b'.format(re.escape(fn)), test) else 'code'
	test = ctx.read_text(test_path)
	return 'tested' if test and re.search(r'\b{}\b'.format(re.escape(fn)), test) else 'code'


def by_target(b, u):
	'''What a "by" name reaches: "bound" (a "code <prefix> <path>" line), "model", or None.'''
	if b == 'model':
		return 'model'
	if b and code_for(b, u):
		return 'bound'
	return None


def gate_level(g, u, ctx, seen=()):
	'''tested, code, none, model or human (spec, Section 2: the level of a gate).'''
	if g.word(1) in ('model', 'human'):
		return g.word(1)
	got = []
	for x in g.kids('by'):
		b, kind = x.word(0), by_target(x.word(0), u)
		if kind == 'bound':
			got.append(bound_level(b, u, ctx))
		else:
			got.append('none')
	return lowest(got)


def coverage(u, ctx=None):
	ctx = ctx_of(u, ctx)
	d = {'gates': 0, 'tested': 0, 'code': 0, 'model': 0, 'human': 0, 'none': 0}
	for g in flow_nodes(u):
		if g.head == 'gate':
			d['gates'] += 1
			lv = gate_level(g, u, ctx, (u.word(0),))
			d[lv if lv in d else 'none'] += 1
	return d


def unit_status(unit, ctx=None):
	'''A short list of status strings for one unit.'''
	out = []
	cv = coverage(unit, ctx)
	steps = [n for n in flow_nodes(unit) if n.head in ('step', 'reason')]
	if cv['gates']:
		parts = ['{} {}'.format(cv[k], k) for k in ('tested', 'code', 'model', 'human', 'none') if cv[k] or k in ('tested', 'model')]
		out.append('flow: {} gates, coverage {:.0%} ({})'.format(cv['gates'], float(cv['tested']) / cv['gates'], ', '.join(parts)))
	elif steps:
		out.append('flow: {} steps, no gates'.format(len(steps)))
	if any(c.head in MATRIX for c in unit.children) and not has_flow(unit):
		out.append('hole')
	return out or ['empty']


# - Rules, placeholders, presets --------------------
def walk_strings(n, skip=('example',)):
	'''Every string argument of n and its descendants -> list of (node, text).'''
	out = []

	def args(node, aa):
		for a in aa:
			if a[0] == 'str':
				out.append((node, value(a)))
			elif a[0] == 'list':
				args(node, a[1])

	def walk(node):
		if node.head in skip:
			return
		args(node, node.args)
		for c in node.children:
			walk(c)
	walk(n)
	return out


def placeholders(n):
	'''The rule ids named as {group.name} in the strings of n, in order, without repeats.'''
	out = []
	skip = ('example',) + (ITEMS if n.head in BLOCKS else ())
	for _, t in walk_strings(n, skip=skip):
		for m in PLACE.finditer(t):
			if m.group(1) not in out:
				out.append(m.group(1))
	return out


def node_reads(f, u=None, ctx=None):
	'''The rules that a step, reason or gate reads: its "reads" lines, placeholders in its strings,
	retry/budget/candidates rules, and R("group.name") calls inferred from bound Python code.'''
	out = []
	unit_rule_list = [r.word(0) for r in u.kids('rule') if r.word(0)] if u is not None else []
	byrule = dict((r.word(0), r) for r in u.kids('rule')) if u is not None else None
	for c in f.kids('reads'):
		for a in c.args:
			tok = a[1]
			if tok.endswith('.*') and u is not None:
				prefix = tok[:-1]
				for rid in unit_rule_list:
					if rid.startswith(prefix) and rid not in out:
						out.append(rid)
			elif tok not in out:
				out.append(tok)
	for rid in placeholders(f):
		target = rid
		if byrule is not None and rid not in byrule:
			base, _, _ = rid.rpartition('.')
			if base in byrule and rule_type(byrule[base]) == 'dict':
				target = base
		if target not in out:
			out.append(target)
	for kind in ('retry', 'budget', 'candidates'):
		for c in f.kids(kind):
			if c.args and c.args[0][0] == 'word' and c.word(0) not in out:
				out.append(c.word(0))
	if u is not None and ctx is not None:
		base = ctx.base.get(u.word(0))
		if base:
			refs = [b.word(0) for b in f.kids('by') if b.word(0)] + [a[1] for t in f.kids('tools') for a in t.args if a[0] == 'word']
			for ref in refs:
				cf = code_for(ref, u)
				if cf and cf[0]['file'] and cf[0]['file'].endswith('.py'):
					tree = ctx.parse_py(os.path.join(base, cf[0]['file']))
					if isinstance(tree, ast.Module):
						for rid in py_func_reads(tree, cf[1]):
							if rid not in out:
								out.append(rid)
	return out


def rule_label(r):
	'''The label of a rule: the string after its value.'''
	a = r.args[2] if len(r.args) > 2 else None
	return value(a) if a and a[0] == 'str' else None


def rule_range(r):
	'''-> (min, max) of the "range" line, or (None, None).'''
	g = r.kids('range')
	if not g or len(g[0].args) < 2:
		return None, None
	lo, hi = g[0].args[0], g[0].args[1]
	return (value(lo) if lo[0] == 'num' else None), (value(hi) if hi[0] == 'num' else None)


def rule_type(r):
	a = r.args[1] if len(r.args) > 1 else None
	if r.kids('options'):
		return 'choice'
	exp = getattr(r, 'explicit_type', None)
	if exp:
		return exp
	if a is None:
		return 'text'
	kind, _, err = parse_literal(a)
	if err is None and kind in ('switch', 'number', 'pattern', 'list', 'tuple', 'dict'):
		return kind
	if kind in ('list', 'tuple', 'dict'):
		return kind
	return 'text'


def _num_range_problem(v, lo, hi, prefix=''):
	if not isinstance(v, (int, float)) or isinstance(v, bool):
		return '{}use a number'.format(prefix)
	if lo is not None and v < lo:
		return '{}the value is below the range: at least {}'.format(prefix, lo)
	if hi is not None and v > hi:
		return '{}the value is above the range: at most {}'.format(prefix, hi)
	return None


def _slot_type_matches(dv, cv):
	if isinstance(dv, bool) or isinstance(cv, bool):
		return isinstance(dv, bool) and isinstance(cv, bool)
	if isinstance(dv, (int, float)):
		return isinstance(cv, (int, float))
	if isinstance(dv, str):
		return isinstance(cv, str)
	return True


def rule_problem(r, a):
	'''Is the value token a valid value for rule r? -> None or a short text.'''
	t = rule_type(r)
	if a is None:
		return 'no value'
	lo, hi = rule_range(r)
	has_range = lo is not None or hi is not None
	if t == 'switch':
		if has_range:
			return 'range is for numbers (or a list, tuple or dict of numbers)'
		return None if (a[0] == 'word' and a[1] in ('on', 'off')) else 'use on or off'
	if t == 'choice':
		if has_range:
			return 'range is for numbers (or a list, tuple or dict of numbers)'
		opts = options_of(r.kids('options')[0])
		if choice_val(a) not in opts:
			return 'use one of: ' + ', '.join(str(o) for o in opts)
		return None
	kind, v, err = parse_literal(a)
	if err is not None:
		return err
	if t == 'number':
		if kind != 'number':
			return 'use a number'
		return _num_range_problem(v, lo, hi)
	if t == 'tuple':
		if kind != 'tuple':
			return 'use a tuple, for example (0.5, 2.0)'
		def_a = r.args[1] if len(r.args) > 1 else None
		if def_a is not None and a is not def_a:
			_, def_v, def_err = parse_literal(def_a)
			if def_err is None and isinstance(def_v, list):
				if len(v) != len(def_v):
					return 'expected {} items in tuple, got {}'.format(len(def_v), len(v))
				for idx, (dv, cv) in enumerate(zip(def_v, v)):
					if not _slot_type_matches(dv, cv):
						return 'item {} of tuple does not match default type'.format(idx)
		if has_range:
			if not v:
				return 'a tuple with range needs at least one number'
			for idx, x in enumerate(v):
				p = _num_range_problem(x, lo, hi, 'item {}: '.format(idx))
				if p:
					return p
		return None
	if t == 'list':
		if kind != 'list':
			return 'use a list, for example ["a", "b"]'
		if has_range:
			for idx, x in enumerate(v):
				p = _num_range_problem(x, lo, hi, 'item {}: '.format(idx))
				if p:
					return p
		return None
	if t == 'dict':
		if kind != 'dict':
			return 'use a dict, for example {Light: 20, Heavy: 48}'
		if has_range:
			if not v:
				return 'a dict with range needs at least one entry'
			for k, x in v.items():
				p = _num_range_problem(x, lo, hi, 'key "{}": '.format(k))
				if p:
					return p
		return None
	if has_range:
		return 'range is for numbers (or a list, tuple or dict of numbers)'
	return None


# - Lowering: the order of the lines -> the edges that the runner follows ---
class Flow(object):
	'''The flow of a unit, with every edge made explicit.
	nodes:  id -> {"next", "fail": [{"to", "when", "continue"}], "back", "block", "loop"} for steps, gates, ends
	blocks: id -> {"kind", "block", "first", "next", "else", "body", ...}
	body:   the ids of the top items; start: the first id; final: the first id of "finally".
	The flow never jumps back: the only edges to an earlier line are the end of a loop body
	(back to its "for" or "until") and "retry" (back to the step before the gate).'''

	def __init__(self, u):
		self.u, self.bids = u, block_ids(u)
		self.nodes, self.blocks, self.problems = {}, {}, []  # problems: (line, text), found while lowering
		seq = items(u)
		fin = [x for x in seq if x.head == 'finally']
		rb = [x for x in seq if x.head == 'rollback']
		self.body = [item_id(x, self.bids) for x in seq]
		self.start = self.seq([x for x in seq if x.head not in ('finally', 'rollback')], None, None, None)
		self.rollback = None
		for r in rb:
			bid = self.bids[id(r)]
			self.rollback = self.seq(items(r), None, bid, None)
			self.blocks[bid] = {'kind': 'rollback', 'block': None, 'first': self.rollback, 'next': None, 'body': self.ids(r), 'node': r}
		self.final = None
		for f in fin:
			bid = self.bids[id(f)]
			self.final = self.seq(items(f), None, bid, None)
			self.blocks[bid] = {'kind': 'finally', 'block': None, 'first': self.final, 'next': None, 'body': self.ids(f), 'node': f}

	def ids(self, n):
		return [item_id(x, self.bids) for x in items(n)]

	def seq(self, seq, after, parent, loop):
		'''Lower one body. -> the id where it starts (after, when it is empty).'''
		groups, i = [], 0
		while i < len(seq):
			it = seq[i]
			if it.head == 'if' and i + 1 < len(seq) and seq[i + 1].head == 'else':
				groups.append((it, seq[i + 1]))
				i += 2
			else:
				if it.head == 'else':
					self.problems.append((it.line, '"else" must follow an "if" block at the same indent'))
				groups.append((it, None))
				i += 1
		entry = after
		prev = {}  # the nearest step or reason before each item in this body, past gates only: "retry" goes back to it
		for k, (it, _) in enumerate(groups):
			back = None
			for j in range(k - 1, -1, -1):
				h = groups[j][0].head
				if h in ('step', 'reason'):
					back = groups[j][0]
					break
				if h != 'gate':
					break
			prev[id(it)] = back
		for it, el in reversed(groups):
			entry = self.item(it, el, entry, parent, loop, prev.get(id(it)))
		return entry

	def fails(self, n, loop):
		out = []
		for c in n.kids('fail'):
			if c.word(0) != '->' or not c.word(1):
				continue
			d = {'to': c.word(1)}
			if len(c.args) > 2:
				d['when'] = value(c.args[2]) if c.args[2][0] == 'str' else ser(c.args[2])
			if d['to'] == 'continue':
				if loop is None:
					self.problems.append((c.line, '"fail -> continue" is only for a gate inside a "for" block'))
				else:
					d['to'], d['continue'] = loop, True
			out.append(d)
		return out

	def item(self, it, el, after, parent, loop, before):
		h = it.head
		if h in FLOW:
			nid = it.word(0)
			d = {'next': None if h == 'end' else after, 'fail': self.fails(it, loop), 'block': parent, 'loop': loop, 'node': it}
			if h == 'gate' and it.kids('retry'):
				if before is None:
					self.problems.append((it.kids('retry')[0].line, 'gate "{}": "retry" does the step before the gate again, but no step is before it in its block (only gates may stand between)'.format(nid)))
				else:
					d['back'] = before.word(0)
			self.nodes[nid] = d
			return nid
		bid = self.bids[id(it)]
		d = {'kind': h, 'block': parent, 'next': after, 'body': self.ids(it), 'node': it}
		if h == 'for':
			d['fail'] = self.fails(it, None)
			d['first'] = self.seq(items(it), bid, bid, bid)
		elif h == 'until':
			d['fail'] = self.fails(it, None)
			d['first'] = self.seq(items(it), bid, bid, loop)
		elif h == 'if':
			d['first'] = self.seq(items(it), after, bid, loop)
			if el is not None:
				ebid = self.bids[id(el)]
				d['else'] = self.seq(items(el), after, ebid, loop)
				d['else_block'] = ebid
				self.blocks[ebid] = {'kind': 'else', 'block': parent, 'first': d['else'], 'next': after, 'body': self.ids(el), 'node': el, 'if': bid}
			else:
				d['else'] = after
		elif h == 'section':
			d['first'] = self.seq(items(it), after, bid, loop)
			self.blocks[bid] = d
			return d['first']  # a section has no effect on a run: the flow goes straight into its body
		elif h in ('else', 'finally', 'rollback'):
			d['first'] = self.seq(items(it), after, bid, loop)
			self.blocks[bid] = d
			return d['first']
		self.blocks[bid] = d
		return bid

	def edges(self, x):
		'''Where the flow can go from the node or block x.'''
		if x in self.nodes:
			d = self.nodes[x]
			out = [d['next']] + [f['to'] for f in d['fail']] + [d.get('back')]
		elif x in self.blocks:
			d = self.blocks[x]
			out = [d.get('first'), d.get('next'), d.get('else')] + [f['to'] for f in d.get('fail', [])]
		else:
			out = []
		return [y for y in out if y]


# - Check --------------------------------------------
def count_problem(c, byrule, name, minimum=1):
	'''"<name> <n>" or "<name> <rule id>" (a number rule). -> None or the error.'''
	if len(c.args) == 1 and c.args[0][0] == 'num' and isinstance(value(c.args[0]), int) and value(c.args[0]) >= minimum:
		return None
	if len(c.args) == 1 and c.args[0][0] == 'word' and c.word(0) in byrule:
		return None if rule_type(byrule[c.word(0)]) == 'number' else '{} {}: the rule must be a number'.format(name, c.word(0))
	return 'write {} <n> (a whole number, {} or more) or {} <rule id> (a number rule)'.format(name, minimum, name)


def retry_problem(c, byrule):
	'''"retry <n>" or "retry <rule id>" (a number rule, so that a preset can change it). -> None or the error.'''
	return count_problem(c, byrule, 'retry', minimum=1)


def never_parts(n):
	'''A "never" node -> (text, gate_id or None). Supports: never "text" [-> <gate-id>].'''
	arrow = next((i for i, a in enumerate(n.args) if a[0] == 'word' and a[1] == '->'), None)
	left = n.args[:arrow] if arrow is not None else n.args
	gate = n.word(arrow + 1) if arrow is not None else None
	text = ' '.join(value(a) if a[0] == 'str' else ser(a) for a in left).strip()
	return text, gate


def intent_info(n):
	'''Structured intent of a unit or reason node -> {"text", "audience", "style", "never"} (only non-empty fields).'''
	intents = n.kids('intent')
	if not intents:
		return None
	text = ' '.join(text_of(x) for x in intents).strip()
	aud = ' '.join(text_of(a) for x in intents for a in x.kids('audience')).strip()
	sty = ' '.join(text_of(s) for x in intents for s in x.kids('style')).strip()
	nevers = []
	for x in intents:
		for nv in x.kids('never'):
			nt, ng = never_parts(nv)
			if nt:
				d = {'text': nt}
				if ng:
					d['gate'] = ng
				nevers.append(d)
	out = {}
	if text:
		out['text'] = text
	if aud:
		out['audience'] = aud
	if sty:
		out['style'] = sty
	if nevers:
		out['never'] = nevers
	return out or None


def removed(c, parent):
	'''-> the error text for a removed word, or None.'''
	if c.head == 'unit' and parent.head == 'rule':
		return '"unit" under a rule is a word of version 0: put the unit in the label. "unit" is only the container'
	if c.head == 'brief' and parent.head == 'gate':
		return '"brief" under a gate is a word of version 0: write check "text"'
	if c.head in REMOVED and not (c.head == 'check' and parent.head == 'probe'):
		return '"{}" is not in version 2: {}'.format(c.head, REMOVED[c.head])
	return None


def check(root, path=None, ctx=None):
	'''-> (errors, warnings): lists of (line, text). path: the file, to check the files of "code" lines.'''
	err, warn = [], []
	names = set()
	base = os.path.dirname(os.path.abspath(path)) if path else None
	if path:
		expand_external_rules(root, path)
	cctx = ctx or (Ctx(root, path) if path else None)
	for top in root.children:
		if top.head != 'unit':
			err.append((top.line, '"{}" at the top level: only "unit" is allowed'.format(top.head)))
	for u in units(root):
		name = u.word(0)
		if not name:
			err.append((u.line, 'a unit without a name'))
		elif name in names:
			err.append((u.line, 'unit "{}" is defined twice'.format(name)))
		names.add(name)
		if u.word(1) == 'snippet':
			err.append((u.line, 'the scope "snippet" is a word of version 0: write "unit {}" (every unit is a flow)'.format(name or '<name>')))
		elif u.word(1) in ('tool', 'agent'):
			err.append((u.line, 'scope "{}" was removed in version 2: write "unit {}" (every unit is a flow)'.format(u.word(1), name or '<name>')))
		elif u.word(1):
			err.append((u.line, 'unexpected "{}" after unit name: write "unit {}"'.format(u.word(1), name or '<name>')))

		def walk(n):
			allowed = CHILDREN.get(n.head)
			for c in n.children:
				bad = removed(c, n)
				if bad:
					err.append((c.line, bad))
				elif allowed is not None and c.head not in allowed:
					if c.head in ITEMS and n.head in NODE_KIDS:
						err.append((c.line, '"{}" under "{}": a node has no body. Indent the line as a sibling'.format(c.head, n.head)))
					else:
						warn.append((c.line, '"{}" is not a known word inside "{}"'.format(c.head, n.head)))
				walk(c)
		walk(u)
		for n in u.kids('in') + u.kids('out'):
			t = in_parts(n)[1]
			bad = type_problem(t) if t else None
			if bad:
				warn.append((n.line, bad))
		prefixes = [c['prefix'] for c in code_lines(u)]
		for c in code_lines(u):
			if not c['prefix'] or not c['file']:
				err.append((c['line'], 'write "code <prefix> <path>" (micro-level "code <path>" was removed in version 2)'))
			elif prefixes.count(c['prefix']) > 1:
				err.append((c['line'], 'two "code" lines for "{}"'.format(c['prefix'])))
			elif base:
				for k in ('file', 'test'):
					if c[k] and not os.path.exists(os.path.join(base, c[k])):
						err.append((c['line'], 'the {} file "{}" does not exist'.format('code' if k == 'file' else 'test', c[k])))

		# Rules and presets
		err.extend(getattr(u, '_sidecar_errors', ()))
		for rs in u.kids('rules'):
			if len(rs.args) == 1 and rs.args[0][0] == 'str':
				if rs.children:
					err.append((rs.children[0].line, 'rules "{}" takes no body'.format(value(rs.args[0]))))
			elif len(rs.args) == 1 and rs.args[0][0] == 'word' and GROUP_ID.match(rs.args[0][1]):
				warn.append((rs.line, '"rules {}" has no rules'.format(rs.args[0][1])))
			else:
				err.append((rs.line, 'write rules "<path>.json" or rules <group> (lowercase letters, digits and _)'))
		rules = set()
		byrule = {}
		for r in u.kids('rule'):
			if getattr(r, '_bad_compact', None):
				err.append((r.line, r._bad_compact))
				continue
			rid = r.word(0)
			if not rid or not RULE_ID.match(rid):
				err.append((r.line, 'rule id "{}": write it as group.name'.format(rid or '')))
				continue
			if rid in rules:
				err.append((r.line, 'rule "{}" is defined twice'.format(rid)))
			rules.add(rid)
			byrule.setdefault(rid, r)
			if len(r.args) > 2 and r.args[2][0] != 'str':
				err.append((r.line, 'rule "{}": after the value, only the label as a "string" (or <min>..<max> before it)'.format(rid)))
			elif len(r.args) > 3:
				err.append((r.line, 'rule "{}": write the value, then the label as one "string"'.format(rid)))
			if len(r.kids('range')) > 1:
				err.append((r.kids('range')[1].line, 'rule "{}": at most one range per rule'.format(rid)))
			for g in r.kids('range'):
				if len(g.args) != 2 or any(a[0] != 'num' and a != ('word', '_') for a in g.args):
					err.append((g.line, 'rule "{}": write range <min> <max>, two numbers (or _ for an open side)'.format(rid)))
				elif g.args[0] == ('word', '_') and g.args[1] == ('word', '_'):
					err.append((g.line, 'rule "{}": range needs at least one number (not _ and _)'.format(rid)))
				elif g.args[0][0] == 'num' and g.args[1][0] == 'num' and value(g.args[0]) > value(g.args[1]):
					err.append((g.line, 'rule "{}": the range starts above its end'.format(rid)))
			for ui in r.kids('ui'):
				if ui.args and ui.word(0) not in UI_CONTROLS:
					err.append((ui.line, 'rule "{}": ui control must be one of {}'.format(rid, ', '.join(UI_CONTROLS))))
			bad = rule_problem(r, r.args[1] if len(r.args) > 1 else None)
			if bad:
				err.append((r.line, 'rule "{}": {}'.format(rid, bad)))
		for n, t in walk_strings(u):
			for m in PLACE.finditer(t):
				ph = m.group(1)
				if ph in rules:
					continue
				base_r, _, key_r = ph.rpartition('.')
				if base_r in byrule and rule_type(byrule[base_r]) == 'dict':
					dval = value(byrule[base_r].args[1]) if len(byrule[base_r].args) > 1 else {}
					if isinstance(dval, dict) and key_r in dval:
						continue
					err.append((n.line, '{{{}}} names key "{}" which is not in dict rule "{}"'.format(ph, key_r, base_r)))
				else:
					err.append((n.line, '{{{}}} names a rule that is not defined in this unit'.format(ph)))
		# Validate structured intent children (unit-level and reason-level)
		intent_hosts = [u] + [f for f in flow_nodes(u) if f.head == 'reason'] if has_flow(u) else [u]
		flow_gates = dict((f.word(0), f) for f in flow_nodes(u) if f.head == 'gate' and f.word(0)) if has_flow(u) else {}
		for host in intent_hosts:
			for it in host.kids('intent'):
				for c in it.kids('audience') + it.kids('style'):
					if not text_of(c).strip():
						err.append((c.line, '"{}" needs text'.format(c.head)))
				for nv in it.kids('never'):
					nt, ng = never_parts(nv)
					if not nt:
						err.append((nv.line, '"never" needs text describing the boundary'))
					if ng is not None:
						g = flow_gates.get(ng)
						if g is None:
							err.append((nv.line, 'never -> "{}": no gate with this id'.format(ng)))
						elif g.word(1) == 'soft':
							err.append((nv.line, 'never -> "{}": a never boundary needs a hard, model or human gate, not soft'.format(ng)))
		pnames = set()
		for p in u.kids('preset'):
			pn = p.word(0)
			if not pn:
				err.append((p.line, 'a preset needs a name'))
			elif pn in pnames:
				err.append((p.line, 'preset "{}" is defined twice'.format(pn)))
			pnames.add(pn)
			for s in p.kids('set'):
				rid = s.word(0)
				if rid not in byrule:
					err.append((s.line, 'preset "{}" sets "{}", which is not a rule of this unit'.format(pn, rid)))
				else:
					bad = rule_problem(byrule[rid], s.args[1] if len(s.args) > 1 else None)
					if bad:
						err.append((s.line, 'preset "{}", rule "{}": {}'.format(pn, rid, bad)))

		def _check_reads_node(rd_node):
			for a in rd_node.args:
				tok = a[1]
				if tok.endswith('.*'):
					grp = tok[:-2]
					prefix = grp + '.'
					if not grp or not any((r or '').startswith(prefix) for r in rules):
						err.append((rd_node.line, 'no rules in group "{}"'.format(grp)))
				elif tok not in rules:
					err.append((rd_node.line, 'rule "{}" is not defined in this unit'.format(tok)))

		# Pluggable queue declaration
		queues = u.kids('queue')
		if len(queues) > 1:
			err.append((queues[1].line, 'at most one "queue" declaration per unit'))
		queue_reads = set()
		for q in queues:
			bys = q.kids('by')
			if not bys:
				err.append((q.line, 'queue needs "by <prefix.function>"'))
			for b in bys:
				t = by_target(b.word(0), u)
				if t != 'bound':
					warn.append((b.line, 'queue "by {}" names no "code" line: add "code <prefix> <path>"'.format(b.word(0))))
				elif base:
					c_line, fn = code_for(b.word(0), u)
					if bound_level(b.word(0), u, cctx) == 'none' and c_line['file'] and os.path.exists(os.path.join(base, c_line['file'])):
						err.append((b.line, '"{}" has no function "{}"'.format(c_line['file'], fn)))
			for rd in q.kids('reads'):
				_check_reads_node(rd)
			queue_reads.update(node_reads(q, u, cctx))

		# The flow
		if not has_flow(u):
			continue
		top = items(u)
		tail_start = len(top)
		for k in range(len(top) - 1, -1, -1):
			if top[k].head in ('finally', 'rollback'):
				tail_start = k
			else:
				break
		for k, it in enumerate(top):
			if it.head in ('finally', 'rollback') and k < tail_start:
				err.append((it.line, '"{}" must be at the end of the flow (the last block)'.format(it.head)))
		for hk in ('finally', 'rollback'):
			seen_hk = [x for x in top if x.head == hk]
			if len(seen_hk) > 1:
				err.append((seen_hk[1].line, 'at most one "{}" block per unit'.format(hk)))
		for it in walk_items(u):
			if it.head in ('finally', 'rollback') and it.parent is not u:
				err.append((it.line, '"{}" is a block of the unit, not of another block'.format(it.head)))
		nodes = flow_nodes(u)
		ids = {}
		for f in nodes:
			fid = f.word(0)
			if not fid:
				err.append((f.line, '"{}" needs an id'.format(f.head)))
			elif fid in RESERVED:
				err.append((f.line, '"{}" is a word of the language, not an id'.format(fid)))
			elif fid in ids:
				err.append((f.line, 'id "{}" is used twice'.format(fid)))
			ids[fid] = f
		ends = set(f.word(0) for f in nodes if f.head == 'end')
		fl = Flow(u)
		err += fl.problems
		read = set(queue_reads)
		for f in nodes:
			fid, kind = f.word(0), f.word(1) if f.head == 'gate' else f.head
			read.update(node_reads(f, u, cctx))
			for c in f.children:
				if c.head == 'reads':
					_check_reads_node(c)
				if c.head in PROSE:
					for _, t in walk_strings(c):
						if PROSE_NUMBER.search(PLACE.sub('', t)):
							warn.append((c.line, 'a number in the text of "{}": make it a rule and write {{group.name}}'.format(fid)))
							break
				if c.head == 'fail':
					if c.word(0) != '->' or not c.word(1):
						err.append((c.line, 'write "fail -> <end>"'))
					elif c.word(1) != 'continue' and c.word(1) not in ends:
						err.append((c.line, '"{}" fails to "{}": a fail goes to an end{}'.format(fid, c.word(1), ' (or continue)' if fl.nodes.get(fid, {}).get('loop') else '') if c.word(1) in ids else '"{}" fails to "{}", which does not exist'.format(fid, c.word(1))))
				if c.head == 'timeout' and seconds(c.word(0)) is None:
					err.append((c.line, 'write timeout <number><s|m|h|d>, for example timeout 5m'))
				if c.head == 'retry':
					bad = retry_problem(c, byrule)
					if bad:
						err.append((c.line, bad))
				if c.head == 'if' and (len(c.args) != 1 or not PATH.match(c.word(0) or '')):
					err.append((c.line, 'write if <path>: a path in the state of the run, not an expression'))
				if c.head == 'out':
					t = out_type_str(c)
					bad = type_problem(t) if t else 'write out <type>'
					if bad:
						err.append((c.line, bad))
				if c.head == 'brief':
					if not c.args or any(a[0] != 'word' for a in c.args):
						err.append((c.line, 'write brief <key>... (one or more output keys)'))
			if f.head == 'step':
				bys = [b.word(0) for b in f.kids('by')]
				if not bys:
					warn.append((f.line, 'step "{}": say who does it: "by <prefix.function>" for code, or "by model"'.format(fid)))
				if 'model' in bys and len(bys) > 1:
					err.append((f.line, 'step "{}": "by model" or code, not both'.format(fid)))
				if f.kids('out') and 'model' not in bys and bys:
					warn.append((f.kids('out')[0].line, 'step "{}": "out" gives the form of the answer of the model; code returns its own value'.format(fid)))
				if ('model' in bys or not bys) and not f.kids('do'):
					warn.append((f.line, 'step "{}" is done by the model, but has no "do" that says what to do'.format(fid)))
				if ('model' in bys or not bys) and not f.kids('out'):
					warn.append((f.line, 'step "{}": add "out <type>" (for example "out text") so the answer has a checked form'.format(fid)))
			if f.head == 'reason':
				if f.kids('by'):
					err.append((f.kids('by')[0].line, 'reason "{}": a reason block is cognitive and takes no "by" (use "tools" for read-only helpers, or "step" for code)'.format(fid)))
				for m in f.kids('mode'):
					if m.word(0) not in REASON_MODES:
						err.append((m.line, 'reason "{}": mode must be careful or creative'.format(fid)))
				if not f.kids('do'):
					warn.append((f.line, 'reason "{}" has no "do" that says what to reason about'.format(fid)))
				if not f.kids('out'):
					warn.append((f.line, 'reason "{}": add "out <type>" (for example "out text") so the answer has a checked form'.format(fid)))
				for b in f.kids('budget'):
					bad = count_problem(b, byrule, 'budget', minimum=1)
					if bad:
						err.append((b.line, bad))
				for c in f.kids('candidates'):
					bad = count_problem(c, byrule, 'candidates', minimum=2)
					if bad:
						err.append((c.line, bad))
				t_nodes = f.kids('tools')
				if t_nodes and not f.kids('budget'):
					warn.append((t_nodes[0].line, 'reason "{}": "tools" should have a hard "budget <n>" limit'.format(fid)))
				for tn in t_nodes:
					if not tn.args:
						err.append((tn.line, 'write tools <prefix.fn>...'))
					for a in tn.args:
						ref = a[1] if a[0] == 'word' else ''
						t = by_target(ref, u)
						if t != 'bound':
							warn.append((tn.line, 'tools "{}": names no "code" line: add "code <prefix> <path>"'.format(ref)))
						elif base:
							c_line, fn = code_for(ref, u)
							if bound_level(ref, u, cctx) == 'none' and c_line['file'] and os.path.exists(os.path.join(base, c_line['file'])):
								err.append((tn.line, '"{}" has no function "{}"'.format(c_line['file'], fn)))
			if f.head == 'gate':
				if kind == 'judge':
					err.append((f.line, 'gate "{}": "judge" is a word of version 0: write model'.format(fid)))
				elif kind not in GATE_KINDS:
					err.append((f.line, 'gate "{}": the kind must be hard, soft, model or human'.format(fid)))
				fails = f.kids('fail')
				if kind in ('hard', 'soft') and not f.kids('by'):
					warn.append((f.line, 'gate "{}" is {} but no code decides it: add "by", or make it model'.format(fid, kind)))
				if kind in ('model', 'human') and f.kids('by') and not f.kids('options'):
					err.append((f.kids('by')[0].line, 'gate "{}": a {} gate is decided by {}, not by code'.format(fid, kind, 'the model' if kind == 'model' else 'the person')))
				if kind == 'model' and not f.kids('check'):
					warn.append((f.line, 'model gate "{}" has no check: say what the model must decide'.format(fid)))
				if kind == 'human' and not f.kids('check') and len(f.args) < 3:
					warn.append((f.line, 'human gate "{}" has no question: write it as the name, gate {} human "Question?"'.format(fid, fid)))
				if kind == 'soft' and fails:
					err.append((fails[0].line, 'gate "{}" is soft: a fail is reported and the flow goes on. Remove the fail line, or make it hard'.format(fid)))
				if kind in ('hard', 'model') and not fails:
					err.append((f.line, 'gate "{}" has no fail line: write fail -> <end>'.format(fid)))
				if f.kids('options'):
					if kind != 'human':
						err.append((f.kids('options')[0].line, 'gate "{}": "options" is for a human gate'.format(fid)))
					elif not f.kids('by'):
						err.append((f.line, 'gate "{}": a gate with options needs "by": the code that reads the answer'.format(fid)))
					elif len(options_of(f.kids('options')[0])) < 2:
						err.append((f.kids('options')[0].line, 'gate "{}": give two or more options'.format(fid)))
				elif kind == 'human' and not fails:
					err.append((f.line, 'human gate "{}" has no fail line: write fail -> <end> for the answer no'.format(fid)))
				if kind == 'human' and f.kids('timeout') and not fails:
					err.append((f.kids('timeout')[0].line, 'gate "{}": after its timeout the gate fails; write fail -> <end> "timeout"'.format(fid)))
				if f.kids('retry') and kind not in ('hard', 'model'):
					err.append((f.kids('retry')[0].line, 'gate "{}": "retry" is for a hard or a model gate'.format(fid)))
				if f.kids('timeout') and kind not in ('model', 'human'):
					err.append((f.kids('timeout')[0].line, 'gate "{}": "timeout" is for a step, a model gate or a human gate'.format(fid)))
				for b in f.kids('by'):
					if b.word(0) == 'model':
						err.append((b.line, 'gate "{}": write "gate {} model", not "by model"'.format(fid, fid)))
		for f in nodes:
			for b in f.kids('by'):
				t = by_target(b.word(0), u)
				if t is None and b.word(0):
					warn.append((b.line, '"by {}" names no "code" line: add "code <prefix> <path>" for code in a file'.format(b.word(0))))
				elif base and t == 'bound':
					c, fn = code_for(b.word(0), u)
					level = bound_level(b.word(0), u, cctx)
					if level == 'none' and c['file'] and os.path.exists(os.path.join(base, c['file'])):
						err.append((b.line, '"{}" has no function "{}"'.format(c['file'], fn)))
					elif level == 'code' and f.head == 'gate':
						warn.append((b.line, 'no test names "{}": {}'.format(fn, 'add a test to "{}"'.format(c['test']) if c['test'] else 'add a "test <path>" line under its "code" line')))
					if f.head == 'gate' and level != 'none' and c['file'] and c['file'].endswith('.py') and not os.path.basename(c['file']).startswith('test_'):
						nums = py_hardcoded_numbers(cctx.parse_py(os.path.join(base, c['file'])), fn)
						if nums:
							shown = ', '.join(str(x) for x in nums[:5])
							warn.append((f.line, 'gate "{}": hardcoded number ({}) in "{}" ({}): make it a rule and read it with R(...)'.format(f.word(0), shown, c['file'], fn)))
		for it in walk_items(u):
			if it.head not in BLOCKS:
				continue
			read.update(node_reads(it, u, cctx))
			opts = BLOCK_OPTIONS.get(it.head, set())
			seen_body = False
			for c in it.children:
				if c.head in ITEMS:
					seen_body = True
				elif c.head in opts and seen_body:
					warn.append((c.line, 'write the options of "{}" before its body'.format(it.head)))
			if not items(it):
				warn.append((it.line, '"{}" has no body: indent the lines that belong to it'.format(it.head)))
			if it.head == 'for':
				w = [ser(a) for a in it.args]
				if len(w) != 3 or w[1] != 'in' or not PATH.match(w[0]) or not PATH.match(w[2]):
					err.append((it.line, 'write for <name> in <path>'))
				t = it.kids('tolerate')
				if t and not re.match(r'^\d+(\.\d+)?%$', t[0].word(0) or ''):
					err.append((t[0].line, 'write tolerate <n>%, for example tolerate 20%'))
			if it.head in ('until', 'if') and (len(it.args) != 1 or not PATH.match(it.word(0) or '')):
				err.append((it.line, 'write {} <path>: a path in the state of the run, not an expression'.format(it.head)))
			if it.head == 'until':
				if not it.kids('retry'):
					err.append((it.line, '"until" needs "retry <n>": the most rounds after the first'))
				for c in it.kids('retry'):
					bad = retry_problem(c, byrule)
					if bad:
						err.append((c.line, bad))
			for c in it.kids('fail'):
				if c.word(0) != '->' or c.word(1) not in ends:
					err.append((c.line, 'the fail of "{}" goes to an end: write fail -> <end>'.format(it.head)))
			if it.head in ('else', 'section', 'finally', 'rollback', 'if') and (it.kids('fail') or it.kids('retry') or it.kids('tolerate')):
				err.append((it.line, '"{}" has no options: only a body'.format(it.head)))
		# Reach: every node from the start (or from "rollback" / "finally")
		seen = set()
		todo = [x for x in (fl.start, fl.rollback, fl.final) if x]
		while todo:
			x = todo.pop()
			if x in seen:
				continue
			seen.add(x)
			todo.extend(fl.edges(x))
		for f in nodes:
			if f.word(0) and f.word(0) not in seen:
				warn.append((f.line, '"{}" cannot be reached from the start'.format(f.word(0))))
		last = [fl.start] if fl.start else []
		runs_off = any(d['next'] is None and fid in seen and ids.get(fid) is not None and ids[fid].head != 'end' and not (d['block'] and fl.blocks.get(d['block'], {}).get('kind') in ('finally', 'rollback'))
			for fid, d in fl.nodes.items())
		if runs_off and last:
			warn.append((u.line, 'the flow can run past its last line: end it with an "end" line'))
		for r in u.kids('rule'):
			if r.word(0) not in read:
				warn.append((r.line, 'rule "{}" is not read by any step, reason or gate'.format(r.word(0))))
	return err, warn


# - Compile: catalogue (JSON) ------------------------
def text_of(n):
	'''The arguments of a node as one text: strings without quotes, joined by one space.'''
	return ' '.join(value(a) if a[0] == 'str' else ser(a) for a in n.args)


def name_of(f):
	'''The display name of a step, gate, end or section: its string argument.'''
	k = 2 if f.head == 'gate' else 0 if f.head == 'section' else 1
	a = f.args[k] if len(f.args) > k else None
	if a is None:
		return ''
	return value(a) if a[0] == 'str' else ser(a)


def notes_of(n):
	return [{'text': text_of(x)} for x in n.kids('note')]


def rule_info(r, token=None):
	'''One rule as a catalogue entry. token: a preset value that replaces the value.'''
	a = r.args[1] if len(r.args) > 1 else None
	rtype = rule_type(r)
	vfn = choice_val if rtype == 'choice' else value
	def_val = vfn(a) if a else None
	cur_tok = token if token is not None else a
	d = {'id': r.word(0), 'group': r.word(0).split('.')[0], 'label': rule_label(r) or r.word(0),
		'type': rtype, 'value': vfn(cur_tok) if cur_tok else None,
		'default': def_val}
	if rtype == 'tuple' and isinstance(def_val, list):
		d['length'] = len(def_val)
	lo, hi = rule_range(r)
	if lo is not None:
		d['min'] = lo
	if hi is not None:
		d['max'] = hi
	if r.kids('options'):
		d['options'] = options_of(r.kids('options')[0])
	if r.kids('ui'):
		u_node = r.kids('ui')[0]
		default_ctrl = {'switch': 'toggle', 'choice': 'select', 'number': 'slider' if ('min' in d and 'max' in d) else 'number'}.get(d['type'], 'input')
		d['ui'] = u_node.word(0) or default_ctrl
	ns = notes_of(r)
	if ns:
		d['note'] = ' '.join(x['text'] for x in ns)
	return d


def presets_of(u):
	byrule = dict((r.word(0), r) for r in u.kids('rule'))
	out = {}
	for p in u.kids('preset'):
		pmap = {}
		for x in p.kids('set'):
			if len(x.args) > 1:
				rid = x.word(0)
				pmap[rid] = choice_val(x.args[1]) if (rid in byrule and rule_type(byrule[rid]) == 'choice') else value(x.args[1])
		out[p.word(0)] = pmap
	return out


def preset_tokens(u, preset):
	if not preset:
		return {}
	for p in u.kids('preset'):
		if p.word(0) == preset:
			return dict((x.word(0), x.args[1]) for x in p.kids('set') if len(x.args) > 1)
	raise SystemExit('unit "{}" has no preset "{}"'.format(u.word(0), preset))


def lane_of(f):
	'''Who decides a node: code, model or person (the bands of the viewer).'''
	if f.head == 'end':
		return 'end'
	if f.head == 'reason':
		return 'model'
	if f.head == 'gate':
		return {'model': 'model', 'human': 'person'}.get(f.word(1), 'code')
	bys = [b.word(0) for b in f.kids('by')]
	return 'model' if not bys or 'model' in bys else 'code'


def node_info(f, fl, u=None, ctx=None):
	d = {'id': f.word(0), 'kind': f.word(1) if f.head == 'gate' else f.head, 'lane': lane_of(f)}
	nm = name_of(f)
	if nm:
		d['name'] = nm
	if f.head == 'reason':
		d['mode'] = f.kids('mode')[0].word(0) if f.kids('mode') else 'careful'
		ispec = intent_info(f)
		if ispec:
			if ispec.get('text'):
				d['intent'] = ispec['text']
			if any(k in ispec for k in ('audience', 'style', 'never')):
				d['intent_spec'] = ispec
		tools = [a[1] for t in f.kids('tools') for a in t.args if a[0] == 'word']
		if tools:
			d['tools'] = tools
		if f.kids('budget') and f.kids('budget')[0].args:
			d['budget'] = value(f.kids('budget')[0].args[0])
		if f.kids('candidates') and f.kids('candidates')[0].args:
			d['candidates'] = value(f.kids('candidates')[0].args[0])
	for k in PROSE:
		xs = f.kids(k)
		if xs:
			d[k] = ' '.join(text_of(x) for x in xs)
	bys = [x.word(0) for x in f.kids('by') if x.word(0) != 'model']
	if bys:
		d['by'] = bys
	rd = node_reads(f, u, ctx)
	if rd:
		d['reads'] = rd
	sees = [a[1] for c in f.kids('sees') for a in c.args]
	if sees:
		d['sees'] = sees
	if f.kids('out') and f.kids('out')[0].args:
		t = out_type_str(f.kids('out')[0])
		d['out'], d['schema'] = t, type_schema(t)
	if f.kids('brief'):
		d['brief'] = [a[1] for c in f.kids('brief') for a in c.args if a[0] == 'word']
	if f.kids('options'):
		d['options'] = options_of(f.kids('options')[0])
	if f.kids('retry'):
		d['retry'] = value(f.kids('retry')[0].args[0])  # a number, or the id of a number rule
	if f.kids('timeout'):
		d['timeout'] = seconds(f.kids('timeout')[0].word(0))
		d['timeout_text'] = f.kids('timeout')[0].word(0)
	if f.kids('if'):
		d['if'] = f.kids('if')[0].word(0)
	low = fl.nodes.get(f.word(0), {})
	if low.get('fail'):
		d['fail'] = [dict((k, v) for k, v in x.items()) for x in low['fail']]
	if f.head != 'end':
		d['next'] = low.get('next')
	if low.get('back'):
		d['back'] = low['back']
	if low.get('block'):
		d['block'] = low['block']
	ns = notes_of(f)
	if ns:
		d['notes'] = ns
	return d


def block_info(bid, b, u=None, ctx=None):
	n = b['node']
	d = {'id': bid, 'kind': b['kind']}
	if b['kind'] == 'for':
		d['item'], d['path'] = n.word(0), n.word(2)
	elif b['kind'] in ('until', 'if'):
		d['path'] = n.word(0)
	elif b['kind'] == 'section':
		d['name'] = name_of(n)
	if n.kids('retry'):
		d['retry'] = value(n.kids('retry')[0].args[0])
	rd = node_reads(n, u, ctx)
	if rd:
		d['reads'] = rd
	if n.kids('tolerate'):
		d['tolerate'] = float(n.kids('tolerate')[0].word(0).rstrip('%'))
		if d['tolerate'] == int(d['tolerate']):
			d['tolerate'] = int(d['tolerate'])
	if b.get('fail'):
		d['fail'] = b['fail']
	for k in ('block', 'if'):
		if b.get(k):
			d[k] = b[k]
	d['body'] = b['body']
	for k in ('first', 'next', 'else', 'else_block'):
		if k in b:
			d[k] = b[k]
	return d


def port_info(n):
	'''An "in" or "out" node -> {"name", "type", "text", "schema"} ("name" for "in" only; "schema" when typed).'''
	name, t, text = in_parts(n)
	d = {'name': name} if n.head == 'in' else {}
	d.update({'type': t if t else None, 'text': text})
	if t is not None:
		d['schema'] = type_schema(t)
		if n.head == 'in' and is_optional(t):
			d['optional'] = True
	return d


def catalog(u, preset=None, ctx=None):
	'''A unit as a catalogue: the JSON that the runner reads. Every edge is written out (Flow).'''
	toks = preset_tokens(u, preset)
	fl = Flow(u)
	order = [item_id(x, fl.bids) for x in walk_items(u) if x.head in BLOCKS]
	out = {
		'rig': VERSION, 'unit': u.word(0), 'preset': preset,
		'intent': ' '.join(text_of(x) for x in u.kids('intent')),
		'notes': notes_of(u),
		'code': [dict((k, c[k]) for k in ('prefix', 'file', 'test')) for c in code_lines(u)],
		'in': [port_info(x) for x in u.kids('in')],
		'out': port_info(u.kids('out')[0]) if u.kids('out') else None,
		'start': fl.start, 'rollback': fl.rollback, 'finally': fl.final, 'body': [item_id(x, fl.bids) for x in items(u)],
		'coverage': coverage(u, ctx),
		'presets': presets_of(u),
		'rules': [rule_info(r, toks.get(r.word(0))) for r in u.kids('rule')],
		'flow': [node_info(f, fl, u, ctx) for f in flow_nodes(u)],
		'blocks': [block_info(b, fl.blocks[b], u, ctx) for b in order if b in fl.blocks],
	}
	if u.kids('queue'):
		q = u.kids('queue')[0]
		qd = {'by': [b.word(0) for b in q.kids('by') if b.word(0)]}
		qrd = node_reads(q, u, ctx)
		if qrd:
			qd['reads'] = qrd
		if q.args and q.args[0][0] == 'str':
			qd['name'] = value(q.args[0])
		out['queue'] = qd
	ispec = intent_info(u)
	if ispec and any(k in ispec for k in ('audience', 'style', 'never')):
		out['intent_spec'] = ispec
	return out


def tool_def(u, preset=None):
	'''A unit as a tool definition for a model that calls tools: name, description, JSON Schema.'''
	props, req = {}, []
	for x in u.kids('in'):
		name, t, text = in_parts(x)
		s = type_schema(t)
		if text:
			s['description'] = text
		props[name] = s
		if not is_maybe(t):
			req.append(name)
	d = {'name': u.word(0), 'description': fill_values(u, ' '.join(text_of(x) for x in u.kids('intent')), preset),
		'parameters': {'type': 'object', 'properties': props, 'required': req}}
	if u.kids('out'):
		_, t, text = in_parts(u.kids('out')[0])
		d['returns'] = type_schema(t)
		if text:
			d['returns']['description'] = text
	return d


# - Compile: skill (Markdown) -------------------------
def show(tok):
	'''A value token as the text a person reads.'''
	if tok is None:
		return ''
	return value(tok) if tok[0] == 'str' else ser(tok)


def _fmt_scalar(v):
	if isinstance(v, bool):
		return 'on' if v else 'off'
	if isinstance(v, (list, dict)):
		return json.dumps(v, ensure_ascii=False)
	return str(v)


def _known_placeholder(ph, byrule):
	if ph in byrule:
		return True
	base, _, key = ph.rpartition('.')
	if base in byrule and rule_type(byrule[base]) == 'dict':
		dval = value(byrule[base].args[1]) if len(byrule[base].args) > 1 else {}
		return isinstance(dval, dict) and key in dval
	return False


def fill_values(u, t, preset=None):
	'''Write the value of each rule in place of {group.name} (or {group.name.key} on a dict rule) in t.'''
	toks = preset_tokens(u, preset)
	byrule = dict((r.word(0), r) for r in u.kids('rule'))

	def sub(m):
		ph = m.group(1)
		if ph in byrule:
			return show(toks.get(ph, byrule[ph].args[1] if len(byrule[ph].args) > 1 else None))
		base, _, key = ph.rpartition('.')
		if base in byrule and rule_type(byrule[base]) == 'dict':
			tok = toks.get(base, byrule[base].args[1] if len(byrule[base].args) > 1 else None)
			dval = value(tok) if tok is not None else {}
			if isinstance(dval, dict) and key in dval:
				return _fmt_scalar(dval[key])
		return m.group(0)

	return PLACE.sub(sub, t)


def guessed_gates(c):
	'''The gates that the agent decides itself, not code: model gates, and hard or soft gates with no code.'''
	return [f['id'] for f in c['flow'] if f['kind'] == 'model' or (f['kind'] in ('hard', 'soft') and not f.get('by'))]


def skill(u, rules_path=None, preset=None, driver=None):
	'''A unit as a SKILL.md for an agent that follows instructions.
	rules_path: refer to that JSON file for the values, instead of writing them in.
	driver: the command of a runner that walks the flow (rigkit); the agent then only
	starts runs and answers what waits. Without it, the agent walks the flow itself.'''
	toks = preset_tokens(u, preset)
	byrule = dict((r.word(0), r) for r in u.kids('rule'))

	def val(rid):
		r = byrule[rid]
		return show(toks.get(rid, r.args[1] if len(r.args) > 1 else None))

	def fill(t):
		if rules_path:
			return PLACE.sub(lambda m: '`{' + m.group(1) + '}`' if _known_placeholder(m.group(1), byrule) else m.group(0), t)
		return fill_values(u, t, preset)

	def cell(t):
		return t.replace('|', '\\|').replace('\n', ' ')
	c = catalog(u, preset)
	intent = fill(c['intent'])
	out = ['---', 'name: ' + u.word(0), 'description: ' + intent, '---', '', '# ' + u.word(0), '']
	if intent:
		out += [intent, '']
	ispec = c.get('intent_spec') or {}
	if ispec.get('audience'):
		out.append('Audience: ' + fill(ispec['audience']))
	if ispec.get('style'):
		out.append('Style: ' + fill(ispec['style']))
	for nv in ispec.get('never', []):
		out.append('Never: ' + fill(nv['text']) + (' (gate `{}`)'.format(nv['gate']) if nv.get('gate') else ''))
	if any(ispec.get(k) for k in ('audience', 'style', 'never')):
		out.append('')
	for n in c['notes']:
		out.append('Note: ' + fill(n['text']))
	if c['notes']:
		out.append('')
	if c['rules']:
		out += ['## Rules', '']
		cap_table = bool(driver and len(c['rules']) > 25)
		shown_rules = [r for r in u.kids('rule') if r.kids('ui') or (r.word(0) or '').startswith('permissions.')] if cap_table else list(u.kids('rule'))
		if rules_path:
			out += ['Read the value of each rule from `' + rules_path + '`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.', '']
		if shown_rules:
			if rules_path:
				out += ['| Rule | Meaning |', '|---|---|']
			else:
				out += ['| Rule | Value | Meaning |', '|---|---|---|']
			for r in shown_rules:
				info = rule_info(r)
				lim = []
				if 'min' in info or 'max' in info:
					lim.append('range {} to {}'.format(info.get('min', '…'), info.get('max', '…')))
				if 'options' in info:
					lim.append('one of: ' + ', '.join(str(o) for o in info['options']))
				mean = info['label'] + ('; ' + ', '.join(lim) if lim else '')
				if rules_path:
					out.append('| `{}` | {} |'.format(info['id'], cell(mean)))
				else:
					out.append('| `{}` | `{}` | {} |'.format(info['id'], cell(val(info['id'])), cell(mean)))
			out.append('')
		if cap_table:
			out += ['Run `{} rules` to inspect all {} rules.'.format(driver, len(c['rules'])), '']
	if not c['flow']:
		return '\n'.join(out).rstrip('\n') + '\n'
	if driver:
		args = ' '.join("{}=<{}>".format(x['name'], x['type'] or 'value') for x in c['in'])
		out += ['## How to run', '',
			'Code walks this flow. Start a run and answer only what waits. Run every command in the folder that holds `rig.json`.', '',
			'1. Start: `{} run \'<inputs as JSON>\'`{}.'.format(driver, ' (inputs: ' + args + ')' if args else ''),
			'2. Read the JSON result:',
			'   - `outcome`: the run ended. Report it, with `problems` first (and `result` if present). `error` means code failed.',
			'   - `waiting` (`kind: model`): decide `check` from `sees` (respecting `intent`). Run `{} answer <run> \'{{"pass": true, "why": "..."}}\'` (or `false`).'.format(driver),
			'   - `waiting` (`kind: step`): do `do` from `sees`. Run `{} answer <run> \'{{"result": ...}}\'` matching `schema` if present.'.format(driver),
			'   - `waiting` (`kind: reason`): deliberate (`mode`: `careful` or `creative`) respecting `intent`, `never` boundaries, and any `candidates` count; use `{} arena <run> <tool>` for read-only tools up to `budget`. Run `{} answer <run> \'{{"result": ...}}\'`.'.format(driver, driver),
			'   - `waiting` (`kind: human`): show the person `name`, `check`, `sees`, and `say` word for word; wait, then run `{} approve <run> yes` (or `no` / their words). Never answer for a person.'.format(driver),
			'   - `waiting.problems`: fix those problems in the new answer. `refused`: final — run `{} status <run>`.'.format(driver),
			'3. Repeat step 2 until `outcome`. Never decide a hard or soft gate yourself.', '',
			'More commands: `{} batch \'<JSON list>\' --report reports/<name>.md`, `{} next-batch`, `{} queues`, `{} status <run>`, `{} rules`, `{} flow`{}{}.'.format(
				driver, driver, driver, driver, driver, driver,
				', `{} restore <run>`'.format(driver) if c.get('rollback') else '',
				', `{} artifact <run> <step>`'.format(driver) if any(f.get('brief') for f in c['flow']) else ''), '']
		code_steps = sum(1 for f in c['flow'] if f['kind'] == 'step' and f['lane'] == 'code')
		code_gates = sum(1 for f in c['flow'] if f['kind'] in ('hard', 'soft') and f.get('by'))
		interactive = [f for f in c['flow'] if f['kind'] in ('model', 'human', 'reason') or (f['kind'] == 'step' and f['lane'] == 'model') or (f['kind'] in ('hard', 'soft') and not f.get('by'))]
		ends = [f for f in c['flow'] if f['kind'] == 'end']
		out += ['## Flow (summary)', '',
			'The runner walks {} code {} and {} code {} automatically (`{} flow` shows the full map).'.format(
				code_steps, 'step' if code_steps == 1 else 'steps',
				code_gates, 'gate' if code_gates == 1 else 'gates', driver), '']
		if interactive:
			out += ['| Node | Kind | Action / check | Sees | Out / options |', '|---|---|---|---|---|']
			for f in interactive:
				k = f['kind']
				kind_label = {'step': 'model step', 'reason': 'reason ({})'.format(f.get('mode', 'careful')), 'model': 'model gate', 'human': 'human gate'}.get(k, k + ' gate (no code)')
				if k == 'human':
					action = ' — '.join(fill(f[x]) for x in ('name', 'check') if f.get(x))
				else:
					action = fill(f.get('do') or f.get('check') or f.get('name') or '')
				sees = ', '.join('`{}`'.format(x) for x in f.get('sees', []))
				if 'out' in f:
					form = '`{}`'.format(f['out'])
					if 'candidates' in f:
						form += ' × {}'.format(f['candidates'])
				elif 'options' in f:
					form = ' / '.join('`{}`'.format(o) for o in f['options'])
				else:
					form = ''
				out.append('| `{}` | {} | {} | {} | {} |'.format(f['id'], kind_label, cell(action), cell(sees), cell(form)))
			out.append('')
		if ends:
			out += ['Ends: ' + ', '.join('`{}` — {}'.format(f['id'], fill(f['name'])) if f.get('name') else '`{}`'.format(f['id']) for f in ends) + '.', '']
	else:
		nodes = dict((f['id'], f) for f in c['flow'])
		blocks = dict((b['id'], b) for b in c['blocks'])
		out += ['## Flow', '',
			'Do the lines in order, from the top. A gate that passes goes on to the next line. A gate that fails goes where its fail line says. Do not skip a gate.',
			'A block holds the lines under it: "for each" runs them once for each item of a list, "until" runs them again until its path is true, "if" runs them only when its path is not empty and not false.', '']

		def where(x):
			if x is None:
				return 'the flow ends'
			if x in blocks:
				return 'the block `{}`'.format(x)
			return '`{}`'.format(x)

		def node(f, depth):
			k = f['kind']
			label = {'step': 'step', 'reason': 'reason ({})'.format(f.get('mode', 'careful')), 'end': 'end'}.get(k, k + ' gate')
			h = '#' * min(6, 3 + depth)
			out.extend(['{} `{}`{} ({})'.format(h, f['id'], ' ' + fill(f['name']) if f.get('name') else '', label), ''])
			if 'if' in f:
				out.append('- Only when `{}` is not empty and not false. Else go on to the next line.'.format(f['if']))
			if k == 'reason' and f.get('intent'):
				out.append('- Intent: ' + fill(f['intent']))
			if k == 'reason' and f.get('intent_spec'):
				sp = f['intent_spec']
				if sp.get('audience'):
					out.append('- Audience: ' + fill(sp['audience']))
				if sp.get('style'):
					out.append('- Style: ' + fill(sp['style']))
				for nv in sp.get('never', []):
					out.append('- Never: ' + fill(nv['text']) + (' (gate `{}`)'.format(nv['gate']) if nv.get('gate') else ''))
			for key, title in (('do', 'Do'), ('check', 'Check')):
				if key in f:
					out.append('- {}: {}'.format(title, fill(f[key])))
			if 'reads' in f:
				out.append('- Rules: ' + ', '.join('`{}`'.format(r) if rules_path or r not in byrule else '`{}` = {}'.format(r, val(r)) for r in f['reads']))
			if 'sees' in f:
				out.append('- Sees: ' + ', '.join('`{}`'.format(x) for x in f['sees']))
			if 'tools' in f:
				out.append('- Read-only tools: ' + ', '.join('`{}`'.format(t) for t in f['tools']) + (' (budget: {})'.format(f['budget']) if 'budget' in f else ''))
			if 'candidates' in f:
				out.append('- Produce {} distinct candidates.'.format(f['candidates']))
			if 'out' in f:
				out.append('- The answer has the type `{}`.'.format(f['out']))
			by = ', '.join('`{}`'.format(b) for b in f.get('by', []))
			guess = '- No code decides this gate yet: decide it yourself and label the result as a guess.'
			if k == 'reason':
				out.append('- Deliberate carefully in {} mode; never mutate the world directly.'.format(f.get('mode', 'careful')))
			elif k == 'step' and f['lane'] == 'model':
				out.append('- You do this step.')
			elif k == 'step' and by:
				out.append('- Code: run {}.'.format(by))
			elif k == 'hard':
				out.append('- Decided by code: run {} and obey its result. Do not decide this gate yourself.'.format(by) if by else guess)
			elif k == 'soft':
				out.append('- Decided by code: run {}. If it fails, report it and go on to the next line.'.format(by) if by else guess)
			elif k == 'model':
				out.append('- You decide this gate. Label the result as a guess.')
			elif k == 'human':
				out.append('- A person decides. Stop and ask the person. Do not decide this gate yourself.')
				if 'options' in f:
					out.append('- The answers: {}. The first is the default: the answer when the person only agrees. Code ({}) reads the answer; when it does not understand it, ask again.'.format(', '.join('`{}`'.format(o) for o in f['options']), by))
			if 'timeout_text' in f:
				out.append('- Time limit: {}.{}'.format(f['timeout_text'], ' After it, the gate fails with the reason timeout.' if k == 'human' else ''))
			if 'retry' in f:
				out.append('- On fail: do `{}` again, at most {} times. Then take the fail line.'.format(f.get('back'), f['retry']))
			for n in f.get('notes', []):
				out.append('- Note: ' + fill(n['text']))
			if k != 'end':
				out.append('- Next: {}.'.format(where(f.get('next'))))
			for l in f.get('fail', []):
				if l.get('continue'):
					out.append('- Fail: leave this item, note it for the report, and go on to the next item of `{}`.'.format(l['to']))
				else:
					out.append('- Fail: go to `{}`{}.'.format(l['to'], ' ({})'.format(fill(l['when'])) if 'when' in l else ''))
			if k == 'end':
				out.append('- Stop here.' + (' Then do the block `finally`.' if c.get('finally') else ''))
			out.append('')

		def block(b, depth):
			k = b['kind']
			if k == 'section':
				out.extend(['{} {}'.format('#' * min(6, 3 + depth), fill(b.get('name', ''))), ''])
				body(b['body'], depth + 1)
				return
			head = {'for': 'For each `{}` in `{}`'.format(b.get('item'), b.get('path')), 'until': 'Until `{}` is true'.format(b.get('path')),
				'if': 'If `{}`'.format(b.get('path')), 'else': 'Else (when the `if` before did not run)',
				'rollback': 'Rollback: on hard fail, error, unattended deferral, or explicit restore',
				'finally': 'Finally: always, after the run ends (also after an error)'}[k]
			out.append('**{}** (block `{}`):'.format(head, b['id']))
			if k == 'for':
				out.append('- Do the lines of this block once for each item. The item is `{}`.'.format(b.get('item')))
				if 'tolerate' in b:
					out.append('- When more than {}% of the items are left (fail -> continue), the block fails after the last item.'.format(b['tolerate']))
			if k == 'until':
				out.append('- Do the lines of this block, then again until `{}` is true: at most {} more times.'.format(b.get('path'), b.get('retry')))
			for l in b.get('fail', []):
				out.append('- Fail: go to `{}`.'.format(l['to']))
			out.append('')
			body(b['body'], depth + 1)
			out.extend(['**End of the block `{}`.**'.format(b['id']), ''])

		def body(ids, depth):
			for x in ids:
				if x in nodes:
					node(nodes[x], depth)
				elif x in blocks:
					block(blocks[x], depth)
		body(c['body'], 0)
	guessed = guessed_gates(c)
	if guessed:
		names = ', '.join(guessed)
		out += ['## Report', '',
			'You decide these gates yourself, not code: {}. Their results are guesses.'.format(', '.join('`{}`'.format(g) for g in guessed)),
			'End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:', '',
			'Guessed: ' + names, '',
			'Do not leave this line out. A person must see which results are guesses.'
			+ (' Write it for each run in which you decided a gate, also when the run ended early.' if driver else ''), '']
	return '\n'.join(out).rstrip('\n') + '\n'


# - Command line -------------------------------------
def tree(n):
	d = {'head': n.head, 'args': [ser(a) for a in n.args], 'line': n.line}
	if n.children:
		d['children'] = [tree(c) for c in n.children]
	return d


def load(path):
	with open(path, encoding='utf-8', newline='') as f:
		text = f.read()
	try:
		root = parse(text)
	except RigError as e:
		raise SystemExit('{}: {}'.format(path, e))
	expand_external_rules(root, path)
	return text, root


def find(root, name):
	for u in units(root):
		if u.word(0) == name:
			return u
	raise SystemExit('no unit "{}"'.format(name))


def pick(root, name=None):
	'''The named unit, or the first unit with a flow, or the first unit.'''
	if name:
		return find(root, name)
	us = units(root)
	if not us:
		raise SystemExit('the file has no unit')
	for u in us:
		if has_flow(u):
			return u
	return us[0]


def option(rest, name, flag=False):
	'''Take "--name VALUE" (or the flag "--name") out of rest.'''
	if name not in rest:
		return False if flag else None
	i = rest.index(name)
	if flag:
		del rest[i]
		return True
	if i + 1 >= len(rest):
		raise SystemExit('{} needs a value'.format(name))
	v = rest[i + 1]
	del rest[i:i + 2]
	return v


def write(path, text):
	with open(path, 'w', encoding='utf-8', newline='\n') as f:
		f.write(text)


def compile_to(kind, u, preset=None, rules_path=None, ctx=None, driver=None):
	if kind == 'json':
		return json.dumps(catalog(u, preset, ctx), ensure_ascii=False, indent=1) + '\n'
	if kind == 'skill':
		return skill(u, rules_path, preset, driver)
	if kind == 'tool':
		raise SystemExit('"compile tool" was removed in version 2: use "compile json" or "compile skill"')
	raise SystemExit('compile json or compile skill')


def outputs(path, unit=None, json_out=None, skill_out=None, rules_ref=False, preset=None):
	'''Compile FILE to the files that agents read. -> the paths written.'''
	text, root = load(path)
	err, _ = check(root, path)
	if err:
		raise SystemExit('{}: line {}: {}'.format(path, err[0][0], err[0][1]))
	u = pick(root, unit)
	done = []
	if json_out:
		write(json_out, compile_to('json', u, preset, None, Ctx(root, path)))
		done.append(json_out)
	if skill_out:
		ref = None
		if rules_ref and json_out:
			ref = os.path.relpath(os.path.abspath(json_out), os.path.dirname(os.path.abspath(skill_out))).replace(os.sep, '/')
		write(skill_out, compile_to('skill', u, preset, ref))
		done.append(skill_out)
	return done


def run_file(folder, run_id):
	'''The file of one run: <runs>/<id>/run.json (the run folder of version 1), or <runs>/<id>.json.'''
	if not re.match(r'^[\w.-]+$', run_id or ''):
		return None
	for p in (os.path.join(folder, run_id, 'run.json'), os.path.join(folder, run_id + '.json')):
		if os.path.exists(p):
			return p
	return None


def run_sort_key(run_id):
	m = re.match(r'^r(\d+)$', run_id or '')
	return (1, int(m.group(1)), '') if m else (0, 0, run_id or '')


def run_list(folder):
	'''The runs of a tool (the files that rigkit writes), newest first, for the viewer.'''
	rows = []
	if not os.path.isdir(folder):
		return []
	names = [n for n in os.listdir(folder) if not n.startswith('.') and n != 'waiting.json']
	names.sort(key=lambda n: run_sort_key(n[:-5] if n.endswith('.json') else n), reverse=True)
	for n in names[:200]:
		p = run_file(folder, n[:-5] if n.endswith('.json') else n)
		if not p:
			continue
		try:
			with open(p, encoding='utf-8') as f:
				r = json.load(f)
			if not isinstance(r, dict) or 'id' not in r or 'at' not in r:
				continue
			o = r.get('outcome')
			state = 'ended at {}'.format(o.get('end') or o.get('label') or 'a stop') if o else 'waits at ' + str(r['at'])
			rows.append((r.get('started') or '', run_sort_key(r['id']), {'id': r['id'], 'state': state}))
		except (OSError, ValueError, KeyError, TypeError, AttributeError):
			pass
	rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
	return [x[2] for x in rows]


def _save_sidecars(root, path, sidecars):
	'''Persist edited JSON sidecar rule values into their "<path>.json" files without touching the .rig file.'''
	if not sidecars or not path:
		return []
	base = os.path.dirname(os.path.abspath(path))
	allowed = {}
	byrule = {}
	for u in units(root):
		for rs in u.kids('rules'):
			if len(rs.args) == 1 and rs.args[0][0] == 'str':
				rel = value(rs.args[0])
				allowed[rel] = os.path.normpath(os.path.join(base, rel))
		for r in u.kids('rule'):
			if r.word(0):
				byrule[r.word(0)] = r
	wrote = []
	for rel, rmap in sorted(sidecars.items()):
		if not rmap or rel not in allowed:
			continue
		jpath = allowed[rel]
		with open(jpath, encoding='utf-8') as f:
			data = json.load(f)
		entries = data if isinstance(data, list) else data.get('rules', [])
		changed = False
		for entry in entries:
			if isinstance(entry, dict) and entry.get('id') in rmap and entry['id'] in byrule:
				new_val = rule_info(byrule[entry['id']])['value']
				if 'default' in entry and entry.get('value') == entry.get('default'):
					entry['default'] = new_val
				entry['value'] = new_val
				changed = True
		if changed:
			write(jpath, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
			wrote.append(jpath)
	return wrote


def bundle(text, path=None, sidecars=None):
	'''Everything the viewer shows for one file, compiled here: the viewer has no parser of its own.
	-> {"file", "text", "errors", "warnings", "units": [...]}; each unit has its catalogue, skill,
	tool definition, status, the levels of its gates, and where each rule value is in the text.'''
	out = {'rig': VERSION, 'file': os.path.basename(path) if path else 'untitled.rig', 'text': text, 'errors': [], 'warnings': [], 'units': []}
	try:
		root = parse(text)
	except RigError as e:
		out['errors'] = [[e.line, str(e).split(': ', 1)[-1]]]
		return out
	if path:
		expand_external_rules(root, path, sidecars=sidecars)
	ctx = Ctx(root, path) if path else Ctx(root)
	err, warn = check(root, path, ctx)
	out['errors'], out['warnings'] = [list(x) for x in sorted(err)], [list(x) for x in sorted(warn)]
	for u in units(root):
		name = u.word(0) or '?'
		d = {'name': name, 'status': unit_status(u, ctx), 'flow': has_flow(u)}
		try:
			d['catalogue'] = catalog(u, None, ctx)
			d['skill'] = skill(u)
			d['skill_ref'] = skill(u, name + '.json')
			d['tool'] = tool_def(u) if u.kids('in') else None
		except Exception as e:  # a unit with errors may not compile; the errors say why
			d['catalogue'], d['problem'] = None, '{}: {}'.format(type(e).__name__, e)
		d['levels'] = dict((g.word(0), gate_level(g, u, ctx, (name,))) for g in flow_nodes(u) if g.head == 'gate' and g.word(0))
		bids = block_ids(u)
		d['lines'] = dict((item_id(x, bids), x.line) for x in walk_items(u) if item_id(x, bids))
		src = {}
		for r in u.kids('rule'):
			if getattr(r, 'from_json', None) and r.word(0) and len(r.args) > 1:
				src[r.word(0)] = {'json_file': r.from_json, 'text': ser(r.args[1]), 'shown': show(r.args[1])}
			elif r.word(0) and len(r.args) > 1 and len(r.spans) > 1:
				a, b = r.spans[1]
				src[r.word(0)] = {'line': r.line, 'a': a, 'b': b, 'text': ser(r.args[1]), 'shown': show(r.args[1])}
		d['rules_src'] = src
		d['presets_src'] = dict((p.word(0), dict((x.word(0), ser(x.args[1])) for x in p.kids('set') if len(x.args) > 1)) for p in u.kids('preset'))
		out['units'].append(d)
	return out


def serve(path, port, runs=None, **outs):
	'''Serve the viewer for one file on 127.0.0.1. Save writes the file and compiles it again.
	runs: the folder of the run files of the tool (default: "runs" next to the file); the graph shows the path of a run.'''
	runs = runs or os.path.join(os.path.dirname(os.path.abspath(path)), 'runs')
	import http.server
	here = os.path.dirname(os.path.abspath(__file__))
	res_dirs = [
		os.path.join(os.path.dirname(os.path.abspath(path)), 'resources'),
		os.path.join(here, 'resources'),
		here,
	]
	fallback_page = os.path.join(here, '..', '..', 'viewer', 'index.html')

	def find_asset(name):
		return next((os.path.join(d, name) for d in res_dirs if os.path.isfile(os.path.join(d, name))), None)

	if not (find_asset('viewer.html') or os.path.isfile(fallback_page)):
		raise SystemExit('the viewer is not found: expected resources/viewer.html next to rig.py')
	print('wrote: ' + ', '.join(outputs(path, **outs) or ['nothing (add --json or --skill)']))

	class Handler(http.server.BaseHTTPRequestHandler):
		def reply(self, code, body, kind='application/json; charset=utf-8'):
			data = body.encode('utf-8')
			self.send_response(code)
			self.send_header('Content-Type', kind)
			self.send_header('X-Rig-File', os.path.basename(path))
			self.send_header('Content-Length', str(len(data)))
			self.send_header('Cache-Control', 'no-store')
			self.end_headers()
			self.wfile.write(data)

		def do_GET(self):
			req = self.path.split('?', 1)[0]
			if req in ('/', '/index.html'):
				self.send_response(302)
				self.send_header('Location', '/viewer?serve=1')
				self.end_headers()
			elif req in ('/viewer.css', '/viewer/viewer.css') and find_asset('viewer.css'):
				with open(find_asset('viewer.css'), encoding='utf-8') as f:
					self.reply(200, f.read(), 'text/css; charset=utf-8')
			elif req in ('/viewer.js', '/viewer/viewer.js') and find_asset('viewer.js'):
				with open(find_asset('viewer.js'), encoding='utf-8') as f:
					self.reply(200, f.read(), 'application/javascript; charset=utf-8')
			elif req in ('/viewer', '/viewer/', '/viewer/index.html'):
				page = find_asset('viewer.html') or fallback_page
				with open(page, encoding='utf-8') as f:
					self.reply(200, f.read(), 'text/html; charset=utf-8')
			elif req == '/bundle':
				with open(path, encoding='utf-8', newline='') as f:
					self.reply(200, json.dumps(bundle(f.read(), path), ensure_ascii=False))
			elif req == '/runs':
				self.reply(200, json.dumps(run_list(runs)))
			elif req.startswith('/runs/') and run_file(runs, req[6:]):
				with open(run_file(runs, req[6:]), encoding='utf-8') as f:
					self.reply(200, f.read())
			else:
				self.reply(404, json.dumps({'error': 'not found'}))

		def do_POST(self):
			if self.path not in ('/file', '/compile'):
				return self.reply(404, json.dumps({'error': 'not found'}))
			raw_body = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8')
			ctype = (self.headers.get('Content-Type') or '').lower()
			sidecars = None
			if 'application/json' in ctype:
				try:
					payload = json.loads(raw_body)
					text = payload.get('text', '')
					sidecars = payload.get('sidecars')
				except ValueError as e:
					return self.reply(400, json.dumps({'error': 'invalid JSON: {}'.format(e)}))
			else:
				text = raw_body
			if self.path == '/compile':  # compile changed text for the viewer; write nothing
				return self.reply(200, json.dumps(bundle(text, path, sidecars=sidecars), ensure_ascii=False))
			try:
				root = parse(text)
				expand_external_rules(root, path, sidecars=sidecars)
				err, _ = check(root, path)
			except RigError as e:
				return self.reply(400, json.dumps({'error': str(e)}))
			if err:
				return self.reply(400, json.dumps({'error': 'line {}: {}'.format(err[0][0], err[0][1])}))
			old_rig = read_text(path)
			saved_files = []
			if old_rig is None or old_rig != text:
				with open(path, 'w', encoding='utf-8', newline='') as f:
					f.write(text)
				saved_files.append(os.path.basename(path))
			sc_wrote = _save_sidecars(root, path, sidecars)
			saved_files.extend(os.path.basename(p) for p in sc_wrote)
			try:
				done = outputs(path, **outs)
			except SystemExit as e:
				return self.reply(400, json.dumps({'error': str(e)}))
			with open(path, encoding='utf-8', newline='') as f:
				fresh_text = f.read()
			self.reply(200, json.dumps({'saved': ', '.join(saved_files) or os.path.basename(path), 'wrote': done, 'bundle': bundle(fresh_text, path)}, ensure_ascii=False))

		def log_message(self, *a):
			pass

	class Server(http.server.HTTPServer):
		def server_bind(self):
			# HTTPServer asks the name service for the full host name here; that can hang for a long time.
			import socketserver
			socketserver.TCPServer.server_bind(self)
			self.server_name, self.server_port = '127.0.0.1', port

	srv = Server(('127.0.0.1', port), Handler)
	print('serving {} at http://127.0.0.1:{}/  (Ctrl+C stops)'.format(path, port), flush=True)
	try:
		srv.serve_forever()
	except KeyboardInterrupt:
		pass


def main(argv):
	try:
		sys.stdout.reconfigure(encoding='utf-8', errors='replace')
	except Exception:
		pass
	if argv and argv[0] in ('new', 'build', 'doctor', 'test', 'plugin', 'mcp-config'):
		import rig_project
		return rig_project.main(argv[0], list(argv[1:]))
	if argv and argv[0] in ('hash', 'prove', 'probe', 'stamp', 'emit'):
		print('"{}" is a command of version 0: casts and hashes are gone. The code lives in files; its tests prove it (rig.py test).'.format(argv[0]))
		return 2
	if len(argv) < 2 or argv[0] not in ('check', 'json', 'compile', 'serve'):
		print(__doc__)
		return 2
	cmd, rest = argv[0], list(argv[1:])
	if cmd == 'compile':
		kind = rest.pop(0)
		preset, out, rules, driver = option(rest, '--preset'), option(rest, '-o'), option(rest, '--rules'), option(rest, '--driver')
		if not rest:
			raise SystemExit('compile {} FILE [UNIT]'.format(kind))
		text, root = load(rest[0])
		err, _ = check(root, rest[0])
		if err:
			raise SystemExit('{}: line {}: {}'.format(rest[0], err[0][0], err[0][1]))
		result = compile_to(kind, pick(root, rest[1] if len(rest) > 1 else None), preset, rules, Ctx(root, rest[0]), driver)
		if out:
			write(out, result)
		else:
			sys.stdout.write(result)
		return 0
	if cmd == 'serve':
		port = int(option(rest, '--port') or 8765)
		outs = {'runs': option(rest, '--runs'), 'json_out': option(rest, '--json'), 'skill_out': option(rest, '--skill'), 'rules_ref': option(rest, '--rules-ref', True),
			'unit': rest[1] if len(rest) > 1 else None}
		serve(rest[0], port, **outs)
		return 0
	if cmd == 'check':
		bad = 0
		for path in rest:
			text, root = load(path)
			ctx = Ctx(root, path)
			print(path)
			for u in units(root):
				print('  {:<28} {}'.format(u.word(0), '; '.join(unit_status(u, ctx))))
			err, warn = check(root, path, ctx)
			for line, t in sorted(err):
				print('  error   line {}: {}'.format(line, t))
			for line, t in sorted(warn):
				print('  warning line {}: {}'.format(line, t))
			bad += len(err)
		return 1 if bad else 0
	text, root = load(rest[0])
	print(json.dumps(tree(root), ensure_ascii=False, indent=1))
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
