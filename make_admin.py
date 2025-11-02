#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to make yourself admin
Usage: python make_admin.py YOUR_MOBILE_NUMBER
Example: python make_admin.py 09123456789
"""

import sys
import sqlite3

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
            print(f"❌ کاربر با شماره {mobile} یافت نشد!")
            print("ابتدا از طریق وب سایت ثبت نام کنید: https://social.msn1.ir/login")
            return False
        
        user_id, user_mobile, is_admin = user
        
        if is_admin:
            print(f"✅ کاربر {mobile} قبلاً ادمین است!")
            return True
        
        # Make admin
        cursor.execute('UPDATE users SET is_admin = 1 WHERE id = ?', (user_id,))
        conn.commit()
        
        print(f"✅ کاربر {mobile} به ادمین تبدیل شد!")
        return True
        
    except Exception as e:
        print(f"❌ خطا: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py YOUR_MOBILE_NUMBER")
        print("Example: python make_admin.py 09123456789")
        sys.exit(1)
    
    mobile = sys.argv[1]
    
    if not mobile.startswith('09') or len(mobile) != 11:
        print("❌ شماره موبایل معتبر وارد کنید (مثال: 09123456789)")
        sys.exit(1)
    
    make_admin(mobile)

