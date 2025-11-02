import sqlite3

conn = sqlite3.connect('multi_bot_platform.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables:", tables)

cursor.execute("SELECT COUNT(*) FROM users")
count = cursor.fetchone()[0]
print(f"Users count: {count}")

if count > 0:
    cursor.execute("SELECT mobile, is_admin FROM users LIMIT 10")
    for row in cursor.fetchall():
        print(f"  {row[0]} - Admin: {row[1]}")

conn.close()

