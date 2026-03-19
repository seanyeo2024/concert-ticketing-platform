// ============================================================
// services/ticket-inventory/src/index.ts
// Scenario 1 & 2 — Ticket Inventory (Atomic Microservice)
// Handles: seat availability, status updates, ownership transfer
// Replicas: 2 | DB: Sharded by EventID
// ============================================================
import express from "express";
import { Pool } from "pg";
import { ok, asyncHandler, errorHandler, NotFoundError, ConflictError } from "../../../shared/utils/http";
import type { Ticket, TicketStatus } from "../../../shared/types";

const app = express();
app.use(express.json());

const db = new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgres://postgres:postgres@inventory-db:5432/ticket_inventory",
});

// ── DB helpers ───────────────────────────────────────────────

async function getTicket(ticketID: number): Promise<Ticket> {
  const { rows } = await db.query<Ticket>(
    `SELECT ticket_id AS "ticketID", owner_id AS "ownerID", event_id AS "eventID",
            ticket_type AS "ticketType", status, version, updated_at AS "updatedAt"
     FROM tickets WHERE ticket_id = $1`,
    [ticketID]
  );
  if (!rows[0]) throw new NotFoundError("Ticket");
  return rows[0];
}

// Optimistic locking — fails if version mismatch (concurrent update detected)
async function updateTicketStatus(
  ticketID: number,
  status: TicketStatus,
  version: number
): Promise<Ticket> {
  const { rows } = await db.query<Ticket>(
    `UPDATE tickets
     SET status = $1, version = version + 1, updated_at = NOW()
     WHERE ticket_id = $2 AND version = $3
     RETURNING ticket_id AS "ticketID", owner_id AS "ownerID", event_id AS "eventID",
               ticket_type AS "ticketType", status, version, updated_at AS "updatedAt"`,
    [status, ticketID, version]
  );
  if (!rows[0]) throw new ConflictError("Ticket was modified by another request. Please retry.");
  return rows[0];
}

// ── Routes ──────────────────────────────────────────────────

/**
 * GET /inventory/ticket/:concertId
 * List available tickets for a concert.
 */
app.get(
  "/inventory/ticket/:concertId",
  asyncHandler(async (req, res) => {
    const { rows } = await db.query<Ticket>(
      `SELECT ticket_id AS "ticketID", ticket_type AS "ticketType", status
       FROM tickets
       WHERE event_id = $1 AND status = 'AVAILABLE'`,
      [req.params.concertId]
    );
    ok(res, rows);
  })
);

/**
 * GET /inventory/ticket/:concertId/:ticketId
 * Get details for a specific ticket.
 */
app.get(
  "/inventory/ticket/:concertId/:ticketId",
  asyncHandler(async (req, res) => {
    const ticket = await getTicket(Number(req.params.ticketId));
    ok(res, ticket);
  })
);

/**
 * PUT /inventory/ticket/:concertId/:ticketId/status
 * Body: { status: TicketStatus, version: number }
 * Update ticket status (with optimistic locking).
 * Used by: Purchase Window, Resale Service
 */
app.put(
  "/inventory/ticket/:concertId/:ticketId/status",
  asyncHandler(async (req, res) => {
    const { status, version } = req.body;
    const ticketID = Number(req.params.ticketId);
    const updated = await updateTicketStatus(ticketID, status, version);
    ok(res, updated);
  })
);

/**
 * PUT /inventory/ticket/:ticketId/owner
 * Body: { buyerID: number, version: number }
 * Transfer ticket ownership (post-payment).
 * Scenario 2B: resale ownership transfer
 */
app.put(
  "/inventory/ticket/:ticketId/owner",
  asyncHandler(async (req, res) => {
    const { buyerID, version } = req.body;
    const ticketID = Number(req.params.ticketId);

    const { rows } = await db.query<Ticket>(
      `UPDATE tickets
       SET owner_id = $1, status = 'SOLD', version = version + 1, updated_at = NOW()
       WHERE ticket_id = $2 AND version = $3
       RETURNING ticket_id AS "ticketID", owner_id AS "ownerID", event_id AS "eventID",
                 ticket_type AS "ticketType", status, version, updated_at AS "updatedAt"`,
      [buyerID, ticketID, version]
    );
    if (!rows[0]) throw new ConflictError("Optimistic lock failed. Ticket was modified.");
    ok(res, rows[0]);
  })
);

// ── Schema ──────────────────────────────────────────────────
export async function initDB(): Promise<void> {
  await db.query(`
    CREATE TABLE IF NOT EXISTS tickets (
      ticket_id   SERIAL PRIMARY KEY,
      owner_id    INT,
      event_id    INT          NOT NULL,
      ticket_type VARCHAR(100) NOT NULL,
      status      VARCHAR(50)  NOT NULL DEFAULT 'AVAILABLE',
      version     INT          NOT NULL DEFAULT 0,
      updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_tickets_event_status ON tickets (event_id, status);
  `);
}

app.use(errorHandler);

const PORT = process.env.PORT ?? 3003;
app.listen(PORT, async () => {
  await initDB();
  console.log(`[ticket-inventory] Listening on :${PORT}`);
});

export default app;
