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

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', '__NAME__.json'))


def rules(**changes):
	'''The rules of the catalogue; write a change as limits__min_length=10.'''
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


class Gates(unittest.TestCase):
	def test_long_enough(self):
		self.assertTrue(gates.long_enough({'look': {'length': 12}}, rules())['pass'])
		v = gates.long_enough({'look': {'length': 1}}, rules())
		self.assertFalse(v['pass'])
		self.assertIn('limits.min_length', v['problems'][0])
		self.assertFalse(gates.long_enough({'look': {'length': 12}}, rules(limits__min_length=20))['pass'])
# >>> level 4

	def test_may_write(self):
		self.assertFalse(gates.may_write({}, rules())['pass'])
		self.assertTrue(gates.may_write({}, rules(permissions__write=True))['pass'])
# <<< level 4


if __name__ == '__main__':
	unittest.main()
