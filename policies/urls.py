from django.urls import path
from .views import PolicyUploadView

urlpatterns = [
    path('upload/', PolicyUploadView.as_view(), name='policy_upload'),
]
