from rest_framework import serializers
from .models import Policy


# OTP Serializers
class OTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()


class OTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.CharField()


# Policy Serializers
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
