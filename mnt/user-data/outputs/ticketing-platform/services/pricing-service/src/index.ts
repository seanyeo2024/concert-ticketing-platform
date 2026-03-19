// ============================================================
// services/pricing-service/src/index.ts
// Atomic Microservice — manages base and resale pricing
// Replicas: 2
// ============================================================
import express from "express";
import { Pool } from "pg";
import { ok, asyncHandler, errorHandler, NotFoundError } from "../../../shared/utils/http";
import type { PricingInfo } from "../../../shared/types";

const app = express();
app.use(express.json());

const db = new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgres://postgres:postgres@pricing-db:5432/pricing",
});

/**
 * GET /pricing/:eventId
 * Returns base price, resale price, and currency for an event.
 */
app.get(
  "/pricing/:eventId",
  asyncHandler(async (req, res) => {
    const { rows } = await db.query<PricingInfo>(
      `SELECT event_id AS "eventID", base_price AS "basePrice",
              resale_price AS "resalePrice", currency, last_updated AS "lastUpdated"
       FROM pricing WHERE event_id = $1`,
      [req.params.eventId]
    );
    if (!rows[0]) throw new NotFoundError("Pricing info");
    ok(res, rows[0]);
  })
);

/**
 * POST /pricing/get
 * Body: { eventID }
 * Alternative POST endpoint for internal service calls.
 */
app.post(
  "/pricing/get",
  asyncHandler(async (req, res) => {
    const { eventID } = req.body;
    const { rows } = await db.query<PricingInfo>(
      `SELECT event_id AS "eventID", base_price AS "basePrice",
              resale_price AS "resalePrice", currency, last_updated AS "lastUpdated"
       FROM pricing WHERE event_id = $1`,
      [eventID]
    );
    if (!rows[0]) throw new NotFoundError("Pricing info");
    ok(res, rows[0]);
  })
);

/**
 * PUT /pricing/:eventId
 * Body: { basePrice, resalePrice, currency }
 * Admin endpoint — update pricing for an event.
 */
app.put(
  "/pricing/:eventId",
  asyncHandler(async (req, res) => {
    const { basePrice, resalePrice, currency } = req.body;
    const { rows } = await db.query(
      `INSERT INTO pricing (event_id, base_price, resale_price, currency, last_updated)
       VALUES ($1, $2, $3, $4, NOW())
       ON CONFLICT (event_id) DO UPDATE
         SET base_price = $2, resale_price = $3, currency = $4, last_updated = NOW()
       RETURNING *`,
      [req.params.eventId, basePrice, resalePrice, currency]
    );
    ok(res, rows[0]);
  })
);

export async function initDB(): Promise<void> {
  await db.query(`
    CREATE TABLE IF NOT EXISTS pricing (
      event_id      INT          PRIMARY KEY,
      base_price    DECIMAL(10,2) NOT NULL,
      resale_price  DECIMAL(10,2) NOT NULL,
      currency      VARCHAR(10)  NOT NULL DEFAULT 'SGD',
      last_updated  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
  `);
}

app.use(errorHandler);

const PORT = process.env.PORT ?? 3008;
app.listen(PORT, async () => {
  await initDB();
  console.log(`[pricing-service] Listening on :${PORT}`);
});

export default app;
