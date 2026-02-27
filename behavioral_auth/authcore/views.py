"""
authcore/views.py — API View Functions
─────────────────────────────────────
Three endpoints power the behavioral auth system:

  POST /api/auth/register/       → Create a new user (no password)
  POST /api/auth/login/          → Authenticate via behavioral signals
  POST /api/auth/behavior/save/  → Save a trusted session's behavioral data

Flow diagram:
  Frontend collects signals → sends to /login/ → trust score computed
  → if score >= threshold → session token issued + behavior saved
  → if score < threshold → 401 Unauthorized
"""

import uuid
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import User, BehaviorLog
from .serializers import (
    UserRegistrationSerializer,
    LoginSerializer,
    BehaviorDataSerializer,
    UserResponseSerializer,
)
from .trust_engine import compute_trust_score, build_baseline


# ---------------------------------------------------------------------------
# Helper: Generate a simple session token
# In production, replace this with JWT (djangorestframework-simplejwt)
# or Django's session framework.
# ---------------------------------------------------------------------------
def _generate_session_token() -> str:
    """Generate a UUID4-based session token (good enough for hackathon demo)."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# VIEW: register_user
# POST /api/auth/register/
#
# Creates a new user account. No password is ever accepted or stored.
# On first login, the system has no baseline — it trusts the first session
# and uses it to build the behavioral profile.
# ---------------------------------------------------------------------------
@api_view(['POST'])
def register_user(request):
    """
    Register a new user without a password.

    Expected JSON:
        {
            "email": "user@example.com",
            "username": "johndoe"
        }

    Returns:
        201 Created  → user object
        400 Bad Request → validation errors
    """
    serializer = UserRegistrationSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {'error': 'Invalid registration data.', 'details': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if email or username already taken
    email    = serializer.validated_data['email']
    username = serializer.validated_data['username']

    if User.objects.filter(email=email).exists():
        return Response(
            {'error': 'An account with this email already exists.'},
            status=status.HTTP_409_CONFLICT
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {'error': 'This username is already taken.'},
            status=status.HTTP_409_CONFLICT
        )

    # Create user — no password is set (set_unusable_password called in manager)
    user = User.objects.create_user(email=email, username=username)

    return Response(
        {
            'message': 'Account created successfully. Your first login will build your behavioral profile.',
            'user': UserResponseSerializer(user).data,
        },
        status=status.HTTP_201_CREATED
    )


# ---------------------------------------------------------------------------
# VIEW: login_user
# POST /api/auth/login/
#
# Core of the system. Receives behavioral signals alongside the email,
# computes a trust score against historical baseline, and either:
#   - Issues a session token (trusted)
#   - Returns 401 (untrusted)
# ---------------------------------------------------------------------------
@api_view(['POST'])
def login_user(request):
    """
    Authenticate a user using behavioral signals instead of a password.

    Expected JSON:
        {
            "email": "user@example.com",
            "behavior_data": {
                "typing_speed": 4.2,
                "key_hold_time": 112.5,
                "mouse_velocity": 380.0,
                "click_interval": 620.0,
                "scroll_depth": 0.65,
                "network_latency": 45.0,
                "device_hash": "a3f1...64 char hex...",
                "location_hash": "9c2b...64 char hex...",
                "time_of_day": 14
            }
        }

    Returns:
        200 OK          → session token + trust score
        401 Unauthorized → trust score below threshold
        404 Not Found   → email not registered
        400 Bad Request → validation errors
    """
    serializer = LoginSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {'error': 'Invalid request data.', 'details': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    email         = serializer.validated_data['email']
    behavior_data = serializer.validated_data['behavior_data']

    # --- Step 1: Find the user ---
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Don't reveal whether email exists — return same 401 for security
        return Response(
            {'error': 'Authentication failed. Please check your credentials.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # --- Step 2: Load behavioral baseline (last N trusted sessions) ---
    baseline_count = settings.BEHAVIOR_CONFIG['BASELINE_LOG_COUNT']
    recent_logs    = BehaviorLog.objects.filter(
        user=user,
        was_trusted=True   # Only use logs from sessions we previously trusted
    ).order_by('-created_at')[:baseline_count]

    baseline = build_baseline(recent_logs)

    # --- Step 3: Compute trust score ---
    trust_score = compute_trust_score(behavior_data, baseline)
    threshold   = settings.BEHAVIOR_CONFIG['TRUST_SCORE_THRESHOLD']

    is_trusted = trust_score >= threshold

    # --- Step 4: Save this attempt as a BehaviorLog (win or fail) ---
    log = BehaviorLog.objects.create(
        user            = user,
        typing_speed    = behavior_data['typing_speed'],
        key_hold_time   = behavior_data['key_hold_time'],
        mouse_velocity  = behavior_data['mouse_velocity'],
        click_interval  = behavior_data['click_interval'],
        scroll_depth    = behavior_data['scroll_depth'],
        network_latency = behavior_data['network_latency'],
        device_hash     = behavior_data['device_hash'],
        location_hash   = behavior_data['location_hash'],
        time_of_day     = behavior_data['time_of_day'],
        was_trusted     = is_trusted,
        trust_score     = trust_score,
    )

    # --- Step 5: Return result ---
    if not is_trusted:
        return Response(
            {
                'error': 'Behavioral authentication failed. Access denied.',
                'trust_score': trust_score,
                'threshold': threshold,
                'hint': 'Your behavioral patterns did not match your profile.',
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Update last login timestamp
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    # Issue session token (replace with JWT in production)
    session_token = _generate_session_token()

    return Response(
        {
            'message': 'Behavioral authentication successful.',
            'session_token': session_token,
            'trust_score': trust_score,
            'threshold': threshold,
            'user': UserResponseSerializer(user).data,
        },
        status=status.HTTP_200_OK
    )


# ---------------------------------------------------------------------------
# VIEW: save_behavior
# POST /api/auth/behavior/save/
#
# Allows the frontend to save behavioral data collected AFTER login
# (e.g., during a browsing session) to continuously refine the user's profile.
# This is the hook for future continuous authentication.
# ---------------------------------------------------------------------------
@api_view(['POST'])
def save_behavior(request):
    """
    Save behavioral data for an authenticated user's active session.
    Useful for building richer behavioral profiles over time.

    In production: protect this endpoint with your session token middleware.

    Expected JSON:
        {
            "email": "user@example.com",
            "behavior_data": { ... same fields as login ... }
        }

    Returns:
        201 Created  → confirmation + log ID
        400 Bad Request → validation errors
    """
    # Extract and validate email
    email = request.data.get('email')
    if not email:
        return Response(
            {'error': 'Email is required to save behavior.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Validate behavioral data
    behavior_serializer = BehaviorDataSerializer(data=request.data.get('behavior_data', {}))

    if not behavior_serializer.is_valid():
        return Response(
            {'error': 'Invalid behavior data.', 'details': behavior_serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = behavior_serializer.validated_data

    # Save the behavioral snapshot — mark as trusted (it's a post-auth save)
    log = BehaviorLog.objects.create(
        user            = user,
        typing_speed    = data['typing_speed'],
        key_hold_time   = data['key_hold_time'],
        mouse_velocity  = data['mouse_velocity'],
        click_interval  = data['click_interval'],
        scroll_depth    = data['scroll_depth'],
        network_latency = data['network_latency'],
        device_hash     = data['device_hash'],
        location_hash   = data['location_hash'],
        time_of_day     = data['time_of_day'],
        was_trusted     = True,   # This data improves the baseline
        trust_score     = 100,    # Assume full trust for post-login saves
    )

    return Response(
        {
            'message': 'Behavioral data saved successfully.',
            'log_id': str(log.id),
        },
        status=status.HTTP_201_CREATED
    )
