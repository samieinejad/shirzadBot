# -*- coding: utf-8 -*-
import requests
import sys

try:
    # Test 1: Send OTP
    print("Test 1: Send OTP")
    r = requests.post("http://localhost:5010/api/auth/send-otp", json={"mobile": "09124335080"})
    print(f"Status: {r.status_code}")
    print(f"OK")
    
    # Test 2: Verify with 11111
    print("\nTest 2: Verify OTP with 11111")
    r = requests.post("http://localhost:5010/api/auth/verify-otp", json={"mobile": "09124335080", "code": "11111"})
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print("SUCCESS!")
        print(f"Response: {r.json()}")
    else:
        print(f"FAILED: {r.text}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

