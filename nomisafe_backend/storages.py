"""
Custom storage backends for AWS S3
"""
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class PolicyDocumentStorage(S3Boto3Storage):
    """
    Custom storage backend for policy documents in S3
    Allows easy switching between development and production buckets
    """
    location = 'policies'
    file_overwrite = False
    default_acl = 'private'
    
    def __init__(self, **settings):
        super().__init__(**settings)
        # Override bucket name if provided in settings
        if hasattr(settings, 'AWS_POLICY_STORAGE_BUCKET_NAME'):
            self.bucket_name = settings.AWS_POLICY_STORAGE_BUCKET_NAME


class AppNomineeDocumentStorage(S3Boto3Storage):
    """
    Custom storage backend for app nominee documents in S3
    """
    location = 'nominees'
    file_overwrite = False
    default_acl = 'private'


class PropertyDocumentStorage(S3Boto3Storage):
    """
    Custom storage backend for property documents in S3
    """
    location = 'properties'
    file_overwrite = False
    default_acl = 'private'
