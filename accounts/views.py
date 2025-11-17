from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken
import secrets
import hmac
import phonenumbers

from .serializers import (
    OTPRequestSerializer, 
    OTPVerifySerializer,
    PolicySerializer,
    PolicyListSerializer,
    PolicyBenefitsSerializer
)
from .otp_utils import generate_code, hash_otp, default_otp_ttl
from .models import OTP, Policy
from .sms_provider import send_sms
from .pdf_processor import get_policy_benefits_summary


def normalize_phone(phone: str):
    try:
        p = phonenumbers.parse(phone, None)
        return phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return phone


# OTP Views
class OTPRequestView(APIView):
    # OTP request is used for login so it must be callable without prior auth.
    # Avoid running authentication classes (which may raise on malformed/expired
    # tokens) by clearing authentication_classes and allow any permission.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = normalize_phone(serializer.validated_data['phone_number'])

        # Generate code and store hashed
        code = generate_code(length=getattr(settings, 'OTP_LENGTH', 6))
        salt = secrets.token_hex(8)
        otp_hash = hash_otp(code, salt)
        expires = timezone.now() + timezone.timedelta(seconds=default_otp_ttl())
        otp = OTP.objects.create(phone_number=phone, otp_hash=otp_hash, salt=salt, expires_at=expires)

        message = f"Your NomiSafe verification code is {code}. It expires in {default_otp_ttl()//60} minutes."

        try:
            provider_id = send_sms(phone, message)
            otp.provider_id = provider_id
            otp.save(update_fields=['provider_id'])
        except Exception:
            # Keep generic response to avoid enumeration and leak
            pass

        return Response({'detail': 'If allowed, an OTP was sent.'}, status=status.HTTP_202_ACCEPTED)


class OTPVerifyView(APIView):
    # OTP verify also needs to be public so clients can exchange OTP for tokens.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = normalize_phone(serializer.validated_data['phone_number'])
        code = serializer.validated_data['otp']

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


# Policy Views
class PolicyUploadView(APIView):
	"""Upload a policy PDF and associate it with the authenticated user."""
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser]

	def post(self, request, format=None):
		serializer = PolicySerializer(data=request.data, context={'request': request})
		serializer.is_valid(raise_exception=True)
		policy = serializer.save()
		return Response({'id': policy.id, 'name': policy.name, 'uploaded_at': policy.uploaded_at}, status=status.HTTP_201_CREATED)


class PolicyListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get list of all policies for the authenticated user
        """
        policies = Policy.objects.filter(user=request.user).order_by('-uploaded_at')
        serializer = PolicyListSerializer(policies, many=True, context={'request': request})
        return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def process_policy_benefits(request, policy_id):
    """
    Process policy benefits using Gemini AI if they're not already extracted
    """
    # Get the policy object
    policy = get_object_or_404(Policy, id=policy_id, user=request.user)
    
    # If benefits are already extracted, return them
    if policy.benefits:
        serializer = PolicyBenefitsSerializer(policy)
        return Response(serializer.data)
    
    # Process the PDF and extract benefits using Gemini
    benefits = get_policy_benefits_summary(policy.document.path)
    
    if not benefits:
        return Response(
            {"error": "Failed to process document"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # Check for error messages
    if benefits.startswith("ERROR:"):
        error_message = benefits.replace("ERROR: ", "")
        return Response(
            {"error": error_message},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Update the policy with extracted benefits
    policy.benefits = benefits
    policy.save()
    serializer = PolicyBenefitsSerializer(policy)
    return Response(serializer.data)
