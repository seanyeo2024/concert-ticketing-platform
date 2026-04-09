from datetime import datetime, timedelta, timezone
import math
import os
import sys
import time
import uuid

import redis
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../notification/src"))
try:
    from amqp_publisher import publish as mq_publish
except ImportError:
    def mq_publish(rk, payload):
        print(f"[MQ STUB] {rk}: {payload}")


WINDOW_SECONDS = int(os.environ.get("PURCHASE_WINDOW_SECONDS", 600))
MAX_ACTIVE_WINDOWS = int(os.environ.get("MAX_ACTIVE_WINDOWS", 5))
HEARTBEAT_TIMEOUT_SECONDS = int(os.environ.get("QUEUE_HEARTBEAT_TIMEOUT_SECONDS", 20))
TICKET_URL = os.environ.get("TICKET_INVENTORY_SERVICE_URL", "http://localhost:5003")
CONCERT_URL = os.environ.get("CONCERT_SERVICE_URL", "http://localhost:5000")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
QUEUE_STATUSES = ("WAITING", "WINDOW_GRANTED", "COMPLETED", "EXPIRED")

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_timeout=5,
    socket_connect_timeout=5,
)

# Return a standardised JSON error payload for the Redis queue service.
def err(code, message, status=400):
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "service": "queue",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            }
        ),
        status,
    )


# Return the current UTC timestamp as an ISO string.
def now_iso():
    return datetime.utcnow().isoformat()


# Return the current UTC timestamp as Unix epoch seconds.
def now_epoch():
    return time.time()


# Parse an integer safely with a default fallback.
def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Fetch concert display metadata for queue notifications.
def fetch_concert_meta(concert_id):
    base_urls = [(CONCERT_URL or "").rstrip("/"), "http://concert:5000", "http://kong:8000", "http://localhost:5000"]
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


# Convert stored ISO timestamps into epoch seconds for Redis sorting.
def iso_to_epoch(value):
    if not value:
        return now_epoch()
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return now_epoch()


# Build the Redis hash key for a single user queue entry.
def entry_key(concert_id, user_id):
    return f"queue:{concert_id}:entry:{user_id}"


# Build the Redis sorted-set key for waiting users.
def waiting_key(concert_id):
    return f"queue:{concert_id}:waiting"


# Build the Redis sorted-set key for granted windows.
def granted_key(concert_id):
    return f"queue:{concert_id}:granted"


# Build the Redis set key for a specific queue status bucket.
def status_key(concert_id, status):
    return f"queue:{concert_id}:status:{status}"


# Build the Redis distributed lock key for a concert queue.
def lock_key(concert_id):
    return f"queue:{concert_id}:lock"


# Create a Redis lock object to serialise queue updates per concert.
def queue_lock(concert_id):
    return redis_client.lock(lock_key(concert_id), timeout=10, blocking_timeout=5)


# Read and normalise a user queue entry from Redis.
def get_entry(concert_id, user_id):
    row = redis_client.hgetall(entry_key(concert_id, user_id))
    if not row:
        return None
    return {
        "queueId": row.get("queueId"),
        "concertId": row.get("concertId"),
        "userId": row.get("userId"),
        "status": row.get("status"),
        "sessionToken": row.get("sessionToken") or None,
        "sessionExpiresAt": row.get("sessionExpiresAt") or None,
        "windowGrantedAt": row.get("windowGrantedAt") or None,
        "windowExpiresAt": row.get("windowExpiresAt") or None,
        "joinedAt": row.get("joinedAt") or None,
        "updatedAt": row.get("updatedAt") or None,
    }


# Persist a queue entry and keep its status membership sets in sync.
def save_entry(row):
    pipe = redis_client.pipeline()
    pipe.hset(
        entry_key(row["concertId"], row["userId"]),
        mapping={
            "queueId": row["queueId"],
            "concertId": row["concertId"],
            "userId": row["userId"],
            "status": row["status"],
            "sessionToken": row.get("sessionToken") or "",
            "sessionExpiresAt": row.get("sessionExpiresAt") or "",
            "windowGrantedAt": row.get("windowGrantedAt") or "",
            "windowExpiresAt": row.get("windowExpiresAt") or "",
            "joinedAt": row.get("joinedAt") or "",
            "updatedAt": row.get("updatedAt") or "",
        },
    )
    for status in QUEUE_STATUSES:
        pipe.srem(status_key(row["concertId"], status), row["userId"])
    pipe.sadd(status_key(row["concertId"], row["status"]), row["userId"])
    pipe.execute()


# Remove a queue entry from Redis and all associated indexes.
def delete_entry(concert_id, user_id):
    pipe = redis_client.pipeline()
    pipe.delete(entry_key(concert_id, user_id))
    pipe.zrem(waiting_key(concert_id), user_id)
    pipe.zrem(granted_key(concert_id), user_id)
    for status in QUEUE_STATUSES:
        pipe.srem(status_key(concert_id, status), user_id)
    pipe.execute()


# Compute a user's current queue position from Redis sorted sets.
def compute_position(concert_id, row):
    if row["status"] == "WAITING":
        rank = redis_client.zrank(waiting_key(concert_id), row["userId"])
        return None if rank is None else rank + 1
    if row["status"] == "WINDOW_GRANTED":
        return 1
    return 0


# Add derived fields such as queue position before returning a row.
def format_row(concert_id, row):
    payload = dict(row)
    payload["position"] = compute_position(concert_id, row)
    return payload


# Build the response payload for queue session validation calls.
def token_response(row):
    return {
        "valid": True,
        "concertId": row["concertId"],
        "userId": row["userId"],
        "sessionToken": row.get("sessionToken"),
        "expiresAt": row.get("sessionExpiresAt") or row.get("windowExpiresAt"),
        "status": row["status"],
    }


# Detect whether a granted session has gone stale due to missed heartbeats.
def is_heartbeat_stale(row):
    if row.get("status") != "WINDOW_GRANTED":
        return False
    updated_at_epoch = iso_to_epoch(row.get("updatedAt"))
    if updated_at_epoch <= 0:
        return False
    return now_epoch() - updated_at_epoch > HEARTBEAT_TIMEOUT_SECONDS


# Publish an event when a granted purchase window expires.
def publish_window_expired(row):
    try:
        concert_meta = fetch_concert_meta(row["concertId"])
        mq_publish(
            "queue.window.expired",
            {
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
            },
        )
    except Exception:
        pass


# Publish an event when a user receives a purchase window.
def publish_window_granted(user_id, concert_id, expires_at):
    try:
        concert_meta = fetch_concert_meta(concert_id)
        mq_publish(
            "queue.window.granted",
            {
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
            },
        )
    except Exception:
        pass


# Publish an event when a user enters the waiting room.
def publish_waiting_room_entered(user_id, concert_id, queue_id, queue_position):
    try:
        concert_meta = fetch_concert_meta(concert_id)
        position = max(parse_int(queue_position, 1), 1)
        people_ahead = max(position - 1, 0)
        mq_publish(
            "queue.waiting_room.entered",
            {
                "eventType": "queue.waiting_room.entered",
                "channel": "SMS",
                "userId": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "concertId": concert_id,
                    "concertName": concert_meta.get("concertName"),
                    "concertDateTime": concert_meta.get("concertDateTime"),
                    "queueId": queue_id,
                    "queuePosition": position,
                    "peopleAhead": people_ahead,
                    "estimatedWaitMins": math.ceil(people_ahead / 10),
                },
            },
        )
    except Exception:
        pass


# Publish an event when a waiting-room session expires.
def publish_waiting_room_session_expired(row):
    try:
        concert_meta = fetch_concert_meta(row["concertId"])
        queue_position = row.get("position")
        if queue_position is None:
            queue_position = compute_position(row["concertId"], row)
        mq_publish(
            "queue.waiting_room.session.expired",
            {
                "eventType": "queue.waiting_room.session.expired",
                "channel": "SMS",
                "userId": row["userId"],
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "concertId": row["concertId"],
                    "concertName": concert_meta.get("concertName"),
                    "concertDateTime": concert_meta.get("concertDateTime"),
                    "queueId": row.get("queueId"),
                    "queuePosition": queue_position if queue_position is not None else 0,
                },
            },
        )
    except Exception:
        pass


# Ask ticket inventory how many tickets remain available.
def fetch_available_seats(concert_id):
    try:
        res = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}?status=AVAILABLE", timeout=5)
        if res.status_code != 200:
            return 0
        return max(len(res.json().get("tickets", []) or []), 0)
    except Exception:
        return 0


# Reconcile Redis sorted sets with the canonical entry hashes.
def reconcile_queue_state_locked(concert_id):
    waiting_members = redis_client.zrange(waiting_key(concert_id), 0, -1)
    granted_members = redis_client.zrange(granted_key(concert_id), 0, -1)

    for user_id in waiting_members:
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WAITING":
            redis_client.zrem(waiting_key(concert_id), user_id)
            continue
        redis_client.zadd(waiting_key(concert_id), {user_id: iso_to_epoch(row.get("joinedAt"))})

    for user_id in granted_members:
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WINDOW_GRANTED":
            redis_client.zrem(granted_key(concert_id), user_id)
            continue
        redis_client.zadd(granted_key(concert_id), {user_id: iso_to_epoch(row.get("windowExpiresAt"))})


# Expire stale granted windows while the queue lock is held.
def expire_granted_windows_locked(concert_id):
    reconcile_queue_state_locked(concert_id)
    granted_users = redis_client.zrange(granted_key(concert_id), 0, -1)
    if not granted_users:
        return

    expired_users = []
    for user_id in granted_users:
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WINDOW_GRANTED":
            expired_users.append(user_id)
            continue
        expires_at_epoch = iso_to_epoch(row.get("sessionExpiresAt") or row.get("windowExpiresAt"))
        if expires_at_epoch <= now_epoch() or is_heartbeat_stale(row):
            expired_users.append(user_id)
    if not expired_users:
        return

    redis_client.zrem(granted_key(concert_id), *expired_users)
    updated_at = now_iso()
    for user_id in expired_users:
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WINDOW_GRANTED":
            continue
        row["status"] = "EXPIRED"
        row["sessionToken"] = None
        row["sessionExpiresAt"] = None
        row["updatedAt"] = updated_at
        save_entry(row)
        publish_window_expired(row)


# Promote waiting users into purchase windows while the queue lock is held.
def grant_windows_if_needed_locked(concert_id):
    reconcile_queue_state_locked(concert_id)
    expire_granted_windows_locked(concert_id)
    available_seats = fetch_available_seats(concert_id)
    target_active = max(0, min(MAX_ACTIVE_WINDOWS, available_seats))
    active_count = parse_int(redis_client.zcard(granted_key(concert_id)))
    slots_needed = max(target_active - active_count, 0)
    if slots_needed == 0:
        return

    waiting_users = redis_client.zrange(waiting_key(concert_id), 0, slots_needed - 1)
    if not waiting_users:
        return

    granted_at = datetime.utcnow()
    updated_at = granted_at.isoformat()
    granted_at_epoch = now_epoch()
    pipe = redis_client.pipeline()
    for user_id in waiting_users:
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WAITING":
            pipe.zrem(waiting_key(concert_id), user_id)
            continue
        expires_at = granted_at + timedelta(seconds=WINDOW_SECONDS)
        expires_at_epoch = granted_at_epoch + WINDOW_SECONDS
        row["status"] = "WINDOW_GRANTED"
        row["sessionToken"] = f"qs_{uuid.uuid4().hex}"
        row["sessionExpiresAt"] = expires_at.isoformat()
        row["windowGrantedAt"] = granted_at.isoformat()
        row["windowExpiresAt"] = expires_at.isoformat()
        row["updatedAt"] = updated_at
        save_entry(row)
        pipe.zrem(waiting_key(concert_id), user_id)
        pipe.zadd(granted_key(concert_id), {user_id: expires_at_epoch})
        publish_window_granted(user_id, concert_id, expires_at)
    pipe.execute()


# Return per-status counts for the current queue state.
def get_breakdown(concert_id):
    rows = []
    for status in QUEUE_STATUSES:
        count = parse_int(redis_client.scard(status_key(concert_id, status)))
        if count:
            rows.append({"status": status, "count": count})
    return rows


# Create a new waiting-room entry in Redis for a user.
@app.route("/queue/v1/queue/<concert_id>", methods=["POST"])
def join_queue(concert_id):
    data = request.get_json() or {}
    user_id = data.get("userId")
    if not user_id:
        return err("MISSING_USER_ID", "userId is required")

    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        expire_granted_windows_locked(concert_id)
        existing = get_entry(concert_id, user_id)
        if existing and existing["status"] in {"WAITING", "WINDOW_GRANTED", "COMPLETED"}:
            return err("ALREADY_IN_QUEUE", "User already has an active queue entry for this concert", 400)

        timestamp = now_iso()
        row = {
            "queueId": f"Q-{uuid.uuid4().hex[:8].upper()}",
            "concertId": concert_id,
            "userId": user_id,
            "status": "WAITING",
            "sessionToken": None,
            "sessionExpiresAt": None,
            "windowGrantedAt": None,
            "windowExpiresAt": None,
            "joinedAt": timestamp,
            "updatedAt": timestamp,
        }
        save_entry(row)
        redis_client.zadd(waiting_key(concert_id), {user_id: iso_to_epoch(row["joinedAt"])})
        initial_position = compute_position(concert_id, row)
        grant_windows_if_needed_locked(concert_id)
        latest = get_entry(concert_id, user_id)
        if latest and latest["status"] == "WAITING":
            publish_waiting_room_entered(user_id, concert_id, latest.get("queueId"), initial_position)

    return jsonify(format_row(concert_id, latest)), 201


# Return the latest queue status and position for a user.
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["GET"])
def get_position(concert_id, user_id):
    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        expire_granted_windows_locked(concert_id)
        row = get_entry(concert_id, user_id)
        if not row:
            return err("NOT_FOUND", "No queue entry found", 404)
        if row["status"] == "EXPIRED":
            return err("WINDOW_EXPIRED", "Purchase window has expired; please rejoin the queue", 410)

        grant_windows_if_needed_locked(concert_id)
        row = get_entry(concert_id, user_id)
        if not row:
            return err("NOT_FOUND", "No queue entry found", 404)
        if row["status"] == "EXPIRED":
            return err("WINDOW_EXPIRED", "Purchase window has expired; please rejoin the queue", 410)

    payload = format_row(concert_id, row)
    ahead = max((payload.get("position") or 1) - 1, 0)
    payload["estimatedWaitMins"] = 0 if row["status"] == "WINDOW_GRANTED" else math.ceil(ahead / 10)
    return jsonify(payload)


# Return queue breakdown statistics for a concert.
@app.route("/queue/v1/queue/<concert_id>", methods=["GET"])
def queue_depth(concert_id):
    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        expire_granted_windows_locked(concert_id)
        grant_windows_if_needed_locked(concert_id)
        rows = get_breakdown(concert_id)
    return jsonify({"concertId": concert_id, "breakdown": rows})


# Update a queue entry status and related session/window fields.
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["PUT"])
def update_entry(concert_id, user_id):
    data = request.get_json() or {}
    new_status = data.get("status")
    if new_status not in {"WAITING", "WINDOW_GRANTED", "COMPLETED", "EXPIRED"}:
        return err("INVALID_STATUS", "Unsupported queue status")

    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        row = get_entry(concert_id, user_id)
        if not row:
            return err("NOT_FOUND", "Queue entry not found", 404)

        previous_status = row["status"]
        previous_position = compute_position(concert_id, row)

        row["status"] = new_status
        row["updatedAt"] = now_iso()
        pipe = redis_client.pipeline()
        pipe.zrem(waiting_key(concert_id), user_id)
        pipe.zrem(granted_key(concert_id), user_id)

        if new_status == "WAITING":
            row["sessionToken"] = None
            row["sessionExpiresAt"] = None
            row["windowGrantedAt"] = None
            row["windowExpiresAt"] = None
            pipe.zadd(waiting_key(concert_id), {user_id: iso_to_epoch(row.get("joinedAt"))})
        elif new_status == "WINDOW_GRANTED":
            granted_at = datetime.utcnow()
            expires_at = granted_at + timedelta(seconds=WINDOW_SECONDS)
            expires_at_epoch = now_epoch() + WINDOW_SECONDS
            row["sessionToken"] = f"qs_{uuid.uuid4().hex}"
            row["sessionExpiresAt"] = expires_at.isoformat()
            row["windowGrantedAt"] = granted_at.isoformat()
            row["windowExpiresAt"] = expires_at.isoformat()
            pipe.zadd(granted_key(concert_id), {user_id: expires_at_epoch})
            publish_window_granted(user_id, concert_id, expires_at)
        elif new_status == "EXPIRED":
            row["sessionToken"] = None
            row["sessionExpiresAt"] = None
            row["position"] = previous_position
            if previous_status == "WINDOW_GRANTED":
                publish_window_expired(row)
            else:
                publish_waiting_room_session_expired(row)
        else:
            row["sessionToken"] = None
            row["sessionExpiresAt"] = None

        pipe.execute()
        save_entry(row)
        grant_windows_if_needed_locked(concert_id)

    return jsonify({"updated": True, "status": new_status})


# Remove a user from the Redis-backed queue.
@app.route("/queue/v1/queue/<concert_id>/<user_id>", methods=["DELETE"])
def leave_queue(concert_id, user_id):
    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        row = get_entry(concert_id, user_id)
        if not row:
            return err("NOT_FOUND", "Queue entry not found", 404)
        delete_entry(concert_id, user_id)
        grant_windows_if_needed_locked(concert_id)
    return jsonify({"deleted": True})


# Expose a health endpoint and verify Redis connectivity.
@app.route("/health")
def health():
    redis_client.ping()
    return jsonify({"status": "ok", "service": "queue", "backend": "redis"})


# Validate that a queue session token is still active and usable.
@app.route("/queue/v1/session/validate", methods=["POST"])
def validate_session():
    data = request.get_json() or {}
    concert_id = data.get("concertId")
    user_id = data.get("userId")
    session_token = data.get("sessionToken")
    if not all([concert_id, user_id, session_token]):
        return err("MISSING_FIELDS", "concertId, userId, and sessionToken are required")

    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        expire_granted_windows_locked(concert_id)
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WINDOW_GRANTED":
            return jsonify({"valid": False, "reason": "NO_ACTIVE_WINDOW"}), 403
        if row.get("sessionToken") != session_token:
            return jsonify({"valid": False, "reason": "INVALID_SESSION_TOKEN"}), 403
        expires_at_epoch = iso_to_epoch(row.get("sessionExpiresAt") or row.get("windowExpiresAt"))
        if expires_at_epoch <= now_epoch():
            row["status"] = "EXPIRED"
            row["sessionToken"] = None
            row["sessionExpiresAt"] = None
            row["updatedAt"] = now_iso()
            save_entry(row)
            redis_client.zrem(granted_key(concert_id), user_id)
            publish_window_expired(row)
            return jsonify({"valid": False, "reason": "SESSION_EXPIRED"}), 410
        if is_heartbeat_stale(row):
            row["status"] = "EXPIRED"
            row["sessionToken"] = None
            row["sessionExpiresAt"] = None
            row["updatedAt"] = now_iso()
            save_entry(row)
            redis_client.zrem(granted_key(concert_id), user_id)
            publish_window_expired(row)
            return jsonify({"valid": False, "reason": "SESSION_ABANDONED"}), 410
        return jsonify(token_response(row))


# Refresh a granted queue session so it is not treated as abandoned.
@app.route("/queue/v1/session/heartbeat", methods=["POST"])
def heartbeat_session():
    data = request.get_json() or {}
    concert_id = data.get("concertId")
    user_id = data.get("userId")
    session_token = data.get("sessionToken")
    if not all([concert_id, user_id, session_token]):
        return err("MISSING_FIELDS", "concertId, userId, and sessionToken are required")

    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        expire_granted_windows_locked(concert_id)
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WINDOW_GRANTED":
            return err("NO_ACTIVE_WINDOW", "No active purchase window for this user", 403)
        if row.get("sessionToken") != session_token:
            return err("INVALID_SESSION_TOKEN", "Queue session token is invalid", 403)
        expires_at_epoch = iso_to_epoch(row.get("sessionExpiresAt") or row.get("windowExpiresAt"))
        if expires_at_epoch <= now_epoch():
            row["status"] = "EXPIRED"
            row["sessionToken"] = None
            row["sessionExpiresAt"] = None
            row["updatedAt"] = now_iso()
            save_entry(row)
            redis_client.zrem(granted_key(concert_id), user_id)
            publish_window_expired(row)
            return err("SESSION_EXPIRED", "Purchase window has expired", 410)
        row["updatedAt"] = now_iso()
        save_entry(row)
        return jsonify(token_response(row))


# Consume a granted queue session after a successful purchase.
@app.route("/queue/v1/session/consume", methods=["POST"])
def consume_session():
    data = request.get_json() or {}
    concert_id = data.get("concertId")
    user_id = data.get("userId")
    session_token = data.get("sessionToken")
    if not all([concert_id, user_id, session_token]):
        return err("MISSING_FIELDS", "concertId, userId, and sessionToken are required")

    with queue_lock(concert_id):
        reconcile_queue_state_locked(concert_id)
        expire_granted_windows_locked(concert_id)
        row = get_entry(concert_id, user_id)
        if not row or row["status"] != "WINDOW_GRANTED":
            return err("NO_ACTIVE_WINDOW", "No active purchase window for this user", 403)
        if row.get("sessionToken") != session_token:
            return err("INVALID_SESSION_TOKEN", "Queue session token is invalid", 403)
        row["status"] = "COMPLETED"
        row["sessionToken"] = None
        row["sessionExpiresAt"] = None
        row["updatedAt"] = now_iso()
        save_entry(row)
        redis_client.zrem(granted_key(concert_id), user_id)
        grant_windows_if_needed_locked(concert_id)
    return jsonify({"consumed": True, "status": "COMPLETED"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)), debug=False)
