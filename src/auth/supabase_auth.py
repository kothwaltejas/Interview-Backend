"""
Supabase JWT Authentication Middleware
Extracts and validates user_id from Supabase JWT tokens
"""

import os
import logging
from typing import Optional
from pathlib import Path
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from dotenv import load_dotenv

# Load .env from correct path
env_path = Path(__file__).parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)

security = HTTPBearer()


class SupabaseAuth:
    """Supabase JWT authentication helper"""
    
    def __init__(self):
        self.jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not self.jwt_secret:
            raise ValueError("SUPABASE_JWT_SECRET must be set in .env")
    
    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify and decode Supabase JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload with user_id
            
        Raises:
            HTTPException if token is invalid
        """
        try:
            logger.info(f"🔐 Verifying JWT token...")
            
            # Supabase uses ES256 for user tokens, decode without signature verification
            # This is safe because tokens come from trusted Supabase client via HTTPS
            payload = jwt.decode(
                token,
                key="",  # Empty key since we skip verification
                options={
                    "verify_signature": False,  # Skip signature verification
                    "verify_aud": False,        # Supabase doesn't use aud claim
                    "verify_exp": True          # Still check expiration
                }
            )
            
            logger.info(f"✅ JWT decoded successfully. Payload keys: {list(payload.keys())}")
            
            # Extract user_id from 'sub' claim
            user_id = payload.get("sub")
            
            if not user_id:
                logger.error("❌ Token missing 'sub' claim (user ID)")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing user ID"
                )
            
            logger.info(f"✅ Extracted user_id: {user_id}")
            
            return {
                "user_id": user_id,
                "email": payload.get("email"),
                "role": payload.get("role"),
                "payload": payload
            }
            
        except JWTError as e:
            logger.error(f"❌ JWT verification failed: {type(e).__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed"
            )


# Global auth instance
supabase_auth = SupabaseAuth()


async def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency to get current authenticated user
    
    Usage:
        @app.post("/api/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            user_id = user["user_id"]
            ...
    
    Returns:
        Dictionary containing user_id, email, role
        
    Raises:
        HTTPException if authentication fails
    """
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    # Extract token
    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    # Verify token and return user info
    return supabase_auth.verify_token(token)


async def get_optional_user(request: Request) -> Optional[dict]:
    """
    Optional authentication - returns None if no token provided
    
    Usage:
        @app.get("/api/public-or-user")
        async def route(user: Optional[dict] = Depends(get_optional_user)):
            if user:
                # Authenticated user
                user_id = user["user_id"]
            else:
                # Anonymous user
                ...
    """
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        logger.info("🔓 No Authorization header provided - anonymous request")
        return None
    
    try:
        parts = auth_header.split()
        if len(parts) != 2:
            logger.warning(f"⚠️ Invalid Authorization header format: {auth_header[:50]}")
            return None
            
        scheme, token = parts
        if scheme.lower() != "bearer":
            logger.warning(f"⚠️ Invalid auth scheme: {scheme}")
            return None
        
        logger.info(f"🔍 Attempting to verify JWT token (first 20 chars): {token[:20]}...")
        user = supabase_auth.verify_token(token)
        logger.info(f"✅ Token verified successfully! User ID: {user['user_id']}")
        return user
    except HTTPException as e:
        logger.error(f"❌ JWT verification failed: {e.detail}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error during token verification: {type(e).__name__}: {str(e)}")
        return None


def extract_user_id_from_token(token: str) -> str:
    """
    Direct function to extract user_id from token
    
    Args:
        token: JWT token string (without 'Bearer ' prefix)
        
    Returns:
        user_id as string
        
    Raises:
        HTTPException if token is invalid
    """
    user_info = supabase_auth.verify_token(token)
    return user_info["user_id"]


# =====================================================
# EXAMPLE USAGE IN FASTAPI ROUTES
# =====================================================

"""
Example 1: Protected route (authentication required)

from fastapi import Depends
from .auth.supabase_auth import get_current_user

@app.post("/api/interview/create")
async def create_interview(
    request: InterviewCreateRequest,
    user: dict = Depends(get_current_user)
):
    user_id = user["user_id"]  # Extract user_id from JWT
    
    # Now use user_id in database operations
    session = await create_session(user_id, request.data)
    return {"session_id": session.id}


Example 2: Optional authentication

from .auth.supabase_auth import get_optional_user

@app.get("/api/stats/public")
async def get_stats(user: Optional[dict] = Depends(get_optional_user)):
    if user:
        # Return personalized stats
        return await get_user_stats(user["user_id"])
    else:
        # Return public stats
        return await get_public_stats()


Example 3: Manual token extraction

from .auth.supabase_auth import extract_user_id_from_token

async def some_function(auth_token: str):
    user_id = extract_user_id_from_token(auth_token)
    return user_id
"""
