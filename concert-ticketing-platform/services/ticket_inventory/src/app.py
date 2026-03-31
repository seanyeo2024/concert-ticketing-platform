"""
Ticket Inventory Service — Atomic Microservice
Port: 5003
DB:   ticket_inventory_db (MySQL)
Most reused service: S1, S2a, S2b, S3
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
        database=os.environ.get("MYSQL_DATABASE", "ticket_inventory_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "ticket_inventory", "timestamp": datetime.utcnow().isoformat()}}), status

# GET /tickets/v1/tickets/<concertId>
@app.route("/tickets/v1/tickets/<concert_id>", methods=["GET"])
def list_tickets(concert_id):
    status_filter = request.args.get("status", "AVAILABLE")
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM ticket WHERE concertId=%s AND status=%s ORDER BY categoryId, seatNumber",
                (concert_id, status_filter))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"concertId": concert_id, "tickets": rows, "count": len(rows)})

# GET /tickets/v1/tickets/<concertId>/resale
@app.route("/tickets/v1/tickets/<concert_id>/resale", methods=["GET"])
def list_resale(concert_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM ticket WHERE concertId=%s AND status='RESALE_LISTED' ORDER BY resalePrice",
                (concert_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"concertId": concert_id, "listings": rows, "count": len(rows)})

# GET /tickets/v1/tickets/<concertId>/<ticketId>
@app.route("/tickets/v1/tickets/<concert_id>/<ticket_id>", methods=["GET"])
def get_ticket(concert_id, ticket_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM ticket WHERE ticketId=%s AND concertId=%s", (ticket_id, concert_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("TICKET_NOT_FOUND", f"Ticket {ticket_id} not found", 404)
    return jsonify(row)

# POST /tickets/v1/tickets  — bulk create (admin)
@app.route("/tickets/v1/tickets", methods=["POST"])
def create_tickets():
    data = request.get_json()
    tickets = data.get("tickets", [])
    if not tickets: return err("EMPTY_PAYLOAD", "tickets array is required")
    db = get_db(); cur = db.cursor()
    created = []
    for t in tickets:
        tid = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        cur.execute("""INSERT INTO ticket (ticketId,concertId,seatNumber,categoryId,status,version)
                       VALUES (%s,%s,%s,%s,'AVAILABLE',0)""",
                    (tid, t["concertId"], t["seatNumber"], t["categoryId"]))
        created.append(tid)
    db.commit(); cur.close(); db.close()
    return jsonify({"created": len(created), "ticketIds": created}), 201

# PUT /tickets/v1/tickets/<concertId>/<ticketId>  — update with optimistic lock
@app.route("/tickets/v1/tickets/<concert_id>/<ticket_id>", methods=["PUT"])
def update_ticket(concert_id, ticket_id):
    data = request.get_json()
    version = data.get("version")
    if version is None: return err("VERSION_REQUIRED", "version field is required for optimistic locking")
    db = get_db(); cur = db.cursor()
    # Build dynamic SET clause from provided fields
    allowed = ["status", "ownerId", "purchasePrice", "resalePrice", "resaleListingId"]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates: return err("NO_FIELDS", "No updatable fields provided")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    values = list(updates.values()) + [int(version), ticket_id, concert_id]
    cur.execute(f"UPDATE ticket SET {set_clause}, version=version+1, updatedAt=NOW() "
                f"WHERE version=%s AND ticketId=%s AND concertId=%s", values)
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    if affected == 0:
        return err("VERSION_CONFLICT",
                   "Optimistic lock failed — ticket was modified by another request. Refresh and retry.", 409)
    return jsonify({"updated": True, "ticketId": ticket_id})

# PUT /tickets/v1/tickets/<concertId>/cancel-all  — S3 bulk refund
@app.route("/tickets/v1/tickets/<concert_id>/cancel-all", methods=["PUT"])
def cancel_all(concert_id):
    data = request.get_json()
    reason = data.get("reason", "Concert cancelled")
    db = get_db(); cur = db.cursor()
    cur.execute("""UPDATE ticket SET status='REFUNDED', updatedAt=NOW()
                   WHERE concertId=%s AND status IN ('CONFIRMED','PENDING','RESALE_LISTED','RESALE_PENDING')""",
                (concert_id,))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    return jsonify({"concertId": concert_id, "ticketsRefunded": affected,
                    "reason": reason, "updatedAt": datetime.utcnow().isoformat()})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "ticket_inventory"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5003)), debug=False)
