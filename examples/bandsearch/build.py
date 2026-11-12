'''Build src/gen from the .rig files. Never edit src/gen by hand.

    python build.py

1. Emit the casts in TypeScript. rig.py emit writes only proved and observed casts,
   each with its catalogue (the rule values). It refuses any other cast.
2. Compile the tool units to tool definitions: name, description, JSON Schema.
3. Compile the agent unit to a skill: the plugin gives it to the model.
'''
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RIG = [sys.executable, os.path.join(HERE, '..', '..', 'skills', 'rig', 'rig.py')]
GEN = os.path.join('src', 'gen')


def run(args):
	p = subprocess.run(RIG + args, cwd=HERE, capture_output=True, text=True)
	if p.returncode != 0:
		sys.exit('build stopped: rig.py {}\n{}{}'.format(' '.join(args), p.stdout, p.stderr))
	return p.stdout


def main():
	shutil.rmtree(os.path.join(HERE, GEN), ignore_errors=True)
	for rig_file in ('search.rig', 'wiki.rig'):
		run(['emit', rig_file, 'ts', GEN])
		unit = rig_file[:-len('.rig')]
		run(['compile', 'tool', rig_file, unit, '-o', os.path.join(GEN, unit + '.tool.json')])
	skill = run(['compile', 'skill', 'bandsearch.rig', 'bandsearch'])
	with open(os.path.join(HERE, GEN, 'skill.ts'), 'w', encoding='utf-8') as f:
		f.write('// Generated from bandsearch.rig by build.py. Do not edit.\n\n')
		f.write('export const skill = {};\n'.format(json.dumps(skill, ensure_ascii=False)))
	print('built ' + GEN + ': ' + ', '.join(sorted(os.listdir(os.path.join(HERE, GEN)))))


if __name__ == '__main__':
	main()
