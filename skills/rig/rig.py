#!/usr/bin/env python3
"""rig.py: the tool of Rig, language version 1. Standard library only.

    python rig.py check FILE...               validate; show the status of every unit
    python rig.py json FILE                   the parsed tree as JSON
    python rig.py compile json FILE [UNIT]    the unit as a catalogue: rules, presets and flow,
                                              the JSON that the runner reads
    python rig.py compile skill FILE [UNIT]   the unit as a SKILL.md for an agent that follows
                                              instructions; --rules PATH: refer to the values
                                              in that JSON file instead of writing them in
    python rig.py compile tool FILE [UNIT]    the unit as a tool definition: name, description
                                              and the JSON Schema of its inputs
        compile options: --preset NAME (use the values of a preset), -o OUT (write a file),
                                              --driver CMD (skill: a runner walks the flow)
    python rig.py from-json FILE.json         a catalogue back to Rig (the same meaning)
    python rig.py serve FILE [UNIT]           the viewer for FILE on 127.0.0.1; Save writes FILE
        [--port 8765] [--json OUT] [--skill OUT] [--rules-ref] [--runs DIR]
                                              and compiles it again to OUT; --rules-ref makes
                                              the skill read its values from the JSON

    python rig.py new DIR NAME [--level N]    make a project: a tool with its source, code, tests
                                              and runner (levels 1 to 4: guide/levels.md)
    python rig.py build [DIR] [--check]       compile the source of a project to its fronts: the
                                              catalogue, the skill, the tool definitions
    python rig.py doctor [DIR] [--no-tests]   check a project against the list of its level
    python rig.py test [DIR] [--replay RUN]   run the tests of a project; --replay: run the flow
                                              again with the answers recorded in a run
    python rig.py plugin DIR [--owner NAME]   add the front for a local model: an LM Studio plugin
                                              that reads its tools and its rules from the build

The language is defined in spec.md (same folder).
"""
import json
import os
import re
import sys

VERSION = 1
FLOW = ('step', 'gate', 'end')                                    # the nodes of a flow
BLOCKS = ('for', 'until', 'if', 'else', 'section', 'finally')     # the blocks: their body is the lines under them
ITEMS = FLOW + BLOCKS
GATE_KINDS = ('hard', 'soft', 'model', 'human')
SCOPES = ('tool', 'agent')
LEVELS = ('none', 'code', 'tested')  # low to high; "model" and "human" are apart
MATRIX = ('in', 'out', 'intent', 'example', 'check')
BASE_TYPES = ('str', 'text', 'word', 'path', 'int', 'float', 'bool', 'list', 'dict', 'any')
TYPE_LISTS = ('list', 'tuple', 'record', 'maybe', 'one-of')
NODE_KIDS = {
	'step': {'do', 'by', 'reads', 'sees', 'out', 'timeout', 'if', 'note'},
	'gate': {'check', 'by', 'reads', 'sees', 'options', 'retry', 'timeout', 'if', 'fail', 'note'},
	'end': {'note'},
}
BLOCK_OPTIONS = {'for': {'tolerate', 'fail'}, 'until': {'retry', 'fail'}}
CHILDREN = {
	'unit': {'in', 'out', 'intent', 'example', 'check', 'note', 'uses', 'code', 'rule', 'preset'} | set(ITEMS),
	'code': {'test', 'note'},
	'preset': {'set'},
	'rule': {'range', 'options', 'note'},
}
CHILDREN.update(NODE_KIDS)
for _b in BLOCKS:
	CHILDREN[_b] = set(ITEMS) | BLOCK_OPTIONS.get(_b, set()) | {'note'}
INLINE = {'step': ('by',), 'gate': ('by', 'fail')}  # children that can stand on the line of their node
RESERVED = ('continue', 'error')  # "fail -> continue" and the built-in outcome "error": not ids
# The words of version 0 that version 1 refuses, with what to write instead (docs/history/handout-language-v1.md, Section 3).
REMOVED = {
	'next': 'remove it: the next line is the next node',
	'pass': 'remove it: a gate that passes goes on to the next line',
	'when': 'write "if <path>" as a child of the node',
	'brief': 'write check "text"',
	'ensure': 'write check "text"',
	'min': 'write range <min> <max>',
	'max': 'write range <min> <max>',
	'label': 'write the label as the string after the value: rule <id> <value> "label"',
	'external': '"by" names a function of a "code" file, or a unit',
	'cast': 'the code lives in a file: write code <path>',
	'probe': 'test the code in its test file',
	'evidence': 'write the evidence in the text of the note',
}
NUMBER = re.compile(r'^-?\d+(\.\d+)?$')
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
def tokenize(s, line, spans=None):
	'''One line (without its indentation) -> a list of args: (kind, text) or ('list', [...]).
	spans: a list that gets (start, end) of each top-level arg in s.'''
	out, stack, i, n = [], [], 0, len(s)
	start = 0
	while i < n:
		if spans is not None and not stack and len(spans) < len(out):
			spans.append((start, i))
		if not stack and s[i] not in ' \t':
			start = i
		c = s[i]
		if c in ' \t':
			i += 1
			continue
		if c == ';':
			break
		if c == '"':
			j = i + 1
			while j < n and s[j] != '"':
				j += 2 if s[j] == '\\' else 1
			if j >= n:
				raise RigError(line, 'the string is not closed')
			out.append(('str', s[i:j + 1]))
			i = j + 1
			continue
		if c == '(':
			stack.append(out)
			out = []
			i += 1
			continue
		if c == ')':
			if not stack:
				raise RigError(line, 'a ")" without "("')
			inner, out = out, stack.pop()
			out.append(('list', inner))
			i += 1
			continue
		if c == '/':
			j = i + 1
			while j < n and s[j] != '/':
				j += 2 if s[j] == '\\' else 1
			if j < n and (j + 1 == n or s[j + 1] in ' \t)'):
				out.append(('re', s[i:j + 1]))
				i = j + 1
				continue
		j = i
		while j < n and s[j] not in ' \t();':
			j += 1
		w = s[i:j]
		out.append(('num' if NUMBER.match(w) else 'word', w))
		i = j
	if stack:
		raise RigError(line, 'a "(" is not closed')
	if spans is not None and len(spans) < len(out):
		spans.append((start, i))
	return out




def ser(arg):
	kind, v = arg
	return '(' + ' '.join(ser(a) for a in v) + ')' if kind == 'list' else v


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
		if node.head in INLINE:  # "step <id> by model", "gate <id> <kind> fail -> <end>": a child on the line of its node
			cuts = [k for k, a in enumerate(node.args) if k >= (2 if node.head == 'gate' else 1) and a[0] == 'word' and a[1] in INLINE[node.head]]
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
	return root


# - Values and types ---------------------------------
def value(arg):
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
		return ''.join(out)
	if kind == 'num':
		return float(v) if '.' in v else int(v)
	if kind == 'list':
		return [value(a) for a in v]
	if kind == 're':
		return v[1:-1]
	return {'true': True, 'false': False, 'on': True, 'off': False, 'none': None}.get(v, v)


def type_parts(t):
	'''A type list -> (its head word, the rest of its items).'''
	items = t[1]
	return (items[0][1] if items and items[0][0] == 'word' else None), items[1:]


def is_maybe(t):
	return t is not None and t[0] == 'list' and type_parts(t)[0] == 'maybe'


def type_problem(t):
	'''-> None, or a short text that says what is wrong with the type.'''
	if t[0] == 'word':
		return None if t[1] in BASE_TYPES else 'type "{}" is not known: use {} or a type list'.format(t[1], ', '.join(BASE_TYPES))
	if t[0] != 'list':
		return 'a type is a word or a list'
	head, rest = type_parts(t)
	if head not in TYPE_LISTS:
		return 'a type list starts with ' + ', '.join(TYPE_LISTS)
	if head in ('list', 'maybe'):
		return type_problem(rest[0]) if len(rest) == 1 else '({} T) takes one type'.format(head)
	if head == 'tuple':
		return next((p for p in map(type_problem, rest) if p), None) if rest else '(tuple T …) needs types'
	if head == 'record':
		if not rest or len(rest) % 2:
			return 'write (record name type …)'
		for i in range(0, len(rest), 2):
			if rest[i][0] != 'word':
				return 'a record field name is a word'
			p = type_problem(rest[i + 1])
			if p:
				return p
		return None
	return None if rest else '(one-of …) needs values'


def type_ok(v, t):
	'''Does the value v (as JSON gives it) match the type token t?'''
	if t is None:
		return True
	if t[0] == 'list':
		head, rest = type_parts(t)
		if head == 'maybe':
			return v is None or type_ok(v, rest[0])
		if head == 'list':
			return isinstance(v, list) and all(type_ok(x, rest[0]) for x in v)
		if head == 'tuple':
			return isinstance(v, list) and len(v) == len(rest) and all(type_ok(x, tt) for x, tt in zip(v, rest))
		if head == 'record':
			if not isinstance(v, dict):
				return False
			for i in range(0, len(rest) - 1, 2):
				name, tt = rest[i][1], rest[i + 1]
				if name not in v:
					if not is_maybe(tt):
						return False
				elif not type_ok(v[name], tt):
					return False
			return True
		if head == 'one-of':
			return v in [value(x) for x in rest]
		return True
	w = t[1]
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


def type_schema(t):
	'''A type token -> JSON Schema.'''
	if t is None:
		return {}
	if t[0] == 'list':
		head, rest = type_parts(t)
		if head == 'list':
			return {'type': 'array', 'items': type_schema(rest[0]) if rest else {}}
		if head == 'tuple':
			return {'type': 'array', 'prefixItems': [type_schema(x) for x in rest], 'minItems': len(rest), 'maxItems': len(rest)}
		if head == 'record':
			props, req = {}, []
			for i in range(0, len(rest) - 1, 2):
				props[rest[i][1]] = type_schema(rest[i + 1])
				if not is_maybe(rest[i + 1]):
					req.append(rest[i][1])
			return {'type': 'object', 'properties': props, 'required': req, 'additionalProperties': False}
		if head == 'maybe':
			return {'anyOf': [type_schema(rest[0]) if rest else {}, {'type': 'null'}]}
		if head == 'one-of':
			return {'enum': [value(x) for x in rest]}
		return {}
	return {'str': {'type': 'string'}, 'text': {'type': 'string'}, 'word': {'type': 'string'}, 'path': {'type': 'string'},
		'int': {'type': 'integer'}, 'float': {'type': 'number'}, 'bool': {'type': 'boolean'},
		'list': {'type': 'array'}, 'dict': {'type': 'object'}}.get(t[1], {})


def in_parts(n):
	'''An "in" or "out" node -> (name, type token or None, text). An "out" node: the name is None.'''
	args = n.args[1:] if n.head == 'in' else n.args
	t = next((a for a in args if a[0] != 'str'), None)
	text = next((value(a) for a in args if a[0] == 'str'), '')
	return (n.word(0) if n.head == 'in' else None), t, text


def seconds(word):
	'''"5m" -> 300; None for a word that is not a time.'''
	m = TIME.match(word or '')
	return int(m.group(1)) * SECONDS[m.group(2)] if m else None


def options_of(n):
	'''The values of an "options" line: "a | b | c", or "a b c" for one-word values.'''
	toks = [ser(a) if a[0] != 'str' else value(a) for a in n.args]
	if '|' in toks:
		out, cur = [], []
		for t in toks + ['|']:
			if t == '|':
				out.append(' '.join(cur))
				cur = []
			else:
				cur.append(t)
		return out
	return [value(a) for a in n.args]


# - The flow: nodes and blocks ------------------------
def units(root):
	return [u for u in root.children if u.head == 'unit']


def items(n):
	'''The flow items of a unit or a block: its steps, gates, ends and blocks, in order.'''
	return [c for c in n.children if c.head in ITEMS and not (c.head == 'if' and n.head in ('step', 'gate'))]


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
		elif b.head == 'finally':
			base = 'finally'
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
		self.add(root, path)

	def add(self, root, path):
		base = os.path.dirname(os.path.abspath(path)) if path else None
		for u in units(root):
			if u.word(0) not in self.units:
				self.units[u.word(0)] = u
				self.base[u.word(0)] = base
		if not path:
			return
		for u in units(root):
			for x in u.kids('uses'):
				f = x.word(1)
				p = os.path.normpath(os.path.join(base, f)) if f else None
				if p and p not in self.files and os.path.exists(p):
					self.files.add(p)
					try:
						with open(p, encoding='utf-8', newline='') as fh:
							self.add(parse(fh.read()), p)
					except (RigError, OSError):
						pass


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


def bound_level(b, u, ctx):
	'''The level of a name that a "code" line holds: none (the file or the function is missing),
	code (the function exists), tested (a test file names it). Without the folder of the file: code.'''
	c, fn = code_for(b, u)
	base = ctx.base.get(u.word(0)) if ctx else None
	if not base:
		return 'code'
	text = read_text(os.path.join(base, c['file'])) if c['file'] else None
	if text is None or not re.search(DEFINES.format(re.escape(fn)), text):
		return 'none'
	test = read_text(os.path.join(base, c['test'])) if c['test'] else None
	return 'tested' if test and re.search(r'\b{}\b'.format(re.escape(fn)), test) else 'code'


def by_target(b, u):
	'''What a "by" name reaches: "bound" (a "code" line), "model", "unit" or None.'''
	if b == 'model':
		return 'model'
	if b and code_for(b, u):
		return 'bound'
	if b in [x.word(0) for x in u.kids('uses')] or b in [v.word(0) for v in units(getattr(u, 'root', Node('file', [], 0, -1)))]:
		return 'unit'
	return None


def unit_level(name, ctx, seen=()):
	'''How much is known about the code of a unit: tested, code or none.'''
	u = ctx.units.get(name)
	if u is None or name in seen:
		return 'code'
	if code_for(name, u):
		return bound_level(name, u, ctx)
	gates = [g for g in flow_nodes(u) if g.head == 'gate']
	if not gates:
		return 'code'
	got = [gate_level(g, u, ctx, tuple(seen) + (name,)) for g in gates]
	return lowest(['code' if x in ('model', 'human', 'none') else x for x in got])


def gate_level(g, u, ctx, seen=()):
	'''tested, code, none, model or human (spec, Section 2: the level of a gate).'''
	if g.word(1) in ('model', 'human'):
		return g.word(1)
	got = []
	for x in g.kids('by'):
		b, kind = x.word(0), by_target(x.word(0), u)
		if kind == 'bound':
			got.append(bound_level(b, u, ctx))
		elif kind == 'unit':
			got.append(unit_level(b, ctx, seen))
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
	steps = [n for n in flow_nodes(unit) if n.head == 'step']
	if cv['gates']:
		parts = ['{} {}'.format(cv[k], k) for k in ('tested', 'code', 'model', 'human', 'none') if cv[k] or k in ('tested', 'model')]
		out.append('flow: {} gates, coverage {:.0%} ({})'.format(cv['gates'], float(cv['tested']) / cv['gates'], ', '.join(parts)))
	elif steps:
		out.append('flow: {} steps, no gates'.format(len(steps)))
	own = code_for(unit.word(0) or '', unit)
	if own:
		out.append('code {} ({})'.format(own[0]['file'], bound_level(unit.word(0), unit, ctx_of(unit, ctx))))
	if not own and any(c.head in MATRIX for c in unit.children) and not has_flow(unit):
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
	for _, t in walk_strings(n):
		for m in PLACE.finditer(t):
			if m.group(1) not in out:
				out.append(m.group(1))
	return out


def node_reads(f):
	'''The rules that a step or gate reads: its "reads" lines and the rules named in its strings.'''
	out = []
	for c in f.kids('reads'):
		for a in c.args:
			if a[1] not in out:
				out.append(a[1])
	for rid in placeholders(f):
		if rid not in out:
			out.append(rid)
	for c in f.kids('retry'):
		if c.args and c.args[0][0] == 'word' and c.word(0) not in out:
			out.append(c.word(0))
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
	if a is None:
		return 'text'
	if a[0] == 'word' and a[1] in ('on', 'off'):
		return 'switch'
	return {'num': 'number', 're': 'pattern', 'list': 'list'}.get(a[0], 'text')


def rule_problem(r, a):
	'''Is the value token a valid value for rule r? -> None or a short text.'''
	t = rule_type(r)
	if a is None:
		return 'no value'
	if t == 'switch' and not (a[0] == 'word' and a[1] in ('on', 'off')):
		return 'use on or off'
	if t == 'choice':
		opts = options_of(r.kids('options')[0])
		if value(a) not in opts and ser(a) not in [str(o) for o in opts]:
			return 'use one of: ' + ', '.join(str(o) for o in opts)
	if t == 'number':
		if a[0] != 'num':
			return 'use a number'
		v = value(a)
		lo, hi = rule_range(r)
		if lo is not None and v < lo:
			return 'the value is below the range: at least {}'.format(lo)
		if hi is not None and v > hi:
			return 'the value is above the range: at most {}'.format(hi)
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
		self.body = [item_id(x, self.bids) for x in seq]
		self.start = self.seq([x for x in seq if x.head != 'finally'], None, None, None)
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
		prev = {}  # the nearest step before each item in this body, past gates only: "retry" goes back to it
		for k, (it, _) in enumerate(groups):
			back = None
			for j in range(k - 1, -1, -1):
				h = groups[j][0].head
				if h == 'step':
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
		elif h in ('else', 'finally'):
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
def retry_problem(c, byrule):
	'''"retry <n>" or "retry <rule id>" (a number rule, so that a preset can change it). -> None or the error.'''
	if len(c.args) == 1 and c.args[0][0] == 'num' and isinstance(value(c.args[0]), int) and value(c.args[0]) >= 1:
		return None
	if len(c.args) == 1 and c.args[0][0] == 'word' and c.word(0) in byrule:
		return None if rule_type(byrule[c.word(0)]) == 'number' else 'retry {}: the rule must be a number'.format(c.word(0))
	return 'write retry <n> (a whole number, 1 or more) or retry <rule id> (a number rule)'


def removed(c, parent):
	'''-> the error text for a word of version 0 that version 1 refuses, or None.'''
	if c.head == 'unit' and parent.head == 'rule':
		return '"unit" under a rule is a word of version 0: put the unit in the label. "unit" is only the container'
	if c.head in REMOVED and not (c.head == 'check' and parent.head == 'probe'):
		return '"{}" is a word of version 0: {}'.format(c.head, REMOVED[c.head])
	return None


def check(root, path=None):
	'''-> (errors, warnings): lists of (line, text). path: the file, to check the files of "code" and "uses" lines.'''
	err, warn = [], []
	names = set()
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
			err.append((u.line, 'the scope "snippet" is a word of version 0: use tool or agent, and put the code in a file (code <path>)'))
		elif u.word(1) and u.word(1) not in SCOPES:
			err.append((u.line, 'scope "{}": use tool or agent'.format(u.word(1))))

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
		for e in u.kids('example'):
			if '=>' not in [ser(a) for a in e.args]:
				err.append((e.line, 'an example needs "=>"'))
		for n in u.kids('in') + u.kids('out'):
			t = in_parts(n)[1]
			bad = type_problem(t) if t else None
			if bad:
				warn.append((n.line, bad))
		base = os.path.dirname(os.path.abspath(path)) if path else None
		cctx = Ctx(root, path) if path else None
		prefixes = [c['prefix'] for c in code_lines(u)]
		for c in code_lines(u):
			if not c['file']:
				err.append((c['line'], 'write "code <path>" or "code <prefix> <path>"'))
			elif prefixes.count(c['prefix']) > 1:
				err.append((c['line'], 'two "code" lines for {}'.format('"' + c['prefix'] + '"' if c['prefix'] else 'the unit')))
			elif base:
				for k in ('file', 'test'):
					if c[k] and not os.path.exists(os.path.join(base, c[k])):
						err.append((c['line'], 'the {} file "{}" does not exist'.format('code' if k == 'file' else 'test', c[k])))
				if c['prefix'] is None and os.path.exists(os.path.join(base, c['file'])) and bound_level(name, u, cctx) == 'none':
					err.append((c['line'], '"{}" has no function "{}"'.format(c['file'], name.replace('-', '_'))))
		if path:
			for x in u.kids('uses'):
				f = x.word(1)
				if not f:
					continue
				p = os.path.join(base, f)
				if not os.path.exists(p):
					warn.append((x.line, 'the file "{}" does not exist'.format(f)))
					continue
				try:
					with open(p, encoding='utf-8', newline='') as fh:
						there = [v.word(0) for v in units(parse(fh.read()))]
				except (RigError, OSError) as e:
					warn.append((x.line, 'the file "{}" cannot be read: {}'.format(f, e)))
					continue
				if x.word(0) not in there:
					warn.append((x.line, 'the file "{}" has no unit "{}"'.format(f, x.word(0))))

		# Rules and presets
		rules = set(r.word(0) for r in u.kids('rule'))
		byrule = dict((r.word(0), r) for r in u.kids('rule'))
		for r in u.kids('rule'):
			rid = r.word(0)
			if not rid or not RULE_ID.match(rid):
				err.append((r.line, 'rule id "{}": write it as group.name'.format(rid or '')))
				continue
			if len(r.args) > 2 and r.args[2][0] != 'str':
				err.append((r.line, 'rule "{}": after the value, only the label as a "string"'.format(rid)))
			elif len(r.args) > 3:
				err.append((r.line, 'rule "{}": write the value, then the label as one "string"'.format(rid)))
			for g in r.kids('range'):
				if len(g.args) != 2 or any(a[0] != 'num' for a in g.args):
					err.append((g.line, 'rule "{}": write range <min> <max>, two numbers'.format(rid)))
				elif value(g.args[0]) > value(g.args[1]):
					err.append((g.line, 'rule "{}": the range starts above its end'.format(rid)))
			bad = rule_problem(r, r.args[1] if len(r.args) > 1 else None)
			if bad:
				err.append((r.line, 'rule "{}": {}'.format(rid, bad)))
		for n, t in walk_strings(u):
			for m in PLACE.finditer(t):
				if m.group(1) not in rules:
					err.append((n.line, '{{{}}} names a rule that is not defined in this unit'.format(m.group(1))))
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

		# The flow
		if not has_flow(u):
			continue
		top = items(u)
		for k, it in enumerate(top):
			if it.head == 'finally' and k != len(top) - 1:
				err.append((it.line, '"finally" is the last block of a flow'))
		for it in walk_items(u):
			if it.head == 'finally' and it.parent is not u:
				err.append((it.line, '"finally" is a block of the unit, not of another block'))
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
		read = set()
		for f in nodes:
			fid, kind = f.word(0), f.word(1) if f.head == 'gate' else f.head
			read.update(node_reads(f))
			for c in f.children:
				if c.head == 'reads':
					for a in c.args:
						if a[1] not in rules:
							err.append((c.line, 'rule "{}" is not defined in this unit'.format(a[1])))
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
					t = c.args[0] if c.args else None
					bad = type_problem(t) if t else 'write out <type>'
					if bad:
						err.append((c.line, bad))
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
					warn.append((b.line, '"by {}" names no unit or "code" line: add "code <prefix> <path>" for code in a file'.format(b.word(0))))
				elif base and t == 'bound':
					c, fn = code_for(b.word(0), u)
					level = bound_level(b.word(0), u, cctx)
					if level == 'none' and c['file'] and os.path.exists(os.path.join(base, c['file'])):
						err.append((b.line, '"{}" has no function "{}"'.format(c['file'], fn)))
					elif level == 'code' and f.head == 'gate':
						warn.append((b.line, 'no test names "{}": {}'.format(fn, 'add a test to "{}"'.format(c['test']) if c['test'] else 'add a "test <path>" line under its "code" line')))
		for it in walk_items(u):
			if it.head not in BLOCKS:
				continue
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
			if it.head in ('else', 'section', 'finally', 'if') and (it.kids('fail') or it.kids('retry') or it.kids('tolerate')):
				err.append((it.line, '"{}" has no options: only a body'.format(it.head)))
		# Reach: every node from the start (or from "finally")
		seen = set()
		todo = [x for x in (fl.start, fl.final) if x]
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
		runs_off = any(d['next'] is None and fid in seen and ids.get(fid) is not None and ids[fid].head != 'end' and not (fl.final and d['block'] and fl.blocks.get(d['block'], {}).get('kind') == 'finally')
			for fid, d in fl.nodes.items())
		if runs_off and last:
			warn.append((u.line, 'the flow can run past its last line: end it with an "end" line'))
		for r in u.kids('rule'):
			if r.word(0) not in read:
				warn.append((r.line, 'rule "{}" is not read by any step or gate'.format(r.word(0))))
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
	d = {'id': r.word(0), 'group': r.word(0).split('.')[0], 'label': rule_label(r) or r.word(0),
		'type': rule_type(r), 'value': value(token if token is not None else a) if (token or a) else None,
		'default': value(a) if a else None}
	lo, hi = rule_range(r)
	if lo is not None:
		d['min'] = lo
	if hi is not None:
		d['max'] = hi
	if r.kids('options'):
		d['options'] = options_of(r.kids('options')[0])
	ns = notes_of(r)
	if ns:
		d['note'] = ' '.join(x['text'] for x in ns)
	return d


def presets_of(u):
	return dict((p.word(0), dict((x.word(0), value(x.args[1])) for x in p.kids('set') if len(x.args) > 1)) for p in u.kids('preset'))


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
	if f.head == 'gate':
		return {'model': 'model', 'human': 'person'}.get(f.word(1), 'code')
	bys = [b.word(0) for b in f.kids('by')]
	return 'model' if not bys or 'model' in bys else 'code'


def node_info(f, fl):
	d = {'id': f.word(0), 'kind': f.word(1) if f.head == 'gate' else f.head, 'lane': lane_of(f)}
	nm = name_of(f)
	if nm:
		d['name'] = nm
	for k in PROSE:
		xs = f.kids(k)
		if xs:
			d[k] = ' '.join(text_of(x) for x in xs)
	bys = [x.word(0) for x in f.kids('by') if x.word(0) != 'model']
	if bys:
		d['by'] = bys
	rd = node_reads(f)
	if rd:
		d['reads'] = rd
	sees = [a[1] for c in f.kids('sees') for a in c.args]
	if sees:
		d['sees'] = sees
	if f.kids('out') and f.kids('out')[0].args:
		t = f.kids('out')[0].args[0]
		d['out'], d['schema'] = ser(t), type_schema(t)
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


def block_info(bid, b):
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
	'''An "in" or "out" node -> {"name", "type", "text"} ("name" for "in" only).'''
	name, t, text = in_parts(n)
	d = {'name': name} if n.head == 'in' else {}
	d.update({'type': ser(t) if t else None, 'text': text})
	return d


def catalog(u, preset=None, ctx=None):
	'''A unit as a catalogue: the JSON that the runner reads. Every edge is written out (Flow).'''
	toks = preset_tokens(u, preset)
	fl = Flow(u)
	uses = []
	for x in u.kids('uses'):
		d = {'unit': x.word(0)}
		if x.word(1):
			d['file'] = x.word(1)
		uses.append(d)
	order = [item_id(x, fl.bids) for x in walk_items(u) if x.head in BLOCKS]
	return {
		'rig': VERSION, 'unit': u.word(0), 'scope': u.word(1, 'tool'), 'preset': preset,
		'intent': ' '.join(text_of(x) for x in u.kids('intent')),
		'notes': notes_of(u), 'uses': uses,
		'code': [dict((k, c[k]) for k in ('prefix', 'file', 'test')) for c in code_lines(u)],
		'in': [port_info(x) for x in u.kids('in')],
		'out': port_info(u.kids('out')[0]) if u.kids('out') else None,
		'examples': [' '.join(ser(a) for a in x.args) for x in u.kids('example')],
		'checks': [text_of(x) for x in u.kids('check')],
		'start': fl.start, 'finally': fl.final, 'body': [item_id(x, fl.bids) for x in items(u)],
		'coverage': coverage(u, ctx),
		'presets': presets_of(u),
		'rules': [rule_info(r, toks.get(r.word(0))) for r in u.kids('rule')],
		'flow': [node_info(f, fl) for f in flow_nodes(u)],
		'blocks': [block_info(b, fl.blocks[b]) for b in order if b in fl.blocks],
	}


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


def fill_values(u, t, preset=None):
	'''Write the value of each rule in place of {group.name} in t.'''
	toks = preset_tokens(u, preset)
	byrule = dict((r.word(0), r) for r in u.kids('rule'))
	return PLACE.sub(lambda m: show(toks.get(m.group(1), byrule[m.group(1)].args[1] if len(byrule[m.group(1)].args) > 1 else None))
		if m.group(1) in byrule else m.group(0), t)


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
			return PLACE.sub(lambda m: '`{' + m.group(1) + '}`' if m.group(1) in byrule else m.group(0), t)
		return fill_values(u, t, preset)

	def cell(t):
		return t.replace('|', '\\|')
	c = catalog(u, preset)
	intent = fill(c['intent'])
	out = ['---', 'name: ' + u.word(0), 'description: ' + intent, '---', '', '# ' + u.word(0), '']
	if intent:
		out += [intent, '']
	for n in c['notes']:
		out.append('Note: ' + fill(n['text']))
	if c['notes']:
		out.append('')
	if c['rules']:
		out += ['## Rules', '']
		if rules_path:
			out += ['Read the value of each rule from `' + rules_path + '`: the `rules` list, by `id`. Do not copy the values into your work. In the text below, `{group.name}` means the value of that rule.', '',
				'| Rule | Meaning |', '|---|---|']
		else:
			out += ['| Rule | Value | Meaning |', '|---|---|---|']
		for r in u.kids('rule'):
			info = rule_info(r)
			lim = []
			if 'min' in info or 'max' in info:
				lim.append('range {} to {}'.format(info.get('min', '…'), info.get('max', '…')))
			if 'options' in info:
				lim.append('one of: ' + ', '.join(str(o) for o in info['options']))
			mean = info['label'] + ('; ' + ', '.join(lim) if lim else '')
			if 'note' in info:
				mean += '. Note: ' + info['note']
			if rules_path:
				out.append('| `{}` | {} |'.format(info['id'], cell(mean)))
			else:
				out.append('| `{}` | `{}` | {} |'.format(info['id'], cell(val(info['id'])), cell(mean)))
		out.append('')
	if not c['flow']:
		return '\n'.join(out).rstrip('\n') + '\n'
	nodes = dict((f['id'], f) for f in c['flow'])
	blocks = dict((b['id'], b) for b in c['blocks'])
	if driver:
		args = ' '.join("{}=<{}>".format(x['name'], x['type'] or 'value') for x in c['in'])
		out += ['## How to run', '',
			'Code walks this flow. You do not walk it yourself: you start a run and answer what waits.',
			'Run every command in the folder of the tool (the folder that holds `rig.json`).', '',
			'1. Start a run: `{} run \'<inputs as JSON>\'`{}.'.format(driver, ' (inputs: ' + args + ')' if args else ''),
			'2. Read the result. It is one JSON object.',
			'   - `outcome`: the run ended at that end. Report it, with `problems` first. `result` is what the run made (only when a step leads to the end).',
			'   - `waiting`: the run stopped at a node that code cannot do. Read `kind`, `do` and `check`. `sees` holds the facts of the run that you need for this node: use them, and nothing else.',
			'     - `model` (a gate): decide what `check` says. Answer: `{} answer <run> \'{{"pass": true}}\'` (or false, with `"why"`).'.format(driver),
			'     - `step`: do what `do` says. Answer: `{} answer <run> \'{{"result": ...}}\'`. When `waiting` has `schema`, the result must have that form.'.format(driver),
			'     - `human`: show the person the question (`name` and `check`), `sees`, and the text of `say` as it is (it names the answers; the first option is the default). Then wait. Give the answer of the person, never your own: `{} approve <run> yes` (or `no`), or `{} approve <run> <the words of the person>`.'.format(driver, driver),
			'   - `problems` in `waiting`: your last answer at this node failed. Fix these problems in the new answer.',
			'   - `refused`: the call was out of order. It is final: do not repeat it. Read `at` and continue from there.',
			'3. Repeat step 2 until the result has `outcome`. The outcome `error` means that code failed: report the error text. Do not answer for code.', '',
			'Never decide a hard or soft gate: code decides them. Use only values from a result or from the rules.',
			'`{} status <run>` shows a run again; `{} rules` shows the rules.'.format(driver, driver), '',
			'More than one item: `{} batch \'<a JSON list of inputs>\' --report reports/<name>.md`. Code starts a run for each item and gives a summary. Then answer the runs in `left_for_model`, one at a time (`status <run>` shows what each waits for). Give the person the list `waits_for_person` and the path of the report. `{} queues` shows what waits, at any time.'.format(driver, driver), '',
			'## Flow (the map of the run)', '',
			'The lines run in order. A gate that passes goes on to the next line.', '']
	else:
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
		label = {'step': 'step', 'end': 'end'}.get(k, k + ' gate')
		h = '#' * min(6, 3 + depth)
		out.extend(['{} `{}`{} ({})'.format(h, f['id'], ' ' + fill(f['name']) if f.get('name') else '', label), ''])
		if 'if' in f:
			out.append('- Only when `{}` is not empty and not false. Else go on to the next line.'.format(f['if']))
		for key, title in (('do', 'Do'), ('check', 'Check')):
			if key in f:
				out.append('- {}: {}'.format(title, fill(f[key])))
		if 'reads' in f:
			out.append('- Rules: ' + ', '.join('`{}`'.format(r) if rules_path or r not in byrule else '`{}` = {}'.format(r, val(r)) for r in f['reads']))
		if 'sees' in f:
			out.append('- Sees: ' + ', '.join('`{}`'.format(x) for x in f['sees']))
		if 'out' in f:
			out.append('- The answer has the type `{}`.'.format(f['out']))
		by = ', '.join('`{}`'.format(b) for b in f.get('by', []))
		guess = '- No code decides this gate yet: decide it yourself and label the result as a guess.'
		if driver and by and k in ('step', 'hard', 'soft'):
			out.append('- {} by code: {}. The runner does this.'.format('Done' if k == 'step' else 'Decided', by))
		elif k == 'step' and f['lane'] == 'model':
			out.append('- You do this step{}.'.format(' when the run waits here' if driver else ''))
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
		if not driver and k != 'end':
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
			'if': 'If `{}`'.format(b.get('path')), 'else': 'Else (when the `if` before did not run)', 'finally': 'Finally: always, after the run ends (also after an error)'}[k]
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


# - Decompile: catalogue (JSON) -> Rig ---------------
def quote(t):
	return '"' + str(t).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def token(v, t='text'):
	if isinstance(v, bool):
		return 'on' if v else 'off'
	if isinstance(v, (int, float)):
		return repr(v)
	if isinstance(v, list):
		return '(' + ' '.join(token(x) for x in v) + ')'
	if t == 'pattern':
		return '/' + v + '/'
	if t == 'choice' and re.match(r'^[A-Za-z_][\w.-]*$', v):
		return v
	return quote(v)


def from_catalog(c):
	'''A catalogue (as made by catalog()) -> Rig text. Not the original layout; the same meaning.'''
	out = ['unit {} {}'.format(c['unit'], c.get('scope', 'agent'))]
	if c.get('intent'):
		out.append('  intent ' + quote(c['intent']))
	for x in c.get('uses', []):
		out.append('  uses ' + x['unit'] + (' ' + x['file'] if x.get('file') else ''))
	for x in c.get('code', []):
		out.append('  code ' + (x['prefix'] + ' ' if x.get('prefix') else '') + x['file'])
		if x.get('test'):
			out.append('    test ' + x['test'])
	for x in c.get('in', []):
		out.append('  in ' + x['name'] + (' ' + x['type'] if x.get('type') else '') + (' ' + quote(x['text']) if x.get('text') else ''))
	o = c.get('out')
	if o is not None:
		out.append('  out' + (' ' + o['type'] if o.get('type') else '') + (' ' + quote(o['text']) if o.get('text') else ''))
	for x in c.get('examples', []):
		out.append('  example ' + x)
	for x in c.get('checks', []):
		out.append('  check ' + quote(x))

	def notes(ns, ind):
		for n in ns:
			out.append(ind + 'note ' + quote(n['text']))
	notes(c.get('notes', []), '  ')
	types = {}
	for r in c.get('rules', []):
		t = r.get('type', 'text')
		types[r['id']] = t
		out.append('  rule {} {}'.format(r['id'], token(r.get('default', r.get('value')), t)) + (' ' + quote(r['label']) if r.get('label') and r['label'] != r['id'] else ''))
		if 'min' in r or 'max' in r:
			out.append('    range {} {}'.format(token(r.get('min')), token(r.get('max'))))
		if 'options' in r:
			out.append('    options ' + ' | '.join(token(o, 'choice') for o in r['options']))
		if 'note' in r:
			out.append('    note ' + quote(r['note']))
	for name, sets in c.get('presets', {}).items():
		out.append('  preset ' + name)
		for rid, v in sets.items():
			out.append('    set {} {}'.format(rid, token(v, types.get(rid, 'text'))))
	nodes = dict((f['id'], f) for f in c.get('flow', []))
	blocks = dict((b['id'], b) for b in c.get('blocks', []))

	def node(f, ind):
		k = f['kind']
		head = 'gate {} {}'.format(f['id'], k) if k in GATE_KINDS else '{} {}'.format(k, f['id'])
		out.append(ind + head + (' ' + quote(f['name']) if f.get('name') else ''))
		i2 = ind + '  '
		if 'if' in f:
			out.append(i2 + 'if ' + f['if'])
		for key in ('retry',):
			if key in f:
				out.append(i2 + 'retry {}'.format(f[key]))
		if 'options' in f:
			out.append(i2 + 'options ' + ' | '.join(str(o) for o in f['options']))
		for key in PROSE:
			if key in f:
				out.append(i2 + '{} {}'.format(key, quote(f[key])))
		for b in f.get('by', []):
			out.append(i2 + 'by ' + b)
		if k == 'step' and f.get('lane') == 'model':
			out.append(i2 + 'by model')
		if 'out' in f:
			out.append(i2 + 'out ' + f['out'])
		if f.get('reads'):
			out.append(i2 + 'reads ' + ' '.join(f['reads']))
		if f.get('sees'):
			out.append(i2 + 'sees ' + ' '.join(f['sees']))
		if 'timeout_text' in f:
			out.append(i2 + 'timeout ' + f['timeout_text'])
		notes(f.get('notes', []), i2)
		for l in f.get('fail', []):
			out.append(i2 + 'fail -> {}{}'.format('continue' if l.get('continue') else l['to'], ' ' + quote(l['when']) if 'when' in l else ''))

	def block(b, ind):
		k = b['kind']
		head = {'for': 'for {} in {}'.format(b.get('item'), b.get('path')), 'until': 'until ' + str(b.get('path')), 'if': 'if ' + str(b.get('path')),
			'else': 'else', 'section': 'section ' + quote(b.get('name', '')), 'finally': 'finally'}[k]
		out.append(ind + head)
		i2 = ind + '  '
		if 'tolerate' in b:
			out.append(i2 + 'tolerate {}%'.format(b['tolerate']))
		if 'retry' in b:
			out.append(i2 + 'retry {}'.format(b['retry']))
		for l in b.get('fail', []):
			out.append(i2 + 'fail -> ' + l['to'] + (' ' + quote(l['when']) if 'when' in l else ''))
		body(b['body'], i2)

	def body(ids, ind):
		for x in ids:
			if x in nodes:
				node(nodes[x], ind)
			elif x in blocks:
				block(blocks[x], ind)
	body(c.get('body', []), '  ')
	return '\n'.join(out) + '\n'


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
		return text, parse(text)
	except RigError as e:
		raise SystemExit('{}: {}'.format(path, e))


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
		return json.dumps(tool_def(u, preset), ensure_ascii=False, indent=1) + '\n'
	raise SystemExit('compile json, compile skill or compile tool')


def outputs(path, unit=None, json_out=None, skill_out=None, rules_ref=False, preset=None):
	'''Compile FILE to the files that agents read. -> the paths written.'''
	text, root = load(path)
	err, _ = check(root)
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


def bound_levels(path):
	'''For the viewer, which cannot read the code files: unit -> {"by" name -> level}.'''
	try:
		text, root = load(path)
	except SystemExit:
		return {}
	ctx, out = Ctx(root, path), {}
	for u in units(root):
		names = [b.word(0) for f in flow_nodes(u) for b in f.kids('by')] + [u.word(0)]
		got = dict((b, bound_level(b, u, ctx)) for b in names if b and code_for(b, u))
		if got:
			out[u.word(0)] = got
	return out


def run_file(folder, run_id):
	'''The file of one run: <runs>/<id>/run.json (the run folder of version 1), or <runs>/<id>.json.'''
	if not re.match(r'^[\w.-]+$', run_id or ''):
		return None
	for p in (os.path.join(folder, run_id, 'run.json'), os.path.join(folder, run_id + '.json')):
		if os.path.exists(p):
			return p
	return None


def run_list(folder):
	'''The runs of a tool (the files that rigkit writes), newest first, for the viewer.'''
	out = []
	if not os.path.isdir(folder):
		return out
	for n in sorted(os.listdir(folder), reverse=True)[:200]:
		p = run_file(folder, n[:-5] if n.endswith('.json') else n)
		if not p:
			continue
		try:
			with open(p, encoding='utf-8') as f:
				r = json.load(f)
			o = r.get('outcome')
			state = 'ended at {}'.format(o.get('end') or o.get('label') or 'a stop') if o else 'waits at ' + str(r['at'])
			out.append({'id': r['id'], 'state': state})
		except (OSError, ValueError, KeyError, TypeError, AttributeError):
			pass
	return out


def bundle(text, path=None):
	'''Everything the viewer shows for one file, compiled here: the viewer has no parser of its own.
	-> {"file", "text", "errors", "warnings", "units": [...]}; each unit has its catalogue, skill,
	tool definition, status, the levels of its gates, and where each rule value is in the text.'''
	out = {'rig': VERSION, 'file': os.path.basename(path) if path else 'untitled.rig', 'text': text, 'errors': [], 'warnings': [], 'units': []}
	try:
		root = parse(text)
	except RigError as e:
		out['errors'] = [[e.line, str(e).split(': ', 1)[-1]]]
		return out
	err, warn = check(root, path)
	out['errors'], out['warnings'] = [list(x) for x in sorted(err)], [list(x) for x in sorted(warn)]
	ctx = Ctx(root, path) if path else Ctx(root)
	for u in units(root):
		name = u.word(0) or '?'
		d = {'name': name, 'scope': u.word(1, 'tool'), 'status': unit_status(u, ctx), 'flow': has_flow(u)}
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
			if r.word(0) and len(r.args) > 1 and len(r.spans) > 1:
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
	pages = [os.path.join(here, 'viewer.html'), os.path.join(here, '..', '..', 'viewer', 'index.html')]
	page = next((p for p in pages if os.path.exists(p)), None)
	if not page:
		raise SystemExit('the viewer is not found: copy viewer/index.html next to rig.py as viewer.html')
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
			if self.path in ('/', '/index.html'):
				self.send_response(302)
				self.send_header('Location', '/viewer?serve=1')
				self.end_headers()
			elif self.path.startswith('/viewer'):
				with open(page, encoding='utf-8') as f:
					self.reply(200, f.read(), 'text/html; charset=utf-8')
			elif self.path == '/file':
				with open(path, encoding='utf-8', newline='') as f:
					self.reply(200, f.read(), 'text/plain; charset=utf-8')
			elif self.path == '/bundle':
				with open(path, encoding='utf-8', newline='') as f:
					self.reply(200, json.dumps(bundle(f.read(), path), ensure_ascii=False))
			elif self.path == '/levels':
				self.reply(200, json.dumps(bound_levels(path)))
			elif self.path == '/runs':
				self.reply(200, json.dumps(run_list(runs)))
			elif self.path.startswith('/runs/') and run_file(runs, self.path[6:]):
				with open(run_file(runs, self.path[6:]), encoding='utf-8') as f:
					self.reply(200, f.read())
			else:
				self.reply(404, json.dumps({'error': 'not found'}))

		def do_POST(self):
			if self.path not in ('/file', '/compile'):
				return self.reply(404, json.dumps({'error': 'not found'}))
			text = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8')
			if self.path == '/compile':  # compile changed text for the viewer; write nothing
				return self.reply(200, json.dumps(bundle(text, path), ensure_ascii=False))
			try:
				err, _ = check(parse(text))
			except RigError as e:
				return self.reply(400, json.dumps({'error': str(e)}))
			if err:
				return self.reply(400, json.dumps({'error': 'line {}: {}'.format(err[0][0], err[0][1])}))
			with open(path, 'w', encoding='utf-8', newline='') as f:
				f.write(text)
			try:
				done = outputs(path, **outs)
			except SystemExit as e:
				return self.reply(400, json.dumps({'error': str(e)}))
			self.reply(200, json.dumps({'saved': os.path.basename(path), 'wrote': done, 'bundle': bundle(text, path)}, ensure_ascii=False))

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
	if argv and argv[0] in ('new', 'build', 'doctor', 'test', 'plugin'):
		import rig_project
		return rig_project.main(argv[0], list(argv[1:]))
	if argv and argv[0] in ('hash', 'prove', 'probe', 'stamp', 'emit'):
		print('"{}" is a command of version 0: casts and hashes are gone. The code lives in files; its tests prove it (rig.py test).'.format(argv[0]))
		return 2
	if len(argv) < 2 or argv[0] not in ('check', 'json', 'compile', 'from-json', 'serve'):
		print(__doc__)
		return 2
	cmd, rest = argv[0], list(argv[1:])
	if cmd == 'compile':
		kind = rest.pop(0)
		preset, out, rules, driver = option(rest, '--preset'), option(rest, '-o'), option(rest, '--rules'), option(rest, '--driver')
		if not rest:
			raise SystemExit('compile {} FILE [UNIT]'.format(kind))
		text, root = load(rest[0])
		err, _ = check(root)
		if err:
			raise SystemExit('{}: line {}: {}'.format(rest[0], err[0][0], err[0][1]))
		result = compile_to(kind, pick(root, rest[1] if len(rest) > 1 else None), preset, rules, Ctx(root, rest[0]), driver)
		if out:
			write(out, result)
		else:
			sys.stdout.write(result)
		return 0
	if cmd == 'from-json':
		out = option(rest, '-o')
		with open(rest[0], encoding='utf-8') as f:
			result = from_catalog(json.load(f))
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
				print('  {:<28} {}'.format('{} ({})'.format(u.word(0), u.word(1, 'tool')), '; '.join(unit_status(u, ctx))))
			err, warn = check(root, path)
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
