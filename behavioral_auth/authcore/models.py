"""
authcore/models.py
Defines:
- Custom passwordless User model
- BehaviorLog model storing feature vectors
"""

import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


# ------------------------------------------------------------------
# USER MANAGER
# ------------------------------------------------------------------
class UserManager(BaseUserManager):

    def create_user(self, email, username, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not username:
            raise ValueError("Username is required")

        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)

        user.set_unusable_password()  # Ensure no password usage
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, username, **extra_fields)


# ------------------------------------------------------------------
# USER MODEL (PASSWORDLESS)
# ------------------------------------------------------------------
class User(AbstractBaseUser, PermissionsMixin):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True)

    created_at = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.username} <{self.email}>"

    # Disable password usage completely
    def set_password(self, raw_password):
        raise NotImplementedError("Password-based authentication is disabled.")

    def check_password(self, raw_password):
        return False

    # Get recent trusted sessions for baseline
    def get_behavior_baseline(self, limit=5):
        return self.behavior_logs.filter(was_trusted=True)[:limit]


# ------------------------------------------------------------------
# BEHAVIOR LOG MODEL
# ------------------------------------------------------------------
class BehaviorLog(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="behavior_logs"
    )

    # Keyboard
    typing_speed = models.FloatField()
    key_hold_time = models.FloatField()

    # Mouse
    mouse_velocity = models.FloatField()
    click_interval = models.FloatField()

    # Scroll
    scroll_depth = models.FloatField()

    # Network
    network_latency = models.FloatField()

    # Device & location (hashed)
    device_hash = models.CharField(max_length=64)
    location_hash = models.CharField(max_length=64)

    # Context
    time_of_day = models.IntegerField()

    # Session result
    was_trusted = models.BooleanField(default=False)
    trust_score = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "behavior_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["device_hash"]),
            models.Index(fields=["location_hash"]),
        ]

    def save(self, *args, **kwargs):
        if not (0 <= self.time_of_day <= 23):
            raise ValueError("time_of_day must be between 0 and 23")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"BehaviorLog({self.user.username}, score={self.trust_score})"