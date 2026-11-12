#!/usr/bin/env python3
"""rig.py: reference tool for the Rig language, version 0. Standard library only.

    python rig.py check FILE...               validate; show the status of every unit
    python rig.py hash FILE                   print the matrix and body hashes of every unit
    python rig.py prove FILE [UNIT] [--stamp] run the examples and checks against each cast
        [--lang L]                            that has a runner (py, js, ts); --stamp writes
                                              the hashes, "proved" and the date when all pass
    python rig.py probe FILE [UNIT] [--stamp] run the probes: live runs against the real world;
        [--lang L]                            --stamp writes "observed" for a cast that has
                                              no examples
    python rig.py stamp FILE UNIT LANG        write the hashes and today's date into a cast in a
                                              language with no runner, ONLY after you proved
                                              it in its own runtime
    python rig.py emit FILE LANG DIR [UNIT]   write the proved and observed casts in LANG as
                                              modules into DIR, each with its catalogue
    python rig.py json FILE                   the parsed tree as JSON
    python rig.py compile json FILE [UNIT]    the unit as a catalogue: rules, presets and flow,
                                              the JSON that a code runner reads
    python rig.py compile skill FILE [UNIT]   the unit as a SKILL.md for an agent that follows
                                              instructions; --rules PATH: refer to the values
                                              in that JSON file instead of writing them in
    python rig.py compile tool FILE [UNIT]    the unit as a tool definition: name, description
                                              and the JSON Schema of its inputs
        compile options: --preset NAME (use the values of a preset), -o OUT (write a file)
    python rig.py from-json FILE.json         a catalogue back to Rig (the same meaning)
    python rig.py serve FILE [UNIT]           the viewer for FILE on 127.0.0.1; Save writes FILE
        [--port 8765] [--json OUT] [--skill OUT] [--rules-ref]
                                              and compiles it again to OUT; --rules-ref makes
                                              the skill read its values from the JSON

The language is defined in spec.md (same folder). `prove` and `probe` run the code of the
file on your machine: use them only on files you trust. On macOS use python3.
"""
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

MATRIX = ('in', 'out', 'intent', 'example', 'ensure')
FLOW = ('step', 'gate', 'end')
GATE_KINDS = ('hard', 'soft', 'judge')
SCOPES = ('snippet', 'tool', 'agent')
LEVELS = ('none', 'code', 'observed', 'proved')  # low to high; "judge" is apart
STAMPS = ('proved', 'observed')
BASE_TYPES = ('str', 'text', 'word', 'path', 'int', 'float', 'bool', 'list', 'dict', 'any')
TYPE_LISTS = ('list', 'tuple', 'record', 'maybe', 'one-of')
CHILDREN = {
	'unit': {'in', 'out', 'intent', 'example', 'ensure', 'note', 'uses', 'external', 'probe', 'rule', 'preset', 'cast', 'step', 'gate', 'end'},
	'ensure': {'check', 'note'},
	'probe': {'check', 'note'},
	'external': {'note'},
	'preset': {'set'},
	'note': {'evidence'},
	'rule': {'min', 'max', 'options', 'unit', 'label', 'note'},
	'step': {'do', 'by', 'reads', 'next', 'note'},
	'gate': {'when', 'reads', 'ensure', 'by', 'brief', 'pass', 'fail', 'note'},
	'end': {'note'},
}
NUMBER = re.compile(r'^-?\d+(\.\d+)?$')
RULE_ID = re.compile(r'^[A-Za-z_][\w-]*(\.[\w-]+)+$')
PLACE = re.compile(r'\{([A-Za-z_][\w-]*(?:\.[\w-]+)+)\}')
PROSE_NUMBER = re.compile(r'(?<![\w.#{-])\d+(?:\.\d+)?(?![\w}])')
PROSE = ('when', 'do', 'ensure', 'brief')


class RigError(Exception):
	def __init__(self, line, text):
		Exception.__init__(self, 'line {}: {}'.format(line, text))
		self.line = line


class Node(object):
	def __init__(self, head, args, line, indent):
		self.head, self.args, self.line, self.indent = head, args, line, indent
		self.children = []
		self.body = None  # raw lines, cast only

	def word(self, i, default=None):
		return self.args[i][1] if len(self.args) > i else default

	def kids(self, head):
		return [c for c in self.children if c.head == head]


# - Parsing ------------------------------------------
def tokenize(s, line):
	'''One line (without its indentation) -> a list of args: (kind, text) or ('list', [...]).'''
	out, stack, i, n = [], [], 0, len(s)
	while i < n:
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
	return out


def ser(arg):
	kind, v = arg
	return '(' + ' '.join(ser(a) for a in v) + ')' if kind == 'list' else v


def parse(text):
	'''Text -> the root node (head "file"). Raises RigError.'''
	lines = text.replace('\r\n', '\n').split('\n')
	root = Node('file', [], 0, -1)
	stack = [root]
	i = 0
	while i < len(lines):
		raw, line = lines[i], i + 1
		body = raw.lstrip(' \t')
		if not body.strip() or body.startswith(';'):
			i += 1
			continue
		lead = raw[:len(raw) - len(body)]
		if '\t' in lead:
			raise RigError(line, 'a tab in the indentation: indent with spaces')
		indent = len(lead)
		while stack[-1].indent >= indent:
			stack.pop()
		toks = tokenize(body, line)
		if not toks:
			i += 1
			continue
		if toks[0][0] != 'word':
			raise RigError(line, 'a line must start with a word')
		node = Node(toks[0][1], toks[1:], line, indent)
		stack[-1].children.append(node)
		i += 1
		if node.head == 'cast':
			cast = []
			while i < len(lines):
				r = lines[i]
				if r.strip() and len(r) - len(r.lstrip(' \t')) <= indent:
					break
				cast.append(r)
				i += 1
			while cast and not cast[-1].strip():
				cast.pop()
			node.body = cast
			continue
		stack.append(node)
	for u in root.children:
		u.root = root  # a unit knows its file: "by" can name the other units in it
	return root


# - Hashes -------------------------------------------
def h8(text):
	return hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]


def canon(node, depth):
	return '  ' * depth + ' '.join([node.head] + [ser(a) for a in node.args])


def matrix_text(unit):
	out = []

	def walk(n, d):
		out.append(canon(n, d))
		for c in n.children:
			walk(c, d + 1)
	for c in unit.children:
		if c.head in MATRIX:
			walk(c, 0)
	return '\n'.join(out)


def body_text(lines):
	lines = [l.rstrip() for l in lines or []]
	while lines and not lines[0]:
		lines.pop(0)
	while lines and not lines[-1]:
		lines.pop()
	full = [l for l in lines if l]
	cut = min(len(l) - len(l.lstrip(' \t')) for l in full) if full else 0
	return '\n'.join(l[cut:] for l in lines)


def matrix_hash(unit):
	return '#' + h8(matrix_text(unit))


def body_hash(cast):
	return '#' + h8(body_text(cast.body))


def cast_info(cast):
	words = [ser(a) for a in cast.args]
	hashes = [w for w in words if w.startswith('#')]
	stamp = next((w for w in words if w in STAMPS), None)
	date = words[words.index(stamp) + 1] if stamp and words.index(stamp) + 1 < len(words) else None
	return {'lang': words[0] if words else '?', 'matrix': hashes[0] if hashes else None,
			'body': hashes[1] if len(hashes) > 1 else None, 'stamp': stamp, 'date': date}


def cast_state(unit, c):
	'''-> "unproved", "remelted", "stale", "proved" or "observed".'''
	info = cast_info(c)
	if not info['matrix']:
		return 'unproved'
	if info['matrix'] != matrix_hash(unit):
		return 'remelted'
	if info['body'] != body_hash(c):
		return 'stale'
	return info['stamp'] or 'proved'


# - Types --------------------------------------------
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
			return {'type': 'object', 'properties': props, 'required': req}
		if head == 'maybe':
			return {'anyOf': [type_schema(rest[0]) if rest else {}, {'type': 'null'}]}
		if head == 'one-of':
			return {'enum': [value(x) for x in rest]}
		return {}
	return {'str': {'type': 'string'}, 'text': {'type': 'string'}, 'word': {'type': 'string'}, 'path': {'type': 'string'},
		'int': {'type': 'integer'}, 'float': {'type': 'number'}, 'bool': {'type': 'boolean'},
		'list': {'type': 'array'}, 'dict': {'type': 'object'}}.get(t[1], {})


def in_parts(n):
	'''An "in" node -> (name, type token or None, text). An "out" node: the name is None.'''
	args = n.args[1:] if n.head == 'in' else n.args
	t = next((a for a in args if a[0] != 'str'), None)
	text = next((value(a) for a in args if a[0] == 'str'), '')
	return (n.word(0) if n.head == 'in' else None), t, text


# - Status, levels and check -------------------------
def units(root):
	return [u for u in root.children if u.head == 'unit']


class Ctx(object):
	'''The units that "by" can reach: the units of the file, and of the files in "uses" lines.'''

	def __init__(self, root, path=None):
		self.units, self.files = {}, set()
		self.add(root, path)

	def add(self, root, path):
		for u in units(root):
			self.units.setdefault(u.word(0), u)
		if not path:
			return
		base = os.path.dirname(os.path.abspath(path))
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


def unit_level(name, ctx, seen=()):
	'''How much is known about the code of a unit: proved, observed or code.'''
	u = ctx.units.get(name)
	if u is None or name in seen:
		return 'code'
	states = [cast_state(u, c) for c in u.kids('cast')]
	for s in ('proved', 'observed'):
		if s in states:
			return s
	gates = u.kids('gate')
	if not gates:
		return 'code'
	got = [gate_level(g, u, ctx, tuple(seen) + (name,)) for g in gates]
	return lowest(['code' if x in ('judge', 'none') else x for x in got])


def by_target(b, u):
	'''What a "by" name reaches: "self", "external", "unit" or None.'''
	if b == u.word(0):
		return 'self'
	if b in [x.word(0) for x in u.kids('external')]:
		return 'external'
	if b in [x.word(0) for x in u.kids('uses')] or b in [v.word(0) for v in units(getattr(u, 'root', Node('file', [], 0, -1)))]:
		return 'unit'
	return None


def gate_level(g, u, ctx, seen=()):
	'''proved, observed, code, judge or none (spec, Section 2: the level of a gate).'''
	if g.word(1) == 'judge':
		return 'judge'
	got = []
	for x in g.kids('by'):
		b, kind = x.word(0), by_target(x.word(0), u)
		if kind == 'self':
			states = [cast_state(u, c) for c in u.kids('cast')]
			got.append('proved' if 'proved' in states else 'observed' if 'observed' in states else 'code')
		elif kind == 'external':
			got.append('code')
		elif kind == 'unit':
			got.append(unit_level(b, ctx, seen))
		else:
			got.append('none')
	return lowest(got)


def coverage(u, ctx=None):
	ctx = ctx_of(u, ctx)
	d = {'gates': 0, 'proved': 0, 'observed': 0, 'code': 0, 'judge': 0, 'none': 0}
	for g in u.kids('gate'):
		d['gates'] += 1
		d[gate_level(g, u, ctx, (u.word(0),))] += 1
	return d


def unit_status(unit, ctx=None):
	'''A short list of status strings for one unit.'''
	out = []
	for c in unit.kids('cast'):
		info, s = cast_info(c), cast_state(unit, c)
		out.append({'unproved': 'unproved {} (no hashes yet)', 'remelted': 'remelted {} (the matrix changed)',
			'stale': 'stale {} (the code changed: prove it again)'}.get(s, s + ' {}' + (' ' + info['date'] if info['date'] else '')).format(info['lang']))
	cv = coverage(unit, ctx)
	if cv['gates']:
		parts = ['{} {}'.format(cv[k], k) for k in ('proved', 'observed', 'code', 'judge', 'none') if cv[k] or k in ('proved', 'judge')]
		out.append('flow: {} gates, coverage {:.0%} ({})'.format(cv['gates'], float(cv['proved']) / cv['gates'], ', '.join(parts)))
	elif unit.kids('step'):
		out.append('flow: {} steps, no gates'.format(len(unit.kids('step'))))
	if not unit.kids('cast') and any(c.head in MATRIX for c in unit.children) and not (cv['gates'] or unit.kids('step')):
		out.append('hole')
	return out or ['empty']


# - Rules, placeholders, presets --------------------
def walk_strings(n, skip=('check', 'example', 'cast')):
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
	return out


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
		opts = [ser(o) for o in r.kids('options')[0].args]
		if ser(a) not in opts and value(a) not in [value(o) for o in r.kids('options')[0].args]:
			return 'use one of: ' + ', '.join(opts)
	if t == 'number':
		if a[0] != 'num':
			return 'use a number'
		v = value(a)
		for k, bad in (('min', lambda lim: v < lim), ('max', lambda lim: v > lim)):
			lim = r.kids(k)
			if lim and lim[0].args and lim[0].args[0][0] == 'num' and bad(value(lim[0].args[0])):
				return 'the value is {} {}'.format('below min' if k == 'min' else 'above max', ser(lim[0].args[0]))
	return None


def check(root, path=None):
	'''-> (errors, warnings): lists of (line, text). path: the file, to check the files of "uses" lines.'''
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
		if u.word(1) and u.word(1) not in SCOPES:
			err.append((u.line, 'scope "{}": use snippet, tool or agent'.format(u.word(1))))

		def walk(n):
			allowed = CHILDREN.get(n.head)
			for c in n.children:
				if allowed is not None and c.head not in allowed:
					warn.append((c.line, '"{}" is not a known word inside "{}"'.format(c.head, n.head)))
				walk(c)
		walk(u)
		for e in u.kids('example'):
			if '=>' not in [ser(a) for a in e.args]:
				err.append((e.line, 'an example needs "=>"'))
		for p in u.kids('probe'):
			if '=>' in [ser(a) for a in p.args]:
				err.append((p.line, 'a probe has no expected value: write the condition in a "check" line'))
		for n in u.kids('in') + u.kids('out'):
			t = in_parts(n)[1]
			bad = type_problem(t) if t else None
			if bad:
				warn.append((n.line, bad))
		exts = [x.word(0) for x in u.kids('external')]
		for x in u.kids('external'):
			if not x.word(0):
				err.append((x.line, 'an external needs a name'))
			elif exts.count(x.word(0)) > 1:
				err.append((x.line, 'external "{}" is defined twice'.format(x.word(0))))
		used_by = set()
		for f in [c for c in u.children if c.head in ('step', 'gate')]:
			for b in f.kids('by'):
				used_by.add(b.word(0))
				if b.word(0) and not by_target(b.word(0), u):
					warn.append((b.line, '"by {}" names no unit, used unit or external: add "external {}" if the code is outside Rig'.format(b.word(0), b.word(0))))
		for x in u.kids('external'):
			if x.word(0) and x.word(0) not in used_by:
				warn.append((x.line, 'external "{}" is not named by any "by"'.format(x.word(0))))
		if path:
			base = os.path.dirname(os.path.abspath(path))
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
						names = [v.word(0) for v in units(parse(fh.read()))]
				except (RigError, OSError) as e:
					warn.append((x.line, 'the file "{}" cannot be read: {}'.format(f, e)))
					continue
				if x.word(0) not in names:
					warn.append((x.line, 'the file "{}" has no unit "{}"'.format(f, x.word(0))))
		langs = [cast_info(c)['lang'] for c in u.kids('cast')]
		for lang in set(langs):
			if langs.count(lang) > 1:
				err.append((u.line, 'two casts in "{}"'.format(lang)))
		rules = set(r.word(0) for r in u.kids('rule'))
		byrule = dict((r.word(0), r) for r in u.kids('rule'))
		for r in u.kids('rule'):
			rid = r.word(0)
			if not rid or not RULE_ID.match(rid):
				err.append((r.line, 'rule id "{}": write it as group.name'.format(rid or '')))
			else:
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
		flow = [c for c in u.children if c.head in FLOW]
		ids = {}
		for f in flow:
			fid = f.word(0)
			if not fid:
				err.append((f.line, '"{}" needs an id'.format(f.head)))
			elif fid in ids:
				err.append((f.line, 'id "{}" is used twice'.format(fid)))
			ids[fid] = f
		read = set()
		edges = {}
		for f in flow:
			fid = f.word(0)
			edges[fid] = []
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
				if c.head in ('next', 'pass', 'fail'):
					if c.word(0) != '->' or not c.word(1):
						err.append((c.line, 'write "{} -> <id>"'.format(c.head)))
					elif c.word(1) not in ids:
						err.append((c.line, '"{}" leads to "{}", which does not exist'.format(fid, c.word(1))))
					else:
						edges[fid].append(c.word(1))
			if f.head == 'gate':
				kind = f.word(1)
				if kind not in GATE_KINDS:
					err.append((f.line, 'gate "{}": the kind must be hard, soft or judge'.format(fid)))
				elif kind in ('hard', 'soft') and not f.kids('by'):
					warn.append((f.line, 'gate "{}" is {} but no code decides it: add "by", or make it judge'.format(fid, kind)))
				elif kind == 'judge' and not f.kids('brief'):
					warn.append((f.line, 'judge gate "{}" has no brief'.format(fid)))
				if not f.kids('pass'):
					warn.append((f.line, 'gate "{}" has no "pass"'.format(fid)))
		if flow:
			seen = set()
			starts = [f for f in flow if f.head != 'end']
			todo = [starts[0].word(0)] if starts else []
			while todo:
				x = todo.pop()
				if x in seen:
					continue
				seen.add(x)
				todo.extend(edges.get(x, []))
			for f in flow:
				if f.word(0) not in seen:
					warn.append((f.line, '"{}" cannot be reached from the start'.format(f.word(0))))
			for r in u.kids('rule'):
				if r.word(0) not in read:
					warn.append((r.line, 'rule "{}" is not read by any step or gate'.format(r.word(0))))
	return err, warn


# - Values and proof ---------------------------------
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


# - Runners: prove and probe in the real runtime -----
# Each runner writes the cast, the casts of the units that it uses and their catalogues as
# modules into an empty folder, then calls the function in a new process (spec, Section 3a).
RUNNERS = {'py': '.py', 'js': '.js', 'ts': '.ts'}
COMMENT = {'py': '#', 'js': '//', 'ts': '//', 'sh': '#', 'rust': '//'}
MARK = '@@rig-result@@'

PY_HARNESS = '''import asyncio, inspect, json, math, re, sys, unicodedata
sys.dont_write_bytecode = True
sys.path.insert(0, %(folder)r)
from %(module)s import %(fn)s as fn
job = json.load(sys.stdin)
out = []
for case in job['cases']:
    try:
        r = fn(*case['args'])
        if inspect.isawaitable(r):
            r = asyncio.run(r)
        env = {'re': re, 'math': math, 'unicodedata': unicodedata, 'json': json, 'result': r}
        env.update(zip(job['inputs'], case['args']))
        bad = []
        for i, expr in case['checks']:
            try:
                if not eval(expr, env):
                    bad.append([i, None])
            except Exception as e:
                bad.append([i, '%%s: %%s' %% (type(e).__name__, e)])
        out.append({'result': json.loads(json.dumps(r)), 'bad': bad})
    except Exception as e:
        out.append({'error': '%%s: %%s' %% (type(e).__name__, e)})
print(%(mark)r + json.dumps(out))
'''

JS_HARNESS = '''import { readFileSync } from "node:fs";
const mod = await import("./%(module)s");
const fn = mod[%(fn)s];
const job = JSON.parse(readFileSync(0, "utf-8"));
const out = [];
for (const c of job.cases) {
  try {
    if (typeof fn !== "function") throw new Error("the cast defines no function " + %(fn)s);
    const result = await fn(...c.args);
    const bad = [];
    for (const [i, expr] of c.checks) {
      try { if (!new Function(...job.inputs, "result", "return (" + expr + ");")(...c.args, result)) bad.push([i, null]); }
      catch (e) { bad.push([i, String(e)]); }
    }
    out.push({ result: result === undefined ? null : JSON.parse(JSON.stringify(result)), bad });
  } catch (e) { out.push({ error: String(e) }); }
}
console.log(%(mark)s + JSON.stringify(out));
'''


def cast_of(u, lang):
	return next((c for c in u.kids('cast') if cast_info(c)['lang'] == lang), None)


def module_name(name, lang):
	return re.sub(r'\W', '_', name) if lang == 'py' else name


def write_modules(folder, unit, lang, ctx):
	'''The cast of unit, the casts of the units that it uses (in the same language), and the catalogue of each.'''
	todo, done = [unit], set()
	while todo:
		u = todo.pop()
		if u.word(0) in done:
			continue
		done.add(u.word(0))
		c = cast_of(u, lang)
		if c:
			write(os.path.join(folder, module_name(u.word(0), lang) + RUNNERS.get(lang, '.' + lang)), body_text(c.body) + '\n')
		write(os.path.join(folder, u.word(0) + '.json'), json.dumps(catalog(u, None, ctx), ensure_ascii=False, indent=1) + '\n')
		todo.extend(ctx.units[x.word(0)] for x in u.kids('uses') if x.word(0) in ctx.units)


def run_cases(unit, lang, cases, ctx):
	'''Run the cast of unit in lang once for each case: {"args", "checks": [[id, expr]]}.
	-> (list of {"result", "bad"} or {"error"}, None) or (None, an error text).'''
	if lang not in RUNNERS:
		return None, 'no runner for "{}": prove it in its own runtime, then use "stamp"'.format(lang)
	inputs = [x.word(0) for x in unit.kids('in')]
	folder = tempfile.mkdtemp(prefix='rig-')
	try:
		write_modules(folder, unit, lang, ctx)
		mod, fn = module_name(unit.word(0), lang), re.sub(r'\W', '_', unit.word(0))
		if lang == 'py':
			write(os.path.join(folder, '__rig_run.py'), PY_HARNESS % {'folder': folder, 'module': mod, 'fn': fn, 'mark': MARK})
			cmd = [sys.executable, '__rig_run.py']
		else:
			write(os.path.join(folder, 'package.json'), '{"type": "module"}\n')
			write(os.path.join(folder, '__rig_run.mjs'), JS_HARNESS % {'module': mod + RUNNERS[lang], 'fn': json.dumps(fn), 'mark': json.dumps(MARK)})
			if not shutil.which('node'):
				return None, 'Node.js is not installed: the {} runner needs it'.format(lang)
			cmd = ['node', '__rig_run.mjs']
		job = json.dumps({'inputs': inputs, 'cases': cases})
		try:
			p = subprocess.run(cmd, cwd=folder, input=job, capture_output=True, text=True, encoding='utf-8', timeout=300)
		except subprocess.TimeoutExpired:
			return None, 'the cast did not finish in 300 seconds'
		if MARK not in p.stdout:
			lines = [l for l in (p.stderr or p.stdout).strip().splitlines() if l.strip()]
			return None, 'the cast does not run: ' + ' | '.join(lines[-3:])
		return json.loads(p.stdout.rsplit(MARK, 1)[1].strip().splitlines()[0]), None
	finally:
		shutil.rmtree(folder, ignore_errors=True)


def case_checks(nodes, lang):
	'''The "check" lines under nodes -> (for the runtime of lang, for Python here, skipped).'''
	there, here, skip = [], [], []
	for n in nodes:
		for c in n.kids('check'):
			if len(c.args) < 2:
				continue
			item = [c.line, value(c.args[1])]
			if c.word(0) == lang:
				there.append(item)
			elif c.word(0) == 'py':
				here.append(item)
			else:
				skip.append(c)
	return there, here, skip


def judge_case(unit, args, got, here):
	'''The type of the result, and the "check py" lines that run here on the JSON result. -> list of problems.'''
	bad = []
	t = in_parts(unit.kids('out')[0])[1] if unit.kids('out') else None
	if not type_ok(got, t):
		bad.append('the result does not match the out type {}'.format(ser(t)))
	env = {'re': re, 'math': math, 'unicodedata': unicodedata, 'json': json, 'result': got}
	env.update(zip([x.word(0) for x in unit.kids('in')], args))
	for line, expr in here:
		try:
			if not eval(expr, env):
				bad.append('line {}'.format(line))
		except Exception as e:
			bad.append('line {} ({}: {})'.format(line, type(e).__name__, e))
	return bad


def args_problem(unit, args):
	for x, a in zip(unit.kids('in'), args):
		t = in_parts(x)[1]
		if not type_ok(a, t):
			return 'the input {} does not match its type {}'.format(x.word(0), ser(t))
	return None


def run_lang(unit, lang=None):
	'''The language to run: the one asked for, else the first cast that has a runner.'''
	langs = [cast_info(c)['lang'] for c in unit.kids('cast')]
	if lang:
		return lang if lang in langs else None
	return next((l for l in langs if l in RUNNERS), langs[0] if langs else None)


def prove(unit, path, lang=None, ctx=None):
	'''Run the examples of one unit against its cast in lang. -> (ok, lines of report); ok is None when nothing can run.'''
	lang = run_lang(unit, lang)
	if not lang:
		return None, ['no cast']
	ctx = ctx_of(unit, ctx)
	examples = unit.kids('example')
	if not examples:
		return None, ['no examples: a cast without examples cannot be proved; add examples, or use probes']
	there, here, skip = case_checks(unit.kids('ensure'), lang)
	report = ['skip: check in "{}" (line {})'.format(c.word(0), c.line) for c in skip]
	cases, wants = [], []
	for ex in examples:
		k = [ser(a) for a in ex.args].index('=>')
		cases.append({'args': [value(a) for a in ex.args[:k]], 'checks': there})
		wants.append(value(ex.args[k + 1]) if k + 1 < len(ex.args) else None)
	results, problem = run_cases(unit, lang, cases, ctx)
	if problem:
		return False if lang in RUNNERS else None, report + [problem]
	ok = True
	for ex, case, want, r in zip(examples, cases, wants, results):
		args = case['args']
		bad = [args_problem(unit, args)] if args_problem(unit, args) else []
		if 'error' in r:
			ok = False
			report.append('FAIL line {}: raised {}'.format(ex.line, r['error']))
			continue
		got = r['result']
		if got != want:
			ok = False
			report.append('FAIL line {}: {!r} gave {!r}, expected {!r}'.format(ex.line, args, got, want))
			continue
		bad += ['line {}{}'.format(i, ' ({})'.format(e) if e else '') for i, e in r['bad']] + judge_case(unit, args, got, here)
		if bad:
			ok = False
			report.append('FAIL line {}: {!r} broke {}'.format(ex.line, args, ', '.join(bad)))
		else:
			report.append('ok   line {}: {!r} => {!r}'.format(ex.line, args, got))
	return ok, report


def probe(unit, path, lang=None, ctx=None):
	'''Run the probes of one unit: live runs. -> (ok, lines of report); ok is None when nothing can run.'''
	lang = run_lang(unit, lang)
	if not lang or not unit.kids('probe'):
		return None, ['no cast' if not lang else 'no probes']
	ctx = ctx_of(unit, ctx)
	cases, heres, report = [], [], []
	for p in unit.kids('probe'):
		there, here, skip = case_checks(unit.kids('ensure') + [p], lang)
		report += ['skip: check in "{}" (line {})'.format(c.word(0), c.line) for c in skip]
		cases.append({'args': [value(a) for a in p.args], 'checks': there})
		heres.append(here)
	results, problem = run_cases(unit, lang, cases, ctx)
	if problem:
		return False if lang in RUNNERS else None, report + [problem]
	ok = True
	for p, case, here, r in zip(unit.kids('probe'), cases, heres, results):
		if 'error' in r:
			ok = False
			report.append('FAIL line {}: raised {}'.format(p.line, r['error']))
			continue
		bad = ['line {}{}'.format(i, ' ({})'.format(e) if e else '') for i, e in r['bad']] + judge_case(unit, case['args'], r['result'], here)
		if bad:
			ok = False
			report.append('FAIL line {}: {!r} broke {}'.format(p.line, case['args'], ', '.join(bad)))
		else:
			shown = json.dumps(r['result'], ensure_ascii=False)
			report.append('observed line {}: {!r} => {}'.format(p.line, case['args'], shown if len(shown) < 120 else shown[:117] + '...'))
	return ok, report


def stamp(path, text, unit, lang, kind='proved'):
	'''Write the current hashes, the kind (proved or observed) and today's date into the cast line of one unit.'''
	c = cast_of(unit, lang)
	if not c:
		raise SystemExit('unit "{}" has no "{}" cast'.format(unit.word(0), lang))
	lines = text.split('\n')
	old = lines[c.line - 1]
	cr = '\r' if old.endswith('\r') else ''
	lines[c.line - 1] = '{}cast {} {} {} {} {}{}'.format(' ' * c.indent, lang, matrix_hash(unit), body_hash(c), kind, datetime.date.today().isoformat(), cr)
	with open(path, 'w', encoding='utf-8', newline='') as f:
		f.write('\n'.join(lines))
	return lines[c.line - 1].strip()


def emit(path, lang, folder, names=None):
	'''Write the proved and observed casts in lang as modules, each with its catalogue. -> (written, refused).'''
	text, root = load(path)
	ctx = Ctx(root, path)
	os.makedirs(folder, exist_ok=True)
	written, refused = [], []
	for u in units(root):
		c = cast_of(u, lang)
		if not c or (names and u.word(0) not in names):
			continue
		s = cast_state(u, c)
		if s not in STAMPS:
			refused.append('{}: {} ({})'.format(u.word(0), s, 'prove it, or probe it if it has no examples'))
			continue
		head = COMMENT.get(lang)
		note = '{} Generated from {} (unit {}, {} {}). Do not edit: change the .rig file.\n\n'.format(
			head, os.path.basename(path), u.word(0), s, cast_info(c)['date'] or '') if head else ''
		target = os.path.join(folder, module_name(u.word(0), lang) + RUNNERS.get(lang, '.' + lang))
		write(target, note + body_text(c.body) + '\n')
		cat = os.path.join(folder, u.word(0) + '.json')
		write(cat, json.dumps(catalog(u, None, ctx), ensure_ascii=False, indent=1) + '\n')
		written += [target, cat]
	return written, refused


# - Compile: catalogue (JSON) ------------------------
def text_of(n):
	'''The arguments of a node as one text: strings without quotes, joined by one space.'''
	return ' '.join(value(a) if a[0] == 'str' else ser(a) for a in n.args)


def name_of(f):
	'''The display name of a step, gate or end: its string argument.'''
	a = f.args[2] if f.head == 'gate' and len(f.args) > 2 else (f.args[1] if f.head != 'gate' and len(f.args) > 1 else None)
	if a is None:
		return ''
	return value(a) if a[0] == 'str' else ser(a)


def notes_of(n):
	return [{'text': text_of(x), 'evidence': [text_of(e) for e in x.kids('evidence')]} for x in n.kids('note')]


def rule_info(r, token=None):
	'''One rule as a catalogue entry. token: a preset value that replaces the value.'''
	a = r.args[1] if len(r.args) > 1 else None
	d = {'id': r.word(0), 'group': r.word(0).split('.')[0], 'label': text_of(r.kids('label')[0]) if r.kids('label') else r.word(0),
		'type': rule_type(r), 'value': value(token if token is not None else a) if (token or a) else None,
		'default': value(a) if a else None}
	for k in ('min', 'max'):
		if r.kids(k) and r.kids(k)[0].args:
			d[k] = value(r.kids(k)[0].args[0])
	if r.kids('options'):
		d['options'] = [value(o) for o in r.kids('options')[0].args]
	if r.kids('unit'):
		d['unit'] = text_of(r.kids('unit')[0])
	ns = notes_of(r)
	if ns:
		d['note'] = ' '.join(x['text'] for x in ns)
		ev = [e for x in ns for e in x['evidence']]
		if ev:
			d['evidence'] = ', '.join(ev)
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


def links(f, head):
	out = []
	for c in f.kids(head):
		d = {'to': c.word(1)}
		if len(c.args) > 2:
			d['when'] = value(c.args[2]) if c.args[2][0] == 'str' else ser(c.args[2])
		out.append(d)
	return out


def flow_info(f):
	d = {'id': f.word(0), 'kind': f.word(1) if f.head == 'gate' else f.head}
	nm = name_of(f)
	if nm:
		d['name'] = nm
	for k in PROSE:
		xs = f.kids(k)
		if xs:
			d[k] = ' '.join(text_of(x) for x in xs)
	if f.kids('by'):
		d['by'] = [x.word(0) for x in f.kids('by')]
	rd = node_reads(f)
	if rd:
		d['reads'] = rd
	for k in ('next', 'pass', 'fail'):
		ls = links(f, k)
		if ls:
			d[k] = ls
	ns = notes_of(f)
	if ns:
		d['notes'] = ns
	return d


def port_info(n):
	'''An "in" or "out" node -> {"name", "type", "text"} ("name" for "in" only).'''
	name, t, text = in_parts(n)
	d = {'name': name} if n.head == 'in' else {}
	d.update({'type': ser(t) if t else None, 'text': text})
	return d


def catalog(u, preset=None, ctx=None):
	'''A unit as a catalogue: the JSON that a code runner reads.'''
	toks = preset_tokens(u, preset)
	flow = [c for c in u.children if c.head in FLOW]
	starts = [f for f in flow if f.head != 'end']
	uses = []
	for x in u.kids('uses'):
		d = {'unit': x.word(0)}
		if x.word(1):
			d['file'] = x.word(1)
		uses.append(d)
	return {
		'rig': 0, 'unit': u.word(0), 'scope': u.word(1, 'snippet'), 'preset': preset,
		'intent': ' '.join(text_of(x) for x in u.kids('intent')),
		'notes': notes_of(u), 'uses': uses,
		'external': [{'name': x.word(0), 'text': ' '.join(value(a) for a in x.args[1:] if a[0] == 'str')} for x in u.kids('external')],
		'in': [port_info(x) for x in u.kids('in')],
		'out': port_info(u.kids('out')[0]) if u.kids('out') else None,
		'start': starts[0].word(0) if starts else None,
		'coverage': coverage(u, ctx),
		'presets': presets_of(u),
		'rules': [rule_info(r, toks.get(r.word(0))) for r in u.kids('rule')],
		'flow': [flow_info(f) for f in flow],
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


def skill(u, rules_path=None, preset=None):
	'''A unit as a SKILL.md for an agent that follows instructions.
	rules_path: refer to that JSON file for the values, instead of writing them in.'''
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
		out.append('Note: ' + fill(n['text']) + (' (evidence: ' + ', '.join(n['evidence']) + ')' if n['evidence'] else ''))
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
			for k in ('min', 'max'):
				if r.kids(k) and r.kids(k)[0].args:
					lim.append(k + ' ' + ser(r.kids(k)[0].args[0]))
			if r.kids('options'):
				lim.append('one of: ' + ', '.join(ser(o) for o in r.kids('options')[0].args))
			mean = info['label'] + (' (' + info['unit'] + ')' if 'unit' in info else '') + ('; ' + ', '.join(lim) if lim else '')
			if 'note' in info:
				mean += '. Note: ' + info['note']
			if rules_path:
				out.append('| `{}` | {} |'.format(info['id'], cell(mean)))
			else:
				out.append('| `{}` | `{}` | {} |'.format(info['id'], cell(val(info['id'])), cell(mean)))
		out.append('')
	if c['flow']:
		out += ['## Flow', '', 'Start at `{}`. Go from node to node as written. Do not skip a gate.'.format(c['start']), '']

		def go(l):
			return 'go to `{}`'.format(l['to']) + (' ({})'.format(fill(l['when'])) if 'when' in l else '')
		for f in c['flow']:
			k = f['kind']
			label = {'step': 'step', 'end': 'end'}.get(k, k + ' gate')
			out += ['### `{}`{} ({})'.format(f['id'], ' ' + fill(f['name']) if f.get('name') else '', label), '']
			for key, title in (('when', 'When'), ('do', 'Do'), ('ensure', 'Check')):
				if key in f:
					out.append('- {}: {}'.format(title, fill(f[key])))
			if 'reads' in f:
				out.append('- Rules: ' + ', '.join('`{}`'.format(r) if rules_path or r not in byrule else '`{}` = {}'.format(r, val(r)) for r in f['reads']))
			by = ', '.join('`{}`'.format(b) for b in f.get('by', []))
			guess = '- No code decides this gate yet: decide it yourself and label the result as a guess.'
			if k == 'step' and by:
				out.append('- Code: run {}.'.format(by))
			elif k == 'hard':
				out.append('- Decided by code: run {} and obey its result. Do not decide this gate yourself.'.format(by) if by else guess)
			elif k == 'soft':
				out.append('- Decided by code: run {}. If it fails, report it and go on as written below.'.format(by) if by else guess)
			elif k == 'judge':
				out.append('- Judge: {}. Label the result as a guess.'.format(fill(f['brief'])) if 'brief' in f else '- Judge: decide it yourself. Label the result as a guess.')
			for n in f.get('notes', []):
				out.append('- Note: ' + fill(n['text']))
			for key, title in (('next', 'Next'), ('pass', 'Pass'), ('fail', 'Fail')):
				for l in f.get(key, []):
					out.append('- {}: {}.'.format(title, go(l)))
			if k == 'end':
				out.append('- Stop here.')
			out.append('')
		guessed = [f['id'] for f in c['flow'] if f['kind'] == 'judge' or (f['kind'] in ('hard', 'soft') and not f.get('by'))]
		if guessed:
			names = ', '.join(guessed)
			out += ['## Report', '',
				'You decide these gates yourself, not code: {}. Their results are guesses.'.format(', '.join('`{}`'.format(g) for g in guessed)),
				'End your answer with one line that starts with `Guessed:` and names each of these gates that you decided, for example:', '',
				'Guessed: ' + names, '',
				'Do not leave this line out. A person must see which results are guesses.', '']
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
	for x in c.get('external', []):
		out.append('  external ' + x['name'] + (' ' + quote(x['text']) if x.get('text') else ''))
	for x in c.get('in', []):
		out.append('  in ' + x['name'] + (' ' + x['type'] if x.get('type') else '') + (' ' + quote(x['text']) if x.get('text') else ''))
	o = c.get('out')
	if o is not None:
		out.append('  out' + (' ' + o['type'] if o.get('type') else '') + (' ' + quote(o['text']) if o.get('text') else ''))

	def notes(ns, ind):
		for n in ns:
			out.append(ind + 'note ' + quote(n['text']))
			for e in n.get('evidence', []):
				out.append(ind + '  evidence ' + e)
	notes(c.get('notes', []), '  ')
	types = {}
	for r in c.get('rules', []):
		t = r.get('type', 'text')
		types[r['id']] = t
		out.append('  rule {} {}'.format(r['id'], token(r.get('default', r.get('value')), t)))
		if r.get('label') and r['label'] != r['id']:
			out.append('    label ' + quote(r['label']))
		if 'unit' in r:
			out.append('    unit ' + quote(r['unit']))
		for k in ('min', 'max'):
			if k in r:
				out.append('    {} {}'.format(k, token(r[k])))
		if 'options' in r:
			out.append('    options ' + ' '.join(token(o, 'choice') for o in r['options']))
		if 'note' in r:
			out.append('    note ' + quote(r['note']))
			for e in (r['evidence'].split(', ') if r.get('evidence') else []):
				out.append('      evidence ' + e)
	for name, sets in c.get('presets', {}).items():
		out.append('  preset ' + name)
		for rid, v in sets.items():
			out.append('    set {} {}'.format(rid, token(v, types.get(rid, 'text'))))
	for f in c.get('flow', []):
		k = f['kind']
		head = 'gate {} {}'.format(f['id'], k) if k in GATE_KINDS else '{} {}'.format(k, f['id'])
		out.append('  ' + head + (' ' + quote(f['name']) if f.get('name') else ''))
		for key in PROSE:
			if key in f:
				out.append('    {} {}'.format(key, quote(f[key])))
		for b in f.get('by', []):
			out.append('    by ' + b)
		if f.get('reads'):
			out.append('    reads ' + ' '.join(f['reads']))
		notes(f.get('notes', []), '    ')
		for key in ('next', 'pass', 'fail'):
			for l in f.get(key, []):
				out.append('    {} -> {}{}'.format(key, l['to'], ' ' + quote(l['when']) if 'when' in l else ''))
	return '\n'.join(out) + '\n'


# - Command line -------------------------------------
def tree(n):
	d = {'head': n.head, 'args': [ser(a) for a in n.args], 'line': n.line}
	if n.children:
		d['children'] = [tree(c) for c in n.children]
	if n.body is not None:
		d['body'] = body_text(n.body)
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
		if any(c.head in FLOW for c in u.children):
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


def compile_to(kind, u, preset=None, rules_path=None, ctx=None):
	if kind == 'json':
		return json.dumps(catalog(u, preset, ctx), ensure_ascii=False, indent=1) + '\n'
	if kind == 'skill':
		return skill(u, rules_path, preset)
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
			import os
			ref = os.path.relpath(os.path.abspath(json_out), os.path.dirname(os.path.abspath(skill_out))).replace(os.sep, '/')
		write(skill_out, compile_to('skill', u, preset, ref))
		done.append(skill_out)
	return done


def serve(path, port, **outs):
	'''Serve the viewer for one file on 127.0.0.1. Save writes the file and compiles it again.'''
	import http.server
	import os
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
				self.send_header('Location', '/viewer?src=/file&save=1')
				self.end_headers()
			elif self.path.startswith('/viewer'):
				with open(page, encoding='utf-8') as f:
					self.reply(200, f.read(), 'text/html; charset=utf-8')
			elif self.path == '/file':
				with open(path, encoding='utf-8', newline='') as f:
					self.reply(200, f.read(), 'text/plain; charset=utf-8')
			else:
				self.reply(404, json.dumps({'error': 'not found'}))

		def do_POST(self):
			if self.path != '/file':
				return self.reply(404, json.dumps({'error': 'not found'}))
			text = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8')
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
			self.reply(200, json.dumps({'saved': os.path.basename(path), 'wrote': done}))

		def log_message(self, *a):
			pass

	srv = http.server.HTTPServer(('127.0.0.1', port), Handler)
	print('serving {} at http://127.0.0.1:{}/  (Ctrl+C stops)'.format(path, port))
	try:
		srv.serve_forever()
	except KeyboardInterrupt:
		pass


def main(argv):
	try:
		sys.stdout.reconfigure(encoding='utf-8', errors='replace')
	except Exception:
		pass
	if len(argv) < 2 or argv[0] not in ('check', 'hash', 'prove', 'probe', 'stamp', 'emit', 'json', 'compile', 'from-json', 'serve'):
		print(__doc__)
		return 2
	cmd, rest = argv[0], list(argv[1:])
	if cmd == 'compile':
		kind = rest.pop(0)
		preset, out, rules = option(rest, '--preset'), option(rest, '-o'), option(rest, '--rules')
		if not rest:
			raise SystemExit('compile {} FILE [UNIT]'.format(kind))
		text, root = load(rest[0])
		err, _ = check(root)
		if err:
			raise SystemExit('{}: line {}: {}'.format(rest[0], err[0][0], err[0][1]))
		result = compile_to(kind, pick(root, rest[1] if len(rest) > 1 else None), preset, rules, Ctx(root, rest[0]))
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
		outs = {'json_out': option(rest, '--json'), 'skill_out': option(rest, '--skill'), 'rules_ref': option(rest, '--rules-ref', True),
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
				print('  {:<28} {}'.format('{} ({})'.format(u.word(0), u.word(1, 'snippet')), '; '.join(unit_status(u, ctx))))
			err, warn = check(root, path)
			for line, t in sorted(err):
				print('  error   line {}: {}'.format(line, t))
			for line, t in sorted(warn):
				print('  warning line {}: {}'.format(line, t))
			bad += len(err)
		return 1 if bad else 0
	path = rest[0]
	text, root = load(path)
	if cmd == 'json':
		print(json.dumps(tree(root), ensure_ascii=False, indent=1))
	elif cmd == 'hash':
		for u in units(root):
			print('{}  matrix {}'.format(u.word(0), matrix_hash(u)))
			for c in u.kids('cast'):
				print('  cast {}  body {}'.format(cast_info(c)['lang'], body_hash(c)))
	elif cmd == 'stamp':
		if len(rest) < 3:
			raise SystemExit('stamp FILE UNIT LANG')
		if rest[2] in RUNNERS:
			raise SystemExit('"{}" has a runner: use "prove --stamp" (or "probe --stamp"), so that a real run decides'.format(rest[2]))
		print(stamp(path, text, find(root, rest[1]), rest[2]))
	elif cmd == 'emit':
		if len(rest) < 3:
			raise SystemExit('emit FILE LANG DIR [UNIT]')
		written, refused = emit(path, rest[1], rest[2], rest[3:] or None)
		for w in written:
			print('wrote ' + w)
		for r in refused:
			print('refused ' + r)
		return 1 if refused else 0
	elif cmd in ('prove', 'probe'):
		lang, do_stamp = option(rest, '--lang'), option(rest, '--stamp', True)
		want = rest[1:]
		todo = [find(root, want[0])] if want else units(root)
		all_ok = True
		for u in todo:
			langs = [lang] if lang else [l for l in (cast_info(c)['lang'] for c in u.kids('cast')) if l in RUNNERS] or [None]
			for lg in langs:
				ok, report = (prove if cmd == 'prove' else probe)(u, path, lg, Ctx(root, path))
				if ok is None and not want:
					continue
				word = {'prove': ('proved', 'not proved'), 'probe': ('observed', 'not observed')}[cmd]
				print('{} ({}): {}'.format(u.word(0), lg or '-', {True: word[0], False: 'FAILED', None: word[1]}[ok]))
				for r in report:
					print('  ' + r)
				if ok and do_stamp:
					c = cast_of(u, lg)
					if cmd == 'probe' and u.kids('example'):
						print('  not stamped: this unit has examples, so prove it')
					elif cmd == 'probe' and cast_state(u, c) == 'proved':
						print('  not stamped: the cast is proved already')
					else:
						print('  ' + stamp(path, text, u, lg, 'proved' if cmd == 'prove' else 'observed'))
						text, root = load(path)
						u = find(root, u.word(0))
				all_ok = all_ok and ok is not False
		return 0 if all_ok else 1
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
