"""The bookmarks file and the plan: pure functions, no files and no network. Standard library only.

    parse(text)                     a Netscape bookmarks file (the HTML export of Edge) -> a collection
    key(url, R)                     the normal form of a URL, for exact duplicates
    duplicates(c, R)                which copies to remove; one copy of each URL stays
    similar(c, removed, R)          groups of URLs on one site, where one path starts with another
    choices(note, page, yes)        the answer of the person for one page of groups -> decisions
    fits(c, removed, R)             the bookmarks that code leaves in their folder; the rest is sorted
    sort_problems(answer, batch, known, made, R)   what is wrong with an answer of the model
    render(c, plan, R)              the new bookmarks file as text

A collection is a dict:
    {"head": text before the first <DL>, "folders": [folder], "bookmarks": [bookmark]}
    folder:   {"id": int, "name", "parent": int or None, "attrs": text, "path": [names], "bar": bool}
    bookmark: {"id": int, "title", "url", "folder": int or None, "attrs": text, "add_date": int, "dd": text or None}
Folder None is the top level of the file. A title is kept as it was written (HTML text), so it never changes.
"""
import html
import re
import urllib.parse

SEP = ' > '

TOKEN = re.compile(
	r'<DT>\s*<H3(?P<fattrs>[^>]*)>(?P<fname>.*?)</H3>'
	r'|<DT>\s*<A(?P<attrs>[^>]*)>(?P<title>.*?)</A>'
	r'|<DD>(?P<dd>[^<]*)'
	r'|(?P<open><DL>)|(?P<close></DL>)', re.I | re.S)
ATTR = re.compile(r'([A-Za-z_][\w-]*)\s*=\s*"([^"]*)"')


def attr(attrs, name):
	for k, v in ATTR.findall(attrs or ''):
		if k.upper() == name.upper():
			return html.unescape(v)
	return None


def without(attrs, name):
	'''The attribute text without one attribute (to write it again with a new value).'''
	return re.sub(r'\s+{}\s*=\s*"[^"]*"'.format(re.escape(name)), '', attrs or '', flags=re.I)


# - Read ----------------------------------------------
def parse(text):
	'''-> a collection. Raises ValueError when the text is not a Netscape bookmarks file.'''
	if not re.search(r'<!DOCTYPE\s+NETSCAPE-Bookmark-file', text[:2000], re.I) and not re.search(r'<DL>', text[:5000], re.I):
		if text.lstrip().startswith('{'):
			raise ValueError('this is a JSON file: it may be the live Bookmarks file of the browser. Export the bookmarks as HTML instead')
		raise ValueError('this is not a bookmarks file in the Netscape HTML form (no <DL> list)')
	first = re.search(r'<DL>', text, re.I)
	if first is None:
		raise ValueError('the file has no <DL> list')
	c = {'head': text[:first.start()], 'folders': [], 'bookmarks': [], 'order_keys': []}
	stack, pending, last = [], None, None
	for m in TOKEN.finditer(text, first.start()):
		if m.group('open'):
			stack.append(pending)
			pending = None
		elif m.group('close'):
			if stack:
				stack.pop()
			last = None
		elif m.group('fname') is not None:
			parent = stack[-1] if stack else None
			f = {'id': len(c['folders']), 'name': m.group('fname'), 'parent': parent, 'attrs': m.group('fattrs')}
			f['path'] = (c['folders'][parent]['path'] if parent is not None else []) + [html.unescape(f['name'])]
			f['bar'] = (attr(f['attrs'], 'PERSONAL_TOOLBAR_FOLDER') or '').lower() == 'true'
			c['folders'].append(f)
			c['order_keys'].append(('f', f['id']))
			pending, last = f['id'], None
		elif m.group('attrs') is not None:
			b = {'id': len(c['bookmarks']), 'title': m.group('title'), 'url': attr(m.group('attrs'), 'HREF') or '',
				'folder': stack[-1] if stack else None, 'attrs': m.group('attrs'), 'dd': None}
			try:
				b['add_date'] = int(attr(b['attrs'], 'ADD_DATE') or 0)
			except ValueError:
				b['add_date'] = 0
			c['bookmarks'].append(b)
			c['order_keys'].append(('b', b['id']))
			last = b
		elif m.group('dd') is not None and last is not None:
			last['dd'] = m.group('dd').rstrip()
	if not c['folders'] and not c['bookmarks']:
		raise ValueError('the file has no folders and no bookmarks')
	return c


def path_of(c, folder):
	return SEP.join(c['folders'][folder]['path']) if folder is not None else ''


def depth(c, folder):
	return len(c['folders'][folder]['path']) if folder is not None else 0


def on_bar(c, b):
	'''The bookmark is directly on the favorites bar.'''
	return b['folder'] is not None and c['folders'][b['folder']]['bar']


def plain_title(b):
	return html.unescape(b['title'])


# - Normal form of a URL --------------------------------
def tracking(name, R):
	name = name.lower()
	return any(name.startswith(t) if t.endswith('_') else name == t for t in R('dupes.tracking'))


def parts(url, R):
	'''-> (host, path segments, query, fragment) of an http(s) URL, in normal form; None for any other URL.'''
	try:
		u = urllib.parse.urlsplit(url.strip())
	except ValueError:
		return None
	if u.scheme.lower() not in ('http', 'https') or not u.hostname:
		return None
	host = u.hostname.lower()
	if host.startswith('www.'):
		host = host[4:]
	try:
		port = u.port
	except ValueError:
		port = None
	if port and port not in (80, 443):
		host += ':{}'.format(port)
	segs = [s for s in u.path.split('/') if s]
	query = '&'.join(sorted(q for q in u.query.split('&') if q and not tracking(q.split('=', 1)[0], R)))
	frag = u.fragment if u.fragment[:1] in ('/', '!') else ''  # "#/page" and "#!page" are pages of one-page sites: keep them
	return host, segs, query, frag


def key(url, R):
	'''The normal form: no scheme, no "www.", no last "/", no tracking parameters, no "#part".'''
	p = parts(url, R)
	if p is None:
		return url.strip()
	host, segs, query, frag = p
	return host + ('/' + '/'.join(segs) if segs else '') + ('?' + query if query else '') + ('#' + frag if frag else '')


# - Exact duplicates ------------------------------------
def protected(c, b, R):
	return R('keep.bar') and on_bar(c, b)


def duplicates(c, R):
	'''-> [{"removed", "kept", "key"}]. One copy of each URL stays: the copy in the deeper folder,
	else the oldest, else the first. A copy on the favorites bar always stays (rule keep.bar).'''
	by_key = {}
	for b in c['bookmarks']:
		by_key.setdefault(key(b['url'], R), []).append(b)
	out = []
	for k, group in by_key.items():
		if len(group) < 2:
			continue
		free = [b for b in group if not protected(c, b, R)]
		if not free:
			continue
		keep = sorted(free, key=lambda b: (-depth(c, b['folder']), b['add_date'] or float('inf'), b['id']))[0]
		for b in free:  # a copy on the bar is not in "free": it stays, and so does the best other copy
			if b is not keep:
				out.append({'removed': b['id'], 'kept': keep['id'], 'key': k})
	return sorted(out, key=lambda d: d['removed'])


# - Similar URLs ----------------------------------------
def skipped_host(host, R):
	host = host.split(':')[0]
	if any(host == h or host.endswith('.' + h) for h in R('similar.skip_hosts')):
		return True
	return bool(re.search(R('similar.skip_pattern'), host))


def similar(c, removed, R):
	'''Groups of bookmarks on one site where one path starts with another.
	-> {"folded": [{"removed", "kept", "why"}], "groups": [{"n", "host", "ids", "default"}], "too_big": [{"host", "size"}]}
	"folded": variants such as /index.html that code folds without a question.
	A group has 2 or more ids, shortest URL first; "default" is the id of the shortest.'''
	items = {}
	for b in c['bookmarks']:
		if b['id'] in removed or protected(c, b, R):
			continue
		p = parts(b['url'], R)
		if p is None or skipped_host(p[0], R):
			continue
		items.setdefault(p[0], []).append((b, p))
	index = set(n.lower() for n in R('similar.index_names'))
	folded, groups, too_big = [], [], []
	for host in sorted(items):
		rows = items[host]
		bare = {}  # path -> the bookmark of that path with no query and no "#part"
		for b, (_, segs, q, f) in rows:
			if not q and not f:
				bare.setdefault(tuple(segs), b)
		live = []
		for b, (h, segs, q, f) in rows:
			if segs and segs[-1].lower() in index and not q and not f and tuple(segs[:-1]) in bare:
				folded.append({'removed': b['id'], 'kept': bare[tuple(segs[:-1])]['id'], 'why': '/' + segs[-1]})
			else:
				live.append((b, segs, q, f))
		parent = dict((b['id'], b['id']) for b, *_ in live)

		def root(i):
			while parent[i] != i:
				parent[i] = parent[parent[i]]
				i = parent[i]
			return i
		heads = dict((tuple(segs), b['id']) for b, segs, q, f in live if not q and not f)
		for b, segs, q, f in live:
			for n in range(len(segs) + (1 if (q or f) else 0)):  # each shorter path; the same path too, when this one has a query
				h = heads.get(tuple(segs[:n]))
				if h is not None and h != b['id']:
					parent[root(b['id'])] = root(h)
		comps = {}
		for b, segs, q, f in live:
			comps.setdefault(root(b['id']), []).append(b)
		for members in comps.values():
			if len(members) < 2:
				continue
			if len(members) > R('similar.max_group'):
				too_big.append({'host': host, 'size': len(members)})
				continue
			members.sort(key=lambda b: (len(key(b['url'], R)), b['add_date'] or float('inf'), b['id']))
			groups.append({'host': host, 'ids': [b['id'] for b in members], 'default': members[0]['id']})
	for i, g in enumerate(groups):
		g['n'] = i + 1
	return {'folded': sorted(folded, key=lambda d: d['removed']), 'groups': groups, 'too_big': too_big}


def pages(groups, size):
	return [[g['n'] for g in groups[i:i + size]] for i in range(0, len(groups), size)]


CHOICE = re.compile(r'^(\d+)=(all|short|\d+)$')


def choices(note, page_groups, yes):
	'''The answer of the person for one page. yes: True for "approve yes", False for "no".
	Note words: G=all (keep every URL of group G), G=short (keep the shortest), G=K (keep URL K of group G),
	rest (the default for this page and every later page). -> (decisions, rest, problems)
	decisions: {group n: "all" | "short" | K}; every group of the page has one.'''
	if not yes:
		return dict((g['n'], 'all') for g in page_groups), True, []
	by_n = dict((g['n'], g) for g in page_groups)
	out = dict((n, 'short') for n in by_n)
	rest, problems = False, []
	for word in (note or '').replace(',', ' ').split():
		w = word.strip().lower()
		if w in ('rest', 'yes', 'ok'):
			rest = rest or w == 'rest'
			continue
		m = CHOICE.match(w)
		if not m:
			problems.append('"{}" is not understood: write G=all, G=short, G=K or rest'.format(word))
			continue
		n = int(m.group(1))
		if n not in by_n:
			problems.append('group {} is not on this page (groups {})'.format(n, ', '.join(str(x) for x in sorted(by_n))))
			continue
		v = m.group(2)
		if v.isdigit():
			k = int(v)
			if not 1 <= k <= len(by_n[n]['ids']):
				problems.append('group {} has URLs 1 to {}, not {}'.format(n, len(by_n[n]['ids']), k))
				continue
			v = k
		out[n] = v
	return out, rest, problems


def removed_by_choice(group, decision):
	'''-> the ids that the decision removes from the group.'''
	if decision == 'all':
		return []
	keep = group['default'] if decision == 'short' else group['ids'][decision - 1]
	return [i for i in group['ids'] if i != keep]


# - Sorting ----------------------------------------------
def fits(c, removed, R):
	'''-> {"fit": [ids], "loose": [ids], "misfiled": [ids]}.
	loose: in the top level of the file, or directly in a top folder that is not the favorites bar.
	misfiled: in a deeper folder, no other bookmark of that folder has its site, and another folder
	has at least sort.host_elsewhere bookmarks of its site. The rest fits, and code leaves it alone.'''
	live = [b for b in c['bookmarks'] if b['id'] not in removed]
	host_of = dict((b['id'], (parts(b['url'], R) or (None,))[0]) for b in live)
	in_folder = {}
	for b in live:
		in_folder.setdefault(b['folder'], []).append(b)
	per_host = {}
	for b in live:
		if host_of[b['id']]:
			per_host.setdefault(host_of[b['id']], {}).setdefault(b['folder'], 0)
			per_host[host_of[b['id']]][b['folder']] += 1
	out = {'fit': [], 'loose': [], 'misfiled': []}
	for b in live:
		h = host_of[b['id']]
		if protected(c, b, R) or h is None:
			out['fit'].append(b['id'])
		elif depth(c, b['folder']) <= R('sort.loose_depth'):
			out['loose'].append(b['id'])
		elif per_host[h][b['folder']] > 1:
			out['fit'].append(b['id'])
		elif any(n >= R('sort.host_elsewhere') for f, n in per_host[h].items() if f != b['folder'] and depth(c, f) > R('sort.loose_depth')):
			# a loose folder does not count: its bookmarks are not filed yet
			out['misfiled'].append(b['id'])
		else:
			out['fit'].append(b['id'])
	return out


def folder_paths(c):
	'''-> {path text: folder id} of every folder of the file.'''
	return dict((path_of(c, f['id']), f['id']) for f in c['folders'])


def shown(c, b, R):
	'''One bookmark as the model sees it.'''
	url = b['url']
	if len(url) > R('sort.url_chars'):
		url = url[:R('sort.url_chars')] + '…'
	title = plain_title(b)
	if len(title) > R('sort.title_chars'):
		title = title[:R('sort.title_chars')] + '…'
	return {'id': b['id'], 'title': title, 'url': url, 'folder': path_of(c, b['folder'])}


def sort_problems(answer, batch, known, made, R):
	'''What is wrong with the answer of the model for one batch. -> (problems, new folders of this answer).
	answer: [{"id", "folder", "new"?}]; batch: the bookmarks as shown; known: the paths of the folders
	of the file; made: the new paths of earlier batches.'''
	if not isinstance(answer, list):
		return ['the result is not a list: give one object {"id", "folder"} for each bookmark'], []
	want = dict((b['id'], b) for b in batch)
	seen, problems, new = {}, [], []
	for a in answer:
		if not isinstance(a, dict) or not isinstance(a.get('id'), int) or isinstance(a.get('id'), bool):
			problems.append('an item is not an object with a whole number "id": {}'.format(str(a)[:80]))
			continue
		i = a['id']
		seen[i] = seen.get(i, 0) + 1
		if i not in want:
			problems.append('id {} is not in this batch'.format(i))
			continue
		for k in ('title', 'url'):
			if k in a and a[k] != want[i][k]:
				problems.append('id {}: the {} was changed; give only "id" and "folder"'.format(i, k))
		folder = a.get('folder')
		if not isinstance(folder, str) or not folder.strip():
			problems.append('id {}: no "folder"'.format(i))
			continue
		folder = SEP.join(x.strip() for x in folder.split(SEP.strip()))
		if folder in known or folder in made or folder in new:
			continue
		if a.get('new') is not True:
			problems.append('id {}: there is no folder "{}"; use a folder of the list, or add "new": true for a new folder'.format(i, folder))
			continue
		parent = SEP.join(folder.split(SEP)[:-1])
		if parent and parent not in known and parent not in made and parent not in new:
			problems.append('id {}: the new folder "{}" is not under a folder of the list'.format(i, folder))
			continue
		new.append(folder)
	for i, n in seen.items():
		if n > 1 and i in want:
			problems.append('id {} is in the result {} times'.format(i, n))
	missing = [i for i in want if i not in seen]
	if missing:
		problems.append('missing ids: {}'.format(', '.join(str(i) for i in missing[:20])))
	if len(new) > R('sort.new_per_batch'):
		problems.append('{} new folders in one batch (sort.new_per_batch {})'.format(len(new), R('sort.new_per_batch')))
	if len(made) + len(new) > R('sort.new_max'):
		problems.append('{} new folders in all (sort.new_max {})'.format(len(made) + len(new), R('sort.new_max')))
	return problems, new


def clean_path(folder):
	return SEP.join(x.strip() for x in folder.split(SEP.strip()))


# - Write ------------------------------------------------
def render(c, plan, R, now=0):
	'''The new bookmarks file.
	plan: {"removed": [ids], "moves": {id: path}, "new_folders": [paths]}
	The folders of the file stay, with their names and order. A new folder goes at the end of its parent.
	A moved bookmark goes at the end of its new folder. Titles, URLs and attributes do not change.'''
	removed = set(plan.get('removed', []))
	moves = dict((int(k), v) for k, v in plan.get('moves', {}).items())
	paths = folder_paths(c)
	kids = {}  # ("f", folder id or None) or ("n", new path) -> [("f", id) | ("b", id) | ("n", path)], in file order
	for kind, item in file_order(c):
		parent = item['parent'] if kind == 'f' else item['folder']
		kids.setdefault(('f', parent), []).append((kind, item['id']))
	for path in plan.get('new_folders', []):
		parent = SEP.join(path.split(SEP)[:-1])
		pid = ('f', paths[parent]) if parent in paths else (('n', parent) if parent else ('f', None))
		kids.setdefault(pid, []).append(('n', path))
	for i, path in sorted(moves.items()):
		b = c['bookmarks'][i]
		if i in removed or path == path_of(c, b['folder']):
			continue
		kids[('f', b['folder'])].remove(('b', i))
		target = ('f', paths[path]) if path in paths else ('n', path)
		kids.setdefault(target, []).append(('b', i))
	L = [c['head'].rstrip('\n'), '<DL><p>']

	def emit(parent, level):
		pad = '    ' * level
		for kind, x in kids.get(parent, []):
			if kind == 'b':
				if x in removed:
					continue
				b = c['bookmarks'][x]
				L.append('{}<DT><A{}>{}</A>'.format(pad, b['attrs'], b['title']))
				if b.get('dd') is not None:
					L.append('{}<DD>{}'.format(pad, b['dd']))
			elif kind == 'f':
				f = c['folders'][x]
				L.append('{}<DT><H3{}>{}</H3>'.format(pad, f['attrs'], f['name']))
				L.append(pad + '<DL><p>')
				emit(('f', x), level + 1)
				L.append(pad + '</DL><p>')
			else:
				name = x.split(SEP)[-1]
				L.append('{}<DT><H3 ADD_DATE="{}" LAST_MODIFIED="{}">{}</H3>'.format(pad, now, now, html.escape(name, quote=False)))
				L.append(pad + '<DL><p>')
				emit(('n', x), level + 1)
				L.append(pad + '</DL><p>')
	emit(('f', None), 1)
	L.append('</DL><p>')
	return '\n'.join(L) + '\n'


def file_order(c):
	'''-> [(kind, item)] in the order of the file. parse() numbers folders and bookmarks apart, and
	records their order in c["order_keys"].'''
	return [(k, c['folders'][i] if k == 'f' else c['bookmarks'][i]) for k, i in c['order_keys']]


# - Compare two collections: the facts for the gate "verify" --
def summary(c, R):
	'''-> facts of a collection: the bookmarks as (title, url), the folder paths.'''
	return {'bookmarks': sorted([plain_title(b), b['url']] for b in c['bookmarks']),
		'folders': sorted(path_of(c, f['id']) for f in c['folders'])}
