"""
authcore/urls.py — App-level URL routing
All routes are prefixed with /api/auth/ from the root urls.py
"""

from django.urls import path
from . import views

urlpatterns = [
    # User registration — no password required
    path('register/', views.register_user, name='register'),

    # Behavioral login — the core authentication endpoint
    path('login/', views.login_user, name='login'),

    # Save behavioral snapshot (post-login continuous profiling)
    path('behavior/save/', views.save_behavior, name='save-behavior'),
]
