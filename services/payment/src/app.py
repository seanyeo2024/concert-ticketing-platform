"""
Payment Service - Atomic Microservice
Port: 5004
DB:   payment_db (MySQL)
External: Stripe API
Handles: PURCHASE, RESALE_PURCHASE, REFUND
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import uuid

from flask import Flask, jsonify, request
from flask_cors import CORS
import mysql.connector
import stripe

app = Flask(__name__)
CORS(app)

SERVICE_NAME = "payment"
MAX_AMOUNT = Decimal("100000.00")
SUPPORTED_PAYMENT_TYPES = {"PURCHASE", "RESALE_PURCHASE"}
SUPPORTED_CURRENCIES = {"SGD", "USD", "EUR", "GBP", "AUD"}
TEST_PAYMENT_METHOD_MAP = {
    "tok_simulated": "pm_card_visa",
    "tok_visa_simulated": "pm_card_visa",
    "tok_visa": "pm_card_visa",
    "pm_card_visa": "pm_card_visa",
    "pm_card_visaDebit": "pm_card_visaDebit",
    "pm_card_chargeDeclined": "pm_card_chargeDeclined",
    "pm_card_insufficientFunds": "pm_card_insufficientFunds",
    "pm_card_authenticationRequired": "pm_card_authenticationRequired",
}

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


def utcnow_iso():
    return datetime.utcnow().isoformat()


def err(code, message, status=400, **details):
    payload = {
        "error": {
            "code": code,
            "message": message,
            "service": SERVICE_NAME,
            "timestamp": utcnow_iso(),
        }
    }
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        database=os.environ.get("MYSQL_DATABASE", "payment_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )


def ensure_schema():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_record (
          paymentId VARCHAR(36) PRIMARY KEY,
          userId VARCHAR(36) NOT NULL,
          ticketId VARCHAR(36) NOT NULL,
          concertId VARCHAR(36) NOT NULL,
          type VARCHAR(20) NOT NULL,
          amount DECIMAL(10,2) NOT NULL,
          currency VARCHAR(3) NOT NULL,
          status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
          stripePaymentIntentId VARCHAR(100) NULL,
          stripeRefundId VARCHAR(100) NULL,
          originalPaymentId VARCHAR(36) NULL,
          reason VARCHAR(200) NULL,
          createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          KEY idx_payment_concert_type (concertId, type),
          KEY idx_payment_user (userId),
          KEY idx_payment_status (status)
        )
        """
    )
    db.commit()
    cur.close()
    db.close()


def parse_amount(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("amount must be a valid number")
    if amount <= 0:
        raise ValueError("amount must be > 0")
    if amount > MAX_AMOUNT:
        raise ValueError(f"amount cannot exceed {MAX_AMOUNT}")
    return amount


def to_minor_units(amount):
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalize_currency(value):
    currency = str(value or "").strip().upper()
    if not currency:
        raise ValueError("currency is required")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency {currency}")
    return currency


def resolve_payment_method(payload):
    candidate = (
        payload.get("stripePaymentMethodId")
        or payload.get("paymentMethodId")
        or payload.get("stripeToken")
        or "tok_simulated"
    )
    candidate = str(candidate).strip()
    if not candidate:
        return TEST_PAYMENT_METHOD_MAP["tok_simulated"]
    return TEST_PAYMENT_METHOD_MAP.get(candidate, candidate)


def stripe_charge(amount, currency, payment_method_id, metadata):
    if not stripe.api_key:
        return None, False, "Stripe is not configured. Missing STRIPE_SECRET_KEY."

    try:
        intent = stripe.PaymentIntent.create(
            amount=to_minor_units(amount),
            currency=currency.lower(),
            payment_method=payment_method_id,
            confirm=True,
            payment_method_types=["card"],
            metadata=metadata,
        )
    except stripe.error.CardError as exc:
        return None, False, exc.user_message or str(exc)
    except stripe.error.StripeError as exc:
        return None, False, str(exc)

    status = getattr(intent, "status", "")
    succeeded = status == "succeeded"
    message = None if succeeded else f"Stripe payment intent status: {status or 'unknown'}"
    return intent, succeeded, message


def stripe_refund(intent_id, amount, metadata):
    if not stripe.api_key:
        return None, False, "Stripe is not configured. Missing STRIPE_SECRET_KEY."
    if not intent_id:
        return None, False, "Original Stripe payment intent is missing"

    try:
        refund = stripe.Refund.create(
            payment_intent=intent_id,
            amount=to_minor_units(amount),
            metadata=metadata,
        )
    except stripe.error.StripeError as exc:
        return None, False, str(exc)

    status = getattr(refund, "status", "")
    succeeded = status in {"succeeded", "pending"}
    message = None if succeeded else f"Stripe refund status: {status or 'unknown'}"
    return refund, succeeded, message


def insert_payment_record(
    payment_id,
    user_id,
    ticket_id,
    concert_id,
    payment_type,
    amount,
    currency,
    status,
    stripe_payment_intent_id=None,
    stripe_refund_id=None,
    original_payment_id=None,
    reason=None,
):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO payment_record
            (paymentId, userId, ticketId, concertId, type, amount, currency, status,
             stripePaymentIntentId, stripeRefundId, originalPaymentId, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payment_id,
            user_id,
            ticket_id,
            concert_id,
            payment_type,
            str(amount),
            currency,
            status,
            stripe_payment_intent_id,
            stripe_refund_id,
            original_payment_id,
            reason,
        ),
    )
    db.commit()
    cur.close()
    db.close()


ensure_schema()


@app.route("/payment/v1/config", methods=["GET"])
def payment_config():
    return jsonify(
        {
            "service": SERVICE_NAME,
            "port": int(os.environ.get("PORT", 5004)),
            "stripeConfigured": bool(stripe.api_key),
            "frontendMode": "server-side-test-payment-method",
            "supportedTestPaymentMethods": sorted(TEST_PAYMENT_METHOD_MAP.values()),
        }
    )


@app.route("/payment/v1/payment", methods=["POST"])
def create_payment():
    data = request.get_json() or {}
    required = ["userId", "ticketId", "amount", "currency", "type"]
    if not all(data.get(key) not in (None, "") for key in required):
        return err("MISSING_FIELDS", f"Required: {required}")

    try:
        amount = parse_amount(data["amount"])
        currency = normalize_currency(data["currency"])
    except ValueError as exc:
        return err("INVALID_PAYMENT_INPUT", str(exc), 400)

    payment_type = str(data.get("type", "")).upper()
    if payment_type not in SUPPORTED_PAYMENT_TYPES:
        return err("INVALID_TYPE", "type must be PURCHASE or RESALE_PURCHASE")

    payment_method_id = resolve_payment_method(data)
    pay_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
    metadata = {
        "paymentId": pay_id,
        "userId": str(data["userId"]),
        "ticketId": str(data["ticketId"]),
        "concertId": str(data.get("concertId", "")),
        "type": payment_type,
    }

    intent, ok, failure_message = stripe_charge(amount, currency, payment_method_id, metadata)
    status = "SUCCESS" if ok else "FAILED"
    intent_id = getattr(intent, "id", None) if intent else None

    insert_payment_record(
        payment_id=pay_id,
        user_id=str(data["userId"]),
        ticket_id=str(data["ticketId"]),
        concert_id=str(data.get("concertId", "")),
        payment_type=payment_type,
        amount=amount,
        currency=currency,
        status=status,
        stripe_payment_intent_id=intent_id,
    )

    if not ok:
        return err(
            "PAYMENT_FAILED",
            failure_message or "Card charge declined by Stripe",
            402,
            paymentId=pay_id,
            stripePaymentIntentId=intent_id,
        )

    return (
        jsonify(
            {
                "paymentId": pay_id,
                "status": status,
                "stripePaymentIntentId": intent_id,
                "amount": str(amount),
                "currency": currency,
                "paymentMethodId": payment_method_id,
                "createdAt": utcnow_iso(),
            }
        ),
        201,
    )


@app.route("/payment/v1/payment/refund", methods=["POST"])
def create_refund():
    data = request.get_json() or {}
    required = ["userId", "ticketId", "paymentId", "amount"]
    if not all(data.get(key) not in (None, "") for key in required):
        return err("MISSING_FIELDS", f"Required: {required}")

    try:
        amount = parse_amount(data["amount"])
    except ValueError as exc:
        return err("INVALID_PAYMENT_INPUT", str(exc), 400)

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM payment_record WHERE paymentId=%s", (data["paymentId"],))
    original = cur.fetchone()
    if not original:
        cur.close()
        db.close()
        return err("NOT_FOUND", "Original payment not found", 404)

    cur.execute(
        "SELECT paymentId FROM payment_record WHERE originalPaymentId=%s AND reason=%s",
        (data["paymentId"], data.get("reason")),
    )
    if cur.fetchone():
        cur.close()
        db.close()
        return err("REFUND_EXISTS", "Refund already issued for this payment and reason", 409)

    refund_record_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
    refund, ok, failure_message = stripe_refund(
        original["stripePaymentIntentId"],
        amount,
        {
            "refundPaymentId": refund_record_id,
            "originalPaymentId": str(data["paymentId"]),
            "reason": str(data.get("reason", "")),
        },
    )
    refund_id = getattr(refund, "id", None) if refund else None
    status = "SUCCESS" if ok else "FAILED"

    cur.execute(
        """
        INSERT INTO payment_record
            (paymentId, userId, ticketId, concertId, type, amount, currency, status,
             stripeRefundId, originalPaymentId, reason)
        VALUES (%s, %s, %s, %s, 'REFUND', %s, %s, %s, %s, %s, %s)
        """,
        (
            refund_record_id,
            str(data["userId"]),
            str(data["ticketId"]),
            str(original.get("concertId", "")),
            str(amount),
            str(original["currency"]).upper(),
            status,
            refund_id,
            str(data["paymentId"]),
            data.get("reason"),
        ),
    )
    db.commit()
    cur.close()
    db.close()

    if not ok:
        return err(
            "REFUND_FAILED",
            failure_message or "Refund could not be created in Stripe",
            402,
            paymentId=refund_record_id,
            refundId=refund_id,
        )

    return (
        jsonify(
            {
                "paymentId": refund_record_id,
                "type": "REFUND",
                "status": status,
                "refundId": refund_id,
                "amount": str(amount),
                "currency": str(original["currency"]).upper(),
                "createdAt": utcnow_iso(),
            }
        ),
        201,
    )


@app.route("/payment/v1/payment/<payment_id>", methods=["GET"])
def get_payment(payment_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM payment_record WHERE paymentId=%s", (payment_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    if not row:
        return err("NOT_FOUND", "Payment not found", 404)
    return jsonify(row)


@app.route("/payment/v1/payment/user/<user_id>", methods=["GET"])
def get_by_user(user_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM payment_record WHERE userId=%s ORDER BY createdAt DESC", (user_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return jsonify({"userId": user_id, "payments": rows})


@app.route("/payment/v1/payment/concert/<concert_id>", methods=["GET"])
def get_by_concert(concert_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM payment_record WHERE concertId=%s AND type IN ('PURCHASE', 'RESALE_PURCHASE')",
        (concert_id,),
    )
    rows = cur.fetchall()
    cur.close()
    db.close()
    return jsonify({"concertId": concert_id, "payments": rows})


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "stripeConfigured": bool(stripe.api_key),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5004)), debug=False)
