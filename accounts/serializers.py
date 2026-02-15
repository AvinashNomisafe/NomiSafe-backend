from rest_framework import serializers
from .models import OTP, User, UserProfile, AppNominee, Property


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


class AppNomineeSerializer(serializers.ModelSerializer):
    id_proof_file_url = serializers.SerializerMethodField()

    class Meta:
        model = AppNominee
        fields = [
            'id',
            'name',
            'relationship',
            'contact_details',
            'id_proof_type',
            'aadhaar_number',
            'id_proof_file',
            'id_proof_file_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'id_proof_file_url']

    def get_id_proof_file_url(self, obj):
        if not obj.id_proof_file:
            return None
        request = self.context.get('request')
        url = obj.id_proof_file.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class PropertySerializer(serializers.ModelSerializer):
    document_url = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'id',
            'name',
            'document',
            'document_url',
            'uploaded_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'uploaded_at', 'updated_at', 'document_url']

    def get_document_url(self, obj):
        if not obj.document:
            return None
        request = self.context.get('request')
        url = obj.document.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


