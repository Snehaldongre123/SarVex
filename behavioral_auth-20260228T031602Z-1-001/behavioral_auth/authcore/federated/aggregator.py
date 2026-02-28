"""FedAvg aggregator — averages weight updates from clients."""
import numpy as np
import logging

logger = logging.getLogger(__name__)


def federated_average(weight_updates: list) -> list:
    """Simple FedAvg: average all client weight deltas."""
    if not weight_updates:
        return []
    try:
        arrays = [np.array(w) for w in weight_updates]
        averaged = np.mean(arrays, axis=0)
        return averaged.tolist()
    except Exception as e:
        logger.error(f'FedAvg error: {e}')
        return weight_updates[0] if weight_updates else []
