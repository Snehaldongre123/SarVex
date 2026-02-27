"""
authcore/admin.py
Django Admin configuration for Passwordless Behavioral Authentication System
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, BehaviorLog


# ------------------------------------------------------------------
# USER ADMIN (PASSWORDLESS)
# ------------------------------------------------------------------
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin panel for passwordless User model.
    Removes password field entirely.
    """

    # Columns visible in user list page
    list_display = (
        'username',
        'email',
        'is_active',
        'is_staff',
        'created_at',
        'last_login'
    )

    list_filter = ('is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'username')
    ordering = ('-created_at',)

    # Remove password field completely
    fieldsets = (
        (None, {
            'fields': ('email', 'username')
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Important Dates', {
            'fields': ('last_login', 'created_at')
        }),
    )

    # When creating new user from admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username'),
        }),
    )

    readonly_fields = ('created_at', 'last_login')


# ------------------------------------------------------------------
# BEHAVIOR LOG ADMIN
# ------------------------------------------------------------------
@admin.register(BehaviorLog)
class BehaviorLogAdmin(admin.ModelAdmin):
    """
    Admin view for Behavior Logs.
    Displays trust score + session behavior snapshot.
    """

    list_display = (
        'user',
        'trust_score',
        'colored_trust_status',
        'time_of_day',
        'created_at'
    )

    list_filter = ('was_trusted', 'time_of_day')
    search_fields = ('user__username', 'user__email')
    ordering = ('-created_at',)

    readonly_fields = (
        'user',
        'typing_speed',
        'key_hold_time',
        'mouse_velocity',
        'click_interval',
        'scroll_depth',
        'network_latency',
        'device_hash',
        'location_hash',
        'time_of_day',
        'was_trusted',
        'trust_score',
        'created_at',
    )

    # Add color to trusted / untrusted
    def colored_trust_status(self, obj):
        if obj.was_trusted:
            return format_html('<span style="color:green; font-weight:bold;">Trusted</span>')
        return format_html('<span style="color:red; font-weight:bold;">Rejected</span>')

    colored_trust_status.short_description = "Status"