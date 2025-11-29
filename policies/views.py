from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import datetime
import logging

from .models import (
    Policy, PolicyCoverage, PolicyNominee, PolicyBenefit,
    PolicyExclusion, HealthInsuranceDetails, CoveredMember,
    ExtractedDocument
)
from .serializers import PolicyUploadSerializer
from .ai_extractor import PolicyAIExtractor

# Configure logger
logger = logging.getLogger(__name__)


class PolicyUploadView(APIView):
    """Step 1: Upload PDF and get AI-extracted preview"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        # Validate input but don't save to database yet
        serializer = PolicyUploadSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        # Get the uploaded file and name without saving
        document_file = request.FILES.get('document')
        policy_name = serializer.validated_data['name']
        
        logger.info(f"Processing policy upload: {policy_name}")
        logger.info(f"File details - Name: {document_file.name}, Size: {document_file.size}, Content-Type: {document_file.content_type}")
        
        # Extract data using AI FIRST (before creating any database entries)
        try:
            extractor = PolicyAIExtractor()
            logger.info("Starting AI extraction...")
            
            extracted_data = extractor.extract_policy_preview(document_file)
            
            logger.info("AI extraction successful")
            logger.debug(f"Extracted data: {extracted_data}")
            
            # Only create database entries if AI extraction succeeds
            with transaction.atomic():
                policy = Policy.objects.create(
                    user=request.user,
                    name=policy_name,
                    document=document_file
                )
                
                logger.info(f"Policy created with ID: {policy.id}")
                
                # Store extracted data temporarily in ExtractedDocument
                ExtractedDocument.objects.create(
                    policy=policy,
                    raw_text='',
                    structured_data=extracted_data,
                    extraction_model='gemini-2.0-flash-exp'
                )
                
                logger.info("ExtractedDocument record created")
            
            # Return extracted data for user verification
            return Response({
                'id': policy.id,
                'name': policy.name,
                'uploaded_at': policy.uploaded_at,
                'extracted_data': extracted_data,
                'message': 'Policy uploaded. Please verify the extracted details.'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            # Don't create any database entries if extraction fails
            error_message = str(e)
            
            logger.error(f"Policy extraction failed: {error_message}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            
            # Check if it's a rate limit error
            if '429' in error_message or 'quota' in error_message.lower() or 'rate' in error_message.lower():
                return Response({
                    'error': 'API rate limit exceeded',
                    'message': 'The AI service has temporary usage limits. Please wait a moment and try again.',
                    'details': 'Rate limit exceeded. Please retry after a minute.'
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)
            
            # Generic error - no policy created, no document stored
            return Response({
                'error': 'Failed to extract policy details',
                'message': 'Could not process the uploaded document. Please try again later.',
                'details': error_message
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PolicyVerifyView(APIView):
    """Step 2: User verifies/edits and saves the extracted data"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, policy_id):
        try:
            policy = Policy.objects.get(id=policy_id, user=request.user)
        except Policy.DoesNotExist:
            return Response(
                {'error': 'Policy not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get verified data from request
        verified_data = request.data
        
        try:
            with transaction.atomic():
                # Save verified data to models
                self._save_verified_data(policy, verified_data)
                
                # Mark as processed
                policy.is_processed = True
                policy.last_processed = timezone.now()
                policy.processing_error = None
                policy.save()
            
            return Response({
                'message': 'Policy details saved successfully',
                'policy_id': policy.id
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'Failed to save policy details',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _save_verified_data(self, policy: Policy, data: dict):
        """Save user-verified data to database"""
        
        # Update basic policy info
        policy.insurance_type = data.get('insurance_type')
        policy.policy_number = data.get('policy_number')
        policy.insurer_name = data.get('insurer_name')
        policy.save()
        
        # Save coverage details
        coverage_data = data.get('coverage', {})
        PolicyCoverage.objects.update_or_create(
            policy=policy,
            defaults={
                'sum_assured': self._to_decimal(coverage_data.get('sum_assured')),
                'premium_amount': self._to_decimal(coverage_data.get('premium_amount')),
                'premium_frequency': coverage_data.get('premium_frequency'),
                'issue_date': self._parse_date(coverage_data.get('issue_date')),
                'start_date': self._parse_date(coverage_data.get('start_date')),
                'end_date': self._parse_date(coverage_data.get('end_date')),
                'maturity_date': self._parse_date(coverage_data.get('maturity_date')),
            }
        )
        
        # Save nominees (for Life Insurance)
        if 'nominees' in data and data['nominees']:
            PolicyNominee.objects.filter(policy=policy).delete()
            for nominee_data in data['nominees']:
                if nominee_data.get('name'):
                    PolicyNominee.objects.create(
                        policy=policy,
                        name=nominee_data.get('name'),
                        relationship=nominee_data.get('relationship'),
                        allocation_percentage=self._to_decimal(
                            nominee_data.get('allocation_percentage', 100)
                        )
                    )
        
        # Save benefits
        if 'benefits' in data and data['benefits']:
            PolicyBenefit.objects.filter(policy=policy).delete()
            for benefit_data in data['benefits']:
                if benefit_data.get('name'):
                    PolicyBenefit.objects.create(
                        policy=policy,
                        benefit_type=benefit_data.get('benefit_type', 'BASE'),
                        name=benefit_data.get('name'),
                        description=benefit_data.get('description'),
                        coverage_amount=self._to_decimal(benefit_data.get('coverage_amount'))
                    )
        
        # Save exclusions
        if 'exclusions' in data and data['exclusions']:
            PolicyExclusion.objects.filter(policy=policy).delete()
            for exclusion_data in data['exclusions']:
                if exclusion_data.get('title'):
                    PolicyExclusion.objects.create(
                        policy=policy,
                        title=exclusion_data.get('title'),
                        description=exclusion_data.get('description', '')
                    )
        
        # Save health-specific details
        if policy.insurance_type == 'HEALTH' and 'health_details' in data:
            health_data = data['health_details']
            health_details, _ = HealthInsuranceDetails.objects.update_or_create(
                policy=policy,
                defaults={
                    'policy_type': health_data.get('policy_type'),
                    'room_rent_limit': self._to_decimal(health_data.get('room_rent_limit')),
                    'co_payment_percentage': self._to_decimal(
                        health_data.get('co_payment_percentage')
                    ),
                    'cashless_facility': health_data.get('cashless_facility', True)
                }
            )
            
            # Save covered members
            if 'covered_members' in data and data['covered_members']:
                CoveredMember.objects.filter(health_insurance=health_details).delete()
                for member_data in data['covered_members']:
                    if member_data.get('name'):
                        CoveredMember.objects.create(
                            health_insurance=health_details,
                            name=member_data.get('name'),
                            relationship=member_data.get('relationship', ''),
                            age=member_data.get('age')
                        )
    
    def _to_decimal(self, value):
        """Convert value to Decimal"""
        if value is None or value == '':
            return None
        try:
            return Decimal(str(value))
        except:
            return None
    
    def _parse_date(self, date_str):
        """Parse date string to date object"""
        if not date_str or date_str == 'null':
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            return None

