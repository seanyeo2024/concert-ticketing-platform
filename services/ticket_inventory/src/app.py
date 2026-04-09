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

# Open a MySQL connection to the ticket inventory database.
def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "ticket_inventory_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

# Return a standardised JSON error payload for the inventory service.
def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "ticket_inventory", "timestamp": datetime.utcnow().isoformat()}}), status


VALID_TRANSITIONS = {
    "AVAILABLE": {"PENDING"},
    "PENDING": {"AVAILABLE", "CONFIRMED", "REFUNDED"},
    "CONFIRMED": {"RESALE_LISTED", "USED", "REFUNDED"},
    "RESALE_LISTED": {"RESALE_PENDING", "CONFIRMED", "REFUNDED"},
    "RESALE_PENDING": {"RESALE_LISTED", "CONFIRMED", "REFUNDED"},
    "USED": set(),
    "REFUNDED": set(),
}


# Create the ticket table and indexes if they do not already exist.
def ensure_schema():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket (
          ticketId VARCHAR(36) NOT NULL,
          concertId VARCHAR(36) NOT NULL,
          seatNumber VARCHAR(20) NOT NULL,
          categoryId VARCHAR(36) NOT NULL,
          ownerId VARCHAR(36) NULL DEFAULT NULL,
          status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',
          purchasePrice DECIMAL(10,2) NULL DEFAULT NULL,
          resalePrice DECIMAL(10,2) NULL DEFAULT NULL,
          resaleListingId VARCHAR(36) NULL DEFAULT NULL,
          version BIGINT NOT NULL DEFAULT 0,
          createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (ticketId),
          UNIQUE KEY uq_concert_seat (concertId, seatNumber),
          KEY idx_concert_status (concertId, status),
          KEY idx_owner_status (ownerId, status),
          KEY idx_resale_available (concertId, status, resalePrice)
        )
        """
    )
    db.commit()
    cur.close()
    db.close()


ensure_schema()

# GET /tickets/v1/tickets/<concertId>
# List tickets for a concert, optionally filtered by status.
@app.route("/tickets/v1/tickets/<concert_id>", methods=["GET"])
def list_tickets(concert_id):
    status_filter = request.args.get("status", "AVAILABLE")
    db = get_db(); cur = db.cursor(dictionary=True)
    if status_filter == "ALL":
        cur.execute("SELECT * FROM ticket WHERE concertId=%s ORDER BY categoryId, seatNumber", (concert_id,))
    else:
        cur.execute("SELECT * FROM ticket WHERE concertId=%s AND status=%s ORDER BY categoryId, seatNumber",
                    (concert_id, status_filter))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"concertId": concert_id, "tickets": rows, "count": len(rows)})

# GET /tickets/v1/tickets/<concertId>/resale
# List tickets that are currently on the resale marketplace.
@app.route("/tickets/v1/tickets/<concert_id>/resale", methods=["GET"])
def list_resale(concert_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM ticket WHERE concertId=%s AND status='RESALE_LISTED' ORDER BY resalePrice",
                (concert_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"concertId": concert_id, "listings": rows, "count": len(rows)})

# GET /tickets/v1/tickets/<concertId>/<ticketId>
# Fetch a specific ticket by concert and ticket id.
@app.route("/tickets/v1/tickets/<concert_id>/<ticket_id>", methods=["GET"])
def get_ticket(concert_id, ticket_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM ticket WHERE ticketId=%s AND concertId=%s", (ticket_id, concert_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("TICKET_NOT_FOUND", f"Ticket {ticket_id} not found", 404)
    return jsonify(row)

# POST /tickets/v1/tickets  — bulk create (admin)
# Bulk-create ticket inventory rows during concert setup.
@app.route("/tickets/v1/tickets", methods=["POST"])
def create_tickets():
    data = request.get_json() or {}
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
# Update ticket state and ownership using optimistic locking.
@app.route("/tickets/v1/tickets/<concert_id>/<ticket_id>", methods=["PUT"])
def update_ticket(concert_id, ticket_id):
    data = request.get_json()
    version = data.get("version")
    if version is None: return err("VERSION_REQUIRED", "version field is required for optimistic locking")
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM ticket WHERE ticketId=%s AND concertId=%s", (ticket_id, concert_id))
    existing = cur.fetchone()
    if not existing:
        cur.close(); db.close()
        return err("TICKET_NOT_FOUND", f"Ticket {ticket_id} not found", 404)
    if int(existing["version"]) != int(version):
        cur.close(); db.close()
        return err("VERSION_CONFLICT",
                   "Optimistic lock failed — ticket was modified by another request. Refresh and retry.", 409)
    new_status = data.get("status")
    if new_status and new_status != existing["status"]:
        allowed = VALID_TRANSITIONS.get(existing["status"], set())
        if new_status not in allowed:
            cur.close(); db.close()
            return err("INVALID_STATUS_TRANSITION",
                       f"Cannot transition ticket from {existing['status']} to {new_status}", 409)
    cur.close()
    db = get_db(); cur = db.cursor()
    # Build dynamic SET clause from provided fields
    allowed = ["status", "ownerId", "purchasePrice", "resalePrice", "resaleListingId"]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates: return err("NO_FIELDS", "No updatable fields provided")
    
    # Validate numeric fields
    if "purchasePrice" in updates and updates["purchasePrice"] is not None:
        try:
            updates["purchasePrice"] = float(updates["purchasePrice"])
            if updates["purchasePrice"] < 0:
                return err("INVALID_PRICE", "purchasePrice cannot be negative", 400)
        except (ValueError, TypeError):
            return err("INVALID_PRICE", "purchasePrice must be a number", 400)
    
    if "resalePrice" in updates and updates["resalePrice"] is not None:
        try:
            updates["resalePrice"] = float(updates["resalePrice"])
            if updates["resalePrice"] < 0:
                return err("INVALID_PRICE", "resalePrice cannot be negative", 400)
        except (ValueError, TypeError):
            return err("INVALID_PRICE", "resalePrice must be a number", 400)
    
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
# Mark all active tickets for a concert as pending refund processing.
@app.route("/tickets/v1/tickets/<concert_id>/cancel-all", methods=["PUT"])
def cancel_all(concert_id):
    data = request.get_json() or {}
    reason = data.get("reason", "Concert cancelled")
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS pendingCount FROM ticket WHERE concertId=%s AND status='PENDING'", (concert_id,))
    pending_count = cur.fetchone()["pendingCount"]
    cur.close(); db.close()
    db = get_db(); cur = db.cursor()
    cur.execute("""UPDATE ticket SET status='PENDING', updatedAt=NOW()
                   WHERE concertId=%s AND status IN ('CONFIRMED','PENDING','RESALE_LISTED','RESALE_PENDING')""",
                (concert_id,))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    return jsonify({"concertId": concert_id, "ticketsQueuedForRefund": affected, "ticketsPending": pending_count,
                    "reason": reason, "updatedAt": datetime.utcnow().isoformat()})


# Finalise a batch of pending tickets as refunded.
@app.route("/tickets/v1/tickets/<concert_id>/refund-batch", methods=["PUT"])
def refund_batch(concert_id):
    data = request.get_json() or {}
    raw_ticket_ids = data.get("ticketIds") or []
    ticket_ids = [str(ticket_id).strip() for ticket_id in raw_ticket_ids if str(ticket_id).strip()]
    if not ticket_ids:
        return err("EMPTY_PAYLOAD", "ticketIds array is required")

    placeholders = ", ".join(["%s"] * len(ticket_ids))
    params = [concert_id, *ticket_ids]
    db = get_db(); cur = db.cursor()
    cur.execute(
        f"""UPDATE ticket SET status='REFUNDED', updatedAt=NOW()
            WHERE concertId=%s AND ticketId IN ({placeholders}) AND status='PENDING'""",
        params,
    )
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    return jsonify({
        "concertId": concert_id,
        "ticketIds": ticket_ids,
        "ticketsRefunded": affected,
        "updatedAt": datetime.utcnow().isoformat(),
    })

# Expose a simple health endpoint for container checks.
@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "ticket_inventory"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5003)), debug=False)
