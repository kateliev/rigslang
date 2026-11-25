#!/usr/bin/env python3
"""The release tool: one command line for every front (the Claude skill, a plugin, a person).

    python3 tool.py run '{"folder": "tests/cases/good"}'
    python3 tool.py answer RUN '{"pass": true}'
    python3 tool.py approve RUN yes
    python3 tool.py status RUN | rules | flow | regress tests/regression-set.json
    python3 tool.py rerun RUN --from ID | replay RUN
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402
import steps  # noqa: E402


def kit(runs=os.path.join(HERE, 'runs')):
	return rigkit.Kit(os.path.join(HERE, 'gen', 'release.json'), runs=runs).bind('gates', gates).bind('steps', steps)


def clean_cases():
	'''A regression case with permissions.publish on writes into its case folder. Take that out again:
	a test set must be the same before and after a run.'''
	cases = os.path.join(HERE, 'tests', 'cases')
	for name in os.listdir(cases):
		path = os.path.join(cases, name, 'published.json')
		if os.path.exists(path):
			os.remove(path)


if __name__ == '__main__':
	code = kit().cli(sys.argv[1:])
	if sys.argv[1:2] == ['regress']:
		clean_cases()
	sys.exit(code)
