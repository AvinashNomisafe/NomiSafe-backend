from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser

from .serializers import PolicySerializer


class PolicyUploadView(APIView):
	"""Upload a policy PDF and associate it with the authenticated user."""
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser]

	def post(self, request, format=None):
		serializer = PolicySerializer(data=request.data, context={'request': request})
		serializer.is_valid(raise_exception=True)
		policy = serializer.save()
		return Response({'id': policy.id, 'name': policy.name, 'uploaded_at': policy.uploaded_at}, status=status.HTTP_201_CREATED)
