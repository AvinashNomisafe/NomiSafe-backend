import google.generativeai as genai
import os
import base64
from django.conf import settings

# Configure the Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY)

def get_policy_benefits_summary(pdf_path):
    """Process PDF content using Gemini AI to extract benefits summary."""
    try:
        # Initialize Gemini model with vision capabilities
        model = genai.GenerativeModel('gemini-2.5-flash-lite')  # Changed to vision model
        
        # Verify file exists and is accessible
        if not os.path.exists(pdf_path):
            return "ERROR: PDF file not found."
        
        # Read the file
        with open(pdf_path, 'rb') as file:
            file_content = file.read()
        
        # Create the prompt with specific instructions
        prompt = """Analyze this policy document and provide a concise summary of:
        1. Key benefits and coverage details
        2. Important terms and conditions
        3. Coverage limits
        Don't add any md elements in the response."""
        
        # Prepare the PDF data
        pdf_data = {
            "mime_type": "application/pdf",
            "data": base64.b64encode(file_content).decode()
        }
        
        # Send content to Gemini with modified settings
        response = model.generate_content(
            contents=[{
                "parts": [
                    {"text": prompt},
                    pdf_data
                ]
            }],
            safety_settings=[
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ],
            generation_config={
                "temperature": 0.4,
                "top_p": 1,
                "top_k": 32,
                "max_output_tokens": 2048,
            }
        )

        # Force response generation
        response.resolve()

        # Try to get the response text directly
        try:
            return response.text
        except Exception as text_error:
            print(f"Error accessing response.text: {str(text_error)}")
            
            # Fallback to accessing parts if text is not available
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts'):
                        parts = candidate.content.parts
                        if parts:
                            return ' '.join(part.text for part in parts if hasattr(part, 'text'))
            
            return "ERROR: Could not extract response text from Gemini API"
            
    except Exception as e:
        print(f"Error processing with Gemini: {str(e)}")
        return f"ERROR: An error occurred while processing the document: {str(e)}"