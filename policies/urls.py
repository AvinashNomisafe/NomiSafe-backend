from django.urls import path
from .views import PolicyUploadView, PolicyVerifyView

urlpatterns = [
    path('upload/', PolicyUploadView.as_view(), name='policy-upload'),
    path('<int:policy_id>/verify/', PolicyVerifyView.as_view(), name='policy-verify'),
]
