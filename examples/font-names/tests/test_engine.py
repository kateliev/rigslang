"""Tests of the naming engine (pure Python). No files, no model."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import engine  # noqa: E402

FAMILY = [{'family': 'SpecimenGrotesque', 'name': 'ExtraBoldCondensedItalic', 'italic': True}, {'family': 'SpecimenGrotesque', 'name': 'Regular'}]


def shorts(standard, **settings):
	settings['standard'] = standard
	return [(r['short'], r['steps']) for r in engine.build_rows(FAMILY, settings)]


class Words(unittest.TestCase):
	def test_split_words(self):
		self.assertEqual(engine.split_words('SemiBold Italic'), [['Semi', ''], ['Bold', ' '], ['Italic', '']])
		self.assertEqual(engine.split_words('ABCFont2'), [['ABC', ''], ['Font', ''], ['2', '']])

	def test_to_ascii(self):
		self.assertEqual(engine.to_ascii('Каранд Ça ß'), 'Karand Ca ss')


class Standards(unittest.TestCase):
	def test_long_limit_changes_nothing(self):
		self.assertEqual(shorts('sp_server'), [('SpecimenGrotesque-ExtraBoldCondensedItalic', []), ('SpecimenGrotesque-Regular', [])])

	def test_hfs_needs_only_the_style_table(self):
		self.assertEqual(shorts('hfs'), [('SpecimenGrotesque-XBdCnIt', ['abbr_style']), ('SpecimenGrotesque-Rg', ['abbr_style'])])

	def test_iso_is_upper_case_with_underscores(self):
		self.assertEqual(shorts('iso2')[1], ('SPECIMENGROTESQUE_RG', ['abbr_style']))

	def test_dos83_cuts_with_a_tilde(self):
		self.assertEqual(shorts('dos83')[0][0], 'SGXBDC~1')
		self.assertEqual(shorts('dos83')[0][1][-2:], ['initials', 'cut'])

	def test_mac533_is_the_method_of_its_standard(self):
		self.assertEqual(shorts('mac533'), [('SpeciGroExtBolConIta', ['m533']), ('SpeciGroReg', ['m533'])])

	def test_sharepoint_counts_the_decoded_folder(self):
		std = engine.standard('sp_server')
		self.assertEqual(engine.base_budget(std, {'folder': 'https://x.sharepoint.com/sites/a%20b/Fonts/', 'suffix': '.otf'}), 124)

	def test_issues(self):
		self.assertEqual(engine.issues('AUX', engine.standard('fs255'), {'suffix': '.otf'}), ['reserved'])
		self.assertEqual(engine.issues('a:b', engine.standard('hfs'), {'suffix': '.otf'}), ['bad chars'])

	def test_duplicates_get_a_number(self):
		rows = engine.build_rows([{'family': 'Sans', 'name': 'Bold'}, {'family': 'Sans', 'name': 'Bold'}], {'standard': 'hfs'})
		self.assertEqual([r['short'] for r in rows], ['Sans-Bold', 'Sans-Bold2'])
		rows = engine.build_rows([{'family': 'Sans', 'name': 'Bold'}, {'family': 'Sans', 'name': 'Bold'}], {'standard': 'hfs', 'unique': False})
		self.assertEqual(rows[0]['issues'], ['duplicate'])


class Abbreviations(unittest.TestCase):
	DISPLAY = [{'family': 'SpecimenGrotesqueDisplay', 'name': n} for n in ('Regular', 'ExtraBoldCondensedItalic')]
	S = {'standard': 'hfs', 'suffix': '.woff2'}

	def test_weak_words(self):
		rows = engine.build_rows(self.DISPLAY, self.S)
		self.assertTrue(all(engine.is_weak(r) for r in rows))
		self.assertEqual(engine.weak_words(self.DISPLAY, rows, 5), ['Specimen', 'Grotesque'])

	def test_a_fair_table(self):
		s = engine.score(self.DISPLAY, self.S, {'Specimen': 'Spc', 'Grotesque': 'Grt'}, (2, 4))
		self.assertTrue(s['fair'], s['problems'])
		self.assertEqual([r['short'] for r in s['rows']], ['SpcGrtDs-Rg', 'SpcGrtDs-XBdCnIt'])

	def test_unfair_tables(self):
		cases = {
			'Spz': 'not the letters of the word in their order',
			'Pcm': 'does not start with the first letter',
			'S': 'not 2 to 4 letters',
			'Sp-c': 'only letters and digits',
		}
		for abbr, why in cases.items():
			s = engine.score(self.DISPLAY, self.S, {'Specimen': abbr, 'Grotesque': 'Grt'}, (2, 4))
			self.assertFalse(s['fair'], abbr)
			self.assertTrue(any(why in p for p in s['problems']), (abbr, s['problems']))
		s = engine.score(self.DISPLAY, self.S, {'Specimen': 'Spc', 'Kursiv': 'Spc'}, (2, 4))
		self.assertTrue(any('not a word of the family' in p for p in s['problems']))
		s = engine.score(self.DISPLAY, self.S, {'Display': 'Dspl'}, (2, 4))
		self.assertTrue(any('still need' in p for p in s['problems']))
		self.assertFalse(engine.score(self.DISPLAY, self.S, ['Spc'], (2, 4))['fair'])

	def test_best_keeps_more_letters(self):
		scores = [engine.score(self.DISPLAY, self.S, t, (2, 4)) for t in ({'Specimen': 'Sp', 'Grotesque': 'Gr'}, {'Specimen': 'Spc', 'Grotesque': 'Grt'}, {'Specimen': 'S'})]
		self.assertEqual(engine.best(scores), 1)
		self.assertIsNone(engine.best(scores[2:]))


if __name__ == '__main__':
	unittest.main()
