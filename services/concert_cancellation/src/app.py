"""
Concert Cancellation — Composite Orchestrator (S3)
Port: 5012
Stateless: no DB
Orchestrates: Concert → Ticket Inventory → QR → Payment (bulk)
Publishes: concert.cancelled
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

CONCERT_URL = os.environ.get("CONCERT_SERVICE_URL",          "http://localhost:5000")
TICKET_URL  = os.environ.get("TICKET_INVENTORY_SERVICE_URL", "http://localhost:5003")
PAYMENT_URL = os.environ.get("PAYMENT_SERVICE_URL",          "http://localhost:5004")
QR_URL      = os.environ.get("QR_SERVICE_URL",               "http://localhost:5005")

# Return a standardised JSON error payload for the cancellation orchestrator.
def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "concert_cancellation", "timestamp": datetime.utcnow().isoformat()}}), status


# Select the payments that must be unwound for each ticket on cancellation.
#
# Normal ticket:
# - refund the original PURCHASE once.
#
# Resold ticket:
# - refund the latest RESALE_PURCHASE to return money to the final holder
# - refund the original PURCHASE so the original owner is not stranded after the
#   resale transfer is reversed
def choose_refundable_payments(payments):
    payments_by_ticket = {}
    refundable = []
    seen_payment_ids = set()

    for payment in payments:
        if str(payment.get("status", "")).upper() != "SUCCESS":
            continue
        if str(payment.get("type", "")).upper() not in {"PURCHASE", "RESALE_PURCHASE"}:
            continue
        ticket_id = payment.get("ticketId")
        if not ticket_id:
            continue
        payments_by_ticket.setdefault(ticket_id, []).append(payment)

    for ticket_id, ticket_payments in payments_by_ticket.items():
        purchases = [
            payment for payment in ticket_payments
            if str(payment.get("type", "")).upper() == "PURCHASE"
        ]
        resale_purchases = [
            payment for payment in ticket_payments
            if str(payment.get("type", "")).upper() == "RESALE_PURCHASE"
        ]

        purchases.sort(key=lambda payment: payment.get("createdAt") or "")
        resale_purchases.sort(key=lambda payment: payment.get("createdAt") or "")

        if resale_purchases:
            candidates = []
            if purchases:
                candidates.append(purchases[0])
            candidates.append(resale_purchases[-1])
        else:
            candidates = [purchases[-1]] if purchases else []

        for payment in candidates:
            payment_id = payment.get("paymentId")
            if payment_id and payment_id not in seen_payment_ids:
                seen_payment_ids.add(payment_id)
                refundable.append(payment)

    return refundable


# Fetch ticket details used in cancellation notifications.
def fetch_ticket_snapshot(concert_id, ticket_id):
    try:
        response = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/{ticket_id}", timeout=6)
        if response.status_code == 200 and isinstance(response.json(), dict):
            return response.json()
    except Exception:
        pass
    return {}


# Fetch concert details used in cancellation notifications.
def fetch_concert_snapshot(concert_id):
    try:
        response = requests.get(f"{CONCERT_URL}/concerts/{concert_id}", timeout=6)
        if response.status_code == 200 and isinstance(response.json(), dict):
            return response.json()
    except Exception:
        pass
    return {}

# POST /cancellation/v1/<concertId>
# Orchestrate concert cancellation, refunds, QR invalidation, and notifications.
@app.route("/cancellation/v1/<concert_id>", methods=["POST"])
def cancel_concert(concert_id):
    data = request.get_json() or {}
    reason = data.get("reason", "Concert cancelled by organiser")
    concert_snapshot = {}
    cancelled_at = datetime.utcnow().isoformat()

    # Step 1 — mark concert as CANCELLED (via OutSystems Concert Service)
    c = requests.put(f"{CONCERT_URL}/concerts/{concert_id}",
                     json={"status": "CANCELLED", "cancellationReason": reason}, timeout=10)
    if c.status_code not in (200, 201):
        if c.status_code == 404:
            return err("CONCERT_NOT_FOUND", f"Concert {concert_id} was not found", 404)
        message = "Could not cancel concert in Concert Service"
        try:
            payload = c.json()
            upstream = payload.get("error", {}).get("message")
            if upstream:
                message = f"Concert Service rejected cancellation: {upstream}"
        except Exception:
            pass
        return err("CONCERT_UPDATE_FAILED", message, c.status_code)

    try:
        concert_snapshot = c.json() if isinstance(c.json(), dict) else {}
    except Exception:
        concert_snapshot = {}
    if not concert_snapshot:
        concert_snapshot = fetch_concert_snapshot(concert_id)

    # Step 2+3 — bulk update all confirmed tickets to REFUNDED
    bulk = requests.put(f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/cancel-all",
                        json={"reason": reason}, timeout=30)
    tickets_queued = 0
    if bulk.status_code == 200:
        tickets_queued = bulk.json().get("ticketsQueuedForRefund", 0)

    # Step 4 — bulk invalidate all QRs
    try:
        requests.put(f"{QR_URL}/qr/v1/qr/concert/{concert_id}/invalidate-all", timeout=30)
    except Exception as e:
        print(f"[S3] QR bulk invalidate failed (non-critical): {e}")

    # Step 5 — refund only the latest effective purchase per ticket
    refund_count = 0; refund_failures = 0
    refunded_ticket_ids = set()
    try:
        pays = requests.get(f"{PAYMENT_URL}/payment/v1/payment/concert/{concert_id}", timeout=10)
        if pays.status_code == 200:
            refundable_payments = choose_refundable_payments(pays.json().get("payments", []))
            for payment in refundable_payments:
                try:
                    r = requests.post(f"{PAYMENT_URL}/payment/v1/payment/refund",
                                      json={"userId": payment["userId"], "ticketId": payment["ticketId"],
                                            "paymentId": payment["paymentId"], "amount": payment["amount"],
                                            "reason": "CONCERT_CANCELLED"}, timeout=10)
                    if r.status_code == 201:
                        refund_count += 1
                        refunded_ticket_ids.add(payment["ticketId"])
                        try:
                            ticket_snapshot = fetch_ticket_snapshot(concert_id, payment["ticketId"])
                            mq_publish("concert.cancelled", {
                                "eventType": "concert.cancelled",
                                "channel": "SMS",
                                "userId": payment["userId"],
                                "timestamp": cancelled_at,
                                "data": {
                                    "concertId": concert_id,
                                    "concertName": concert_snapshot.get("name") or concert_snapshot.get("concertName"),
                                    "concertDateTime": concert_snapshot.get("eventDate") or concert_snapshot.get("concertDateTime"),
                                    "cancellationReason": concert_snapshot.get("cancellationReason") or reason,
                                    "ticketId": payment["ticketId"],
                                    "seatNumber": ticket_snapshot.get("seatNumber"),
                                    "price": payment["amount"],
                                    "amount": payment["amount"],
                                    "currency": payment.get("currency", "SGD"),
                                    "purchaseDateTime": payment.get("createdAt"),
                                    "cancelledAt": cancelled_at,
                                    "reason": concert_snapshot.get("cancellationReason") or reason,
                                },
                            })
                        except Exception:
                            pass
                    else:
                        refund_failures += 1
                except Exception:
                    refund_failures += 1
    except Exception as e:
        print(f"[S3] Refund loop failed: {e}")

    tickets_refunded = 0
    if refunded_ticket_ids:
        try:
            finalize = requests.put(
                f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/refund-batch",
                json={"ticketIds": list(refunded_ticket_ids)},
                timeout=30,
            )
            if finalize.status_code == 200:
                tickets_refunded = finalize.json().get("ticketsRefunded", 0)
        except Exception as e:
            print(f"[S3] Ticket refund finalization failed: {e}")

    return jsonify({"success": True, "concertId": concert_id,
                    "ticketsQueuedForRefund": tickets_queued,
                    "ticketsRefunded": tickets_refunded,
                    "paymentsRefunded": refund_count,
                    "paymentRefundFailures": refund_failures,
                    "completedAt": cancelled_at})

# Expose a simple health endpoint for container checks.
@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "concert_cancellation"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5012)), debug=False)
