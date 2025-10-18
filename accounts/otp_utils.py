import secrets
import hashlib
import hmac
from django.conf import settings


def hash_otp(code: str, salt: str):
    key = settings.SECRET_KEY.encode()
    return hmac.new(key + salt.encode(), code.encode(), hashlib.sha256).hexdigest()


def generate_code(length=6):
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def default_otp_ttl():
    return getattr(settings, 'OTP_TTL_SECONDS', 300)
