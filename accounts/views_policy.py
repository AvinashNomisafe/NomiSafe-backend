from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from .models import Policy
from .serializers_policy import PolicyBenefitsSerializer, PolicyListSerializer
from .pdf_processor import get_policy_benefits_summary


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