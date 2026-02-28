"""
NeuralAuth Views v4 — Adaptive behavioral authentication.
- 3-phase registration building multi-context identity profile
- Login with dynamic threshold, risk classification, challenge flow
- Full explainability on every decision
"""
import uuid
import logging
from datetime import datetime

from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from authcore.models import (
    User, BehaviorLog, RegistrationBehavior,
    CalibrationSession, UserBehaviorProfile, LoginRiskEvent
)
from authcore.serializers import RegistrationSerializer, LoginSerializer, ChallengeSerializer
from authcore.trust_engine import compute_trust_score
from authcore.profile_updater import (
    build_profile_from_calibration, compute_quality_score,
    update_profile_after_trusted_login, update_profile_after_failed_login
)
import authcore.ml_engine as ml_engine

logger = logging.getLogger(__name__)

# In-memory challenge store (use Redis/DB in production)
_pending_challenges = {}


class IndexView(TemplateView):
    template_name = 'prototype.html'


class RegisterView(APIView):
    """
    POST /api/auth/register/
    
    Accepts 3-phase calibration data and creates user + behavioral profile.
    """

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Create user
        try:
            user = User.objects.create_user(
                email=data['email'],
                username=data['username'],
                password=data['password'],
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Prepare phase features — inject device/location hash into calm baseline
        calm = data.get('calm_features') or {}
        cognitive = data.get('cognitive_features') or {}
        controlled = data.get('controlled_features') or {}

        # Ensure device/location hash is stored in baselines
        for feat_dict in [calm, cognitive, controlled]:
            if data.get('device_hash'):
                feat_dict['device_hash'] = data['device_hash']
            if data.get('location_hash'):
                feat_dict['location_hash'] = data['location_hash']

        # Save calibration sessions
        for phase, features in [('calm', calm), ('cognitive', cognitive), ('controlled', controlled)]:
            quality = compute_quality_score(features)
            CalibrationSession.objects.create(
                user=user, phase=phase, features=features,
                quality_score=quality,
                duration_ms=features.get('session_duration_ms', 0)
            )

        # Build behavioral profile
        profile = build_profile_from_calibration(user, calm, cognitive, controlled)

        # Create legacy RegistrationBehavior for backward compat
        try:
            RegistrationBehavior.objects.create(
                user=user,
                typing_speed=calm.get('typing_speed', 4),
                key_hold_time=calm.get('key_hold_time', 120),
                mouse_velocity=calm.get('mouse_velocity', 350),
                click_interval=calm.get('click_interval', 600),
                decision_time=calm.get('decision_time', 800),
                scroll_depth=calm.get('scroll_depth', 0),
                network_latency=calm.get('network_latency', 100),
                behavior_under_slowness=calm.get('behavior_under_slowness', 0.9),
                time_of_day=calm.get('time_of_day', 12),
                device_hash=data.get('device_hash', ''),
                location_hash=data.get('location_hash', ''),
            )
        except Exception:
            pass

        calm_quality = compute_quality_score(calm)
        cog_quality = compute_quality_score(cognitive)

        logger.info(f'User registered: {user.email} (conf:0.30 calm_q:{calm_quality:.2f})')

        return Response({
            'message': 'Registration successful',
            'user_id': str(user.id),
            'email': user.email,
            'calm_quality': round(calm_quality, 3),
            'cognitive_quality': round(cog_quality, 3),
            'identity_confidence': 0.3,
            'dynamic_threshold': 60.0,
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """
    POST /api/auth/login/

    Returns:
      200 → GRANTED (LOW risk)
      202 → CHALLENGED (MEDIUM risk)  + challenge_token
      401 → DENIED (HIGH risk)
    """

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data['email']

        # Find user
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal user existence — still compute score for logging
            return Response({
                'trust_score': 5,
                'risk_level': 'HIGH',
                'action': 'DENIED',
                'error': 'Authentication failed',
                'dynamic_threshold': 60.0,
                'breakdown': {},
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Load behavioral profile
        try:
            profile = user.behavior_profile
        except UserBehaviorProfile.DoesNotExist:
            profile = None

        # Load recent trusted logs (for consistency scoring)
        recent_logs = BehaviorLog.objects.filter(user=user, was_trusted=True).order_by('-created_at')[:5]

        # Compute trust score
        result = compute_trust_score(
            current_data=dict(data),
            user_profile=profile,
            recent_logs=list(recent_logs),
            ml_engine=ml_engine,
        )

        trust_score = result['trust_score']
        risk_level = result['risk_level']
        action = result['action']

        # Save behavior log
        BehaviorLog.objects.create(
            user=user,
            typing_speed=data['typing_speed'],
            key_hold_time=data['key_hold_time'],
            mouse_velocity=data['mouse_velocity'],
            click_interval=data['click_interval'],
            decision_time=data['decision_time'],
            scroll_depth=data['scroll_depth'],
            network_latency=data['network_latency'],
            behavior_under_slowness=data['behavior_under_slowness'],
            time_of_day=data['time_of_day'],
            iki_mean=data['iki_mean'],
            iki_std=data['iki_std'],
            hold_mean=data['hold_mean'],
            hold_std=data['hold_std'],
            mvel_mean=data['mvel_mean'],
            mvel_std=data['mvel_std'],
            lat_mean=data['lat_mean'],
            lat_jitter=data['lat_jitter'],
            slow_key_ratio=data['slow_key_ratio'],
            device_hash=data['device_hash'],
            location_hash=data['location_hash'],
            trust_score=trust_score,
            was_trusted=(action == 'GRANTED'),
        )

        # Save risk event
        LoginRiskEvent.objects.create(
            user=user,
            email_attempted=email,
            trust_score=trust_score,
            risk_level=risk_level,
            dynamic_threshold_used=result['dynamic_threshold'],
            confidence_at_time=result['confidence'],
            ml_score=result['breakdown'].get('ml_score', 0),
            context_score=result['breakdown'].get('context_score', 0),
            consistency_score=result['breakdown'].get('consistency_score', 0),
            calm_deviation=result['breakdown'].get('calm_deviation', 0),
            cognitive_deviation=result['breakdown'].get('cognitive_deviation', 0),
            device_matched=result.get('device_matched', False),
            location_matched=result.get('location_matched', False),
            time_anomaly=result.get('time_anomaly', False),
            action_taken=action,
            rejection_reasons=result.get('rejection_reasons', {}),
        )

        # Update profile
        if profile:
            if action == 'GRANTED':
                update_profile_after_trusted_login(profile, dict(data), trust_score)
            elif action == 'DENIED':
                update_profile_after_failed_login(profile)

        # Build response
        response_body = {
            'trust_score': trust_score,
            'risk_level': risk_level,
            'dynamic_threshold': result['dynamic_threshold'],
            'confidence': result['confidence'],
            'breakdown': result['breakdown'],
            'rejection_reasons': result.get('rejection_reasons', {}),
            'action': action,
        }

        if action == 'GRANTED':
            response_body['session_token'] = str(uuid.uuid4())
            response_body['message'] = 'Access granted'
            return Response(response_body, status=status.HTTP_200_OK)

        elif action == 'CHALLENGED':
            challenge_token = str(uuid.uuid4())
            _pending_challenges[challenge_token] = {
                'user_id': user.id,
                'email': email,
                'created_at': datetime.now().isoformat(),
                'profile_snapshot': {'threshold': result['dynamic_threshold'], 'score': trust_score}
            }
            response_body['challenge_token'] = challenge_token
            response_body['challenge_sentence'] = _get_challenge_sentence()
            response_body['message'] = 'Identity challenge required'
            return Response(response_body, status=202)

        else:  # DENIED
            response_body['message'] = 'Access denied — behavioral anomaly detected'
            return Response(response_body, status=status.HTTP_401_UNAUTHORIZED)


class VerifyChallengeView(APIView):
    """
    POST /api/auth/verify-challenge/
    Handle MEDIUM risk secondary verification.
    """

    def post(self, request):
        serializer = ChallengeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        challenge_token = data.get('challenge_token', '')
        email = data['email']

        # Validate challenge token
        challenge = _pending_challenges.get(challenge_token)
        if not challenge or challenge['email'] != email:
            return Response({'error': 'Invalid or expired challenge', 'trust_score': 10},
                          status=status.HTTP_401_UNAUTHORIZED)

        # Remove used token
        del _pending_challenges[challenge_token]

        try:
            user = User.objects.get(email=email)
            profile = user.behavior_profile
        except (User.DoesNotExist, UserBehaviorProfile.DoesNotExist):
            return Response({'error': 'User not found', 'trust_score': 5},
                          status=status.HTTP_401_UNAUTHORIZED)

        # Compare challenge typing behavior against baseline
        challenge_features = {
            'typing_speed': data.get('typing_speed', 0),
            'key_hold_time': data.get('key_hold_time', 120),
            'iki_mean': data.get('iki_mean', 200),
            'iki_std': data.get('iki_std', 50),
            'hold_mean': data.get('hold_mean', 120),
            'hold_std': data.get('hold_std', 30),
            'device_hash': data.get('device_hash', ''),
            'location_hash': data.get('location_hash', ''),
        }

        # Quick scoring: check if challenge typing matches calm baseline
        from authcore.trust_engine import deviation_score
        if profile and profile.calm_baseline:
            dev = deviation_score(challenge_features, profile.calm_baseline, max_pts=10)
            passed = dev >= 5.0  # At least 50% deviation match
        else:
            passed = True  # No baseline yet — give benefit of doubt

        if passed:
            # Grant and update profile
            new_score = challenge.get('profile_snapshot', {}).get('score', 60) + 10
            update_profile_after_trusted_login(profile, challenge_features, new_score)
            
            LoginRiskEvent.objects.create(
                user=user, email_attempted=email,
                trust_score=new_score, risk_level='LOW',
                action_taken='GRANTED',
                dynamic_threshold_used=profile.dynamic_threshold,
                confidence_at_time=profile.identity_confidence,
            )
            return Response({
                'message': 'Challenge passed. Access granted.',
                'trust_score': new_score,
                'session_token': str(uuid.uuid4()),
                'action': 'GRANTED',
            }, status=status.HTTP_200_OK)
        else:
            update_profile_after_failed_login(profile)
            return Response({
                'message': 'Challenge failed. Access denied.',
                'trust_score': 20,
                'action': 'DENIED',
            }, status=status.HTTP_401_UNAUTHORIZED)


class SaveBehaviorView(APIView):
    """POST /api/auth/behavior/save/ — Save a behavior snapshot."""

    def post(self, request):
        email = request.data.get('email')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        BehaviorLog.objects.create(
            user=user,
            typing_speed=request.data.get('typing_speed', 0),
            key_hold_time=request.data.get('key_hold_time', 120),
            mouse_velocity=request.data.get('mouse_velocity', 0),
            click_interval=request.data.get('click_interval', 600),
            decision_time=request.data.get('decision_time', 800),
            trust_score=request.data.get('trust_score', 0),
            was_trusted=request.data.get('was_trusted', False),
        )
        return Response({'saved': True})


class ProfileView(APIView):
    """GET /api/auth/profile/?email=... — Get user's behavioral profile analytics."""

    def get(self, request):
        email = request.query_params.get('email')
        try:
            user = User.objects.get(email=email)
            profile = user.behavior_profile
        except (User.DoesNotExist, UserBehaviorProfile.DoesNotExist):
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

        recent_events = LoginRiskEvent.objects.filter(user=user).order_by('-created_at')[:10]
        events_data = []
        for ev in recent_events:
            events_data.append({
                'trust_score': ev.trust_score,
                'risk_level': ev.risk_level,
                'action_taken': ev.action_taken,
                'confidence_at_time': ev.confidence_at_time,
                'created_at': ev.created_at.isoformat(),
            })

        return Response({
            'email': user.email,
            'identity_confidence': profile.identity_confidence,
            'dynamic_threshold': profile.dynamic_threshold,
            'login_count': profile.login_count,
            'trusted_login_count': profile.trusted_login_count,
            'consecutive_trusted': profile.consecutive_trusted,
            'consecutive_deviations': profile.consecutive_deviations,
            'typical_hours': profile.typical_hours,
            'recent_events': events_data,
        })


def _get_challenge_sentence():
    import random
    sentences = [
        "The behavioral system secures access through continuous identity verification.",
        "Each keystroke carries a unique signature that reveals the typist.",
        "Security without passwords relies on how people naturally interact.",
        "The rhythm of typing is as unique as a fingerprint to the system.",
        "Behavioral biometrics verify identity without storing sensitive data.",
    ]
    return random.choice(sentences)

import uuid
from authcore.models import LoginSession

def merge_phase_data(p1, p2, p3):
    def avg(a, b):
        return (a + b) / 2 if a and b else a or b or 0

    return {
        'typing_speed': avg(p1.get('typing_speed'), p3.get('typing_speed')),
        'key_hold_time': avg(p1.get('key_hold_time'), p3.get('key_hold_time')),
        'mouse_velocity': avg(p1.get('mouse_velocity'), p2.get('mouse_velocity')),
        'click_interval': avg(p1.get('click_interval'), p3.get('click_interval')),
        'decision_time': p3.get('decision_time', 0),
        'scroll_depth': p2.get('scroll_depth', 0),
        'network_latency': p1.get('network_latency', 0),
        'behavior_under_slowness': p1.get('behavior_under_slowness', 0),
        'time_of_day': p1.get('time_of_day', 12),
        'device_hash': p1.get('device_hash', ''),
        'location_hash': p1.get('location_hash', ''),
    }


class LoginStartView(APIView):
    def post(self, request):
        email = request.data.get('email')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=401)

        session = LoginSession.objects.create(user=user)

        return Response({
            'session_id': str(session.session_id),
            'next_phase': 1
        })


class LoginPhaseView(APIView):
    def post(self, request):
        session_id = request.data.get('session_id')
        phase = request.data.get('phase')
        features = request.data.get('features')

        try:
            session = LoginSession.objects.get(session_id=session_id)
        except LoginSession.DoesNotExist:
            return Response({'error': 'Invalid session'}, status=400)

        if phase == 1:
            session.phase1_data = features
        elif phase == 2:
            session.phase2_data = features
        elif phase == 3:
            session.phase3_data = features

        session.save()

        return Response({'next_phase': phase + 1})


class LoginCompleteView(APIView):
    def post(self, request):
        session_id = request.data.get('session_id')

        try:
            session = LoginSession.objects.get(session_id=session_id)
        except LoginSession.DoesNotExist:
            return Response({'error': 'Invalid session'}, status=400)

        merged = merge_phase_data(
            session.phase1_data or {},
            session.phase2_data or {},
            session.phase3_data or {}
        )

        user = session.user
        profile = getattr(user, 'behavior_profile', None)
        recent_logs = BehaviorLog.objects.filter(user=user, was_trusted=True).order_by('-created_at')[:5]

        result = compute_trust_score(
            current_data=merged,
            user_profile=profile,
            recent_logs=list(recent_logs),
            ml_engine=ml_engine,
        )

        session.completed = True
        session.save()

        return Response(result)