"""Tests of the gates, with the rule defaults of the catalogue. No files, no model.
Run: python3 -m unittest discover -s tests   (or: rig.py test .)
Every gate needs a test here that names it: rig.py check counts a gate as tested only then."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'font-names.json'))
DISPLAY = [{'family': 'SpecimenGrotesqueDisplay', 'name': n} for n in ('Regular', 'ExtraBoldCondensedItalic')]


def rules(**changes):
	'''The rules of the catalogue; write a change as target__standard="hfs".'''
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


def read(names, instances=DISPLAY, suffix='.woff2'):
	fonts = [{'file': n, 'instance': i} for i, n in enumerate(names)]
	return {'fonts': fonts, 'instances': instances, 'names': list(names), 'suffix': suffix}


class Gates(unittest.TestCase):
	def test_files_ok(self):
		self.assertTrue(gates.files_ok({'read': read(['A-Rg.otf', 'A-Bd.otf'])}, rules())['pass'])
		v = gates.files_ok({'read': read([], [])}, rules())
		self.assertFalse(v['pass'])
		self.assertIn('no font file', v['problems'][0])
		v = gates.files_ok({'read': read(['-Bold.otf'], [{'family': '', 'name': 'Bold'}])}, rules())
		self.assertIn('no family name', v['problems'][0])

	def test_abbr_ok(self):
		state = {'read': read(['a', 'b'])}
		state['abbreviate'] = [{'Specimen': 'S'}, {'Specimen': 'Spc', 'Grotesque': 'Grt'}]
		v = gates.abbr_ok(state, rules(target__standard='hfs'))
		self.assertTrue(v['pass'], v['problems'])
		self.assertEqual((v['best'], v['fair']), (1, [False, True]))
		state['abbreviate'] = [{'Specimen': 'S'}, {'Grotesque': 'Gzk'}]
		v = gates.abbr_ok(state, rules(target__standard='hfs'))
		self.assertFalse(v['pass'])
		self.assertEqual(len(v['problems']), 2)
		self.assertFalse(gates.abbr_ok({'read': state['read'], 'abbreviate': None}, rules())['pass'])
		# a stricter rule refuses three letters
		state['abbreviate'] = [{'Specimen': 'Spc', 'Grotesque': 'Grt'}, {'Specimen': 'Spc', 'Grotesque': 'Grt'}]
		self.assertFalse(gates.abbr_ok(state, rules(target__standard='hfs', shorten__abbr_letters=[2, 2]))['pass'])

	def test_fits(self):
		ok = {'final': {'rows': [{'short': 'Sans-Bd', 'issues': ['duplicate']}]}}
		self.assertTrue(gates.fits(ok, rules())['pass'])
		bad = {'final': {'rows': [{'short': 'AUX', 'issues': ['reserved']}]}}
		v = gates.fits(bad, rules())
		self.assertFalse(v['pass'])
		self.assertEqual(v['problems'], ['AUX: reserved'])

	def test_unique(self):
		tbl = [{'old': 'A-Bold.otf', 'new': 'A-Bd.otf'}, {'old': 'A-Black.otf', 'new': 'A-Blk.otf'}]
		self.assertTrue(gates.unique({'final': {'table': tbl}, 'read': {'names': ['A-Bold.otf', 'A-Black.otf']}}, rules())['pass'])
		same = [{'old': 'A-Bold.otf', 'new': 'A-Bd.otf'}, {'old': 'A-Bd.otf', 'new': 'a-bd.otf'}]
		v = gates.unique({'final': {'table': same}, 'read': {'names': ['A-Bold.otf', 'A-Bd.otf']}}, rules())
		self.assertIn('both become', v['problems'][0])
		v = gates.unique({'final': {'table': tbl[:1]}, 'read': {'names': ['A-Bold.otf', 'a-bd.otf']}}, rules())
		self.assertIn('another file', v['problems'][0])
		# a change of case only: the old name is the file itself
		case = [{'old': 'sans-bd.otf', 'new': 'SANS-BD.otf'}]
		self.assertTrue(gates.unique({'final': {'table': case}, 'read': {'names': ['sans-bd.otf']}}, rules())['pass'])

	def test_something(self):
		self.assertTrue(gates.something({'final': {'changes': 2}}, rules())['pass'])
		self.assertFalse(gates.something({'final': {'changes': 0}}, rules())['pass'])

	def test_may_rename(self):
		self.assertFalse(gates.may_rename({}, rules())['pass'])
		self.assertTrue(gates.may_rename({}, rules(permissions__rename=True))['pass'])

	def test_verify(self):
		final = {'table': [{'old': 'A-Bold.otf', 'new': 'A-Bd.otf'}, {'old': 'A-Rg.otf', 'new': 'A-Rg.otf'}]}
		rd = {'fonts': [1, 2]}
		good = {'final': final, 'read': rd, 'rename': {'renamed': [['A-Bold.otf', 'A-Bd.otf']], 'after': ['A-Bd.otf', 'A-Rg.otf']}}
		self.assertTrue(gates.verify(good, rules())['pass'])
		left = dict(good, rename={'renamed': [['A-Bold.otf', 'A-Bd.otf']], 'after': ['A-Bold.otf.font-names-tmp', 'A-Rg.otf']})
		v = gates.verify(left, rules())
		self.assertFalse(v['pass'])
		self.assertEqual(v['problems'], ['A-Bd.otf is missing', 'A-Bold.otf.font-names-tmp was left behind', '2 font files before, 1 after'])


if __name__ == '__main__':
	unittest.main()
