from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .digilocker_service import DigiLockerService
from .models import AadhaarVerification


class DigiLockerAuthURLView(APIView):
    """Get DigiLocker authorization URL"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        auth_url = DigiLockerService.get_auth_url()
        return Response({'auth_url': auth_url})


class DigiLockerCallbackView(APIView):
    """Handle DigiLocker OAuth callback"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        code = request.query_params.get('code')
        if not code:
            return Response(
                {'error': 'Authorization code not provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Exchange code for access token
            token_data = DigiLockerService.get_access_token(code)
            if 'access_token' not in token_data:
                return Response(
                    {'error': 'Failed to get access token'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verify Aadhaar using DigiLocker
            verified, aadhaar_last_4 = DigiLockerService.verify_aadhaar(
                token_data['access_token']
            )

            if not verified:
                return Response(
                    {'error': 'Aadhaar verification failed'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update user's verification status
            AadhaarVerification.objects.update_or_create(
                user=request.user,
                defaults={
                    'aadhaar_reference': f"digilocker-{token_data['access_token'][-8:]}",
                    'aadhaar_last_4': aadhaar_last_4
                }
            )

            request.user.is_aadhaar_verified = True
            request.user.save()

            return Response({
                'message': 'Aadhaar verified successfully',
                'aadhaar_last_4': aadhaar_last_4
            })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )