from rest_framework import serializers
from .models import Policy


class PolicySerializer(serializers.ModelSerializer):
	document = serializers.FileField(required=True)

	class Meta:
		model = Policy
		fields = ['id', 'name', 'document', 'benefits', 'uploaded_at']
		read_only_fields = ['id', 'uploaded_at']

	def create(self, validated_data):
		# user should be injected by the view
		user = self.context['request'].user
		return Policy.objects.create(user=user, **validated_data)
