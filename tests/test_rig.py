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


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class ViewerParity(unittest.TestCase):
	def test_viewer_matches_rig_py(self):
		got = json.loads(subprocess.check_output(['node', os.path.join(ROOT, 'tests', 'parity.js')] + EXAMPLES).decode('utf-8'))
		want = []
		for path in EXAMPLES:
			root = load(path)
			for u in rig.units(root):
				want.append([u.word(0), rig.matrix_hash(u), [rig.body_hash(c) for c in u.kids('cast')]])
			want.append(['errors', sorted(line for line, _ in rig.check(root)[0])])
		self.assertEqual(got, want)


if __name__ == '__main__':
	unittest.main()
