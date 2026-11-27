"""Tests for rig.py: the parser, the checker, the lowering of the blocks and the compilers.
Run: python3 -m unittest discover -s tests"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig'))
import rig  # noqa: E402

EXAMPLES = sorted(glob.glob(os.path.join(ROOT, 'examples', '**', '*.rig'), recursive=True))
MISTAKES = os.path.join(ROOT, 'tests', 'fixtures', 'mistakes.rig')
SPEC = os.path.join(ROOT, 'skills', 'rig', 'spec.md')
TOOL = os.path.join(ROOT, 'skills', 'rig', 'rig.py')


def load(path):
	with open(path, encoding='utf-8') as f:
		return rig.parse(f.read())


def errors(text):
	return rig.check(rig.parse(text))[0]


def warnings(text):
	return rig.check(rig.parse(text))[1]


def catalogue(text):
	return rig.catalog(rig.units(rig.parse(text))[0])


def node(c, nid):
	return next(n for n in c['flow'] if n['id'] == nid)


def block(c, bid):
	return next(b for b in c['blocks'] if b['id'] == bid)


def unit(body, head='unit x'):
	'''A unit with code lines, so that "by" names something.'''
	return head + '\n  code code code.py\n' + body


class Examples(unittest.TestCase):
	def test_examples_have_no_errors(self):
		self.assertTrue(EXAMPLES)
		for path in EXAMPLES:
			self.assertEqual(rig.check(load(path), path)[0], [], path)

	def test_every_example_of_the_spec_is_accepted(self):
		with open(SPEC, encoding='utf-8') as f:
			blocks = re.findall(r'```rig\n(.*?)```', f.read(), re.S)
		self.assertGreaterEqual(len(blocks), 3)
		for text in blocks:
			if not text.startswith('unit '):
				text = 'unit example\n' + ''.join('  ' + l + '\n' for l in text.split('\n') if l.strip())
			self.assertEqual(errors(text), [], text)


class Removed(unittest.TestCase):
	'''Every removed word from version 0 and version 1 is refused, and the error names the replacement.'''
	CASES = {
		'next': ('  step a by code.a\n    next -> b\n  end b\n', 'the next line'),
		'pass': ('  gate a hard by code.a\n    pass -> b\n    fail -> b\n  end b\n', 'next line'),
		'when': ('  gate a hard by code.a\n    when "x"\n    fail -> b\n  end b\n', 'if <path>'),
		'brief': ('  gate a model\n    brief "x"\n    fail -> b\n  end b\n', 'check'),
		'ensure': ('  gate a hard by code.a\n    ensure "x"\n    fail -> b\n  end b\n', 'check'),
		'judge': ('  gate a judge\n    check "x"\n    fail -> b\n  end b\n', 'model'),
		'min': ('  rule a.b 3\n    min 1\n', 'range'),
		'max': ('  rule a.b 3\n    max 9\n', 'range'),
		'label': ('  rule a.b 3\n    label "x"\n', 'the string after the value'),
		'unit': ('  rule a.b 3\n    unit "words"\n', 'in the label'),
		'external': ('  external a.b "x"\n', 'code'),
		'cast': ('  cast py\n    def x(): pass\n', 'code <prefix> <path>'),
		'probe': ('  probe 1\n', 'test file'),
		'evidence': ('  note "x"\n    evidence README.md\n', 'text of the note'),
		'example': ('  example 1 => 2\n', 'version 2'),
		'uses': ('  uses helper other.rig\n', 'version 2'),
	}

	def test_each_removed_word_is_refused_with_its_replacement(self):
		for word, (body, hint) in self.CASES.items():
			err = errors(unit(body))
			self.assertTrue(err, word)
			self.assertTrue(any(hint in t for _, t in err), (word, err))

	def test_removed_scopes_and_prefixless_code(self):
		for scope in ('snippet', 'tool', 'agent'):
			err = errors('unit x {}\n  intent "x"\n'.format(scope))
			self.assertTrue(any('unit x' in t for _, t in err), (scope, err))
		err = errors('unit x\n  code tools.py\n  step a by code.a\n  end e\n')
		self.assertTrue(any('code <prefix> <path>' in t for _, t in err), err)
		r = subprocess.run([sys.executable, TOOL, 'compile', 'tool', PATTERN], capture_output=True, text=True)
		self.assertNotEqual(r.returncode, 0)
		self.assertIn('version 2', r.stderr + r.stdout)

	def test_the_commands_of_the_snippet_scale(self):
		for cmd in ('prove', 'probe', 'stamp', 'emit', 'hash'):
			r = subprocess.run([sys.executable, TOOL, cmd, 'x.rig'], capture_output=True, text=True)
			self.assertEqual(r.returncode, 2)
			self.assertIn('version 0', r.stdout)


FLOW = unit('''  in n int "a number"
  rule limits.max 10 "Largest number"
    range 1 100
  rule limits.rounds 2 "Retries"
    range 0 5
  step make "Make" by code.make
    do "make a list"
  for x in make.items
    tolerate 25%
    fail -> held "too many left"
    step draft "Draft" by model
      do "give a number"
      out {v: int}
    gate ok hard "Even"
      check "the number is even and at most {limits.max}"
      by code.even
      retry limits.rounds
      fail -> continue "not even"
  if make.big
    gate big human "Big?"
      timeout 2d
      fail -> no "timeout"
  else
    step small by code.small
  until make.done
    retry 3
    fail -> held
    step tick by code.tick
  section "Choose"
    gate pick human "Which?"
      options a | b c
      by code.pick
  gate sure model "Sure"
    check "is it right?"
    fail -> no
  end done "Done"
  end held "Held"
  end no "No"
  finally
    step sum by code.sum
''')


class Blocks(unittest.TestCase):
	def setUp(self):
		self.c = catalogue(FLOW)

	def test_the_flow_has_no_error(self):
		self.assertEqual(errors(FLOW), [])

	def test_the_order_of_the_lines(self):
		c = self.c
		self.assertEqual(c['start'], 'make')
		self.assertEqual(node(c, 'make')['next'], 'for:x')
		self.assertEqual(node(c, 'sure')['next'], 'done')
		self.assertNotIn('next', node(c, 'done'))
		self.assertEqual(c['body'], ['make', 'for:x', 'if:make.big', 'else:make.big', 'until:make.done', 'section:Choose', 'sure', 'done', 'held', 'no', 'finally'])

	def test_for(self):
		b = block(self.c, 'for:x')
		self.assertEqual((b['item'], b['path'], b['first'], b['next'], b['tolerate']), ('x', 'make.items', 'draft', 'if:make.big', 25))
		self.assertEqual(b['fail'], [{'to': 'held', 'when': 'too many left'}])
		self.assertEqual(node(self.c, 'ok')['next'], 'for:x')  # the end of the body goes back to the head of the loop
		self.assertEqual(node(self.c, 'draft')['block'], 'for:x')

	def test_fail_continue(self):
		self.assertEqual(node(self.c, 'ok')['fail'], [{'to': 'for:x', 'when': 'not even', 'continue': True}])
		err = errors(unit('  gate a hard by code.a\n    fail -> continue\n'))
		self.assertTrue(any('only for a gate inside a "for"' in t for _, t in err))

	def test_tolerate(self):
		err = errors(unit('  for x in a.b\n    tolerate many\n    step s by code.s\n'))
		self.assertTrue(any('tolerate <n>%' in t for _, t in err))

	def test_retry(self):
		ok = node(self.c, 'ok')
		self.assertEqual((ok['retry'], ok['back']), ('limits.rounds', 'draft'))
		self.assertIn('limits.rounds', ok['reads'])
		err = errors(unit('  gate a hard by code.a\n    retry 2\n    fail -> e\n  end e\n'))
		self.assertTrue(any('no step is before it' in t for _, t in err))
		err = errors(unit('  step s by code.s\n  gate a hard by code.a\n    retry two\n    fail -> e\n  end e\n'))
		self.assertTrue(any('write retry <n>' in t for _, t in err))
		err = errors(unit('  step s by code.s\n  gate a soft by code.a\n    retry 2\n'))
		self.assertTrue(any('hard or a model gate' in t for _, t in err))

	def test_retry_goes_back_past_gates(self):
		c = catalogue(unit('  step s by model\n    do "x"\n  gate a hard by code.a\n    fail -> e\n  gate b model\n    check "y"\n    retry 1\n    fail -> e\n  end e\n'))
		self.assertEqual(node(c, 'b')['back'], 's')

	def test_if_and_else(self):
		b = block(self.c, 'if:make.big')
		self.assertEqual((b['path'], b['first'], b['else'], b['next']), ('make.big', 'big', 'small', 'until:make.done'))
		self.assertEqual(node(self.c, 'small')['next'], 'until:make.done')
		self.assertEqual(block(self.c, 'else:make.big')['if'], 'if:make.big')
		err = errors(unit('  if a > 3\n    step s by code.s\n  end e\n'))
		self.assertTrue(any('not an expression' in t for _, t in err))
		err = errors(unit('  else\n    step s by code.s\n  end e\n'))
		self.assertTrue(any('must follow an "if"' in t for _, t in err))

	def test_if_on_one_node(self):
		c = catalogue(unit('  step s by code.s\n    if a.b\n  end e\n'))
		self.assertEqual(node(c, 's')['if'], 'a.b')

	def test_until(self):
		b = block(self.c, 'until:make.done')
		self.assertEqual((b['retry'], b['first'], b['next']), (3, 'tick', 'pick'))
		self.assertEqual(node(self.c, 'tick')['next'], 'until:make.done')
		err = errors(unit('  until a.b\n    step s by code.s\n  end e\n'))
		self.assertTrue(any('needs "retry <n>"' in t for _, t in err))

	def test_section(self):
		b = block(self.c, 'section:Choose')
		self.assertEqual((b['name'], b['body']), ('Choose', ['pick']))
		self.assertEqual(node(self.c, 'pick')['block'], 'section:Choose')  # a section has no effect on a run: no node leads to it

	def test_finally(self):
		self.assertEqual(self.c['finally'], 'sum')
		self.assertEqual(node(self.c, 'sum')['block'], 'finally')
		err = errors(unit('  finally\n    step s by code.s\n  step t by code.t\n  end e\n'))
		self.assertTrue(any('the last block' in t for _, t in err))

	def test_by_model_and_out(self):
		d = node(self.c, 'draft')
		self.assertEqual((d['lane'], d['out']), ('model', '{v: int}'))
		self.assertEqual(d['schema'], {'type': 'object', 'properties': {'v': {'type': 'integer'}}, 'required': ['v'], 'additionalProperties': False})
		self.assertNotIn('by', d)
		self.assertEqual(node(self.c, 'make')['lane'], 'code')
		w = warnings(unit('  step s\n    do "x"\n  end e\n'))
		self.assertTrue(any('say who does it' in t for _, t in w))
		self.assertTrue(any('add "out <type>"' in t for _, t in w))
		w2 = warnings(unit('  step s by model\n    do "x"\n  end e\n'))
		self.assertTrue(any('add "out <type>"' in t for _, t in w2))
		w3 = warnings(unit('  step s by model\n    do "x"\n    out text\n  end e\n'))
		self.assertFalse(any('add "out <type>"' in t for _, t in w3))
		err = errors(unit('  gate g hard by model\n    fail -> e\n  end e\n'))
		self.assertTrue(any('not "by model"' in t for _, t in err))

	def test_options(self):
		p = node(self.c, 'pick')
		self.assertEqual((p['options'], p['by'], p['lane']), (['a', 'b c'], ['code.pick'], 'person'))
		err = errors(unit('  gate g human "Q?"\n    options a | b\n  end e\n'))
		self.assertTrue(any('needs "by"' in t for _, t in err))
		err = errors(unit('  gate g hard by code.g\n    options a | b\n    fail -> e\n  end e\n'))
		self.assertTrue(any('for a human gate' in t for _, t in err))

	def test_timeout(self):
		b = node(self.c, 'big')
		self.assertEqual((b['timeout'], b['timeout_text']), (2 * 86400, '2d'))
		err = errors(unit('  step s by model\n    do "x"\n    timeout soon\n  end e\n'))
		self.assertTrue(any('timeout 5m' in t for _, t in err))
		err = errors(unit('  gate g human "Q?"\n    options a | b\n    by code.g\n    timeout 1h\n  end e\n'))
		self.assertTrue(any('after its timeout the gate fails' in t for _, t in err))

	def test_check(self):
		self.assertEqual(node(self.c, 'ok')['check'], 'the number is even and at most {limits.max}')
		self.assertNotIn('checks', self.c)
		w = warnings('unit x\n  check "every result is even"\n  code c x.py\n')
		self.assertTrue(any('not a known word inside "unit"' in t for _, t in w))

	def test_range_and_the_label(self):
		r = next(r for r in self.c['rules'] if r['id'] == 'limits.max')
		self.assertEqual((r['min'], r['max'], r['label']), (1, 100, 'Largest number'))
		err = errors('unit x\n  rule a.b 300 "x"\n    range 1 100\n')
		self.assertTrue(any('above the range' in t for _, t in err))
		err = errors('unit x\n  rule a.b 3 x\n')
		self.assertTrue(any('only the label' in t for _, t in err))

	def test_a_fail_goes_to_an_end(self):
		err = errors(unit('  step s by code.s\n  gate g hard by code.g\n    fail -> s\n  end e\n'))
		self.assertTrue(any('a fail goes to an end' in t for _, t in err))

	def test_a_child_on_the_line_of_its_node(self):
		c = catalogue(unit('  step s "S" by code.s\n  gate g hard "G" by code.g fail -> e "why"\n  end e\n'))
		self.assertEqual((node(c, 's')['by'], node(c, 's')['name']), (['code.s'], 'S'))
		self.assertEqual((node(c, 'g')['by'], node(c, 'g')['fail']), (['code.g'], [{'to': 'e', 'when': 'why'}]))

	def test_soft_has_no_fail_and_hard_needs_one(self):
		self.assertTrue(any('is soft' in t for _, t in errors(unit('  gate g soft by code.g\n    fail -> e\n  end e\n'))))
		self.assertTrue(any('has no fail line' in t for _, t in errors(unit('  gate g hard by code.g\n  end e\n'))))

	def test_reach_and_the_last_line(self):
		w = warnings(unit('  step s by code.s\n  end e\n  step t by code.t\n'))
		self.assertTrue(any('"t" cannot be reached' in t for _, t in w))
		w = warnings(unit('  step s by code.s\n'))
		self.assertTrue(any('run past its last line' in t for _, t in w))

	def test_reserved_ids(self):
		self.assertTrue(any('not an id' in t for _, t in errors(unit('  step error by code.s\n  end continue\n'))))

	def test_node_under_node(self):
		err = errors(unit('  step s by code.s\n    step t by code.t\n  end e\n'))
		self.assertTrue(any('a node has no body' in t for _, t in err))


class RulesAndPresets(unittest.TestCase):
	def test_mistakes_are_refused(self):
		lines = sorted(set(line for line, _ in rig.check(load(MISTAKES))[0]))
		self.assertEqual(lines, [4, 5, 6, 10, 13, 14, 15, 16, 22])

	def test_a_number_in_prose_warns(self):
		_, warn = rig.check(load(MISTAKES))
		self.assertTrue(any(line == 18 and 'number' in t for line, t in warn))

	def test_plain_braces_are_text(self):
		self.assertEqual(errors('unit x\n  intent "keep {name} as written"\n'), [])

	def test_placeholder_counts_as_read(self):
		w = warnings(unit('  rule a.b 1\n  gate g hard by code.g\n    check "at most {a.b}"\n    fail -> e\n  end e\n'))
		self.assertFalse(any('not read' in t for _, t in w))


PATTERN = os.path.join(ROOT, 'examples', 'font-names', 'font-names.rig')  # the pattern example


class Compile(unittest.TestCase):
	def unit(self):
		return rig.units(load(PATTERN))[0]

	def test_skill_writes_values_in(self):
		text = rig.skill(self.unit())
		self.assertIn('every new name fits sp_server', text)
		self.assertNotIn('{target.standard}', text)
		self.assertIn('Next: `files-ok`', text)  # the agent walks the flow itself: each node says the next one

	def test_skill_can_refer_to_the_catalogue(self):
		text = rig.skill(self.unit(), 'font-names.json')
		self.assertIn('`font-names.json`', text)
		self.assertIn('every new name fits `{target.standard}`', text)

	def test_skill_with_a_runner(self):
		text = rig.skill(self.unit(), None, None, 'python3 tool.py')
		self.assertIn('python3 tool.py run', text)
		self.assertIn('python3 tool.py flow', text)
		self.assertIn('## Flow (summary)', text)
		self.assertIn('| `abbreviate` | reason (careful) |', text)
		self.assertIn('| `readable` | model gate |', text)
		self.assertIn('| `approve` | human gate |', text)
		self.assertIn('Ends: `done`', text)
		self.assertNotIn('Next: ', text)
		self.assertNotIn('### `read`', text)
		self.assertNotIn('### `files-ok`', text)

	def test_skill_with_a_runner_lists_a_model_step(self):
		text = rig.skill(rig.units(rig.parse(unit('  step draft "Draft" by model\n    do "write a draft"\n    out text\n  end done\n')))[0], None, None, 'python3 tool.py')
		self.assertIn('| `draft` | model step |', text)

	def test_skill_shows_the_blocks(self):
		text = rig.skill(rig.units(rig.parse(FLOW))[0])
		for part in ('**For each `x` in `make.items`**', '**Until `make.done` is true**', '**If `make.big`**', '**Else', '**Finally', '### Choose',
				'leave this item', 'at most 3 more times', 'The first is the default'):
			self.assertIn(part, text)

	def test_preset_changes_value_not_default(self):
		c = rig.catalog(self.unit(), 'mac')
		r = [x for x in c['rules'] if x['id'] == 'target.standard'][0]
		self.assertEqual((r['value'], r['default']), ('hfs', 'sp_server'))
		self.assertIn('every new name fits hfs', rig.skill(self.unit(), None, 'mac'))

	def test_command_line(self):
		out = subprocess.check_output([sys.executable, TOOL, 'compile', 'json', PATTERN, '--preset', 'mac']).decode('utf-8')
		c = json.loads(out)
		self.assertEqual((c['unit'], c['preset'], c['rig']), ('font-names', 'mac', 2))
		out = subprocess.check_output([sys.executable, TOOL, 'compile', 'skill', PATTERN]).decode('utf-8')
		self.assertTrue(out.replace('\r\n', '\n').startswith('---\nname: font-names\n'))
		r = subprocess.run([sys.executable, TOOL, 'check', MISTAKES], capture_output=True, text=True)
		self.assertEqual(r.returncode, 1)


def temp_rig(test, text):
	folder = tempfile.mkdtemp(prefix='rig-test-')
	test.addCleanup(shutil.rmtree, folder, True)
	path = os.path.join(folder, 'x.rig')
	with open(path, 'w', encoding='utf-8') as f:
		f.write(text)
	return path


class Levels(unittest.TestCase):
	def test_by_must_name_something(self):
		root = rig.parse('unit x\n  gate g hard by nowhere.fn\n    fail -> e\n  end e\n')
		_, warn = rig.check(root)
		self.assertTrue(any('names no "code" line' in t for _, t in warn))
		self.assertEqual(rig.coverage(rig.units(root)[0])['none'], 1)

	def test_levels_of_the_example(self):
		cv = rig.coverage(rig.units(load(PATTERN))[0], rig.Ctx(load(PATTERN), PATTERN))
		self.assertEqual((cv['gates'], cv['tested'], cv['model'], cv['human']), (9, 7, 1, 1))

	def test_ast_bound_level_ignores_comments_and_strings(self):
		folder = tempfile.mkdtemp(prefix='rig-test-')
		self.addCleanup(shutil.rmtree, folder, True)
		with open(os.path.join(folder, 'gates.py'), 'w', encoding='utf-8') as f:
			f.write('# def fake_fn(state, R): return True\ndef real_fn(state, R):\n\treturn True\n')
		with open(os.path.join(folder, 'test_gates.py'), 'w', encoding='utf-8') as f:
			f.write('"""real_fn is only in a docstring"""\n# and real_fn in a comment\nx = "real_fn"\n')
		path = os.path.join(folder, 'x.rig')
		with open(path, 'w', encoding='utf-8') as f:
			f.write('unit x\n  code g gates.py\n    test test_gates.py\n  gate a hard by g.real_fn\n    fail -> e\n  gate b hard by g.fake_fn\n    fail -> e\n  end e\n')
		root = rig.load(path)[1]
		ctx = rig.Ctx(root, path)
		u = rig.units(root)[0]
		self.assertEqual(rig.bound_level('g.fake_fn', u, ctx), 'none')
		self.assertEqual(rig.bound_level('g.real_fn', u, ctx), 'code')
		self.assertTrue(ctx._texts and ctx._asts)
		with open(os.path.join(folder, 'test_gates.py'), 'w', encoding='utf-8') as f:
			f.write('import gates\ndef test_it():\n\tassert gates.real_fn({}, None)\n')
		ctx2 = rig.Ctx(root, path)
		self.assertEqual(rig.bound_level('g.real_fn', u, ctx2), 'tested')

	def test_inferred_rule_reads_from_python_code(self):
		folder = tempfile.mkdtemp(prefix='rig-test-')
		self.addCleanup(shutil.rmtree, folder, True)
		with open(os.path.join(folder, 'gates.py'), 'w', encoding='utf-8') as f:
			f.write('def helper(R):\n\treturn R.get("limits.extra")\ndef ok(state, R):\n\treturn state["x"] <= R("limits.max") and helper(R)\n')
		path = os.path.join(folder, 'x.rig')
		with open(path, 'w', encoding='utf-8') as f:
			f.write('unit x\n  code g gates.py\n  rule limits.max 10 "Max"\n  rule limits.extra on "Extra"\n  gate a hard by g.ok\n    fail -> e\n  end e\n')
		root = rig.load(path)[1]
		ctx = rig.Ctx(root, path)
		err, warn = rig.check(root, path, ctx)
		self.assertEqual(err, [])
		self.assertFalse(any('not read' in t for _, t in warn), warn)
		c = rig.catalog(rig.units(root)[0], None, ctx)
		self.assertEqual(node(c, 'a')['reads'], ['limits.max', 'limits.extra'])

	def test_hardcoded_number_in_gate_warns(self):
		folder = tempfile.mkdtemp(prefix='rig-test-')
		self.addCleanup(shutil.rmtree, folder, True)
		with open(os.path.join(folder, 'gates.py'), 'w', encoding='utf-8') as f:
			f.write('def bad(state, R):\n\treturn state["x"] > 42\n'
				'def clean(state, R, default_n=10):\n\tx = state["items"][2]\n\ty = state["word"][:-3]\n\tfor i in range(5):\n\t\tpass\n\treturn len(y) > 0 and round(x, 2) >= -1 and x <= 1\n')
		path = os.path.join(folder, 'x.rig')
		with open(path, 'w', encoding='utf-8') as f:
			f.write('unit x\n  code g gates.py\n  gate a hard by g.bad\n    fail -> e\n  gate b hard by g.clean\n    fail -> e\n  end e\n')
		root = rig.load(path)[1]
		err, warn = rig.check(root, path)
		self.assertEqual(err, [])
		hard_warns = [(ln, t) for ln, t in warn if 'hardcoded number' in t]
		self.assertEqual(len(hard_warns), 1, hard_warns)
		self.assertEqual(hard_warns[0][0], 3)
		self.assertIn('42', hard_warns[0][1])


class RigV2Language(unittest.TestCase):
	def test_structured_intent_and_never_gate_validation(self):
		ok_src = unit('''  intent "ship safe output"
    audience "users"
    style "concise"
    never "skip hard check" -> g
  step s by code.s
  gate g hard by code.g
    fail -> bad
  end done
  end bad
''')
		self.assertEqual(errors(ok_src), [])
		c = catalogue(ok_src)
		self.assertEqual(c['intent_spec']['audience'], 'users')
		self.assertEqual(c['intent_spec']['never'], [{'text': 'skip hard check', 'gate': 'g'}])
		bad_soft = unit('''  intent "ship"
    never "bad" -> s_gate
  gate s_gate soft by code.g
  end done
''')
		self.assertTrue(any('not soft' in t for _, t in errors(bad_soft)))

	def test_reason_block_validation_and_retry(self):
		src = unit('''  rule r.budget 2 "Tool budget"
  reason plan "Plan"
    intent "think carefully"
      style "json"
    do "propose options"
    mode creative
    tools code.inspect
    budget r.budget
    candidates 2
    out str
  gate ok hard by code.ok
    retry 1
    fail -> bad
  end done
  end bad
''')
		self.assertEqual(errors(src), [])
		c = catalogue(src)
		p = node(c, 'plan')
		self.assertEqual((p['kind'], p['lane'], p['mode'], p['tools'], p['budget'], p['candidates']),
			('reason', 'model', 'creative', ['code.inspect'], 'r.budget', 2))
		self.assertEqual(node(c, 'ok')['back'], 'plan')
		self.assertTrue(any('takes no "by"' in t for _, t in errors(unit('  reason p\n    by code.a\n    do "x"\n    out str\n  end e\n'))))
		self.assertTrue(any('careful or creative' in t for _, t in errors(unit('  reason p\n    mode wild\n    do "x"\n    out str\n  end e\n'))))

	def test_rollback_queue_ui_and_brief(self):
		src = unit('''  rule batch.size 5 "Chunk"
    range 1 20
    ui
  rule flag.on off "Flag"
    ui toggle
  queue by code.pending
    reads batch.size
  step load by code.load
    reads flag.on
    brief count summary
  end done
  rollback
    step undo by code.undo
  finally
    step done_log by code.log
''')
		self.assertEqual(errors(src), [])
		self.assertEqual(warnings(src), [])
		c = catalogue(src)
		self.assertEqual(c['queue'], {'by': ['code.pending'], 'reads': ['batch.size']})
		self.assertEqual(c['rollback'], 'undo')
		self.assertEqual(c['finally'], 'done_log')
		self.assertEqual(node(c, 'load')['brief'], ['count', 'summary'])
		self.assertEqual(c['rules'][0]['ui'], 'slider')
		self.assertEqual(c['rules'][1]['ui'], 'toggle')


	def test_dict_tuple_and_list_rules_and_ranges(self):
		src = unit('''  rule scale.bounds (0.5, 2.0) "Scale (min, max)"
    range 0.1 5.0
  rule tiers.depth {small: 8, medium: 16, large: 32} "Depth per tier"
    range 0 100
    ui
  rule tags.skip ["utm_", "fbclid"] "Ignored tags"
  preset compact
    set scale.bounds (0.6, 1.5)
    set tiers.depth {small: 6, medium: 12, large: 24}
  step check_it by code.check_it
    reads scale.bounds tags.skip
  gate ok hard by code.ok
    check "large tier at most {tiers.depth.large}"
    fail -> bad
  end done
  end bad
''')
		self.assertEqual(errors(src), [])
		self.assertEqual(warnings(src), [])
		c = catalogue(src)
		by_id = dict((r['id'], r) for r in c['rules'])
		self.assertEqual((by_id['scale.bounds']['type'], by_id['scale.bounds']['length'], by_id['scale.bounds']['value']), ('tuple', 2, [0.5, 2.0]))
		self.assertEqual((by_id['tiers.depth']['type'], by_id['tiers.depth']['value']), ('dict', {'small': 8, 'medium': 16, 'large': 32}))
		self.assertEqual((by_id['tags.skip']['type'], by_id['tags.skip']['value']), ('list', ['utm_', 'fbclid']))
		self.assertIn('tiers.depth', node(c, 'ok')['reads'])
		sk = rig.skill(rig.units(rig.parse(src))[0])
		self.assertIn('large tier at most 32', sk)
		sk_p = rig.skill(rig.units(rig.parse(src))[0], None, 'compact')
		self.assertIn('large tier at most 24', sk_p)

		# Tuple arity, range violations, unknown dict key in placeholder, and legacy (a b) list refused
		self.assertTrue(any('expected 2 items' in t for _, t in errors(unit(
			'  rule a.b (1, 2)\n  preset p\n    set a.b (1, 2, 3)\n  step s by code.s\n    reads a.b\n  end e\n'))))
		self.assertTrue(any('key "large": the value is above the range' in t for _, t in errors(unit(
			'  rule a.b {small: 5, large: 250}\n    range 0 100\n  step s by code.s\n    reads a.b\n  end e\n'))))
		self.assertTrue(any('item 1: the value is above the range' in t for _, t in errors(unit(
			'  rule a.b (0.5, 9.0)\n    range 0.1 5.0\n  step s by code.s\n    reads a.b\n  end e\n'))))
		self.assertTrue(any('not in dict rule' in t for _, t in errors(unit(
			'  rule a.b {small: 5}\n  gate g hard by code.g\n    check "at most {a.b.missing}"\n    fail -> e\n  end e\n'))))
		self.assertTrue(any('use [a, b] for a list' in t for _, t in errors(unit(
			'  rule a.b (utm_ fbclid)\n  step s by code.s\n    reads a.b\n  end e\n'))))

	def test_until_retry_rule_is_read_and_validated(self):
		ok_src = unit('''  rule repair.outer_limit 1 "Max outer rebuilds"
    range 0 5
    note "Default single retry."
  until evaluate.settled
    retry repair.outer_limit
    step draft "Build draft" by code.draft
  end done
''')
		self.assertEqual(errors(ok_src), [])
		self.assertEqual(warnings(ok_src), [])
		c = catalogue(ok_src)
		self.assertIn('repair.outer_limit', block(c, 'until:evaluate.settled')['reads'])
		bad_missing = unit('''  until evaluate.settled
    retry missing.rule
    step draft by code.draft
  end done
''')
		self.assertTrue(any('write retry <n>' in t for _, t in errors(bad_missing)))
		bad_type = unit('''  rule repair.flag on "Flag"
  until evaluate.settled
    retry repair.flag
    step draft by code.draft
      reads repair.flag
  end done
''')
		self.assertTrue(any('the rule must be a number' in t for _, t in errors(bad_type)))

	def test_choice_rule_preserves_reserved_words_in_options_and_presets(self):
		src = unit('''  rule mode.balance balanced "Balance mode"
    options strict | balanced | off
  rule mode.space off "Space-separated choice"
    options strict balanced off
  rule mode.words none "Boolean-like choice words"
    options true | false | on | off | none
  preset minimal
    set mode.balance off
    set mode.space strict
    set mode.words false
  step run_it by code.run_it
    reads mode.balance mode.space mode.words
  end done
''')
		self.assertEqual(errors(src), [])
		self.assertEqual(warnings(src), [])
		c = catalogue(src)
		by_id = dict((r['id'], r) for r in c['rules'])
		self.assertEqual(by_id['mode.balance']['options'], ['strict', 'balanced', 'off'])
		self.assertEqual(by_id['mode.space']['options'], ['strict', 'balanced', 'off'])
		self.assertEqual(by_id['mode.space']['default'], 'off')
		self.assertIsInstance(by_id['mode.space']['value'], str)
		self.assertEqual(by_id['mode.words']['options'], ['true', 'false', 'on', 'off', 'none'])
		self.assertEqual(by_id['mode.words']['default'], 'none')
		self.assertEqual(c['presets']['minimal'], {'mode.balance': 'off', 'mode.space': 'strict', 'mode.words': 'false'})
		c_min = rig.catalog(rig.units(rig.parse(src))[0], 'minimal')
		by_min = dict((r['id'], r) for r in c_min['rules'])
		self.assertEqual((by_min['mode.balance']['value'], by_min['mode.words']['value']), ('off', 'false'))

	def test_compact_rules_group_inline_ranges_and_reads_wildcard(self):
		src = unit('''  rules quality
    min_words   200                 50..5000  "Minimum length (words)"
      note "Short notes fail review."
    max_typos   0                   0.._      "Maximum typos"
      ui number
      note "Zero tolerance by default."
    upper_cap   10                  _..100    "Upper cap"
    weights     {title: 2, body: 1} 0..10     "Section weights"
      note "Relative scoring weights."
    strategy    balanced                      "Check mode"
      options strict | balanced | off
      ui select
  rule limits.extra 5 "Extra count"
    range 0 _
  rule limits.ceiling 20 "Ceiling"
    range _ 50
  step evaluate "Score document" by code.evaluate
    reads quality.* limits.*
  end done "Done"
''')
		self.assertEqual(errors(src), [])
		self.assertEqual(warnings(src), [])
		c = catalogue(src)
		by_id = dict((r['id'], r) for r in c['rules'])
		self.assertEqual((by_id['quality.min_words']['min'], by_id['quality.min_words']['max'], by_id['quality.min_words']['label']), (50, 5000, 'Minimum length (words)'))
		self.assertEqual(by_id['quality.max_typos']['min'], 0)
		self.assertNotIn('max', by_id['quality.max_typos'])
		self.assertEqual(by_id['quality.upper_cap']['max'], 100)
		self.assertNotIn('min', by_id['quality.upper_cap'])
		self.assertEqual((by_id['quality.weights']['min'], by_id['quality.weights']['max']), (0, 10))
		self.assertEqual(by_id['quality.strategy']['options'], ['strict', 'balanced', 'off'])
		self.assertEqual(by_id['limits.extra']['min'], 0)
		self.assertNotIn('max', by_id['limits.extra'])
		self.assertEqual(by_id['limits.ceiling']['max'], 50)
		self.assertNotIn('min', by_id['limits.ceiling'])
		self.assertEqual(node(c, 'evaluate')['reads'], [
			'quality.min_words', 'quality.max_typos', 'quality.upper_cap', 'quality.weights', 'quality.strategy',
			'limits.extra', 'limits.ceiling',
		])
		# Bundle rules_src spans point directly at each value token on compact lines too
		b = rig.bundle(src, None)
		u0 = b['units'][0]
		lines = src.split('\n')
		for rid, expected_tok in (('quality.min_words', '200'), ('quality.max_typos', '0'), ('quality.strategy', 'balanced')):
			sp = u0['rules_src'][rid]
			self.assertEqual(lines[sp['line'] - 1][sp['a']:sp['b']], expected_tok)
		# Errors: range _ _, _.._, out of open bounds, and wildcard matching no group
		self.assertTrue(any('at least one number' in t for _, t in errors(unit('  rule a.b 5 _.._ "Bad"\n  step s by code.s\n    reads a.b\n  end e\n'))))
		self.assertTrue(any('at least one number' in t for _, t in errors(unit('  rule a.b 5 "Bad"\n    range _ _\n  step s by code.s\n    reads a.b\n  end e\n'))))
		self.assertTrue(any('below the range' in t for _, t in errors(unit('  rule a.b -1 0.._ "Bad"\n  step s by code.s\n    reads a.b\n  end e\n'))))
		self.assertTrue(any('above the range' in t for _, t in errors(unit('  rule a.b 150 _..100 "Bad"\n  step s by code.s\n    reads a.b\n  end e\n'))))
		self.assertTrue(any('no rules in group "ghost"' in t for _, t in errors(unit('  step s by code.s\n    reads ghost.*\n  end e\n'))))

	def test_external_rules_json_sidecar_and_validation(self):
		folder = tempfile.mkdtemp(prefix='rig-sidecar-')
		self.addCleanup(shutil.rmtree, folder, True)
		sidecar = {
			'presets': {
				'strict': {'limits.max_errors': 0, 'mode.balance': 'strict'},
			},
			'rules': [
				{'id': 'limits.max_errors', 'value': 3, 'min': 0, 'max': 100, 'ui': 'number', 'label': 'Max errors (count)', 'note': 'Baseline audit.'},
				{'id': 'mode.balance', 'value': 'balanced', 'options': ['strict', 'balanced', 'off'], 'ui': 'select', 'label': 'Balance strategy'},
				{'id': 'scale.bounds', 'type': 'range', 'value': [0.5, 2.0], 'min': 0.1, 'max': 5.0, 'label': 'Scale bounds'},
				{'id': 'tiers.map', 'type': 'per_master', 'value': {'light': 10, 'heavy': 40}, 'min': 0, 'label': 'Tier map'},
			],
		}
		with open(os.path.join(folder, 'rules.json'), 'w', encoding='utf-8') as f:
			json.dump(sidecar, f)
		with open(os.path.join(folder, 'extra.json'), 'w', encoding='utf-8') as f:
			json.dump([{'id': 'extra.flag', 'value': True, 'label': 'Extra flag'}], f)
		with open(os.path.join(folder, 'code.py'), 'w', encoding='utf-8') as f:
			f.write('def run_it(state, R):\n\treturn R("limits.max_errors")\n')
		rig_path = os.path.join(folder, 'checker.rig')
		rig_src = '''unit document-checker
  intent "check documents up to {limits.max_errors} errors (heavy: {tiers.map.heavy})"
  code code code.py
  rules "rules.json"
  rules "extra.json"
  rule permissions.write off "Allow writes"
  preset off_mode
    set mode.balance off
  step run_it by code.run_it
    reads mode.* scale.* tiers.* extra.* permissions.*
  end done "Done"
'''
		with open(rig_path, 'w', encoding='utf-8') as f:
			f.write(rig_src)
		_, root = rig.load(rig_path)
		err, warn = rig.check(root, rig_path)
		self.assertEqual(err, [])
		self.assertEqual(warn, [])
		u = rig.units(root)[0]
		c = rig.catalog(u, 'strict')
		by_id = dict((r['id'], r) for r in c['rules'])
		self.assertEqual((by_id['limits.max_errors']['value'], by_id['limits.max_errors']['default']), (0, 3))
		self.assertEqual((by_id['scale.bounds']['type'], by_id['scale.bounds']['length']), ('tuple', 2))
		self.assertEqual(by_id['tiers.map']['type'], 'dict')
		self.assertEqual(by_id['extra.flag']['type'], 'switch')
		self.assertEqual(c['presets']['off_mode'], {'mode.balance': 'off'})
		# Duplicate rule across rules.json and .rig is refused
		dup_src = rig_src.replace('  rule permissions.write off "Allow writes"\n',
			'  rule permissions.write off "Allow writes"\n  rule limits.max_errors 5 "Dup"\n')
		with open(rig_path, 'w', encoding='utf-8') as f:
			f.write(dup_src)
		_, dup_root = rig.load(rig_path)
		dup_err, _ = rig.check(dup_root, rig_path)
		self.assertTrue(any('limits.max_errors" is defined twice' in t for _, t in dup_err), dup_err)

	def test_skill_omits_rule_notes_and_caps_large_tables_with_driver(self):
		rules_lines = []
		for i in range(28):
			rules_lines.append('  rule cal.k{} {} 0..100 "Metric {}"\n    note "Historical calibration survey note {}."'.format(i, i, i, i))
		rules_lines.append('  rule tune.knob 5 0..10 "Interactive knob"\n    ui slider\n    note "Long provenance note that should not bloat SKILL.md."')
		rules_lines.append('  rule permissions.write off "Allow writes"\n    note "Dry run by default."')
		src = unit('\n'.join(rules_lines) + '\n  step calc by code.calc\n    reads cal.* tune.* permissions.*\n  end done "Done"\n')
		u = rig.units(rig.parse(src))[0]
		# Without driver: lists all 30 rules, zero ". Note:" bloat
		sk_full = rig.skill(u)
		self.assertNotIn('. Note:', sk_full)
		self.assertNotIn('Historical calibration survey', sk_full)
		self.assertIn('`cal.k0`', sk_full)
		self.assertIn('`cal.k27`', sk_full)
		# With driver and > 25 rules: lists only ui + permissions rules, plus "<driver> rules" hint
		sk_drv = rig.skill(u, 'gen/x.json', None, 'python3 tool.py')
		self.assertNotIn('. Note:', sk_drv)
		self.assertIn('`tune.knob`', sk_drv)
		self.assertIn('`permissions.write`', sk_drv)
		self.assertNotIn('`cal.k0`', sk_drv)
		self.assertIn('Run `python3 tool.py rules` to inspect all 30 rules.', sk_drv)


class Types(unittest.TestCase):
	def test_type_problems(self):
		self.assertIsNone(rig.type_problem('list[tuple[str, int]]'))
		self.assertIsNone(rig.type_problem('list[(str, int)]'))
		self.assertIsNone(rig.type_problem('{a: str, b?: int, pass: bool, from?: str}'))
		self.assertIsNone(rig.type_problem('dict[str, float]'))
		self.assertIsNone(rig.type_problem('int?'))
		self.assertIsNone(rig.type_problem('"done" | "error"'))
		self.assertIn('not known', rig.type_problem('strng'))
		self.assertIn('takes one type', rig.type_problem('list[str, int]'))
		self.assertIn('write list[T]', rig.type_problem('(list str)'))
		self.assertIn('write {field: type', rig.type_problem('(record a int)'))
		self.assertIn('write T?', rig.type_problem('(maybe int)'))
		_, warn = rig.check(rig.parse('unit x\n  in a strng\n'))
		self.assertTrue(any('not known' in t for _, t in warn))
		self.assertTrue(any('not known' in t for _, t in errors(unit('  step s by model\n    do "x"\n    out strng\n  end e\n'))))

	def test_type_ok(self):
		rec = '{end: "done" | "error", n?: int}'
		self.assertTrue(rig.type_ok({'end': 'done'}, rec))
		self.assertTrue(rig.type_ok({'end': 'done', 'n': None}, rec))
		self.assertFalse(rig.type_ok({'end': 'other'}, rec))
		self.assertFalse(rig.type_ok({'end': 'done', 'extra': 1}, rec))
		self.assertFalse(rig.type_ok({'n': 1}, rec))
		self.assertFalse(rig.type_ok(True, 'int'))
		self.assertTrue(rig.type_ok([['a', 1]], 'list[tuple[str, int]]'))
		self.assertTrue(rig.type_ok({'small': 1.5, 'large': 3}, 'dict[str, float]'))
		self.assertFalse(rig.type_ok({'small': 'bad'}, 'dict[str, float]'))

	def test_tool_definition(self):
		u = rig.units(rig.parse('unit search\n  intent "search; give the first {search.n} results"\n  in query str "the words to search for"\n  in page int?\n'
			'  out {end: "done" | "error", results: list[str], reason?: str}\n  rule search.n 5 "Results"\n  code s search.py\n  step run by s.run\n  end done\n'))[0]
		d = rig.tool_def(u)
		self.assertEqual(d['name'], 'search')
		self.assertIn('the first 5 results', d['description'])
		self.assertEqual(d['parameters']['properties']['query'], {'type': 'string', 'description': 'the words to search for'})
		self.assertEqual(d['parameters']['required'], ['query'])
		self.assertEqual(d['returns']['required'], ['end', 'results'])


class Report(unittest.TestCase):
	def test_skill_asks_for_a_guessed_line(self):
		text = rig.skill(rig.units(load(PATTERN))[0])
		self.assertIn('## Report', text)
		self.assertIn('Guessed: readable', text)

	def test_no_report_without_guesses(self):
		text = rig.skill(rig.units(rig.parse(unit('  gate g hard by code.g\n    fail -> e\n  end e\n')))[0])
		self.assertNotIn('## Report', text)


class Viewer(unittest.TestCase):
	def test_the_viewer_has_no_parser(self):
		res_dir = os.path.join(ROOT, 'skills', 'rig', 'resources')
		for path in (
			os.path.join(ROOT, 'viewer', 'index.html'),
			os.path.join(res_dir, 'viewer.html'),
			os.path.join(res_dir, 'viewer.js'),
		):
			with open(path, encoding='utf-8') as f:
				content = f.read()
			for name in ('function parse(', 'function tokenize(', 'function check(', 'function catalog('):
				self.assertNotIn(name, content, path)
		for html_path in (os.path.join(ROOT, 'viewer', 'index.html'), os.path.join(res_dir, 'viewer.html')):
			with open(html_path, encoding='utf-8') as f:
				html_text = f.read()
			self.assertNotIn('<style', html_text, html_path)
			self.assertIn('viewer.css', html_text, html_path)
			self.assertIn('viewer.js', html_text, html_path)
		with open(os.path.join(res_dir, 'viewer.css'), encoding='utf-8') as f:
			css = f.read()
		for tok in ('--graph-col', '--graph-gap', '--graph-lane-pad'):
			self.assertIn(tok, css)
		self.assertTrue(os.path.isfile(os.path.join(res_dir, 'http.css')))

	def test_bundle_gives_what_the_viewer_draws(self):
		with open(PATTERN, encoding='utf-8') as f:
			text = f.read()
		b = rig.bundle(text, PATTERN)
		self.assertEqual(b['errors'], [])
		u = b['units'][0]
		root = rig.parse(text)
		self.assertEqual(u['catalogue'], rig.catalog(rig.units(root)[0], None, rig.Ctx(root, PATTERN)))
		for rid in ('target.standard', 'shorten.abbr_letters', 'permissions.rename'):  # a row of a rules block, a tuple, a rule line
			s = u['rules_src'][rid]
			line = text.split('\n')[s['line'] - 1]
			self.assertEqual(line[s['a']:s['b']], s['text'], rid)
		self.assertEqual(u['levels']['approve'], 'human')
		self.assertEqual(u['levels']['readable'], 'model')
		self.assertEqual(text.split('\n')[u['lines']['readable'] - 1].strip()[:13], 'gate readable')
		self.assertTrue(rig.bundle('unit x\n  in "a', None)['errors'])


class EditorGrammars(unittest.TestCase):
	def test_grammars_are_current(self):
		build = os.path.join(ROOT, 'editors', 'build.py')
		r = subprocess.run([sys.executable, build, '--check'], capture_output=True, text=True)
		self.assertEqual(r.returncode, 0, r.stdout)

	def test_head_words_match_the_spec(self):
		sys.path.insert(0, os.path.join(ROOT, 'editors'))
		import build
		with open(SPEC, encoding='utf-8') as f:
			spec = f.read()
		words = set()
		for rx, _, _ in build.HEADS:
			words.update(rx.split('(', 1)[1].split(')', 1)[0].split('|'))
		for w in sorted(words):
			self.assertIn('`' + w, spec, w)
		for w in sorted(rig.REMOVED):
			self.assertNotIn(w, words, w)

	def test_syntax_assertions_pass(self):
		'''Run every column scope assertion in editors/sublime/syntax_test_rig.rig against rig.tmLanguage.json.'''
		grammar_path = os.path.join(ROOT, 'editors', 'vscode', 'syntaxes', 'rig.tmLanguage.json')
		sublime_path = os.path.join(ROOT, 'editors', 'sublime', 'Rig.sublime-syntax')
		test_path = os.path.join(ROOT, 'editors', 'sublime', 'syntax_test_rig.rig')
		with open(grammar_path, encoding='utf-8') as f:
			tm = json.load(f)
		with open(sublime_path, encoding='utf-8') as f:
			sub_txt = f.read()
		self.assertIn('rules-block:', sub_txt)
		self.assertIn('fn-refs:', sub_txt)
		repo = tm['repository']

		def expand(patterns):
			out = []
			for p in patterns:
				if 'include' in p:
					ref = p['include'][1:]
					r = repo[ref]
					out.extend(expand(r['patterns']) if 'patterns' in r and 'begin' not in r and 'match' not in r else [r])
				else:
					out.append(p)
			return out

		def best_match(rules, line, pos):
			best = None
			for idx, rule in enumerate(rules):
				rx = rule.get('begin') or rule.get('match')
				m = re.compile(rx).search(line, pos)
				if m and (best is None or m.start() < best[0] or (m.start() == best[0] and idx < best[1])):
					best = (m.start(), idx, m, rule)
			return best

		def add_caps(tokens, base_scopes, m, caps, default_name=None):
			if default_name:
				tokens.append((m.start(), m.end(), base_scopes + [default_name]))
			if not caps:
				if not default_name and m.end() > m.start():
					tokens.append((m.start(), m.end(), list(base_scopes)))
				return
			cur = m.start()
			spans = []
			for k, v in sorted(((int(k), v['name']) for k, v in caps.items()), key=lambda x: x[0]):
				if k <= (m.lastindex or 0) and m.start(k) != -1 and m.end(k) > m.start(k):
					spans.append((m.start(k), m.end(k), v))
			spans.sort(key=lambda x: (x[0], -x[1]))
			for a, b, sc in spans:
				if a > cur:
					tokens.append((cur, a, list(base_scopes)))
				tokens.append((a, b, base_scopes + [sc]))
				cur = max(cur, b)
			if cur < m.end():
				tokens.append((cur, m.end(), list(base_scopes)))

		top_rules = expand(tm['patterns'])
		stack = []  # [(end_re, rules, scopes)]

		def tokenize_line(line):
			tokens = []
			pos = 0
			n = len(line)
			while pos <= n:
				cur_scopes = ['source.rig'] + [sc for _, _, scs in stack for sc in scs]
				end_hit = None
				if stack:
					end_re, _, _ = stack[-1]
					end_hit = end_re.search(line, pos)
				active_rules = stack[-1][1] if stack else top_rules
				hit = best_match(active_rules, line, pos) if pos < n else None
				if end_hit and (hit is None or end_hit.start() <= hit[0]):
					if end_hit.start() > pos:
						tokens.append((pos, end_hit.start(), cur_scopes))
					_, _, popped = stack.pop()
					if end_hit.end() > end_hit.start():
						tokens.append((end_hit.start(), end_hit.end(), cur_scopes))
						pos = end_hit.end()
						continue
					if pos == n:
						break
					continue
				if hit is None:
					if pos < n:
						tokens.append((pos, n, cur_scopes))
					break
				m_start, _, m, rule = hit
				if m_start > pos:
					tokens.append((pos, m_start, cur_scopes))
				if 'begin' in rule:
					extra = [rule['name']] if rule.get('name') else []
					add_caps(tokens, cur_scopes + extra, m, rule.get('beginCaptures'))
					stack.append((re.compile(rule['end']), expand(rule.get('patterns', [])), extra))
					pos = m.end() if m.end() > m_start else m_start + 1
				else:
					add_caps(tokens, cur_scopes, m, rule.get('captures'), rule.get('name'))
					pos = m.end() if m.end() > m_start else m_start + 1
			return tokens or [(0, max(1, n), ['source.rig'])]

		def has_scope(scopes, sel):
			return any(sc == sel or sc.startswith(sel + '.') for sc in scopes)

		with open(test_path, encoding='utf-8') as f:
			lines = f.read().split('\n')
		last = None
		checks = 0
		for i, line in enumerate(lines):
			toks = tokenize_line(line)
			m = re.match(r'^;( *)(<-|\^+) (- )?(\S+)', line)
			if i > 0 and m and last is not None:
				col = 0 if m.group(2) == '<-' else len(m.group(1)) + 1
				ln = 1 if m.group(2) == '<-' else len(m.group(2))
				neg = bool(m.group(3))
				want = m.group(4)
				for c in range(col, col + ln):
					tok = next((t for t in last[2] if t[0] <= c < t[1]), None)
					scopes = tok[2] if tok else ['source.rig']
					ok = (not has_scope(scopes, want)) if neg else has_scope(scopes, want)
					checks += 1
					self.assertTrue(
						ok,
						'line {} col {}: want {}{} got {}\n  {}'.format(last[0] + 1, c, '- ' if neg else '', want, scopes, last[1]),
					)
			else:
				last = (i, line, toks)
		self.assertGreater(checks, 100)


if __name__ == '__main__':
	unittest.main()
