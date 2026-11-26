"""The steps of __NAME__: wire the pure-Python engine (engine.py) to the host adapter (adapter.py)."""
import adapter
import engine


def pending(state, R):
	return adapter.list_pending(limit=int(R('batch.size')))


def snapshot(state, R):
	return adapter.read_snapshot(state['item'])


def compute(state, R):
	return engine.propose(state['snapshot'])


def apply(state, R):
	return adapter.write_item(state['item'], state['compute'])


def restore(state, R):
	snap = state.get('snapshot')
	if snap is None:
		return {'restored': False}
	adapter.write_item(state['item'], snap)
	return {'restored': True, 'item': state['item']}
