import json
import requests
from datetime import datetime, timedelta
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import AadhaarOTP, AadhaarVerification
from .serializers_aadhaar import (
    AadhaarRequestOTPSerializer,
    AadhaarVerifyOTPSerializer,
    AadhaarVerificationSerializer,
)

# For demo/testing purposes, we'll use a mock API
# In production, replace with actual UIDAI API endpoints
MOCK_AADHAAR_API = {
    'generate_otp': 'https://mock-aadhaar-api.example.com/api/v1/aadhaar/generate-otp',
    'verify_otp': 'https://mock-aadhaar-api.example.com/api/v1/aadhaar/verify-otp',
}

class AadhaarRequestOTPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AadhaarRequestOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        aadhaar_number = serializer.validated_data['aadhaar_number']

        try:
            # For demo purposes, we'll create a mock OTP reference
            # In production, this would come from the UIDAI API
            otp_reference = f"mock-ref-{datetime.now().timestamp()}"

            # Create AadhaarOTP record
            AadhaarOTP.objects.create(
                user=request.user,
                aadhaar_number=aadhaar_number[-4:],  # Store only last 4 digits
                otp_reference=otp_reference,
                expires_at=datetime.now() + timedelta(minutes=10)
            )

            # In production, you would make an actual API call to UIDAI
            # For demo, we'll just return success
            return Response({
                'message': 'OTP sent successfully',
                'otp_reference': otp_reference
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to generate OTP'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AadhaarVerifyOTPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AadhaarVerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        otp = serializer.validated_data['otp']
        otp_reference = serializer.validated_data['otp_reference']

        try:
            aadhaar_otp = AadhaarOTP.objects.get(
                user=request.user,
                otp_reference=otp_reference,
                is_verified=False,
                expires_at__gt=datetime.now()
            )

            # For demo purposes, we'll accept any 6-digit OTP
            # In production, this would verify with UIDAI API
            if len(otp) == 6 and otp.isdigit():
                # Mark OTP as verified
                aadhaar_otp.is_verified = True
                aadhaar_otp.save()

                # Create or update AadhaarVerification
                AadhaarVerification.objects.update_or_create(
                    user=request.user,
                    defaults={
                        'aadhaar_reference': f"mock-aadhaar-ref-{datetime.now().timestamp()}",
                        'aadhaar_last_4': aadhaar_otp.aadhaar_number
                    }
                )

                # Update user's Aadhaar verification status
                request.user.is_aadhaar_verified = True
                request.user.save()

                return Response({
                    'message': 'Aadhaar verified successfully',
                    'aadhaar_last_4': aadhaar_otp.aadhaar_number
                })
            else:
                aadhaar_otp.attempts += 1
                aadhaar_otp.save()
                return Response(
                    {'error': 'Invalid OTP'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except AadhaarOTP.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired OTP reference'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': 'Failed to verify OTP'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AadhaarVerificationStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            verification = AadhaarVerification.objects.get(user=request.user)
            serializer = AadhaarVerificationSerializer(verification)
            return Response(serializer.data)
        except AadhaarVerification.DoesNotExist:
            return Response({
                'verified': False,
                'message': 'Aadhaar not verified'
            })