#!/usr/bin/env python
"""Test the actual HTTP endpoint to see the 400 error"""

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

async def test_http_endpoint():
    """Test the actual HTTP endpoint"""
    
    print("\n" + "="*60)
    print("HTTP ENDPOINT TEST")
    print("="*60)
    
    # Test 1: Create a valid test PDF
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
    
    # Test 2: Test with valid PDF
    print("\n2️⃣ Testing POST /api/resume/parse with valid PDF...")
    try:
        async with httpx.AsyncClient() as client:
            files = {'file': ('test_resume.pdf', pdf_content, 'application/pdf')}
            response = await client.post(
                'http://localhost:8000/api/resume/parse',
                files=files,
                timeout=30.0
            )
            
            print(f"Status Code: {response.status_code}")
            
            try:
                result = response.json()
                print(f"Response: {json.dumps(result, indent=2)[:500]}")
            except:
                print(f"Response Text: {response.text[:500]}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Test with empty file
    print("\n3️⃣ Testing with EMPTY file (should return 400)...")
    try:
        async with httpx.AsyncClient() as client:
            files = {'file': ('empty.pdf', b'', 'application/pdf')}
            response = await client.post(
                'http://localhost:8000/api/resume/parse',
                files=files,
                timeout=30.0
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 4: Test with non-PDF file
    print("\n4️⃣ Testing with non-PDF file (should return 400)...")
    try:
        async with httpx.AsyncClient() as client:
            files = {'file': ('resume.txt', b'Not a PDF', 'text/plain')}
            response = await client.post(
                'http://localhost:8000/api/resume/parse',
                files=files,
                timeout=30.0
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*60)
    print("Tests Completed!")
    print("="*60)

if __name__ == "__main__":
    print("\n⚠️  Make sure the backend is running on http://localhost:8000")
    print("   If not listening, the test will fail.\n")
    asyncio.run(test_http_endpoint())
