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


def unit(body, head='unit x agent'):
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
				text = 'unit example agent\n' + ''.join('  ' + l + '\n' for l in text.split('\n') if l.strip())
			self.assertEqual(errors(text), [], text)


class Removed(unittest.TestCase):
	'''Every word of version 0 that version 1 removed is refused, and the error names the replacement.'''
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
		'cast': ('  cast py\n    def x(): pass\n', 'code <path>'),
		'probe': ('  probe 1\n', 'test file'),
		'evidence': ('  note "x"\n    evidence README.md\n', 'text of the note'),
	}

	def test_each_removed_word_is_refused_with_its_replacement(self):
		for word, (body, hint) in self.CASES.items():
			err = errors(unit(body))
			self.assertTrue(err, word)
			self.assertTrue(any(hint in t for _, t in err), (word, err))

	def test_the_scope_snippet(self):
		err = errors('unit x snippet\n  intent "x"\n')
		self.assertTrue(any('tool or agent' in t for _, t in err))

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
      out (record v int)
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
		self.assertEqual((d['lane'], d['out']), ('model', '(record v int)'))
		self.assertEqual(d['schema'], {'type': 'object', 'properties': {'v': {'type': 'integer'}}, 'required': ['v'], 'additionalProperties': False})
		self.assertNotIn('by', d)
		self.assertEqual(node(self.c, 'make')['lane'], 'code')
		w = warnings(unit('  step s\n    do "x"\n  end e\n'))
		self.assertTrue(any('say who does it' in t for _, t in w))
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
		c = catalogue('unit x tool\n  check "every result is even"\n  code x.py\n')
		self.assertEqual(c['checks'], ['every result is even'])

	def test_range_and_the_label(self):
		r = next(r for r in self.c['rules'] if r['id'] == 'limits.max')
		self.assertEqual((r['min'], r['max'], r['label']), (1, 100, 'Largest number'))
		err = errors('unit x agent\n  rule a.b 300 "x"\n    range 1 100\n')
		self.assertTrue(any('above the range' in t for _, t in err))
		err = errors('unit x agent\n  rule a.b 3 x\n')
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
		self.assertEqual(errors('unit x tool\n  intent "keep {name} as written"\n'), [])

	def test_placeholder_counts_as_read(self):
		w = warnings(unit('  rule a.b 1\n  gate g hard by code.g\n    check "at most {a.b}"\n    fail -> e\n  end e\n'))
		self.assertFalse(any('not read' in t for _, t in w))


RELEASE = os.path.join(ROOT, 'examples', 'release-tool', 'release.rig')


class Compile(unittest.TestCase):
	def unit(self):
		return rig.units(load(RELEASE))[0]

	def test_skill_writes_values_in(self):
		text = rig.skill(self.unit())
		self.assertIn('at least 50 words', text)
		self.assertNotIn('{notes.min_words}', text)
		self.assertIn('Next: `notes`', text)  # the agent walks the flow itself: each node says the next one

	def test_skill_can_refer_to_the_catalogue(self):
		text = rig.skill(self.unit(), 'release.json')
		self.assertIn('`release.json`', text)
		self.assertIn('at least `{notes.min_words}` words', text)

	def test_skill_with_a_runner(self):
		text = rig.skill(self.unit(), None, None, 'python3 tool.py')
		self.assertIn('python3 tool.py run', text)
		self.assertNotIn('Next: ', text)

	def test_skill_shows_the_blocks(self):
		text = rig.skill(rig.units(rig.parse(FLOW))[0])
		for part in ('**For each `x` in `make.items`**', '**Until `make.done` is true**', '**If `make.big`**', '**Else', '**Finally', '### Choose',
				'leave this item', 'at most 3 more times', 'The first is the default'):
			self.assertIn(part, text)

	def test_preset_changes_value_not_default(self):
		c = rig.catalog(self.unit(), 'hotfix')
		r = [x for x in c['rules'] if x['id'] == 'notes.min_words'][0]
		self.assertEqual((r['value'], r['default']), (10, 50))
		self.assertIn('at least 10 words', rig.skill(self.unit(), None, 'hotfix'))

	def test_catalogue_round_trip(self):
		def meaning(c):
			return dict((k, v) for k, v in c.items() if k != 'coverage')  # coverage depends on the files, not on the unit
		for text in [FLOW] + [open(p, encoding='utf-8').read() for p in EXAMPLES]:
			for u in rig.units(rig.parse(text)):
				c = rig.catalog(u)
				back = rig.from_catalog(c)
				self.assertEqual(meaning(rig.catalog(rig.units(rig.parse(back))[0])), meaning(c), u.word(0))
				self.assertEqual(rig.check(rig.parse(back))[0], [], u.word(0))

	def test_command_line(self):
		out = subprocess.check_output([sys.executable, TOOL, 'compile', 'json', RELEASE, '--preset', 'hotfix']).decode('utf-8')
		c = json.loads(out)
		self.assertEqual((c['unit'], c['preset'], c['rig']), ('release', 'hotfix', 1))
		out = subprocess.check_output([sys.executable, TOOL, 'compile', 'skill', RELEASE]).decode('utf-8')
		self.assertTrue(out.replace('\r\n', '\n').startswith('---\nname: release\n'))
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
		root = rig.parse('unit x agent\n  gate g hard by nowhere.fn\n    fail -> e\n  end e\n')
		_, warn = rig.check(root)
		self.assertTrue(any('names no unit' in t for _, t in warn))
		self.assertEqual(rig.coverage(rig.units(root)[0])['none'], 1)

	def test_levels_of_the_example(self):
		cv = rig.coverage(rig.units(load(RELEASE))[0], rig.Ctx(load(RELEASE), RELEASE))
		self.assertEqual((cv['gates'], cv['tested'], cv['model'], cv['human']), (8, 6, 1, 1))

	def test_a_unit_in_another_file(self):
		folder = tempfile.mkdtemp(prefix='rig-test-')
		self.addCleanup(shutil.rmtree, folder, True)
		with open(os.path.join(folder, 'other.rig'), 'w', encoding='utf-8') as f:
			f.write('unit helper tool\n  intent "x"\n  code helper.py\n')
		with open(os.path.join(folder, 'helper.py'), 'w', encoding='utf-8') as f:
			f.write('def helper(state, R):\n\treturn True\n')
		path = os.path.join(folder, 'x.rig')
		with open(path, 'w', encoding='utf-8') as f:
			f.write('unit x agent\n  uses helper other.rig\n  gate g hard by helper\n    fail -> e\n  end e\n')
		root = rig.load(path)[1]
		self.assertEqual(rig.coverage(rig.units(root)[0], rig.Ctx(root, path))['code'], 1)
		self.assertEqual(rig.check(root, path)[0], [])

	def test_missing_uses_file_warns(self):
		path = temp_rig(self, 'unit x agent\n  uses y nothere.rig\n')
		_, warn = rig.check(rig.load(path)[1], path)
		self.assertTrue(any('does not exist' in t for _, t in warn))


class Types(unittest.TestCase):
	def t(self, s):
		return rig.tokenize(s, 1)[0]

	def test_type_problems(self):
		self.assertIsNone(rig.type_problem(self.t('(list (tuple str int))')))
		self.assertIsNone(rig.type_problem(self.t('(record a str b (maybe int))')))
		self.assertIn('not known', rig.type_problem(self.t('strng')))
		self.assertIn('takes one type', rig.type_problem(self.t('(list str int)')))
		_, warn = rig.check(rig.parse('unit x\n  in a strng\n'))
		self.assertTrue(any('not known' in t for _, t in warn))
		self.assertTrue(any('not known' in t for _, t in errors(unit('  step s by model\n    do "x"\n    out strng\n  end e\n'))))

	def test_type_ok(self):
		rec = self.t('(record end (one-of done error) n (maybe int))')
		self.assertTrue(rig.type_ok({'end': 'done'}, rec))
		self.assertFalse(rig.type_ok({'end': 'other'}, rec))
		self.assertFalse(rig.type_ok({'n': 1}, rec))
		self.assertFalse(rig.type_ok(True, self.t('int')))
		self.assertTrue(rig.type_ok([['a', 1]], self.t('(list (tuple str int))')))

	def test_tool_definition(self):
		u = rig.units(rig.parse('unit search tool\n  intent "search; give the first {search.n} results"\n  in query str "the words to search for"\n  in page (maybe int)\n'
			'  out (record end (one-of done error) results (list str) reason (maybe str))\n  rule search.n 5 "Results"\n  code search.py\n'))[0]
		d = rig.tool_def(u)
		self.assertEqual(d['name'], 'search')
		self.assertIn('the first 5 results', d['description'])
		self.assertEqual(d['parameters']['properties']['query'], {'type': 'string', 'description': 'the words to search for'})
		self.assertEqual(d['parameters']['required'], ['query'])
		self.assertEqual(d['returns']['required'], ['end', 'results'])


class Report(unittest.TestCase):
	def test_skill_asks_for_a_guessed_line(self):
		text = rig.skill(rig.units(load(RELEASE))[0])
		self.assertIn('## Report', text)
		self.assertIn('Guessed: tone', text)

	def test_no_report_without_guesses(self):
		text = rig.skill(rig.units(rig.parse(unit('  gate g hard by code.g\n    fail -> e\n  end e\n')))[0])
		self.assertNotIn('## Report', text)


class Viewer(unittest.TestCase):
	def test_the_viewer_has_no_parser(self):
		with open(os.path.join(ROOT, 'viewer', 'index.html'), encoding='utf-8') as f:
			page = f.read()
		for name in ('function parse(', 'function tokenize(', 'function check(', 'function catalog('):
			self.assertNotIn(name, page)

	def test_bundle_gives_what_the_viewer_draws(self):
		with open(RELEASE, encoding='utf-8') as f:
			text = f.read()
		b = rig.bundle(text, RELEASE)
		self.assertEqual(b['errors'], [])
		u = b['units'][0]
		root = rig.parse(text)
		self.assertEqual(u['catalogue'], rig.catalog(rig.units(root)[0], None, rig.Ctx(root, RELEASE)))
		s = u['rules_src']['notes.min_words']
		line = text.split('\n')[s['line'] - 1]
		self.assertEqual(line[s['a']:s['b']], s['text'])
		self.assertEqual(u['levels']['approve'], 'human')
		self.assertEqual(text.split('\n')[u['lines']['tone'] - 1].strip()[:9], 'gate tone')
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


if __name__ == '__main__':
	unittest.main()
