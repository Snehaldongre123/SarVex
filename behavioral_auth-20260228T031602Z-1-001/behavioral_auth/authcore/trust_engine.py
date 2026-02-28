"""
Trust Engine v4 — Adaptive, Z-score based, multi-context behavioral scoring.
No static threshold. Fully dynamic per-user.
"""
import math
import logging

logger = logging.getLogger(__name__)

# Feature weights for final trust score
WEIGHTS = {
    'ml':          0.40,
    'calm_dev':    0.20,
    'cognitive_dev': 0.15,
    'context':     0.15,
    'consistency': 0.10,
}

MAX_POINTS = {
    'ml': 75,
    'calm_dev': 10,
    'cognitive_dev': 8,
    'context': 17,    # device(8) + location(5) + time(4)
    'consistency': 10,
}

def zscore(value, mean, std, clamp=3.0):
    """Compute Z-score — how many std devs away from baseline."""
    if std < 0.001:
        std = max(abs(mean) * 0.15, 5.0)
    z = abs(value - mean) / std
    return min(z, clamp)

def deviation_score(current, baseline, max_pts=10):
    """
    Compare current feature dict to baseline dict.
    Returns score 0→max_pts. Lower deviation = higher score.
    """
    if not baseline or not current:
        return max_pts * 0.5  # neutral if no baseline yet

    features = ['typing_speed', 'key_hold_time', 'mouse_velocity',
                'click_interval', 'decision_time', 'iki_mean', 'iki_std',
                'hold_mean', 'hold_std', 'mvel_mean']
    
    scores = []
    for feat in features:
        if feat not in current or feat not in baseline:
            continue
        cv = current.get(feat, 0)
        bv = baseline.get(feat, 0)
        std_key = feat.replace('_mean','_std') if '_mean' not in feat else feat+'_std'
        std = baseline.get(std_key, abs(bv)*0.2 or 20)
        z = zscore(cv, bv, std)
        # Sigmoid to map Z-score to 0-1 (z=0 → 1.0, z=3 → 0.05)
        score = 1.0 / (1 + math.exp(z - 1.0))
        scores.append(score)
    
    if not scores:
        return max_pts * 0.5
    
    avg = sum(scores) / len(scores)
    return round(avg * max_pts, 2)

def compute_context_score(current_data, profile):
    """
    Device hash, location hash, time-of-day pattern.
    Returns 0-17.
    """
    score = 0

    # Device hash (8 points)
    if profile and profile.calm_baseline:
        reg_device = profile.calm_baseline.get('device_hash', '')
        cur_device = current_data.get('device_hash', '')
        if reg_device and cur_device and reg_device == cur_device:
            score += 8

    # Location hash (5 points)
    if profile and profile.calm_baseline:
        reg_loc = profile.calm_baseline.get('location_hash', '')
        cur_loc = current_data.get('location_hash', '')
        if reg_loc and cur_loc and reg_loc == cur_loc:
            score += 5

    # Time of day (4 points)
    typical_hours = profile.typical_hours if profile else []
    cur_hour = int(current_data.get('time_of_day', 12))
    if not typical_hours:
        score += 2  # neutral for new user
    else:
        # Check if within 2 hours of any typical hour
        nearby = any(abs(cur_hour - h) <= 2 or abs(cur_hour - h) >= 22 for h in typical_hours)
        score += 4 if nearby else 0

    return score

def compute_consistency_score(recent_logs, max_pts=10):
    """
    How consistent has this user been across recent sessions?
    Low variance in past trust scores = high consistency = bonus.
    """
    if not recent_logs or len(recent_logs) < 2:
        return max_pts * 0.6  # generous for new users

    scores = [log.trust_score for log in recent_logs[:5]]
    mean = sum(scores) / len(scores)
    variance = sum((s - mean)**2 for s in scores) / len(scores)
    std = math.sqrt(variance)

    # std < 5 = very consistent, std > 25 = inconsistent
    consistency = max(0, 1 - (std / 25))
    return round(consistency * max_pts, 2)

def compute_trust_score(current_data, user_profile, recent_logs, ml_engine=None):
    """
    Main scoring function.
    
    Returns dict: {
        trust_score: int (0-100),
        risk_level: LOW|MEDIUM|HIGH,
        dynamic_threshold: float,
        breakdown: {...},
        action: GRANTED|CHALLENGED|DENIED,
        rejection_reasons: {...}
    }
    """
    # 1. ML Score (0-75)
    ml_score = 37  # neutral fallback
    if ml_engine:
        try:
            feature_vector = [
                current_data.get('typing_speed', 4),
                current_data.get('key_hold_time', 120),
                current_data.get('mouse_velocity', 350),
                current_data.get('click_interval', 600),
                current_data.get('decision_time', 800),
                current_data.get('scroll_depth', 0),
                current_data.get('network_latency', 100),
                current_data.get('behavior_under_slowness', 0.9),
                current_data.get('time_of_day', 12),
            ]
            prob = ml_engine.predict_proba(feature_vector)
            ml_score = round(prob * 75, 2)
        except Exception as e:
            logger.warning(f'ML engine error: {e}')

    # 2. Deviation scores from multi-context baselines
    calm_dev = 0
    cognitive_dev = 0
    if user_profile:
        calm_dev = deviation_score(current_data, user_profile.calm_baseline, max_pts=10)
        cognitive_dev = deviation_score(current_data, user_profile.cognitive_baseline, max_pts=8)
    else:
        calm_dev = 5.0
        cognitive_dev = 4.0

    # 3. Context score (device + location + time)
    context_score = compute_context_score(current_data, user_profile)

    # 4. Consistency score
    consistency_score = compute_consistency_score(recent_logs)

    # 5. Final weighted trust score
    trust_score = round(
        ml_score * WEIGHTS['ml'] +              # 40% of 75pts
        calm_dev * WEIGHTS['calm_dev'] * 10 +   # 20% of 10pts
        cognitive_dev * WEIGHTS['cognitive_dev'] * 12.5 +
        context_score * WEIGHTS['context'] * (100/17) * 0.15 +
        consistency_score * WEIGHTS['consistency'] * 10
    )

    # Simpler, more readable formula:
    trust_score = round(ml_score + calm_dev + cognitive_dev + context_score + consistency_score)
    trust_score = max(0, min(100, trust_score))

    # 6. Dynamic threshold
    threshold = compute_dynamic_threshold(user_profile)

    # 7. Risk classification
    gap = trust_score - threshold
    if gap > 20:
        risk_level = 'LOW'
        action = 'GRANTED'
    elif gap >= 0:
        risk_level = 'MEDIUM'
        action = 'CHALLENGED'
    else:
        risk_level = 'HIGH'
        action = 'DENIED'

    # 8. Rejection reasons (explainability)
    rejection_reasons = {}
    if user_profile and user_profile.calm_baseline:
        baseline = user_profile.calm_baseline
        for feat, label in [
            ('mouse_velocity', 'mouse velocity'),
            ('decision_time', 'decision time'),
            ('typing_speed', 'typing speed'),
            ('iki_std', 'typing rhythm variance'),
        ]:
            cv = current_data.get(feat, 0)
            bv = baseline.get(feat, cv)
            std = baseline.get(feat+'_std', abs(bv)*0.2 or 20)
            z = zscore(cv, bv, std)
            if z > 2.0:
                rejection_reasons[feat] = f'{z:.1f}x deviation from your baseline'

    # Device/location
    if context_score < 8:
        if not current_data.get('device_hash') or \
           current_data.get('device_hash') != (user_profile.calm_baseline.get('device_hash','') if user_profile and user_profile.calm_baseline else ''):
            rejection_reasons['device_hash'] = 'Unrecognized device'
    
    if context_score < 13:
        rejection_reasons.setdefault('location', 'Unfamiliar location or time pattern')

    confidence = user_profile.identity_confidence if user_profile else 0.3

    return {
        'trust_score': trust_score,
        'risk_level': risk_level,
        'dynamic_threshold': round(threshold, 1),
        'action': action,
        'confidence': round(confidence, 3),
        'breakdown': {
            'ml_score': round(ml_score, 1),
            'calm_deviation': round(calm_dev, 1),
            'cognitive_deviation': round(cognitive_dev, 1),
            'context_score': round(context_score, 1),
            'consistency_score': round(consistency_score, 1),
            'threshold_used': round(threshold, 1),
            'confidence': round(confidence, 2),
        },
        'rejection_reasons': rejection_reasons,
        'device_matched': context_score >= 8,
        'location_matched': context_score >= 13,
        'time_anomaly': context_score < 13,
    }


def compute_dynamic_threshold(profile):
    """
    Compute per-user dynamic threshold.
    
    Base = 60
    - confidence adjustment: lowers threshold for consistent users
    + deviation penalty: raises threshold if suspicious pattern
    + time anomaly: small raise if unusual hour
    
    Range: 40 to 85
    """
    if not profile:
        return 60.0

    base = 60.0

    # Confidence reduces friction (max -15)
    conf_adj = profile.identity_confidence * 15

    # Consecutive deviations raise sensitivity (max +25)
    dev_adj = min(25, profile.consecutive_deviations * 5)

    threshold = base - conf_adj + dev_adj

    return max(40.0, min(85.0, threshold))
