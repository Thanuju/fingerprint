import sqlite3

account = input("Enter account number to delete: ")

conn = sqlite3.connect("database.db")
cur = conn.cursor()

# Get user ID
cur.execute("SELECT id FROM users WHERE account_no=?", (account,))
user = cur.fetchone()

if not user:
    print("❌ No user found with that account number!")
else:
    uid = user[0]

    # Delete transactions
    cur.execute("DELETE FROM transactions WHERE user_id=?", (uid,))

    # Delete user
    cur.execute("DELETE FROM users WHERE id=?", (uid,))

    conn.commit()
    print("✔ User deleted successfully!")

conn.close()
