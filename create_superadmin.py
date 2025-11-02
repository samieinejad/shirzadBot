import sqlite3
from datetime import datetime

conn = sqlite3.connect('multi_bot_platform.db')
cursor = conn.cursor()

mobile = '09124335080'

# Create superadmin user
cursor.execute('''
    INSERT OR IGNORE INTO users (mobile, full_name, is_verified, is_admin, balance, created_at, is_active)
    VALUES (?, 'Super Admin', 1, 1, 0, ?, 1)
''', (mobile, datetime.now().isoformat()))

conn.commit()

print(f"SUCCESS: Superadmin created with mobile: {mobile}")
print("\nTo login:")
print(f"1. Go to https://social.msn1.ir/login")
print(f"2. Enter mobile: {mobile}")
print(f"3. Use OTP code: 11111")
print(f"4. You'll be redirected to admin dashboard")

# List all admins
cursor.execute('SELECT mobile, is_admin FROM users WHERE is_admin = 1')
admins = cursor.fetchall()
print(f"\nTotal admins: {len(admins)}")
for admin_mobile, _ in admins:
    print(f"  - {admin_mobile}")

conn.close()

