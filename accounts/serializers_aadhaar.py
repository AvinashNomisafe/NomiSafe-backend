from rest_framework import serializers
from .models import AadhaarOTP, AadhaarVerification

class AadhaarRequestOTPSerializer(serializers.Serializer):
    aadhaar_number = serializers.CharField(max_length=12, min_length=12)

    def validate_aadhaar_number(self, value):
        # Basic Aadhaar number validation
        if not value.isdigit():
            raise serializers.ValidationError("Aadhaar number must contain only digits")
        # Verhoeff algorithm check can be added here for more validation
        return value

class AadhaarVerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, min_length=6)
    otp_reference = serializers.CharField()

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits")
        return value

class AadhaarVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AadhaarVerification
        fields = ['aadhaar_last_4', 'verified_at']
        read_only_fields = fields