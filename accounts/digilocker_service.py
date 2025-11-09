import requests
from django.conf import settings
from urllib.parse import urlencode
import base64
import json

class DigiLockerService:
    BASE_URL = 'https://api.digitallocker.gov.in/public/oauth2/1'
    REDIRECT_URI = settings.DIGILOCKER_REDIRECT_URI
    CLIENT_ID = settings.DIGILOCKER_CLIENT_ID
    CLIENT_SECRET = settings.DIGILOCKER_CLIENT_SECRET

    @classmethod
    def get_auth_url(cls):
        """Generate DigiLocker authorization URL"""
        params = {
            'response_type': 'code',
            'client_id': cls.CLIENT_ID,
            'redirect_uri': cls.REDIRECT_URI,
            'state': 'state',
        }
        return f"{cls.BASE_URL}/authorize?{urlencode(params)}"

    @classmethod
    def get_access_token(cls, code):
        """Exchange authorization code for access token"""
        url = f"{cls.BASE_URL}/token"
        auth_string = base64.b64encode(
            f"{cls.CLIENT_ID}:{cls.CLIENT_SECRET}".encode()
        ).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_string}'
        }

        data = {
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': cls.REDIRECT_URI,
        }

        response = requests.post(url, headers=headers, data=data)
        return response.json()

    @classmethod
    def get_aadhaar_file(cls, access_token):
        """Fetch Aadhaar card from DigiLocker"""
        url = f"{cls.BASE_URL}/files/issued/AADHAAR"
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        response = requests.get(url, headers=headers)
        return response.json()

    @classmethod
    def verify_aadhaar(cls, access_token):
        """Verify Aadhaar details from DigiLocker"""
        aadhaar_data = cls.get_aadhaar_file(access_token)
        if not aadhaar_data.get('uri'):
            return False, None
        
        # Get the actual file
        file_response = requests.get(
            aadhaar_data['uri'],
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        if file_response.status_code != 200:
            return False, None

        # Extract and return last 4 digits of Aadhaar
        # In production, implement proper XML parsing of the Aadhaar card data
        aadhaar_last_4 = "XXXX"  # Replace with actual extraction
        return True, aadhaar_last_4