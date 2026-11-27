"""The naming engine of font-names: pure Python, standard library only. No files, no network.

A pattern ("{fam}-{style}") expands to segments. A segment has a kind ('family', 'style' or 'lit')
and a list of [word, gap] pairs, so that shortening works word by word: style words first, then
family words. Literal text of the pattern is never shortened; only the 'tight' step drops it.

The steps of a method run in order until the name fits the standard; 'cut' (truncate) is the
last resort. The table of abbreviations follows Adobe Tech Note 5088 (font naming), extended
with common words. A run can add words to it (extra): that is the job of the model.

Entry points: build_rows(), weak_words(), score(), best().
"""
import copy
import re
import unicodedata
from urllib.parse import unquote, urlsplit

# - Standards -------------------------------------------------------------
# name_max: whole file name with the suffix; path_max: folder + '/' + name;
# base_max / ext_max: 8.3 limits; chars: 'any' | 'dos' | 'iso'.

INVALID_ANY = set('"*:<>?/\\|') | set(chr(c) for c in range(32)) | {'\x7f'}
INVALID_SHAREPOINT = INVALID_ANY | set('#%')		# # and % are off in some tenants
INVALID_HFS = set(':') | set(chr(c) for c in range(32))

RESERVED_WINDOWS = set(['CON', 'PRN', 'AUX', 'NUL'] + ['COM%d' % i for i in range(10)] + ['LPT%d' % i for i in range(10)])
RESERVED_SHAREPOINT = RESERVED_WINDOWS | {'.LOCK', 'DESKTOP.INI'}


class Standard(object):
	def __init__(self, key, title, name_max=None, path_max=None, base_max=None, ext_max=None, chars='any',
			invalid=INVALID_ANY, reserved=RESERVED_WINDOWS, case=None, tilde=False, method='auto', note=''):
		self.key, self.title, self.note, self.method = key, title, note, method
		self.name_max, self.path_max, self.base_max, self.ext_max = name_max, path_max, base_max, ext_max
		self.chars, self.invalid, self.reserved, self.case, self.tilde = chars, invalid, reserved, case, tilde


STANDARDS = (
	Standard('none', 'No limit (patterns only)', name_max=255),
	Standard('sp_online', 'SharePoint Online / OneDrive (path 400)', name_max=255, path_max=400,
		invalid=INVALID_SHAREPOINT, reserved=RESERVED_SHAREPOINT,
		note='decoded path after the site URL, file name included, at most 400; each name at most 255'),
	Standard('sp_server', 'SharePoint Server 2013/2016 (name 128, URL 260)', name_max=128, path_max=260,
		invalid=INVALID_SHAREPOINT, reserved=RESERVED_SHAREPOINT),
	Standard('win_path', 'Windows MAX_PATH (path 260)', name_max=255, path_max=259),
	Standard('fs255', 'Windows / macOS / Linux name (255)', name_max=255),
	Standard('joliet', 'CD-ROM Joliet (64)', name_max=64),
	Standard('hfs', 'Mac OS classic HFS (31)', name_max=31, invalid=INVALID_HFS, reserved=set()),
	Standard('iso2', 'ISO 9660 Level 2 (31)', name_max=31, chars='iso', case='upper'),
	Standard('dos83', 'DOS / ISO 9660 Level 1 (8.3)', base_max=8, ext_max=3, chars='dos', case='upper', tilde=True),
	Standard('mac533', 'Mac Type 1 printer font (5:3:3)', name_max=31, invalid=INVALID_HFS, reserved=set(), method='m533'),
)


def standard(key):
	for s in STANDARDS:
		if s.key == key:
			return s
	raise ValueError('unknown standard {!r}'.format(key))


# - Methods ---------------------------------------------------------------

STEP_TITLES = {
	'abbr_style': 'style abbreviated', 'abbr_family': 'family abbreviated',
	'vow_style': 'style vowels dropped', 'vow_family': 'family vowels dropped',
	'tight': 'separators dropped', 'initials': 'family initials', 'm533': '5:3:3',
	'cut': 'cut', 'renamed': 'renamed (duplicate)',
}

# Steps that make a name a person cannot read: the words are no longer the words of the family.
WEAK_STEPS = ('vow_style', 'vow_family', 'initials', 'cut')

METHODS = {
	'auto': ('abbr_style', 'abbr_family', 'vow_style', 'vow_family', 'tight', 'initials'),
	'abbr': ('abbr_style', 'abbr_family'),
	'vowels': ('vow_style', 'vow_family'),
	'm533': ('m533',),
	'cut': (),
}

ABBREVIATIONS = {
	'black': 'Blk', 'bold': 'Bd', 'book': 'Bk', 'caption': 'Cap', 'compressed': 'Cm',
	'condensed': 'Cn', 'demi': 'Dm', 'display': 'Ds', 'expanded': 'Exp', 'extended': 'Ex',
	'extra': 'X', 'fat': 'Ft', 'hairline': 'Hl', 'headline': 'Hd', 'heavy': 'Hv',
	'inclined': 'Ic', 'italic': 'It', 'kursiv': 'Ks', 'light': 'Lt', 'medium': 'Md',
	'micro': 'Mc', 'mono': 'Mn', 'narrow': 'Nr', 'nord': 'Nd', 'normal': 'Nm',
	'oblique': 'Obl', 'poster': 'Po', 'regular': 'Rg', 'roman': 'Rm', 'semi': 'Sm',
	'slanted': 'Sl', 'standard': 'Std', 'super': 'Su', 'text': 'Tx', 'thin': 'Th',
	'ultra': 'Ult', 'upright': 'Up', 'variable': 'VF', 'wide': 'Wd',
}

VOWELS = set('aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿ')
SUFFIXES = ('.otf', '.ttf', '.woff', '.woff2')

DEFAULTS = {
	'standard': 'sp_server', 'folder': '', 'suffix': '.otf', 'method': 'auto', 'always': False,
	'consistent': True, 'unique': True, 'spaces': 'remove', 'ascii': True, 'case': 'keep',
	'short_pattern': '{fam}-{style}', 'var_short_pattern': '{fam}{style}VF',
}

# - Transliteration -------------------------------------------------------

_CYRILLIC = {	# Bulgarian streamlined system, extended for Russian, Ukrainian, Serbian, Macedonian
	'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i',
	'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's',
	'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sht',
	'ъ': 'a', 'ь': 'y', 'ю': 'yu', 'я': 'ya', 'ё': 'yo', 'ы': 'y', 'э': 'e', 'і': 'i',
	'ї': 'yi', 'є': 'ye', 'ґ': 'g', 'ђ': 'dj', 'ј': 'j', 'љ': 'lj', 'њ': 'nj', 'ћ': 'c',
	'џ': 'dz', 'ѓ': 'gj', 'ќ': 'kj', 'ѕ': 'dz',
}
_LATIN = {'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'ø': 'o', 'ł': 'l', 'đ': 'd', 'ð': 'd', 'þ': 'th', 'ı': 'i'}


def to_ascii(text):
	'''Transliterate Cyrillic, fold accents; drop what is left outside ASCII.'''
	out = []
	for ch in text:
		low = ch.lower()
		rep = _CYRILLIC.get(low) or _LATIN.get(low)
		if rep is not None:
			if ch != low:
				rep = rep.upper() if len(rep) == 1 else rep[0].upper() + rep[1:]
			out.append(rep)
		else:
			out.append(ch)
	text = unicodedata.normalize('NFKD', ''.join(out))
	return ''.join(ch for ch in text if ord(ch) < 128 and not unicodedata.combining(ch))


# - Words and segments ----------------------------------------------------

def split_words(text):
	'''"SemiBold Italic" -> [['Semi', ''], ['Bold', ' '], ['Italic', '']]. Splits at spaces, - _ .
	and at camelCase and letter-digit changes; the gap after a word keeps what separated it.'''
	words, cur = [], ''
	for i, ch in enumerate(text):
		if ch in ' -_.':
			if cur:
				words.append([cur, ch])
				cur = ''
			elif words:
				words[-1][1] += ch
			continue
		if cur:
			prev, nxt = cur[-1], (text[i + 1] if i + 1 < len(text) else '')
			if (prev.islower() and ch.isupper()) or (prev.isdigit() != ch.isdigit()) \
					or (prev.isupper() and ch.isupper() and nxt.islower()):		# 'ABCFont' -> ABC + Font
				words.append([cur, ''])
				cur = ''
		cur += ch
	if cur:
		words.append([cur, ''])
	return words


class Segment(object):
	def __init__(self, kind, text):
		self.kind, self.text = kind, text		# kind: 'family' | 'style' | 'lit'
		self.words = split_words(text) if kind != 'lit' else None


TOKEN_RE = re.compile(r'\{(\w+)\}')
ELIDED_VARIABLE_STYLES = ('regular', 'variable', 'roman', 'upright', 'normal')


def token_values(inst, index):
	style = inst.get('name', '') or ''
	if inst.get('variable') and style.strip().lower() in ELIDED_VARIABLE_STYLES:
		style = ''
	family = inst.get('family') or ''
	return {
		'family': ('family', family), 'fam': ('family', family), 'style': ('style', style),
		'italic': ('style', 'Italic' if inst.get('italic') else ''),
		'index': ('lit', '%02d' % (index + 1)), 'vf': ('lit', 'VF' if inst.get('variable') else ''),
	}


def expand(pattern, values):
	'''Pattern -> (segments, unknown tokens).'''
	segs, unknown, pos = [], [], 0
	for m in TOKEN_RE.finditer(pattern):
		if m.start() > pos:
			segs.append(Segment('lit', pattern[pos:m.start()]))
		name = m.group(1)
		if name in values:
			kind, text = values[name]
			if text:
				segs.append(Segment(kind, text))
		else:
			unknown.append(name)
			segs.append(Segment('lit', m.group(0)))
		pos = m.end()
	if pos < len(pattern):
		segs.append(Segment('lit', pattern[pos:]))
	return segs, unknown


# - Steps -----------------------------------------------------------------

def _match_case(src, abbr):
	if src.islower():
		return abbr.lower()
	if src.isupper() and len(src) > 1:
		return abbr.upper()
	return abbr


def _abbreviate(segs, kind, table):
	for seg in segs:
		if seg.kind == kind:
			for w in seg.words:
				abbr = table.get(w[0].lower())
				if abbr is not None:
					w[0] = _match_case(w[0], abbr)


def _drop_vowels(segs, kind):
	for seg in segs:
		if seg.kind == kind:
			for w in seg.words:
				if len(w[0]) > 2 and not w[0].isupper():
					w[0] = w[0][0] + ''.join(c for c in w[0][1:] if c not in VOWELS)


def _m533(segs):
	first = True
	for seg in segs:
		if seg.kind == 'lit':
			if not seg.text.strip(' -_.'):
				seg.text = ''		# 5:3:3 drops separators
			continue
		for w in seg.words:
			if not w[0].isdigit():
				w[0] = w[0][:5] if first else w[0][:3]
			first = False
			w[1] = ''


def _tight(segs):
	for seg in segs:
		if seg.kind == 'lit':
			seg.text = ''.join(c for c in seg.text if c not in ' -_.')
		else:
			for w in seg.words:
				w[1] = ''


def _initials(segs):
	for seg in segs:
		if seg.kind == 'family':
			seg.words = [[w[0] if w[0].isdigit() else w[0][:1].upper(), ''] for w in seg.words]


def apply_step(segs, step, table):
	if step == 'abbr_style':
		_abbreviate(segs, 'style', table)
	elif step == 'abbr_family':
		_abbreviate(segs, 'family', table)
	elif step == 'vow_style':
		_drop_vowels(segs, 'style')
	elif step == 'vow_family':
		_drop_vowels(segs, 'family')
	elif step == 'm533':
		_m533(segs)
	elif step == 'tight':
		_tight(segs)
	elif step == 'initials':
		_initials(segs)


# - Rendering and clean-up ------------------------------------------------

SPACE_CHAR = {'remove': '', 'underscore': '_', 'hyphen': '-', 'keep': ' '}


def render(segs, settings):
	space = SPACE_CHAR.get(settings.get('spaces', 'remove'), '')
	out = []
	for seg in segs:
		if seg.kind == 'lit':
			out.append(seg.text.replace(' ', space))
		else:
			for word, gap in seg.words:
				out.append(word + gap.replace(' ', space))
	return ''.join(out)


def clean(name, std, settings):
	'''The character rules of the standard and the options; never shortens.'''
	if settings.get('ascii', True) or std.chars != 'any':
		name = to_ascii(name)
	case = std.case or settings.get('case', 'keep')
	if case == 'lower':
		name = name.lower()
	elif case == 'upper':
		name = name.upper()
	if std.chars == 'iso':
		name = ''.join(c if (c.isalnum() or c == '_') else ('_' if c in ' -.' else '') for c in name)
	elif std.chars == 'dos':
		name = ''.join(c for c in name if c.isalnum() or c in "_-!#$%&'()@^`{}~")
	name = ''.join(c for c in name if c not in std.invalid)
	name = re.sub(r'([ _\-])\1+', r'\1', name)		# no doubled separators
	return name.strip(' .-_')


# - Budget ----------------------------------------------------------------

def folder_length(folder):
	'''The length of the destination folder as the standard counts it: a URL is decoded and loses
	its scheme and host; a last separator does not count.'''
	folder = (folder or '').strip()
	if not folder:
		return 0
	if re.match(r'^[a-z]+://', folder, re.I):
		folder = urlsplit(folder).path
	return len(unquote(folder).strip('/\\'))


def name_budget(std, settings):
	'''The longest base name + suffix, or None for no limit.'''
	limits = []
	if std.name_max:
		limits.append(std.name_max)
	if std.path_max:
		flen = folder_length(settings.get('folder', ''))
		limits.append(std.path_max - flen - (1 if flen else 0))
	return min(limits) if limits else None


def base_budget(std, settings):
	'''The longest base name alone (the suffix taken off).'''
	if std.base_max:
		return std.base_max
	budget = name_budget(std, settings)
	if budget is None:
		return None
	return max(1, budget - len(settings.get('suffix', '.otf')))


# - Checks ----------------------------------------------------------------

def issues(base, std, settings):
	'''The problems of a finished base name under the standard (a list of words).'''
	found = []
	suffix = settings.get('suffix', '.otf')
	limit = base_budget(std, settings)
	if not base:
		found.append('empty')
	if limit is not None and len(base) > limit:
		found.append('too long')
	if std.ext_max and len(suffix) - 1 > std.ext_max:
		found.append('suffix > %d' % std.ext_max)
	if any(c in std.invalid for c in base):
		found.append('bad chars')
	if std.chars == 'iso' and not re.match(r'^[A-Z0-9_]*$', base):
		found.append('not ISO')
	if base.upper() in std.reserved or (base + suffix).upper() in std.reserved:
		found.append('reserved')
	if std.invalid is INVALID_SHAREPOINT and ('_vti_' in base.lower() or base.startswith('~$')):
		found.append('reserved')
	if base != base.strip() or base.endswith('.'):
		found.append('edge space/dot')
	return found


# - Build -----------------------------------------------------------------

def _cut(base, limit, std):
	if limit is None or len(base) <= limit:
		return base, False
	if std.tilde:
		return base[:max(1, limit - 2)].rstrip(' .-_') + '~1', True
	return base[:limit].rstrip(' .-_'), True


def _short_at(segs, steps, level, table, std, settings):
	work = copy.deepcopy(segs)
	for step in steps[:level]:
		apply_step(work, step, table)
	return clean(render(work, settings), std, settings)


def table_with(extra):
	'''The built-in table and the words of a run (extra: {word: abbreviation}).'''
	table = dict(ABBREVIATIONS)
	table.update(dict((str(k).lower(), str(v)) for k, v in (extra or {}).items()))
	return table


def build_rows(instances, settings, extra=None):
	'''instances: [{name, family, italic, variable}]; settings: see DEFAULTS; extra: words to add to the
	table. -> one row for each instance: {index, name, short, steps, length, limit, issues}.'''
	s = dict(DEFAULTS)
	s.update(settings or {})
	std = standard(s['standard'])
	method = std.method if s['method'] == 'auto' else s['method']		# auto: the method of the standard
	steps = METHODS[method]
	table = table_with(extra)
	limit = base_budget(std, s)
	always = s['always'] or method == 'm533'		# 5:3:3 is a naming rule, not a fallback

	prepared = []
	for i, inst in enumerate(instances):
		pattern = s['var_short_pattern'] if inst.get('variable') else s['short_pattern']
		segs, unknown = expand(pattern, token_values(inst, i))
		need = len(steps) if always else 0
		if not always:
			while need < len(steps) and limit is not None and len(_short_at(segs, steps, need, table, std, s)) > limit:
				need += 1
		prepared.append((inst, segs, need, unknown))
	level_all = max([p[2] for p in prepared] or [0]) if s['consistent'] else None

	rows = []
	for i, (inst, segs, need, unknown) in enumerate(prepared):
		level = need if level_all is None else level_all
		base, was_cut = _cut(_short_at(segs, steps, level, table, std, s), limit, std)
		used = list(steps[:level]) + (['cut'] if was_cut else [])
		rows.append({'index': i, 'name': inst.get('name', ''), 'short': base, 'steps': used, 'unknown': unknown})

	if s['unique']:		# file systems compare names without case
		seen = set()
		for row in rows:
			if row['short'].lower() in seen:
				stem = re.sub(r'~\d+$', '', row['short']) if std.tilde else row['short']
				n = 2
				while True:
					tag = ('~%d' % n) if std.tilde else str(n)
					cand = (stem if limit is None else stem[:max(1, limit - len(tag))]) + tag
					if cand.lower() not in seen:
						break
					n += 1
				row['short'] = cand
				row['steps'].append('renamed')
			seen.add(row['short'].lower())

	counts = {}
	for row in rows:
		counts[row['short'].lower()] = counts.get(row['short'].lower(), 0) + 1
	for row in rows:
		found = issues(row['short'], std, s)
		if row.pop('unknown'):
			found.append('unknown token')
		if counts[row['short'].lower()] > 1:
			found.append('duplicate')
		row['issues'] = found
		row['length'] = len(row['short']) if std.base_max else len(row['short']) + len(s['suffix'])
		row['limit'] = limit if (std.base_max or limit is None) else limit + len(s['suffix'])
	return rows


def settings_of(R, suffix):
	'''The engine settings from the rules of a run, and the longest suffix of the font files.'''
	return {'standard': R('target.standard'), 'folder': R('target.folder'), 'method': R('shorten.method'),
		'consistent': R('shorten.consistent'), 'suffix': suffix}


# - The words that the model may help with --------------------------------

def is_weak(row):
	return any(st in WEAK_STEPS for st in row['steps'])


def weak_words(instances, rows, min_letters):
	'''The words of the weak rows that the table does not know, in the order they first come.
	A word shorter than min_letters is left alone: it is short already.'''
	out = []
	for inst, row in zip(instances, rows):
		if not is_weak(row):
			continue
		for text in (inst.get('family') or '', inst.get('name') or ''):
			for word, _ in split_words(text):
				if len(word) >= min_letters and not word.isdigit() and word.lower() not in ABBREVIATIONS and word not in out:
					out.append(word)
	return out


def family_words(instances):
	words = set()
	for inst in instances:
		for text in (inst.get('family') or '', inst.get('name') or ''):
			words.update(w.lower() for w, _ in split_words(text))
	return words


def _in_order(short, word):
	'''True when the letters of short come in word in the same order.'''
	it = iter(word)
	return all(c in it for c in short)


def score(instances, settings, extra, letters):
	'''How fair one table of abbreviations is. -> {fair, problems, weak, steps, letters, rows}.
	Fair: every abbreviation is a word of the family, starts with its first letter, keeps the order
	of its letters, is shorter than the word and has letters[0] to letters[1] letters; no two words share
	an abbreviation; and with the table no name needs a weak step (vowels dropped, initials, cut).'''
	problems = []
	if not isinstance(extra, dict) or not extra:
		return {'fair': False, 'problems': ['the answer is not a table of abbreviations'], 'weak': None, 'steps': None, 'letters': None, 'rows': []}
	known = family_words(instances)
	seen = {}
	for word, abbr in extra.items():
		word, abbr = str(word), str(abbr)
		w, a = word.lower(), abbr.lower()
		if w not in known:
			problems.append('{!r} is not a word of the family'.format(word))
		if not abbr.isalnum():
			problems.append('{!r} -> {!r}: only letters and digits'.format(word, abbr))
		elif not a or a[0] != w[:1]:
			problems.append('{!r} -> {!r}: does not start with the first letter of the word'.format(word, abbr))
		elif not _in_order(a, w):
			problems.append('{!r} -> {!r}: not the letters of the word in their order'.format(word, abbr))
		if len(abbr) >= len(word):
			problems.append('{!r} -> {!r}: not shorter than the word'.format(word, abbr))
		if not letters[0] <= len(abbr) <= letters[1]:
			problems.append('{!r} -> {!r}: not {} to {} letters'.format(word, abbr, letters[0], letters[1]))
		if a in seen and seen[a] != w:
			problems.append('{!r} and {!r} share the abbreviation {!r}'.format(seen[a], word, abbr))
		seen[a] = w
	rows = build_rows(instances, settings, extra)
	weak = [r['short'] for r in rows if is_weak(r)]
	if weak:
		problems.append('{} names still need vowels dropped, initials or a cut: {}'.format(len(weak), ', '.join(weak[:3])))
	return {'fair': not problems, 'problems': problems, 'weak': len(weak),
		'steps': sum(len(r['steps']) for r in rows), 'letters': sum(len(r['short']) for r in rows), 'rows': rows}


def best(scores):
	'''The index of the best fair table: fewest shortening steps, then the most letters kept
	(more letters read better), then the first. None when no table is fair.'''
	fair = [(s['steps'], -s['letters'], i) for i, s in enumerate(scores) if s['fair']]
	return min(fair)[2] if fair else None
