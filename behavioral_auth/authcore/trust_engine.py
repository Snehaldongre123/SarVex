"""
authcore/trust_engine.py — Rule-Based Behavioral Trust Scorer
─────────────────────────────────────────────────────────────
This module computes a TRUST SCORE (0–100) for a login attempt
by comparing the current session's behavioral signals against
the user's historical baseline.

Design goals:
  - Pure functions: no DB calls, easily unit-testable
  - Structured for future ML swap-in (replace `compute_trust_score`
    with a model.predict() call without touching views.py)
  - Each signal contributes independently to a weighted total

Trust Score Anatomy:
  ┌──────────────────────────┬────────┐
  │ Signal                   │ Weight │
  ├──────────────────────────┼────────┤
  │ typing_speed             │  15    │
  │ key_hold_time            │  15    │
  │ mouse_velocity           │  10    │
  │ click_interval           │  10    │
  │ scroll_depth             │  10    │
  │ network_latency          │  10    │
  │ device_hash match        │  15    │
  │ location_hash match      │  10    │
  │ time_of_day proximity    │   5    │
  └──────────────────────────┴────────┘
  Total max = 100
"""

from django.conf import settings


# Signal weights — must sum to 100
SIGNAL_WEIGHTS = {
    'typing_speed':    15,
    'key_hold_time':   15,
    'mouse_velocity':  10,
    'click_interval':  10,
    'scroll_depth':    10,
    'network_latency': 10,
    'device_hash':     15,
    'location_hash':   10,
    'time_of_day':      5,
}


# ---------------------------------------------------------------------------
# Helper: Score a single numeric signal against its baseline value.
#
# Logic:
#   - Calculate the percentage deviation from the baseline average
#   - If deviation <= tolerance threshold → full points for that signal
#   - If deviation > threshold → score decreases proportionally
#   - Max penalty: the full weight of that signal (score = 0 for it)
# ---------------------------------------------------------------------------
def _score_numeric_signal(current: float, baseline_avg: float,
                           tolerance: float, weight: int) -> float:
    """
    Returns a partial score (0 to weight) for one numeric behavioral signal.

    Args:
        current:      The value measured in the current session.
        baseline_avg: Average of the user's past N sessions for this signal.
        tolerance:    Allowed % deviation before score starts dropping (0.0–1.0).
        weight:       Maximum points this signal can contribute.
    """
    if baseline_avg == 0:
        # No baseline yet — give benefit of the doubt, award full score
        return float(weight)

    deviation = abs(current - baseline_avg) / baseline_avg

    if deviation <= tolerance:
        # Within acceptable range → full score
        return float(weight)
    else:
        # Penalize proportionally beyond tolerance
        # e.g., 2× tolerance = 0 score; 1.5× tolerance = half score
        excess = deviation - tolerance
        penalty_ratio = min(excess / tolerance, 1.0)  # cap at 100% penalty
        return float(weight) * (1.0 - penalty_ratio)


# ---------------------------------------------------------------------------
# Helper: Score a hash-based signal (device or location).
# Binary: either hashes match (full score) or they don't (zero).
# ---------------------------------------------------------------------------
def _score_hash_signal(current_hash: str, baseline_hash: str, weight: int) -> float:
    """
    Returns full weight if hashes match, 0 otherwise.
    A new/unseen hash may indicate a different device or unusual location.
    """
    if not baseline_hash:
        # No prior hash stored — benefit of the doubt
        return float(weight)
    return float(weight) if current_hash == baseline_hash else 0.0


# ---------------------------------------------------------------------------
# Helper: Score time-of-day proximity.
# Uses circular distance so e.g. 23:00 and 01:00 are only 2 hours apart.
# ---------------------------------------------------------------------------
def _score_time_of_day(current_hour: int, baseline_hour: float, weight: int) -> float:
    """
    Scores how close the current login hour is to the user's typical hour.
    Max distance on a 24-hour clock is 12 hours.
    """
    if baseline_hour is None:
        return float(weight)

    # Circular distance (handles midnight boundary)
    diff = abs(current_hour - baseline_hour)
    circular_diff = min(diff, 24 - diff)

    # Scale: 0h diff = full score, 6h+ diff = 0 score
    score_ratio = max(0.0, 1.0 - (circular_diff / 6.0))
    return float(weight) * score_ratio


# ---------------------------------------------------------------------------
# Main Entry Point: compute_trust_score
#
# Called by the login view with:
#   - current_data: dict of behavioral signals from this login attempt
#   - baseline: dict of averages from the user's recent BehaviorLog entries
#               (computed in views.py from the last N logs)
#
# Returns an integer trust score from 0 to 100.
# ---------------------------------------------------------------------------
def compute_trust_score(current_data: dict, baseline: dict) -> int:
    """
    Compute a composite behavioral trust score by evaluating each signal
    against the user's established baseline.

    Args:
        current_data: Dict of behavioral features from the current session.
        baseline:     Dict of baseline averages from recent sessions.
                      If empty (new user), scores default to maximum.

    Returns:
        int: Trust score from 0 (definitely not the user) to 100 (perfect match).
    """
    config = settings.BEHAVIOR_CONFIG
    total_score = 0.0

    # --- Numeric signals: compared by % deviation ---
    numeric_signals = [
        ('typing_speed',    'TYPING_SPEED_TOLERANCE'),
        ('key_hold_time',   'KEY_HOLD_TOLERANCE'),
        ('mouse_velocity',  'MOUSE_VELOCITY_TOLERANCE'),
        ('click_interval',  'CLICK_INTERVAL_TOLERANCE'),
        ('scroll_depth',    'SCROLL_DEPTH_TOLERANCE'),
    ]

    for signal_name, tolerance_key in numeric_signals:
        current_val  = current_data.get(signal_name, 0)
        baseline_avg = baseline.get(signal_name, 0)
        tolerance    = config[tolerance_key]
        weight       = SIGNAL_WEIGHTS[signal_name]

        total_score += _score_numeric_signal(current_val, baseline_avg, tolerance, weight)

    # --- Network latency: hard cap (not percentage-based) ---
    latency        = current_data.get('network_latency', 0)
    max_latency    = config['MAX_NETWORK_LATENCY_MS']
    latency_weight = SIGNAL_WEIGHTS['network_latency']

    if latency <= max_latency:
        # Score proportionally: lower latency = better
        total_score += latency_weight * (1.0 - latency / max_latency)
    # else: 0 points (latency too high — unusual network or VPN)

    # --- Hash signals: binary match ---
    total_score += _score_hash_signal(
        current_data.get('device_hash', ''),
        baseline.get('device_hash', ''),
        SIGNAL_WEIGHTS['device_hash']
    )
    total_score += _score_hash_signal(
        current_data.get('location_hash', ''),
        baseline.get('location_hash', ''),
        SIGNAL_WEIGHTS['location_hash']
    )

    # --- Time of day: proximity scoring ---
    total_score += _score_time_of_day(
        current_data.get('time_of_day', 0),
        baseline.get('time_of_day'),
        SIGNAL_WEIGHTS['time_of_day']
    )

    return int(round(total_score))


# ---------------------------------------------------------------------------
# Compute Baseline from Recent Logs
#
# Averages numeric signals across the last N BehaviorLog entries.
# The most recent device_hash and location_hash are used for comparison.
# ---------------------------------------------------------------------------
def build_baseline(recent_logs) -> dict:
    """
    Build a behavioral baseline dict from a queryset of recent BehaviorLog objects.

    Args:
        recent_logs: QuerySet of BehaviorLog instances (most recent first).

    Returns:
        dict: Averaged signal values, or empty dict if no prior logs exist.
    """
    logs = list(recent_logs)

    if not logs:
        return {}  # New user — no baseline yet

    n = len(logs)

    baseline = {
        'typing_speed':    sum(l.typing_speed    for l in logs) / n,
        'key_hold_time':   sum(l.key_hold_time   for l in logs) / n,
        'mouse_velocity':  sum(l.mouse_velocity   for l in logs) / n,
        'click_interval':  sum(l.click_interval  for l in logs) / n,
        'scroll_depth':    sum(l.scroll_depth    for l in logs) / n,
        'network_latency': sum(l.network_latency for l in logs) / n,
        'time_of_day':     sum(l.time_of_day     for l in logs) / n,

        # Use the most recent hash as the expected fingerprint
        'device_hash':   logs[0].device_hash,
        'location_hash': logs[0].location_hash,
    }

    return baseline
