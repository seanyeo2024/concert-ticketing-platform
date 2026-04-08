"""
Notification Service — Atomic Microservice
Port: 5006
DB:   notification_db (MySQL)
Consumes: RabbitMQ topic exchange (all ctms_topic routing keys)
External: Twilio / SendGrid
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import html as html_lib
import mysql.connector, os, uuid, json, threading
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
import smtplib
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
EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
SMS_MAX_LENGTH = 320


def is_e164_phone_number(value):
    return isinstance(value, str) and bool(E164_PATTERN.fullmatch(value.strip()))


def is_email_address(value):
    return isinstance(value, str) and bool(EMAIL_PATTERN.fullmatch(value.strip()))


def resolve_sms_recipient(payload, data, user_id):
    for candidate in (
        payload.get("phoneNumber"),
        payload.get("toNumber"),
        data.get("phoneNumber"),
        data.get("toNumber"),
    ):
        if is_e164_phone_number(candidate):
            return candidate.strip()

    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT userId, phoneE164, smsOptIn FROM user_contact WHERE userId=%s",
            (user_id,),
        )
        contact = cur.fetchone()
    finally:
        cur.close()
        db.close()

    if not contact:
        raise ValueError(f"No contact record found for user {user_id}")
    if not contact.get("smsOptIn"):
        raise ValueError(f"User {user_id} has not opted in to SMS notifications")
    if not is_e164_phone_number(contact.get("phoneE164")):
        raise ValueError(f"User {user_id} does not have a valid E.164 phone number")
    return contact["phoneE164"].strip()


def resolve_email_recipient(payload, data, user_id):
    for candidate in (
        payload.get("email"),
        payload.get("emailAddress"),
        payload.get("contactEmail"),
        data.get("email"),
        data.get("emailAddress"),
        data.get("contactEmail"),
    ):
        if is_email_address(candidate):
            return candidate.strip()

    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT userId, email FROM user_contact WHERE userId=%s",
            (user_id,),
        )
        contact = cur.fetchone()
    finally:
        cur.close()
        db.close()

    if not contact:
        raise ValueError(f"No contact record found for user {user_id}")
    if not is_email_address(contact.get("email")):
        raise ValueError(f"User {user_id} does not have a valid email address")
    return contact["email"].strip()


def extract_inline_qr_image(qr_image_url):
    if not isinstance(qr_image_url, str):
        return None
    prefix = "data:image/png;base64,"
    value = qr_image_url.strip()
    if not value.lower().startswith(prefix):
        return None
    try:
        return base64.b64decode(value[len(prefix):])
    except Exception:
        return None


def build_email_html(subject, body, data, qr_cid=None):
    concert_name = html_lib.escape(str(data.get("concertName") or data.get("concert") or data.get("name") or "").strip())
    seat_number = html_lib.escape(str(data.get("seatNumber") or "").strip())
    ticket_id = html_lib.escape(str(data.get("ticketId") or "").strip())
    qr_data = html_lib.escape(str(data.get("qrData") or "").strip())
    body_text = html_lib.escape((body or "").strip()).replace("\n", "<br/>")

    subtitle_parts = []
    if concert_name:
        subtitle_parts.append(concert_name)
    if seat_number:
        subtitle_parts.append(f"Seat {seat_number}")
    if ticket_id:
        subtitle_parts.append(f"Ticket {ticket_id}")
    subtitle = " &middot; ".join(subtitle_parts)

    qr_section = ""
    if qr_data:
        qr_image_html = ""
        if qr_cid:
            qr_image_html = f'<img src="cid:{qr_cid[1:-1]}" alt="Ticket QR" style="width:180px;height:180px;border-radius:14px;border:2px solid rgba(17,17,17,0.08);background:#fff;display:block;margin:0 auto 12px"/>'
        qr_section = f'''
          <div style="margin-top:24px;padding:22px;border:1px solid rgba(17,17,17,0.10);border-radius:24px;background:#faf7f1;text-align:center">
            <div style="font-family:Georgia, 'Times New Roman', serif;font-size:30px;line-height:1.1;font-weight:700;color:#111;margin-bottom:8px">Your Ticket QR</div>
            <div style="font-size:15px;line-height:1.5;color:#666;margin-bottom:18px">{subtitle or 'Ticket ready for scanning'}</div>
            <div style="display:inline-block;padding:18px 18px 14px;border-radius:20px;background:#fff;border:1px solid rgba(17,17,17,0.08);box-shadow:0 6px 24px rgba(17,17,17,0.06);margin-bottom:16px">
              {qr_image_html}
              <div style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;font-weight:800;color:#31c7b1">Valid QR Ready</div>
            </div>
            <div style="text-align:left;background:#fff;border:1px solid rgba(17,17,17,0.08);border-radius:18px;padding:14px 16px;margin:0 auto 14px;max-width:520px">
              <div style="font-size:11px;letter-spacing:0.10em;text-transform:uppercase;color:#888;margin-bottom:8px">QR Data</div>
              <div style="font-size:13px;line-height:1.6;color:#444;word-break:break-all;font-family:Courier New, monospace">{qr_data}</div>
            </div>
            <div style="font-size:13px;line-height:1.6;color:#777">Use this at the venue entrance for scanning.</div>
          </div>
        '''

    return f'''
      <html>
        <body style="margin:0;padding:0;background:#f4f1ea;color:#111;font-family:Arial, Helvetica, sans-serif">
          <div style="max-width:680px;margin:0 auto;padding:32px 16px 40px">
            <div style="background:#fffaf2;border:1px solid rgba(17,17,17,0.08);border-radius:28px;padding:28px 24px 30px;box-shadow:0 20px 48px rgba(17,17,17,0.08)">
              <div style="text-align:center;font-family:Georgia, 'Times New Roman', serif;font-size:24px;font-weight:700;margin-bottom:18px">Solstitix</div>
              <div style="font-size:22px;line-height:1.25;font-weight:700;text-align:center;margin-bottom:12px">{html_lib.escape(subject or 'Notification')}</div>
              <div style="font-size:15px;line-height:1.7;color:#333;text-align:center;margin:0 auto 10px;max-width:560px">{body_text}</div>
              {qr_section}
            </div>
          </div>
        </body>
      </html>
    '''


def ensure_schema():
    db = get_db()
    cur = db.cursor()
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
    db.commit()
    cur.close()
    db.close()

def send_email(to_user, subject, body, data=None):
    """Send an HTML email with an inline QR image when available."""
    data = data or {}
    to_email = (to_user or "").strip()
    if not is_email_address(to_email):
        raise ValueError("Email recipient must be a valid email address")

    provider = (os.environ.get("EMAIL_PROVIDER") or "gmail_smtp").strip().lower()
    allow_stub = (os.environ.get("EMAIL_ALLOW_STUB") or "false").strip().lower() == "true"
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_use_tls = (os.environ.get("SMTP_USE_TLS") or "true").strip().lower() == "true"
    smtp_username = (os.environ.get("SMTP_USERNAME") or "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD") or ""
    from_email = (os.environ.get("SMTP_FROM") or os.environ.get("EMAIL_FROM") or "demo@example.com").strip()

    if provider not in ("gmail_smtp", "smtp"):
        if allow_stub:
            print(f"[EMAIL STUB] To={to_email} Subject={subject}")
            return f"msg_{uuid.uuid4().hex[:8]}", True
        raise RuntimeError(f"Unsupported email provider: {provider}")

    if not smtp_host or not from_email:
        if allow_stub:
            print(f"[EMAIL STUB] To={to_email} Subject={subject}")
            return f"msg_{uuid.uuid4().hex[:8]}", True
        raise RuntimeError("SMTP environment variables are not configured")

    plain_body = (body or "").strip() or (subject or "Solstitix Notification")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message["Message-ID"] = make_msgid(domain="solstitix.local")
    message.set_content(plain_body)

    qr_bytes = extract_inline_qr_image(data.get("qrImageUrl"))
    qr_cid = make_msgid(domain="solstitix.local") if qr_bytes else None
    html_body = build_email_html(subject, plain_body, data, qr_cid=qr_cid)
    message.add_alternative(html_body, subtype="html")
    if qr_bytes and qr_cid:
        message.get_payload()[1].add_related(
            qr_bytes,
            maintype="image",
            subtype="png",
            cid=qr_cid,
            filename="ticket-qr.png",
        )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
        if smtp_use_tls:
            smtp.starttls()
        if smtp_username and smtp_password:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)

    return message["Message-ID"].strip("<>") or f"msg_{uuid.uuid4().hex[:8]}", True

def send_sms(to_number, body):
    """Send an SMS via Twilio."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")

    if not account_sid or not auth_token or not from_number:
        raise RuntimeError("Twilio environment variables are not configured")
    if not is_e164_phone_number(to_number):
        raise ValueError("SMS recipient must be in E.164 format, e.g. +6591234567")
    if not is_e164_phone_number(from_number):
        raise ValueError("TWILIO_FROM_NUMBER must be in E.164 format, e.g. +6591234567")

    body = (body or "").strip()
    if len(body) > SMS_MAX_LENGTH:
        body = body[:SMS_MAX_LENGTH]

    client = import_module("twilio.rest").Client(account_sid, auth_token)
    retryable_tokens = ("timeout", "temporarily", "rate", "429", "502", "503", "connection")
    last_error = None

    for attempt in range(3):
        try:
            message = client.messages.create(
                body=body,
                from_=from_number.strip(),
                to=to_number.strip(),
            )
            return message.sid, True
        except Exception as exc:
            last_error = exc
            error_text = str(exc).lower()
            can_retry = any(token in error_text for token in retryable_tokens)
            if can_retry and attempt < 2:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise

    raise last_error

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
    channel = payload.get("channel", "EMAIL")
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
        try:
            recipient = resolve_email_recipient(payload, data, user_id)
            ext_id, ok = send_email(recipient, subject, body, data=data)
        except Exception as e:
            print(f"[NOTIFICATION] Email failed for {event_type}: {e}")
            ext_id, ok = None, False
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
