from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken
import secrets
import hmac
import phonenumbers
import boto3
from botocore.client import Config

from .serializers import (
    OTPRequestSerializer, 
    OTPVerifySerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
    AppNomineeSerializer,
    PropertySerializer,
)
from .otp_utils import generate_code, hash_otp, default_otp_ttl
from .models import OTP, AppNominee, Property
from .sms_provider import send_sms


def normalize_phone(phone: str):
    """
    Normalize phone number to E164 format.
    Assumes India (+91) as default region if no country code is provided.
    """
    try:
        # If phone doesn't start with '+', assume it's an Indian number
        if not phone.startswith('+'):
            # Try parsing with 'IN' as default region
            p = phonenumbers.parse(phone, 'IN')
        else:
            p = phonenumbers.parse(phone, None)
        
        normalized = phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)
        print(f"[Phone Normalization] Input: {phone} -> Output: {normalized}")
        return normalized
    except Exception as e:
        print(f"[Phone Normalization] Failed for {phone}: {e}")
        return phone


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'detail': 'Account deleted successfully.'}, status=status.HTTP_200_OK)

@method_decorator(csrf_exempt, name='dispatch')
class OTPRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_phone = serializer.validated_data['phone_number']
        phone = normalize_phone(raw_phone)
        
        print(f"[OTP Request] Raw: {raw_phone}, Normalized: {phone}")

        # Generate code and store hashed
        code = generate_code(length=getattr(settings, 'OTP_LENGTH', 6))
        salt = secrets.token_hex(8)
        otp_hash = hash_otp(code, salt)
        expires = timezone.now() + timezone.timedelta(seconds=default_otp_ttl())
        otp = OTP.objects.create(phone_number=phone, otp_hash=otp_hash, salt=salt, expires_at=expires)

        message = f"Your NomiSafe verification code is {code}. It expires in {default_otp_ttl()//60} minutes."

        try:
            print(f"[SMS] Sending to {phone}: {message}")
            provider_id = send_sms(phone, message)
            print(f"[SMS] Success! Provider ID: {provider_id}")
            otp.provider_id = provider_id
            otp.save(update_fields=['provider_id'])
        except Exception as e:
            # Keep generic response to avoid enumeration and leak
            print(f"[SMS] Failed to send to {phone}: {e}")
            pass

        return Response({'detail': 'If allowed, an OTP was sent.'}, status=status.HTTP_202_ACCEPTED)


class OTPVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = normalize_phone(serializer.validated_data['phone_number'])
        code = serializer.validated_data['otp']

        # Bypass OTP for dummy account
        if phone in ('+918003780822', '8003780822') and code == '197325':
            User = get_user_model()
            user, created = User.objects.get_or_create(phone_number=phone)
            refresh = RefreshToken.for_user(user)
            return Response({'id': user.id, 'phone_number': user.phone_number, 'access': str(refresh.access_token), 'refresh': str(refresh)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        otp = OTP.objects.filter(phone_number=phone, used=False, expires_at__gt=timezone.now()).order_by('-created_at').first()
        if not otp:
            return Response({'detail': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

        expected = hash_otp(code, otp.salt)
        if not hmac.compare_digest(expected, otp.otp_hash):
            otp.attempts += 1
            if otp.attempts >= getattr(settings, 'OTP_MAX_ATTEMPTS', 5):
                otp.used = True
            otp.save(update_fields=['attempts', 'used'])
            return Response({'detail': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

        # success
        otp.used = True
        otp.save(update_fields=['used'])

        User = get_user_model()
        user, created = User.objects.get_or_create(phone_number=phone)
        refresh = RefreshToken.for_user(user)
        return Response({'id': user.id, 'phone_number': user.phone_number, 'access': str(refresh.access_token), 'refresh': str(refresh)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AppNomineeView(APIView):
    """Get or update the user's app nominee"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        nominee = AppNominee.objects.filter(user=request.user).first()
        if not nominee:
            return Response({'nominee': None}, status=status.HTTP_200_OK)

        serializer = AppNomineeSerializer(nominee, context={'request': request})
        return Response({'nominee': serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        nominee = AppNominee.objects.filter(user=request.user).first()
        serializer = AppNomineeSerializer(
            nominee,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(user=request.user)
        response_serializer = AppNomineeSerializer(instance, context={'request': request})
        return Response({'nominee': response_serializer.data}, status=status.HTTP_200_OK)


class PropertyListCreateView(APIView):
    """List or upload user properties"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        properties = Property.objects.filter(user=request.user)
        serializer = PropertySerializer(properties, many=True, context={'request': request})
        return Response({'properties': serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PropertySerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(user=request.user)
        response_serializer = PropertySerializer(instance, context={'request': request})
        return Response({'property': response_serializer.data}, status=status.HTTP_201_CREATED)


class PropertyDownloadView(APIView):
    """Get a fresh download URL for a property document"""
    permission_classes = [IsAuthenticated]

    def get(self, request, property_id):
        property_obj = get_object_or_404(
            Property,
            id=property_id,
            user=request.user
        )

        if not property_obj.document:
            return Response(
                {'error': 'Document not available'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Generate presigned URL using boto3 directly
        try:
            region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=region,
                config=Config(signature_version='s3v4')
            )
            
            # Get the S3 key - prepend 'properties/' since storage location isn't in document.name
            s3_key = f"properties/{property_obj.document.name}"
            
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Key': s3_key,
                },
                ExpiresIn=3600  # 1 hour
            )
            
            return Response({'url': url}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': f'Failed to generate download URL: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserProfileView(APIView):
    """Get or update user profile"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get current user's profile"""
        # Ensure profile exists
        from .models import UserProfile
        UserProfile.objects.get_or_create(user=request.user)
        
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request):
        """Update current user's profile"""
        return self._update_profile(request, partial=False)
    
    def patch(self, request):
        """Partially update current user's profile"""
        return self._update_profile(request, partial=True)
    
    def _update_profile(self, request, partial=True):
        """Helper method to update user profile"""
        from .models import UserProfile
        
        serializer = UserProfileUpdateSerializer(
            data=request.data,
            partial=partial
        )
        serializer.is_valid(raise_exception=True)
        
        validated_data = serializer.validated_data
        
        # Update User model fields (email)
        if 'email' in validated_data:
            request.user.email = validated_data.pop('email') or None
            request.user.save(update_fields=['email'])
        
        # Update or create UserProfile
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Update profile fields
        for field, value in validated_data.items():
            setattr(profile, field, value or None)
        
        profile.save()
        
        # Return updated profile
        response_serializer = UserProfileSerializer(request.user)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


