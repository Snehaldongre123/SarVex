"""
Profile Updater — Handles weighted learning after every session.
Prevents sudden drift. Grows confidence slowly. Adapts over time.
"""
import logging

logger = logging.getLogger(__name__)

LEARNING_RATE = 0.10       # 10% shift per trusted session
MAX_TYPICAL_HOURS = 10     # Remember last 10 login hours
CONFIDENCE_GROW = 0.05     # +5% per trusted login (decelerating)
CONFIDENCE_SHRINK = 0.10   # -10% per failed login
MIN_CONFIDENCE = 0.1
MAX_CONFIDENCE = 1.0


def weighted_avg_features(old_features: dict, new_features: dict, alpha=LEARNING_RATE) -> dict:
    """
    Slowly shift baseline toward new observations.
    alpha = learning rate (0.1 = 10% new data per session)
    """
    if not old_features:
        return new_features or {}
    if not new_features:
        return old_features

    result = dict(old_features)
    numeric_keys = [
        'typing_speed', 'key_hold_time', 'mouse_velocity', 'click_interval',
        'decision_time', 'scroll_depth', 'network_latency', 'behavior_under_slowness',
        'iki_mean', 'iki_std', 'hold_mean', 'hold_std', 'mvel_mean', 'mvel_std',
        'lat_mean', 'lat_jitter',
    ]
    for key in numeric_keys:
        if key in new_features and key in old_features:
            old_val = old_features[key]
            new_val = new_features[key]
            # Only update if new value is plausible (not 0 for most signals)
            if new_val > 0 or key in ('scroll_depth', 'slow_key_ratio'):
                result[key] = (1 - alpha) * old_val + alpha * new_val

    # Keep hashes from original registration (don't drift on these)
    for key in ('device_hash', 'location_hash'):
        if key in old_features:
            result[key] = old_features[key]

    return result


def update_profile_after_trusted_login(profile, current_data: dict, trust_score: int):
    """Call after a GRANTED session. Updates baseline + confidence."""
    # Update calm baseline using weighted moving average
    if profile.calm_baseline and current_data:
        profile.calm_baseline = weighted_avg_features(profile.calm_baseline, current_data)

    # Update cognitive baseline if data available
    if profile.cognitive_baseline and current_data:
        profile.cognitive_baseline = weighted_avg_features(
            profile.cognitive_baseline, current_data, alpha=LEARNING_RATE * 0.5
        )

    # Grow confidence (decelerating — harder to grow near 1.0)
    conf = profile.identity_confidence
    growth = CONFIDENCE_GROW * (1 - conf)
    profile.identity_confidence = min(MAX_CONFIDENCE, conf + growth)

    # Update streaks
    profile.trusted_login_count += 1
    profile.consecutive_trusted += 1
    profile.consecutive_deviations = 0
    profile.login_count += 1

    # Learn typical login hours
    from datetime import datetime
    hour = datetime.now().hour
    if hour not in profile.typical_hours:
        profile.typical_hours.append(hour)
        # Keep only last MAX_TYPICAL_HOURS
        if len(profile.typical_hours) > MAX_TYPICAL_HOURS:
            profile.typical_hours = profile.typical_hours[-MAX_TYPICAL_HOURS:]

    # Recalculate dynamic threshold
    from authcore.trust_engine import compute_dynamic_threshold
    profile.dynamic_threshold = compute_dynamic_threshold(profile)

    profile.save()
    logger.info(f'Profile updated (trusted): conf={profile.identity_confidence:.3f} thr={profile.dynamic_threshold:.1f}')


def update_profile_after_failed_login(profile):
    """Call after a DENIED session. Shrinks confidence, raises sensitivity."""
    # Shrink confidence
    profile.identity_confidence = max(
        MIN_CONFIDENCE,
        profile.identity_confidence - CONFIDENCE_SHRINK
    )

    # Update streaks
    profile.consecutive_deviations += 1
    profile.consecutive_trusted = 0
    profile.login_count += 1

    # Recalculate dynamic threshold (will rise due to deviations)
    from authcore.trust_engine import compute_dynamic_threshold
    profile.dynamic_threshold = compute_dynamic_threshold(profile)

    profile.save()
    logger.warning(f'Profile updated (failed): conf={profile.identity_confidence:.3f} thr={profile.dynamic_threshold:.1f} devs={profile.consecutive_deviations}')


def build_profile_from_calibration(user, calm_features: dict, cognitive_features: dict, controlled_features: dict):
    """
    Build initial UserBehaviorProfile from 3-phase registration data.
    Called once after complete registration.
    """
    from authcore.models import UserBehaviorProfile

    profile, created = UserBehaviorProfile.objects.get_or_create(user=user)

    if calm_features:
        profile.calm_baseline = calm_features
    if cognitive_features:
        profile.cognitive_baseline = cognitive_features
    if controlled_features:
        profile.controlled_baseline = controlled_features

    profile.identity_confidence = 0.3
    profile.dynamic_threshold = 60.0
    profile.typical_hours = []
    profile.save()
    return profile


def compute_quality_score(features: dict) -> float:
    """
    Rate how complete and high-quality a captured feature set is.
    Returns 0.0 - 1.0
    """
    if not features:
        return 0.0

    checks = [
        features.get('typing_speed', 0) > 0,
        features.get('key_hold_time', 0) > 0,
        features.get('iki_mean', 0) > 0,
        features.get('iki_std', 0) > 0,
        features.get('hold_mean', 0) > 0,
        features.get('key_count', 0) >= 5,
        features.get('session_duration_ms', 0) >= 2000,
        features.get('mouse_count', 0) >= 3,
        features.get('device_hash', '') != '',
    ]
    return sum(checks) / len(checks)
