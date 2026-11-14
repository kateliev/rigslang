"""Tests of the steps and of whole runs, on a copy of a case folder. No model: the test plays its answers."""
import json
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

GOOD = os.path.join(HERE, 'tests', 'cases', 'good')


class Steps(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.folder = os.path.join(self.tmp, 'release')
		shutil.copytree(GOOD, self.folder)
		self.kit = tool.kit(runs=None)

	def tearDown(self):
		shutil.rmtree(self.tmp)

	def test_collect(self):
		got = steps.collect({'folder': self.folder}, self.kit.rules)
		self.assertEqual(got['version'], '1.4.0')
		self.assertTrue(got['tests']['passed'])

	def test_dry_run_changes_nothing(self):
		r = self.kit.run({'folder': self.folder})
		self.assertEqual(r['waiting']['node'], 'tone')
		r = self.kit.answer(r['run'], {'pass': True})
		self.assertEqual(r['waiting']['kind'], 'human')
		r = self.kit.answer(r['run'], {'pass': True}, who='person')
		self.assertEqual(r['outcome']['end'], 'ready')
		self.assertFalse(os.path.exists(os.path.join(self.folder, 'published.json')))

	def test_publish_with_permission(self):
		r = self.kit.run({'folder': self.folder}, rules={'permissions.publish': True})
		r = self.kit.answer(r['run'], {'pass': True})
		r = self.kit.answer(r['run'], {'pass': True}, who='person')
		self.assertEqual(r['outcome']['end'], 'done')
		with open(os.path.join(self.folder, 'published.json'), encoding='utf-8') as f:
			self.assertEqual(json.load(f)['version'], '1.4.0')

	def test_publish_refuses_without_the_rule(self):
		with self.assertRaises(ValueError):
			steps.publish({'folder': self.folder, 'collect': {'version': '1', 'notes': ''}}, self.kit.rules)

	def test_the_model_cannot_answer_for_the_person(self):
		r = self.kit.run({'folder': self.folder})
		r = self.kit.answer(r['run'], {'pass': True})
		with self.assertRaises(rigkit.Refused):
			self.kit.answer(r['run'], {'pass': True})

	def test_regression_set(self):
		cases = rigkit.read_json(os.path.join(HERE, 'tests', 'regression-set.json'))
		try:
			_, diffs = self.kit.regress(cases)
		finally:
			tool.clean_cases()
		self.assertEqual(diffs, [])


if __name__ == '__main__':
	unittest.main()
