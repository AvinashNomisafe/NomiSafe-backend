from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q, Avg
from decimal import Decimal
from datetime import datetime, timedelta
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
                'maturity_amount': self._to_decimal(coverage_data.get('maturity_amount')),
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
        # Get optional insurance_type filter from query params
        insurance_type_filter = request.query_params.get('insurance_type', None)
        
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
        
        # If insurance_type filter is provided, return only that type + unprocessed
        if insurance_type_filter:
            if insurance_type_filter.upper() == 'HEALTH':
                return Response({
                    'health': health_policies,
                    'life': [],
                    'unprocessed': unprocessed_policies
                }, status=status.HTTP_200_OK)
            elif insurance_type_filter.upper() == 'LIFE':
                return Response({
                    'health': [],
                    'life': life_policies,
                    'unprocessed': unprocessed_policies
                }, status=status.HTTP_200_OK)
        
        # Return all if no filter
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


class DashboardStatsView(APIView):
    """Get dashboard statistics and analytics"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        today = timezone.now().date()
        
        # Get all verified policies
        all_policies = Policy.objects.filter(
            user=user,
            is_verified_by_user=True
        ).select_related('coverage')
        
        life_policies = all_policies.filter(insurance_type='LIFE')
        health_policies = all_policies.filter(insurance_type='HEALTH')
        
        # Calculate totals
        life_stats = self._calculate_insurance_stats(life_policies, today)
        health_stats = self._calculate_insurance_stats(health_policies, today)
        
        # Upcoming renewals (policies expiring in next 90 days)
        upcoming_renewals = all_policies.filter(
            coverage__end_date__gte=today,
            coverage__end_date__lte=today + timedelta(days=90)
        ).select_related('coverage').order_by('coverage__end_date')
        
        renewals_data = [{
            'id': p.id,
            'name': p.name,
            'insurance_type': p.insurance_type,
            'insurer_name': p.insurer_name,
            'end_date': p.coverage.end_date,
            'days_remaining': (p.coverage.end_date - today).days if p.coverage.end_date else None,
            'premium_amount': float(p.coverage.premium_amount) if p.coverage.premium_amount else None
        } for p in upcoming_renewals if hasattr(p, 'coverage')]
        
        # Recent policies (last 5 added)
        recent_policies = all_policies.order_by('-uploaded_at')[:5]
        recent_data = [{
            'id': p.id,
            'name': p.name,
            'insurance_type': p.insurance_type,
            'insurer_name': p.insurer_name,
            'uploaded_at': p.uploaded_at,
            'sum_assured': float(p.coverage.sum_assured) if hasattr(p, 'coverage') and p.coverage.sum_assured else None
        } for p in recent_policies]
        
        # Monthly premium breakdown
        monthly_premium = self._calculate_monthly_premium(all_policies)
        
        return Response({
            'summary': {
                'total_policies': all_policies.count(),
                'life_insurance_count': life_policies.count(),
                'health_insurance_count': health_policies.count(),
                'total_monthly_premium': monthly_premium,
            },
            'life_insurance': life_stats,
            'health_insurance': health_stats,
            'upcoming_renewals': renewals_data,
            'recent_policies': recent_data,
            'profile_completion': self._get_profile_completion(user),
        }, status=status.HTTP_200_OK)
    
    def _calculate_insurance_stats(self, policies, today):
        """Calculate statistics for insurance type"""
        total_policies = policies.count()
        
        if total_policies == 0:
            return {
                'total_policies': 0,
                'total_sum_assured': 0,
                'total_premium': 0,
                'active_policies': 0,
                'expired_policies': 0,
                'total_maturity_amount': 0,
            }
        
        # Get coverage data
        coverages = PolicyCoverage.objects.filter(policy__in=policies)
        
        # Calculate totals
        sum_assured_total = coverages.aggregate(
            total=Sum('sum_assured')
        )['total'] or Decimal('0')
        
        maturity_total = coverages.aggregate(
            total=Sum('maturity_amount')
        )['total'] or Decimal('0')
        
        # Calculate total monthly premium (convert all to monthly)
        total_premium = Decimal('0')
        for coverage in coverages:
            if coverage.premium_amount:
                monthly = self._convert_to_monthly_premium(
                    coverage.premium_amount,
                    coverage.premium_frequency
                )
                total_premium += monthly
        
        # Count active vs expired
        active_count = coverages.filter(
            Q(end_date__gte=today) | Q(end_date__isnull=True)
        ).count()
        
        expired_count = coverages.filter(end_date__lt=today).count()
        
        return {
            'total_policies': total_policies,
            'total_sum_assured': float(sum_assured_total),
            'total_premium': float(total_premium),
            'active_policies': active_count,
            'expired_policies': expired_count,
            'total_maturity_amount': float(maturity_total),
        }
    
    def _calculate_monthly_premium(self, policies):
        """Calculate total monthly premium across all policies"""
        total = Decimal('0')
        
        for policy in policies:
            if hasattr(policy, 'coverage') and policy.coverage.premium_amount:
                monthly = self._convert_to_monthly_premium(
                    policy.coverage.premium_amount,
                    policy.coverage.premium_frequency
                )
                total += monthly
        
        return float(total)
    
    def _convert_to_monthly_premium(self, amount, frequency):
        """Convert premium to monthly equivalent"""
        if not amount:
            return Decimal('0')
        
        amount = Decimal(str(amount))
        
        if frequency == 'MONTHLY':
            return amount
        elif frequency == 'QUARTERLY':
            return amount / Decimal('3')
        elif frequency == 'HALF_YEARLY':
            return amount / Decimal('6')
        elif frequency == 'YEARLY':
            return amount / Decimal('12')
        else:
            return Decimal('0')
    
    def _get_profile_completion(self, user):
        """Calculate profile completion percentage"""
        completed = 0
        total = 4
        
        # Check profile fields
        if hasattr(user, 'profile'):
            profile = user.profile
            if profile.name:
                completed += 1
            if profile.date_of_birth:
                completed += 1
        
        # Check email
        if user.email:
            completed += 1
        
        # Check Aadhaar verification
        if user.is_aadhaar_verified:
            completed += 1
        
        return {
            'completed': completed,
            'total': total,
            'percentage': int((completed / total) * 100)
        }


