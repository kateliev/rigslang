"""Tests for rig.py and for the viewer parser. Run: python -m unittest discover tests"""
import glob
import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'rig'))
import rig  # noqa: E402

EXAMPLES = sorted(glob.glob(os.path.join(ROOT, 'examples', '*.rig')))
MISTAKES = os.path.join(ROOT, 'tests', 'fixtures', 'mistakes.rig')


def load(path):
	with open(path, encoding='utf-8') as f:
		return rig.parse(f.read())


class Examples(unittest.TestCase):
	def test_examples_have_no_errors(self):
		for path in EXAMPLES:
			self.assertEqual(rig.check(load(path))[0], [], path)

	def test_slugify_is_proved(self):
		root = load(os.path.join(ROOT, 'examples', 'slugify.rig'))
		unit = rig.units(root)[0]
		self.assertTrue(rig.unit_status(unit)[0].startswith('proved'))
		ok, report = rig.prove(unit, 'slugify.rig')
		self.assertTrue(ok, report)

	def test_matrix_change_remelts(self):
		with open(os.path.join(ROOT, 'examples', 'slugify.rig'), encoding='utf-8') as f:
			text = f.read().replace('words joined by hyphens', 'words joined by dashes')
		self.assertTrue(rig.unit_status(rig.units(rig.parse(text))[0])[0].startswith('remelted'))

	def test_code_change_is_stale(self):
		with open(os.path.join(ROOT, 'examples', 'slugify.rig'), encoding='utf-8') as f:
			text = f.read().replace('.strip("-")', '.strip("-") or ""')
		self.assertTrue(rig.unit_status(rig.units(rig.parse(text))[0])[0].startswith('stale'))

	def test_bad_wiring_is_an_error(self):
		err, _ = rig.check(rig.parse('unit x agent\n  gate g maybe\n    pass -> nowhere\n'))
		self.assertEqual(len(err), 2)


class RulesAndPresets(unittest.TestCase):
	def test_mistakes_are_refused(self):
		lines = sorted(set(line for line, _ in rig.check(load(MISTAKES))[0]))
		self.assertEqual(lines, [4, 5, 6, 11, 14, 15, 16, 17])

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
		return rig.find(load(os.path.join(ROOT, 'examples', path)), name)

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
		for path in EXAMPLES:
			for u in rig.units(load(path)):
				c = rig.catalog(u)
				back = rig.units(rig.parse(rig.from_catalog(c)))[0]
				self.assertEqual(rig.catalog(back), c, u.word(0))
				self.assertEqual(rig.check(rig.parse(rig.from_catalog(c)))[0], [], u.word(0))

	def test_command_line(self):
		tool = os.path.join(ROOT, 'skills', 'rig', 'rig.py')
		path = os.path.join(ROOT, 'examples', 'translate-ui.rig')
		out = subprocess.check_output([sys.executable, tool, 'compile', 'json', path, '--preset', 'careful']).decode('utf-8')
		c = json.loads(out)
		self.assertEqual((c['unit'], c['preset']), ('translate-ui', 'careful'))
		out = subprocess.check_output([sys.executable, tool, 'compile', 'skill', path, 'check-translation']).decode('utf-8')
		self.assertTrue(out.replace('\r\n', '\n').startswith('---\nname: check-translation\n'))


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
					[[p.word(0), rig.catalog(u, p.word(0)), rig.skill(u, None, p.word(0))] for p in u.kids('preset')]])
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
