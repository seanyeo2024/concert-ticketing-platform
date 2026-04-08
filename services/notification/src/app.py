"""
Notification Service — Atomic Microservice
Port: 5006
DB:   notification_db (MySQL)
Consumes: RabbitMQ topic exchange (all ctms_topic routing keys)
External: Twilio / SendGrid
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector, os, uuid, json, threading
from datetime import datetime
import pika
import re
import time
from importlib import import_module

app = Flask(__name__)
CORS(app)

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "notification_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "notification", "timestamp": datetime.utcnow().isoformat()}}), status


E164_PATTERN = re.compile(r'^\+[1-9]\d{7,14}$')
SMS_MAX_LENGTH = 320


def is_e164_phone_number(value):
    return isinstance(value, str) and bool(E164_PATTERN.fullmatch(value.strip().replace(" ", "")))


def normalize_phone(value):
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace(" ", "")
    return cleaned if is_e164_phone_number(cleaned) else None


def get_user_contact(user_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT userId, phoneE164, smsOptIn FROM user_contact WHERE userId=%s",
            (user_id,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        db.close()


def resolve_sms_recipient(payload, data, user_id):
    for candidate in (
        payload.get("phoneNumber"),
        payload.get("toNumber"),
        payload.get("contactPhone"),
        data.get("phoneNumber"),
        data.get("toNumber"),
        data.get("contactPhone"),
        data.get("sellerPhoneNumber"),
        data.get("buyerPhoneNumber"),
    ):
        normalized = normalize_phone(candidate)
        if normalized:
            return normalized

    contact = get_user_contact(user_id)
    if not contact:
        raise ValueError(f"No contact record found for user {user_id}")
    if not contact.get("smsOptIn"):
        raise ValueError(f"User {user_id} has not opted in to SMS notifications")

    normalized = normalize_phone(contact.get("phoneE164"))
    if not normalized:
        raise ValueError(f"User {user_id} does not have a valid E.164 phone number")
    return normalized


def ensure_schema():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_contact (
          userId VARCHAR(36) PRIMARY KEY,
          email VARCHAR(200) NULL,
          phoneE164 VARCHAR(20) NOT NULL,
          smsOptIn TINYINT(1) NOT NULL DEFAULT 0,
          createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_log (
          notificationId VARCHAR(36) PRIMARY KEY,
          userId VARCHAR(36) NOT NULL,
          eventType VARCHAR(60) NOT NULL,
          channel VARCHAR(10) NOT NULL,
          subject VARCHAR(200) NULL,
          body TEXT NOT NULL,
          status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
          refId VARCHAR(36) NULL,
          externalMsgId VARCHAR(200) NULL,
          retryCount INT NOT NULL DEFAULT 0,
          sentAt DATETIME NULL,
          createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          KEY idx_notification_user_event (userId, eventType),
          KEY idx_notification_status_retry (status, retryCount)
        )
        """
    )
    db.commit()
    cur.close()
    db.close()

def send_email(to_user, subject, body):
    """Stub — replace with SendGrid / SMTP call."""
    # TODO: sendgrid.SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(...)
    print(f"[EMAIL STUB] To={to_user} Subject={subject}")
    return f"msg_{uuid.uuid4().hex[:8]}", True

def send_sms(to_number, body):
    """Send an SMS via Twilio."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = normalize_phone(os.environ.get("TWILIO_FROM_NUMBER"))

    if not account_sid or not auth_token or not from_number:
        raise RuntimeError("Twilio environment variables are not configured")

    to_number = normalize_phone(to_number)
    if not to_number:
        raise ValueError("SMS recipient must be in E.164 format, e.g. +6591234567")

    body = (body or "").strip()
    if len(body) > SMS_MAX_LENGTH:
        body = body[:SMS_MAX_LENGTH]

    client = import_module("twilio.rest").Client(account_sid, auth_token)
    retryable_tokens = ("timeout", "temporarily", "rate", "429", "502", "503", "connection")

    for attempt in range(3):
        try:
            message = client.messages.create(body=body, from_=from_number, to=to_number)
            return message.sid, True
        except Exception as exc:
            if attempt >= 2:
                raise
            if not any(token in str(exc).lower() for token in retryable_tokens):
                raise
            time.sleep(0.6 * (attempt + 1))

TEMPLATES = {
    "ticket.purchased":     ("Your ticket is confirmed!", "You have successfully purchased ticket {ticketId} for {concertName}. Seat: {seatNumber}."),
    "ticket.resale.listed": ("Your ticket is listed for resale", "Ticket {ticketId} for {concertName} has been listed at {resalePrice} {currency}."),
    "ticket.resale.sold":   ("Your ticket has been sold!", "Ticket {ticketId} has been sold. Payout will be processed shortly."),
    "concert.cancelled":    ("Concert Cancelled — Refund Issued", "We regret to inform you that {concertName} has been cancelled. A full refund of {amount} {currency} will be processed."),
    "queue.window.granted": ("It's your turn!", "Your purchase window for {concertName} is now open. You have 10 minutes to complete your purchase."),
    "queue.window.expired": ("Purchase window expired", "Your purchase window has expired. Please rejoin the queue to try again."),
}

def handle_event(event_type, payload):
    data = payload.get("data", payload)
    user_id = payload.get("userId", data.get("userId", "UNKNOWN"))
    channel = str(payload.get("channel", "EMAIL")).upper()
    tmpl = TEMPLATES.get(event_type, ("Notification", str(data)))
    subject = tmpl[0]
    try: body = tmpl[1].format(**data)
    except KeyError: body = tmpl[1]
    if channel == "SMS":
        try:
            recipient = resolve_sms_recipient(payload, data, user_id)
            ext_id, ok = send_sms(recipient, body)
            subject = None
        except Exception as e:
            print(f"[NOTIFICATION] SMS failed for {event_type}: {e}")
            ext_id, ok = None, False
    else:
        ext_id, ok = send_email(user_id, subject, body)
    status = "SENT" if ok else "FAILED"
    notif_id = f"NOTIF-{uuid.uuid4().hex[:8].upper()}"
    db = get_db(); cur = db.cursor()
    cur.execute("""INSERT INTO notification_log
        (notificationId,userId,eventType,channel,subject,body,status,refId,externalMsgId,retryCount,sentAt)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (notif_id, user_id, event_type, channel, subject, body, status,
         data.get("ticketId", data.get("concertId")), ext_id,
         0 if ok else 1, datetime.utcnow() if ok else None))
    db.commit(); cur.close(); db.close()


ensure_schema()

def start_consumer():
    """Background thread: consumes all messages from ctms_topic."""
    try:
        creds = pika.PlainCredentials(os.environ.get("RABBITMQ_USER","ctms"),
                                      os.environ.get("RABBITMQ_PASSWORD","ctms_pass"))
        params = pika.ConnectionParameters(host=os.environ.get("RABBITMQ_HOST","localhost"),
                                           credentials=creds, heartbeat=60)
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        exchange = os.environ.get("RABBITMQ_EXCHANGE","ctms_topic")
        ch.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
        q = ch.queue_declare(queue="notification_all", durable=True)
        ch.queue_bind(exchange=exchange, queue="notification_all", routing_key="#")
        def callback(ch, method, props, body):
            try:
                payload = json.loads(body)
                handle_event(method.routing_key, payload)
            except Exception as e:
                print(f"[NOTIFICATION] Error handling event: {e}")
        ch.basic_consume(queue="notification_all", on_message_callback=callback, auto_ack=True)
        ch.start_consuming()
    except Exception as e:
        print(f"[NOTIFICATION] RabbitMQ consumer failed: {e}")

# REST endpoints (admin/monitoring)
@app.route("/notification/v1/notification/<notif_id>", methods=["GET"])
def get_notification(notif_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM notification_log WHERE notificationId=%s", (notif_id,))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("NOT_FOUND", "Notification not found", 404)
    return jsonify(row)

@app.route("/notification/v1/notification/user/<user_id>", methods=["GET"])
def get_by_user(user_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM notification_log WHERE userId=%s ORDER BY createdAt DESC", (user_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"userId": user_id, "notifications": rows})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "notification"})

if __name__ == "__main__":
    t = threading.Thread(target=start_consumer, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5006)), debug=False)
