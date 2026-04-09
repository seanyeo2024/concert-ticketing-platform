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
import re
from urllib.parse import quote

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
CONCERT_URL = os.environ.get("CONCERT_SERVICE_URL",          "https://personal-cqdsnkhp.outsystemscloud.com/ConcertAPI/rest/v1")
FRONTEND_PAGES_BASE_URL = os.environ.get("FRONTEND_PAGES_BASE_URL", "http://localhost:8080/pages")
EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

def err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message,
                              "service": "resale_purchase", "timestamp": datetime.utcnow().isoformat()}}), status


def issue_buyer_qr(ticket_id, buyer_id, concert_id, retries=3):
    last_error = None
    for _ in range(retries):
        try:
            qr = requests.post(
                f"{QR_URL}/qr/v1/qr",
                json={"ticketId": ticket_id, "userId": buyer_id, "concertId": concert_id},
                timeout=5,
            )
            if qr.status_code == 201:
                return qr.json()
            last_error = qr.text
        except requests.RequestException as exc:
            last_error = str(exc)
    return {"error": last_error or "QR generation failed"}


def fetch_concert_meta(concert_id):
    base_urls = [(CONCERT_URL or "").rstrip("/"), "http://concert:5000", "http://kong:8000", "http://localhost:5000"]
    tried = set()
    for base in base_urls:
        if not base or base in tried:
            continue
        tried.add(base)
        try:
            res = requests.get(f"{base}/concerts/{concert_id}", timeout=5)
            if res.status_code == 200 and isinstance(res.json(), dict):
                data = res.json()
                return {
                    "concertName": data.get("name") or data.get("concertName") or data.get("title") or concert_id,
                    "concertDateTime": data.get("eventDate") or data.get("concertDateTime"),
                }
        except Exception:
            continue
    return {"concertName": concert_id, "concertDateTime": None}

# ── S2a: Seller lists ticket ──────────────────────────────────────────────────
# POST /resale/v1/list
@app.route("/resale/v1/list", methods=["POST"])
def list_ticket():
    data = request.get_json()
    required = ["sellerId", "ticketId", "concertId", "resalePrice"]
    if not all(k in data for k in required): return err("MISSING_FIELDS", f"Required: {required}")
    seller_email = (data.get("sellerEmail") or data.get("contactEmail") or data.get("toEmail") or data.get("email") or "").strip()
    if seller_email and not EMAIL_PATTERN.fullmatch(seller_email):
        return err("INVALID_EMAIL", "A valid sellerEmail/contactEmail/toEmail is required when provided")

    # Step 1 — verify ticket ownership and status
    t = requests.get(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}", timeout=5)
    if t.status_code != 200: return err("TICKET_NOT_FOUND", "Ticket not found", 404)
    ticket = t.json()
    if ticket.get("ownerId") != data["sellerId"]:
        return err("NOT_OWNER", "You do not own this ticket", 403)
    if ticket["status"] != "CONFIRMED":
        return err("INVALID_STATUS", f"Ticket must be CONFIRMED to list; current: {ticket['status']}", 400)

    # Business rule: a ticket can only be resold once.
    try:
        pay = requests.get(f"{PAYMENT_URL}/payment/v1/payment/concert/{data['concertId']}", timeout=5)
        if pay.status_code != 200:
            return err("PAYMENT_LOOKUP_FAILED", "Unable to verify resale eligibility right now", 503)
        payments = pay.json().get("payments", [])
        already_resold_once = any(
            str(p.get("ticketId")) == str(data["ticketId"])
            and p.get("type") == "RESALE_PURCHASE"
            and p.get("status") == "SUCCESS"
            for p in payments
        )
        if already_resold_once:
            return err("RESALE_LIMIT_REACHED", "This ticket has already been resold once and cannot be listed again", 409)
    except requests.RequestException:
        return err("PAYMENT_LOOKUP_FAILED", "Unable to verify resale eligibility right now", 503)

    # Step 2 — validate resale price against ceiling
    try:
        pr = requests.get(
            f"{PRICING_URL}/pricing/v1/concerts/{data['concertId']}/prices/{ticket['categoryId']}/ceiling",
            timeout=5,
        )
        if pr.status_code == 200:
            ceiling = pr.json().get("resaleCeiling")
            if ceiling and float(data["resalePrice"]) > float(ceiling):
                return err("PRICE_EXCEEDS_CEILING", f"Resale price cannot exceed {ceiling}", 400)
    except requests.RequestException:
        # Do not block listing when pricing service is temporarily unavailable.
        pass

    # Step 3 — update ticket to RESALE_LISTED
    listing_id = f"LST-{data['ticketId']}-001"
    upd = requests.put(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                       json={"status": "RESALE_LISTED", "resalePrice": data["resalePrice"],
                             "resaleListingId": listing_id, "version": ticket["version"]}, timeout=5)
    if upd.status_code == 409: return err("VERSION_CONFLICT", "Ticket was modified; refresh and retry", 409)

    # Step 4 — notify seller (non-critical)
    try:
        concert_meta = fetch_concert_meta(data["concertId"])
        seller_phone = data.get("sellerPhoneNumber") or data.get("phoneNumber") or data.get("toNumber")
        event_payload = {
            "eventType": "ticket.resale.listed", "channel": "SMS", "userId": data["sellerId"],
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"ticketId": data["ticketId"], "concertId": data["concertId"],
                     "concertName": concert_meta.get("concertName"),
                     "concertDateTime": concert_meta.get("concertDateTime"),
                     "seatNumber": ticket.get("seatNumber"),
                     "resalePrice": data["resalePrice"],
                     "currency": "SGD"}
        }
        if seller_phone:
            event_payload["phoneNumber"] = seller_phone
            event_payload["data"]["phoneNumber"] = seller_phone
        if seller_email:
            event_payload["toEmail"] = seller_email
            event_payload["contactEmail"] = seller_email
            event_payload["data"]["toEmail"] = seller_email
            event_payload["data"]["contactEmail"] = seller_email
        mq_publish("ticket.resale.listed", event_payload)
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
    buyer_phone = data.get("phoneNumber") or data.get("contactPhone") or data.get("toNumber")
    buyer_email = (data.get("contactEmail") or data.get("toEmail") or data.get("email") or "").strip()
    seller_email = (data.get("sellerEmail") or data.get("sellerContactEmail") or "").strip()
    if not buyer_phone:
        return err("MISSING_FIELDS", "phoneNumber is required for buyer SMS notifications")
    if buyer_email and not EMAIL_PATTERN.fullmatch(buyer_email):
        return err("INVALID_EMAIL", "A valid contactEmail/toEmail is required when provided")
    if seller_email and not EMAIL_PATTERN.fullmatch(seller_email):
        return err("INVALID_EMAIL", "A valid sellerEmail/sellerContactEmail is required when provided")

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
    try:
        pr = requests.get(
            f"{PRICING_URL}/pricing/v1/concerts/{data['concertId']}/prices/{ticket['categoryId']}/ceiling",
            timeout=5,
        )
        if pr.status_code == 200:
            ceiling = pr.json().get("resaleCeiling")
            if ceiling and float(resale_price) > float(ceiling):
                return err("PRICE_EXCEEDS_CEILING", "Listed price exceeds allowed ceiling", 400)
    except requests.RequestException:
        # Do not block purchase when pricing service is temporarily unavailable.
        pass

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
                              "sellerId": seller_id,
                              "stripeToken": data["stripeToken"]}, timeout=10)
    if pay.status_code != 201:
        requests.put(f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                     json={"status": "RESALE_LISTED", "version": pending_version}, timeout=5)
        return err("PAYMENT_FAILED", "Payment declined", 402)
    payment_data = pay.json()

    # Step 5 — record seller payout against the buyer's successful resale payment
    seller_payout_recorded = False
    seller_payout_id = None
    try:
        payout = requests.post(
            f"{PAYMENT_URL}/payment/v1/payment/resale-payout",
            json={
                "sellerId": seller_id,
                "ticketId": data["ticketId"],
                "concertId": data["concertId"],
                "buyerPaymentId": payment_data["paymentId"],
                "amount": resale_price,
            },
            timeout=5,
        )
        if payout.status_code == 201:
            payout_data = payout.json()
            seller_payout_recorded = True
            seller_payout_id = payout_data.get("paymentId")
    except Exception:
        seller_payout_recorded = False

    # Step 6 — invalidate seller's QR
    seller_qr_invalidated = False
    try:
        invalidate = requests.put(
            f"{QR_URL}/qr/v1/qr/{data['ticketId']}/invalidate",
            json={"reason": "RESALE_TRANSFER"},
            timeout=5,
        )
        seller_qr_invalidated = invalidate.status_code in (200, 409)
    except Exception:
        seller_qr_invalidated = False

    # Step 7 — confirm ticket to buyer (with retry on version conflict)
    confirm_retries = 0
    while confirm_retries < 3:
        try:
            confirm = requests.put(
                f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                json={"status": "CONFIRMED", "ownerId": data["buyerId"],
                      "purchasePrice": resale_price,
                      "resalePrice": None, "resaleListingId": None,
                      "version": pending_version},
                timeout=5,
            )
            if confirm.status_code == 200:
                break
            elif confirm.status_code == 409:
                # Version conflict: fetch fresh version and retry
                confirm_retries += 1
                if confirm_retries < 3:
                    try:
                        fresh_t = requests.get(
                            f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
                            timeout=5,
                        )
                        if fresh_t.status_code == 200:
                            pending_version = fresh_t.json().get("version", pending_version)
                    except Exception:
                        pass
                    continue
            else:
                return err("CONFIRM_FAILED", f"Could not confirm ticket to buyer: {confirm.text}", 500)
        except requests.RequestException as exc:
            return err("CONFIRM_ERROR", f"Error confirming ticket: {str(exc)}", 500)
    
    if confirm_retries >= 3:
        return err("CONFIRM_CONFLICT", "Could not finalize ticket ownership after 3 retries", 500)

    # Step 8 — generate new QR for buyer
    qr_data = issue_buyer_qr(data["ticketId"], data["buyerId"], data["concertId"])
    qr_ready = "qrId" in qr_data

    # Step 9 — notify both parties (non-critical)
    concert_meta = fetch_concert_meta(data["concertId"])
    sale_dt = payment_data.get("createdAt") or datetime.utcnow().isoformat()
    next_page = quote(
        f"my-tickets.html?refreshTicket={data['ticketId']}&refreshConcert={data['concertId']}",
        safe="",
    )
    qr_link = (
        f"{FRONTEND_PAGES_BASE_URL}/login.html?next={next_page}"
        f"&requiredOwner={quote(str(data['buyerId']), safe='')}"
    )

    try:
        seller_phone = data.get("sellerPhoneNumber") or data.get("sellerContactPhone") or data.get("sellerToNumber")
        event_payload = {
            "eventType": "ticket.resale.sold",
            "channel": "SMS",
            "userId": seller_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"ticketId": data["ticketId"], "concertId": data["concertId"],
                     "concertName": concert_meta.get("concertName"),
                     "concertDateTime": concert_meta.get("concertDateTime"),
                     "seatNumber": ticket.get("seatNumber"),
                     "resalePrice": resale_price, "currency": "SGD",
                     "saleDateTime": sale_dt,
                     "buyerId": data["buyerId"]}
        }
        if seller_phone:
            event_payload["phoneNumber"] = seller_phone
            event_payload["data"]["phoneNumber"] = seller_phone
        if seller_email:
            event_payload["toEmail"] = seller_email
            event_payload["contactEmail"] = seller_email
            event_payload["email"] = seller_email
            event_payload["data"]["toEmail"] = seller_email
            event_payload["data"]["contactEmail"] = seller_email
            event_payload["data"]["email"] = seller_email
        mq_publish("ticket.resale.sold", event_payload)
    except Exception as exc:
        print(f"[RESALE_PURCHASE] Seller notification publish failed: {exc}")

    try:
        buyer_event = {
            "eventType": "ticket.purchased",
            "channel": "SMS",
            "userId": data["buyerId"],
            "phoneNumber": buyer_phone,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "userId": data["buyerId"],
                "ticketId": data["ticketId"],
                "concertId": data["concertId"],
                "concertName": concert_meta.get("concertName"),
                "concertDateTime": concert_meta.get("concertDateTime"),
                "seatNumber": ticket.get("seatNumber"),
                "amount": resale_price,
                "currency": "SGD",
                "purchaseDateTime": sale_dt,
                "purchaseType": "RESALE",
                "phoneNumber": buyer_phone,
                "qrImageUrl": qr_data.get("qrImageUrl"),
                "qrCodeLink": qr_link,
            },
        }
        if buyer_email:
            buyer_event["toEmail"] = buyer_email
            buyer_event["contactEmail"] = buyer_email
            buyer_event["email"] = buyer_email
            buyer_event["data"]["toEmail"] = buyer_email
            buyer_event["data"]["contactEmail"] = buyer_email
            buyer_event["data"]["email"] = buyer_email

        mq_publish("ticket.purchased", buyer_event)
    except Exception as exc:
        print(f"[RESALE_PURCHASE] Buyer notification publish failed: {exc}")

    return jsonify({"success": True, "ticketId": data["ticketId"],
                    "newOwner": data["buyerId"], "paymentId": payment_data["paymentId"],
                    "sellerPayoutRecorded": seller_payout_recorded,
                    "sellerPayoutId": seller_payout_id,
                    "sellerQrInvalidated": seller_qr_invalidated,
                    "qrReady": qr_ready,
                    "qrId": qr_data.get("qrId"),
                    "qrData": qr_data.get("qrData"),
                    "qrImageUrl": qr_data.get("qrImageUrl"),
                    "message": "Resale ticket purchased successfully!"}), 201

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "resale_purchase"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5011)), debug=False)
