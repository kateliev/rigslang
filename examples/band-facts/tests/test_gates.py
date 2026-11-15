"""Tests of the gates and of the pure helpers, with the rule defaults of the catalogue. No network, no model.
Run: python3 -m unittest discover -s tests   (or: rig.py test .)"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import parse  # noqa: E402
import rigkit  # noqa: E402

CATALOGUE = rigkit.read_json(os.path.join(HERE, 'gen', 'band-facts.json'))


def rules(**changes):
	'''The rules of the catalogue; write a change as answer__max_words=40.'''
	return rigkit.Rules(CATALOGUE, dict((k.replace('__', '.'), v) for k, v in changes.items()))


class Gates(unittest.TestCase):
	def test_article_found(self):
		self.assertTrue(gates.article_found({'find': {'url': 'https://en.wikipedia.org/wiki/X', 'results': [[1, 2]]}}, rules())['pass'])
		v = gates.article_found({'find': {'url': None, 'results': []}}, rules())
		self.assertFalse(v['pass'])
		self.assertIn('search.results', v['problems'][0])
		off = gates.article_found({'find': {'answered': False, 'url': None, 'results': []}}, rules())
		self.assertEqual(off['when'], 'the search did not answer')

	def test_summary_ok(self):
		self.assertTrue(gates.summary_ok({'find': {}, 'read': {'summary': 'A band.'}}, rules())['pass'])
		self.assertFalse(gates.summary_ok({'find': {'title': 'X'}, 'read': {'summary': '  '}}, rules())['pass'])

	def test_albums_found(self):
		self.assertTrue(gates.albums_found({'read': {'albums': [['A', 1999]]}}, rules())['pass'])
		self.assertFalse(gates.albums_found({'read': {'albums': []}}, rules())['pass'])

	def test_short_enough(self):
		self.assertTrue(gates.short_enough({'write': 'word ' * 120}, rules())['pass'])
		v = gates.short_enough({'write': 'word ' * 121}, rules())
		self.assertFalse(v['pass'])
		self.assertEqual(v['words'], 121)
		self.assertIn('answer.max_words 120', v['problems'][0])
		self.assertFalse(gates.short_enough({'write': 'word ' * 50}, rules(answer__max_words=40))['pass'])
		self.assertFalse(gates.short_enough({'write': ''}, rules())['pass'])
		self.assertFalse(gates.short_enough({'write': {'text': 'not a text'}}, rules())['pass'])

	def test_rounds_left(self):
		self.assertTrue(gates.rounds_left({'_visits': {'write': 1}}, rules())['pass'])
		self.assertTrue(gates.rounds_left({'_visits': {'write': 2}}, rules())['pass'])
		self.assertFalse(gates.rounds_left({'_visits': {'write': 3}}, rules())['pass'])
		self.assertFalse(gates.rounds_left({'_visits': {'write': 1}}, rules(answer__rounds=0))['pass'])


class Parse(unittest.TestCase):
	def test_search_titles(self):
		data = {'query': {'search': [{'title': 'A'}, {'title': 'B'}, {'nothing': 1}]}}
		self.assertEqual(parse.search_titles(data, 5), ['A', 'B'])
		self.assertEqual(parse.search_titles(data, 1), ['A'])
		self.assertEqual(parse.search_titles({}, 5), [])

	def test_pick_title(self):
		titles = ['List of Some Band members', 'Some Band discography', 'Some Band']
		self.assertEqual(parse.pick_title('some band', titles), 'Some Band')
		self.assertEqual(parse.pick_title('Mercury', ['Mercury (planet)', 'Mercury (band)']), 'Mercury (band)')
		self.assertEqual(parse.pick_title('Other', titles), 'List of Some Band members')
		self.assertIsNone(parse.pick_title('Other', []))

	def test_wiki_title(self):
		self.assertEqual(parse.wiki_title('https://en.wikipedia.org/wiki/Some_Band'), 'Some_Band')
		self.assertEqual(parse.wiki_title('https://en.m.wikipedia.org/wiki/Mot%C3%B6rhead#Discography'), 'Motörhead')
		self.assertEqual(parse.wiki_title('https://de.wikipedia.org/wiki/Some_Band'), '')
		self.assertEqual(parse.wiki_title('https://example.org/wiki/Some_Band'), '')

	def test_album_list(self):
		self.assertEqual(parse.album_list("* ''[[The Hill]]'' (1979)\n* ''[[Animals (an album)|Animals]]'' (1977)"), [['The Hill', 1979], ['Animals', 1977]])
		self.assertEqual(parse.album_list("* ''Demo Tape''"), [['Demo Tape', 0]])
		self.assertEqual(parse.album_list('{{Main|Some discography}}'), [])


if __name__ == '__main__':
	unittest.main()
