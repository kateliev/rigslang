"""Host application adapter for __NAME__: the only module that talks to the host app.

Keep every host quirk (RPC transport, host APIs, retries, timeouts) inside this file.
Never import host modules into engine.py or gates.py.
"""
import os

import rigkit

HOST_URL = os.environ.get('__FN___HOST_URL', '')


class InMemoryHost(object):
	'''Default in-memory host stub for offline tests and dry runs. Replace with real RPC calls.'''

	def __init__(self):
		self.items = {}

	def list_pending(self):
		return [{'item': k} for k in sorted(self.items)]

	def read(self, item):
		return dict(self.items.get(item, {'item': item, 'text': item, 'length': len(item)}))

	def write(self, item, data):
		self.items[item] = dict(data)
		return {'item': item, 'written': True}


_HOST = InMemoryHost()


def list_pending(limit=10):
	if HOST_URL:
		return rigkit.rpc_call(HOST_URL, 'list_pending', {'limit': limit})
	return _HOST.list_pending()[:limit]


def read_snapshot(item):
	if HOST_URL:
		return rigkit.rpc_call(HOST_URL, 'read_item', {'item': item})
	return _HOST.read(item)


def write_item(item, data):
	if HOST_URL:
		return rigkit.rpc_call(HOST_URL, 'write_item', {'item': item, 'data': data})
	return _HOST.write(item, data)
