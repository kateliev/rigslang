"""The steps of the release tool: the only code that touches the world (here: files)."""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def folder_of(state):
	f = state['folder']
	return f if os.path.isabs(f) else os.path.join(HERE, f)


def read(path):
	if not os.path.exists(path):
		return ''
	with open(path, encoding='utf-8') as f:
		return f.read()


def collect(state, R):
	folder = folder_of(state)
	if not os.path.isdir(folder):
		raise ValueError('no folder {}'.format(state['folder']))
	tests = read(os.path.join(folder, 'tests.json'))
	return {'notes': read(os.path.join(folder, 'NOTES.md')).strip(), 'version': read(os.path.join(folder, 'VERSION')).strip(),
		'tests': json.loads(tests) if tests.strip() else {}}


def publish(state, R):
	'''Write published.json. The gate "allowed" is before this step; the step checks the rule again.'''
	if not R('permissions.publish'):
		raise ValueError('permissions.publish is off')
	path = os.path.join(folder_of(state), 'published.json')
	notes = state.get('rewrite') or state['collect']['notes']
	with open(path, 'w', encoding='utf-8', newline='\n') as f:
		json.dump({'version': state['collect']['version'], 'notes': notes, 'date': datetime.date.today().isoformat()}, f, ensure_ascii=False, indent=1)
		f.write('\n')
	return {'written': path}
