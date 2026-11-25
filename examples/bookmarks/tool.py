#!/usr/bin/env python3
"""bookmarks: one command line for every front (the Claude skill, the LM Studio plugin, a person).

    python3 tool.py run '{"file": "~/Downloads/favorites.html"}'   start a run; code walks the flow as far as it can
    python3 tool.py answer RUN '{"result": [...]}'                 the model gives the folders of a sort batch
    python3 tool.py approve RUN yes|no [WORDS]                     a person answers a human gate
    python3 tool.py resume RUN | status RUN | queues | rules | flow
    python3 tool.py rerun RUN --from ID [--set group.name=value]   a new run from a line of an old run
    python3 tool.py replay RUN                                     the flow again, with the recorded answers
    python3 tool.py regress tests/regression-set.json [--baseline]

Each call prints one JSON line. A "refused" result is final: do not repeat the call.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402
import steps  # noqa: E402

TMP = os.path.join(HERE, 'tests', '.tmp')  # the work and out folders of the regression cases (their rules name it)


def kit(runs=os.path.join(HERE, 'runs')):
	return rigkit.Kit(os.path.join(HERE, 'gen', 'bookmarks.json'), runs=runs).bind('gates', gates).bind('steps', steps)


def clean_cases():
	'''A test set must be the same before and after a run: take the work of the regression cases out.'''
	shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
	regress = sys.argv[1:2] == ['regress']
	if regress:
		clean_cases()
	code = kit().cli(sys.argv[1:])
	if regress:
		clean_cases()
	sys.exit(code)
