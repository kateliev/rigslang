"""Tests of the steps, rollback, and whole runs."""
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

	def test_snapshot_and_compute(self):
		snap = steps.snapshot({'item': 'two words'}, self.kit.rules)
		out = steps.compute({'snapshot': snap}, self.kit.rules)
		self.assertEqual(out['words'], 2)

	def test_a_short_item_stops_and_rolls_back(self):
		r = self.kit.run({'item': 'ab'})
		self.assertEqual(r['outcome']['end'], 'stop')
		self.assertTrue(r.get('rolled_back'))

	def test_the_run_waits_for_the_model(self):
		r = self.kit.run({'item': 'a longer item'})
		self.assertEqual(r['waiting']['node'], 'sensible')
# >>> level 2

	def test_regression_set(self):
		cases = rigkit.read_json(os.path.join(HERE, 'tests', 'regression-set.json'))
		_, diffs = self.kit.regress(cases)
		self.assertEqual(diffs, [])
# <<< level 2


if __name__ == '__main__':
	unittest.main()
