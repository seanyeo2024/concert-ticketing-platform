"""
Queue Service — Atomic Microservice
Port: 5002
DB:   queue_db (MySQL)
Also publishes: queue.window.granted, queue.window.expired → RabbitMQ
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector, os, uuid, sys, math, requests, time
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../notification/src"))
try:
    from amqp_publisher import publish as mq_publish
except ImportError:
    def mq_publish(rk, payload): print(f"[MQ STUB] {rk}: {payload}")

WINDOW_SECONDS = int(os.environ.get("PURCHASE_WINDOW_SECONDS", 600))
max_windows_str = os.environ.get("MAX_ACTIVE_WINDOWS", "5").strip()
MAX_ACTIVE_WINDOWS = int(max_windows_str) if max_windows_str else 5
TICKET_URL = os.environ.get("TICKET_INVENTORY_SERVICE_URL", "http://localhost:5003")

# Open a MySQL connection to the queue database.
def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "queue_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

# Return a standardised JSON error payload for the queue service.
def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "queue", "timestamp": datetime.utcnow().isoformat()}}), status


# Fetch concert display metadata for queue-related notifications.
def fetch_concert_meta(concert_id):
    base_urls = [(CONCERT_URL or "").rstrip("/"), "http://concert:5000", "http://localhost:5000"]
    tried = set()
    for base in base_urls:
        if not base or base in tried:
            continue
        tried.add(base)
        try:
            res = requests.get(f"{base}/concerts/{concert_id}", timeout=5)
            if res.status_code == 200 and isinstance(res.json(), dict):
                data = res.json()
                return {
                    "concertName": data.get("name") or data.get("concertName") or data.get("title") or concert_id,
                    "concertDateTime": data.get("eventDate") or data.get("concertDateTime"),
                }
        except Exception:
            continue
    return {"concertName": concert_id, "concertDateTime": None}


# Identify lock wait and deadlock errors that are safe to retry.
def is_retryable_db_error(exc):
    return getattr(exc, "errno", None) in {1205, 1213}


# Create the queue table and supporting indexes if they do not exist.
def ensure_schema():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS queue_entry (
          queueId VARCHAR(36) PRIMARY KEY,
          concertId VARCHAR(36) NOT NULL,
          userId VARCHAR(36) NOT NULL,
          position INT NOT NULL,
          status VARCHAR(20) NOT NULL DEFAULT 'WAITING',
          windowGrantedAt DATETIME NULL,
          windowExpiresAt DATETIME NULL,
          joinedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uq_queue_user (concertId, userId),
          KEY idx_concert_status_position (concertId, status, position)
        )
        """
    )
    db.commit()
    cur.close()
    db.close()


# Publish an event when a granted purchase window expires.
def publish_window_expired(row):
    try:
        concert_meta = fetch_concert_meta(row["concertId"])
        mq_publish("queue.window.expired", {
            "eventType": "queue.window.expired",
            "channel": "SMS",
            "userId": row["userId"],
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "concertId": row["concertId"],
                "concertName": concert_meta.get("concertName"),
                "concertDateTime": concert_meta.get("concertDateTime"),
                "queueId": row["queueId"],
            },
        })
    except Exception:
        pass


# Publish an event when a waiting user receives a purchase window.
def publish_window_granted(user_id, concert_id, expires_at):
    try:
        concert_meta = fetch_concert_meta(concert_id)
        mq_publish("queue.window.granted", {
            "eventType": "queue.window.granted",
            "channel": "SMS",
            "userId": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "concertId": concert_id,
                "concertName": concert_meta.get("concertName"),
                "concertDateTime": concert_meta.get("concertDateTime"),
                "windowExpiresAt": expires_at.isoformat(),
                "windowDurationSeconds": WINDOW_SECONDS,
                "windowDurationMinutes": max(1, math.ceil(WINDOW_SECONDS / 60)),
            },
        })
    except Exception:
        pass


# Publish an event when a user first enters the waiting room.
def publish_waiting_room_entered(user_id, concert_id, queue_id, position):
    try:
        concert_meta = fetch_concert_meta(concert_id)
        queue_position = max(int(position or 1), 1)
        waiting_ahead = max(queue_position - 1, 0)
        mq_publish("queue.waiting_room.entered", {
            "eventType": "queue.waiting_room.entered",
            "channel": "SMS",
            "userId": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "concertId": concert_id,
                "concertName": concert_meta.get("concertName"),
                "concertDateTime": concert_meta.get("concertDateTime"),
                "queueId": queue_id,
                "queuePosition": queue_position,
                "peopleAhead": waiting_ahead,
                "estimatedWaitMins": math.ceil(waiting_ahead / 10),
            },
        })
    except Exception:
        pass


# Publish an event when a waiting-room session expires before window grant.
def publish_waiting_room_session_expired(user_id, concert_id, queue_id=None, position=None):
    try:
        concert_meta = fetch_concert_meta(concert_id)
        queue_position = max(int(position or 1), 1)
        mq_publish("queue.waiting_room.session.expired", {
            "eventType": "queue.waiting_room.session.expired",
            "channel": "SMS",
            "userId": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "concertId": concert_id,
                "concertName": concert_meta.get("concertName"),
                "concertDateTime": concert_meta.get("concertDateTime"),
                "queueId": queue_id,
                "queuePosition": queue_position,
            },
        })
    except Exception:
        pass


# Ask ticket inventory how many tickets are still available for sale.
def fetch_available_seats(concert_id):
    try:
        res = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}?status=AVAILABLE", timeout=5)
        if res.status_code != 200:
            return 0
        data = res.json()
        return max(len(data.get("tickets", []) or []), 0)
    except Exception:
        return 0


# Recalculate contiguous queue positions for all waiting users.
def rebalance_waiting_positions(concert_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        """
        SELECT queueId
        FROM queue_entry
        WHERE concertId=%s AND status='WAITING'
        ORDER BY joinedAt, updatedAt, queueId
        """,
        (concert_id,),
    )
    rows = cur.fetchall()
    cur.close()
    cur = db.cursor()
    for index, row in enumerate(rows, start=1):
        cur.execute(
            "UPDATE queue_entry SET position=%s WHERE queueId=%s AND position<>%s",
            (index, row["queueId"], index),
        )
    db.commit()
    cur.close()
    db.close()


# Expire any granted windows that have passed their deadline.
def expire_granted_windows(concert_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        """
        SELECT queueId, concertId, userId, windowExpiresAt
        FROM queue_entry
        WHERE concertId=%s AND status='WINDOW_GRANTED'
        """,
        (concert_id,),
    )
    rows = cur.fetchall()
    cur.close()
    expired = [row for row in rows if row.get("windowExpiresAt") and datetime.utcnow() > row["windowExpiresAt"]]
    if not expired:
        db.close()
        return
    cur = db.cursor()
    for row in expired:
        cur.execute(
            "UPDATE queue_entry SET status='EXPIRED', updatedAt=NOW() WHERE queueId=%s AND status='WINDOW_GRANTED'",
            (row["queueId"],),
        )
        publish_window_expired(row)
    db.commit()
    cur.close()
    db.close()


# Grant new purchase windows up to the configured active limit.
def grant_windows_if_needed(concert_id):
    expire_granted_windows(concert_id)
    rebalance_waiting_positions(concert_id)
    available_seats = fetch_available_seats(concert_id)
    target_active = max(0, min(MAX_ACTIVE_WINDOWS, available_seats))

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        """
        SELECT COUNT(*) AS activeCount
        FROM queue_entry
        WHERE concertId=%s AND status='WINDOW_GRANTED'
        """,
        (concert_id,),
    )
    active_count = cur.fetchone()["activeCount"]
    slots_needed = max(target_active - active_count, 0)
    if slots_needed == 0:
        cur.close()
        db.close()
        return

    cur.execute(
        """
        SELECT queueId, userId, position
        FROM queue_entry
        WHERE concertId=%s AND status='WAITING'
        ORDER BY position, joinedAt, queueId
        LIMIT %s
        """,
        (concert_id, slots_needed),
    )
    to_grant = cur.fetchall()
    cur.close()

    if not to_grant:
        db.close()
        return

    cur = db.cursor()
    granted_at = datetime.utcnow()
    for row in to_grant:
        expires_at = granted_at + timedelta(seconds=WINDOW_SECONDS)
        cur.execute(
            """
            UPDATE queue_entry
            SET status='WINDOW_GRANTED',
                windowGrantedAt=%s,
                windowExpiresAt=%s,
                updatedAt=NOW()
            WHERE queueId=%s AND status='WAITING'
            """,
            (granted_at, expires_at, row["queueId"]),
        )
        publish_window_granted(row["userId"], concert_id, expires_at)
    db.commit()
    cur.close()
    db.close()
    rebalance_waiting_positions(concert_id)


# Retry window-grant logic safely when transient DB lock errors occur.
def safe_grant_windows_if_needed(concert_id):
    try:
        grant_windows_if_needed(concert_id)
    except mysql.connector.Error as exc:
        if not is_retryable_db_error(exc):
            raise
        print(f"[QUEUE] Skipping grant_windows_if_needed for {concert_id} due to retryable DB lock error: {exc}")


# Expire a single queue row on read if its granted window is already stale.
def expire_if_needed(row):
    expires_at = row.get("windowExpiresAt")
    if row.get("status") == "WINDOW_GRANTED" and expires_at and datetime.utcnow() > expires_at:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            UPDATE queue_entry
            SET status='EXPIRED', updatedAt=NOW()
            WHERE queueId=%s AND status='WINDOW_GRANTED'
            """,
            (row["queueId"],),
        )
        db.commit()
        cur.close()
        db.close()
        row["status"] = "EXPIRED"
        publish_window_expired(row)
        return True
    return False


ensure_schema()

# POST /queue/v1/queue/<concertId>  — join queue
# Create a new waiting-room entry for a user.
@app.route("/queue/v1/queue/<concert_id>", methods=["POST"])
def join_queue(concert_id):
    data = request.get_json() or {}
    user_id = data.get("userId")
    if not user_id: return err("MISSING_USER_ID", "userId is required")
    attempts = 3
    queue_id = None
    for attempt in range(attempts):
        db = None
        cur = None
        try:
            db = get_db()
            cur = db.cursor(dictionary=True)
            cur.execute("SELECT queueId FROM queue_entry WHERE concertId=%s AND userId=%s AND status IN ('WAITING','WINDOW_GRANTED','COMPLETED')",
                        (concert_id, user_id))
            if cur.fetchone():
                return err("ALREADY_IN_QUEUE", "User already has an active queue entry for this concert", 400)
            cur.execute("SELECT COUNT(*)+1 AS pos FROM queue_entry WHERE concertId=%s AND status='WAITING'", (concert_id,))
            position = cur.fetchone()["pos"]
            queue_id = f"Q-{uuid.uuid4().hex[:8].upper()}"
            cur.execute("""INSERT INTO queue_entry (queueId,concertId,userId,position,status,joinedAt,updatedAt)
                           VALUES (%s,%s,%s,%s,'WAITING',NOW(),NOW())""",
                        (queue_id, concert_id, user_id, position))
            db.commit()
            break
        except mysql.connector.Error as exc:
            if db:
                db.rollback()
            if not is_retryable_db_error(exc) or attempt == attempts - 1:
                return err("QUEUE_DB_BUSY", "Queue is busy right now. Please try again.", 503)
            time.sleep(0.2 * (attempt + 1))
        finally:
            if cur:
                cur.close()
            if db:
                db.close()

    safe_grant_windows_if_needed(concert_id)
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM queue_entry WHERE queueId=%s", (queue_id,))
    row = cur.fetchone()
    cur.close(); db.close()
    if row and row.get("status") == "WAITING":
        publish_waiting_room_entered(user_id, concert_id, row.get("queueId"), row.get("position"))
    return jsonify(row), 201

# GET /queue/v1/queue/<concertId>/<userId>
# Return the latest queue position and status for a user.
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["GET"])
def get_position(concert_id, user_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM queue_entry WHERE concertId=%s AND userId=%s ORDER BY joinedAt DESC LIMIT 1",
                (concert_id, user_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("NOT_FOUND", "No queue entry found", 404)
    if expire_if_needed(row):
        safe_grant_windows_if_needed(concert_id)
        return err("WINDOW_EXPIRED", "Purchase window has expired; please rejoin the queue", 410)
    safe_grant_windows_if_needed(concert_id)
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM queue_entry WHERE concertId=%s AND userId=%s ORDER BY joinedAt DESC LIMIT 1",
                (concert_id, user_id))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("NOT_FOUND", "No queue entry found", 404)
    ahead = max((row.get("position") or 1) - 1, 0)
    row["estimatedWaitMins"] = 0 if row.get("status") == "WINDOW_GRANTED" else math.ceil(ahead / 10)
    return jsonify(row)

# GET /queue/v1/queue/<concertId>  — queue depth
# Return queue depth statistics grouped by status.
@app.route("/queue/v1/queue/<concert_id>", methods=["GET"])
def queue_depth(concert_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT status, COUNT(*) AS count FROM queue_entry WHERE concertId=%s GROUP BY status", (concert_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    queue_depth = sum(int(r.get("count", 0)) for r in rows)
    waiting = sum(int(r.get("count", 0)) for r in rows if r.get("status") == "WAITING")
    window_granted = sum(int(r.get("count", 0)) for r in rows if r.get("status") == "WINDOW_GRANTED")
    return jsonify({
        "concertId": concert_id,
        "queueDepth": queue_depth,
        "waitingCount": waiting,
        "windowGrantedCount": window_granted,
        "breakdown": rows,
    })

# PUT /queue/v1/queue/<concertId>/<userId>  — update status
# Update a queue entry status and publish matching lifecycle events.
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["PUT"])
def update_entry(concert_id, user_id):
    data = request.get_json() or {}
    new_status = data.get("status")
    if new_status not in {"WAITING", "WINDOW_GRANTED", "COMPLETED", "EXPIRED"}:
        return err("INVALID_STATUS", "Unsupported queue status")
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT queueId, position, status FROM queue_entry WHERE concertId=%s AND userId=%s ORDER BY joinedAt DESC LIMIT 1",
        (concert_id, user_id),
    )
    existing = cur.fetchone()
    if not existing:
        cur.close(); db.close()
        return err("NOT_FOUND", "Queue entry not found", 404)
    cur.close(); cur = db.cursor()
    if new_status == "WINDOW_GRANTED":
        granted_at = datetime.utcnow()
        expires_at = granted_at + timedelta(seconds=WINDOW_SECONDS)
        cur.execute("""UPDATE queue_entry SET status='WINDOW_GRANTED',
                       windowGrantedAt=%s, windowExpiresAt=%s, updatedAt=NOW()
                       WHERE concertId=%s AND userId=%s""",
                    (granted_at, expires_at, concert_id, user_id))
        db.commit()
        publish_window_granted(user_id, concert_id, expires_at)
    else:
        cur.execute("UPDATE queue_entry SET status=%s, updatedAt=NOW() WHERE concertId=%s AND userId=%s",
                    (new_status, concert_id, user_id))
        db.commit()
        if new_status == "EXPIRED":
            if existing.get("status") == "WINDOW_GRANTED":
                publish_window_expired({
                    "queueId": existing.get("queueId"),
                    "concertId": concert_id,
                    "userId": user_id,
                })
            else:
                publish_waiting_room_session_expired(
                    user_id,
                    concert_id,
                    existing.get("queueId"),
                    existing.get("position"),
                )
    affected = cur.rowcount; cur.close(); db.close()
    if affected == 0: return err("NOT_FOUND", "Queue entry not found", 404)
    safe_grant_windows_if_needed(concert_id)
    return jsonify({"updated": True, "status": new_status})

# DELETE /queue/v1/queue/<concertId>/<userId>
# Remove a user from the queue and free space for others.
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["DELETE"])
def leave_queue(concert_id, user_id):
    db = get_db(); cur = db.cursor()
    cur.execute("DELETE FROM queue_entry WHERE concertId=%s AND userId=%s", (concert_id, user_id))
    db.commit(); affected = cur.rowcount; cur.close(); db.close()
    if affected == 0: return err("NOT_FOUND", "Queue entry not found", 404)
    safe_grant_windows_if_needed(concert_id)
    return jsonify({"deleted": True})

# Expose a simple health endpoint for container checks.
@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "queue"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)), debug=False)
