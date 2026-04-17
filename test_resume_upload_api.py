#!/usr/bin/env python
"""Test resume upload API to diagnose the 400 error"""

import asyncio
import sys
import io
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env FIRST
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    print(f"❌ .env not found at {env_path}")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_resume_upload():
    """Test resume upload without making HTTP requests"""
    
    print("\n" + "="*60)
    print("RESUME UPLOAD DIAGNOSTICS")
    print("="*60)
    
    # Test 1: Import modules
    print("\n1️⃣ Testing imports...")
    try:
        from services.resume_parser import parse_resume_with_llm, validate_parsed_resume
        print("✅ resume_parser imported successfully")
    except Exception as e:
        print(f"❌ Failed to import resume_parser: {e}")
        return
    
    # Test 2: Create a test PDF
    print("\n2️⃣ Creating test PDF...")
    try:
        # Create a minimal PDF
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
    except Exception as e:
        print(f"❌ Failed to create test PDF: {e}")
        return
    
    # Test 3: Test parsing
    print("\n3️⃣ Testing resume parsing with LLM...")
    try:
        parsed_data = parse_resume_with_llm(pdf_content)
        print(f"✅ Parsing returned: {type(parsed_data).__name__}")
        if isinstance(parsed_data, dict):
            print(f"   Keys: {list(parsed_data.keys())[:5]}...")
    except Exception as e:
        print(f"❌ Parse failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 4: Test validation
    print("\n4️⃣ Testing resume validation...")
    try:
        validated_data = validate_parsed_resume(parsed_data)
        if "error" in validated_data:
            print(f"❌ Validation failed: {validated_data['error']}")
            if "raw_response" in validated_data:
                print(f"   Raw response: {validated_data.get('raw_response', '')[:200]}")
        else:
            print(f"✅ Validation passed")
            print(f"   Name: {validated_data.get('name', 'N/A')}")
            print(f"   Email: {validated_data.get('email', 'N/A')}")
            print(f"   Skills: {len(validated_data.get('skills', []))} found")
    except Exception as e:
        print(f"❌ Validation error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_resume_upload())
