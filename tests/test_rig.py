"""Tests for rig.py and for the viewer parser. Run: python -m unittest discover tests"""
import glob
import json
import os
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


def load(path):
	with open(path, encoding='utf-8') as f:
		return rig.parse(f.read())


class Examples(unittest.TestCase):
	def test_examples_have_no_errors(self):
		for path in EXAMPLES:
			self.assertEqual(rig.check(load(path))[0], [], path)

	def test_slugify_is_proved(self):
		root = load(os.path.join(ROOT, 'examples', 'older', 'slugify.rig'))
		unit = rig.units(root)[0]
		self.assertTrue(rig.unit_status(unit)[0].startswith('proved'))
		ok, report = rig.prove(unit, 'slugify.rig')
		self.assertTrue(ok, report)

	def test_matrix_change_remelts(self):
		with open(os.path.join(ROOT, 'examples', 'older', 'slugify.rig'), encoding='utf-8') as f:
			text = f.read().replace('words joined by hyphens', 'words joined by dashes')
		self.assertTrue(rig.unit_status(rig.units(rig.parse(text))[0])[0].startswith('remelted'))

	def test_code_change_is_stale(self):
		with open(os.path.join(ROOT, 'examples', 'older', 'slugify.rig'), encoding='utf-8') as f:
			text = f.read().replace('.strip("-")', '.strip("-") or ""')
		self.assertTrue(rig.unit_status(rig.units(rig.parse(text))[0])[0].startswith('stale'))

	def test_bad_wiring_is_an_error(self):
		err, _ = rig.check(rig.parse('unit x agent\n  gate g maybe\n    pass -> nowhere\n'))
		self.assertEqual(len(err), 2)


class RulesAndPresets(unittest.TestCase):
	def test_mistakes_are_refused(self):
		lines = sorted(set(line for line, _ in rig.check(load(MISTAKES))[0]))
		self.assertEqual(lines, [4, 5, 6, 11, 14, 15, 16, 17, 28, 29])

	def test_a_number_in_prose_warns(self):
		_, warn = rig.check(load(MISTAKES))
		self.assertTrue(any(line == 19 and 'number' in t for line, t in warn))

	def test_plain_braces_are_text(self):
		err, _ = rig.check(rig.parse('unit x snippet\n  intent "keep {name} as written"\n'))
		self.assertEqual(err, [])

	def test_placeholder_counts_as_read(self):
		_, warn = rig.check(rig.parse('unit x agent\n  rule a.b 1\n  gate g hard\n    ensure "at most {a.b}"\n    by c.d\n    pass -> e\n  end e\n'))
		self.assertFalse(any('not read' in t for _, t in warn))


class Compile(unittest.TestCase):
	def unit(self, name, path='release-check.rig'):
		return rig.find(load(os.path.join(ROOT, 'examples', 'older', path)), name)

	def test_skill_writes_values_in(self):
		text = rig.skill(self.unit('release-check'))
		self.assertIn('at least 50 words', text)
		self.assertNotIn('{notes.min_words}', text)

	def test_skill_can_refer_to_the_catalogue(self):
		text = rig.skill(self.unit('release-check'), 'release-check.json')
		self.assertIn('`release-check.json`', text)
		self.assertIn('at least `{notes.min_words}` words', text)

	def test_preset_changes_value_not_default(self):
		c = rig.catalog(self.unit('release-check'), 'hotfix')
		r = [x for x in c['rules'] if x['id'] == 'notes.min_words'][0]
		self.assertEqual((r['value'], r['default']), (10, 50))
		self.assertIn('at least 10 words', rig.skill(self.unit('release-check'), None, 'hotfix'))

	def test_catalogue_round_trip(self):
		# Coverage depends on the other units of the file, not on the unit: leave it out.
		def meaning(c):
			return dict((k, v) for k, v in c.items() if k != 'coverage')
		for path in EXAMPLES:
			for u in rig.units(load(path)):
				c = rig.catalog(u)
				back = rig.units(rig.parse(rig.from_catalog(c)))[0]
				self.assertEqual(meaning(rig.catalog(back)), meaning(c), u.word(0))
				self.assertEqual(rig.check(rig.parse(rig.from_catalog(c)))[0], [], u.word(0))

	def test_command_line(self):
		tool = os.path.join(ROOT, 'skills', 'rig', 'rig.py')
		path = os.path.join(ROOT, 'examples', 'older', 'translate-ui.rig')
		out = subprocess.check_output([sys.executable, tool, 'compile', 'json', path, '--preset', 'careful']).decode('utf-8')
		c = json.loads(out)
		self.assertEqual((c['unit'], c['preset']), ('translate-ui', 'careful'))
		out = subprocess.check_output([sys.executable, tool, 'compile', 'skill', path, 'check-translation']).decode('utf-8')
		self.assertTrue(out.replace('\r\n', '\n').startswith('---\nname: check-translation\n'))


BANDSEARCH = os.path.join(ROOT, 'examples', 'older', 'bandsearch')
TOOL = os.path.join(ROOT, 'skills', 'rig', 'rig.py')


def cli(*args):
	return subprocess.run([sys.executable, TOOL] + list(args), capture_output=True, text=True)


def temp_rig(test, text):
	folder = tempfile.mkdtemp(prefix='rig-test-')
	test.addCleanup(shutil.rmtree, folder, True)
	path = os.path.join(folder, 'x.rig')
	with open(path, 'w', encoding='utf-8') as f:
		f.write(text)
	return path


class Levels(unittest.TestCase):
	def test_by_must_name_something(self):
		root = rig.parse('unit x agent\n  gate g hard\n    by nowhere.fn\n    pass -> e\n  end e\n')
		_, warn = rig.check(root)
		self.assertTrue(any('names no unit' in t for _, t in warn))
		self.assertEqual(rig.coverage(rig.units(root)[0])['none'], 1)

	def test_external_counts_as_code_and_must_be_used(self):
		root = rig.parse('unit x agent\n  external a.b "a library call"\n  external c.d\n  gate g hard\n    by a.b\n    pass -> e\n  end e\n')
		_, warn = rig.check(root)
		self.assertTrue(any('"c.d" is not named' in t for _, t in warn))
		self.assertEqual(rig.coverage(rig.units(root)[0])['code'], 1)

	def test_proved_unit_makes_a_proved_gate(self):
		u = rig.find(load(os.path.join(ROOT, 'examples', 'older', 'translate-ui.rig')), 'check-translation')
		cv = rig.coverage(u)
		self.assertEqual((cv['proved'], cv['code']), (2, 1))

	def test_old_coverage_was_too_high(self):
		cv = rig.coverage(rig.units(load(os.path.join(ROOT, 'examples', 'older', 'release-check.rig')))[0])
		self.assertEqual((cv['gates'], cv['proved'], cv['code'], cv['judge']), (4, 0, 3, 1))

	def test_uses_file_reaches_another_file(self):
		path = os.path.join(BANDSEARCH, 'bandsearch.rig')
		_, root = rig.load(path)
		u = rig.units(root)[0]
		self.assertEqual(rig.coverage(u, rig.Ctx(root, path))['observed'], 2)
		self.assertEqual(rig.coverage(u)['code'], 2)  # without the path, other files count as code

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

	def test_type_ok(self):
		rec = self.t('(record end (one-of done error) n (maybe int))')
		self.assertTrue(rig.type_ok({'end': 'done'}, rec))
		self.assertFalse(rig.type_ok({'end': 'other'}, rec))
		self.assertFalse(rig.type_ok({'n': 1}, rec))
		self.assertFalse(rig.type_ok(True, self.t('int')))
		self.assertTrue(rig.type_ok([['a', 1]], self.t('(list (tuple str int))')))
		self.assertFalse(rig.type_ok([['a', 'b']], self.t('(list (tuple str int))')))

	def test_tool_definition(self):
		u = rig.find(rig.load(os.path.join(BANDSEARCH, 'search.rig'))[1], 'search')
		d = rig.tool_def(u)
		self.assertEqual(d['name'], 'search')
		self.assertIn('the first 5 results', d['description'])
		self.assertEqual(d['parameters']['properties']['query'], {'type': 'string', 'description': 'the words to search for'})
		self.assertEqual(d['parameters']['required'], ['query'])
		self.assertEqual(d['returns']['required'], ['end', 'results'])  # "reason" is (maybe str)


class Report(unittest.TestCase):
	def test_skill_asks_for_a_guessed_line(self):
		text = rig.skill(rig.units(load(os.path.join(ROOT, 'examples', 'older', 'release-check.rig')))[0])
		self.assertIn('## Report', text)
		self.assertIn('Guessed: tone', text)

	def test_no_report_without_guesses(self):
		text = rig.skill(rig.parse('unit x agent\n  external a.b\n  gate g hard\n    by a.b\n    pass -> e\n  end e\n').children[0])
		self.assertNotIn('## Report', text)


PY_UNIT = '''unit twice snippet
  intent "two times the number"
  in n int
  out int
  example 2 => 4
  ensure "the result is even"
    check py "result % 2 == 0"
  cast py
    def twice(n):
        return n * 2
'''


class Runs(unittest.TestCase):
	def test_py_prove_and_stamp(self):
		path = temp_rig(self, PY_UNIT)
		r = cli('prove', path, '--stamp')
		self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
		self.assertTrue(rig.unit_status(rig.units(rig.load(path)[1])[0])[0].startswith('proved py'))

	def test_wrong_out_type_fails(self):
		path = temp_rig(self, PY_UNIT.replace('return n * 2', 'return float(n * 2) + 0.5').replace('example 2 => 4', 'example 2 => 4.5').replace('result % 2 == 0', 'True'))
		ok, report = rig.prove(rig.units(rig.load(path)[1])[0], path)
		self.assertFalse(ok)
		self.assertIn('out type', ' '.join(report))

	def test_no_examples_cannot_be_proved(self):
		path = temp_rig(self, PY_UNIT.replace('  example 2 => 4\n', ''))
		ok, report = rig.prove(rig.units(rig.load(path)[1])[0], path)
		self.assertIsNone(ok)

	def test_stamp_refuses_a_language_with_a_runner(self):
		path = temp_rig(self, PY_UNIT)
		r = cli('stamp', path, 'twice', 'py')
		self.assertNotEqual(r.returncode, 0)
		self.assertIn('prove --stamp', r.stdout + r.stderr)

	def test_probe_stamps_observed_only_without_examples(self):
		path = temp_rig(self, PY_UNIT.replace('  example 2 => 4\n', '  probe 21\n    check py "result == 42"\n'))
		r = cli('probe', path, '--stamp')
		self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
		self.assertTrue(rig.unit_status(rig.units(rig.load(path)[1])[0])[0].startswith('observed py'))
		path = temp_rig(self, PY_UNIT + '  probe 21\n')
		self.assertIn('not stamped', cli('probe', path, '--stamp').stdout)

	def test_failed_probe(self):
		path = temp_rig(self, PY_UNIT.replace('  example 2 => 4\n', '  probe 21\n    check py "result == 43"\n'))
		ok, report = rig.probe(rig.units(rig.load(path)[1])[0], path)
		self.assertFalse(ok)

	def test_emit_writes_only_stamped_casts(self):
		path = temp_rig(self, PY_UNIT)
		out = os.path.join(os.path.dirname(path), 'out')
		written, refused = rig.emit(path, 'py', out)
		self.assertEqual((written, len(refused)), ([], 1))
		cli('prove', path, '--stamp')
		written, refused = rig.emit(path, 'py', out)
		self.assertEqual(sorted(os.path.basename(w) for w in written), ['twice.json', 'twice.py'])

	@unittest.skipUnless(shutil.which('node'), 'node is not installed')
	def test_ts_casts_are_proved_in_node(self):
		_, root = rig.load(os.path.join(BANDSEARCH, 'wiki.rig'))
		for name in ('wiki-title', 'album-list'):
			ok, report = rig.prove(rig.find(root, name), 'wiki.rig')
			self.assertTrue(ok, report)

	@unittest.skipUnless(shutil.which('node'), 'node is not installed')
	def test_broken_ts_cast_fails(self):
		with open(os.path.join(BANDSEARCH, 'wiki.rig'), encoding='utf-8') as f:
			text = f.read().replace('return decodeURIComponent(title);', 'return title;')
		ok, report = rig.prove(rig.find(rig.parse(text), 'wiki-title'), 'wiki.rig')
		self.assertFalse(ok)


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class ViewerParity(unittest.TestCase):
	def test_viewer_matches_rig_py(self):
		self.maxDiff = 4000
		got = json.loads(subprocess.check_output(['node', os.path.join(ROOT, 'tests', 'parity.js')] + EXAMPLES + [MISTAKES]).decode('utf-8'))
		want = []
		for path in EXAMPLES + [MISTAKES]:
			root = load(path)
			for u in rig.units(root):
				want.append([u.word(0), rig.matrix_hash(u), [rig.body_hash(c) for c in u.kids('cast')],
					rig.catalog(u), rig.skill(u), rig.skill(u, 'rules.json'),
					[[p.word(0), rig.catalog(u, p.word(0)), rig.skill(u, None, p.word(0))] for p in u.kids('preset')],
					rig.tool_def(u)])
			want.append(['errors', sorted(line for line, _ in rig.check(root)[0])])
		self.assertEqual(got, want)


class EditorGrammars(unittest.TestCase):
	def test_grammars_are_current(self):
		build = os.path.join(ROOT, 'editors', 'build.py')
		r = subprocess.run([sys.executable, build, '--check'], capture_output=True, text=True)
		self.assertEqual(r.returncode, 0, r.stdout)

	def test_head_words_match_the_spec(self):
		sys.path.insert(0, os.path.join(ROOT, 'editors'))
		import build
		with open(os.path.join(ROOT, 'skills', 'rig', 'spec.md'), encoding='utf-8') as f:
			spec = f.read()
		words = set()
		for rx, _, _ in build.HEADS:
			words.update(rx.split('(', 1)[1].split(')', 1)[0].split('|'))
		for w in sorted(words):
			self.assertIn('`' + w, spec, w)


if __name__ == '__main__':
	unittest.main()
