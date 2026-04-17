#!/usr/bin/env python
"""
Test script to verify Supabase Storage bucket connection and upload/delete functionality
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from {env_path}")
else:
    load_dotenv()
    print("⚠️ Using default .env location")

# Get credentials
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

print("\n" + "="*60)
print("SUPABASE STORAGE CONNECTION TEST")
print("="*60)

# Check if credentials exist
print(f"\n1️⃣ Checking credentials...")
if not SUPABASE_URL:
    print("❌ SUPABASE_URL not found in .env")
    sys.exit(1)
else:
    print(f"✅ SUPABASE_URL: {SUPABASE_URL}")

if not SUPABASE_SERVICE_KEY:
    print("❌ SUPABASE_SERVICE_KEY not found in .env")
    sys.exit(1)
else:
    print(f"✅ SUPABASE_SERVICE_KEY: {'*' * 20}...")

# Try to initialize Supabase client
print(f"\n2️⃣ Initializing Supabase SDK client...")
try:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    print("✅ Supabase client created successfully")
except Exception as e:
    print(f"❌ Failed to create Supabase client: {e}")
    sys.exit(1)

# Test getting bucket info
print(f"\n3️⃣ Checking 'resumes' bucket...")
try:
    # Try to list files in the bucket - this will fail if bucket doesn't exist
    files = supabase.storage.from_("resumes").list()
    print(f"✅ 'resumes' bucket exists")
    print(f"   Current files in bucket: {len(files) if files else 0}")
except Exception as e:
    print(f"❌ Error accessing 'resumes' bucket: {e}")
    print(f"   This likely means the bucket doesn't exist or isn't accessible")
    print(f"\n   FIX: Create a bucket named 'resumes' in Supabase:")
    print(f"   1. Go to https://app.supabase.com")
    print(f"   2. Select your project")
    print(f"   3. Go to Storage tab")
    print(f"   4. Click '+ New bucket'")
    print(f"   5. Name it 'resumes'")
    print(f"   6. Make sure it's in 'Public' mode")
    sys.exit(1)

# Test upload
print(f"\n4️⃣ Testing file upload...")
try:
    test_content = b"Test resume content"
    test_path = "test-user/test_resume.pdf"
    
    response = supabase.storage.from_("resumes").upload(
        path=test_path,
        file=test_content,
        file_options={"content-type": "application/pdf"}
    )
    print(f"✅ Upload successful")
    print(f"   File path: {test_path}")
    
    # Get public URL
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/resumes/{test_path}"
    print(f"   Public URL: {public_url}")
    
except Exception as e:
    print(f"❌ Upload failed: {e}")
    sys.exit(1)

# Test delete
print(f"\n5️⃣ Testing file deletion...")
try:
    response = supabase.storage.from_("resumes").remove([test_path])
    print(f"✅ Delete successful")
    
except Exception as e:
    print(f"❌ Delete failed: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("✅ ALL TESTS PASSED!")
print("="*60)
print("\nYour Supabase Storage setup is working correctly.")
print("Resume uploads should now work without 'Bucket not found' errors.\n")
