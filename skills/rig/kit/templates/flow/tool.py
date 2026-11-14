#!/usr/bin/env python3
"""__NAME__: one command line for every front (the Claude skill, a plugin, a person).

    python3 tool.py run '{"item": "..."}'      start a run; code walks the flow as far as it can
    python3 tool.py answer RUN '{"pass": true}' the model answers the node that the run waits at
    python3 tool.py approve RUN yes|no [NOTE]   a person answers a human gate
    python3 tool.py resume RUN | status RUN | rules | flow
    python3 tool.py regress tests/regression-set.json [--baseline]

Each call prints one JSON line. A "refused" result is final: do not repeat the call.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import rigkit  # noqa: E402
import steps  # noqa: E402


def kit(runs=os.path.join(HERE, 'runs')):
	return rigkit.Kit(os.path.join(HERE, 'gen', '__NAME__.json'), runs=runs).bind('gates', gates).bind('steps', steps)


if __name__ == '__main__':
	sys.exit(kit().cli(sys.argv[1:]))
