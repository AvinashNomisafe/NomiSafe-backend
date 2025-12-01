from django.urls import path
from .views import PolicyUploadView, PolicyVerifyView, PolicyListView, PolicyDetailView

urlpatterns = [
    path('', PolicyListView.as_view(), name='policy-list'),
    path('<int:policy_id>/', PolicyDetailView.as_view(), name='policy-detail'),
    path('upload/', PolicyUploadView.as_view(), name='policy-upload'),
    path('<int:policy_id>/verify/', PolicyVerifyView.as_view(), name='policy-verify'),
]
