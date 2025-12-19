from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    OTPRequestView, 
    OTPVerifyView,
    UserProfileView,
    DeleteAccountView,
)

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/otp/request/', OTPRequestView.as_view(), name='otp_request'),
    path('auth/otp/verify/', OTPVerifyView.as_view(), name='otp_verify'),
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete_account'),
]
