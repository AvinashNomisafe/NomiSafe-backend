from django.urls import path
from .views import (
	PolicyUploadView,
	PolicyListView,
	process_policy_benefits,
)

urlpatterns = [
	path('upload/', PolicyUploadView.as_view(), name='policy_upload'),
	path('', PolicyListView.as_view(), name='policy_list'),
	path('<int:policy_id>/benefits/', process_policy_benefits, name='policy_benefits'),
]
