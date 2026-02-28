from django.urls import path
from authcore.views import (
    IndexView, RegisterView, LoginView,
    VerifyChallengeView, SaveBehaviorView, ProfileView,
    LoginStartView, LoginPhaseView, LoginCompleteView
)
from authcore.federated.fed_views import FederatedModelView, FederatedUpdateView, FederatedStatusView

urlpatterns = [
    path('', IndexView.as_view(), name='index'),
    # Auth
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/verify-challenge/', VerifyChallengeView.as_view(), name='verify_challenge'),
    path('api/auth/behavior/save/', SaveBehaviorView.as_view(), name='save_behavior'),
    path('api/auth/profile/', ProfileView.as_view(), name='profile'),
    # Federated
    path('api/auth/federated/model/', FederatedModelView.as_view(), name='federated_model'),
    path('api/auth/federated/update/', FederatedUpdateView.as_view(), name='federated_update'),
    path('api/auth/federated/status/', FederatedStatusView.as_view(), name='federated_status'),
        # New Multi-Phase Login
    path('api/auth/login/start/', LoginStartView.as_view(), name='login_start'),
    path('api/auth/login/phase/', LoginPhaseView.as_view(), name='login_phase'),
    path('api/auth/login/complete/', LoginCompleteView.as_view(), name='login_complete'),
]
