from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
import uuid

class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, username, password, **extra_fields)


class User(AbstractBaseUser):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    objects = UserManager()

    def has_perm(self, perm, obj=None): return self.is_superuser
    def has_module_perms(self, app_label): return self.is_superuser

    class Meta:
        db_table = 'auth_user'


class RegistrationBehavior(models.Model):
    """Legacy — kept for backward compat. New system uses UserBehaviorProfile."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='registration_behavior')
    typing_speed = models.FloatField(default=0)
    key_hold_time = models.FloatField(default=0)
    mouse_velocity = models.FloatField(default=0)
    click_interval = models.FloatField(default=0)
    decision_time = models.FloatField(default=0)
    scroll_depth = models.FloatField(default=0)
    network_latency = models.FloatField(default=0)
    behavior_under_slowness = models.FloatField(default=1.0)
    time_of_day = models.FloatField(default=12)
    device_hash = models.CharField(max_length=64, blank=True, default='')
    location_hash = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'registration_behavior'


class BehaviorLog(models.Model):
    """Records every login session with full signal snapshot."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='behavior_logs')
    typing_speed = models.FloatField(default=0)
    key_hold_time = models.FloatField(default=0)
    mouse_velocity = models.FloatField(default=0)
    click_interval = models.FloatField(default=0)
    decision_time = models.FloatField(default=0)
    scroll_depth = models.FloatField(default=0)
    network_latency = models.FloatField(default=0)
    behavior_under_slowness = models.FloatField(default=1.0)
    time_of_day = models.FloatField(default=12)
    # Micro features
    iki_mean = models.FloatField(default=200)
    iki_std = models.FloatField(default=50)
    hold_mean = models.FloatField(default=120)
    hold_std = models.FloatField(default=30)
    mvel_mean = models.FloatField(default=300)
    mvel_std = models.FloatField(default=100)
    lat_mean = models.FloatField(default=100)
    lat_jitter = models.FloatField(default=20)
    slow_key_ratio = models.FloatField(default=0)
    device_hash = models.CharField(max_length=256, blank=True, default='')
    location_hash = models.CharField(max_length=256, blank=True, default='')
    trust_score = models.IntegerField(default=0)
    was_trusted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'behavior_log'
        ordering = ['-created_at']


class CalibrationSession(models.Model):
    """Stores one phase of the 3-phase registration calibration."""
    PHASE_CHOICES = [
        ('calm', 'Calm Typing'),
        ('cognitive', 'Cognitive Typing'),
        ('controlled', 'Controlled Typing'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calibration_sessions')
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES)
    features = models.JSONField(default=dict)  # Full feature dict for this phase
    quality_score = models.FloatField(default=0.5)  # 0-1, completeness of capture
    duration_ms = models.IntegerField(default=0)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'calibration_session'
        ordering = ['-captured_at']


class UserBehaviorProfile(models.Model):
    """
    The evolving identity fingerprint.
    Stores multi-context baselines and grows smarter with each login.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='behavior_profile')

    # Multi-context baselines (JSON feature dicts)
    calm_baseline = models.JSONField(default=dict)
    cognitive_baseline = models.JSONField(default=dict)
    controlled_baseline = models.JSONField(default=dict)

    # Identity confidence (0.1 → 1.0)
    # Starts at 0.3, grows with trusted logins, shrinks on failures
    identity_confidence = models.FloatField(default=0.3)

    # Dynamic threshold (40 → 85)
    # Starts at 60, lowers for consistent users, raises for suspicious
    dynamic_threshold = models.FloatField(default=60.0)

    # Login counts
    login_count = models.IntegerField(default=0)
    trusted_login_count = models.IntegerField(default=0)
    consecutive_trusted = models.IntegerField(default=0)
    consecutive_deviations = models.IntegerField(default=0)

    # Learned time patterns (list of hours 0-23)
    typical_hours = models.JSONField(default=list)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_behavior_profile'

    def __str__(self):
        return f'{self.user.email} — conf:{self.identity_confidence:.2f} thr:{self.dynamic_threshold:.1f}'


class LoginRiskEvent(models.Model):
    """Full audit log of every authentication decision."""
    ACTION_CHOICES = [
        ('GRANTED', 'Granted'),
        ('CHALLENGED', 'Challenged'),
        ('DENIED', 'Denied'),
    ]
    RISK_CHOICES = [
        ('LOW', 'Low Risk'),
        ('MEDIUM', 'Medium Risk'),
        ('HIGH', 'High Risk'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='risk_events', null=True, blank=True)
    email_attempted = models.EmailField(blank=True)

    trust_score = models.IntegerField(default=0)
    risk_level = models.CharField(max_length=10, choices=RISK_CHOICES, default='HIGH')
    dynamic_threshold_used = models.FloatField(default=60.0)
    confidence_at_time = models.FloatField(default=0.3)

    # Score breakdown
    ml_score = models.FloatField(default=0)
    context_score = models.FloatField(default=0)
    consistency_score = models.FloatField(default=0)
    calm_deviation = models.FloatField(default=0)
    cognitive_deviation = models.FloatField(default=0)

    device_matched = models.BooleanField(default=False)
    location_matched = models.BooleanField(default=False)
    time_anomaly = models.BooleanField(default=False)

    action_taken = models.CharField(max_length=15, choices=ACTION_CHOICES, default='DENIED')

    # Explainability
    rejection_reasons = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'login_risk_event'
        ordering = ['-created_at']
class LoginSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session_id = models.UUIDField(default=uuid.uuid4, unique=True)
    phase1_data = models.JSONField(null=True, blank=True)
    phase2_data = models.JSONField(null=True, blank=True)
    phase3_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)