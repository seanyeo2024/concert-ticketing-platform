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

def send_email(to_user, subject, body):
    """Stub — replace with SendGrid / SMTP call."""
    # TODO: sendgrid.SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(...)
    print(f"[EMAIL STUB] To={to_user} Subject={subject}")
    return f"msg_{uuid.uuid4().hex[:8]}", True

def send_sms(to_user, body):
    """Stub — replace with Twilio call."""
    # TODO: twilio.rest.Client(...).messages.create(...)
    print(f"[SMS STUB] To={to_user} Body={body[:60]}")
    return f"SM{uuid.uuid4().hex[:16]}", True

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
    tmpl = TEMPLATES.get(event_type, ("Notification", str(data)))
    subject = tmpl[0]
    try: body = tmpl[1].format(**data)
    except KeyError: body = tmpl[1]
    ext_id, ok = send_email(user_id, subject, body)
    status = "SENT" if ok else "FAILED"
    notif_id = f"NOTIF-{uuid.uuid4().hex[:8].upper()}"
    db = get_db(); cur = db.cursor()
    cur.execute("""INSERT INTO notification_log
        (notificationId,userId,eventType,channel,subject,body,status,refId,externalMsgId,sentAt)
        VALUES (%s,%s,%s,'EMAIL',%s,%s,%s,%s,%s,%s)""",
        (notif_id, user_id, event_type, subject, body, status,
         data.get("ticketId", data.get("concertId")), ext_id,
         datetime.utcnow() if ok else None))
    db.commit(); cur.close(); db.close()

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
