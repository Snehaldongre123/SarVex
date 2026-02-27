"""
config/urls.py — Root URL configuration
Routes all API requests to the authcore app.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # All behavioral auth endpoints live under /api/auth/
    path('api/auth/', include('authcore.urls')),
]
