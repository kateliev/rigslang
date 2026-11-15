"""Pure helpers of band-facts: they read text and give data. No network."""
import re
from urllib.parse import unquote, urlparse


def wiki_title(url):
	'''The article title of an English Wikipedia URL (desktop or mobile), else an empty text.'''
	try:
		u = urlparse(url)
	except ValueError:
		return ''
	if not re.match(r'^en\.(m\.)?wikipedia\.org$', u.hostname or '') or not u.path.startswith('/wiki/'):
		return ''
	return unquote(u.path[len('/wiki/'):])


def search_titles(data, limit):
	'''The answer of the Wikipedia search API (action=query, list=search) -> the titles, at most limit.'''
	hits = ((data or {}).get('query') or {}).get('search') or []
	return [h['title'] for h in hits if h.get('title')][:limit]


def pick_title(band, titles):
	'''The title that is the article of the band: the name itself, else "name (band)", else the first.
	A full-text search puts lists and member pages first for a famous band; the name itself is the article.'''
	name = band.strip().lower()
	for want in (name, name + ' (band)'):
		for t in titles:
			if t.lower() == want:
				return t
	return titles[0] if titles else None


def same_name(band, title):
	'''Is the title the name of the band? "Name", or "Name (band)" and the like; case and "The" do not count.'''
	def norm(s):
		s = re.sub(r'\s*\([^)]*\)\s*$', '', s.strip().lower())
		return re.sub(r'^the\s+', '', s)
	return bool(norm(band)) and norm(band) == norm(title)


def album_list(wikitext):
	'''The albums of the wikitext of a Discography section -> [[title, year]]; the year is 0 when
	the line has none. Many large bands keep only a link to another article here: then the list is empty.'''
	out = []
	for line in wikitext.split('\n'):
		if not line.startswith('*'):
			continue
		m = re.search(r"''(.+?)''", line)
		if not m:
			continue
		title = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', m.group(1)).strip()
		year = re.search(r'\b(\d{4})\b', line[m.end():])
		out.append([title, int(year.group(1)) if year else 0])
	return out
