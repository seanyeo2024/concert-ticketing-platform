// ============================================================
// services/qr-service/src/index.ts
// Atomic Microservice — generates and invalidates QR codes
// Consumes: ticket.confirmed, ticket.resold (AMQP)
// Replicas: 1
// ============================================================
import express from "express";
import { createHash, randomBytes } from "crypto";
import { Pool } from "pg";
import { subscribe, publish, TOPICS } from "../../../shared/utils/amqp";
import { ok, asyncHandler, errorHandler, NotFoundError } from "../../../shared/utils/http";
import type { TicketConfirmedEvent, TicketResoldEvent } from "../../../shared/types";

const app = express();
app.use(express.json());

const db = new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgres://postgres:postgres@qr-db:5432/qr_service",
});

// ── QR generation helpers ────────────────────────────────────

function generateQRHash(ticketID: number, buyerID: number): string {
  const salt = randomBytes(16).toString("hex");
  return createHash("sha256")
    .update(`${ticketID}-${buyerID}-${salt}-${Date.now()}`)
    .digest("hex");
}

async function createQR(ticketID: number, buyerID: number): Promise<string> {
  // Invalidate any existing valid QR for this ticket
  await db.query(
    `UPDATE qr_codes SET status = 'INVALIDATED' WHERE ticket_id = $1 AND status = 'VALID'`,
    [ticketID]
  );

  const qrHash = generateQRHash(ticketID, buyerID);

  await db.query(
    `INSERT INTO qr_codes (ticket_id, qr_hash, status) VALUES ($1, $2, 'VALID')`,
    [ticketID, qrHash]
  );

  return qrHash;
}

// ── Routes ──────────────────────────────────────────────────

/**
 * POST /qr/generate
 * Body: { ticketID, buyerID }
 * Generates a new QR and invalidates the old one.
 */
app.post(
  "/qr/generate",
  asyncHandler(async (req, res) => {
    const { ticketID, buyerID } = req.body;
    const qrHash = await createQR(ticketID, buyerID);
    ok(res, { ticketID, qrHash, status: "VALID" }, 201);
  })
);

/**
 * GET /qr/:ticketId
 * Retrieve the current valid QR for a ticket.
 */
app.get(
  "/qr/:ticketId",
  asyncHandler(async (req, res) => {
    const { rows } = await db.query(
      `SELECT qr_id AS "qrID", ticket_id AS "ticketID", qr_hash AS "qrHash", 
              created_at AS "createdAt", status
       FROM qr_codes WHERE ticket_id = $1 AND status = 'VALID'
       ORDER BY created_at DESC LIMIT 1`,
      [req.params.ticketId]
    );
    if (!rows[0]) throw new NotFoundError("QR code");
    ok(res, rows[0]);
  })
);

/**
 * POST /qr/validate
 * Body: { qrHash }
 * Validate a QR code at the venue gate.
 */
app.post(
  "/qr/validate",
  asyncHandler(async (req, res) => {
    const { qrHash } = req.body;
    const { rows } = await db.query(
      `SELECT ticket_id AS "ticketID", status FROM qr_codes WHERE qr_hash = $1`,
      [qrHash]
    );
    const qr = rows[0];
    ok(res, { valid: !!qr && qr.status === "VALID", ticketID: qr?.ticketID });
  })
);

// ── AMQP consumers ──────────────────────────────────────────

async function startConsumers(): Promise<void> {
  // Consume ticket.confirmed — generate initial QR
  await subscribe(
    [TOPICS.TICKET_CONFIRMED],
    "qr-service-confirmed",
    async (_topic, data) => {
      const { ticketID, buyerID } = data as TicketConfirmedEvent;
      const qrHash = await createQR(ticketID, buyerID);

      // Publish qr.generated for Notification service
      await publish({
        topic: "ticket.resold", // reuse resold shape for notification
        data: { ticketID, buyerID, newQR: qrHash, eventID: (data as TicketConfirmedEvent).eventID },
      });

      console.log(`[qr-service] Generated QR for ticket ${ticketID}`);
    }
  );

  // Consume ticket.resold — regenerate QR for new owner
  await subscribe(
    [TOPICS.TICKET_RESOLD],
    "qr-service-resold",
    async (_topic, data) => {
      const { ticketID, buyerID } = data as TicketResoldEvent;
      const newQR = await createQR(ticketID, buyerID);
      console.log(`[qr-service] Regenerated QR for resold ticket ${ticketID}, newQR: ${newQR}`);
    }
  );
}

// ── Schema ──────────────────────────────────────────────────
export async function initDB(): Promise<void> {
  await db.query(`
    CREATE TABLE IF NOT EXISTS qr_codes (
      qr_id      SERIAL PRIMARY KEY,
      ticket_id  INT          NOT NULL,
      qr_hash    VARCHAR(255) NOT NULL UNIQUE,
      created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      status     VARCHAR(50)  NOT NULL DEFAULT 'VALID'
    );
    CREATE INDEX IF NOT EXISTS idx_qr_ticket ON qr_codes (ticket_id, status);
  `);
}

app.use(errorHandler);

const PORT = process.env.PORT ?? 3007;
app.listen(PORT, async () => {
  await initDB();
  await startConsumers();
  console.log(`[qr-service] Listening on :${PORT}`);
});

export default app;
