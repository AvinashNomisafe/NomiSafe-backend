from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Policy
from .serializers import (
	PolicySerializer,
	PolicyListSerializer,
	PolicyBenefitsSerializer,
)

class PolicyUploadView(APIView):
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = []  # can add MultiPartParser later if needed

	def post(self, request, format=None):
		serializer = PolicySerializer(data=request.data, context={'request': request})
		serializer.is_valid(raise_exception=True)
		policy = serializer.save()
		return Response({'id': policy.id, 'name': policy.name, 'uploaded_at': policy.uploaded_at}, status=status.HTTP_201_CREATED)


class PolicyListView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def get(self, request):
		policies = Policy.objects.filter(user=request.user).order_by('-uploaded_at')
		serializer = PolicyListSerializer(policies, many=True, context={'request': request})
		return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def process_policy_benefits(request, policy_id):
	policy = get_object_or_404(Policy, id=policy_id, user=request.user)
	if policy.benefits:
		serializer = PolicyBenefitsSerializer(policy)
		return Response(serializer.data)

	benefits = get_policy_benefits_summary(policy.document.path)
	if not benefits:
		return Response({"error": "Failed to process document"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
	if benefits.startswith("ERROR:"):
		return Response({"error": benefits.replace("ERROR: ", "")}, status=status.HTTP_400_BAD_REQUEST)

	policy.benefits = benefits
	policy.save(update_fields=['benefits'])
	serializer = PolicyBenefitsSerializer(policy)
	return Response(serializer.data)
