"""
Pricing Service — Atomic Microservice
Port: 5001
DB:   pricing_db (MySQL)
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector, requests, os, uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)

CONCERT_URL = os.environ.get("CONCERT_SERVICE_URL", "http://localhost:5000")

# Open a MySQL connection to the pricing service database.
def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "pricing_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

# Return a standardised JSON error payload for the pricing service.
def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "pricing", "timestamp": datetime.utcnow().isoformat()}}), status


# Create the pricing table if it does not already exist.
def ensure_schema():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_rule (
          priceRuleId VARCHAR(36) NOT NULL,
          concertId VARCHAR(36) NOT NULL,
          categoryId VARCHAR(36) NOT NULL,
          basePrice DECIMAL(10,2) NOT NULL,
          resaleCeiling DECIMAL(10,2) NULL,
          currency VARCHAR(3) NOT NULL DEFAULT 'SGD',
          effectiveFrom DATETIME NOT NULL,
          effectiveTo DATETIME NULL,
          createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (priceRuleId),
          UNIQUE KEY uq_price_rule (concertId, categoryId, effectiveFrom)
        )
        """
    )
    db.commit()
    cur.close()
    db.close()


# Fetch a seat category from the concert service for category validation.
def fetch_seat_category(concert_id, category_id):
    try:
        res = requests.get(f"{CONCERT_URL}/concerts/{concert_id}/seats", timeout=5)
        if res.status_code != 200:
            return None
        categories = res.json().get("categories", [])
        return next((c for c in categories if c["categoryId"] == category_id), None)
    except Exception:
        return None


# Normalise incoming datetime values into MySQL-compatible strings.
def parse_mysql_datetime(value, field_name):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        candidates = [
            raw,
            raw.replace("T", " ").replace("Z", ""),
        ]
        parsed = None
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(candidate)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            for fmt in ("%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            raise ValueError(f"{field_name} must be a valid datetime")
        dt = parsed
    else:
        raise ValueError(f"{field_name} must be a valid datetime")

    if dt.year < 1000:
        raise ValueError(f"{field_name} year must be 1000 or later")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


ensure_schema()

# GET /pricing/v1/concerts/<concertId>/prices
# List all price rules configured for a concert.
@app.route("/pricing/v1/concerts/<concert_id>/prices", methods=["GET"])
def get_prices(concert_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM price_rule WHERE concertId = %s ORDER BY effectiveFrom, categoryId", (concert_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    currency = rows[0]["currency"] if rows else None
    return jsonify({"concertId": concert_id, "currency": currency, "prices": rows})

# GET /pricing/v1/concerts/<concertId>/prices/<categoryId>
# Fetch a single price rule for one concert category.
@app.route("/pricing/v1/concerts/<concert_id>/prices/<category_id>", methods=["GET"])
def get_price(concert_id, category_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM price_rule WHERE concertId=%s AND categoryId=%s", (concert_id, category_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("PRICE_NOT_FOUND", f"No price rule for {concert_id}/{category_id}", 404)
    return jsonify(row)

# GET /pricing/v1/concerts/<concertId>/prices/<categoryId>/ceiling
# Return only the resale ceiling and currency for a category.
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
# Create a new pricing rule after validating price and category inputs.
@app.route("/pricing/v1/concerts/<concert_id>/prices", methods=["POST"])
def create_price(concert_id):
    data = request.get_json()
    required = ["categoryId", "basePrice", "currency", "effectiveFrom"]
    if not all(k in data for k in required):
        return err("MISSING_FIELDS", f"Required: {required}")
    
    # Validate basePrice
    try:
        base_price = float(data["basePrice"])
        if base_price < 0:
            return err("INVALID_PRICE", "basePrice must be >= 0")
        if base_price > 100000:
            return err("INVALID_PRICE", "basePrice cannot exceed 100000")
    except (ValueError, TypeError):
        return err("INVALID_PRICE", "basePrice must be a valid number", 400)
    
    # Validate resaleCeiling
    if data.get("resaleCeiling") is not None:
        try:
            resale_ceiling = float(data["resaleCeiling"])
            if resale_ceiling < base_price:
                return err("INVALID_CEILING", "resaleCeiling must be >= basePrice")
            if resale_ceiling > 150000:
                return err("INVALID_CEILING", "resaleCeiling cannot exceed 150000")
        except (ValueError, TypeError):
            return err("INVALID_CEILING", "resaleCeiling must be a valid number", 400)
    
    if fetch_seat_category(concert_id, data["categoryId"]) is None:
        return err("CATEGORY_NOT_FOUND", "concertId or categoryId not found", 404)
    try:
        effective_from = parse_mysql_datetime(data["effectiveFrom"], "effectiveFrom")
        effective_to = parse_mysql_datetime(data.get("effectiveTo"), "effectiveTo")
    except ValueError as exc:
        return err("INVALID_DATETIME", str(exc), 400)
    rule_id = f"PR-{uuid.uuid4().hex[:8].upper()}"
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""INSERT INTO price_rule
            (priceRuleId,concertId,categoryId,basePrice,resaleCeiling,currency,effectiveFrom,effectiveTo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rule_id, concert_id, data["categoryId"], data["basePrice"],
             data.get("resaleCeiling"), data["currency"], effective_from, effective_to))
        db.commit()
    except mysql.connector.IntegrityError:
        return err("DUPLICATE_RULE", "Price rule already exists for this concert+category", 409)
    finally:
        cur.close(); db.close()
    return jsonify({"priceRuleId": rule_id, "concertId": concert_id}), 201

# PUT /pricing/v1/concerts/<concertId>/prices/<categoryId>
# Update the active pricing rule for a concert category.
@app.route("/pricing/v1/concerts/<concert_id>/prices/<category_id>", methods=["PUT"])
def update_price(concert_id, category_id):
    data = request.get_json()
    if data.get("basePrice") is not None and float(data["basePrice"]) < 0:
        return err("INVALID_PRICE", "basePrice must be >= 0")
    if (
        data.get("resaleCeiling") is not None
        and data.get("basePrice") is not None
        and float(data["resaleCeiling"]) < float(data["basePrice"])
    ):
        return err("INVALID_CEILING", "resaleCeiling must be >= basePrice")
    db = get_db(); cur = db.cursor()
    cur.execute("""UPDATE price_rule SET basePrice=%s, resaleCeiling=%s, effectiveTo=%s
                   WHERE concertId=%s AND categoryId=%s""",
                (data.get("basePrice"), data.get("resaleCeiling"), data.get("effectiveTo"),
                 concert_id, category_id))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    if affected == 0: return err("NOT_FOUND", "Price rule not found", 404)
    return jsonify({"updated": True})

# Expose a simple health endpoint for container checks.
@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "pricing"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
