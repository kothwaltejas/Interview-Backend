#!/usr/bin/env python
"""Test the /api/db/resumes/upload endpoint to diagnose 400 errors"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env FIRST
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

import httpx
import asyncio
import json

async def test_db_upload_endpoint():
    """Test the /api/db/resumes/upload endpoint"""
    
    print("\n" + "="*60)
    print("DATABASE RESUME UPLOAD TEST")
    print("="*60)
    
    # Create a test PDF
    print("\n1️⃣ Creating test PDF...")
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test Resume) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000229 00000 n 
0000000323 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
401
%%EOF"""
    print(f"✅ Test PDF created ({len(pdf_content)} bytes)")
    
    # Test without auth (should fail with auth error)
    print("\n2️⃣ Testing /api/db/resumes/upload WITHOUT auth (should fail)...")
    try:
        async with httpx.AsyncClient() as client:
            files = {'file': ('test_resume.pdf', pdf_content, 'application/pdf')}
            response = await client.post(
                'http://localhost:8000/api/db/resumes/upload',
                files=files,
                timeout=30.0
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test: Get actual Supabase JWT token
    print("\n3️⃣ Note: To test with auth, you need a valid JWT token from Supabase auth.")
    print("   Current test using /api/resume/parse (auth optional)...")
    
    # Test the working endpoint
    print("\n4️⃣ Testing /api/resume/parse (for comparison)...")
    try:
        async with httpx.AsyncClient() as client:
            files = {'file': ('test_resume.pdf', pdf_content, 'application/pdf')}
            response = await client.post(
                'http://localhost:8000/api/resume/parse',
                files=files,
                timeout=30.0
            )
            
            print(f"Status Code: {response.status_code}")
            result = response.json()
            print(f"Success: {result.get('success')}")
            print(f"Saved to DB: {result.get('saved_to_database')}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*60)
    print("Tests Completed!")
    print("="*60)

if __name__ == "__main__":
    print("\n⚠️  Make sure the backend is running on http://localhost:8000")
    asyncio.run(test_db_upload_endpoint())
