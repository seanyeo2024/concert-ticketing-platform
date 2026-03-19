// ============================================================
// services/purchase-window/src/index.ts
// Scenario 1 — Purchase Window (Composite / Orchestrator)
// Orchestrates: inventory hold → payment → ticket confirm → QR
// This service coordinates multiple atomic services in sequence.
// ============================================================
import express from "express";
import axios from "axios";
import { v4 as uuidv4 } from "uuid";
import { publish, TOPICS } from "../../../shared/utils/amqp";
import { ok, asyncHandler, errorHandler, ValidationError, PaymentError } from "../../../shared/utils/http";
import type { PurchaseSession, PaymentRequest } from "../../../shared/types";

const app = express();
app.use(express.json());

// ── Internal service URLs (resolved via Kong / service mesh) ─
const INVENTORY_URL  = process.env.INVENTORY_URL  ?? "http://ticket-inventory:3003";
const PAYMENT_URL    = process.env.PAYMENT_URL    ?? "http://payment-service:3005";
const QR_URL         = process.env.QR_URL         ?? "http://qr-service:3007";

// ── Routes ──────────────────────────────────────────────────

/**
 * POST /purchase/details
 * Body: { concertID, sessionToken, expiresAt, seatId? }
 * 
 * Orchestration steps:
 *  1. Validate session token has not expired
 *  2. GET available tickets for seat/type
 *  3. PUT ticket status → PENDING (inventory hold)
 *  4. POST payment charge
 *  5. PUT ticket status → SOLD
 *  6. Publish ticket.confirmed (AMQP) → QR + Notification services consume
 */
app.post(
  "/purchase/details",
  asyncHandler(async (req, res) => {
    const { concertID, sessionToken, expiresAt, seatId, ticketID, buyerID } = req.body;

    // Step 1 — Validate session window has not expired
    if (!sessionToken || !expiresAt) throw new ValidationError("sessionToken and expiresAt are required");
    if (new Date(expiresAt) < new Date()) throw new ValidationError("Purchase window has expired. Please rejoin the queue.");

    // Step 2 — Get ticket details
    const { data: ticketRes } = await axios.get(`${INVENTORY_URL}/inventory/ticket/${concertID}/${ticketID}`);
    const ticket = ticketRes.data;

    if (ticket.status !== "AVAILABLE") throw new ValidationError("Ticket is no longer available.");

    // Step 3 — Hold ticket (PENDING) with optimistic lock
    await axios.put(`${INVENTORY_URL}/inventory/ticket/${concertID}/${ticketID}/status`, {
      status: "PENDING",
      version: ticket.version,
    });

    // Step 4 — Process payment
    const paymentPayload: PaymentRequest = {
      buyerID,
      amount: ticket.price ?? 0,
      currency: "SGD",
      ticketID,
      idempotencyKey: `${sessionToken}-${ticketID}`, // idempotent — safe to retry
    };

    let paymentResult;
    try {
      const { data: payRes } = await axios.post(`${PAYMENT_URL}/payment/charge`, paymentPayload);
      paymentResult = payRes.data;
    } catch (err: any) {
      // Payment failed — revert hold back to AVAILABLE
      await axios.put(`${INVENTORY_URL}/inventory/ticket/${concertID}/${ticketID}/status`, {
        status: "AVAILABLE",
        version: ticket.version + 1,
      });
      throw new PaymentError(err?.response?.data?.error?.message ?? "Payment processing failed");
    }

    if (paymentResult.status !== "SUCCESS") {
      await axios.put(`${INVENTORY_URL}/inventory/ticket/${concertID}/${ticketID}/status`, {
        status: "AVAILABLE",
        version: ticket.version + 1,
      });
      throw new PaymentError("Payment was not successful.");
    }

    // Step 5 — Mark ticket SOLD
    await axios.put(`${INVENTORY_URL}/inventory/ticket/${concertID}/${ticketID}/status`, {
      status: "SOLD",
      version: ticket.version + 1,
    });

    // Step 6 — Publish ticket.confirmed (triggers QR generation + notification)
    await publish({
      topic: "ticket.confirmed",
      data: { ticketID, buyerID, eventID: ticket.eventID, concertID },
    });

    ok(res, {
      message: "Purchase successful",
      ticketID,
      transactionID: paymentResult.transactionID,
      status: "SOLD",
    });
  })
);

/**
 * GET /purchase/receipt/:ticketId
 * Retrieve stored receipt for a purchased ticket.
 */
app.get(
  "/purchase/receipt/:ticketId",
  asyncHandler(async (req, res) => {
    // TODO: query receipt DB
    ok(res, { ticketID: req.params.ticketId, message: "Receipt retrieval not yet implemented" });
  })
);

app.use(errorHandler);

const PORT = process.env.PORT ?? 3004;
app.listen(PORT, () => console.log(`[purchase-window] Listening on :${PORT}`));

export default app;
