"""
QR Service — Atomic Microservice
Port: 5005
DB:   qr_db (MySQL)
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector, os, uuid, hmac, hashlib, base64, io
from datetime import datetime
import qrcode
from qrcode.image.pure import PyPNGImage

app = Flask(__name__)
CORS(app)

HMAC_SECRET = os.environ.get("QR_HMAC_SECRET", "dev_secret_replace_me")

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "qr_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "qr", "timestamp": datetime.utcnow().isoformat()}}), status


def ensure_schema():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS qr_record (
          qrId VARCHAR(36) PRIMARY KEY,
          ticketId VARCHAR(36) NOT NULL,
          concertId VARCHAR(36) NOT NULL,
          userId VARCHAR(36) NOT NULL,
          qrData TEXT NOT NULL,
          qrImageUrl MEDIUMTEXT NOT NULL,
          isValid TINYINT(1) NOT NULL DEFAULT 1,
          invalidatedAt DATETIME NULL,
          invalidReason VARCHAR(100) NULL,
          generatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          KEY idx_qr_ticket_valid (ticketId, isValid),
          KEY idx_qr_concert_valid (concertId, isValid)
        )
        """
    )
    db.commit()
    cur.close()
    db.close()


ensure_schema()


def make_qr_data(ticket_id, user_id, concert_id):
    payload = f"CTMS|{ticket_id}|{user_id}|{concert_id}"
    sig = hmac.new(HMAC_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:8]
    return f"{payload}|{sig}"


def generate_qr_base64(qr_data):
    """Generate a QR code image and return it as a base64 data URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PyPNGImage)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


# POST /qr/v1/qr  — generate
@app.route("/qr/v1/qr", methods=["POST"])
def generate_qr():
    data = request.get_json()
    required = ["ticketId", "userId", "concertId"]
    if not all(k in data for k in required):
        return err("MISSING_FIELDS", f"Required: {required}")
    db = get_db(); cur = db.cursor()
    cur.execute(
        """
        UPDATE qr_record
        SET isValid=0, invalidatedAt=NOW(), invalidReason='REPLACED_BY_NEW_QR'
        WHERE ticketId=%s AND isValid=1
        """,
        (data["ticketId"],),
    )
    qr_id = f"QR-{uuid.uuid4().hex[:8].upper()}"
    qr_data = make_qr_data(data["ticketId"], data["userId"], data["concertId"])
    image_url = generate_qr_base64(qr_data)
    cur.execute("""INSERT INTO qr_record (qrId,ticketId,concertId,userId,qrData,qrImageUrl,isValid)
                   VALUES (%s,%s,%s,%s,%s,%s,1)""",
                (qr_id, data["ticketId"], data["concertId"], data["userId"], qr_data, image_url))
    db.commit(); cur.close(); db.close()
    return jsonify({"qrId": qr_id, "ticketId": data["ticketId"], "userId": data["userId"],
                    "qrData": qr_data, "qrImageUrl": image_url,
                    "isValid": True, "generatedAt": datetime.utcnow().isoformat()}), 201

# GET /qr/v1/qr/<ticketId>
@app.route("/qr/v1/qr/<ticket_id>", methods=["GET"])
def get_qr(ticket_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM qr_record WHERE ticketId=%s AND isValid=1 ORDER BY generatedAt DESC LIMIT 1", (ticket_id,))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("NOT_FOUND", "No valid QR found for this ticket", 404)
    return jsonify(row)

# GET /qr/v1/qr/<ticketId>/validate  — gate scan
@app.route("/qr/v1/qr/<ticket_id>/validate", methods=["GET"])
def validate_qr(ticket_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM qr_record WHERE ticketId=%s AND isValid=1", (ticket_id,))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return jsonify({"valid": False, "reason": "QR invalidated or not found"}), 200
    return jsonify({"valid": True, "ticketId": ticket_id, "userId": row["userId"],
                    "concertId": row["concertId"]})

# PUT /qr/v1/qr/<ticketId>/invalidate
@app.route("/qr/v1/qr/<ticket_id>/invalidate", methods=["PUT"])
def invalidate_qr(ticket_id):
    data = request.get_json() or {}
    reason = data.get("reason", "INVALIDATED")
    db = get_db(); cur = db.cursor()
    cur.execute("""UPDATE qr_record SET isValid=0, invalidatedAt=NOW(), invalidReason=%s
                   WHERE ticketId=%s AND isValid=1""", (reason, ticket_id))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    if affected == 0: return err("NOT_FOUND_OR_ALREADY_INVALID", "No valid QR found to invalidate", 409)
    return jsonify({"invalidated": True, "ticketId": ticket_id, "reason": reason})

# PUT /qr/v1/qr/concert/<concertId>/invalidate-all  — S3 bulk
@app.route("/qr/v1/qr/concert/<concert_id>/invalidate-all", methods=["PUT"])
def invalidate_all(concert_id):
    db = get_db(); cur = db.cursor()
    cur.execute("""UPDATE qr_record SET isValid=0, invalidatedAt=NOW(), invalidReason='CONCERT_CANCELLED'
                   WHERE concertId=%s AND isValid=1""", (concert_id,))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    return jsonify({"concertId": concert_id, "qrsInvalidated": affected,
                    "updatedAt": datetime.utcnow().isoformat()})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "qr"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5005)), debug=False)
