from rest_framework import serializers
from .models import OTP  


# OTP Serializers
class OTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()


class OTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.CharField()


