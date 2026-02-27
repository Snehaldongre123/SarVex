"""
authcore/serializers.py — Request/Response data validation
DRF serializers handle incoming JSON, validate fields, and
convert model instances to JSON for responses.
"""

from rest_framework import serializers
from .models import User, BehaviorLog


# ---------------------------------------------------------------------------
# User Registration Serializer
# Validates the fields needed to create a new user account.
# ---------------------------------------------------------------------------
class UserRegistrationSerializer(serializers.ModelSerializer):

    class Meta:
        model  = User
        fields = ['email', 'username']
        extra_kwargs = {
            'email':    {'required': True},
            'username': {'required': True, 'min_length': 3, 'max_length': 50},
        }

    def validate_username(self, value):
        """Usernames must be alphanumeric + underscores only."""
        if not value.replace('_', '').isalnum():
            raise serializers.ValidationError(
                'Username may only contain letters, numbers, and underscores.'
            )
        return value.lower()


# ---------------------------------------------------------------------------
# Behavior Data Serializer
# Validates the behavioral feature vector sent by the frontend.
# Used by both login_user and save_behavior endpoints.
# ---------------------------------------------------------------------------
class BehaviorDataSerializer(serializers.Serializer):

    # Keyboard signals
    typing_speed   = serializers.FloatField(min_value=0)
    key_hold_time  = serializers.FloatField(min_value=0)

    # Mouse signals
    mouse_velocity = serializers.FloatField(min_value=0)
    click_interval = serializers.FloatField(min_value=0)

    # Scroll signal (0.0 = top of page, 1.0 = bottom)
    scroll_depth   = serializers.FloatField(min_value=0.0, max_value=1.0)

    # Network
    network_latency = serializers.FloatField(min_value=0)

    # Hashed fingerprints — must be 64-char hex strings (SHA-256)
    device_hash   = serializers.CharField(min_length=64, max_length=64)
    location_hash = serializers.CharField(min_length=64, max_length=64)

    # Hour of day sent from client (0–23)
    time_of_day   = serializers.IntegerField(min_value=0, max_value=23)


# ---------------------------------------------------------------------------
# Login Request Serializer
# Login only needs an email identifier + behavioral data.
# No password field — ever.
# ---------------------------------------------------------------------------
class LoginSerializer(serializers.Serializer):
    email         = serializers.EmailField(required=True)
    behavior_data = BehaviorDataSerializer(required=True)


# ---------------------------------------------------------------------------
# User Response Serializer (safe fields only for API responses)
# ---------------------------------------------------------------------------
class UserResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'email', 'username', 'created_at']
