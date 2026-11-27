"""The steps of font-names: the only code that touches the world (here: the files of one folder).

The naming itself is in engine.py (pure Python). A step reads the state of the run and the rules,
does its work and returns a value; the value goes to state[<step id>].
The rename writes an undo log first (files.undo/<token>.json), so the rollback block and
"tool.py restore RUN" can put every name back.
"""
import json
import os
import re
import uuid

import engine

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = '.font-names-tmp'


def folder_of(state):
	f = state['folder']
	return f if os.path.isabs(f) else os.path.join(HERE, f)


def parse(base):
	'''A file name without its suffix -> an instance. The convention is Family-Style
	(the PostScript name); a variable font has its axes in brackets: Family[wght].'''
	variable = '[' in base
	core = re.sub(r'\[.*?\]', '', base)
	family, _, style = core.partition('-')
	return {'family': family.strip(), 'name': style.strip(), 'italic': 'italic' in style.lower(), 'variable': variable}


def read(state, R):
	folder = folder_of(state)
	if not os.path.isdir(folder):
		raise ValueError('no folder {}'.format(state['folder']))
	names = sorted(os.listdir(folder))
	fonts, instances, index = [], [], {}
	for name in names:
		base, suffix = os.path.splitext(name)
		if suffix.lower() not in engine.SUFFIXES or not os.path.isfile(os.path.join(folder, name)):
			continue
		if base not in index:
			index[base] = len(instances)
			instances.append(parse(base))
		fonts.append({'file': name, 'base': base, 'suffix': suffix, 'instance': index[base]})
	suffix = max([f['suffix'] for f in fonts] or ['.otf'], key=len)
	return {'folder': folder, 'fonts': fonts, 'instances': instances, 'names': names, 'suffix': suffix}


def settings(state, R):
	return engine.settings_of(R, state['read']['suffix'])


def plan(state, R):
	'''The names that the built-in table gives, and the words that the table does not know.'''
	rd = state['read']
	rows = engine.build_rows(rd['instances'], settings(state, R))
	weak = engine.weak_words(rd['instances'], rows, R('shorten.abbr_letters')[1] + 1) if R('shorten.ask_model') else []
	files = {}
	for f in rd['fonts']:
		files.setdefault(f['instance'], []).append(f['file'])
	return {'weak_words': weak,
		'rows': [{'files': files.get(r['index'], []), 'short': r['short'], 'steps': r['steps']} for r in rows]}


def try_names(state, R, args):
	'''Arena tool (read only): the names that a table of abbreviations gives, and what the gate
	abbr-ok will say about it. args: {"table": {"Word": "Abbr", ...}}.'''
	table = (args or {}).get('table')
	rd = state['read']
	s = engine.score(rd['instances'], settings(state, R), table, R('shorten.abbr_letters'))
	return {'fair': s['fair'], 'problems': s['problems'], 'names': [{'short': r['short'], 'steps': r['steps']} for r in s['rows']]}


def table(state, R, args):
	'''Arena tool (read only): the built-in table of abbreviations, after Adobe Tech Note 5088.'''
	return {'table': dict(engine.ABBREVIATIONS), 'letters': R('shorten.abbr_letters')}


def final(state, R):
	'''The names with the built-in table and the best fair table of the model (when it gave one).'''
	rd = state['read']
	s = settings(state, R)
	extra, chosen = {}, None
	cands = state.get('abbreviate')
	if isinstance(cands, list) and cands:
		scores = [engine.score(rd['instances'], s, c, R('shorten.abbr_letters')) for c in cands]
		chosen = engine.best(scores)
		if chosen is not None:
			extra = cands[chosen]
	rows = engine.build_rows(rd['instances'], s, extra)
	rows_by = dict((r['index'], r) for r in rows)
	tbl = [{'old': f['file'], 'new': rows_by[f['instance']]['short'] + f['suffix']} for f in rd['fonts']]
	return {'table': tbl, 'changes': sum(1 for t in tbl if t['old'] != t['new']), 'abbreviations': extra, 'chosen': chosen,
		'rows': [{'short': r['short'], 'steps': r['steps'], 'issues': r['issues']} for r in rows], 'token': uuid.uuid4().hex[:12]}


# - Rename and undo -------------------------------------------------------

def log_path(state, R):
	return os.path.join(HERE, R('files.undo'), state['final']['token'] + '.json')


def _save(path, log):
	tmp = path + '.part'
	with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
		json.dump(log, f, ensure_ascii=False, indent=1)
	os.replace(tmp, path)


def rename(state, R):
	'''Rename every changed file, in two phases (old -> tmp, then tmp -> new), so that a swap of two
	names or a change of case only also works. The log is written before each move.'''
	if not R('permissions.rename'):
		raise ValueError('permissions.rename is off')
	folder = state['read']['folder']
	path = log_path(state, R)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	moves = [{'old': t['old'], 'new': t['new'], 'at': 'old'} for t in state['final']['table'] if t['old'] != t['new']]
	log = {'folder': folder, 'moves': moves}
	_save(path, log)
	for m in moves:
		os.rename(os.path.join(folder, m['old']), os.path.join(folder, m['old'] + TMP))
		m['at'] = 'tmp'
		_save(path, log)
	for m in moves:
		os.rename(os.path.join(folder, m['old'] + TMP), os.path.join(folder, m['new']))
		m['at'] = 'new'
		_save(path, log)
	return {'renamed': [[m['old'], m['new']] for m in moves], 'after': sorted(os.listdir(folder)), 'log': path}


def undo_log(path):
	'''Put back every move of an undo log, then remove the log. Safe to call twice.'''
	if not os.path.exists(path):
		return {'restored': 0}
	with open(path, encoding='utf-8') as f:
		log = json.load(f)
	folder = log['folder']
	for m in log['moves']:		# new -> tmp
		if m['at'] == 'new' and os.path.exists(os.path.join(folder, m['new'])):
			os.rename(os.path.join(folder, m['new']), os.path.join(folder, m['old'] + TMP))
			m['at'] = 'tmp'
			_save(path, log)
	restored = 0
	for m in log['moves']:		# tmp -> old
		if m['at'] == 'tmp' and os.path.exists(os.path.join(folder, m['old'] + TMP)):
			os.rename(os.path.join(folder, m['old'] + TMP), os.path.join(folder, m['old']))
			m['at'] = 'old'
			restored += 1
			_save(path, log)
	os.remove(path)
	return {'restored': restored}


def undo(state, R):
	'''The rollback: put back the names of this run, from its undo log.'''
	if not (state.get('final') or {}).get('token'):
		return {'restored': 0}
	return undo_log(log_path(state, R))
