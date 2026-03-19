// ============================================================
// services/event-catalog/src/index.ts
// Scenario 1 — Event Catalog (Atomic Microservice)
// Handles: browse/search events, return concert details
// Replicas: 2 | Protocol: HTTP (sync)
// ============================================================
import express from "express";
import { Pool } from "pg";
import { ok, asyncHandler, errorHandler, NotFoundError } from "../../../shared/utils/http";
import type { Concert } from "../../../shared/types";

const app = express();
app.use(express.json());

const db = new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgres://postgres:postgres@event-catalog-db:5432/event_catalog",
});

// ── DB helpers ───────────────────────────────────────────────

async function findAll(): Promise<Concert[]> {
  const { rows } = await db.query<Concert>(
    `SELECT concert_id AS "concertId", name, venue, date, price, currency
     FROM concerts
     ORDER BY date ASC`
  );
  return rows;
}

async function findById(concertId: number): Promise<Concert> {
  const { rows } = await db.query<Concert>(
    `SELECT concert_id AS "concertId", name, venue, date, price, currency
     FROM concerts
     WHERE concert_id = $1`,
    [concertId]
  );
  if (!rows[0]) throw new NotFoundError("Concert");
  return rows[0];
}

// ── Routes ──────────────────────────────────────────────────

/**
 * GET /events
 * List all upcoming events.
 * Returns: Concert[]
 */
app.get(
  "/events",
  asyncHandler(async (_req, res) => {
    const concerts = await findAll();
    ok(res, concerts);
  })
);

/**
 * GET /events/:id
 * Get details for a single concert.
 * Returns: { concertId, name, venue, date, price, currency }
 */
app.get(
  "/events/:id",
  asyncHandler(async (req, res) => {
    const concert = await findById(Number(req.params.id));
    ok(res, concert);
  })
);

// ── Schema (run once on DB init) ────────────────────────────
export async function initDB(): Promise<void> {
  await db.query(`
    CREATE TABLE IF NOT EXISTS concerts (
      concert_id  SERIAL PRIMARY KEY,
      name        VARCHAR(255) NOT NULL,
      venue       VARCHAR(255) NOT NULL,
      date        TIMESTAMPTZ  NOT NULL,
      price       DECIMAL(10,2) NOT NULL,
      currency    VARCHAR(10)  NOT NULL DEFAULT 'SGD',
      created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
  `);
}

// ── Error handler ───────────────────────────────────────────
app.use(errorHandler);

const PORT = process.env.PORT ?? 3002;
app.listen(PORT, async () => {
  await initDB();
  console.log(`[event-catalog] Listening on :${PORT}`);
});

export default app;
