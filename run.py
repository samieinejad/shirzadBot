#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main entry point for Shirzad Bot Platform

This script starts the Flask application and bot services.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Main entry point"""
    # For now, run the old app.py
    # Once refactoring is complete, we'll use the new structure
    
    # Check if we should use old or new structure
    use_new_structure = os.environ.get('USE_NEW_STRUCTURE', 'false').lower() == 'true'
    
    if use_new_structure:
        print("🚀 Starting with NEW structure...")
        from app import create_app
        app = create_app('production')
        app.run(host='0.0.0.0', port=5010, debug=False)
    else:
        print("🚀 Starting with OLD structure...")
        # Import and run old app.py
        import app as old_app_module
        old_app_module.main()

if __name__ == '__main__':
    main()

