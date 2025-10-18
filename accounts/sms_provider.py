import os
from django.conf import settings

def send_sms_twilio(phone: str, body: str):
    from twilio.rest import Client

    sid = os.environ.get('TWILIO_ACCOUNT_SID')
    token = os.environ.get('TWILIO_AUTH_TOKEN')
    from_number = os.environ.get('TWILIO_FROM_NUMBER')
    if not sid or not token or not from_number:
        raise RuntimeError('Twilio credentials not configured')
    client = Client(sid, token)
    msg = client.messages.create(body=body, from_=from_number, to=phone)
    return msg.sid


def send_sms(phone: str, body: str):
    return send_sms_twilio(phone, body)
