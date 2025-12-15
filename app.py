from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import mysql.connector          
from mysql.connector import Error
from gtts import gTTS
import os, time, re
from datetime import datetime


app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-key")




DB_CFG = {
    "host": "gateway01.ap-southeast-1.prod.aws.tidbcloud.com",
    "user": "3payERwEpdbUUiL.root",
    "password": "op4ApnvV0XUYAT0F",
    "database": "test",
    "port": 4000,
    "ssl_ca": "ca.pem"
}

def get_db():
    try:
        conn = mysql.connector.connect(**DB_CFG)
        return conn
    except Error as e:
        print("❌ TiDB connection failed:", e)
        return None



# ROUTES — USER AUTHENTICATION

@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        return jsonify({"status": "fail", "msg": "Missing fields"})

    con = get_db()
    if not con:
        return jsonify({"status": "db_fail"})

    try:
        cur = con.cursor()
        query = """
            SELECT user_id, username, user_role 
            FROM users 
            WHERE username = %s AND user_password = %s
        """
        cur.execute(query, (username, password))
        row = cur.fetchone()
    finally:
        cur.close()
        con.close()

    if row:
        session["user_id"] = row[0]
        session["username"] = row[1]
        session["role"] = row[2]
        return jsonify({"status": "ok"})

    return jsonify({"status": "fail", "msg": "Invalid credentials"})



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ROUTES — DASHBOARD UI

@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("home"))
    return render_template("dashboard.html",
                           username=session["username"],
                           role=session["role"])

# REST API — MENU

@app.route("/api/me")
def api_me():
    return jsonify({
        "logged_in": bool(session.get("user_id")),
        "username": session.get("username", ""),
        "role": session.get("role", "")
    })


@app.route("/api/menu")
def get_menu():
    con = get_db()
    if con is None:
        return jsonify([])

    cur = con.cursor()
    
    cur.execute("SELECT item_id, item_name, te_name, price, availability FROM menu")
    items = cur.fetchall()
    cur.close()
    con.close()

    return jsonify([
        {
            "id": r[0],
            "name_en": r[1],
            "name_te": r[2],
            "price": float(r[3]),
            "availability": r[4],
        }
        for r in items
    ])


@app.route("/api/order", methods=["POST"])
def api_order():
    if not session.get("user_id"):
        return jsonify({"status": "unauthorized"}), 401

    data = request.get_json() or {}
    item_id = data.get("item_id")
    qty = max(1, int(data.get("quantity", 1)))

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT item_name, price FROM menu WHERE item_id=%s", (item_id,))
    row = cur.fetchone()

    if not row:
        return jsonify({"status": "fail", "msg": "not found"})

    item_name, price = row
    total = float(price) * qty

    cur.execute("INSERT INTO orders (user_id, item_id, quantity, total_price) VALUES (%s,%s,%s,%s)",
                (session["user_id"], item_id, qty, total))
    con.commit()
    order_id = cur.lastrowid
    cur.close(); con.close()

    return jsonify({
        "status": "ok",
        "total": total,
        "receipt": {
            "order_id": order_id,
            "customer": session["username"],
            "item": item_name,
            "quantity": qty,
            "unit_price": float(price),
            "total_price": total,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    })

@app.route("/api/order_voice", methods=["POST"])
def api_order_voice():
    if not session.get("user_id"):
        return jsonify({"status": "unauthorized"}), 401

    data = request.get_json() or {}
    transcript = (data.get("transcript") or "").strip().lower()
    lang = (data.get("lang") or "en").lower()

    print("🎤 Transcript:", transcript, "| Lang:", lang)


    num_words = {
        "one": 1, "1": 1,
        "two": 2, "to": 2, "too": 2, "2": 2,
        "three": 3, "3": 3,
        "four": 4, "for": 4, "4": 4,
        "five": 5, "5": 5,

        "ఒకటి": 1, "ఒక్కటి": 1,
        "రెండు": 2,
        "మూడు": 3,
        "నాలుగు": 4,
        "ఐదు": 5
    }

    qty = 1
    for word in transcript.replace("?", "").split():
        w = word.strip()
        if w in num_words:
            qty = num_words[w]
            break

    print("➡️ Quantity Detected:", qty)

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT item_id, item_name, te_name, price FROM menu WHERE availability='yes'")
    items = cur.fetchall()

    norm = transcript.replace(" ", "")

    item_id = None
    item_name = ""
    price = 0.0

    synonyms = {
        "biryani": ["biryani", "biriyani", "బిర్యాని", "బిర్యానీ"],
        "chicken fry": ["chicken fry", "చికెన్ ఫ్రై", "చికెన్‌ఫ్రై"],
        "kebab": ["kebab", "kebabs", "కెబాబ్", "కెబబ్", "కబాబ్", "కబబ్"]
    }

    for row in items:
        row_id, en_name, te_name, row_price = row
        en_low = (en_name or "").lower()
        te_low = (te_name or "").replace(" ", "").lower()

        
        if en_low in transcript or te_low in norm:
            item_id, item_name, price = row_id, en_name, float(row_price)
            break

        
        if en_low in synonyms:
            for syn in synonyms[en_low]:
                if syn.replace(" ", "").lower() in norm:
                    item_id, item_name, price = row_id, en_name, float(row_price)
                    break

        if item_id:
            break

    if not item_id:
        cur.close()
        con.close()
        print(" Item not recognized")
        return jsonify({"status": "fail", "msg": "item not recognized"})

    total = price * qty

    cur.execute(
        "INSERT INTO orders (user_id, item_id, quantity, total_price) VALUES (%s,%s,%s,%s)",
        (session["user_id"], item_id, qty, total)
    )
    con.commit()
    order_id = cur.lastrowid
    cur.close()
    con.close()

    receipt = {
        "order_id": order_id,
        "customer": session["username"],
        "item": item_name,
        "quantity": qty,
        "unit_price": price,
        "total_price": total,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


    if lang == "te":
        response_text = f"{session['username']} గారి కోసం {qty} {item_name} విజయవంతంగా ఆర్డర్ పెట్టబడింది."
    else:
        response_text = f"Order placed. {qty} {item_name} for {session['username']}."

    return jsonify({
        "status": "ok",
        "total": total,
        "receipt": receipt,
        "tts": response_text
    })



# SPEECH OUTPUT API

@app.route("/speak", methods=["POST"])
def speak():
    print("🎤 /speak called!")  

    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    lang = data.get("lang", "en")
    
    print("➡ Text:", text)
    print("➡ Lang:", lang)

    if not text.strip():
        return jsonify({"error": "No text provided"}), 400

    try:
        tld = "co.in" if lang == "te" else "com"
        tts = gTTS(text=text, lang=lang, tld=tld)
        filename = f"voice_{int(time.time())}.mp3"
        filepath = os.path.join("static", filename)
        tts.save(filepath)
        return jsonify({"file": f"/static/{filename}"})
    except Exception as e:
        print("❌ TTS FAILED:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run()

