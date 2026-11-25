"""The bookmarks file and the plan: pure functions, no files and no network. Standard library only.

    parse(text)                     a Netscape bookmarks file (the HTML export of Edge) -> a collection
    key(url, R)                     the normal form of a URL, for exact duplicates
    duplicates(c, R)                which copies to remove; one copy of each URL stays
    similar(c, removed, R)          groups of URLs on one site, where one path starts with another
    choices(note, page, yes)        the answer of the person for one page of groups -> decisions
    fits(c, removed, R)             the bookmarks that code leaves in their folder; the rest is sorted
    candidates(c, todo, removed, R) for each bookmark to sort, the folders most like it
    folder_map(c, R)                the top folders with the names of their sub-folders
    sort_problems(answer, batch, known, made, R)   what is wrong with an answer of the model
    render(c, plan, R)              the new bookmarks file as text

A collection is a dict:
    {"head": text before the first <DL>, "folders": [folder], "bookmarks": [bookmark]}
    folder:   {"id": int, "name", "parent": int or None, "attrs": text, "path": [names], "bar": bool}
    bookmark: {"id": int, "title", "url", "folder": int or None, "attrs": text, "add_date": int, "dd": text or None}
Folder None is the top level of the file. A title is kept as it was written (HTML text), so it never changes.
"""
import html
import math
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
	has at least sort.host_elsewhere bookmarks of its site. A site of similar.skip_hosts or
	similar.skip_pattern (one site, many topics) says nothing about the folder: it never makes a
	bookmark misfiled. The rest fits, and code leaves it alone.'''
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
		elif per_host[h][b['folder']] > 1 or skipped_host(h, R):
			out['fit'].append(b['id'])
		elif any(n >= R('sort.host_elsewhere') for f, n in per_host[h].items() if f != b['folder'] and depth(c, f) > R('sort.loose_depth')):
			# a loose folder does not count: its bookmarks are not filed yet
			out['misfiled'].append(b['id'])
		else:
			out['fit'].append(b['id'])
	return out


# - Candidate folders: code finds them, the model only picks -----
STOP = set("""the and for with from your you this that are was not but all any our how what why who
www com org net edu gov http https htm php asp aspx index wiki wikipedia free encyclopedia
view item watch feature player embedded""".split())  # parts of URLs and words of any page; the weights (idf) do the rest
WORD = re.compile(r'[^\W_]{3,}')
K1, B, HOST, NAME = 1.2, 0.3, 1.0, 3  # BM25 values; HOST: the weight of a folder with pages of the same site; NAME: of a word of the folder name


def words(text):
	'''The words of a text for matching: lower case, three letters or more, no numbers and no common
	words. A plural s and the end of a long word are cut, so "fonts" and "font" match.'''
	out = set()
	for w in WORD.findall((text or '').lower()):
		if w.isdigit() or w in STOP:
			continue
		if len(w) > 4 and w.endswith('s'):
			w = w[:-1]
		out.add(w[:8])
	return out


def bookmark_words(b, R):
	'''The words of the title, of the site name and of the path of the URL.'''
	text = plain_title(b)
	p = parts(b['url'], R)
	if p:
		text += ' ' + ' '.join(p[0].split(':')[0].split('.')[:-1]) + ' ' + ' '.join(p[1])
	return words(text)


def site(host):
	'''The site of a host name: its last two labels, three when the second last is a label such as
	"co" or "com" (shop.example.co.uk -> example.co.uk). So shop.example.com and example.com are one site.'''
	labels = host.split(':')[0].split('.')
	n = 3 if len(labels) > 2 and labels[-2] in ('co', 'com', 'org', 'net', 'gov', 'ac', 'edu') else 2
	return '.'.join(labels[-n:])


def targets(c, R):
	'''The folders where code may put a bookmark: not the favorites bar itself (keep.bar), and not a
	folder of loose bookmarks (sort.loose_depth): its bookmarks are not filed yet.'''
	return [f['id'] for f in c['folders'] if not (f['bar'] and R('keep.bar')) and depth(c, f['id']) > R('sort.loose_depth')]


def candidates(c, todo, removed, R):
	'''-> {bookmark id: [folder paths]}: for each bookmark to sort, the folders most like it and its
	present folder (when it has one), at most sort.choices in all, the most like it first. The present
	folder is in the list at the place of its own score: a model that reads the list finds no safe default.
	A folder is like a bookmark when they share words (the names of the folder and of its parents, the
	words of the bookmarks that are filed in it), weighted so that a word of many folders counts less,
	and when the folder holds bookmarks of the same site. A site of similar.skip_hosts gives no help.
	A bookmark that no folder is like gets the top folders (folder_map) and its present folder.'''
	todo_set = set(todo)
	ids = targets(c, R)
	profile, hosts = {}, {}
	for f in ids:
		p = {}
		for n, name in enumerate(reversed(c['folders'][f]['path'])):
			for w in words(html.unescape(name)):
				p[w] = p.get(w, 0) + (NAME if n == 0 else 1)
		profile[f], hosts[f] = p, {}
	for b in c['bookmarks']:
		f = b['folder']
		if f not in profile or b['id'] in removed or b['id'] in todo_set:
			continue
		for w in bookmark_words(b, R):
			profile[f][w] = profile[f].get(w, 0) + 1
		h = (parts(b['url'], R) or (None,))[0]
		if h and not skipped_host(h, R):
			hosts[f][site(h)] = hosts[f].get(site(h), 0) + 1
	df = {}
	for p in profile.values():
		for w in p:
			df[w] = df.get(w, 0) + 1
	n = max(1, len(profile))
	idf = dict((w, math.log(1 + (n - k + 0.5) / (k + 0.5))) for w, k in df.items())
	size = dict((f, sum(p.values())) for f, p in profile.items())
	mean = (sum(size.values()) / n) or 1
	by_word = {}  # BM25: a word that a folder has often counts more, a large folder counts less for each word
	for f, p in profile.items():
		norm = K1 * (1 - B + B * size[f] / mean)
		for w, t in p.items():
			by_word.setdefault(w, []).append((f, t * (K1 + 1) / (t + norm)))
	tops = list(folder_map(c, R))
	out = {}
	for i in todo:
		b = c['bookmarks'][i]
		score = {}
		for w in bookmark_words(b, R):
			for f, x in by_word.get(w, []):
				score[f] = score.get(f, 0) + x * idf[w]
		h = (parts(b['url'], R) or (None,))[0]
		if h and not skipped_host(h, R):
			for f in ids:
				k = hosts[f].get(site(h), 0)
				if k:
					score[f] = score.get(f, 0) + HOST * min(1.0, k / 2)
		here = b['folder']
		others = sorted((f for f in score if f != here and score[f] > 0), key=lambda f: (-score[f], f))
		paths = [path_of(c, f) for f in others[:R('sort.choices') - (here is not None)]]
		if not paths:  # no folder shares a word or a site: the top folders, so that a pick is always possible
			paths = [p for p in tops if here is None or p != path_of(c, here)]
		if here is not None:  # the present folder takes its place by score, so that it is no safe default at the first place
			at = sum(1 for f in others[:len(paths)] if score[f] > score.get(here, 0)) if others else len(paths)
			paths.insert(at, path_of(c, here))
		out[i] = paths
	return out


def folder_map(c, R):
	'''-> {path of a top folder: [names of its sub-folders]}: a small map of the file for the model, for
	a bookmark that none of its choices fits. A top folder is a target folder (targets) whose parent is not one.'''
	ids = set(targets(c, R))
	out = {}
	for f in c['folders']:
		if f['id'] in ids and f['parent'] not in ids:
			out[path_of(c, f['id'])] = [html.unescape(x['name']) for x in c['folders'] if x['parent'] == f['id']]
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
	answer: [{"id", "topic"?, "pick"?, "folder"?, "new"?}]; batch: the bookmarks as shown, each with its
	"choices" ({"1": path, ...}); known: the paths of the folders of the file; made: the new paths of
	earlier batches. "pick" is the number of a choice; a "folder" (a path) counts in place of the pick.
	Use places(answer, batch) for the folder of each id after the answer passed.'''
	if not isinstance(answer, list):
		return ['the result is not a list: give one object {"id", "pick"} for each bookmark'], []
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
				problems.append('id {}: the {} was changed; give only "id" and "pick"'.format(i, k))
		if a.get('folder') is None and 'pick' in a:  # a "folder" counts in place of the pick
			pick, chosen = a['pick'], want[i].get('choices', {})
			if isinstance(pick, bool) or not isinstance(pick, int) or str(pick) not in chosen:
				problems.append('id {}: "pick" {} is not one of its choices ({}); when none fits, give "folder"'.format(i, json_short(pick), ', '.join(chosen) or 'none'))
			continue
		folder = a.get('folder')
		if not isinstance(folder, str) or not folder.strip():
			problems.append('id {}: no "pick" of its choices, and no "folder"'.format(i))
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


def json_short(v):
	return str(v)[:40]


def places(answer, batch):
	'''-> {id: folder path} of an answer that passed sort_problems: the path of the choice that
	"pick" names, else the "folder" of the answer.'''
	chosen = dict((b['id'], b.get('choices', {})) for b in batch)
	out = {}
	for a in answer:
		if a.get('folder') is None:
			out[a['id']] = chosen[a['id']][str(a['pick'])]
		else:
			out[a['id']] = clean_path(a['folder'])
	return out


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
