"""Tests of the steps and of whole runs. No model: the test plays its answers."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rigkit  # noqa: E402
import steps  # noqa: E402
import tool  # noqa: E402


class Steps(unittest.TestCase):
	def setUp(self):
		self.kit = tool.kit(runs=None)

	def test_look(self):
		self.assertEqual(steps.look({'item': 'two words'}, self.kit.rules), {'length': 9, 'words': 2})

	def test_a_short_item_stops(self):
		r = self.kit.run({'item': 'ab'})
		self.assertEqual(r['outcome']['end'], 'stop')
		self.assertIn('limits.min_length', r['problems'][0])

	def test_the_run_waits_for_the_model(self):
		r = self.kit.run({'item': 'a longer item'})
		self.assertEqual(r['waiting']['node'], 'sensible')
		with self.assertRaises(rigkit.Refused):
			self.kit.answer(r['run'], {'result': 'this is a gate, not a step'})
# >>> level 3

	def test_regression_set(self):
		cases = rigkit.read_json(os.path.join(HERE, 'tests', 'regression-set.json'))
		_, diffs = self.kit.regress(cases)
		self.assertEqual(diffs, [])
# <<< level 3


if __name__ == '__main__':
	unittest.main()
