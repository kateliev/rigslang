"""Pure-Python domain engine for __NAME__.

Zero host imports, zero I/O. Everything here is deterministic and directly unit-testable.
"""


def propose(snapshot):
	'''TODO: replace this example pure-Python computation.'''
	text = str(snapshot.get('text') or snapshot.get('item') or '')
	return {
		'item': snapshot.get('item', text),
		'text': text.strip(),
		'length': len(text),
		'words': len(text.split()),
	}
