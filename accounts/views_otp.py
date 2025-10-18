from django.utils import timezone
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers_otp import OTPRequestSerializer, OTPVerifySerializer
from .otp_utils import generate_code, hash_otp, default_otp_ttl
from .models import OTP
from .sms_provider import send_sms
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
import secrets
import phonenumbers


def normalize_phone(phone: str):
    try:
        p = phonenumbers.parse(phone, None)
        return phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return phone


class OTPRequestView(APIView):
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
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = normalize_phone(serializer.validated_data['phone_number'])
        code = serializer.validated_data['otp']

        otp = OTP.objects.filter(phone_number=phone, used=False, expires_at__gt=timezone.now()).order_by('-created_at').first()
        if not otp:
            return Response({'detail': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

        expected = hash_otp(code, otp.salt)
        import hmac
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
