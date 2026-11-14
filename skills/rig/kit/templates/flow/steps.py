"""The steps of __NAME__: the only code that touches the world (files, a network, a host application).

A step reads the state of the run and the rules, does its work, and returns a value.
The value goes to state[<step id>], where the gates and the later steps read it.
A step that changes something must have a way back: keep the old thing, or work on a copy.
"""


def look(state, R):
	'''TODO: replace this example step. It measures the item.'''
	item = state['item']
	return {'length': len(item), 'words': len(item.split())}
