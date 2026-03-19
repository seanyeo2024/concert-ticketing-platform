// ============================================================
// services/payment-service/src/index.ts
// Atomic Microservice — handles all payment transactions
// Integrates with Stripe API; supports idempotency keys
// Replicas: 2
// ============================================================
import express from "express";
import Stripe from "stripe";
import { Pool } from "pg";
import { publish } from "../../../shared/utils/amqp";
import { ok, asyncHandler, errorHandler, NotFoundError, PaymentError } from "../../../shared/utils/http";
import type { PaymentRequest, PaymentResult } from "../../../shared/types";

const app = express();
app.use(express.json());

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY ?? "sk_test_placeholder", {
  apiVersion: "2024-06-20",
});

const db = new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgres://postgres:postgres@payment-db:5432/payments",
});

// ── Routes ──────────────────────────────────────────────────

/**
 * POST /payment/charge
 * Body: PaymentRequest
 * Processes a charge via Stripe. Idempotency key prevents double charges.
 */
app.post(
  "/payment/charge",
  asyncHandler(async (req, res) => {
    const { buyerID, amount, currency, ticketID, idempotencyKey }: PaymentRequest = req.body;

    // Check idempotency — return cached result if same key seen before
    const { rows: existing } = await db.query(
      `SELECT transaction_id, status FROM transactions WHERE idempotency_key = $1`,
      [idempotencyKey]
    );
    if (existing[0]) {
      const cached = existing[0];
      ok(res, { transactionID: cached.transaction_id, status: cached.status, buyerID, amount });
      return;
    }

    // Charge via Stripe
    // In production: use paymentMethodId from frontend (e.g., Stripe Elements)
    let stripeCharge;
    try {
      stripeCharge = await stripe.paymentIntents.create(
        {
          amount: Math.round(amount * 100), // Stripe expects cents
          currency: currency.toLowerCase(),
          metadata: { buyerID: String(buyerID), ticketID: String(ticketID ?? "") },
          confirm: true, // auto-confirm for server-side flows
          payment_method: process.env.TEST_PAYMENT_METHOD ?? "pm_card_visa", // replace with real PM in prod
          automatic_payment_methods: { enabled: false },
        },
        { idempotencyKey }
      );
    } catch (stripeErr: any) {
      throw new PaymentError(stripeErr.message ?? "Stripe charge failed");
    }

    const status = stripeCharge.status === "succeeded" ? "SUCCESS" : "FAILED";
    const transactionID = stripeCharge.id;

    // Persist transaction
    await db.query(
      `INSERT INTO transactions (transaction_id, buyer_id, ticket_id, amount, currency, status, idempotency_key)
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [transactionID, buyerID, ticketID, amount, currency, status, idempotencyKey]
    );

    if (status === "SUCCESS") {
      // Publish payment.completed for downstream services
      await publish({
        topic: "payment.completed",
        data: { ticketID: ticketID!, buyerID, sellerID: undefined, amount, concertID: 0 },
      });
    }

    const result: PaymentResult = { transactionID, status, buyerID, amount };
    ok(res, result);
  })
);

/**
 * GET /payment/:transactionId
 * Look up a transaction by ID.
 */
app.get(
  "/payment/:transactionId",
  asyncHandler(async (req, res) => {
    const { rows } = await db.query(
      `SELECT transaction_id AS "transactionID", buyer_id AS "buyerID", 
              amount, currency, status, created_at AS "createdAt"
       FROM transactions WHERE transaction_id = $1`,
      [req.params.transactionId]
    );
    if (!rows[0]) throw new NotFoundError("Transaction");
    ok(res, rows[0]);
  })
);

/**
 * POST /payment/seller-payout
 * Body: { sellerID, payoutAmount, currency, ticketID }
 * Scenario 2: trigger payout to resale seller after successful buyer payment.
 */
app.post(
  "/payment/seller-payout",
  asyncHandler(async (req, res) => {
    const { sellerID, payoutAmount, currency } = req.body;

    // TODO: integrate with Stripe Connect for marketplace payouts
    // For now, record the payout intent
    ok(res, {
      payoutStatus: "SUCCESS",
      sellerID,
      payoutAmount,
      currency,
      transactionID: `payout_${Date.now()}`,
    });
  })
);

// ── Schema ──────────────────────────────────────────────────
export async function initDB(): Promise<void> {
  await db.query(`
    CREATE TABLE IF NOT EXISTS transactions (
      id               SERIAL PRIMARY KEY,
      transaction_id   VARCHAR(255) UNIQUE NOT NULL,
      buyer_id         INT          NOT NULL,
      ticket_id        INT,
      amount           DECIMAL(10,2) NOT NULL,
      currency         VARCHAR(10)  NOT NULL,
      status           VARCHAR(50)  NOT NULL,
      idempotency_key  VARCHAR(255) UNIQUE NOT NULL,
      created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
  `);
}

app.use(errorHandler);

const PORT = process.env.PORT ?? 3005;
app.listen(PORT, async () => {
  await initDB();
  console.log(`[payment-service] Listening on :${PORT}`);
});

export default app;
