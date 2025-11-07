from rest_framework import serializers
from .models import Policy

class PolicyListSerializer(serializers.ModelSerializer):
    document_url = serializers.SerializerMethodField()

    class Meta:
        model = Policy
        fields = ['id', 'name', 'document_url', 'benefits', 'uploaded_at']
        read_only_fields = fields

    def get_document_url(self, obj):
        request = self.context.get('request')
        if obj.document and request:
            return request.build_absolute_uri(obj.document.url)
        return None

class PolicyBenefitsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Policy
        fields = ['id', 'name', 'benefits']
        read_only_fields = ['name', 'benefits']