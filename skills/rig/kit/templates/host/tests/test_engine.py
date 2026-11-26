"""Pure-Python engine tests: no host app, no network, no model."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import engine  # noqa: E402


class Engine(unittest.TestCase):
	def test_propose(self):
		out = engine.propose({'item': 'abc', 'text': '  hello world  '})
		self.assertEqual(out['text'], 'hello world')
		self.assertEqual(out['words'], 2)


if __name__ == '__main__':
	unittest.main()
