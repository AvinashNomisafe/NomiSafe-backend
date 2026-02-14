import google.generativeai as genai
from django.conf import settings
import json
import tempfile
import os
import logging
import time
from google.api_core import exceptions as google_exceptions

genai.configure(api_key=settings.GEMINI_API_KEY)

# Configure logger
logger = logging.getLogger(__name__)

class PolicyAIExtractor:
    def __init__(self):
        # Use free Gemini 2.0 Flash model
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    def extract_policy_preview(self, policy_document) -> dict:
        """
        Extract data from policy for user preview/verification
        Returns structured data without saving to database
        policy_document: Django FileField object
        """
        try:
            # Upload PDF directly to Gemini
            uploaded_file = self._upload_to_gemini(policy_document)
            
            # Step 1: Validate document is an insurance policy
            is_valid, validation_msg = self._validate_insurance_document(uploaded_file)
            if not is_valid:
                raise ValueError(validation_msg)
            
            # Step 2: Identify insurance type
            insurance_type = self._identify_insurance_type(uploaded_file)
            
            # Step 3: Extract data based on type
            if insurance_type == 'LIFE':
                extracted_data = self._extract_life_insurance_data(uploaded_file)
            elif insurance_type == 'HEALTH':
                extracted_data = self._extract_health_insurance_data(uploaded_file)
            elif insurance_type == 'MOTOR':
                extracted_data = self._extract_motor_insurance_data(uploaded_file)
            else:
                raise ValueError(f"This document doesn't appear to be a valid Health, Life, or Motor insurance policy. Please upload only insurance policy documents.")
            
            # Add insurance type to response
            extracted_data['insurance_type'] = insurance_type
            
            return extracted_data
            
        except Exception as e:
            raise e
    
    def _upload_to_gemini(self, file_field):
        """Upload PDF file to Gemini API with robust retry/backoff"""
        # Create a temporary file to store the PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            # Read file content from S3 or local storage
            file_field.open('rb')
            content = file_field.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        # Check file size (Gemini has limits)
        file_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
        logger.info(f"PDF file size: {file_size_mb:.2f} MB")
        
        if file_size_mb > 20:  # Gemini free tier limit
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise ValueError(f"PDF file too large ({file_size_mb:.2f} MB). Maximum size is 20 MB.")
        
        max_retries = 5
        retry_delay = 3
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Uploading to Gemini (attempt {attempt + 1}/{max_retries})...")
                # Use resumable upload for files > 10MB
                resumable = file_size_mb > 10
                uploaded_file = genai.upload_file(
                    tmp_path, 
                    mime_type='application/pdf',
                    resumable=resumable
                )
                logger.info("File uploaded successfully to Gemini")
                return uploaded_file
            except BrokenPipeError as e:
                logger.warning(f"Broken pipe error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise ValueError("Failed to upload PDF to AI service after multiple attempts. This could be due to network issues or file size. Please try again.")
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Error uploading to Gemini: {type(e).__name__}: {err_msg}")
                # Handle transient socket errors like "Can't assign requested address" or 503
                transient = (
                    'assign requested address' in err_msg.lower()
                    or '503' in err_msg
                    or 'temporarily unavailable' in err_msg.lower()
                )
                if transient and attempt < max_retries - 1:
                    wait_for = retry_delay
                    logger.info(f"Transient upload error. Backing off {wait_for}s and retrying...")
                    time.sleep(wait_for)
                    retry_delay = min(retry_delay * 2, 30)
                    continue
                # Non-transient or last attempt -> fail
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise ValueError(f"Failed to upload PDF to AI service: {err_msg}")
            finally:
                # Only clean up on last attempt or success
                if attempt == max_retries - 1 or 'uploaded_file' in locals():
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
    
    def _validate_insurance_document(self, uploaded_file) -> tuple:
        """
        Validate if the uploaded document is actually an insurance policy.
        Returns (is_valid: bool, message: str)
        """
        prompt = """
        Analyze this document carefully and determine if it is an Indian Insurance Policy document.
        
        An insurance policy document should contain:
        - Policy number
        - Insurance company name
        - Premium details or sum assured
        - Policy terms and conditions
        - Coverage details
        
        This is NOT an insurance policy if it is:
        - A bill, invoice, or receipt
        - A bank statement
        - An ID card (Aadhaar, PAN, etc.)
        - A medical prescription or report
        - A general document or letter
        - Any other non-insurance document
        
        Respond with ONLY:
        "VALID" if this is a Life Insurance, Health Insurance, or Motor/Vehicle Insurance policy document
        "INVALID: <reason>" if this is not an insurance policy (e.g., "INVALID: This appears to be a medical prescription")
        """
        
        response = self.model.generate_content([uploaded_file, prompt])
        result = response.text.strip()
        
        if result.upper().startswith('VALID'):
            return (True, "Valid insurance policy document")
        elif result.upper().startswith('INVALID'):
            # Extract reason after "INVALID:"
            reason = result.split(':', 1)[1].strip() if ':' in result else "This document is not an insurance policy"
            return (False, f"Invalid document: {reason}. Please upload only Life, Health, or Motor insurance policy documents.")
        else:
            # Unclear response, be conservative
            return (False, "Unable to verify this as a valid insurance policy document. Please upload only Life, Health, or Motor insurance policy documents.")
    
    def _identify_insurance_type(self, uploaded_file) -> str:
        """Identify the type of insurance from document"""
        prompt = """
        Analyze this Indian insurance policy document and identify the insurance type.
        
        Return ONLY one of these exact values:
        - LIFE (for Life Insurance, Term Insurance, Endowment, ULIP, Whole Life, Money Back, etc.)
        - HEALTH (for Health Insurance, Mediclaim, Family Floater, Critical Illness, Top-up, etc.)
        - MOTOR (for Car Insurance, Two Wheeler Insurance, Vehicle Insurance, Motor Insurance)
        - OTHER (if it's none of the above)
        
        Return only the insurance type code (LIFE, HEALTH, MOTOR, or OTHER), nothing else.
        """
        
        response = self.model.generate_content([uploaded_file, prompt])
        insurance_type = response.text.strip().upper()
        
        if insurance_type not in ['LIFE', 'HEALTH', 'MOTOR']:
            return 'OTHER'  # Will be rejected
        
        return insurance_type
    
    def _extract_life_insurance_data(self, uploaded_file) -> dict:
        """Extract data specific to Life Insurance policies"""
        prompt = """
        You are an expert at analyzing Indian Life Insurance policy documents.
        Extract the following information and return it as valid JSON.
        
        {
            "policy_number": "string",
            "insurer_name": "string (e.g., LIC, HDFC Life, ICICI Prudential, Max Life)",
            "coverage": {
                "sum_assured": number (in rupees, no commas),
                "premium_amount": number (in rupees, no commas),
                "premium_frequency": "MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY",
                "maturity_amount": number or null (guaranteed amount payable at maturity, for endowment/money-back policies),
                "issue_date": "YYYY-MM-DD or null",
                "start_date": "YYYY-MM-DD or null",
                "end_date": "YYYY-MM-DD or null",
                "maturity_date": "YYYY-MM-DD or null"
            },
            "nominees": [
                {
                    "name": "string",
                    "relationship": "string (e.g., Spouse, Son, Daughter, Father, Mother)",
                    "allocation_percentage": number (e.g., 100.00)
                }
            ],
            "benefits": [
                {
                    "benefit_type": "BASE/RIDER/ADDON/BONUS",
                    "name": "string",
                    "description": "string or null",
                    "coverage_amount": number or null
                }
            ],
            "exclusions": [
                {
                    "title": "string",
                    "description": "string"
                }
            ]
        }
        
        Important:
        - Use YYYY-MM-DD format for dates
        - Remove commas from numbers
        - If info not found, use null
        - Include all nominees found
        - List major benefits and riders
        - List 3-5 key exclusions
        
        Return ONLY valid JSON.
        """
        
        logger.info("Sending request to Gemini API for life insurance extraction")
        response = self.model.generate_content([uploaded_file, prompt])
        
        logger.info("Received response from Gemini API")
        logger.debug(f"Raw response text length: {len(response.text) if response.text else 0}")
        logger.debug(f"Raw response text: {response.text[:1000]}...")  # Log first 1000 chars
        
        return self._parse_json_response(response.text)
    
    def _extract_health_insurance_data(self, uploaded_file) -> dict:
        """Extract data specific to Health Insurance policies"""
        prompt = """
        You are an expert at analyzing Indian Health Insurance policy documents.
        Extract the following information and return it as valid JSON.
        
        {
            "policy_number": "string",
            "insurer_name": "string (e.g., Star Health, HDFC Ergo, Care Health, Niva Bupa)",
            "coverage": {
                "sum_assured": number (in rupees, no commas),
                "premium_amount": number (in rupees, no commas),
                "premium_frequency": "MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY",
                "maturity_amount": number or null (if policy has maturity benefit),
                "issue_date": "YYYY-MM-DD or null",
                "start_date": "YYYY-MM-DD or null",
                "end_date": "YYYY-MM-DD or null",
                "maturity_date": "YYYY-MM-DD or null"
            },
            "health_details": {
                "policy_type": "INDIVIDUAL/FAMILY/SENIOR_CITIZEN",
                "room_rent_limit": number or null,
                "co_payment_percentage": number or null,
                "cashless_facility": true/false
            },
            "covered_members": [
                {
                    "name": "string",
                    "relationship": "string (Self/Spouse/Son/Daughter/Father/Mother)",
                    "age": number or null
                }
            ],
            "benefits": [
                {
                    "benefit_type": "BASE/RIDER/ADDON",
                    "name": "string (e.g., Hospitalization, Ambulance, OPD)",
                    "description": "string or null",
                    "coverage_amount": number or null
                }
            ],
            "exclusions": [
                {
                    "title": "string",
                    "description": "string"
                }
            ]
        }
        
        Important:
        - Use YYYY-MM-DD format for dates
        - Remove commas from numbers
        - If info not found, use null
        - Include all family members
        - List major benefits (hospitalization, day care, ambulance, etc.)
        - List 5-7 key exclusions
        
        Return ONLY valid JSON.
        """
        
        logger.info("Sending request to Gemini API for health insurance extraction")
        response = self.model.generate_content([uploaded_file, prompt])
        
        logger.info("Received response from Gemini API")
        logger.debug(f"Raw response text length: {len(response.text) if response.text else 0}")
        logger.debug(f"Raw response text: {response.text[:1000]}...")  # Log first 1000 chars
        
        return self._parse_json_response(response.text)
    
    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON response from Gemini, handling markdown code blocks and trailing commas"""
        logger.info("Parsing JSON response from Gemini")
        logger.debug(f"Response text to parse (first 500 chars): {response_text[:500]}")
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Initial JSON parse failed: {e}. Attempting to clean response.")
            logger.debug(f"Full response text that failed to parse:\n{response_text}")
            
            # Try to extract JSON from markdown code blocks
            clean_text = response_text.strip()
            if clean_text.startswith('```json'):
                clean_text = clean_text[7:]
            elif clean_text.startswith('```'):
                clean_text = clean_text[3:]
            if clean_text.endswith('```'):
                clean_text = clean_text[:-3]
            
            clean_text = clean_text.strip()
            
            # Try to fix common JSON issues
            # Remove trailing commas before closing brackets/braces
            import re
            clean_text = re.sub(r',\s*([}\]])', r'\1', clean_text)
            
            try:
                logger.info("Attempting to parse cleaned response text as JSON")
                return json.loads(clean_text)
            except json.JSONDecodeError as e:
                logger.error(f"Cleaned JSON parse failed: {e}")
                logger.error(f"Full cleaned text:\n{clean_text}")
                raise ValueError(f"Could not parse JSON response from AI model. The AI returned invalid JSON: {str(e)}")
    
    def _extract_motor_insurance_data(self, uploaded_file) -> dict:
        """Extract data specific to Motor/Vehicle Insurance policies"""
        prompt = """
        You are an expert at analyzing Indian Motor/Vehicle Insurance policy documents.
        Extract the following information and return it as valid JSON.
        
        {
            "policy_number": "string",
            "insurer_name": "string (e.g., ICICI Lombard, HDFC Ergo, Bajaj Allianz, Reliance General)",
            "coverage": {
                "sum_assured": number or null (total cover amount in rupees, no commas),
                "premium_amount": number (in rupees, no commas),
                "premium_frequency": "MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY",
                "maturity_amount": null,
                "issue_date": "YYYY-MM-DD or null",
                "start_date": "YYYY-MM-DD or null (policy start date)",
                "end_date": "YYYY-MM-DD or null (policy expiry date)",
                "maturity_date": null
            },
            "motor_details": {
                "vehicle_type": "TWO_WHEELER/FOUR_WHEELER/COMMERCIAL",
                "policy_type": "COMPREHENSIVE/THIRD_PARTY/STANDALONE_OD",
                "vehicle_make": "string (e.g., Maruti Suzuki, Honda, Hyundai, Hero, Bajaj)",
                "vehicle_model": "string (e.g., Swift, City, i20, Splendor, Pulsar)",
                "registration_number": "string (e.g., MH01AB1234)",
                "engine_number": "string or null",
                "chassis_number": "string or null",
                "year_of_manufacture": number or null (e.g., 2020),
                "idv": number or null (Insured Declared Value in rupees, no commas),
                "own_damage_cover": number or null (OD cover amount),
                "third_party_cover": number or null (TP cover amount),
                "ncb_percentage": number or null (No Claim Bonus percentage, e.g., 20.00, 50.00),
                "previous_policy_number": "string or null",
                "has_zero_depreciation": true/false,
                "has_engine_protection": true/false,
                "has_roadside_assistance": true/false
            },
            "benefits": [
                {
                    "benefit_type": "BASE/RIDER/ADDON",
                    "name": "string (e.g., Own Damage, Third Party Liability, Personal Accident Cover, Zero Depreciation, Engine Protection)",
                    "description": "string or null",
                    "coverage_amount": number or null
                }
            ],
            "exclusions": [
                {
                    "title": "string",
                    "description": "string"
                }
            ]
        }
        
        Important:
        - Use YYYY-MM-DD format for dates
        - Remove commas from numbers
        - If info not found, use null
        - IDV is the current market value of the vehicle
        - For COMPREHENSIVE policy, both own damage and third party are covered
        - For THIRD_PARTY, only third party liability is covered
        - NCB (No Claim Bonus) is the discount percentage for claim-free years
        - List major benefits/add-ons (Zero Depreciation, Engine Protection, Road Side Assistance, etc.)
        - List 3-5 key exclusions
        
        Return ONLY valid JSON.
        """
        
        logger.info("Sending request to Gemini API for motor insurance extraction")
        response = self.model.generate_content([uploaded_file, prompt])
        
        logger.info("Received response from Gemini API")
        logger.debug(f"Raw response text length: {len(response.text) if response.text else 0}")
        logger.debug(f"Raw response text: {response.text[:1000]}...")  # Log first 1000 chars
        
        return self._parse_json_response(response.text)
