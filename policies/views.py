from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404
from decimal import Decimal
from datetime import datetime
import logging
import threading

from .models import (
    Policy, PolicyCoverage, PolicyNominee, PolicyBenefit,
    PolicyExclusion, HealthInsuranceDetails, CoveredMember,
    ExtractedDocument
)
from .serializers import (
    PolicyUploadSerializer, PolicyListSerializer, PolicyDetailSerializer
)
from .ai_extractor import PolicyAIExtractor

# Configure logger
logger = logging.getLogger(__name__)


def process_policy_extraction_background(policy_id):
    """Background task to extract policy data using AI"""
    try:
        policy = Policy.objects.get(id=policy_id)
        logger.info(f"[Background] Starting AI extraction for policy {policy_id}")
        
        # Update status to PROCESSING
        policy.ai_extraction_status = 'PROCESSING'
        policy.save(update_fields=['ai_extraction_status'])
        
        # Perform AI extraction
        extractor = PolicyAIExtractor()
        extracted_data = extractor.extract_policy_preview(policy.document)
        
        # Save extracted data
        with transaction.atomic():
            ExtractedDocument.objects.update_or_create(
                policy=policy,
                defaults={
                    'raw_text': '',
                    'structured_data': extracted_data,
                    'extraction_model': 'gemini-2.0-flash-exp'
                }
            )
            
            policy.ai_extraction_status = 'COMPLETED'
            policy.ai_extracted_at = timezone.now()
            policy.ai_extraction_error = None
            policy.save(update_fields=['ai_extraction_status', 'ai_extracted_at', 'ai_extraction_error'])
        
        logger.info(f"[Background] AI extraction completed for policy {policy_id}")
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"[Background] AI extraction failed for policy {policy_id}: {error_message}", exc_info=True)
        
        try:
            policy = Policy.objects.get(id=policy_id)
            policy.ai_extraction_status = 'FAILED'
            policy.ai_extraction_error = error_message[:1000]  # Limit error message length
            policy.save(update_fields=['ai_extraction_status', 'ai_extraction_error'])
        except:
            pass


class PolicyUploadView(APIView):
    """Step 1: Upload PDF immediately, start background AI extraction"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = PolicyUploadSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        document_file = request.FILES.get('document')
        policy_name = serializer.validated_data['name']
        
        logger.info(f"Uploading policy: {policy_name}")
        logger.info(f"File: {document_file.name}, Size: {document_file.size}")
        
        try:
            # Save policy immediately without waiting for AI
            policy = Policy.objects.create(
                user=request.user,
                name=policy_name,
                document=document_file,
                ai_extraction_status='PENDING'
            )
            
            logger.info(f"Policy {policy.id} saved. Starting background AI extraction...")
            
            # Start background AI extraction
            extraction_thread = threading.Thread(
                target=process_policy_extraction_background,
                args=(policy.id,),
                daemon=True
            )
            extraction_thread.start()
            
            # Return immediately
            return Response({
                'id': policy.id,
                'name': policy.name,
                'uploaded_at': policy.uploaded_at,
                'ai_extraction_status': policy.ai_extraction_status,
                'message': 'Policy uploaded successfully. AI extraction is processing in background.'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Policy upload failed: {str(e)}", exc_info=True)
            return Response({
                'error': 'Failed to upload policy',
                'message': 'Could not save the document. Please try again.',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PolicyExtractionStatusView(APIView):
    """Get AI extraction status for a policy"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, policy_id):
        try:
            policy = Policy.objects.select_related('extracted_document').get(
                id=policy_id, 
                user=request.user
            )
        except Policy.DoesNotExist:
            return Response(
                {'error': 'Policy not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        response_data = {
            'policy_id': policy.id,
            'ai_extraction_status': policy.ai_extraction_status,
            'ai_extracted_at': policy.ai_extracted_at,
            'ai_extraction_error': policy.ai_extraction_error,
        }
        
        # Include extracted data if available
        if policy.ai_extraction_status == 'COMPLETED':
            try:
                extracted_doc = policy.extracted_document
                response_data['extracted_data'] = extracted_doc.structured_data
            except ExtractedDocument.DoesNotExist:
                pass
        
        return Response(response_data, status=status.HTTP_200_OK)


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
        
        # Check if AI extraction is completed
        if policy.ai_extraction_status != 'COMPLETED':
            return Response(
                {'error': 'AI extraction not completed yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get verified data from request
        verified_data = request.data
        
        try:
            with transaction.atomic():
                # Save verified data to models
                self._save_verified_data(policy, verified_data)
                
                # Mark as verified by user
                policy.is_verified_by_user = True
                policy.verified_at = timezone.now()
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


class PolicyListView(APIView):
    """List all policies for the authenticated user, grouped by type"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Get ALL policies (including those still being processed)
        policies = Policy.objects.filter(
            user=request.user,
            is_active=True
        ).select_related('coverage').order_by('-uploaded_at')
        
        # Separate by insurance type
        health_policies = []
        life_policies = []
        unprocessed_policies = []
        
        for policy in policies:
            serializer = PolicyListSerializer(policy, context={'request': request})
            policy_data = serializer.data
            
            # Only group by type if verified
            if policy.is_verified_by_user and policy.insurance_type:
                if policy.insurance_type == 'HEALTH':
                    health_policies.append(policy_data)
                elif policy.insurance_type == 'LIFE':
                    life_policies.append(policy_data)
            else:
                # Unprocessed/unverified policies
                unprocessed_policies.append(policy_data)
        
        return Response({
            'health': health_policies,
            'life': life_policies,
            'unprocessed': unprocessed_policies
        }, status=status.HTTP_200_OK)


class PolicyDetailView(APIView):
    """Get detailed information about a specific policy"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, policy_id):
        policy = get_object_or_404(
            Policy.objects.select_related('coverage', 'health_details').prefetch_related(
                'nominees', 'benefits', 'exclusions', 'health_details__covered_members'
            ),
            id=policy_id,
            user=request.user
        )
        
        # Only allow access to verified policies
        if not policy.is_verified_by_user:
            return Response(
                {'error': 'Policy details not verified yet'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = PolicyDetailSerializer(policy, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

