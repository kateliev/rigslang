"""The gates of __NAME__: pure-Python decisions (no host imports, no I/O)."""


def long_enough(state, R):
	'''TODO: replace this example gate.'''
	length = state['snapshot']['length']
	ok = length >= R('limits.min_length')
	return {'pass': ok, 'length': length, 'problems': [] if ok else ['the item has {} characters (limits.min_length {})'.format(length, R('limits.min_length'))]}
# >>> level 3


def may_write(state, R):
	ok = R('permissions.write')
	return {'pass': ok, 'problems': [] if ok else ['permissions.write is off: a dry run']}
# <<< level 3
