import pypdf
import io
import json
import re
import logging
from typing import Dict, Any, Optional, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# -------- Normalize Text --------
def normalize_text(text: str) -> str:
    """Clean and normalize extracted text."""
    if not text:
        return ""
    
    # Replace multiple spaces/tabs with single space
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Replace multiple newlines with double newline
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove non-printable characters except newlines
    text = ''.join(char for char in text if char.isprintable() or char in '\n\r\t')
    
    # Fix common OCR/extraction issues
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # CamelCase to spaces
    text = re.sub(r'(\w)([•●◦▪])', r'\1 \2', text)  # Add space before bullets
    text = re.sub(r'([•●◦▪])(\w)', r'\1 \2', text)  # Add space after bullets
    
    return text.strip()


# -------- Extract text from PDF --------
def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file content with multiple strategies."""
    text = ""
    
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = pypdf.PdfReader(pdf_file)
        
        # Strategy 1: Standard extraction
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        # Strategy 2: If standard extraction yields little text, try layout mode
        if len(text.strip()) < 100:
            logger.info("Standard extraction yielded little text, trying layout extraction")
            text = ""
            for page in pdf_reader.pages:
                try:
                    # Extract with layout preservation
                    page_text = page.extract_text(extraction_mode="layout")
                    if page_text:
                        text += page_text + "\n"
                except:
                    pass
        
        # Normalize the extracted text
        text = normalize_text(text)
        
        if not text:
            raise Exception("No text could be extracted from PDF")
            
        logger.info(f"Extracted {len(text)} characters from PDF")
        return text
        
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise Exception(f"PDF extraction failed: {str(e)}")


# -------- Clean JSON --------
def clean_json_response(response: str) -> str:
    """Clean and extract JSON from LLM response."""
    if not response:
        return "{}"
    
    # Remove markdown code blocks
    response = re.sub(r'```json\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'```\s*', '', response)
    
    # Remove any text before the first {
    first_brace = response.find('{')
    if first_brace != -1:
        response = response[first_brace:]
    
    # Remove any text after the last }
    last_brace = response.rfind('}')
    if last_brace != -1:
        response = response[:last_brace + 1]
    
    # Fix common JSON issues
    response = response.replace('\n', ' ')
    response = re.sub(r',\s*}', '}', response)  # Remove trailing commas
    response = re.sub(r',\s*]', ']', response)  # Remove trailing commas in arrays
    
    return response.strip() or "{}"


# -------- Get Prompt --------
def get_resume_prompt(resume_text: str) -> str:
    """Get the prompt for resume parsing."""
    return f"""You are an expert resume parser. Analyze the following resume text carefully and extract ALL information into a structured JSON format.

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON - no explanations, no markdown, no code blocks
2. Extract information even if the resume format is unusual or text is fragmented
3. Look for patterns like email addresses (contains @), phone numbers (digits with dashes/spaces)
4. Identify skills from technical terms, programming languages, tools, and frameworks mentioned anywhere
5. Parse education even if formatted differently (look for degree keywords: B.E., B.Tech, M.S., MBA, Bachelor, Master, PhD)
6. Extract work experience from sections with company names, job titles, and date ranges

Required JSON structure:
{{
  "name": "extracted full name or empty string",
  "email": "extracted email or empty string",
  "phone": "extracted phone or empty string",
  "location": "city/state/country if found or empty string",
  "summary": "professional summary/objective if present or empty string",
  "education": [
    {{
      "degree": "degree name",
      "field": "field of study",
      "institution": "school/university name",
      "year": "graduation year or date range",
      "gpa": "GPA if mentioned or empty string"
    }}
  ],
  "skills": ["skill1", "skill2", "skill3"],
  "experience": [
    {{
      "title": "job title",
      "company": "company name",
      "location": "job location if mentioned",
      "duration": "time period (e.g., Jan 2020 - Present)",
      "description": "key responsibilities and achievements"
    }}
  ],
  "projects": [
    {{
      "title": "project name",
      "tech": ["technology1", "technology2"],
      "description": "project description and achievements",
      "link": "project URL if mentioned"
    }}
  ],
  "certifications": ["certification1", "certification2"],
  "languages": ["language1", "language2"],
  "links": {{
    "linkedin": "linkedin URL if found",
    "github": "github URL if found",
    "portfolio": "portfolio URL if found"
  }}
}}

Resume Text:
---
{resume_text}
---

Return only the JSON object:"""


# -------- Parse Resume --------
def parse_resume_with_llm(file_content: bytes, max_retries: int = 3) -> Dict[str, Any]:
    """
    Parse resume from PDF file content using LLM.
    
    Args:
        file_content: PDF file content as bytes
        max_retries: Maximum number of retry attempts
        
    Returns:
        Dictionary containing parsed resume data or error information
    """
    from .llm_groq_config import chat_completion
    
    try:
        resume_text = extract_text_from_pdf(file_content)
        if not resume_text:
            return {"error": "Could not extract text from PDF"}
        
        # Use up to 6000 chars to capture more content
        prompt = get_resume_prompt(resume_text[:6000])

        for attempt in range(max_retries):
            try:
                response = chat_completion(prompt)
                if not response:
                    logger.error("No response from LLM")
                    if attempt == max_retries - 1:
                        return {"error": "No response from LLM"}
                    continue
                    
                cleaned_response = clean_json_response(response)
                parsed_data = json.loads(cleaned_response)
                
                logger.info("Resume parsed successfully")
                return parsed_data
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    return {
                        "error": "Failed to parse JSON after multiple attempts", 
                        "raw_response": response, 
                        "cleaned_response": cleaned_response
                    }
            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    return {"error": f"Failed to process resume: {str(e)}"}
                    
        return {"error": "Unexpected failure"}
        
    except Exception as e:
        logger.error(f"Critical error in parse_resume_with_llm: {e}")
        return {"error": f"Critical parsing error: {str(e)}"}


def parse_resume_from_file_path(file_path: str) -> Dict[str, Any]:
    """
    Parse resume from a file path.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Dictionary containing parsed resume data or error information
    """
    try:
        with open(file_path, 'rb') as file:
            file_content = file.read()
        return parse_resume_with_llm(file_content)
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return {"error": f"Could not read file: {str(e)}"}


def validate_parsed_resume(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and clean parsed resume data.
    
    Args:
        parsed_data: Raw parsed data from LLM
        
    Returns:
        Validated and cleaned resume data
    """
    if "error" in parsed_data:
        return parsed_data
    
    # Define default structure
    defaults = {
        "name": "",
        "email": "",
        "phone": "",
        "location": "",
        "summary": "",
        "education": [],
        "skills": [],
        "experience": [],
        "projects": [],
        "certifications": [],
        "languages": [],
        "links": {"linkedin": "", "github": "", "portfolio": ""}
    }
    
    # Merge with defaults
    for key, default_value in defaults.items():
        if key not in parsed_data:
            parsed_data[key] = default_value
        elif isinstance(default_value, list) and not isinstance(parsed_data[key], list):
            parsed_data[key] = []
        elif isinstance(default_value, dict) and not isinstance(parsed_data[key], dict):
            parsed_data[key] = default_value
    
    return parsed_data