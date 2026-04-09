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

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "concert_cancellation", "timestamp": datetime.utcnow().isoformat()}}), status

# POST /cancellation/v1/<concertId>
@app.route("/cancellation/v1/<concert_id>", methods=["POST"])
def cancel_concert(concert_id):
    data = request.get_json() or {}
    reason = data.get("reason", "Concert cancelled by organiser")

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

    # Step 5 — get all payments for this concert and refund each
    refund_count = 0; refund_failures = 0
    refunded_ticket_ids = []
    try:
        pays = requests.get(f"{PAYMENT_URL}/payment/v1/payment/concert/{concert_id}", timeout=10)
        if pays.status_code == 200:
            for payment in pays.json().get("payments", []):
                try:
                    r = requests.post(f"{PAYMENT_URL}/payment/v1/payment/refund",
                                      json={"userId": payment["userId"], "ticketId": payment["ticketId"],
                                            "paymentId": payment["paymentId"], "amount": payment["amount"],
                                            "reason": "CONCERT_CANCELLED"}, timeout=10)
                    if r.status_code == 201:
                        refund_count += 1
                        refunded_ticket_ids.append(payment["ticketId"])
                        try:
                            mq_publish("concert.cancelled", {
                                "eventType": "concert.cancelled",
                                "channel": "SMS",
                                "userId": payment["userId"],
                                "timestamp": datetime.utcnow().isoformat(),
                                "data": {
                                    "concertId": concert_id,
                                    "amount": payment["amount"],
                                    "currency": payment.get("currency", "SGD"),
                                    "reason": reason,
                                },
                            })
                        except Exception:
                            pass
                    else:
                        refund_failures += 1
                except Exception: refund_failures += 1
    except Exception as e:
        print(f"[S3] Refund loop failed: {e}")

    tickets_refunded = 0
    if refunded_ticket_ids:
        try:
            finalize = requests.put(
                f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/refund-batch",
                json={"ticketIds": refunded_ticket_ids},
                timeout=30,
            )
            if finalize.status_code == 200:
                tickets_refunded = finalize.json().get("ticketsRefunded", 0)
        except Exception as e:
            print(f"[S3] Ticket refund finalization failed: {e}")

    # Step 6 — publish per-user cancellation notifications after successful refunds
    # so notification service can resolve the recipient and send SMS.

    return jsonify({"success": True, "concertId": concert_id,
                    "ticketsQueuedForRefund": tickets_queued,
                    "ticketsRefunded": tickets_refunded,
                    "paymentsRefunded": refund_count,
                    "paymentRefundFailures": refund_failures,
                    "completedAt": datetime.utcnow().isoformat()})

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "concert_cancellation"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5012)), debug=False)
