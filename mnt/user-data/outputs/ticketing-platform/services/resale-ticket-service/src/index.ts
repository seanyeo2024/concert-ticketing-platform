// ============================================================
// services/resale-ticket-service/src/index.ts
// Scenario 2 — Resale Ticket Service (Composite Orchestrator)
// Handles: list ticket for resale, buyer purchase flow,
//          pricing, ownership transfer, seller payout
// ============================================================
import express from "express";
import axios from "axios";
import { publish, subscribe, TOPICS } from "../../../shared/utils/amqp";
import { ok, asyncHandler, errorHandler, NotFoundError, ValidationError, PaymentError } from "../../../shared/utils/http";

const app = express();
app.use(express.json());

const INVENTORY_URL = process.env.INVENTORY_URL ?? "http://ticket-inventory:3003";
const PRICING_URL   = process.env.PRICING_URL   ?? "http://pricing-service:3008";
const PAYMENT_URL   = process.env.PAYMENT_URL   ?? "http://payment-service:3005";

// ── In-memory listing store (replace with DB in production) ──
const listings = new Map<number, {
  ticketID: number;
  sellerID: number;
  eventID: number;
  resalePrice: number;
  currency: string;
  status: string;
}>();

// ── Scenario 2A: Seller lists ticket ────────────────────────

/**
 * POST /resale/list
 * Body: { ticketID, sellerID }
 * 1. Mark ticket as RESALE in inventory
 * 2. Fetch pricing details
 * 3. Create listing
 */
app.post(
  "/resale/list",
  asyncHandler(async (req, res) => {
    const { ticketID, sellerID } = req.body;

    // GET current ticket
    const { data: ticketRes } = await axios.get(`${INVENTORY_URL}/inventory/ticket/0/${ticketID}`);
    const ticket = ticketRes.data;

    if (ticket.ownerID !== sellerID) throw new ValidationError("You do not own this ticket.");
    if (ticket.status !== "AVAILABLE" && ticket.status !== "SOLD") {
      throw new ValidationError(`Cannot list a ticket with status: ${ticket.status}`);
    }

    // Mark as RESALE in inventory
    await axios.put(`${INVENTORY_URL}/inventory/ticket/0/${ticketID}/status`, {
      status: "RESALE",
      version: ticket.version,
    });

    // Get pricing
    const { data: priceRes } = await axios.get(`${PRICING_URL}/pricing/${ticket.eventID}`);
    const { basePrice, resalePrice, currency } = priceRes.data;

    // Store listing
    listings.set(ticketID, { ticketID, sellerID, eventID: ticket.eventID, resalePrice, currency, status: "LISTED" });

    // Confirm listing back to inventory (status → LISTED)
    await axios.put(`${INVENTORY_URL}/inventory/ticket/0/${ticketID}/status`, {
      status: "LISTED",
      version: ticket.version + 1,
    });

    ok(res, { ticketID, status: "LISTED", resalePrice, currency });
  })
);

/**
 * DELETE /resale/list/:ticketId
 * Seller cancels their listing.
 */
app.delete(
  "/resale/list/:ticketId",
  asyncHandler(async (req, res) => {
    const ticketID = Number(req.params.ticketId);
    const listing = listings.get(ticketID);
    if (!listing) throw new NotFoundError("Listing");

    const { data: ticketRes } = await axios.get(`${INVENTORY_URL}/inventory/ticket/0/${ticketID}`);
    await axios.put(`${INVENTORY_URL}/inventory/ticket/0/${ticketID}/status`, {
      status: "AVAILABLE",
      version: ticketRes.data.version,
    });

    listings.delete(ticketID);
    ok(res, { ticketID, status: "AVAILABLE" });
  })
);

// ── Scenario 2B: Buyer purchases resale ticket ───────────────

/**
 * GET /resale/tickets
 * List all available resale tickets.
 */
app.get(
  "/resale/tickets",
  asyncHandler(async (_req, res) => {
    const available = [...listings.values()].filter((l) => l.status === "LISTED");
    ok(res, available);
  })
);

/**
 * GET /resale/tickets/:ticketId
 * Get a specific resale listing.
 */
app.get(
  "/resale/tickets/:ticketId",
  asyncHandler(async (req, res) => {
    const listing = listings.get(Number(req.params.ticketId));
    if (!listing || listing.status !== "LISTED") throw new NotFoundError("Resale listing");
    ok(res, listing);
  })
);

/**
 * POST /resale/purchase
 * Body: { ticketID, buyerID, resalePrice }
 * 
 * Orchestration:
 *  1. Validate listing exists
 *  2. Mark ticket PROCESSING
 *  3. Charge buyer via Payment service
 *  4. Transfer ownership in Inventory
 *  5. Trigger seller payout
 *  6. Publish ticket.resold (AMQP) → QR + Notification
 */
app.post(
  "/resale/purchase",
  asyncHandler(async (req, res) => {
    const { ticketID, buyerID, resalePrice } = req.body;

    const listing = listings.get(ticketID);
    if (!listing || listing.status !== "LISTED") throw new NotFoundError("Resale listing");

    // Mark as processing to prevent double-purchases
    listing.status = "PROCESSING";

    // Get current ticket version for optimistic locking
    const { data: ticketRes } = await axios.get(`${INVENTORY_URL}/inventory/ticket/0/${ticketID}`);
    const ticket = ticketRes.data;

    // Charge buyer
    let paymentResult;
    try {
      const { data: payRes } = await axios.post(`${PAYMENT_URL}/payment/charge`, {
        buyerID,
        amount: resalePrice,
        currency: listing.currency,
        ticketID,
        idempotencyKey: `resale-${ticketID}-${buyerID}-${Date.now()}`,
      });
      paymentResult = payRes.data;
    } catch (err: any) {
      listing.status = "LISTED"; // revert
      throw new PaymentError(err?.response?.data?.error?.message ?? "Buyer payment failed");
    }

    if (paymentResult.status !== "SUCCESS") {
      listing.status = "LISTED";
      throw new PaymentError("Buyer payment unsuccessful.");
    }

    // Transfer ownership
    await axios.put(`${INVENTORY_URL}/inventory/ticket/${ticketID}/owner`, {
      buyerID,
      version: ticket.version,
    });

    // Trigger seller payout (platform takes a fee)
    const platformFee = resalePrice * 0.05; // 5% platform fee
    await axios.post(`${PAYMENT_URL}/payment/seller-payout`, {
      sellerID: listing.sellerID,
      payoutAmount: resalePrice - platformFee,
      currency: listing.currency,
      ticketID,
    });

    // Publish ticket.resold — QR service and Notification service will consume
    await publish({
      topic: "ticket.resold",
      data: { ticketID, buyerID, newQR: "", eventID: listing.eventID },
    });

    listings.delete(ticketID);

    ok(res, {
      message: "Resale purchase successful",
      ticketID,
      status: "SOLD",
      transactionID: paymentResult.transactionID,
    });
  })
);

app.use(errorHandler);

const PORT = process.env.PORT ?? 3009;
app.listen(PORT, () => console.log(`[resale-ticket-service] Listening on :${PORT}`));

export default app;
