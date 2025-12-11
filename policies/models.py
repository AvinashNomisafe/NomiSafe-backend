from django.db import models
from django.conf import settings
from django.utils import timezone


def get_policy_storage():
    """
    Dynamically get the storage backend based on settings
    Allows easy switching between local and S3 storage
    """
    if getattr(settings, 'USE_S3_STORAGE', False):
        from nomisafe_backend.storages import PolicyDocumentStorage
        return PolicyDocumentStorage()
    return None


class Policy(models.Model):
    INSURANCE_TYPES = [
        ('LIFE', 'Life Insurance'),
        ('HEALTH', 'Health Insurance'),
    ]
    
    AI_EXTRACTION_STATUS = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='policies'
    )
    
    # Basic Information 
    name = models.CharField(max_length=255, help_text="Policy name or identifier")
    document = models.FileField(upload_to='', storage=get_policy_storage())
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # AI-Extracted Fields
    insurance_type = models.CharField(max_length=20, choices=INSURANCE_TYPES, blank=True, null=True)
    policy_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    insurer_name = models.CharField(max_length=255, blank=True, null=True)
    
    # AI Extraction Status
    ai_extraction_status = models.CharField(
        max_length=20, 
        choices=AI_EXTRACTION_STATUS, 
        default='PENDING',
        db_index=True
    )
    ai_extracted_at = models.DateTimeField(blank=True, null=True)
    ai_extraction_error = models.TextField(blank=True, null=True)
    
    # User Verification
    is_verified_by_user = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    
    # Status (Legacy - keeping for compatibility)
    is_active = models.BooleanField(default=True)
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True, null=True)
    last_processed = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name_plural = 'Policies'
        indexes = [
            models.Index(fields=['user', 'insurance_type']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['policy_number']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.get_insurance_type_display() if self.insurance_type else 'Unknown'}"


class PolicyCoverage(models.Model):
    """Coverage and financial details"""
    
    PREMIUM_FREQUENCY = [
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('HALF_YEARLY', 'Half Yearly'),
        ('YEARLY', 'Yearly'),
    ]
    
    policy = models.OneToOneField(
        Policy, 
        on_delete=models.CASCADE, 
        related_name='coverage'
    )
    
    # Financial Details
    sum_assured = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    premium_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    premium_frequency = models.CharField(
        max_length=20, 
        choices=PREMIUM_FREQUENCY, 
        blank=True, 
        null=True
    )
    maturity_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        blank=True, 
        null=True,
        help_text="Amount payable on maturity (guaranteed returns)"
    )
    
    # Important Dates
    issue_date = models.DateField(blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True, db_index=True)
    maturity_date = models.DateField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['end_date']),
            models.Index(fields=['start_date']),
        ]
    
    @property
    def is_expired(self):
        if self.end_date:
            return self.end_date < timezone.now().date()
        return False
    
    @property
    def days_until_expiry(self):
        if self.end_date:
            delta = self.end_date - timezone.now().date()
            return delta.days
        return None
    
    def __str__(self):
        return f"Coverage for {self.policy.name}"

class PolicyNominee(models.Model):
    """Nominee/Beneficiary information"""
    policy = models.ForeignKey(
        Policy, 
        on_delete=models.CASCADE, 
        related_name='nominees'
    )
    
    name = models.CharField(max_length=255)
    relationship = models.CharField(max_length=100, blank=True, null=True)
    allocation_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=100.00,
        help_text="Percentage of sum assured allocated to this nominee"
    )
    date_of_birth = models.DateField(blank=True, null=True)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        ordering = ['-allocation_percentage']
    
    def __str__(self):
        return f"{self.name} - {self.policy.name}"


class PolicyBenefit(models.Model):
    """Individual benefits/coverages"""
    BENEFIT_TYPES = [
        ('BASE', 'Base Coverage'),
        ('RIDER', 'Rider'),
        ('ADDON', 'Add-on'),
        ('BONUS', 'Bonus'),
    ]
    
    policy = models.ForeignKey(
        Policy, 
        on_delete=models.CASCADE, 
        related_name='benefits'
    )
    
    benefit_type = models.CharField(max_length=20, choices=BENEFIT_TYPES, default='BASE')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    coverage_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['benefit_type', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.policy.name}"


class PolicyExclusion(models.Model):
    """Policy exclusions"""
    policy = models.ForeignKey(
        Policy, 
        on_delete=models.CASCADE, 
        related_name='exclusions'
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    class Meta:
        ordering = ['title']
    
    def __str__(self):
        return f"{self.title} - {self.policy.name}"


class HealthInsuranceDetails(models.Model):
    """Specific details for health insurance"""
    POLICY_TYPES = [
        ('INDIVIDUAL', 'Individual'),
        ('FAMILY', 'Family Floater'),
        ('SENIOR_CITIZEN', 'Senior Citizen'),
    ]
    
    policy = models.OneToOneField(
        Policy, 
        on_delete=models.CASCADE, 
        related_name='health_details'
    )
    
    policy_type = models.CharField(max_length=50, choices=POLICY_TYPES, blank=True, null=True)
    room_rent_limit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    co_payment_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    network_hospitals_count = models.IntegerField(blank=True, null=True)
    cashless_facility = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Health Details - {self.policy.name}"


class CoveredMember(models.Model):
    """Family members covered under health insurance"""
    health_insurance = models.ForeignKey(
        HealthInsuranceDetails, 
        on_delete=models.CASCADE, 
        related_name='covered_members'
    )
    
    name = models.CharField(max_length=255)
    relationship = models.CharField(max_length=50)
    date_of_birth = models.DateField(blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    pre_existing_conditions = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} - {self.relationship}"


class ExtractedDocument(models.Model):
    """Store extracted text and AI processing metadata"""
    policy = models.OneToOneField(
        Policy, 
        on_delete=models.CASCADE, 
        related_name='extracted_document'
    )
    
    raw_text = models.TextField(blank=True, null=True)
    structured_data = models.JSONField(default=dict, blank=True)
    extraction_timestamp = models.DateTimeField(auto_now_add=True)
    extraction_model = models.CharField(max_length=100, default='gemini-pro')
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    
    def __str__(self):
        return f"Extracted data - {self.policy.name}"