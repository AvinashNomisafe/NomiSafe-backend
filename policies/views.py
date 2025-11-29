from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from .models import Policy
from .serializers import PolicyUploadSerializer


class PolicyUploadView(APIView):
    """API endpoint for uploading a new policy document"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = PolicyUploadSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        policy = serializer.save()
        
        return Response(
            {
                'id': policy.id,
                'name': policy.name,
                'uploaded_at': policy.uploaded_at,
                'message': 'Policy uploaded successfully'
            },
            status=status.HTTP_201_CREATED
        )
