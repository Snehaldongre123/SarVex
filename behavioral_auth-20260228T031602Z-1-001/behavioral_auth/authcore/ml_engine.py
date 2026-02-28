"""
ML Engine — Loads and runs the RandomForest behavioral model.
Tries global_model.pkl (federated) first, falls back to behavior_model.pkl.
"""
import os
import pickle
import logging
import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ML_DIR = os.path.join(BASE_DIR, 'ml')

_model = None
_model_version = 'local'


def load_model():
    global _model, _model_version
    
    # Try federated global model first
    global_path = os.path.join(ML_DIR, 'global_model.pkl')
    local_path = os.path.join(ML_DIR, 'behavior_model.pkl')
    
    for path, version in [(global_path, 'federated'), (local_path, 'local')]:
        if os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    _model = pickle.load(f)
                _model_version = version
                logger.info(f'Loaded ML model: {version} from {path}')
                return _model
            except Exception as e:
                logger.error(f'Failed to load model from {path}: {e}')
    
    logger.warning('No ML model found. Using neutral fallback.')
    return None


def get_model():
    global _model
    if _model is None:
        load_model()
    return _model


def predict_proba(feature_vector: list) -> float:
    """
    Returns probability 0.0-1.0 that this session is legitimate.
    Feature vector: [typing_speed, key_hold_time, mouse_velocity, click_interval,
                     decision_time, scroll_depth, network_latency,
                     behavior_under_slowness, time_of_day]
    """
    model = get_model()
    if model is None:
        return 0.5  # neutral
    
    try:
        X = np.array(feature_vector).reshape(1, -1)
        proba = model.predict_proba(X)[0]
        # Class 1 = legitimate
        return float(proba[1]) if len(proba) > 1 else float(proba[0])
    except Exception as e:
        logger.error(f'predict_proba error: {e}')
        return 0.5


def get_model_version():
    return _model_version
