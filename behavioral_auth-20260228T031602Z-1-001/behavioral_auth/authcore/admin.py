from django.contrib import admin
from authcore.models import User, BehaviorLog, RegistrationBehavior, CalibrationSession, UserBehaviorProfile, LoginRiskEvent


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'username', 'is_active', 'created_at']
    search_fields = ['email', 'username']


@admin.register(UserBehaviorProfile)
class UserBehaviorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'identity_confidence', 'dynamic_threshold', 'trusted_login_count', 'consecutive_deviations', 'updated_at']
    readonly_fields = ['calm_baseline', 'cognitive_baseline', 'controlled_baseline', 'typical_hours']


@admin.register(LoginRiskEvent)
class LoginRiskEventAdmin(admin.ModelAdmin):
    list_display = ['email_attempted', 'trust_score', 'risk_level', 'action_taken', 'device_matched', 'confidence_at_time', 'created_at']
    list_filter = ['risk_level', 'action_taken', 'device_matched']
    readonly_fields = ['rejection_reasons']


@admin.register(CalibrationSession)
class CalibrationSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'phase', 'quality_score', 'duration_ms', 'captured_at']


@admin.register(BehaviorLog)
class BehaviorLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'trust_score', 'was_trusted', 'typing_speed', 'device_hash', 'created_at']


@admin.register(RegistrationBehavior)
class RegistrationBehaviorAdmin(admin.ModelAdmin):
    list_display = ['user', 'typing_speed', 'key_hold_time', 'created_at']
