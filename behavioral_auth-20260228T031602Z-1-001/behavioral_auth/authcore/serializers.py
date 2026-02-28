from rest_framework import serializers
from authcore.models import User, BehaviorLog, RegistrationBehavior


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6, write_only=True)
    
    # Phase features
    calm_features = serializers.DictField(required=False, allow_null=True, default=None)
    cognitive_features = serializers.DictField(required=False, allow_null=True, default=None)
    controlled_features = serializers.DictField(required=False, allow_null=True, default=None)
    cognitive_text = serializers.CharField(required=False, allow_blank=True, default='')
    device_hash = serializers.CharField(required=False, allow_blank=True, default='')
    location_hash = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('Email already registered.')
        return value.lower()

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Username already taken.')
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    # Computed behavioral features
    typing_speed = serializers.FloatField(required=False, default=0)
    key_hold_time = serializers.FloatField(required=False, default=120)
    mouse_velocity = serializers.FloatField(required=False, default=0)
    click_interval = serializers.FloatField(required=False, default=600)
    decision_time = serializers.FloatField(required=False, default=800)
    scroll_depth = serializers.FloatField(required=False, default=0)
    network_latency = serializers.FloatField(required=False, default=100)
    behavior_under_slowness = serializers.FloatField(required=False, default=0.9)
    time_of_day = serializers.FloatField(required=False, default=12)
    # Micro features
    iki_mean = serializers.FloatField(required=False, default=200)
    iki_std = serializers.FloatField(required=False, default=50)
    hold_mean = serializers.FloatField(required=False, default=120)
    hold_std = serializers.FloatField(required=False, default=30)
    mvel_mean = serializers.FloatField(required=False, default=300)
    mvel_std = serializers.FloatField(required=False, default=100)
    lat_mean = serializers.FloatField(required=False, default=100)
    lat_jitter = serializers.FloatField(required=False, default=20)
    lat_probes = serializers.IntegerField(required=False, default=0)
    slow_key_ratio = serializers.FloatField(required=False, default=0)
    device_hash = serializers.CharField(required=False, allow_blank=True, default='')
    location_hash = serializers.CharField(required=False, allow_blank=True, default='')
    key_count = serializers.IntegerField(required=False, default=0)
    mouse_count = serializers.IntegerField(required=False, default=0)
    session_duration_ms = serializers.IntegerField(required=False, default=0)


class ChallengeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    challenge_token = serializers.CharField(required=False, allow_blank=True, default='')
    challenge_text = serializers.CharField(required=False, allow_blank=True, default='')
    # Re-use all behavioral fields
    typing_speed = serializers.FloatField(required=False, default=0)
    key_hold_time = serializers.FloatField(required=False, default=120)
    mouse_velocity = serializers.FloatField(required=False, default=0)
    click_interval = serializers.FloatField(required=False, default=600)
    decision_time = serializers.FloatField(required=False, default=800)
    iki_mean = serializers.FloatField(required=False, default=200)
    iki_std = serializers.FloatField(required=False, default=50)
    hold_mean = serializers.FloatField(required=False, default=120)
    hold_std = serializers.FloatField(required=False, default=30)
    device_hash = serializers.CharField(required=False, allow_blank=True, default='')
    location_hash = serializers.CharField(required=False, allow_blank=True, default='')


class BehaviorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BehaviorLog
        fields = '__all__'
