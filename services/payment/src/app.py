"""
Payment Service — Atomic Microservice
Port: 5004
DB:   payment_db (MySQL)
External: Stripe API
Handles: PURCHASE, RESALE_PURCHASE, REFUND
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
        database=os.environ.get("MYSQL_DATABASE", "payment_db"),
        user=os.environ.get("MYSQL_USER", "ctms_user"),
        password=os.environ.get("MYSQL_PASSWORD", "ctms_pass"),
    )

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "payment", "timestamp": datetime.utcnow().isoformat()}}), status

def stripe_charge(amount, currency, token):
    """
    Call Stripe API to charge the card.
    Replace this stub with actual stripe.PaymentIntent.create() call.
    Returns: (intent_id, success_bool)
    """
    # TODO: import stripe; stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    # intent = stripe.PaymentIntent.create(amount=int(amount*100), currency=currency, payment_method=token, confirm=True)
    return f"pi_SIMULATED_{uuid.uuid4().hex[:16]}", True

def stripe_refund(intent_id, amount):
    """
    Call Stripe API to issue a refund.
    Returns: (refund_id, success_bool)
    """
    # TODO: import stripe; stripe.Refund.create(payment_intent=intent_id, amount=int(amount*100))
    return f"re_SIMULATED_{uuid.uuid4().hex[:16]}", True

# POST /payment/v1/payment  — charge
@app.route("/payment/v1/payment", methods=["POST"])
def create_payment():
    data = request.get_json()
    required = ["userId", "ticketId", "amount", "currency", "type"]
    if not all(k in data for k in required): return err("MISSING_FIELDS", f"Required: {required}")
    intent_id, ok = stripe_charge(data["amount"], data["currency"], data.get("stripeToken", "tok_simulated"))
    status = "SUCCESS" if ok else "FAILED"
    pay_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
    db = get_db(); cur = db.cursor()
    cur.execute("""INSERT INTO payment_record
        (paymentId,userId,ticketId,concertId,type,amount,currency,status,stripePaymentIntentId)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (pay_id, data["userId"], data["ticketId"], data.get("concertId",""),
         data["type"], data["amount"], data["currency"], status, intent_id))
    db.commit(); cur.close(); db.close()
    if not ok: return err("PAYMENT_FAILED", "Card charge declined by Stripe", 402)
    return jsonify({"paymentId": pay_id, "status": status,
                    "stripePaymentIntentId": intent_id, "amount": data["amount"],
                    "currency": data["currency"], "createdAt": datetime.utcnow().isoformat()}), 201

# POST /payment/v1/payment/refund
@app.route("/payment/v1/payment/refund", methods=["POST"])
def create_refund():
    data = request.get_json()
    required = ["userId", "ticketId", "paymentId", "amount"]
    if not all(k in data for k in required): return err("MISSING_FIELDS", f"Required: {required}")
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM payment_record WHERE paymentId=%s", (data["paymentId"],))
    original = cur.fetchone()
    if not original: return err("NOT_FOUND", "Original payment not found", 404)
    refund_id_stripe, ok = stripe_refund(original["stripePaymentIntentId"], data["amount"])
    pay_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
    cur.execute("""INSERT INTO payment_record
        (paymentId,userId,ticketId,concertId,type,amount,currency,status,stripeRefundId,originalPaymentId,reason)
        VALUES (%s,%s,%s,%s,'REFUND',%s,%s,%s,%s,%s,%s)""",
        (pay_id, data["userId"], data["ticketId"], original.get("concertId",""),
         data["amount"], original["currency"], "SUCCESS" if ok else "FAILED",
         refund_id_stripe, data["paymentId"], data.get("reason")))
    db.commit(); cur.close(); db.close()
    return jsonify({"paymentId": pay_id, "type": "REFUND", "status": "SUCCESS",
                    "refundId": refund_id_stripe, "amount": data["amount"],
                    "createdAt": datetime.utcnow().isoformat()}), 201

# GET /payment/v1/payment/<paymentId>
@app.route("/payment/v1/payment/<payment_id>", methods=["GET"])
def get_payment(payment_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM payment_record WHERE paymentId=%s", (payment_id,))
    row = cur.fetchone(); cur.close(); db.close()
    if not row: return err("NOT_FOUND", "Payment not found", 404)
    return jsonify(row)

# GET /payment/v1/payment/user/<userId>
@app.route("/payment/v1/payment/user/<user_id>", methods=["GET"])
def get_by_user(user_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM payment_record WHERE userId=%s ORDER BY createdAt DESC", (user_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"userId": user_id, "payments": rows})

# GET /payment/v1/payment/concert/<concertId>
@app.route("/payment/v1/payment/concert/<concert_id>", methods=["GET"])
def get_by_concert(concert_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM payment_record WHERE concertId=%s AND type IN ('PURCHASE','RESALE_PURCHASE')",
                (concert_id,))
    rows = cur.fetchall(); cur.close(); db.close()
    return jsonify({"concertId": concert_id, "payments": rows})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "payment"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5004)), debug=False)
