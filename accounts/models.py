from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.conf import settings


def get_nominee_storage():
    if getattr(settings, 'USE_S3_STORAGE', False):
        from nomisafe_backend.storages import AppNomineeDocumentStorage
        return AppNomineeDocumentStorage()
    return None


def get_property_storage():
    if getattr(settings, 'USE_S3_STORAGE', False):
        from nomisafe_backend.storages import PropertyDocumentStorage
        return PropertyDocumentStorage()
    return None


class UserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('Phone number is required')
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    phone_number = models.CharField(max_length=24, unique=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_aadhaar_verified = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.phone_number


class UserProfile(models.Model):
    """Extended user profile information"""
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='profile',
        primary_key=True
    )
    name = models.CharField(max_length=255, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    alternate_phone = models.CharField(max_length=24, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profile'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
    
    def __str__(self):
        return f"Profile for {self.user.phone_number}"


class OTP(models.Model):
    phone_number = models.CharField(max_length=32, db_index=True)
    otp_hash = models.CharField(max_length=128)
    salt = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    used = models.BooleanField(default=False)
    provider_id = models.CharField(max_length=128, null=True, blank=True)

    def mark_used(self):
        self.used = True
        self.save(update_fields=['used'])


class AppNominee(models.Model):
    """App-level nominee (separate from policy nominees)"""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='app_nominee'
    )

    name = models.CharField(max_length=255)
    relationship = models.CharField(max_length=100, blank=True, null=True)
    contact_details = models.CharField(max_length=255, blank=True, null=True)
    id_proof_type = models.CharField(max_length=100, blank=True, null=True)
    aadhaar_number = models.CharField(max_length=16, blank=True, null=True)
    id_proof_file = models.FileField(upload_to='', storage=get_nominee_storage(), blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'App Nominee'
        verbose_name_plural = 'App Nominees'

    def __str__(self):
        return f"{self.name} ({self.user.phone_number})"


class Property(models.Model):
    """Property documents uploaded by the user"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='properties'
    )
    name = models.CharField(max_length=255)
    document = models.FileField(upload_to='', storage=get_property_storage())

    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.name} ({self.user.phone_number})"


class FirstConnect(models.Model):
    """First Connect emergency contacts (max 3 per user)"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='first_connects'
    )
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.name} - {self.phone_number} ({self.user.phone_number})"


