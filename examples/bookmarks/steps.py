"""The steps of bookmarks: the only code that touches the world (files).

A step reads the state of the run and the rules, does its work, and returns a value.
The value goes to state[<step id>], where the gates and the later steps read it.

Each run has a work folder (rule files.work). A step writes what it found there, and the state of
the run keeps only the counts and the paths. So the state stays small, and every page of choices and
every sorted batch is saved as its own file: a run that stops goes on from the last saved file.

No step changes the export file or a file of the browser. The new file goes to the folder of the
rule files.out, and only after the person agreed to the report.
"""
import datetime
import json
import os
import secrets
import shutil

import bm

HERE = os.path.dirname(os.path.abspath(__file__))


# - Files of the work folder ------------------------------
def where(path):
	'''A path of the person or of a rule: "~" is the home folder; a relative path is in the tool folder.'''
	path = os.path.expanduser(str(path))
	return path if os.path.isabs(path) else os.path.join(HERE, path)


def load(work, name, default=None):
	path = os.path.join(work, name)
	if not os.path.exists(path):
		return default
	with open(path, encoding='utf-8') as f:
		return json.load(f)


def save(work, name, data):
	path = os.path.join(work, name)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
		json.dump(data, f, ensure_ascii=False, indent=1)
		f.write('\n')
	os.replace(path + '.tmp', path)
	return path


def write_text(work, name, text):
	path = os.path.join(work, name)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, 'w', encoding='utf-8', newline='\n') as f:
		f.write(text)
	return path


def work_of(state):
	return state['read']['work']


def collection(state):
	return load(work_of(state), 'collection.json')


def removed_so_far(work):
	'''The ids that duplicates, folded variants and the choices of the person remove.'''
	out = set(d['removed'] for d in load(work, 'dupes.json', []))
	out |= set(d['removed'] for d in (load(work, 'similar.json') or {}).get('folded', []))
	folder = os.path.join(work, 'choices')
	if os.path.isdir(folder):
		for n in sorted(os.listdir(folder)):
			if n.startswith('page-') and n.endswith('.json'):
				out |= set(load(folder, n)['removed'])
	return out


# - Read ------------------------------------------------
def read(state, R):
	'''Read the export. A file that is not a bookmarks file gives "ok": false and the reason.'''
	path = where(state['file'])
	out = {'ok': False, 'file': path}
	if not os.path.isfile(path):
		out['problem'] = 'no file at {}'.format(path)
		return out
	with open(path, encoding='utf-8', errors='replace') as f:
		text = f.read()
	try:
		c = bm.parse(text)
	except ValueError as e:
		out['problem'] = str(e)
		return out
	stem = os.path.splitext(os.path.basename(path))[0]
	work = os.path.join(where(R('files.work')), '{}-{}-{}'.format(stem, datetime.datetime.now().strftime('%Y%m%d-%H%M%S'), secrets.token_hex(2)))
	save(work, 'collection.json', c)
	out.update(ok=True, work=work, stem=stem, bookmarks=len(c['bookmarks']), folders=len(c['folders']),
		bar=sum(1 for b in c['bookmarks'] if bm.on_bar(c, b)))
	return out


# - Exact duplicates ------------------------------------
def dupes(state, R):
	c = collection(state)
	d = bm.duplicates(c, R)
	save(work_of(state), 'dupes.json', d)
	return {'removed': len(d)}


# - Similar URLs ----------------------------------------
def group(state, R):
	'''Find the groups of similar URLs, fold the plain variants, and cut the groups into pages.'''
	c, work = collection(state), work_of(state)
	s = bm.similar(c, removed_so_far(work), R)
	s['pages'] = bm.pages(s['groups'], R('similar.page_size'))
	save(work, 'similar.json', s)
	return {'folded': len(s['folded']), 'groups': len(s['groups']), 'pages': len(s['pages']), 'too_big': len(s['too_big'])}


def how_page(groups):
	'''The answers that the person can give for this page, with the real numbers of its groups.
	Each key is the end of the command: approve <run id> <answer>.'''
	g = groups[0]
	out = {'yes': 'keep the shortest URL of every group of this page'}
	out['yes {}=all'.format(g['n'])] = 'group {}: keep every URL; the other groups: the shortest'.format(g['n'])
	out['yes {}={}'.format(g['n'], len(g['ids']))] = 'group {}: keep only URL {}; the other groups: the shortest'.format(g['n'], len(g['ids']))
	if len(groups) > 1:
		h = groups[1]
		out['yes {}=all {}=2'.format(g['n'], h['n'])] = 'two changes in one answer'
	out['yes rest'] = 'the shortest URL on this page and on every later page'
	out['no'] = 'keep every URL, on this page and on every later page'
	return out


def page(state, R):
	'''The next page of groups that waits for the person, or "page": null when every page is decided.'''
	c, work = collection(state), work_of(state)
	s = load(work, 'similar.json')
	by_n = dict((g['n'], g) for g in s['groups'])
	rest = load(work, 'choices/rest.json')
	for k, ns in enumerate(s['pages'], 1):
		name = 'choices/page-{:03d}.json'.format(k)
		if load(work, name) is not None:
			continue
		groups = [by_n[n] for n in ns]
		if rest is not None:  # the person said "rest" or "no" on an earlier page
			decisions = dict((g['n'], rest['mode']) for g in groups)
			save(work, name, {'page': k, 'decisions': decisions, 'by': 'rest',
				'removed': [i for g in groups for i in bm.removed_by_choice(g, rest['mode'])]})
			continue
		shown = []
		for g in groups:
			urls = []
			for j, i in enumerate(g['ids'], 1):
				b = c['bookmarks'][i]
				urls.append('{}. {}  "{}"  in {}{}'.format(j, b['url'], bm.plain_title(b)[:R('sort.title_chars')], bm.path_of(c, b['folder']) or 'the top level',
					'  (shortest)' if i == g['default'] else ''))
			shown.append({'group': g['n'], 'site': g['host'], 'urls': urls})
		how = how_page(groups)
		text = ['# Similar URLs: page {} of {}'.format(k, len(s['pages'])), '', 'Answer with: approve <run id> and one of these answers:', '']
		text += ['- `{}`: {}'.format(a, m) for a, m in how.items()] + ['']
		for g in shown:
			text += ['## Group {} ({})'.format(g['group'], g['site']), ''] + ['- ' + u for u in g['urls']] + ['']
		path = write_text(work, 'pages/page-{:03d}.md'.format(k), '\n'.join(text))
		return {'page': k, 'of': len(s['pages']), 'groups': shown, 'file': path, 'how': how}
	return {'page': None, 'of': len(s['pages'])}


def apply(state, R):
	'''Read the answer of the person for the page. Save it only when every word is understood.'''
	work, p = work_of(state), state['page']
	answer = state.get('choose') or {}
	s = load(work, 'similar.json')
	groups = [g for g in s['groups'] if g['n'] in set(s['pages'][p['page'] - 1])]
	decisions, rest, problems = bm.choices(answer.get('why'), groups, answer.get('pass') is True)
	if problems:
		return {'ok': False, 'page': p['page'], 'problems': problems}
	removed = [i for g in groups for i in bm.removed_by_choice(g, decisions[g['n']])]
	save(work, 'choices/page-{:03d}.json'.format(p['page']), {'page': p['page'], 'decisions': decisions, 'by': 'person', 'removed': removed})
	if rest:
		save(work, 'choices/rest.json', {'mode': 'short' if answer.get('pass') is True else 'all', 'from_page': p['page']})
	return {'ok': True, 'page': p['page'], 'removed': len(removed), 'rest': rest, 'problems': []}


# - Sorting ----------------------------------------------
def loose(state, R):
	'''Find the bookmarks that code leaves alone, and cut the rest into batches for the model.'''
	c, work = collection(state), work_of(state)
	f = bm.fits(c, removed_so_far(work), R)
	todo = sorted(f['loose'] + f['misfiled'])
	size = R('sort.batch')
	f['batches'] = [todo[i:i + size] for i in range(0, len(todo), size)]
	save(work, 'loose.json', f)
	return {'fit': len(f['fit']), 'loose': len(f['loose']), 'misfiled': len(f['misfiled']), 'batches': len(f['batches'])}


def made_folders(work):
	'''The new folders of the batches that are sorted so far, in order.'''
	out = []
	folder = os.path.join(work, 'sorted')
	if os.path.isdir(folder):
		for n in sorted(os.listdir(folder)):
			if n.endswith('.json'):
				out += [p for p in load(folder, n).get('new', []) if p not in out]
	return out


def batch(state, R):
	'''The next batch that is not sorted, with the folder list; or "batch": null when all are done.'''
	c, work = collection(state), work_of(state)
	batches = load(work, 'loose.json')['batches']
	for k, ids in enumerate(batches, 1):
		if load(work, 'sorted/batch-{:03d}.json'.format(k)) is not None:
			continue
		made = made_folders(work)
		return {'batch': k, 'of': len(batches), 'bookmarks': [bm.shown(c, c['bookmarks'][i], R) for i in ids],
			'folders': [bm.path_of(c, x['id']) for x in c['folders'] if not (x['bar'] and R('keep.bar'))] + made, 'new_so_far': made,
			'sort_visits': state.get('_visits', {}).get('sort', 0)}
	return {'batch': None, 'of': len(batches)}


def keep(state, R):
	'''Save the answer of the model for the batch (the gate sort-ok passed it).'''
	b = state['batch']
	known = [p for p in b['folders'] if p not in b['new_so_far']]
	_, new = bm.sort_problems(state['sort'], b['bookmarks'], known, b['new_so_far'], R)
	folder_of = dict((x['id'], x['folder']) for x in b['bookmarks'])
	places = dict((a['id'], bm.clean_path(a['folder'])) for a in state['sort'])
	moves = dict((str(i), p) for i, p in places.items() if p != folder_of[i])
	save(work_of(state), 'sorted/batch-{:03d}.json'.format(b['batch']), {'batch': b['batch'], 'moves': moves, 'new': new})
	return {'batch': b['batch'], 'moved': len(moves), 'new': new}


def skip(state, R):
	'''No good answer after the retries: the batch stays where it is, and the report lists it.'''
	b = state['batch']
	save(work_of(state), 'sorted/batch-{:03d}.json'.format(b['batch']), {'batch': b['batch'], 'moves': {}, 'new': [], 'skipped': True,
		'ids': [x['id'] for x in b['bookmarks']]})
	return {'batch': b['batch'], 'skipped': True}


def how_new(proposed):
	'''The answers that the person can give about the new folders. Each key is the end of the command.'''
	out = {'yes': 'make every new folder of the list'}
	out['yes 1=no'] = 'leave out new folder 1: its bookmarks stay where they are'
	if len(proposed) > 1:
		out['yes 1=no {}=no'.format(len(proposed))] = 'leave out new folders 1 and {}'.format(len(proposed))
	out['no'] = 'make no new folder'
	return out


def folders(state, R):
	'''The new folders that the model proposed, with how many bookmarks go to each.'''
	c, work = collection(state), work_of(state)
	moves = {}
	folder = os.path.join(work, 'sorted')
	for n in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
		moves.update(load(folder, n)['moves'])
	out = []
	for k, path in enumerate(made_folders(work), 1):
		ids = [int(i) for i, p in moves.items() if p == path or p.startswith(path + bm.SEP)]
		out.append({'n': k, 'path': path, 'bookmarks': len(ids), 'examples': [bm.plain_title(c['bookmarks'][i])[:R('sort.title_chars')] for i in ids[:3]]})
	save(work, 'new-folders.json', out)
	return {'new': out, 'how': how_new(out)}


def accept(state, R):
	'''Read the answer of the person about the new folders.'''
	work, proposed = work_of(state), state['folders']['new']
	answer = state.get('new-ok') or {}
	if answer.get('pass') is not True:
		made, problems = [], []
	else:
		drop, problems = set(), []
		for word in (answer.get('why') or '').replace(',', ' ').split():
			w = word.strip().lower()
			if w in ('yes', 'ok'):
				continue
			n = w[:-3] if w.endswith('=no') else ''
			if not n.isdigit() or not 1 <= int(n) <= len(proposed):
				problems.append('"{}" is not understood: write N=no, with N from 1 to {}'.format(word, len(proposed)))
				continue
			drop.add(int(n))
		made = [p['path'] for p in proposed if p['n'] not in drop]
		made = [p for p in made if all(q in made for q in parents_new(p, proposed))]  # a new folder in a left-out new folder is left out too
	if problems:
		return {'ok': False, 'problems': problems}
	save(work, 'new-folders-ok.json', made)
	return {'ok': True, 'made': made, 'left_out': [p['path'] for p in proposed if p['path'] not in made], 'problems': []}


def parents_new(path, proposed):
	paths = [p['path'] for p in proposed]
	parts = path.split(bm.SEP)
	return [bm.SEP.join(parts[:i]) for i in range(1, len(parts)) if bm.SEP.join(parts[:i]) in paths]


# - Dead links: the hook for a later version -------------
def links(state, R):
	'''Not in v1. A later link checker writes the ids of dead bookmarks to dead.json in the work folder;
	the report then moves them to the folder of the rule links.folder. Nothing is deleted.'''
	if R('links.check'):
		raise NotImplementedError('the link checker is not in this version: set links.check off')
	dead = load(work_of(state), 'dead.json', [])
	return {'checked': False, 'dead': len(dead)}


# - The plan and the report -------------------------------
def plan_of(state, R):
	c, work = collection(state), work_of(state)
	removed = removed_so_far(work)
	made = load(work, 'new-folders-ok.json', [])
	moves, known = {}, bm.folder_paths(c)
	folder = os.path.join(work, 'sorted')
	for n in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
		for i, p in load(folder, n)['moves'].items():
			if int(i) not in removed and (p in known or p in made):
				moves[int(i)] = p
	dead = [i for i in load(work, 'dead.json', []) if i not in removed]
	new_folders = list(made)
	if dead:
		if R('links.folder') not in known:
			new_folders.append(R('links.folder'))
		for i in dead:
			moves[i] = R('links.folder')
	return {'removed': sorted(removed), 'moves': dict((str(i), p) for i, p in sorted(moves.items())), 'new_folders': new_folders, 'dead': dead}


def report(state, R):
	'''The dry run: what would be removed, merged, moved and made, with counts. Nothing is written but
	the report and the plan, in the work folder.'''
	c, work = collection(state), work_of(state)
	plan = plan_of(state, R)
	save(work, 'plan.json', plan)
	d = load(work, 'dupes.json', [])
	s = load(work, 'similar.json')
	chosen = [load(os.path.join(work, 'choices'), n) for n in sorted(os.listdir(os.path.join(work, 'choices')))
		if n.startswith('page-')] if os.path.isdir(os.path.join(work, 'choices')) else []
	by_choice = [i for ch in chosen for i in ch['removed']]
	batches = [load(os.path.join(work, 'sorted'), n) for n in sorted(os.listdir(os.path.join(work, 'sorted')))] if os.path.isdir(os.path.join(work, 'sorted')) else []
	skipped = [b['batch'] for b in batches if b.get('skipped')]
	moves = dict((int(i), p) for i, p in plan['moves'].items())
	before, after = len(c['bookmarks']), len(c['bookmarks']) - len(plan['removed'])
	counts = {'bookmarks_before': before, 'bookmarks_after': after, 'duplicates': len(d), 'variants_folded': len(s['folded']),
		'similar_removed': len(by_choice), 'similar_groups': len(s['groups']), 'too_big_groups': len(s['too_big']),
		'moved': len(moves), 'new_folders': len(plan['new_folders']), 'unsorted_batches': len(skipped), 'dead': len(plan['dead']),
		'removed_share': round(100.0 * len(plan['removed']) / before, 1) if before else 0.0}

	def line(i):
		b = c['bookmarks'][i]
		return '{} "{}" in {}'.format(b['url'], bm.plain_title(b)[:R('sort.title_chars')], bm.path_of(c, b['folder']) or 'the top level')
	L = ['# Dry run: {}'.format(os.path.basename(state['read']['file'])), '',
		'Nothing is written yet. This is what the new file would change.', '',
		'| What | Count |', '|---|---|']
	L += ['| {} | {} |'.format(k.replace('_', ' '), v) for k, v in counts.items()]
	L += ['', '## Removed: exact duplicates ({})'.format(len(d)), '']
	L += ['- {}  (kept: {})'.format(line(x['removed']), bm.path_of(c, c['bookmarks'][x['kept']]['folder']) or 'the top level') for x in d]
	L += ['', '## Removed: plain variants ({})'.format(len(s['folded'])), '']
	L += ['- {}  (kept: {})'.format(line(x['removed']), c['bookmarks'][x['kept']]['url']) for x in s['folded']]
	L += ['', '## Removed: similar URLs, by choice ({})'.format(len(by_choice)), '']
	L += ['- ' + line(i) for i in by_choice]
	L += ['', '## Moved ({})'.format(len(moves)), '']
	L += ['- {}  ->  {}'.format(line(i), p) for i, p in moves.items()]
	L += ['', '## New folders ({})'.format(len(plan['new_folders'])), ''] + ['- ' + p for p in plan['new_folders']]
	if skipped:
		L += ['', '## Batches left unsorted ({})'.format(len(skipped)), '', 'The model gave no good answer after the retries. These bookmarks stay where they are.', '']
		L += ['- batch {}'.format(k) for k in skipped]
	if s['too_big']:
		L += ['', '## Similar groups left alone: too big ({})'.format(len(s['too_big'])), '']
		L += ['- {}: {} URLs (similar.max_group {})'.format(g['host'], g['size'], R('similar.max_group')) for g in s['too_big']]
	path = write_text(work, 'report.md', '\n'.join(L) + '\n')
	counts['report'] = path
	return counts


# - Write ------------------------------------------------
def build(state, R):
	'''Write the new file into the work folder, read it again, and give the facts that the gate verify compares.'''
	c, work = collection(state), work_of(state)
	plan = load(work, 'plan.json')
	now = int(datetime.datetime.now().timestamp())
	text = bm.render(c, plan, R, now)
	path = write_text(work, 'cleaned.html', text)
	again = bm.parse(text)
	removed = set(plan['removed'])
	want = bm.summary({'bookmarks': [b for b in c['bookmarks'] if b['id'] not in removed], 'folders': c['folders']}, R)
	got = bm.summary(again, R)
	want['folders'] = sorted(want['folders'] + plan['new_folders'])
	missing = [x for x in want['bookmarks'] if x not in got['bookmarks']]
	extra = [x for x in got['bookmarks'] if x not in want['bookmarks']]
	places = {}  # (title, url) -> the folders where the new file has it
	for b in again['bookmarks']:
		places.setdefault((bm.plain_title(b), b['url']), set()).add(bm.path_of(again, b['folder']))
	astray = [i for i, p in plan['moves'].items() if p not in places.get((bm.plain_title(c['bookmarks'][int(i)]), c['bookmarks'][int(i)]['url']), set())]
	target = os.path.join(where(R('files.out')), state['read']['stem'] + '-cleaned.html')
	return {'file': path, 'bookmarks_expected': len(want['bookmarks']), 'bookmarks_found': len(got['bookmarks']),
		'same_bookmarks': want['bookmarks'] == got['bookmarks'], 'missing': missing[:10], 'extra': extra[:10],
		'folders_missing': [p for p in want['folders'] if p not in got['folders']][:10], 'moves_astray': astray[:10],
		'target': target, 'target_exists': os.path.exists(target)}


def place(state, R):
	'''Copy the checked file to the folder of files.out. The export and the browser files stay as they are.'''
	b = state['build']
	if b['target_exists'] and not R('permissions.overwrite'):
		raise PermissionError('{} exists and permissions.overwrite is off'.format(b['target']))
	os.makedirs(os.path.dirname(b['target']), exist_ok=True)
	shutil.copyfile(b['file'], b['target'])
	return {'file': b['target'], 'bookmarks': b['bookmarks_found'], 'report': state['report']['report'],
		'next': 'Import this file in Edge (Settings, Favorites, Import favorites, Favorites or bookmarks HTML file). Check the imported folder. Then delete the old folders in Edge.'}
