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
import smtplib
import math
from urllib.parse import parse_qs, quote, urlparse
from email.message import EmailMessage
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
CONCERT_ID_PATTERN = re.compile(r'^CONC-\d+$', re.IGNORECASE)
SMS_MAX_LENGTH = 1200
FRONTEND_PAGES_BASE_URL = os.environ.get("FRONTEND_PAGES_BASE_URL", "http://localhost:8080/pages")


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
            "SELECT userId, email, phoneE164, smsOptIn FROM user_contact WHERE userId=%s",
            (user_id,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        db.close()


def fetch_concert_meta(concert_id):
    concert_name = concert_id or "N/A"
    concert_dt = None
    configured_url = (os.environ.get("CONCERT_SERVICE_URL", "http://localhost:5000") or "").rstrip("/")
    base_urls = [configured_url, "http://concert:5000", "http://kong:8000", "http://localhost:5000"]
    unique_base_urls = []
    for base in base_urls:
        if base and base not in unique_base_urls:
            unique_base_urls.append(base)

    for base in unique_base_urls:
        try:
            res = import_module("requests").get(f"{base}/concerts/{concert_id}", timeout=5)
            if res.status_code == 200 and isinstance(res.json(), dict):
                data = res.json()
                concert_name = data.get("name") or data.get("concertName") or data.get("title") or concert_name
                concert_dt = data.get("eventDate") or data.get("concertDateTime")
                if concert_name and concert_name != concert_id:
                    break
        except Exception:
            continue
    return {"concertName": concert_name, "concertDateTime": concert_dt}


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


def is_valid_email(value):
    return isinstance(value, str) and bool(EMAIL_PATTERN.fullmatch(value.strip()))


def resolve_email_recipient(payload, data, user_id):
    for candidate in (
        payload.get("toEmail"),
        payload.get("contactEmail"),
        payload.get("email"),
        data.get("toEmail"),
        data.get("contactEmail"),
        data.get("email"),
    ):
        if is_valid_email(candidate):
            return candidate.strip()

    contact = get_user_contact(user_id)
    if contact and is_valid_email(contact.get("email")):
        return contact.get("email").strip()

    raise ValueError(f"No valid email found for user {user_id}")


def persist_contact_hints(payload, data, user_id):
    if not user_id or user_id == "UNKNOWN":
        return

    hinted_email = None
    for candidate in (
        payload.get("toEmail"),
        payload.get("contactEmail"),
        payload.get("email"),
        data.get("toEmail"),
        data.get("contactEmail"),
        data.get("email"),
    ):
        if is_valid_email(candidate):
            hinted_email = candidate.strip()
            break

    hinted_phone = None
    for candidate in (
        payload.get("phoneNumber"),
        payload.get("contactPhone"),
        payload.get("toNumber"),
        data.get("phoneNumber"),
        data.get("contactPhone"),
        data.get("toNumber"),
    ):
        normalized = normalize_phone(candidate)
        if normalized:
            hinted_phone = normalized
            break

    if not hinted_email and not hinted_phone:
        return

    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT userId FROM user_contact WHERE userId=%s",
            (user_id,),
        )
        existing = cur.fetchone()

        # Profile Settings is the source of truth for saved contact data.
        # Do not overwrite existing records from transactional inputs.
        if existing:
            return

        if hinted_phone:
            sms_opt_in = 1 if hinted_phone else 0
            cur.execute(
                """
                INSERT INTO user_contact (userId, email, phoneE164, smsOptIn)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, hinted_email, hinted_phone, sms_opt_in),
            )
            db.commit()
    except Exception as e:
        print(f"[NOTIFICATION] Could not persist contact hints for {user_id}: {e}")
    finally:
        cur.close()
        db.close()


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

def send_email(to_email, subject, body):
    """Send an email via configured provider (Gmail SMTP or SendGrid), else demo stub."""
    provider = (os.environ.get("EMAIL_PROVIDER") or "sendgrid").strip().lower()
    allow_stub = (os.environ.get("EMAIL_ALLOW_STUB") or "false").strip().lower() in ("1", "true", "yes")
    api_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
    from_email = (os.environ.get("EMAIL_FROM") or "demo@example.com").strip()
    subject = (subject or "Solstitix Notification").strip()

    body = (body or "").strip()
    if len(body) > 8000:
        body = body[:8000]

    if provider in ("gmail", "gmail_smtp", "smtp"):
        smtp_host = (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip()
        smtp_port = int((os.environ.get("SMTP_PORT") or "587").strip())
        smtp_use_tls = (os.environ.get("SMTP_USE_TLS") or "true").strip().lower() in ("1", "true", "yes")
        smtp_username = (os.environ.get("SMTP_USERNAME") or "").strip()
        smtp_password = (os.environ.get("SMTP_PASSWORD") or "").strip()
        smtp_from = (os.environ.get("SMTP_FROM") or from_email or smtp_username).strip()

        if not (smtp_host and smtp_username and smtp_password and is_valid_email(to_email)):
            print("[NOTIFICATION] SMTP email not configured or invalid recipient")
            return "smtp_not_configured", False

        try:
            msg = EmailMessage()
            msg["From"] = smtp_from
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                if smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
            return f"smtp_{uuid.uuid4().hex[:8]}", True
        except Exception as e:
            print(f"[NOTIFICATION] SMTP email failed: {e}")
            return "smtp_send_failed", False

    if provider == "sendgrid" and api_key and api_key.lower() not in ("dummy", "changeme"):
        try:
            sg_mod = import_module("sendgrid")
            mail_mod = import_module("sendgrid.helpers.mail")
            msg = mail_mod.Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=subject,
                plain_text_content=body,
            )
            resp = sg_mod.SendGridAPIClient(api_key).send(msg)
            if 200 <= int(getattr(resp, "status_code", 0)) < 300:
                return f"sg_{uuid.uuid4().hex[:8]}", True
            raise RuntimeError(f"SendGrid returned status {getattr(resp, 'status_code', 'unknown')}")
        except Exception as e:
            print(f"[NOTIFICATION] SendGrid email failed: {e}")

    if allow_stub:
        print(f"[EMAIL STUB] To={to_email} Subject={subject}")
        return f"msg_{uuid.uuid4().hex[:8]}", True

    print("[NOTIFICATION] Email send failed and stub mode disabled")
    return "email_send_failed", False

def send_sms(to_number, body):
    """Send an SMS via Twilio."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = normalize_phone(os.environ.get("TWILIO_FROM_NUMBER") or os.environ.get("WILIO_FROM_NUMBER"))

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


def send_whatsapp(to_number, body):
    """Send a WhatsApp message via Twilio sandbox/number."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = normalize_phone(os.environ.get("TWILIO_WHATSAPP_FROM_NUMBER", "+14155238886"))

    if not account_sid or not auth_token or not from_number:
        raise RuntimeError("Twilio WhatsApp environment variables are not configured")

    to_number = normalize_phone(to_number)
    if not to_number:
        raise ValueError("WhatsApp recipient must be in E.164 format, e.g. +6591234567")

    body = (body or "").strip()
    if len(body) > SMS_MAX_LENGTH:
        body = body[:SMS_MAX_LENGTH]

    client = import_module("twilio.rest").Client(account_sid, auth_token)
    message = client.messages.create(
        body=body,
        from_=f"whatsapp:{from_number}",
        to=f"whatsapp:{to_number}",
    )
    return message.sid, True

TEMPLATES = {
    "ticket.resale.listed": ("Your ticket is listed for resale", "Ticket {ticketId} for {concertName} has been listed at {resalePrice} {currency}."),
    "concert.cancelled":    ("Concert Cancelled — Refund Issued", "We regret to inform you that {concertName} has been cancelled. A full refund will be processed."),
    "queue.window.granted": ("It's your turn!", "Your purchase window for {concertName} is now open. You have {windowDurationMinutes} minutes to complete your purchase."),
    "queue.window.expired": ("Purchase window expired", "Your purchase window has expired. Please rejoin the queue to try again."),
}


def _value(data, key, fallback="N/A"):
    raw = data.get(key)
    if raw is None:
        return fallback
    text = str(raw).strip()
    return text if text else fallback


def _money(data, primary_key="amount", fallback_key="resalePrice"):
    amount = data.get(primary_key)
    if amount in (None, ""):
        amount = data.get(fallback_key)
    currency = _value(data, "currency", "SGD")
    if amount in (None, ""):
        return f"{currency} N/A"
    try:
        return f"{currency} {float(amount):.2f}"
    except Exception:
        return f"{currency} {amount}"


def _is_blank(value):
    return value is None or str(value).strip() in ("", "N/A")


def _looks_like_concert_id(value):
    return isinstance(value, str) and bool(CONCERT_ID_PATTERN.fullmatch(value.strip()))


def _resolve_window_minutes(payload, data):
    for candidate in (
        data.get("windowDurationMinutes"),
        payload.get("windowDurationMinutes"),
    ):
        try:
            if candidate is not None:
                value = int(candidate)
                if value > 0:
                    return value
        except Exception:
            pass

    for candidate in (
        data.get("windowDurationSeconds"),
        payload.get("windowDurationSeconds"),
    ):
        try:
            if candidate is not None:
                value = int(candidate)
                if value > 0:
                    return max(1, math.ceil(value / 60))
        except Exception:
            pass

    try:
        expires_at = data.get("windowExpiresAt")
        event_ts = data.get("timestamp") or payload.get("timestamp")
        if expires_at and event_ts:
            expires_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            event_dt = datetime.fromisoformat(str(event_ts).replace("Z", "+00:00"))
            diff_seconds = max(0, int((expires_dt - event_dt).total_seconds()))
            if diff_seconds:
                return max(1, math.ceil(diff_seconds / 60))
    except Exception:
        pass

    return max(1, math.ceil(int(os.environ.get("PURCHASE_WINDOW_SECONDS", "600")) / 60))


def enrich_concert_fields(payload, data):
    concert_id = data.get("concertId") or payload.get("concertId")
    if not concert_id:
        return

    needs_name = _is_blank(data.get("concertName")) or _looks_like_concert_id(data.get("concertName"))
    needs_dt = _is_blank(data.get("concertDateTime"))
    if not needs_name and not needs_dt:
        return

    meta = fetch_concert_meta(concert_id)
    if needs_name:
        data["concertName"] = meta.get("concertName") or concert_id
    if needs_dt:
        data["concertDateTime"] = meta.get("concertDateTime")


def _qr_link(data):
    owner_id = _value(data, "userId", _value(data, "buyerId", _value(data, "ownerId", "")))

    def _build_login_ticket_link(ticket_id, concert_id, required_owner=""):
        next_page = quote(f"my-tickets.html?refreshTicket={ticket_id}&refreshConcert={concert_id}", safe="")
        link = f"{FRONTEND_PAGES_BASE_URL}/login.html?next={next_page}"
        if required_owner:
            link += f"&requiredOwner={quote(str(required_owner), safe='')}"
        return link

    explicit = data.get("qrCodeLink")
    if isinstance(explicit, str) and explicit.strip():
        raw_link = explicit.strip()
        if "/login.html?" in raw_link:
            return raw_link
        parsed = urlparse(raw_link)
        params = parse_qs(parsed.query)
        ticket_id = (params.get("refreshTicket", [None])[0] or _value(data, "ticketId", "")).strip()
        concert_id = (params.get("refreshConcert", [None])[0] or _value(data, "concertId", "")).strip()
        if ticket_id and concert_id:
            return _build_login_ticket_link(ticket_id, concert_id, owner_id)
    ticket_id = _value(data, "ticketId", "")
    concert_id = _value(data, "concertId", "")
    if ticket_id and concert_id:
        return _build_login_ticket_link(ticket_id, concert_id, owner_id)
    return f"{FRONTEND_PAGES_BASE_URL}/login.html"


def compose_message(event_type, data):
    if event_type == "ticket.purchased":
        purchase_type = str(data.get("purchaseType", "PRIMARY")).upper()
        subject = "Your ticket is confirmed!"
        if purchase_type == "RESALE":
            body = (
                "🎟️ 🎉 Success! You've secured your resale ticket\n\n"
                "Solstitix is delighted to bring you one step closer to your concert experience ✨\n\n"
                f"Concert: {_value(data, 'concertName')}\n"
                f"Ticket ID: {_value(data, 'ticketId')}\n"
                f"Seat: {_value(data, 'seatNumber')}\n"
                f"Date & Time: {_value(data, 'concertDateTime', _value(data, 'eventDate'))}\n\n"
                f"💰 Price Paid: {_money(data)}\n"
                f"🕒 Purchased At: {_value(data, 'purchaseDateTime', _value(data, 'timestamp'))}\n\n"
                f"📲 Click here to view your ticket: {_qr_link(data)}\n\n"
                "This is going to be an amazing experience — enjoy every moment 🎶"
            )
            return subject, body

        body = (
            "🎟️ 🎉 You're in! Your ticket is confirmed\n\n"
            "Solstitix is delighted to bring you one step closer to your concert experience ✨\n\n"
            f"Concert: {_value(data, 'concertName')}\n"
            f"Ticket ID: {_value(data, 'ticketId')}\n"
            f"Seat: {_value(data, 'seatNumber')}\n"
            f"Date & Time: {_value(data, 'concertDateTime', _value(data, 'eventDate'))}\n\n"
            f"💰 Price Paid: {_money(data)}\n"
            f"🕒 Purchased At: {_value(data, 'purchaseDateTime', _value(data, 'timestamp'))}\n\n"
            f"📲 Click here to view your ticket: {_qr_link(data)}\n\n"
            "Get ready for an unforgettable night — we'll see you there 💫"
        )
        return subject, body

    if event_type == "ticket.resale.sold":
        subject = "Your ticket has been sold!"
        body = (
            "💸 ✅ Your ticket has been successfully sold\n\n"
            "Solstitix is pleased to have supported a smooth and secure resale.\n\n"
            f"Concert: {_value(data, 'concertName')}\n"
            f"Ticket ID: {_value(data, 'ticketId')}\n"
            f"Seat: {_value(data, 'seatNumber')}\n"
            f"Date & Time: {_value(data, 'concertDateTime', _value(data, 'eventDate'))}\n\n"
            f"💰 Sold For: {_money(data, primary_key='resalePrice', fallback_key='amount')}\n"
            f"🕒 Sold At: {_value(data, 'saleDateTime', _value(data, 'timestamp'))}\n\n"
            "💳 Your refund will be processed to your original payment method within 3–5 working days.\n\n"
            "Thank you for using Solstitix."
        )
        return subject, body

    if event_type == "concert.cancelled":
        subject = "⚠️ Update: Your concert has been cancelled"
        refund_value = _money(data, primary_key='price', fallback_key='amount')
        body = (
            "⚠️ Update: Your concert has been cancelled\n\n"
            f"We’re truly sorry — {_value(data, 'concertName')} will no longer be taking place.\n\n"
            "Solstitix sincerely regrets the disappointment caused and remains committed to supporting you.\n\n"
            f"📌 Reason: {_value(data, 'cancellationReason', _value(data, 'reason'))}\n\n"
            f"Ticket ID: {_value(data, 'ticketId')}\n"
            f"Seat: {_value(data, 'seatNumber')}\n"
            f"Original Date & Time: {_value(data, 'concertDateTime', _value(data, 'eventDate'))}\n\n"
            f"💰 Original Price: {refund_value}\n"
            f"🕒 Purchased At: {_value(data, 'purchaseDateTime', 'N/A')}\n"
            f"🕒 Cancelled At: {_value(data, 'cancelledAt', _value(data, 'timestamp'))}\n\n"
            f"💳 A full refund of {refund_value} will be processed to your original payment method within 3–5 working days.\n\n"
            "If you have any questions or need assistance, please reach out to us:\n"
            "📞 +65 9876 5432\n"
            "📧 solstitixcustomerservice@gmail.com\n\n"
            "We truly appreciate your understanding 🤍"
        )
        return subject, body

    tmpl = TEMPLATES.get(event_type, ("Notification", str(data)))
    subject = tmpl[0]
    try:
        body = tmpl[1].format(**data)
    except KeyError:
        body = tmpl[1]
    return subject, body


def compose_sms_message(event_type, data):
    footer = "Check your gmail inbox for more details."
    purchase_type = str(data.get("purchaseType", "PRIMARY")).upper()
    concert_name = _value(data, "concertName")
    ticket_id = _value(data, "ticketId")
    seat_number = _value(data, "seatNumber")
    concert_time = _value(data, "concertDateTime", _value(data, "eventDate"))
    purchase_dt = _value(data, "purchaseDateTime", _value(data, "timestamp"))

    if event_type == "ticket.purchased":
        label = "Resale purchase confirmed" if purchase_type == "RESALE" else "Ticket purchase confirmed"
        price_label = "Price paid" if purchase_type == "RESALE" else "Transaction price"
        price_value = _money(data)
        return (
            f"{label}\n"
            f"Concert: {concert_name}\n"
            f"Ticket ID: {ticket_id}\n"
            f"Seat: {seat_number}\n"
            f"Date & Time: {concert_time}\n"
            f"{price_label}: {price_value}\n"
            f"Purchased At: {purchase_dt}\n"
            f"{footer}"
        )

    if event_type == "ticket.resale.sold":
        return (
            "Resale sale confirmed\n"
            f"Concert: {concert_name}\n"
            f"Ticket ID: {ticket_id}\n"
            f"Seat: {seat_number}\n"
            f"Date & Time: {concert_time}\n"
            f"Sold For: {_money(data, primary_key='resalePrice', fallback_key='amount')}\n"
            f"Sold At: {_value(data, 'saleDateTime', _value(data, 'timestamp'))}\n"
            f"{footer}"
        )

    if event_type == "ticket.resale.listed":
        return (
            "Ticket listed for resale\n"
            f"Concert: {concert_name}\n"
            f"Ticket ID: {ticket_id}\n"
            f"Seat: {seat_number}\n"
            f"Listing Price: {_money(data, primary_key='resalePrice', fallback_key='amount')}\n"
            f"{footer}"
        )

    if event_type == "concert.cancelled":
        refund_amount = str(_value(data, 'price', _value(data, 'amount'))).lstrip('$').strip()
        concert_short = str(concert_name)[:40]
        ticket_short = str(ticket_id)[:24]
        seat_short = str(seat_number)[:18]
        return (
            f"Solstitix update: {concert_short} cancelled. "
            f"Ticket {ticket_short}, Seat {seat_short}. "
            f"Refund SGD {refund_amount} in 3-5 working days. "
            f"Check gmail for details."
        )

    if event_type == "queue.window.granted":
        window_minutes = _value(data, "windowDurationMinutes", "N/A")
        return (
            "Your purchase window is open\n"
            f"Concert: {concert_name}\n"
            f"Window: {window_minutes} minutes\n"
            f"{footer}"
        )

    if event_type == "queue.window.expired":
        return (
            "Purchase window expired\n"
            f"Concert: {concert_name}\n"
            f"{footer}"
        )

    return (
        f"Notification\n"
        f"Concert: {concert_name}\n"
        f"Ticket ID: {ticket_id}\n"
        f"{footer}"
    )


def log_notification(user_id, event_type, channel, subject, body, status, ref_id, external_msg_id, ok):
    notif_id = f"NOTIF-{uuid.uuid4().hex[:8].upper()}"
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""INSERT INTO notification_log
            (notificationId,userId,eventType,channel,subject,body,status,refId,externalMsgId,retryCount,sentAt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (notif_id, user_id, event_type, channel, subject, body, status,
             ref_id, external_msg_id, 0 if ok else 1, datetime.utcnow() if ok else None))
        db.commit()
    finally:
        cur.close()
        db.close()


def deliver_email(event_type, payload, data, user_id, subject, body):
    try:
        recipient_email = resolve_email_recipient(payload, data, user_id)
    except Exception as e:
        print(f"[NOTIFICATION] Email recipient unavailable for {event_type}: {e}")
        return None

    ext_id, ok = send_email(recipient_email, subject, body)
    status = "SENT_EMAIL_FORCED" if ok else "FAILED"
    log_notification(
        user_id,
        event_type,
        "EMAIL",
        subject,
        body,
        status,
        data.get("ticketId", data.get("concertId")),
        ext_id,
        ok,
    )
    return {"channel": "EMAIL", "recipient": recipient_email, "ok": ok, "status": status, "externalMsgId": ext_id}


def deliver_sms(event_type, payload, data, user_id, subject, body):
    prefer_whatsapp = os.environ.get("USE_WHATSAPP_SANDBOX_FOR_SMS", "false").strip().lower() in ("1", "true", "yes")
    try:
        recipient_phone = resolve_sms_recipient(payload, data, user_id)
    except Exception as e:
        print(f"[NOTIFICATION] SMS recipient unavailable for {event_type}: {e}")
        return None

    sms_body = compose_sms_message(event_type, data)

    try:
        if prefer_whatsapp:
            ext_id, ok = send_whatsapp(recipient_phone, sms_body)
            channel = "WHATSAPP"
            status = "SENT_WHATSAPP" if ok else "FAILED"
        else:
            ext_id, ok = send_sms(recipient_phone, sms_body)
            channel = "SMS"
            status = "SENT" if ok else "FAILED"
    except Exception as e:
        print(f"[NOTIFICATION] SMS send failed for {event_type}: {e}")
        ext_id, ok = None, False
        channel = "WHATSAPP" if prefer_whatsapp else "SMS"
        status = "FAILED"

    log_notification(
        user_id,
        event_type,
        channel,
        None,
        sms_body,
        status,
        data.get("ticketId", data.get("concertId")),
        ext_id,
        ok,
    )
    return {"channel": channel, "recipient": recipient_phone, "ok": ok, "status": status, "externalMsgId": ext_id}

def handle_event(event_type, payload):
    data = payload.get("data", payload)
    if isinstance(data, dict) and "timestamp" not in data and payload.get("timestamp"):
        data["timestamp"] = payload.get("timestamp")
    if isinstance(data, dict) and "userId" not in data and payload.get("userId"):
        data["userId"] = payload.get("userId")
    if isinstance(data, dict):
        enrich_concert_fields(payload, data)
        if event_type == "queue.window.granted":
            data["windowDurationMinutes"] = _resolve_window_minutes(payload, data)
    user_id = payload.get("userId", data.get("userId", "UNKNOWN"))
    persist_contact_hints(payload, data, user_id)
    subject, body = compose_message(event_type, data)

    deliver_email(event_type, payload, data, user_id, subject, body)
    deliver_sms(event_type, payload, data, user_id, subject, body)


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


@app.route("/notification/v1/contact/<user_id>", methods=["GET"])
def get_contact(user_id):
    contact = get_user_contact(user_id)
    if not contact:
        return jsonify({"userId": user_id, "email": None, "phoneNumber": None, "smsOptIn": 0})
    return jsonify({
        "userId": user_id,
        "email": contact.get("email"),
        "phoneNumber": contact.get("phoneE164"),
        "smsOptIn": int(contact.get("smsOptIn") or 0),
    })


@app.route("/notification/v1/contact/<user_id>", methods=["PUT"])
def upsert_contact(user_id):
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or payload.get("contactEmail") or "").strip()
    phone = normalize_phone(
        payload.get("phoneNumber") or payload.get("contactPhone") or payload.get("toNumber")
    )
    sms_opt_in_raw = payload.get("smsOptIn", True)
    sms_opt_in = 1 if str(sms_opt_in_raw).lower() in ("1", "true", "yes", "on") else 0

    if not is_valid_email(email):
        return err("INVALID_EMAIL", "A valid email is required")
    if not phone:
        return err("INVALID_PHONE", "A valid E.164 phoneNumber is required (e.g. +6591234567)")

    db = get_db(); cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO user_contact (userId, email, phoneE164, smsOptIn)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              email=VALUES(email),
              phoneE164=VALUES(phoneE164),
              smsOptIn=VALUES(smsOptIn)
            """,
            (user_id, email, phone, sms_opt_in),
        )
        db.commit()
    finally:
        cur.close(); db.close()

    return jsonify({"userId": user_id, "email": email, "phoneNumber": phone, "smsOptIn": sms_opt_in})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "notification"})

if __name__ == "__main__":
    t = threading.Thread(target=start_consumer, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5006)), debug=False)
