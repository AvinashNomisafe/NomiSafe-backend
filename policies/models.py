from django.db import models
from django.conf import settings


class Policy(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='policies')
	name = models.CharField(max_length=255)
	document = models.FileField(upload_to='policies/')
	benefits = models.TextField(blank=True)
	uploaded_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-uploaded_at']

	def __str__(self):
		return f"{self.name} ({self.user})"

