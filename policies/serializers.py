from rest_framework import serializers
from .models import Policy


class PolicyUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading a new policy"""
    document = serializers.FileField(required=True)
    name = serializers.CharField(max_length=255, required=True)

    class Meta:
        model = Policy
        fields = ['id', 'name', 'document', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

    def create(self, validated_data):
        user = self.context['request'].user
        return Policy.objects.create(user=user, **validated_data)
