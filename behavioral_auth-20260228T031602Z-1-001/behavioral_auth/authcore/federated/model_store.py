"""Model store — version tracking for federated global model."""
import os, json, pickle, logging
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)

REGISTRY_PATH = settings.FEDERATED_CONFIG.get('MODEL_REGISTRY_PATH',
    os.path.join(os.path.dirname(__file__), '..', 'ml', 'model_registry.json'))
GLOBAL_MODEL_PATH = settings.FEDERATED_CONFIG.get('GLOBAL_MODEL_PATH',
    os.path.join(os.path.dirname(__file__), '..', 'ml', 'global_model.pkl'))

_pending_updates = []


def get_registry():
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, 'r') as f:
            return json.load(f)
    return {
        'current_version': 1,
        'history': [],
        'pending_updates': 0,
        'min_updates_to_aggregate': settings.FEDERATED_CONFIG.get('MIN_UPDATES_TO_AGGREGATE', 3),
        'total_contributors': 0,
        'updated_at': None,
    }


def save_registry(registry):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(registry, f, indent=2)


def load_global_model():
    if os.path.exists(GLOBAL_MODEL_PATH):
        with open(GLOBAL_MODEL_PATH, 'rb') as f:
            return pickle.load(f)
    return None


def add_pending_update(weights, version, user_id=None):
    """Add a client weight update to the pending pool."""
    registry = get_registry()
    if version != registry['current_version']:
        return False, 'Version mismatch'

    _pending_updates.append({'weights': weights, 'user_id': user_id})
    registry['pending_updates'] = len(_pending_updates)
    save_registry(registry)

    min_updates = registry['min_updates_to_aggregate']
    if len(_pending_updates) >= min_updates:
        _aggregate_and_update(registry)
        return True, 'Aggregated'

    return True, 'Accepted'


def _aggregate_and_update(registry):
    from authcore.federated.aggregator import federated_average
    try:
        all_weights = [u['weights'] for u in _pending_updates]
        avg_weights = federated_average(all_weights)
        
        new_version = registry['current_version'] + 1
        registry['history'].append({
            'version': registry['current_version'],
            'aggregated_at': datetime.now().isoformat(),
            'contributors': len(_pending_updates),
        })
        registry['current_version'] = new_version
        registry['total_contributors'] = registry.get('total_contributors', 0) + len(_pending_updates)
        registry['pending_updates'] = 0
        registry['updated_at'] = datetime.now().isoformat()
        _pending_updates.clear()
        save_registry(registry)
        logger.info(f'Federated aggregation complete. New version: {new_version}')
    except Exception as e:
        logger.error(f'Aggregation error: {e}')
