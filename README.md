Minimal Django + DRF backend for NomiSafe

Minimal Django + DRF backend for NomiSafe

This project includes:

- Django project `nomisafe_backend`
- One app `accounts` with a user model that uses `phone_number` as the username field.

Auth flow (server-driven OTP using Twilio)

1. Client requests an OTP be sent to a phone number via POST /api/auth/otp/request/.
2. Backend generates a one-time numeric code, stores a hashed record with expiry, and sends the code via Twilio (or Textbelt) SMS.
3. Client submits the received code to POST /api/auth/otp/verify/.
4. Backend validates code, marks it used, creates (or returns) the user, and returns JWT tokens.

Setup

1. Create & activate venv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Twilio setup

- Create a Twilio account (you mentioned you already did).
- Note your `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and buy or use a trial Twilio phone number for `TWILIO_FROM_NUMBER`.
- For development, Twilio trial accounts can only send to verified phone numbers. Add your test number to Twilio or upgrade.

4. Environment variables (zsh example)

```bash
export SMS_PROVIDER=twilio
export TWILIO_ACCOUNT_SID=your_sid
export TWILIO_AUTH_TOKEN=your_token
export TWILIO_FROM_NUMBER=+1555XXXXXXX
```

If you want the simpler free option for development use `textbelt` as `SMS_PROVIDER` and set `TEXTBELT_KEY`.

5. Run migrations & start server

```bash
python manage.py migrate
python manage.py runserver
```

API

- POST /api/auth/otp/request/ — body: { "phone_number": "+15551234567" }
- POST /api/auth/otp/verify/ — body: { "phone_number": "+15551234567", "otp": "123456" }

On success the verify endpoint returns the user id, phone_number and JWT tokens (`access` and `refresh`).

Notes & security

- OTPs are hashed in the database and marked used after verification.
- Throttle requests in production to prevent abuse.
- Use HTTPS in production.
- For production delivery and scale use Twilio; for quick dev use Textbelt or Twilio trial numbers.
