"""
Pricing Service — Atomic Microservice
Port: 5001
DB:   pricing_db (MySQL)
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector, os, uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "pricing_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "pricing", "timestamp": datetime.utcnow().isoformat()}}), status

# GET /pricing/v1/concerts/<concertId>/prices
@app.route("/pricing/v1/concerts/<concert_id>/prices", methods=["GET"])
def get_prices(concert_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM price_rule WHERE concertId = %s", (concert_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"concertId": concert_id, "prices": rows})

# GET /pricing/v1/concerts/<concertId>/prices/<categoryId>
@app.route("/pricing/v1/concerts/<concert_id>/prices/<category_id>", methods=["GET"])
def get_price(concert_id, category_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM price_rule WHERE concertId=%s AND categoryId=%s", (concert_id, category_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("PRICE_NOT_FOUND", f"No price rule for {concert_id}/{category_id}", 404)
    return jsonify(row)

# GET /pricing/v1/concerts/<concertId>/prices/<categoryId>/ceiling
@app.route("/pricing/v1/concerts/<concert_id>/prices/<category_id>/ceiling", methods=["GET"])
def get_ceiling(concert_id, category_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT resaleCeiling, currency FROM price_rule WHERE concertId=%s AND categoryId=%s",
                (concert_id, category_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("PRICE_NOT_FOUND", "No price rule found", 404)
    return jsonify({"concertId": concert_id, "categoryId": category_id,
                    "resaleCeiling": row["resaleCeiling"], "currency": row["currency"]})

# POST /pricing/v1/concerts/<concertId>/prices
@app.route("/pricing/v1/concerts/<concert_id>/prices", methods=["POST"])
def create_price(concert_id):
    data = request.get_json()
    required = ["categoryId", "basePrice", "currency", "effectiveFrom"]
    if not all(k in data for k in required):
        return err("MISSING_FIELDS", f"Required: {required}")
    rule_id = f"PR-{uuid.uuid4().hex[:8].upper()}"
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""INSERT INTO price_rule
            (priceRuleId,concertId,categoryId,basePrice,resaleCeiling,currency,effectiveFrom,effectiveTo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rule_id, concert_id, data["categoryId"], data["basePrice"],
             data.get("resaleCeiling"), data["currency"], data["effectiveFrom"], data.get("effectiveTo")))
        db.commit()
    except mysql.connector.IntegrityError:
        return err("DUPLICATE_RULE", "Price rule already exists for this concert+category", 409)
    finally:
        cur.close(); db.close()
    return jsonify({"priceRuleId": rule_id, "concertId": concert_id}), 201

# PUT /pricing/v1/concerts/<concertId>/prices/<categoryId>
@app.route("/pricing/v1/concerts/<concert_id>/prices/<category_id>", methods=["PUT"])
def update_price(concert_id, category_id):
    data = request.get_json()
    db = get_db(); cur = db.cursor()
    cur.execute("""UPDATE price_rule SET basePrice=%s, resaleCeiling=%s, effectiveTo=%s
                   WHERE concertId=%s AND categoryId=%s""",
                (data.get("basePrice"), data.get("resaleCeiling"), data.get("effectiveTo"),
                 concert_id, category_id))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    if affected == 0: return err("NOT_FOUND", "Price rule not found", 404)
    return jsonify({"updated": True})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "pricing"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
