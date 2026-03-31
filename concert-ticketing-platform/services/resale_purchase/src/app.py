"""
Resale Purchase — Composite Orchestrator (S2a + S2b)
Port: 5011
Stateless: no DB
S2a: POST /resale/v1/list        — seller lists ticket
S2b: POST /resale/v1/purchase    — buyer purchases resale ticket
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

TICKET_URL  = os.environ.get("TICKET_INVENTORY_SERVICE_URL", "http://localhost:5003")
PRICING_URL = os.environ.get("PRICING_SERVICE_URL",          "http://localhost:5001")
PAYMENT_URL = os.environ.get("PAYMENT_SERVICE_URL",          "http://localhost:5004")
QR_URL      = os.environ.get("QR_SERVICE_URL",               "http://localhost:5005")

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "resale_purchase", "timestamp": datetime.utcnow().isoformat()}}), status

# ── S2a: Seller lists ticket ──────────────────────────────────────────────────
# POST /resale/v1/list
@app.route("/resale/v1/list", methods=["POST"])
def list_ticket():
    data = request.get_json()
    required = ["sellerId", "ticketId", "concertId", "resalePrice"]
    if not all(k in data for k in required): return err("MISSING_FIELDS", f"Required: {required}")

    # Step 1 — verify ticket ownership and status
    t = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}", timeout=5)
    if t.status_code != 200: return err("TICKET_NOT_FOUND", "Ticket not found", 404)
    ticket = t.json()
    if ticket.get("ownerId") != data["sellerId"]:
        return err("NOT_OWNER", "You do not own this ticket", 403)
    if ticket["status"] != "CONFIRMED":
        return err("INVALID_STATUS", f"Ticket must be CONFIRMED to list; current: {ticket['status']}", 400)

    # Step 2 — validate resale price against ceiling
    pr = requests.get(f"{PRICING_URL}/pricing/v1/concerts/{data['concertId']}/prices/{ticket['categoryId']}/ceiling", timeout=5)
    if pr.status_code == 200:
        ceiling = pr.json().get("resaleCeiling")
        if ceiling and float(data["resalePrice"]) > float(ceiling):
            return err("PRICE_EXCEEDS_CEILING", f"Resale price cannot exceed {ceiling}", 400)

    # Step 3 — update ticket to RESALE_LISTED
    listing_id = f"LST-{data['ticketId']}-001"
    upd = requests.put(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                       json={"status": "RESALE_LISTED", "resalePrice": data["resalePrice"],
                             "resaleListingId": listing_id, "version": ticket["version"]}, timeout=5)
    if upd.status_code == 409: return err("VERSION_CONFLICT", "Ticket was modified; refresh and retry", 409)

    # Step 4 — notify seller (non-critical)
    try:
        mq_publish("ticket.resale.listed", {
            "eventType": "ticket.resale.listed", "userId": data["sellerId"],
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"ticketId": data["ticketId"], "concertId": data["concertId"],
                     "resalePrice": data["resalePrice"]}
        })
    except Exception: pass

    return jsonify({"success": True, "listingId": listing_id, "ticketId": data["ticketId"],
                    "resalePrice": data["resalePrice"], "status": "RESALE_LISTED"}), 201

# ── S2b: Buyer purchases resale ticket ────────────────────────────────────────
# POST /resale/v1/purchase
@app.route("/resale/v1/purchase", methods=["POST"])
def purchase_resale():
    data = request.get_json()
    required = ["buyerId", "ticketId", "concertId", "stripeToken"]
    if not all(k in data for k in required): return err("MISSING_FIELDS", f"Required: {required}")

    # Step 1 — verify ticket is RESALE_LISTED
    t = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}", timeout=5)
    if t.status_code != 200: return err("TICKET_NOT_FOUND", "Ticket not found", 404)
    ticket = t.json()
    if ticket["status"] != "RESALE_LISTED":
        return err("NOT_AVAILABLE", f"Ticket is {ticket['status']}, not available for resale purchase", 409)
    seller_id = ticket["ownerId"]
    resale_price = ticket["resalePrice"]
    current_version = ticket["version"]

    # Step 2 — validate price ceiling
    pr = requests.get(f"{PRICING_URL}/pricing/v1/concerts/{data['concertId']}/prices/{ticket['categoryId']}/ceiling", timeout=5)
    if pr.status_code == 200:
        ceiling = pr.json().get("resaleCeiling")
        if ceiling and float(resale_price) > float(ceiling):
            return err("PRICE_EXCEEDS_CEILING", "Listed price exceeds allowed ceiling", 400)

    # Step 3 — lock → RESALE_PENDING
    lock = requests.put(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                        json={"status": "RESALE_PENDING", "version": current_version}, timeout=5)
    if lock.status_code == 409: return err("TICKET_CONFLICT", "Ticket was just purchased by another buyer", 409)
    pending_version = current_version + 1

    # Step 4 — charge buyer
    pay = requests.post(f"{PAYMENT_URL}/payment/v1/payment",
                        json={"userId": data["buyerId"], "ticketId": data["ticketId"],
                              "concertId": data["concertId"], "amount": resale_price,
                              "currency": "SGD", "type": "RESALE_PURCHASE",
                              "stripeToken": data["stripeToken"]}, timeout=10)
    if pay.status_code != 201:
        requests.put(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                     json={"status": "RESALE_LISTED", "version": pending_version}, timeout=5)
        return err("PAYMENT_FAILED", "Payment declined", 402)
    payment_data = pay.json()

    # Step 5 — payout to seller (simulated in demo)
    try:
        requests.post(f"{PAYMENT_URL}/payment/v1/payment/refund",
                      json={"userId": seller_id, "ticketId": data["ticketId"],
                            "paymentId": payment_data["paymentId"],
                            "amount": resale_price, "reason": "RESALE_PAYOUT"}, timeout=5)
    except Exception: pass

    # Step 6 — invalidate seller's QR
    try:
        requests.put(f"{QR_URL}/qr/v1/qr/{data['ticketId']}/invalidate",
                     json={"reason": "RESALE_TRANSFER"}, timeout=5)
    except Exception: pass

    # Step 7 — confirm ticket to buyer
    requests.put(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                 json={"status": "CONFIRMED", "ownerId": data["buyerId"],
                       "resalePrice": None, "resaleListingId": None,
                       "version": pending_version}, timeout=5)

    # Step 8 — generate new QR for buyer
    qr_data = {}
    try:
        qr = requests.post(f"{QR_URL}/qr/v1/qr",
                           json={"ticketId": data["ticketId"], "userId": data["buyerId"],
                                 "concertId": data["concertId"]}, timeout=5)
        if qr.status_code == 201: qr_data = qr.json()
    except Exception: pass

    # Step 9 — notify both parties (non-critical)
    try:
        mq_publish("ticket.resale.sold", {
            "eventType": "ticket.resale.sold",
            "userId": seller_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"ticketId": data["ticketId"], "concertId": data["concertId"],
                     "resalePrice": resale_price, "buyerId": data["buyerId"]}
        })
    except Exception: pass

    return jsonify({"success": True, "ticketId": data["ticketId"],
                    "newOwner": data["buyerId"], "paymentId": payment_data["paymentId"],
                    "qrImageUrl": qr_data.get("qrImageUrl"),
                    "message": "Resale ticket purchased successfully!"}), 201

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "resale_purchase"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5011)), debug=False)
