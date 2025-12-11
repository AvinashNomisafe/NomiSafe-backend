from django.urls import path
from .views import (
    PolicyUploadView, PolicyVerifyView, PolicyListView, 
    PolicyDetailView, PolicyExtractionStatusView, DashboardStatsView
)

urlpatterns = [
    path('', PolicyListView.as_view(), name='policy-list'),
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('<int:policy_id>/', PolicyDetailView.as_view(), name='policy-detail'),
    path('upload/', PolicyUploadView.as_view(), name='policy-upload'),
    path('<int:policy_id>/extraction-status/', PolicyExtractionStatusView.as_view(), name='policy-extraction-status'),
    path('<int:policy_id>/verify/', PolicyVerifyView.as_view(), name='policy-verify'),
]
