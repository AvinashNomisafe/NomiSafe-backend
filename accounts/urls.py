from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views_otp import OTPRequestView, OTPVerifyView
from .views import PolicyUploadView
from .views_policy import process_policy_benefits, PolicyListView

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/otp/request/', OTPRequestView.as_view(), name='otp_request'),
    path('auth/otp/verify/', OTPVerifyView.as_view(), name='otp_verify'),
    path('policies/upload/', PolicyUploadView.as_view(), name='policy_upload'),
    path('policies/', PolicyListView.as_view(), name='policy_list'),
    path('policies/<int:policy_id>/benefits/', process_policy_benefits, name='policy_benefits'),
]
