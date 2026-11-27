"""Tests of the steps and of whole runs, on a copy of a case folder. No model: the test plays its answers."""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rigkit  # noqa: E402
import steps  # noqa: E402
import tool  # noqa: E402

CASES = os.path.join(HERE, 'tests', 'cases')
HFS = {'target.standard': 'hfs'}
GOOD = [{'Specimen': 'Spc', 'Grotesque': 'Grt'}, {'Specimen': 'Sp', 'Grotesque': 'Gr'}]
NEW = ['SpcGrtDs-HlExp.woff2', 'SpcGrtDs-It.woff2', 'SpcGrtDs-Rg.otf', 'SpcGrtDs-Rg.woff2', 'SpcGrtDs-XBdCnIt.otf', 'SpcGrtDs-XBdCnIt.woff2']


class Steps(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.folder = os.path.join(self.tmp, 'fonts')
		shutil.copytree(os.path.join(CASES, 'display'), self.folder)
		self.old = sorted(os.listdir(self.folder))
		self.kit = tool.kit(runs=None)

	def tearDown(self):
		shutil.rmtree(self.tmp)

	def test_parse(self):
		self.assertEqual(steps.parse('Sans-BoldItalic'), {'family': 'Sans', 'name': 'BoldItalic', 'italic': True, 'variable': False})
		self.assertEqual(steps.parse('Sans[wght]'), {'family': 'Sans', 'name': '', 'italic': False, 'variable': True})

	def test_read_groups_the_formats_of_one_style(self):
		got = steps.read({'folder': self.folder}, self.kit.rules)
		self.assertEqual(len(got['fonts']), 6)
		self.assertEqual(len(got['instances']), 4)
		self.assertEqual(got['suffix'], '.woff2')

	def test_plan_finds_the_words_the_table_does_not_know(self):
		r = self.kit.run({'folder': self.folder}, rules=HFS)
		self.assertEqual(r['waiting']['node'], 'abbreviate')
		self.assertEqual(r['waiting']['sees']['plan.weak_words'], ['Specimen', 'Grotesque'])

	def test_the_arena_tests_a_table_and_keeps_its_budget(self):
		r = self.kit.run({'folder': self.folder}, rules=HFS)
		self.assertIn('Takes {"table": {"Word": "Abbr", ...}}', r['waiting']['tool_help']['steps.try_names'])
		a = self.kit.arena_call(r['run'], 'steps.try_names', GOOD[0])  # the table without "table": the answer says how
		self.assertFalse(a['result']['fair'])
		self.assertIn('give the table inside "table"', a['result']['problems'][0])
		a = self.kit.arena_call(r['run'], 'steps.try_names', {'table': GOOD[0]})
		self.assertTrue(a['result']['fair'], a['result']['problems'])
		self.assertEqual(a['budget_remaining'], 4)
		a = self.kit.arena_call(r['run'], 'steps.table', {})
		self.assertEqual(a['result']['table']['bold'], 'Bd')
		with self.assertRaises(rigkit.Refused):
			self.kit.arena_call(r['run'], 'steps.rename', {})
		for _ in range(3):
			self.kit.arena_call(r['run'], 'steps.table', {})
		with self.assertRaises(rigkit.Refused):
			self.kit.arena_call(r['run'], 'steps.table', {})

	def test_dry_run_changes_nothing(self):
		r = self.kit.run({'folder': self.folder}, rules=HFS)
		r = self.kit.answer(r['run'], {'result': GOOD})
		r = self.kit.answer(r['run'], {'pass': True, 'why': 'Spc and Grt read as Specimen Grotesque'})  # readable: a model gate
		self.assertEqual(r['waiting']['kind'], 'human')
		r = self.kit.answer(r['run'], {'pass': True}, who='person')
		self.assertEqual(r['outcome']['end'], 'ready')
		self.assertEqual(r['guessed'], ['readable'])
		self.assertEqual(sorted(os.listdir(self.folder)), self.old)

	def test_rename_then_restore(self):
		r = self.kit.run({'folder': self.folder}, rules=dict(HFS, **{'permissions.rename': True}))
		r = self.kit.answer(r['run'], {'result': GOOD})
		r = self.kit.answer(r['run'], {'pass': True, 'why': 'Spc and Grt read as Specimen Grotesque'})  # readable: a model gate
		r = self.kit.answer(r['run'], {'pass': True}, who='person')
		self.assertEqual(r['outcome']['end'], 'done')
		self.assertEqual(sorted(os.listdir(self.folder)), NEW)
		r = self.kit.restore(r['run'])
		self.assertTrue(r['restored'])
		self.assertEqual(sorted(os.listdir(self.folder)), self.old)

	def test_rename_refuses_without_the_rule(self):
		with self.assertRaises(ValueError):
			steps.rename({'read': {'folder': self.folder}, 'final': {'table': [], 'token': 'x'}}, self.kit.rules)

	def test_undo_puts_back_a_rename_that_stopped_half_way(self):
		path = os.path.join(self.tmp, 'log.json')
		first = self.old[0]
		os.rename(os.path.join(self.folder, first), os.path.join(self.folder, first + steps.TMP))
		steps._save(path, {'folder': self.folder, 'moves': [{'old': first, 'new': 'X.otf', 'at': 'tmp'}, {'old': self.old[1], 'new': 'Y.otf', 'at': 'old'}]})
		self.assertEqual(steps.undo_log(path), {'restored': 1})
		self.assertEqual(sorted(os.listdir(self.folder)), self.old)
		self.assertFalse(os.path.exists(path))
		self.assertEqual(steps.undo_log(path), {'restored': 0})

	def test_the_model_cannot_answer_for_the_person(self):
		r = self.kit.run({'folder': self.folder}, rules=HFS)
		r = self.kit.answer(r['run'], {'result': GOOD})
		r = self.kit.answer(r['run'], {'pass': True, 'why': 'Spc and Grt read as Specimen Grotesque'})  # readable: a model gate
		with self.assertRaises(rigkit.Refused):
			self.kit.answer(r['run'], {'pass': True})

	def test_regression_set(self):
		cases = rigkit.read_json(os.path.join(HERE, 'tests', 'regression-set.json'))
		rename = os.path.join(CASES, 'rename')
		before = sorted(os.listdir(rename))
		try:
			_, diffs = self.kit.regress(cases)
		finally:
			tool.clean_cases()
		self.assertEqual(diffs, [])
		self.assertEqual(sorted(os.listdir(rename)), before)


if __name__ == '__main__':
	unittest.main()
