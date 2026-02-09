import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE users ADD COLUMN is_logged_in INTEGER DEFAULT 0")
    print("Column added successfully!")
except:
    print("Column already exists or error occurred.")

conn.commit()
conn.close()
