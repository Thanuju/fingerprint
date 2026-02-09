from flask import Flask, render_template, request, redirect, session
import os
import sqlite3
import cv2
import numpy as np
import joblib
import time
from numpy.linalg import norm
from numpy import dot
from sms import send_sms

# ---------------------- FLASK APP ----------------------
app = Flask(__name__)
app.secret_key = "atm_secret_key"

# ---------------------- MODEL LOAD ----------------------
model = joblib.load("fingerprint_model.pkl")

# Fingerprint Folder
FINGERPRINT_DIR = "fingerprints"
if not os.path.exists(FINGERPRINT_DIR):
    os.makedirs(FINGERPRINT_DIR)

# ---------------------- SECURITY SETTINGS ----------------------
LOCK_DURATION = 60         # 1 minute lock
MATCH_THRESHOLD = 0.92     # fingerprint similarity threshold


# ---------------------- DATABASE ----------------------
def get_db():
    return sqlite3.connect("database.db")


# ---------------------- IMAGE PROCESS ----------------------
def preprocess(path):
    img = cv2.imread(path, 0)
    img = cv2.resize(img, (128, 128))
    img = img.astype("float32") / 255.0
    return img.flatten().reshape(1, -1)


def cosine_similarity(a, b):
    a = a.flatten()
    b = b.flatten()
    denom = norm(a) * norm(b)
    if denom == 0:
        return 0
    return float(dot(a, b) / denom)


# ============================================================
#                           ROUTES
# ============================================================

# ---------------------- HOME ----------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------- REGISTER PAGE ----------------------
@app.route("/register")
def register():
    return render_template("register.html")


# ---------------------- SAVE USER ----------------------
@app.route("/save_user", methods=["POST"])
def save_user():
    name = request.form["name"]
    account = request.form["account"]
    pin = request.form["pin"]
    phone = request.form["phone"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users WHERE account_no=?", (account,))
    if cur.fetchone()[0] > 0:
        conn.close()
        return "❌ This Account Number is already registered!"

    cur.execute("SELECT COUNT(*) FROM users WHERE phone=?", (phone,))
    if cur.fetchone()[0] > 0:
        conn.close()
        return "❌ This Phone Number is already registered!"

    file = request.files["fingerprint"]
    temp_path = "temp_reg.jpg"
    file.save(temp_path)

    X = preprocess(temp_path)
    pred = model.predict(X)[0]

    if pred == 0:
        return "❌ Registration failed: Uploaded image is NOT a fingerprint."

    fp_path = f"{FINGERPRINT_DIR}/{account}.jpg"
    os.replace(temp_path, fp_path)

    cur.execute("""
        INSERT INTO users (name, account_no, pin, balance, phone, fingerprint_path, is_logged_in)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (name, account, pin, 0, phone, fp_path))

    conn.commit()
    conn.close()

    return render_template("success.html")


# ---------------------- FINGERPRINT LOGIN ----------------------
@app.route("/verify_fingerprint", methods=["POST"])
def verify_fingerprint():
    file = request.files.get("file")

    if not file:
        return "❌ Please upload a fingerprint."

    file.save("temp_login.jpg")

    session.setdefault("fail_count", 0)
    session.setdefault("lock_until", 0)

    if time.time() < session["lock_until"]:
        remaining = int(session["lock_until"] - time.time())
        return f"⛔ Login locked. Try again in {remaining} seconds."

    Xu = preprocess("temp_login.jpg")
    pred = model.predict(Xu)[0]

    if pred == 0:
        session["fail_count"] += 1

        if session["fail_count"] >= 3:
            session["lock_until"] = time.time() + LOCK_DURATION
            session["fail_count"] = 0
            return "⛔ Too many invalid attempts. Locked for 1 minute."

        return f"❌ Invalid fingerprint image. Attempts: {session['fail_count']}/3"

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, account_no, fingerprint_path FROM users")
    users = cur.fetchall()
    conn.close()

    identified_user = None
    best_sim = 0

    for uid, account, fp_path in users:
        if os.path.exists(fp_path):
            Xs = preprocess(fp_path)
            sim = cosine_similarity(Xu, Xs)

            if sim > best_sim:
                best_sim = sim
                identified_user = (uid, account)

    if identified_user and best_sim >= MATCH_THRESHOLD:
        uid, account = identified_user

        session["fingerprint_ok"] = True
        session["user_id"] = uid
        session["fail_count"] = 0

        return redirect("/pin")

    session["fail_count"] += 1

    if session["fail_count"] >= 3:
        session["lock_until"] = time.time() + LOCK_DURATION
        session["fail_count"] = 0
        return "⛔ Too many failed attempts. Locked for 1 minute."

    return f"❌ Fingerprint not matched. Attempts: {session['fail_count']}/3"


# ---------------------- PIN PAGE ----------------------
@app.route("/pin")
def pin():
    if not session.get("fingerprint_ok"):
        return "❌ Valid fingerprint required before PIN."
    return render_template("pin.html")


# ---------------------- VERIFY PIN ----------------------
@app.route("/verify_pin", methods=["POST"])
def verify_pin():
    pin = request.form["pin"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, is_logged_in FROM users WHERE pin=?", (pin,))
    user = cur.fetchone()

    if not user:
        conn.close()
        return "❌ Invalid PIN"

    uid, logged = user

    if logged == 1:
        conn.close()
        return "⚠️ User already logged in."

    cur.execute("UPDATE users SET is_logged_in=1 WHERE id=?", (uid,))
    conn.commit()
    conn.close()

    session["user_id"] = uid
    return redirect("/dashboard")


# ---------------------- DASHBOARD ----------------------
@app.route("/dashboard")
def dashboard():
    uid = session["user_id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name, account_no, balance FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    conn.close()

    return render_template("dashboard.html", user=user)


# ---------------------- WITHDRAW ----------------------
@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    if request.method == "GET":
        return render_template("withdraw.html")

    amount = int(request.form["amount"])
    uid = session["user_id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT balance, phone FROM users WHERE id=?", (uid,))
    bal, phone = cur.fetchone()

    if amount > bal:
        conn.close()
        return "❌ Insufficient Balance"

    new_bal = bal - amount

    cur.execute("UPDATE users SET balance=? WHERE id=?", (new_bal, uid))
    cur.execute("""
        INSERT INTO transactions (user_id, type, amount, balance_after)
        VALUES (?, ?, ?, ?)
    """, (uid, "Withdraw", amount, new_bal))

    conn.commit()
    conn.close()

    send_sms(phone, f"₹{amount} withdrawn. New balance ₹{new_bal}")

    return redirect("/dashboard")


# ---------------------- DEPOSIT ----------------------
@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    if request.method == "GET":
        return render_template("deposit.html")

    amount = int(request.form["amount"])
    uid = session["user_id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT balance, phone FROM users WHERE id=?", (uid,))
    bal, phone = cur.fetchone()

    new_bal = bal + amount

    cur.execute("UPDATE users SET balance=? WHERE id=?", (new_bal, uid))
    cur.execute("""
        INSERT INTO transactions (user_id, type, amount, balance_after)
        VALUES (?, ?, ?, ?)
    """, (uid, "Deposit", amount, new_bal))

    conn.commit()
    conn.close()

    send_sms(phone, f"₹{amount} deposited. New balance ₹{new_bal}")

    return redirect("/dashboard")


# ---------------------- HISTORY ----------------------
@app.route("/history")
def history():
    uid = session["user_id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT type, amount, balance_after, timestamp
        FROM transactions WHERE user_id=?
    """, (uid,))
    data = cur.fetchall()

    conn.close()
    return render_template("history.html", data=data)


# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    uid = session.get("user_id")

    if uid:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_logged_in=0 WHERE id=?", (uid,))
        conn.commit()
        conn.close()

    session.clear()
    return redirect("/")


# ---------------------- RUN SERVER ----------------------
if __name__ == "__main__":
    app.run(debug=True)
