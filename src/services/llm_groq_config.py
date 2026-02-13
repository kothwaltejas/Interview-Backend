import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def chat_completion(prompt: str, system_prompt: str = None, max_tokens: int = 4096, temperature: float = 0.1) -> Optional[str]:
    """Send a chat completion request to GROQ API directly via HTTP.
    
    Args:
        prompt: The user prompt
        system_prompt: Optional system prompt for context
        max_tokens: Maximum tokens in response
        temperature: Controls randomness (0.0-2.0). Lower = more deterministic, Higher = more creative
                     Recommended: 0.1 for evaluation, 0.3-0.5 for conversational
    """
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        logger.error("GROQ_API_KEY not found in environment variables")
        return None
    
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(GROQ_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from GROQ API: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Chat completion failed: {e}")
        return None

def test_connection() -> bool:
    """Test if GROQ connection is working."""
    try:
        result = chat_completion("Say 'OK' if you can hear me.")
        return result is not None and 'OK' in result.upper()
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False

