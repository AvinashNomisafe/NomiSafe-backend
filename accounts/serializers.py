from rest_framework import serializers
from .models import OTP, User, UserProfile


# OTP Serializers
class OTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()


class OTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.CharField()


# User Profile Serializers
class UserProfileDetailSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile model"""
    class Meta:
        model = UserProfile
        fields = [
            'name',
            'date_of_birth',
            'alternate_phone',
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    """Combined serializer with User and UserProfile data"""
    profile = UserProfileDetailSerializer(required=False)
    
    class Meta:
        model = User
        fields = [
            'id',
            'phone_number',
            'email',
            'is_aadhaar_verified',
            'profile',
        ]
        read_only_fields = ['id', 'phone_number', 'is_aadhaar_verified']


class UserProfileUpdateSerializer(serializers.Serializer):
    """Serializer for updating user profile"""
    email = serializers.EmailField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    alternate_phone = serializers.CharField(required=False, allow_blank=True, max_length=24)
    
    def validate_alternate_phone(self, value):
        """Validate alternate phone number format if provided"""
        if value and len(value) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits")
        return value


