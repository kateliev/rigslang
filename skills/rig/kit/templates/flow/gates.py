"""The gates of __NAME__: every decision that code can make.

Pure Python: no files, no network, no host application. A gate reads the state of the
run and the rules (R('group.name')), and returns "pass", and for a fail the "problems".
A gate with more than one fail line returns "when" too: the text of the line to follow.
Never write a number here: add a rule to __NAME__.rig and read it with R.
"""


def long_enough(state, R):
	'''TODO: replace this example gate.'''
	length = state['look']['length']
	ok = length >= R('limits.min_length')
	return {'pass': ok, 'length': length, 'problems': [] if ok else ['the item has {} characters (limits.min_length {})'.format(length, R('limits.min_length'))]}
# >>> level 3


def may_write(state, R):
	ok = R('permissions.write')
	return {'pass': ok, 'problems': [] if ok else ['permissions.write is off: a dry run']}
# <<< level 3
