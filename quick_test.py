#!/usr/bin/env python3
import sys

# Just import app to check for errors
try:
    print("Importing app...")
    import app
    print("OK: app imported successfully")
    
    # Check if it has Flask app
    if hasattr(app, 'app'):
        print("OK: Flask app exists")
    else:
        print("ERROR: No Flask app found")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

