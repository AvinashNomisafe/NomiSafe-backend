from rest_framework import serializers
from .models import (
    Policy, PolicyCoverage, PolicyNominee, PolicyBenefit,
    PolicyExclusion, HealthInsuranceDetails, CoveredMember
)


class PolicyUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading a new policy"""
    document = serializers.FileField(required=True)
    name = serializers.CharField(max_length=255, required=True)

    class Meta:
        model = Policy
        fields = ['id', 'name', 'document', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

    def create(self, validated_data):
        user = self.context['request'].user
        return Policy.objects.create(user=user, **validated_data)


class PolicyListSerializer(serializers.ModelSerializer):
    """Serializer for policy list view"""
    insurer_name = serializers.CharField(read_only=True)
    policy_number = serializers.CharField(read_only=True)
    insurance_type = serializers.CharField(read_only=True)
    sum_assured = serializers.SerializerMethodField()
    premium_amount = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = Policy
        fields = [
            'id', 'name', 'insurance_type', 'policy_number', 
            'insurer_name', 'sum_assured', 'premium_amount',
            'end_date', 'is_expired', 'uploaded_at'
        ]
    
    def get_sum_assured(self, obj):
        if hasattr(obj, 'coverage') and obj.coverage:
            return float(obj.coverage.sum_assured) if obj.coverage.sum_assured else None
        return None
    
    def get_premium_amount(self, obj):
        if hasattr(obj, 'coverage') and obj.coverage:
            return float(obj.coverage.premium_amount) if obj.coverage.premium_amount else None
        return None
    
    def get_end_date(self, obj):
        if hasattr(obj, 'coverage') and obj.coverage and obj.coverage.end_date:
            return obj.coverage.end_date.isoformat()
        return None
    
    def get_is_expired(self, obj):
        if hasattr(obj, 'coverage') and obj.coverage:
            return obj.coverage.is_expired
        return False


class PolicyNomineeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyNominee
        fields = ['id', 'name', 'relationship', 'allocation_percentage', 'date_of_birth', 'contact_number']


class PolicyBenefitSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyBenefit
        fields = ['id', 'benefit_type', 'name', 'description', 'coverage_amount', 'is_active']


class PolicyExclusionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyExclusion
        fields = ['id', 'title', 'description']


class CoveredMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoveredMember
        fields = ['id', 'name', 'relationship', 'date_of_birth', 'age', 'pre_existing_conditions']


class HealthInsuranceDetailsSerializer(serializers.ModelSerializer):
    covered_members = CoveredMemberSerializer(many=True, read_only=True)
    
    class Meta:
        model = HealthInsuranceDetails
        fields = [
            'id', 'policy_type', 'room_rent_limit', 'co_payment_percentage',
            'network_hospitals_count', 'cashless_facility', 'covered_members'
        ]


class PolicyCoverageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyCoverage
        fields = [
            'id', 'sum_assured', 'premium_amount', 'premium_frequency',
            'issue_date', 'start_date', 'end_date', 'maturity_date',
            'is_expired', 'days_until_expiry'
        ]


class PolicyDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single policy view"""
    coverage = PolicyCoverageSerializer(read_only=True)
    nominees = PolicyNomineeSerializer(many=True, read_only=True)
    benefits = PolicyBenefitSerializer(many=True, read_only=True)
    exclusions = PolicyExclusionSerializer(many=True, read_only=True)
    health_details = HealthInsuranceDetailsSerializer(read_only=True)
    document_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Policy
        fields = [
            'id', 'name', 'insurance_type', 'policy_number', 'insurer_name',
            'uploaded_at', 'is_active', 'coverage', 'nominees', 'benefits',
            'exclusions', 'health_details', 'document_url'
        ]
    
    def get_document_url(self, obj):
        if obj.document:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document.url)
        return None
