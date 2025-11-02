#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import sys

DB_FILE = "multi_bot_platform.db"

def make_admin(mobile):
    """Make a user admin by mobile number"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT id, mobile, is_admin FROM users WHERE mobile = ?', (mobile,))
        user = cursor.fetchone()
        
        if not user:
            print(f"ERROR: User {mobile} not found!")
            print("Please register first at https://social.msn1.ir/login")
            return False
        
        user_id, user_mobile, is_admin = user
        
        if is_admin:
            print(f"SUCCESS: User {mobile} is already admin!")
            return True
        
        # Make admin
        cursor.execute('UPDATE users SET is_admin = 1 WHERE id = ?', (user_id,))
        conn.commit()
        
        print(f"SUCCESS: User {mobile} is now admin!")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        conn.close()

def list_users():
    """List all users"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT id, mobile, is_admin, created_at FROM users ORDER BY created_at DESC')
        users = cursor.fetchall()
        
        if not users:
            print("No users found in database")
            return
        
        print(f"\nTotal users: {len(users)}")
        print("-" * 60)
        for user_id, mobile, is_admin, created in users:
            admin_text = "ADMIN" if is_admin else "USER"
            print(f"{user_id}. {mobile} - {admin_text} - {created}")
        print("-" * 60)
        
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python admin_setup.py list           # List all users")
        print("  python admin_setup.py admin MOBILE   # Make user admin")
        print("\nExample:")
        print("  python admin_setup.py admin 09124335080")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        list_users()
    elif command == 'admin':
        if len(sys.argv) < 3:
            print("ERROR: Provide mobile number")
            sys.exit(1)
        mobile = sys.argv[2]
        make_admin(mobile)
    else:
        print(f"ERROR: Unknown command: {command}")
        sys.exit(1)

