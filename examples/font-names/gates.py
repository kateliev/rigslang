"""The gates of font-names: every decision that code can make.

Pure Python: no files, no network. A gate reads the state of the run and the rules
(R('group.name')) and returns "pass", and for a fail the "problems". The numbers live
in font-names.rig, not here; the naming rules live in engine.py.
"""
import engine


def files_ok(state, R):
	rd = state['read']
	problems = []
	if not rd['fonts']:
		problems.append('the folder has no font file ({})'.format(', '.join(engine.SUFFIXES)))
	for f in rd['fonts']:
		if not rd['instances'][f['instance']]['family']:
			problems.append('{}: no family name before the "-"'.format(f['file']))
	return {'pass': not problems, 'fonts': len(rd['fonts']), 'problems': problems}


def abbr_ok(state, R):
	'''Pass when at least one candidate table of the model is fair (engine.score says what fair is).'''
	cands = state.get('abbreviate')
	if not isinstance(cands, list) or not cands:
		return {'pass': False, 'problems': ['no candidate tables']}
	rd = state['read']
	s = engine.settings_of(R, rd['suffix'])
	scores = [engine.score(rd['instances'], s, c, R('shorten.abbr_letters')) for c in cands]
	best = engine.best(scores)
	problems = [] if best is not None else ['candidate {}: {}'.format(i + 1, '; '.join(sc['problems'])) for i, sc in enumerate(scores)]
	return {'pass': best is not None, 'best': best, 'fair': [sc['fair'] for sc in scores], 'problems': problems}


def fits(state, R):
	'''Every new name fits the standard: length, characters, reserved names. Duplicates are the gate unique.'''
	problems = []
	for row in state['final']['rows']:
		found = [i for i in row['issues'] if i != 'duplicate']
		if found:
			problems.append('{}: {}'.format(row['short'], ', '.join(found)))
	return {'pass': not problems, 'standard': R('target.standard'), 'problems': problems}


def unique(state, R):
	'''No two files get one name, and no new name is the name of another file in the folder
	(file systems compare names without case).'''
	tbl = state['final']['table']
	olds = set(t['old'].lower() for t in tbl)
	seen, problems = {}, []
	for t in tbl:
		key = t['new'].lower()
		if key in seen:
			problems.append('{} and {} both become {}'.format(seen[key], t['old'], t['new']))
		seen[key] = t['old']
	for name in state['read']['names']:
		if name.lower() in seen and name.lower() not in olds:
			problems.append('{} is the name of another file in the folder'.format(name))
	return {'pass': not problems, 'problems': problems}


def something(state, R):
	n = state['final']['changes']
	return {'pass': n > 0, 'changes': n, 'problems': [] if n else ['every file has its short name already']}


def may_rename(state, R):
	ok = R('permissions.rename')
	return {'pass': ok, 'problems': [] if ok else ['permissions.rename is off: a dry run']}


def verify(state, R):
	'''After the rename: every new name is there, no old name and no temporary name is left,
	and the count of font files did not change.'''
	after = state['rename']['after']
	news = [t['new'] for t in state['final']['table']]
	gone = set(old for old, new in state['rename']['renamed'] if old.lower() not in set(n.lower() for n in news))
	problems = ['{} is missing'.format(n) for n in news if n not in after]
	problems += ['{} is still there'.format(o) for o in sorted(gone) if o in after]
	problems += ['{} was left behind'.format(a) for a in after if a.endswith('.font-names-tmp')]
	count = sum(1 for a in after if a.lower().endswith(engine.SUFFIXES))
	if count != len(state['read']['fonts']):
		problems.append('{} font files before, {} after'.format(len(state['read']['fonts']), count))
	return {'pass': not problems, 'problems': problems}
