"""
Queue Service — Atomic Microservice
Port: 5002
DB:   queue_db (MySQL)
Also publishes: queue.window.granted, queue.window.expired → RabbitMQ
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector, os, uuid, sys
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../notification/src"))
try:
    from amqp_publisher import publish as mq_publish
except ImportError:
    def mq_publish(rk, payload): print(f"[MQ STUB] {rk}: {payload}")

WINDOW_SECONDS = int(os.environ.get("PURCHASE_WINDOW_SECONDS", 600))

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "queue_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "queue", "timestamp": datetime.utcnow().isoformat()}}), status

# POST /queue/v1/queue/<concertId>  — join queue
@app.route("/queue/v1/queue/<concert_id>", methods=["POST"])
def join_queue(concert_id):
    data = request.get_json()
    user_id = data.get("userId")
    if not user_id: return err("MISSING_USER_ID", "userId is required")
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT queueId FROM queue_entry WHERE concertId=%s AND userId=%s AND status IN ('WAITING','WINDOW_GRANTED')",
                (concert_id, user_id))
    if cur.fetchone():
        cur.close(); db.close()
        return err("ALREADY_IN_QUEUE", "User already has an active queue entry for this concert", 400)
    cur.execute("SELECT COUNT(*)+1 AS pos FROM queue_entry WHERE concertId=%s AND status='WAITING'", (concert_id,))
    position = cur.fetchone()["pos"]
    queue_id = f"Q-{uuid.uuid4().hex[:8].upper()}"
    cur.execute("""INSERT INTO queue_entry (queueId,concertId,userId,position,status,joinedAt,updatedAt)
                   VALUES (%s,%s,%s,%s,'WAITING',NOW(),NOW())""",
                (queue_id, concert_id, user_id, position))
    db.commit(); cur.close(); db.close()
    return jsonify({"queueId": queue_id, "concertId": concert_id, "userId": user_id,
                    "position": position, "status": "WAITING",
                    "joinedAt": datetime.utcnow().isoformat()}), 201

# GET /queue/v1/queue/<concertId>/<userId>
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["GET"])
def get_position(concert_id, user_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM queue_entry WHERE concertId=%s AND userId=%s ORDER BY joinedAt DESC LIMIT 1",
                (concert_id, user_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("NOT_FOUND", "No queue entry found", 404)
    if row.get("windowExpiresAt") and datetime.utcnow() > row["windowExpiresAt"]:
        return err("WINDOW_EXPIRED", "Purchase window has expired; please rejoin the queue", 410)
    return jsonify(row)

# GET /queue/v1/queue/<concertId>  — queue depth
@app.route("/queue/v1/queue/<concert_id>", methods=["GET"])
def queue_depth(concert_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT status, COUNT(*) AS count FROM queue_entry WHERE concertId=%s GROUP BY status", (concert_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"concertId": concert_id, "breakdown": rows})

# PUT /queue/v1/queue/<concertId>/<userId>  — update status
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["PUT"])
def update_entry(concert_id, user_id):
    data = request.get_json()
    new_status = data.get("status")
    db = get_db(); cur = db.cursor()
    if new_status == "WINDOW_GRANTED":
        granted_at = datetime.utcnow()
        expires_at = granted_at + timedelta(seconds=WINDOW_SECONDS)
        cur.execute("""UPDATE queue_entry SET status='WINDOW_GRANTED',
                       windowGrantedAt=%s, windowExpiresAt=%s, updatedAt=NOW()
                       WHERE concertId=%s AND userId=%s""",
                    (granted_at, expires_at, concert_id, user_id))
        db.commit()
        mq_publish("queue.window.granted", {"userId": user_id, "concertId": concert_id,
                                             "windowExpiresAt": expires_at.isoformat()})
    else:
        cur.execute("UPDATE queue_entry SET status=%s, updatedAt=NOW() WHERE concertId=%s AND userId=%s",
                    (new_status, concert_id, user_id))
        db.commit()
    affected = cur.rowcount; cur.close(); db.close()
    if affected == 0: return err("NOT_FOUND", "Queue entry not found", 404)
    return jsonify({"updated": True, "status": new_status})

# DELETE /queue/v1/queue/<concertId>/<userId>
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["DELETE"])
def leave_queue(concert_id, user_id):
    db = get_db(); cur = db.cursor()
    cur.execute("DELETE FROM queue_entry WHERE concertId=%s AND userId=%s", (concert_id, user_id))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    if affected == 0: return err("NOT_FOUND", "Queue entry not found", 404)
    return jsonify({"deleted": True})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "queue"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)), debug=False)
