"""Tests of the tools. Run: python3 -m unittest discover -s tests   (or: rig.py test .)"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rigkit  # noqa: E402
import tool  # noqa: E402
import tools  # noqa: E402


class Tools(unittest.TestCase):
	def test___FN__(self):
		self.assertEqual(tools.__FN__('two words'), {'words': 2, 'characters': 9})

	def test_a_wrong_input_is_refused(self):
		with self.assertRaises(rigkit.Refused):
			tool.kit().call('__NAME__', {'txt': 'a wrong name'})


if __name__ == '__main__':
	unittest.main()
