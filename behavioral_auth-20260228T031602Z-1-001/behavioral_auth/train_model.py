"""
Train the initial RandomForest model on synthetic behavioral data.
Run once: python train_model.py
"""

import os
import sys
import pickle
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
except ImportError:
    print("Install scikit-learn: pip install scikit-learn")
    sys.exit(1)

np.random.seed(42)

# Feature order:
# [typing_speed, key_hold_time, mouse_velocity, click_interval,
#  decision_time, scroll_depth, network_latency,
#  behavior_under_slowness, time_of_day]

print("Generating synthetic training data...")

# ------------------------------
# Legitimate users (1200 samples)
# ------------------------------
n_legit = 1200
legit = np.column_stack([
    np.random.normal(4.2, 0.8, n_legit).clip(1, 8),        # typing_speed
    np.random.normal(112, 18, n_legit).clip(60, 200),      # key_hold_time
    np.random.normal(360, 60, n_legit).clip(100, 600),     # mouse_velocity
    np.random.normal(610, 80, n_legit).clip(200, 1200),    # click_interval
    np.random.normal(820, 150, n_legit).clip(200, 2000),   # decision_time
    np.random.uniform(100, 500, n_legit),                  # scroll_depth (real users scroll more)
    np.random.normal(95, 25, n_legit).clip(10, 300),       # network_latency
    np.random.normal(0.91, 0.06, n_legit).clip(0.5, 1.0),  # behavior_under_slowness
    np.random.normal(14, 3, n_legit).clip(0, 23),          # time_of_day
])

# ------------------------------
# Attackers / bots (800 samples)
# ------------------------------
n_attack = 800

# Fix for np.random.choice error → use concatenate instead
typing_attack = np.concatenate([
    np.random.normal(0.5, 0.3, n_attack // 2).clip(0.1, 2),   # too slow (copy-paste)
    np.random.normal(12, 2, n_attack // 2).clip(8, 20),       # too fast (bot)
])

keyhold_attack = np.concatenate([
    np.random.normal(420, 80, n_attack // 2).clip(200, 800),  # too long hold
    np.random.normal(8, 3, n_attack // 2).clip(1, 20),        # too short hold (bot)
])

attack = np.column_stack([
    typing_attack,
    keyhold_attack,
    np.random.normal(950, 200, n_attack).clip(600, 2000),     # extreme mouse
    np.random.normal(35, 15, n_attack).clip(5, 100),          # instant clicking
    np.random.normal(9, 5, n_attack).clip(1, 30),             # low decision time
    np.random.uniform(0, 100, n_attack),                      # minimal scroll
    np.random.normal(200, 80, n_attack).clip(50, 600),        # odd latency
    np.random.normal(0.15, 0.08, n_attack).clip(0, 0.4),      # degraded behavior
    np.random.uniform(0, 23, n_attack),                       # random hours
])

# ------------------------------
# Combine dataset
# ------------------------------
X = np.vstack([legit, attack])
y = np.array([1] * n_legit + [0] * n_attack)

# Shuffle
idx = np.random.permutation(len(X))
X, y = X[idx], y[idx]

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print("Training RandomForest model...")

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=12,
    min_samples_split=5,
    random_state=42,
    n_jobs=-1,
    class_weight='balanced'
)

model.fit(X_train, y_train)

# Evaluate
auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
print(f"Model AUC: {auc:.4f}")

# ------------------------------
# Save model
# ------------------------------
ml_dir = os.path.join(os.path.dirname(__file__), 'authcore', 'ml')
os.makedirs(ml_dir, exist_ok=True)

model_path = os.path.join(ml_dir, 'behavior_model.pkl')
global_path = os.path.join(ml_dir, 'global_model.pkl')

with open(model_path, 'wb') as f:
    pickle.dump(model, f)

with open(global_path, 'wb') as f:
    pickle.dump(model, f)

print(f"✓ Saved: {model_path}")
print(f"✓ Saved: {global_path}")

# ------------------------------
# Initialize model registry
# ------------------------------
import json

registry = {
    'current_version': 1,
    'history': [
        {
            'version': 1,
            'created_at': 'init',
            'contributors': 0,
            'source': 'train_model.py'
        }
    ],
    'pending_updates': 0,
    'min_updates_to_aggregate': 3,
    'total_contributors': 0,
    'updated_at': None,
}

registry_path = os.path.join(ml_dir, 'model_registry.json')

with open(registry_path, 'w') as f:
    json.dump(registry, f, indent=2)

print(f"✓ Saved: {registry_path}")

print(f"\n✅ Training complete! AUC: {auc:.4f}")
print("Run: python manage.py runserver")