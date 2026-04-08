"""
QR Service — Atomic Microservice
Port: 5005
DB:   qr_db (MySQL)
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector, os, uuid, hmac, hashlib, base64, io
from datetime import datetime
import requests
import qrcode
from qrcode.image.pure import PyPNGImage

app = Flask(__name__)
CORS(app)

HMAC_SECRET = os.environ.get("QR_HMAC_SECRET", "dev_secret_replace_me")
TICKET_URL = os.environ.get("TICKET_INVENTORY_SERVICE_URL", "http://localhost:5003").rstrip("/")
CONCERT_URL = os.environ.get("CONCERT_SERVICE_URL", "http://localhost:5000").rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("QR_SCAN_HTTP_TIMEOUT", "5"))

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


def safe_json(response):
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}


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


def decode_qr_payload(qr_data):
    if not isinstance(qr_data, str) or not qr_data.strip():
        raise ValueError("QR data is required")
    raw = qr_data.strip()
    parts = raw.split("|")
    if len(parts) != 5 or parts[0] != "CTMS":
        raise ValueError("QR payload format is invalid")
    payload = "|".join(parts[:4])
    sig = hmac.new(HMAC_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:8]
    if not hmac.compare_digest(sig, parts[4]):
        raise ValueError("QR signature is invalid")
    return {
        "ticketId": parts[1],
        "userId": parts[2],
        "concertId": parts[3],
        "qrData": raw,
    }


def parse_event_datetime(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except Exception:
            return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(f"{raw}T23:59:59")
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def fetch_ticket(concert_id, ticket_id):
    response = requests.get(
        f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/{ticket_id}",
        timeout=HTTP_TIMEOUT,
    )
    return response.status_code, safe_json(response)


def update_ticket_status(concert_id, ticket_id, version, status):
    response = requests.put(
        f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/{ticket_id}",
        json={"status": status, "version": version},
        timeout=HTTP_TIMEOUT,
    )
    return response.status_code, safe_json(response)


def fetch_concert(concert_id):
    response = requests.get(f"{CONCERT_URL}/concerts/{concert_id}", timeout=HTTP_TIMEOUT)
    return response.status_code, safe_json(response)


def invalid_reason_response(reason):
    reason_key = str(reason or "INVALIDATED").upper()
    mapping = {
        "USED_AT_GATE": ("TICKET_USED", "Ticket has already been used"),
        "CONCERT_CANCELLED": ("TICKET_REFUNDED", "Ticket has been refunded because the concert was cancelled"),
        "REPLACED_BY_NEW_QR": ("QR_REPLACED", "A newer QR code has already been issued for this ticket"),
        "INVALIDATED": ("QR_INVALID", "Ticket QR is invalid"),
    }
    code, message = mapping.get(reason_key, ("QR_INVALID", "Ticket QR is invalid"))
    return {"success": False, "code": code, "message": message, "invalidReason": reason_key}


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


# POST /qr/v1/scan  — gate scan + consume
@app.route("/qr/v1/scan", methods=["POST"])
def scan_qr():
    data = request.get_json() or {}
    qr_data = data.get("qrData")
    confirm = bool(data.get("confirm"))
    try:
        payload = decode_qr_payload(qr_data)
    except ValueError as exc:
        return jsonify({"success": False, "code": "INVALID_QR", "message": str(exc)}), 200

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM qr_record WHERE ticketId=%s AND qrData=%s ORDER BY generatedAt DESC LIMIT 1",
        (payload["ticketId"], payload["qrData"]),
    )
    qr_row = cur.fetchone()
    cur.close()
    db.close()
    if not qr_row:
        return jsonify({"success": False, "code": "QR_NOT_FOUND", "message": "Ticket QR was not recognised"}), 200
    if not qr_row["isValid"]:
        return jsonify(invalid_reason_response(qr_row.get("invalidReason"))), 200

    try:
        ticket_status, ticket_data = fetch_ticket(payload["concertId"], payload["ticketId"])
    except requests.RequestException:
        return jsonify({"success": False, "code": "TICKET_LOOKUP_FAILED", "message": "Could not verify ticket status"}), 503
    if ticket_status != 200:
        return jsonify({"success": False, "code": "TICKET_NOT_FOUND", "message": "Ticket could not be found"}), 200

    ticket_state = str(ticket_data.get("status") or "").upper()
    if ticket_state == "USED":
        return jsonify({"success": False, "code": "TICKET_USED", "message": "Ticket has already been used"}), 200
    if ticket_state == "REFUNDED":
        return jsonify({"success": False, "code": "TICKET_REFUNDED", "message": "Ticket has been refunded or cancelled"}), 200
    if ticket_state != "CONFIRMED":
        return jsonify({
            "success": False,
            "code": "INVALID_TICKET_STATUS",
            "message": f"Ticket cannot be scanned while status is {ticket_state or 'UNKNOWN'}",
            "ticketStatus": ticket_state or "UNKNOWN",
        }), 200

    try:
        concert_status, concert_data = fetch_concert(payload["concertId"])
    except requests.RequestException:
        return jsonify({"success": False, "code": "CONCERT_LOOKUP_FAILED", "message": "Could not verify concert timing"}), 503
    if concert_status != 200:
        return jsonify({"success": False, "code": "CONCERT_NOT_FOUND", "message": "Concert details were not found"}), 200

    event_dt = parse_event_datetime(concert_data.get("eventDate"))
    if event_dt and datetime.now() > event_dt:
        return jsonify({
            "success": False,
            "code": "TICKET_EXPIRED",
            "message": "Ticket has expired because the concert time has passed",
            "eventDate": concert_data.get("eventDate"),
        }), 200

    if not confirm:
        return jsonify({
            "success": True,
            "code": "TICKET_READY",
            "message": "Ticket is valid. Click OK to confirm entry.",
            "ticketId": payload["ticketId"],
            "concertId": payload["concertId"],
            "userId": payload["userId"],
            "ticketStatus": ticket_state,
            "concertName": concert_data.get("name"),
            "eventDate": concert_data.get("eventDate"),
            "actionRequired": True,
        }), 200

    version = ticket_data.get("version")
    if version is None:
        return jsonify({"success": False, "code": "VERSION_MISSING", "message": "Ticket version was missing"}), 500

    try:
        update_status, update_data = update_ticket_status(payload["concertId"], payload["ticketId"], version, "USED")
    except requests.RequestException:
        return jsonify({"success": False, "code": "TICKET_UPDATE_FAILED", "message": "Could not mark ticket as used"}), 503

    if update_status == 409:
        latest_status, latest_data = fetch_ticket(payload["concertId"], payload["ticketId"])
        latest_state = str((latest_data or {}).get("status") or "").upper() if latest_status == 200 else ""
        if latest_state == "USED":
            return jsonify({"success": False, "code": "TICKET_USED", "message": "Ticket has already been used"}), 200
        if latest_state == "REFUNDED":
            return jsonify({"success": False, "code": "TICKET_REFUNDED", "message": "Ticket has been refunded or cancelled"}), 200
        return jsonify({"success": False, "code": "SCAN_CONFLICT", "message": "Ticket state changed during scanning. Please retry."}), 200
    if update_status != 200:
        return jsonify({
            "success": False,
            "code": "TICKET_UPDATE_FAILED",
            "message": "Could not mark ticket as used",
            "details": update_data,
        }), 503

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """UPDATE qr_record SET isValid=0, invalidatedAt=NOW(), invalidReason='USED_AT_GATE'
           WHERE ticketId=%s AND qrData=%s AND isValid=1""",
        (payload["ticketId"], payload["qrData"]),
    )
    db.commit()
    cur.close()
    db.close()

    return jsonify({
        "success": True,
        "code": "TICKET_ACCEPTED",
        "message": "Ticket validated. Entry confirmed.",
        "ticketId": payload["ticketId"],
        "concertId": payload["concertId"],
        "userId": payload["userId"],
        "ticketStatus": "USED",
        "concertName": concert_data.get("name"),
        "eventDate": concert_data.get("eventDate"),
    }), 200

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
