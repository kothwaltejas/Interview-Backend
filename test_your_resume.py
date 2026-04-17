#!/usr/bin/env python
"""
Frontend developers: Use this to test EXACTLY how your resume upload works
Copy your actual resume file and test locally to see the exact error message
"""

import asyncio
import httpx
import sys

async def test_with_your_file(file_path: str):
    """Test with your actual resume file"""
    
    print(f"\n📄 Testing with: {file_path}")
    
    try:
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        file_size_mb = len(file_content) / (1024 * 1024)
        print(f"   File size: {file_size_mb:.2f} MB")
        print(f"   Is PDF: {file_path.lower().endswith('.pdf')}")
        
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return
    
    print("\n🚀 Sending to /api/resume/parse...")
    
    try:
        async with httpx.AsyncClient() as client:
            files = {'file': (file_path, file_content, 'application/pdf')}
            response = await client.post(
                'http://localhost:8000/api/resume/parse',
                files=files,
                timeout=30.0
            )
            
            print(f"\nStatus Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ SUCCESS!")
                print(f"   Parsed Name: {result['data'].get('name', 'N/A')}")
                print(f"   Skills Found: {len(result['data'].get('skills', []))}")
                print(f"   Email: {result['data'].get('email', 'N/A')}")
            else:
                result = response.json()
                print(f"❌ ERROR")
                print(f"   Detail: {result.get('detail', result)}")
            
            return response.status_code
                
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        print(f"   Make sure backend is running: http://localhost:8000/health")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        print("Usage: python test_your_resume.py <path_to_resume.pdf>")
        print("\nExample: python test_your_resume.py resume.pdf")
        print("Example: python test_your_resume.py C:\\Users\\Your\\Documents\\resume.pdf")
        sys.exit(1)
    
    asyncio.run(test_with_your_file(file_path))
