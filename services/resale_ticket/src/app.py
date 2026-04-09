"""
Resale Ticket Gateway — Composite Orchestrator (S2)
Port: 5013
Stateless: no DB
Responsibilities:
- Browse resale listings by concert
- Seller list/unlist ticket
- Buyer purchase resale ticket

This gateway composes atomic services and delegates purchase/list flows
to resale_purchase for consistency.
"""

from datetime import datetime
import os

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TICKET_URL = os.environ.get("TICKET_INVENTORY_SERVICE_URL", "http://localhost:5003")
PRICING_URL = os.environ.get("PRICING_SERVICE_URL", "http://localhost:5001")
RESALE_PURCHASE_URL = os.environ.get("RESALE_PURCHASE_SERVICE_URL", "http://localhost:5011")


# Return a standardised JSON error payload for the resale gateway.
def err(code, message, status=400):
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "service": "resale_ticket",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            }
        ),
        status,
    )


# Safely decode JSON bodies from upstream service responses.
def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


# Aggregate resale listings and enrich them with pricing ceiling data.
@app.route("/resale-ticket/v1/listings/<concert_id>", methods=["GET"])
def list_marketplace(concert_id):
    try:
        listings_resp = requests.get(
            f"{TICKET_URL}/tickets/v1/tickets/{concert_id}/resale", timeout=5
        )
        if listings_resp.status_code != 200:
            return err("TICKET_SERVICE_ERROR", "Could not retrieve resale listings", 503)

        listings_payload = safe_json(listings_resp)
        listings = listings_payload.get("listings", [])
        enriched = []
        for listing in listings:
            category_id = listing.get("categoryId")
            ceiling = None
            currency = "SGD"
            if category_id:
                try:
                    pr = requests.get(
                        f"{PRICING_URL}/pricing/v1/concerts/{concert_id}/prices/{category_id}/ceiling",
                        timeout=4,
                    )
                    if pr.status_code == 200:
                        pr_data = safe_json(pr)
                        ceiling = pr_data.get("resaleCeiling")
                        currency = pr_data.get("currency") or currency
                except requests.RequestException:
                    pass

            row = dict(listing)
            row["currency"] = currency
            row["resaleCeiling"] = ceiling
            enriched.append(row)

        return jsonify({"concertId": concert_id, "count": len(enriched), "listings": enriched})
    except requests.RequestException:
        return err("MARKETPLACE_ERROR", "Marketplace request failed", 503)


# Forward seller listing requests to the resale purchase orchestrator.
@app.route("/resale-ticket/v1/list", methods=["POST"])
def seller_list():
    payload = request.get_json() or {}
    required = ["sellerId", "ticketId", "concertId", "resalePrice"]
    if not all(k in payload for k in required):
        return err("MISSING_FIELDS", f"Required: {required}")

    try:
        resale_price = float(payload["resalePrice"])
        if resale_price <= 0:
            return err("INVALID_PRICE", "resalePrice must be > 0")
    except (TypeError, ValueError):
        return err("INVALID_PRICE", "resalePrice must be numeric")

    try:
        resp = requests.post(
            f"{RESALE_PURCHASE_URL}/resale/v1/list", json=payload, timeout=8
        )
        data = safe_json(resp)
        if resp.status_code >= 400:
            return jsonify(data), resp.status_code
        return jsonify(data), resp.status_code
    except requests.RequestException:
        return err("RESALE_COMPOSITE_ERROR", "Could not list resale ticket", 503)


# Remove a listed ticket from the marketplace and restore confirmed status.
@app.route("/resale-ticket/v1/unlist", methods=["PUT"])
def seller_unlist():
    data = request.get_json() or {}
    required = ["sellerId", "ticketId", "concertId"]
    if not all(k in data for k in required):
        return err("MISSING_FIELDS", f"Required: {required}")

    try:
        t = requests.get(
            f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}", timeout=5
        )
        if t.status_code != 200:
            return err("TICKET_NOT_FOUND", "Ticket not found", 404)
        ticket = safe_json(t)

        if ticket.get("ownerId") != data["sellerId"]:
            return err("NOT_OWNER", "You do not own this ticket", 403)
        if ticket.get("status") != "RESALE_LISTED":
            return err("INVALID_STATUS", "Ticket is not currently listed", 409)

        upd = requests.put(
            f"{TICKET_URL}/tickets/v1/tickets/{data['concertId']}/{data['ticketId']}",
            json={
                "status": "CONFIRMED",
                "resalePrice": None,
                "resaleListingId": None,
                "version": ticket["version"],
            },
            timeout=5,
        )
        if upd.status_code >= 400:
            return jsonify(safe_json(upd)), upd.status_code

        return (
            jsonify(
                {
                    "success": True,
                    "ticketId": data["ticketId"],
                    "status": "CONFIRMED",
                    "message": "Ticket removed from resale marketplace",
                }
            ),
            200,
        )
    except requests.RequestException:
        return err("UNLIST_ERROR", "Could not unlist ticket", 503)


# Forward a buyer resale checkout request to the resale orchestrator.
@app.route("/resale-ticket/v1/purchase", methods=["POST"])
def buyer_purchase():
    data = request.get_json() or {}
    required = ["buyerId", "ticketId", "concertId", "stripeToken"]
    if not all(k in data for k in required):
        return err("MISSING_FIELDS", f"Required: {required}")

    try:
        resp = requests.post(
            f"{RESALE_PURCHASE_URL}/resale/v1/purchase", json=data, timeout=15
        )
        body = safe_json(resp)
        return jsonify(body), resp.status_code
    except requests.RequestException:
        return err("PURCHASE_ERROR", "Could not process resale purchase", 503)


# Expose a simple health endpoint for container checks.
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "resale_ticket"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5013)), debug=False)
