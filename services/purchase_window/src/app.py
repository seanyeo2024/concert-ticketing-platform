"""
Purchase Window — Composite Orchestrator (S1)
Port: 5010
Stateless: no DB
Orchestrates: Queue → Concert → Pricing → Ticket Inventory → Payment → QR
Publishes: ticket.purchased, queue.window.granted
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests, os, sys
from datetime import datetime

app = Flask(__name__)
CORS(app)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../notification/src"))
try:
    from amqp_publisher import publish as mq_publish
except ImportError:
    def mq_publish(rk, payload): print(f"[MQ STUB] {rk}: {payload}")

CONCERT_URL  = os.environ.get("CONCERT_SERVICE_URL",          "http://localhost:5000")
PRICING_URL  = os.environ.get("PRICING_SERVICE_URL",          "http://localhost:5001")
QUEUE_URL    = os.environ.get("QUEUE_SERVICE_URL",            "http://localhost:5002")
TICKET_URL   = os.environ.get("TICKET_INVENTORY_SERVICE_URL", "http://localhost:5003")
PAYMENT_URL  = os.environ.get("PAYMENT_SERVICE_URL",          "http://localhost:5004")
QR_URL       = os.environ.get("QR_SERVICE_URL",               "http://localhost:5005")

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "purchase_window", "timestamp": datetime.utcnow().isoformat()}}), status


def safe_json(response):
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}

def rollback_ticket(concert_id, ticket_id, version):
    try:
        requests.put(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/{ticket_id}",
                     json={"status": "AVAILABLE", "ownerId": None, "version": version}, timeout=5)
    except Exception: pass


def resolve_ticket(concert_id, ticket_id, seat_number):
    ticket_res = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/{ticket_id}", timeout=5)
    if ticket_res.status_code == 200:
        return ticket_res.json(), None

    if not seat_number:
        return None, "Ticket not found"

    available_res = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}?status=AVAILABLE", timeout=5)
    if available_res.status_code != 200:
        return None, "Ticket not found"

    tickets = available_res.json().get("tickets", [])
    fallback = next((row for row in tickets if str(row.get("seatNumber")) == str(seat_number)), None)
    if not fallback:
        return None, "Ticket not found"

    return fallback, f"Recovered ticket by seat number {seat_number}"

# POST /purchase/v1/window/<concertId>
@app.route("/purchase/v1/window/<concert_id>", methods=["POST"])
def purchase(concert_id):
    data = request.get_json() or {}
    user_id   = data.get("userId")
    ticket_id = data.get("ticketId")
    seat_number = data.get("seatNumber")
    session_token = data.get("sessionToken")
    stripe_token = data.get("stripeToken", "tok_simulated")
    if not all([user_id, ticket_id, session_token]):
        return err("MISSING_FIELDS", "userId, ticketId, and sessionToken are required")

    # Step 1 — verify queue window is WINDOW_GRANTED and not expired
    q = requests.get(f"{QUEUE_URL}/queue/v1/queue/{concert_id}/{user_id}", timeout=5)
    if q.status_code == 410:
        return jsonify({"error": {
            "code": "WINDOW_EXPIRED",
            "message": "Purchase window expired; rejoin the queue",
            "queueStatusCode": q.status_code,
            "queueResponse": safe_json(q),
            "service": "purchase_window",
            "timestamp": datetime.utcnow().isoformat()
        }}), 410
    if q.status_code != 200:
        return jsonify({"error": {
            "code": "QUEUE_ERROR",
            "message": "Could not verify queue status",
            "queueStatusCode": q.status_code,
            "queueResponse": safe_json(q),
            "service": "purchase_window",
            "timestamp": datetime.utcnow().isoformat()
        }}), 503
    queue_payload = safe_json(q)
    if queue_payload.get("status") != "WINDOW_GRANTED":
        return jsonify({"error": {
            "code": "NO_WINDOW",
            "message": "No active purchase window for this user",
            "queueStatusCode": q.status_code,
            "queueResponse": queue_payload,
            "service": "purchase_window",
            "timestamp": datetime.utcnow().isoformat()
        }}), 403

    session_check = requests.post(
        f"{QUEUE_URL}/queue/v1/session/validate",
        json={"concertId": concert_id, "userId": user_id, "sessionToken": session_token},
        timeout=5,
    )
    if session_check.status_code == 410:
        return jsonify({"error": {
            "code": "WINDOW_EXPIRED",
            "message": "Purchase window expired; rejoin the queue",
            "queueStatusCode": session_check.status_code,
            "queueResponse": safe_json(session_check),
            "service": "purchase_window",
            "timestamp": datetime.utcnow().isoformat()
        }}), 410
    if session_check.status_code != 200:
        return jsonify({"error": {
            "code": "INVALID_QUEUE_SESSION",
            "message": "Queue session token is invalid",
            "queueStatusCode": session_check.status_code,
            "queueResponse": safe_json(session_check),
            "service": "purchase_window",
            "timestamp": datetime.utcnow().isoformat()
        }}), 403

    # Step 2 — get ticket and verify AVAILABLE
    ticket, resolution_note = resolve_ticket(concert_id, ticket_id, seat_number)
    if not ticket:
        return err("TICKET_NOT_FOUND", "Ticket not found", 404)
    ticket_id = ticket["ticketId"]
    if ticket["status"] != "AVAILABLE":
        return err("TICKET_UNAVAILABLE", f"Ticket is {ticket['status']}, not AVAILABLE", 409)
    current_version = ticket["version"]

    # Step 3 — get price
    pr = requests.get(f"{PRICING_URL}/pricing/v1/concerts/{concert_id}/prices/{ticket['categoryId']}", timeout=5)
    if pr.status_code != 200: return err("PRICING_ERROR", "Could not retrieve price", 503)
    price_data = pr.json()
    amount = price_data["basePrice"]
    currency = price_data["currency"]

    # Step 4 — lock ticket → PENDING
    lock = requests.put(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/{ticket_id}",
                        json={"status": "PENDING", "ownerId": user_id, "version": current_version}, timeout=5)
    if lock.status_code == 409: return err("TICKET_CONFLICT", "Ticket was taken by another user", 409)
    if lock.status_code != 200: return err("LOCK_ERROR", "Could not lock ticket", 503)
    pending_version = current_version + 1

    # Step 5 — charge payment
    try:
        pay = requests.post(f"{PAYMENT_URL}/payment/v1/payment",
                            json={"userId": user_id, "ticketId": ticket_id, "concertId": concert_id,
                                  "amount": amount, "currency": currency, "type": "PURCHASE",
                                  "stripeToken": stripe_token}, timeout=10)
        if pay.status_code != 201:
            rollback_ticket(concert_id, ticket_id, pending_version)
            return err("PAYMENT_FAILED", "Payment was declined", 402)
        payment_data = pay.json()
    except requests.exceptions.Timeout:
        rollback_ticket(concert_id, ticket_id, pending_version)
        return err("PAYMENT_TIMEOUT", "Payment request timed out; ticket lock released", 503)
    except requests.exceptions.RequestException as e:
        rollback_ticket(concert_id, ticket_id, pending_version)
        return err("PAYMENT_ERROR", f"Payment service error: {str(e)}", 503)

    # Step 6 — confirm ticket ownership
    try:
        requests.put(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/{ticket_id}",
                     json={"status": "CONFIRMED", "ownerId": user_id,
                           "purchasePrice": amount, "version": pending_version}, timeout=5)
    except requests.exceptions.RequestException:
        # Non-critical; if this fails, ticket stays PENDING but payment succeeded
        print(f"[WARN] Could not confirm ticket {ticket_id} after payment succeeded")
        pass

    # Step 7 — mark queue COMPLETED (non-critical)
    try:
        requests.post(
            f"{QUEUE_URL}/queue/v1/session/consume",
            json={"concertId": concert_id, "userId": user_id, "sessionToken": session_token},
            timeout=5,
        )
    except Exception:
        pass

    # Step 8 — generate QR (non-critical)
    qr_data = {}
    try:
        qr = requests.post(f"{QR_URL}/qr/v1/qr",
                           json={"ticketId": ticket_id, "userId": user_id, "concertId": concert_id}, timeout=5)
        if qr.status_code == 201: qr_data = qr.json()
    except Exception: pass

    # Step 9 — publish notification event (non-critical)
    try:
        mq_publish("ticket.purchased", {
            "eventType": "ticket.purchased", "channel": "SMS", "userId": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"ticketId": ticket_id, "concertId": concert_id,
                     "seatNumber": ticket.get("seatNumber"), "amount": amount, "currency": currency,
                     "qrImageUrl": qr_data.get("qrImageUrl")}
        })
    except Exception: pass

    return jsonify({"success": True, "ticketId": ticket_id, "paymentId": payment_data["paymentId"],
                    "amount": amount, "currency": currency,
                    "qrImageUrl": qr_data.get("qrImageUrl"),
                    "resolutionNote": resolution_note,
                    "message": "Ticket purchased successfully!"}), 201

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "purchase_window"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5010)), debug=False)
